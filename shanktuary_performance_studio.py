#!/usr/bin/env python3
"""
Shanktuary Performance Studio
------------------------------
Connects to OpenLaunch Nova (via official mDNS _openlaunch-ws._tcp.local. discovery) and provides:
  1. Mode 1: 4-Quadrant Quad Studio Dashboard (matching 2.webp)
  2. Mode 2: Floor Divot Projector View (Hitting Mat Projection)
  3. Mode 3: Performance Suite & Trajectory Comparison Dashboard (matching 3.webp)
     - Zero-Config Official mDNS Auto-Discovery (_openlaunch-ws._tcp.local.)
     - Interactive Session Shot List (Select any shot from session history)
     - Clickable Dispersion Map & Trajectory Charts
     - Click-to-Inspect 4-Quadrant Quad View analysis for any historical shot
     - Interactive Draggable Sidebar Divider & Auto-scaling text

Controls:
  - M or Tab : Cycle View Modes (1 -> 2 -> 3)
  - 1, 2, 3   : Jump directly to Mode 1, 2, or 3
  - F or F11 : Toggle Fullscreen
  - C        : Clear current session history
  - Esc      : Exit
"""

import base64
import json
import math
import os
import queue
import socket
import struct
import sys
import threading
import time
import tkinter as tk
import webbrowser
from collections import OrderedDict
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageOps, ImageTk

import obs_server
import theme
from src.analytics.aim import (
    MAX_AIM_OFFSET_DEG,
    MIN_CALIBRATION_SHOTS,
    apply_aim,
    load_aim_offset,
    offset_from_geometry,
    offset_from_shots,
    save_aim_offset,
)
from src.gspro import GsproPoller, locate_gspro_database_path, match_gspro_club
from src.gspro import settings as gspro_settings
from src.processing.pressure import PressureTraceStore, derive_pressure_metrics

# Configuration & Logging
FALLBACK_NOVA_HOST = "192.168.40.249"
FALLBACK_NOVA_PORT = 2920

# Windows High-DPI Scaling Precision Fix
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

if getattr(sys, "frozen", False):
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    DATA_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BUNDLE_DIR

SCRIPT_DIR = BUNDLE_DIR
SESSION_LOG_PATH = os.path.join(DATA_DIR, "shanktuary_session_history.json")

DEFAULT_CLUBS = ["Driver", "3 Wood", "5 Wood", "3 Hybrid", "4 Iron", "5 Iron", "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW", "Putter"]

BAG_CATEGORIES = [
    "Woods & Drivers",
    "Hybrids & Utilities",
    "Irons",
    "Wedges",
    "Putter"
]

# --- OpenGolfCoach clubhead-speed model constants -------------------------
# Mirrors open-golf-coach/core/src/clubhead_data.rs (OpenLaunchLabs).
# The Nova measures BALL data only; it has no club-tracking hardware. OGC
# infers clubhead speed (and therefore smash factor) from ball speed, launch
# angle and spin via a collision model whose effective COR is clamped to
# [OGC_MIN_EFFECTIVE_COR, OGC_DRIVER_COR_LIMIT]. When that clamp engages the
# reported smash/club speed collapse to a constant boundary value and stop
# describing the strike at all -- see compute_smash_confidence().
#
# NOTE: these must stay in sync with the upstream Rust source. If OGC changes
# its constants, clamp detection silently goes stale; verify_ogc_model_sync()
# re-derives club speed from the live payload to catch that drift.
OGC_BALL_MASS_KG = 0.04593
OGC_CLUBHEAD_MASS_KG = 0.200
OGC_DRIVER_COR_LIMIT = 0.83
OGC_MIN_EFFECTIVE_COR = 0.52

# Bands are selected by BALL speed (m/s), so club category is inferred from
# speed alone -- a slow player's driver is scored against wedge-optimal
# parameters. This is why sub-90mph ball speeds routinely pin the COR floor.
OGC_IMPACT_BANDS = [
    {"max_ball_speed_mps": 40.0, "base_cor": 0.55, "optimal_launch_deg": 28.0,
     "launch_tolerance_deg": 15.0, "optimal_spin_rpm": 9000.0, "spin_tolerance_rpm": 4000.0},
    {"max_ball_speed_mps": 50.0, "base_cor": 0.66, "optimal_launch_deg": 20.0,
     "launch_tolerance_deg": 12.0, "optimal_spin_rpm": 7000.0, "spin_tolerance_rpm": 2500.0},
    {"max_ball_speed_mps": 60.0, "base_cor": 0.72, "optimal_launch_deg": 16.0,
     "launch_tolerance_deg": 10.0, "optimal_spin_rpm": 5000.0, "spin_tolerance_rpm": 2000.0},
    {"max_ball_speed_mps": float("inf"), "base_cor": OGC_DRIVER_COR_LIMIT, "optimal_launch_deg": 12.0,
     "launch_tolerance_deg": 8.0, "optimal_spin_rpm": 2500.0, "spin_tolerance_rpm": 1500.0},
]

_OGC_MASS_RATIO = OGC_BALL_MASS_KG / OGC_CLUBHEAD_MASS_KG
# Smash values produced when the COR clamp saturates. Any shot reporting one of
# these is a boundary artifact, not a measurement.
OGC_SMASH_AT_COR_FLOOR = (1.0 + OGC_MIN_EFFECTIVE_COR) / (1.0 + _OGC_MASS_RATIO)
OGC_SMASH_AT_COR_CEILING = (1.0 + OGC_DRIVER_COR_LIMIT) / (1.0 + _OGC_MASS_RATIO)

DEFAULT_BAG = [
    {"name": "Driver", "category": "Woods & Drivers", "brand": "Generic", "model": "Driver", "loft_deg": 10.5, "lie_deg": 56.0, "shaft": "Stiff"},
    {"name": "3 Wood", "category": "Woods & Drivers", "brand": "Generic", "model": "Fairway", "loft_deg": 15.0, "lie_deg": 56.5, "shaft": "Stiff"},
    {"name": "5 Wood", "category": "Woods & Drivers", "brand": "Generic", "model": "Fairway", "loft_deg": 18.0, "lie_deg": 57.0, "shaft": "Stiff"},
    {"name": "3 Hybrid", "category": "Hybrids & Utilities", "brand": "Generic", "model": "Hybrid", "loft_deg": 19.0, "lie_deg": 58.5, "shaft": "Stiff"},
    {"name": "4 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 21.0, "lie_deg": 61.0, "shaft": "Steel S"},
    {"name": "5 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 24.0, "lie_deg": 61.5, "shaft": "Steel S"},
    {"name": "6 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 27.0, "lie_deg": 62.0, "shaft": "Steel S"},
    {"name": "7 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 31.0, "lie_deg": 62.5, "shaft": "Steel S"},
    {"name": "8 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 35.0, "lie_deg": 63.0, "shaft": "Steel S"},
    {"name": "9 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 40.0, "lie_deg": 63.5, "shaft": "Steel S"},
    {"name": "PW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 45.0, "lie_deg": 64.0, "shaft": "Wedge Flex"},
    {"name": "GW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 50.0, "lie_deg": 64.0, "shaft": "Wedge Flex"},
    {"name": "SW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 54.0, "lie_deg": 64.0, "shaft": "Wedge Flex"},
    {"name": "LW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 58.0, "lie_deg": 64.0, "shaft": "Wedge Flex"},
    {"name": "Putter", "category": "Putter", "brand": "Generic", "model": "Blade", "loft_deg": 3.0, "lie_deg": 70.0, "shaft": "Standard"}
]

def infer_club_category(club_name):
    name_lower = club_name.lower()
    if "putter" in name_lower or "blade" in name_lower or "mallet" in name_lower:
        return "Putter"
    elif "driver" in name_lower or "wood" in name_lower or "mini" in name_lower:
        return "Woods & Drivers"
    elif "hybrid" in name_lower or "rescue" in name_lower or "utility" in name_lower or "driving iron" in name_lower:
        return "Hybrids & Utilities"
    elif any(w in name_lower for w in ["pw", "gw", "sw", "lw", "wedge", "°", "deg", "pitching", "gap", "sand", "lob"]):
        return "Wedges"
    # Golfers name wedges by loft -- "60", "56", "52". A bare number in the
    # wedge range is a wedge, not an iron.
    elif name_lower.strip().rstrip("°").isdigit() and 44 <= int(name_lower.strip().rstrip("°")) <= 72:
        return "Wedges"
    else:
        return "Irons"

# Club Image Assets
OVERHEAD_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_overhead.png")
FACE_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_face.png")
SIDE_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_side.png")

shot_queue = queue.Queue()

# Completed pressure captures, posted from the pressure thread as
# (shot_id, trace_frames). A capture finishes ~3s after impact -- long after
# poll_queue() has already written the shot to disk -- so the trace has to
# come back through a queue and be attached on the Tk thread. Writing to
# self.sessions from the capture thread would race json.dump().
pressure_trace_queue = queue.Queue()

# --- Official OpenLaunch Nova Zero-Config Auto-Discovery Engine ---
def discover_nova_device():
    # 1. Environment Variable Override
    if "NOVA_IP" in os.environ:
        ip = os.environ["NOVA_IP"]
        port = int(os.environ.get("NOVA_PORT", 2920))
        print(f"[+] Using NOVA_IP environment variable: {ip}:{port}")
        return ip, port

    # 2. Official OpenLaunch Zeroconf mDNS Discovery (_openlaunch-ws._tcp.local.)
    try:
        from zeroconf import ServiceBrowser, Zeroconf

        class NovaMDNSListener:
            def __init__(self):
                self.found_ip = None
                self.found_port = None

            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.addresses:
                    # Set port BEFORE ip: the polling loop keys on found_ip,
                    # so ip-first could be observed with port still None.
                    self.found_port = info.port
                    self.found_ip = socket.inet_ntoa(info.addresses[0])

            def update_service(self, zc, type_, name):
                pass

            def remove_service(self, zc, type_, name):
                pass

        zeroconf_obj = Zeroconf()
        listener = NovaMDNSListener()
        browser = ServiceBrowser(zeroconf_obj, "_openlaunch-ws._tcp.local.", listener)  # noqa: F841  # keepalive — do not delete (holds mDNS browse alive until zeroconf_obj.close())
        
        # Poll up to 2 seconds for mDNS broadcast response
        for _ in range(20):
            if listener.found_ip:
                ip, port = listener.found_ip, listener.found_port
                zeroconf_obj.close()
                print(f"[+] Discovered Nova via mDNS (_openlaunch-ws._tcp.local.): {ip}:{port}")
                return ip, port
            time.sleep(0.1)
        zeroconf_obj.close()
    except Exception as e:
        print(f"[!] mDNS discovery note: {e}")

    # 3. Direct mDNS Hostname Resolution (openlaunch-nova.local)
    try:
        ip = socket.gethostbyname("openlaunch-nova.local")
        print(f"[+] Resolved openlaunch-nova.local: {ip}")
        return ip, 2920
    except Exception:
        pass

    # 4. Fallback Static IP
    return FALLBACK_NOVA_HOST, FALLBACK_NOVA_PORT

# --- WebSocket Client Thread ---
def make_ws_frame(data, opcode=1):
    payload = data.encode("utf-8") if isinstance(data, str) else data
    length = len(payload)
    header = bytearray([0x80 | (opcode & 0x0F)])
    mask_key = os.urandom(4)
    if length <= 125:
        header.append(0x80 | length)
    elif length <= 65535:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask_key)
    masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(header + masked)

class _SockBuf:
    """Buffered reader so bytes received with the handshake aren't lost."""
    def __init__(self, sock, initial=b""):
        self.sock = sock
        self.buf = bytearray(initial)

    def ensure(self, n):
        """Fill the buffer to at least n bytes WITHOUT consuming.
        Raises ConnectionError if the peer closes; socket.timeout propagates
        (buffer content is preserved, so a retry resumes cleanly)."""
        while len(self.buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Nova closed the connection")
            self.buf.extend(chunk)

    def consume(self, n):
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

def read_ws_frame(r):
    """Read one complete WebSocket frame from a _SockBuf.
    Peek-based: nothing is consumed until the entire frame is buffered, so a
    socket.timeout mid-frame leaves the stream position intact and the caller
    can simply retry. Raises ConnectionError on peer close."""
    r.ensure(2)
    b1, b2 = r.buf[0], r.buf[1]
    opcode = b1 & 0x0F
    has_mask = (b2 & 0x80) != 0
    payload_len = b2 & 0x7F
    off = 2
    if payload_len == 126:
        r.ensure(off + 2)
        payload_len = struct.unpack("!H", bytes(r.buf[off:off + 2]))[0]
        off += 2
    elif payload_len == 127:
        r.ensure(off + 8)
        payload_len = struct.unpack("!Q", bytes(r.buf[off:off + 8]))[0]
        off += 8
    mask_key = None
    if has_mask:
        r.ensure(off + 4)
        mask_key = bytes(r.buf[off:off + 4])
        off += 4
    r.ensure(off + payload_len)
    r.consume(off)
    raw = r.consume(payload_len)
    if has_mask and raw:
        raw = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw))
    return opcode, raw

# Live Nova connection status, written by websocket_worker, read by the UI.
nova_status = {"connected": False, "host": ""}

# Live GSPro poller status, written by gspro_worker, read by the UI
# (draw_tools_menu's HARDWARE rows and the top header status dot).
gspro_status = {
    "connected": False,
    "db_path": "",
    "last_message": "",
    "enabled": False,
    "db_found": False,
    "shots": 0,
}

# Set by the UI when the shot source changes, so the supervisor below can
# start/stop polling without an app restart.
gspro_reconfigure = threading.Event()


def apply_shot_source(source=None, db_path=None, onboarded=None):
    """Persist a shot-source change and wake the GSPro supervisor.

    The single entry point the UI calls; keeps disk state, the in-process
    cache, and the running poller consistent.
    """
    settings = gspro_settings.save_settings(
        source=source, db_path=db_path, onboarded=onboarded
    )
    gspro_reconfigure.set()
    return settings


def gspro_worker():
    """Supervisor thread: run the GSPro poller whenever the user's shot
    source includes GSPro, and stop it when it does not.

    Shots feed the same shot_queue the Nova WebSocket worker uses, so
    poll_queue() consumes both identically.

    Source selection is persisted user configuration (src/gspro/settings.py),
    chosen in the UI and overridable with the SPS_SHOT_SOURCE env var:
      "nova"   -- default; GSPro polling is disabled entirely.
      "gspro"  -- poll GSPro.db only; the Nova WebSocket thread still runs
                  but its shots are ignored, so a host that feeds GSPro via
                  a launch monitor never double-ingests one physical shot.
      "both"   -- both sources ingest (only correct when they describe
                  different shots, e.g. separate bays).

    Unlike the original env-var-only version this loop never returns: a user
    who starts in Nova mode and later picks GSPro in the UI gets polling
    without restarting the app.
    """
    poller = None
    poller_thread = None

    def on_shot(payload, meta):
        # poll_queue() stamps club/timestamp and validates like any Nova shot.
        gspro_status["shots"] = gspro_status.get("shots", 0) + 1
        shot_queue.put(payload)

    def on_status(message):
        gspro_status["last_message"] = message
        if "connected" in message:
            gspro_status["connected"] = True
        elif "unavailable" in message or "stopped" in message:
            gspro_status["connected"] = False
        print(f"[gspro] {message}")

    def stop_poller():
        nonlocal poller, poller_thread
        if poller is not None:
            poller.stop()
            if poller_thread is not None:
                poller_thread.join(timeout=3.0)
        poller = None
        poller_thread = None
        gspro_status["connected"] = False

    while True:
        enabled = gspro_settings.gspro_enabled()
        db_path = gspro_settings.effective_db_path() if enabled else ""
        gspro_status["enabled"] = enabled
        gspro_status["db_path"] = db_path
        gspro_status["db_found"] = bool(db_path) and os.path.isfile(db_path)

        running = poller_thread is not None and poller_thread.is_alive()
        wanted = enabled

        if running and (not wanted or poller.db_path != db_path):
            # Disabled, or the user pointed us at a different database.
            stop_poller()
            running = False

        if wanted and not running:
            if not gspro_status["db_found"]:
                gspro_status["last_message"] = (
                    f"GSPro database not found at {db_path}"
                )
            poller = GsproPoller(on_shot=on_shot, db_path=db_path, on_status=on_status)
            poller_thread = threading.Thread(target=poller.run, daemon=True)
            poller_thread.start()
        elif not wanted:
            source = gspro_settings.effective_source()
            gspro_status["last_message"] = f"GSPro polling disabled (source={source})"

        # Wake immediately on a UI change, otherwise re-check periodically so
        # a database that appears later (GSPro installed/launched after SPS)
        # is picked up on its own.
        gspro_reconfigure.wait(timeout=5.0)
        gspro_reconfigure.clear()


def load_bag_specs_for_splash():
    """Read {club_name: spec} from the saved session file.

    The startup splash runs before ShanktuaryApp exists, so it cannot use
    get_bag_club(). Returns {} on any problem — the splash then shows plain
    club names rather than failing or inventing gear.
    """
    try:
        with open(SESSION_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    specs = {}
    for club in data.get("bag", []) or []:
        if isinstance(club, dict) and club.get("name"):
            specs[str(club["name"])] = club
    return specs


def websocket_worker():
    while True:
        s = None
        try:
            nova_ip, nova_port = discover_nova_device()
            print(f"[*] Connecting to OpenLaunch Nova at ws://{nova_ip}:{nova_port}...")
            s = socket.create_connection((nova_ip, nova_port), timeout=5)
            key = base64.b64encode(os.urandom(16)).decode()
            req = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {nova_ip}:{nova_port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            s.sendall(req.encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    raise ConnectionError("Nova closed during handshake")
                buf += chunk
            headers, _, residual = buf.partition(b"\r\n\r\n")
            status_line = headers.split(b"\r\n", 1)[0]
            if b" 101" not in status_line:
                raise ConnectionError(f"WebSocket handshake rejected: {status_line.decode(errors='replace')}")

            print(f"[+] Connected to Nova WebSocket on {nova_ip}:{nova_port}!")
            nova_status["connected"] = True
            nova_status["host"] = f"{nova_ip}:{nova_port}"
            s.settimeout(1.0)
            # Carry any frame bytes that arrived with the handshake tail
            reader = _SockBuf(s, residual)
            while True:
                try:
                    opcode, data = read_ws_frame(reader)
                except socket.timeout:
                    continue  # idle between frames — keep waiting
                if opcode == 0x8:  # close
                    raise ConnectionError("Nova sent close frame")
                if opcode == 0x9:  # ping → masked pong
                    try:
                        s.sendall(make_ws_frame(data, opcode=0xA))
                    except OSError:
                        raise ConnectionError("failed to send pong")
                    continue
                if data:
                    text = data.decode("utf-8", errors="replace")
                    try:
                        msg = json.loads(text)
                        if msg.get("type") == "shot":
                            # When the GSPro poller is the chosen source, this
                            # host's Nova feed describes the SAME physical
                            # shots (the monitor feeds GSPro) — dropping them
                            # here prevents double ingestion.
                            if gspro_settings.nova_enabled():
                                shot_queue.put(msg)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            nova_status["connected"] = False
            print(f"[!] WebSocket error: {e}. Reconnecting in 3s...")
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
            time.sleep(3)

def load_image_asset(path, target_h=210, mirror=False):
    if os.path.exists(path):
        try:
            img = Image.open(path).convert("RGBA")
            if mirror:
                img = ImageOps.mirror(img)
            w, h = img.size
            target_w = int(w * (target_h / h))
            resized = img.resize((target_w, target_h), resample=Image.LANCZOS)
            
            dim = max(target_w, target_h) + 40
            canvas_img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
            canvas_img.paste(resized, ((dim - target_w) // 2, (dim - target_h) // 2), resized)
            return canvas_img
        except Exception as e:
            print(f"[!] Error loading {path}: {e}")
    return None

APP_VERSION = "v1.3.1"
BUILD_NUMBER = "2026.08.29.1"

class ShanktuaryApp:
    # Bound on img_cache. Rotated overhead sprites measure ~0.5 MB each as PIL
    # data, and Tk's PhotoImage keeps its own copy of the pixels, so budget
    # ~1 MB per entry: 96 entries is roughly 100 MB worst case. Comfortably
    # larger than one view's working set (a handful of sizes x angles), small
    # enough that a window-resize sweep can't run away.
    IMG_CACHE_MAX = 96

    # Pressure traces read back from disk, kept in memory for review. Each is
    # ~480 frames / ~155 KB parsed, so 12 is roughly 2 MB.
    TRACE_CACHE_MAX = 12

    def __init__(self, root):
        self.root = root
        self.root.title(f"Shanktuary Performance Studio {APP_VERSION} - Launch Monitor Suite")
        self.root.configure(bg=theme.BG)
        self.fullscreen = False
        # Landing view. Mode 9 is Overview -- the shot-at-a-glance summary.
        # See theme.NAV_ITEMS for the full mode map; note mode 0 is the floor
        # divot projector, not a content view.
        self.view_mode = 9

        # Multi-Session & Shot Management (Nova & Uneekor style)
        self.sessions = [
            {
                "id": f"sess_{int(time.time())}",
                "name": "Session 1 - 7 Iron",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "shots": []
            }
        ]
        self.active_session_index = 0
        self.selected_shot_index = -1
        self.club_filter = "ALL"  # "ALL" or specific club like "7 Iron"
        self.sidebar_collapsed = False
        self.sidebar_width = 270
        self.sidebar_scroll_offset = 0

        # Bag Club Management
        self.clubs = list(DEFAULT_CLUBS)
        self.current_club = "7 Iron"
        
        # Overlay & Dropdown states
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.show_club_menu = False
        self.show_tools_menu = False
        self.copy_feedback = None
        self.nova_connected = False
        self.is_left_handed = False

        # Hit testing regions for top header & interactive menus
        self.sidebar_toggle_rect = None       # Hamburger [ ☰ ] or collapse [ ◀ ]
        self.sidebar_session_btn_rect = None  # [ 📂 Session Name ▼ ]
        self.sidebar_rename_sess_btn_rect = None # [ ✏️ ]
        self.sidebar_new_sess_btn_rect = None # [ ＋ ]
        self.sidebar_filter_btn_rect = None   # [ 🎯 Filter: All Clubs ▼ ]
        self.sidebar_clear_btn_rect = None    # [ 🗑️ Clear Session ]
        self.sidebar_shot_card_rects = []     # (x1, y1, x2, y2, shot_idx_in_session)
        self.shot_delete_btn_rects = []       # (x1, y1, x2, y2, shot_idx_in_session) [ ✕ ]
        self.design_shot_delete_rects = []    # same, for the desktop-redesign card layout
        self.session_menu_items = []          # (x1, y1, x2, y2, sess_idx)
        self.filter_menu_items = []           # (x1, y1, x2, y2, club_name)

        self.mode_pill_rects = {}             # mode_id -> (x1, y1, x2, y2)
        self.club_btn_rect = None             # (x1, y1, x2, y2)
        self.dexterity_btn_rect = None        # (x1, y1, x2, y2) [ 🏌️‍♂️ RH ] / [ 🏌️‍♀️ LH ]
        self.tools_btn_rect = None            # (x1, y1, x2, y2)
        self.fullscreen_btn_rect = None       # (x1, y1, x2, y2)
        self.club_menu_items = []             # (x1, y1, x2, y2, club_name)
        self.tools_menu_items = []            # (x1, y1, x2, y2, action_key)
        self.land_dot_coords = []             # (x, y, index)

        # Mode 4: Table Viewport State
        self.table_sort_col = "index"
        self.table_sort_asc = True
        self.table_scroll_offset = 0
        self.table_row_rects = []             # (x1, y1, x2, y2, shot_idx)
        self.table_header_rects = []          # (x1, y1, x2, y2, col_key)
        self.table_checkbox_rects = []        # (x1, y1, x2, y2, shot_idx)

        # Mode 3: Dispersion Viewport State
        self.dispersion_selected_club = "ALL"
        self.dispersion_view_submode = "split" # "split", "topdown", "side"
        self.dispersion_submode_rects = []     # (x1, y1, x2, y2, submode_key)
        self.dispersion_club_chip_rects = []  # (x1, y1, x2, y2, club_name)
        self.dispersion_dot_rects = []        # (x, y, shot_idx)
        self.dispersion_splitter_ratio = 0.62 # Proportion for left charts (0.25 to 0.85)
        self.dispersion_splitter_dragging = False
        self.dispersion_splitter_rect = None  # (x1, y1, x2, y2)

        # In-Canvas Custom Club Modal State
        self.show_custom_club_modal = False
        # Custom clubs found in the save file with no matching bag entry;
        # adopted into the bag once it has loaded.
        self._orphan_customs = []
        self.custom_club_input_text = ""
        self.custom_club_modal_box_rect = None
        self.custom_club_modal_add_rect = None
        self.custom_club_modal_cancel_rect = None

        # Mode 6: My Bag Viewport State
        self.bag = []
        self.bag_scope = "session"            # "session" or "all_time"
        self.bag_scroll_offset = 0
        self.bag_scope_session_rect = None
        self.bag_scope_all_rect = None
        self.bag_add_club_btn_rect = None
        self.bag_club_card_rects = []         # (x1, y1, x2, y2, club_name)
        self.bag_edit_btn_rects = []          # (x1, y1, x2, y2, club_name)
        self.bag_move_up_rects = []           # (x1, y1, x2, y2, club_name)
        self.bag_move_down_rects = []         # (x1, y1, x2, y2, club_name)

        # In-Canvas Spec Editor Modal State
        self.show_spec_editor_modal = False
        self.spec_editor_orig_name = ""
        self.spec_editor_club_name = ""
        self.spec_editor_category = "Irons"
        self.spec_editor_brand = ""
        self.spec_editor_model = ""
        self.spec_editor_loft = ""
        self.spec_editor_lie = ""
        self.spec_editor_shaft = ""
        self.spec_editor_notes = ""
        self.spec_editor_active_field = "brand" # "name", "category", "brand", "model", "loft", "lie", "shaft"
        self.spec_editor_box_rect = None
        self.spec_editor_save_rect = None
        self.spec_editor_delete_rect = None
        self.spec_editor_cancel_rect = None
        self.spec_editor_cat_chips = []       # (x1, y1, x2, y2, cat_name)
        self.spec_editor_field_rects = {}     # field_name -> (x1, y1, x2, y2)
        self.spec_editor_notes_edit_rect = None

        # Mode 2: 3D Range Viewport State
        self.range_launch_web_rect = None

        # Mode 7: Club Fitting & Comparison Viewport State
        self.fitting_submode = "split"        # "split", "topdown", "side"
        self.fitting_selected_clubs = []      # list of club names to compare
        self.fitting_baseline_club = None     # club name used as baseline for comparison
        self.fitting_splitter_ratio = 0.52    # Proportion for left overlaid charts
        self.fitting_splitter_dragging = False
        self.fitting_splitter_rect = None     # (x1, y1, x2, y2)
        self.fitting_submode_rects = []       # (x1, y1, x2, y2, submode_key)
        self.fitting_club_chip_rects = []     # (x1, y1, x2, y2, club_name)
        self.fitting_baseline_chip_rects = [] # (x1, y1, x2, y2, club_name)
        self.fitting_add_club_rect = None     # (x1, y1, x2, y2)
        self.fitting_dot_rects = []           # (x, y, shot_idx)

        # Load Assets
        self.overhead_img = load_image_asset(OVERHEAD_PATH, target_h=150, mirror=True)
        self.face_img = load_image_asset(FACE_PATH, target_h=115, mirror=False)
        self.side_img = load_image_asset(SIDE_PATH, target_h=110, mirror=False)

        # Rendered-image cache. MUST stay bounded: entries are keyed partly on
        # continuous values (window scale, and face angle rounded to 0.1deg), so
        # an unbounded dict grows without limit -- a resize sweep alone spans
        # ~166 heights x 301 angles, and at ~0.5 MB per rotated RGBA sprite
        # (plus Tk's own copy of the pixels) that reaches tens of GB.
        # OrderedDict + move_to_end gives LRU eviction.
        self.img_cache = OrderedDict()

        self.canvas = tk.Canvas(root, bg=theme.BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Centralized Keyboard Handler (Modal & Global Hotkeys)
        self.root.bind("<Key>", self.handle_key_press)

        # Mouse & Scroll Events
        self.canvas.bind("<Motion>", self.handle_mouse_hover)
        self.canvas.bind("<Button-1>", self.handle_mouse_press)
        self.canvas.bind("<B1-Motion>", self.handle_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_mouse_release)
        self.canvas.bind("<MouseWheel>", self.handle_mouse_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.handle_scroll_delta(-1))
        self.canvas.bind("<Button-5>", lambda e: self.handle_scroll_delta(1))
        self.canvas.bind("<Configure>", lambda e: self.draw_screen())

        # Mode 8: Swing Lab Biomechanics Suite
        self.swing_lab_history = []
        # Captured pressure traces live beside the session file, one gzipped
        # file per shot: a trace is ~200 KB of JSON and the history file is
        # rewritten whole after every shot, so inlining them would mean a
        # multi-megabyte write 3 seconds after each swing.
        self.trace_store = PressureTraceStore(DATA_DIR)
        # Cache of traces read back from disk, keyed by shot id, so scrolling
        # the shot list doesn't re-read and re-parse the same file each frame.
        self._trace_cache = OrderedDict()
        self.swing_lab_tare_rect = None
        self.swing_lab_hw_rect = None
        self.swing_lab_demo_rect = None
        self.show_balance_hardware_modal = False
        self.balance_modal_box_rect = None
        self.balance_modal_close_rect = None
        self.balance_modal_tare_rect = None
        self.balance_modal_align_rect = None
        self.balance_modal_stance_rect = None
        # Overview interactive regions
        self.overview_viewall_rect = None
        self.overview_prev_rect = None
        self.overview_next_rect = None
        self.overview_bar_rects = []
        self.nav_setup_rect = None
        self.setup_mode_1_rect = None
        self.setup_mode_2_rect = None
        self.setup_pair_rect = None
        self.setup_step_a_rect = None
        self.setup_step_b_rect = None
        self.setup_align_rect = None
        self.setup_tare_rect = None
        # Aim calibration: where the Nova points relative to the target line.
        # The device has no aim calibration of its own, so an off-square unit
        # reports every shot as a push or a pull.
        self.aim_offset_deg = load_aim_offset()
        self.aim_calibrating = False
        self.aim_calib_shots = []
        self.setup_aim_start_rect = None
        self.setup_aim_nudge_rects = []
        self.setup_aim_clear_rect = None
        # Shot-source buttons on the Setup page (nova / gspro / both).
        self.setup_source_btn_rects = []
        # Aim measurement modal: distance to the aim point and how far that
        # point sits off the target line. Two numbers a tape measure gives you,
        # because nobody can eyeball "2.4 degrees".
        self.show_aim_modal = False
        self.aim_modal_distance = ""
        self.aim_modal_lateral = ""
        self.aim_modal_active_field = "distance"
        self.aim_modal_field_rects = {}
        self.aim_modal_save_rect = None
        self.aim_modal_cancel_rect = None
        self.aim_modal_box_rect = None
        self.setup_aim_measure_rect = None
        # Cache for _text_width(): measuring is cheap but this runs per card
        # per redraw, and the set of strings is small and repetitive.
        self._text_w_cache = {}
        self.balance_modal_sim_rect = None
        self.balance_modal_pair_rect = None
        self.balance_modal_copy_pin_rect = None
        self.balance_modal_bt_settings_rect = None
        self.balance_modal_mode_1_rect = None
        self.balance_modal_mode_2_rect = None
        self.balance_modal_assign_btn_rect = None
        self.balance_modal_step_a_rect = None
        self.balance_modal_step_b_rect = None
        self.balance_modal_pin_text = ""
        self.root.after(33, self.poll_pressure_stream)

        self.current_shot = None
        self.load_session_history()
        # Select the most recent shot on launch. Without this the app starts
        # with nothing selected, so Overview -- the landing view -- renders its
        # empty state even when the session file holds shots.
        if self.session_shots:
            self.selected_shot_index = len(self.session_shots) - 1
            self.current_shot = self.session_shots[self.selected_shot_index]
        self.root.after(100, self.poll_queue)
        self.root.after(250, self.poll_pressure_traces)

        # Pressure captures complete on the pressure thread ~3s after impact.
        # Hand them to the Tk thread via a queue rather than touching
        # self.sessions from there -- json.dump() runs on the Tk thread.
        try:
            obs_server.obs_state.trace_listeners.append(
                lambda shot_id, frames: pressure_trace_queue.put((shot_id, frames))
            )
        except Exception as e:
            print(f"[!] Could not register pressure trace listener: {e}")

    def set_aim_offset(self, offset_deg):
        """Set and persist the aim offset, clamped to the sane range."""
        self.aim_offset_deg = max(-MAX_AIM_OFFSET_DEG,
                                  min(MAX_AIM_OFFSET_DEG, float(offset_deg)))
        # Nudges land on values like 1.9000000000000001 otherwise.
        self.aim_offset_deg = round(self.aim_offset_deg, 2)
        try:
            save_aim_offset(self.aim_offset_deg)
        except Exception as e:
            print(f"[!] Could not save aim calibration: {e}")
        # The overlay server caches the offset; tell it to re-read so a
        # mid-session recalibration reaches OBS without a restart.
        try:
            obs_server.obs_state.invalidate_aim_cache()
        except Exception as e:
            print(f"[!] Could not refresh server aim cache: {e}")

    def finish_aim_calibration(self):
        """Turn the collected calibration shots into an offset, or explain why not."""
        offset = offset_from_shots(self.aim_calib_shots)
        if offset is None:
            need = MIN_CALIBRATION_SHOTS - len(self.aim_calib_shots)
            self.copy_feedback = f"Need {need} more shot{'s' if need != 1 else ''}"
            self.root.after(2500, self.clear_copy_feedback)
            return
        self.set_aim_offset(offset)
        self.aim_calibrating = False
        self.aim_calib_shots = []
        self.copy_feedback = f"✓ Aim set to {self.aim_offset_deg:+.1f}°"
        self.root.after(2500, self.clear_copy_feedback)

    def aim_corrected(self, shot):
        """Return ``shot`` with the aim offset removed.

        Applied at READ time, never on the incoming event: the native Nova
        payload must be preserved when forwarding, and shots recorded before a
        user calibrated have to be corrected too.
        """
        if not shot or not self.aim_offset_deg:
            return shot
        return apply_aim(shot, self.aim_offset_deg)

    def get_active_session(self):
        if not self.sessions:
            self.create_new_session("Default Session")
        if self.active_session_index >= len(self.sessions):
            self.active_session_index = max(0, len(self.sessions) - 1)
        return self.sessions[self.active_session_index]

    @property
    def session_shots(self):
        return self.get_active_session().get("shots", [])

    def get_filtered_shots(self):
        """Returns list of (shot_idx_in_session, shot_dict) matching active club filter."""
        shots = self.session_shots
        if self.club_filter == "ALL":
            return list(enumerate(shots))
        return [(idx, s) for idx, s in enumerate(shots) if s.get("club") == self.club_filter]

    def create_new_session(self, name=None):
        idx = len(self.sessions) + 1
        if not name:
            name = f"Session {idx} - {self.current_club}"
        new_sess = {
            "id": f"sess_{int(time.time())}_{idx}",
            "name": name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "shots": []
        }
        self.sessions.append(new_sess)
        self.active_session_index = len(self.sessions) - 1
        self.selected_shot_index = -1
        self.current_shot = None
        self.show_session_dropdown = False
        self.save_session_to_file()
        self.draw_screen()

    def rename_active_session(self, new_name=None):
        sess = self.get_active_session()
        if not sess:
            return
        if new_name is None:
            curr = sess.get("name", "Session")
            try:
                from tkinter import simpledialog
                res = simpledialog.askstring("Rename Session", "Enter new name for active session:", initialvalue=curr, parent=self.root)
                if res is not None and res.strip():
                    new_name = res.strip()
                else:
                    return
            except Exception as e:
                print(f"[!] Simpledialog failed: {e}")
                return

        sess["name"] = new_name
        self.show_session_dropdown = False
        self.save_session_to_file()
        self.copy_feedback = f"Renamed to '{new_name}'"
        self.root.after(2000, self.clear_copy_feedback)
        self.draw_screen()

    def edit_session_notes(self):
        """Toplevel + Text editor for the active session's freeform notes."""
        sess = self.get_active_session()
        if not sess:
            return

        try:
            top = tk.Toplevel(self.root)
            top.title("Session Notes")
            top.configure(bg=theme.SURFACE)
            top.geometry("420x260")
            top.transient(self.root)

            text = tk.Text(top, wrap="word", font=(theme.ui_font(), 10))
            text.pack(fill="both", expand=True, padx=10, pady=(10, 4))
            text.insert("1.0", sess.get("notes", ""))
            text.focus_set()

            def _save():
                self._save_session_notes(text.get("1.0", "end-1c"))
                top.destroy()

            btn_row = tk.Frame(top, bg=theme.SURFACE)
            btn_row.pack(fill="x", padx=10, pady=(0, 10))
            tk.Button(btn_row, text="Save", command=_save).pack(side="right", padx=(6, 0))
            tk.Button(btn_row, text="Cancel", command=top.destroy).pack(side="right")
        except Exception as exc:
            print(f"[!] Session notes editor failed: {exc}")

    def _save_session_notes(self, text):
        """Core notes-write, split out so tests can call it without a Toplevel."""
        sess = self.get_active_session()
        if not sess:
            return
        sess["notes"] = text
        self.show_session_dropdown = False
        self.save_session_to_file()
        self.copy_feedback = "✓ Session notes saved"
        self.root.after(2000, self.clear_copy_feedback)
        self.draw_screen()

    def delete_session(self, session_idx, confirm=True):
        """Delete a session, with confirmation when it holds shots.

        Rules that keep this from destroying data:
          * Never delete the last remaining session — clear it instead, so
            the app always has somewhere to put the next shot.
          * A session WITH shots always asks first; an empty one does not
            (deleting nothing is not a decision worth interrupting for).
          * The active index is re-pointed so it can never dangle past the
            end of the list.
        """
        if not (0 <= session_idx < len(self.sessions)):
            return False

        sess = self.sessions[session_idx]
        name = sess.get("name", "Session")
        shot_count = len(sess.get("shots", []))

        if confirm and shot_count:
            try:
                from tkinter import messagebox

                ok = messagebox.askyesno(
                    "Delete session",
                    f"Delete '{name}' and its {shot_count} shot"
                    f"{'' if shot_count == 1 else 's'}?\n\n"
                    "This cannot be undone.",
                    parent=self.root,
                )
            except Exception as exc:
                print(f"[!] Delete confirmation failed: {exc}")
                return False
            if not ok:
                return False

        if len(self.sessions) == 1:
            # Last session: empty it rather than leaving the app with none.
            sess["shots"] = []
            self.selected_shot_index = -1
            self.current_shot = None
            self.copy_feedback = f"Cleared '{name}'"
        else:
            self.sessions.pop(session_idx)
            if self.active_session_index > session_idx:
                self.active_session_index -= 1
            elif self.active_session_index == session_idx:
                self.active_session_index = min(session_idx,
                                                len(self.sessions) - 1)
            shots = self.session_shots
            if shots:
                self.selected_shot_index = len(shots) - 1
                self.current_shot = shots[-1]
            else:
                self.selected_shot_index = -1
                self.current_shot = None
            self.copy_feedback = f"Deleted '{name}'"

        self.show_session_dropdown = False
        self.save_session_to_file()
        self.root.after(2000, self.clear_copy_feedback)
        self.draw_screen()
        return True

    def delete_shot(self, shot_idx, confirm=True):
        """Hard-delete a single shot from the active session's shot list.

        This is NOT the soft "excluded" flag used by get_filtered_shots() —
        the shot is removed from the underlying data entirely.
        """
        shots = self.session_shots
        if not (0 <= shot_idx < len(shots)):
            return False

        if confirm:
            try:
                from tkinter import messagebox
                ok = messagebox.askyesno(
                    "Delete shot",
                    f"Delete shot #{shot_idx + 1}? This cannot be undone.",
                    parent=self.root,
                )
            except Exception as exc:
                print(f"[!] Delete shot confirmation failed: {exc}")
                return False
            if not ok:
                return False

        shots.pop(shot_idx)

        if shots:
            if self.selected_shot_index == shot_idx:
                self.selected_shot_index = len(shots) - 1
                self.current_shot = shots[-1]
            elif self.selected_shot_index > shot_idx:
                self.selected_shot_index -= 1
        else:
            self.selected_shot_index = -1
            self.current_shot = None

        self.copy_feedback = f"✓ Deleted shot #{shot_idx + 1}"
        self.save_session_to_file()
        self.root.after(2500, self.clear_copy_feedback)
        self.draw_screen()
        return True

    def delete_empty_sessions(self):
        """Remove every session with no shots, keeping the active one.

        Empty sessions accumulate from stray "+" clicks and clutter the
        list. Nothing with shots in it is ever touched.
        """
        if len(self.sessions) <= 1:
            return 0

        active = self.sessions[self.active_session_index]
        keep = [s for s in self.sessions
                if s.get("shots") or s is active]
        removed = len(self.sessions) - len(keep)
        if not removed:
            return 0

        self.sessions[:] = keep
        self.active_session_index = self.sessions.index(active)
        self.show_session_dropdown = False
        self.save_session_to_file()
        self.copy_feedback = (
            f"Removed {removed} empty session{'' if removed == 1 else 's'}"
        )
        self.root.after(2000, self.clear_copy_feedback)
        self.draw_screen()
        return removed

    def switch_session(self, session_idx):
        if 0 <= session_idx < len(self.sessions):
            self.active_session_index = session_idx
            shots = self.session_shots
            if shots:
                self.selected_shot_index = len(shots) - 1
                self.current_shot = shots[-1]
            else:
                self.selected_shot_index = -1
                self.current_shot = None
            self.show_session_dropdown = False
            self.draw_screen()

    def open_shot_source_picker(self):
        """Reopen the splash so the user can change shot source or club.

        Imported lazily: src.ui imports this module, so a module-level import
        here would be circular.
        """
        try:
            from src.ui.splash import SplashScreen
        except Exception as exc:
            print(f"[splash] unavailable: {exc}")
            return

        try:
            specs = {}
            for name in self.clubs:
                club = self.get_bag_club(name)
                if isinstance(club, dict):
                    specs[name] = club
            choice = SplashScreen(
                self.root, clubs=list(self.clubs), current_club=self.current_club,
                club_specs=specs,
            ).run()
        except Exception as exc:
            print(f"[splash] failed to open: {exc}")
            return

        # Wake the GSPro supervisor whether or not the source changed — the
        # user may have fixed the database path outside the app.
        gspro_reconfigure.set()
        if choice:
            club = choice.get("club")
            if club and club in self.clubs:
                self.current_club = club
        self.draw_screen()

    def clear_session(self):
        sess = self.get_active_session()
        sess["shots"].clear()
        self.current_shot = None
        self.selected_shot_index = -1
        self.save_session_to_file()
        self.draw_screen()

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.draw_screen()

    def handle_mouse_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.handle_scroll_delta(delta, mouse_x=event.x)

    def handle_scroll_delta(self, delta, mouse_x=None):
        if mouse_x is None:
            mouse_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx() if self.canvas.winfo_exists() else 0
        
        # If hovering over sidebar
        if not self.sidebar_collapsed and theme.RAIL_W < mouse_x <= self.sidebar_width:
            self.scroll_sidebar(delta)
        elif self.view_mode == 4: # Table view
            max_offset = max(0, len(self.session_shots) - 8)
            self.table_scroll_offset = max(0, min(max_offset, self.table_scroll_offset + delta))
            self.draw_screen()
        elif self.view_mode == 6: # My Bag view
            max_offset = max(0, len(self.bag) * 72 - 300)
            self.bag_scroll_offset = max(0, min(max_offset, self.bag_scroll_offset + delta * 30))
            self.draw_screen()
        else:
            self.scroll_sidebar(delta)

    def scroll_sidebar(self, delta):
        filtered_count = len(self.get_filtered_shots())
        max_offset = max(0, filtered_count - 3)
        self.sidebar_scroll_offset = max(0, min(max_offset, self.sidebar_scroll_offset + delta))
        self.draw_screen()

    def copy_to_clipboard(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            self.copy_feedback = "Copied to clipboard!"
            self.root.after(2000, self.clear_copy_feedback)
            self.draw_screen()
        except Exception as e:
            print(f"[!] Clipboard error: {e}")

    def clear_copy_feedback(self):
        self.copy_feedback = None
        self.draw_screen()

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        self.draw_screen()

    def cycle_mode(self, event=None):
        next_mode = self.view_mode + 1
        if next_mode > 8 or next_mode < 1:
            next_mode = 1
        self.set_mode(next_mode)

    def set_mode(self, mode):
        self.view_mode = mode
        self.draw_screen()

    def launch_3d_range(self, event=None):
        webbrowser.open("http://localhost:9321/range")

    def resolve_handed(self, val, default: Any = 0.0) -> Any:
        """Resolve a Nova/OGC field that may be a plain scalar or a dict keyed
        by right_handed/left_handed. Honors self.is_left_handed; scalar values
        are assumed right-handed and numeric ones are sign-flipped for LH."""
        if isinstance(val, dict):
            key = "left_handed" if self.is_left_handed else "right_handed"
            return val.get(key, val.get("right_handed", default))
        if val is None:
            return default
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return -val if self.is_left_handed else val
        return val

    def load_session_history(self):
        if not os.path.exists(SESSION_LOG_PATH):
            if not self.bag:
                self.init_default_bag()
            return
        try:
            with open(SESSION_LOG_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                if data:
                    self.sessions = data
            elif isinstance(data, dict):
                loaded_sess = data.get("sessions", [])
                if loaded_sess:
                    self.sessions = loaded_sess
                loaded_bag = data.get("bag", [])
                if loaded_bag:
                    self.bag = loaded_bag
                for c in data.get("custom_clubs", []):
                    if c and c not in self.clubs:
                        self.clubs.append(c)
                # Adopt orphaned custom clubs into the bag. Before the bag
                # existed -- and via the club dropdown until recently -- a
                # custom club was only a name in custom_clubs. Those clubs
                # never appeared in My Bag, had no loft or lie, and could not
                # be removed because the delete button lives in the spec
                # editor, which only opens for clubs that ARE in the bag.
                self._orphan_customs = [
                    c for c in data.get("custom_clubs", [])
                    if c and self.get_bag_club(c) is None
                ]
                self.is_left_handed = bool(data.get("is_left_handed", False))
            if not self.bag:
                self.init_default_bag()
            # Backfill lie_deg for bags saved before the field existed. Uses the
            # matching DEFAULT_BAG entry so upgrading users get a sane standard
            # rather than 0.0, without touching any spec they set themselves.
            _default_lies = {c["name"]: c.get("lie_deg", 0.0) for c in DEFAULT_BAG}
            for club_item in self.bag:
                if isinstance(club_item, dict) and "lie_deg" not in club_item:
                    club_item["lie_deg"] = _default_lies.get(club_item.get("name"), 0.0)
            for club_item in self.bag:
                c_name = club_item.get("name")
                if c_name and c_name not in self.clubs:
                    self.clubs.append(c_name)
            # Adopt the orphans found above, now that the bag is populated.
            # add_club_to_bag() infers the category from the name; loft and
            # lie stay 0.0 so the spec editor shows them as blank rather than
            # inventing a number the user never entered.
            for _orphan in getattr(self, "_orphan_customs", []):
                if self.get_bag_club(_orphan) is None:
                    self.add_club_to_bag(_orphan)
            if getattr(self, "_orphan_customs", None):
                print(f"[+] Adopted {len(self._orphan_customs)} custom club(s) "
                      f"into My Bag: {', '.join(self._orphan_customs)}")
            self._orphan_customs = []
        except Exception as e:
            print(f"[!] Error loading session history: {e}")
            # Preserve the unreadable file for recovery — the next save would
            # otherwise silently overwrite possibly-recoverable data.
            try:
                backup = f"{SESSION_LOG_PATH}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                os.replace(SESSION_LOG_PATH, backup)
                print(f"[!] Unreadable history preserved at: {backup}")
                self.copy_feedback = "⚠ History file unreadable — backup saved"
            except OSError:
                pass
            if not self.bag:
                self.init_default_bag()

    def save_session_to_file(self):
        try:
            custom_clubs = [c for c in self.clubs if c not in DEFAULT_CLUBS]
            payload = {
                "sessions": self.sessions,
                "custom_clubs": custom_clubs,
                "bag": self.bag,
                "is_left_handed": self.is_left_handed
            }
            # Atomic write: serialize to a temp file, then swap into place so
            # a crash mid-write can never truncate the whole history.
            tmp_path = SESSION_LOG_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, SESSION_LOG_PATH)
        except Exception as e:
            print(f"[!] Error saving session: {e}")

    def _text_width(self, text, font_spec):
        """Measured pixel width of a string, cached.

        Estimating from character count under-counts badly on a proportional
        face -- "67.6 mph  ·  Straight Fade" measures 167px but a len*5
        estimate gives 130px, so truncation never triggered and the text ran
        under the right-aligned value beside it.
        """
        key = (text, font_spec)
        cached = self._text_w_cache.get(key)
        if cached is None:
            try:
                import tkinter.font as tkfont
                fam = font_spec[0]
                size = font_spec[1] if len(font_spec) > 1 else 10
                weight = "bold" if "bold" in font_spec else "normal"
                cached = tkfont.Font(family=fam, size=size,
                                     weight=weight).measure(text)
            except Exception:
                cached = int(len(text) * size * 0.62)
            self._text_w_cache[key] = cached
        return cached

    def _cache_image(self, key, photo):
        """Store a rendered image, evicting the least recently used entries.

        Bounded because several keys embed continuously-varying values (window
        scale, face angle); see the img_cache comment in __init__.
        """
        self.img_cache[key] = photo
        self.img_cache.move_to_end(key)
        while len(self.img_cache) > self.IMG_CACHE_MAX:
            self.img_cache.popitem(last=False)
        return photo

    def _cached_image(self, key):
        """Fetch and mark as recently used, or None."""
        if key in self.img_cache:
            self.img_cache.move_to_end(key)
            return self.img_cache[key]
        return None

    def get_scaled_club_asset(self, path, target_h, mirror=False):
        key = (path, target_h, mirror)
        hit = self._cached_image(key)
        if hit is not None:
            return hit
        img = load_image_asset(path, target_h=target_h, mirror=mirror)
        if img:
            return self._cache_image(key, ImageTk.PhotoImage(img))
        return None

    def get_rotated_overhead_asset(self, target_h, face_angle, mirror=False):
        raw_key = (OVERHEAD_PATH, target_h, mirror, round(face_angle, 1))
        hit = self._cached_image(raw_key)
        if hit is not None:
            return hit

        if os.path.exists(OVERHEAD_PATH):
            try:
                base_img = Image.open(OVERHEAD_PATH).convert("RGBA")
                # Default overhead sprite faces right; for RH it needs mirror=True, for LH mirror=False (facing left)
                actual_mirror = not mirror
                if actual_mirror:
                    base_img = ImageOps.mirror(base_img)
                w, h = base_img.size
                target_w = int(w * (target_h / h))
                resized = base_img.resize((target_w, target_h), resample=Image.LANCZOS)
                
                dim = max(target_w, target_h) + 60
                canvas_img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
                canvas_img.paste(resized, ((dim - target_w) // 2, (dim - target_h) // 2), resized)
                
                # For RH, -face_angle; For LH, +face_angle
                rot_deg = -face_angle if not mirror else face_angle
                rotated = canvas_img.rotate(rot_deg, resample=Image.BICUBIC, expand=True)
                return self._cache_image(raw_key, ImageTk.PhotoImage(rotated))
            except Exception as e:
                print(f"[!] Error creating overhead asset: {e}")
        return None

    def init_default_bag(self):
        self.bag = [dict(c) for c in DEFAULT_BAG]

    def get_bag_club(self, club_name):
        for c in self.bag:
            if c.get("name") == club_name:
                return c
        return None

    def update_club_specs(self, club_name, brand=None, model=None, loft_deg=None, shaft=None, category=None, new_name=None, lie_deg=None, notes=None):
        c = self.get_bag_club(club_name)
        if c:
            if brand is not None: c["brand"] = str(brand)
            if model is not None: c["model"] = str(model)
            if loft_deg is not None:
                try:
                    c["loft_deg"] = float(loft_deg)
                except (ValueError, TypeError):
                    c["loft_deg"] = 0.0
            if lie_deg is not None:
                try:
                    c["lie_deg"] = float(lie_deg)
                except (ValueError, TypeError):
                    c["lie_deg"] = 0.0
            if shaft is not None: c["shaft"] = str(shaft)
            if category is not None: c["category"] = str(category)
            if notes is not None: c["notes"] = str(notes)
            if new_name is not None and new_name.strip():
                clean_name = new_name.strip()
                old_name = c["name"]
                c["name"] = clean_name
                if old_name in self.clubs:
                    self.clubs[self.clubs.index(old_name)] = clean_name
                elif clean_name not in self.clubs:
                    self.clubs.append(clean_name)
                if self.current_club == old_name:
                    self.current_club = clean_name
            self.save_session_to_file()
            self.draw_screen()

    def add_club_to_bag(self, name, category=None, brand="", model="", loft_deg=0.0, shaft="", lie_deg=0.0, notes=""):
        clean_name = name.strip() if name else ""
        if not clean_name:
            return
        if not category:
            category = infer_club_category(clean_name)
        try:
            loft_val = float(loft_deg) if loft_deg else 0.0
        except (ValueError, TypeError):
            loft_val = 0.0
        try:
            lie_val = float(lie_deg) if lie_deg else 0.0
        except (ValueError, TypeError):
            lie_val = 0.0

        existing = self.get_bag_club(clean_name)
        if existing:
            self.update_club_specs(clean_name, brand=brand, model=model, loft_deg=loft_val, shaft=shaft, category=category, lie_deg=lie_val, notes=notes)
            return
        club_dict = {
            "name": clean_name,
            "category": category,
            "brand": brand,
            "model": model,
            "loft_deg": loft_val,
            "lie_deg": lie_val,
            "shaft": shaft,
            "notes": notes or "",
        }
        self.bag.append(club_dict)
        if clean_name not in self.clubs:
            self.clubs.append(clean_name)
        self.current_club = clean_name
        self.save_session_to_file()
        self.copy_feedback = f"✓ Added {clean_name} to Bag"
        self.root.after(2500, self.clear_copy_feedback)
        self.draw_screen()

    def remove_club_from_bag(self, club_name):
        self.bag = [c for c in self.bag if c.get("name") != club_name]
        # Also drop it from the selectable name list. These are separate
        # stores -- a club added from the club dropdown used to land only in
        # self.clubs, so removing the bag entry alone left the name behind in
        # every dropdown with no way to clear it.
        if club_name in self.clubs and club_name not in DEFAULT_CLUBS:
            self.clubs.remove(club_name)
        if self.current_club == club_name:
            if self.bag:
                self.current_club = self.bag[0].get("name", "Driver")
            elif self.clubs:
                self.current_club = self.clubs[0]
        self.save_session_to_file()
        self.copy_feedback = f"✓ Removed {club_name}"
        self.root.after(2500, self.clear_copy_feedback)
        self.draw_screen()

    def reorder_bag_club(self, club_name, direction="up"):
        idx = next((i for i, c in enumerate(self.bag) if c.get("name") == club_name), -1)
        if idx == -1:
            return
        if direction == "up" and idx > 0:
            self.bag[idx], self.bag[idx - 1] = self.bag[idx - 1], self.bag[idx]
        elif direction == "down" and idx < len(self.bag) - 1:
            self.bag[idx], self.bag[idx + 1] = self.bag[idx + 1], self.bag[idx]
        self.save_session_to_file()
        self.draw_screen()

    def set_bag_scope(self, scope):
        if scope in ("session", "all_time"):
            self.bag_scope = scope
            self.draw_screen()

    def get_bag_club_stats(self, club_name, scope="session"):
        target_clean = str(club_name).strip().lower()
        if scope == "session":
            shots = [
                s for s in self.session_shots 
                if str(s.get("club", "")).strip().lower() == target_clean and not s.get("excluded", False)
            ]
        else:
            shots = []
            for sess in self.sessions:
                for s in sess.get("shots", []):
                    if str(s.get("club", "")).strip().lower() == target_clean and not s.get("excluded", False):
                        shots.append(s)
        
        count = len(shots)
        if count == 0:
            return {
                "shot_count": 0,
                "avg_carry": 0.0, "min_carry": 0.0, "max_carry": 0.0, "std_carry": 0.0,
                "avg_total": 0.0,
                "avg_ball_speed": 0.0, "avg_club_speed": 0.0,
                "avg_smash": 0.0,
                "smash_clamped": True,
                "avg_launch": 0.0,
                "avg_spin": 0.0,
                "avg_offline": 0.0
            }
        
        metrics = [self.extract_shot_metrics(s) for s in shots]
        carries = [m["carry"] for m in metrics]
        totals = [m["total"] for m in metrics]
        bspeeds = [m["ball_speed"] for m in metrics]
        cspeeds = [m["club_speed"] for m in metrics]
        smashes = [m["smash"] for m in metrics]
        launches = [m["launch_angle"] for m in metrics]
        spins = [m["total_spin"] for m in metrics]
        offlines = [m["offline"] for m in metrics]

        avg_c = sum(carries) / count
        min_c = min(carries)
        max_c = max(carries)
        std_c = (sum((x - avg_c) ** 2 for x in carries) / count) ** 0.5 if count > 1 else 0.0

        return {
            "shot_count": count,
            "avg_carry": avg_c,
            "min_carry": min_c,
            "max_carry": max_c,
            "std_carry": std_c,
            "avg_total": sum(totals) / count,
            "avg_ball_speed": sum(bspeeds) / count,
            "avg_club_speed": sum(cspeeds) / count,
            "avg_smash": sum(smashes) / count,
            "avg_launch": sum(launches) / count,
            "avg_spin": sum(spins) / count,
            "avg_offline": sum(offlines) / count,
            # True when every contributing shot had a saturated OGC smash --
            # the average is then a constant, not a measurement.
            "smash_clamped": all(
                self.compute_smash_confidence(
                    float(s.get("ball_speed_meters_per_second") or 0.0),
                    s.get("vertical_launch_angle_degrees"),
                    s.get("total_spin_rpm"),
                ).get("clamped", True)
                for s in shots
            ) if shots else True,
        }

    def extract_shot_metrics(self, s):
        if not isinstance(s, dict):
            return {
                "carry": 0.0, "total": 0.0, "ball_speed": 0.0, "club_speed": 0.0,
                "smash": 0.0, "launch_angle": 0.0, "total_spin": 0.0, "offline": 0.0
            }

        # Correct for a mis-squared device before anything reads direction.
        # Applied here rather than on the incoming event so that shots recorded
        # before the user calibrated are corrected too.
        s = self.aim_corrected(s)

        ogc = s.get("open_golf_coach", {})
        us = ogc.get("us_customary_units", {})
        
        # 1. Carry distance in yards
        carry = us.get("carry_distance_yards")
        if carry is None:
            carry = s.get("carry") or s.get("carry_distance_yards") or s.get("carry_distance")
        if carry is None and ogc.get("carry_distance_meters"):
            carry = float(ogc.get("carry_distance_meters")) * 1.09361
        carry = float(carry or 0.0)

        # 2. Total distance in yards
        total = us.get("total_distance_yards")
        if total is None:
            total = s.get("total") or s.get("total_distance_yards") or s.get("total_distance")
        if total is None and ogc.get("total_distance_meters"):
            total = float(ogc.get("total_distance_meters")) * 1.09361
        if total is None or total <= 0.0:
            total = carry * 1.05
        total = float(total or 0.0)

        # 3. Ball speed in mph
        ball_speed = us.get("ball_speed_mph")
        if ball_speed is None:
            ball_speed = s.get("ball_speed") or s.get("ball_speed_mph")
        if ball_speed is None and s.get("ball_speed_meters_per_second"):
            ball_speed = float(s.get("ball_speed_meters_per_second")) * 2.236936
        ball_speed = float(ball_speed or 0.0)

        # 4. Club speed in mph
        club_speed = us.get("club_speed_mph")
        if club_speed is None:
            club_speed = s.get("club_speed") or s.get("club_speed_mph")
        if club_speed is None and ogc.get("club_speed_meters_per_second"):
            club_speed = float(ogc.get("club_speed_meters_per_second")) * 2.236936
        club_speed = float(club_speed or 0.0)

        # 5. Smash factor
        smash = ogc.get("smash_factor")
        if smash is None:
            smash = s.get("smash") or s.get("smash_factor")
        if (smash is None or smash == 0.0) and club_speed > 0.0:
            smash = ball_speed / club_speed
        smash = float(smash or 0.0)

        # 6. Launch angle in degrees
        launch = s.get("vertical_launch_angle_degrees")
        if launch is None:
            launch = s.get("launch_angle") or s.get("launch_angle_degrees") or ogc.get("vertical_launch_angle_degrees")
        launch = float(launch or 0.0)

        # 7. Total spin in rpm
        spin = ogc.get("total_spin_rpm")
        if spin is None:
            spin = s.get("total_spin_rpm") or s.get("total_spin") or s.get("spin_rate_rpm")
        spin = float(spin or 0.0)

        # 8. Offline distance in yards
        offline = us.get("offline_distance_yards")
        if offline is None:
            offline = s.get("offline") or s.get("offline_distance_yards") or s.get("offline_yards")
        if offline is None and ogc.get("offline_distance_meters"):
            offline = float(ogc.get("offline_distance_meters")) * 1.09361
        offline = float(offline or 0.0)

        return {
            "carry": carry,
            "total": total,
            "ball_speed": ball_speed,
            "club_speed": club_speed,
            "smash": smash,
            "launch_angle": launch,
            "total_spin": spin,
            "offline": offline
        }

    def calculate_bag_gapping(self, scope="session"):
        club_stats_list = []
        for c in self.bag:
            name = c.get("name")
            stats = self.get_bag_club_stats(name, scope=scope)
            if stats["shot_count"] > 0:
                club_stats_list.append({
                    "name": name,
                    "category": c.get("category", "Irons"),
                    "color": self.get_club_color(name),
                    "loft_deg": c.get("loft_deg", 0.0),
                    **stats
                })
        
        # Sort descending by carry distance
        club_stats_list.sort(key=lambda x: x["avg_carry"], reverse=True)

        steps = []
        for i in range(len(club_stats_list) - 1):
            upper = club_stats_list[i]
            lower = club_stats_list[i + 1]
            delta = upper["avg_carry"] - lower["avg_carry"]
            
            # Classification
            if delta < 7.0:
                status = "collision"
                status_text = f"Collision ({delta:.1f}y)"
                color = theme.DANGER
            elif delta > 18.0:
                status = "wide"
                status_text = f"Wide Gap (+{delta:.1f}y)"
                color = theme.WARN
            else:
                status = "healthy"
                status_text = f"+{delta:.1f}y gap"
                color = theme.ACCENT_TEXT

            steps.append({
                "from_club": upper["name"],
                "to_club": lower["name"],
                "delta": delta,
                "status": status,
                "status_text": status_text,
                "color": color
            })

        # Calculate consistency grade
        if len(steps) >= 3:
            deltas = [s["delta"] for s in steps]
            mean_gap = sum(deltas) / len(deltas)
            var_gap = sum((d - mean_gap) ** 2 for d in deltas) / len(deltas)
            std_gap = var_gap ** 0.5
            if std_gap <= 3.5:
                grade = "A (Optimal Gapping)"
                grade_color = theme.ACCENT_TEXT
            elif std_gap <= 6.0:
                grade = "B (Good Gapping)"
                grade_color = theme.ACCENT_LINE
            elif std_gap <= 9.0:
                grade = "C (Variable Gapping)"
                grade_color = theme.WARN
            else:
                grade = "D (Irregular Steps)"
                grade_color = theme.DANGER
        else:
            mean_gap = sum(s["delta"] for s in steps) / len(steps) if steps else 0.0
            grade = "Insufficient Data"
            grade_color = theme.TEXT_3

        return {
            "clubs": club_stats_list,
            "steps": steps,
            "mean_gap": mean_gap,
            "consistency_grade": grade,
            "consistency_color": grade_color
        }

    def open_custom_club_modal(self):
        self.show_club_menu = False
        self.show_tools_menu = False
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.custom_club_input_text = ""
        self.show_custom_club_modal = True
        self.draw_screen()

    def draw_custom_club_modal(self, w, h):
        # 1. Semi-transparent dark overlay
        self.canvas.create_rectangle(0, 0, w, h, fill="#04060A", outline="", stipple="gray75")

        # 2. Centered Modal Box
        modal_w = 480
        modal_h = 220
        cx = w // 2
        cy = h // 2
        x1 = cx - modal_w // 2
        x2 = cx + modal_w // 2
        y1 = cy - modal_h // 2
        y2 = cy + modal_h // 2

        self.custom_club_modal_box_rect = (x1, y1, x2, y2)

        # Shadow & Box Border
        self.canvas.create_rectangle(x1 + 6, y1 + 6, x2 + 6, y2 + 6, fill="#020305", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline=theme.ACCENT_TEXT, width=2)

        # Header
        self.canvas.create_text(cx, y1 + 28, text="🏌️ ADD CUSTOM CLUB TO BAG", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 12, "bold"))
        self.canvas.create_text(cx, y1 + 52, text="Type custom club name (e.g. 2 Hybrid, 7 Wood, 64° Wedge):", fill=theme.TEXT_2, font=(theme.ui_font(), 9))

        # Input Text Box
        in_x1 = cx - 180
        in_x2 = cx + 180
        in_y1 = y1 + 75
        in_y2 = in_y1 + 42
        self.canvas.create_rectangle(in_x1, in_y1, in_x2, in_y2, fill=theme.BG, outline=theme.ACCENT_TEXT, width=2)

        if self.custom_club_input_text:
            display_text = self.custom_club_input_text + " |"
            self.canvas.create_text(cx, (in_y1 + in_y2) // 2, text=display_text, fill=theme.TEXT, font=(theme.ui_font(), 14, "bold"))
        else:
            self.canvas.create_text(cx, (in_y1 + in_y2) // 2, text="Type club name here... |", fill=theme.TEXT_3, font=(theme.ui_font(), 12, "italic"))

        # Buttons
        btn_y1 = in_y2 + 20
        btn_y2 = btn_y1 + 32
        btn_w = 140

        # Add Button (Left)
        add_x1 = cx - btn_w - 10
        add_x2 = cx - 10
        self.custom_club_modal_add_rect = (add_x1, btn_y1, add_x2, btn_y2)
        self.canvas.create_rectangle(add_x1, btn_y1, add_x2, btn_y2, fill=theme.ACCENT_TEXT, outline="")
        self.canvas.create_text((add_x1 + add_x2) // 2, (btn_y1 + btn_y2) // 2, text="✓ Add Club", fill="#08090C", font=(theme.ui_font(), 9, "bold"))

        # Cancel Button (Right)
        can_x1 = cx + 10
        can_x2 = cx + btn_w + 10
        self.custom_club_modal_cancel_rect = (can_x1, btn_y1, can_x2, btn_y2)
        self.canvas.create_rectangle(can_x1, btn_y1, can_x2, btn_y2, fill=theme.HAIRLINE, outline="#323B50")
        self.canvas.create_text((can_x1 + can_x2) // 2, (btn_y1 + btn_y2) // 2, text="Cancel (<Esc>)", fill=theme.TEXT_2, font=(theme.ui_font(), 9, "bold"))

        # Footer shortcut hint
        self.canvas.create_text(cx, y2 - 12, text="Press <Enter> to confirm  •  <Esc> to cancel", fill=theme.TEXT_3, font=(theme.ui_font(), 8))

    def handle_key_press(self, event):
        if self.show_aim_modal:
            if event.keysym == "Escape":
                self.show_aim_modal = False
                self.draw_screen()
                return "break"
            if event.keysym in ("Return", "KP_Enter"):
                self.apply_aim_measurements()
                self.draw_screen()
                return "break"
            if event.keysym == "Tab":
                self.aim_modal_active_field = (
                    "lateral" if self.aim_modal_active_field == "distance"
                    else "distance"
                )
                self.draw_screen()
                return "break"
            f = self.aim_modal_active_field
            cur = self.aim_modal_distance if f == "distance" else self.aim_modal_lateral
            if event.keysym == "BackSpace":
                cur = cur[:-1]
            elif event.char and (event.char.isdigit()
                                 or (event.char == "." and "." not in cur)
                                 or (event.char == "-" and not cur and f == "lateral")):
                cur += event.char
            else:
                return "break"
            if f == "distance":
                self.aim_modal_distance = cur
            else:
                self.aim_modal_lateral = cur
            self.draw_screen()
            return "break"
        if self.show_balance_hardware_modal:
            if event.keysym == "Escape":
                self.show_balance_hardware_modal = False
                self.draw_screen()
                return "break"
            return "break"
        if self.show_spec_editor_modal:
            if event.keysym == "Escape":
                self.show_spec_editor_modal = False
                self.draw_screen()
                return "break"
            elif event.keysym in ("Return", "KP_Enter"):
                self.save_spec_editor_values()
                return "break"
            elif event.keysym == "Tab":
                fields = ["name", "brand", "model", "loft", "lie", "shaft"]
                if self.spec_editor_active_field in fields:
                    curr_i = fields.index(self.spec_editor_active_field)
                    self.spec_editor_active_field = fields[(curr_i + 1) % len(fields)]
                else:
                    self.spec_editor_active_field = "name"
                self.draw_screen()
                return "break"
            elif event.keysym == "BackSpace":
                f = self.spec_editor_active_field
                if f == "name": self.spec_editor_club_name = self.spec_editor_club_name[:-1]
                elif f == "brand": self.spec_editor_brand = self.spec_editor_brand[:-1]
                elif f == "model": self.spec_editor_model = self.spec_editor_model[:-1]
                elif f == "loft": self.spec_editor_loft = self.spec_editor_loft[:-1]
                elif f == "lie": self.spec_editor_lie = self.spec_editor_lie[:-1]
                elif f == "shaft": self.spec_editor_shaft = self.spec_editor_shaft[:-1]
                self.draw_screen()
                return "break"
            elif event.char and event.char.isprintable() and len(event.char) == 1:
                f = self.spec_editor_active_field
                if f == "name" and len(self.spec_editor_club_name) < 25: self.spec_editor_club_name += event.char
                elif f == "brand" and len(self.spec_editor_brand) < 25: self.spec_editor_brand += event.char
                elif f == "model" and len(self.spec_editor_model) < 25: self.spec_editor_model += event.char
                elif f == "loft" and len(self.spec_editor_loft) < 8: self.spec_editor_loft += event.char
                elif f == "lie" and len(self.spec_editor_lie) < 8: self.spec_editor_lie += event.char
                elif f == "shaft" and len(self.spec_editor_shaft) < 25: self.spec_editor_shaft += event.char
                self.draw_screen()
                return "break"
            return "break"

        if self.show_custom_club_modal:
            if event.keysym == "Escape":
                self.show_custom_club_modal = False
                self.draw_screen()
                return "break"
            elif event.keysym in ("Return", "KP_Enter"):
                val = self.custom_club_input_text.strip()
                self.show_custom_club_modal = False
                if val:
                    self.add_custom_club(val)
                else:
                    self.draw_screen()
                return "break"
            elif event.keysym == "BackSpace":
                self.custom_club_input_text = self.custom_club_input_text[:-1]
                self.draw_screen()
                return "break"
            elif event.char and event.char.isprintable() and len(self.custom_club_input_text) < 25:
                self.custom_club_input_text += event.char
                self.draw_screen()
                return "break"
            return "break"

        # Global Hotkeys when modal is closed
        if event.keysym == "Escape":
            self.root.destroy()
        elif event.keysym == "F11" or (event.char and event.char in ("f", "F")):
            self.toggle_fullscreen()
        elif (event.char and event.char in ("m", "M")) or event.keysym == "Tab":
            self.cycle_mode()
        elif event.char == "1":
            self.set_mode(1)
        elif event.char == "2":
            self.set_mode(2)
        elif event.char == "3":
            self.set_mode(3)
        elif event.char == "4":
            self.set_mode(4)
        elif event.char == "5":
            self.set_mode(5)
        elif event.char in ("6", "b", "B"):
            self.set_mode(6)
        elif event.char in ("7", "f", "F") and event.keysym != "F11":
            self.set_mode(7)
        elif event.char in ("8", "w", "W"):
            self.set_mode(8)
        elif event.keysym in ("F1", "F2", "F3", "F4", "F5"):
            f_num = int(event.keysym[1]) - 1
            sess_clubs = self.get_fitting_clubs()
            if 0 <= f_num < len(sess_clubs):
                self.current_club = sess_clubs[f_num]
                self.copy_feedback = f"Switched to {self.current_club}"
                self.root.after(2000, self.clear_copy_feedback)
                self.draw_screen()
        elif event.char in ("0", "p", "P"):
            self.set_mode(0)
        elif event.char in ("s", "S"):
            self.toggle_sidebar()
        elif event.char in ("r", "R"):
            self.rename_active_session()
        elif event.char in ("c", "C"):
            self.clear_session()

    def add_custom_club(self, club_name=None):
        if not club_name:
            self.open_custom_club_modal()
            return
        clean_name = club_name.strip()
        if clean_name:
            if clean_name not in self.clubs:
                self.clubs.append(clean_name)
            # Also add it to the bag. Appending to self.clubs alone only
            # creates a selectable NAME -- the club had no loft, lie or
            # category, so strike scoring fell back to defaults and the club
            # disappeared on restart because the bag is what gets persisted.
            is_new_to_bag = self.get_bag_club(clean_name) is None
            if is_new_to_bag:
                self.add_club_to_bag(clean_name)
            self.current_club = clean_name
            self.show_club_menu = False
            self.show_custom_club_modal = False
            self.save_session_to_file()
            self.copy_feedback = f"✓ Added & Selected '{clean_name}'"
            self.root.after(2500, self.clear_copy_feedback)
            self.draw_screen()
            # A club with no loft scores strikes against a 0 degree face, so
            # send the user straight to the spec editor to fill it in.
            if is_new_to_bag:
                self.open_club_spec_editor(clean_name)

    def open_club_spec_editor(self, club_name=None):
        self.show_club_menu = False
        self.show_tools_menu = False
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.show_custom_club_modal = False

        if club_name and self.get_bag_club(club_name):
            c = self.get_bag_club(club_name)
            self.spec_editor_orig_name = club_name
            self.spec_editor_club_name = club_name
            self.spec_editor_category = c.get("category", infer_club_category(club_name))
            self.spec_editor_brand = c.get("brand", "")
            self.spec_editor_model = c.get("model", "")
            loft = c.get("loft_deg", 0.0)
            self.spec_editor_loft = f"{loft:.1f}" if loft else ""
            lie = c.get("lie_deg", 0.0)
            self.spec_editor_lie = f"{lie:.1f}" if lie else ""
            self.spec_editor_shaft = c.get("shaft", "")
            self.spec_editor_notes = c.get("notes", "")
            self.spec_editor_active_field = "brand"
        else:
            self.spec_editor_orig_name = ""
            self.spec_editor_club_name = ""
            self.spec_editor_category = "Irons"
            self.spec_editor_brand = ""
            self.spec_editor_model = ""
            self.spec_editor_loft = ""
            self.spec_editor_lie = ""
            self.spec_editor_shaft = ""
            self.spec_editor_notes = ""
            self.spec_editor_active_field = "name"

        self.show_spec_editor_modal = True
        self.draw_screen()

    def edit_club_spec_notes(self):
        """Toplevel + Text editor for the notes field on the spec editor modal.

        Only touches self.spec_editor_notes (in-memory draft state) — actual
        persistence happens when the user hits Save Specs, same as every
        other field on this modal.
        """
        try:
            top = tk.Toplevel(self.root)
            top.title("Club Notes")
            top.configure(bg=theme.SURFACE)
            top.geometry("420x260")
            top.transient(self.root)

            text = tk.Text(top, wrap="word", font=(theme.ui_font(), 10))
            text.pack(fill="both", expand=True, padx=10, pady=(10, 4))
            text.insert("1.0", self.spec_editor_notes or "")
            text.focus_set()

            def _save():
                self._save_club_spec_notes(text.get("1.0", "end-1c"))
                top.destroy()

            btn_row = tk.Frame(top, bg=theme.SURFACE)
            btn_row.pack(fill="x", padx=10, pady=(0, 10))
            tk.Button(btn_row, text="Save", command=_save).pack(side="right", padx=(6, 0))
            tk.Button(btn_row, text="Cancel", command=top.destroy).pack(side="right")
        except Exception as exc:
            print(f"[!] Club notes editor failed: {exc}")

    def _save_club_spec_notes(self, text):
        """Core notes-write, split out so tests can call it without a Toplevel."""
        self.spec_editor_notes = text
        self.draw_screen()

    def save_spec_editor_values(self):
        name = self.spec_editor_club_name.strip()
        if not name:
            self.show_spec_editor_modal = False
            self.draw_screen()
            return
        
        try:
            loft_val = float(self.spec_editor_loft) if self.spec_editor_loft else 0.0
        except (ValueError, TypeError):
            loft_val = 0.0
        try:
            lie_val = float(self.spec_editor_lie) if self.spec_editor_lie else 0.0
        except (ValueError, TypeError):
            lie_val = 0.0

        if self.spec_editor_orig_name:
            self.update_club_specs(
                self.spec_editor_orig_name,
                brand=self.spec_editor_brand.strip(),
                model=self.spec_editor_model.strip(),
                loft_deg=loft_val,
                lie_deg=lie_val,
                shaft=self.spec_editor_shaft.strip(),
                category=self.spec_editor_category,
                new_name=name,
                notes=self.spec_editor_notes,
            )
        else:
            self.add_club_to_bag(
                name=name,
                category=self.spec_editor_category,
                brand=self.spec_editor_brand.strip(),
                model=self.spec_editor_model.strip(),
                loft_deg=loft_val,
                lie_deg=lie_val,
                shaft=self.spec_editor_shaft.strip(),
                notes=self.spec_editor_notes,
            )
        self.show_spec_editor_modal = False
        self.copy_feedback = f"✓ Saved {name} Specs"
        self.root.after(2500, self.clear_copy_feedback)
        self.draw_screen()

    def draw_aim_measure_modal(self, w, h):
        """Turn two tape-measure numbers into an aim offset.

        Nobody can look at a launch monitor and say "that's 2.4 degrees off".
        They CAN measure how far away the screen is and how far the device's
        aim point sits off the target line. This does the trigonometry.
        """
        self.canvas.create_rectangle(0, 0, w, h, fill="#04060A", outline="",
                                     stipple="gray75")

        modal_w = min(620, max(500, int(w * 0.52)))
        modal_h = 420
        cx, cy = w // 2, h // 2
        x1, x2 = cx - modal_w // 2, cx + modal_w // 2
        y1, y2 = cy - modal_h // 2, cy + modal_h // 2
        self.aim_modal_box_rect = (x1, y1, x2, y2)

        self.canvas.create_rectangle(x1 + 6, y1 + 6, x2 + 6, y2 + 6,
                                     fill="#020305", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE,
                                     outline=theme.ACCENT_TEXT, width=2)

        self.canvas.create_text(x1 + 35, y1 + 30, text="Measure your aim",
                                fill=theme.TEXT, font=(theme.ui_font(), 15),
                                anchor="w")
        for i, line in enumerate((
            "Put an alignment stick on the target line your device is meant to",
            "watch. Measure to where the device is actually pointing.",
        )):
            self.canvas.create_text(x1 + 35, y1 + 54 + i * 14, text=line,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="w")

        # Diagram: device at the bottom, target line up, aim point offset.
        dgx, dgy = x2 - 110, y1 + 40
        d_h = 96
        self.canvas.create_line(dgx, dgy + d_h, dgx, dgy,
                                fill=theme.GUIDE, dash=(3, 3))
        self.canvas.create_text(dgx - 4, dgy - 4, text="target",
                                fill=theme.TEXT_3,
                                font=(theme.ui_font(), 7), anchor="se")
        try:
            lat_prev = float(self.aim_modal_lateral or 0.0)
            dist_prev = float(self.aim_modal_distance or 0.0)
        except (TypeError, ValueError):
            lat_prev = dist_prev = 0.0
        shown = offset_from_geometry(dist_prev, lat_prev) if dist_prev > 0 else None
        a = math.radians(max(-28.0, min(28.0, (shown or 0.0) * 5.0)))
        self.canvas.create_line(dgx, dgy + d_h,
                                dgx + d_h * math.sin(a), dgy + d_h - d_h * math.cos(a),
                                fill=theme.ACCENT_LINE, width=2)
        self.canvas.create_oval(dgx - 4, dgy + d_h - 4, dgx + 4, dgy + d_h + 4,
                                fill=theme.ACCENT, outline="")
        self.canvas.create_text(dgx, dgy + d_h + 14, text="device",
                                fill=theme.TEXT_3,
                                font=(theme.ui_font(), 7), anchor="n")

        fields = [
            ("distance", "Distance from device to screen / net  (feet)",
             self.aim_modal_distance),
            ("lateral", "Aim point offset from the target line  (inches, − left)",
             self.aim_modal_lateral),
        ]
        self.aim_modal_field_rects = {}
        fy = y1 + 116
        for f_key, f_label, f_val in fields:
            self.canvas.create_text(x1 + 35, fy, text=f_label, fill=theme.TEXT_2,
                                    font=(theme.ui_font(), 8), anchor="w")
            bx1, bx2 = x1 + 35, x2 - 35
            by1 = fy + 14
            by2 = by1 + 30
            self.aim_modal_field_rects[f_key] = (bx1, by1, bx2, by2)
            active = (self.aim_modal_active_field == f_key)
            self.canvas.create_rectangle(bx1, by1, bx2, by2, fill=theme.BG,
                                         outline=theme.ACCENT_TEXT if active
                                         else "#282F42",
                                         width=2 if active else 1)
            txt = (f_val + " |") if active else f_val
            self.canvas.create_text(bx1 + 12, (by1 + by2) // 2,
                                    text=txt or "Click, then type a number…",
                                    fill=theme.TEXT if f_val else "#485065",
                                    font=(theme.ui_font(), 10), anchor="w")
            fy += 66

        # Live result, so the user sees the angle before committing.
        self.canvas.create_line(x1 + 35, fy + 2, x2 - 35, fy + 2,
                                fill=theme.HAIRLINE)
        if shown is None:
            res_txt, res_col = "Enter both measurements", theme.TEXT_3
        else:
            side = "right" if shown > 0 else "left" if shown < 0 else ""
            res_txt = (f"Aim offset  {shown:+.2f}°"
                       + (f"   ({abs(shown):.2f}° {side} of target)" if side else ""))
            res_col = theme.ACCENT_TEXT
        self.canvas.create_text(x1 + 35, fy + 24, text=res_txt, fill=res_col,
                                font=(theme.ui_font(), 13), anchor="w")

        btn_y1 = y2 - 52
        btn_y2 = btn_y1 + 32
        self.aim_modal_save_rect = (cx - 180, btn_y1, cx - 40, btn_y2)
        can_save = shown is not None
        self.canvas.create_rectangle(*self.aim_modal_save_rect,
                                     fill=theme.ACCENT_TEXT if can_save
                                     else theme.HAIRLINE, outline="")
        self.canvas.create_text((cx - 110), (btn_y1 + btn_y2) // 2,
                                text="✓ Apply offset",
                                fill="#08090C" if can_save else theme.TEXT_3,
                                font=(theme.ui_font(), 9, "bold"))
        self.aim_modal_cancel_rect = (cx - 30, btn_y1, cx + 110, btn_y2)
        self.canvas.create_rectangle(*self.aim_modal_cancel_rect,
                                     fill=theme.HAIRLINE, outline="#323B50")
        self.canvas.create_text((cx + 40), (btn_y1 + btn_y2) // 2,
                                text="Cancel (Esc)", fill=theme.TEXT_2,
                                font=(theme.ui_font(), 9, "bold"))
        self.canvas.create_text(cx, y2 - 12,
                                text="Tab switches fields  •  Enter applies",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8))

    def apply_aim_measurements(self):
        """Commit the modal's measurements as an aim offset."""
        try:
            dist = float(self.aim_modal_distance)
            lat = float(self.aim_modal_lateral or 0.0)
        except (TypeError, ValueError):
            self.copy_feedback = "Enter a distance in feet"
            self.root.after(2500, self.clear_copy_feedback)
            return
        offset = offset_from_geometry(dist, lat)
        if offset is None:
            self.copy_feedback = "Distance must be greater than zero"
            self.root.after(2500, self.clear_copy_feedback)
            return
        self.set_aim_offset(offset)
        self.show_aim_modal = False
        self.copy_feedback = f"✓ Aim set to {self.aim_offset_deg:+.2f}°"
        self.root.after(2500, self.clear_copy_feedback)

    def draw_club_spec_editor_modal(self, w, h):
        # 1. Backdrop
        self.canvas.create_rectangle(0, 0, w, h, fill="#04060A", outline="", stipple="gray75")

        # 2. Responsive Modal Box
        modal_w = min(640, max(520, int(w * 0.54)))
        # 6 spec fields at 58px each need ~434px of form; keep the action
        # buttons (y2 - 52) clear of the last input box.
        modal_h = min(580, max(540, int(h * 0.76)))
        cx = w // 2
        cy = h // 2
        x1 = cx - modal_w // 2
        x2 = cx + modal_w // 2
        y1 = cy - modal_h // 2
        y2 = cy + modal_h // 2

        self.spec_editor_box_rect = (x1, y1, x2, y2)

        # Shadow & Card
        self.canvas.create_rectangle(x1 + 6, y1 + 6, x2 + 6, y2 + 6, fill="#020305", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline=theme.ACCENT_TEXT, width=2)

        # Title
        title = f"EDIT CLUB SPECS: {self.spec_editor_orig_name}" if self.spec_editor_orig_name else "ADD NEW CLUB TO BAG"
        self.canvas.create_text(cx, y1 + 24, text=title, fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 11, "bold"))
        self.canvas.create_text(cx, y1 + 44, text="Configure your club profile, category, and equipment specs", fill=theme.TEXT_2, font=(theme.ui_font(), 8))

        self.spec_editor_cat_chips.clear()
        self.spec_editor_field_rects.clear()

        # Category Chips Row (y1 + 58 to y1 + 86)
        cat_y1 = y1 + 58
        cat_y2 = cat_y1 + 28
        chip_gap = 6
        avail_chips_w = modal_w - 70
        chip_w = (avail_chips_w - (len(BAG_CATEGORIES) - 1) * chip_gap) // len(BAG_CATEGORIES)
        start_chip_x = x1 + 35

        for i, cat in enumerate(BAG_CATEGORIES):
            cx1 = start_chip_x + i * (chip_w + chip_gap)
            cx2 = cx1 + chip_w
            self.spec_editor_cat_chips.append((cx1, cat_y1, cx2, cat_y2, cat))
            is_cat_sel = (self.spec_editor_category == cat)
            self.canvas.create_rectangle(cx1, cat_y1, cx2, cat_y2, fill=theme.SURFACE_2 if is_cat_sel else theme.SURFACE, outline=theme.ACCENT_TEXT if is_cat_sel else theme.HAIRLINE)
            
            chip_label = "Woods" if cat == "Woods & Drivers" else ("Hybrids" if cat == "Hybrids & Utilities" else cat)
            self.canvas.create_text((cx1 + cx2) // 2, (cat_y1 + cat_y2) // 2, text=chip_label, fill=theme.ACCENT_TEXT if is_cat_sel else "#A0A7B8", font=(theme.ui_font(), 8, "bold" if is_cat_sel else "normal"))

        # Input Form Grid
        fields = [
            ("name", "Club Name (e.g. 7 Iron, 60° Wedge):", self.spec_editor_club_name),
            ("brand", "Manufacturer / Brand (e.g. TaylorMade, Titleist):", self.spec_editor_brand),
            ("model", "Clubhead Model (e.g. Qi10, T150, SM10):", self.spec_editor_model),
            ("loft", "Loft Angle (°) — check actual spec, not the number on the sole:", self.spec_editor_loft),
            ("lie", "Lie Angle (°, optional):", self.spec_editor_lie),
            ("shaft", "Shaft Specs (e.g. Ventus Black 6X, KBS Tour):", self.spec_editor_shaft),
        ]

        curr_fy = y1 + 102
        field_step = 58
        for f_key, f_label, f_val in fields:
            self.canvas.create_text(x1 + 35, curr_fy, text=f_label, fill=theme.TEXT_2, font=(theme.ui_font(), 8, "bold"), anchor="w")
            
            box_x1 = x1 + 35
            box_x2 = x2 - 35
            box_y1 = curr_fy + 14
            box_y2 = box_y1 + 28
            self.spec_editor_field_rects[f_key] = (box_x1, box_y1, box_x2, box_y2)

            is_f_active = (self.spec_editor_active_field == f_key)
            self.canvas.create_rectangle(box_x1, box_y1, box_x2, box_y2, fill=theme.BG, outline=theme.ACCENT_TEXT if is_f_active else "#282F42", width=1.5 if is_f_active else 1)

            val_display = (f_val + " |") if is_f_active else (f_val if f_val else "")
            val_color = theme.TEXT if f_val else (theme.ACCENT_TEXT if is_f_active else "#485065")
            val_text = val_display if val_display else "Click to enter..."
            self.canvas.create_text(box_x1 + 10, (box_y1 + box_y2) // 2, text=val_text, fill=val_color, font=(theme.ui_font(), 9, "bold" if is_f_active else "normal"), anchor="w")

            curr_fy += field_step

        # Action Buttons
        btn_y1 = y2 - 52
        btn_y2 = btn_y1 + 32

        # Notes row -- lives in the free band between the last input box
        # (ends y1+434) and the action buttons (btn_y1 = y2-52).
        notes_y = y1 + 434
        notes_label_y = notes_y + 14
        self.canvas.create_text(x1 + 35, notes_label_y, text="Notes:", fill=theme.TEXT_2, font=(theme.ui_font(), 8, "bold"), anchor="w")
        notes_preview = (self.spec_editor_notes or "").replace("\n", " ").strip()
        notes_font = (theme.ui_font(), 8)
        max_preview_w = modal_w - 190
        if notes_preview:
            if self._text_width(notes_preview, notes_font) > max_preview_w:
                while notes_preview and self._text_width(notes_preview + "…", notes_font) > max_preview_w:
                    notes_preview = notes_preview[:-1]
                notes_preview += "…"
        else:
            notes_preview = "(none)"
        self.canvas.create_text(x1 + 85, notes_label_y, text=notes_preview, fill=theme.TEXT_3 if notes_preview == "(none)" else theme.TEXT, font=notes_font, anchor="w")

        notes_btn_x1, notes_btn_x2 = x2 - 115, x2 - 35
        notes_btn_y1, notes_btn_y2 = notes_y + 2, notes_y + 24
        self.spec_editor_notes_edit_rect = (notes_btn_x1, notes_btn_y1, notes_btn_x2, notes_btn_y2)
        self.canvas.create_rectangle(notes_btn_x1, notes_btn_y1, notes_btn_x2, notes_btn_y2, fill=theme.SURFACE_2, outline=theme.HAIRLINE)
        self.canvas.create_text((notes_btn_x1 + notes_btn_x2) // 2, (notes_btn_y1 + notes_btn_y2) // 2, text="Edit Notes", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"))

        # Save Button
        save_x1 = cx - 180
        save_x2 = cx - 40
        self.spec_editor_save_rect = (save_x1, btn_y1, save_x2, btn_y2)
        self.canvas.create_rectangle(save_x1, btn_y1, save_x2, btn_y2, fill=theme.ACCENT_TEXT, outline="")
        self.canvas.create_text((save_x1 + save_x2) // 2, (btn_y1 + btn_y2) // 2, text="✓ Save Specs", fill="#08090C", font=(theme.ui_font(), 9, "bold"))

        # Cancel Button
        cancel_x1 = cx - 30
        cancel_x2 = cx + 70
        self.spec_editor_cancel_rect = (cancel_x1, btn_y1, cancel_x2, btn_y2)
        self.canvas.create_rectangle(cancel_x1, btn_y1, cancel_x2, btn_y2, fill=theme.HAIRLINE, outline="#323B50")
        self.canvas.create_text((cancel_x1 + cancel_x2) // 2, (btn_y1 + btn_y2) // 2, text="Cancel", fill=theme.TEXT_2, font=(theme.ui_font(), 9, "bold"))

        # Delete Button (if existing club)
        if self.spec_editor_orig_name:
            del_x1 = cx + 80
            del_x2 = cx + 180
            self.spec_editor_delete_rect = (del_x1, btn_y1, del_x2, btn_y2)
            self.canvas.create_rectangle(del_x1, btn_y1, del_x2, btn_y2, fill="#3A141E", outline=theme.DANGER)
            self.canvas.create_text((del_x1 + del_x2) // 2, (btn_y1 + btn_y2) // 2, text="🗑️ Remove", fill=theme.DANGER, font=(theme.ui_font(), 9, "bold"))
        else:
            self.spec_editor_delete_rect = None

        # Footer Hint
        self.canvas.create_text(cx, y2 - 12, text="Press <Tab> to cycle fields  •  <Enter> to Save  •  <Esc> to Cancel", fill=theme.TEXT_3, font=(theme.ui_font(), 8))

    def get_club_color(self, club_name):
        """Per-club series colour for charts.

        Clubs still need to be distinguishable from each other, but a full
        rainbow fights the rest of the UI. This walks the club order through
        a single hue ramp -- long clubs cool, short clubs warm -- so a chart
        reads as one family and the ordering itself carries meaning.
        """
        ramp = [
            "#7FB3C8",  # driver / longest
            "#84BBC0",
            "#89C2B4",
            "#8FC9A6",
            "#96CE99",
            "#A5D394",
            "#B7D690",
            "#C9D78D",
            "#D8D28A",
            "#E0C689",
            "#E4B788",
            "#E6A587",
            "#E59187",
            "#E27D88",  # lob wedge / shortest
        ]
        order = ["Driver", "3 Wood", "5 Wood", "3 Hybrid", "4 Iron", "5 Iron",
                 "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW"]
        if club_name in order:
            return ramp[order.index(club_name)]
        # Custom clubs: deterministic slot in the same ramp.
        h = sum(ord(c) for c in str(club_name))
        return ramp[h % len(ramp)]

    def poll_pressure_stream(self):
        try:
            if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                pm = obs_server.pressure_manager
                latest = pm.latest_frame
                if latest:
                    self.swing_lab_history.append(latest)
                    if len(self.swing_lab_history) > 200:
                        self.swing_lab_history.pop(0)

                # Views that render live pressure state need the repaint:
                # Swing Lab (8), Setup (10) and the hardware modal. Without
                # this the calibration countdown is drawn once and frozen.
                if (self.view_mode in (8, 10)
                        or self.show_balance_hardware_modal):
                    self.draw_screen()
        except Exception:
            pass
        self.root.after(33, self.poll_pressure_stream)

    def validate_shot_payload(self, msg):
        """Flag physically impossible values in an incoming Nova shot.

        Deliberately ADDITIVE: per AGENTS.md the native payload is preserved
        verbatim, so we annotate `_data_quality` rather than rewriting the
        device's fields. Downstream display code decides how to present a
        suspect shot; nothing here mutates spin, speed or angles.

        Observed in the wild: negative total_spin_rpm (e.g. -471, -859), which
        OGC clamps to 0 and then penalises as a knuckleball, burying effective
        COR and silently pinning smash factor to its floor.
        """
        issues = []
        try:
            if not isinstance(msg, dict):
                return msg
            ogc = msg.get("open_golf_coach", {})
            ogc = ogc if isinstance(ogc, dict) else {}

            total_spin = msg.get("total_spin_rpm", ogc.get("total_spin_rpm"))
            if total_spin is not None and float(total_spin) < 0.0:
                issues.append(f"negative total_spin_rpm ({float(total_spin):.0f})")

            backspin = ogc.get("backspin_rpm")
            if backspin is not None and float(backspin) < 0.0:
                issues.append(f"negative backspin_rpm ({float(backspin):.0f})")

            ball_mps = msg.get("ball_speed_meters_per_second")
            if ball_mps is not None and float(ball_mps) <= 0.0:
                issues.append("non-positive ball_speed")

            if issues:
                msg["_data_quality"] = {"suspect": True, "issues": issues}
                print(f"[!] Shot data quality: {'; '.join(issues)}")
        except (TypeError, ValueError):
            return msg
        return msg

    def poll_queue(self):
        try:
            while True:
                msg = shot_queue.get_nowait()
                if msg.get("_source") == "gspro":
                    # GSPro reports its own club string (from ITS bag config,
                    # e.g. "7i"). Trust it when it matches a real SPS bag
                    # entry; otherwise fall back to the current selection —
                    # never invent a phantom club name.
                    raw_club = (msg.get("_gspro") or {}).get("club")
                    matched = None
                    if raw_club:
                        bag_names = [c.get("name", "") for c in self.bag]
                        matched = match_gspro_club(raw_club, bag_names)
                    club_name = matched or self.current_club
                else:
                    # Nova doesn't report the club — SPS's selection is truth.
                    club_name = self.current_club
                msg["club"] = club_name
                msg["club_color"] = self.get_club_color(club_name)
                msg["timestamp"] = datetime.now().strftime("%I:%M %p")
                self.nova_connected = True
                self.validate_shot_payload(msg)
                self.verify_ogc_model_sync(msg)
                
                sess = self.get_active_session()
                sess["shots"].append(msg)
                self.selected_shot_index = len(sess["shots"]) - 1
                self.current_shot = msg
                self.save_session_to_file()

                # Aim calibration collects raw start lines. The shot is stored
                # uncorrected either way -- calibration reads the device's own
                # frame, which is exactly the bias being measured.
                if self.aim_calibrating:
                    self.aim_calib_shots.append(msg)
                    if len(self.aim_calib_shots) >= MIN_CALIBRATION_SHOTS:
                        self.finish_aim_calibration()


                # Push a COPY to the OBS server: its pressure-capture callback
                # mutates the pushed dict from another thread (adds
                # pressure_trace), which would race with json.dump of the
                # session file and pollute stored history.
                try:
                    obs_server.obs_state.push_shot(dict(msg))
                except Exception as e:
                    print(f"[!] OBS push note: {e}")

                self.draw_screen()
        except queue.Empty:
            pass

        # Repaint when hardware connection state changes, not only when a
        # shot lands. The worker threads update nova_status/gspro_status from
        # the background, and Nova typically connects ~0.5s AFTER the first
        # paint — so without this the UI kept showing "disconnected" forever
        # even though shots would have arrived fine. Cheap: a tuple compare
        # every 100ms, and draw_screen() only when it actually differs.
        try:
            status_now = (
                nova_status.get("connected", False),
                nova_status.get("host", ""),
                gspro_status.get("enabled", False),
                gspro_status.get("connected", False),
                gspro_status.get("db_found", False),
            )
            if status_now != getattr(self, "_last_conn_status", None):
                self._last_conn_status = status_now
                self.draw_screen()
        except Exception:
            pass

        self.root.after(100, self.poll_queue)

    def poll_pressure_traces(self):
        """Attach completed pressure captures to their shots.

        Runs on the Tk thread. The capture itself finishes ~3s after impact on
        the pressure thread, by which point poll_queue() has already appended
        and saved the shot -- so the trace arrives here afterwards and the shot
        is found again by id.

        Derived metrics go inline on the shot (~250 bytes, and what swing
        analysis actually reads). The raw ~200 KB trace goes to its own file.
        """
        try:
            while True:
                shot_id, frames = pressure_trace_queue.get_nowait()
                if not frames:
                    continue

                shot = self._find_shot_by_id(shot_id)
                if shot is None:
                    # Shot may have been cleared, or the session switched
                    # during the 3s capture. Keep the trace anyway; it is
                    # still valid data and costs nothing to leave on disk.
                    self.trace_store.save(shot_id, frames)
                    continue

                metrics = derive_pressure_metrics(frames)
                if metrics:
                    shot["pressure_metrics"] = metrics
                path = self.trace_store.save(shot_id, frames)
                if path:
                    shot["has_pressure_trace"] = True
                    self._trace_cache[str(shot_id)] = frames
                    while len(self._trace_cache) > self.TRACE_CACHE_MAX:
                        self._trace_cache.popitem(last=False)

                if metrics or path:
                    self.save_session_to_file()
                    if self.current_shot is shot:
                        self.draw_screen()
        except queue.Empty:
            pass
        self.root.after(250, self.poll_pressure_traces)

    def _find_shot_by_id(self, shot_id):
        """Locate a stored shot by its Nova shotId, newest first."""
        if shot_id is None:
            return None
        target = str(shot_id)
        for sess in reversed(self.sessions):
            for shot in reversed(sess.get("shots", [])):
                if str(shot.get("shotId")) == target:
                    return shot
        return None

    def get_pressure_trace(self, shot):
        """Full pressure trace for a shot, loaded from disk on demand.

        Returns None when the shot has no stored trace. Traces are not held in
        the session file (see trace_store), so this is the only way to get the
        frame-level data back for review.
        """
        if not shot:
            return None
        # A live shot may still carry its trace inline before it is persisted.
        inline = shot.get("pressure_trace")
        if inline:
            return inline
        if not shot.get("has_pressure_trace"):
            return None
        shot_id = shot.get("shotId")
        if shot_id is None:
            return None
        key = str(shot_id)
        cached = self._trace_cache.get(key)
        if cached is not None:
            self._trace_cache.move_to_end(key)
            return cached
        frames = self.trace_store.load(shot_id)
        if frames:
            self._trace_cache[key] = frames
            while len(self._trace_cache) > self.TRACE_CACHE_MAX:
                self._trace_cache.popitem(last=False)
        return frames

    def rotate_point(self, x, y, cx, cy, angle_rad):
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        nx = cos_a * (x - cx) - sin_a * (y - cy) + cx
        ny = sin_a * (x - cx) + cos_a * (y - cy) + cy
        return nx, ny

    def handle_mouse_hover(self, event):
        # 0. In-Canvas Balance Hardware Modal Hover
        if self.show_balance_hardware_modal:
            for r in (
                self.balance_modal_close_rect, self.balance_modal_pair_rect,
                self.balance_modal_stance_rect,
                self.balance_modal_tare_rect, self.balance_modal_sim_rect,
                self.balance_modal_copy_pin_rect, self.balance_modal_bt_settings_rect,
                self.balance_modal_mode_1_rect, self.balance_modal_mode_2_rect,
                self.balance_modal_assign_btn_rect,
                self.balance_modal_step_a_rect, self.balance_modal_step_b_rect
            ):
                if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                    self.canvas.config(cursor="hand2")
                    return
            self.canvas.config(cursor="")
            return

        # 0a. In-Canvas Spec Editor Modal Hover
        if self.show_spec_editor_modal:
            for cx1, cy1, cx2, cy2, _ in self.spec_editor_cat_chips:
                if cx1 <= event.x <= cx2 and cy1 <= event.y <= cy2:
                    self.canvas.config(cursor="hand2")
                    return
            for f_key, (bx1, by1, bx2, by2) in self.spec_editor_field_rects.items():
                if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                    self.canvas.config(cursor="xterm")
                    return
            if self.spec_editor_save_rect and self.spec_editor_save_rect[0] <= event.x <= self.spec_editor_save_rect[2] and self.spec_editor_save_rect[1] <= event.y <= self.spec_editor_save_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.spec_editor_cancel_rect and self.spec_editor_cancel_rect[0] <= event.x <= self.spec_editor_cancel_rect[2] and self.spec_editor_cancel_rect[1] <= event.y <= self.spec_editor_cancel_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.spec_editor_delete_rect and self.spec_editor_delete_rect[0] <= event.x <= self.spec_editor_delete_rect[2] and self.spec_editor_delete_rect[1] <= event.y <= self.spec_editor_delete_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            self.canvas.config(cursor="")
            return

        # 0b. In-Canvas Custom Club Modal Hover
        if self.show_custom_club_modal:
            if self.custom_club_modal_add_rect and self.custom_club_modal_add_rect[0] <= event.x <= self.custom_club_modal_add_rect[2] and self.custom_club_modal_add_rect[1] <= event.y <= self.custom_club_modal_add_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.custom_club_modal_cancel_rect and self.custom_club_modal_cancel_rect[0] <= event.x <= self.custom_club_modal_cancel_rect[2] and self.custom_club_modal_cancel_rect[1] <= event.y <= self.custom_club_modal_cancel_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            self.canvas.config(cursor="")
            return

        # 1. Overlay Menus Hover
        if self.show_session_dropdown:
            for x1, y1, x2, y2, _ in self.session_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
        if self.show_filter_dropdown:
            for x1, y1, x2, y2, _ in self.filter_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
        if self.show_tools_menu:
            for x1, y1, x2, y2, _ in self.tools_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
        if self.show_club_menu:
            for x1, y1, x2, y2, _ in self.club_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return

        # 1a. Rail Setup slot
        if self.nav_setup_rect:
            r = self.nav_setup_rect
            if r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                self.canvas.config(cursor="hand2")
                return

        # 1b. Overview interactive regions
        if self.view_mode == 9:
            for r in (self.overview_viewall_rect, self.overview_prev_rect,
                      self.overview_next_rect):
                if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                    self.canvas.config(cursor="hand2")
                    return
            for bx1, by1, bx2, by2, _ in self.overview_bar_rects:
                if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                    self.canvas.config(cursor="hand2")
                    return

        # 2. Sidebar Elements Hover
        if not self.sidebar_collapsed:
            if self.sidebar_toggle_rect and self.sidebar_toggle_rect[0] <= event.x <= self.sidebar_toggle_rect[2] and self.sidebar_toggle_rect[1] <= event.y <= self.sidebar_toggle_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.sidebar_session_btn_rect and self.sidebar_session_btn_rect[0] <= event.x <= self.sidebar_session_btn_rect[2] and self.sidebar_session_btn_rect[1] <= event.y <= self.sidebar_session_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.sidebar_rename_sess_btn_rect and self.sidebar_rename_sess_btn_rect[0] <= event.x <= self.sidebar_rename_sess_btn_rect[2] and self.sidebar_rename_sess_btn_rect[1] <= event.y <= self.sidebar_rename_sess_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.sidebar_new_sess_btn_rect and self.sidebar_new_sess_btn_rect[0] <= event.x <= self.sidebar_new_sess_btn_rect[2] and self.sidebar_new_sess_btn_rect[1] <= event.y <= self.sidebar_new_sess_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.sidebar_filter_btn_rect and self.sidebar_filter_btn_rect[0] <= event.x <= self.sidebar_filter_btn_rect[2] and self.sidebar_filter_btn_rect[1] <= event.y <= self.sidebar_filter_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.sidebar_clear_btn_rect and self.sidebar_clear_btn_rect[0] <= event.x <= self.sidebar_clear_btn_rect[2] and self.sidebar_clear_btn_rect[1] <= event.y <= self.sidebar_clear_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            for x1, y1, x2, y2, _ in self.sidebar_shot_card_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
        else:
            if self.sidebar_toggle_rect and self.sidebar_toggle_rect[0] <= event.x <= self.sidebar_toggle_rect[2] and self.sidebar_toggle_rect[1] <= event.y <= self.sidebar_toggle_rect[3]:
                self.canvas.config(cursor="hand2")
                return

        # 3. Header Buttons Hover
        for mode_id, (x1, y1, x2, y2) in self.mode_pill_rects.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.canvas.config(cursor="hand2")
                return

        if self.club_btn_rect and self.club_btn_rect[0] <= event.x <= self.club_btn_rect[2] and self.club_btn_rect[1] <= event.y <= self.club_btn_rect[3]:
            self.canvas.config(cursor="hand2")
            return

        if self.tools_btn_rect and self.tools_btn_rect[0] <= event.x <= self.tools_btn_rect[2] and self.tools_btn_rect[1] <= event.y <= self.tools_btn_rect[3]:
            self.canvas.config(cursor="hand2")
            return

        if self.fullscreen_btn_rect and self.fullscreen_btn_rect[0] <= event.x <= self.fullscreen_btn_rect[2] and self.fullscreen_btn_rect[1] <= event.y <= self.fullscreen_btn_rect[3]:
            self.canvas.config(cursor="hand2")
            return

        # 4. Viewport Interactive Elements Hover
        if self.view_mode == 2:
            if self.range_launch_web_rect and self.range_launch_web_rect[0] <= event.x <= self.range_launch_web_rect[2] and self.range_launch_web_rect[1] <= event.y <= self.range_launch_web_rect[3]:
                self.canvas.config(cursor="hand2")
                return

        if self.view_mode == 3:
            if self.dispersion_splitter_rect and self.dispersion_splitter_rect[0] <= event.x <= self.dispersion_splitter_rect[2] and self.dispersion_splitter_rect[1] <= event.y <= self.dispersion_splitter_rect[3]:
                self.canvas.config(cursor="sb_h_double_arrow")
                return
            for x1, y1, x2, y2, _ in self.dispersion_submode_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.dispersion_club_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for dx, dy, _ in self.dispersion_dot_rects:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    self.canvas.config(cursor="hand2")
                    return

        if self.view_mode == 4:
            for x1, y1, x2, y2, _ in self.table_header_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.table_checkbox_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.table_row_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return

        if self.view_mode == 6:
            if self.bag_scope_session_rect and self.bag_scope_session_rect[0] <= event.x <= self.bag_scope_session_rect[2] and self.bag_scope_session_rect[1] <= event.y <= self.bag_scope_session_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.bag_scope_all_rect and self.bag_scope_all_rect[0] <= event.x <= self.bag_scope_all_rect[2] and self.bag_scope_all_rect[1] <= event.y <= self.bag_scope_all_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            if self.bag_add_club_btn_rect and self.bag_add_club_btn_rect[0] <= event.x <= self.bag_add_club_btn_rect[2] and self.bag_add_club_btn_rect[1] <= event.y <= self.bag_add_club_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            for x1, y1, x2, y2, _ in self.bag_edit_btn_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.bag_move_up_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.bag_move_down_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.bag_club_card_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return

        if self.view_mode == 8:
            for r in (self.swing_lab_tare_rect, self.swing_lab_hw_rect, self.swing_lab_demo_rect):
                if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                    self.canvas.config(cursor="hand2")
                    return
        if self.view_mode == 7:
            if self.fitting_splitter_rect and self.fitting_splitter_rect[0] <= event.x <= self.fitting_splitter_rect[2] and self.fitting_splitter_rect[1] <= event.y <= self.fitting_splitter_rect[3]:
                self.canvas.config(cursor="sb_h_double_arrow")
                return
            if self.fitting_add_club_rect and self.fitting_add_club_rect[0] <= event.x <= self.fitting_add_club_rect[2] and self.fitting_add_club_rect[1] <= event.y <= self.fitting_add_club_rect[3]:
                self.canvas.config(cursor="hand2")
                return
            for x1, y1, x2, y2, _ in self.fitting_submode_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.fitting_club_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for x1, y1, x2, y2, _ in self.fitting_baseline_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return
            for dx, dy, _ in self.fitting_dot_rects:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    self.canvas.config(cursor="hand2")
                    return

        self.canvas.config(cursor="")

    def handle_mouse_press(self, event):
        # 0a. Rail Setup slot. Checked before the modal handler so the button
        # also closes the modal -- otherwise clicking it while open would be
        # swallowed by the modal's own hit testing and feel dead.
        r = self.nav_setup_rect
        if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
            self.set_mode(10)
            return

        # 0. In-Canvas Balance Hardware Modal Click Handling
        if self.show_balance_hardware_modal:
            if self.balance_modal_close_rect and self.balance_modal_close_rect[0] <= event.x <= self.balance_modal_close_rect[2] and self.balance_modal_close_rect[1] <= event.y <= self.balance_modal_close_rect[3]:
                self.show_balance_hardware_modal = False
                self.draw_screen()
                return
            if self.balance_modal_copy_pin_rect and self.balance_modal_copy_pin_rect[0] <= event.x <= self.balance_modal_copy_pin_rect[2] and self.balance_modal_copy_pin_rect[1] <= event.y <= self.balance_modal_copy_pin_rect[3]:
                if self.balance_modal_pin_text:
                    try:
                        self.root.clipboard_clear()
                        self.root.clipboard_append(self.balance_modal_pin_text)
                        self.copy_feedback = "✓ PIN Copied! Paste into Windows Bluetooth prompt (Ctrl+V)"
                        self.root.after(3000, self.clear_copy_feedback)
                        self.draw_screen()
                    except Exception as e:
                        print(f"[!] Clipboard copy failed: {e}")
                return
            if self.balance_modal_bt_settings_rect and self.balance_modal_bt_settings_rect[0] <= event.x <= self.balance_modal_bt_settings_rect[2] and self.balance_modal_bt_settings_rect[1] <= event.y <= self.balance_modal_bt_settings_rect[3]:
                try:
                    from src.hardware.pressure.bluetooth_windows import (
                        open_windows_bluetooth_settings,
                    )
                    open_windows_bluetooth_settings()
                    self.copy_feedback = "✓ Opening Bluetooth Settings..."
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                except Exception as e:
                    print(f"[!] Launch settings failed: {e}")
                return
            if self.balance_modal_pair_rect and self.balance_modal_pair_rect[0] <= event.x <= self.balance_modal_pair_rect[2] and self.balance_modal_pair_rect[1] <= event.y <= self.balance_modal_pair_rect[3]:
                self.copy_feedback = "Scanning for Wii Balance Boards..."
                self.root.after(2000, self.clear_copy_feedback)
                def _do_pair():
                    try:
                        from src.hardware.pressure import connect_board
                        connect_board()
                    except Exception as e:
                        print(f"[!] Pairing notice: {e}")
                threading.Thread(target=_do_pair, daemon=True).start()
                self.draw_screen()
                return
            if self.balance_modal_tare_rect and self.balance_modal_tare_rect[0] <= event.x <= self.balance_modal_tare_rect[2] and self.balance_modal_tare_rect[1] <= event.y <= self.balance_modal_tare_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.tare()
                    self.swing_lab_history.clear()
                    self.copy_feedback = "✓ Baseline Zeroed (Tared)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_align_rect and self.balance_modal_align_rect[0] <= event.x <= self.balance_modal_align_rect[2] and self.balance_modal_align_rect[1] <= event.y <= self.balance_modal_align_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.start_stance_alignment(duration_sec=4.0)
                    self.copy_feedback = "⏳ Stand still in address posture (4s)..."
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_stance_rect and self.balance_modal_stance_rect[0] <= event.x <= self.balance_modal_stance_rect[2] and self.balance_modal_stance_rect[1] <= event.y <= self.balance_modal_stance_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    pm_ = obs_server.pressure_manager
                    if pm_.get_stance_width_status().get("active"):
                        pm_.cancel_stance_width_calibration()
                        self.copy_feedback = "Stance width measurement cancelled"
                    else:
                        pm_.start_stance_width_calibration()
                        self.copy_feedback = "📏 Shift weight to your LEFT foot and hold"
                    self.root.after(2500, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_sim_rect and self.balance_modal_sim_rect[0] <= event.x <= self.balance_modal_sim_rect[2] and self.balance_modal_sim_rect[1] <= event.y <= self.balance_modal_sim_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    curr = obs_server.pressure_manager.is_simulator
                    obs_server.pressure_manager.set_simulator(not curr)
                    self.copy_feedback = f"Simulator: {'[ON]' if not curr else '[OFF]'}"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_mode_1_rect and self.balance_modal_mode_1_rect[0] <= event.x <= self.balance_modal_mode_1_rect[2] and self.balance_modal_mode_1_rect[1] <= event.y <= self.balance_modal_mode_1_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.set_board_mode("single")
                    self.copy_feedback = "Mode: 1 Board (Single Mat)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_mode_2_rect and self.balance_modal_mode_2_rect[0] <= event.x <= self.balance_modal_mode_2_rect[2] and self.balance_modal_mode_2_rect[1] <= event.y <= self.balance_modal_mode_2_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.set_board_mode("dual")
                    self.copy_feedback = "Mode: 2 Boards (Dual Plate)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_assign_btn_rect and self.balance_modal_assign_btn_rect[0] <= event.x <= self.balance_modal_assign_btn_rect[2] and self.balance_modal_assign_btn_rect[1] <= event.y <= self.balance_modal_assign_btn_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.start_assignment_wizard()
                    self.copy_feedback = "🦶 Wizard Started: Step on LEFT Board"
                    self.root.after(3000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_step_a_rect and self.balance_modal_step_a_rect[0] <= event.x <= self.balance_modal_step_a_rect[2] and self.balance_modal_step_a_rect[1] <= event.y <= self.balance_modal_step_a_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.update_assignment_wizard(35.0, 0.0)
                    self.copy_feedback = "🦶 Stepped on Board A (35 kg)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_step_b_rect and self.balance_modal_step_b_rect[0] <= event.x <= self.balance_modal_step_b_rect[2] and self.balance_modal_step_b_rect[1] <= event.y <= self.balance_modal_step_b_rect[3]:
                if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                    obs_server.pressure_manager.update_assignment_wizard(0.0, 35.0)
                    self.copy_feedback = "🦶 Stepped on Board B (35 kg)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.balance_modal_box_rect:
                bx1, by1, bx2, by2 = self.balance_modal_box_rect
                if not (bx1 <= event.x <= bx2 and by1 <= event.y <= by2):
                    self.show_balance_hardware_modal = False
                    self.draw_screen()
                    return
            return

        # 0a. In-Canvas Spec Editor Modal Click Handling
        if self.show_aim_modal:
            for f_key, (bx1, by1, bx2, by2) in self.aim_modal_field_rects.items():
                if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                    self.aim_modal_active_field = f_key
                    self.draw_screen()
                    return
            r = self.aim_modal_save_rect
            if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                self.apply_aim_measurements()
                self.draw_screen()
                return
            r = self.aim_modal_cancel_rect
            if r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]:
                self.show_aim_modal = False
                self.draw_screen()
                return
            # A click outside the card dismisses, matching the other modals.
            b = self.aim_modal_box_rect
            if b and not (b[0] <= event.x <= b[2] and b[1] <= event.y <= b[3]):
                self.show_aim_modal = False
                self.draw_screen()
            return

        if self.show_spec_editor_modal:
            for cx1, cy1, cx2, cy2, cat in self.spec_editor_cat_chips:
                if cx1 <= event.x <= cx2 and cy1 <= event.y <= cy2:
                    self.spec_editor_category = cat
                    self.draw_screen()
                    return
            for f_key, (bx1, by1, bx2, by2) in self.spec_editor_field_rects.items():
                if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                    self.spec_editor_active_field = f_key
                    self.draw_screen()
                    return
            if self.spec_editor_notes_edit_rect and self.spec_editor_notes_edit_rect[0] <= event.x <= self.spec_editor_notes_edit_rect[2] and self.spec_editor_notes_edit_rect[1] <= event.y <= self.spec_editor_notes_edit_rect[3]:
                self.edit_club_spec_notes()
                return
            if self.spec_editor_save_rect and self.spec_editor_save_rect[0] <= event.x <= self.spec_editor_save_rect[2] and self.spec_editor_save_rect[1] <= event.y <= self.spec_editor_save_rect[3]:
                self.save_spec_editor_values()
                return
            if self.spec_editor_cancel_rect and self.spec_editor_cancel_rect[0] <= event.x <= self.spec_editor_cancel_rect[2] and self.spec_editor_cancel_rect[1] <= event.y <= self.spec_editor_cancel_rect[3]:
                self.show_spec_editor_modal = False
                self.draw_screen()
                return
            if self.spec_editor_delete_rect and self.spec_editor_delete_rect[0] <= event.x <= self.spec_editor_delete_rect[2] and self.spec_editor_delete_rect[1] <= event.y <= self.spec_editor_delete_rect[3]:
                if self.spec_editor_orig_name:
                    self.remove_club_from_bag(self.spec_editor_orig_name)
                self.show_spec_editor_modal = False
                self.draw_screen()
                return
            if self.spec_editor_box_rect:
                bx1, by1, bx2, by2 = self.spec_editor_box_rect
                if not (bx1 <= event.x <= bx2 and by1 <= event.y <= by2):
                    self.show_spec_editor_modal = False
                    self.draw_screen()
                    return
            return

        # 0b. In-Canvas Custom Club Modal Click Handling
        if self.show_custom_club_modal:
            if self.custom_club_modal_add_rect and self.custom_club_modal_add_rect[0] <= event.x <= self.custom_club_modal_add_rect[2] and self.custom_club_modal_add_rect[1] <= event.y <= self.custom_club_modal_add_rect[3]:
                val = self.custom_club_input_text.strip()
                self.show_custom_club_modal = False
                if val:
                    self.add_custom_club(val)
                else:
                    self.draw_screen()
                return
            elif self.custom_club_modal_cancel_rect and self.custom_club_modal_cancel_rect[0] <= event.x <= self.custom_club_modal_cancel_rect[2] and self.custom_club_modal_cancel_rect[1] <= event.y <= self.custom_club_modal_cancel_rect[3]:
                self.show_custom_club_modal = False
                self.draw_screen()
                return
            if self.custom_club_modal_box_rect:
                bx1, by1, bx2, by2 = self.custom_club_modal_box_rect
                if not (bx1 <= event.x <= bx2 and by1 <= event.y <= by2):
                    self.show_custom_club_modal = False
                    self.draw_screen()
                    return
            return

        # 1. Floating Dropdowns Clicks
        if self.show_session_dropdown:
            for x1, y1, x2, y2, s_idx in self.session_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if s_idx == -1:
                        self.create_new_session()
                    elif s_idx == -2:
                        self.rename_active_session()
                    elif s_idx == -3:
                        self.delete_empty_sessions()
                    elif s_idx == -4:
                        self.edit_session_notes()
                    elif s_idx <= -1000:
                        # Per-row ✕ delete (encoded as -1000 - index).
                        self.delete_session(-1000 - s_idx)
                    else:
                        self.switch_session(s_idx)
                    return
            self.show_session_dropdown = False
            self.draw_screen()
            return

        if self.show_filter_dropdown:
            for x1, y1, x2, y2, club_name in self.filter_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.club_filter = club_name
                    self.sidebar_scroll_offset = 0
                    self.show_filter_dropdown = False
                    self.draw_screen()
                    return
            self.show_filter_dropdown = False
            self.draw_screen()
            return

        if self.show_tools_menu:
            for x1, y1, x2, y2, action in self.tools_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if action == "open_config":
                        webbrowser.open(f"http://localhost:{obs_server.OBS_PORT}/config")
                    elif action == "copy_obs_url":
                        self.copy_to_clipboard(f"http://localhost:{obs_server.OBS_PORT}")
                    elif action == "copy_divot_url":
                        self.copy_to_clipboard(f"http://localhost:{obs_server.OBS_PORT}/divot")
                    elif action == "open_divot":
                        webbrowser.open(f"http://localhost:{obs_server.OBS_PORT}/divot")
                    elif action == "copy_tiles_url":
                        self.copy_to_clipboard(f"http://localhost:{obs_server.OBS_PORT}/tiles")
                    elif action == "open_tiles":
                        webbrowser.open(f"http://localhost:{obs_server.OBS_PORT}/tiles")
                    elif action == "open_range":
                        self.launch_3d_range()
                    elif action == "set_mode_2" or action == "set_mode_0":
                        self.set_mode(0)
                    elif action == "open_setup":
                        # Route to the Setup page (view_mode 10), which now
                        # owns board pairing, alignment, and tare -- the old
                        # balance-hardware modal was a dead end that never
                        # reached it.
                        self.set_mode(10)
                    elif action == "open_shot_source":
                        self.open_shot_source_picker()
                    elif action == "clear_session":
                        self.clear_session()
                    break
            self.show_tools_menu = False
            self.draw_screen()
            return

        if self.show_club_menu:
            for x1, y1, x2, y2, club_name in self.club_menu_items:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if club_name == "__add_custom__":
                        self.open_custom_club_modal()
                        return
                    else:
                        self.current_club = club_name
                    break
            self.show_club_menu = False
            self.draw_screen()
            return

        # 2. Sidebar Interactive Clicks
        if self.sidebar_toggle_rect and self.sidebar_toggle_rect[0] <= event.x <= self.sidebar_toggle_rect[2] and self.sidebar_toggle_rect[1] <= event.y <= self.sidebar_toggle_rect[3]:
            self.toggle_sidebar()
            return

        if not self.sidebar_collapsed and theme.RAIL_W < event.x <= self.sidebar_width:
            if self.sidebar_session_btn_rect and self.sidebar_session_btn_rect[0] <= event.x <= self.sidebar_session_btn_rect[2] and self.sidebar_session_btn_rect[1] <= event.y <= self.sidebar_session_btn_rect[3]:
                self.show_session_dropdown = not self.show_session_dropdown
                self.show_filter_dropdown = False
                self.draw_screen()
                return

            if self.sidebar_rename_sess_btn_rect and self.sidebar_rename_sess_btn_rect[0] <= event.x <= self.sidebar_rename_sess_btn_rect[2] and self.sidebar_rename_sess_btn_rect[1] <= event.y <= self.sidebar_rename_sess_btn_rect[3]:
                self.rename_active_session()
                return

            if self.sidebar_new_sess_btn_rect and self.sidebar_new_sess_btn_rect[0] <= event.x <= self.sidebar_new_sess_btn_rect[2] and self.sidebar_new_sess_btn_rect[1] <= event.y <= self.sidebar_new_sess_btn_rect[3]:
                self.create_new_session()
                return

            if self.sidebar_filter_btn_rect and self.sidebar_filter_btn_rect[0] <= event.x <= self.sidebar_filter_btn_rect[2] and self.sidebar_filter_btn_rect[1] <= event.y <= self.sidebar_filter_btn_rect[3]:
                self.show_filter_dropdown = not self.show_filter_dropdown
                self.show_session_dropdown = False
                self.draw_screen()
                return

            if self.sidebar_clear_btn_rect and self.sidebar_clear_btn_rect[0] <= event.x <= self.sidebar_clear_btn_rect[2] and self.sidebar_clear_btn_rect[1] <= event.y <= self.sidebar_clear_btn_rect[3]:
                self.clear_session()
                return

            # Check Shot Delete (✕) Clicks -- before card selection, so the
            # ✕ never falls through to "select this shot" instead.
            for x1, y1, x2, y2, shot_idx in self.shot_delete_btn_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.delete_shot(shot_idx)
                    return

            # Check Shot Card Clicks
            for x1, y1, x2, y2, shot_idx in self.sidebar_shot_card_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if 0 <= shot_idx < len(self.session_shots):
                        self.selected_shot_index = shot_idx
                        self.current_shot = self.session_shots[shot_idx]
                        self.draw_screen()
                        return

        # 3. Header Buttons Clicks
        for mode_id, (x1, y1, x2, y2) in self.mode_pill_rects.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.set_mode(mode_id)
                return

        if self.club_btn_rect and self.club_btn_rect[0] <= event.x <= self.club_btn_rect[2] and self.club_btn_rect[1] <= event.y <= self.club_btn_rect[3]:
            self.show_club_menu = not self.show_club_menu
            self.show_tools_menu = False
            self.draw_screen()
            return

        if self.dexterity_btn_rect and self.dexterity_btn_rect[0] <= event.x <= self.dexterity_btn_rect[2] and self.dexterity_btn_rect[1] <= event.y <= self.dexterity_btn_rect[3]:
            self.is_left_handed = not self.is_left_handed
            self.show_club_menu = False
            self.show_tools_menu = False
            self.copy_feedback = f"Switched to {'Left-Handed (LH)' if self.is_left_handed else 'Right-Handed (RH)'} Mode"
            self.root.after(2500, self.clear_copy_feedback)
            self.save_session_to_file()
            self.draw_screen()
            return

        if self.tools_btn_rect and self.tools_btn_rect[0] <= event.x <= self.tools_btn_rect[2] and self.tools_btn_rect[1] <= event.y <= self.tools_btn_rect[3]:
            self.show_tools_menu = not self.show_tools_menu
            self.show_club_menu = False
            self.draw_screen()
            return

        if self.fullscreen_btn_rect and self.fullscreen_btn_rect[0] <= event.x <= self.fullscreen_btn_rect[2] and self.fullscreen_btn_rect[1] <= event.y <= self.fullscreen_btn_rect[3]:
            self.toggle_fullscreen()
            return

        # 4. Viewport Interactive Clicks
        if self.view_mode == 2:
            if self.range_launch_web_rect and self.range_launch_web_rect[0] <= event.x <= self.range_launch_web_rect[2] and self.range_launch_web_rect[1] <= event.y <= self.range_launch_web_rect[3]:
                self.launch_3d_range()
                return

        if self.view_mode == 3:
            if self.dispersion_splitter_rect and self.dispersion_splitter_rect[0] <= event.x <= self.dispersion_splitter_rect[2] and self.dispersion_splitter_rect[1] <= event.y <= self.dispersion_splitter_rect[3]:
                self.dispersion_splitter_dragging = True
                self.draw_screen()
                return

            for x1, y1, x2, y2, sub_key in self.dispersion_submode_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.dispersion_view_submode = sub_key
                    self.draw_screen()
                    return

            for x1, y1, x2, y2, club_name in self.dispersion_club_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.dispersion_selected_club = club_name
                    self.draw_screen()
                    return
            for dx, dy, idx in self.dispersion_dot_rects:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    if 0 <= idx < len(self.session_shots):
                        self.selected_shot_index = idx
                        self.current_shot = self.session_shots[idx]
                        self.draw_screen()
                        return

        if self.view_mode == 10:
            def _h(r):
                return r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]
            pm = getattr(obs_server, "pressure_manager", None)

            if _h(self.setup_mode_1_rect) or _h(self.setup_mode_2_rect):
                want_dual = _h(self.setup_mode_2_rect)
                if pm:
                    pm.set_board_mode("dual" if want_dual else "single")
                    self.copy_feedback = ("Mode: 2 Boards (Dual Plate)"
                                          if want_dual else "Mode: 1 Board (Single Mat)")
                    self.root.after(2000, self.clear_copy_feedback)
                self.draw_screen()
                return

            if _h(self.setup_pair_rect):
                self.copy_feedback = "Scanning for Wii Balance Boards..."
                self.root.after(2000, self.clear_copy_feedback)

                def _do_pair():
                    try:
                        from src.hardware.pressure import connect_board
                        connect_board()
                    except Exception as e:
                        print(f"[!] Pairing notice: {e}")
                threading.Thread(target=_do_pair, daemon=True).start()
                self.draw_screen()
                return

            # Step chips feed the assignment wizard a simulated load so a
            # user can drive it without a board, matching the modal.
            for rect, (kg_a, kg_b) in ((self.setup_step_a_rect, (35.0, 0.0)),
                                       (self.setup_step_b_rect, (0.0, 35.0))):
                if _h(rect):
                    if pm:
                        if not (pm.assignment_wizard
                                and pm.assignment_wizard.get_status().get("phase")
                                not in (None, "idle")):
                            pm.start_assignment_wizard()
                        pm.update_assignment_wizard(kg_a, kg_b)
                    self.draw_screen()
                    return

            if _h(self.setup_align_rect):
                try:
                    if pm and hasattr(pm, "start_stance_alignment"):
                        pm.start_stance_alignment(duration_sec=4.0)
                except Exception as e:
                    print(f"[!] Stance alignment failed: {e}")
                self.draw_screen()
                return

            if _h(self.setup_tare_rect):
                try:
                    if pm and hasattr(pm, "tare"):
                        pm.tare()
                        self.copy_feedback = "✓ Boards tared"
                        self.root.after(2000, self.clear_copy_feedback)
                except Exception as e:
                    print(f"[!] Tare failed: {e}")
                self.draw_screen()
                return

            # --- aim calibration ---
            if _h(self.setup_aim_measure_rect):
                self.show_aim_modal = True
                self.aim_modal_active_field = "distance"
                self.draw_screen()
                return

            for ax0, ay0, ax1, ay1, key in getattr(
                    self, "setup_source_btn_rects", []):
                if ax0 <= event.x <= ax1 and ay0 <= event.y <= ay1:
                    # Switch shot source from Setup — the same persisted
                    # setting the splash writes, so a user who never wants
                    # the splash can still choose GSPro.
                    apply_shot_source(source=key)
                    self.copy_feedback = f"Shot source: {key}"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                    return

            for ax0, ay0, ax1, ay1, delta in self.setup_aim_nudge_rects:
                if ax0 <= event.x <= ax1 and ay0 <= event.y <= ay1:
                    self.set_aim_offset(self.aim_offset_deg + delta)
                    self.draw_screen()
                    return

            if _h(self.setup_aim_clear_rect):
                self.set_aim_offset(0.0)
                self.aim_calibrating = False
                self.aim_calib_shots = []
                self.copy_feedback = "Aim calibration cleared"
                self.root.after(2000, self.clear_copy_feedback)
                self.draw_screen()
                return

            if _h(self.setup_aim_start_rect):
                if not self.aim_calibrating:
                    self.aim_calibrating = True
                    self.aim_calib_shots = []
                    self.copy_feedback = "Pick one target and hit at it"
                    self.root.after(2500, self.clear_copy_feedback)
                else:
                    self.finish_aim_calibration()
                self.draw_screen()
                return

        if self.view_mode == 9:
            def _hit(r):
                return r and r[0] <= event.x <= r[2] and r[1] <= event.y <= r[3]

            if _hit(self.overview_viewall_rect):
                # "View all" opens the full shot table.
                self.view_mode = 4
                self.draw_screen()
                return
            for rect, delta in ((self.overview_prev_rect, -1),
                                (self.overview_next_rect, 1)):
                if _hit(rect):
                    cur = (self.selected_shot_index
                           if self.selected_shot_index is not None
                           else len(self.session_shots) - 1)
                    tgt = cur + delta
                    if 0 <= tgt < len(self.session_shots):
                        self.selected_shot_index = tgt
                        self.current_shot = self.session_shots[tgt]
                        self.draw_screen()
                    return
            for bx1, by1, bx2, by2, idx in self.overview_bar_rects:
                if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                    if 0 <= idx < len(self.session_shots):
                        self.selected_shot_index = idx
                        self.current_shot = self.session_shots[idx]
                        self.draw_screen()
                    return

        if self.view_mode == 4:
            # Checkbox click
            for x1, y1, x2, y2, shot_idx in self.table_checkbox_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if 0 <= shot_idx < len(self.session_shots):
                        cur_ex = self.session_shots[shot_idx].get("excluded", False)
                        self.session_shots[shot_idx]["excluded"] = not cur_ex
                        self.save_session_to_file()
                        self.draw_screen()
                        return
            # Column header sort click
            for x1, y1, x2, y2, col_key in self.table_header_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if self.table_sort_col == col_key:
                        self.table_sort_asc = not self.table_sort_asc
                    else:
                        self.table_sort_col = col_key
                        self.table_sort_asc = True
                    self.draw_screen()
                    return
            # Row selection click
            for x1, y1, x2, y2, shot_idx in self.table_row_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    if 0 <= shot_idx < len(self.session_shots):
                        self.selected_shot_index = shot_idx
                        self.current_shot = self.session_shots[shot_idx]
                        self.draw_screen()
                        return

        if self.view_mode == 6:
            if self.bag_scope_session_rect and self.bag_scope_session_rect[0] <= event.x <= self.bag_scope_session_rect[2] and self.bag_scope_session_rect[1] <= event.y <= self.bag_scope_session_rect[3]:
                self.set_bag_scope("session")
                return
            if self.bag_scope_all_rect and self.bag_scope_all_rect[0] <= event.x <= self.bag_scope_all_rect[2] and self.bag_scope_all_rect[1] <= event.y <= self.bag_scope_all_rect[3]:
                self.set_bag_scope("all_time")
                return
            if self.bag_add_club_btn_rect and self.bag_add_club_btn_rect[0] <= event.x <= self.bag_add_club_btn_rect[2] and self.bag_add_club_btn_rect[1] <= event.y <= self.bag_add_club_btn_rect[3]:
                self.open_club_spec_editor(None)
                return
            for x1, y1, x2, y2, c_name in self.bag_edit_btn_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.open_club_spec_editor(c_name)
                    return
            for x1, y1, x2, y2, c_name in self.bag_move_up_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.reorder_bag_club(c_name, direction="up")
                    return
            for x1, y1, x2, y2, c_name in self.bag_move_down_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.reorder_bag_club(c_name, direction="down")
                    return
            for x1, y1, x2, y2, c_name in self.bag_club_card_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.current_club = c_name
                    self.copy_feedback = f"✓ Selected {c_name}"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                    return

        if self.view_mode == 8:
            if self.swing_lab_tare_rect and self.swing_lab_tare_rect[0] <= event.x <= self.swing_lab_tare_rect[2] and self.swing_lab_tare_rect[1] <= event.y <= self.swing_lab_tare_rect[3]:
                if hasattr(obs_server, "pressure_manager"):
                    obs_server.pressure_manager.tare()
                    self.swing_lab_history.clear()
                    self.copy_feedback = "✓ Baseline Zeroed (Tared)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.swing_lab_hw_rect and self.swing_lab_hw_rect[0] <= event.x <= self.swing_lab_hw_rect[2] and self.swing_lab_hw_rect[1] <= event.y <= self.swing_lab_hw_rect[3]:
                # Board pairing lives in Setup now (draw_setup_viewport) --
                # route there instead of opening the old standalone modal's
                # separate pairing flow.
                self.set_mode(10)
                return
            if self.swing_lab_demo_rect and self.swing_lab_demo_rect[0] <= event.x <= self.swing_lab_demo_rect[2] and self.swing_lab_demo_rect[1] <= event.y <= self.swing_lab_demo_rect[3]:
                if hasattr(obs_server, "pressure_manager"):
                    is_on = obs_server.pressure_manager.toggle_demo_swing()
                    self.copy_feedback = "✓ Demo Swing: ON" if is_on else "✓ Demo Swing: OFF"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
        if self.view_mode == 7:
            if self.fitting_splitter_rect and self.fitting_splitter_rect[0] <= event.x <= self.fitting_splitter_rect[2] and self.fitting_splitter_rect[1] <= event.y <= self.fitting_splitter_rect[3]:
                self.fitting_splitter_dragging = True
                self.draw_screen()
                return
            if self.fitting_add_club_rect and self.fitting_add_club_rect[0] <= event.x <= self.fitting_add_club_rect[2] and self.fitting_add_club_rect[1] <= event.y <= self.fitting_add_club_rect[3]:
                self.open_custom_club_modal()
                return
            for x1, y1, x2, y2, sub_key in self.fitting_submode_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.fitting_submode = sub_key
                    self.draw_screen()
                    return
            for x1, y1, x2, y2, c_name in self.fitting_club_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.current_club = c_name
                    self.copy_feedback = f"Active Fitting Club: {c_name}"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                    return
            for x1, y1, x2, y2, c_name in self.fitting_baseline_chip_rects:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.fitting_baseline_club = c_name
                    self.draw_screen()
                    return
            for dx, dy, idx in self.fitting_dot_rects:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    if 0 <= idx < len(self.session_shots):
                        self.selected_shot_index = idx
                        self.current_shot = self.session_shots[idx]
                        self.draw_screen()
                        return

    def handle_mouse_drag(self, event):
        if self.view_mode == 3 and self.dispersion_splitter_dragging:
            offset_x = theme.RAIL_W if self.sidebar_collapsed else self.sidebar_width
            avail_w = max(100, self.canvas.winfo_width() - offset_x)
            rel_x = event.x - offset_x
            new_ratio = max(0.20, min(0.85, rel_x / float(avail_w)))
            self.dispersion_splitter_ratio = new_ratio
            self.draw_screen()
        elif self.view_mode == 7 and self.fitting_splitter_dragging:
            offset_x = theme.RAIL_W if self.sidebar_collapsed else self.sidebar_width
            avail_w = max(100, self.canvas.winfo_width() - offset_x)
            rel_x = event.x - offset_x
            new_ratio = max(0.20, min(0.85, rel_x / float(avail_w)))
            self.fitting_splitter_ratio = new_ratio
            self.draw_screen()

    def handle_mouse_release(self, event):
        if self.dispersion_splitter_dragging:
            self.dispersion_splitter_dragging = False
            self.draw_screen()
        if self.fitting_splitter_dragging:
            self.fitting_splitter_dragging = False
            self.draw_screen()

    def calculate_session_averages(self, club_filter=None):
        shots = [s for s in self.session_shots if not s.get("excluded", False)]
        if club_filter and club_filter != "ALL":
            shots = [s for s in shots if s.get("club") == club_filter]
        if not shots:
            return {}

        count = len(shots)
        sum_bs = sum_cs = sum_sm = sum_la = sum_spin = sum_carry = sum_total = sum_hl = sum_ss = sum_sa = sum_cp = sum_fp = sum_da = sum_apex = sum_off = 0.0

        for shot in shots:
            shot = self.aim_corrected(shot)
            ogc = shot.get("open_golf_coach", {})
            us_units = ogc.get("us_customary_units", {})

            sum_bs += us_units.get("ball_speed_mph", 0.0)
            sum_cs += us_units.get("club_speed_mph", 0.0)
            sum_sm += ogc.get("smash_factor", 1.0)
            sum_la += shot.get("vertical_launch_angle_degrees", 0.0)
            sum_spin += ogc.get("total_spin_rpm", 0.0)
            sum_carry += us_units.get("carry_distance_yards", 0.0)
            sum_total += us_units.get("total_distance_yards", 0.0)
            sum_hl += shot.get("horizontal_launch_angle_degrees", 0.0)
            sum_ss += ogc.get("sidespin_rpm", 0.0)
            sum_sa += ogc.get("spin_axis_degrees", 0.0)
            sum_cp += self.resolve_handed(ogc.get("club_path_degrees"), 0.0)
            sum_fp += self.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
            sum_da += ogc.get("descent_angle_degrees", 0.0)
            sum_apex += us_units.get("peak_height_yards", 0.0)
            sum_off += us_units.get("offline_distance_yards", 0.0)

        return {
            "count": count,
            "ball_speed": sum_bs / count,
            "club_speed": sum_cs / count,
            "smash": sum_sm / count,
            "launch_angle": sum_la / count,
            "total_spin": sum_spin / count,
            "carry": sum_carry / count,
            "total": sum_total / count,
            "push_pull": sum_hl / count,
            "sidespin": sum_ss / count,
            "spin_axis": sum_sa / count,
            "club_path": sum_cp / count,
            "face_to_path": sum_fp / count,
            "descent": sum_da / count,
            "apex": sum_apex / count,
            "offline": sum_off / count
        }

    def draw_left_sidebar(self, w, h):
        if self.sidebar_collapsed:
            return

        # The sidebar's internals use many hardcoded x offsets measured from 0.
        # Rather than rewrite every one, draw it as a tagged group and shift the
        # whole group right by the rail width afterwards. Hit rects registered
        # during the draw are corrected by the same delta.
        self._sidebar_items_start = len(self.canvas.find_all())

        sb_w = self.sidebar_width - theme.RAIL_W

        # 1. Header (y: 0 to 52)
        self.canvas.create_rectangle(0, 0, sb_w, 52, fill=theme.RAIL, outline="")
        self.canvas.create_line(0, 52, sb_w, 52, fill=theme.HAIRLINE)
        self.canvas.create_text(16, 26, text="Shots", fill=theme.TEXT, font=(theme.ui_font(), 12), anchor="w")
        
        # Collapse button [ ◀ ]
        coll_x1, coll_y1, coll_x2, coll_y2 = sb_w - 38, 12, sb_w - 10, 40
        self.sidebar_toggle_rect = (coll_x1, coll_y1, coll_x2, coll_y2)
        self.canvas.create_rectangle(coll_x1, coll_y1, coll_x2, coll_y2, fill=theme.SURFACE_2, outline="")
        self.canvas.create_text((coll_x1 + coll_x2) // 2, 26, text="◀", fill=theme.TEXT_3, font=(theme.ui_font(), 9))

        # 2. Session Bar (y: 52 to 92)
        self.canvas.create_rectangle(0, 52, sb_w, 92, fill=theme.RAIL, outline="")
        
        active_sess = self.get_active_session()
        sess_title = active_sess.get("name", "Session")
        if len(sess_title) > 13:
            sess_title = sess_title[:11] + "..."

        btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2 = 10, 58, sb_w - 74, 86
        self.sidebar_session_btn_rect = (btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2)
        self.canvas.create_rectangle(btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2, fill=theme.SURFACE_2, outline=theme.ACCENT_LINE if self.show_session_dropdown else "")
        self.canvas.create_text(btn_s_x1 + 10, 72, text=f"{sess_title}  ▼", fill=theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")

        # Rename Session Button [ ✏️ ]
        btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2 = sb_w - 68, 58, sb_w - 40, 86
        self.sidebar_rename_sess_btn_rect = (btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2)
        self.canvas.create_rectangle(btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2, fill=theme.SURFACE_2, outline="")
        self.canvas.create_text((btn_ren_x1 + btn_ren_x2) // 2, 72, text="✎", fill=theme.TEXT_3, font=(theme.ui_font(), 10))

        # New Session Button [ ＋ ]
        btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2 = sb_w - 36, 58, sb_w - 8, 86
        self.sidebar_new_sess_btn_rect = (btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2)
        self.canvas.create_rectangle(btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2, fill=theme.ACCENT, outline="")
        self.canvas.create_text((btn_add_x1 + btn_add_x2) // 2, 72, text="＋", fill="#EAF5EE", font=(theme.ui_font(), 11, "bold"))

        # 3. Filter Bar (y: 92 to 128)
        self.canvas.create_rectangle(0, 92, sb_w, 128, fill=theme.RAIL, outline="")
        self.canvas.create_line(0, 128, sb_w, 128, fill=theme.HAIRLINE)
        
        filt_x1, filt_y1, filt_x2, filt_y2 = 10, 97, sb_w - 82, 123
        self.sidebar_filter_btn_rect = (filt_x1, filt_y1, filt_x2, filt_y2)
        filt_label = f"🎯 {self.club_filter} ▼"
        self.canvas.create_rectangle(filt_x1, filt_y1, filt_x2, filt_y2, fill=theme.ACCENT_DEEP if self.club_filter != "ALL" else theme.SURFACE_2, outline=theme.ACCENT_LINE if self.show_filter_dropdown else "")
        self.canvas.create_text(filt_x1 + 10, 110, text=filt_label, fill=theme.ACCENT_TEXT if self.club_filter != "ALL" else theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")

        filtered_shots = self.get_filtered_shots()
        count_str = f"{len(filtered_shots)} shots"
        self.canvas.create_text(sb_w - 12, 110, text=count_str, fill=theme.TEXT_3, font=(theme.ui_font(), 9), anchor="e")

        # 4. Shot Card Stream (y: 132 to h - 42)
        card_stream_y1 = 132
        card_stream_y2 = h - 42
        # 66 not 56: three 8-10pt lines in a real UI face measure ~17px each,
        # so they baseline at 14/35/54 and the card needs descender room under
        # the last one.
        card_h = 66
        card_gap = 6

        self.sidebar_shot_card_rects.clear()
        self.shot_delete_btn_rects.clear()

        if not filtered_shots:
            self.canvas.create_text(sb_w // 2, 220, text="NO SHOTS RECORDED", fill="#353A4B", font=(theme.ui_font(), 10, "bold"))
            self.canvas.create_text(sb_w // 2, 245, text="Hit a shot with Nova or\nchange active club filter.", fill=theme.TEXT_3, font=(theme.ui_font(), 9), justify="center")
        else:
            avail_h = card_stream_y2 - card_stream_y1
            max_cards = max(1, avail_h // (card_h + card_gap))
            
            # Display reverse chronological (latest shots on top)
            rev_shots = list(reversed(filtered_shots))
            visible_shots = rev_shots[self.sidebar_scroll_offset : self.sidebar_scroll_offset + max_cards]

            for i, (real_idx, shot) in enumerate(visible_shots):
                cy1 = card_stream_y1 + i * (card_h + card_gap)
                cy2 = cy1 + card_h
                if cy2 > card_stream_y2:
                    break

                self.sidebar_shot_card_rects.append((10, cy1, sb_w - 10, cy2, real_idx))
                is_selected = (real_idx == self.selected_shot_index)

                # Selection is an accent edge on a lifted surface -- no
                # yellow box, and no zebra striping fighting it.
                card_bg = theme.SURFACE_2 if is_selected else theme.SURFACE
                self.canvas.create_rectangle(10, cy1, sb_w - 10, cy2, fill=card_bg, outline="")
                if is_selected:
                    self.canvas.create_rectangle(10, cy1, 13, cy2, fill=theme.ACCENT_LINE, outline="")

                # Aim-corrected so the list agrees with the shot table and the
                # HUD -- including shot_name, whose start-line word OGC derived
                # from the uncorrected angles.
                shot = self.aim_corrected(shot)
                ogc = shot.get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                carry = us.get("carry_distance_yards", 0.0)
                bspeed = us.get("ball_speed_mph", 0.0)
                s_name = self.resolve_handed(ogc.get("shot_name"), "Shot")
                c_tag = shot.get("club", "Club")
                t_stamp = shot.get("timestamp", "--:--")

                # Line 1: #N  [Club]  Carry
                # Line spacing is 14/32/49 rather than 12/30/45: a real UI face
                # renders taller than the Nimbus Sans fallback the app used to
                # get, and the tighter values had the three lines touching.
                num_txt = f"#{real_idx + 1}"
                self.canvas.create_text(20, cy1 + 14, text=num_txt, fill=theme.TEXT if is_selected else theme.TEXT_2, font=(theme.ui_font(), 10), anchor="w")
                self.canvas.create_text(58, cy1 + 15, text=c_tag, fill=theme.ACCENT_TEXT if is_selected else theme.TEXT_3, font=(theme.ui_font(), 8), anchor="w")
                self.canvas.create_text(sb_w - 20, cy1 + 14, text=f"{carry:.1f} yds", fill=theme.TEXT if is_selected else theme.TEXT_2, font=(theme.ui_font(), 11), anchor="e")

                # Line 2: Speed & Shot Name. Clip the shape name to the card
                # width -- "Straight Fade" plus the speed runs under the
                # right-aligned carry figure on the line above.
                sub2 = f"{bspeed:.1f} mph  ·  {s_name}"
                sub_font = (theme.ui_font(), 8)
                max_sub = sb_w - 40
                if self._text_width(sub2, sub_font) > max_sub:
                    while sub2 and self._text_width(sub2 + "…", sub_font) > max_sub:
                        sub2 = sub2[:-1]
                    sub2 += "…"
                self.canvas.create_text(20, cy1 + 35, text=sub2, fill=theme.TEXT_3, font=sub_font, anchor="w")

                # Line 3: Timestamp only -- smash is a constant when the OGC
                # model saturates, so repeating it on every card is noise.
                self.canvas.create_text(20, cy1 + 54, text=t_stamp, fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="w")

                # Delete ✕ -- bottom-right corner, clear of the top-right
                # carry text and the timestamp on the bottom-left.
                del_x1, del_y1, del_x2, del_y2 = sb_w - 30, cy2 - 20, sb_w - 10, cy2 - 2
                self.canvas.create_text((del_x1 + del_x2) // 2, (del_y1 + del_y2) // 2, text="✕", fill=theme.TEXT_3, font=(theme.ui_font(), 9))
                self.shot_delete_btn_rects.append((del_x1, del_y1, del_x2, del_y2, real_idx))

        # 5. Footer (y: h - 42 to h)
        clear_y1, clear_y2 = h - 38, h - 8
        self.sidebar_clear_btn_rect = (10, clear_y1, sb_w - 10, clear_y2)
        self.canvas.create_rectangle(10, clear_y1, sb_w - 10, clear_y2, fill=theme.SURFACE_2, outline="")
        self.canvas.create_text(sb_w // 2, (clear_y1 + clear_y2) // 2, text="Clear session", fill=theme.TEXT_3, font=(theme.ui_font(), 9))

        # Shift the whole sidebar group clear of the nav rail, then correct the
        # hit rects registered above by the same delta.
        dx = theme.RAIL_W
        for item in self.canvas.find_all()[self._sidebar_items_start:]:
            self.canvas.move(item, dx, 0)

        def _shift(rect):
            return None if not rect else (rect[0] + dx, rect[1],
                                          rect[2] + dx, rect[3])

        self.sidebar_clear_btn_rect = _shift(self.sidebar_clear_btn_rect)
        self.sidebar_toggle_rect = _shift(getattr(self, "sidebar_toggle_rect", None))
        self.sidebar_session_btn_rect = _shift(getattr(self, "sidebar_session_btn_rect", None))
        self.sidebar_filter_btn_rect = _shift(getattr(self, "sidebar_filter_btn_rect", None))
        self.sidebar_shot_card_rects = [
            (x1 + dx, y1, x2 + dx, y2, idx)
            for (x1, y1, x2, y2, idx) in self.sidebar_shot_card_rects
        ]
        self.shot_delete_btn_rects = [
            (x1 + dx, y1, x2 + dx, y2, idx)
            for (x1, y1, x2, y2, idx) in self.shot_delete_btn_rects
        ]

    def draw_session_dropdown(self, w, h):
        # Sidebar palette, not the old dark-theme greys. This panel sits on
        # the redesigned blue-teal drawer; theme.SURFACE (#16191E) read as a
        # grey slab against it.
        panel_bg = "#0B1D27"
        row_bg = "#0D1F29"
        row_sel = "#18313A"
        edge = "#24434C"
        gold = "#D4A24F"

        box_w = self.sidebar_width - 20
        x1, y1 = 10, 88
        item_h = 28
        empty_count = sum(1 for s in self.sessions if not s.get("shots"))
        # rows: sessions + Rename + New, plus "clear empty" when it applies
        extra = 3 if (empty_count > 1 or
                      (empty_count == 1 and
                       not self.sessions[self.active_session_index].get("shots")
                       and len(self.sessions) > 1)) else 2
        extra += 1  # Session notes row is always present
        total_items = len(self.sessions) + extra
        box_h = total_items * item_h + 10
        x2, y2 = x1 + box_w, y1 + box_h

        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 + 3, y2 + 3, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=panel_bg, outline=edge)

        self.session_menu_items.clear()
        for idx, sess in enumerate(self.sessions):
            iy1 = y1 + 5 + (idx * item_h)
            iy2 = iy1 + item_h - 2

            is_sel = (idx == self.active_session_index)
            bg = row_sel if is_sel else row_bg
            s_name = sess.get("name", f"Session {idx+1}")
            shot_cnt = len(sess.get("shots", []))

            self.canvas.create_rectangle(x1 + 4, iy1, x2 - 4, iy2, fill=bg, outline="")
            if is_sel:
                self.canvas.create_rectangle(x1 + 4, iy1, x1 + 7, iy2, fill=theme.ACCENT_LINE, outline="")

            # Delete control on the right of each row. The active session is
            # deletable too (the handler re-points the index), but the very
            # last remaining session is cleared rather than removed.
            del_x2 = x2 - 8
            del_x1 = del_x2 - 22
            self.canvas.create_text((del_x1 + del_x2) // 2, (iy1 + iy2) // 2,
                                    text="✕", fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 9), anchor="center")
            # Row click = switch; the ✕ zone is registered first so it wins.
            self.session_menu_items.append((del_x1, iy1, del_x2, iy2, -1000 - idx))
            self.session_menu_items.append((x1 + 4, iy1, del_x1 - 2, iy2, idx))

            # Shot count sits left of the ✕ so the two never collide.
            self.canvas.create_text(x1 + 14, (iy1 + iy2) // 2, text=s_name,
                                    fill=theme.TEXT if is_sel else theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="w")
            self.canvas.create_text(del_x1 - 8, (iy1 + iy2) // 2,
                                    text=f"{shot_cnt}",
                                    fill=theme.TEXT_3 if shot_cnt else "#5A7078",
                                    font=(theme.ui_font(), 9), anchor="e")

        row = len(self.sessions)

        # Optional: clear out empty sessions in one go.
        if extra == 3:
            ce_iy1 = y1 + 5 + (row * item_h)
            ce_iy2 = ce_iy1 + item_h - 2
            self.session_menu_items.append((x1 + 4, ce_iy1, x2 - 4, ce_iy2, -3))
            self.canvas.create_rectangle(x1 + 4, ce_iy1, x2 - 4, ce_iy2, fill=row_bg, outline="")
            self.canvas.create_text(x1 + 14, (ce_iy1 + ce_iy2) // 2,
                                    text="Clear empty sessions", fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 9), anchor="w")
            row += 1

        # Session Notes item
        notes_iy1 = y1 + 5 + (row * item_h)
        notes_iy2 = notes_iy1 + item_h - 2
        self.session_menu_items.append((x1 + 4, notes_iy1, x2 - 4, notes_iy2, -4))
        self.canvas.create_rectangle(x1 + 4, notes_iy1, x2 - 4, notes_iy2, fill=row_bg, outline="")
        self.canvas.create_text(x1 + 14, (notes_iy1 + notes_iy2) // 2, text="📝 Session notes", fill=theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")
        row += 1

        # Rename Active Session item
        ren_iy1 = y1 + 5 + (row * item_h)
        ren_iy2 = ren_iy1 + item_h - 2
        self.session_menu_items.append((x1 + 4, ren_iy1, x2 - 4, ren_iy2, -2))
        self.canvas.create_rectangle(x1 + 4, ren_iy1, x2 - 4, ren_iy2, fill=row_bg, outline="")
        self.canvas.create_text(x1 + 14, (ren_iy1 + ren_iy2) // 2, text="Rename session", fill=theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")
        row += 1

        # + Add New Session item
        add_iy1 = y1 + 5 + (row * item_h)
        add_iy2 = add_iy1 + item_h - 2
        self.session_menu_items.append((x1 + 4, add_iy1, x2 - 4, add_iy2, -1))
        self.canvas.create_rectangle(x1 + 4, add_iy1, x2 - 4, add_iy2,
                                     fill="#10252E", outline=gold, width=1)
        self.canvas.create_text(x1 + 14, (add_iy1 + add_iy2) // 2, text="＋  New session", fill="#E3BC70", font=(theme.ui_font(), 9, "bold"), anchor="w")

    def draw_filter_dropdown(self, w, h):
        box_w = 180
        x1, y1 = 10, 125
        options = ["ALL"] + self.clubs
        item_h = 22
        box_h = min(360, len(options) * item_h + 10)
        x2, y2 = x1 + box_w, y1 + box_h

        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 + 3, y2 + 3, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline=theme.HAIRLINE)

        self.filter_menu_items.clear()
        for idx, club_opt in enumerate(options[:15]):
            iy1 = y1 + 5 + (idx * item_h)
            iy2 = iy1 + item_h - 2
            self.filter_menu_items.append((x1 + 4, iy1, x2 - 4, iy2, club_opt))

            is_sel = (club_opt == self.club_filter)
            bg = theme.SURFACE_2 if is_sel else theme.SURFACE
            label = "All clubs" if club_opt == "ALL" else club_opt

            self.canvas.create_rectangle(x1 + 4, iy1, x2 - 4, iy2, fill=bg, outline="")
            if is_sel:
                self.canvas.create_rectangle(x1 + 4, iy1, x1 + 7, iy2, fill=theme.ACCENT_LINE, outline="")
            self.canvas.create_text(x1 + 14, (iy1 + iy2) // 2, text=label, fill=theme.TEXT if is_sel else theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")

    def draw_top_header(self, w, h, offset_x=0):
        header_h = 52
        avail_w = w - offset_x
        # Header Background & Bottom Border
        self.canvas.create_rectangle(offset_x, 0, w, header_h, fill=theme.BG, outline="")
        self.canvas.create_line(offset_x, header_h, w, header_h, fill=theme.HAIRLINE)

        # 1. Drawer Hamburger Toggle & Branding
        if self.sidebar_collapsed:
            hamb_x1, hamb_y1, hamb_x2, hamb_y2 = 10, 10, 42, 42
            self.sidebar_toggle_rect = (hamb_x1, hamb_y1, hamb_x2, hamb_y2)
            self.canvas.create_rectangle(hamb_x1, hamb_y1, hamb_x2, hamb_y2, fill=theme.SURFACE_2, outline="")
            self.canvas.create_text(26, 26, text="☰", fill=theme.TEXT_2, font=(theme.ui_font(), 12), anchor="center")
            brand_x = 52
            brand_text = "SHANKTUARY STUDIO"
        else:
            brand_x = offset_x + 12
            brand_text = "STUDIO" if avail_w < 1050 else "SHANKTUARY STUDIO"

        brand_id = self.canvas.create_text(brand_x, 26, text=brand_text, fill=theme.TEXT_2, font=(theme.ui_font(), 11), anchor="w")
        brand_bbox = self.canvas.bbox(brand_id)
        if brand_bbox and isinstance(brand_bbox, (tuple, list)) and len(brand_bbox) >= 4 and isinstance(brand_bbox[2], (int, float)):
            brand_right = int(brand_bbox[2])
        else:
            brand_right = brand_x + (50 if brand_text == "STUDIO" else 150)
        
        # Status Box — live shot-source link state. Which source is named
        # depends on what the user actually connected: a GSPro-only user
        # should never be told to look for a Nova they do not own.
        nova_up = nova_status["connected"]
        gspro_on = gspro_status.get("enabled", False)
        gspro_up = gspro_status.get("connected", False)

        if gspro_on and not gspro_settings.nova_enabled():
            source_up = gspro_up
            source_name = "GSPro"
        elif gspro_on:
            source_up = nova_up or gspro_up
            if nova_up and gspro_up:
                source_name = "Nova + GSPro"
            elif gspro_up:
                source_name = "GSPro"
            else:
                source_name = "Nova"
        else:
            source_up = nova_up
            source_name = "Nova"

        if source_up:
            status_text = source_name if (avail_w < 1050 and not self.sidebar_collapsed) else f"{source_name} Ready"
        else:
            status_text = "Ready"
        # A live dot plus plain text -- no bordered box.
        status_col = theme.ACCENT_LINE if source_up else theme.TEXT_3

        status_x1 = brand_right + 16
        self.canvas.create_oval(status_x1, 22, status_x1 + 8, 30, fill=status_col, outline="")
        self.canvas.create_text(status_x1 + 15, 26, text=status_text, fill=theme.TEXT_2, font=(theme.ui_font(), 9), anchor="w")

        # 2. Right Utility Pills
        fs_w = 32
        tools_w = 76
        dex_w = 46
        club_w = 98
        gap = 6

        fs_x2 = w - 10
        fs_x1 = fs_x2 - fs_w
        self.fullscreen_btn_rect = (fs_x1, 10, fs_x2, 42)
        self.canvas.create_rectangle(fs_x1, 10, fs_x2, 42, fill=theme.SURFACE, outline="")
        self.canvas.create_text((fs_x1 + fs_x2) // 2, 26, text="⛶", fill=theme.TEXT_3, font=(theme.ui_font(), 11), anchor="center")

        tools_x2 = fs_x1 - gap
        tools_x1 = tools_x2 - tools_w
        self.tools_btn_rect = (tools_x1, 10, tools_x2, 42)
        t_bg = theme.SURFACE_2 if self.show_tools_menu else theme.SURFACE
        self.canvas.create_rectangle(tools_x1, 10, tools_x2, 42, fill=t_bg, outline="")
        self.canvas.create_text((tools_x1 + tools_x2) // 2, 26, text="Tools  ▼", fill=theme.TEXT if self.show_tools_menu else theme.TEXT_2, font=(theme.ui_font(), 10), anchor="center")

        dex_x2 = tools_x1 - gap
        dex_x1 = dex_x2 - dex_w
        self.dexterity_btn_rect = (dex_x1, 10, dex_x2, 42)
        # Handedness is a state, not an alert -- accent it, do not flag it.
        dex_bg = theme.ACCENT_DEEP if self.is_left_handed else theme.SURFACE
        dex_fg = theme.ACCENT_TEXT if self.is_left_handed else theme.TEXT_2
        dex_label = "LH" if self.is_left_handed else "RH"
        self.canvas.create_rectangle(dex_x1, 10, dex_x2, 42, fill=dex_bg, outline="")
        self.canvas.create_text((dex_x1 + dex_x2) // 2, 26, text=dex_label, fill=dex_fg, font=(theme.ui_font(), 10), anchor="center")

        club_x2 = dex_x1 - gap
        club_x1 = club_x2 - club_w
        self.club_btn_rect = (club_x1, 10, club_x2, 42)
        c_bg = theme.SURFACE_2 if self.show_club_menu else theme.SURFACE
        self.canvas.create_rectangle(club_x1, 10, club_x2, 42, fill=c_bg, outline="")
        self.canvas.create_text((club_x1 + club_x2) // 2, 26, text=f"{self.current_club}  ▼", fill=theme.TEXT, font=(theme.ui_font(), 10), anchor="center")

        # 3. Mode switching now lives in the persistent left rail
        #    (draw_nav_rail). The old segmented pills were removed: eight
        #    46px pills could not hold readable labels, and abbreviations like
        #    "Nums"/"Fit"/"Lab" were a large part of the amateur feel.
        return


    def draw_nav_rail(self, h):
        """Persistent left icon rail -- replaces the 8 cramped mode pills.

        Registers hit rects in self.mode_pill_rects, so the existing click
        handlers keep working unchanged.
        """
        rw = theme.RAIL_W
        self.canvas.create_rectangle(0, 0, rw, h, fill=theme.RAIL, outline="")
        self.canvas.create_line(rw, 0, rw, h, fill=theme.HAIRLINE)

        # brand mark
        self.canvas.create_rectangle(18, 20, 46, 48, fill=theme.ACCENT, outline="")
        self.canvas.create_text(32, 34, text="S", fill="#DFF0E6",
                                font=(theme.ui_font(), 13, "bold"), anchor="center")

        y = 84
        for mode_id, label, _tip in theme.NAV_ITEMS:
            is_active = (self.view_mode == mode_id)
            # full-width hit target so clicks land on the icon OR the label
            self.mode_pill_rects[mode_id] = (0, y, rw, y + theme.NAV_ITEM_H - 10)

            if is_active:
                self.canvas.create_rectangle(8, y, rw - 8, y + 46,
                                             fill=theme.SURFACE_2, outline="")
                self.canvas.create_line(0, y + 8, 0, y + 38,
                                        fill=theme.ACCENT_LINE, width=3)
                icon_fill, txt_col = theme.ACCENT_LINE, theme.TEXT
            else:
                icon_fill, txt_col = "", theme.TEXT_3

            self.canvas.create_rectangle(
                25, y + 10, 39, y + 24,
                fill=icon_fill, outline="" if is_active else txt_col,
                width=0 if is_active else 2)
            self.canvas.create_text(32, y + 34, text=label, fill=txt_col,
                                    font=(theme.ui_font(), 7), anchor="center")
            y += theme.NAV_ITEM_H

        # Setup pinned to the bottom, away from view switching. It opens the
        # balance-hardware modal rather than switching view_mode, so it gets
        # its own hit rect instead of joining mode_pill_rects.
        setup_active = (self.view_mode == 10)
        s_col = theme.ACCENT_TEXT if setup_active else theme.TEXT_3
        if setup_active:
            self.canvas.create_rectangle(4, h - 72, theme.RAIL_W - 4, h - 24,
                                         fill=theme.ACCENT_DEEP, outline="")
        self.canvas.create_rectangle(25, h - 66, 39, h - 52, fill="",
                                     outline=s_col, width=2)
        self.canvas.create_text(32, h - 38, text="Setup", fill=s_col,
                                font=(theme.ui_font(), 7), anchor="center")
        self.nav_setup_rect = (4, h - 72, theme.RAIL_W - 4, h - 24)

    def verify_ogc_model_sync(self, shot):
        """Detect drift between our mirrored OGC constants and the live payload.

        OGC derives club speed as `ball_speed / smash_factor`, so that identity
        must hold exactly in any payload it produced. If it stops holding, or a
        clamped shot no longer reports one of our boundary smash values, then
        upstream changed its model and clamp detection has gone stale.

        Logs once per session rather than per shot. Returns True when in sync.
        """
        if getattr(self, "_ogc_sync_warned", False):
            return False
        try:
            # GSPro-sourced shots carry MEASURED club metrics from the launch
            # monitor (via SimRead), not OGC's derived model — the identity
            # below is specific to Nova payloads and must not be checked here.
            if shot.get("_source") == "gspro":
                return True
            ogc = shot.get("open_golf_coach", {}) if isinstance(shot, dict) else {}
            if not isinstance(ogc, dict):
                return True
            ball_mps = float(shot.get("ball_speed_meters_per_second") or 0.0)
            club_mps = float(ogc.get("club_speed_meters_per_second") or 0.0)
            smash = float(ogc.get("smash_factor") or 0.0)
            if ball_mps <= 0.0 or club_mps <= 0.0 or smash <= 0.0:
                return True

            # 1) The club_speed = ball_speed / smash identity.
            if abs(ball_mps / smash - club_mps) > 1e-6:
                self._ogc_sync_warned = True
                print(
                    "[OGC SYNC] club_speed != ball_speed/smash "
                    f"(ball={ball_mps:.4f} smash={smash:.6f} club={club_mps:.4f}). "
                    "Upstream clubhead model changed; smash clamp detection may be stale."
                )
                return False

            # 2) A shot we believe is clamped must report a boundary smash.
            conf = self.compute_smash_confidence(
                ball_mps,
                shot.get("vertical_launch_angle_degrees"),
                shot.get("total_spin_rpm"),
            )
            if conf["clamped"]:
                at_floor = abs(smash - OGC_SMASH_AT_COR_FLOOR) < 1e-9
                at_ceiling = abs(smash - OGC_SMASH_AT_COR_CEILING) < 1e-9
                if not (at_floor or at_ceiling):
                    self._ogc_sync_warned = True
                    print(
                        f"[OGC SYNC] predicted clamp but smash={smash:.9f} is not a "
                        f"boundary value ({OGC_SMASH_AT_COR_FLOOR:.9f} / "
                        f"{OGC_SMASH_AT_COR_CEILING:.9f}). Re-check OGC constants."
                    )
                    return False
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            return True
        return True

    def compute_smash_confidence(self, ball_speed_mps, vertical_launch_deg, total_spin_rpm):
        """Detect when OpenGolfCoach's clubhead-speed model has saturated.

        OGC does not measure clubhead speed -- the Nova has no club-tracking
        hardware. It infers an "effective COR" from ball speed, launch angle and
        spin, then clamps it to [MIN_EFFECTIVE_COR, DRIVER_COR_LIMIT] before
        converting to a smash factor (core/src/clubhead_data.rs).

        When that clamp engages, every shot in a wide range of inputs collapses
        onto the SAME boundary value, so the reported smash factor and club
        speed carry no information about the strike:

            floor   -> (1 + 0.52) / (1 + 0.04593/0.200) = 1.2361241...
            ceiling -> (1 + 0.83) / (1 + 0.04593/0.200) = 1.4882283...

        Slow swingers pin the floor; very fast swingers pin the ceiling. We
        re-run OGC's penalty math here to recover the UNCLAMPED value so the UI
        can grey out numbers that are boundary artifacts rather than estimates.

        Returns dict with:
            clamped  -- bool, the reported smash/club speed is a constant
            raw_cor  -- float, effective COR before clamping
            margin   -- float, distance from the nearest clamp boundary
        """
        result = {"clamped": False, "raw_cor": None, "margin": None}
        try:
            bs = float(ball_speed_mps or 0.0)
            if bs <= 0.0:
                return result
            launch = max(-5.0, min(70.0, float(vertical_launch_deg or 0.0)))
            spin = max(0.0, float(total_spin_rpm or 0.0))

            band = None
            for b in OGC_IMPACT_BANDS:
                if max(bs, 5.0) <= b["max_ball_speed_mps"]:
                    band = b
                    break
            if band is None:
                band = OGC_IMPACT_BANDS[-1]

            launch_dev = abs(launch - band["optimal_launch_deg"])
            norm_launch = min(launch_dev / band["launch_tolerance_deg"], 3.0)
            launch_penalty = (norm_launch ** 1.25) * 0.06

            spin_tol = max(band["spin_tolerance_rpm"], 1.0)
            if spin >= band["optimal_spin_rpm"]:
                norm_spin = min((spin - band["optimal_spin_rpm"]) / spin_tol, 3.0)
            else:
                norm_spin = min((band["optimal_spin_rpm"] - spin) / (spin_tol * 1.5), 3.0)
            spin_penalty = (norm_spin ** 1.15) * 0.08

            knuckle_penalty = 0.0
            if spin < 1200.0:
                knuckle_penalty = (((1200.0 - spin) / 1200.0) ** 1.3) * 0.05

            raw_cor = band["base_cor"] - launch_penalty - spin_penalty - knuckle_penalty
            result["raw_cor"] = raw_cor
            result["clamped"] = raw_cor < OGC_MIN_EFFECTIVE_COR or raw_cor > OGC_DRIVER_COR_LIMIT
            result["margin"] = min(
                raw_cor - OGC_MIN_EFFECTIVE_COR,
                OGC_DRIVER_COR_LIMIT - raw_cor,
            )
        except (TypeError, ValueError, ZeroDivisionError):
            return {"clamped": False, "raw_cor": None, "margin": None}
        return result

    def draw_top_metric_toolbar(self, avail_w, ball_speed, club_speed, smash, carry, total, offline, hang_time, eff_pct, offset_x=0, smash_clamped=False):
        t_scale = max(0.9, min(2.0, avail_w / 1200.0))
        top_y = 52
        bar_h = int(56 * t_scale)
        bot_y = top_y + bar_h
        # Borderless strip: the design language groups with whitespace and a
        # single hairline, not boxes and per-column dividers.
        self.canvas.create_rectangle(offset_x, top_y, offset_x + avail_w, bot_y, fill=theme.BG, outline="")
        self.canvas.create_line(offset_x, bot_y, offset_x + avail_w, bot_y, fill=theme.HAIRLINE)

        off_abs = abs(offline)
        off_dir = "L" if offline < 0 else "R"
        off_str = f"{off_abs:.1f} {off_dir} YDS" if off_abs > 0.1 else "0.0 STRAIGHT"

        # Club speed and smash factor are DERIVED from ball data by OGC, never
        # measured. When the COR clamp saturates they collapse to a constant, so
        # grey them out rather than presenting a boundary artifact as a reading.
        derived_col = theme.MUTED if smash_clamped else theme.TEXT
        smash_col = theme.MUTED if smash_clamped else theme.TEXT
        club_speed_val = "-- MPH" if smash_clamped else f"{club_speed:.1f} MPH"
        smash_val = "--" if smash_clamped else f"{smash:.2f}"

        # One accent (carry -- the number people look at first), neutrals for
        # everything else, and semantic colour ONLY where it means something:
        # offline warns/alerts by magnitude, derived values stay muted.
        metrics = [
            ("BALL SPEED", f"{ball_speed:.1f} MPH", theme.TEXT),
            ("CLUB SPEED", club_speed_val, derived_col),
            ("SMASH FACTOR", smash_val, smash_col),
            ("CARRY", f"{carry:.1f} YDS", theme.ACCENT_TEXT),
            ("TOTAL", f"{total:.1f} YDS", theme.TEXT),
            ("OFFLINE", off_str, theme.TEXT if off_abs <= 4.0 else (theme.WARN if off_abs <= 12.0 else theme.DANGER)),
            ("HANG TIME", f"{hang_time:.1f} SEC", theme.TEXT_2),
            ("EFFICIENCY", f"{eff_pct:.0f}%", theme.TEXT_2)
        ]

        lbl_font = (theme.ui_font(), max(8, int(9 * t_scale)), "bold")
        val_font = (theme.ui_font(), max(11, int(15 * t_scale)), "bold")

        col_w = avail_w / len(metrics)
        # Left-aligned label above value, so the eye tracks a column.
        pad = int(18 * t_scale)
        for i, (label, val, val_col) in enumerate(metrics):
            lx = int(offset_x + i * col_w) + pad
            # 13 / 40 rather than 15 / 38: a real UI face is taller than the
            # old fallback and the label's descenders touched the value's caps.
            self.canvas.create_text(lx, top_y + int(13 * t_scale), text=label,
                                    fill=theme.TEXT_3, font=lbl_font, anchor="w")
            self.canvas.create_text(lx, top_y + int(40 * t_scale), text=val,
                                    fill=val_col, font=val_font, anchor="w")

    def draw_club_dropdown(self, w, h):
        # Same blue-teal palette as the session dropdown -- both are
        # drawer-attached menus, not standalone panels, and the old grey
        # theme.SURFACE colors read as a mismatched leftover next to them.
        panel_bg = "#0B1D27"
        row_bg = "#0D1F29"
        row_sel = "#18313A"
        edge = "#24434C"

        box_w = 180
        x1 = self.club_btn_rect[0] if self.club_btn_rect else w - 245
        x2 = x1 + box_w
        y1 = 48
        item_h = 24
        custom_btn_h = 28
        total_items = len(self.clubs)
        box_h = total_items * item_h + custom_btn_h + 16
        y2 = y1 + box_h

        self.canvas.create_rectangle(x1 + 4, y1 + 4, x2 + 4, y2 + 4, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=panel_bg, outline=edge)
        self.canvas.create_text(x1 + 14, y1 + 12, text="ACTIVE CLUB", fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="w")

        self.club_menu_items.clear()
        for idx, club_name in enumerate(self.clubs):
            iy1 = y1 + 22 + (idx * item_h)
            iy2 = iy1 + item_h - 2
            self.club_menu_items.append((x1 + 6, iy1, x2 - 6, iy2, club_name))

            is_sel = (club_name == self.current_club)
            bg = row_sel if is_sel else row_bg
            txt_col = theme.TEXT if is_sel else theme.TEXT_2

            self.canvas.create_rectangle(x1 + 6, iy1, x2 - 6, iy2, fill=bg, outline="")
            if is_sel:
                self.canvas.create_rectangle(x1 + 6, iy1, x1 + 9, iy2, fill=theme.ACCENT_LINE, outline="")
            self.canvas.create_text(x1 + 16, (iy1 + iy2) // 2, text=club_name, fill=txt_col, font=(theme.ui_font(), 9), anchor="w")

        # Divider & Add Custom Club Action
        div_y = y1 + 22 + (total_items * item_h) + 2
        self.canvas.create_line(x1 + 6, div_y, x2 - 6, div_y, fill=edge, width=1)

        btn_y1 = div_y + 4
        btn_y2 = btn_y1 + 22
        self.club_menu_items.append((x1 + 6, btn_y1, x2 - 6, btn_y2, "__add_custom__"))
        self.canvas.create_rectangle(x1 + 6, btn_y1, x2 - 6, btn_y2, fill=row_sel, outline="")
        self.canvas.create_text((x1 + x2) // 2, (btn_y1 + btn_y2) // 2, text="＋  Add custom club", fill=theme.TEXT_2, font=(theme.ui_font(), 9), anchor="center")

    def draw_tools_flyout_menu(self, w, h):
        """Tools flyout. Every row states what it does -- navigation says
        where it opens, copy actions show the literal URL -- so open-vs-copy
        is scannable rather than read word by word."""
        # Same blue-teal palette as the session/club dropdowns -- all three
        # are drawer-attached menus and should read as one family, not a
        # mix of the current theme and the old grey theme.SURFACE.
        panel_bg = "#0B1D27"
        row_sel = "#18313A"
        edge = "#24434C"

        box_w = 372
        x2 = self.tools_btn_rect[2] if self.tools_btn_rect else w - 16
        x1 = x2 - box_w
        y1 = 48

        port = obs_server.OBS_PORT
        sections = [
            ("BROADCAST & OVERLAYS", [
                ("open_config", "OBS Overlay Config", "opens /config in your browser", True),
                ("copy_obs_url", "Copy OBS Overlay URL", f"http://localhost:{port}", False),
                ("open_range", "Open 3D Range", "opens /range in your browser", False),
            ]),
            ("FLOOR PROJECTION", [
                ("copy_divot_url", "Copy Virtual Divot URL", f"http://localhost:{port}/divot", False),
                ("open_divot", "Open Virtual Divot", "opens /divot in your browser", False),
                ("copy_tiles_url", "Copy Metric Tiles URL", f"http://localhost:{port}/tiles", False),
                ("open_tiles", "Open Metric Tiles", "opens /tiles in your browser", False),
                ("set_mode_2", "Switch to Divot Mode", "fullscreen floor projector", False),
            ]),
        ]

        item_h, sec_h, div_h = 46, 22, 20
        pad_bottom = 16

        # The panel is drawn FIRST so it stacks directly behind this menu's
        # own content and above the app screen beneath it. Its height is not
        # known yet, so it is created at a placeholder size and resized with
        # canvas.coords() once the layout walk below has run.
        #
        # Do not "draw it last and tag_lower" instead: tag_lower moves an item
        # to the bottom of the WHOLE canvas display list, which puts the panel
        # behind the app background and the menu renders transparent.
        shadow = self.canvas.create_rectangle(x1 + 4, y1 + 4, x2 + 4, y1 + 4,
                                              fill="#08090C", outline="")
        panel = self.canvas.create_rectangle(x1, y1, x2, y1,
                                             fill=panel_bg, outline=edge)

        self.tools_menu_items.clear()
        curr_y = y1 + 16

        for s_idx, (title, items) in enumerate(sections):
            if s_idx > 0:
                self.canvas.create_line(x1 + 20, curr_y, x2 - 20, curr_y, fill=edge)
                curr_y += div_h
            self.canvas.create_text(x1 + 20, curr_y, text=title, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="w")
            curr_y += sec_h

            for action, label, sub, primary in items:
                r = (x1 + 12, curr_y, x2 - 12, curr_y + item_h - 4)
                self.tools_menu_items.append((r[0], r[1], r[2], r[3], action))
                if primary:
                    self.canvas.create_rectangle(r[0], r[1], r[2], r[3],
                                                 fill=row_sel, outline="")
                self.canvas.create_text(x1 + 26, r[1] + 13, text=label,
                                        fill=theme.TEXT if primary else theme.TEXT_2,
                                        font=(theme.ui_font(), 10), anchor="w")
                self.canvas.create_text(x1 + 26, r[1] + 30, text=sub,
                                        fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="w")
                curr_y += item_h

        # Hardware status -- Nova and the balance boards answer the same
        # question ("is my hardware talking to me"), so they sit together.
        curr_y += 4
        self.canvas.create_line(x1 + 20, curr_y, x2 - 20, curr_y, fill=edge)
        curr_y += 18
        self.canvas.create_text(x1 + 20, curr_y, text="HARDWARE", fill=theme.TEXT_3,
                                font=(theme.ui_font(), 8), anchor="w")
        curr_y += 20

        nova_up = nova_status["connected"]
        pm = getattr(obs_server, "pressure_manager", None)
        try:
            b_open = bool(pm and pm.backend and pm.backend.is_open)
            b_dual = bool(pm and getattr(pm, "board_mode", "single") == "dual")
        except Exception:
            b_open, b_dual = False, False

        rows = [
            ("Nova", nova_status["host"] if nova_up else "searching...", nova_up),
        ]

        # GSPro appears only when the user has actually chosen it as a shot
        # source — a Nova-only user should not see a permanently dead row.
        if gspro_status.get("enabled"):
            gspro_up = gspro_status.get("connected", False)
            if gspro_up:
                shots = gspro_status.get("shots", 0)
                gspro_value = f"polling · {shots} shot{'' if shots == 1 else 's'}"
            elif not gspro_status.get("db_found"):
                gspro_value = "database not found"
            else:
                gspro_value = "connecting..."
            rows.append(("GSPro", gspro_value, gspro_up))

        rows.append(
            ("Balance boards",
             ("2 paired · dual plate" if b_dual else "1 paired") if b_open else "not connected",
             b_open)
        )
        for label, value, ok in rows:
            self.canvas.create_oval(x1 + 22, curr_y + 5, x1 + 30, curr_y + 13,
                                    fill=theme.ACCENT_LINE if ok else theme.TEXT_3, outline="")
            self.canvas.create_text(x1 + 40, curr_y + 9, text=label, fill=theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="w")
            self.canvas.create_text(x2 - 20, curr_y + 9, text=str(value), fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="e")
            curr_y += 24

        curr_y += 6
        # Two side-by-side actions: hardware setup and the shot-source picker.
        half = (x2 - x1 - 24 - 8) // 2
        sb = (x1 + 12, curr_y, x1 + 12 + half, curr_y + 38)
        self.tools_menu_items.append((sb[0], sb[1], sb[2], sb[3], "open_setup"))
        self.canvas.create_rectangle(sb[0], sb[1], sb[2], sb[3], fill=row_sel, outline="")
        self.canvas.create_text((sb[0] + sb[2]) // 2, (sb[1] + sb[3]) // 2, text="Open Setup",
                                fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 10), anchor="center")

        ss = (sb[2] + 8, curr_y, x2 - 12, curr_y + 38)
        self.tools_menu_items.append((ss[0], ss[1], ss[2], ss[3], "open_shot_source"))
        self.canvas.create_rectangle(ss[0], ss[1], ss[2], ss[3], fill=row_sel, outline="")
        self.canvas.create_text((ss[0] + ss[2]) // 2, (ss[1] + ss[3]) // 2, text="Shot Source",
                                fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 10), anchor="center")

        # Panel wraps whatever the walk above produced, with real padding
        # below the last element. Resized in place -- stacking already correct.
        y2 = sb[3] + pad_bottom
        self.canvas.coords(panel, x1, y1, x2, y2)
        self.canvas.coords(shadow, x1 + 4, y1 + 4, x2 + 4, y2 + 4)


    def draw_screen(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 10 or h <= 10:
            w, h = 1150, 780

        self.land_dot_coords.clear()
        self.mode_pill_rects.clear()

        # Extract Current Shot Metrics
        if self.current_shot:
            # Read through the aim correction so the HUD, the 3D range and the
            # shot table all agree with the analytics.
            shot_view = self.aim_corrected(self.current_shot)
            ogc = shot_view.get("open_golf_coach", {})
            us_units = ogc.get("us_customary_units", {})

            hand_key = "left_handed" if self.is_left_handed else "right_handed"
            path_data = ogc.get("club_path_degrees", {})
            if isinstance(path_data, dict):
                club_path = path_data.get(hand_key, path_data.get("right_handed", 0.0))
            else:
                club_path = float(path_data or 0.0)
                if self.is_left_handed: club_path = -club_path

            f2p_data = ogc.get("club_face_to_path_degrees", {})
            if isinstance(f2p_data, dict):
                face_to_path = f2p_data.get(hand_key, f2p_data.get("right_handed", 0.0))
            else:
                face_to_path = float(f2p_data or 0.0)
                if self.is_left_handed: face_to_path = -face_to_path

            f2t_data = ogc.get("club_face_to_target_degrees", {})
            if isinstance(f2t_data, dict):
                face_to_target = f2t_data.get(hand_key, f2t_data.get("right_handed", 0.0))
            else:
                face_to_target = float(f2t_data or 0.0)
                if self.is_left_handed: face_to_target = -face_to_target
            vert_launch = shot_view.get("vertical_launch_angle_degrees", 0.0)
            horiz_launch = shot_view.get("horizontal_launch_angle_degrees", 0.0)
            sidespin = ogc.get("sidespin_rpm", 0.0)
            backspin = ogc.get("backspin_rpm", 0.0)
            spin_axis = ogc.get("spin_axis_degrees", 0.0)
            total_spin = ogc.get("total_spin_rpm", 0.0)
            smash = ogc.get("smash_factor", 1.23)
            hang_time = ogc.get("hang_time_seconds", 0.0)
            descent_angle = ogc.get("descent_angle_degrees", 0.0)
            eff_pct = ogc.get("distance_efficiency_percent", 0.0)

            ball_speed_mph = us_units.get("ball_speed_mph", 0.0)
            club_speed_mph = us_units.get("club_speed_mph", 0.0)
            carry_yds = us_units.get("carry_distance_yards", 0.0)
            total_yds = us_units.get("total_distance_yards", 0.0)
            offline_yds = us_units.get("offline_distance_yards", 0.0)
            peak_height_yds = us_units.get("peak_height_yards", 0.0)

            shot_name_val = ogc.get("shot_name", "Straight")
            shot_name = shot_name_val.get(hand_key, shot_name_val.get("right_handed", "Straight")) if isinstance(shot_name_val, dict) else str(shot_name_val or "Straight")

            shot_rank_val = ogc.get("shot_rank", "A")
            shot_rank = shot_rank_val.get(hand_key, shot_rank_val.get("right_handed", "A")) if isinstance(shot_rank_val, dict) else str(shot_rank_val or "A")

            opt_val = us_units.get("optimal_maximum_distance_yards") or ogc.get("distance_potential_yards", 0.0)
            optimal_max_yds = opt_val.get(hand_key, opt_val.get("right_handed", 0.0)) if isinstance(opt_val, dict) else float(opt_val or 0.0)

            cr_val = ogc.get("face_closure_rate_dps") or self.current_shot.get("face_closure_rate_dps") or ogc.get("closure_rate_dps") or 0.0
            closure_rate = cr_val.get(hand_key, cr_val.get("right_handed", 0.0)) if isinstance(cr_val, dict) else float(cr_val or 0.0)

            aoa_val = ogc.get("angle_of_attack_degrees") or self.current_shot.get("angle_of_attack_degrees") or 0.0
            attack_angle = aoa_val.get(hand_key, aoa_val.get("right_handed", 0.0)) if isinstance(aoa_val, dict) else float(aoa_val or 0.0)

            dl_val = ogc.get("dynamic_loft_degrees") or self.current_shot.get("dynamic_loft_degrees") or 0.0
            dynamic_loft = dl_val.get(hand_key, dl_val.get("right_handed", 0.0)) if isinstance(dl_val, dict) else float(dl_val or 0.0)
        else:
            club_path = 0.0
            face_to_path = 0.0
            face_to_target = 0.0
            vert_launch = 0.0
            horiz_launch = 0.0
            sidespin = 0.0
            backspin = 0.0
            spin_axis = 0.0
            total_spin = 0.0
            smash = 0.0
            hang_time = 0.0
            descent_angle = 0.0
            eff_pct = 0.0
            ball_speed_mph = 0.0
            club_speed_mph = 0.0
            carry_yds = 0.0
            total_yds = 0.0
            offline_yds = 0.0
            peak_height_yds = 0.0
            shot_name = "Ready"
            shot_rank = "A"
            optimal_max_yds = 0.0
            closure_rate = 0.0
            attack_angle = 0.0
            dynamic_loft = 0.0

        offset_x = theme.RAIL_W if self.sidebar_collapsed else self.sidebar_width
        avail_w = w - offset_x
        top_bar_h = 52 + int(56 * max(0.9, min(2.0, avail_w / 1200.0))) + 8

        # Is OGC's clubhead-speed model saturated for this shot? If so its
        # smash factor / club speed are constants, not estimates.
        smash_clamped = False
        if self.current_shot:
            _s = self.current_shot
            smash_clamped = self.compute_smash_confidence(
                _s.get("ball_speed_meters_per_second"),
                _s.get("vertical_launch_angle_degrees"),
                _s.get("total_spin_rpm"),
            )["clamped"]

        # 1. Left Shot Library Sidebar
        self.draw_left_sidebar(w, h)
        self.draw_nav_rail(h)

        # 2. Top Navigation Bar
        self.draw_top_header(w, h, offset_x=offset_x)

        # 3. Workspace View Routing
        if self.view_mode == 1:
            # Mode 1: Delivery (4-Quadrant Studio)
            self.draw_top_metric_toolbar(avail_w, ball_speed_mph, club_speed_mph, smash, carry_yds, total_yds, offline_yds, hang_time, eff_pct, offset_x=offset_x, smash_clamped=smash_clamped)
            if self.current_shot:
                self.draw_4_quadrant_studio(avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, peak_height_yds, descent_angle, optimal_max_yds, eff_pct, shot_name, shot_rank, smash, ball_speed=ball_speed_mph, offset_x=offset_x, top_bar_h=top_bar_h)
            else:
                self.canvas.create_text(offset_x + avail_w // 2, (h + top_bar_h) // 2, text="READY FOR SHOT", fill="#282C38", font=(theme.ui_font(), 32, "bold"))
        elif self.view_mode == 2:
            # Mode 2: 3D Range Viewport
            self.draw_3d_range_viewport(avail_w, h, carry_yds, total_yds, ball_speed_mph, club_speed_mph, peak_height_yds, offline_yds, total_spin, vert_launch, horiz_launch, offset_x=offset_x)
        elif self.view_mode == 3:
            # Mode 3: Dispersion & Club Gapping Viewport
            self.draw_dispersion_and_gapping(avail_w, h, offset_x=offset_x)
        elif self.view_mode == 4:
            # Mode 4: Sortable Shot Table Matrix
            self.draw_shot_table_viewport(avail_w, h, offset_x=offset_x)
        elif self.view_mode == 5:
            # Mode 5: High-Contrast Big Numbers Sim Grid
            self.draw_big_numbers_viewport(avail_w, h, carry_yds, total_yds, ball_speed_mph, club_speed_mph, smash, vert_launch, total_spin, spin_axis, club_path, face_to_path, peak_height_yds, offline_yds, closure_rate, attack_angle, dynamic_loft, hang_time, offset_x=offset_x)
        elif self.view_mode == 6:
            # Mode 6: My Bag Mapping & Gapping Matrix
            self.draw_my_bag_viewport(avail_w, h, offset_x=offset_x)
        elif self.view_mode == 8:
            # Mode 8: Swing Lab Biomechanics Suite
            self.draw_swing_lab_viewport(avail_w, h, offset_x=offset_x)
        elif self.view_mode == 7:
            # Mode 7: Club Fitting & Head-to-Head Comparison
            self.draw_fitting_viewport(avail_w, h, offset_x=offset_x)
        elif self.view_mode == 10:
            # Mode 10: Setup -- devices & hardware.
            self.draw_setup_viewport(avail_w, h, offset_x=offset_x)

        elif self.view_mode == 9:
            # Mode 9: Overview -- the landing view.
            # No shared metric toolbar here: Overview draws its own primary
            # metric row, and rendering both showed the same numbers twice
            # while eating the vertical space the bottom band needs.
            if self.current_shot:
                self.draw_overview_viewport(
                    avail_w, h, carry_yds, total_yds, ball_speed_mph,
                    club_speed_mph, smash, vert_launch, total_spin,
                    peak_height_yds, offline_yds, descent_angle, hang_time,
                    club_path, face_to_path, spin_axis, face_to_target,
                    shot_name, smash_clamped=smash_clamped, offset_x=offset_x,
                    top_bar_h=52)
            else:
                self.canvas.create_text(offset_x + avail_w // 2, (h + top_bar_h) // 2, text="READY FOR SHOT", fill="#1D2621", font=(theme.ui_font(), 26))
        elif self.view_mode == 0:
            # Mode 0: Floor Divot Focus Projector
            self.draw_divot_focus(avail_w, h, club_path, face_to_path, ball_speed_mph, club_speed_mph, carry_yds, shot_name, offset_x=offset_x)
        else:
            self.draw_top_metric_toolbar(avail_w, ball_speed_mph, club_speed_mph, smash, carry_yds, total_yds, offline_yds, hang_time, eff_pct, offset_x=offset_x, smash_clamped=smash_clamped)
            if self.current_shot:
                self.draw_4_quadrant_studio(avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, peak_height_yds, descent_angle, optimal_max_yds, eff_pct, shot_name, shot_rank, smash, ball_speed=ball_speed_mph, offset_x=offset_x, top_bar_h=top_bar_h)

        # 4. Floating Overlay Menus (Top Layer)
        if self.show_session_dropdown:
            self.draw_session_dropdown(w, h)
        elif self.show_filter_dropdown:
            self.draw_filter_dropdown(w, h)
        elif self.show_club_menu:
            self.draw_club_dropdown(w, h)
        elif self.show_tools_menu:
            self.draw_tools_flyout_menu(w, h)

        # 5. In-Canvas Modal Dialog (Top-most Modal Layer)
        if self.show_balance_hardware_modal:
            self.draw_balance_hardware_modal(w, h)
        if self.show_spec_editor_modal:
            self.draw_club_spec_editor_modal(w, h)
        elif self.show_custom_club_modal:
            self.draw_custom_club_modal(w, h)
        elif self.show_aim_modal:
            self.draw_aim_measure_modal(w, h)

        # 6. Toast Notification (Always on Top)
        if self.copy_feedback:
            msg = self.copy_feedback if self.copy_feedback.startswith("✓") or self.copy_feedback.startswith("🦶") else f"✓ {self.copy_feedback}"
            toast_w = max(260, len(msg) * 8 + 36)
            tx1 = (w - toast_w) // 2
            tx2 = tx1 + toast_w
            ty1 = h - 60
            ty2 = ty1 + 38
            self.canvas.create_rectangle(tx1, ty1, tx2, ty2, fill=theme.ACCENT_DEEP, outline="")
            self.canvas.create_text((tx1 + tx2) // 2, (ty1 + ty2) // 2, text=msg, fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 9), anchor="center")

    def draw_3d_range_viewport(self, avail_w, h, carry_yds, total_yds, ball_speed, club_speed, apex_yds, offline_yds, total_spin, vert_launch, horiz_launch, offset_x=0):
        self.range_launch_web_rect = None
        top_y = 52
        horizon_y = top_y + int((h - top_y) * 0.28)
        ground_y = h - 25

        # 1. Sky Gradient Background
        self.canvas.create_rectangle(offset_x, top_y, offset_x + avail_w, horizon_y, fill=theme.BG, outline="")
        self.canvas.create_rectangle(offset_x, horizon_y - 2, offset_x + avail_w, horizon_y + 2, fill=theme.HAIRLINE, outline="")

        # Distant Mountain Silhouettes
        mtn_pts = [
            offset_x, horizon_y,
            offset_x + int(avail_w * 0.15), horizon_y - 28,
            offset_x + int(avail_w * 0.30), horizon_y - 12,
            offset_x + int(avail_w * 0.50), horizon_y - 35,
            offset_x + int(avail_w * 0.70), horizon_y - 18,
            offset_x + int(avail_w * 0.88), horizon_y - 30,
            offset_x + avail_w, horizon_y
        ]
        self.canvas.create_polygon(mtn_pts, fill=theme.RAIL, outline=theme.HAIRLINE)

        # 2. Ground & Perspective Fairway
        self.canvas.create_rectangle(offset_x, horizon_y, offset_x + avail_w, h, fill="#0B120E", outline="")

        fx1 = offset_x + int(avail_w * 0.32)
        fx2 = offset_x + int(avail_w * 0.68)
        bx1 = offset_x + 30
        bx2 = offset_x + avail_w - 30

        fairway_poly = [fx1, horizon_y, fx2, horizon_y, bx2, ground_y, bx1, ground_y]
        self.canvas.create_polygon(fairway_poly, fill="#101A14", outline=theme.ACCENT_DEEP, width=2)

        # Center target line
        cx_top = (fx1 + fx2) // 2
        cx_bot = (bx1 + bx2) // 2
        self.canvas.create_line(cx_bot, ground_y, cx_top, horizon_y, fill=theme.GUIDE, width=1, dash=(6, 5))

        # Yardage Arcs & Pins
        yardages = [50, 100, 150, 200, 250, 300, 350]
        # Distance pins: one cool-to-warm ramp, same idea as get_club_color.
        pin_colors = {100: "#7FB3C8", 150: "#96CE99", 200: "#C9D78D", 250: "#E0C689", 300: "#E59187"}
        
        for yds in yardages:
            frac = yds / 380.0
            arc_y = ground_y - int((ground_y - horizon_y) * (frac ** 0.74))
            w_at_y = (bx2 - bx1) + ((fx2 - fx1) - (bx2 - bx1)) * ((ground_y - arc_y) / (ground_y - horizon_y))
            ax1 = cx_bot - int(w_at_y * 0.46)
            ax2 = cx_bot + int(w_at_y * 0.46)
            
            # Arc curve
            self.canvas.create_line(ax1, arc_y, ax2, arc_y, fill="#1B2620", width=1, dash=(3, 4))
            
            # Distance Signboard
            self.canvas.create_rectangle(cx_bot - 18, arc_y - 8, cx_bot + 18, arc_y + 8, fill=theme.SURFACE, outline=theme.ACCENT_LINE if yds == 150 else theme.HAIRLINE)
            self.canvas.create_text(cx_bot, arc_y, text=str(yds), fill=theme.ACCENT_TEXT if yds == 150 else theme.TEXT_3, font=(theme.ui_font(), 8, "bold"))

            # Pin Flag
            if yds in pin_colors:
                p_col = pin_colors[yds]
                pin_x = cx_bot + (35 if yds % 2 == 0 else -35)
                pin_y = arc_y
                self.canvas.create_line(pin_x, pin_y, pin_x, pin_y - 18, fill=theme.TEXT, width=2)
                self.canvas.create_polygon(pin_x, pin_y - 18, pin_x + 10, pin_y - 13, pin_x, pin_y - 8, fill=p_col, outline="")

        # 3. Multi-Shot Tracer History & Active Shot
        for s in self.session_shots[:-1]:
            if s.get("excluded", False):
                continue
            s_ogc = self.aim_corrected(s).get("open_golf_coach", {})
            s_us = s_ogc.get("us_customary_units", {})
            s_c = s_us.get("carry_distance_yards", 0.0)
            s_off = s_us.get("offline_distance_yards", 0.0)
            s_ap = s_us.get("peak_height_yards", 25.0)
            if s_c > 0:
                past_pts = []
                for step in range(0, 101, 5):
                    tf = step / 100.0
                    cdist = s_c * tf
                    coff = s_off * tf
                    calt = math.sin(tf * math.pi) * s_ap
                    gfrac = min(1.0, cdist / 380.0)
                    gy = ground_y - int((ground_y - horizon_y) * (gfrac ** 0.74))
                    gw = (bx2 - bx1) + ((fx2 - fx1) - (bx2 - bx1)) * ((ground_y - gy) / (ground_y - horizon_y))
                    gx = cx_bot + int((coff / 50.0) * (gw * 0.45))
                    ty = gy - int(calt * 3.6 * (1.0 - 0.45 * gfrac))
                    past_pts.extend([gx, ty])
                if len(past_pts) >= 4:
                    self.canvas.create_line(past_pts, fill="#232A26", width=1, smooth=True)

        # Draw Active Shot Tracer & Curtain
        if carry_yds > 0:
            traj_pts = []
            ground_pts = []
            max_alt = -1

            for step in range(0, 101, 3):
                tf = step / 100.0
                cdist = carry_yds * tf
                coff = (horiz_launch * 0.6 * (1.0 - tf)) + (offline_yds * tf)
                calt = math.sin(tf * math.pi) * apex_yds
                
                gfrac = min(1.0, cdist / 380.0)
                gy = ground_y - int((ground_y - horizon_y) * (gfrac ** 0.74))
                gw = (bx2 - bx1) + ((fx2 - fx1) - (bx2 - bx1)) * ((ground_y - gy) / (ground_y - horizon_y))
                gx = cx_bot + int((coff / 50.0) * (gw * 0.45))
                
                alt_px = int(calt * 3.8 * (1.0 - 0.45 * gfrac))
                ty = gy - alt_px
                traj_pts.append((gx, ty))
                ground_pts.append((gx, gy))

                if alt_px > max_alt:
                    max_alt = alt_px

            # Shadow Curtain dropped to ground
            curtain_poly = []
            for p in traj_pts:
                curtain_poly.extend([p[0], p[1]])
            for p in reversed(ground_pts):
                curtain_poly.extend([p[0], p[1]])
            if len(curtain_poly) >= 6:
                self.canvas.create_polygon(curtain_poly, fill=theme.ACCENT, outline="", stipple="gray25")

            # Ground landing path
            flat_pts = []
            for p in ground_pts:
                flat_pts.extend([p[0], p[1]])
            self.canvas.create_line(flat_pts, fill=theme.ACCENT_DEEP, width=2, dash=(4, 3))

            # Neon flight tracer line
            flight_pts = []
            for p in traj_pts:
                flight_pts.extend([p[0], p[1]])
            self.canvas.create_line(flight_pts, fill=theme.ACCENT_LINE, width=3, smooth=True)

            # Landing impact circle
            lx, ly = ground_pts[-1]
            self.canvas.create_oval(lx - 12, ly - 6, lx + 12, ly + 6, fill="", outline=theme.ACCENT_LINE, width=2)
            self.canvas.create_oval(lx - 4, ly - 2, lx + 4, ly + 2, fill=theme.ACCENT, outline="")
            
            # Carry Flag Tag
            self.canvas.create_rectangle(lx - 34, ly - 28, lx + 34, ly - 10, fill=theme.SURFACE, outline=theme.ACCENT_LINE, width=1)
            self.canvas.create_text(lx, ly - 19, text=f"{carry_yds:.1f} YDS", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"))

            # Floating Apex Badge
            # Apex is already in the top metric strip; labelling it on the
            # arc as well is redundant and crowds the flight path.
        else:
            self.canvas.create_text(cx_bot, horizon_y + 80, text="READY FOR SHOT", fill="#1D2621", font=(theme.ui_font(), 22))

        # 4. Top Floating HUD Tiles
        hud_h = 48
        hud_y1 = top_y + 10
        hud_y2 = hud_y1 + hud_h
        
        off_dir = "L" if offline_yds < 0 else "R"
        off_str = f"{abs(offline_yds):.1f} {off_dir} YDS" if abs(offline_yds) > 0.1 else "0.0 STRAIGHT"

        # Club speed is derived from ball data by OpenGolfCoach and collapses
        # to a constant when its model saturates -- mute it rather than
        # present a constant as a measurement.
        _sc = self.compute_smash_confidence(
            (self.current_shot or {}).get("ball_speed_meters_per_second"),
            (self.current_shot or {}).get("vertical_launch_angle_degrees"),
            (self.current_shot or {}).get("total_spin_rpm"),
        )["clamped"] if self.current_shot else False
        cs_val = "-- MPH" if _sc else f"{club_speed:.1f} MPH"

        hud_cards = [
            ("CARRY", f"{carry_yds:.1f} YDS", theme.ACCENT_TEXT),
            ("TOTAL", f"{total_yds:.1f} YDS", theme.TEXT),
            ("BALL SPEED", f"{ball_speed:.1f} MPH", theme.TEXT),
            ("CLUB SPEED", cs_val, theme.MUTED if _sc else theme.TEXT),
            ("LAUNCH", f"{vert_launch:.1f}°", theme.TEXT),
            ("TOTAL SPIN", f"{int(total_spin)} RPM", theme.TEXT),
            ("APEX", f"{apex_yds:.1f} YDS", theme.TEXT),
            ("OFFLINE", off_str, theme.TEXT if abs(offline_yds) <= 5.0 else theme.WARN)
        ]
        
        # Borderless, left-aligned: label small and quiet above the value.
        card_w = (avail_w - 30) // len(hud_cards)
        self.canvas.create_line(offset_x, hud_y2, offset_x + avail_w, hud_y2,
                                fill=theme.HAIRLINE)
        for i, (h_title, h_val, h_col) in enumerate(hud_cards):
            hx1 = offset_x + 18 + i * card_w
            self.canvas.create_text(hx1, hud_y1 + 12, text=h_title,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7, "bold"), anchor="w")
            self.canvas.create_text(hx1, hud_y1 + 34, text=h_val, fill=h_col,
                                    font=(theme.ui_font(), 13), anchor="w")

        # 5. WebGPU Launch Button (Bottom Right)
        btn_w, btn_h = 240, 32
        bx2 = offset_x + avail_w - 15
        bx1 = bx2 - btn_w
        by2 = h - 12
        by1 = by2 - btn_h
        self.range_launch_web_rect = (bx1, by1, bx2, by2)
        self.canvas.create_rectangle(bx1, by1, bx2, by2, fill=theme.ACCENT, outline="")
        self.canvas.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text="Open 3D WebGPU Range  ↗", fill="#EAF5EE", font=(theme.ui_font(), 9, "bold"))

    def draw_dispersion_and_gapping(self, avail_w, h, offset_x=0):
        self.dispersion_club_chip_rects.clear()
        self.dispersion_dot_rects.clear()
        self.dispersion_submode_rects.clear()

        top_y = 58
        bot_y = h - 14

        # Left Fairway / Trajectory Area vs Right Gapping Panel (Resizable Splitter)
        plot_w = int(avail_w * self.dispersion_splitter_ratio)
        plot_w = max(220, min(avail_w - 180, plot_w))
        
        split_x1 = offset_x + plot_w + 3
        split_x2 = split_x1 + 8
        self.dispersion_splitter_rect = (split_x1 - 4, top_y, split_x2 + 4, bot_y)

        gap_x1 = split_x2 + 6
        gap_w = (offset_x + avail_w) - gap_x1 - 12

        # 1. Sub-View Navigation Pills at top of Left Area
        submodes = [
            ("split", "🔀 Split View (Both)"),
            ("topdown", "🎯 Overhead Dispersion"),
            ("side", "📈 Trajectory Side-View")
        ]
        sub_x = offset_x + 10
        for sm_key, sm_label in submodes:
            sm_w = len(sm_label) * 6 + 22
            sm_rect = (sub_x, top_y, sub_x + sm_w, top_y + 24)
            self.dispersion_submode_rects.append((sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], sm_key))
            is_active = (self.dispersion_view_submode == sm_key)
            self.canvas.create_rectangle(sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], fill=theme.SURFACE_2 if is_active else theme.SURFACE, outline=theme.ACCENT_TEXT if is_active else theme.HAIRLINE)
            self.canvas.create_text((sm_rect[0] + sm_rect[2]) // 2, (sm_rect[1] + sm_rect[3]) // 2, text=sm_label, fill=theme.ACCENT_TEXT if is_active else theme.TEXT_2, font=(theme.ui_font(), 8, "bold" if is_active else "normal"))
            sub_x += sm_w + 8

        # Filter session shots
        grouped_shots = {}
        for idx, shot in enumerate(self.session_shots):
            if shot.get("excluded", False):
                continue
            c_name = shot.get("club", "7 Iron")
            if self.dispersion_selected_club != "ALL" and c_name != self.dispersion_selected_club:
                continue
            if c_name not in grouped_shots:
                grouped_shots[c_name] = []
            grouped_shots[c_name].append((idx, shot))

        content_top = top_y + 30
        content_h = bot_y - content_top
        plot_x1 = offset_x + 10
        plot_x2 = offset_x + plot_w
        chart_w = max(100, plot_x2 - plot_x1 - 50)
        margin_x = plot_x1 + 45
        max_x_yds = 350.0

        # Draw Left Area Charts according to submode
        if self.dispersion_view_submode == "split":
            # Stacked: Top = Side View Trajectory Profile, Bottom = Top-Down Overhead Dispersion
            side_h = int(content_h * 0.44)
            side_y1 = content_top
            side_y2 = side_y1 + side_h

            disp_y1 = side_y2 + 12
            disp_y2 = bot_y

            self._draw_side_trajectory_chart(plot_x1, side_y1, plot_x2, side_y2, margin_x, chart_w, max_x_yds, grouped_shots)
            self._draw_topdown_dispersion_chart(plot_x1, disp_y1, plot_x2, disp_y2, max_x_yds, grouped_shots)

        elif self.dispersion_view_submode == "side":
            # Full Height Side View Trajectory Profile
            self._draw_side_trajectory_chart(plot_x1, content_top, plot_x2, bot_y, margin_x, chart_w, max_x_yds, grouped_shots)

        else: # "topdown"
            # Full Height Overhead Dispersion
            self._draw_topdown_dispersion_chart(plot_x1, content_top, plot_x2, bot_y, max_x_yds, grouped_shots)

        # Draw Vertical Draggable Splitter Bar Handle
        is_dragging = self.dispersion_splitter_dragging
        self.canvas.create_rectangle(split_x1, top_y, split_x2, bot_y, fill=theme.ACCENT_TEXT if is_dragging else theme.SURFACE, outline=theme.ACCENT_TEXT if is_dragging else theme.HAIRLINE)
        mid_y = (top_y + bot_y) // 2
        for dy in [-16, -8, 0, 8, 16]:
            self.canvas.create_line(split_x1 + 2, mid_y + dy, split_x2 - 2, mid_y + dy, fill=theme.TEXT if is_dragging else theme.TEXT_3, width=1)

        # 2. Right Gapping & Distribution Panel
        self.canvas.create_rectangle(gap_x1, top_y, gap_x1 + gap_w, bot_y, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(gap_x1 + 14, top_y + 16, text="📊 CLUB GAPPING & SPREAD", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 9, "bold"), anchor="w")

        # Club Filter Chips along top of right panel
        chip_y1 = top_y + 30
        chip_y2 = chip_y1 + 22
        all_chip_rect = (gap_x1 + 10, chip_y1, gap_x1 + 55, chip_y2)
        self.dispersion_club_chip_rects.append((all_chip_rect[0], all_chip_rect[1], all_chip_rect[2], all_chip_rect[3], "ALL"))
        is_all = (self.dispersion_selected_club == "ALL")
        self.canvas.create_rectangle(all_chip_rect[0], all_chip_rect[1], all_chip_rect[2], all_chip_rect[3], fill=theme.SURFACE_2 if is_all else theme.SURFACE, outline=theme.ACCENT_TEXT if is_all else theme.HAIRLINE)
        self.canvas.create_text((all_chip_rect[0] + all_chip_rect[2]) // 2, (chip_y1 + chip_y2) // 2, text="ALL", fill=theme.ACCENT_TEXT if is_all else theme.TEXT_2, font=(theme.ui_font(), 8, "bold"))

        # Gapping Cards per club
        card_start_y = top_y + 60
        card_h = 70
        card_gap = 8

        session_clubs = []
        for s in self.session_shots:
            c = s.get("club", "7 Iron")
            if c not in session_clubs:
                session_clubs.append(c)

        if not session_clubs:
            self.canvas.create_text(gap_x1 + gap_w // 2, top_y + 150, text="NO SHOTS RECORDED", fill=theme.TEXT_3, font=(theme.ui_font(), 10, "bold"))
        else:
            prev_avg_carry = None
            for i, c_name in enumerate(session_clubs[:6]):
                cy1 = card_start_y + i * (card_h + card_gap)
                cy2 = cy1 + card_h
                if cy2 > bot_y:
                    break

                c_color = self.get_club_color(c_name)
                c_shots = [s for s in self.session_shots if s.get("club") == c_name and not s.get("excluded", False)]
                c_us = [self.aim_corrected(s).get("open_golf_coach", {}).get("us_customary_units", {}) for s in c_shots]
                c_carries = [u.get("carry_distance_yards", 0.0) for u in c_us]
                c_carries = [x for x in c_carries if x > 0]
                c_offs = [u.get("offline_distance_yards", 0.0) for u in c_us]

                if c_carries:
                    avg_c = sum(c_carries) / len(c_carries)
                    min_c, max_c = min(c_carries), max(c_carries)
                    std_c = (sum((x - avg_c) ** 2 for x in c_carries) / len(c_carries)) ** 0.5
                    avg_off = sum(c_offs) / len(c_offs) if c_offs else 0.0
                    off_dir = "R" if avg_off >= 0 else "L"
                else:
                    avg_c = min_c = max_c = std_c = avg_off = 0.0
                    off_dir = "R"

                # Card background
                self.canvas.create_rectangle(gap_x1 + 10, cy1, gap_x1 + gap_w - 10, cy2, fill=theme.SURFACE, outline=theme.HAIRLINE)
                # Left accent color strip
                self.canvas.create_rectangle(gap_x1 + 10, cy1, gap_x1 + 15, cy2, fill=c_color, outline="")

                # Line 1: Club Name & Shot Count
                self.canvas.create_text(gap_x1 + 22, cy1 + 14, text=f"🏌️ {c_name}", fill=theme.TEXT, font=(theme.ui_font(), 9, "bold"), anchor="w")
                self.canvas.create_text(gap_x1 + gap_w - 18, cy1 + 14, text=f"{len(c_shots)} shots", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="e")

                # Line 2: Average Carry with Std Dev & Gap Delta
                gap_str = f"({avg_c - prev_avg_carry:+.1f}y gap)" if (prev_avg_carry is not None and avg_c > 0) else ""
                self.canvas.create_text(gap_x1 + 22, cy1 + 34, text=f"Carry: {avg_c:.1f} yds (±{std_c:.1f}y)  {gap_str}", fill=c_color, font=(theme.ui_font(), 9, "bold"), anchor="w")

                # Line 3: Min-Max window & Offline Dispersion
                self.canvas.create_text(gap_x1 + 22, cy1 + 52, text=f"Window: {min_c:.0f}–{max_c:.0f}y  •  Lateral: {abs(avg_off):.1f}y {off_dir}", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")

                if avg_c > 0:
                    prev_avg_carry = avg_c

    def _draw_side_trajectory_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, margin_x, chart_w, max_x_yds, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="📈 TRAJECTORY PROFILE (ELEVATION & APEX)", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

        base_y = plot_y2 - 20
        chart_h = base_y - (plot_y1 + 28)
        max_h_yds = 60.0

        # X distance grid ticks
        ticks = [0, 50, 100, 150, 200, 250, 300, 350]
        for t in ticks:
            tx = margin_x + int((t / max_x_yds) * chart_w)
            self.canvas.create_line(tx, plot_y1 + 24, tx, base_y, fill=theme.SURFACE_2, width=1, dash=(2, 2))
            self.canvas.create_text(tx, base_y + 10, text=str(t), fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Y height grid lines. Steps follow max_h_yds -- a fixed [0,20,40,60]
        # against a small axis puts labels far above the plot, where they
        # trail up the page over whatever is drawn above the chart.
        _hstep = 20 if max_h_yds > 45 else (10 if max_h_yds > 22 else 5)
        for hy in range(0, int(max_h_yds) + 1, _hstep):
            ty = base_y - int((hy / max_h_yds) * chart_h)
            if ty < plot_y1 + 22 or ty > base_y:
                continue
            self.canvas.create_line(margin_x, ty, margin_x + chart_w, ty, fill=theme.SURFACE_2, width=1, dash=(2, 2))
            self.canvas.create_text(margin_x - 14, ty, text=f"{hy}y", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Ground baseline
        self.canvas.create_line(margin_x, base_y, margin_x + chart_w, base_y, fill=theme.ACCENT_TEXT, width=1)

        # Plot flight arcs for each shot
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            for real_idx, shot in items:
                shot = self.aim_corrected(shot)
                ogc = shot.get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                c_yds = us.get("carry_distance_yards", 0.0)
                apex_y = us.get("peak_height_yards", 25.0)
                if c_yds <= 0:
                    continue

                is_sel = (real_idx == self.selected_shot_index)
                arc_col = theme.WARN if is_sel else c_color
                line_w = 3 if is_sel else 1

                pts = []
                for step in range(0, 101, 4):
                    frac = step / 100.0
                    curr_x = c_yds * frac
                    curr_h = math.sin(frac * math.pi) * apex_y
                    cx_px = margin_x + int((curr_x / max_x_yds) * chart_w)
                    cy_px = base_y - int((curr_h / max_h_yds) * chart_h)
                    pts.extend([cx_px, cy_px])

                if len(pts) >= 4:
                    self.canvas.create_line(pts, fill=arc_col, width=line_w, smooth=True)

                land_x = margin_x + int((c_yds / max_x_yds) * chart_w)
                self.dispersion_dot_rects.append((land_x, base_y, real_idx))
                self.canvas.create_oval(land_x - (4 if is_sel else 2), base_y - (4 if is_sel else 2), land_x + (4 if is_sel else 2), base_y + (4 if is_sel else 2), fill=theme.WARN if is_sel else c_color, outline="")

    def _draw_topdown_dispersion_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, max_range_yds, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="🎯 OVERHEAD DISPERSION & COVARIANCE ELLIPSES", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

        plot_w = plot_x2 - plot_x1
        cx = (plot_x1 + plot_x2) // 2
        tee_y = plot_y2 - 16
        plot_h = tee_y - plot_y1 - 26
        max_lat_yds = 45.0

        # Centerline
        self.canvas.create_line(cx, tee_y, cx, plot_y1 + 22, fill=theme.HAIRLINE, width=2, dash=(6, 4))

        # Lateral deviation guides
        for lat in [-30, -15, 15, 30]:
            lx = cx + int((lat / max_lat_yds) * (plot_w * 0.45))
            self.canvas.create_line(lx, tee_y, lx, plot_y1 + 24, fill=theme.SURFACE_2, width=1, dash=(2, 4))
            self.canvas.create_text(lx, plot_y2 - 6, text=f"{abs(lat)}y{'L' if lat < 0 else 'R'}", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Concentric distance arcs. Step follows max_range_yds -- a fixed
        # 50..350 list against a small axis draws arcs above the plot and
        # stacks their labels up the left edge over the panel above.
        # Pick the finest step that still yields at most 6 arcs, so the
        # ladder stays legible whether the session is wedges or drivers.
        _rstep = next((s for s in (5, 10, 20, 25, 50, 100)
                       if max_range_yds / s <= 6), 100)
        for yds in range(_rstep, int(max_range_yds) + 1, _rstep):
            frac = yds / max_range_yds
            arc_y = tee_y - int(frac * plot_h)
            if arc_y < plot_y1 + 24 or arc_y > tee_y:
                continue
            self.canvas.create_line(plot_x1 + 10, arc_y, plot_x2 - 10, arc_y, fill=theme.SURFACE_2, width=1, dash=(3, 3))
            self.canvas.create_text(plot_x1 + 20, arc_y, text=f"{yds}y", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Render Ellipses & Dots
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            carries = []
            offs = []
            for real_idx, s in items:
                ogc = self.aim_corrected(s).get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                c_yds = us.get("carry_distance_yards", 0.0)
                o_yds = us.get("offline_distance_yards", 0.0)
                if c_yds > 0:
                    carries.append(c_yds)
                    offs.append(o_yds)

            if len(carries) >= 2:
                mu_c = sum(carries) / len(carries)
                mu_o = sum(offs) / len(offs)
                std_c = max(3.0, (sum((x - mu_c) ** 2 for x in carries) / len(carries)) ** 0.5)
                std_o = max(2.0, (sum((x - mu_o) ** 2 for x in offs) / len(offs)) ** 0.5)

                cen_x = cx + int((mu_o / max_lat_yds) * (plot_w * 0.45))
                cen_y = tee_y - int((mu_c / max_range_yds) * plot_h)
                rx1 = int((std_o / max_lat_yds) * (plot_w * 0.45))
                ry1 = int((std_c / max_range_yds) * plot_h)

                # 2-Sigma outer dashed
                self.canvas.create_oval(cen_x - rx1 * 2, cen_y - ry1 * 2, cen_x + rx1 * 2, cen_y + ry1 * 2, fill="", outline=c_color, width=1, dash=(4, 4))
                # 1-Sigma inner solid
                self.canvas.create_oval(cen_x - rx1, cen_y - ry1, cen_x + rx1, cen_y + ry1, fill=c_color, outline=c_color, width=2, stipple="gray25")
                # Mean marker
                self.canvas.create_line(cen_x - 5, cen_y, cen_x + 5, cen_y, fill=theme.TEXT, width=2)
                self.canvas.create_line(cen_x, cen_y - 5, cen_x, cen_y + 5, fill=theme.TEXT, width=2)
                self.canvas.create_text(cen_x, cen_y - ry1 - 8, text=f"{c_name}: {mu_c:.1f}y", fill=c_color, font=(theme.ui_font(), 7, "bold"))

            # Draw dots
            for real_idx, s in items:
                ogc = self.aim_corrected(s).get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                c_yds = us.get("carry_distance_yards", 0.0)
                o_yds = us.get("offline_distance_yards", 0.0)
                if c_yds <= 0:
                    continue

                dx = cx + int((o_yds / max_lat_yds) * (plot_w * 0.45))
                dy = tee_y - int((c_yds / max_range_yds) * plot_h)
                self.dispersion_dot_rects.append((dx, dy, real_idx))

                is_sel = (real_idx == self.selected_shot_index)
                r = 5 if is_sel else 3
                self.canvas.create_oval(dx - r, dy - r, dx + r, dy + r, fill=theme.WARN if is_sel else c_color, outline=theme.TEXT if is_sel else "")


    def draw_shot_table_viewport(self, avail_w, h, offset_x=0):
        self.table_row_rects.clear()
        self.table_header_rects.clear()
        self.table_checkbox_rects.clear()

        ui_scale = max(0.9, min(2.4, min(avail_w / 1100.0, h / 720.0)))
        font_scale = max(0.9, min(1.8, ui_scale))

        top_y = 58
        table_x1 = offset_x + 10
        table_x2 = offset_x + avail_w - 10
        table_avail_w = table_x2 - table_x1

        # 1. Pinned Summary Averages Banner (Dynamically scaled height & font)
        avg_h = int(42 * ui_scale)
        avg_y1 = top_y
        avg_y2 = avg_y1 + avg_h
        self.canvas.create_rectangle(table_x1, avg_y1, table_x2, avg_y2, fill=theme.SURFACE_2, outline=theme.ACCENT_TEXT, width=2)
        
        avgs = self.calculate_session_averages()
        active_count = avgs.get("count", 0)
        
        # Left Tag Badge (Clean, contained, zero overlap)
        badge_w = int(210 * font_scale)
        badge_x1 = table_x1 + 10
        badge_x2 = badge_x1 + badge_w
        self.canvas.create_rectangle(badge_x1, avg_y1 + 6, badge_x2, avg_y2 - 6, fill=theme.SURFACE_2, outline=theme.ACCENT_TEXT, width=1)
        self.canvas.create_text((badge_x1 + badge_x2) // 2, (avg_y1 + avg_y2) // 2, text=f"SESSION AVERAGES ({active_count})", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), max(8, int(10 * font_scale)), "bold"))
        
        if avgs:
            metrics_x = badge_x2 + 16
            # Averaging a saturated club-speed/smash estimate produces a
            # confident-looking constant, so drop them from the summary when
            # every contributing shot was clamped.
            all_clamped = all(
                self.compute_smash_confidence(
                    s.get("ball_speed_meters_per_second"),
                    s.get("vertical_launch_angle_degrees"),
                    s.get("total_spin_rpm"),
                )["clamped"]
                for s in self.session_shots
            ) if self.session_shots else False

            derived = ("Club Spd: --  |  Smash: --  |  " if all_clamped else
                       f"Club Spd: {avgs.get('club_speed', 0.0):.1f}mph  |  "
                       f"Smash: {avgs.get('smash', 1.0):.2f}  |  ")
            avg_metrics = (
                f"Carry: {avgs.get('carry', 0.0):.1f}y  |  "
                f"Ball Spd: {avgs.get('ball_speed', 0.0):.1f}mph  |  "
                + derived +
                f"Launch: {avgs.get('launch_angle', 0.0):.1f}°  |  "
                f"Spin: {int(avgs.get('total_spin', 0.0))}rpm  |  "
                f"Apex: {avgs.get('apex', 0.0):.1f}y  |  "
                f"Offline: {avgs.get('offline', 0.0):+.1f}y"
            )
            self.canvas.create_text(metrics_x, (avg_y1 + avg_y2) // 2, text=avg_metrics, fill=theme.TEXT_2, font=(theme.ui_font(), max(9, int(11 * font_scale))), anchor="w")

        # 2. Interactive Column Headers (Proportionally distributed across 100% width)
        head_h = int(32 * ui_scale)
        head_y1 = avg_y2 + 6
        head_y2 = head_y1 + head_h
        self.canvas.create_rectangle(table_x1, head_y1, table_x2, head_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)

        cols_base = [
            ("index", "#", 40, "c"),
            ("excluded", "Excl", 44, "c"),
            ("club", "Club", 70, "w"),
            ("carry", "Carry", 68, "e"),
            ("total", "Total", 68, "e"),
            ("ball_speed", "Ball Spd", 74, "e"),
            ("club_speed", "Club Spd", 74, "e"),
            ("smash", "Smash", 60, "e"),
            ("launch", "Launch", 64, "e"),
            ("push_pull", "Push/Pull", 72, "e"),
            ("spin", "Spin", 68, "e"),
            ("sidespin", "Sidespin", 72, "e"),
            ("axis", "Axis", 64, "e"),
            ("path", "Path", 64, "e"),
            ("face", "Face", 64, "e"),
            ("apex", "Apex", 62, "e"),
            ("descent", "Descent", 64, "e"),
            ("offline", "Offline", 72, "e")
        ]

        base_tot_w = sum(c[2] for c in cols_base)
        w_factor = max(1.0, table_avail_w / float(base_tot_w))
        cols = [(c[0], c[1], int(c[2] * w_factor), c[3]) for c in cols_base]

        curr_x = table_x1
        for col_key, col_title, col_w, align in cols:
            cx2 = min(table_x2, curr_x + col_w)
            self.table_header_rects.append((curr_x, head_y1, cx2, head_y2, col_key))
            
            is_sorted = (self.table_sort_col == col_key)
            sort_arrow = (" ▲" if self.table_sort_asc else " ▼") if is_sorted else ""
            txt_col = theme.ACCENT_TEXT if is_sorted else theme.TEXT_2
            
            if align == "c":
                tx = (curr_x + cx2) // 2
            elif align == "e":
                tx = cx2 - 8
            else:
                tx = curr_x + 8

            self.canvas.create_text(tx, (head_y1 + head_y2) // 2, text=col_title + sort_arrow, fill=txt_col, font=(theme.ui_font(), max(8, int(10 * font_scale)), "bold"), anchor=align)
            curr_x = cx2

        # 3. Sortable Data Rows
        data_y1 = head_y2 + 4
        row_h = int(32 * ui_scale)
        avail_rows = max(1, (h - data_y1 - 15) // row_h)
        
        raw_items = list(enumerate(self.session_shots))

        def get_sort_val(item):
            idx, s = item
            ogc = self.aim_corrected(s).get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            if self.table_sort_col == "index": return idx
            elif self.table_sort_col == "excluded": return 1 if s.get("excluded", False) else 0
            elif self.table_sort_col == "club": return s.get("club", "")
            elif self.table_sort_col == "carry": return us.get("carry_distance_yards", 0.0)
            elif self.table_sort_col == "total": return us.get("total_distance_yards", 0.0)
            elif self.table_sort_col == "ball_speed": return us.get("ball_speed_mph", 0.0)
            elif self.table_sort_col == "club_speed": return us.get("club_speed_mph", 0.0)
            elif self.table_sort_col == "smash": return ogc.get("smash_factor", 1.0)
            elif self.table_sort_col == "launch": return s.get("vertical_launch_angle_degrees", 0.0)
            elif self.table_sort_col == "push_pull": return self.aim_corrected(s).get("horizontal_launch_angle_degrees", 0.0)
            elif self.table_sort_col == "spin": return ogc.get("total_spin_rpm", 0.0)
            elif self.table_sort_col == "sidespin": return ogc.get("sidespin_rpm", 0.0)
            elif self.table_sort_col == "axis": return ogc.get("spin_axis_degrees", 0.0)
            elif self.table_sort_col == "path": return self.resolve_handed(ogc.get("club_path_degrees"), 0.0)
            elif self.table_sort_col == "face": return self.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
            elif self.table_sort_col == "apex": return us.get("peak_height_yards", 0.0)
            elif self.table_sort_col == "descent": return ogc.get("descent_angle_degrees", 0.0)
            elif self.table_sort_col == "offline": return us.get("offline_distance_yards", 0.0)
            return idx

        sorted_items = sorted(raw_items, key=get_sort_val, reverse=not self.table_sort_asc)
        visible_items = sorted_items[self.table_scroll_offset : self.table_scroll_offset + avail_rows]

        for r_i, (real_idx, shot) in enumerate(visible_items):
            ry1 = data_y1 + r_i * row_h
            ry2 = ry1 + row_h - 2
            
            is_sel = (real_idx == self.selected_shot_index)
            is_ex = shot.get("excluded", False)
            bg = "#2A2118" if is_sel else (theme.SURFACE if r_i % 2 == 0 else theme.SURFACE_2)
            border = theme.WARN if is_sel else theme.HAIRLINE
            txt_color = theme.TEXT_3 if is_ex else (theme.TEXT if not is_sel else theme.WARN)

            self.canvas.create_rectangle(table_x1, ry1, table_x2, ry2, fill=bg, outline=border, width=2 if is_sel else 1)
            self.table_row_rects.append((table_x1, ry1, table_x2, ry2, real_idx))

            ogc_shot = self.aim_corrected(shot)
            ogc = ogc_shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            c_val = us.get("carry_distance_yards", 0.0)
            tot_val = us.get("total_distance_yards", 0.0)
            bs_val = us.get("ball_speed_mph", 0.0)
            cs_val = us.get("club_speed_mph", 0.0)
            sm_val = ogc.get("smash_factor", 1.0)
            # Both are OpenGolfCoach derivations of ball speed and collapse to
            # a constant when its model saturates -- show "--" rather than a
            # column of identical numbers that looks like measurement.
            row_clamped = self.compute_smash_confidence(
                shot.get("ball_speed_meters_per_second"),
                shot.get("vertical_launch_angle_degrees"),
                shot.get("total_spin_rpm"),
            )["clamped"]
            la_val = ogc_shot.get("vertical_launch_angle_degrees", 0.0)
            hl_val = ogc_shot.get("horizontal_launch_angle_degrees", 0.0)
            sp_val = ogc.get("total_spin_rpm", 0.0)
            ss_val = ogc.get("sidespin_rpm", 0.0)
            sa_val = ogc.get("spin_axis_degrees", 0.0)
            cp_val = self.resolve_handed(ogc.get("club_path_degrees"), 0.0)
            fp_val = self.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
            ap_val = us.get("peak_height_yards", 0.0)
            da_val = ogc.get("descent_angle_degrees", 0.0)
            off_val = us.get("offline_distance_yards", 0.0)

            row_data = {
                "index": f"#{real_idx + 1}",
                "excluded": "[X]" if is_ex else "[✓]",
                "club": shot.get("club", "Club"),
                "carry": f"{c_val:.1f}",
                "total": f"{tot_val:.1f}",
                "ball_speed": f"{bs_val:.1f}",
                "club_speed": "--" if row_clamped else f"{cs_val:.1f}",
                "smash": "--" if row_clamped else f"{sm_val:.2f}",
                "launch": f"{la_val:.1f}°",
                "push_pull": f"{hl_val:+.1f}°",
                "spin": f"{int(sp_val)}",
                "sidespin": f"{int(ss_val):+d}",
                "axis": f"{sa_val:+.1f}°",
                "path": f"{cp_val:+.1f}°",
                "face": f"{fp_val:+.1f}°",
                "apex": f"{ap_val:.1f}y",
                "descent": f"{da_val:.1f}°",
                "offline": f"{off_val:+.1f}y"
            }

            curr_x = table_x1
            for col_key, col_title, col_w, align in cols:
                cx2 = min(table_x2, curr_x + col_w)
                val_text = row_data.get(col_key, "-")

                if col_key == "excluded":
                    self.table_checkbox_rects.append((curr_x, ry1, cx2, ry2, real_idx))
                    chk_color = theme.DANGER if is_ex else theme.ACCENT_TEXT
                    self.canvas.create_text((curr_x + cx2) // 2, (ry1 + ry2) // 2, text=val_text, fill=chk_color, font=(theme.ui_font(), max(9, int(11 * font_scale)), "bold"))
                else:
                    if align == "c":
                        tx = (curr_x + cx2) // 2
                    elif align == "e":
                        tx = cx2 - 8
                    else:
                        tx = curr_x + 8
                    self.canvas.create_text(tx, (ry1 + ry2) // 2, text=val_text, fill=txt_color, font=(theme.ui_font(), max(8, int(11 * font_scale)), "bold" if is_sel else "normal"), anchor=align)

                curr_x = cx2

    def draw_big_numbers_viewport(self, avail_w, h, carry, total, ball_speed, club_speed, smash, launch, spin, spin_axis, club_path, face_to_path, apex, offline, closure_rate=0.0, attack_angle=0.0, dynamic_loft=0.0, hang_time=0.0, offset_x=0):
        ui_scale = max(0.9, min(2.5, min(avail_w / 1100.0, h / 720.0)))
        top_y = 60
        bot_y = h - 15
        grid_w = avail_w - 30
        grid_h = bot_y - top_y

        off_dir = "L" if offline < 0 else "R"
        # Match draw_4_quadrant_studio's handed convention: the club_path value
        # is already hand-resolved, and for LH the sign semantics mirror.
        if self.is_left_handed:
            path_dir = "In-Out" if club_path < 0 else "Out-In"
        else:
            path_dir = "In-Out" if club_path > 0 else "Out-In"
        face_dir = "Open" if face_to_path > 0 else "Closed"
        axis_dir = "R" if spin_axis > 0 else "L"
        apex_ft = apex * 3.0

        # One accent (carry), neutrals elsewhere. Tags carry the semantics.
        clamped = self.compute_smash_confidence(
            (self.current_shot or {}).get("ball_speed_meters_per_second"),
            (self.current_shot or {}).get("vertical_launch_angle_degrees"),
            (self.current_shot or {}).get("total_spin_rpm"),
        )["clamped"] if self.current_shot else False
        muted = theme.MUTED

        cards = [
            ("CARRY DISTANCE", f"{carry:.1f}", "YARDS", theme.ACCENT_TEXT, ""),
            ("TOTAL DISTANCE", f"{total:.1f}", "YARDS", theme.TEXT, ""),
            ("BALL SPEED", f"{ball_speed:.1f}", "MPH", theme.TEXT, ""),
            ("CLUB SPEED", "--" if clamped else f"{club_speed:.1f}",
             "" if clamped else "MPH", muted if clamped else theme.TEXT,
             "" if clamped else "DERIVED"),
            ("SMASH FACTOR", "--" if clamped else f"{smash:.2f}",
             "" if clamped else "RATIO", muted if clamped else theme.TEXT,
             "" if clamped else "DERIVED"),
            ("LAUNCH ANGLE", f"{launch:.1f}°", "DEGREES", theme.TEXT, ""),
            ("TOTAL SPIN", f"{int(spin)}", "RPM", theme.TEXT, ""),
            ("SPIN AXIS", f"{abs(spin_axis):.1f}° {axis_dir}", "DEGREES", theme.TEXT, "DRAW" if spin_axis < 0 else "FADE"),
            ("CLOSURE RATE", f"{int(closure_rate)}", "DEG / SEC", theme.TEXT, "DERIVED"),
            ("APEX HEIGHT", f"{apex_ft:.1f}", "FEET", theme.TEXT, ""),
            ("CLUB PATH", f"{abs(club_path):.1f}° {path_dir}", "DEGREES", theme.TEXT, "DERIVED"),
            ("FACE TO PATH", f"{abs(face_to_path):.1f}° {face_dir}", "DEGREES", theme.TEXT, "DERIVED"),
            ("ATTACK ANGLE", "--", "", muted, "NOT MEASURED"),
            ("DYNAMIC LOFT", "--", "", muted, "NOT MEASURED"),
            ("HANG TIME", f"{hang_time:.1f}s", "SECONDS", theme.TEXT, ""),
            ("OFFLINE", f"{abs(offline):.1f} {off_dir}", "YARDS",
             theme.TEXT if abs(offline) <= 4.0 else theme.WARN,
             "ON TARGET" if abs(offline) <= 4.0 else "")
        ]

        rows = 4
        cols = 4
        col_gap = int(10 * ui_scale)
        row_gap = int(10 * ui_scale)
        card_w = (grid_w - (cols - 1) * col_gap) // cols
        card_h = (grid_h - (rows - 1) * row_gap) // rows

        lbl_font = (theme.ui_font(), max(8, int(10 * ui_scale)), "bold")
        unit_font = (theme.ui_font(), max(7, int(9 * ui_scale)), "bold")
        tag_font = (theme.ui_font(), max(7, int(8 * ui_scale)), "bold")

        for idx, (c_label, c_val, c_unit, c_color, c_tag) in enumerate(cards):
            r = idx // cols
            c = idx % cols
            
            x1 = offset_x + 15 + c * (card_w + col_gap)
            y1 = top_y + r * (card_h + row_gap)
            x2 = x1 + card_w
            y2 = y1 + card_h

            # Card Container
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline="")
            
            # Header Label
            self.canvas.create_text(x1 + int(14 * ui_scale), y1 + int(16 * ui_scale), text=c_label, fill=theme.TEXT_3, font=lbl_font, anchor="w")

            # Status pill in top right of card
            if c_tag:
                # Provenance tags (DERIVED / NOT MEASURED) are quiet captions,
                # not badges -- they qualify the number, they do not alert.
                quiet = c_tag in ("DERIVED", "NOT MEASURED")
                if quiet:
                    self.canvas.create_text(x2 - 14, y1 + int(16 * ui_scale), text=c_tag,
                                            fill=theme.TEXT_3, font=tag_font, anchor="e")
                else:
                    tag_w = int(len(c_tag) * 6 * ui_scale + 14 * ui_scale)
                    self.canvas.create_rectangle(x2 - tag_w - 10, y1 + int(8 * ui_scale),
                                                 x2 - 10, y1 + int(24 * ui_scale),
                                                 fill=theme.ACCENT_DEEP, outline="")
                    self.canvas.create_text(x2 - 10 - tag_w // 2, y1 + int(16 * ui_scale),
                                            text=c_tag, fill=theme.ACCENT_TEXT,
                                            font=tag_font, anchor="center")

            # Giant Primary Value (Dynamically scaled font to prevent wide strings from overflowing card width)
            val_len = len(c_val)
            if val_len > 9:
                f_size = max(13, int(18 * ui_scale))
            elif val_len > 6:
                f_size = max(15, int(22 * ui_scale))
            else:
                f_size = max(18, int(28 * ui_scale))
            dynamic_val_font = (theme.ui_font(), f_size, "bold")
            self.canvas.create_text((x1 + x2) // 2, y1 + (card_h // 2) + 4, text=c_val, fill=c_color, font=dynamic_val_font, anchor="center")

            # Bottom Unit Tag
            self.canvas.create_text((x1 + x2) // 2, y2 - int(12 * ui_scale), text=c_unit, fill=theme.TEXT_3, font=unit_font, anchor="center")

    def draw_overview_viewport(self, avail_w, h, carry, total, ball_speed,
                               club_speed, smash, launch, spin, apex, offline,
                               descent, hang_time, club_path, face_to_path,
                               spin_axis, face_to_target=0.0, shot_name="",
                               smash_clamped=False, offset_x=0, top_bar_h=52):
        """Landing view: this shot at a glance, plus session context.

        Layout follows the approved full-screen mockup -- header, primary
        metric row, three cards, recent strip + session summary, then a
        bottom band with dispersion and tendencies.
        """
        pad = 20
        x0, x1 = offset_x + pad, offset_x + avail_w - pad
        y = top_bar_h + 14

        shots = self.session_shots
        n = len(shots)

        self.overview_viewall_rect = None
        self.overview_prev_rect = None
        self.overview_next_rect = None
        self.overview_bar_rects = []

        # ---- header -------------------------------------------------------
        idx = (self.selected_shot_index + 1) if self.selected_shot_index is not None else n
        hid = self.canvas.create_text(x0, y + 12, text=f"Shot {idx}",
                                      fill=theme.TEXT,
                                      font=(theme.ui_font(), 19, "bold"), anchor="w")
        hbb = self.canvas.bbox(hid)
        hx = (hbb[2] + 10) if hbb else (x0 + 90)
        oid = self.canvas.create_text(hx, y + 16, text=f"of {n}",
                                      fill=theme.TEXT_3,
                                      font=(theme.ui_font(), 10), anchor="w")

        # Shot shape as a quiet chip. Measure the "of N" text rather than
        # assuming a width -- a hardcoded offset overlaps as soon as the
        # shot count reaches two digits.
        if shot_name:
            obb = self.canvas.bbox(oid)
            chip_x = (obb[2] + 14) if obb else (hx + 46)
            tid = self.canvas.create_text(chip_x + 12, y + 15, text=shot_name,
                                          fill=theme.TEXT_2,
                                          font=(theme.ui_font(), 9), anchor="w")
            tbb = self.canvas.bbox(tid)
            if tbb:
                self.canvas.create_rectangle(chip_x, y + 4, tbb[2] + 12, y + 26,
                                             fill=theme.SURFACE_2, outline="")
                self.canvas.tag_raise(tid)

        # prev / next shot
        for i, (glyph, delta) in enumerate((("‹", -1), ("›", 1))):
            bx2 = x1 - (1 - i) * 34
            bx1 = bx2 - 28
            # Grey the arrow out at the ends of the session.
            tgt = (self.selected_shot_index if self.selected_shot_index is not None
                   else n - 1) + delta
            live = 0 <= tgt < n
            self.canvas.create_rectangle(bx1, y + 2, bx2, y + 28,
                                         fill=theme.SURFACE, outline="")
            self.canvas.create_text((bx1 + bx2) / 2, y + 15, text=glyph,
                                    fill=theme.TEXT_2 if live else theme.TEXT_3,
                                    font=(theme.ui_font(), 12),
                                    anchor="center")
            rect = (bx1, y + 2, bx2, y + 28) if live else None
            if delta < 0:
                self.overview_prev_rect = rect
            else:
                self.overview_next_rect = rect
        y += 40
        self.canvas.create_line(x0, y, x1, y, fill=theme.HAIRLINE)
        y += 18

        # ---- primary metrics ----------------------------------------------
        prim = [("CARRY", f"{carry:.1f}", "yds", theme.ACCENT_TEXT),
                ("TOTAL", f"{total:.1f}", "yds", theme.TEXT),
                ("BALL SPEED", f"{ball_speed:.1f}", "mph", theme.TEXT),
                ("CLUB SPEED", "--" if smash_clamped else f"{club_speed:.1f}",
                 "" if smash_clamped else "mph",
                 theme.MUTED if smash_clamped else theme.TEXT),
                ("SMASH", "--" if smash_clamped else f"{smash:.2f}", "",
                 theme.MUTED if smash_clamped else theme.TEXT)]
        step = (x1 - x0) / len(prim)
        for i, (lb, v, u, col) in enumerate(prim):
            cx = x0 + i * step
            self.canvas.create_text(cx, y, text=lb, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="w")
            vid = self.canvas.create_text(cx, y + 26, text=v, fill=col,
                                          font=(theme.ui_font(), 27), anchor="w")
            if u:
                bb = self.canvas.bbox(vid)
                if bb:
                    self.canvas.create_text(bb[2] + 6, y + 34, text=u,
                                            fill=theme.TEXT_3,
                                            font=(theme.ui_font(), 9), anchor="w")
        y += 48
        if smash_clamped:
            self.canvas.create_text(
                x0, y + 6,
                text="Club speed and smash unavailable — OpenGolfCoach estimate saturated for this shot",
                fill=theme.TEXT_3, font=(theme.ui_font(), 9), anchor="w")
        y += 22

        # ---- three cards ---------------------------------------------------
        gap = 14
        card_w = (x1 - x0 - gap * 2) / 3

        # Split the remaining height proportionally instead of giving the
        # cards everything and leaving the band the remainder -- that made
        # the band the only section that could be clipped, so growing the
        # window fed the cards while dispersion stayed cut off.
        avail_v = max(320, h - y - 56)          # 56 = inter-section gaps
        # The card row carries the hero graphic (the clubface), so it gets the
        # larger share; the recent strip and the bottom band are mostly text
        # and bars and stay readable at a smaller height.
        card_h = max(150, avail_v * 0.53)
        recent_h = max(104, avail_v * 0.21)

        def card(cx0, title, rows, tag=None):
            cx1 = cx0 + card_w
            self.canvas.create_rectangle(cx0, y, cx1, y + card_h,
                                         fill=theme.SURFACE, outline="")
            self.canvas.create_text(cx0 + 16, y + 15, text=title,
                                    fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                    anchor="w")
            if tag:
                self.canvas.create_text(cx1 - 16, y + 15, text=tag,
                                        fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 8), anchor="e")
            rh = (card_h - 44) / max(1, len(rows))
            for i, (k, v) in enumerate(rows):
                ry = y + 40 + i * rh + rh / 2
                self.canvas.create_text(cx0 + 16, ry, text=k, fill=theme.TEXT_2,
                                        font=(theme.ui_font(), 9), anchor="w")
                self.canvas.create_text(cx1 - 16, ry, text=v, fill=theme.TEXT,
                                        font=(theme.ui_font(), 10), anchor="e")
                if i < len(rows) - 1:
                    self.canvas.create_line(cx0 + 16, ry + rh / 2, cx1 - 16,
                                            ry + rh / 2, fill=theme.HAIRLINE)

        card(x0, "BALL FLIGHT", [
            ("Launch angle", f"{launch:.1f}°"),
            ("Apex", f"{apex:.1f} yds"),
            ("Descent angle", f"{descent:.1f}°"),
            ("Hang time", f"{hang_time:.1f} s"),
            ("Offline", f"{abs(offline):.1f} {'L' if offline < 0 else 'R'} yds"),
        ])
        card(x0 + card_w + gap, "CLUB DELIVERY", [
            ("Club path", f"{abs(club_path):.1f}° {'in-to-out' if club_path > 0 else 'out-to-in'}"),
            ("Face to target", f"{abs(face_to_target):.1f}° {'open' if face_to_target > 0 else 'closed'}"),
            ("Face to path", f"{abs(face_to_path):.1f}° {'open' if face_to_path > 0 else 'closed'}"),
            ("Spin axis", f"{abs(spin_axis):.1f} {'R' if spin_axis > 0 else 'L'}"),
            ("Total spin", f"{int(spin)} rpm"),
        ], tag="DERIVED")

        # strike card, with the clubface
        sx0 = x0 + (card_w + gap) * 2
        sx1 = sx0 + card_w
        self.canvas.create_rectangle(sx0, y, sx1, y + card_h,
                                     fill=theme.SURFACE, outline="")
        self.canvas.create_text(sx0 + 16, y + 15, text="STRIKE",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="w")
        head, detail, hcol = self.summarize_strike(self.current_shot)

        # Verdict block sits top-left: chip, then the plain-language answer.
        # Type scales with the card so a bigger window gets a bigger verdict
        # rather than more blank space around a fixed 17px string.
        head_size = int(max(17, min(30, card_h * 0.072)))
        line_h = int(head_size * 1.32)

        ty = y + 28
        if hcol == theme.WARN:
            self.canvas.create_rectangle(sx0 + 16, ty, sx0 + 104, ty + 21,
                                         fill="#2A2118", outline="")
            self.canvas.create_text(sx0 + 60, ty + 10, text="ESTIMATE",
                                    fill=theme.WARN,
                                    font=(theme.ui_font(), 8, "bold"),
                                    anchor="center")
            ty += 25
        parts = head.split(" ", 1) if " " in head else [head]
        for li, part in enumerate(parts):
            self.canvas.create_text(sx0 + 16, ty + line_h * 0.5 + li * line_h,
                                    text=part, fill=theme.TEXT,
                                    font=(theme.ui_font(), head_size), anchor="w")
        text_bot = ty + line_h * len(parts) + 6

        self.canvas.create_line(sx0 + 16, text_bot, sx1 - 16, text_bot,
                                fill=theme.HAIRLINE)
        self.canvas.create_text(sx0 + 16, y + card_h - 20, text=detail,
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="w")

        # Face centred between the verdict block and the footer.
        #
        # load_image_asset() pads the scaled art onto a SQUARE canvas of
        # max(w, h) + 40, so the on-canvas footprint is that square -- not the
        # target height passed in. For iron_face.png (290x220) the width wins,
        # making the real footprint 1.32*target_h + 40 on BOTH axes. Sizing
        # against the raw height overflowed the card by ~23px.
        face_top = text_bot + 12
        face_bot = y + card_h - 30
        FACE_ASPECT = 290.0 / 220.0

        def _footprint(th):
            return max(th * FACE_ASPECT, th) + 40

        # The +40 the loader adds is TRANSPARENT margin: it occupies layout
        # space but shows nothing, so budgeting against the padded footprint
        # leaves a visible gap. Budget against the visible art instead and
        # let the margin overhang into the card's own padding.
        fit_v = face_bot - face_top
        fit_h = card_w - 24
        face_h = max(84, min(fit_v / FACE_ASPECT, fit_h / FACE_ASPECT))
        # Centre on the true footprint so the art sits in the middle of the
        # remaining space rather than hanging off the bottom.
        self._draw_overview_face((sx0 + sx1) / 2,
                                 (face_top + face_bot) / 2, face_h)
        y += card_h + 20

        # ---- recent strip + session summary --------------------------------
        self.canvas.create_text(x0, y, text="RECENT", fill=theme.TEXT_3,
                                font=(theme.ui_font(), 8), anchor="w")
        va = self.canvas.create_text(x1, y, text="View all",
                                     fill=theme.TEXT_3,
                                     font=(theme.ui_font(), 8), anchor="e")
        vabb = self.canvas.bbox(va)
        if vabb:
            # Pad the hit area -- 8px text is a very small click target.
            self.overview_viewall_rect = (vabb[0] - 8, vabb[1] - 6,
                                          vabb[2] + 8, vabb[3] + 6)
        y += 14

        recent = shots[-5:]
        carries = []
        for s in recent:
            us = (s.get("open_golf_coach", {}) or {}).get("us_customary_units", {}) or {}
            carries.append(float(us.get("carry_distance_yards") or 0.0))

        bars_w = (x1 - x0) * 0.42
        if recent:
            mx = max(carries) or 1.0
            bw = (bars_w - 4 * 10) / len(recent)
            base_y = y + recent_h - 34
            bar_span = recent_h - 66        # room for value above, label below
            for i, (s, cv) in enumerate(zip(recent, carries)):
                bx = x0 + i * (bw + 10)
                # Bars share one baseline and scale to the session max, so
                # height is comparable across the strip.
                bh = max(10, int(bar_span * (cv / mx)))
                sel = (s is self.current_shot)
                # Whole column is the hit target, not just the drawn bar --
                # a 10px-tall bar is unclickable otherwise.
                self.overview_bar_rects.append(
                    (bx, y, bx + bw, base_y + 20, n - len(recent) + i))
                self.canvas.create_rectangle(bx, base_y - bh, bx + bw, base_y,
                                             fill=theme.ACCENT if sel else theme.SURFACE_2,
                                             outline="")
                # Tall bars have no room for a label above them, so the value
                # moves inside the bar rather than off the top of the strip.
                lab_y = base_y - bh - 10
                if lab_y < y + 6:
                    # No room above: drop the value inside the bar. Keep it off
                    # pure white so it reads against the accent fill.
                    lab_y = base_y - bh + 14
                    lab_col = theme.BG if sel else theme.TEXT_2
                else:
                    lab_col = theme.TEXT if sel else theme.TEXT_3
                self.canvas.create_text(bx + bw / 2, lab_y, text=f"{cv:.0f}",
                                        fill=lab_col, font=(theme.ui_font(), 9),
                                        anchor="center")
                lbl = f"#{n - len(recent) + i + 1}"
                self.canvas.create_text(bx + bw / 2, base_y + 13, text=lbl,
                                        fill=theme.TEXT if sel else theme.TEXT_3,
                                        font=(theme.ui_font(), 8), anchor="center")

        # session summary card sits to the right of the bars
        sm_x = x0 + bars_w + 24
        sm_y1, sm_y2 = y - 4, y + recent_h - 14
        self.canvas.create_rectangle(sm_x, sm_y1, x1, sm_y2,
                                     fill=theme.SURFACE, outline="")
        self.canvas.create_text(sm_x + 18, sm_y1 + 16, text="SESSION",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="w")
        self.canvas.create_text(x1 - 18, sm_y1 + 16, text=f"{n} shots",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="e")

        avgs = self.calculate_session_averages()
        disp = self._session_dispersion_yds()
        sm = [("AVG CARRY", f"{avgs.get('carry', 0.0):.1f}" if avgs else "--", "yds"),
              ("BEST", f"{max(carries):.1f}" if carries else "--", "yds"),
              ("DISPERSION", f"{disp:.1f}" if disp is not None else "--", "yds")]

        # Fill the box rather than clustering in its top third: the value row
        # is centred in the space under the title, and the type scales with
        # the box so a taller card gets bigger numbers, not more blank space.
        body_top = sm_y1 + 30
        body_h = sm_y2 - body_top
        val_size = int(max(21, min(46, body_h * 0.42)))
        lab_y = body_top + body_h * 0.30
        val_y = body_top + body_h * 0.62

        inner = (x1 - sm_x - 36) / len(sm)
        for i, (lb, v, u) in enumerate(sm):
            cxp = sm_x + 18 + i * inner
            self.canvas.create_text(cxp, lab_y, text=lb, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="w")
            vid2 = self.canvas.create_text(cxp, val_y, text=v, fill=theme.TEXT,
                                           font=(theme.ui_font(), val_size),
                                           anchor="w")
            bb2 = self.canvas.bbox(vid2)
            if bb2:
                self.canvas.create_text(bb2[2] + 6, val_y + val_size * 0.28,
                                        text=u, fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 9), anchor="w")
        y += recent_h + 2

        # ---- bottom band: dispersion + tendencies --------------------------
        bb_h = max(120, h - y - 14)
        dw = (x1 - x0) * 0.30
        self._draw_overview_dispersion(x0, y, dw, bb_h)
        self._draw_overview_tendencies(x0 + dw + 16, y, x1 - (x0 + dw + 16),
                                       bb_h)



    def _session_dispersion_yds(self):
        """Std-dev of offline distance across the session, in yards."""
        offs = []
        for s in self.session_shots:
            if s.get("excluded"):
                continue
            us = (self.aim_corrected(s).get("open_golf_coach", {}) or {}).get("us_customary_units", {}) or {}
            v = us.get("offline_distance_yards")
            if v is not None:
                offs.append(float(v))
        if len(offs) < 2:
            return None
        mean = sum(offs) / len(offs)
        return (sum((o - mean) ** 2 for o in offs) / len(offs)) ** 0.5

    def _draw_overview_face(self, cx, cy, size):
        """Small clubface with the estimated strike marker."""
        img = self.get_scaled_club_asset(FACE_PATH, int(size),
                                         mirror=self.is_left_handed)
        if img:
            self.canvas.create_image(cx, cy, image=img, anchor="c")
        else:
            half = size / 2
            self.canvas.create_rectangle(cx - half * 0.7, cy - half,
                                         cx + half * 0.7, cy + half,
                                         fill=theme.SURFACE_2, outline="")

        # Sweet spot: same groove-centre offsets the quad studio uses
        # (-43.5, -40.0 px on a 290x220 asset), mirrored for LH.
        sdx = (43.5 / 220.0) * size * (1 if self.is_left_handed else -1)
        sdy = (-40.0 / 220.0) * size
        ssx, ssy = cx + sdx, cy + sdy
        for d in (-6, -3, 3, 6):
            self.canvas.create_line(ssx + d, ssy, ssx + d + 2, ssy,
                                    fill=theme.GUIDE)
            self.canvas.create_line(ssx, ssy + d, ssx, ssy + d + 2,
                                    fill=theme.GUIDE)

        head, _, hcol = self.summarize_strike(self.current_shot)
        dy = 0.0
        if "Low" in head:
            dy = size * 0.14
        elif "High" in head:
            dy = -size * 0.14
        mx_, my_ = ssx + size * 0.05, ssy + dy
        r = size * 0.13
        for a in range(0, 360, 12):
            a1 = math.radians(a)
            a2 = math.radians(a + 6)
            self.canvas.create_line(mx_ + r * math.cos(a1), my_ + r * math.sin(a1),
                                    mx_ + r * math.cos(a2), my_ + r * math.sin(a2),
                                    fill=hcol, width=2)
        self.canvas.create_oval(mx_ - 3, my_ - 3, mx_ + 3, my_ + 3,
                                fill=hcol, outline="")

    def _draw_overview_dispersion(self, x, y, w, hh):
        """Scatter of the session's landing points, left/right vs distance."""
        self.canvas.create_rectangle(x, y, x + w, y + hh,
                                     fill=theme.SURFACE, outline="")
        self.canvas.create_text(x + 16, y + 15, text="DISPERSION",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="w")
        pts = []
        for s in self.session_shots[-20:]:
            if s.get("excluded"):
                continue
            us = (self.aim_corrected(s).get("open_golf_coach", {}) or {}).get("us_customary_units", {}) or {}
            off = us.get("offline_distance_yards")
            car = us.get("carry_distance_yards")
            if off is None or car is None:
                continue
            pts.append((float(off), float(car), s is self.current_shot))
        self.canvas.create_text(x + w - 16, y + 15, text=f"last {len(pts)}",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="e")
        if not pts:
            return

        # Keep the axis labels INSIDE the panel: py2 must leave room for the
        # L / R row beneath it, or the scatter runs off the bottom edge.
        px1, py1 = x + 20, y + 34
        px2, py2 = x + w - 20, y + hh - 26
        cx = (px1 + px2) / 2
        max_off = max(6.0, max(abs(p[0]) for p in pts) * 1.25)
        cars = [p[1] for p in pts]
        lo, hi = min(cars), max(cars)
        span = max(1.0, hi - lo)

        # centre line and L / R markers
        for dash_y in range(int(py1), int(py2), 6):
            self.canvas.create_line(cx, dash_y, cx, dash_y + 3, fill=theme.GUIDE)
        self.canvas.create_text(cx - w * 0.22, py2 + 13, text="L",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8))
        self.canvas.create_text(cx + w * 0.22, py2 + 13, text="R",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8))

        for off, car, sel in pts:
            dx = cx + (off / max_off) * ((px2 - px1) / 2)
            dy = py2 - ((car - lo) / span) * (py2 - py1)
            r = 5 if sel else 3
            self.canvas.create_oval(dx - r, dy - r, dx + r, dy + r,
                                    fill=theme.ACCENT if sel else theme.SURFACE_2,
                                    outline=theme.ACCENT_LINE if sel else "")

    def _draw_overview_tendencies(self, x, y, w, hh):
        """Session-level patterns -- what keeps happening, not one shot.

        Each row is scored only from data the Nova actually measures, and a
        row with too few usable shots reports that rather than drawing a bar
        at an arbitrary position.
        """
        self.canvas.create_rectangle(x, y, x + w, y + hh,
                                     fill=theme.SURFACE, outline="")
        self.canvas.create_text(x + 16, y + 15, text="TENDENCIES",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="w")

        shots = [s for s in self.session_shots if not s.get("excluded")]
        rows = []

        # 1. strike height, from launch deviation vs the club's loft
        devs = []
        for s in shots:
            club = s.get("club") or self.current_club
            c = self.get_bag_club(club) or {}
            loft = float(c.get("loft_deg") or 0.0)
            vla = s.get("vertical_launch_angle_degrees")
            if loft > 0 and vla is not None:
                base = 2.0 if "Putter" in club else loft * 0.68
                devs.append(float(vla) - base)
        if devs:
            mean_dev = sum(devs) / len(devs)
            frac = max(0.0, min(1.0, 0.5 + mean_dev / 20.0))
            verdict = "low" if mean_dev < -2 else ("high" if mean_dev > 2 else "centred")
            col = theme.WARN if verdict != "centred" else theme.ACCENT_LINE
            rows.append(("Strike height", frac, verdict, col))
        else:
            rows.append(("Strike height", None, "no loft data", theme.TEXT_3))

        # 2. face control, from spin-axis consistency
        axes = [abs(float(((s.get("open_golf_coach", {}) or {}).get("spin_axis_degrees") or 0.0)))
                for s in shots if (s.get("open_golf_coach", {}) or {}).get("spin_axis_degrees") is not None]
        if len(axes) >= 3:
            mean_ax = sum(axes) / len(axes)
            frac = max(0.05, min(1.0, 1.0 - mean_ax / 25.0))
            verdict = "good" if mean_ax < 8 else ("fair" if mean_ax < 15 else "loose")
            col = theme.ACCENT_LINE if verdict == "good" else theme.WARN
            rows.append(("Face control", frac, verdict, col))
        else:
            rows.append(("Face control", None, "needs 3+ shots", theme.TEXT_3))

        # 3. path consistency, from the spread of club path
        paths = []
        for s in shots:
            v = self.resolve_handed((s.get("open_golf_coach", {}) or {}).get("club_path_degrees"), None)
            if v is not None:
                paths.append(float(v))
        if len(paths) >= 3:
            m = sum(paths) / len(paths)
            sd = (sum((p - m) ** 2 for p in paths) / len(paths)) ** 0.5
            frac = max(0.05, min(1.0, 1.0 - sd / 10.0))
            verdict = "good" if sd < 3 else ("fair" if sd < 6 else "variable")
            col = theme.ACCENT_LINE if verdict == "good" else theme.WARN
            rows.append(("Path consistency", frac, verdict, col))
        else:
            rows.append(("Path consistency", None, "needs 3+ shots", theme.TEXT_3))

        bar_x1 = x + 150
        bar_x2 = x + w - 90
        top = y + 40
        step = max(20, (hh - 52) / len(rows))
        for i, (label, frac, verdict, col) in enumerate(rows):
            ry = top + i * step + step / 2
            self.canvas.create_text(x + 16, ry, text=label, fill=theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="w")
            self.canvas.create_line(bar_x1, ry, bar_x2, ry,
                                    fill=theme.SURFACE_2, width=6)
            if frac is not None:
                self.canvas.create_line(bar_x1, ry,
                                        bar_x1 + (bar_x2 - bar_x1) * frac, ry,
                                        fill=col, width=6)
            self.canvas.create_text(x + w - 16, ry, text=verdict, fill=col,
                                    font=(theme.ui_font(), 8), anchor="e")

    def summarize_strike(self, shot):
        """Plain-language strike direction for the current shot.

        Reuses the same launch-deviation signal the quad studio plots, but
        returns text rather than drawing, so Overview can show a verdict
        without duplicating the estimator.

        Returns (headline, detail, colour).
        """
        if not shot:
            return ("No shot", "", theme.TEXT_3)

        club = shot.get("club") or self.current_club
        vla = float(shot.get("vertical_launch_angle_degrees") or 0.0)

        c = self.get_bag_club(club) or {}
        loft = float(c.get("loft_deg") or 0.0)
        if loft > 0:
            base_launch = 2.0 if "Putter" in club else loft * 0.68
        else:
            base_launch = 21.0

        clamped = self.compute_smash_confidence(
            shot.get("ball_speed_meters_per_second"),
            shot.get("vertical_launch_angle_degrees"),
            shot.get("total_spin_rpm"),
        )["clamped"]

        dev = vla - base_launch
        if abs(dev) < 1.0:
            return ("Centre strike", "launch matches this club's loft",
                    theme.ACCENT_TEXT)

        side = "High on face" if dev > 0 else "Low on face"
        detail = ("direction only — no club-speed data" if clamped
                  else f"{abs(dev):.1f}° from expected launch")
        return (side, detail, theme.WARN)

    def draw_4_quadrant_studio(self, avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, apex_yds, descent, opt_max, eff_pct, shot_name, shot_rank, smash, ball_speed=0.0, offset_x=0, top_bar_h=108):
        if isinstance(shot_rank, dict):
            shot_rank = shot_rank.get("left_handed" if self.is_left_handed else "right_handed", shot_rank.get("right_handed", "A"))
        shot_rank = str(shot_rank or "A")

        if isinstance(shot_name, dict):
            shot_name = shot_name.get("left_handed" if self.is_left_handed else "right_handed", shot_name.get("right_handed", "Straight"))
        shot_name = str(shot_name or "Straight")

        avail_h = h - top_bar_h - 10
        quad_w = avail_w // 2
        quad_h = avail_h // 2
        mid_x = offset_x + quad_w
        mid_y = top_bar_h + quad_h

        # Dynamic responsive scale based on quadrant dimensions (fills empty space on large displays)
        scale = max(0.85, min(2.5, min(quad_w / 380.0, quad_h / 230.0)))
        font_scale = max(0.85, min(1.85, scale))

        self.canvas.create_line(mid_x, top_bar_h, mid_x, h - 10, fill=theme.HAIRLINE, width=2)
        self.canvas.create_line(offset_x, mid_y, offset_x + avail_w, mid_y, fill=theme.HAIRLINE, width=2)

        # Inspection Banner Header
        if 0 <= self.selected_shot_index < len(self.session_shots):
            # Shot position is already stated in the footer; a centred banner
            # here collided with the panel captions.
            pass

        # Quadrant 1 (Top-Left): Overhead View
        q1_cx, q1_cy = offset_x + (quad_w // 2), top_bar_h + (quad_h // 2)
        q1_top = top_bar_h
        q1_bot = mid_y

        # Panel annotations follow the mockup: a small quiet caption with the
        # value beneath it, anchored to the panel gutter -- not a centred
        # "Label: Value" headline in monospace.
        cap_f = (theme.ui_font(), max(7, int(8 * font_scale)))
        val_f = (theme.ui_font(), max(9, int(12 * font_scale)))

        # Anchor the pair from its TOP ("nw"/"ne") rather than its vertical
        # centre ("w"/"e"). With centre anchoring the gap has to cover half of
        # each item's height, which forces the caption and value apart; the
        # concept has them tight, as one unit. Top-anchoring makes the gap
        # simply the caption's line height.
        try:
            import tkinter.font as _tkf
            _cap_line = _tkf.Font(family=cap_f[0], size=cap_f[1]).metrics("linespace")
        except Exception:
            _cap_line = int(cap_f[1] * 1.4)
        try:
            _val_line = _tkf.Font(family=val_f[0], size=val_f[1]).metrics("linespace")
        except Exception:
            _val_line = int(val_f[1] * 1.4)
        annot_gap = _cap_line + 1
        # Height of one caption+value unit, for stacking consecutive pairs.
        pair_h = annot_gap + _val_line

        def annot(ax, ay, cap, val, anchor="w", col=None):
            a = "ne" if anchor == "e" else "nw"
            self.canvas.create_text(ax, ay, text=cap, fill=theme.TEXT_3,
                                    font=cap_f, anchor=a)
            self.canvas.create_text(ax, ay + annot_gap, text=val,
                                    fill=col or theme.TEXT, font=val_f,
                                    anchor=a)

        def panel_cap(px, py, text, tag=None, tag_col=None):
            cid = self.canvas.create_text(px, py, text=text, fill=theme.TEXT_3,
                                          font=cap_f, anchor="w")
            if tag:
                # Measure, do not estimate from character count -- that
                # under-counts on a proportional face and the tag lands on
                # top of the caption.
                cbb = self.canvas.bbox(cid)
                tx = (cbb[2] + int(14 * font_scale)) if cbb else (
                    px + int(len(text) * 6.2 * font_scale) + 14)
                self.canvas.create_text(tx, py, text=tag,
                                        fill=tag_col or theme.TEXT_3,
                                        font=cap_f, anchor="w")

        gut_l = offset_x + int(18 * font_scale)          # left gutter
        gut_r = offset_x + quad_w - int(18 * font_scale)  # right gutter of col 1

        panel_cap(gut_l, q1_top + int(16 * font_scale), "CLUB PATH & FACE")
        self.canvas.create_text(gut_r, q1_top + int(16 * font_scale),
                                text="DERIVED", fill=theme.TEXT_3,
                                font=cap_f, anchor="e")

        path_val = f"{abs(club_path):.1f}° " + (
            ("in-to-out" if club_path < 0 else "out-to-in") if self.is_left_handed
            else ("in-to-out" if club_path > 0 else "out-to-in"))
        annot(gut_l, q1_top + int(34 * font_scale), "CLUB PATH", path_val)
        self.canvas.create_line(q1_cx - int(150 * scale), q1_cy, q1_cx + int(150 * scale), q1_cy, fill=theme.GUIDE, width=1, dash=(4, 4))
        
        overhead_h = int(140 * scale)
        ov_img = self.get_rotated_overhead_asset(overhead_h, face_to_target, mirror=self.is_left_handed)
        if ov_img:
            self.canvas.create_image(q1_cx, q1_cy, image=ov_img, anchor="c")

        path_rad = math.radians(club_path)
        arrow_len = int(75 * scale)
        px1, py1 = self.rotate_point(q1_cx, q1_cy + arrow_len, q1_cx, q1_cy, path_rad)
        px2, py2 = self.rotate_point(q1_cx, q1_cy - arrow_len, q1_cx, q1_cy, path_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill=theme.ACCENT_TEXT, width=max(3, int(3.5 * scale)), arrow=tk.LAST, arrowshape=(int(12 * scale), int(15 * scale), int(5 * scale)))

        ball_offset_x = int(-50 * scale) if self.is_left_handed else int(50 * scale)
        ball_r = int(9 * scale)
        self.canvas.create_oval(q1_cx + ball_offset_x - ball_r, q1_cy - ball_r, q1_cx + ball_offset_x + ball_r, q1_cy + ball_r, fill=theme.TEXT, outline=theme.TEXT_2)

        # Keep clear of the next panel's caption: the value sits ~22px below
        # its own y, so the last row needs that much clearance from q1_bot.
        face_y = q1_bot - pair_h * 2 - int(14 * font_scale)
        annot(gut_l, face_y, "FACE TO PATH",
              f"{abs(face_to_path):.1f}° {'open' if face_to_path > 0 else 'closed'}")
        annot(gut_l, face_y + pair_h, "FACE TO TARGET",
              f"{abs(face_to_target):.1f}° {'open' if face_to_target > 0 else 'closed'}")
        annot(gut_r, q1_cy + int(12 * font_scale), "SIDESPIN",
              f"{int(abs(sidespin))} rpm", anchor="e")

        # Quadrant 2 (Bottom-Left): Trajectory Arc
        q2_cx, q2_cy = offset_x + (quad_w // 2), mid_y + (quad_h // 2)
        q2_top = mid_y
        q2_bot = h - 10
        ground_y = q2_cy + int(36 * scale)


        panel_cap(gut_l, q2_top + int(16 * font_scale), "LAUNCH & LOFT")
        annot(gut_l, q2_top + int(34 * font_scale), "LAUNCH ANGLE",
              f"{vert_launch:.1f}°")
        _c = self.get_bag_club((self.current_shot or {}).get("club") or self.current_club) or {}
        _lf = float(_c.get("loft_deg") or 0.0)
        if _lf > 0:
            annot(gut_l, q2_top + int(34 * font_scale) + pair_h, "STATIC LOFT",
                  f"{_lf:.1f}°")
        self.canvas.create_line(q2_cx - int(160 * scale), ground_y, q2_cx + int(160 * scale), ground_y, fill=theme.GUIDE, width=2, dash=(4, 4))
        
        side_h = int(115 * scale)
        side_offset_x = int(95 * scale)
        side_img = self.get_scaled_club_asset(SIDE_PATH, side_h, mirror=False)
        if side_img:
            self.canvas.create_image(q2_cx - side_offset_x, ground_y - int(24 * scale), image=side_img, anchor="c")

        arc_span = int(240 * scale)
        arc_pts = []
        for t in range(0, 101, 4):
            frac = t / 100.0
            x_p = (q2_cx - side_offset_x) + int(arc_span * frac)
            h_p = math.sin(frac * math.pi) * min(int(70 * scale), int(apex_yds * 16 * scale))
            y_p = ground_y - int(h_p)
            arc_pts.extend([x_p, y_p])
        
        self.canvas.create_line(arc_pts, fill=theme.ACCENT_TEXT, width=max(3, int(3.5 * scale)), smooth=True)
        ball_r2 = int(7 * scale)
        self.canvas.create_oval(q2_cx - side_offset_x - ball_r2, ground_y - ball_r2, q2_cx - side_offset_x + ball_r2, ground_y + ball_r2, fill=theme.TEXT)

        annot(gut_r, q2_top + int(34 * font_scale), "BACKSPIN",
              f"{int(backspin)} rpm", anchor="e")
        annot(gut_r, q2_bot - pair_h - int(14 * font_scale), "DESCENT",
              f"{descent:.1f}°", anchor="e")
        # The Nova measures ball flight only -- say so rather than leave a gap.
        self.canvas.create_text(gut_l, q2_bot - int(14 * font_scale),
                                text="Attack angle not measured",
                                fill=theme.TEXT_3, font=cap_f, anchor="w")

        # Quadrant 3 (Top-Right): 3D Spin Axis
        q3_cx, q3_cy = offset_x + (3 * quad_w // 2), top_bar_h + (quad_h // 2)
        q3_top = top_bar_h
        q3_bot = mid_y
        
        gut_l3 = offset_x + quad_w + int(18 * font_scale)
        gut_r3 = offset_x + avail_w - int(18 * font_scale)
        panel_cap(gut_l3, q3_top + int(16 * font_scale), "SPIN")
        # Shot shape sits above the ball, not in a coloured grade pill.
        self.canvas.create_text(q3_cx, q3_top + int(30 * font_scale),
                                text=shot_name, fill=theme.ACCENT_TEXT,
                                font=(theme.ui_font(), max(10, int(12 * font_scale))),
                                anchor="center")
        
        # (grade pill and duplicated shape label removed -- the shape is drawn
        # above the ball and the grade is not part of the mockup)

        ball_r3 = int(30 * scale)
        self.canvas.create_oval(q3_cx - ball_r3, q3_cy - ball_r3, q3_cx + ball_r3, q3_cy + ball_r3, fill=theme.TEXT, outline=theme.TEXT_2, width=2)
        
        axis_rad = math.radians(spin_axis)
        spin_len = int(46 * scale)
        ax1, ay1 = self.rotate_point(q3_cx, q3_cy + spin_len, q3_cx, q3_cy, axis_rad)
        ax2, ay2 = self.rotate_point(q3_cx, q3_cy - spin_len, q3_cx, q3_cy, axis_rad)
        self.canvas.create_line(ax1, ay1, ax2, ay2, fill=theme.ACCENT_LINE, width=max(4, int(4.5 * scale)), arrow=tk.LAST, arrowshape=(int(14 * scale), int(18 * scale), int(6 * scale)))


        annot(gut_l3, q3_cy - int(34 * font_scale), "SPIN AXIS",
              f"{abs(spin_axis):.1f}° {'right' if spin_axis > 0 else 'left'}")
        spin_y = q3_bot - pair_h * 2 - int(14 * font_scale)
        annot(gut_r3, spin_y, "TOTAL SPIN",
              f"{int(total_spin)} rpm", anchor="e")
        annot(gut_r3, spin_y + pair_h, "BACKSPIN",
              f"{int(backspin)} rpm", anchor="e")

        # Quadrant 4 (Bottom-Right): High-Precision Face Impact Location & Strike Coordinates
        q4_cx, q4_cy = offset_x + (3 * quad_w // 2), mid_y + (quad_h // 2)
        q4_top = mid_y
        q4_bot = h - 10

        # --- Strike estimation ---
        # The Nova / OpenGolfCoach payload carries NO measured face-impact
        # location. If a future firmware adds one we use it verbatim
        # ("measured"); otherwise we build an honest ESTIMATE:
        #   * MAGNITUDE from smash-factor deficit vs. the club's max
        #     achievable smash (energy loss on off-center strikes is real,
        #     well-documented physics).
        #   * DIRECTION as a low-confidence hint from gear-effect residuals
        #     (sidespin not explained by face-to-path; launch/spin deviation
        #     from club-typical for high/low face).
        shot_obj = self.current_shot or {}
        ogc = shot_obj.get("open_golf_coach", {}) if isinstance(shot_obj, dict) else {}
        impact_data = (
            shot_obj.get("face_impact") or
            shot_obj.get("impact_location") or
            ogc.get("face_impact") or
            ogc.get("impact_location") or
            ogc.get("face_contact") or {}
        )

        measured = False
        h_impact_mm = 0.0
        v_impact_mm = 0.0
        smash_deficit = 0.0
        est_offset_mm = 0.0
        if isinstance(impact_data, dict) and impact_data:
            for key in ("lateral_offset_mm", "heel_toe_mm", "horizontal_offset_mm", "x_mm"):
                if key in impact_data:
                    h_impact_mm = float(impact_data[key])
                    measured = True
                    break
            for key in ("vertical_offset_mm", "high_low_mm", "y_mm"):
                if key in impact_data:
                    v_impact_mm = float(impact_data[key])
                    measured = True
                    break

        # Club specs must come from the SHOT being displayed, not from whatever
        # is selected in the dropdown right now. Reviewing shot history, or
        # changing club after a shot, would otherwise re-score old shots against
        # the wrong loft and silently flip their strike verdict.
        strike_club = (shot_obj.get("club") if isinstance(shot_obj, dict) else None) or self.current_club

        if not measured:
            # 1) Magnitude from smash deficit.
            #
            # CAUTION: this is only meaningful when OGC's clubhead-speed model
            # is NOT saturated. When the effective-COR clamp engages (common
            # below ~90 mph ball speed) smash_factor is a constant, so this
            # yields the SAME offset for every shot with a given club -- a
            # fabricated number, not an estimate. compute_smash_confidence()
            # detects that case and we suppress the magnitude entirely.
            club_max_smash = {
                "Driver": 1.50, "3 Wood": 1.48, "5 Wood": 1.47, "3 Hybrid": 1.46,
                "4 Iron": 1.43, "5 Iron": 1.41, "6 Iron": 1.39, "7 Iron": 1.37,
                "8 Iron": 1.34, "9 Iron": 1.31, "PW": 1.27, "GW": 1.24,
                "SW": 1.21, "LW": 1.18
            }
            max_smash = club_max_smash.get(strike_club, 1.37)
            smash_val = float(smash or 0.0)
            if smash_val <= 0.0:
                smash_val = max_smash
            smash_conf = self.compute_smash_confidence(
                shot_obj.get("ball_speed_meters_per_second"),
                shot_obj.get("vertical_launch_angle_degrees"),
                shot_obj.get("total_spin_rpm"),
            )
            magnitude_known = not smash_conf["clamped"]
            if magnitude_known:
                smash_deficit = max(0.0, min(0.35, max_smash - smash_val))
                # ~0.01 smash lost per mm off-center near the sweet spot
                est_offset_mm = min(20.0, smash_deficit * 100.0)
            else:
                smash_deficit = 0.0
                est_offset_mm = 0.0

            # 2) Direction hints from gear-effect residuals (low confidence)
            club_baselines = {
                "Driver": 11.5, "3 Wood": 13.0, "5 Wood": 14.5, "3 Hybrid": 16.0,
                "4 Iron": 16.5, "5 Iron": 17.5, "6 Iron": 19.0, "7 Iron": 21.0,
                "8 Iron": 23.5, "9 Iron": 26.5, "PW": 29.0, "GW": 32.0,
                "SW": 35.0, "LW": 38.0
            }
            club_spin_baselines = {
                "Driver": 2700, "3 Wood": 3600, "5 Wood": 4300, "3 Hybrid": 4800,
                "4 Iron": 4800, "5 Iron": 5300, "6 Iron": 6200, "7 Iron": 7000,
                "8 Iron": 7800, "9 Iron": 8500, "PW": 9300, "GW": 10000,
                "SW": 10500, "LW": 11000
            }
            club_speed_baselines = {
                "Driver": 160.0, "3 Wood": 150.0, "5 Wood": 140.0, "3 Hybrid": 130.0,
                "4 Iron": 125.0, "5 Iron": 120.0, "6 Iron": 115.0, "7 Iron": 105.0,
                "8 Iron": 95.0, "9 Iron": 90.0, "PW": 85.0, "GW": 80.0,
                "SW": 75.0, "LW": 70.0
            }
            # Dynamic baseline launch angle from club's configured loft in My Bag (Mitchell standards fallback)
            configured_loft = None
            for c in getattr(self, "bag", []):
                if isinstance(c, dict) and c.get("name") == strike_club:
                    configured_loft = c.get("loft_deg")
                    break
            if configured_loft and float(configured_loft) > 0:
                c_loft = float(configured_loft)
                if strike_club in ("Driver", "3 Wood", "5 Wood", "7 Wood"):
                    base_launch = c_loft * 1.10
                elif "Hybrid" in strike_club:
                    base_launch = c_loft * 0.82
                elif "Putter" in strike_club:
                    base_launch = 2.0
                else:
                    # Irons & Wedges: forward shaft lean delofting delivers ~68% of static loft launch angle
                    base_launch = c_loft * 0.68
            else:
                base_launch = club_baselines.get(strike_club, 21.0)

            base_spin = club_spin_baselines.get(strike_club, 7000)
            full_speed = club_speed_baselines.get(strike_club, 105.0)

            # Scale expected baseline spin and sidespin by swing speed ratio so partial swings don't falsely skew
            ball_spd = float(ball_speed or 0.0)
            if ball_spd <= 0.0 and self.current_shot:
                ogc_s = self.current_shot.get("open_golf_coach", {}) if isinstance(self.current_shot, dict) else {}
                us_s = ogc_s.get("us_customary_units", {}) if isinstance(ogc_s, dict) else {}
                ball_spd = float(us_s.get("ball_speed_mph", 0.0) or (self.current_shot.get("ball_speed_meters_per_second", 0.0) * 2.23694 if isinstance(self.current_shot, dict) else 0.0))
            speed_ratio = max(0.2, min(1.3, ball_spd / full_speed)) if ball_spd > 0 else 1.0
            expected_spin = base_spin * speed_ratio

            # Horizontal: sidespin beyond what face-to-path predicts.
            # For RH: open face (+f2p) → fade (+sidespin); heel gear-effect
            # adds fade spin, toe adds draw spin. Mirrored for LH.
            hand_sign = -1.0 if self.is_left_handed else 1.0
            expected_side = hand_sign * face_to_path * 150.0 * speed_ratio
            side_residual = (sidespin - expected_side) * hand_sign
            h_hint = max(-1.0, min(1.0, side_residual / (400.0 * speed_ratio)))  # + = heel, - = toe

            # Vertical: Launch deviation is the primary physical indicator of strike height.
            # On flat-faced irons, low-face/thin/bladed shots launch low (e.g. worm burners); high hits launch higher.
            # On drivers/woods with roll curvature, vertical gear effect also reduces backspin on high strikes.
            launch_dev = (vert_launch - base_launch) / 5.0
            is_wood = strike_club in ("Driver", "3 Wood", "5 Wood", "3 Hybrid")
            if is_wood:
                spin_dev = (backspin - expected_spin) / (1000.0 * speed_ratio)
                v_hint = (launch_dev * 0.7) - (spin_dev * 0.3)
            else:
                # Irons/wedges: flat face means launch angle directly determines vertical contact point
                v_hint = launch_dev
            v_hint = max(-1.0, min(1.0, v_hint))

            hint_mag = math.sqrt(h_hint**2 + v_hint**2)
            # Direction is independent of magnitude: launch-angle deviation is a
            # genuinely measured signal even when smash (and therefore the mm
            # offset) is unavailable. Only require a usable magnitude when we
            # actually have one to scale by.
            dir_known = hint_mag >= 0.15 and (est_offset_mm >= 2.0 or not magnitude_known)
            if dir_known and magnitude_known:
                h_impact_mm = (h_hint / hint_mag) * est_offset_mm
                v_impact_mm = (v_hint / hint_mag) * est_offset_mm
            elif dir_known:
                # Direction only. Plot at a fixed nominal radius so the face
                # graphic still shows WHERE, while the text omits any mm value.
                nominal = 6.0
                h_impact_mm = (h_hint / hint_mag) * nominal
                v_impact_mm = (v_hint / hint_mag) * nominal
            else:
                h_impact_mm = 0.0
                v_impact_mm = 0.0
        else:
            dir_known = True
            magnitude_known = True

        # Clamp offsets to physical face dimensions
        h_impact_mm = max(-24.0, min(24.0, h_impact_mm))
        v_impact_mm = max(-16.0, min(16.0, v_impact_mm))
        total_offset_mm = math.sqrt(h_impact_mm**2 + v_impact_mm**2)
        if not measured:
            if not dir_known:
                total_offset_mm = est_offset_mm

        # Coordinate Tags & Strike Tier Styling
        est_tag = "" if measured else " (EST)"
        if measured:
            def fmt_mm(val):
                return f"{abs(val):.1f} mm"
        elif magnitude_known:
            def fmt_mm(val):
                return f"~{abs(val):.0f} mm"
        else:
            # No usable magnitude -- report direction only, never a mm figure.
            def fmt_mm(val):
                return ""

        if not dir_known and not measured:
            h_text = "↔ DIR UNKNOWN"
            h_badge_col = theme.TEXT_2
        elif abs(h_impact_mm) < 1.0:
            h_text = f"↔ CENTER{est_tag}"
            h_badge_col = theme.ACCENT_TEXT
        else:
            h_side = "HEEL" if h_impact_mm > 0 else "TOE"
            if magnitude_known:
                h_text = f"↔ {fmt_mm(h_impact_mm)} {h_side}{est_tag}"
                h_badge_col = theme.DANGER if abs(h_impact_mm) > 8.0 else (theme.WARN if abs(h_impact_mm) > 3.0 else theme.ACCENT_TEXT)
            else:
                # Direction-only: readable amber, uncertainty lives in the label.
                h_text = f"↔ {h_side}{est_tag}"
                h_badge_col = "#FF9100"

        if not dir_known and not measured:
            v_text = "↕ DIR UNKNOWN"
            v_badge_col = theme.TEXT_2
        elif abs(v_impact_mm) < 1.0:
            v_text = f"↕ FLUSH{est_tag}"
            v_badge_col = theme.ACCENT_TEXT
        else:
            v_side = "HIGH" if v_impact_mm > 0 else "LOW"
            if magnitude_known:
                v_text = f"↕ {fmt_mm(v_impact_mm)} {v_side}{est_tag}"
                v_badge_col = theme.DANGER if abs(v_impact_mm) > 6.0 else (theme.WARN if abs(v_impact_mm) > 2.5 else theme.ACCENT_TEXT)
            else:
                v_text = f"↕ {v_side}{est_tag}"
                v_badge_col = "#FF9100"

        if not measured and not magnitude_known:
            # Direction-only: never imply a severity tier we cannot compute.
            if dir_known:
                h_part = "HEEL" if h_impact_mm > 1.5 else ("TOE" if h_impact_mm < -1.5 else "")
                v_part = "HIGH" if v_impact_mm > 1.5 else ("THIN" if v_impact_mm < -1.5 else "")
                strike_rank = f"{h_part} {v_part}".strip() or "OFF-CENTER"
                # Direction IS a real signal (launch-angle derived) -- keep it
                # clearly readable. The "DIR EST" tag carries the uncertainty,
                # so the marker itself doesn't need to be dimmed.
                strike_color = "#FF9100"
            else:
                strike_rank = "STRIKE UNKNOWN"
                strike_color = theme.TEXT_2
        elif total_offset_mm < 3.0:
            strike_rank = "CENTER FLUSH"
            strike_color = theme.ACCENT_TEXT
        elif not dir_known and not measured:
            strike_rank = "OFF-CENTER (DIR ?)"
            strike_color = theme.WARN if total_offset_mm < 8.0 else theme.DANGER
        elif total_offset_mm < 8.0:
            h_part = "HEEL" if h_impact_mm > 1.5 else ("TOE" if h_impact_mm < -1.5 else "")
            v_part = "HIGH" if v_impact_mm > 1.5 else ("THIN" if v_impact_mm < -1.5 else "")
            strike_rank = f"{h_part} {v_part}".strip() or "OFF-CENTER"
            strike_color = theme.WARN
        else:
            h_part = "EXTREME HEEL" if h_impact_mm > 0 else "EXTREME TOE"
            v_part = "HIGH" if v_impact_mm > 2.5 else ("THIN" if v_impact_mm < -2.5 else "")
            strike_rank = f"{h_part} {v_part}".strip()
            strike_color = theme.DANGER
        # The "~" prefix denotes an approximate MAGNITUDE; skip it when we only
        # have a direction (and for the explicit unknown states).
        if (not measured and magnitude_known and strike_rank != "CENTER FLUSH"
                and "(DIR ?)" not in strike_rank and strike_rank != "STRIKE UNKNOWN"):
            strike_rank = f"~{strike_rank}"

        # Caption + ESTIMATE chip, then the two readings as gutter
        # annotations -- the mockup has no outlined pills here.
        gut_l4 = offset_x + quad_w + int(18 * font_scale)
        cap_y4 = q4_top + int(16 * font_scale)
        # Measure the caption rather than assuming its width: a fixed offset
        # overlaps once the font or scale changes.
        cap_id4 = self.canvas.create_text(gut_l4, cap_y4,
                                          text="IMPACT LOCATION",
                                          fill=theme.TEXT_3, font=cap_f,
                                          anchor="w")
        cap_bb4 = self.canvas.bbox(cap_id4)
        chip_x = (cap_bb4[2] + int(12 * font_scale)) if cap_bb4 else (
            gut_l4 + int(110 * font_scale))
        chip_f = (theme.ui_font(), max(7, int(8 * font_scale)), "bold")
        chip_id = self.canvas.create_text(chip_x + int(9 * font_scale), cap_y4,
                                          text="ESTIMATE", fill=theme.WARN,
                                          font=chip_f, anchor="w")
        chip_bb = self.canvas.bbox(chip_id)
        if chip_bb:
            self.canvas.create_rectangle(chip_x, chip_bb[1] - int(4 * font_scale),
                                         chip_bb[2] + int(9 * font_scale),
                                         chip_bb[3] + int(4 * font_scale),
                                         fill="#2A2118", outline="")
            self.canvas.tag_raise(chip_id)

        imp_y = q4_top + int(34 * font_scale)
        annot(gut_l4, imp_y, "VERTICAL",
              v_text.split(" ", 1)[-1] if " " in v_text else v_text,
              col=v_badge_col)
        annot(gut_l4, imp_y + pair_h, "HORIZONTAL",
              h_text.split(" ", 1)[-1] if " " in h_text else h_text,
              col=h_badge_col)

        # Clubface Graphic
        # Raw iron_face.png: toe on LEFT (x: 36..167 are grooves), hosel on RIGHT (x: 180..290)
        # For LH: mirror the image so hosel moves to LEFT, toe to RIGHT
        face_h = int(130 * scale)
        face_img = self.get_scaled_club_asset(FACE_PATH, face_h, mirror=self.is_left_handed)
        if face_img:
            self.canvas.create_image(q4_cx, q4_cy, image=face_img, anchor="c")

        # Sweet Spot Origin — exact center of the scoring grooves
        # Raw image 290x220: grooves X in [36, 167] -> Center X = 101.5 (dX = -43.5px from image center 145.0)
        # Grooves Y in [23, 117] -> Center Y = 70.0 (dY = -40.0px from image center 110.0)
        sweet_dx_ratio = -43.5 / 220.0  # -0.1977 (grooves are on the LEFT in raw image)
        sweet_dy_ratio = -40.0 / 220.0  # -0.1818 (grooves are above image center)
        # RH (raw image): shift LEFT into center of grooves (sweet_dx_ratio is negative)
        # LH (mirrored image): shift RIGHT into center of mirrored grooves (-sweet_dx_ratio is positive)
        center_offset_x = -int(sweet_dx_ratio * face_h) if self.is_left_handed else int(sweet_dx_ratio * face_h)
        center_offset_y = int(sweet_dy_ratio * face_h)
        center_x = q4_cx + center_offset_x
        center_y = q4_cy + center_offset_y
        cross_len = int(18 * scale)
        self.canvas.create_line(center_x - cross_len, center_y, center_x + cross_len, center_y, fill="#3A445C", width=1, dash=(2, 2))
        self.canvas.create_line(center_x, center_y - cross_len, center_x, center_y + cross_len, fill="#3A445C", width=1, dash=(2, 2))
        self.canvas.create_oval(center_x - int(3 * scale), center_y - int(3 * scale), center_x + int(3 * scale), center_y + int(3 * scale), fill=theme.ACCENT_TEXT, outline="")

        # Impact Contact Location
        # Real groove width: 131px across 290px -> ~52mm physical width on a standard iron face
        target_w = int(290 * (face_h / 220.0))
        scale_px = ((167.0 - 36.0) / 290.0 * target_w) / 52.0
        # OpenGolfCoach: h_impact_mm < 0 is TOE, h_impact_mm > 0 is HEEL
        # Raw image: TOE is on LEFT (-X), HOSEL is on RIGHT (+X)
        # RH (raw): h_impact_mm < 0 (TOE) moves LEFT (-X), h_impact_mm > 0 (HEEL) moves RIGHT (+X)
        # LH (mirrored): h_impact_mm < 0 (TOE) moves RIGHT (+X), h_impact_mm > 0 (HEEL) moves LEFT (-X)
        dx_px = -int(h_impact_mm * scale_px) if self.is_left_handed else int(h_impact_mm * scale_px)
        impact_x = center_x + dx_px
        impact_y = center_y - int(v_impact_mm * scale_px)

        # Vector Line from Sweet Spot to Impact
        if total_offset_mm >= 2.0 and (measured or dir_known):
            self.canvas.create_line(center_x, center_y, impact_x, impact_y, fill=strike_color, width=1, dash=(3, 2))

        if measured:
            # Precision Strike Reticle (real measurement)
            r_outer = int(14 * scale)
            r_mid = int(7 * scale)
            r_dot = int(3.5 * scale)
            self.canvas.create_oval(impact_x - r_outer, impact_y - r_outer, impact_x + r_outer, impact_y + r_outer, fill="", outline=strike_color, width=2)
            self.canvas.create_oval(impact_x - r_mid, impact_y - r_mid, impact_x + r_mid, impact_y + r_mid, fill="", outline=strike_color, width=1)
            self.canvas.create_oval(impact_x - r_dot, impact_y - r_dot, impact_x + r_dot, impact_y + r_dot, fill=strike_color, outline="")
        elif dir_known:
            # Fuzzy estimate zone: dashed halo sized by uncertainty, soft dot.
            # With no usable magnitude the halo is deliberately wide -- the dot
            # marks a DIRECTION on the face, not a located point.
            if magnitude_known:
                r_zone = max(int(10 * scale), int((4.0 + total_offset_mm * 0.6) * scale_px))
                zone_tag = "EST"
            else:
                r_zone = max(int(18 * scale), int(11.0 * scale_px))
                zone_tag = "DIR EST"
            r_dot = int(3.5 * scale)
            self.canvas.create_oval(impact_x - r_zone, impact_y - r_zone, impact_x + r_zone, impact_y + r_zone, fill="", outline=strike_color, width=1, dash=(4, 3))
            self.canvas.create_oval(impact_x - r_dot, impact_y - r_dot, impact_x + r_dot, impact_y + r_dot, fill=strike_color, outline="")
            self.canvas.create_text(impact_x, impact_y - r_zone - int(8 * scale), text=zone_tag, fill=strike_color, font=(theme.ui_font(), max(7, int(8 * font_scale)), "bold"))
        else:
            # Off-center but direction unknown: dashed ring around sweet spot
            r_ring = max(int(12 * scale), int(total_offset_mm * scale_px))
            self.canvas.create_oval(center_x - r_ring, center_y - r_ring, center_x + r_ring, center_y + r_ring, fill="", outline=strike_color, width=1, dash=(4, 3))
            self.canvas.create_text(center_x, center_y - r_ring - int(8 * scale), text="EST RADIUS", fill=strike_color, font=(theme.ui_font(), max(7, int(8 * font_scale)), "bold"))

        # Footer sits in the gutter as quiet caption text, matching the
        # mockup -- no centred bold banner.
        if measured:
            foot1 = f"{total_offset_mm:.1f} mm from centre"
        elif magnitude_known:
            foot1 = f"~{total_offset_mm:.0f} mm from centre, from smash"
        else:
            foot1 = "Direction only — no club-speed data"
        self.canvas.create_text(gut_l4, q4_bot - int(30 * font_scale),
                                text=foot1, fill=theme.TEXT_3, font=cap_f,
                                anchor="w")
        self.canvas.create_text(gut_l4, q4_bot - int(14 * font_scale),
                                text="Nova measures ball flight, not face contact",
                                fill=theme.TEXT_3, font=cap_f, anchor="w")

    def draw_divot_focus(self, pane_w, h, club_path, face_to_path, ball_speed, club_speed, carry, shot_name, offset_x=0):
        calib = obs_server.obs_state.load_layout().get("divot_calibration", {})
        cal_x = calib.get("offset_x", 0)
        cal_y = calib.get("offset_y", 0)

        cx = offset_x + (pane_w // 2) + cal_x
        cy = (h // 2) + 10 + cal_y

        self.canvas.create_line(cx - 130, cy, cx + 130, cy, fill="#22252E", width=2, dash=(4, 4))
        self.canvas.create_line(cx, cy - 130, cx, cy + 130, fill="#22252E", width=2, dash=(4, 4))

        divot_w, divot_h = 42, 150
        angle_rad = math.radians(club_path + calib.get("tilt_deg", 0.0))

        pts = [
            (cx - divot_w // 2, cy + 20),
            (cx - divot_w // 2 - 5, cy - divot_h // 2),
            (cx, cy - divot_h // 2 - 25),
            (cx + divot_w // 2 + 5, cy - divot_h // 2),
            (cx + divot_w // 2, cy + 20),
            (cx, cy + 45)
        ]

        rotated_pts = []
        for px, py in pts:
            rx, ry = self.rotate_point(px, py, cx, cy, angle_rad)
            rotated_pts.extend([rx, ry])

        self.canvas.create_polygon(rotated_pts, fill="#1B3B1B", outline=theme.ACCENT_TEXT, width=3)
        self.canvas.create_polygon(rotated_pts, fill="#4A2E13", outline="", stipple="gray50")

        path_len = 190
        px1, py1 = self.rotate_point(cx, cy + path_len // 2, cx, cy, angle_rad)
        px2, py2 = self.rotate_point(cx, cy - path_len // 2, cx, cy, angle_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill=theme.ACCENT_TEXT, width=3, arrow=tk.LAST, arrowshape=(12, 15, 5))

        self.canvas.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=theme.ACCENT_LINE, width=2)
        self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=theme.DANGER, outline="")
        self.canvas.create_text(cx, cy + 22, text="🎯 PHYSICAL BALL ORIGIN", fill=theme.DANGER, font=(theme.ui_font(), 8, "bold"))
        self.canvas.create_text(cx, 55, text=f"DIVOT PROJECTOR  •  {shot_name.upper()}", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 14, "bold"))

    def draw_my_bag_viewport(self, avail_w, h, offset_x=0):
        # 1. Background
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline="")

        self.bag_club_card_rects.clear()
        self.bag_edit_btn_rects.clear()
        self.bag_move_up_rects.clear()
        self.bag_move_down_rects.clear()

        # 2. Top Toolbar (y: 52 to 98)
        bar_y1, bar_y2 = 52, 98
        self.canvas.create_rectangle(offset_x, bar_y1, offset_x + avail_w, bar_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)

        total_shots = sum(len(s.get("shots", [])) for s in self.sessions)
        sess_shots = len(self.session_shots)
        display_shots = sess_shots if self.bag_scope == "session" else total_shots
        scope_str = "Current Session" if self.bag_scope == "session" else "All-Time History"

        self.canvas.create_text(offset_x + 18, 66, text="MY BAG MAPPING & GAPPING MATRIX", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 11, "bold"), anchor="w")
        self.canvas.create_text(offset_x + 18, 84, text=f"{len(self.bag)} Clubs in Bag  •  {display_shots} Shots ({scope_str})", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")

        # Scope Selector Pills (Center-Right)
        pill_w = 120
        p1_x1 = offset_x + avail_w - 410
        p1_x2 = p1_x1 + pill_w
        p2_x1 = p1_x2 + 8
        p2_x2 = p2_x1 + pill_w
        py1, py2 = 62, 88

        self.bag_scope_session_rect = (p1_x1, py1, p1_x2, py2)
        self.bag_scope_all_rect = (p2_x1, py1, p2_x2, py2)

        is_sess = (self.bag_scope == "session")
        self.canvas.create_rectangle(p1_x1, py1, p1_x2, py2, fill=theme.ACCENT_DEEP if is_sess else theme.SURFACE_2, outline=theme.ACCENT_TEXT if is_sess else theme.HAIRLINE)
        self.canvas.create_text((p1_x1 + p1_x2) // 2, (py1 + py2) // 2, text="Current Session", fill=theme.ACCENT_TEXT if is_sess else theme.TEXT_2, font=(theme.ui_font(), 8, "bold" if is_sess else "normal"), anchor="center")

        is_all = (self.bag_scope == "all_time")
        self.canvas.create_rectangle(p2_x1, py1, p2_x2, py2, fill=theme.ACCENT_DEEP if is_all else theme.SURFACE_2, outline=theme.ACCENT_TEXT if is_all else theme.HAIRLINE)
        self.canvas.create_text((p2_x1 + p2_x2) // 2, (py1 + py2) // 2, text="All-Time History", fill=theme.ACCENT_TEXT if is_all else theme.TEXT_2, font=(theme.ui_font(), 8, "bold" if is_all else "normal"), anchor="center")

        # Add Club to Bag Button (Far Right)
        add_x1 = offset_x + avail_w - 146
        add_x2 = offset_x + avail_w - 16
        self.bag_add_club_btn_rect = (add_x1, py1, add_x2, py2)
        self.canvas.create_rectangle(add_x1, py1, add_x2, py2, fill=theme.ACCENT_TEXT, outline="")
        self.canvas.create_text((add_x1 + add_x2) // 2, (py1 + py2) // 2, text="+ Add Club to Bag", fill="#08090C", font=(theme.ui_font(), 8, "bold"), anchor="center")

        # 3. Dual-Pane Dimensions
        content_y = 104
        content_h = h - content_y - 12
        left_w = int(avail_w * 0.54)
        right_w = avail_w - left_w - 18
        right_x = offset_x + left_w + 12

        self._draw_bag_rack_pane(offset_x + 6, content_y, left_w, content_h)
        self._draw_bag_gapping_ladder_pane(right_x, content_y, right_w, content_h)

    def _draw_bag_rack_pane(self, x1, y1, w, h):
        self.canvas.create_rectangle(x1, y1, x1 + w, y1 + h, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(x1 + 16, y1 + 16, text="BAG EQUIPMENT & SHOT AVERAGES", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 9, "bold"), anchor="w")
        self.canvas.create_text(x1 + w - 16, y1 + 16, text="Click card to Select  •  Edit Specs for Details", fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="e")

        card_area_y1 = y1 + 30
        curr_y = card_area_y1 - self.bag_scroll_offset

        for cat in BAG_CATEGORIES:
            cat_clubs = [c for c in self.bag if c.get("category") == cat]
            if not cat_clubs:
                continue

            # Category Header Bar
            if y1 + 24 <= curr_y <= y1 + h - 10:
                self.canvas.create_rectangle(x1 + 8, curr_y, x1 + w - 8, curr_y + 18, fill=theme.SURFACE, outline=theme.HAIRLINE)
                self.canvas.create_text(x1 + 16, curr_y + 9, text=f"{cat} ({len(cat_clubs)})", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")
            curr_y += 22

            for c in cat_clubs:
                c_name = c.get("name", "")
                # A club with no shots has nothing to show on lines 2-3, so it
                # gets a compact row. With 15 bag clubs and typically 1-2 hit
                # in a session, full-height empty cards pushed the clubs that
                # DO have data off the bottom of the pane.
                _has_data = self.get_bag_club_stats(
                    c_name, scope=self.bag_scope)["shot_count"] > 0
                card_h = 62 if _has_data else 30
                cy1 = curr_y
                cy2 = cy1 + card_h

                if y1 + 20 <= cy1 <= y1 + h or y1 + 20 <= cy2 <= y1 + h:
                    cx1 = x1 + 8
                    cx2 = x1 + w - 8
                    self.bag_club_card_rects.append((cx1, cy1, cx2, cy2, c_name))

                    is_active = (self.current_club == c_name)
                    bg_col = theme.ACCENT_DEEP if is_active else theme.SURFACE
                    border_col = theme.ACCENT_LINE if is_active else theme.HAIRLINE
                    c_color = self.get_club_color(c_name)

                    self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill=bg_col, outline=border_col, width=1.5 if is_active else 1)
                    self.canvas.create_rectangle(cx1, cy1, cx1 + 4, cy2, fill=c_color, outline="")

                    # Line 1: Name, Loft, Active badge, Specs
                    name_x = cx1 + 12
                    self.canvas.create_text(name_x, cy1 + 12, text=c_name, fill=theme.TEXT, font=(theme.ui_font(), 10, "bold"), anchor="w")
                    
                    loft = c.get("loft_deg", 0.0)
                    loft_str = f"{loft:.1f}°" if loft else ""
                    if loft_str:
                        self.canvas.create_text(name_x + 95, cy1 + 12, text=loft_str, fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

                    specs_parts = [p for p in [c.get("brand", ""), c.get("model", ""), c.get("shaft", "")] if p]
                    specs_str = " • ".join(specs_parts)
                    if len(specs_str) > 26:
                        specs_str = specs_str[:24] + "..."
                    self.canvas.create_text(name_x + 135, cy1 + 12, text=specs_str, fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")

                    if is_active:
                        badge_x2 = cx2 - 130
                        badge_x1 = badge_x2 - 54
                        # Selected club is a STATE, not a caution -- accent it.
                        _by = cy1 + (card_h - 15) // 2 if card_h < 50 else cy1 + 4
                        self.canvas.create_rectangle(badge_x1, _by, badge_x2, _by + 15, fill=theme.ACCENT_DEEP, outline="")
                        self.canvas.create_text((badge_x1 + badge_x2) // 2, _by + 7, text="ACTIVE", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 7, "bold"))
                    elif c.get("notes"):
                        # Notes indicator only when the ACTIVE badge isn't
                        # already occupying this corner of the card.
                        self.canvas.create_text(cx2 - 136, cy1 + 12, text="📝", font=(theme.ui_font(), 9))

                    # Action buttons: Edit Specs, Move Up, Move Down
                    # Centre the buttons in the row so they line up on both
                    # the full-height and compact variants.
                    btn_ey1 = cy1 + (card_h - 20) // 2
                    btn_ey2 = btn_ey1 + 20
                    edit_x1 = cx2 - 120
                    edit_x2 = cx2 - 54
                    self.bag_edit_btn_rects.append((edit_x1, btn_ey1, edit_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(edit_x1, btn_ey1, edit_x2, btn_ey2, fill=theme.SURFACE_2, outline=theme.HAIRLINE)
                    self.canvas.create_text((edit_x1 + edit_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="Edit Specs", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 7, "bold"))

                    up_x1 = cx2 - 48
                    up_x2 = cx2 - 28
                    self.bag_move_up_rects.append((up_x1, btn_ey1, up_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(up_x1, btn_ey1, up_x2, btn_ey2, fill=theme.SURFACE, outline=theme.HAIRLINE)
                    self.canvas.create_text((up_x1 + up_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="▲", fill=theme.TEXT_2, font=(theme.ui_font(), 8))

                    dn_x1 = cx2 - 24
                    dn_x2 = cx2 - 4
                    self.bag_move_down_rects.append((dn_x1, btn_ey1, dn_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(dn_x1, btn_ey1, dn_x2, btn_ey2, fill=theme.SURFACE, outline=theme.HAIRLINE)
                    self.canvas.create_text((dn_x1 + dn_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="▼", fill=theme.TEXT_2, font=(theme.ui_font(), 8))

                    # Line 2 & 3: Performance stats
                    stats = self.get_bag_club_stats(c_name, scope=self.bag_scope)
                    if stats["shot_count"] > 0:
                        # Caption-above-value pairs, matching the rest of the
                        # app, instead of a pipe-delimited run-on line.
                        cells = [
                            ("CARRY", f"{stats['avg_carry']:.1f} yds"),
                            ("SPREAD", f"±{stats['std_carry']:.1f}"),
                            ("TOTAL", f"{stats['avg_total']:.1f} yds"),
                            ("BALL", f"{stats['avg_ball_speed']:.1f} mph"),
                            ("LAUNCH", f"{stats['avg_launch']:.1f}°"),
                            ("SPIN", f"{stats['avg_spin']:.0f} rpm"),
                            ("SHOTS", f"{stats['shot_count']}"),
                        ]
                        # Smash is a constant wherever the OGC model saturates,
                        # so print it only when it carries information.
                        if not stats.get("smash_clamped", True):
                            cells.insert(4, ("SMASH", f"{stats['avg_smash']:.2f}"))
                        cw_ = 96
                        for ci, (cl, cv) in enumerate(cells):
                            cxp = name_x + ci * cw_
                            if cxp + cw_ > edit_x1 - 8:
                                break
                            self.canvas.create_text(cxp, cy1 + 30, text=cl,
                                                    fill=theme.TEXT_3,
                                                    font=(theme.ui_font(), 7),
                                                    anchor="nw")
                            self.canvas.create_text(cxp, cy1 + 41, text=cv,
                                                    fill=theme.TEXT,
                                                    font=(theme.ui_font(), 11),
                                                    anchor="nw")
                    # No else-branch: an empty club is a compact row and the
                    # absence of figures is the message. Repeating "no shots"
                    # on 13 of 15 clubs is noise, not information.

                curr_y += card_h + 5

    def _draw_bag_gapping_ladder_pane(self, x1, y1, w, h):
        self.canvas.create_rectangle(x1, y1, x1 + w, y1 + h, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(x1 + 16, y1 + 16, text="DISTANCE GAPPING LADDER", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 9, "bold"), anchor="w")

        gapping = self.calculate_bag_gapping(scope=self.bag_scope)
        grade_text = f"Consistency: {gapping['consistency_grade']}  •  Mean Gap: {gapping['mean_gap']:.1f} yds"
        self.canvas.create_text(x1 + w - 16, y1 + 16, text=grade_text, fill=gapping['consistency_color'], font=(theme.ui_font(), 8, "bold"), anchor="e")

        ladder_top = y1 + 44
        ladder_bot = y1 + h - 26
        ladder_h = ladder_bot - ladder_top
        # Scale the axis to the data instead of a fixed 0-320. A bag where the
        # longest club carries 57 yds otherwise draws every bar squashed into
        # the bottom sixth of the pane with five empty gridlines above it.
        _carries = [c["avg_carry"] for c in self.calculate_bag_gapping(
            scope=self.bag_scope)["clubs"]] or [0.0]
        _hi = max(_carries)
        min_yds = 0.0
        max_yds = 320.0 if _hi > 260 else max(60.0, _hi * 1.25)

        _step = 50 if max_yds > 240 else (25 if max_yds > 120 else 10)
        grid_steps = list(range(_step, int(max_yds) + 1, _step))
        for yds in grid_steps:
            gy = ladder_bot - int(((yds - min_yds) / (max_yds - min_yds)) * ladder_h)
            self.canvas.create_line(x1 + 65, gy, x1 + w - 20, gy, fill=theme.SURFACE_2, dash=(2, 4))
            self.canvas.create_text(x1 + 45, gy, text=f"{yds}y", fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="e")

        clubs_with_shots = gapping["clubs"]
        if not clubs_with_shots:
            self.canvas.create_text(x1 + w // 2, y1 + h // 2, text="No shot data recorded for current scope.\nHit shots or switch to All-Time History to view your visual gapping ladder.", fill=theme.TEXT_3, font=(theme.ui_font(), 10), justify="center")
            return

        bar_x1 = x1 + 105
        bar_x2 = x1 + w - 145
        bar_avail_w = bar_x2 - bar_x1

        club_y_coords = {}
        for c in clubs_with_shots:
            carry = c["avg_carry"]
            cy = ladder_bot - int(((carry - min_yds) / (max_yds - min_yds)) * ladder_h)
            cy = max(ladder_top + 10, min(ladder_bot - 10, cy))
            club_y_coords[c["name"]] = cy

            # Club Label on left
            self.canvas.create_text(x1 + 95, cy, text=c["name"], fill=c["color"], font=(theme.ui_font(), 8, "bold"), anchor="e")

            # Min-Max Whisker
            min_c = c.get("min_carry", carry)
            max_c = c.get("max_carry", carry)
            wx1 = bar_x1 + int((min_c / max_yds) * bar_avail_w)
            wx2 = bar_x1 + int((max_c / max_yds) * bar_avail_w)
            wx1 = max(bar_x1, min(bar_x2, wx1))
            wx2 = max(bar_x1, min(bar_x2, wx2))
            self.canvas.create_line(wx1, cy, wx2, cy, fill=theme.HAIRLINE, width=3)
            self.canvas.create_line(wx1, cy - 4, wx1, cy + 4, fill=theme.HAIRLINE, width=1.5)
            self.canvas.create_line(wx2, cy - 4, wx2, cy + 4, fill=theme.HAIRLINE, width=1.5)

            # Center Dot / Mean marker
            cx_pos = bar_x1 + int((carry / max_yds) * bar_avail_w)
            cx_pos = max(bar_x1, min(bar_x2, cx_pos))
            self.canvas.create_oval(cx_pos - 4, cy - 4, cx_pos + 4, cy + 4, fill=c["color"], outline=theme.TEXT, width=1)

            # Yardage readout on right
            self.canvas.create_text(bar_x2 + 10, cy, text=f"{carry:.1f} yds", fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

        # Plot Step Callout Indicators
        for step in gapping["steps"]:
            c_top = step["from_club"]
            c_bot = step["to_club"]
            if c_top in club_y_coords and c_bot in club_y_coords:
                yt = club_y_coords[c_top]
                yb = club_y_coords[c_bot]
                mid_y = (yt + yb) // 2

                bx = bar_x2 + 75
                self.canvas.create_line(bx - 4, yt, bx, yt, fill=step["color"], width=1)
                self.canvas.create_line(bx, yt, bx, yb, fill=step["color"], width=1)
                self.canvas.create_line(bx - 4, yb, bx, yb, fill=step["color"], width=1)

                badge_w = 68
                badge_h = 16
                self.canvas.create_rectangle(bx + 4, mid_y - badge_h // 2, bx + 4 + badge_w, mid_y + badge_h // 2, fill=theme.BG, outline=step["color"])
                self.canvas.create_text(bx + 4 + badge_w // 2, mid_y, text=step["status_text"], fill=step["color"], font=(theme.ui_font(), 7, "bold"), anchor="center")

    def get_fitting_clubs(self):
        """Returns list of distinct club names present in the active session, or current club + bag."""
        sess_clubs = []
        for s in self.session_shots:
            c = s.get("club")
            if c and c not in sess_clubs:
                sess_clubs.append(c)
        if self.current_club not in sess_clubs:
            sess_clubs.append(self.current_club)
        # If still only 1 club, offer some candidate bag clubs so user can immediately compare
        for b_c in self.bag:
            bn = b_c.get("name")
            if bn and bn not in sess_clubs and len(sess_clubs) < 5:
                sess_clubs.append(bn)
        return sess_clubs

    def _calculate_club_fitting_stats(self, c_name):
        c_shots = [s for s in self.session_shots if s.get("club") == c_name and not s.get("excluded", False)]
        if not c_shots:
            return None

        carries = []
        totals = []
        ball_speeds = []
        club_speeds = []
        smashes = []
        launches = []
        spins = []
        spin_axes = []
        apexes = []
        offlines = []
        closure_rates = []
        attacks = []
        dyn_lofts = []

        for s in c_shots:
            ogc = self.aim_corrected(s).get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})

            c = us.get("carry_distance_yards", 0.0)
            if c > 0: carries.append(c)

            tot = us.get("total_distance_yards", 0.0)
            if tot > 0: totals.append(tot)

            bs = us.get("ball_speed_mph", 0.0)
            if bs > 0: ball_speeds.append(bs)

            cs = us.get("club_speed_mph", 0.0)
            if cs > 0: club_speeds.append(cs)

            sm = ogc.get("smash_factor")
            if sm is not None: smashes.append(sm)

            la = s.get("vertical_launch_angle_degrees")
            if la is not None: launches.append(la)

            sp = ogc.get("total_spin_rpm")
            if sp is not None: spins.append(sp)

            sa = ogc.get("spin_axis_degrees")
            if sa is not None: spin_axes.append(sa)

            ap = us.get("peak_height_yards")
            if ap is not None: apexes.append(ap * 3.0)

            off = us.get("offline_distance_yards")
            if off is not None: offlines.append(off)

            cr = ogc.get("face_closure_rate_dps") or s.get("face_closure_rate_dps") or s.get("closure_rate")
            if cr is None and cs and len(smashes):
                fp = self.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
                cr = 1800 + abs(fp) * 320 + (cs * 12.5)
            if cr: closure_rates.append(cr)

            aa = ogc.get("angle_of_attack_degrees", {}).get("right_handed") if isinstance(ogc.get("angle_of_attack_degrees"), dict) else ogc.get("angle_of_attack_degrees", s.get("angle_of_attack_degrees", (la * 0.3 - 4.5) if la else None))
            if aa is not None: attacks.append(aa)

            dl = ogc.get("dynamic_loft_degrees", {}).get("right_handed") if isinstance(ogc.get("dynamic_loft_degrees"), dict) else ogc.get("dynamic_loft_degrees", s.get("dynamic_loft_degrees", (la * 0.85) if la else None))
            if dl is not None: dyn_lofts.append(dl)

        def _mean_std(arr, default_std=0.0):
            if not arr: return 0.0, default_std
            m = sum(arr) / len(arr)
            st = (sum((x - m)**2 for x in arr) / len(arr))**0.5 if len(arr) > 1 else default_std
            return m, st

        avg_c, std_c = _mean_std(carries, 3.0)
        avg_tot, std_tot = _mean_std(totals, 3.5)
        avg_bs, std_bs = _mean_std(ball_speeds, 1.0)
        avg_cs, std_cs = _mean_std(club_speeds, 1.0)
        avg_sm, std_sm = _mean_std(smashes, 0.02)
        avg_la, std_la = _mean_std(launches, 0.8)
        avg_sp, std_sp = _mean_std(spins, 150.0)
        avg_sa, std_sa = _mean_std(spin_axes, 1.2)
        avg_ap, std_ap = _mean_std(apexes, 4.0)
        avg_off, std_off = _mean_std(offlines, 2.0)
        avg_cr, std_cr = _mean_std(closure_rates, 80.0)
        avg_aa, std_aa = _mean_std(attacks, 0.5)
        avg_dl, std_dl = _mean_std(dyn_lofts, 0.6)

        # 95% Ellipse Area in square yards (pi * 2*std_off * 2*std_c)
        ellipse_area = math.pi * (2.0 * max(1.5, std_off)) * (2.0 * max(2.5, std_c))

        return {
            "name": c_name,
            "color": self.get_club_color(c_name),
            "count": len(c_shots),
            "carries": carries,
            "offlines": offlines,
            "apexes": apexes,
            "avg_carry": avg_c, "std_carry": std_c,
            "min_carry": min(carries) if carries else 0.0,
            "max_carry": max(carries) if carries else 0.0,
            "avg_total": avg_tot, "std_total": std_tot,
            "avg_ball_speed": avg_bs, "std_ball_speed": std_bs,
            "avg_club_speed": avg_cs, "std_club_speed": std_cs,
            "avg_smash": avg_sm, "std_smash": std_sm,
            # True when every contributing shot hit the OpenGolfCoach COR
            # floor, i.e. the smash figure carries no information.
            "smash_clamped": all(
                self.compute_smash_confidence(
                    s.get("ball_speed_meters_per_second"),
                    s.get("vertical_launch_angle_degrees"),
                    s.get("total_spin_rpm"),
                )["clamped"] for s in c_shots
            ) if c_shots else False,
            "avg_launch": avg_la, "std_launch": std_la,
            "avg_spin": avg_sp, "std_spin": std_sp,
            "avg_spin_axis": avg_sa, "std_spin_axis": std_sa,
            "avg_apex_ft": avg_ap, "std_apex_ft": std_ap,
            "avg_offline": avg_off, "std_offline": std_off,
            "avg_closure_rate": avg_cr, "std_closure_rate": std_cr,
            "avg_attack": avg_aa, "std_attack": std_aa,
            "avg_dyn_loft": avg_dl, "std_dyn_loft": std_dl,
            "ellipse_area": ellipse_area
        }

    def draw_fitting_viewport(self, avail_w, h, offset_x=0):
        # 1. Background
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline="")

        self.fitting_submode_rects.clear()
        self.fitting_club_chip_rects.clear()
        self.fitting_baseline_chip_rects.clear()
        self.fitting_dot_rects.clear()

        top_y = 58
        bot_y = h - 14

        # 2. Unified Top Fitting Toolbar (y: 58 to 100)
        bar_y1, bar_y2 = top_y, top_y + 42
        self.canvas.create_rectangle(offset_x + 10, bar_y1, offset_x + avail_w - 10, bar_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)

        # A. Sub-Mode Navigation Pills (Inside the top toolbar on left)
        submodes = [
            ("split", "Split View"),
            ("topdown", "Overhead Dispersion"),
            ("side", "Trajectory Side-View")
        ]
        sub_x = offset_x + 18
        for sm_key, sm_label in submodes:
            sm_w = len(sm_label) * 6 + 18
            sm_rect = (sub_x, bar_y1 + 7, sub_x + sm_w, bar_y2 - 7)
            self.fitting_submode_rects.append((sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], sm_key))
            is_active = (self.fitting_submode == sm_key)
            self.canvas.create_rectangle(sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], fill=theme.SURFACE_2 if is_active else theme.SURFACE, outline=theme.ACCENT_TEXT if is_active else theme.HAIRLINE)
            self.canvas.create_text((sm_rect[0] + sm_rect[2]) // 2, (sm_rect[1] + sm_rect[3]) // 2, text=sm_label, fill=theme.ACCENT_TEXT if is_active else theme.TEXT_2, font=(theme.ui_font(), 8, "bold" if is_active else "normal"))
            sub_x += sm_w + 6

        # Vertical separator between view modes and club chips
        sep_x = sub_x + 8
        self.canvas.create_line(sep_x, bar_y1 + 6, sep_x, bar_y2 - 6, fill=theme.HAIRLINE, width=1)

        # B. Session fitting clubs
        session_clubs = []
        for s in self.session_shots:
            c = s.get("club")
            if c and c not in session_clubs:
                session_clubs.append(c)
        if self.current_club not in session_clubs:
            session_clubs.append(self.current_club)

        # Baseline Club Selection (default to first club with shots)
        if not self.fitting_baseline_club or self.fitting_baseline_club not in session_clubs:
            self.fitting_baseline_club = session_clubs[0] if session_clubs else self.current_club

        # C. Competitor Club Chips (Inside the top toolbar, middle section)
        chip_x = sep_x + 14
        for i, c_name in enumerate(session_clubs[:5]):
            c_color = self.get_club_color(c_name)
            c_count = len([s for s in self.session_shots if s.get("club") == c_name and not s.get("excluded", False)])
            is_active = (c_name == self.current_club)
            is_baseline = (c_name == self.fitting_baseline_club)

            chip_text = f"{c_name} ({c_count})"
            base_badge_w = 46 if is_baseline else 0
            chip_w = len(chip_text) * 7 + 28 + base_badge_w
            cx1 = chip_x
            cx2 = cx1 + chip_w
            cy1 = bar_y1 + 7
            cy2 = bar_y2 - 7
            self.fitting_club_chip_rects.append((cx1, cy1, cx2, cy2, c_name))

            bg = theme.SURFACE_2 if is_active else theme.SURFACE
            border = c_color if is_active else theme.HAIRLINE
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill=bg, outline=border, width=2 if is_active else 1)

            # Color dot
            mid_y_chip = (cy1 + cy2) // 2
            self.canvas.create_oval(cx1 + 8, mid_y_chip - 4, cx1 + 16, mid_y_chip + 4, fill=c_color, outline="")
            self.canvas.create_text(cx1 + 22, mid_y_chip, text=chip_text, fill=theme.TEXT if is_active else theme.TEXT_2, font=(theme.ui_font(), 8, "bold" if is_active else "normal"), anchor="w")

            # Dedicated non-overlapping Baseline pill
            if is_baseline:
                bx1 = cx2 - 42
                bx2 = cx2 - 6
                by1 = cy1 + 3
                by2 = cy2 - 3
                self.fitting_baseline_chip_rects.append((bx1, by1, bx2, by2, c_name))
                self.canvas.create_rectangle(bx1, by1, bx2, by2, fill=theme.ACCENT_DEEP, outline=theme.ACCENT_TEXT, width=1)
                self.canvas.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text="BASE", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 7, "bold"), anchor="center")

            chip_x += chip_w + 8

        # D. + New Club button (Far right of top toolbar)
        add_w = 92
        add_x2 = offset_x + avail_w - 24
        add_x1 = add_x2 - add_w
        self.fitting_add_club_rect = (add_x1, bar_y1 + 7, add_x2, bar_y2 - 7)
        self.canvas.create_rectangle(add_x1, bar_y1 + 7, add_x2, bar_y2 - 7, fill=theme.ACCENT_DEEP, outline=theme.ACCENT_TEXT, width=1)
        self.canvas.create_text((add_x1 + add_x2) // 2, (bar_y1 + bar_y2) // 2, text="+ New Club", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="center")

        # 3. Stats for every competitor club
        stats_by_club = {}
        grouped_shots = {}
        for c_name in session_clubs:
            st = self._calculate_club_fitting_stats(c_name)
            if st and st["count"] > 0:
                stats_by_club[c_name] = st
            c_items = [(idx, s) for idx, s in enumerate(self.session_shots) if s.get("club") == c_name and not s.get("excluded", False)]
            if c_items:
                grouped_shots[c_name] = c_items

        # --- Stacked layout, per the Fit view mockup: club header cards,
        # --- then the stat matrix, then chart + recommendation on one row.
        cx0 = offset_x + 10
        cx1 = offset_x + avail_w - 10
        y = bar_y2 + 10

        # A. Club header cards -- baseline first, then the comparison clubs
        cmp_clubs = [c for c in session_clubs if c in stats_by_club][:3]
        if self.fitting_baseline_club in cmp_clubs:
            cmp_clubs.remove(self.fitting_baseline_club)
            cmp_clubs.insert(0, self.fitting_baseline_club)
        hdr_h = 78
        if cmp_clubs:
            hw_ = (cx1 - cx0 - 10 * (len(cmp_clubs) - 1)) / len(cmp_clubs)
            for i, c_name in enumerate(cmp_clubs):
                hx0 = cx0 + i * (hw_ + 10)
                hx1 = hx0 + hw_
                st = stats_by_club[c_name]
                is_base = (c_name == self.fitting_baseline_club)
                self.canvas.create_rectangle(hx0, y, hx1, y + hdr_h,
                                             fill=theme.SURFACE, outline="")
                # Accent rule on top, in the club's series colour.
                self.canvas.create_rectangle(hx0, y, hx1, y + 3,
                                             fill=self.get_club_color(c_name),
                                             outline="")
                self.canvas.create_text(hx0 + 18, y + 18, text=c_name,
                                        fill=theme.TEXT,
                                        font=(theme.ui_font(), 19), anchor="nw")
                spec = self.get_bag_club(c_name) or {}
                bits = [b for b in (spec.get("brand"), spec.get("model")) if b]
                loft = spec.get("loft_deg")
                sub = " ".join(bits) if bits else "—"
                if loft:
                    sub += f" · {float(loft):.1f}°"
                self.canvas.create_text(hx0 + 18, y + 48, text=sub,
                                        fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 8), anchor="nw")
                self.canvas.create_text(hx0 + 18, y + 61,
                                        text=f"{st['count']} shots",
                                        fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 8), anchor="nw")
                tag = "BASE" if is_base else "TEST"
                self.canvas.create_rectangle(hx1 - 62, y + 14, hx1 - 18, y + 30,
                                             fill=theme.SURFACE_2, outline="")
                self.canvas.create_text(hx1 - 40, y + 22, text=tag,
                                        fill=theme.ACCENT_TEXT if is_base else theme.TEXT_3,
                                        font=(theme.ui_font(), 7), anchor="center")
        y += hdr_h + 10

        # B. Head-to-head matrix. Height comes from the row count, not a
        # magic number: 214px across 7 rows plus a header and footer left
        # ~9px per row, so 10pt figures overlapped their own gridlines.
        _n_rows = 7
        matrix_h = 38 + 22 + _n_rows * 26 + 22
        self._draw_fitting_h2h_matrix(cx0, y, cx1 - cx0, y + matrix_h,
                                      stats_by_club, session_clubs)
        y += matrix_h + 10

        # C. Chart + recommendation
        chart_x1 = cx0
        chart_x2 = cx0 + (cx1 - cx0) * 0.63
        rec_x1 = chart_x2 + 10
        self.fitting_splitter_rect = None
        # Scale the range axis to the data. A fixed 350 yds squashes a
        # wedge session into the left corner of the plot.
        _max_carry = max((st.get("max_carry", 0.0)
                          for st in stats_by_club.values()), default=0.0)
        _axis = 350.0 if _max_carry > 280 else max(60.0, _max_carry * 1.30)
        # Height axis too: apex is reported in feet, so a 60 yd ceiling
        # leaves a 24 ft flight hugging the baseline.
        _max_apex_ft = max((st.get("avg_apex_ft", 0.0)
                            for st in stats_by_club.values()), default=0.0)
        _h_axis = max(10.0, (_max_apex_ft / 3.0) * 1.45)
        self._draw_fitting_overlaid_charts(chart_x1, y, chart_x2, bot_y,
                                           _axis, _h_axis, stats_by_club,
                                           grouped_shots)
        self._draw_fitting_recommendation(rec_x1, y, cx1, bot_y,
                                          stats_by_club, session_clubs)

    def _draw_fitting_overlaid_charts(self, plot_x1, plot_y1, plot_x2, plot_y2, max_x_yds, max_h_yds, stats_by_club, grouped_shots):
        content_h = plot_y2 - plot_y1
        chart_w = max(100, plot_x2 - plot_x1 - 50)
        margin_x = plot_x1 + 45

        if self.fitting_submode == "split":
            side_h = int(content_h * 0.44)
            side_y1 = plot_y1
            side_y2 = side_y1 + side_h

            disp_y1 = side_y2 + 10
            disp_y2 = plot_y2

            self._draw_fitting_side_chart(plot_x1, side_y1, plot_x2, side_y2, margin_x, chart_w, max_x_yds, max_h_yds, stats_by_club, grouped_shots)
            self._draw_fitting_topdown_chart(plot_x1, disp_y1, plot_x2, disp_y2, max_x_yds, stats_by_club, grouped_shots)
        elif self.fitting_submode == "side":
            self._draw_fitting_side_chart(plot_x1, plot_y1, plot_x2, plot_y2, margin_x, chart_w, max_x_yds, max_h_yds, stats_by_club, grouped_shots)
        else: # "topdown"
            self._draw_fitting_topdown_chart(plot_x1, plot_y1, plot_x2, plot_y2, max_x_yds, stats_by_club, grouped_shots)

    def _draw_fitting_topdown_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, max_range_yds, stats_by_club, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="OVERLAID DISPERSION & CONFIDENCE ELLIPSES", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

        plot_w = plot_x2 - plot_x1
        cx = (plot_x1 + plot_x2) // 2
        tee_y = plot_y2 - 16
        plot_h = tee_y - plot_y1 - 26
        max_lat_yds = 45.0

        # Centerline & Lateral guides
        self.canvas.create_line(cx, tee_y, cx, plot_y1 + 22, fill=theme.HAIRLINE, width=2, dash=(6, 4))
        for lat in [-30, -15, 15, 30]:
            lx = cx + int((lat / max_lat_yds) * (plot_w * 0.45))
            self.canvas.create_line(lx, tee_y, lx, plot_y1 + 24, fill=theme.SURFACE_2, width=1, dash=(2, 4))
            self.canvas.create_text(lx, plot_y2 - 6, text=f"{abs(lat)}y{'L' if lat < 0 else 'R'}", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Concentric distance arcs. Step follows max_range_yds -- a fixed
        # 50..350 list against a small axis draws arcs above the plot and
        # stacks their labels up the left edge over the panel above.
        # Pick the finest step that still yields at most 6 arcs, so the
        # ladder stays legible whether the session is wedges or drivers.
        _rstep = next((s for s in (5, 10, 20, 25, 50, 100)
                       if max_range_yds / s <= 6), 100)
        for yds in range(_rstep, int(max_range_yds) + 1, _rstep):
            frac = yds / max_range_yds
            arc_y = tee_y - int(frac * plot_h)
            if arc_y < plot_y1 + 24 or arc_y > tee_y:
                continue
            self.canvas.create_line(plot_x1 + 10, arc_y, plot_x2 - 10, arc_y, fill=theme.SURFACE_2, width=1, dash=(3, 3))
            self.canvas.create_text(plot_x1 + 20, arc_y, text=f"{yds}y", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        if not stats_by_club:
            self.canvas.create_text(cx, (plot_y1 + plot_y2) // 2, text="No shots recorded yet for fitting clubs", fill=theme.TEXT_3, font=(theme.ui_font(), 9))
            return

        # Render Multi-Club Overlaid Ellipses
        for c_name, st in stats_by_club.items():
            c_color = st["color"]
            mu_c = st["avg_carry"]
            mu_o = st["avg_offline"]
            std_c = st["std_carry"]
            std_o = st["std_offline"]

            cen_x = cx + int((mu_o / max_lat_yds) * (plot_w * 0.45))
            cen_y = tee_y - int((mu_c / max_range_yds) * plot_h)
            rx1 = int((std_o / max_lat_yds) * (plot_w * 0.45))
            ry1 = int((std_c / max_range_yds) * plot_h)

            # 2-Sigma outer dashed ellipse (95% confidence)
            self.canvas.create_oval(cen_x - rx1 * 2, cen_y - ry1 * 2, cen_x + rx1 * 2, cen_y + ry1 * 2, fill="", outline=c_color, width=1, dash=(4, 4))
            # 1-Sigma inner solid ellipse (68% confidence)
            self.canvas.create_oval(cen_x - rx1, cen_y - ry1, cen_x + rx1, cen_y + ry1, fill=c_color, outline=c_color, width=2, stipple="gray25")
            # Mean crosshair marker
            self.canvas.create_line(cen_x - 6, cen_y, cen_x + 6, cen_y, fill=theme.TEXT, width=2)
            self.canvas.create_line(cen_x, cen_y - 6, cen_x, cen_y + 6, fill=theme.TEXT, width=2)
            # Label badge
            self.canvas.create_text(cen_x, cen_y - ry1 - 8, text=f"{c_name}: {mu_c:.1f}y (±{std_c:.1f}y)", fill=c_color, font=(theme.ui_font(), 7, "bold"))

        # Render Dots for each shot
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            for real_idx, s in items:
                ogc = self.aim_corrected(s).get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                c_yds = us.get("carry_distance_yards", 0.0)
                o_yds = us.get("offline_distance_yards", 0.0)
                if c_yds <= 0:
                    continue

                dx = cx + int((o_yds / max_lat_yds) * (plot_w * 0.45))
                dy = tee_y - int((c_yds / max_range_yds) * plot_h)
                self.fitting_dot_rects.append((dx, dy, real_idx))

                is_sel = (real_idx == self.selected_shot_index)
                r = 5 if is_sel else 3
                self.canvas.create_oval(dx - r, dy - r, dx + r, dy + r, fill=theme.WARN if is_sel else c_color, outline=theme.TEXT if is_sel else "")

    def _draw_fitting_side_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, margin_x, chart_w, max_x_yds, max_h_yds, stats_by_club, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="TRAJECTORY PROFILES & APEX HEIGHT COMPARISON", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="w")

        base_y = plot_y2 - 22
        chart_h = max(30, base_y - plot_y1 - 32)

        # X distance ticks
        for t in [0, 50, 100, 150, 200, 250, 300, 350]:
            tx = margin_x + int((t / max_x_yds) * chart_w)
            self.canvas.create_line(tx, plot_y1 + 24, tx, base_y, fill=theme.SURFACE_2, width=1, dash=(2, 2))
            self.canvas.create_text(tx, base_y + 10, text=str(t), fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Y height grid lines. Steps follow max_h_yds -- a fixed [0,20,40,60]
        # against a small axis puts labels far above the plot, where they
        # trail up the page over whatever is drawn above the chart.
        _hstep = 20 if max_h_yds > 45 else (10 if max_h_yds > 22 else 5)
        for hy in range(0, int(max_h_yds) + 1, _hstep):
            ty = base_y - int((hy / max_h_yds) * chart_h)
            if ty < plot_y1 + 22 or ty > base_y:
                continue
            self.canvas.create_line(margin_x, ty, margin_x + chart_w, ty, fill=theme.SURFACE_2, width=1, dash=(2, 2))
            self.canvas.create_text(margin_x - 14, ty, text=f"{hy}y", fill=theme.TEXT_3, font=(theme.ui_font(), 7))

        # Ground baseline
        self.canvas.create_line(margin_x, base_y, margin_x + chart_w, base_y, fill=theme.ACCENT_TEXT, width=1)

        if not stats_by_club:
            self.canvas.create_text(margin_x + chart_w // 2, (plot_y1 + plot_y2) // 2, text="No trajectory data recorded yet", fill=theme.TEXT_3, font=(theme.ui_font(), 9))
            return

        # Render Overlaid Flight Arcs
        for c_name, st in stats_by_club.items():
            c_color = st["color"]
            avg_c = st["avg_carry"]
            avg_apex_y = st["avg_apex_ft"] / 3.0 # convert ft to yds
            if avg_c <= 0:
                continue

            pts = []
            for step in range(0, 101, 4):
                frac = step / 100.0
                curr_x = avg_c * frac
                curr_h = math.sin(frac * math.pi) * avg_apex_y
                cx_px = margin_x + int((curr_x / max_x_yds) * chart_w)
                cy_px = base_y - int((curr_h / max_h_yds) * chart_h)
                pts.extend([cx_px, cy_px])

            if len(pts) >= 4:
                self.canvas.create_line(pts, fill=c_color, width=2, smooth=True)

            # Apex callout badge
            apex_x_px = margin_x + int((avg_c * 0.5 / max_x_yds) * chart_w)
            apex_y_px = base_y - int((avg_apex_y / max_h_yds) * chart_h)
            self.canvas.create_oval(apex_x_px - 3, apex_y_px - 3, apex_x_px + 3, apex_y_px + 3, fill=c_color, outline=theme.TEXT)
            self.canvas.create_text(apex_x_px, apex_y_px - 8, text=f"{c_name}: {st['avg_apex_ft']:.0f}ft", fill=c_color, font=(theme.ui_font(), 7, "bold"))

            # Carry Landing Flag marker
            land_x = margin_x + int((avg_c / max_x_yds) * chart_w)
            self.canvas.create_oval(land_x - 4, base_y - 4, land_x + 4, base_y + 4, fill=c_color, outline=theme.TEXT)

    def _draw_fitting_h2h_matrix(self, x0, y0, w, y1, stats_by_club, session_clubs):
        """Row-per-stat comparison table, per the Fit view mockup.

        One row per metric with a column per club and a delta column, rather
        than a stacked block per club -- the point of a fitting view is
        comparing the same metric across clubs, which reads across a row.
        """
        x1 = x0 + w
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=theme.SURFACE,
                                     outline="")
        self.canvas.create_text(x0 + 18, y0 + 14, text="HEAD-TO-HEAD STAT MATRIX",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="nw")

        baseline = self.fitting_baseline_club or (session_clubs[0] if session_clubs else None)

        if not stats_by_club:
            self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                                    text="No clubs with shots in this session",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 10), anchor="center")
            return

        cols = [c for c in session_clubs if c in stats_by_club][:3]
        if baseline in cols:
            cols.remove(baseline)
            cols.insert(0, baseline)

        # Column geometry: label gutter, one column per club, delta on the right.
        lab_x = x0 + 18
        delta_x = x1 - 18
        first_col = x0 + w * 0.34
        col_span = (delta_x - 90 - first_col) / max(1, len(cols))

        hdr_y = y0 + 38
        for i, c in enumerate(cols):
            self.canvas.create_text(first_col + i * col_span, hdr_y, text=c,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="nw")
        if len(cols) >= 2:
            self.canvas.create_text(delta_x, hdr_y, text="DELTA",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="ne")

        rows = [
            ("Avg carry",  "avg_carry",  "{:.1f}",  1),
            ("Avg total",  "avg_total",  "{:.1f}",  1),
            ("Ball speed", "avg_ball_speed", "{:.1f}", 1),
            ("Launch",     "avg_launch", "{:.1f}°", 1),
            ("Spin",       "avg_spin",   "{:.0f}",  -1),
            ("Dispersion", "std_carry",  "±{:.1f}", -1),
            ("Club speed", None,         "--",       0),
        ]

        ry = hdr_y + 22
        foot_y = y1 - 20          # reserved strip for the caveat line
        row_h = (foot_y - 6 - ry) / len(rows)
        for label, key, fmt, better in rows:
            self.canvas.create_line(x0 + 18, ry, x1 - 18, ry,
                                    fill=theme.HAIRLINE)
            ty = ry + row_h * 0.5 - 7
            muted = key is None
            self.canvas.create_text(lab_x, ty, text=label,
                                    fill=theme.TEXT_3 if muted else theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="nw")
            vals = []
            for i, c in enumerate(cols):
                st = stats_by_club[c]
                if muted:
                    txt = "--"
                else:
                    v = float(st.get(key, 0.0) or 0.0)
                    vals.append(v)
                    txt = fmt.format(v)
                self.canvas.create_text(first_col + i * col_span, ty, text=txt,
                                        fill=theme.TEXT_3 if muted else theme.TEXT,
                                        font=(theme.ui_font(), 10), anchor="nw")
            # Delta against the baseline, coloured by whether it is an
            # improvement -- for spin and dispersion, lower is better.
            if muted or len(vals) < 2:
                self.canvas.create_text(delta_x, ty, text="--",
                                        fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 10), anchor="ne")
            else:
                d = vals[1] - vals[0]
                good = (d * better) > 0
                self.canvas.create_text(
                    delta_x, ty, text=f"{d:+.1f}" if abs(d) < 1000 else f"{d:+.0f}",
                    fill=theme.ACCENT_TEXT if good else theme.WARN,
                    font=(theme.ui_font(), 10), anchor="ne")
            ry += row_h

        self.canvas.create_text(lab_x, foot_y + 4,
                                text="Smash and club speed excluded — "
                                     "OpenGolfCoach saturates at these speeds",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")

    def _draw_fitting_recommendation(self, x0, y0, x1, y1, stats_by_club,
                                     session_clubs):
        """Which club won, and on what evidence."""
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=theme.SURFACE,
                                     outline="")
        self.canvas.create_text(x0 + 18, y0 + 14, text="RECOMMENDATION",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="nw")

        ranked = sorted(stats_by_club.items(),
                        key=lambda kv: kv[1].get("avg_carry", 0.0),
                        reverse=True)
        if not ranked:
            self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                                    text="Hit shots with two clubs to compare",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 9), anchor="center")
            return

        win_name, win_st = ranked[0]
        self.canvas.create_text(x0 + 18, y0 + 40, text=win_name,
                                fill=theme.ACCENT_TEXT,
                                font=(theme.ui_font(), 26), anchor="nw")

        ly = y0 + 84
        if len(ranked) >= 2:
            _, other = ranked[1]
            d_carry = win_st.get("avg_carry", 0.0) - other.get("avg_carry", 0.0)
            d_disp = win_st.get("std_carry", 0.0) - other.get("std_carry", 0.0)
            tighter = "tighter to target" if d_disp <= 0 else "wider dispersion"
            for line in (f"+{d_carry:.1f} yds carry, {tighter}",
                         f"{'at the cost of' if d_disp > 0 else 'and'} "
                         f"{abs(d_disp):.1f} yds dispersion"):
                self.canvas.create_text(x0 + 18, ly, text=line,
                                        fill=theme.TEXT_2,
                                        font=(theme.ui_font(), 9), anchor="nw")
                ly += 18
        else:
            self.canvas.create_text(x0 + 18, ly,
                                    text="Only one club has shots this session",
                                    fill=theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="nw")
            ly += 18

        total = sum(s.get("count", 0) for s in stats_by_club.values())
        self.canvas.create_text(x0 + 18, y1 - 16,
                                text=f"Based on {total} shots — smash factor excluded",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="sw")


    def draw_swing_lab_viewport(self, avail_w, h, offset_x=0):
        # 1. Background
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline="")

        top_y = 58
        bot_y = h - 14
        bar_y1, bar_y2 = top_y, top_y + 44
        bar_w = avail_w - 20
        bar_x1 = offset_x + 10
        bar_x2 = bar_x1 + bar_w

        # 2. Header: page title, then a borderless metric strip, per
        #    the Swing Lab mockup -- not a bordered toolbar of pills.
        _tid = self.canvas.create_text(bar_x1 + 4, bar_y1 - 2, text="Swing Lab",
                                       fill=theme.TEXT,
                                       font=(theme.ui_font(), 17), anchor="nw")
        _tbb = self.canvas.bbox(_tid)
        self.canvas.create_text((_tbb[2] + 12) if _tbb else bar_x1 + 110,
                                bar_y1 + 7, text="pressure & balance",
                                fill=theme.TEXT_3,
                                font=(theme.ui_font(), 9), anchor="nw")

        # Get latest pressure sample
        latest = None
        if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
            latest = obs_server.pressure_manager.latest_frame
        if not latest and self.current_shot:
            trace = self.get_pressure_trace(self.current_shot)
            if trace:
                latest = trace[-1]

        phase_str = latest.get("phase", "Address").title() if latest else "Ready"
        total_kg = latest.get("total_kg", 0.0) if latest else 0.0
        force_bw = latest.get("force_bw", 0.0) if latest else 0.0
        pct_l = latest.get("pct_left", 50.0) if latest else 50.0
        pct_r = latest.get("pct_right", 50.0) if latest else 50.0
        torque_nm = latest.get("torque_nm", 0.0) if latest else 0.0
        live = latest is not None

        lead_pct, trail_pct = (pct_r, pct_l) if self.is_left_handed else (pct_l, pct_r)

        # Metric strip. Values read "--" rather than a plausible default when
        # no board is connected -- 80.0 kg looked like a live reading.
        strip_y = bar_y2 + 6
        cells = [
            ("TOTAL WEIGHT", f"{total_kg:.1f}" if live else "--", "kg"),
            ("FORCE", f"{force_bw:.2f}" if live else "--", "BW"),
            ("LEAD", f"{lead_pct:.0f}" if live else "--", "%"),
            ("TRAIL", f"{trail_pct:.0f}" if live else "--", "%"),
            ("TORQUE", f"{torque_nm:+.1f}" if live else "--", "N·m"),
            ("PHASE", phase_str, ""),
        ]
        cw_ = (bar_w - 260) / len(cells)
        for i, (lb, val, unit) in enumerate(cells):
            cxp = bar_x1 + 4 + i * cw_
            self.canvas.create_text(cxp, strip_y, text=lb, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            # PHASE is a word, so it takes body-text size; the figures stay
            # large. Everything mutes when no board is reporting.
            _is_word = (lb == "PHASE")
            vid = self.canvas.create_text(
                cxp, strip_y + (16 if _is_word else 12), text=val,
                fill=theme.TEXT if live else theme.TEXT_3,
                font=(theme.ui_font(), 13 if _is_word else 20), anchor="nw")
            if unit:
                vbb = self.canvas.bbox(vid)
                if vbb:
                    self.canvas.create_text(vbb[2] + 5, strip_y + 26, text=unit,
                                            fill=theme.TEXT_3,
                                            font=(theme.ui_font(), 8),
                                            anchor="nw")
        bar_y2 = strip_y + 46
        self.canvas.create_line(bar_x1, bar_y2, bar_x2, bar_y2,
                                fill=theme.HAIRLINE)



        # 5. Right Action Buttons (Right-aligned with 12px fixed gap and generous width)
        btn_w = 96 if avail_w >= 1000 else 88
        btn_h = 26
        btn_gap = 12
        tare_x2 = bar_x2 - 10
        tare_x1 = tare_x2 - btn_w
        hw_x2 = tare_x1 - btn_gap
        hw_x1 = hw_x2 - btn_w
        demo_x2 = hw_x1 - btn_gap
        demo_x1 = demo_x2 - btn_w
        # Pin the actions to the title row, not the centre of the whole
        # header -- the metric strip below made "centred" land on the numbers.
        btn_y1 = bar_y1 - 2
        btn_y2 = btn_y1 + btn_h

        # Check if simulator/demo is active
        is_demo_on = obs_server.pressure_manager.is_simulator if hasattr(obs_server, "pressure_manager") else False

        self.swing_lab_demo_rect = (demo_x1, btn_y1, demo_x2, btn_y2)
        demo_bg = theme.SURFACE_2 if is_demo_on else theme.SURFACE
        demo_border = theme.ACCENT_TEXT if is_demo_on else theme.HAIRLINE
        demo_txt = "■ Stop Demo" if is_demo_on else "▶ Demo Swing"
        demo_col = theme.ACCENT_TEXT if is_demo_on else theme.TEXT_2
        self.canvas.create_rectangle(demo_x1, btn_y1, demo_x2, btn_y2, fill=demo_bg, outline=demo_border, width=1)
        self.canvas.create_text((demo_x1 + demo_x2) // 2, (btn_y1 + btn_y2) // 2, text=demo_txt, fill=demo_col, font=(theme.ui_font(), 8, "bold" if is_demo_on else "normal"), anchor="center")

        self.swing_lab_hw_rect = (hw_x1, btn_y1, hw_x2, btn_y2)
        self.canvas.create_rectangle(hw_x1, btn_y1, hw_x2, btn_y2, fill=theme.SURFACE, outline=theme.HAIRLINE, width=1)
        self.canvas.create_text((hw_x1 + hw_x2) // 2, (btn_y1 + btn_y2) // 2, text="⚙ Hardware", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="center")

        self.swing_lab_tare_rect = (tare_x1, btn_y1, tare_x2, btn_y2)
        self.canvas.create_rectangle(tare_x1, btn_y1, tare_x2, btn_y2, fill=theme.SURFACE, outline=theme.HAIRLINE, width=1)
        self.canvas.create_text((tare_x1 + tare_x2) // 2, (btn_y1 + btn_y2) // 2, text="⚖ Tare Zero", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="center")

        # 3. Main Workspace Split (Left: Heatmap, Right: COP & Curves)
        content_y1 = bar_y2 + 10
        content_h = bot_y - content_y1

        # Per the Swing Lab mockup: CoP trail and dual-foot pressure share the
        # top row, weight transfer and force curve share the bottom. The two
        # curves get their own panels rather than sharing one.
        top_h = int(content_h * 0.52)
        top_y1 = content_y1
        top_y2 = top_y1 + top_h
        bot_y1 = top_y2 + 10

        left_w = int(bar_w * 0.52)
        left_x1 = bar_x1
        left_x2 = left_x1 + left_w
        right_x1 = left_x2 + 10
        right_x2 = bar_x2

        def panel(px1, py1, px2, py2, title, tag=None):
            self.canvas.create_rectangle(px1, py1, px2, py2,
                                         fill=theme.SURFACE, outline="")
            self.canvas.create_text(px1 + 16, py1 + 13, text=title,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="nw")
            if tag:
                self.canvas.create_text(px2 - 16, py1 + 13, text=tag,
                                        fill=theme.TEXT_3,
                                        font=(theme.ui_font(), 8), anchor="ne")

        # --- TOP LEFT: CoP trail ---
        panel(left_x1, top_y1, left_x2, top_y2, "CENTRE OF PRESSURE TRAIL")
        self.draw_cop_trajectory_canvas(left_x1, top_y1 + 26, left_w,
                                        top_h - 30, latest=latest)

        # --- TOP RIGHT: dual-foot pressure ---
        panel(right_x1, top_y1, right_x2, top_y2, "DUAL-FOOT PRESSURE")
        right_w = right_x2 - right_x1
        foot_w = (right_w - 58) // 2
        foot_h = top_h - 96
        l_foot_x1 = right_x1 + 18
        r_foot_x1 = l_foot_x1 + foot_w + 22
        self.draw_single_foot_heatmap(l_foot_x1, top_y1 + 30, foot_w, foot_h,
                                      is_left=True, latest=latest)
        self.draw_single_foot_heatmap(r_foot_x1, top_y1 + 30, foot_w, foot_h,
                                      is_left=False, latest=latest)

        # Lead / trail split beneath the footbeds, per the mockup.
        sp_y = top_y1 + 30 + foot_h + 14
        lead_pct, trail_pct = (pct_r, pct_l) if self.is_left_handed else (pct_l, pct_r)
        self.canvas.create_text(l_foot_x1, sp_y, text="LEAD (L)",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        self.canvas.create_text(l_foot_x1 + foot_w, sp_y,
                                text=f"{lead_pct:.0f}%" if live else "--",
                                fill=theme.TEXT if live else theme.TEXT_3,
                                font=(theme.ui_font(), 15), anchor="ne")
        self.canvas.create_text(r_foot_x1, sp_y, text="TRAIL (R)",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        self.canvas.create_text(r_foot_x1 + foot_w, sp_y,
                                text=f"{trail_pct:.0f}%" if live else "--",
                                fill=theme.TEXT if live else theme.TEXT_3,
                                font=(theme.ui_font(), 15), anchor="ne")
        sb_y = sp_y + 28
        sb_x2 = r_foot_x1 + foot_w
        self.canvas.create_rectangle(l_foot_x1, sb_y, sb_x2, sb_y + 6,
                                     fill=theme.SURFACE_2, outline="")
        if live:
            _split = max(0.0, min(1.0, lead_pct / 100.0))
            self.canvas.create_rectangle(l_foot_x1, sb_y,
                                         l_foot_x1 + (sb_x2 - l_foot_x1) * _split,
                                         sb_y + 6, fill=theme.ACCENT, outline="")
            self.canvas.create_text(l_foot_x1, sb_y + 10,
                                    text=f"{lead_pct:.0f}% lead",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            self.canvas.create_text(sb_x2, sb_y + 10,
                                    text=f"{trail_pct:.0f}% trail",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="ne")
        else:
            self.canvas.create_text((l_foot_x1 + sb_x2) / 2, sb_y + 10,
                                    text="No board connected",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="n")

        # --- BOTTOM: weight transfer + force curve, side by side ---
        cw_ = (bar_w - 10) / 2
        wt_x1 = bar_x1
        wt_x2 = wt_x1 + cw_
        fc_x1 = wt_x2 + 10
        fc_x2 = bar_x2
        panel(wt_x1, bot_y1, wt_x2, bot_y, "WEIGHT TRANSFER", "lead · trail")
        panel(fc_x1, bot_y1, fc_x2, bot_y, "FORCE CURVE", "× bodyweight")
        self.draw_force_timeline_canvas(wt_x1, bot_y1 + 24, cw_,
                                        bot_y - bot_y1 - 28, series="transfer")
        self.draw_force_timeline_canvas(fc_x1, bot_y1 + 24, cw_,
                                        bot_y - bot_y1 - 28, series="force")

    def draw_single_foot_heatmap(self, x1, y1, w, h, is_left=True, latest=None):
        x2, y2 = x1 + w, y1 + h
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline=theme.HAIRLINE, width=1)
        if self.is_left_handed:
            foot_label = "TRAIL FOOT (LEFT)" if is_left else "LEAD FOOT (RIGHT)"
        else:
            foot_label = "LEAD FOOT (LEFT)" if is_left else "TRAIL FOOT (RIGHT)"
        self.canvas.create_text((x1 + x2) // 2, y1 + 14, text=foot_label, fill=theme.TEXT_2, font=(theme.ui_font(), 8))

        # Foot Outline
        cx = (x1 + x2) // 2
        f_top = y1 + 28
        f_bot = y2 - 28
        f_half_w = (w - 24) // 2

        # Draw anatomical shoe/foot contour
        pts = [
            cx - f_half_w * 0.7, f_top + 15,
            cx, f_top + 4,
            cx + f_half_w * 0.7, f_top + 15,
            cx + f_half_w * 0.85, f_top + int(h * 0.35),
            cx + f_half_w * 0.55, f_top + int(h * 0.60),
            cx + f_half_w * 0.65, f_bot - 10,
            cx, f_bot,
            cx - f_half_w * 0.65, f_bot - 10,
            cx - f_half_w * 0.55, f_top + int(h * 0.60),
            cx - f_half_w * 0.85, f_top + int(h * 0.35),
        ]
        self.canvas.create_polygon(pts, fill=theme.BG, outline=theme.HAIRLINE, width=2)

        # 4 Load Sensors for this foot
        raw = latest.get("raw_cells", [20.0, 20.0, 20.0, 20.0]) if latest else [20.0, 20.0, 20.0, 20.0]
        # raw_cells: [TL, TR, BL, BR]
        if is_left:
            tl_kg, tr_kg = raw[0] * 0.55, raw[0] * 0.45
            bl_kg, br_kg = raw[2] * 0.55, raw[2] * 0.45
            tot_foot = latest.get("pct_left", 50.0) if latest else 50.0
        else:
            tl_kg, tr_kg = raw[1] * 0.45, raw[1] * 0.55
            bl_kg, br_kg = raw[3] * 0.45, raw[3] * 0.55
            tot_foot = latest.get("pct_right", 50.0) if latest else 50.0

        sensors = [
            (cx - f_half_w * 0.45, f_top + int(h * 0.25), tl_kg, "Toe In"),
            (cx + f_half_w * 0.45, f_top + int(h * 0.25), tr_kg, "Toe Out"),
            (cx - f_half_w * 0.35, f_bot - int(h * 0.20), bl_kg, "Heel In"),
            (cx + f_half_w * 0.35, f_bot - int(h * 0.20), br_kg, "Heel Out"),
        ]

        for sx, sy, kg, name in sensors:
            # Color based on load intensity
            intensity = min(1.0, max(0.05, kg / 35.0))
            rad = int(14 + intensity * 22)
            
            # Draw gradient rings
            # Load ramp: quiet at rest, accent as weight arrives, warn only
            # at genuine peak. The previous version mapped the bottom two
            # bands to the same colour, so half the range read identically.
            if intensity > 0.75:
                glow_col = theme.WARN
            elif intensity > 0.5:
                glow_col = theme.ACCENT_TEXT
            elif intensity > 0.25:
                glow_col = theme.ACCENT_LINE
            else:
                glow_col = theme.ACCENT_DEEP
            self.canvas.create_oval(sx - rad, sy - rad, sx + rad, sy + rad, fill="", outline=glow_col, width=2)
            self.canvas.create_oval(sx - rad // 2, sy - rad // 2, sx + rad // 2, sy + rad // 2, fill=glow_col, outline="")
            self.canvas.create_text(sx, sy + rad + 9,
                                    text=f"{kg:.1f}kg" if latest else "--",
                                    fill=theme.TEXT_2 if latest else theme.TEXT_3,
                                    font=(theme.ui_font(), 7))

        # Foot Total Badge
        self.canvas.create_rectangle(x1 + 10, y2 - 24, x2 - 10, y2 - 6, fill=theme.SURFACE, outline=theme.HAIRLINE)
        self.canvas.create_text((x1 + x2) // 2, y2 - 15,
                                text=f"Total: {int(tot_foot)}%" if latest else "Total: --",
                                fill=theme.TEXT_2 if latest else theme.TEXT_3,
                                font=(theme.ui_font(), 8))

    def draw_cop_trajectory_canvas(self, x1, y1, w, h, latest=None):
        x2, y2 = x1 + w, y1 + h
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        max_r = min(w, h) // 2 - 20

        # Grid lines & Rings
        for r_frac, label in [(0.33, "50mm"), (0.66, "100mm"), (1.0, "150mm")]:
            r = int(max_r * r_frac)
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="", outline=theme.HAIRLINE, dash=(2, 4))
            self.canvas.create_text(cx + r + 4, cy - 6, text=label, fill=theme.TEXT_3, font=(theme.ui_font(), 6), anchor="w")

        # Crosshairs
        self.canvas.create_line(x1 + 20, cy, x2 - 20, cy, fill=theme.HAIRLINE, width=1)
        self.canvas.create_line(cx, y1 + 10, cx, y2 - 10, fill=theme.HAIRLINE, width=1)
        self.canvas.create_text(cx - max_r + 10, cy - 8, text="◀ LEAD (L)", fill=theme.TEXT_3, font=(theme.ui_font(), 6))
        self.canvas.create_text(cx + max_r - 10, cy - 8, text="TRAIL (R) ▶", fill=theme.TEXT_3, font=(theme.ui_font(), 6))
        self.canvas.create_text(cx + 6, y1 + 14, text="▲ TOES", fill=theme.TEXT_3, font=(theme.ui_font(), 6))
        self.canvas.create_text(cx + 6, y2 - 14, text="▼ HEELS", fill=theme.TEXT_3, font=(theme.ui_font(), 6))

        # Scale: 150mm maps to max_r
        scale = max_r / 150.0

        # Draw Trail from history
        trail = self.swing_lab_history
        if self.current_shot:
            stored = self.get_pressure_trace(self.current_shot)
            if stored:
                trail = stored

        if len(trail) > 1:
            pts = []
            for item in trail[-120:]:
                tx = cx + int(item.get("cop_x", 0.0) * scale)
                ty = cy - int(item.get("cop_y", 0.0) * scale)
                pts.append((tx, ty, item.get("phase", "Address")))
            
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i + 1]
                ph = p2[2]
                seg_col = theme.ACCENT_TEXT if "ADDR" in ph.upper() else (theme.WARN if "BACK" in ph.upper() else (theme.DANGER if "IMPACT" in ph.upper() else theme.ACCENT_TEXT))
                self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=seg_col, width=2)

        # Current COP Bullseye Dot
        cur_cop_x = latest.get("cop_x", 0.0) if latest else 0.0
        cur_cop_y = latest.get("cop_y", 0.0) if latest else 0.0
        dot_x = cx + int(cur_cop_x * scale)
        dot_y = cy - int(cur_cop_y * scale)

        self.canvas.create_oval(dot_x - 12, dot_y - 12, dot_x + 12, dot_y + 12, fill="", outline=theme.ACCENT_TEXT, width=2)
        self.canvas.create_oval(dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5, fill=theme.ACCENT_TEXT, outline=theme.TEXT)
        self.canvas.create_text(dot_x + 14, dot_y, text=f"({cur_cop_x:+.0f}, {cur_cop_y:+.0f})", fill=theme.TEXT, font=(theme.ui_font(), 7, "bold"), anchor="w")

    def draw_force_timeline_canvas(self, x1, y1, w, h, series="transfer"):
        """Timeline curve for the swing.

        series="transfer" plots lead and trail foot load as a percentage;
        series="force" plots vertical load in bodyweights. Both share the
        same normalised timeline and phase bands so they can be read
        together vertically, per the Swing Lab mockup.
        """
        x2, y2 = x1 + w, y1 + h

        trail = self.swing_lab_history
        if self.current_shot:
            stored = self.get_pressure_trace(self.current_shot)
            if stored:
                trail = stored

        gx1, gx2 = x1 + 46, x2 - 16
        gy1, gy2 = y1 + 22, y2 - 26
        gw, gh = gx2 - gx1, gy2 - gy1

        if len(trail) < 2:
            self.canvas.create_text((x1 + x2) // 2, (y1 + y2) // 2,
                                    text="No swing captured yet",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 9))
            return

        samples = trail[-120:]
        n = len(samples)

        def sx(i):
            return gx1 + (i / float(max(1, n - 1))) * gw

        # Phase bands along the bottom, from the sample phases themselves.
        phases = []
        for i, s in enumerate(samples):
            ph = str(s.get("phase", "")).title() or "—"
            if not phases or phases[-1][0] != ph:
                phases.append((ph, i))
        for pi, (ph, i0) in enumerate(phases):
            i1 = phases[pi + 1][1] if pi + 1 < len(phases) else n - 1
            if i1 - i0 < 1:
                continue
            bx1, bx2_ = sx(i0), sx(i1)
            if pi % 2:
                self.canvas.create_rectangle(bx1, gy1, bx2_, gy2,
                                             fill=theme.SURFACE_2, outline="")
            self.canvas.create_text((bx1 + bx2_) / 2, gy2 + 8, text=ph,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="n")

        if series == "transfer":
            ticks = [(0.0, "0%"), (0.5, "50%"), (1.0, "100%")]
            lead_key = "pct_right" if self.is_left_handed else "pct_left"
            trail_key = "pct_left" if self.is_left_handed else "pct_right"
            seriess = [
                (lead_key, theme.ACCENT_LINE, "lead", 100.0),
                (trail_key, theme.TEXT_2, "trail", 100.0),
            ]
        else:
            vals = [float(s.get("force_bw", 1.0) or 1.0) for s in samples]
            hi = max(1.6, max(vals) * 1.1)
            ticks = [(0.0, "0"), (1.0 / hi, "1.0"), (1.0, f"{hi:.1f}")]
            seriess = [("force_bw", theme.ACCENT_LINE, "total", hi)]

        for frac, label in ticks:
            ty = gy2 - frac * gh
            self.canvas.create_line(gx1, ty, gx2, ty, fill=theme.HAIRLINE,
                                    dash=(2, 4))
            self.canvas.create_text(gx1 - 8, ty, text=label, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="e")

        for key, col, label, scale in seriess:
            pts = []
            for i, s in enumerate(samples):
                v = s.get(key)
                if v is None and key == "pct_right":
                    v = 100.0 - float(s.get("pct_left", 50.0) or 50.0)
                v = float(v if v is not None else 0.0)
                pts.append((sx(i), gy2 - max(0.0, min(1.0, v / scale)) * gh))
            for i in range(len(pts) - 1):
                self.canvas.create_line(pts[i][0], pts[i][1],
                                        pts[i + 1][0], pts[i + 1][1],
                                        fill=col, width=2)

        # Impact marker -- the moment both curves are read against.
        for i, s in enumerate(samples):
            if "impact" in str(s.get("phase", "")).lower():
                ix = sx(i)
                self.canvas.create_line(ix, gy1, ix, gy2, fill=theme.WARN,
                                        dash=(3, 3))
                self.canvas.create_text(ix, gy1 - 4, text="impact",
                                        fill=theme.WARN,
                                        font=(theme.ui_font(), 7), anchor="s")
                break

        # Legend on the panel header row, clear of the plot.
        lx = gx2
        for key, col, label, _ in reversed(seriess):
            tid = self.canvas.create_text(lx, y1 + 8, text=label, fill=col,
                                          font=(theme.ui_font(), 7), anchor="ne")
            bb = self.canvas.bbox(tid)
            if bb:
                self.canvas.create_line(bb[0] - 16, y1 + 12, bb[0] - 4, y1 + 12,
                                        fill=col, width=2)
                lx = bb[0] - 24

    def draw_setup_viewport(self, avail_w, h, offset_x=0):
        """Setup / hardware view -- see the Setup view mockup.

        Replaces the balance-hardware modal as the primary surface. Board
        pairing used to live behind Swing Lab -> Hardware, which is a strange
        place to look when you are trying to connect a board for the first
        time and have no data yet.

        Every control from the modal is preserved: single/dual mode, pairing,
        the step-on assignment wizard, 50/50 alignment and tare.
        """
        pm = getattr(obs_server, "pressure_manager", None)
        x0 = offset_x + 24
        x1 = offset_x + avail_w - 24
        # Start below the app top bar -- this view draws its own page header
        # and would otherwise sit on top of the brand/status row.
        y = 74

        # ---- header --------------------------------------------------------
        self.canvas.create_text(x0, y, text="Setup", fill=theme.TEXT,
                                font=(theme.ui_font(), 17), anchor="nw")
        hb = self.canvas.bbox(self.canvas.find_all()[-1])
        self.canvas.create_text((hb[2] + 10) if hb else x0 + 70, y + 8,
                                text="devices & hardware", fill=theme.TEXT_3,
                                font=(theme.ui_font(), 9), anchor="nw")

        # Real link state from the worker threads. self.nova_connected was
        # only ever set when a SHOT arrived, so this page said "Not
        # connected" on a live link until the user hit a ball — while the
        # tools menu, reading nova_status, correctly showed it online.
        nova_up = bool(nova_status.get("connected", False))
        gspro_on = bool(gspro_status.get("enabled", False))
        gspro_up = bool(gspro_status.get("connected", False))

        if gspro_on and not gspro_settings.nova_enabled():
            src_up, src_label = gspro_up, ("GSPro connected" if gspro_up
                                           else "GSPro offline")
        elif gspro_on:
            src_up = nova_up or gspro_up
            if nova_up and gspro_up:
                src_label = "Nova + GSPro connected"
            elif gspro_up:
                src_label = "GSPro connected"
            elif nova_up:
                src_label = "Nova connected"
            else:
                src_label = "No source connected"
        else:
            src_up, src_label = nova_up, ("Nova connected" if nova_up
                                          else "Nova offline")

        dot = theme.ACCENT if src_up else theme.TEXT_3
        self.canvas.create_oval(x1 - 132, y + 6, x1 - 126, y + 12,
                                fill=dot, outline="")
        self.canvas.create_text(x1 - 118, y + 4,
                                text=src_label,
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="nw")
        y += 40
        self.canvas.create_line(x0, y, x1, y, fill=theme.HAIRLINE)
        y += 16

        col_gap = 20
        col_w = (x1 - x0 - col_gap) / 2
        lx0, lx1 = x0, x0 + col_w
        rx0, rx1 = lx1 + col_gap, x1
        bot = h - 40

        def card(cx0, cy0, cx1, cy1, title):
            self.canvas.create_rectangle(cx0, cy0, cx1, cy1,
                                         fill=theme.SURFACE, outline="")
            self.canvas.create_text(cx0 + 18, cy0 + 14, text=title,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 8), anchor="nw")

        def row(rx, ry, label, value, vcol=None):
            self.canvas.create_text(rx + 18, ry, text=label, fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 9), anchor="nw")
            self.canvas.create_text(rx1_cur - 18, ry, text=value,
                                    fill=vcol or theme.TEXT,
                                    font=(theme.ui_font(), 9), anchor="ne")

        # ================= LEFT COLUMN =================
        ly = y

        # --- launch monitor / shot source ---
        lm_h = 186
        card(lx0, ly, lx1, ly + lm_h, "SHOT SOURCE")
        rx1_cur = lx1

        source = gspro_settings.effective_source()
        locked = gspro_settings.load_settings()["source_locked"]

        if source == "gspro":
            dev_name = "GSPro"
            dev_up = gspro_up
            dev_state = ("Polling GSPro.db" if gspro_up else
                         ("Database not found" if not gspro_status.get("db_found")
                          else "Connecting..."))
        elif source == "both":
            dev_name = "Nova + GSPro"
            dev_up = nova_up or gspro_up
            dev_state = f"Nova {'up' if nova_up else 'down'} · GSPro {'up' if gspro_up else 'down'}"
        else:
            dev_name = "OpenLaunch Nova"
            dev_up = nova_up
            dev_state = "Connected" if nova_up else "Not connected"

        self.canvas.create_oval(lx0 + 18, ly + 36, lx0 + 28, ly + 46,
                                fill=theme.ACCENT if dev_up else theme.TEXT_3,
                                outline="")
        self.canvas.create_text(lx0 + 36, ly + 30, text=dev_name,
                                fill=theme.TEXT, font=(theme.ui_font(), 13),
                                anchor="nw")
        self.canvas.create_text(lx0 + 36, ly + 50,
                                text=dev_state,
                                fill=theme.ACCENT_TEXT if dev_up else theme.TEXT_3,
                                font=(theme.ui_font(), 8), anchor="nw")

        if source == "gspro":
            row(lx0, ly + 76, "Database",
                gspro_status.get("db_path") or "(auto-locating)")
        else:
            host = getattr(obs_server, "NOVA_HOST", None) or "openlaunch-nova.local"
            row(lx0, ly + 76, "Host", str(host))
        row(lx0, ly + 96, "Shots this session", str(len(self.session_shots)))

        # Source switcher, so GSPro can be selected without the splash.
        self.canvas.create_text(lx0 + 18, ly + 122, text="SOURCE",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 8),
                                anchor="nw")
        self.setup_source_btn_rects = []
        btn_y1, btn_y2 = ly + 140, ly + 168
        btn_w = (lx1 - lx0 - 36 - 16) // 3
        for i, (key, label) in enumerate((("nova", "Nova"),
                                          ("gspro", "GSPro"),
                                          ("both", "Both"))):
            bx1 = lx0 + 18 + i * (btn_w + 8)
            bx2 = bx1 + btn_w
            active = source == key
            self.canvas.create_rectangle(
                bx1, btn_y1, bx2, btn_y2,
                fill=theme.ACCENT_DEEP if active else theme.SURFACE_2,
                outline=theme.ACCENT_LINE if active else theme.HAIRLINE)
            self.canvas.create_text(
                (bx1 + bx2) // 2, (btn_y1 + btn_y2) // 2, text=label,
                fill=theme.ACCENT_TEXT if active else theme.TEXT_2,
                font=(theme.ui_font(), 9, "bold"), anchor="center")
            if not locked:
                self.setup_source_btn_rects.append(
                    (bx1, btn_y1, bx2, btn_y2, key))

        if locked:
            self.canvas.create_text(
                lx0 + 18, ly + 172,
                text="Locked by the SPS_SHOT_SOURCE environment variable",
                fill=theme.WARN, font=(theme.ui_font(), 7), anchor="nw")

        ly += lm_h + 14

        # --- display ---
        dsp_h = 118
        card(lx0, ly, lx1, ly + dsp_h, "DISPLAY")
        port = getattr(obs_server, "OBS_PORT", 9321)
        row(lx0, ly + 34, "Overlay server", f"localhost:{port}")
        row(lx0, ly + 56, "Handedness",
            "Left" if self.is_left_handed else "Right")
        row(lx0, ly + 78, "Units", "Yards / MPH")
        ly += dsp_h + 14

        # --- aim calibration -------------------------------------------------
        # The Nova has no aim calibration. A unit sitting a couple of degrees
        # off square reports every shot as a push (or a pull), which biases
        # start line and offline for every shot the app has ever stored.
        aim_h = 188
        card(lx0, ly, lx1, ly + aim_h, "AIM CALIBRATION")
        rx1_cur = lx1
        off = float(self.aim_offset_deg or 0.0)

        if off == 0.0:
            head, head_col = "Not calibrated", theme.TEXT_2
            sub = "Offline and start line are read as-is from the device"
        else:
            side = "right" if off > 0 else "left"
            head, head_col = f"{abs(off):.1f}° {side} of target", theme.ACCENT_TEXT
            sub = "Applied to start line and offline on every shot"
        self.canvas.create_text(lx0 + 18, ly + 28, text=head, fill=head_col,
                                font=(theme.ui_font(), 13), anchor="nw")
        self.canvas.create_text(lx0 + 18, ly + 48, text=sub,
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")

        # A tiny plan view: target line, and the device's actual heading.
        # Kept above the nudge row -- an earlier version ran into the Reset
        # button, which the postscript capture caught.
        gx, gy = lx1 - 60, ly + 22
        base_y = gy + 40
        self.canvas.create_line(gx, base_y, gx, gy, fill=theme.GUIDE, dash=(2, 3))
        ang = math.radians(max(-25.0, min(25.0, off * 5.0)))
        self.canvas.create_line(gx, base_y,
                                gx + 40 * math.sin(ang), base_y - 40 * math.cos(ang),
                                fill=theme.ACCENT_LINE, width=2)
        self.canvas.create_oval(gx - 3, base_y - 3, gx + 3, base_y + 3,
                                fill=theme.ACCENT, outline="")

        # Primary path: measure the room. Nobody can eyeball a degree value,
        # so this is the button that has to look like the way in.
        my = ly + 70
        self.setup_aim_measure_rect = (lx0 + 18, my, lx1 - 18, my + 34)
        self.canvas.create_rectangle(*self.setup_aim_measure_rect,
                                     fill=theme.ACCENT_DEEP,
                                     outline=theme.ACCENT_LINE)
        self.canvas.create_text((lx0 + lx1) / 2, my + 17,
                                text="Measure with a tape  —  distance & offset",
                                fill=theme.ACCENT_TEXT,
                                font=(theme.ui_font(), 9), anchor="center")

        # Secondary: fine adjustment for someone who already knows the number.
        ny = my + 56
        self.canvas.create_text(lx0 + 18, ny - 14, text="FINE ADJUST",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        self.setup_aim_nudge_rects = []
        for i, (lbl, delta) in enumerate((("−1.0", -1.0), ("−0.1", -0.1),
                                          ("+0.1", 0.1), ("+1.0", 1.0))):
            bw = 46
            bx0 = lx0 + 18 + i * (bw + 6)
            self.canvas.create_rectangle(bx0, ny, bx0 + bw, ny + 26,
                                         fill=theme.SURFACE_2, outline="")
            self.canvas.create_text(bx0 + bw / 2, ny + 13, text=lbl,
                                    fill=theme.TEXT_2,
                                    font=(theme.ui_font(), 9), anchor="center")
            self.setup_aim_nudge_rects.append((bx0, ny, bx0 + bw, ny + 26, delta))

        self.setup_aim_clear_rect = (lx1 - 76, ny, lx1 - 18, ny + 26)
        self.canvas.create_rectangle(*self.setup_aim_clear_rect,
                                     fill=theme.SURFACE_2, outline="")
        self.canvas.create_text((lx1 - 47), ny + 13, text="Reset",
                                fill=theme.TEXT_3,
                                font=(theme.ui_font(), 8), anchor="center")

        # Calibrate from shots.
        cy = ny + 36
        n_cal = len(self.aim_calib_shots)
        self.setup_aim_start_rect = (lx0 + 18, cy, lx1 - 18, cy + 30)
        self.canvas.create_rectangle(*self.setup_aim_start_rect,
                                     fill=theme.ACCENT_DEEP if self.aim_calibrating
                                     else theme.SURFACE_2,
                                     outline=theme.ACCENT_LINE if self.aim_calibrating
                                     else "")
        if self.aim_calibrating:
            btn_txt = (f"Aim at one target — {n_cal}/{MIN_CALIBRATION_SHOTS} shots"
                       if n_cal < MIN_CALIBRATION_SHOTS
                       else f"Apply median of {n_cal} shots")
        else:
            btn_txt = f"Calibrate from {MIN_CALIBRATION_SHOTS} shots at one target"
        self.canvas.create_text((lx0 + lx1) / 2, cy + 15, text=btn_txt,
                                fill=theme.ACCENT_TEXT if self.aim_calibrating
                                else theme.TEXT_2,
                                font=(theme.ui_font(), 9), anchor="center")
        if self.aim_calibrating and n_cal:
            frac = min(1.0, n_cal / float(MIN_CALIBRATION_SHOTS))
            self.canvas.create_rectangle(lx0 + 18, cy + 27,
                                         lx0 + 18 + (lx1 - lx0 - 36) * frac,
                                         cy + 30, fill=theme.ACCENT, outline="")
        ly += aim_h + 14

        # --- data sources: what is measured vs derived vs estimated ---
        card(lx0, ly, lx1, bot, "DATA SOURCES")
        dy = ly + 34
        for tone, head, sub in (
            (theme.TEXT, "Measured by Nova",
             "Ball speed · launch angles · spin · spin axis"),
            (theme.TEXT_2, "Derived by OpenGolfCoach",
             "Club speed · smash · club path · face angles"),
            (theme.WARN, "Estimated",
             "Strike location — direction only, no club tracking"),
        ):
            self.canvas.create_text(lx0 + 18, dy, text=head, fill=tone,
                                    font=(theme.ui_font(), 9), anchor="nw")
            self.canvas.create_text(lx0 + 18, dy + 16, text=sub,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            dy += 40

        self.canvas.create_line(lx0 + 18, dy + 2, lx1 - 18, dy + 2,
                                fill=theme.HAIRLINE)
        self.canvas.create_text(lx0 + 18, dy + 12, text="WHY SOME VALUES SHOW --",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        for i, line in enumerate((
            "OpenGolfCoach infers club speed from ball data. Below",
            "roughly 90 mph ball speed its model saturates and returns",
            "a constant, so club speed and smash are hidden rather",
            "than shown as a measurement.",
        )):
            self.canvas.create_text(lx0 + 18, dy + 28 + i * 12, text=line,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")

        # ================= RIGHT COLUMN =================
        ry = y
        rx1_cur = rx1
        card(rx0, ry, rx1, bot, "BALANCE BOARDS")

        is_dual = bool(pm and getattr(pm, "board_mode", "single") == "dual")
        self.canvas.create_text(rx0 + 18, ry + 34, text="MODE",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        mw_ = (rx1 - rx0 - 44) / 2
        for i, (lbl, sub, active) in enumerate((
            ("1 Board", "single mat", not is_dual),
            ("2 Boards", "dual plate", is_dual),
        )):
            bx0 = rx0 + 18 + i * (mw_ + 8)
            bx1_ = bx0 + mw_
            self.canvas.create_rectangle(bx0, ry + 48, bx1_, ry + 84,
                                         fill=theme.ACCENT_DEEP if active else theme.SURFACE_2,
                                         outline=theme.ACCENT_LINE if active else "")
            self.canvas.create_text(bx0 + 12, ry + 55, text=lbl,
                                    fill=theme.ACCENT_TEXT if active else theme.TEXT_2,
                                    font=(theme.ui_font(), 10), anchor="nw")
            self.canvas.create_text(bx0 + 12, ry + 70, text=sub,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            if i == 0:
                self.setup_mode_1_rect = (bx0, ry + 48, bx1_, ry + 84)
            else:
                self.setup_mode_2_rect = (bx0, ry + 48, bx1_, ry + 84)

        # --- pair ---
        py = ry + 96
        self.setup_pair_rect = (rx0 + 18, py, rx1 - 18, py + 32)
        self.canvas.create_rectangle(rx0 + 18, py, rx1 - 18, py + 32,
                                     fill=theme.ACCENT_DEEP,
                                     outline=theme.ACCENT_LINE)
        self.canvas.create_text((rx0 + rx1) / 2, py + 16,
                                text="Pair a board over Bluetooth",
                                fill=theme.ACCENT_TEXT,
                                font=(theme.ui_font(), 9), anchor="center")
        self.canvas.create_text(rx0 + 18, py + 40,
                                text="Press the red SYNC button inside the battery compartment",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")

        # --- paired boards ---
        wiz = getattr(pm, "assignment_wizard", None) if pm else None
        wst = wiz.get_status() if wiz else {}
        w_a = wst.get("board_a_weight", 0.0)
        w_b = wst.get("board_b_weight", 0.0)
        phase = wst.get("phase", "idle")

        by = py + 60
        self.canvas.create_text(rx0 + 18, by, text="PAIRED",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        by += 16
        boards = [("Board A", "LEAD (L)", w_a)]
        if is_dual:
            boards.append(("Board B", "TRAIL (R)", w_b))
        for name, foot, kg in boards:
            live = kg > 0.5
            self.canvas.create_rectangle(rx0 + 18, by, rx1 - 18, by + 40,
                                         fill=theme.SURFACE_2, outline="")
            self.canvas.create_oval(rx0 + 30, by + 17, rx0 + 38, by + 25,
                                    fill=theme.ACCENT if live else theme.TEXT_3,
                                    outline="")
            self.canvas.create_text(rx0 + 48, by + 8, text=name,
                                    fill=theme.TEXT,
                                    font=(theme.ui_font(), 10), anchor="nw")
            self.canvas.create_text(rx0 + 48, by + 24, text=foot,
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            self.canvas.create_text(rx1 - 30, by + 12,
                                    text=f"{kg:.1f} kg" if live else "--",
                                    fill=theme.TEXT if live else theme.TEXT_3,
                                    font=(theme.ui_font(), 12), anchor="ne")
            by += 46

        # --- assign left / right (dual only) ---
        if is_dual:
            self.canvas.create_text(rx0 + 18, by, text="ASSIGN LEFT / RIGHT",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            self.canvas.create_text(rx0 + 18, by + 14,
                                    text="Step on each board to tell the app which foot it is under",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
            by += 32
            sw_ = (rx1 - rx0 - 44) / 2
            for i, (lbl, kg) in enumerate((("Step Board A", w_a),
                                           ("Step Board B", w_b))):
                sx0 = rx0 + 18 + i * (sw_ + 8)
                sx1_ = sx0 + sw_
                waiting = (phase == "waiting_left" and i == 0) or \
                          (phase == "waiting_right" and i == 1)
                self.canvas.create_rectangle(sx0, by, sx1_, by + 44,
                                             fill=theme.SURFACE_2,
                                             outline=theme.ACCENT_LINE if waiting else "")
                self.canvas.create_text(sx0 + 12, by + 8, text=lbl,
                                        fill=theme.TEXT_2,
                                        font=(theme.ui_font(), 8), anchor="nw")
                self.canvas.create_text(sx0 + 12, by + 22, text=f"{kg:.1f} kg",
                                        fill=theme.TEXT,
                                        font=(theme.ui_font(), 13), anchor="nw")
                if waiting:
                    self.canvas.create_text(sx1_ - 12, by + 28, text="detecting",
                                            fill=theme.ACCENT_TEXT,
                                            font=(theme.ui_font(), 7), anchor="ne")
                if i == 0:
                    self.setup_step_a_rect = (sx0, by, sx1_, by + 44)
                else:
                    self.setup_step_b_rect = (sx0, by, sx1_, by + 44)
            by += 56
        else:
            self.setup_step_a_rect = None
            self.setup_step_b_rect = None

        # --- calibration ---
        self.canvas.create_text(rx0 + 18, by, text="CALIBRATION",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="nw")
        by += 16
        al = pm.get_alignment_status() if (pm and hasattr(pm, "get_alignment_status")) else {}
        aligning = al.get("active", False)
        rem = al.get("remaining_sec", 0.0)
        in_lead = al.get("in_lead_in", False)
        prog = al.get("progress", 0.0)
        al_msg = al.get("message", "")

        self.setup_align_rect = (rx0 + 18, by, rx1 - 18, by + 40)
        self.canvas.create_rectangle(rx0 + 18, by, rx1 - 18, by + 40,
                                     fill=theme.ACCENT_DEEP if aligning else theme.SURFACE_2,
                                     outline=theme.ACCENT_LINE if aligning else "")
        self.canvas.create_text(rx0 + 30, by + 8, text="50/50 Stance Calibration",
                                fill=theme.ACCENT_TEXT if aligning else theme.TEXT,
                                font=(theme.ui_font(), 9), anchor="nw")
        sub_msg = (al_msg if aligning
                   else "Stand in address, hold still for 4s")
        self.canvas.create_text(rx0 + 30, by + 24, text=sub_msg,
                                fill=theme.WARN if in_lead else theme.TEXT_3,
                                font=(theme.ui_font(), 7), anchor="nw")
        if aligning:
            self.canvas.create_text(rx1 - 30, by + 12, text=f"{rem:.1f}s",
                                    fill=theme.WARN if in_lead else theme.ACCENT_TEXT,
                                    font=(theme.ui_font(), 13), anchor="ne")
            # progress covers the whole lead-in + sample sequence.
            frac = max(0.0, min(1.0, float(prog)))
            self.canvas.create_rectangle(rx0 + 18, by + 37,
                                         rx0 + 18 + (rx1 - rx0 - 36) * frac,
                                         by + 40,
                                         fill=theme.WARN if in_lead else theme.ACCENT,
                                         outline="")
        mult = getattr(obs_server.obs_state, "balance_multiplier", None) or [1.0, 1.0]
        try:
            self.canvas.create_text(rx0 + 18, by + 46,
                                    text=f"Applied: L {float(mult[0]):.2f}   ·   R {float(mult[1]):.2f}",
                                    fill=theme.TEXT_3,
                                    font=(theme.ui_font(), 7), anchor="nw")
        except Exception:
            pass
        by += 66

        self.setup_tare_rect = (rx0 + 18, by, rx1 - 18, by + 30)
        self.canvas.create_rectangle(rx0 + 18, by, rx1 - 18, by + 30,
                                     fill=theme.SURFACE_2, outline="")
        self.canvas.create_text((rx0 + rx1) / 2, by + 15,
                                text="Tare — zero both boards (step off first)",
                                fill=theme.TEXT_2,
                                font=(theme.ui_font(), 8), anchor="center")

        # ---- footer --------------------------------------------------------
        self.canvas.create_line(x0, h - 26, x1, h - 26, fill=theme.HAIRLINE)
        self.canvas.create_text(x0, h - 18, text="Setup", fill=theme.TEXT_3,
                                font=(theme.ui_font(), 7), anchor="nw")
        self.canvas.create_text(x1, h - 18, text="Changes apply immediately",
                                fill=theme.TEXT_3, font=(theme.ui_font(), 7),
                                anchor="ne")

    def draw_balance_hardware_modal(self, w, h):
        # Modal dark backdrop
        self.canvas.create_rectangle(0, 0, w, h, fill="#000000", stipple="gray50")
        mw, mh = 580, 540
        mx1, my1 = (w - mw) // 2, (h - mh) // 2
        mx2, my2 = mx1 + mw, my1 + mh
        self.balance_modal_box_rect = (mx1, my1, mx2, my2)

        # Modal Window Container
        self.canvas.create_rectangle(mx1, my1, mx2, my2, fill=theme.SURFACE, outline=theme.ACCENT_TEXT, width=2)
        self.canvas.create_text(mx1 + 20, my1 + 22, text="⚙️ WII BALANCE BOARD HARDWARE & PAIRING", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 10, "bold"), anchor="w")

        # Close button [X]
        self.balance_modal_close_rect = (mx2 - 36, my1 + 10, mx2 - 12, my1 + 34)
        self.canvas.create_rectangle(mx2 - 36, my1 + 10, mx2 - 12, my1 + 34, fill="#1E222E", outline="#383E50")
        self.canvas.create_text(mx2 - 24, my1 + 22, text="✕", fill=theme.TEXT, font=(theme.ui_font(), 9, "bold"))

        pm = obs_server.pressure_manager if hasattr(obs_server, "pressure_manager") else None
        board_mode = pm.board_mode if pm else "single"
        is_dual = (board_mode == "dual")

        # --- SECTION 0: 1-BOARD VS 2-BOARDS MODE SELECTOR ---
        mode_y1 = my1 + 42
        mode_y2 = mode_y1 + 30
        half_mw = (mx2 - mx1 - 50) // 2
        m1_x1, m1_x2 = mx1 + 20, mx1 + 20 + half_mw
        m2_x1, m2_x2 = m1_x2 + 10, mx2 - 20

        self.balance_modal_mode_1_rect = (m1_x1, mode_y1, m1_x2, mode_y2)
        bg1 = theme.SURFACE_2 if not is_dual else theme.SURFACE
        bd1 = theme.ACCENT_TEXT if not is_dual else theme.HAIRLINE
        col1 = theme.ACCENT_TEXT if not is_dual else theme.TEXT_2
        self.canvas.create_rectangle(m1_x1, mode_y1, m1_x2, mode_y2, fill=bg1, outline=bd1, width=2 if not is_dual else 1)
        self.canvas.create_text((m1_x1 + m1_x2) // 2, (mode_y1 + mode_y2) // 2, text="🦶 1 Board (Single Mat)", fill=col1, font=(theme.ui_font(), 8, "bold" if not is_dual else "normal"))

        self.balance_modal_mode_2_rect = (m2_x1, mode_y1, m2_x2, mode_y2)
        bg2 = theme.SURFACE_2 if is_dual else theme.SURFACE
        bd2 = theme.ACCENT_TEXT if is_dual else theme.HAIRLINE
        col2 = theme.ACCENT_TEXT if is_dual else theme.TEXT_2
        self.canvas.create_rectangle(m2_x1, mode_y1, m2_x2, mode_y2, fill=bg2, outline=bd2, width=2 if is_dual else 1)
        self.canvas.create_text((m2_x1 + m2_x2) // 2, (mode_y1 + mode_y2) // 2, text="🦶🦶 2 Boards (Dual Plate)", fill=col2, font=(theme.ui_font(), 8, "bold" if is_dual else "normal"))

        # --- SECTION 0B: DUAL-BOARD FOOT ASSIGNMENT WIZARD CARD (When Dual Mode is Active) ---
        next_y = mode_y2 + 8
        if is_dual:
            wiz = pm.assignment_wizard if pm else None
            wiz_status = wiz.get_status() if wiz else {"phase": "idle", "message": "Click Calibrate to begin assignment", "board_a_weight": 0.0, "board_b_weight": 0.0}
            wiz_phase = wiz_status.get("phase", "idle")
            w_a = wiz_status.get("board_a_weight", 0.0)
            w_b = wiz_status.get("board_b_weight", 0.0)

            card_h = 68 if wiz_phase in ("waiting_left", "waiting_right") else 56
            card_y1 = next_y
            card_y2 = card_y1 + card_h
            self.canvas.create_rectangle(mx1 + 20, card_y1, mx2 - 20, card_y2, fill=theme.BG, outline="#38BDF8" if wiz_phase != "idle" else theme.HAIRLINE)

            # Status Message
            if wiz_phase == "waiting_left":
                p_text = "🦶 Step on the board under your LEFT foot (>5kg)"
                p_col = theme.ACCENT_TEXT
            elif wiz_phase == "waiting_right":
                p_text = "🦶 Now step on the board under your RIGHT foot (>5kg)"
                p_col = theme.WARN
            elif wiz_phase == "complete":
                p_text = "✓ Both boards assigned (Left: Board A, Right: Board B)"
                p_col = theme.ACCENT_TEXT
            else:
                p_text = "Step on boards to assign Left & Right feet:"
                p_col = "#CBD5E1"

            self.canvas.create_text(mx1 + 32, card_y1 + 14, text=p_text, fill=p_col, font=(theme.ui_font(), 8, "bold"), anchor="w")
            self.canvas.create_text(mx1 + 32, card_y1 + 32, text=f"Board A: {w_a:.1f} kg   |   Board B: {w_b:.1f} kg", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")

            # Step simulation chips during wizard
            if wiz_phase in ("waiting_left", "waiting_right"):
                sa_x1 = mx1 + 32
                sa_x2 = sa_x1 + 105
                sb_x1 = sa_x2 + 8
                sb_x2 = sb_x1 + 105
                s_y1 = card_y1 + 44
                s_y2 = s_y1 + 18

                self.balance_modal_step_a_rect = (sa_x1, s_y1, sa_x2, s_y2)
                self.canvas.create_rectangle(sa_x1, s_y1, sa_x2, s_y2, fill=theme.HAIRLINE, outline=theme.ACCENT_TEXT)
                self.canvas.create_text((sa_x1 + sa_x2) // 2, (s_y1 + s_y2) // 2, text="🦶 Step Board A", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 7, "bold"))

                self.balance_modal_step_b_rect = (sb_x1, s_y1, sb_x2, s_y2)
                self.canvas.create_rectangle(sb_x1, s_y1, sb_x2, s_y2, fill=theme.HAIRLINE, outline=theme.DANGER)
                self.canvas.create_text((sb_x1 + sb_x2) // 2, (s_y1 + s_y2) // 2, text="🦶 Step Board B", fill=theme.DANGER, font=(theme.ui_font(), 7, "bold"))
            else:
                self.balance_modal_step_a_rect = None
                self.balance_modal_step_b_rect = None

            # Calibrate / Start Button
            btn_w = 135
            b_x2 = mx2 - 32
            b_x1 = b_x2 - btn_w
            b_y1 = card_y1 + 12
            b_y2 = card_y2 - 12
            self.balance_modal_assign_btn_rect = (b_x1, b_y1, b_x2, b_y2)
            btn_lbl = "🎯 Re-Assign" if wiz_phase == "complete" else ("⏳ Detecting..." if wiz_phase in ("waiting_left", "waiting_right") else "🎯 Start Wizard")
            btn_bg = "#0284C7" if wiz_phase != "idle" else theme.HAIRLINE
            self.canvas.create_rectangle(b_x1, b_y1, b_x2, b_y2, fill=btn_bg, outline="#38BDF8")
            self.canvas.create_text((b_x1 + b_x2) // 2, (b_y1 + b_y2) // 2, text=btn_lbl, fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"))

            next_y = card_y2 + 8
        else:
            self.balance_modal_assign_btn_rect = None
            self.balance_modal_step_a_rect = None
            self.balance_modal_step_b_rect = None

        # --- SECTION 1: BLUETOOTH PAIRING PIN CARD ---
        from src.hardware.pressure.bluetooth_windows import (
            format_mac_display,
            get_host_bluetooth_mac,
            mac_to_wii_pin,
            mac_to_wii_pin_display,
        )
        mac = get_host_bluetooth_mac() or ""
        if mac:
            pin_raw = mac_to_wii_pin(mac)
            pin_disp = mac_to_wii_pin_display(mac)
            mac_disp = format_mac_display(mac)
        else:
            mac_disp = "Default / Auto (38:FC:98:3B:B4:DC)"
            pin_raw = mac_to_wii_pin("38FC983BB4DC")
            pin_disp = mac_to_wii_pin_display("38FC983BB4DC")

        self.balance_modal_pin_text = pin_raw

        pin_card_y1 = next_y
        pin_card_y2 = pin_card_y1 + 130
        self.canvas.create_rectangle(mx1 + 20, pin_card_y1, mx2 - 20, pin_card_y2, fill="#171B2A", outline=theme.HAIRLINE)
        self.canvas.create_text(mx1 + 32, pin_card_y1 + 14, text="WINDOWS BLUETOOTH PAIRING PIN", fill=theme.TEXT_3, font=(theme.ui_font(), 7, "bold"), anchor="w")
        self.canvas.create_text(mx1 + 32, pin_card_y1 + 28, text=f"Host Adapter MAC: {mac_disp}", fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")

        # Big Glowing PIN Box. Starts at +48, not +40: the MAC line above
        # baselines at +28 and a real UI face is tall enough that the box
        # edge cut through its descenders.
        p_box_y1 = pin_card_y1 + 48
        p_box_y2 = p_box_y1 + 44
        self.canvas.create_rectangle(mx1 + 32, p_box_y1, mx2 - 32, p_box_y2, fill="#0B0F17", outline=theme.ACCENT_TEXT, width=1)
        self.canvas.create_text((mx1 + mx2) // 2, (p_box_y1 + p_box_y2) // 2, text=pin_disp, fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 16, "bold"))

        # Action Buttons under PIN (Copy PIN + Open BT Settings)
        act_y1 = p_box_y2 + 8
        act_y2 = act_y1 + 28
        half_w = (mx2 - mx1 - 74) // 2
        btn_copy_x1 = mx1 + 32
        btn_copy_x2 = btn_copy_x1 + half_w
        btn_open_x1 = btn_copy_x2 + 10
        btn_open_x2 = mx2 - 32

        self.balance_modal_copy_pin_rect = (btn_copy_x1, act_y1, btn_copy_x2, act_y2)
        self.canvas.create_rectangle(btn_copy_x1, act_y1, btn_copy_x2, act_y2, fill=theme.SURFACE_2, outline=theme.ACCENT_TEXT)
        self.canvas.create_text((btn_copy_x1 + btn_copy_x2) // 2, (act_y1 + act_y2) // 2, text="📋 Copy PIN to Clipboard", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"))

        self.balance_modal_bt_settings_rect = (btn_open_x1, act_y1, btn_open_x2, act_y2)
        self.canvas.create_rectangle(btn_open_x1, act_y1, btn_open_x2, act_y2, fill="#1E2A3A", outline="#38BDF8")
        self.canvas.create_text((btn_open_x1 + btn_open_x2) // 2, (act_y1 + act_y2) // 2, text="🌐 Open Bluetooth Settings", fill="#38BDF8", font=(theme.ui_font(), 8, "bold"))

        # --- SECTION 2: HARDWARE CONTROLS ---
        hw_y1 = pin_card_y2 + 8
        hw_y2 = hw_y1 + 38
        is_sim = pm.is_simulator if pm else False

        tot_hw_w = mx2 - mx1 - 40
        btn_w3 = (tot_hw_w - 20) // 3
        b1_x1, b1_x2 = mx1 + 20, mx1 + 20 + btn_w3
        b2_x1, b2_x2 = b1_x2 + 10, b1_x2 + 10 + btn_w3
        b3_x1, b3_x2 = b2_x2 + 10, mx2 - 20

        # Pair over Bluetooth. The click handler for this existed but nothing
        # ever assigned balance_modal_pair_rect, so pairing was unreachable
        # from the UI. Its own full-width row above the three action buttons.
        pair_y2 = hw_y1 - 8
        pair_y1 = pair_y2 - 26
        self.balance_modal_pair_rect = (b1_x1, pair_y1, mx2 - 20, pair_y2)
        self.canvas.create_rectangle(b1_x1, pair_y1, mx2 - 20, pair_y2,
                                     fill=theme.ACCENT_DEEP,
                                     outline=theme.ACCENT_LINE)
        self.canvas.create_text((b1_x1 + mx2 - 20) // 2,
                                (pair_y1 + pair_y2) // 2,
                                text="Pair board over Bluetooth  ·  hold SYNC first",
                                fill=theme.ACCENT_TEXT,
                                font=(theme.ui_font(), 8, "bold"))

        # Button 1: Tare Zero
        self.balance_modal_tare_rect = (b1_x1, hw_y1, b1_x2, hw_y2)
        self.canvas.create_rectangle(b1_x1, hw_y1, b1_x2, hw_y2, fill=theme.HAIRLINE, outline=theme.ACCENT_TEXT)
        self.canvas.create_text((b1_x1 + b1_x2) // 2, (hw_y1 + hw_y2) // 2, text="⚖️ Tare Resting Zero", fill=theme.ACCENT_TEXT, font=(theme.ui_font(), 8, "bold"))

        # Button 2: 50/50 Stance Calibration (5s Lead-in + 4s Sample)
        align_st = pm.get_alignment_status() if (pm and hasattr(pm, "get_alignment_status")) else {"active": False, "remaining_sec": 0.0, "in_lead_in": False, "message": "Idle"}
        is_aligning = align_st.get("active", False)
        in_lead = align_st.get("in_lead_in", False)
        rem_sec = align_st.get("remaining_sec", 0.0)

        self.balance_modal_align_rect = (b2_x1, hw_y1, b2_x2, hw_y2)
        if is_aligning:
            if in_lead:
                align_bg = theme.ACCENT_DEEP  # Warm amber/orange during lead-in
                align_bd = theme.WARN
                align_txt = f"⏳ Step On & Settle... {rem_sec:.0f}s"
            else:
                align_bg = "#0369A1"  # Cyan/blue during hold
                align_bd = "#38BDF8"
                align_txt = f"🎯 Hold Stance... {rem_sec:.1f}s"
        else:
            align_bg = theme.HAIRLINE
            align_bd = theme.ACCENT_TEXT
            align_txt = "🎯 50/50 Stance Calibrate"

        self.canvas.create_rectangle(b2_x1, hw_y1, b2_x2, hw_y2, fill=align_bg, outline=align_bd, width=2 if is_aligning else 1)
        self.canvas.create_text((b2_x1 + b2_x2) // 2, (hw_y1 + hw_y2) // 2, text=align_txt, fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"))

        # Button 3: Simulator Toggle
        self.balance_modal_sim_rect = (b3_x1, hw_y1, b3_x2, hw_y2)
        sim_col = theme.ACCENT_TEXT if is_sim else theme.TEXT_3
        self.canvas.create_rectangle(b3_x1, hw_y1, b3_x2, hw_y2, fill=theme.SURFACE, outline=sim_col)
        self.canvas.create_text((b3_x1 + b3_x2) // 2, (hw_y1 + hw_y2) // 2, text=f"Simulator: {'[ON]' if is_sim else '[OFF]'}", fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"))

        # Button 4: Stance WIDTH calibration (shift left, then right).
        # Separate row so the three buttons above keep their width.
        sw_y1 = hw_y2 + 8
        sw_y2 = sw_y1 + (hw_y2 - hw_y1)
        st_st = pm.get_stance_width_status() if (pm and hasattr(pm, "get_stance_width_status")) else {"active": False, "state": "idle", "instruction": "", "stance_width_mm": None}
        sw_active = st_st.get("active", False)
        sw_mm = st_st.get("stance_width_mm")

        self.balance_modal_stance_rect = (b1_x1, sw_y1, b3_x2, sw_y2)
        if sw_active:
            sw_bg, sw_bd = theme.ACCENT_DEEP, theme.ACCENT_LINE
            sw_txt = f"📏 {st_st.get('instruction', '')}"
        elif sw_mm:
            sw_bg, sw_bd = theme.SURFACE, theme.TEXT_3
            sw_txt = f"📏 Stance Width: {sw_mm:.0f} mm  (tap to redo)"
        else:
            sw_bg, sw_bd = theme.SURFACE, theme.TEXT_3
            sw_txt = "📏 Measure Stance Width (shift L, then R)"
        self.canvas.create_rectangle(b1_x1, sw_y1, b3_x2, sw_y2, fill=sw_bg, outline=sw_bd, width=2 if sw_active else 1)
        self.canvas.create_text((b1_x1 + b3_x2) // 2, (sw_y1 + sw_y2) // 2, text=sw_txt, fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"))

        # --- SECTION 3: STEP-BY-STEP PAIRING INSTRUCTIONS ---
        guide_y1 = sw_y2 + 8
        guide_y2 = my2 - 12
        self.canvas.create_rectangle(mx1 + 20, guide_y1, mx2 - 20, guide_y2, fill="#141824", outline="#1F2536")
        self.canvas.create_text(mx1 + 32, guide_y1 + 12, text="PAIRING & CALIBRATION INSTRUCTIONS", fill=theme.TEXT_3, font=(theme.ui_font(), 7, "bold"), anchor="w")

        # Alignment feedback banner if present
        msg = align_st.get("message", "")
        if msg and msg != "Idle":
            msg_col = theme.ACCENT_TEXT if msg.startswith("✓") else (theme.WARN if "Sampling" in msg or "Stand" in msg else theme.DANGER)
            self.canvas.create_text(mx2 - 32, guide_y1 + 12, text=msg, fill=msg_col, font=(theme.ui_font(), 7, "bold"), anchor="e")

        steps = [
            "1. Press red SYNC button on board(s) (4 LEDs blink) → Open BT Settings → Paste PIN.",
            "2. For 2-Board setups: Select '2 Boards' above and click 'Start Wizard' to identify feet.",
            "3. Step on Left board first, then Right board when prompted.",
            "4. Step off and click 'Tare Resting Zero' → Stand at address and click '50/50 Stance (4s)'."
        ]
        for idx, s in enumerate(steps):
            self.canvas.create_text(mx1 + 32, guide_y1 + 26 + (idx * 14), text=s, fill="#CBD5E1", font=(theme.ui_font(), 7), anchor="w")

def main():
    t_ws = threading.Thread(target=websocket_worker, daemon=True)
    t_ws.start()

    # GSPro range-shot poller (no-op unless SPS_SHOT_SOURCE=gspro). Feeds the
    # same shot_queue as Nova; see gspro_worker for source-selection rules.
    t_gspro = threading.Thread(target=gspro_worker, daemon=True)
    t_gspro.start()

    # Start OBS Studio Browser Source Overlay Server on port 9321
    obs_server.launch_obs_server_thread()

    root = tk.Tk()
    # Default to 1080p. Clamp to the display so the window can never open with
    # its lower-right corner (footer, launch button, tendencies) off the
    # desktop, but allow an exact match: on a 1920x1080 screen the intent is
    # a full 1920x1080 window, positioned at the origin, not a shrunken one.
    DEFAULT_W, DEFAULT_H = 1920, 1080
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    if scr_w >= DEFAULT_W and scr_h >= DEFAULT_H:
        win_w, win_h = DEFAULT_W, DEFAULT_H
    else:
        # Smaller display: leave room for a taskbar/panel.
        win_w = min(DEFAULT_W, scr_w - 40)
        win_h = min(DEFAULT_H, scr_h - 80)
    pos_x = max(0, (scr_w - win_w) // 2)
    pos_y = max(0, (scr_h - win_h) // 3)
    root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    root.minsize(1100, 720)
    app = ShanktuaryApp(root)  # noqa: F841  # keepalive — do not delete (holds the Tk app alive until mainloop() returns)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass

if __name__ == "__main__":
    main()

