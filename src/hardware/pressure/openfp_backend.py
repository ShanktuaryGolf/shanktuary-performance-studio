"""open-fp force plates (github.com/open-flight/open-fp) as a pressure backend.

open-fp is two aluminium plates with four load cells each, read by an Arduino
UNO Q that serves a Socket.IO feed on the LAN (default ``open-fp.local:7000``).
We are a network CLIENT of that feed; none of open-fp's (AGPL) code is used
here, only its documented wire format:

* Socket.IO v5 / Engine.IO v4 over WebSocket at ``/socket.io/``.
* ``live`` event about every 33 ms, carrying the 200 Hz samples since the last
  push: ``t`` (seconds, the BOARD's monotonic clock), ``forces`` (one list of
  eight calibrated newton values per sample, order L1 L2 L3 L4 R1 R2 R3 R4).
* ``POST /api/events/shot`` with ``{"t_unix_ms": ...}`` marks impact in the
  board's own swing capture.

Channel corners (open-fp ``config.py``): L1/L2 and R1/R2 are the toe-side
cells (+y, toward the ball), L3/L4 and R3/R4 the heel side. The reading is
collapsed exactly like ``DualWbbBackend``: one front and one back value per
foot, so everything downstream (tare, CoP, swing phases, traces) is
unchanged.

Clock: ``t`` means nothing on this PC. ``ArrivalClock`` maps it onto
``time.monotonic()`` with the lower envelope of (arrival - board time): network
delay only ever makes a message LATE, so the smallest offset seen is the best
estimate. The error is the one-way delay of the fastest message in the
window, typically a few ms on a LAN.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import socket
import threading
import time
import urllib.request
from collections import deque
from urllib.parse import urlparse

from .base import BoardBackend, DualPlateReading, SensorReading

DEFAULT_URL = "http://open-fp.local:7000"
GRAVITY = 9.80665  # N per kg-force

# Indices into the 8-value forces row.
_L_TOE, _L_HEEL = (0, 1), (2, 3)
_R_TOE, _R_HEEL = (4, 5), (6, 7)


class OpenFpProtocolError(ValueError):
    pass


def parse_url(url: str) -> tuple[str, int]:
    """'http://host:port' / 'host:port' / 'host' -> (host, port)."""
    url = (url or DEFAULT_URL).strip()
    if "://" not in url:
        url = "http://" + url
    p = urlparse(url)
    if not p.hostname:
        raise ValueError(f"no host in open-fp URL {url!r}")
    return p.hostname, p.port or 7000


class ArrivalClock:
    """Map board-clock seconds onto local time.monotonic() seconds.

    Keeps (arrival, arrival - board_t) pairs for `window_s` and uses the
    minimum offset. A sliding window (rather than an all-time minimum) lets
    slow crystal drift between the two clocks age out.
    """

    def __init__(self, window_s: float = 30.0):
        self.window_s = window_s
        self._pts: deque[tuple[float, float]] = deque()
        self._min_offset: float | None = None

    def reset(self) -> None:
        self._pts.clear()
        self._min_offset = None

    def update(self, board_t_last: float, arrival_mono: float) -> None:
        off = arrival_mono - board_t_last
        # Monotonic deque: drop points that can never be the minimum again.
        while self._pts and self._pts[-1][1] >= off:
            self._pts.pop()
        self._pts.append((arrival_mono, off))
        while self._pts and arrival_mono - self._pts[0][0] > self.window_s:
            self._pts.popleft()
        self._min_offset = self._pts[0][1]

    @property
    def offset(self) -> float | None:
        return self._min_offset

    def to_local(self, board_t: float) -> float:
        if self._min_offset is None:
            raise RuntimeError("ArrivalClock has no samples yet")
        return board_t + self._min_offset


def readings_from_live(data: dict, clock: ArrivalClock, arrival_mono: float,
                       ) -> list[DualPlateReading]:
    """Decode one ``live`` payload into per-sample dual-plate readings (kg)."""
    if not isinstance(data, dict):
        raise OpenFpProtocolError("live payload is not an object")
    ts = data.get("t") or []
    forces = data.get("forces") or []
    if len(ts) != len(forces):
        raise OpenFpProtocolError(f"live: {len(ts)} times vs {len(forces)} force rows")
    if not ts:
        return []
    clock.update(float(ts[-1]), arrival_mono)
    out = []
    for t, row in zip(ts, forces):
        if row is None or len(row) != 8:
            raise OpenFpProtocolError("live: forces row must have 8 values")
        kg = [float(v) / GRAVITY for v in row]
        local_t = clock.to_local(float(t))
        left = SensorReading(top_left=kg[0], top_right=kg[1],
                             bottom_left=kg[3], bottom_right=kg[2],
                             timestamp=local_t)
        right = SensorReading(top_left=kg[4], top_right=kg[5],
                              bottom_left=kg[7], bottom_right=kg[6],
                              timestamp=local_t)
        out.append(DualPlateReading(left=left, right=right, timestamp=local_t,
                                    device_timestamp_us=int(float(t) * 1e6)))
    return out


def _mean_reading(rs: list[SensorReading], ts: float) -> SensorReading:
    n = len(rs)
    return SensorReading(
        top_left=sum(r.top_left for r in rs) / n,
        top_right=sum(r.top_right for r in rs) / n,
        bottom_left=sum(r.bottom_left for r in rs) / n,
        bottom_right=sum(r.bottom_right for r in rs) / n,
        timestamp=ts,
    )


def average_duals(group: list[DualPlateReading]) -> DualPlateReading:
    """Boxcar-average consecutive samples; time = the group's middle sample."""
    mid = group[len(group) // 2]
    return DualPlateReading(
        left=_mean_reading([g.left for g in group], mid.timestamp),
        right=_mean_reading([g.right for g in group], mid.timestamp),
        timestamp=mid.timestamp,
        device_timestamp_us=mid.device_timestamp_us,
    )


def collapse(dual: DualPlateReading) -> SensorReading:
    """Two plates -> the four-value foot reading DualWbbBackend produces."""
    lf, rf = dual.left, dual.right
    return SensorReading(
        top_left=lf.top_left + lf.top_right,
        bottom_left=lf.bottom_left + lf.bottom_right,
        top_right=rf.top_left + rf.top_right,
        bottom_right=rf.bottom_left + rf.bottom_right,
        timestamp=dual.timestamp,
    )


class SocketIOClient:
    """Just enough Socket.IO (EIO4, WebSocket transport, text frames) to
    receive events. Not thread-safe; one reader thread owns it."""

    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock: socket.socket | None = None
        self._buf = b""

    # -- connection ----------------------------------------------------------
    def connect(self) -> None:
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            s.sendall((
                "GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    raise ConnectionError("open-fp closed during handshake")
                buf += chunk
                if len(buf) > 65536:
                    raise OpenFpProtocolError("oversized handshake response")
            head, self._buf = buf.split(b"\r\n\r\n", 1)
            status = head.split(b"\r\n", 1)[0]
            if b" 101 " not in status + b" ":
                raise ConnectionError(f"open-fp refused WebSocket: {status!r}")
            self.sock = s
            opened = self._recv_text()
            if not opened.startswith("0"):
                raise OpenFpProtocolError(f"expected Engine.IO open, got {opened[:40]!r}")
            self.send_text("40")  # Socket.IO connect to the default namespace
            # The server's "40{sid}" ack arrives with the stream; recv_event
            # skips it.
        except BaseException:
            s.close()
            self.sock = None
            raise

    def _live_sock(self) -> socket.socket:
        if self.sock is None:
            raise ConnectionError("open-fp socket is closed")
        return self.sock

    def close(self) -> None:
        s, self.sock = self.sock, None
        if s is None:
            return
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        s.close()

    # -- framing -------------------------------------------------------------
    def send_text(self, text: str) -> None:
        data = text.encode()
        n = len(data)
        if n < 126:
            head = bytes([0x81, 0x80 | n])
        elif n < 65536:
            head = bytes([0x81, 0x80 | 126]) + n.to_bytes(2, "big")
        else:
            head = bytes([0x81, 0x80 | 127]) + n.to_bytes(8, "big")
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self._live_sock().sendall(head + mask + body)

    def _need(self, n: int) -> None:
        while len(self._buf) < n:
            chunk = self._live_sock().recv(65536)
            if not chunk:
                raise ConnectionError("open-fp connection closed")
            self._buf += chunk

    def _recv_frame(self) -> tuple[int, bool, bytes]:
        self._need(2)
        b0, b1 = self._buf[0], self._buf[1]
        fin, opcode, masked, n = bool(b0 & 0x80), b0 & 0x0F, bool(b1 & 0x80), b1 & 0x7F
        i = 2
        if n == 126:
            self._need(4)
            n, i = int.from_bytes(self._buf[2:4], "big"), 4
        elif n == 127:
            self._need(10)
            n, i = int.from_bytes(self._buf[2:10], "big"), 10
        if n > 8 * 1024 * 1024:
            raise OpenFpProtocolError(f"frame too large ({n} B)")
        mask = b""
        if masked:
            self._need(i + 4)
            mask, i = self._buf[i:i + 4], i + 4
        self._need(i + n)
        payload, self._buf = self._buf[i:i + n], self._buf[i + n:]
        if mask:
            payload = bytes(b ^ mask[j % 4] for j, b in enumerate(payload))
        return opcode, fin, payload

    def _recv_text(self) -> str:
        parts: list[bytes] = []
        while True:
            opcode, fin, payload = self._recv_frame()
            if opcode == 0x8:
                raise ConnectionError("open-fp sent WebSocket close")
            if opcode == 0x9:  # WS ping -> pong
                self._send_control(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2, 0x0):
                parts.append(payload)
                if fin:
                    return b"".join(parts).decode("utf-8", errors="replace")

    def _send_control(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload[:125]))
        self._live_sock().sendall(bytes([0x80 | opcode, 0x80 | len(body)]) + mask + body)

    # -- Socket.IO -----------------------------------------------------------
    def recv_event(self) -> tuple[str, object] | None:
        """Next Socket.IO event as (name, data); None for non-event packets."""
        pkt = self._recv_text()
        if pkt == "2":          # Engine.IO ping -> pong, or the server drops us
            self.send_text("3")
            return None
        if pkt.startswith("1") or pkt.startswith("41"):
            raise ConnectionError("open-fp closed the Socket.IO session")
        if pkt.startswith("42"):
            body = pkt[2:]
            # Optional ack id between the type and the JSON array.
            j = 0
            while j < len(body) and body[j].isdigit():
                j += 1
            arr = json.loads(body[j:])
            if isinstance(arr, list) and arr and isinstance(arr[0], str):
                return arr[0], (arr[1] if len(arr) > 1 else None)
        return None


class OpenFpBackend(BoardBackend):
    """Live open-fp plates over the LAN.

    ``open()`` never blocks: it starts a reader thread that connects, streams,
    and reconnects every ``RETRY_S`` until ``close()``. That matters because
    PressureManager calls open() under its lock, and a TCP/mDNS timeout to a
    switched-off board would otherwise stall the UI and HTTP threads.
    Because it reconnects itself (``SELF_RECONNECTS``), the manager must not
    tear it down and rebuild it while it is not ``is_open``.

    ``is_open`` is honest: True only while live data is actually arriving.
    """

    SELF_RECONNECTS = True
    STALE_S = 3.0    # no live message for this long -> not open
    RECV_TIMEOUT_S = 5.0  # silence on the socket -> drop and reconnect
    RETRY_S = 2.0
    # 200 Hz in, 66.7 Hz out. ShotSynchronizedPressureBuffer counts FRAMES
    # (600 ring, 180 post-impact), sized for ~60 Hz; feeding it 200 Hz would
    # quietly shrink every shot window to about a third. Averaging rather than
    # picking every 3rd sample keeps it from aliasing.
    DECIMATE = 3

    def __init__(self, url: str | None = None, connect_timeout: float = 3.0,
                 client_factory=SocketIOClient):
        self.url = url or DEFAULT_URL
        self.host, self.port = parse_url(self.url)
        self.connect_timeout = connect_timeout
        self._client_factory = client_factory
        self._client = None
        self._client_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False
        self._q: queue.Queue[DualPlateReading] = queue.Queue(maxsize=2000)
        self.clock = ArrivalClock()
        self._last_msg = 0.0
        self._last_ts = float("-inf")
        self._last_dual: DualPlateReading | None = None
        self._acc: list[DualPlateReading] = []
        self.last_error: str | None = None
        self.board_status: dict | None = None
        self.messages = 0
        self.protocol_errors = 0
        self.connects = 0

    # -- BoardBackend ----------------------------------------------------------
    def open(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="openfp-reader")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._drop_client()
        t, self._thread = self._thread, None
        # Short join only: close() runs under PressureManager's lock, and a
        # reader stuck in a connect() would hold it for connect_timeout. A
        # late connect sees _stop under _client_lock and closes itself.
        if t is not None and t is not threading.current_thread():
            t.join(timeout=0.2)

    @property
    def is_open(self) -> bool:
        return (self._connected and not self._stop.is_set()
                and time.monotonic() - self._last_msg < self.STALE_S)

    @property
    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive() and not self._stop.is_set()

    def read(self) -> SensorReading | None:
        """Newest sample since the last call; older queued ones are dropped.
        For callers that poll and only want "now" (the BoardBackend contract)."""
        pending = self.read_all()
        return pending[-1] if pending else None

    def read_all(self) -> list[SensorReading]:
        """Every sample queued since the last call, oldest first. The pressure
        worker uses this so a 33 ms batch of samples is not cut to one."""
        out: list[SensorReading] = []
        while True:
            try:
                dual = self._q.get_nowait()
            except queue.Empty:
                break
            self._last_dual = dual
            out.append(collapse(dual))
        return out

    @property
    def last_dual_reading(self) -> DualPlateReading | None:
        return self._last_dual

    # -- shot hook ------------------------------------------------------------
    def notify_shot(self, t_unix_ms: float | None = None) -> None:
        """Tell the board a shot happened so its swing capture labels impact.
        Fire-and-forget on a thread: must never stall the shot path."""
        t_ms = float(t_unix_ms if t_unix_ms is not None else time.time() * 1000.0)
        url = f"http://{self.host}:{self.port}/api/events/shot"

        def post():
            try:
                req = urllib.request.Request(
                    url, data=json.dumps({"t_unix_ms": t_ms}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=2.0).close()
            except Exception as e:  # board off / old firmware: not fatal
                self.last_error = f"shot event: {type(e).__name__}: {e}"

        threading.Thread(target=post, daemon=True, name="openfp-shot").start()

    # -- reader thread --------------------------------------------------------
    def _drop_client(self) -> None:
        with self._client_lock:
            client, self._client = self._client, None
        self._connected = False
        if client is not None:
            client.close()  # unblocks a recv() in the reader thread

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                client = self._client_factory(self.host, self.port,
                                              timeout=self.connect_timeout)
                client.connect()
                if client.sock is not None:
                    client.sock.settimeout(self.RECV_TIMEOUT_S)
                with self._client_lock:
                    if self._stop.is_set():
                        client.close()
                        return
                    self._client = client
                # Fresh session: a restarted board has a new clock, and a
                # half-filled average must not join samples across the gap.
                self.clock.reset()
                self._acc = []
                self._last_ts = float("-inf")
                self.connects += 1
                self._connected = True
                self.last_error = None
                while not self._stop.is_set():
                    ev = client.recv_event()
                    if ev is None:
                        continue
                    name, data = ev
                    if name == "live":
                        self._on_live(data, time.monotonic())
                    elif name == "status" and isinstance(data, dict):
                        self.board_status = data
            except Exception as e:
                if not self._stop.is_set():
                    self.last_error = f"{type(e).__name__}: {e}"
            finally:
                self._drop_client()
            self._stop.wait(self.RETRY_S)

    def _on_live(self, data, arrival: float) -> None:
        self._last_msg = arrival
        self.messages += 1
        try:
            readings = readings_from_live(data, self.clock, arrival)
        except (OpenFpProtocolError, TypeError, ValueError) as e:
            self.protocol_errors += 1
            self.last_error = f"live: {e}"
            return
        for raw in readings:
            self._acc.append(raw)
            if len(self._acc) < self.DECIMATE:
                continue
            r = average_duals(self._acc)
            self._acc = []
            # The envelope can step the offset down by a few ms; never let
            # that make timestamps run backwards inside the ring buffer.
            if r.timestamp <= self._last_ts:
                continue
            self._last_ts = r.timestamp
            try:
                self._q.put_nowait(r)
            except queue.Full:
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                self._q.put_nowait(r)
