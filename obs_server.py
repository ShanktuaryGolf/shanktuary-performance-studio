#!/usr/bin/env python3
"""
Shanktuary Performance Studio - OBS Overlay & Web Configurator Server
-----------------------------------------------------------------------
Runs an HTTP + WebSocket server in a background thread on port 9321.
Based on the proven architecture from ShanktuaryGolf/SwingLab:
  - Serves http://localhost:9321         -> Transparent OBS Browser Source Overlay (overlay.html)
  - Serves http://localhost:9321/config   -> Interactive Web Configurator UI (config.html)
  - Serves /api/layout                   -> GET/POST saved layout preferences (overlay_layout.json)
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
    
    script_assets = SCRIPT_DIR / "assets"
    if script_assets.exists():
        return script_assets
        
    cwd_assets = Path.cwd() / "assets"
    if cwd_assets.exists():
        return cwd_assets
        
    return script_assets

ASSETS_DIR = get_assets_dir()
CONFIG_DIR = Path.home() / ".config" / "shanktuary"
LAYOUT_FILE = CONFIG_DIR / "overlay_layout.json"

DEFAULT_LAYOUT = {
    "visuals": {
        "divot": True,
        "face_impact": True,
        "overhead": True
    },
    "metrics": {
        "ball_speed": True,
        "club_speed": True,
        "carry": True,
        "total": False,
        "smash": True,
        "launch_angle": True,
        "push_pull": False,
        "total_spin": True,
        "sidespin": False,
        "spin_axis": True,
        "club_path": True,
        "face_angle": True,
        "offline": True
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
            # Broadcast layout update to OBS browser clients
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
        # Silence verbose HTTP logging
        return

    def do_GET(self):
        parsed_path = self.path.split("?")[0].rstrip("/")
        if not parsed_path:
            parsed_path = "/"

        assets_dir = get_assets_dir()

        # Handle WebSocket Handshake
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.handle_websocket()
            return

        if parsed_path == "/" or parsed_path == "/overlay":
            self.serve_file(assets_dir / "overlay.html", "text/html; charset=utf-8")
        elif parsed_path == "/config":
            self.serve_file(assets_dir / "config.html", "text/html; charset=utf-8")
        elif parsed_path == "/api/layout":
            self.send_json(obs_state.load_layout())
        elif parsed_path == "/api/shot":
            with obs_state.lock:
                shot = obs_state.latest_shot or {}
            self.send_json(shot)
        elif parsed_path.startswith("/assets/"):
            asset_filename = parsed_path.replace("/assets/", "")
            file_path = assets_dir / asset_filename
            mime = "image/png" if file_path.suffix == ".png" else "text/plain"
            self.serve_file(file_path, mime)
        else:
            self.send_error(404, f"File Not Found: {parsed_path}")

    def do_POST(self):
        parsed_path = self.path.split("?")[0]
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
            self.send_error(404, "File Not Found")

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

        # Send initial state and layout
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

        # Keep socket open in read loop
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
