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
        "offline": {"x": 1780, "y": 970, "w": 140, "h": 70, "visible": False}
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

        if parsed_path == "/" or parsed_path == "/overlay":
            self.serve_file(assets_dir / "overlay.html", "text/html; charset=utf-8")
        elif parsed_path == "/config":
            self.serve_file(assets_dir / "config.html", "text/html; charset=utf-8")
        elif parsed_path == "/range":
            self.serve_file(assets_dir / "range" / "index.html", "text/html; charset=utf-8")
        elif parsed_path == "/api/layout":
            self.send_json(obs_state.load_layout())
        elif parsed_path == "/api/shot":
            with obs_state.lock:
                shot = obs_state.latest_shot or {}
            self.send_json(shot)
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

def start_obs_server():
    try:
        server = ThreadedHTTPServer(("0.0.0.0", OBS_PORT), OBSHTTPRequestHandler)
        print(f"[+] Started OBS Overlay Server on http://localhost:{OBS_PORT}")
        print(f"[+] OBS Web Configurator available at http://localhost:{OBS_PORT}/config")
        server.serve_forever()
    except Exception as e:
        print(f"[!] Error starting OBS Overlay Server: {e}")

def launch_obs_server_thread():
    t = threading.Thread(target=start_obs_server, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    start_obs_server()
