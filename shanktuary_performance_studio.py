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

import socket
import base64
import os
import struct
import json
import time
import math
import threading
import queue
import webbrowser
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageOps
import obs_server

# Configuration & Logging
FALLBACK_NOVA_HOST = "192.168.40.249"
FALLBACK_NOVA_PORT = 2920

SESSION_LOG_PATH = "/home/sean/shanktuary_session_history.json"

# Club Image Assets
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OVERHEAD_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_overhead.png")
FACE_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_face.png")
SIDE_PATH = os.path.join(SCRIPT_DIR, "assets", "iron_side.png")

shot_queue = queue.Queue()

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
        from zeroconf import Zeroconf, ServiceBrowser

        class NovaMDNSListener:
            def __init__(self):
                self.found_ip = None
                self.found_port = None

            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.addresses:
                    self.found_ip = socket.inet_ntoa(info.addresses[0])
                    self.found_port = info.port

            def update_service(self, zc, type_, name):
                pass

            def remove_service(self, zc, type_, name):
                pass

        zeroconf_obj = Zeroconf()
        listener = NovaMDNSListener()
        browser = ServiceBrowser(zeroconf_obj, "_openlaunch-ws._tcp.local.", listener)
        
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

def read_ws_frame(s):
    head = s.recv(2)
    if not head or len(head) < 2:
        return None, None
    b1, b2 = head[0], head[1]
    opcode = b1 & 0x0F
    has_mask = (b2 & 0x80) != 0
    payload_len = b2 & 0x7F
    if payload_len == 126:
        payload_len = struct.unpack("!H", s.recv(2))[0]
    elif payload_len == 127:
        payload_len = struct.unpack("!Q", s.recv(8))[0]
    mask_key = s.recv(4) if has_mask else None
    raw = b""
    while len(raw) < payload_len:
        chunk = s.recv(payload_len - len(raw))
        if not chunk:
            break
        raw += chunk
    if has_mask:
        raw = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw))
    return opcode, raw

def websocket_worker():
    while True:
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
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk

            print(f"[+] Connected to Nova WebSocket on {nova_ip}:{nova_port}!")
            s.settimeout(1.0)
            while True:
                try:
                    opcode, data = read_ws_frame(s)
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        try:
                            msg = json.loads(text)
                            if msg.get("type") == "shot":
                                shot_queue.put(msg)
                        except json.JSONDecodeError:
                            pass
                except socket.timeout:
                    pass
        except Exception as e:
            print(f"[!] WebSocket error: {e}. Reconnecting in 3s...")
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

class ShanktuaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Shanktuary Performance Studio - Launch Monitor Suite")
        self.root.configure(bg="#101114")
        self.fullscreen = False
        self.view_mode = 1  # 1: 4-Quad Studio, 2: Floor Divot Projector, 3: Performance Suite

        self.session_shots = []
        self.selected_shot_index = -1
        self.sidebar_width = 250  # User resizable sidebar width
        self.is_dragging_sidebar = False

        # Hit testing regions for clicks in Mode 3
        self.shot_list_item_rects = [] # (y1, y2, index)
        self.land_dot_coords = [] # (x, y, index)
        self.inspect_btn_rect = None # (x1, y1, x2, y2)
        self.clear_btn_rect = None # (x1, y1, x2, y2)

        # Load Assets
        self.overhead_img = load_image_asset(OVERHEAD_PATH, target_h=210, mirror=True)
        self.face_img = load_image_asset(FACE_PATH, target_h=140, mirror=False)
        self.side_img = load_image_asset(SIDE_PATH, target_h=150, mirror=False)

        self.img_cache = {}

        self.canvas = tk.Canvas(root, bg="#101114", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Keybindings
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<f>", self.toggle_fullscreen)
        self.root.bind("<m>", self.cycle_mode)
        self.root.bind("<M>", self.cycle_mode)
        self.root.bind("<Tab>", self.cycle_mode)
        self.root.bind("1", lambda e: self.set_mode(1))
        self.root.bind("2", lambda e: self.set_mode(2))
        self.root.bind("3", lambda e: self.set_mode(3))
        self.root.bind("<c>", lambda e: self.clear_session())
        self.root.bind("<C>", lambda e: self.clear_session())

        # Mouse Events for Sidebar Resizing & Selection Clicks
        self.canvas.bind("<Motion>", self.handle_mouse_hover)
        self.canvas.bind("<Button-1>", self.handle_mouse_press)
        self.canvas.bind("<B1-Motion>", self.handle_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_mouse_release)
        self.canvas.bind("<Configure>", lambda e: self.draw_screen())

        self.current_shot = None
        self.root.after(100, self.poll_queue)

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        self.draw_screen()

    def cycle_mode(self, event=None):
        self.view_mode = (self.view_mode % 3) + 1
        self.draw_screen()

    def set_mode(self, mode):
        self.view_mode = mode
        self.draw_screen()

    def clear_session(self):
        self.current_shot = None
        self.session_shots.clear()
        self.selected_shot_index = -1
        self.draw_screen()

    def save_session_to_file(self):
        try:
            with open(SESSION_LOG_PATH, "w") as f:
                json.dump(self.session_shots, f, indent=2)
        except Exception as e:
            print(f"[!] Error saving session: {e}")

    def poll_queue(self):
        try:
            while True:
                msg = shot_queue.get_nowait()
                self.session_shots.append(msg)
                self.selected_shot_index = len(self.session_shots) - 1
                self.current_shot = msg
                self.save_session_to_file()
                
                # Push shot to OBS Stream Overlay Server
                try:
                    obs_server.obs_state.push_shot(msg)
                except Exception as e:
                    print(f"[!] OBS push note: {e}")

                self.draw_screen()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def rotate_point(self, x, y, cx, cy, angle_rad):
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        nx = cos_a * (x - cx) - sin_a * (y - cy) + cx
        ny = sin_a * (x - cx) + cos_a * (y - cy) + cy
        return nx, ny

    def handle_mouse_hover(self, event):
        if self.view_mode == 3:
            w = self.canvas.winfo_width()
            sb_x1 = w - self.sidebar_width - 15

            # Hover near divider line
            if abs(event.x - sb_x1) <= 8:
                self.canvas.config(cursor="sb_h_double_arrow")
                return
            
            # Hover over clickable elements
            if self.inspect_btn_rect and self.inspect_btn_rect[0] <= event.x <= self.inspect_btn_rect[2] and self.inspect_btn_rect[1] <= event.y <= self.inspect_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return

            if self.clear_btn_rect and self.clear_btn_rect[0] <= event.x <= self.clear_btn_rect[2] and self.clear_btn_rect[1] <= event.y <= self.clear_btn_rect[3]:
                self.canvas.config(cursor="hand2")
                return

            for y1, y2, idx in self.shot_list_item_rects:
                if sb_x1 <= event.x <= w and y1 <= event.y <= y2:
                    self.canvas.config(cursor="hand2")
                    return

            for dx, dy, idx in self.land_dot_coords:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    self.canvas.config(cursor="hand2")
                    return

        self.canvas.config(cursor="")

    def handle_mouse_press(self, event):
        if self.view_mode == 3:
            w = self.canvas.winfo_width()
            sb_x1 = w - self.sidebar_width - 15

            # Check divider drag
            if abs(event.x - sb_x1) <= 10:
                self.is_dragging_sidebar = True
                return

            # Check Inspect Button click
            if self.inspect_btn_rect and self.inspect_btn_rect[0] <= event.x <= self.inspect_btn_rect[2] and self.inspect_btn_rect[1] <= event.y <= self.inspect_btn_rect[3]:
                if 0 <= self.selected_shot_index < len(self.session_shots):
                    self.current_shot = self.session_shots[self.selected_shot_index]
                    self.set_mode(1)
                return

            # Check Clear Button click
            if self.clear_btn_rect and self.clear_btn_rect[0] <= event.x <= self.clear_btn_rect[2] and self.clear_btn_rect[1] <= event.y <= self.clear_btn_rect[3]:
                self.clear_session()
                return

            # Check Sidebar Shot List click
            for y1, y2, idx in self.shot_list_item_rects:
                if sb_x1 <= event.x <= w and y1 <= event.y <= y2:
                    self.selected_shot_index = idx
                    self.current_shot = self.session_shots[idx]
                    self.draw_screen()
                    return

            # Check Dispersion Landing Dot click
            for dx, dy, idx in self.land_dot_coords:
                if abs(event.x - dx) <= 10 and abs(event.y - dy) <= 10:
                    self.selected_shot_index = idx
                    self.current_shot = self.session_shots[idx]
                    self.draw_screen()
                    return

    def handle_mouse_drag(self, event):
        if self.is_dragging_sidebar and self.view_mode == 3:
            w = self.canvas.winfo_width()
            new_sb_w = max(160, min(450, w - event.x - 15))
            if new_sb_w != self.sidebar_width:
                self.sidebar_width = new_sb_w
                self.draw_screen()

    def handle_mouse_release(self, event):
        self.is_dragging_sidebar = False
        self.canvas.config(cursor="")

    def calculate_session_averages(self):
        if not self.session_shots:
            return {}

        count = len(self.session_shots)
        sum_bs = sum_la = sum_spin = sum_carry = sum_total = sum_hl = sum_ss = sum_da = sum_apex = sum_off = 0.0

        for shot in self.session_shots:
            ogc = shot.get("open_golf_coach", {})
            us_units = ogc.get("us_customary_units", {})

            sum_bs += us_units.get("ball_speed_mph", 0.0)
            sum_la += shot.get("vertical_launch_angle_degrees", 0.0)
            sum_spin += ogc.get("total_spin_rpm", 0.0)
            sum_carry += us_units.get("carry_distance_yards", 0.0)
            sum_total += us_units.get("total_distance_yards", 0.0)
            sum_hl += shot.get("horizontal_launch_angle_degrees", 0.0)
            sum_ss += ogc.get("sidespin_rpm", 0.0)
            sum_da += ogc.get("descent_angle_degrees", 0.0)
            sum_apex += us_units.get("peak_height_yards", 0.0)
            sum_off += us_units.get("offline_distance_yards", 0.0)

        return {
            "ball_speed": sum_bs / count,
            "launch_angle": sum_la / count,
            "total_spin": sum_spin / count,
            "carry": sum_carry / count,
            "total": sum_total / count,
            "push_pull": sum_hl / count,
            "sidespin": sum_ss / count,
            "descent": sum_da / count,
            "apex": sum_apex / count,
            "offline": sum_off / count
        }

    def draw_top_metric_toolbar(self, w, ball_speed, club_speed, smash, carry, total, offline, hang_time, eff_pct):
        bar_h = 60
        self.canvas.create_rectangle(0, 0, w, bar_h, fill="#181A20", outline="#262933")

        metrics = [
            ("BALL SPEED", f"{ball_speed:.1f} MPH"),
            ("CLUB SPEED", f"{club_speed:.1f} MPH"),
            ("SMASH FACTOR", f"{smash:.2f}"),
            ("CARRY", f"{carry:.1f} YDS"),
            ("TOTAL", f"{total:.1f} YDS"),
            ("OFFLINE", f"{abs(offline):.1f} {'L' if offline < 0 else 'R'} YDS"),
            ("HANG TIME", f"{hang_time:.1f} SEC"),
            ("EFFICIENCY", f"{eff_pct:.0f}%")
        ]

        col_w = w / len(metrics)
        for i, (label, val) in enumerate(metrics):
            cx = int(i * col_w + col_w / 2)
            self.canvas.create_text(cx, 16, text=label, fill="#7E8496", font=("Helvetica", 9, "bold"))
            self.canvas.create_text(cx, 38, text=val, fill="#FFFFFF", font=("Consolas", 14, "bold"))
            if i < len(metrics) - 1:
                self.canvas.create_line(int((i + 1) * col_w), 10, int((i + 1) * col_w), bar_h - 10, fill="#2A2E3B")

    def draw_screen(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 10 or h <= 10:
            w, h = 1150, 780

        self.shot_list_item_rects.clear()
        self.land_dot_coords.clear()
        self.inspect_btn_rect = None
        self.clear_btn_rect = None

        foot_text = f"[M/Tab] Mode (1: 4-Quad Studio, 2: Floor Divot Projector, 3: Performance Suite) | [F] Fullscreen | [C] Clear ({len(self.session_shots)} shots) | [Esc] Exit"
        self.canvas.create_text(w // 2, h - 14, text=foot_text, fill="#4E5363", font=("Helvetica", 9))

        if not self.current_shot and self.view_mode != 3:
            self.canvas.create_text(w // 2, h // 2, text="READY FOR SHOT", fill="#2C303B", font=("Helvetica", 36, "bold"))
            return

        # Extract Current Shot Metrics
        if self.current_shot:
            ogc = self.current_shot.get("open_golf_coach", {})
            us_units = ogc.get("us_customary_units", {})

            club_path = ogc.get("club_path_degrees", {}).get("right_handed", 0.0)
            face_to_path = ogc.get("club_face_to_path_degrees", {}).get("right_handed", 0.0)
            face_to_target = ogc.get("club_face_to_target_degrees", {}).get("right_handed", 0.0)
            vert_launch = self.current_shot.get("vertical_launch_angle_degrees", 0.0)
            horiz_launch = self.current_shot.get("horizontal_launch_angle_degrees", 0.0)
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
            optimal_max_yds = us_units.get("optimal_maximum_distance_yards", 0.0)
            
            shot_name = ogc.get("shot_name", {}).get("right_handed", "Shot")
            shot_rank = ogc.get("shot_rank", {}).get("right_handed", "B")
        else:
            club_path = face_to_path = face_to_target = vert_launch = horiz_launch = sidespin = backspin = spin_axis = total_spin = smash = hang_time = descent_angle = eff_pct = ball_speed_mph = club_speed_mph = carry_yds = total_yds = offline_yds = peak_height_yds = optimal_max_yds = 0.0
            shot_name = "Ready"
            shot_rank = "-"

        if self.view_mode == 1:
            self.draw_top_metric_toolbar(w, ball_speed_mph, club_speed_mph, smash, carry_yds, total_yds, offline_yds, hang_time, eff_pct)
            self.draw_4_quadrant_studio(w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, peak_height_yds, descent_angle, optimal_max_yds, eff_pct, shot_name, shot_rank, smash)
        elif self.view_mode == 2:
            self.draw_divot_focus(w, h, club_path, face_to_path, ball_speed_mph, club_speed_mph, carry_yds, shot_name)
        else:
            self.draw_performance_suite(w, h)

    def draw_performance_suite(self, w, h):
        table_h = 85
        self.canvas.create_rectangle(0, 0, w, table_h, fill="#14151B", outline="#262933")

        avgs = self.calculate_session_averages()

        if 0 <= self.selected_shot_index < len(self.session_shots):
            active_shot = self.session_shots[self.selected_shot_index]
        else:
            active_shot = self.current_shot

        cols = [
            ("SPEED", "ball_speed_mph", "{:.1f}", "MPH"),
            ("LAUNCH ANGLE", "vertical_launch_angle_degrees", "{:.1f}°", "DEG"),
            ("TOTAL SPIN", "total_spin_rpm", "{:.0f}", "RPM"),
            ("CARRY", "carry_distance_yards", "{:.1f}", "YDS"),
            ("TOTAL", "total_distance_yards", "{:.1f}", "YDS"),
            ("PUSH/PULL", "horizontal_launch_angle_degrees", "{:+.1f}°", "DEG"),
            ("SIDESPIN", "sidespin_rpm", "{:+.0f}", "RPM"),
            ("DESCENT ANGLE", "descent_angle_degrees", "{:.1f}°", "DEG"),
            ("PEAK HEIGHT", "peak_height_yards", "{:.1f}", "YDS"),
            ("OFFLINE", "offline_distance_yards", "{:+.1f}", "YDS")
        ]

        sb_w = self.sidebar_width
        margin_x = 70
        chart_w = max(380, w - margin_x - sb_w - 30)

        col_w = (w - 120) / len(cols)

        row_label_text = f"SHOT #{self.selected_shot_index + 1}" if self.selected_shot_index >= 0 else "LAST"
        self.canvas.create_text(15, 42, text=row_label_text, fill="#FFEA00", font=("Helvetica", 9, "bold"), anchor="w")
        self.canvas.create_text(15, 65, text="AVERAGE", fill="#7E8496", font=("Helvetica", 9, "bold"), anchor="w")

        for i, (col_name, field, fmt, unit) in enumerate(cols):
            cx = int(100 + i * col_w + col_w / 2)
            self.canvas.create_text(cx, 18, text=col_name, fill="#8E94A5", font=("Helvetica", 8, "bold"))

            if active_shot:
                ogc = active_shot.get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                v_last = us.get(field, active_shot.get(field, ogc.get(field, 0.0)))
                val_last_str = fmt.format(v_last)
            else:
                val_last_str = "-"
            self.canvas.create_text(cx, 42, text=val_last_str, fill="#FFFFFF", font=("Consolas", 12, "bold"))

            if avgs:
                mapping = {
                    "ball_speed_mph": avgs.get("ball_speed", 0.0),
                    "vertical_launch_angle_degrees": avgs.get("launch_angle", 0.0),
                    "total_spin_rpm": avgs.get("total_spin", 0.0),
                    "carry_distance_yards": avgs.get("carry", 0.0),
                    "total_distance_yards": avgs.get("total", 0.0),
                    "horizontal_launch_angle_degrees": avgs.get("push_pull", 0.0),
                    "sidespin_rpm": avgs.get("sidespin", 0.0),
                    "descent_angle_degrees": avgs.get("descent", 0.0),
                    "peak_height_yards": avgs.get("apex", 0.0),
                    "offline_distance_yards": avgs.get("offline", 0.0)
                }
                val_avg_str = fmt.format(mapping.get(field, 0.0))
            else:
                val_avg_str = "-"
            self.canvas.create_text(cx, 65, text=val_avg_str, fill="#AAB0C0", font=("Consolas", 11))

            if i < len(cols) - 1:
                self.canvas.create_line(int(100 + (i + 1) * col_w), 10, int(100 + (i + 1) * col_w), table_h - 10, fill="#232632")

        plot_y1 = table_h + 20
        plot_h = (h - table_h - 60) // 2
        plot_y2 = plot_y1 + plot_h

        self.canvas.create_rectangle(margin_x, plot_y1, margin_x + chart_w, plot_y2, fill="#16171E", outline="#252834")

        max_x_yds = 350
        ticks = [0, 25, 75, 125, 175, 225, 275, 325]
        for t in ticks:
            tx = margin_x + int((t / max_x_yds) * chart_w)
            self.canvas.create_line(tx, plot_y1, tx, plot_y2, fill="#222530", width=1, dash=(2, 2))
            self.canvas.create_text(tx, plot_y2 + 12, text=str(t), fill="#62687A", font=("Consolas", 9))

        max_h_yds = 60
        for hy in range(0, 61, 20):
            ty = plot_y2 - int((hy / max_h_yds) * plot_h)
            self.canvas.create_line(margin_x, ty, margin_x + chart_w, ty, fill="#222530", width=1, dash=(2, 2))
            self.canvas.create_text(margin_x - 20, ty, text=f"{hy}y", fill="#62687A", font=("Consolas", 9))

        for idx, shot in enumerate(self.session_shots):
            ogc = shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            c_yds = us.get("carry_distance_yards", 0.0)
            apex_y = us.get("peak_height_yards", 0.0)
            
            if c_yds <= 0:
                continue

            is_selected = (idx == self.selected_shot_index)
            curve_color = "#FFEA00" if is_selected else "#505866"
            line_w = 3 if is_selected else 1

            pts = []
            for step in range(0, 101, 4):
                frac = step / 100.0
                curr_x = c_yds * frac
                curr_h = math.sin(frac * math.pi) * apex_y
                
                cx_pixel = margin_x + int((curr_x / max_x_yds) * chart_w)
                cy_pixel = plot_y2 - int((curr_h / max_h_yds) * plot_h)
                pts.extend([cx_pixel, cy_pixel])

            if len(pts) >= 4:
                self.canvas.create_line(pts, fill=curve_color, width=line_w, smooth=True)

            land_x = margin_x + int((c_yds / max_x_yds) * chart_w)
            dot_color = "#FFEA00" if is_selected else "#7E8496"
            self.canvas.create_oval(land_x - (4 if is_selected else 2), plot_y2 - (4 if is_selected else 2), land_x + (4 if is_selected else 2), plot_y2 + (4 if is_selected else 2), fill=dot_color, outline="")

        disp_y1 = plot_y2 + 35
        disp_h = (h - disp_y1 - 35)
        disp_y2 = disp_y1 + disp_h
        center_y = disp_y1 + (disp_h // 2)

        self.canvas.create_rectangle(margin_x, disp_y1, margin_x + chart_w, disp_y2, fill="#16171E", outline="#252834")
        self.canvas.create_line(margin_x, center_y, margin_x + chart_w, center_y, fill="#2C3040", width=2, dash=(6, 4))

        land_coords = []
        for idx, shot in enumerate(self.session_shots):
            ogc = shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            c_yds = us.get("carry_distance_yards", 0.0)
            off_yds = us.get("offline_distance_yards", 0.0)

            if c_yds <= 0:
                continue

            dx_pixel = margin_x + int((c_yds / max_x_yds) * chart_w)
            dy_pixel = center_y + int((off_yds / 50.0) * (disp_h // 2))

            land_coords.append((dx_pixel, dy_pixel))
            self.land_dot_coords.append((dx_pixel, dy_pixel, idx))

            is_selected = (idx == self.selected_shot_index)
            dot_fill = "#FFEA00" if is_selected else "#00FF66"
            dot_r = 6 if is_selected else 3
            self.canvas.create_oval(dx_pixel - dot_r, dy_pixel - dot_r, dx_pixel + dot_r, dy_pixel + dot_r, fill=dot_fill, outline="#FFFFFF" if is_selected else "")

        if len(land_coords) >= 2:
            xs = [p[0] for p in land_coords]
            ys = [p[1] for p in land_coords]
            min_x, max_x = min(xs) - 15, max(xs) + 15
            min_y, max_y = min(ys) - 12, max(ys) + 12
            self.canvas.create_oval(min_x, min_y, max_x, max_y, fill="", outline="#00FF66", width=1, dash=(4, 4))

        sb_x1 = margin_x + chart_w + 15
        divider_w = 6
        self.canvas.create_rectangle(sb_x1 - divider_w, plot_y1, sb_x1, disp_y2, fill="#00E5FF" if self.is_dragging_sidebar else "#2A2D3A", outline="")

        self.canvas.create_rectangle(sb_x1, plot_y1, sb_x1 + sb_w, disp_y2, fill="#14151C", outline="#252834")

        title_font_sz = max(9, min(12, int(sb_w / 18)))
        val_font_sz = max(8, min(11, int(sb_w / 20)))

        self.canvas.create_text(sb_x1 + sb_w // 2, plot_y1 + 18, text="SESSION SHOT LIST", fill="#00E5FF", font=("Helvetica", title_font_sz, "bold"))
        
        btn_margin = max(10, int(sb_w * 0.06))
        btn_y1 = plot_y1 + 38
        btn_y2 = plot_y1 + 68
        self.inspect_btn_rect = (sb_x1 + btn_margin, btn_y1, sb_x1 + sb_w - btn_margin, btn_y2)
        
        self.canvas.create_rectangle(self.inspect_btn_rect[0], btn_y1, self.inspect_btn_rect[2], btn_y2, fill="#00E5FF", outline="")
        self.canvas.create_text(sb_x1 + sb_w // 2, (btn_y1 + btn_y2) // 2, text="🔍 INSPECT QUAD VIEW", fill="#101114", font=("Helvetica", max(8, val_font_sz - 1), "bold"))

        list_y1 = plot_y1 + 78
        list_y2 = disp_y2 - 50
        max_visible_items = max(3, (list_y2 - list_y1) // 24)

        start_idx = max(0, len(self.session_shots) - max_visible_items)
        visible_shots = list(enumerate(self.session_shots))[start_idx:]

        for i, (real_idx, shot) in enumerate(visible_shots):
            item_y1 = list_y1 + i * 24
            item_y2 = item_y1 + 22
            if item_y2 > list_y2:
                break

            self.shot_list_item_rects.append((item_y1, item_y2, real_idx))
            is_selected = (real_idx == self.selected_shot_index)

            bg_color = "#3A3800" if is_selected else ("#1D2028" if i % 2 == 0 else "#161820")
            border_color = "#FFEA00" if is_selected else "#282B36"
            self.canvas.create_rectangle(sb_x1 + 8, item_y1, sb_x1 + sb_w - 8, item_y2, fill=bg_color, outline=border_color)

            ogc = shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            c_yds = us.get("carry_distance_yards", 0.0)
            s_name = ogc.get("shot_name", {}).get("right_handed", "Shot")

            item_str = f"#{real_idx + 1}: {c_yds:.1f}y ({s_name})"
            text_color = "#FFEA00" if is_selected else "#D0D5DD"
            self.canvas.create_text(sb_x1 + 14, (item_y1 + item_y2) // 2, text=item_str, fill=text_color, font=("Consolas", max(8, val_font_sz - 1), "bold" if is_selected else "normal"), anchor="w")

        self.clear_btn_rect = (sb_x1 + btn_margin, disp_y2 - 40, sb_x1 + sb_w - btn_margin, disp_y2 - 12)
        self.canvas.create_rectangle(self.clear_btn_rect[0], self.clear_btn_rect[1], self.clear_btn_rect[2], self.clear_btn_rect[3], fill="#1F2129", outline="#303442")
        self.canvas.create_text(sb_x1 + sb_w // 2, (self.clear_btn_rect[1] + self.clear_btn_rect[3]) // 2, text="[C] CLEAR SHOTS", fill="#FF4081", font=("Helvetica", max(8, val_font_sz - 1), "bold"))

    def draw_4_quadrant_studio(self, w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, apex_yds, descent, opt_max, eff_pct, shot_name, shot_rank, smash):
        top_bar_h = 60
        avail_h = h - top_bar_h - 30
        mid_x = w // 2
        mid_y = top_bar_h + (avail_h // 2)

        self.canvas.create_line(mid_x, top_bar_h, mid_x, h - 25, fill="#232630", width=2)
        self.canvas.create_line(0, mid_y, w, mid_y, fill="#232630", width=2)

        # Inspection Banner Header
        if 0 <= self.selected_shot_index < len(self.session_shots):
            insp_text = f"INSPECTING SHOT #{self.selected_shot_index + 1} OF {len(self.session_shots)}"
            self.canvas.create_text(mid_x, top_bar_h + 12, text=insp_text, fill="#FFEA00", font=("Helvetica", 9, "bold"))

        # Quadrant 1 (Top-Left): Overhead View
        q1_cx, q1_cy = mid_x // 2, top_bar_h + (avail_h // 4)
        self.canvas.create_line(q1_cx - 140, q1_cy, q1_cx + 140, q1_cy, fill="#40C4FF", width=1, dash=(4, 4))
        
        if self.overhead_img:
            rotated = self.overhead_img.rotate(-face_to_target, resample=Image.BICUBIC, expand=True)
            self.img_cache["q1_overhead"] = ImageTk.PhotoImage(rotated)
            self.canvas.create_image(q1_cx, q1_cy, image=self.img_cache["q1_overhead"], anchor="c")

        path_rad = math.radians(club_path)
        px1, py1 = self.rotate_point(q1_cx, q1_cy + 80, q1_cx, q1_cy, path_rad)
        px2, py2 = self.rotate_point(q1_cx, q1_cy - 80, q1_cx, q1_cy, path_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill="#00E5FF", width=3, arrow=tk.LAST)

        self.canvas.create_oval(q1_cx + 55 - 10, q1_cy - 10, q1_cx + 55 + 10, q1_cy + 10, fill="#FFFFFF", outline="#D0D5DD")

        path_str = f"Path: {abs(club_path):.1f}° {'In To Out' if club_path > 0 else 'Out To In'}"
        face_target_str = f"Face To Target: {abs(face_to_target):.1f}° {'Open' if face_to_target > 0 else 'Closed'}"
        face_path_str = f"Face To Path: {abs(face_to_path):.1f}° {'Open' if face_to_path > 0 else 'Closed'}"
        
        self.canvas.create_text(q1_cx, q1_cy - 110, text=path_str, fill="#00E5FF", font=("Consolas", 12, "bold"))
        self.canvas.create_text(q1_cx, q1_cy + 95, text=face_target_str, fill="#FFEA00", font=("Consolas", 11, "bold"))
        self.canvas.create_text(q1_cx, q1_cy + 115, text=face_path_str, fill="#FF4081", font=("Consolas", 11, "bold"))

        # Quadrant 2 (Bottom-Left): Trajectory Arc
        q2_cx, q2_cy = mid_x // 2, mid_y + (avail_h // 4)
        ground_y = q2_cy + 40
        self.canvas.create_line(q2_cx - 150, ground_y, q2_cx + 150, ground_y, fill="#3A3F4D", width=2, dash=(4, 4))
        
        if self.side_img:
            self.img_cache["q2_side"] = ImageTk.PhotoImage(self.side_img)
            self.canvas.create_image(q2_cx - 90, ground_y - 25, image=self.img_cache["q2_side"], anchor="c")

        arc_pts = []
        for t in range(0, 101, 5):
            frac = t / 100.0
            x_p = (q2_cx - 90) + int(240 * frac)
            h_p = math.sin(frac * math.pi) * min(65, int(apex_yds * 20))
            y_p = ground_y - int(h_p)
            arc_pts.extend([x_p, y_p])
        
        self.canvas.create_line(arc_pts, fill="#00FF66", width=3, smooth=True)
        self.canvas.create_oval(q2_cx - 90 - 7, ground_y - 7, q2_cx - 90 + 7, ground_y + 7, fill="#FFFFFF")

        top_elev_str = f"Launch Angle: {vert_launch:.1f}°   |   Apex: {apex_yds:.1f} yds"
        bot_elev_str = f"Descent: {descent:.1f}°   |   Backspin: {int(backspin)} rpm"
        
        self.canvas.create_text(q2_cx, q2_cy - 85, text=top_elev_str, fill="#00FF66", font=("Consolas", 11, "bold"))
        self.canvas.create_text(q2_cx, q2_cy + 65, text=bot_elev_str, fill="#E0E0E0", font=("Consolas", 11, "bold"))

        # Quadrant 3 (Top-Right): 3D Spin Axis
        q3_cx, q3_cy = mid_x + (mid_x // 2), top_bar_h + (avail_h // 4)
        
        rank_colors = {"A": "#00FF66", "B": "#00E5FF", "C": "#FFC107", "D": "#FF4081"}
        badge_color = rank_colors.get(shot_rank, "#00FF66")
        
        self.canvas.create_rectangle(q3_cx - 100, q3_cy - 80, q3_cx - 65, q3_cy - 55, fill=badge_color, outline="")
        self.canvas.create_text(q3_cx - 82, q3_cy - 67, text=shot_rank, fill="#101114", font=("Helvetica", 12, "bold"))
        self.canvas.create_text(q3_cx - 50, q3_cy - 67, text=shot_name.upper(), fill=badge_color, font=("Helvetica", 14, "bold"), anchor="w")

        ball_r = 24
        self.canvas.create_oval(q3_cx - ball_r, q3_cy - ball_r + 5, q3_cx + ball_r, q3_cy + ball_r + 5, fill="#FFFFFF", outline="#D0D5DD", width=2)
        
        axis_rad = math.radians(spin_axis)
        ax1, ay1 = self.rotate_point(q3_cx, q3_cy + 5 + 38, q3_cx, q3_cy + 5, axis_rad)
        ax2, ay2 = self.rotate_point(q3_cx, q3_cy + 5 - 38, q3_cx, q3_cy + 5, axis_rad)
        self.canvas.create_line(ax1, ay1, ax2, ay2, fill="#FF4081", width=4, arrow=tk.LAST, arrowshape=(14, 18, 6))

        spin_line1 = f"Spin Axis: {abs(spin_axis):.1f}° {'R' if spin_axis > 0 else 'L'}   |   Sidespin: {int(sidespin)} rpm"
        spin_line2 = f"Total Spin: {int(total_spin)} rpm   |   Opt. Potential: {opt_max:.1f} YDS"

        self.canvas.create_text(q3_cx, q3_cy + 58, text=spin_line1, fill="#00E5FF", font=("Consolas", 11, "bold"))
        self.canvas.create_text(q3_cx, q3_cy + 78, text=spin_line2, fill="#8E94A5", font=("Consolas", 10))

        # Quadrant 4 (Bottom-Right): Face Impact Location
        q4_cx, q4_cy = mid_x + (mid_x // 2), mid_y + (avail_h // 4)
        
        if self.face_img:
            self.img_cache["q4_face"] = ImageTk.PhotoImage(self.face_img)
            self.canvas.create_image(q4_cx, q4_cy, image=self.img_cache["q4_face"], anchor="c")

        h_impact_mm = int(face_to_path * 0.75)
        v_impact_mm = int((vert_launch - 22.0) * 0.85)

        px_shift_h = max(-40, min(35, int(h_impact_mm * 1.8)))
        px_shift_v = max(-22, min(22, int(v_impact_mm * 1.8)))

        impact_x = q4_cx - 25 + px_shift_h
        impact_y = q4_cy - 5 - px_shift_v

        self.canvas.create_oval(impact_x - 11, impact_y - 11, impact_x + 11, impact_y + 11, fill="", outline="#FF1744", width=3)
        self.canvas.create_oval(impact_x - 5, impact_y - 5, impact_x + 5, impact_y + 5, fill="#FF1744", outline="")

        h_dir = "Heel" if h_impact_mm > 0 else "Toe"
        v_dir = "High" if v_impact_mm > 0 else "Low (Thin/Topped)"
        
        impact_header = f"H Impact: {abs(h_impact_mm)}mm {h_dir}   |   V Impact: {abs(v_impact_mm)}mm {v_dir}"

        self.canvas.create_text(q4_cx, q4_cy - 75, text=impact_header, fill="#FF1744", font=("Consolas", 11, "bold"))
        self.canvas.create_text(q4_cx, q4_cy + 75, text=f"Distance Efficiency: {eff_pct:.0f}%", fill="#00E5FF", font=("Consolas", 11, "bold"))

    def draw_divot_focus(self, pane_w, h, club_path, face_to_path, ball_speed, club_speed, carry, shot_name, offset_x=0):
        cx = offset_x + (pane_w // 2)
        cy = (h // 2) - 20

        self.canvas.create_line(cx - 130, cy, cx + 130, cy, fill="#22252E", width=2, dash=(4, 4))
        self.canvas.create_line(cx, cy - 130, cx, cy + 130, fill="#22252E", width=2, dash=(4, 4))

        divot_w, divot_h = 42, 150
        angle_rad = math.radians(club_path)

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

        self.canvas.create_polygon(rotated_pts, fill="#1B3B1B", outline="#00FF66", width=3)
        self.canvas.create_polygon(rotated_pts, fill="#4A2E13", outline="", stipple="gray50")

        path_len = 190
        px1, py1 = self.rotate_point(cx, cy + path_len // 2, cx, cy, angle_rad)
        px2, py2 = self.rotate_point(cx, cy - path_len // 2, cx, cy, angle_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill="#00E5FF", width=3, arrow=tk.LAST, arrowshape=(12, 15, 5))

        self.canvas.create_text(cx, 55, text=f"DIVOT PROJECTOR  •  {shot_name.upper()}", fill="#00FF66", font=("Helvetica", 14, "bold"))

def main():
    t_ws = threading.Thread(target=websocket_worker, daemon=True)
    t_ws.start()

    # Start OBS Studio Browser Source Overlay Server on port 9321
    obs_server.launch_obs_server_thread()

    root = tk.Tk()
    root.geometry("1150x780")
    app = ShanktuaryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
