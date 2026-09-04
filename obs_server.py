#!/usr/bin/env python3
"""
Shanktuary Performance Studio - OBS Overlay & Web Configurator Server
-----------------------------------------------------------------------
Runs an HTTP + WebSocket server in a background thread on port 9321.
Based on the proven architecture from ShanktuaryGolf/SwingLab:
  - Serves http://localhost:9321         -> Transparent OBS Browser Source Overlay (overlay.html)
  - Serves http://localhost:9321?edit=true-> Interactive Drag, Drop & Resize Widget Canvas Editor
  - Serves http://localhost:9321?mode=projector -> Fullscreen Floor Projector Mat Mode
  - Serves http://localhost:9321/divot    -> Floor projector: fullscreen divot target only
  - Serves http://localhost:9321/tiles    -> Floor projector: placed metric cards only
  - Serves http://localhost:9321/config   -> Interactive Web Configurator UI (config.html)
  - Serves /api/layout                   -> GET/POST saved layout preferences, widget positions, and divot physical calibration
  - Serves /api/shot                     -> GET last shot payload
  - Broadcasts live shot events to connected OBS browser sources over WebSocket
"""

import base64
import http.server
import json
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from pathlib import Path

from src.analytics.aim import AIM_FILE as _DEFAULT_AIM_FILE
from src.analytics.aim import apply_aim, load_aim_offset
from src.processing.pressure.stance import (
    CalibrationState as StanceCalState,
)

# Stance-width calibration state machine (shift left, then right).
from src.processing.pressure.stance import (
    StanceCalibrator,
)

APP_VERSION = "v1.2.0"
BUILD_NUMBER = "2026.08.24.1"
OBS_PORT = 9321
SCRIPT_DIR = Path(__file__).parent.resolve()

def get_assets_dir():
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        if (base / "assets").exists():
            return base / "assets"
        return base
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
        if (base / "assets").exists():
            return base / "assets"
        if (base / "_internal" / "assets").exists():
            return base / "_internal" / "assets"
        return base
    
    # Source runs. SCRIPT_DIR first so the assets next to obs_server.py win,
    # then cwd for the case where the app is launched from elsewhere.
    #
    # No absolute developer paths here: SPS ships to other Nova owners, and
    # a hardcoded /home/<someone> is dead weight on every other machine --
    # worse, it can silently resolve to a stale checkout on the one machine
    # where it does exist.
    candidates = [
        SCRIPT_DIR / "assets",
        SCRIPT_DIR / "shanktuary-performance-studio" / "assets",
        Path.cwd() / "assets",
        Path.cwd() / "shanktuary-performance-studio" / "assets",
    ]
    
    for path in candidates:
        if path.exists() and (path / "config.html").exists():
            return path

    return SCRIPT_DIR / "assets"

ASSETS_DIR = get_assets_dir()
CONFIG_DIR = Path.home() / ".config" / "shanktuary"
LAYOUT_FILE = CONFIG_DIR / "overlay_layout.json"
# Aim calibration is written by the desktop app; the server only reads it, and
# re-reads when the desktop app tells it the value changed. Module-level so
# tests can point it somewhere harmless.
AIM_FILE = _DEFAULT_AIM_FILE

# Shot history / My Bag live beside the executable (source dir when running from
# source), matching DATA_DIR in shanktuary_performance_studio.py. The desktop
# app owns this file; the server only ever reads it.
if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).parent
else:
    DATA_DIR = SCRIPT_DIR
SESSION_LOG_PATH = DATA_DIR / "shanktuary_session_history.json"

# Default positions, sizes, visibility, and physical divot calibration (1920x1080 canvas)
DEFAULT_LAYOUT = {
    "widgets": {
        "divot": {"x": 30, "y": 30, "w": 250, "h": 250, "visible": True},
        "face_impact": {"x": 290, "y": 30, "w": 250, "h": 180, "visible": True},
        "overhead_path": {"x": 550, "y": 30, "w": 250, "h": 200, "visible": True},
        "side_launch": {"x": 810, "y": 30, "w": 250, "h": 180, "visible": True},
        "spin_axis_3d": {"x": 1070, "y": 30, "w": 250, "h": 180, "visible": True},
        "wbb_heatmap": {"x": 30, "y": 680, "w": 260, "h": 260, "visible": True},
        "wbb_cop_dot": {"x": 300, "y": 680, "w": 180, "h": 180, "visible": True},
        "wbb_balance_bar": {"x": 490, "y": 680, "w": 240, "h": 80, "visible": True},
        "wbb_force_curve": {"x": 740, "y": 680, "w": 240, "h": 120, "visible": False},
        "ball_speed": {"x": 30, "y": 970, "w": 140, "h": 70, "visible": True},
        "club_speed": {"x": 180, "y": 970, "w": 140, "h": 70, "visible": True},
        "carry": {"x": 330, "y": 970, "w": 140, "h": 70, "visible": True},
        "total": {"x": 480, "y": 970, "w": 140, "h": 70, "visible": False},
        "smash": {"x": 630, "y": 970, "w": 140, "h": 70, "visible": True},
        "launch_angle": {"x": 780, "y": 970, "w": 140, "h": 70, "visible": True},
        "push_pull": {"x": 930, "y": 970, "w": 140, "h": 70, "visible": False},
        "total_spin": {"x": 1080, "y": 970, "w": 140, "h": 70, "visible": True},
        "sidespin": {"x": 1230, "y": 970, "w": 140, "h": 70, "visible": False},
        "spin_axis": {"x": 1380, "y": 970, "w": 140, "h": 70, "visible": True},
        "club_path": {"x": 1530, "y": 970, "w": 140, "h": 70, "visible": True},
        "face_angle": {"x": 1680, "y": 970, "w": 140, "h": 70, "visible": True},
        "offline": {"x": 1780, "y": 970, "w": 140, "h": 70, "visible": False},
        "closure_rate": {"x": 1680, "y": 890, "w": 140, "h": 70, "visible": True},
        "apex": {"x": 1530, "y": 890, "w": 140, "h": 70, "visible": True},
        "face_to_path": {"x": 1380, "y": 890, "w": 140, "h": 70, "visible": False},
        "attack_angle": {"x": 1230, "y": 890, "w": 140, "h": 70, "visible": False},
        "dynamic_loft": {"x": 1080, "y": 890, "w": 140, "h": 70, "visible": False},
        "hang_time": {"x": 930, "y": 890, "w": 140, "h": 70, "visible": False},
        "descent_angle": {"x": 780, "y": 890, "w": 140, "h": 70, "visible": False}
    },
    "divot_calibration": {
        "offset_x": 0,
        "offset_y": 0,
        "tilt_deg": 0.0,
        "scale": 1.0
    },
    "styling": {
        "theme": "dark",
        "font_scale": 1.0,
        "auto_fade_sec": 0
    }
}

class OBSState:
    def __init__(self):
        self.latest_shot = None
        self.ws_clients = set()
        self.lock = threading.Lock()
        # Callbacks invoked with (shot_id, trace_frames) once a shot's
        # pressure capture completes. The capture finishes ~3s after impact,
        # on the pressure thread, so this is the only path by which the
        # desktop app can learn about a trace for a shot it has already saved.
        self.trace_listeners = []
        # Serializes writes to each WS client socket so concurrent broadcasts
        # can't interleave partial frames; held only around socket I/O and
        # NEVER while holding self.lock (a stalled client must not wedge the
        # 30 Hz pressure pipeline or the HTTP handlers).
        self.send_lock = threading.Lock()
        # Aim offset, read lazily from disk and cached: every shot broadcast
        # and every /api/shot would otherwise stat+parse a JSON file.
        # invalidate_aim_cache() is how the desktop app publishes a change.
        self._aim_offset = None
        self.ensure_layout_file()

    def invalidate_aim_cache(self):
        """Force the next read to re-load the aim offset from disk.

        Called by the desktop app after a user calibrates, so a mid-session
        recalibration reaches the overlay without restarting OBS.
        """
        with self.lock:
            self._aim_offset = None

    def aim_offset(self):
        """Cached aim offset in degrees; 0.0 when uncalibrated or unreadable."""
        with self.lock:
            cached = self._aim_offset
        if cached is None:
            # load_aim_offset already degrades to 0.0 on a missing or corrupt
            # file, so a lost calibration never stops shots being served.
            cached = load_aim_offset(path=AIM_FILE)
            with self.lock:
                self._aim_offset = cached
        return cached

    def aim_corrected(self, shot):
        """Return ``shot`` with the device's aim error removed.

        The stored/broadcast payload stays native (AGENTS.md), so correction
        happens here, at the read boundary, exactly as in the desktop app.
        """
        if not shot:
            return shot
        offset = self.aim_offset()
        if not offset:
            return shot
        return apply_aim(shot, offset)

    def latest_shot_for_display(self):
        """The most recent shot, aim-corrected, for browser consumers."""
        with self.lock:
            shot = self.latest_shot
        return self.aim_corrected(shot)

    def ensure_layout_file(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if not LAYOUT_FILE.exists():
                LAYOUT_FILE.write_text(json.dumps(DEFAULT_LAYOUT, indent=2))
        except Exception as e:
            print(f"[!] Error creating layout file: {e}")

    def load_layout(self):
        try:
            if LAYOUT_FILE.exists():
                return json.loads(LAYOUT_FILE.read_text())
        except Exception:
            pass
        return DEFAULT_LAYOUT

    def save_layout(self, layout_data):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            LAYOUT_FILE.write_text(json.dumps(layout_data, indent=2))
            self.broadcast({"type": "layout_update", "layout": layout_data})
            return True
        except Exception as e:
            print(f"[!] Error saving layout: {e}")
            return False

    def load_bag(self):
        """Read My Bag from the desktop app's session history.

        The Tkinter process owns the bag and writes it to
        shanktuary_session_history.json; this is a read-only view for the
        browser surfaces. Deliberately NOT cached in OBSState -- the desktop
        app can edit the bag at any time and a stale copy here would silently
        disagree with what the user sees in My Bag.

        Returns {"clubs": [...], "is_left_handed": bool}. An empty list means
        "unknown", and the caller must say so rather than inventing clubs:
        a fabricated bag would send the user's shots to the wrong club stats.
        """
        for path in (SESSION_LOG_PATH, SCRIPT_DIR / "shanktuary_session_history.json"):
            try:
                if not path or not Path(path).exists():
                    continue
                data = json.loads(Path(path).read_text())
                if not isinstance(data, dict):
                    continue
                bag = data.get("bag") or []
                if not isinstance(bag, list):
                    continue
                clubs = []
                for c in bag:
                    if not isinstance(c, dict) or not c.get("name"):
                        continue
                    clubs.append({
                        "name": c.get("name"),
                        "category": c.get("category") or "",
                        "brand": c.get("brand") or "",
                        "model": c.get("model") or "",
                        "loft_deg": c.get("loft_deg"),
                    })
                if clubs:
                    return {
                        "clubs": clubs,
                        "is_left_handed": bool(data.get("is_left_handed", False)),
                    }
            except Exception as e:
                print(f"[!] Error reading bag from {path}: {e}")
        return {"clubs": [], "is_left_handed": False}

    def push_shot(self, shot_data):
        with self.lock:
            self.latest_shot = shot_data

        # Trigger shot impact capture in pressure buffer
        pm = globals().get('pressure_manager')
        if pm is not None and pm.buffer is not None:
            # The Nova payload has no `shotId`, so keying on it alone wrote
            # every trace to "None.json.gz" -- each shot silently overwriting
            # the last, and no shot ever able to find its own trace again.
            from src.processing.pressure import shot_trace_id
            shot_id = shot_trace_id(shot_data)

            def on_pressure_captured(trace_frames):
                # Build an immutable snapshot instead of mutating the shared
                # dict that /api/shot and broadcast may be serializing.
                snapshot = {**shot_data, "pressure_trace": trace_frames}
                with self.lock:
                    if self.latest_shot is shot_data:
                        self.latest_shot = snapshot
                pm.last_shot_trace = trace_frames
                self.broadcast({"type": "shot_pressure", "shot_id": shot_id, "trace": trace_frames})

                # Hand the trace to whoever owns shot history. This fires on
                # the pressure thread ~3s after impact, long after the desktop
                # app has already written the shot to disk, so it cannot
                # simply mutate the stored dict -- see the listener in
                # shanktuary_performance_studio.poll_queue().
                for cb in list(self.trace_listeners):
                    try:
                        cb(shot_id, trace_frames)
                    except Exception as e:
                        print(f"[!] Pressure trace listener error: {e}")

            pm.buffer.trigger_shot_impact(callback=on_pressure_captured)

        # latest_shot above stays native; only the outbound copy is corrected.
        self.broadcast({"type": "shot", "data": self.aim_corrected(shot_data)})

    def broadcast(self, message):
        payload = json.dumps(message)
        frame = self.make_ws_frame(payload)
        # Snapshot the client set under the state lock, but do all socket I/O
        # OUTSIDE it: one stalled client (full TCP buffer in a backgrounded
        # OBS source) must not block push_shot/save_layout/the pressure loop.
        with self.lock:
            clients = list(self.ws_clients)
        dead = set()
        with self.send_lock:
            for client in clients:
                try:
                    client.sendall(frame)
                except Exception:
                    dead.add(client)
        if dead:
            with self.lock:
                self.ws_clients -= dead
            for client in dead:
                try:
                    client.close()
                except OSError:
                    pass

    @staticmethod
    def make_ws_frame(data, opcode=1):
        payload = data.encode("utf-8") if isinstance(data, str) else data
        length = len(payload)
        header = bytearray([0x80 | (opcode & 0x0F)])
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        return bytes(header + payload)

obs_state = OBSState()

CALIBRATION_FILE = os.path.expanduser("~/.shanktuary/wbb_calibration.json")

# Placeholder identifiers the assignment wizard used to invent when a second
# board was not actually enumerated. They are not device paths, and opening a
# backend with one silently fell back to "first board matching the WBB
# VID/PID" -- which is the SAME physical board the left handle already owns.
# The result was an app that reported a configured dual setup while reading
# one board twice. Treat them as "no device".
_PLACEHOLDER_BOARD_IDS = frozenset({
    "Board A", "Board B", b"Board A", b"Board B",
})


def _is_placeholder_board_id(value) -> bool:
    """True when `value` is a wizard placeholder rather than a real device path."""
    if value is None:
        return True
    if isinstance(value, (str, bytes)) and not value:
        return True
    return value in _PLACEHOLDER_BOARD_IDS

# --- Biomechanical Pressure Subsystem Manager ---
class PressureManager:
    """Manages Wii Balance Board hardware, simulator, and 60Hz telemetry broadcasting."""

    def __init__(self):
        self.backend = None
        self.cop_calc = None
        self.torque_calc = None
        self.swing_det = None
        self.buffer = None
        self.tare_offsets = None
        self.is_simulator = False
        self.board_mode = "single"  # "single" or "dual"
        self.assigned_left = None
        self.assigned_right = None
        self.assignment_wizard = None
        self.balance_multiplier = [1.0, 1.0]
        # Stance-width calibration (shift left, then right). Distinct from the
        # 50/50 alignment above: that corrects an uneven left/right SPLIT,
        # this measures the physical DISTANCE between the feet so CoP travel
        # can be reported in mm instead of arbitrary units.
        self.stance_cal = StanceCalibrator()
        self.stance_width_mm = None
        self._alignment_active = False
        self._alignment_start_time = 0.0
        self._alignment_end_time = 0.0
        self._alignment_samples = []
        self._alignment_status_msg = "Idle"
        self.running = False
        self.thread = None
        self.latest_frame = None
        self.last_shot_trace = None
        # Reentrant: several public methods legitimately call one another
        # while holding it (update_assignment_wizard -> start_assignment_wizard,
        # set_board_mode -> _set_simulator_unlocked). A plain Lock deadlocks
        # the calling thread outright on those paths.
        self.lock = threading.RLock()
        self._load_calibration()
        self._init_subsystem()

    def _init_subsystem(self):
        try:
            from src.hardware.pressure import TareOffsets
            from src.processing.pressure import (
                CoPCalculator,
                ShotSynchronizedPressureBuffer,
                SwingDetector,
                TorqueCalculator,
            )
            self.cop_calc = CoPCalculator()
            self.torque_calc = TorqueCalculator()
            self.swing_det = SwingDetector()
            self.buffer = ShotSynchronizedPressureBuffer(capacity=600)
            self.tare_offsets = TareOffsets()
            self.backend = None
            self._wiz_backend_a = None
            self._wiz_backend_b = None
            self._latest_raw_reading = None
            self._last_reconnect_attempt = 0.0
            try:
                # Honour a restored dual assignment. Calling
                # _create_hardware_backend() bare would open a single board
                # even when both are assigned, so the app came up in single
                # mode until something else re-triggered the dual path.
                self._set_simulator_unlocked(self.is_simulator)
            except Exception:
                self.backend = None
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True, name="pressure-worker")
            self.thread.start()
            print("[+] Swing Lab Pressure Subsystem initialized (Hardware Mode / Demo OFF)")
        except Exception as e:
            print(f"[!] Warning: Could not initialize Pressure subsystem: {e}")

    def _loop(self):
        last_broadcast = 0.0
        last_error_log = 0.0
        while self.running:
            try:
                # Snapshot swappable references under the lock so HTTP threads
                # (set_simulator/set_board_mode/wizard) can't close/replace a
                # backend out from under us mid-read.
                with self.lock:
                    backend = self.backend
                    wiz = self.assignment_wizard
                    wiz_a = self._wiz_backend_a
                    wiz_b = self._wiz_backend_b

                # 0. Hardware auto-reconnect if not in simulator mode, no backend open, and wizard not active
                is_wiz_active = bool(wiz and wiz.phase in ("waiting_left", "waiting_right"))
                if not self.is_simulator and not is_wiz_active and (not backend or not backend.is_open):
                    now = time.time()
                    if now - self._last_reconnect_attempt >= 2.0:
                        self._last_reconnect_attempt = now
                        with self.lock:
                            try:
                                # Dual-aware: a bare _create_hardware_backend()
                                # here would silently demote a configured dual
                                # setup to one board after any dropout.
                                self._set_simulator_unlocked(self.is_simulator)
                            except Exception:
                                pass
                            backend = self.backend

                # 1. Wizard multi-board polling. Only a genuine two-backend
                # setup drives the wizard. The old code fell back to splitting
                # ONE board's left/right cells into board_a/board_b, so
                # shifting weight on a single board walked the wizard all the
                # way to "both boards assigned" -- a dual configuration the
                # user did not have.
                if wiz and wiz.phase in ("waiting_left", "waiting_right"):
                    if wiz_a and wiz_b:
                        w_a = wiz.board_a_weight
                        w_b = wiz.board_b_weight
                        rd_a = wiz_a.read()
                        rd_b = wiz_b.read()
                        if rd_a:
                            w_a = rd_a.total_weight
                        if rd_b:
                            w_b = rd_b.total_weight
                        if w_a > 0.0 or w_b > 0.0:
                            self.update_assignment_wizard(w_a, w_b)

                # 2. Standard stream loop
                if backend and backend.is_open:
                    reading = backend.read()
                    if reading:
                        self._latest_raw_reading = reading
                        tared = self.tare_offsets.apply(reading) if self.tare_offsets else reading

                        # Sampling for 4-second stance alignment
                        if self._alignment_active:
                            now_t = time.time()
                            if now_t >= self._alignment_sample_start:
                                if tared.total >= 10.0:
                                    left_w = tared.top_left + tared.bottom_left
                                    right_w = tared.top_right + tared.bottom_right
                                    self._alignment_samples.append((left_w, right_w))
                            if now_t >= self._alignment_end_time:
                                self._finish_stance_alignment()

                        # Apply 50/50 stance balance calibration multipliers
                        if self.balance_multiplier != [1.0, 1.0]:
                            mult_l, mult_r = self.balance_multiplier
                            from src.hardware.pressure.base import SensorReading
                            tared = SensorReading(
                                top_left=tared.top_left * mult_l,
                                bottom_left=tared.bottom_left * mult_l,
                                top_right=tared.top_right * mult_r,
                                bottom_right=tared.bottom_right * mult_r,
                                timestamp=tared.timestamp
                            )
                        
                        # When load is under threshold (< 1.0 kg), emit zero resting frame at center (0,0)
                        if tared.total < 1.0:
                            from src.processing.pressure.cop import CoPSample
                            zero_cop = CoPSample(
                                cop_x=0.0,
                                cop_y=0.0,
                                total_kg=0.0,
                                pct_left=50.0,
                                pct_right=50.0,
                                pct_front=50.0,
                                pct_back=50.0,
                                timestamp=time.time(),
                                raw=tared,
                                left_kg=0.0,
                                right_kg=0.0,
                            )
                            frame = self.buffer.push(zero_cop, torque=0.0, phase="Address")
                            with self.lock:
                                self.latest_frame = frame
                        else:
                            cop = self.cop_calc.compute(tared) if self.cop_calc else None
                            if cop:
                                torque = self.torque_calc.update(cop) if self.torque_calc else 0.0
                                phase = self.swing_det.update(cop).value if self.swing_det else "Address"
                                frame = self.buffer.push(cop, torque=torque, phase=phase)
                                # Drive the stance-width state machine while a
                                # calibration is running.
                                if self.stance_cal.state != StanceCalState.IDLE:
                                    self.stance_cal.update(cop)
                                    if self.stance_cal.state == StanceCalState.DONE:
                                        w = self.stance_cal.stance_width_mm
                                        if w is not None:
                                            with self.lock:
                                                self.stance_width_mm = round(w, 1)
                                            self._save_calibration()
                                with self.lock:
                                    self.latest_frame = frame

                        now = time.time()
                        if now - last_broadcast >= 0.033:  # ~30Hz broadcast rate for smooth UI rendering
                            if self.latest_frame:
                                obs_state.broadcast({"type": "pressure", "data": self.latest_frame})
                            last_broadcast = now
            except Exception as e:
                # Rate-limited logging: real bugs must not vanish silently,
                # but a persistent hardware fault can't be allowed to spam.
                now = time.time()
                if now - last_error_log >= 5.0:
                    last_error_log = now
                    print(f"[!] Pressure worker error: {type(e).__name__}: {e}")
            time.sleep(0.012)

    def _save_calibration(self, filepath=None):
        fp = filepath or CALIBRATION_FILE
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            data = {
                "board_mode": self.board_mode,
                "assigned_left": str(self.assigned_left) if self.assigned_left else None,
                "assigned_right": str(self.assigned_right) if self.assigned_right else None,
                "balance_multiplier": self.balance_multiplier,
                "stance_width_mm": self.stance_width_mm,
            }
            with open(fp, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[+] Saved balance calibration to {fp}")
        except Exception as e:
            print(f"[!] Could not save calibration: {e}")

    def _load_calibration(self, filepath=None):
        fp = filepath or CALIBRATION_FILE
        try:
            if os.path.exists(fp):
                with open(fp, "r") as f:
                    data = json.load(f)
                if "balance_multiplier" in data and isinstance(data["balance_multiplier"], list) and len(data["balance_multiplier"]) == 2:
                    self.balance_multiplier = [float(data["balance_multiplier"][0]), float(data["balance_multiplier"][1])]
                if data.get("stance_width_mm") is not None:
                    self.stance_width_mm = float(data["stance_width_mm"])
                if "board_mode" in data:
                    self.board_mode = data["board_mode"]
                # Restore the physical left/right binding. _save_calibration
                # has always written these, but nothing read them back, so a
                # dual setup silently reverted to unassigned on every launch
                # and the user had to re-run the wizard each session.
                for key, attr in (("assigned_left", "assigned_left"),
                                  ("assigned_right", "assigned_right")):
                    val = data.get(key)
                    if val and not _is_placeholder_board_id(val):
                        setattr(self, attr, val)
                if self.board_mode == "dual" and not (self.assigned_left
                                                      and self.assigned_right):
                    # A dual mode with no usable assignment is just single
                    # mode wearing a dual label.
                    self.board_mode = "single"
                print(f"[+] Loaded balance calibration from {fp}: multipliers={self.balance_multiplier}")
        except Exception as e:
            print(f"[!] Could not load calibration: {e}")

    def start_stance_alignment(self, delay_sec=5.0, duration_sec=4.0):
        with self.lock:
            self._alignment_samples = []
            self._alignment_start_time = time.time()
            self._alignment_sample_start = self._alignment_start_time + delay_sec
            self._alignment_end_time = self._alignment_sample_start + duration_sec
            self._alignment_active = True
            self._alignment_status_msg = f"⏳ Step onto boards & take stance in {delay_sec:.0f}s..."
            return {"status": "started", "delay_sec": delay_sec, "duration_sec": duration_sec}

    def get_alignment_status(self):
        with self.lock:
            now = time.time()
            rem = max(0.0, self._alignment_end_time - now) if self._alignment_active else 0.0
            tot_dur = max(0.01, self._alignment_end_time - self._alignment_start_time) if self._alignment_start_time > 0 else 9.0
            prog = min(1.0, max(0.0, (tot_dur - rem) / tot_dur)) if self._alignment_active else (1.0 if self._alignment_status_msg.startswith("✓") else 0.0)
            
            # Dynamic message update based on phase
            if self._alignment_active:
                if now < self._alignment_sample_start:
                    rem_lead = max(0.1, self._alignment_sample_start - now)
                    msg = f"⏳ Step onto boards & take stance ({rem_lead:.1f}s)..."
                else:
                    rem_samp = max(0.1, self._alignment_end_time - now)
                    msg = f"🎯 Hold stance still... ({rem_samp:.1f}s)"
            else:
                msg = self._alignment_status_msg

            return {
                "active": self._alignment_active,
                "in_lead_in": bool(self._alignment_active and now < self._alignment_sample_start),
                "remaining_sec": round(rem, 1),
                "progress": round(prog, 2),
                "message": msg,
                "multipliers": self.balance_multiplier,
            }

    def _finish_stance_alignment(self):
        with self.lock:
            self._alignment_active = False
            if len(self._alignment_samples) >= 15:
                avg_l = sum(s[0] for s in self._alignment_samples) / len(self._alignment_samples)
                avg_r = sum(s[1] for s in self._alignment_samples) / len(self._alignment_samples)
                if avg_l > 5.0 and avg_r > 5.0:
                    target = (avg_l + avg_r) * 0.5
                    scale_l = target / avg_l
                    scale_r = target / avg_r
                    self.balance_multiplier = [round(scale_l, 4), round(scale_r, 4)]
                    self._save_calibration()
                    self._alignment_status_msg = f"✓ 50/50 Stance Calibrated (L:{self.balance_multiplier[0]:.2f}, R:{self.balance_multiplier[1]:.2f})"
                else:
                    self._alignment_status_msg = "Alignment failed: Under 5kg detected on boards."
            else:
                self._alignment_status_msg = "Alignment failed: Stand still during countdown."

    def tare(self):
        with self.lock:
            from src.hardware.pressure import SensorReading, TareOffsets
            from src.processing.pressure.cop import CoPSample
            if self.buffer is None:
                return False
            if self._latest_raw_reading:
                self.tare_offsets = TareOffsets(
                    top_left=self._latest_raw_reading.top_left,
                    top_right=self._latest_raw_reading.top_right,
                    bottom_left=self._latest_raw_reading.bottom_left,
                    bottom_right=self._latest_raw_reading.bottom_right,
                )
            elif self.latest_frame and "raw_cells" in self.latest_frame:
                rc = self.latest_frame["raw_cells"]
                self.tare_offsets = TareOffsets(
                    top_left=rc[0], top_right=rc[1], bottom_left=rc[2], bottom_right=rc[3]
                )
            else:
                self.tare_offsets = TareOffsets(0.0, 0.0, 0.0, 0.0)

            # Immediately produce a zeroed resting frame at (0,0)
            zero_reading = SensorReading(0.0, 0.0, 0.0, 0.0, timestamp=time.time())
            zero_cop = CoPSample(
                cop_x=0.0,
                cop_y=0.0,
                total_kg=0.0,
                pct_left=50.0,
                pct_right=50.0,
                pct_front=50.0,
                pct_back=50.0,
                timestamp=time.time(),
                raw=zero_reading,
                left_kg=0.0,
                right_kg=0.0,
            )
            frame = self.buffer.push(zero_cop, torque=0.0, phase="Address")
            self.latest_frame = frame
        # Broadcast OUTSIDE self.lock: socket I/O to a stalled client must
        # not hold up the pressure worker or other /api/pressure/* handlers.
        obs_state.broadcast({"type": "pressure", "data": frame})
        return True

    def start_stance_width_calibration(self):
        """Begin the shift-left / shift-right stance-width measurement."""
        with self.lock:
            self.stance_cal.start()
            self.stance_width_mm = None
        return self.get_stance_width_status()

    def cancel_stance_width_calibration(self):
        with self.lock:
            self.stance_cal.reset()
        return self.get_stance_width_status()

    def get_stance_width_status(self):
        """State, instruction text and result for the stance-width flow."""
        with self.lock:
            st = self.stance_cal.state
            return {
                "state": st.name.lower(),
                "active": st not in (StanceCalState.IDLE, StanceCalState.DONE),
                "instruction": self.stance_cal.instruction,
                "stance_width_mm": self.stance_width_mm,
            }

    def _create_hardware_backend(self, device_path=None):
        """Create hardware backend appropriate for host OS (Evdev on Linux, Hid on Windows/macOS).

        Returns None when no board is present. The pressure worker retries every
        2s, so failures here are the NORMAL state for anyone running without a
        balance board -- log the first one and stay quiet after that rather than
        spamming the console twice a second.

        A placeholder id ("Board B") is NOT a device. Opening one used to fall
        through to open-by-VID/PID and hand back the first board found, so a
        dual setup could end up reading the same physical board through two
        handles. Refuse it explicitly instead.
        """
        if device_path is not None and _is_placeholder_board_id(device_path):
            return None
        if sys.platform == "win32":
            try:
                from src.hardware.pressure.hid_backend import HidBackend
                path = device_path.encode("utf-8") if isinstance(device_path, str) else device_path
                b = HidBackend(device_path=path)
                b.open()
                self._backend_error_logged = False
                return b
            except Exception as e:
                if not getattr(self, "_backend_error_logged", False):
                    self._backend_error_logged = True
                    print(f"[!] Balance board not connected ({e}). "
                          f"Retrying quietly in the background; further errors suppressed.")
                return None
        else:
            try:
                from src.hardware.pressure.evdev_backend import EvdevBackend
                b = EvdevBackend(device_path=device_path)
                b.open()
                self._backend_error_logged = False
                return b
            except Exception:
                try:
                    from src.hardware.pressure.hid_backend import HidBackend
                    path = device_path.encode("utf-8") if isinstance(device_path, str) else device_path
                    b = HidBackend(device_path=path)
                    b.open()
                    self._backend_error_logged = False
                    return b
                except Exception as e:
                    if not getattr(self, "_backend_error_logged", False):
                        self._backend_error_logged = True
                        print(f"[!] Balance board not connected ({e}). "
                              f"Retrying quietly in the background; further errors suppressed.")
                    return None

    def _set_simulator_unlocked(self, enabled: bool):
        """Inner logic — caller MUST already hold self.lock."""
        self.is_simulator = enabled
        if self.backend:
            try: self.backend.close()
            except Exception: pass
        if self.is_simulator:
            from src.hardware.pressure import SimulatorBackend
            self.backend = SimulatorBackend()
            try: self.backend.open()
            except Exception: pass
        else:
            try:
                if self.board_mode == "dual" and self.assigned_left and self.assigned_right:
                    from src.hardware.pressure.dual_wbb_backend import DualWbbBackend
                    b_left = self._create_hardware_backend(self.assigned_left)
                    b_right = self._create_hardware_backend(self.assigned_right)
                    if b_left and b_right:
                        self.backend = DualWbbBackend(b_left, b_right)
                    else:
                        self.backend = b_left or b_right
                else:
                    self.backend = self._create_hardware_backend()
            except Exception:
                self.backend = None
        return self.is_simulator

    def set_simulator(self, enabled: bool):
        with self.lock:
            return self._set_simulator_unlocked(enabled)

    def set_board_mode(self, mode: str):
        """Toggle between 'single' and 'dual' board modes."""
        with self.lock:
            if mode not in ("single", "dual"):
                mode = "single"
            self.board_mode = mode
            self._set_simulator_unlocked(self.is_simulator)
            return self.board_mode

    def enumerate_boards(self, max_age_sec: float = 1.0):
        """Return the device paths of every balance board the OS can see.

        This is the honest answer to "how many boards are actually connected",
        and it is what the Setup page shows. A board that is blinking has not
        finished OS-level Bluetooth pairing and will NOT appear here.

        Result is cached briefly: this is polled by the status endpoint and the
        Setup page redraw, and hid.enumerate() is not free.
        """
        now = time.time()
        cached = getattr(self, "_device_scan_cache", None)
        if cached is not None and (now - cached[0]) < max_age_sec:
            return list(cached[1])

        dev_paths = []
        if sys.platform == "win32":
            try:
                from src.hardware.pressure.hid_backend import enumerate_boards
                devs = enumerate_boards()
                dev_paths = [d["path"] for d in devs]
            except Exception:
                pass
        else:
            try:
                from src.hardware.pressure.evdev_backend import (
                    enumerate_board_devices,
                )
                dev_paths = enumerate_board_devices()
            except Exception:
                pass
        result = [p for p in dev_paths if not _is_placeholder_board_id(p)]
        self._device_scan_cache = (now, list(result))
        return result

    def assign_boards(self, left_path, right_path):
        """Explicitly bind physical devices to the left and right foot.

        The step-on wizard infers L/R from the ORDER the user steps, which is
        unrecoverable if they step wrong. This is the direct route: label the
        boards from the Setup list in any order. Persists so the assignment
        survives a restart.
        """
        with self.lock:
            if _is_placeholder_board_id(left_path) or _is_placeholder_board_id(right_path):
                return {"status": "error", "message": "Both boards must be real devices."}
            if str(left_path) == str(right_path):
                return {"status": "error",
                        "message": "Left and right must be different boards."}

            available = {str(p) for p in self.enumerate_boards()}
            for label, path in (("left", left_path), ("right", right_path)):
                if available and str(path) not in available:
                    return {"status": "error",
                            "message": f"The {label} board is no longer connected."}

            self.assigned_left = left_path
            self.assigned_right = right_path
            self.board_mode = "dual"
            if self.assignment_wizard:
                self.assignment_wizard.reset()
            self._set_simulator_unlocked(self.is_simulator)
            self._save_calibration()
            return {
                "status": "ok",
                "assigned_left": str(left_path),
                "assigned_right": str(right_path),
                "connected": bool(self.backend and self.backend.is_open),
            }

    def start_assignment_wizard(self):
        with self.lock:
            from src.hardware.pressure.connection import BoardAssignmentWizard
            
            # Close existing backend so we don't hold exclusive handle on Board 1
            if self.backend:
                try: self.backend.close()
                except Exception: pass
                self.backend = None

            if self._wiz_backend_a:
                try: self._wiz_backend_a.close()
                except Exception: pass
                self._wiz_backend_a = None
            if self._wiz_backend_b:
                try: self._wiz_backend_b.close()
                except Exception: pass
                self._wiz_backend_b = None

            dev_paths = self.enumerate_boards()

            # Dual assignment requires TWO boards. It used to invent a
            # "Board B" placeholder and drive the wizard from one board's
            # left/right CELLS, so shifting weight on a single board would
            # report "both boards assigned" -- a configured dual setup that
            # never existed. Refuse instead of lying.
            if len(dev_paths) < 2 and not self.is_simulator:
                self.assignment_wizard = None
                self._set_simulator_unlocked(self.is_simulator)
                return {
                    "phase": "idle",
                    "is_complete": False,
                    "detected": len(dev_paths),
                    "message": (
                        f"{len(dev_paths)} of 2 boards detected. Pair the second "
                        "board over Bluetooth first — a blinking light means it "
                        "has not finished pairing with this PC."
                    ),
                }

            if len(dev_paths) >= 2:
                b_a_id = dev_paths[0]
                b_b_id = dev_paths[1]
                self._wiz_backend_a = self._create_hardware_backend(b_a_id)
                self._wiz_backend_b = self._create_hardware_backend(b_b_id)
                if not (self._wiz_backend_a and self._wiz_backend_b):
                    # Two devices enumerated but one would not open -- usually
                    # a stale handle. Do not proceed on a single handle.
                    for attr in ("_wiz_backend_a", "_wiz_backend_b"):
                        b = getattr(self, attr)
                        if b:
                            try: b.close()
                            except Exception: pass
                        setattr(self, attr, None)
                    self.assignment_wizard = None
                    self._set_simulator_unlocked(self.is_simulator)
                    return {
                        "phase": "idle",
                        "is_complete": False,
                        "detected": len(dev_paths),
                        "message": ("Both boards are listed but one could not be "
                                    "opened. Reconnect it and try again."),
                    }
            else:
                # Simulator only: no real devices, synthetic ids are fine
                # because nothing will be opened against them.
                b_a_id = "Board A"
                b_b_id = "Board B"
                self._wiz_backend_a = None
                self._wiz_backend_b = None

            self.assignment_wizard = BoardAssignmentWizard(
                board_a=b_a_id,
                board_b=b_b_id,
                threshold=5.0
            )
            self.assignment_wizard.start()
            return self.assignment_wizard.get_status()

    def update_assignment_wizard(self, weight_a: float, weight_b: float):
        with self.lock:
            if not self.assignment_wizard:
                # start_assignment_wizard refuses to run without two real
                # boards and returns a plain status dict, leaving the wizard
                # unset. Report that instead of raising on None.
                status = self.start_assignment_wizard()
                if not self.assignment_wizard:
                    return status
            phase, msg = self.assignment_wizard.update(weight_a, weight_b)
            if phase == "complete" or getattr(phase, "value", phase) == "complete":
                self.assigned_left = self.assignment_wizard.left_board
                self.assigned_right = self.assignment_wizard.right_board
                # Persist, or the whole wizard has to be re-run on every
                # launch: _load_calibration reads these back at startup.
                self._save_calibration()

                # Seamlessly transition wizard backends directly into DualWbbBackend
                if self.board_mode == "dual" and self._wiz_backend_a and self._wiz_backend_b:
                    from src.hardware.pressure.dual_wbb_backend import DualWbbBackend
                    if self.assigned_left == self.assignment_wizard.board_a:
                        b_left = self._wiz_backend_a
                        b_right = self._wiz_backend_b
                    else:
                        b_left = self._wiz_backend_b
                        b_right = self._wiz_backend_a
                    self.backend = DualWbbBackend(b_left, b_right)
                    self._wiz_backend_a = None
                    self._wiz_backend_b = None
                else:
                    if self._wiz_backend_a:
                        try: self._wiz_backend_a.close()
                        except Exception: pass
                        self._wiz_backend_a = None
                    if self._wiz_backend_b:
                        try: self._wiz_backend_b.close()
                        except Exception: pass
                        self._wiz_backend_b = None
                    self._set_simulator_unlocked(self.is_simulator)
            return self.assignment_wizard.get_status()

    def reset_assignment_wizard(self):
        with self.lock:
            if self.assignment_wizard:
                self.assignment_wizard.reset()
            return {"phase": "idle", "message": ""}

    def toggle_demo_swing(self) -> bool:
        with self.lock:
            new_state = not self.is_simulator
            self._set_simulator_unlocked(new_state)
            return new_state

    def trigger_demo_swing(self):
        with self.lock:
            if not self.is_simulator or not self.backend:
                self._set_simulator_unlocked(True)
            elif hasattr(self.backend, "open"):
                self.backend.open()
            return True

    def get_status(self):
        with self.lock:
            wizard_status = self.assignment_wizard.get_status() if self.assignment_wizard else {
                "phase": "idle", "message": "", "is_complete": False
            }
            devices = self.enumerate_boards()
            return {
                "connected": self.backend.is_open if self.backend else False,
                "mode": "simulator" if self.is_simulator else "hardware",
                "board_mode": self.board_mode,
                "is_dual": self.board_mode == "dual",
                "assigned_left": self.assigned_left,
                "assigned_right": self.assigned_right,
                "devices": [str(p) for p in devices],
                "device_count": len(devices),
                "dual_ready": bool(
                    self.board_mode == "dual"
                    and self.assigned_left and self.assigned_right
                    and self.backend is not None
                    and self.backend.__class__.__name__ == "DualWbbBackend"
                ),
                "assignment_wizard": wizard_status,
                "latest": self.latest_frame,
                "tare": {
                    "top_left": self.tare_offsets.top_left if self.tare_offsets else 0.0,
                    "top_right": self.tare_offsets.top_right if self.tare_offsets else 0.0,
                    "bottom_left": self.tare_offsets.bottom_left if self.tare_offsets else 0.0,
                    "bottom_right": self.tare_offsets.bottom_right if self.tare_offsets else 0.0,
                }
            }

pressure_manager = PressureManager()

class OBSHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed_path = self.path.split("?")[0].rstrip("/")
        if not parsed_path:
            parsed_path = "/"

        assets_dir = get_assets_dir()

        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.handle_websocket()
            return

        # All of these serve the same document; overlay.html branches on the
        # path to pick its projector role. /divot is the fullscreen divot
        # target, /tiles is the placed metric cards -- two separate windows
        # so each can be aimed at its own surface. /projector aliases /divot.
        if parsed_path in ["/", "/overlay", "/divot", "/projector", "/tiles"]:
            self.serve_file(assets_dir / "overlay.html", "text/html; charset=utf-8")
        elif parsed_path in ["/config", "/config.html"]:
            self.serve_file(assets_dir / "config.html", "text/html; charset=utf-8")
        elif parsed_path == "/range":
            self.serve_file(assets_dir / "range" / "index.html", "text/html; charset=utf-8")
        elif parsed_path == "/api/layout":
            self.send_json(obs_state.load_layout())
        elif parsed_path == "/api/bag":
            self.send_json(obs_state.load_bag())
        elif parsed_path == "/api/shot":
            # Aim-corrected: the browser overlay must agree with the desktop
            # app's shot table about which way the ball started.
            self.send_json(obs_state.latest_shot_for_display() or {})
        elif parsed_path == "/api/pressure/status":
            self.send_json(pressure_manager.get_status())
        elif parsed_path == "/api/pressure/shot":
            self.send_json({"trace": pressure_manager.last_shot_trace or []})
        elif parsed_path == "/api/pressure/pin":
            try:
                from src.hardware.pressure.bluetooth_windows import (
                    format_mac_display,
                    get_host_bluetooth_mac,
                    mac_has_zero_byte,
                    mac_to_wii_pin,
                    mac_to_wii_pin_display,
                )
                mac = get_host_bluetooth_mac() or ""
                self.send_json({
                    "status": "ok",
                    "host_mac": mac,
                    "host_mac_formatted": format_mac_display(mac) if mac else "",
                    "pin_raw": mac_to_wii_pin(mac) if mac else "",
                    "pin_display": mac_to_wii_pin_display(mac) if mac else "",
                    "has_zero_byte": mac_has_zero_byte(mac) if mac else False,
                    "platform": sys.platform,
                })
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/pressure/mode":
            self.send_json({"board_mode": pressure_manager.board_mode, "is_dual": pressure_manager.board_mode == "dual"})
        elif parsed_path == "/api/pressure/assign":
            wizard_status = pressure_manager.assignment_wizard.get_status() if pressure_manager.assignment_wizard else {"phase": "idle", "message": ""}
            self.send_json(wizard_status)
        elif parsed_path == "/api/pressure/align_stance":
            self.send_json(pressure_manager.get_alignment_status())
        elif parsed_path == "/api/pressure/stance":
            self.send_json(pressure_manager.get_stance_width_status())
        elif parsed_path.startswith("/assets/"):
            self.serve_static(assets_dir, parsed_path[len("/assets/"):])
        elif parsed_path.startswith("/range/"):
            self.serve_static(assets_dir / "range", parsed_path[len("/range/"):])
        elif parsed_path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404, "Not Found")

    def serve_static(self, root, rel_path):
        """Serve a file strictly inside root — rejects path traversal
        (../, encoded variants, absolute paths). The server listens on
        0.0.0.0, so this must never escape the assets directory."""
        from urllib.parse import unquote
        rel_path = unquote(rel_path)
        try:
            root = root.resolve()
            file_path = (root / rel_path).resolve()
            if not file_path.is_relative_to(root):
                self.send_error(403, "Forbidden")
                return
        except (OSError, ValueError):
            self.send_error(400, "Bad Request")
            return
        import mimetypes
        mime, _ = mimetypes.guess_type(file_path)
        if not mime: mime = "application/octet-stream"
        self.serve_file(file_path, mime)

    MAX_POST_BODY = 1024 * 1024  # 1 MB — nothing this API accepts is larger

    def read_post_body(self):
        """Read the POST body with validation. Returns str, or None after an
        error response has already been sent (malformed/oversized length)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json({"status": "error", "message": "bad Content-Length"}, code=400)
            return None
        if length < 0 or length > self.MAX_POST_BODY:
            self.send_json({"status": "error", "message": "body too large"}, code=413)
            return None
        return self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"

    def do_POST(self):
        parsed_path = self.path.split("?")[0].rstrip("/")
        if parsed_path == "/api/layout":
            body = self.read_post_body()
            if body is None:
                return
            try:
                layout_data = json.loads(body)
                if not isinstance(layout_data, dict):
                    raise ValueError("layout must be a JSON object")
                success = obs_state.save_layout(layout_data)
                self.send_json({"status": "ok" if success else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/tare":
            ok = pressure_manager.tare()
            self.send_json({"status": "ok" if ok else "error"})
        elif parsed_path == "/api/pressure/align_stance":
            body = self.read_post_body()
            if body is None:
                return
            dur = 4.0
            try:
                data = json.loads(body)
                dur = float(data.get("duration_sec", 4.0))
            except Exception:
                pass
            res = pressure_manager.start_stance_alignment(duration_sec=dur)
            self.send_json(res)
        elif parsed_path == "/api/pressure/stance":
            body = self.read_post_body()
            if body is None:
                return
            action = "start"
            try:
                action = str(json.loads(body).get("action", "start"))
            except Exception:
                pass
            if action == "cancel":
                self.send_json(pressure_manager.cancel_stance_width_calibration())
            else:
                self.send_json(pressure_manager.start_stance_width_calibration())
        elif parsed_path == "/api/pressure/simulator":
            body = self.read_post_body()
            if body is None:
                return
            try:
                data = json.loads(body)
                enabled = data.get("enabled", True)
                pressure_manager.set_simulator(enabled)
                self.send_json({"status": "ok", "mode": "simulator" if enabled else "hardware"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/open_bt_settings":
            try:
                from src.hardware.pressure.bluetooth_windows import (
                    open_windows_bluetooth_settings,
                )
                ok = open_windows_bluetooth_settings()
                self.send_json({"status": "ok" if ok else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/pressure/mode":
            body = self.read_post_body()
            if body is None:
                return
            try:
                data = json.loads(body)
                mode = data.get("mode", "single")
                new_mode = pressure_manager.set_board_mode(mode)
                self.send_json({"status": "ok", "board_mode": new_mode})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/assign":
            body = self.read_post_body()
            if body is None:
                return
            try:
                data = json.loads(body)
                action = data.get("action", "start")
                if action == "start":
                    status = pressure_manager.start_assignment_wizard()
                elif action == "reset":
                    status = pressure_manager.reset_assignment_wizard()
                elif action == "update":
                    w_a = float(data.get("weight_a", 0.0))
                    w_b = float(data.get("weight_b", 0.0))
                    status = pressure_manager.update_assignment_wizard(w_a, w_b)
                elif action == "set":
                    # Explicit binding: label each physical board directly
                    # instead of inferring L/R from step order.
                    status = pressure_manager.assign_boards(
                        data.get("left"), data.get("right")
                    )
                elif action == "devices":
                    devs = pressure_manager.enumerate_boards(max_age_sec=0.0)
                    status = {"status": "ok",
                              "devices": [str(p) for p in devs],
                              "device_count": len(devs)}
                else:
                    status = {"status": "error", "message": f"Unknown action {action}"}
                self.send_json(status)
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        else:
            self.send_error(404)

    def serve_file(self, filepath, content_type):
        if filepath.exists():
            try:
                data = filepath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404, "Not Found")

    def send_json(self, obj, code=200):
        try:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(500, str(e))

    def handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400)
            return

        import hashlib
        GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_key = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_key)
        self.end_headers()
        self.wfile.flush()

        raw_sock = self.connection
        # Bound sendall so one stalled client can't block broadcasts forever;
        # dead clients get pruned by the broadcast error path.
        try:
            raw_sock.settimeout(2.0)
        except OSError:
            pass

        current_shot = obs_state.latest_shot_for_display()

        init_msg = json.dumps({
            "type": "init",
            "layout": obs_state.load_layout(),
            "data": current_shot
        })
        # Send init BEFORE registering, under send_lock, so no broadcast can
        # arrive ahead of (or interleave with) the init frame.
        with obs_state.send_lock:
            try:
                raw_sock.sendall(obs_state.make_ws_frame(init_msg))
            except Exception:
                return
        with obs_state.lock:
            obs_state.ws_clients.add(raw_sock)

        try:
            while True:
                try:
                    data = raw_sock.recv(1024)
                except socket.timeout:
                    continue  # settimeout(2.0) applies to recv too — idle is fine
                if not data:
                    break
        except Exception:
            pass
        finally:
            with obs_state.lock:
                obs_state.ws_clients.discard(raw_sock)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def start_obs_server(port=None):
    use_port = port or OBS_PORT
    try:
        server = ThreadedHTTPServer(("0.0.0.0", use_port), OBSHTTPRequestHandler)
        print(f"[+] Started OBS Overlay Server on http://localhost:{use_port}")
        print(f"[+] OBS Web Configurator available at http://localhost:{use_port}/config")
        server.serve_forever()
    except Exception as e:
        print(f"[!] Error starting OBS Overlay Server: {e}")

def launch_obs_server_thread(port=None):
    t = threading.Thread(target=start_obs_server, args=(port,), daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    start_obs_server()
