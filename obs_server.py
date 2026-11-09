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
  - Serves /api/index                    -> GET Shanktuary Index summary by club
  - Serves /api/club                     -> POST the club selected on the range (must already be in My Bag)
  - Broadcasts live shot events to connected OBS browser sources over WebSocket
    (message types: init, shot, pressure, shot_pressure, layout_update, club)
"""

import base64
import copy
import http.server
import json
import math
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.analytics.aim import AIM_FILE as _DEFAULT_AIM_FILE
from src.analytics.aim import apply_aim, load_aim_offset
from src.processing.pressure.stance import (
    CalibrationState as StanceCalState,
)

# Stance-width calibration state machine (shift left, then right).
from src.processing.pressure.stance import (
    StanceCalibrator,
)
from user_data import HISTORY_NAME, get_data_dir

APP_VERSION = "v1.9.0"
BUILD_NUMBER = "2026.11.08.1"
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

# Shared with the desktop app; only the desktop migrates/writes history.
DATA_DIR = get_data_dir()
SESSION_LOG_PATH = DATA_DIR / HISTORY_NAME

# Default positions, sizes, visibility, and physical divot calibration (1920x1080 canvas)
DEFAULT_LAYOUT = {
    "widgets": {
        "divot": {"x": 30, "y": 30, "w": 250, "h": 250, "visible": True},
        "face_impact": {"x": 290, "y": 30, "w": 250, "h": 180, "visible": True},
        "overhead_path": {"x": 550, "y": 30, "w": 250, "h": 200, "visible": True},
        "side_launch": {"x": 810, "y": 30, "w": 250, "h": 180, "visible": True},
        "spin_axis_3d": {"x": 1070, "y": 30, "w": 250, "h": 180, "visible": True},
        "shanktuary_index": {"x": 1330, "y": 30, "w": 220, "h": 110, "visible": True},
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

# Fresh-install composition from the approved Studio Broadcast concept.
# All other widgets remain available in the configurator. Existing saved
# layouts are loaded unchanged by OBSState; this is not a migration.
STUDIO_BROADCAST_WIDGETS = {
    "carry": {"x": 230, "y": 140, "w": 600, "h": 330, "visible": True},
    "total_spin": {"x": 1080, "y": 140, "w": 650, "h": 330, "visible": True},
    "side_launch": {"x": 90, "y": 560, "w": 1080, "h": 470, "visible": True},
    "wbb_heatmap": {"x": 1210, "y": 560, "w": 650, "h": 370, "visible": True},
    "wbb_balance_bar": {"x": 1210, "y": 940, "w": 650, "h": 90, "visible": True},
}
for _widget_name, _widget in DEFAULT_LAYOUT["widgets"].items():
    _widget["visible"] = _widget_name in STUDIO_BROADCAST_WIDGETS
    if _widget_name in STUDIO_BROADCAST_WIDGETS:
        _widget.update(STUDIO_BROADCAST_WIDGETS[_widget_name])
# Index stays available by default as an established product contract.
DEFAULT_LAYOUT["widgets"]["shanktuary_index"].update(
    x=1570, y=20, w=300, h=100, visible=True
)
DEFAULT_LAYOUT["styling"]["preset"] = "studio-broadcast"

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
        # Club selected on the range (or None). In-process listeners (desktop
        # app) get the name string; browsers get a `club` WS message and the
        # current value on `init` so a late join agrees with the picker.
        self.selected_club = None
        self.club_listeners = []
        # Combine run started from the range (or None). Same contract as the
        # club: in-process listeners get the run dict (None = ended) and apply
        # it on the Tk thread; the desktop app owns stamping and recording.
        self.combine_run = None
        self.combine_listeners = []
        # Serializes writes to each WS client socket so concurrent broadcasts
        # can't interleave partial frames; held only around socket I/O and
        # NEVER while holding self.lock (a stalled client must not wedge the
        # 30 Hz pressure pipeline or the HTTP handlers).
        self.send_lock = threading.Lock()
        # Aim offset, read lazily from disk and cached: every shot broadcast
        # and every /api/shot would otherwise stat+parse a JSON file.
        # invalidate_aim_cache() is how the desktop app publishes a change.
        self._aim_offset = None
        self.layout_lock = threading.RLock()
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

    def _layout_path(self, output):
        if output not in ("overlay", "projection"):
            raise ValueError("output must be overlay or projection")
        return LAYOUT_FILE if output == "overlay" else LAYOUT_FILE.with_name("projection_layout.json")

    def load_layout(self, output="overlay"):
        with self.layout_lock:
            path = self._layout_path(output)
            # Read-only legacy fallback: both surfaces initially look exactly
            # as before. First save freezes that baseline for the floor.
            if not path.exists() and output == "projection":
                path = LAYOUT_FILE
            try:
                if path.exists():
                    return json.loads(path.read_text())
            except Exception:
                pass
            return copy.deepcopy(DEFAULT_LAYOUT)

    @staticmethod
    def _merge_layout(base, draft, latest):
        result = copy.deepcopy(latest) if isinstance(latest, dict) else {}
        for key, value in draft.items():
            if key in base and value == base[key]:
                continue
            result[key] = (OBSState._merge_layout(
                base.get(key, {}) if isinstance(base.get(key), dict) else {},
                value, result.get(key, {})) if isinstance(value, dict)
                else copy.deepcopy(value))
        return result

    @staticmethod
    def _write_layout(path, layout):
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(layout, indent=2))
        temporary.replace(path)

    def save_layout(self, layout_data, output="overlay", base=None):
        try:
            with self.layout_lock:
                path = self._layout_path(output)
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                floor = self._layout_path("projection")
                if not floor.exists():
                    # Fail closed on corrupt legacy data, rather than silently
                    # replacing a user's calibration with factory defaults.
                    legacy = json.loads(LAYOUT_FILE.read_text()) if LAYOUT_FILE.exists() else copy.deepcopy(DEFAULT_LAYOUT)
                    self._write_layout(floor, legacy)
                if base is not None:
                    layout_data = self._merge_layout(base, layout_data, self.load_layout(output))
                self._write_layout(path, layout_data)
            self.broadcast({"type": "layout_update", "output": output, "layout": layout_data})
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

    def set_selected_club(self, club):
        """Validate and apply a range club selection.

        Returns ``(payload, http_code)``. Unknown or malformed names are
        rejected with 400 and **do not** change state, notify listeners, or
        broadcast — a bad payload must not move the desktop app's club.
        """
        if not isinstance(club, str) or not club.strip():
            return (
                {"status": "error", "message": "club must be a non-empty string"},
                400,
            )
        club = club.strip()
        names = {c.get("name") for c in self.load_bag().get("clubs", []) if c.get("name")}
        if club not in names:
            return (
                {"status": "error", "message": "club not in bag"},
                400,
            )
        with self.lock:
            self.selected_club = club
        for cb in list(self.club_listeners):
            try:
                cb(club)
            except Exception as e:
                print(f"[!] Club listener error: {e}")
        self.broadcast({"type": "club", "club": club})
        return {"status": "ok", "club": club}, 200

    def _read_history(self):
        """Session history dict from disk, or {} -- never cached (see load_bag)."""
        for path in (SESSION_LOG_PATH, SCRIPT_DIR / "shanktuary_session_history.json"):
            try:
                if path and Path(path).exists():
                    data = json.loads(Path(path).read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[!] Could not read session history: {e}")
        return {}

    def combine_status(self):
        """GET /api/combine: protocol from the bag, the live run scored from the
        saved session shots, and the recorded history summary."""
        from src.analytics import combine

        data = self._read_history()
        bag = data.get("bag") or []
        protocol = combine.protocol_for_bag(bag if isinstance(bag, list) else [])
        with self.lock:
            run = self.combine_run
        result = None
        if run:
            shots = []
            for sess in data.get("sessions") or []:
                if isinstance(sess, dict) and (sess.get("id") or sess.get("name")) == run.get("session_id"):
                    shots = [x for x in (sess.get("shots") or []) if isinstance(x, dict)]
            result = combine.score(run["stations"], shots,
                                   is_left_handed=bool(data.get("is_left_handed", False)))
        try:
            history = combine.summary(combine.load(Path(SESSION_LOG_PATH).parent / combine.FILE_NAME))
        except Exception:
            history = None
        return {"active": run is not None, "run": run, "result": result,
                "protocol": protocol, "history": history}

    def set_combine(self, action):
        """POST /api/combine {"action": "start"|"end"} -> (payload, code)."""
        from src.analytics import combine

        if action == "start":
            data = self._read_history()
            bag = data.get("bag") or []
            proto = combine.protocol_for_bag(bag if isinstance(bag, list) else [])
            if not proto["stations"]:
                return {"status": "error", "message": proto["reason"] or "Combine needs more clubs"}, 400
            sessions = [x for x in (data.get("sessions") or []) if isinstance(x, dict)]
            sess = sessions[-1] if sessions else {}
            run = {"stations": [dict(x) for x in proto["stations"]],
                   "session_id": sess.get("id") or sess.get("name")}
        elif action == "end":
            run = None
        else:
            return {"status": "error", "message": "action must be start or end"}, 400
        with self.lock:
            self.combine_run = run
        for cb in list(self.combine_listeners):
            try:
                cb(run)
            except Exception as e:
                print(f"[!] Combine listener error: {e}")
        self.broadcast({"type": "combine", "active": run is not None, "run": run})
        return {"status": "ok", "active": run is not None, "run": run}, 200

    def load_index(self):
        """Read shots from session history and compute the player shanktuary index.

        Pure calculation via player_shanktuary_index(); reads session history from
        disk rather than caching in OBSState so any desktop edits or new shots
        are immediately visible.
        """
        paths = [SESSION_LOG_PATH]
        default_path = DATA_DIR / "shanktuary_session_history.json"
        if SESSION_LOG_PATH == default_path and SCRIPT_DIR / "shanktuary_session_history.json" != default_path:
            paths.append(SCRIPT_DIR / "shanktuary_session_history.json")

        for path in paths:
            if not path:
                continue
            path_obj = Path(path)
            if not path_obj.exists():
                continue
            try:
                data = json.loads(path_obj.read_text(encoding="utf-8"))
                shots = []
                is_left_handed = False
                if isinstance(data, dict):
                    is_left_handed = bool(data.get("is_left_handed", False))
                    sessions = data.get("sessions") or []
                elif isinstance(data, list):
                    sessions = data
                else:
                    sessions = []
                for sess in sessions:
                    if isinstance(sess, dict):
                        sess_shots = sess.get("shots")
                        if isinstance(sess_shots, list):
                            shots.extend(sess_shots)
                if not shots:
                    return {}
                from src.analytics import player_shanktuary_index
                summary = player_shanktuary_index(shots, is_left_handed=is_left_handed)
                res = dict(summary)
                for club, c_data in summary.get("clubs", {}).items():
                    if club not in res:
                        res[club] = c_data
                return res
            except Exception as e:
                print(f"[!] Error computing index from {path}: {e}")
                return {}
        return {}

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
            pm.notify_shot()

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


def board_id_to_text(value) -> str:
    """Board id -> a string that can round-trip back to the original bytes.

    hidapi hands out device paths as BYTES on Windows. Calling str() on them
    embeds the repr -- b'\\\\?\\HID#...' becomes the literal 7 characters
    "b'\\\\?\\H..." -- and re-encoding that produces a path no device has. The
    board then "could not be opened" forever while sitting there paired and
    healthy, because the saved calibration had been corrupted on write.

    Decode instead of repr. Windows HID paths are ASCII; latin-1 is used so
    any byte value survives rather than raising.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return str(value)


def board_id_to_bytes(value):
    """Board id -> the bytes hidapi's open_path() expects.

    Also repairs ids already corrupted by the old str(bytes) write, so users
    who ran an affected build are not stuck with an unusable calibration file
    they'd have to delete by hand.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    text = str(value)
    # Undo a Python bytes repr that was written to disk as text.
    if len(text) >= 3 and text[:2] in ("b'", 'b"') and text[-1] == text[1]:
        try:
            import ast
            recovered = ast.literal_eval(text)
            if isinstance(recovered, bytes):
                return recovered
        except (ValueError, SyntaxError):
            pass
    return text.encode("latin-1", errors="replace")

# --- Biomechanical Pressure Subsystem Manager ---
class PressureManager:
    """Manages Wii Balance Board hardware, simulator, and 60Hz telemetry broadcasting."""

    # Class-level defaults so a manager built without __init__ (tests do
    # this) or one whose init failed part-way still behaves as Wii-boards-only.
    pressure_source = "wbb"
    openfp_url = None
    _env_source_override = False
    _saved_source = "wbb"
    _saved_openfp_url = None
    WIZARD_SAMPLE_MAX_AGE = 1.5
    WIZARD_RETRY_DELAY = 3.0
    WIZARD_MAX_RETRIES = 2

    def __init__(self):
        self.backend = None
        self.cop_calc = None
        self.torque_calc = None
        self.swing_det = None
        self.buffer = None
        self.tare_offsets = None
        self.is_simulator = False
        self.board_mode = "single"  # "single" or "dual"
        # Which hardware feeds the pipeline: "wbb" (Wii Balance Boards, set up
        # by board_mode/assignment) or "openfp" (open-fp plates on the LAN,
        # always two plates, nothing to pair or assign).
        self.pressure_source = "wbb"
        self.openfp_url = None
        # 50/50 multipliers and stance width describe the HARDWARE they were
        # measured on: Wii boards' uneven split must not be applied to
        # calibrated open-fp plates. Kept per source; the live attributes
        # (balance_multiplier, stance_width_mm) hold the active source's.
        self._per_source_cal = {}
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
        # SPS_OPENFP_URL selects open-fp for this run without touching the
        # saved setting (handy for pointing at open-fp's desktop simulator).
        env_url = os.environ.get("SPS_OPENFP_URL", "").strip()
        self._env_source_override = bool(env_url)
        self._saved_source = self.pressure_source
        self._saved_openfp_url = self.openfp_url
        if env_url:
            self.openfp_url = env_url
            self._activate_source_cal("openfp")
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
            if os.environ.get("SPS_UI_PREVIEW") == "1":
                print("[preview] Pressure hardware disabled; no readings simulated")
                return
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

                # 0. Hardware auto-reconnect if not in simulator mode, no backend open, and wizard not active
                is_wiz_active = bool(wiz and wiz.phase in ("waiting_left", "waiting_right"))
                # A backend that reconnects on its own thread (open-fp) is
                # left alone while that thread runs: rebuilding it every 2 s
                # would abort each connection attempt before it could land.
                self_managed = bool(
                    backend is not None
                    and getattr(type(backend), "SELF_RECONNECTS", False)
                    and getattr(backend, "is_running", False))
                if (not self.is_simulator and not is_wiz_active and not self_managed
                        and (not backend or not backend.is_open)):
                    now = time.time()
                    if now - self._last_reconnect_attempt >= 2.0:
                        self._last_reconnect_attempt = now
                        with self.lock:
                            current = self.backend
                            current_wiz = self.assignment_wizard
                            wizard_now = bool(current_wiz and current_wiz.phase in
                                              ("waiting_left", "waiting_right"))
                            managed_now = bool(current is not None and
                                getattr(type(current), "SELF_RECONNECTS", False) and
                                getattr(current, "is_running", False))
                            # A UI action may have started assignment or replaced
                            # the backend since the snapshot. Never close it on
                            # the strength of that stale reconnect decision.
                            if (not self.is_simulator and not wizard_now and not managed_now
                                    and (not current or not current.is_open)):
                                try:
                                    self._set_simulator_unlocked(self.is_simulator)
                                except Exception:
                                    pass
                            backend = self.backend

                # Assignment owns its two readers until completion/cancellation.
                # It validates freshness and exposes bounded recovery failures.
                if is_wiz_active:
                    self._poll_assignment_wizard()

                # 2. Standard stream loop
                if backend and backend.is_open:
                    # The read MUST happen under the lock. The UI thread
                    # (start_assignment_wizard, set_board_mode, reopen...)
                    # closes self.backend under this lock; hidapi's native
                    # read runs without the GIL, so closing the handle while
                    # we are inside read() is a use-after-free that kills the
                    # whole process with no traceback. Reads are non-blocking,
                    # so holding the lock here costs microseconds.
                    with self.lock:
                        if self.backend is backend and backend.is_open:
                            # Batched sources (open-fp delivers ~3 samples per
                            # 33 ms push) hand over everything queued; one
                            # read() per pass would cut them to the push rate.
                            # Looked up on the CLASS so a Mock test double
                            # (which grows any attribute) keeps using read().
                            drain = getattr(type(backend), "read_all", None)
                            readings = (drain(backend) if drain
                                        else [backend.read()])
                        else:
                            readings = []
                    for reading in readings:
                        if not reading:
                            continue
                        self._latest_raw_reading = reading
                        tared = self.tare_offsets.apply(reading) if self.tare_offsets else reading

                        # Alignment consumes genuine, fresh samples before
                        # balance multipliers, never a retained display frame.
                        self._advance_stance_alignment(tared, source_backend=backend)

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
                                # Sensor clock, like every loaded frame --
                                # never wall clock (see board_is_streaming).
                                timestamp=tared.timestamp,
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
                # Also run when read() returns None or no backend is open.
                # A stopped stream must not leave a completed countdown active.
                self._advance_stance_alignment()
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
                "assigned_left": board_id_to_text(self.assigned_left) if self.assigned_left else None,
                "assigned_right": board_id_to_text(self.assigned_right) if self.assigned_right else None,
                "balance_multiplier": self.balance_multiplier,
                "stance_width_mm": self.stance_width_mm,
                # An SPS_OPENFP_URL run must not rewrite the saved choice.
                "pressure_source": (self._saved_source
                                    if getattr(self, "_env_source_override", False)
                                    else self.pressure_source),
                "openfp_url": (self._saved_openfp_url
                               if getattr(self, "_env_source_override", False)
                               else self.openfp_url),
                "calibration_by_source": {
                    **getattr(self, "_per_source_cal", {}),
                    self.pressure_source: {
                        "balance_multiplier": self.balance_multiplier,
                        "stance_width_mm": self.stance_width_mm,
                    },
                },
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
                if data.get("openfp_url"):
                    self.openfp_url = str(data["openfp_url"])
                # Files written before open-fp support hold only top-level
                # values, which were measured on Wii boards.
                by_source = data.get("calibration_by_source")
                if not isinstance(by_source, dict):
                    by_source = {"wbb": {"balance_multiplier": self.balance_multiplier,
                                         "stance_width_mm": self.stance_width_mm}}
                self._per_source_cal = {
                    k: dict(v) for k, v in by_source.items()
                    if k in ("wbb", "openfp") and isinstance(v, dict)}
                src_saved = data.get("pressure_source")
                if src_saved not in ("wbb", "openfp"):
                    src_saved = "wbb"
                active = self._per_source_cal.get(src_saved, {})
                bm = active.get("balance_multiplier")
                if isinstance(bm, list) and len(bm) == 2:
                    self.balance_multiplier = [float(bm[0]), float(bm[1])]
                else:
                    self.balance_multiplier = [1.0, 1.0]
                sw = active.get("stance_width_mm")
                self.stance_width_mm = float(sw) if sw is not None else None
                self.pressure_source = src_saved
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

    def _calibration_configuration(self):
        """Identify the source/assignment that a calibration was sampled from."""
        return (getattr(self, "pressure_source", "wbb"), getattr(self, "board_mode", "single"),
                bool(getattr(self, "is_simulator", False)),
                getattr(self, "openfp_url", None) if getattr(self, "pressure_source", "wbb") == "openfp" else None,
                board_id_to_text(getattr(self, "assigned_left", None)),
                board_id_to_text(getattr(self, "assigned_right", None)))

    def start_stance_alignment(self, delay_sec=5.0, duration_sec=4.0):
        delay_sec, duration_sec = float(delay_sec), float(duration_sec)
        if not (math.isfinite(delay_sec) and delay_sec >= 0
                and math.isfinite(duration_sec) and duration_sec > 0):
            raise ValueError("Alignment requires a nonnegative delay and positive duration")
        with self.lock:
            self._alignment_configuration = self._calibration_configuration()
            self._alignment_backend = self.backend
            self._alignment_delay_sec = delay_sec
            self._alignment_duration_sec = duration_sec
            self._alignment_samples = []
            self._alignment_last_sample_timestamp = None
            self._alignment_hold_start = None
            self._alignment_start_time = time.time()
            self._alignment_sample_start = self._alignment_start_time + delay_sec
            self._alignment_end_time = self._alignment_sample_start + duration_sec
            self._alignment_active = True
            self._alignment_paused = False
            self._alignment_status_msg = f"⏳ Step onto boards & take stance in {delay_sec:.0f}s..."
            self._advance_stance_alignment()
            return {"status": "started", "delay_sec": delay_sec, "duration_sec": duration_sec}

    def _pause_stance_alignment_unlocked(self, message):
        """Discard only the unfinished hold, preserving saved calibration."""
        self._alignment_paused = True
        self._alignment_samples = []
        self._alignment_last_sample_timestamp = None
        self._alignment_hold_start = None
        self._alignment_status_msg = message

    def _alignment_live_unlocked(self):
        backend = self.backend
        if not backend or not backend.is_open:
            return False
        diagnostic_method = getattr(type(backend), "get_diagnostics", None)
        if diagnostic_method:
            try:
                detail = diagnostic_method(backend)
            except Exception:
                return False
            if (detail.get("ready") is False or detail.get("recovery_blocked")
                    or detail.get("calibration_status") == "unavailable"):
                return False
        reading = self._latest_raw_reading
        if reading is None or not math.isfinite(reading.timestamp):
            return False
        return 0 <= time.monotonic() - reading.timestamp <= self.WIZARD_SAMPLE_MAX_AGE

    def _advance_stance_alignment(self, reading=None, *, source_backend=None):
        """Watch collection even without samples; only new data can finish it."""
        with self.lock:
            if not self._alignment_active:
                return
            if self._alignment_configuration != self._calibration_configuration():
                self._alignment_active = False
                self._alignment_samples = []
                self._alignment_status_msg = "Alignment cancelled: board configuration changed."
                return
            if source_backend is not None and source_backend is not self.backend:
                self._pause_stance_alignment_unlocked(
                    "Reader changed. Waiting for live data to restart the full hold.")
                return
            if self._alignment_backend is not self.backend:
                self._alignment_backend = self.backend
                self._pause_stance_alignment_unlocked(
                    "Reader changed. Waiting for live data to restart the full hold.")
            if not self._alignment_live_unlocked():
                self._pause_stance_alignment_unlocked(
                    "Readings paused. Waiting for live board data; the full hold will restart.")
                return
            if reading is None:
                # Never persist old samples merely because the timer expired.
                return
            now = time.time()
            stamp = reading.timestamp
            if (not math.isfinite(stamp)
                    or not 0 <= time.monotonic() - stamp <= self.WIZARD_SAMPLE_MAX_AGE):
                self._pause_stance_alignment_unlocked(
                    "Readings paused. Waiting for live board data; the full hold will restart.")
                return
            previous = self._alignment_last_sample_timestamp
            if previous is not None:
                if stamp <= previous:
                    return  # duplicate/stale samples cannot fill or finish a hold
                if stamp - previous > self.WIZARD_SAMPLE_MAX_AGE:
                    self._pause_stance_alignment_unlocked(
                        "Readings interrupted. The full hold will restart.")
            if self._alignment_paused:
                self._alignment_paused = False
                self._alignment_start_time = now
                self._alignment_sample_start = now + self._alignment_delay_sec
                self._alignment_end_time = self._alignment_sample_start + self._alignment_duration_sec
            self._alignment_last_sample_timestamp = stamp
            if now < self._alignment_sample_start:
                return
            left_w = reading.top_left + reading.bottom_left
            right_w = reading.top_right + reading.bottom_right
            if not (math.isfinite(left_w) and math.isfinite(right_w)
                    and left_w > 5.0 and right_w > 5.0):
                self._pause_stance_alignment_unlocked(
                    "Waiting for load on both boards; the full hold will restart.")
                return
            if self._alignment_hold_start is None:
                self._alignment_hold_start = stamp
                self._alignment_end_time = now + self._alignment_duration_sec
            self._alignment_samples.append((left_w, right_w))
            if stamp - self._alignment_hold_start >= self._alignment_duration_sec:
                self._finish_stance_alignment()

    def cancel_stance_alignment(self):
        """Discard an interrupted sample without changing saved calibration."""
        with self.lock:
            if self._alignment_active:
                self._alignment_active = False
                self._alignment_samples = []
                self._alignment_status_msg = "Alignment cancelled"
        return self.get_alignment_status()

    def get_alignment_status(self):
        with self.lock:
            # A read-only status request may invalidate an unsafe collection,
            # but can never resume it or save calibration without new samples.
            self._advance_stance_alignment()
            now = time.time()
            paused = bool(self._alignment_active and getattr(self, "_alignment_paused", False))
            rem = max(0.0, self._alignment_end_time - now) if self._alignment_active else 0.0
            tot_dur = max(0.01, self._alignment_end_time - self._alignment_start_time) if self._alignment_start_time > 0 else 9.0
            prog = min(0.99, max(0.0, (tot_dur - rem) / tot_dur)) if self._alignment_active else (1.0 if self._alignment_status_msg.startswith("✓") else 0.0)
            if paused:
                msg, rem, prog = self._alignment_status_msg, None, 0.0
            elif self._alignment_active:
                if now < self._alignment_sample_start:
                    msg = f"⏳ Step onto boards & take stance ({self._alignment_sample_start - now:.1f}s)..."
                elif rem > 0:
                    msg = f"🎯 Hold stance still... ({rem:.1f}s)"
                else:
                    msg, rem = "Waiting for a fresh reading to finish the hold...", None
            else:
                msg = self._alignment_status_msg
            return {
                "active": self._alignment_active,
                "paused": paused,
                "in_lead_in": bool(self._alignment_active and not paused and now < self._alignment_sample_start),
                "remaining_sec": round(rem, 1) if rem is not None else None,
                "progress": round(prog, 2),
                "message": msg,
                "multipliers": self.balance_multiplier,
                "configuration_matches": getattr(self, "_alignment_configuration", None) == self._calibration_configuration(),
            }

    def _finish_stance_alignment(self):
        with self.lock:
            if not self._alignment_active:
                return
            start = getattr(self, "_alignment_hold_start", None)
            end = getattr(self, "_alignment_last_sample_timestamp", None)
            if (getattr(self, "_alignment_configuration", None) != self._calibration_configuration()
                    or getattr(self, "_alignment_paused", False)
                    or start is None or end is None
                    or end - start < self._alignment_duration_sec
                    or not 0 <= time.monotonic() - end <= self.WIZARD_SAMPLE_MAX_AGE
                    or not self._alignment_live_unlocked()
                    or self._latest_raw_reading.timestamp != end):
                self._pause_stance_alignment_unlocked(
                    "Readings interrupted. Waiting for live data to restart the full hold.")
                return
            self._alignment_active = False
            if len(self._alignment_samples) >= 15:
                avg_l = sum(s[0] for s in self._alignment_samples) / len(self._alignment_samples)
                avg_r = sum(s[1] for s in self._alignment_samples) / len(self._alignment_samples)
                if avg_l > 5.0 and avg_r > 5.0:
                    target = (avg_l + avg_r) * 0.5
                    self.balance_multiplier = [round(target / avg_l, 4), round(target / avg_r, 4)]
                    self._save_calibration()
                    self._alignment_status_msg = f"✓ 50/50 Stance Calibrated (L:{self.balance_multiplier[0]:.2f}, R:{self.balance_multiplier[1]:.2f})"
                else:
                    self._alignment_status_msg = "Alignment failed: Under 5kg detected on boards."
            else:
                self._alignment_status_msg = "Alignment failed: Not enough live samples. Try again."

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
            now_mono = time.monotonic()
            zero_reading = SensorReading(0.0, 0.0, 0.0, 0.0, timestamp=now_mono)
            zero_cop = CoPSample(
                cop_x=0.0,
                cop_y=0.0,
                total_kg=0.0,
                pct_left=50.0,
                pct_right=50.0,
                pct_front=50.0,
                pct_back=50.0,
                timestamp=now_mono,
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
            self._stance_configuration = self._calibration_configuration()
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
                "configuration_matches": getattr(self, "_stance_configuration", None) == self._calibration_configuration(),
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
                path = board_id_to_bytes(device_path)
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
                    path = board_id_to_bytes(device_path)
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

    def _create_openfp_backend(self):
        """open-fp plates over the LAN.

        open() returns at once (we hold self.lock here); the backend connects
        and reconnects on its own thread. Only a malformed URL fails.
        """
        try:
            from src.hardware.pressure.openfp_backend import OpenFpBackend
            b = OpenFpBackend(self.openfp_url)
            b.open()
            print(f"[+] open-fp: streaming from {b.host}:{b.port} once reachable")
            return b
        except Exception as e:
            print(f"[!] open-fp backend not started ({e}).")
            return None

    def _activate_source_cal(self, source: str) -> None:
        """Park the current source's calibration and load `source`'s."""
        store = getattr(self, "_per_source_cal", None)
        if store is None:
            store = self._per_source_cal = {}
        cur = getattr(self, "pressure_source", "wbb")
        store[cur] = {"balance_multiplier": list(self.balance_multiplier),
                      "stance_width_mm": self.stance_width_mm}
        nxt = store.get(source) or {}
        self.balance_multiplier = list(nxt.get("balance_multiplier") or [1.0, 1.0])
        self.stance_width_mm = nxt.get("stance_width_mm")
        self.pressure_source = source

    def set_pressure_source(self, source: str, url: str | None = None):
        """Switch between Wii Balance Boards and open-fp plates; persists."""
        if source not in ("wbb", "openfp"):
            raise ValueError(f"unknown pressure source {source!r}")
        if url is not None:
            from src.hardware.pressure.openfp_backend import parse_url
            parse_url(url)  # reject garbage before saving it
        with self.lock:
            self._env_source_override = False  # an explicit choice wins
            if source != self.pressure_source:
                self._activate_source_cal(source)
            if url is not None:
                self.openfp_url = url.strip() or None
            self._set_simulator_unlocked(self.is_simulator)
            self._save_calibration()
            return self.get_source_status()

    def get_source_status(self):
        with self.lock:
            b = self.backend
            is_openfp = b is not None and b.__class__.__name__ == "OpenFpBackend"
            return {
                "source": self.pressure_source,
                "openfp_url": self.openfp_url,
                "connected": bool(b and b.is_open),
                "openfp": {
                    "host": f"{b.host}:{b.port}",
                    "messages": b.messages,
                    "connects": b.connects,
                    "protocol_errors": b.protocol_errors,
                    "clock_offset_s": b.clock.offset,
                    "last_error": b.last_error,
                    "board_status": b.board_status,
                } if is_openfp else None,
            }

    def notify_shot(self):
        """Forward a launch-monitor shot to hardware that wants it (open-fp
        labels impact in its own swing capture). Never raises."""
        b = self.backend
        hook = getattr(type(b), "notify_shot", None) if b is not None else None
        if hook is None:
            return
        try:
            hook(b, time.time() * 1000.0)
        except Exception as e:
            print(f"[!] Shot forward to pressure hardware failed: {e}")

    def _set_simulator_unlocked(self, enabled: bool):
        """Inner logic — caller MUST already hold self.lock."""
        self._close_wizard_backends_unlocked()
        wizard = getattr(self, "assignment_wizard", None)
        if wizard and wizard.phase in ("waiting_left", "waiting_right"):
            wizard.reset()
        self.latest_frame = None
        self._latest_raw_reading = None
        self.is_simulator = enabled
        if self.backend:
            try: self.backend.close()
            except Exception: pass
        if self.is_simulator:
            from src.hardware.pressure import SimulatorBackend
            self.backend = SimulatorBackend()
            try: self.backend.open()
            except Exception: pass
        elif self.pressure_source == "openfp":
            self.backend = self._create_openfp_backend()
        else:
            try:
                if self.board_mode == "dual" and self.assigned_left and self.assigned_right:
                    from src.hardware.pressure.dual_wbb_backend import DualWbbBackend
                    b_left = self._create_hardware_backend(self.assigned_left)
                    b_right = self._create_hardware_backend(self.assigned_right)
                    if b_left and b_right:
                        self.backend = DualWbbBackend(b_left, b_right)
                    else:
                        # A configured dual setup must not silently become one
                        # board while claiming its saved left/right assignment.
                        for board in (b_left, b_right):
                            if board:
                                board.close()
                        self.backend = None
                else:
                    self.backend = self._create_hardware_backend()
            except Exception:
                self.backend = None
        return self.is_simulator

    def set_simulator(self, enabled: bool):
        with self.lock:
            return self._set_simulator_unlocked(enabled)

    def reopen_backend(self):
        """Rebuild the hardware backend against whatever is connected NOW.

        Called after pairing: a board that was just paired is not readable
        through the existing (failed or stale) backend, so without this the
        user pairs successfully and the app still shows no board until they
        restart it. Also clears the device scan cache so the fresh device is
        actually seen rather than a stale enumeration being reused.
        """
        with self.lock:
            self._device_scan_cache = None
            self._backend_error_logged = False
            return self._set_simulator_unlocked(self.is_simulator)

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
            if board_id_to_text(left_path) == board_id_to_text(right_path):
                return {"status": "error",
                        "message": "Left and right must be different boards."}

            available = {board_id_to_text(p) for p in self.enumerate_boards()}
            for label, path in (("left", left_path), ("right", right_path)):
                if available and board_id_to_text(path) not in available:
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
                "assigned_left": board_id_to_text(left_path),
                "assigned_right": board_id_to_text(right_path),
                "connected": bool(self.backend and self.backend.is_open),
            }

    def _close_wizard_backends_unlocked(self):
        """Release each assignment reader once while holding the I/O lock."""
        closed = set()
        for attr in ("_wiz_backend_a", "_wiz_backend_b"):
            board = getattr(self, attr, None)
            setattr(self, attr, None)
            if board is not None and id(board) not in closed:
                closed.add(id(board))
                try:
                    board.close()
                except Exception as exc:
                    print(f"[!] Assignment board close failed: {exc}")
        self._wiz_health = {}

    def _poll_assignment_wizard(self):
        """Read genuine samples, expose failures, and bound per-board recovery.

        A HID handle or an enumerated Bluetooth device is not a weight sample.
        Uncalibrated/stale data must not be shown as zero kg or assign a foot.
        All read/close/reopen operations share the same lock as normal I/O.
        """
        with self.lock:
            wiz = self.assignment_wizard
            if not wiz or wiz.phase not in ("waiting_left", "waiting_right"):
                return
            if self.is_simulator:
                return  # Demo loads are explicitly supplied, never inferred.
            now = time.monotonic()
            health = getattr(self, "_wiz_health", None)
            if not health:
                health = self._wiz_health = {
                    key: {"opened_at": now, "last_sample_timestamp": None,
                          "retries": 0, "last_error": None}
                    for key in ("a", "b")
                }
            diagnostics = {}
            for key in ("a", "b"):
                attr = f"_wiz_backend_{key}"
                board = getattr(self, attr, None)
                state = health[key]
                reading = None
                try:
                    if board and board.is_open:
                        reading = board.read()
                except Exception as exc:
                    state["last_error"] = f"Read failed: {exc}"
                    try:
                        board.close()
                    except Exception:
                        pass
                    setattr(self, attr, None)
                    board = None
                now = time.monotonic()
                if reading is not None:
                    stamp = reading.timestamp
                    weight = reading.total_weight
                    if (math.isfinite(stamp) and 0 <= now - stamp <= self.WIZARD_SAMPLE_MAX_AGE
                            and math.isfinite(weight) and weight >= 0):
                        state["last_sample_timestamp"] = stamp
                        state["last_error"] = None
                        setattr(wiz, f"board_{key}_weight", weight)
                diagnostic_method = getattr(type(board), "get_diagnostics", None)
                try:
                    detail = dict(diagnostic_method(board)) if diagnostic_method else {}
                except Exception as exc:
                    detail = {"last_error": f"Diagnostics failed: {exc}"}
                stamp = state["last_sample_timestamp"]
                fresh = bool(board and board.is_open and stamp is not None
                             and 0 <= now - stamp <= self.WIZARD_SAMPLE_MAX_AGE)
                recovery_blocked = bool(detail.get("recovery_blocked"))
                if detail.get("calibration_status") == "unavailable" or recovery_blocked:
                    fresh = False
                elapsed = now - (stamp if stamp is not None else state["opened_at"])
                if (not fresh and not recovery_blocked
                        and elapsed >= self.WIZARD_RETRY_DELAY):
                    if state["retries"] < self.WIZARD_MAX_RETRIES:
                        state["retries"] += 1
                        if board:
                            try:
                                board.close()
                            except Exception:
                                pass
                        setattr(self, attr, None)
                        # A previous load is never reusable after reopening.
                        state["last_sample_timestamp"] = None
                        setattr(wiz, f"board_{key}_weight", 0.0)
                        path = wiz.board_a if key == "a" else wiz.board_b
                        board = self._create_hardware_backend(path)
                        setattr(self, attr, board)
                        state["opened_at"] = time.monotonic()
                        state["last_error"] = None if board else "Board could not be opened."
                        diagnostic_method = getattr(type(board), "get_diagnostics", None)
                        try:
                            detail = dict(diagnostic_method(board)) if diagnostic_method else {}
                        except Exception:
                            detail = {}
                        stamp = None
                detail.update(
                    device_id=board_id_to_text(wiz.board_a if key == "a" else wiz.board_b),
                    is_open=bool(board and board.is_open), fresh=fresh,
                    last_sample_timestamp=stamp, retries=state["retries"],
                    retry_exhausted=bool(not fresh and
                        state["retries"] >= self.WIZARD_MAX_RETRIES and
                        time.monotonic() - state["opened_at"] >= self.WIZARD_RETRY_DELAY),
                )
                if state["last_error"]:
                    detail["last_error"] = state["last_error"]
                diagnostics[key] = detail
            # Initializing the second reader can take seconds. Recheck both
            # ages after all I/O rather than treating the first as still fresh.
            now = time.monotonic()
            for detail in diagnostics.values():
                stamp = detail.get("last_sample_timestamp")
                age = now - stamp if stamp is not None else None
                packet = detail.get("last_packet_timestamp")
                detail["sample_age_seconds"] = round(age, 3) if age is not None else None
                detail["packet_age_seconds"] = round(now - packet, 3) if packet is not None else None
                detail["fresh"] = bool(detail["fresh"] and age is not None
                                       and 0 <= age <= self.WIZARD_SAMPLE_MAX_AGE)
            wiz.board_diagnostics = diagnostics
            missing = [key.upper() for key, detail in diagnostics.items() if not detail["fresh"]]
            if missing:
                labels = " / ".join(missing)
                invalid = [key for key in missing
                           if diagnostics[key.lower()].get("recovery_blocked")]
                if invalid:
                    wiz.health_state = "error"
                    wiz.health_message = (
                        f"Board {' / '.join(invalid)}: invalid zero sensor data. "
                        "Reading paused. Inspect packet diagnostics before restarting setup.")
                    return
                failed = any(diagnostics[key.lower()]["retry_exhausted"] for key in missing)
                uncalibrated = any(diagnostics[key.lower()].get("calibration_status") == "unavailable"
                                   for key in missing)
                wiz.health_state = "error" if failed else "recovering" if any(
                    detail["retries"] for detail in diagnostics.values()) else "waiting"
                problem = "factory calibration unavailable" if uncalibrated else "no live readings"
                wiz.health_message = (f"Board {labels}: {problem}. " +
                    ("Step off, check power and close other board apps, then cancel and retry setup."
                     if failed else "Keep boards unloaded while the connection retries."))
                return
            wiz.health_state = "ready"
            wiz.health_message = ""
            self.update_assignment_wizard(wiz.board_a_weight, wiz.board_b_weight,
                                          _from_hardware=True)

    def start_assignment_wizard(self):
        with self.lock:
            from src.hardware.pressure.connection import BoardAssignmentWizard
            
            # Close existing backend so we don't hold exclusive handle on Board 1
            if self.backend:
                try: self.backend.close()
                except Exception: pass
                self.backend = None

            self._close_wizard_backends_unlocked()
            self.latest_frame = None
            self._latest_raw_reading = None
            # Different HID paths are required; duplicate enumeration records
            # must never make one physical reader look like a dual setup.
            dev_paths = ([] if self.is_simulator else list(
                {board_id_to_text(p): p for p in self.enumerate_boards()}.values()))

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
            now = time.monotonic()
            self._wiz_health = {
                key: {"opened_at": now, "last_sample_timestamp": None,
                      "retries": 0, "last_error": None}
                for key in ("a", "b")
            }
            if not self.is_simulator:
                self.assignment_wizard.health_state = "waiting"
                self.assignment_wizard.health_message = "Waiting for live calibrated readings from both boards."
                self.assignment_wizard.board_diagnostics = {
                    key: {"fresh": False, "last_sample_timestamp": None}
                    for key in ("a", "b")
                }
            return self.assignment_wizard.get_status()

    def update_assignment_wizard(self, weight_a: float, weight_b: float,
                                 *, _from_hardware: bool = False):
        with self.lock:
            if not self.assignment_wizard:
                # start_assignment_wizard refuses to run without two real
                # boards and returns a plain status dict, leaving the wizard
                # unset. Report that instead of raising on None.
                status = self.start_assignment_wizard()
                if not self.assignment_wizard:
                    return status
            # HTTP/demo controls may supply synthetic weights only in demo
            # mode. Physical assignment is driven exclusively by our readers.
            if (not self.is_simulator and
                    (not _from_hardware or self.assignment_wizard.health_state != "ready")):
                return self.assignment_wizard.get_status()
            # Completion is a one-time ownership transfer, not a reason to
            # reopen the just-transferred devices on a repeated HTTP update.
            if self.assignment_wizard.phase == "complete":
                return self.assignment_wizard.get_status()
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
            self._close_wizard_backends_unlocked()
            if self.assignment_wizard:
                self.assignment_wizard.reset()
            # The ordinary worker can reopen hardware on its next pass. No
            # old wizard handle or displayed frame survives cancellation.
            self.latest_frame = None
            self._latest_raw_reading = None
            if self.is_simulator and self.backend is None:
                self._set_simulator_unlocked(True)
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

    def _hardware_diagnostics(self):
        backend = self.backend
        method = getattr(type(backend), "get_diagnostics", None)
        if not method:
            return {"is_open": bool(backend and backend.is_open)}
        try:
            return method(backend)
        except Exception as exc:
            return {"is_open": bool(backend and backend.is_open), "last_error": str(exc)}

    def get_status(self):
        with self.lock:
            wizard_status = self.assignment_wizard.get_status() if self.assignment_wizard else {
                "phase": "idle", "message": "", "is_complete": False
            }
            devices = self.enumerate_boards()
            return {
                "connected": self.backend.is_open if self.backend else False,
                "mode": "simulator" if self.is_simulator else "hardware",
                "source": self.pressure_source,
                "board_mode": self.board_mode,
                "is_dual": self.board_mode == "dual",
                "assigned_left": board_id_to_text(self.assigned_left) if self.assigned_left else None,
                "assigned_right": board_id_to_text(self.assigned_right) if self.assigned_right else None,
                "devices": [board_id_to_text(p) for p in devices],
                "device_count": len(devices),
                "dual_ready": bool(
                    self.board_mode == "dual"
                    and self.assigned_left and self.assigned_right
                    and self.backend is not None
                    and self.backend.__class__.__name__ == "DualWbbBackend"
                ),
                "assignment_wizard": wizard_status,
                "hardware_diagnostics": self._hardware_diagnostics(),
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
        length = self.request_body_length()
        if length is None:
            return
        if length:
            self.reject_request("GET request bodies are not supported", code=400)
            return
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
            try:
                output = parse_qs(urlsplit(self.path).query).get("output", ["overlay"])[0]
                self.send_json(obs_state.load_layout(output))
            except ValueError as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/bag":
            self.send_json(obs_state.load_bag())
        elif parsed_path == "/api/club":
            with obs_state.lock:
                club = obs_state.selected_club
            self.send_json({"club": club})
        elif parsed_path == "/api/shot":
            # Aim-corrected: the browser overlay must agree with the desktop
            # app's shot table about which way the ball started.
            self.send_json(obs_state.latest_shot_for_display() or {})
        elif parsed_path == "/api/combine":
            try:
                self.send_json(obs_state.combine_status())
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/index":
            try:
                self.send_json(obs_state.load_index())
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/pressure/status":
            self.send_json(pressure_manager.get_status())
        elif parsed_path == "/api/pressure/shot":
            self.send_json({"trace": pressure_manager.last_shot_trace or []})
        elif parsed_path == "/api/pressure/pin":
            try:
                from src.hardware.pressure.bluetooth_windows import (
                    describe_pin_entry,
                    format_mac_display,
                    get_host_bluetooth_mac,
                    mac_has_zero_byte,
                    mac_to_wii_pin,
                    mac_to_wii_pin_display,
                    pin_is_typeable,
                )
                try:
                    from src.hardware.pressure import native_pairing_available
                    native_ok = native_pairing_available()
                except Exception:
                    native_ok = False
                mac = get_host_bluetooth_mac() or ""
                self.send_json({
                    "status": "ok",
                    "host_mac": mac,
                    "host_mac_formatted": format_mac_display(mac) if mac else "",
                    "pin_raw": mac_to_wii_pin(mac) if mac else "",
                    "pin_display": mac_to_wii_pin_display(mac) if mac else "",
                    "has_zero_byte": mac_has_zero_byte(mac) if mac else False,
                    # Whether the PIN can be typed/pasted into the Windows PIN
                    # box at all. False means manual entry is impossible and
                    # native pairing is the only route -- clients must not
                    # present "copy the PIN" as a workable step.
                    "pin_typeable": pin_is_typeable(mac) if mac else False,
                    "pin_entry_note": describe_pin_entry(mac) if mac else "",
                    "native_pairing_available": native_ok,
                    "platform": sys.platform,
                })
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/pressure/mode":
            self.send_json({"board_mode": pressure_manager.board_mode, "is_dual": pressure_manager.board_mode == "dual"})
        elif parsed_path == "/api/pressure/source":
            self.send_json(pressure_manager.get_source_status())
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

    def reject_request(self, message, code=400):
        # Never parse unread body bytes as another request on this connection.
        self.close_connection = True
        self.send_json({"status": "error", "message": message}, code=code)

    def request_body_length(self):
        """Validate the one supported framing: a single decimal Content-Length."""
        if self.headers.get_all("Transfer-Encoding"):
            self.reject_request("Transfer-Encoding is not supported")
            return None
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            self.reject_request("multiple Content-Length headers")
            return None
        raw_length = lengths[0].strip() if lengths else "0"
        if not raw_length or any(c not in "0123456789" for c in raw_length):
            self.reject_request("bad Content-Length")
            return None
        try:
            length = int(raw_length)
        except ValueError:
            self.reject_request("bad Content-Length")
            return None
        if length > self.MAX_POST_BODY:
            self.reject_request("body too large", code=413)
            return None
        return length

    def read_post_body(self):
        """Read a complete, bounded body, closing on invalid request framing."""
        length = self.request_body_length()
        if length is None:
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self.reject_request("incomplete request body")
            return None
        return body.decode("utf-8", errors="replace") if length else "{}"

    def is_cross_origin(self):
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return True

        origin = self.headers.get("Origin")
        if not origin:
            # Headerless CLI/LAN tooling is trusted by design.
            return False

        from urllib.parse import urlsplit

        try:
            origin_parts = urlsplit(origin)
            host_header = self.headers.get("Host")
            if origin_parts.scheme != "http" or not host_header:
                return True
            host_parts = urlsplit(f"//{host_header}")
            if not origin_parts.hostname or not host_parts.hostname:
                return True
            origin_port = origin_parts.port or 80
            host_port = host_parts.port or 80
            return (
                origin_parts.hostname.lower() != host_parts.hostname.lower()
                or origin_port != host_port
            )
        except ValueError:
            return True

    def do_POST(self):
        if self.is_cross_origin():
            self.reject_request("cross-origin request rejected", code=403)
            return

        # Even bodyless actions must consume the framed body before allowing
        # another request on this HTTP/1.1 connection.
        body = self.read_post_body()
        if body is None:
            return

        parsed_path = self.path.split("?")[0].rstrip("/")
        if parsed_path == "/api/layout":
            try:
                layout_data = json.loads(body)
                if not isinstance(layout_data, dict):
                    raise ValueError("layout must be a JSON object")
                output = parse_qs(urlsplit(self.path).query).get("output", ["overlay"])[0]
                base = None
                if self.headers.get("X-Studio-Layout-Merge") == "1":
                    base, layout_data = layout_data.get("base"), layout_data.get("draft")
                    if not isinstance(base, dict) or not isinstance(layout_data, dict):
                        raise ValueError("base and draft must be objects")
                obs_state._layout_path(output)  # Reject invalid output before writing.
                success = obs_state.save_layout(layout_data, output, base)
                self.send_json({"status": "ok" if success else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/club":
            try:
                data = json.loads(body)
            except Exception:
                self.send_json({"status": "error", "message": "invalid JSON"}, code=400)
                return
            if not isinstance(data, dict):
                self.send_json(
                    {"status": "error", "message": "body must be a JSON object"},
                    code=400,
                )
                return
            payload, code = obs_state.set_selected_club(data.get("club"))
            self.send_json(payload, code=code)
        elif parsed_path == "/api/combine":
            try:
                data = json.loads(body)
            except Exception:
                self.send_json({"status": "error", "message": "invalid JSON"}, code=400)
                return
            if not isinstance(data, dict):
                self.send_json({"status": "error", "message": "body must be a JSON object"}, code=400)
                return
            payload, code = obs_state.set_combine(data.get("action"))
            self.send_json(payload, code=code)
        elif parsed_path == "/api/pressure/tare":
            ok = pressure_manager.tare()
            self.send_json({"status": "ok" if ok else "error"})
        elif parsed_path == "/api/pressure/align_stance":
            dur = 4.0
            try:
                data = json.loads(body)
                dur = float(data.get("duration_sec", 4.0))
            except Exception:
                pass
            res = pressure_manager.start_stance_alignment(duration_sec=dur)
            self.send_json(res)
        elif parsed_path == "/api/pressure/stance":
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
            try:
                data = json.loads(body)
                mode = data.get("mode", "single")
                new_mode = pressure_manager.set_board_mode(mode)
                self.send_json({"status": "ok", "board_mode": new_mode})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/source":
            # {"source": "wbb"|"openfp", "url": "http://open-fp.local:7000"}
            body = self.read_post_body()
            if body is None:
                return
            try:
                data = json.loads(body)
                result = pressure_manager.set_pressure_source(
                    data.get("source", "wbb"), data.get("url"))
                self.send_json({"status": "ok", **result})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/assign":
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
                              "devices": [board_id_to_text(p) for p in devs],
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
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(500, str(e))

    def handle_websocket(self):
        if self.is_cross_origin():
            self.send_error(403)
            return

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
        with obs_state.lock:
            current_club = obs_state.selected_club

        init_msg = json.dumps({
            "type": "init",
            "layout": obs_state.load_layout(),
            "projection_layout": obs_state.load_layout("projection"),
            "data": current_shot,
            "club": current_club,
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
