"""open-fp force plates as a pressure backend (src/hardware/pressure/openfp_backend.py).

No hardware and no third-party packages: a fake open-fp board speaks the real
wire format (Engine.IO v4 over WebSocket, "42[event, data]" frames, server
pings) captured from open-fp's own tools/sim/sim_server.py, with the board's
clock deliberately offset from ours so a missing clock mapping cannot pass.
"""
import base64
import hashlib
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import obs_server
from src.hardware.pressure import SensorReading, TareOffsets
from src.hardware.pressure.openfp_backend import (
    GRAVITY,
    ArrivalClock,
    OpenFpBackend,
    OpenFpProtocolError,
    collapse,
    parse_url,
    readings_from_live,
)
from src.processing.pressure import (
    CoPCalculator,
    ShotSynchronizedPressureBuffer,
    SwingDetector,
    TorqueCalculator,
)

BOARD_CLOCK_OFFSET = -5000.0  # board t = our monotonic + this


# --------------------------------------------------------------------------
# Pure decoding
# --------------------------------------------------------------------------

def _row(l1, l2, l3, l4, r1, r2, r3, r4):
    return [v * GRAVITY for v in (l1, l2, l3, l4, r1, r2, r3, r4)]


def test_channels_map_to_toe_and_heel_per_foot():
    # L1/L2 + R1/R2 are toe-side (+y toward the ball), L3/L4 + R3/R4 heel.
    clock = ArrivalClock()
    data = {"t": [10.0], "forces": [_row(1, 2, 3, 4, 5, 6, 7, 8)]}
    (dual,) = readings_from_live(data, clock, arrival_mono=110.0)
    foot = collapse(dual)
    assert foot.top_left == pytest.approx(1 + 2)       # left toe
    assert foot.bottom_left == pytest.approx(3 + 4)    # left heel
    assert foot.top_right == pytest.approx(5 + 6)      # right toe
    assert foot.bottom_right == pytest.approx(7 + 8)   # right heel
    assert foot.total == pytest.approx(36.0)           # newtons -> kg


def test_board_time_is_mapped_onto_local_monotonic():
    clock = ArrivalClock()
    data = {"t": [10.0, 10.005], "forces": [_row(*[1] * 8)] * 2}
    out = readings_from_live(data, clock, arrival_mono=110.010)
    assert out[-1].timestamp == pytest.approx(110.010)
    assert out[0].timestamp == pytest.approx(110.005)


def test_malformed_live_payload_is_rejected():
    clock = ArrivalClock()
    with pytest.raises(OpenFpProtocolError):
        readings_from_live({"t": [1.0, 2.0], "forces": [[0] * 8]}, clock, 5.0)
    with pytest.raises(OpenFpProtocolError):
        readings_from_live({"t": [1.0], "forces": [[0] * 7]}, clock, 5.0)


def test_arrival_clock_uses_the_lower_envelope_of_delays():
    clock = ArrivalClock()
    true_offset = 100.0
    delays = [0.040, 0.012, 0.003, 0.025, 0.060, 0.004]  # network only adds delay
    for i, d in enumerate(delays):
        bt = i * 0.033
        clock.update(bt, bt + true_offset + d)
    assert clock.offset == pytest.approx(true_offset + 0.003)


def test_arrival_clock_window_ages_out_old_minimum():
    clock = ArrivalClock(window_s=1.0)
    clock.update(0.0, 100.0)        # offset 100.0 (lucky fast message)
    for i in range(1, 40):          # later: offset 100.010 steady
        t = i * 0.05
        clock.update(t, 100.010 + t)
    assert clock.offset == pytest.approx(100.010)


def test_parse_url_forms():
    assert parse_url("http://open-fp.local:7000") == ("open-fp.local", 7000)
    assert parse_url("192.168.1.40") == ("192.168.1.40", 7000)
    assert parse_url("box:7070") == ("box", 7070)


# --------------------------------------------------------------------------
# Fake open-fp board over a real socket
# --------------------------------------------------------------------------

class FakeBoard:
    """Minimal open-fp Socket.IO server: handshake, ping, live @ 30 Hz."""

    def __init__(self, samples_per_push=10, kg=(10, 10, 10, 10, 20, 20, 20, 20)):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.samples_per_push = samples_per_push
        self.kg = kg
        self.got_pong = threading.Event()
        self.connections = 0
        self.kick = threading.Event()   # drop the current client
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()
        self.srv.close()

    @staticmethod
    def _frame(text):
        d = text.encode()
        n = len(d)
        if n < 126:
            return bytes([0x81, n]) + d
        if n < 65536:
            return bytes([0x81, 126]) + n.to_bytes(2, "big") + d
        return bytes([0x81, 127]) + n.to_bytes(8, "big") + d

    @staticmethod
    def _recv_exact(c, n):
        out = b""
        while len(out) < n:
            chunk = c.recv(n - len(out))
            if not chunk:
                raise ConnectionError("client went away")  # an OSError
            out += chunk
        return out

    def _read_client_text(self, c):
        h = self._recv_exact(c, 2)
        n = h[1] & 0x7F
        mask = self._recv_exact(c, 4)
        body = self._recv_exact(c, n)
        return bytes(b ^ mask[i % 4] for i, b in enumerate(body)).decode()

    def _serve(self):
        while not self._stop.is_set():
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.connections += 1
            self.kick.clear()
            try:
                self._session(c)
            except OSError:
                pass
            finally:
                c.close()

    def _session(self, c):
        req = b""
        while b"\r\n\r\n" not in req:
            req += c.recv(4096)
        key = [ln.split(b":", 1)[1].strip() for ln in req.split(b"\r\n")
               if ln.lower().startswith(b"sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1(
            key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()).decode()
        c.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        c.sendall(self._frame('0{"sid":"x","upgrades":[],"pingInterval":25000,'
                              '"pingTimeout":20000,"maxPayload":1000000}'))
        assert self._read_client_text(c) == "40"
        c.sendall(self._frame('40{"sid":"y"}'))
        # One server ping up front; the client must answer "3".
        c.sendall(self._frame("2"))
        c.settimeout(1.0)
        assert self._read_client_text(c) == "3"
        self.got_pong.set()
        c.settimeout(None)
        dt = 0.005
        while not self._stop.is_set() and not self.kick.is_set():
            now_board = time.monotonic() + BOARD_CLOCK_OFFSET
            ts = [now_board - dt * (self.samples_per_push - 1 - i)
                  for i in range(self.samples_per_push)]
            payload = {"t": ts, "forces": [_row(*self.kg)] * len(ts),
                       "fz": {"L": [], "R": []}, "flags": 0, "state": "address"}
            c.sendall(self._frame("42" + json.dumps(["live", payload])))
            c.sendall(self._frame("42" + json.dumps(["status", {"rate_hz": 200.0}])))
            time.sleep(dt * self.samples_per_push)


def _wait(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def board():
    b = FakeBoard()
    yield b
    b.stop()


def test_streams_decimated_readings_on_our_clock(board):
    be = OpenFpBackend(f"http://127.0.0.1:{board.port}")
    be.open()
    try:
        assert _wait(lambda: be.is_open), be.last_error
        assert board.got_pong.wait(1.0), "client did not answer the Engine.IO ping"
        time.sleep(0.6)
        got = be.read_all()
        # 200 Hz in -> 66.7 Hz out; ~0.6 s plus whatever queued during connect.
        assert 25 <= len(got) <= 70, len(got)
        ts = [r.timestamp for r in got]
        assert ts == sorted(ts) and len(set(ts)) == len(ts)
        # Mapped onto OUR monotonic clock, not the board's (-5000 s) one.
        assert abs(time.monotonic() - ts[-1]) < 0.25
        assert got[-1].total == pytest.approx(120.0, abs=0.01)
        assert got[-1].top_left == pytest.approx(20.0, abs=0.01)
        assert be.board_status == {"rate_hz": 200.0}
        assert be.protocol_errors == 0
    finally:
        be.close()
    assert not be.is_open and not be.is_running


def test_read_returns_only_the_newest_sample(board):
    be = OpenFpBackend(f"http://127.0.0.1:{board.port}")
    be.open()
    try:
        assert _wait(lambda: be.is_open)
        time.sleep(0.2)
        r = be.read()
        assert isinstance(r, SensorReading)
        assert be.read_all() == [] or len(be.read_all()) <= 3
    finally:
        be.close()


def test_reconnects_by_itself_after_the_board_drops(board):
    be = OpenFpBackend(f"http://127.0.0.1:{board.port}")
    be.RETRY_S = 0.1
    be.open()
    try:
        assert _wait(lambda: be.is_open)
        board.kick.set()
        assert _wait(lambda: be.connects >= 2 and be.is_open, timeout=4.0), be.last_error
        assert board.connections >= 2
    finally:
        be.close()


def test_open_never_blocks_when_the_board_is_off():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here
    be = OpenFpBackend(f"http://127.0.0.1:{port}", connect_timeout=2.0)
    t0 = time.monotonic()
    be.open()
    try:
        assert time.monotonic() - t0 < 0.1
        time.sleep(0.2)
        assert not be.is_open and be.is_running
        assert be.last_error  # refused, recorded, retrying
        assert be.read() is None and be.read_all() == []
    finally:
        t0 = time.monotonic()
        be.close()
        assert time.monotonic() - t0 < 0.5


def test_notify_shot_posts_impact_time_to_the_board():
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            seen.append((self.path, json.loads(self.rfile.read(n))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        be = OpenFpBackend(f"http://127.0.0.1:{srv.server_port}")
        be.notify_shot(1_700_000_000_123.0)
        assert _wait(lambda: seen)
        assert seen[0] == ("/api/events/shot", {"t_unix_ms": 1_700_000_000_123.0})
    finally:
        srv.shutdown()


# --------------------------------------------------------------------------
# PressureManager wiring
# --------------------------------------------------------------------------

class BatchBoard:
    """A backend that delivers samples in batches, like open-fp."""
    SELF_RECONNECTS = True

    def __init__(self):
        self.is_open = True
        self.is_running = True
        self.batches = []
        self.reads = 0

    def read(self):
        raise AssertionError("worker must drain batched backends with read_all()")

    def read_all(self):
        self.reads += 1
        return self.batches.pop(0) if self.batches else []

    def close(self):
        self.is_open = False


def _manager():
    pm = obs_server.PressureManager.__new__(obs_server.PressureManager)
    pm.lock = threading.RLock()
    pm.backend = None
    pm.assignment_wizard = None
    pm._wiz_backend_a = None
    pm._wiz_backend_b = None
    pm._latest_raw_reading = None
    pm._last_reconnect_attempt = 0.0
    pm.is_simulator = False
    pm.pressure_source = "openfp"
    pm.tare_offsets = TareOffsets()
    pm.balance_multiplier = [1.0, 1.0]
    pm._alignment_active = False
    pm.cop_calc = CoPCalculator()
    pm.torque_calc = TorqueCalculator()
    pm.swing_det = SwingDetector()
    pm.buffer = ShotSynchronizedPressureBuffer(capacity=600)
    pm.stance_cal = obs_server.StanceCalibrator()
    pm.latest_frame = None
    pm.running = True
    pm._per_source_cal = {}
    pm._env_source_override = False
    return pm


def test_worker_processes_every_sample_of_a_batch(monkeypatch):
    monkeypatch.setattr(obs_server.obs_state, "broadcast", lambda *_a, **_k: None)
    pm = _manager()
    rebuilt = []
    monkeypatch.setattr(pm, "_set_simulator_unlocked",
                        lambda *_a: rebuilt.append(1), raising=False)
    board = BatchBoard()
    t0 = time.monotonic()
    board.batches = [[SensorReading(20, 20, 20, 20, timestamp=t0 + i * 0.015 + j * 0.005)
                      for j in range(3)] for i in range(5)]
    pm.backend = board
    worker = threading.Thread(target=pm._loop, daemon=True)
    worker.start()
    try:
        assert _wait(lambda: not board.batches and board.reads > 5)
        time.sleep(0.05)
    finally:
        pm.running = False
        worker.join(timeout=2)
    assert len(pm.buffer._ring) == 15
    assert rebuilt == [], "manager rebuilt a backend that reconnects itself"


def test_disconnected_self_reconnecting_backend_is_left_alone(monkeypatch):
    monkeypatch.setattr(obs_server.obs_state, "broadcast", lambda *_a, **_k: None)
    pm = _manager()
    rebuilt = []
    monkeypatch.setattr(pm, "_set_simulator_unlocked",
                        lambda *_a: rebuilt.append(1), raising=False)
    board = BatchBoard()
    board.is_open = False          # board switched off; its thread retries
    pm.backend = board
    worker = threading.Thread(target=pm._loop, daemon=True)
    worker.start()
    time.sleep(0.1)
    pm.running = False
    worker.join(timeout=2)
    assert rebuilt == []


def test_shot_is_forwarded_to_backends_that_want_it():
    pm = _manager()

    class Shooter(BatchBoard):
        def __init__(self):
            super().__init__()
            self.shots = []

        def notify_shot(self, t_unix_ms):
            self.shots.append(t_unix_ms)

    pm.backend = Shooter()
    before = time.time() * 1000
    pm.notify_shot()
    assert len(pm.backend.shots) == 1 and pm.backend.shots[0] >= before
    pm.backend = BatchBoard()      # no hook: silently nothing
    pm.notify_shot()


def test_source_setting_round_trips_through_the_calibration_file(tmp_path, monkeypatch):
    fp = tmp_path / "wbb_calibration.json"
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(fp))
    pm = _manager()
    pm.board_mode = "single"
    pm.assigned_left = pm.assigned_right = None
    pm.stance_width_mm = None
    pm.openfp_url = None
    pm._backend_error_logged = False
    started = []

    class NoNet(OpenFpBackend):
        def open(self):
            started.append((self.host, self.port))

    import src.hardware.pressure.openfp_backend as mod
    monkeypatch.setattr(mod, "OpenFpBackend", NoNet)
    status = pm.set_pressure_source("openfp", "http://10.0.0.9:7000")
    assert status["source"] == "openfp"
    assert started == [("10.0.0.9", 7000)]
    saved = json.loads(fp.read_text())
    assert saved["pressure_source"] == "openfp"
    assert saved["openfp_url"] == "http://10.0.0.9:7000"

    pm2 = _manager()
    pm2.pressure_source, pm2.openfp_url = "wbb", None
    pm2.board_mode = "single"
    pm2.assigned_left = pm2.assigned_right = None
    pm2.stance_width_mm = None
    pm2._load_calibration()
    assert (pm2.pressure_source, pm2.openfp_url) == ("openfp", "http://10.0.0.9:7000")

    with pytest.raises(ValueError):
        pm.set_pressure_source("kinect")
    pm.backend.close()


def test_wii_board_calibration_is_not_applied_to_openfp(tmp_path, monkeypatch):
    """Saved 50/50 multipliers and stance width were measured on Wii boards;
    applying them to calibrated plates skewed every reading (82.5 vs 82.0 kg
    on open-fp's simulator)."""
    fp = tmp_path / "wbb_calibration.json"
    # A file written before open-fp support existed.
    fp.write_text(json.dumps({"board_mode": "single", "balance_multiplier": [0.875, 1.1667],
                              "stance_width_mm": 410.0}))
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(fp))
    import src.hardware.pressure.openfp_backend as mod

    class NoNet(OpenFpBackend):
        def open(self):
            pass

    monkeypatch.setattr(mod, "OpenFpBackend", NoNet)
    pm = _manager()
    pm.pressure_source, pm.openfp_url = "wbb", None
    pm.board_mode = "single"
    pm.assigned_left = pm.assigned_right = None
    pm.stance_width_mm = None
    pm._load_calibration()
    assert pm.balance_multiplier == [0.875, 1.1667] and pm.stance_width_mm == 410.0

    monkeypatch.setattr(pm, "_create_hardware_backend", lambda *_a: None)
    pm.set_pressure_source("openfp", "127.0.0.1:7070")
    assert pm.balance_multiplier == [1.0, 1.0] and pm.stance_width_mm is None
    pm.balance_multiplier = [1.02, 0.98]     # aligned on the plates
    pm.set_pressure_source("wbb")
    assert pm.balance_multiplier == [0.875, 1.1667] and pm.stance_width_mm == 410.0
    pm.set_pressure_source("openfp")
    assert pm.balance_multiplier == [1.02, 0.98]
    pm.backend.close()


def test_env_override_does_not_rewrite_the_saved_source(tmp_path, monkeypatch):
    fp = tmp_path / "wbb_calibration.json"
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(fp))
    pm = _manager()
    pm.board_mode = "single"
    pm.assigned_left = pm.assigned_right = None
    pm.stance_width_mm = None
    pm.pressure_source, pm.openfp_url = "openfp", "http://127.0.0.1:7070"
    pm._env_source_override = True
    pm._saved_source, pm._saved_openfp_url = "wbb", None
    pm._save_calibration()
    saved = json.loads(fp.read_text())
    assert (saved["pressure_source"], saved["openfp_url"]) == ("wbb", None)
