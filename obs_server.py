#!/usr/bin/env python3
"""
Shanktuary Performance Studio - OBS Overlay & Web Configurator Server
-----------------------------------------------------------------------
Runs an HTTP + WebSocket server in a background thread on port 9321.
Based on the proven architecture from ShanktuaryGolf/SwingLab:
  - Serves http://localhost:9321         -> Transparent OBS Browser Source Overlay (overlay.html)
  - Serves http://localhost:9321?edit=true-> Interactive Drag, Drop & Resize Widget Canvas Editor
  - Serves http://localhost:9321?mode=projector -> Fullscreen Floor Projector Mat Mode
  - Serves http://localhost:9321/config   -> Interactive Web Configurator UI (config.html)
  - Serves /api/layout                   -> GET/POST saved layout preferences, widget positions, and divot physical calibration
  - Serves /api/shot                     -> GET last shot payload
  - Broadcasts live shot events to connected OBS browser sources over WebSocket
"""

import http.server
import socketserver
import threading
import json
import os
import time
import socket
import base64
import struct
import sys
from pathlib import Path

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
    
    candidates = [
        SCRIPT_DIR / "assets",
        SCRIPT_DIR / "shanktuary-performance-studio" / "assets",
        Path.cwd() / "assets",
        Path.cwd() / "shanktuary-performance-studio" / "assets",
        Path("/home/sean/shanktuary-performance-studio/assets"),
        Path("/home/sean/assets"),
        Path("/home/sean/sps/assets")
    ]
    
    for path in candidates:
        if path.exists() and (path / "config.html").exists():
            return path

    return SCRIPT_DIR / "assets"

ASSETS_DIR = get_assets_dir()
CONFIG_DIR = Path.home() / ".config" / "shanktuary"
LAYOUT_FILE = CONFIG_DIR / "overlay_layout.json"

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
        self.ensure_layout_file()

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

    def push_shot(self, shot_data):
        with self.lock:
            self.latest_shot = shot_data
        
        # Trigger shot impact capture in pressure buffer
        if 'pressure_manager' in globals():
            def on_pressure_captured(trace_frames):
                shot_data["pressure_trace"] = trace_frames
                pressure_manager.last_shot_trace = trace_frames
                self.broadcast({"type": "shot_pressure", "shot_id": shot_data.get("shotId"), "trace": trace_frames})

            pressure_manager.buffer.trigger_shot_impact(callback=on_pressure_captured)

        self.broadcast({"type": "shot", "data": shot_data})

    def broadcast(self, message):
        payload = json.dumps(message)
        frame = self.make_ws_frame(payload)
        with self.lock:
            dead = set()
            for client in self.ws_clients:
                try:
                    client.sendall(frame)
                except Exception:
                    dead.add(client)
            self.ws_clients -= dead

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
        self.running = False
        self.thread = None
        self.latest_frame = None
        self.last_shot_trace = None
        self.lock = threading.Lock()
        self._init_subsystem()

    def _init_subsystem(self):
        try:
            from src.hardware.pressure import TareOffsets
            from src.processing.pressure import (
                CoPCalculator,
                TorqueCalculator,
                SwingDetector,
                ShotSynchronizedPressureBuffer,
            )
            self.cop_calc = CoPCalculator()
            self.torque_calc = TorqueCalculator()
            self.swing_det = SwingDetector()
            self.buffer = ShotSynchronizedPressureBuffer(capacity=600)
            self.tare_offsets = TareOffsets()
            self.backend = None
            self._wiz_backend_a = None
            self._wiz_backend_b = None
            self._last_reconnect_attempt = 0.0
            try:
                self.backend = self._create_hardware_backend()
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
        while self.running:
            try:
                # 0. Hardware auto-reconnect if not in simulator mode, no backend open, and wizard not active
                is_wiz_active = bool(self.assignment_wizard and self.assignment_wizard.phase in ("waiting_left", "waiting_right"))
                if not self.is_simulator and not is_wiz_active and (not self.backend or not self.backend.is_open):
                    now = time.time()
                    if now - self._last_reconnect_attempt >= 2.0:
                        self._last_reconnect_attempt = now
                        with self.lock:
                            try:
                                self.backend = self._create_hardware_backend()
                            except Exception:
                                pass

                # 1. Wizard multi-board polling
                wiz = self.assignment_wizard
                if wiz and wiz.phase in ("waiting_left", "waiting_right"):
                    w_a = wiz.board_a_weight
                    w_b = wiz.board_b_weight
                    if self._wiz_backend_a and self._wiz_backend_b:
                        rd_a = self._wiz_backend_a.read()
                        rd_b = self._wiz_backend_b.read()
                        if rd_a:
                            w_a = rd_a.total_weight
                        if rd_b:
                            w_b = rd_b.total_weight
                    elif self._wiz_backend_a and not self._wiz_backend_b:
                        rd_a = self._wiz_backend_a.read()
                        if rd_a:
                            w_a = rd_a.top_left + rd_a.bottom_left
                            w_b = rd_a.top_right + rd_a.bottom_right
                    elif self.backend and self.backend.is_open:
                        rd = self.backend.read()
                        if rd:
                            w_a = rd.top_left + rd.bottom_left
                            w_b = rd.top_right + rd.bottom_right

                    if w_a > 0.0 or w_b > 0.0:
                        self.update_assignment_wizard(w_a, w_b)

                # 2. Standard stream loop
                if self.backend and self.backend.is_open:
                    reading = self.backend.read()
                    if reading:
                        tared = self.tare_offsets.apply(reading) if self.tare_offsets else reading
                        cop = self.cop_calc.compute(tared) if self.cop_calc else None
                        if cop:
                            torque = self.torque_calc.update(cop) if self.torque_calc else None
                            phase = self.swing_det.update(cop).value if self.swing_det else "Address"
                            frame = self.buffer.push(cop, torque=torque, phase=phase)
                            with self.lock:
                                self.latest_frame = frame

                            now = time.time()
                            if now - last_broadcast >= 0.033:  # ~30Hz broadcast rate for smooth UI rendering
                                obs_state.broadcast({"type": "pressure", "data": frame})
                                last_broadcast = now
            except Exception:
                pass
            time.sleep(0.012)

    def tare(self):
        with self.lock:
            from src.hardware.pressure import TareOffsets
            if self.latest_frame and "raw_cells" in self.latest_frame:
                rc = self.latest_frame["raw_cells"]
                self.tare_offsets = TareOffsets(
                    top_left=rc[0], top_right=rc[1], bottom_left=rc[2], bottom_right=rc[3]
                )
            else:
                self.tare_offsets = TareOffsets(
                    top_left=0.0, top_right=0.0, bottom_left=0.0, bottom_right=0.0
                )
            return True

    def _create_hardware_backend(self, device_path=None):
        """Create hardware backend appropriate for host OS (Evdev on Linux, Hid on Windows/macOS)."""
        if sys.platform == "win32":
            try:
                from src.hardware.pressure.hid_backend import HidBackend
                path = device_path.encode("utf-8") if isinstance(device_path, str) else device_path
                b = HidBackend(device_path=path)
                b.open()
                return b
            except Exception as e:
                print(f"[!] Error creating Windows HID backend for path={device_path}: {e}")
                return None
        else:
            try:
                from src.hardware.pressure.evdev_backend import EvdevBackend
                b = EvdevBackend(device_path=device_path)
                b.open()
                return b
            except Exception:
                try:
                    from src.hardware.pressure.hid_backend import HidBackend
                    path = device_path.encode("utf-8") if isinstance(device_path, str) else device_path
                    b = HidBackend(device_path=path)
                    b.open()
                    return b
                except Exception:
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
                    from src.hardware.pressure.evdev_backend import enumerate_board_devices
                    dev_paths = enumerate_board_devices()
                except Exception:
                    pass

            if len(dev_paths) >= 2:
                b_a_id = dev_paths[0]
                b_b_id = dev_paths[1]
                self._wiz_backend_a = self._create_hardware_backend(b_a_id)
                self._wiz_backend_b = self._create_hardware_backend(b_b_id)
            elif len(dev_paths) == 1:
                b_a_id = dev_paths[0]
                b_b_id = "Board B"
                self._wiz_backend_a = self._create_hardware_backend(b_a_id)
                self._wiz_backend_b = None
            else:
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
                self.start_assignment_wizard()
            phase, msg = self.assignment_wizard.update(weight_a, weight_b)
            if phase == "complete" or getattr(phase, "value", phase) == "complete":
                self.assigned_left = self.assignment_wizard.left_board
                self.assigned_right = self.assignment_wizard.right_board

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
            return {
                "connected": self.backend.is_open if self.backend else False,
                "mode": "simulator" if self.is_simulator else "hardware",
                "board_mode": self.board_mode,
                "is_dual": self.board_mode == "dual",
                "assigned_left": self.assigned_left,
                "assigned_right": self.assigned_right,
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

        if parsed_path in ["/", "/overlay", "/divot", "/projector"]:
            self.serve_file(assets_dir / "overlay.html", "text/html; charset=utf-8")
        elif parsed_path in ["/config", "/config.html"]:
            self.serve_file(assets_dir / "config.html", "text/html; charset=utf-8")
        elif parsed_path == "/range":
            self.serve_file(assets_dir / "range" / "index.html", "text/html; charset=utf-8")
        elif parsed_path == "/api/layout":
            self.send_json(obs_state.load_layout())
        elif parsed_path == "/api/shot":
            with obs_state.lock:
                shot = obs_state.latest_shot or {}
            self.send_json(shot)
        elif parsed_path == "/api/pressure/status":
            self.send_json(pressure_manager.get_status())
        elif parsed_path == "/api/pressure/shot":
            self.send_json({"trace": pressure_manager.last_shot_trace or []})
        elif parsed_path == "/api/pressure/pin":
            try:
                from src.hardware.pressure.bluetooth_windows import (
                    get_host_bluetooth_mac,
                    mac_to_wii_pin,
                    mac_to_wii_pin_display,
                    mac_has_zero_byte,
                    format_mac_display,
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
        elif parsed_path.startswith("/assets/"):
            asset_filename = parsed_path.replace("/assets/", "")
            file_path = assets_dir / asset_filename
            import mimetypes
            mime, _ = mimetypes.guess_type(file_path)
            if not mime: mime = "application/octet-stream"
            self.serve_file(file_path, mime)
        elif parsed_path.startswith("/range/"):
            asset_filename = parsed_path.replace("/range/", "")
            file_path = assets_dir / "range" / asset_filename
            import mimetypes
            mime, _ = mimetypes.guess_type(file_path)
            if not mime: mime = "application/octet-stream"
            self.serve_file(file_path, mime)
        elif parsed_path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404, f"File Not Found: {parsed_path}")

    def do_POST(self):
        parsed_path = self.path.split("?")[0].rstrip("/")
        if parsed_path == "/api/layout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                layout_data = json.loads(body)
                success = obs_state.save_layout(layout_data)
                self.send_json({"status": "ok" if success else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/tare":
            ok = pressure_manager.tare()
            self.send_json({"status": "ok" if ok else "error"})
        elif parsed_path == "/api/pressure/simulator":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
                enabled = data.get("enabled", True)
                pressure_manager.set_simulator(enabled)
                self.send_json({"status": "ok", "mode": "simulator" if enabled else "hardware"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/open_bt_settings":
            try:
                from src.hardware.pressure.bluetooth_windows import open_windows_bluetooth_settings
                ok = open_windows_bluetooth_settings()
                self.send_json({"status": "ok" if ok else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=500)
        elif parsed_path == "/api/pressure/mode":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
                mode = data.get("mode", "single")
                new_mode = pressure_manager.set_board_mode(mode)
                self.send_json({"status": "ok", "board_mode": new_mode})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, code=400)
        elif parsed_path == "/api/pressure/assign":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
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
            self.send_error(404, f"File Not Found: {filepath}")

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

        raw_sock = self.connection
        with obs_state.lock:
            obs_state.ws_clients.add(raw_sock)

        with obs_state.lock:
            current_shot = obs_state.latest_shot
        
        init_msg = json.dumps({
            "type": "init",
            "layout": obs_state.load_layout(),
            "data": current_shot
        })
        try:
            raw_sock.sendall(obs_state.make_ws_frame(init_msg))
        except Exception:
            pass

        try:
            while True:
                data = raw_sock.recv(1024)
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
