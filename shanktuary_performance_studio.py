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
import sys
import struct
import json
import time
import math
import threading
import queue
import webbrowser
from datetime import datetime
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageOps
import obs_server

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

DEFAULT_BAG = [
    {"name": "Driver", "category": "Woods & Drivers", "brand": "Generic", "model": "Driver", "loft_deg": 10.5, "shaft": "Stiff"},
    {"name": "3 Wood", "category": "Woods & Drivers", "brand": "Generic", "model": "Fairway", "loft_deg": 15.0, "shaft": "Stiff"},
    {"name": "5 Wood", "category": "Woods & Drivers", "brand": "Generic", "model": "Fairway", "loft_deg": 18.0, "shaft": "Stiff"},
    {"name": "3 Hybrid", "category": "Hybrids & Utilities", "brand": "Generic", "model": "Hybrid", "loft_deg": 19.0, "shaft": "Stiff"},
    {"name": "4 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 21.0, "shaft": "Steel S"},
    {"name": "5 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 24.0, "shaft": "Steel S"},
    {"name": "6 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 27.0, "shaft": "Steel S"},
    {"name": "7 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 31.0, "shaft": "Steel S"},
    {"name": "8 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 35.0, "shaft": "Steel S"},
    {"name": "9 Iron", "category": "Irons", "brand": "Generic", "model": "Iron", "loft_deg": 40.0, "shaft": "Steel S"},
    {"name": "PW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 45.0, "shaft": "Wedge Flex"},
    {"name": "GW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 50.0, "shaft": "Wedge Flex"},
    {"name": "SW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 54.0, "shaft": "Wedge Flex"},
    {"name": "LW", "category": "Wedges", "brand": "Generic", "model": "Wedge", "loft_deg": 58.0, "shaft": "Wedge Flex"},
    {"name": "Putter", "category": "Putter", "brand": "Generic", "model": "Blade", "loft_deg": 3.0, "shaft": "Standard"}
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
    else:
        return "Irons"

# Club Image Assets
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

        # Hit testing regions for top header & interactive menus
        self.sidebar_toggle_rect = None       # Hamburger [ ☰ ] or collapse [ ◀ ]
        self.sidebar_session_btn_rect = None  # [ 📂 Session Name ▼ ]
        self.sidebar_rename_sess_btn_rect = None # [ ✏️ ]
        self.sidebar_new_sess_btn_rect = None # [ ＋ ]
        self.sidebar_filter_btn_rect = None   # [ 🎯 Filter: All Clubs ▼ ]
        self.sidebar_clear_btn_rect = None    # [ 🗑️ Clear Session ]
        self.sidebar_shot_card_rects = []     # (x1, y1, x2, y2, shot_idx_in_session)
        self.session_menu_items = []          # (x1, y1, x2, y2, sess_idx)
        self.filter_menu_items = []           # (x1, y1, x2, y2, club_name)

        self.mode_pill_rects = {}             # mode_id -> (x1, y1, x2, y2)
        self.club_btn_rect = None             # (x1, y1, x2, y2)
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
        self.spec_editor_shaft = ""
        self.spec_editor_active_field = "brand" # "name", "category", "brand", "model", "loft", "shaft"
        self.spec_editor_box_rect = None
        self.spec_editor_save_rect = None
        self.spec_editor_delete_rect = None
        self.spec_editor_cancel_rect = None
        self.spec_editor_cat_chips = []       # (x1, y1, x2, y2, cat_name)
        self.spec_editor_field_rects = {}     # field_name -> (x1, y1, x2, y2)

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

        self.img_cache = {}

        self.canvas = tk.Canvas(root, bg="#101114", highlightthickness=0)
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
        self.swing_lab_tare_rect = None
        self.swing_lab_hw_rect = None
        self.swing_lab_demo_rect = None
        self.show_balance_hardware_modal = False
        self.balance_modal_box_rect = None
        self.balance_modal_close_rect = None
        self.balance_modal_tare_rect = None
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
        self.root.after(100, self.poll_queue)

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
        if not self.sidebar_collapsed and mouse_x <= self.sidebar_width:
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
            if not self.bag:
                self.init_default_bag()
            for club_item in self.bag:
                c_name = club_item.get("name")
                if c_name and c_name not in self.clubs:
                    self.clubs.append(c_name)
        except Exception as e:
            print(f"[!] Error loading session history: {e}")
            if not self.bag:
                self.init_default_bag()

    def save_session_to_file(self):
        try:
            custom_clubs = [c for c in self.clubs if c not in DEFAULT_CLUBS]
            payload = {
                "sessions": self.sessions,
                "custom_clubs": custom_clubs,
                "bag": self.bag
            }
            with open(SESSION_LOG_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[!] Error saving session: {e}")

    def init_default_bag(self):
        self.bag = [dict(c) for c in DEFAULT_BAG]

    def get_bag_club(self, club_name):
        for c in self.bag:
            if c.get("name") == club_name:
                return c
        return None

    def update_club_specs(self, club_name, brand=None, model=None, loft_deg=None, shaft=None, category=None, new_name=None):
        c = self.get_bag_club(club_name)
        if c:
            if brand is not None: c["brand"] = str(brand)
            if model is not None: c["model"] = str(model)
            if loft_deg is not None:
                try:
                    c["loft_deg"] = float(loft_deg)
                except (ValueError, TypeError):
                    c["loft_deg"] = 0.0
            if shaft is not None: c["shaft"] = str(shaft)
            if category is not None: c["category"] = str(category)
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

    def add_club_to_bag(self, name, category=None, brand="", model="", loft_deg=0.0, shaft=""):
        clean_name = name.strip() if name else ""
        if not clean_name:
            return
        if not category:
            category = infer_club_category(clean_name)
        try:
            loft_val = float(loft_deg) if loft_deg else 0.0
        except (ValueError, TypeError):
            loft_val = 0.0

        existing = self.get_bag_club(clean_name)
        if existing:
            self.update_club_specs(clean_name, brand=brand, model=model, loft_deg=loft_val, shaft=shaft, category=category)
            return
        club_dict = {
            "name": clean_name,
            "category": category,
            "brand": brand,
            "model": model,
            "loft_deg": loft_val,
            "shaft": shaft
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
            "avg_offline": sum(offlines) / count
        }

    def extract_shot_metrics(self, s):
        if not isinstance(s, dict):
            return {
                "carry": 0.0, "total": 0.0, "ball_speed": 0.0, "club_speed": 0.0,
                "smash": 0.0, "launch_angle": 0.0, "total_spin": 0.0, "offline": 0.0
            }
        
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
                color = "#FF3366"
            elif delta > 18.0:
                status = "wide"
                status_text = f"Wide Gap (+{delta:.1f}y)"
                color = "#FFCC00"
            else:
                status = "healthy"
                status_text = f"+{delta:.1f}y gap"
                color = "#00FF66"
            
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
                grade_color = "#00FF66"
            elif std_gap <= 6.0:
                grade = "B (Good Gapping)"
                grade_color = "#00E5FF"
            elif std_gap <= 9.0:
                grade = "C (Variable Gapping)"
                grade_color = "#FFCC00"
            else:
                grade = "D (Irregular Steps)"
                grade_color = "#FF3366"
        else:
            mean_gap = sum(s["delta"] for s in steps) / len(steps) if steps else 0.0
            grade = "Insufficient Data"
            grade_color = "#8E94A5"

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
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#12151F", outline="#00E5FF", width=2)

        # Header
        self.canvas.create_text(cx, y1 + 28, text="🏌️ ADD CUSTOM CLUB TO BAG", fill="#00E5FF", font=("Helvetica", 12, "bold"))
        self.canvas.create_text(cx, y1 + 52, text="Type custom club name (e.g. 2 Hybrid, 7 Wood, 64° Wedge):", fill="#8E94A5", font=("Helvetica", 9))

        # Input Text Box
        in_x1 = cx - 180
        in_x2 = cx + 180
        in_y1 = y1 + 75
        in_y2 = in_y1 + 42
        self.canvas.create_rectangle(in_x1, in_y1, in_x2, in_y2, fill="#0A0C12", outline="#00FF66", width=2)

        if self.custom_club_input_text:
            display_text = self.custom_club_input_text + " |"
            self.canvas.create_text(cx, (in_y1 + in_y2) // 2, text=display_text, fill="#FFFFFF", font=("Consolas", 14, "bold"))
        else:
            self.canvas.create_text(cx, (in_y1 + in_y2) // 2, text="Type club name here... |", fill="#464E62", font=("Consolas", 12, "italic"))

        # Buttons
        btn_y1 = in_y2 + 20
        btn_y2 = btn_y1 + 32
        btn_w = 140

        # Add Button (Left)
        add_x1 = cx - btn_w - 10
        add_x2 = cx - 10
        self.custom_club_modal_add_rect = (add_x1, btn_y1, add_x2, btn_y2)
        self.canvas.create_rectangle(add_x1, btn_y1, add_x2, btn_y2, fill="#00FF66", outline="")
        self.canvas.create_text((add_x1 + add_x2) // 2, (btn_y1 + btn_y2) // 2, text="✓ Add Club", fill="#08090C", font=("Helvetica", 9, "bold"))

        # Cancel Button (Right)
        can_x1 = cx + 10
        can_x2 = cx + btn_w + 10
        self.custom_club_modal_cancel_rect = (can_x1, btn_y1, can_x2, btn_y2)
        self.canvas.create_rectangle(can_x1, btn_y1, can_x2, btn_y2, fill="#212636", outline="#323B50")
        self.canvas.create_text((can_x1 + can_x2) // 2, (btn_y1 + btn_y2) // 2, text="Cancel (<Esc>)", fill="#D0D5DD", font=("Helvetica", 9, "bold"))

        # Footer shortcut hint
        self.canvas.create_text(cx, y2 - 12, text="Press <Enter> to confirm  •  <Esc> to cancel", fill="#5A6175", font=("Helvetica", 8))

    def handle_key_press(self, event):
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
                fields = ["name", "brand", "model", "loft", "shaft"]
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
                elif f == "shaft": self.spec_editor_shaft = self.spec_editor_shaft[:-1]
                self.draw_screen()
                return "break"
            elif event.char and event.char.isprintable() and len(event.char) == 1:
                f = self.spec_editor_active_field
                if f == "name" and len(self.spec_editor_club_name) < 25: self.spec_editor_club_name += event.char
                elif f == "brand" and len(self.spec_editor_brand) < 25: self.spec_editor_brand += event.char
                elif f == "model" and len(self.spec_editor_model) < 25: self.spec_editor_model += event.char
                elif f == "loft" and len(self.spec_editor_loft) < 8: self.spec_editor_loft += event.char
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
            self.current_club = clean_name
            self.show_club_menu = False
            self.show_custom_club_modal = False
            self.save_session_to_file()
            self.copy_feedback = f"✓ Added & Selected '{clean_name}'"
            self.root.after(2500, self.clear_copy_feedback)
            self.draw_screen()

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
            self.spec_editor_shaft = c.get("shaft", "")
            self.spec_editor_active_field = "brand"
        else:
            self.spec_editor_orig_name = ""
            self.spec_editor_club_name = ""
            self.spec_editor_category = "Irons"
            self.spec_editor_brand = ""
            self.spec_editor_model = ""
            self.spec_editor_loft = ""
            self.spec_editor_shaft = ""
            self.spec_editor_active_field = "name"

        self.show_spec_editor_modal = True
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

        if self.spec_editor_orig_name:
            self.update_club_specs(
                self.spec_editor_orig_name,
                brand=self.spec_editor_brand.strip(),
                model=self.spec_editor_model.strip(),
                loft_deg=loft_val,
                shaft=self.spec_editor_shaft.strip(),
                category=self.spec_editor_category,
                new_name=name
            )
        else:
            self.add_club_to_bag(
                name=name,
                category=self.spec_editor_category,
                brand=self.spec_editor_brand.strip(),
                model=self.spec_editor_model.strip(),
                loft_deg=loft_val,
                shaft=self.spec_editor_shaft.strip()
            )
        self.show_spec_editor_modal = False
        self.copy_feedback = f"✓ Saved {name} Specs"
        self.root.after(2500, self.clear_copy_feedback)
        self.draw_screen()

    def draw_club_spec_editor_modal(self, w, h):
        # 1. Backdrop
        self.canvas.create_rectangle(0, 0, w, h, fill="#04060A", outline="", stipple="gray75")

        # 2. Responsive Modal Box
        modal_w = min(640, max(520, int(w * 0.54)))
        modal_h = min(560, max(500, int(h * 0.76)))
        cx = w // 2
        cy = h // 2
        x1 = cx - modal_w // 2
        x2 = cx + modal_w // 2
        y1 = cy - modal_h // 2
        y2 = cy + modal_h // 2

        self.spec_editor_box_rect = (x1, y1, x2, y2)

        # Shadow & Card
        self.canvas.create_rectangle(x1 + 6, y1 + 6, x2 + 6, y2 + 6, fill="#020305", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#12151F", outline="#00E5FF", width=2)

        # Title
        title = f"EDIT CLUB SPECS: {self.spec_editor_orig_name}" if self.spec_editor_orig_name else "ADD NEW CLUB TO BAG"
        self.canvas.create_text(cx, y1 + 24, text=title, fill="#00E5FF", font=("Helvetica", 11, "bold"))
        self.canvas.create_text(cx, y1 + 44, text="Configure your club profile, category, and equipment specs", fill="#8E94A5", font=("Helvetica", 8))

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
            self.canvas.create_rectangle(cx1, cat_y1, cx2, cat_y2, fill="#0E2A38" if is_cat_sel else "#1A1E2B", outline="#00E5FF" if is_cat_sel else "#2C3446")
            
            chip_label = "Woods" if cat == "Woods & Drivers" else ("Hybrids" if cat == "Hybrids & Utilities" else cat)
            self.canvas.create_text((cx1 + cx2) // 2, (cat_y1 + cat_y2) // 2, text=chip_label, fill="#00E5FF" if is_cat_sel else "#A0A7B8", font=("Helvetica", 8, "bold" if is_cat_sel else "normal"))

        # Input Form Grid
        fields = [
            ("name", "Club Name (e.g. 7 Iron, 60° Wedge):", self.spec_editor_club_name),
            ("brand", "Manufacturer / Brand (e.g. TaylorMade, Titleist):", self.spec_editor_brand),
            ("model", "Clubhead Model (e.g. Qi10, T150, SM10):", self.spec_editor_model),
            ("loft", "Loft Angle (°):", self.spec_editor_loft),
            ("shaft", "Shaft Specs (e.g. Ventus Black 6X, KBS Tour):", self.spec_editor_shaft),
        ]

        curr_fy = y1 + 102
        field_step = 58
        for f_key, f_label, f_val in fields:
            self.canvas.create_text(x1 + 35, curr_fy, text=f_label, fill="#8E94A5", font=("Helvetica", 8, "bold"), anchor="w")
            
            box_x1 = x1 + 35
            box_x2 = x2 - 35
            box_y1 = curr_fy + 14
            box_y2 = box_y1 + 28
            self.spec_editor_field_rects[f_key] = (box_x1, box_y1, box_x2, box_y2)

            is_f_active = (self.spec_editor_active_field == f_key)
            self.canvas.create_rectangle(box_x1, box_y1, box_x2, box_y2, fill="#0A0C12", outline="#00FF66" if is_f_active else "#282F42", width=1.5 if is_f_active else 1)

            val_display = (f_val + " |") if is_f_active else (f_val if f_val else "")
            val_color = "#FFFFFF" if f_val else ("#00FF66" if is_f_active else "#485065")
            val_text = val_display if val_display else "Click to enter..."
            self.canvas.create_text(box_x1 + 10, (box_y1 + box_y2) // 2, text=val_text, fill=val_color, font=("Consolas", 9, "bold" if is_f_active else "normal"), anchor="w")

            curr_fy += field_step

        # Action Buttons
        btn_y1 = y2 - 52
        btn_y2 = btn_y1 + 32

        # Save Button
        save_x1 = cx - 180
        save_x2 = cx - 40
        self.spec_editor_save_rect = (save_x1, btn_y1, save_x2, btn_y2)
        self.canvas.create_rectangle(save_x1, btn_y1, save_x2, btn_y2, fill="#00FF66", outline="")
        self.canvas.create_text((save_x1 + save_x2) // 2, (btn_y1 + btn_y2) // 2, text="✓ Save Specs", fill="#08090C", font=("Helvetica", 9, "bold"))

        # Cancel Button
        cancel_x1 = cx - 30
        cancel_x2 = cx + 70
        self.spec_editor_cancel_rect = (cancel_x1, btn_y1, cancel_x2, btn_y2)
        self.canvas.create_rectangle(cancel_x1, btn_y1, cancel_x2, btn_y2, fill="#212636", outline="#323B50")
        self.canvas.create_text((cancel_x1 + cancel_x2) // 2, (btn_y1 + btn_y2) // 2, text="Cancel", fill="#D0D5DD", font=("Helvetica", 9, "bold"))

        # Delete Button (if existing club)
        if self.spec_editor_orig_name:
            del_x1 = cx + 80
            del_x2 = cx + 180
            self.spec_editor_delete_rect = (del_x1, btn_y1, del_x2, btn_y2)
            self.canvas.create_rectangle(del_x1, btn_y1, del_x2, btn_y2, fill="#3A141E", outline="#FF3366")
            self.canvas.create_text((del_x1 + del_x2) // 2, (btn_y1 + btn_y2) // 2, text="🗑️ Remove", fill="#FF3366", font=("Helvetica", 9, "bold"))
        else:
            self.spec_editor_delete_rect = None

        # Footer Hint
        self.canvas.create_text(cx, y2 - 12, text="Press <Tab> to cycle fields  •  <Enter> to Save  •  <Esc> to Cancel", fill="#5A6175", font=("Helvetica", 8))

    def get_club_color(self, club_name):
        standard = {
            "Driver": "#FF3366", "3 Wood": "#FF8800", "5 Wood": "#FFCC00",
            "3 Hybrid": "#FFEA00", "4 Iron": "#AEEA00", "5 Iron": "#64DD17",
            "6 Iron": "#00E676", "7 Iron": "#00E5FF", "8 Iron": "#00B0FF",
            "9 Iron": "#2979FF", "PW": "#651FFF", "GW": "#AA00FF",
            "SW": "#FF4081", "LW": "#F50057"
        }
        if club_name in standard:
            return standard[club_name]
        palette = ["#FF5722", "#E91E63", "#9C27B0", "#00BCD4", "#8BC34A", "#FFC107", "#009688", "#3F51B5", "#F06292", "#4DD0E1"]
        h = sum(ord(c) for c in str(club_name))
        return palette[h % len(palette)]

    def poll_pressure_stream(self):
        try:
            if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
                pm = obs_server.pressure_manager
                latest = pm.latest_frame
                if latest:
                    self.swing_lab_history.append(latest)
                    if len(self.swing_lab_history) > 200:
                        self.swing_lab_history.pop(0)

                if self.view_mode == 8 or self.show_balance_hardware_modal:
                    self.draw_screen()
        except Exception:
            pass
        self.root.after(33, self.poll_pressure_stream)

    def poll_queue(self):
        try:
            while True:
                msg = shot_queue.get_nowait()
                msg["club"] = self.current_club
                msg["club_color"] = self.get_club_color(self.current_club)
                msg["timestamp"] = datetime.now().strftime("%I:%M %p")
                self.nova_connected = True
                
                sess = self.get_active_session()
                sess["shots"].append(msg)
                self.selected_shot_index = len(sess["shots"]) - 1
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
        # 0. In-Canvas Balance Hardware Modal Hover
        if self.show_balance_hardware_modal:
            for r in (
                self.balance_modal_close_rect, self.balance_modal_pair_rect,
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
                    from src.hardware.pressure.bluetooth_windows import open_windows_bluetooth_settings
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
                    self.copy_feedback = "✓ Baseline Zeroed (Tared)"
                    self.root.after(2000, self.clear_copy_feedback)
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
                    elif action == "open_range":
                        self.launch_3d_range()
                    elif action == "set_mode_2" or action == "set_mode_0":
                        self.set_mode(0)
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

        if not self.sidebar_collapsed and event.x <= self.sidebar_width:
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
                    self.copy_feedback = "✓ Baseline Zeroed (Tared)"
                    self.root.after(2000, self.clear_copy_feedback)
                    self.draw_screen()
                return
            if self.swing_lab_hw_rect and self.swing_lab_hw_rect[0] <= event.x <= self.swing_lab_hw_rect[2] and self.swing_lab_hw_rect[1] <= event.y <= self.swing_lab_hw_rect[3]:
                self.show_balance_hardware_modal = True
                self.draw_screen()
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
            offset_x = 0 if self.sidebar_collapsed else self.sidebar_width
            avail_w = max(100, self.canvas.winfo_width() - offset_x)
            rel_x = event.x - offset_x
            new_ratio = max(0.20, min(0.85, rel_x / float(avail_w)))
            self.dispersion_splitter_ratio = new_ratio
            self.draw_screen()
        elif self.view_mode == 7 and self.fitting_splitter_dragging:
            offset_x = 0 if self.sidebar_collapsed else self.sidebar_width
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
            sum_cp += ogc.get("club_path_degrees", {}).get("right_handed", 0.0)
            sum_fp += ogc.get("club_face_to_path_degrees", {}).get("right_handed", 0.0)
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

        sb_w = self.sidebar_width
        # Base container
        self.canvas.create_rectangle(0, 0, sb_w, h, fill="#12141A", outline="#232734")

        # 1. Header (y: 0 to 52)
        self.canvas.create_rectangle(0, 0, sb_w, 52, fill="#151822", outline="#232734")
        self.canvas.create_text(16, 26, text="📁 SHOT LIBRARY", fill="#00E5FF", font=("Helvetica", 10, "bold"), anchor="w")
        
        # Collapse button [ ◀ ]
        coll_x1, coll_y1, coll_x2, coll_y2 = sb_w - 38, 12, sb_w - 10, 40
        self.sidebar_toggle_rect = (coll_x1, coll_y1, coll_x2, coll_y2)
        self.canvas.create_rectangle(coll_x1, coll_y1, coll_x2, coll_y2, fill="#1D202C", outline="#2E3547")
        self.canvas.create_text((coll_x1 + coll_x2) // 2, 26, text="◀", fill="#8E94A5", font=("Helvetica", 9, "bold"))

        # 2. Session Bar (y: 52 to 92)
        sess_bg = "#181B26"
        self.canvas.create_rectangle(0, 52, sb_w, 92, fill=sess_bg, outline="#232734")
        
        active_sess = self.get_active_session()
        sess_title = active_sess.get("name", "Session")
        if len(sess_title) > 13:
            sess_title = sess_title[:11] + "..."

        btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2 = 10, 58, sb_w - 74, 86
        self.sidebar_session_btn_rect = (btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2)
        self.canvas.create_rectangle(btn_s_x1, btn_s_y1, btn_s_x2, btn_s_y2, fill="#1F2332", outline="#00E5FF" if self.show_session_dropdown else "#2E374D")
        self.canvas.create_text(btn_s_x1 + 8, 72, text=f"📂 {sess_title} ▼", fill="#FFFFFF", font=("Helvetica", 8, "bold"), anchor="w")

        # Rename Session Button [ ✏️ ]
        btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2 = sb_w - 68, 58, sb_w - 40, 86
        self.sidebar_rename_sess_btn_rect = (btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2)
        self.canvas.create_rectangle(btn_ren_x1, btn_ren_y1, btn_ren_x2, btn_ren_y2, fill="#181B26", outline="#2E374D")
        self.canvas.create_text((btn_ren_x1 + btn_ren_x2) // 2, 72, text="✏️", fill="#A0A5B5", font=("Helvetica", 9))

        # New Session Button [ ＋ ]
        btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2 = sb_w - 36, 58, sb_w - 8, 86
        self.sidebar_new_sess_btn_rect = (btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2)
        self.canvas.create_rectangle(btn_add_x1, btn_add_y1, btn_add_x2, btn_add_y2, fill="#0E2A38", outline="#00E5FF")
        self.canvas.create_text((btn_add_x1 + btn_add_x2) // 2, 72, text="＋", fill="#00E5FF", font=("Helvetica", 11, "bold"))

        # 3. Filter Bar (y: 92 to 128)
        self.canvas.create_rectangle(0, 92, sb_w, 128, fill="#151720", outline="#232734")
        
        filt_x1, filt_y1, filt_x2, filt_y2 = 10, 97, sb_w - 82, 123
        self.sidebar_filter_btn_rect = (filt_x1, filt_y1, filt_x2, filt_y2)
        filt_label = f"🎯 {self.club_filter} ▼"
        self.canvas.create_rectangle(filt_x1, filt_y1, filt_x2, filt_y2, fill="#1B1E2B", outline="#00E5FF" if self.show_filter_dropdown else "#2E374D")
        self.canvas.create_text(filt_x1 + 8, 110, text=filt_label, fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        filtered_shots = self.get_filtered_shots()
        count_str = f"{len(filtered_shots)} shots"
        self.canvas.create_rectangle(sb_w - 76, 97, sb_w - 10, 123, fill="#181A24", outline="#262B3B")
        self.canvas.create_text(sb_w - 43, 110, text=count_str, fill="#8E94A5", font=("Consolas", 8))

        # 4. Shot Card Stream (y: 132 to h - 42)
        card_stream_y1 = 132
        card_stream_y2 = h - 42
        card_h = 56
        card_gap = 6

        self.sidebar_shot_card_rects.clear()

        if not filtered_shots:
            self.canvas.create_text(sb_w // 2, 220, text="NO SHOTS RECORDED", fill="#353A4B", font=("Helvetica", 10, "bold"))
            self.canvas.create_text(sb_w // 2, 245, text="Hit a shot with Nova or\nchange active club filter.", fill="#606678", font=("Helvetica", 8), justify="center")
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

                card_bg = "#2C2A0A" if is_selected else ("#191C26" if i % 2 == 0 else "#151720")
                card_border = "#FFEA00" if is_selected else "#282D3D"
                border_w = 2 if is_selected else 1

                self.canvas.create_rectangle(10, cy1, sb_w - 10, cy2, fill=card_bg, outline=card_border, width=border_w)

                ogc = shot.get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                carry = us.get("carry_distance_yards", 0.0)
                bspeed = us.get("ball_speed_mph", 0.0)
                smash = ogc.get("smash_factor", 1.0)
                s_name = ogc.get("shot_name", {}).get("right_handed", "Shot")
                c_tag = shot.get("club", "Club")
                t_stamp = shot.get("timestamp", "--:--")

                # Line 1: #N  [Club]  Carry
                num_txt = f"#{real_idx + 1}"
                self.canvas.create_text(18, cy1 + 12, text=num_txt, fill="#FFEA00" if is_selected else "#FFFFFF", font=("Consolas", 9, "bold"), anchor="w")
                self.canvas.create_text(52, cy1 + 12, text=f"[{c_tag}]", fill="#00E5FF", font=("Consolas", 8, "bold"), anchor="w")
                self.canvas.create_text(sb_w - 18, cy1 + 12, text=f"{carry:.1f} yds", fill="#00FF66" if is_selected else "#FFFFFF", font=("Consolas", 9, "bold"), anchor="e")

                # Line 2: Speed & Shot Name
                self.canvas.create_text(18, cy1 + 28, text=f"{bspeed:.1f} mph  •  {s_name}", fill="#00E5FF" if is_selected else "#AAB0C0", font=("Helvetica", 8), anchor="w")

                # Line 3: Timestamp & Smash
                self.canvas.create_text(18, cy1 + 44, text=f"{t_stamp}  •  Smash {smash:.2f}", fill="#6B7285", font=("Consolas", 8), anchor="w")

        # 5. Footer (y: h - 42 to h)
        clear_y1, clear_y2 = h - 38, h - 8
        self.sidebar_clear_btn_rect = (10, clear_y1, sb_w - 10, clear_y2)
        self.canvas.create_rectangle(10, clear_y1, sb_w - 10, clear_y2, fill="#231318", outline="#4A1E2A")
        self.canvas.create_text(sb_w // 2, (clear_y1 + clear_y2) // 2, text="🗑️ Clear Current Session", fill="#FF4081", font=("Helvetica", 8, "bold"))

    def draw_session_dropdown(self, w, h):
        box_w = self.sidebar_width - 20
        x1, y1 = 10, 88
        item_h = 28
        total_items = len(self.sessions) + 2  # +1 for Rename, +1 for + New Session
        box_h = total_items * item_h + 10
        x2, y2 = x1 + box_w, y1 + box_h

        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 + 3, y2 + 3, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#161822", outline="#00E5FF", width=2)
        
        self.session_menu_items.clear()
        for idx, sess in enumerate(self.sessions):
            iy1 = y1 + 5 + (idx * item_h)
            iy2 = iy1 + item_h - 2
            self.session_menu_items.append((x1 + 4, iy1, x2 - 4, iy2, idx))

            is_sel = (idx == self.active_session_index)
            bg = "#0E2A38" if is_sel else ("#1C1F2B" if idx % 2 == 0 else "#161822")
            s_name = sess.get("name", f"Session {idx+1}")
            shot_cnt = len(sess.get("shots", []))

            self.canvas.create_rectangle(x1 + 4, iy1, x2 - 4, iy2, fill=bg, outline="#00E5FF" if is_sel else "")
            self.canvas.create_text(x1 + 10, (iy1 + iy2) // 2, text=f"📂 {s_name}", fill="#00E5FF" if is_sel else "#D0D5DD", font=("Helvetica", 8, "bold" if is_sel else "normal"), anchor="w")
            self.canvas.create_text(x2 - 10, (iy1 + iy2) // 2, text=f"{shot_cnt}s", fill="#70788C", font=("Consolas", 8), anchor="e")

        # ✏️ Rename Active Session item
        ren_iy1 = y1 + 5 + (len(self.sessions) * item_h)
        ren_iy2 = ren_iy1 + item_h - 2
        self.session_menu_items.append((x1 + 4, ren_iy1, x2 - 4, ren_iy2, -2))
        self.canvas.create_rectangle(x1 + 4, ren_iy1, x2 - 4, ren_iy2, fill="#1C2130", outline="#2E374D")
        self.canvas.create_text(x1 + 10, (ren_iy1 + ren_iy2) // 2, text="✏️  Rename Active Session", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        # + Add New Session item
        add_iy1 = y1 + 5 + ((len(self.sessions) + 1) * item_h)
        add_iy2 = add_iy1 + item_h - 2
        self.session_menu_items.append((x1 + 4, add_iy1, x2 - 4, add_iy2, -1))
        self.canvas.create_rectangle(x1 + 4, add_iy1, x2 - 4, add_iy2, fill="#0D2A1C", outline="#00FF66")
        self.canvas.create_text(x1 + 10, (add_iy1 + add_iy2) // 2, text="＋  Create New Session", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")

    def draw_filter_dropdown(self, w, h):
        box_w = 180
        x1, y1 = 10, 125
        options = ["ALL"] + self.clubs
        item_h = 22
        box_h = min(360, len(options) * item_h + 10)
        x2, y2 = x1 + box_w, y1 + box_h

        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 + 3, y2 + 3, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#161822", outline="#00E5FF", width=2)

        self.filter_menu_items.clear()
        for idx, club_opt in enumerate(options[:15]):
            iy1 = y1 + 5 + (idx * item_h)
            iy2 = iy1 + item_h - 2
            self.filter_menu_items.append((x1 + 4, iy1, x2 - 4, iy2, club_opt))

            is_sel = (club_opt == self.club_filter)
            bg = "#0E2A38" if is_sel else ("#1C1F2B" if idx % 2 == 0 else "#161822")
            label = "All Clubs (No Filter)" if club_opt == "ALL" else f"🏌️ {club_opt}"

            self.canvas.create_rectangle(x1 + 4, iy1, x2 - 4, iy2, fill=bg, outline="#00E5FF" if is_sel else "")
            self.canvas.create_text(x1 + 10, (iy1 + iy2) // 2, text=label, fill="#00E5FF" if is_sel else "#D0D5DD", font=("Helvetica", 8, "bold" if is_sel else "normal"), anchor="w")

    def draw_top_header(self, w, h, offset_x=0):
        header_h = 52
        avail_w = w - offset_x
        # Header Background & Bottom Border
        self.canvas.create_rectangle(offset_x, 0, w, header_h, fill="#12141A", outline="#242834")

        # 1. Drawer Hamburger Toggle & Branding
        if self.sidebar_collapsed:
            hamb_x1, hamb_y1, hamb_x2, hamb_y2 = 10, 10, 42, 42
            self.sidebar_toggle_rect = (hamb_x1, hamb_y1, hamb_x2, hamb_y2)
            self.canvas.create_rectangle(hamb_x1, hamb_y1, hamb_x2, hamb_y2, fill="#181A24", outline="#00E5FF")
            self.canvas.create_text(26, 26, text="☰", fill="#00E5FF", font=("Helvetica", 12, "bold"), anchor="center")
            brand_x = 52
            brand_text = "SHANKTUARY STUDIO"
        else:
            brand_x = offset_x + 12
            brand_text = "STUDIO" if avail_w < 1050 else "SHANKTUARY STUDIO"

        brand_id = self.canvas.create_text(brand_x, 26, text=brand_text, fill="#00E5FF", font=("Helvetica", 10, "bold"), anchor="w")
        brand_bbox = self.canvas.bbox(brand_id)
        if brand_bbox and isinstance(brand_bbox, (tuple, list)) and len(brand_bbox) >= 4 and isinstance(brand_bbox[2], (int, float)):
            brand_right = int(brand_bbox[2])
        else:
            brand_right = brand_x + (50 if brand_text == "STUDIO" else 150)
        
        # Status Box
        if avail_w < 1050 and not self.sidebar_collapsed:
            status_text = "● Nova" if (self.nova_connected or len(self.session_shots) > 0) else "● Ready"
            status_w = 60
        else:
            status_text = "● Nova Ready" if (self.nova_connected or len(self.session_shots) > 0) else "● Ready"
            status_w = 86

        status_x1 = brand_right + 8
        status_x2 = status_x1 + status_w
        self.canvas.create_rectangle(status_x1, 12, status_x2, 40, fill="#0D2618", outline="#00FF66")
        self.canvas.create_text((status_x1 + status_x2) // 2, 26, text=status_text, fill="#00FF66", font=("Helvetica", 7, "bold"), anchor="center")

        # 2. Right Utility Pills
        fs_w = 28
        tools_w = 64
        club_w = 92
        gap = 6

        fs_x2 = w - 10
        fs_x1 = fs_x2 - fs_w
        self.fullscreen_btn_rect = (fs_x1, 10, fs_x2, 42)
        self.canvas.create_rectangle(fs_x1, 10, fs_x2, 42, fill="#181A22", outline="#2E3342")
        self.canvas.create_text((fs_x1 + fs_x2) // 2, 26, text="⛶", fill="#A0A5B5", font=("Helvetica", 11, "bold"), anchor="center")

        tools_x2 = fs_x1 - gap
        tools_x1 = tools_x2 - tools_w
        self.tools_btn_rect = (tools_x1, 10, tools_x2, 42)
        t_bg = "#0E2A38" if self.show_tools_menu else "#181A22"
        t_border = "#00E5FF" if self.show_tools_menu else "#2E3342"
        self.canvas.create_rectangle(tools_x1, 10, tools_x2, 42, fill=t_bg, outline=t_border)
        self.canvas.create_text((tools_x1 + tools_x2) // 2, 26, text="Tools  ▼", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="center")

        club_x2 = tools_x1 - gap
        club_x1 = club_x2 - club_w
        self.club_btn_rect = (club_x1, 10, club_x2, 42)
        c_bg = "#0E2A38" if self.show_club_menu else "#181A22"
        c_border = "#00E5FF" if self.show_club_menu else "#2E3342"
        self.canvas.create_rectangle(club_x1, 10, club_x2, 42, fill=c_bg, outline=c_border)
        self.canvas.create_text((club_x1 + club_x2) // 2, 26, text=f"{self.current_club}  ▼", fill="#FFFFFF", font=("Helvetica", 8, "bold"), anchor="center")

        # 3. Segmented Mode Pills (Responsive fitting between status_x2 and club_x1)
        left_limit = status_x2 + 8
        right_limit = club_x1 - 8
        avail_middle = right_limit - left_limit
        n_tabs = 8
        tab_gap = 3
        calc_tab_w = (avail_middle - (n_tabs - 1) * tab_gap) // n_tabs
        tab_w = max(46, min(76, calc_tab_w))
        total_tab_w = n_tabs * tab_w + (n_tabs - 1) * tab_gap
        start_tab_x = max(left_limit, left_limit + (avail_middle - total_tab_w) // 2)

        if tab_w >= 70:
            mode_tabs = [
                (1, "Quad View"),
                (2, "3D Range"),
                (3, "Dispersion"),
                (4, "Table"),
                (5, "Big Numbers"),
                (6, "My Bag"),
                (7, "Club Fitting"),
                (8, "Swing Lab")
            ]
            tab_font = ("Helvetica", 8)
            tab_font_bold = ("Helvetica", 8, "bold")
        elif tab_w >= 54:
            mode_tabs = [
                (1, "Quad"),
                (2, "Range"),
                (3, "Dispersion"),
                (4, "Table"),
                (5, "Numbers"),
                (6, "My Bag"),
                (7, "Fitting"),
                (8, "Swing Lab")
            ]
            tab_font = ("Helvetica", 7)
            tab_font_bold = ("Helvetica", 7, "bold")
        else:
            mode_tabs = [
                (1, "Quad"),
                (2, "Range"),
                (3, "Disp"),
                (4, "Table"),
                (5, "Nums"),
                (6, "Bag"),
                (7, "Fit"),
                (8, "Lab")
            ]
            tab_font = ("Helvetica", 7)
            tab_font_bold = ("Helvetica", 7, "bold")

        for i, (m_id, label) in enumerate(mode_tabs):
            x1 = start_tab_x + i * (tab_w + tab_gap)
            x2 = x1 + tab_w
            y1, y2 = 10, 42
            self.mode_pill_rects[m_id] = (x1, y1, x2, y2)

            is_active = (self.view_mode == m_id)
            bg_col = "#0E2A38" if is_active else "#181A22"
            border_col = "#00E5FF" if is_active else "#282C3A"
            txt_col = "#00E5FF" if is_active else "#8E94A5"
            txt_font = tab_font_bold if is_active else tab_font

            self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg_col, outline=border_col)
            self.canvas.create_text((x1 + x2) // 2, (y1 + y2) // 2, text=label, fill=txt_col, font=txt_font, anchor="center")

    def draw_top_metric_toolbar(self, avail_w, ball_speed, club_speed, smash, carry, total, offline, hang_time, eff_pct, offset_x=0):
        top_y = 52
        bar_h = 56
        bot_y = top_y + bar_h
        self.canvas.create_rectangle(offset_x, top_y, offset_x + avail_w, bot_y, fill="#15171F", outline="#232632")

        off_abs = abs(offline)
        off_dir = "L" if offline < 0 else "R"
        off_str = f"{off_abs:.1f} {off_dir} YDS" if off_abs > 0.1 else "0.0 STRAIGHT"

        metrics = [
            ("BALL SPEED", f"{ball_speed:.1f} MPH", "#FFFFFF"),
            ("CLUB SPEED", f"{club_speed:.1f} MPH", "#FFFFFF"),
            ("SMASH FACTOR", f"{smash:.2f}", "#00E5FF"),
            ("CARRY", f"{carry:.1f} YDS", "#00FF66"),
            ("TOTAL", f"{total:.1f} YDS", "#FFFFFF"),
            ("OFFLINE", off_str, "#00E5FF" if off_abs <= 4.0 else ("#FFEA00" if off_abs <= 12.0 else "#FF4081")),
            ("HANG TIME", f"{hang_time:.1f} SEC", "#A0A5B5"),
            ("EFFICIENCY", f"{eff_pct:.0f}%", "#00E5FF")
        ]

        col_w = avail_w / len(metrics)
        for i, (label, val, val_col) in enumerate(metrics):
            cx = int(offset_x + i * col_w + col_w / 2)
            self.canvas.create_text(cx, top_y + 16, text=label, fill="#7E8496", font=("Helvetica", 8, "bold"))
            self.canvas.create_text(cx, top_y + 37, text=val, fill=val_col, font=("Consolas", 12, "bold"))
            if i < len(metrics) - 1:
                self.canvas.create_line(int(offset_x + (i + 1) * col_w), top_y + 10, int(offset_x + (i + 1) * col_w), bot_y - 10, fill="#232632")

    def draw_club_dropdown(self, w, h):
        box_w = 180
        x1 = w - 245
        x2 = x1 + box_w
        y1 = 48
        item_h = 24
        custom_btn_h = 28
        total_items = len(self.clubs)
        box_h = total_items * item_h + custom_btn_h + 16
        y2 = y1 + box_h

        self.canvas.create_rectangle(x1 + 4, y1 + 4, x2 + 4, y2 + 4, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#161822", outline="#00E5FF", width=2)
        self.canvas.create_text(x1 + 14, y1 + 12, text="SELECT ACTIVE CLUB", fill="#7E8496", font=("Helvetica", 8, "bold"), anchor="w")

        self.club_menu_items.clear()
        for idx, club_name in enumerate(self.clubs):
            iy1 = y1 + 22 + (idx * item_h)
            iy2 = iy1 + item_h - 2
            self.club_menu_items.append((x1 + 6, iy1, x2 - 6, iy2, club_name))

            is_sel = (club_name == self.current_club)
            bg = "#0E2A38" if is_sel else ("#1D202B" if idx % 2 == 0 else "#161822")
            txt_col = "#00E5FF" if is_sel else "#D0D5DD"
            
            self.canvas.create_rectangle(x1 + 6, iy1, x2 - 6, iy2, fill=bg, outline="#00E5FF" if is_sel else "")
            self.canvas.create_text(x1 + 16, (iy1 + iy2) // 2, text=f"🏌️  {club_name}", fill=txt_col, font=("Helvetica", 8, "bold" if is_sel else "normal"), anchor="w")

        # Divider & Add Custom Club Action
        div_y = y1 + 22 + (total_items * item_h) + 2
        self.canvas.create_line(x1 + 6, div_y, x2 - 6, div_y, fill="#282E40", width=1)

        btn_y1 = div_y + 4
        btn_y2 = btn_y1 + 22
        self.club_menu_items.append((x1 + 6, btn_y1, x2 - 6, btn_y2, "__add_custom__"))
        self.canvas.create_rectangle(x1 + 6, btn_y1, x2 - 6, btn_y2, fill="#142C24", outline="#00FF66", width=1)
        self.canvas.create_text((x1 + x2) // 2, (btn_y1 + btn_y2) // 2, text="＋ Add Custom Club...", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="center")

    def draw_tools_flyout_menu(self, w, h):
        box_w = 320
        x2 = w - 16
        x1 = x2 - box_w
        y1 = 48
        y2 = y1 + 395

        self.canvas.create_rectangle(x1 + 4, y1 + 4, x2 + 4, y2 + 4, fill="#08090C", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#161922", outline="#00E5FF", width=2)

        self.tools_menu_items.clear()
        curr_y = y1 + 14

        self.canvas.create_text(x1 + 14, curr_y, text="⚙️ STUDIO TOOLS & STREAMING", fill="#00E5FF", font=("Helvetica", 10, "bold"), anchor="w")
        curr_y += 24

        # Section 1: Broadcast & Overlays
        self.canvas.create_text(x1 + 14, curr_y, text="🎥 BROADCAST & OVERLAYS", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")
        curr_y += 14

        btn1_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn1_rect[0], btn1_rect[1], btn1_rect[2], btn1_rect[3], "open_config"))
        self.canvas.create_rectangle(btn1_rect[0], btn1_rect[1], btn1_rect[2], btn1_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn1_rect[1] + btn1_rect[3]) // 2, text="🎛️ OBS Overlay Config (/config)", fill="#FFFFFF", font=("Helvetica", 8, "bold"), anchor="w")
        curr_y += 32

        btn2_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn2_rect[0], btn2_rect[1], btn2_rect[2], btn2_rect[3], "copy_obs_url"))
        self.canvas.create_rectangle(btn2_rect[0], btn2_rect[1], btn2_rect[2], btn2_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn2_rect[1] + btn2_rect[3]) // 2, text="📋 Copy Full Overlay URL (OBS)", fill="#D0D5DD", font=("Helvetica", 8), anchor="w")
        curr_y += 32

        btn3_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn3_rect[0], btn3_rect[1], btn3_rect[2], btn3_rect[3], "open_range"))
        self.canvas.create_rectangle(btn3_rect[0], btn3_rect[1], btn3_rect[2], btn3_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn3_rect[1] + btn3_rect[3]) // 2, text="⛳ Open 3D Range Source (/range)", fill="#D0D5DD", font=("Helvetica", 8), anchor="w")
        curr_y += 36

        # Section 2: Floor Projection & Virtual Divot
        self.canvas.create_text(x1 + 14, curr_y, text="🎯 FLOOR PROJECTION & VIRTUAL DIVOT", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")
        curr_y += 14

        btn4_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn4_rect[0], btn4_rect[1], btn4_rect[2], btn4_rect[3], "copy_divot_url"))
        self.canvas.create_rectangle(btn4_rect[0], btn4_rect[1], btn4_rect[2], btn4_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn4_rect[1] + btn4_rect[3]) // 2, text="📋 Copy Virtual Divot URL (/divot)", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")
        curr_y += 32

        btn5_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn5_rect[0], btn5_rect[1], btn5_rect[2], btn5_rect[3], "open_divot"))
        self.canvas.create_rectangle(btn5_rect[0], btn5_rect[1], btn5_rect[2], btn5_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn5_rect[1] + btn5_rect[3]) // 2, text="🎯 Open Virtual Divot (/divot)", fill="#D0D5DD", font=("Helvetica", 8), anchor="w")
        curr_y += 32

        btn6_rect = (x1 + 10, curr_y, x2 - 10, curr_y + 26)
        self.tools_menu_items.append((btn6_rect[0], btn6_rect[1], btn6_rect[2], btn6_rect[3], "set_mode_2"))
        self.canvas.create_rectangle(btn6_rect[0], btn6_rect[1], btn6_rect[2], btn6_rect[3], fill="#1F2432", outline="#2E374D")
        self.canvas.create_text(x1 + 18, (btn6_rect[1] + btn6_rect[3]) // 2, text="🎚️ Switch App to Divot Mode (2)", fill="#D0D5DD", font=("Helvetica", 8), anchor="w")
        curr_y += 36

        # Section 3: Hardware
        self.canvas.create_text(x1 + 14, curr_y, text="📡 NOVA & HARDWARE", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")
        curr_y += 16
        self.canvas.create_text(x1 + 18, curr_y, text="Host: 192.168.40.249:2920 (mDNS Ready)", fill="#8E94A5", font=("Consolas", 8), anchor="w")

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

            closure_rate = ogc.get("face_closure_rate_dps") or self.current_shot.get("face_closure_rate_dps") or self.current_shot.get("closure_rate")
            if closure_rate is None:
                closure_rate = 1800 + abs(face_to_path) * 320 + (club_speed_mph * 12.5) if club_speed_mph > 20 else 0.0

            attack_angle = ogc.get("angle_of_attack_degrees", {}).get("right_handed") if isinstance(ogc.get("angle_of_attack_degrees"), dict) else ogc.get("angle_of_attack_degrees", self.current_shot.get("angle_of_attack_degrees", vert_launch * 0.3 - 4.5))
            dynamic_loft = ogc.get("dynamic_loft_degrees", {}).get("right_handed") if isinstance(ogc.get("dynamic_loft_degrees"), dict) else ogc.get("dynamic_loft_degrees", self.current_shot.get("dynamic_loft_degrees", vert_launch * 0.85))
            
            shot_name = ogc.get("shot_name", {}).get("right_handed", "Shot")
            shot_rank = ogc.get("shot_rank", {}).get("right_handed", "B")
        else:
            club_path = face_to_path = face_to_target = vert_launch = horiz_launch = sidespin = backspin = spin_axis = total_spin = smash = hang_time = descent_angle = eff_pct = ball_speed_mph = club_speed_mph = carry_yds = total_yds = offline_yds = peak_height_yds = optimal_max_yds = closure_rate = attack_angle = dynamic_loft = 0.0
            shot_name = "Ready"
            shot_rank = "-"

        # Layout Geometry Offset
        offset_x = self.sidebar_width if not self.sidebar_collapsed else 0
        avail_w = w - offset_x

        # 1. Left Shot Library Sidebar
        self.draw_left_sidebar(w, h)

        # 2. Top Navigation Bar
        self.draw_top_header(w, h, offset_x=offset_x)

        # 3. Workspace View Routing
        if self.view_mode == 1:
            # Mode 1: Delivery (4-Quadrant Studio)
            self.draw_top_metric_toolbar(avail_w, ball_speed_mph, club_speed_mph, smash, carry_yds, total_yds, offline_yds, hang_time, eff_pct, offset_x=offset_x)
            if self.current_shot:
                self.draw_4_quadrant_studio(avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, peak_height_yds, descent_angle, optimal_max_yds, eff_pct, shot_name, shot_rank, smash, offset_x=offset_x)
            else:
                self.canvas.create_text(offset_x + avail_w // 2, (h + 108) // 2, text="READY FOR SHOT", fill="#282C38", font=("Helvetica", 32, "bold"))
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
        elif self.view_mode == 0:
            # Mode 0: Floor Divot Focus Projector
            self.draw_divot_focus(avail_w, h, club_path, face_to_path, ball_speed_mph, club_speed_mph, carry_yds, shot_name, offset_x=offset_x)
        else:
            self.draw_top_metric_toolbar(avail_w, ball_speed_mph, club_speed_mph, smash, carry_yds, total_yds, offline_yds, hang_time, eff_pct, offset_x=offset_x)
            if self.current_shot:
                self.draw_4_quadrant_studio(avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, peak_height_yds, descent_angle, optimal_max_yds, eff_pct, shot_name, shot_rank, smash, offset_x=offset_x)

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

        # 6. Toast Notification (Always on Top)
        if self.copy_feedback:
            msg = self.copy_feedback if self.copy_feedback.startswith("✓") or self.copy_feedback.startswith("🦶") else f"✓ {self.copy_feedback}"
            toast_w = max(260, len(msg) * 8 + 36)
            self.canvas.create_rectangle((w - toast_w) // 2, h - 52, (w + toast_w) // 2, h - 18, fill="#0E2A1B", outline="#00FF66", width=2)
            self.canvas.create_text(w // 2, h - 35, text=msg, fill="#00FF66", font=("Helvetica", 9, "bold"))

    def draw_3d_range_viewport(self, avail_w, h, carry_yds, total_yds, ball_speed, club_speed, apex_yds, offline_yds, total_spin, vert_launch, horiz_launch, offset_x=0):
        self.range_launch_web_rect = None
        top_y = 52
        horizon_y = top_y + int((h - top_y) * 0.28)
        ground_y = h - 25

        # 1. Sky Gradient Background
        self.canvas.create_rectangle(offset_x, top_y, offset_x + avail_w, horizon_y, fill="#0B0F19", outline="")
        self.canvas.create_rectangle(offset_x, horizon_y - 2, offset_x + avail_w, horizon_y + 2, fill="#182338", outline="")

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
        self.canvas.create_polygon(mtn_pts, fill="#0F1624", outline="#192336")

        # 2. Ground & Perspective Fairway
        self.canvas.create_rectangle(offset_x, horizon_y, offset_x + avail_w, h, fill="#09140C", outline="")

        fx1 = offset_x + int(avail_w * 0.32)
        fx2 = offset_x + int(avail_w * 0.68)
        bx1 = offset_x + 30
        bx2 = offset_x + avail_w - 30

        fairway_poly = [fx1, horizon_y, fx2, horizon_y, bx2, ground_y, bx1, ground_y]
        self.canvas.create_polygon(fairway_poly, fill="#122518", outline="#1D3E28", width=2)

        # Center target line
        cx_top = (fx1 + fx2) // 2
        cx_bot = (bx1 + bx2) // 2
        self.canvas.create_line(cx_bot, ground_y, cx_top, horizon_y, fill="#00FF66", width=2, dash=(6, 4))

        # Yardage Arcs & Pins
        yardages = [50, 100, 150, 200, 250, 300, 350]
        pin_colors = {100: "#FF1744", 150: "#FFFFFF", 200: "#2979FF", 250: "#FFD600", 300: "#00E676"}
        
        for yds in yardages:
            frac = yds / 380.0
            arc_y = ground_y - int((ground_y - horizon_y) * (frac ** 0.74))
            w_at_y = (bx2 - bx1) + ((fx2 - fx1) - (bx2 - bx1)) * ((ground_y - arc_y) / (ground_y - horizon_y))
            ax1 = cx_bot - int(w_at_y * 0.46)
            ax2 = cx_bot + int(w_at_y * 0.46)
            
            # Arc curve
            self.canvas.create_line(ax1, arc_y, ax2, arc_y, fill="#23422C", width=1, dash=(3, 3))
            
            # Distance Signboard
            self.canvas.create_rectangle(cx_bot - 18, arc_y - 8, cx_bot + 18, arc_y + 8, fill="#0E2114", outline="#00FF66" if yds == 150 else "#254830")
            self.canvas.create_text(cx_bot, arc_y, text=str(yds), fill="#00FF66" if yds == 150 else "#8E9F94", font=("Consolas", 8, "bold"))

            # Pin Flag
            if yds in pin_colors:
                p_col = pin_colors[yds]
                pin_x = cx_bot + (35 if yds % 2 == 0 else -35)
                pin_y = arc_y
                self.canvas.create_line(pin_x, pin_y, pin_x, pin_y - 18, fill="#FFFFFF", width=2)
                self.canvas.create_polygon(pin_x, pin_y - 18, pin_x + 10, pin_y - 13, pin_x, pin_y - 8, fill=p_col, outline="")

        # 3. Multi-Shot Tracer History & Active Shot
        for s in self.session_shots[:-1]:
            if s.get("excluded", False):
                continue
            s_ogc = s.get("open_golf_coach", {})
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
                    self.canvas.create_line(past_pts, fill="#244B36", width=1, smooth=True)

        # Draw Active Shot Tracer & Curtain
        if carry_yds > 0:
            traj_pts = []
            ground_pts = []
            apex_pt = None
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
                    apex_pt = (gx, ty, apex_yds)

            # Shadow Curtain dropped to ground
            curtain_poly = []
            for p in traj_pts:
                curtain_poly.extend([p[0], p[1]])
            for p in reversed(ground_pts):
                curtain_poly.extend([p[0], p[1]])
            if len(curtain_poly) >= 6:
                self.canvas.create_polygon(curtain_poly, fill="#00E5FF", outline="", stipple="gray25")

            # Ground landing path
            flat_pts = []
            for p in ground_pts:
                flat_pts.extend([p[0], p[1]])
            self.canvas.create_line(flat_pts, fill="#008855", width=2, dash=(4, 2))

            # Neon flight tracer line
            flight_pts = []
            for p in traj_pts:
                flight_pts.extend([p[0], p[1]])
            self.canvas.create_line(flight_pts, fill="#00FF66", width=3, smooth=True)

            # Landing impact circle
            lx, ly = ground_pts[-1]
            self.canvas.create_oval(lx - 12, ly - 6, lx + 12, ly + 6, fill="", outline="#00FF66", width=2)
            self.canvas.create_oval(lx - 4, ly - 2, lx + 4, ly + 2, fill="#00FF66", outline="")
            
            # Carry Flag Tag
            self.canvas.create_rectangle(lx - 34, ly - 28, lx + 34, ly - 10, fill="#0C2515", outline="#00FF66", width=2)
            self.canvas.create_text(lx, ly - 19, text=f"{carry_yds:.1f} YDS", fill="#00FF66", font=("Consolas", 8, "bold"))

            # Floating Apex Badge
            if apex_pt:
                ax, ay, a_val = apex_pt
                self.canvas.create_rectangle(ax - 32, ay - 20, ax + 32, ay - 4, fill="#0E2838", outline="#00E5FF")
                self.canvas.create_text(ax, ay - 12, text=f"▲ {a_val:.1f} yds", fill="#00E5FF", font=("Consolas", 8, "bold"))
        else:
            self.canvas.create_text(cx_bot, horizon_y + 80, text="READY FOR SHOT", fill="#1C3827", font=("Helvetica", 24, "bold"))

        # 4. Top Floating HUD Tiles
        hud_h = 48
        hud_y1 = top_y + 10
        hud_y2 = hud_y1 + hud_h
        
        off_dir = "L" if offline_yds < 0 else "R"
        off_str = f"{abs(offline_yds):.1f} {off_dir} YDS" if abs(offline_yds) > 0.1 else "0.0 STRAIGHT"

        hud_cards = [
            ("CARRY", f"{carry_yds:.1f} YDS", "#00FF66"),
            ("TOTAL", f"{total_yds:.1f} YDS", "#FFFFFF"),
            ("BALL SPEED", f"{ball_speed:.1f} MPH", "#FFFFFF"),
            ("CLUB SPEED", f"{club_speed:.1f} MPH", "#FFFFFF"),
            ("LAUNCH", f"{vert_launch:.1f}°", "#00E5FF"),
            ("TOTAL SPIN", f"{int(total_spin)} RPM", "#FFEA00"),
            ("APEX", f"{apex_yds:.1f} YDS", "#00E5FF"),
            ("OFFLINE", off_str, "#00E5FF" if abs(offline_yds) <= 5.0 else "#FF4081")
        ]
        
        card_w = (avail_w - 30) // len(hud_cards)
        for i, (h_title, h_val, h_col) in enumerate(hud_cards):
            hx1 = offset_x + 15 + i * card_w
            hx2 = hx1 + card_w - 6
            self.canvas.create_rectangle(hx1, hud_y1, hx2, hud_y2, fill="#121622", outline="#242B3B")
            self.canvas.create_text((hx1 + hx2) // 2, hud_y1 + 13, text=h_title, fill="#7E8799", font=("Helvetica", 7, "bold"))
            self.canvas.create_text((hx1 + hx2) // 2, hud_y1 + 33, text=h_val, fill=h_col, font=("Consolas", 10, "bold"))

        # 5. WebGPU Launch Button (Bottom Right)
        btn_w, btn_h = 240, 32
        bx2 = offset_x + avail_w - 15
        bx1 = bx2 - btn_w
        by2 = h - 12
        by1 = by2 - btn_h
        self.range_launch_web_rect = (bx1, by1, bx2, by2)
        self.canvas.create_rectangle(bx1, by1, bx2, by2, fill="#0E2838", outline="#00E5FF", width=2)
        self.canvas.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text="⛳ Open 3D WebGPU Range (/range) ↗", fill="#00E5FF", font=("Helvetica", 8, "bold"))

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
            self.canvas.create_rectangle(sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], fill="#0E2838" if is_active else "#161922", outline="#00E5FF" if is_active else "#282E40")
            self.canvas.create_text((sm_rect[0] + sm_rect[2]) // 2, (sm_rect[1] + sm_rect[3]) // 2, text=sm_label, fill="#00E5FF" if is_active else "#8E94A5", font=("Helvetica", 8, "bold" if is_active else "normal"))
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
        self.canvas.create_rectangle(split_x1, top_y, split_x2, bot_y, fill="#00E5FF" if is_dragging else "#161924", outline="#00E5FF" if is_dragging else "#252B3B")
        mid_y = (top_y + bot_y) // 2
        for dy in [-16, -8, 0, 8, 16]:
            self.canvas.create_line(split_x1 + 2, mid_y + dy, split_x2 - 2, mid_y + dy, fill="#FFFFFF" if is_dragging else "#50586D", width=1)

        # 2. Right Gapping & Distribution Panel
        self.canvas.create_rectangle(gap_x1, top_y, gap_x1 + gap_w, bot_y, fill="#12141D", outline="#232736")
        self.canvas.create_text(gap_x1 + 14, top_y + 16, text="📊 CLUB GAPPING & SPREAD", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")

        # Club Filter Chips along top of right panel
        chip_y1 = top_y + 30
        chip_y2 = chip_y1 + 22
        all_chip_rect = (gap_x1 + 10, chip_y1, gap_x1 + 55, chip_y2)
        self.dispersion_club_chip_rects.append((all_chip_rect[0], all_chip_rect[1], all_chip_rect[2], all_chip_rect[3], "ALL"))
        is_all = (self.dispersion_selected_club == "ALL")
        self.canvas.create_rectangle(all_chip_rect[0], all_chip_rect[1], all_chip_rect[2], all_chip_rect[3], fill="#0E2838" if is_all else "#181B26", outline="#00E5FF" if is_all else "#282E40")
        self.canvas.create_text((all_chip_rect[0] + all_chip_rect[2]) // 2, (chip_y1 + chip_y2) // 2, text="ALL", fill="#00E5FF" if is_all else "#8E94A5", font=("Helvetica", 8, "bold"))

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
            self.canvas.create_text(gap_x1 + gap_w // 2, top_y + 150, text="NO SHOTS RECORDED", fill="#353B4D", font=("Helvetica", 10, "bold"))
        else:
            prev_avg_carry = None
            for i, c_name in enumerate(session_clubs[:6]):
                cy1 = card_start_y + i * (card_h + card_gap)
                cy2 = cy1 + card_h
                if cy2 > bot_y:
                    break

                c_color = self.get_club_color(c_name)
                c_shots = [s for s in self.session_shots if s.get("club") == c_name and not s.get("excluded", False)]
                c_carries = [s.get("open_golf_coach", {}).get("us_customary_units", {}).get("carry_distance_yards", 0.0) for s in c_shots]
                c_carries = [x for x in c_carries if x > 0]
                c_offs = [s.get("open_golf_coach", {}).get("us_customary_units", {}).get("offline_distance_yards", 0.0) for s in c_shots]

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
                self.canvas.create_rectangle(gap_x1 + 10, cy1, gap_x1 + gap_w - 10, cy2, fill="#161924", outline="#252A3B")
                # Left accent color strip
                self.canvas.create_rectangle(gap_x1 + 10, cy1, gap_x1 + 15, cy2, fill=c_color, outline="")

                # Line 1: Club Name & Shot Count
                self.canvas.create_text(gap_x1 + 22, cy1 + 14, text=f"🏌️ {c_name}", fill="#FFFFFF", font=("Helvetica", 9, "bold"), anchor="w")
                self.canvas.create_text(gap_x1 + gap_w - 18, cy1 + 14, text=f"{len(c_shots)} shots", fill="#8E94A5", font=("Consolas", 8), anchor="e")

                # Line 2: Average Carry with Std Dev & Gap Delta
                gap_str = f"({avg_c - prev_avg_carry:+.1f}y gap)" if (prev_avg_carry is not None and avg_c > 0) else ""
                self.canvas.create_text(gap_x1 + 22, cy1 + 34, text=f"Carry: {avg_c:.1f} yds (±{std_c:.1f}y)  {gap_str}", fill=c_color, font=("Consolas", 9, "bold"), anchor="w")

                # Line 3: Min-Max window & Offline Dispersion
                self.canvas.create_text(gap_x1 + 22, cy1 + 52, text=f"Window: {min_c:.0f}–{max_c:.0f}y  •  Lateral: {abs(avg_off):.1f}y {off_dir}", fill="#8E94A5", font=("Helvetica", 8), anchor="w")

                if avg_c > 0:
                    prev_avg_carry = avg_c

    def _draw_side_trajectory_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, margin_x, chart_w, max_x_yds, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill="#13151D", outline="#232736")
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="📈 TRAJECTORY PROFILE (ELEVATION & APEX)", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")

        base_y = plot_y2 - 20
        chart_h = base_y - (plot_y1 + 28)
        max_h_yds = 60.0

        # X distance grid ticks
        ticks = [0, 50, 100, 150, 200, 250, 300, 350]
        for t in ticks:
            tx = margin_x + int((t / max_x_yds) * chart_w)
            self.canvas.create_line(tx, plot_y1 + 24, tx, base_y, fill="#1D202C", width=1, dash=(2, 2))
            self.canvas.create_text(tx, base_y + 10, text=str(t), fill="#5A6174", font=("Consolas", 7))

        # Y height grid lines
        for hy in [0, 20, 40, 60]:
            ty = base_y - int((hy / max_h_yds) * chart_h)
            self.canvas.create_line(margin_x, ty, margin_x + chart_w, ty, fill="#1D202C", width=1, dash=(2, 2))
            self.canvas.create_text(margin_x - 14, ty, text=f"{hy}y", fill="#5A6174", font=("Consolas", 7))

        # Ground baseline
        self.canvas.create_line(margin_x, base_y, margin_x + chart_w, base_y, fill="#00FF66", width=1)

        # Plot flight arcs for each shot
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            for real_idx, shot in items:
                ogc = shot.get("open_golf_coach", {})
                us = ogc.get("us_customary_units", {})
                c_yds = us.get("carry_distance_yards", 0.0)
                apex_y = us.get("peak_height_yards", 25.0)
                if c_yds <= 0:
                    continue

                is_sel = (real_idx == self.selected_shot_index)
                arc_col = "#FFEA00" if is_sel else c_color
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
                self.canvas.create_oval(land_x - (4 if is_sel else 2), base_y - (4 if is_sel else 2), land_x + (4 if is_sel else 2), base_y + (4 if is_sel else 2), fill="#FFEA00" if is_sel else c_color, outline="")

    def _draw_topdown_dispersion_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, max_range_yds, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill="#12141D", outline="#232736")
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="🎯 OVERHEAD DISPERSION & COVARIANCE ELLIPSES", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        plot_w = plot_x2 - plot_x1
        cx = (plot_x1 + plot_x2) // 2
        tee_y = plot_y2 - 16
        plot_h = tee_y - plot_y1 - 26
        max_lat_yds = 45.0

        # Centerline
        self.canvas.create_line(cx, tee_y, cx, plot_y1 + 22, fill="#2B3142", width=2, dash=(6, 4))

        # Lateral deviation guides
        for lat in [-30, -15, 15, 30]:
            lx = cx + int((lat / max_lat_yds) * (plot_w * 0.45))
            self.canvas.create_line(lx, tee_y, lx, plot_y1 + 24, fill="#1C202C", width=1, dash=(2, 4))
            self.canvas.create_text(lx, plot_y2 - 6, text=f"{abs(lat)}y{'L' if lat < 0 else 'R'}", fill="#5A6175", font=("Consolas", 7))

        # Concentric distance arcs
        for yds in [50, 100, 150, 200, 250, 300, 350]:
            frac = yds / max_range_yds
            arc_y = tee_y - int(frac * plot_h)
            self.canvas.create_line(plot_x1 + 10, arc_y, plot_x2 - 10, arc_y, fill="#1E2332", width=1, dash=(3, 3))
            self.canvas.create_text(plot_x1 + 20, arc_y, text=f"{yds}y", fill="#6B7285", font=("Consolas", 7))

        # Render Ellipses & Dots
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            carries = []
            offs = []
            for real_idx, s in items:
                ogc = s.get("open_golf_coach", {})
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
                self.canvas.create_line(cen_x - 5, cen_y, cen_x + 5, cen_y, fill="#FFFFFF", width=2)
                self.canvas.create_line(cen_x, cen_y - 5, cen_x, cen_y + 5, fill="#FFFFFF", width=2)
                self.canvas.create_text(cen_x, cen_y - ry1 - 8, text=f"{c_name}: {mu_c:.1f}y", fill=c_color, font=("Helvetica", 7, "bold"))

            # Draw dots
            for real_idx, s in items:
                ogc = s.get("open_golf_coach", {})
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
                self.canvas.create_oval(dx - r, dy - r, dx + r, dy + r, fill="#FFEA00" if is_sel else c_color, outline="#FFFFFF" if is_sel else "")


    def draw_shot_table_viewport(self, avail_w, h, offset_x=0):
        self.table_row_rects.clear()
        self.table_header_rects.clear()
        self.table_checkbox_rects.clear()

        top_y = 58
        table_x1 = offset_x + 10
        table_x2 = offset_x + avail_w - 10

        # 1. Pinned Summary Averages Banner (y: 58 to 98)
        avg_y1 = top_y
        avg_y2 = avg_y1 + 40
        self.canvas.create_rectangle(table_x1, avg_y1, table_x2, avg_y2, fill="#0C2534", outline="#00E5FF", width=2)
        
        avgs = self.calculate_session_averages()
        active_count = avgs.get("count", 0)
        
        # Left Tag Badge (Clean, contained, zero overlap)
        badge_x1 = table_x1 + 10
        badge_x2 = badge_x1 + 190
        self.canvas.create_rectangle(badge_x1, avg_y1 + 7, badge_x2, avg_y2 - 7, fill="#0E384D", outline="#00E5FF", width=1)
        self.canvas.create_text((badge_x1 + badge_x2) // 2, (avg_y1 + avg_y2) // 2, text=f"SESSION AVERAGES ({active_count})", fill="#00E5FF", font=("Helvetica", 8, "bold"))
        
        if avgs:
            metrics_x = badge_x2 + 16
            avg_metrics = (
                f"Carry: {avgs.get('carry', 0.0):.1f}y  |  "
                f"Ball Spd: {avgs.get('ball_speed', 0.0):.1f}mph  |  "
                f"Club Spd: {avgs.get('club_speed', 0.0):.1f}mph  |  "
                f"Smash: {avgs.get('smash', 1.0):.2f}  |  "
                f"Launch: {avgs.get('launch_angle', 0.0):.1f}°  |  "
                f"Spin: {int(avgs.get('total_spin', 0.0))}rpm  |  "
                f"Apex: {avgs.get('apex', 0.0):.1f}y  |  "
                f"Offline: {avgs.get('offline', 0.0):+.1f}y"
            )
            self.canvas.create_text(metrics_x, (avg_y1 + avg_y2) // 2, text=avg_metrics, fill="#00FF66", font=("Consolas", 9, "bold"), anchor="w")

        # 2. Interactive Column Headers (y: 104 to 132)
        head_y1 = 104
        head_y2 = 132
        self.canvas.create_rectangle(table_x1, head_y1, table_x2, head_y2, fill="#161822", outline="#262A3B")

        cols = [
            ("index", "#", 40, "c"),
            ("excluded", "Excl", 44, "c"),
            ("club", "Club", 68, "w"),
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

        curr_x = table_x1
        for col_key, col_title, col_w, align in cols:
            cx2 = min(table_x2, curr_x + col_w)
            self.table_header_rects.append((curr_x, head_y1, cx2, head_y2, col_key))
            
            is_sorted = (self.table_sort_col == col_key)
            sort_arrow = (" ▲" if self.table_sort_asc else " ▼") if is_sorted else ""
            txt_col = "#00E5FF" if is_sorted else "#8E94A5"
            
            if align == "c":
                tx = (curr_x + cx2) // 2
            elif align == "e":
                tx = cx2 - 8
            else:
                tx = curr_x + 8

            self.canvas.create_text(tx, (head_y1 + head_y2) // 2, text=col_title + sort_arrow, fill=txt_col, font=("Helvetica", 8, "bold"), anchor=align)
            curr_x = cx2

        # 3. Sortable Data Rows
        data_y1 = 134
        row_h = 28
        avail_rows = max(1, (h - data_y1 - 15) // row_h)
        
        raw_items = list(enumerate(self.session_shots))

        def get_sort_val(item):
            idx, s = item
            ogc = s.get("open_golf_coach", {})
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
            elif self.table_sort_col == "push_pull": return s.get("horizontal_launch_angle_degrees", 0.0)
            elif self.table_sort_col == "spin": return ogc.get("total_spin_rpm", 0.0)
            elif self.table_sort_col == "sidespin": return ogc.get("sidespin_rpm", 0.0)
            elif self.table_sort_col == "axis": return ogc.get("spin_axis_degrees", 0.0)
            elif self.table_sort_col == "path": return ogc.get("club_path_degrees", {}).get("right_handed", 0.0)
            elif self.table_sort_col == "face": return ogc.get("club_face_to_path_degrees", {}).get("right_handed", 0.0)
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
            bg = "#2B280A" if is_sel else ("#191C28" if r_i % 2 == 0 else "#141620")
            border = "#FFEA00" if is_sel else "#242838"
            txt_color = "#5A6175" if is_ex else ("#FFFFFF" if not is_sel else "#FFEA00")

            self.canvas.create_rectangle(table_x1, ry1, table_x2, ry2, fill=bg, outline=border, width=2 if is_sel else 1)
            self.table_row_rects.append((table_x1, ry1, table_x2, ry2, real_idx))

            ogc = shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            
            c_val = us.get("carry_distance_yards", 0.0)
            tot_val = us.get("total_distance_yards", 0.0)
            bs_val = us.get("ball_speed_mph", 0.0)
            cs_val = us.get("club_speed_mph", 0.0)
            sm_val = ogc.get("smash_factor", 1.0)
            la_val = shot.get("vertical_launch_angle_degrees", 0.0)
            hl_val = shot.get("horizontal_launch_angle_degrees", 0.0)
            sp_val = ogc.get("total_spin_rpm", 0.0)
            ss_val = ogc.get("sidespin_rpm", 0.0)
            sa_val = ogc.get("spin_axis_degrees", 0.0)
            cp_val = ogc.get("club_path_degrees", {}).get("right_handed", 0.0)
            fp_val = ogc.get("club_face_to_path_degrees", {}).get("right_handed", 0.0)
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
                "club_speed": f"{cs_val:.1f}",
                "smash": f"{sm_val:.2f}",
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
                    chk_color = "#FF4081" if is_ex else "#00FF66"
                    self.canvas.create_text((curr_x + cx2) // 2, (ry1 + ry2) // 2, text=val_text, fill=chk_color, font=("Consolas", 8, "bold"))
                else:
                    if align == "c":
                        tx = (curr_x + cx2) // 2
                    elif align == "e":
                        tx = cx2 - 8
                    else:
                        tx = curr_x + 8
                    self.canvas.create_text(tx, (ry1 + ry2) // 2, text=val_text, fill=txt_color, font=("Consolas", 8, "bold" if is_sel else "normal"), anchor=align)

                curr_x = cx2

    def draw_big_numbers_viewport(self, avail_w, h, carry, total, ball_speed, club_speed, smash, launch, spin, spin_axis, club_path, face_to_path, apex, offline, closure_rate=0.0, attack_angle=0.0, dynamic_loft=0.0, hang_time=0.0, offset_x=0):
        top_y = 60
        bot_y = h - 15
        grid_w = avail_w - 30
        grid_h = bot_y - top_y

        off_dir = "L" if offline < 0 else "R"
        path_dir = "In-Out" if club_path > 0 else "Out-In"
        face_dir = "Open" if face_to_path > 0 else "Closed"
        axis_dir = "R" if spin_axis > 0 else "L"
        apex_ft = apex * 3.0

        cards = [
            ("CARRY DISTANCE", f"{carry:.1f}", "YARDS", "#00FF66", "OPTIMAL" if carry > 150 else ""),
            ("TOTAL DISTANCE", f"{total:.1f}", "YARDS", "#FFFFFF", ""),
            ("BALL SPEED", f"{ball_speed:.1f}", "MPH", "#FFFFFF", "TOUR AVG" if ball_speed > 115 else ""),
            ("CLUB SPEED", f"{club_speed:.1f}", "MPH", "#FFFFFF", ""),
            ("SMASH FACTOR", f"{smash:.2f}", "RATIO", "#00E5FF", "HIGH" if smash >= 1.35 else ""),
            ("LAUNCH ANGLE", f"{launch:.1f}°", "DEGREES", "#00E5FF", "OPTIMAL" if 14 <= launch <= 20 else ""),
            ("TOTAL SPIN", f"{int(spin)}", "RPM", "#FFEA00", "MID SPIN"),
            ("SPIN AXIS", f"{abs(spin_axis):.1f}° {axis_dir}", "DEGREES", "#FF4081", "DRAW" if spin_axis < 0 else "FADE"),
            ("CLOSURE RATE", f"{int(closure_rate)}", "DEG / SEC", "#00FF66", "RELEASE" if closure_rate > 1500 else ""),
            ("APEX HEIGHT", f"{apex_ft:.1f}", "FEET", "#40C4FF", "APEX"),
            ("CLUB PATH", f"{abs(club_path):.1f}° {path_dir}", "DEGREES", "#00E5FF", ""),
            ("FACE TO PATH", f"{abs(face_to_path):.1f}° {face_dir}", "DEGREES", "#FFEA00", "SQUARE" if abs(face_to_path) < 1.5 else ""),
            ("ATTACK ANGLE", f"{attack_angle:+.1f}°", "DEGREES", "#00E5FF", ""),
            ("DYNAMIC LOFT", f"{dynamic_loft:.1f}°", "DEGREES", "#FFEA00", ""),
            ("HANG TIME", f"{hang_time:.1f}s", "SECONDS", "#A0A5B5", ""),
            ("OFFLINE", f"{abs(offline):.1f} {off_dir}", "YARDS", "#00FF66" if abs(offline) <= 4.0 else "#FF4081", "ON TARGET" if abs(offline) <= 4.0 else "OFFLINE")
        ]

        rows = 4
        cols = 4
        col_gap = 10
        row_gap = 10
        card_w = (grid_w - (cols - 1) * col_gap) // cols
        card_h = (grid_h - (rows - 1) * row_gap) // rows

        for idx, (c_label, c_val, c_unit, c_color, c_tag) in enumerate(cards):
            r = idx // cols
            c = idx % cols
            
            x1 = offset_x + 15 + c * (card_w + col_gap)
            y1 = top_y + r * (card_h + row_gap)
            x2 = x1 + card_w
            y2 = y1 + card_h

            # Card Container
            self.canvas.create_rectangle(x1, y1, x2, y2, fill="#151722", outline="#262C3D", width=2)
            
            # Header Label
            self.canvas.create_text(x1 + 14, y1 + 16, text=c_label, fill="#7E8799", font=("Helvetica", 8, "bold"), anchor="w")

            # Status pill in top right of card
            if c_tag:
                tag_w = len(c_tag) * 6 + 10
                self.canvas.create_rectangle(x2 - tag_w - 10, y1 + 8, x2 - 10, y1 + 24, fill="#0D261A" if ("OPTIMAL" in c_tag or "TOUR" in c_tag or "TARGET" in c_tag or "HIGH" in c_tag or "SQUARE" in c_tag) else "#26151A", outline=c_color)
                self.canvas.create_text(x2 - 10 - tag_w // 2, y1 + 16, text=c_tag, fill=c_color, font=("Helvetica", 7, "bold"), anchor="center")

            # Giant Primary Value (Centered in card)
            self.canvas.create_text((x1 + x2) // 2, y1 + (card_h // 2) + 4, text=c_val, fill=c_color, font=("Consolas", 26, "bold"), anchor="center")

            # Bottom Unit Tag
            self.canvas.create_text((x1 + x2) // 2, y2 - 12, text=c_unit, fill="#50566A", font=("Helvetica", 7, "bold"), anchor="center")

    def draw_4_quadrant_studio(self, avail_w, h, club_path, face_to_target, face_to_path, vert_launch, horiz_launch, sidespin, backspin, total_spin, spin_axis, apex_yds, descent, opt_max, eff_pct, shot_name, shot_rank, smash, offset_x=0):
        top_bar_h = 108
        avail_h = h - top_bar_h - 10
        mid_x = offset_x + (avail_w // 2)
        mid_y = top_bar_h + (avail_h // 2)

        self.canvas.create_line(mid_x, top_bar_h, mid_x, h - 10, fill="#232630", width=2)
        self.canvas.create_line(offset_x, mid_y, offset_x + avail_w, mid_y, fill="#232630", width=2)

        # Inspection Banner Header
        if 0 <= self.selected_shot_index < len(self.session_shots):
            insp_text = f"INSPECTING SHOT #{self.selected_shot_index + 1} OF {len(self.session_shots)}"
            self.canvas.create_text(mid_x, top_bar_h + 12, text=insp_text, fill="#FFEA00", font=("Helvetica", 9, "bold"))

        # Quadrant 1 (Top-Left): Overhead View
        q1_cx, q1_cy = offset_x + (avail_w // 4), top_bar_h + (avail_h // 4)
        q1_top = top_bar_h
        q1_bot = mid_y

        path_str = f"Path: {abs(club_path):.1f}° {'In To Out' if club_path > 0 else 'Out To In'}"
        face_target_str = f"Face To Target: {abs(face_to_target):.1f}° {'Open' if face_to_target > 0 else 'Closed'}"
        face_path_str = f"Face To Path: {abs(face_to_path):.1f}° {'Open' if face_to_path > 0 else 'Closed'}"

        self.canvas.create_text(q1_cx, q1_top + 22, text=path_str, fill="#00E5FF", font=("Consolas", 11, "bold"))
        self.canvas.create_line(q1_cx - 130, q1_cy, q1_cx + 130, q1_cy, fill="#40C4FF", width=1, dash=(4, 4))
        
        if self.overhead_img:
            rotated = self.overhead_img.rotate(-face_to_target, resample=Image.BICUBIC, expand=True)
            self.img_cache["q1_overhead"] = ImageTk.PhotoImage(rotated)
            self.canvas.create_image(q1_cx, q1_cy, image=self.img_cache["q1_overhead"], anchor="c")

        path_rad = math.radians(club_path)
        px1, py1 = self.rotate_point(q1_cx, q1_cy + 65, q1_cx, q1_cy, path_rad)
        px2, py2 = self.rotate_point(q1_cx, q1_cy - 65, q1_cx, q1_cy, path_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill="#00E5FF", width=3, arrow=tk.LAST)

        self.canvas.create_oval(q1_cx + 45 - 7, q1_cy - 7, q1_cx + 45 + 7, q1_cy + 7, fill="#FFFFFF", outline="#D0D5DD")

        self.canvas.create_text(q1_cx, q1_bot - 34, text=face_target_str, fill="#FFEA00", font=("Consolas", 10, "bold"))
        self.canvas.create_text(q1_cx, q1_bot - 16, text=face_path_str, fill="#FF4081", font=("Consolas", 10, "bold"))

        # Quadrant 2 (Bottom-Left): Trajectory Arc
        q2_cx, q2_cy = offset_x + (avail_w // 4), mid_y + (avail_h // 4)
        q2_top = mid_y
        q2_bot = h - 10
        ground_y = q2_cy + 30

        top_elev_str = f"Launch Angle: {vert_launch:.1f}°   |   Apex: {apex_yds:.1f} yds"
        bot_elev_str = f"Descent: {descent:.1f}°   |   Backspin: {int(backspin)} rpm"

        self.canvas.create_text(q2_cx, q2_top + 22, text=top_elev_str, fill="#00FF66", font=("Consolas", 10, "bold"))
        self.canvas.create_line(q2_cx - 140, ground_y, q2_cx + 140, ground_y, fill="#3A3F4D", width=2, dash=(4, 4))
        
        if self.side_img:
            self.img_cache["q2_side"] = ImageTk.PhotoImage(self.side_img)
            self.canvas.create_image(q2_cx - 85, ground_y - 20, image=self.img_cache["q2_side"], anchor="c")

        arc_pts = []
        for t in range(0, 101, 5):
            frac = t / 100.0
            x_p = (q2_cx - 85) + int(220 * frac)
            h_p = math.sin(frac * math.pi) * min(55, int(apex_yds * 16))
            y_p = ground_y - int(h_p)
            arc_pts.extend([x_p, y_p])
        
        self.canvas.create_line(arc_pts, fill="#00FF66", width=3, smooth=True)
        self.canvas.create_oval(q2_cx - 85 - 6, ground_y - 6, q2_cx - 85 + 6, ground_y + 6, fill="#FFFFFF")

        self.canvas.create_text(q2_cx, q2_bot - 16, text=bot_elev_str, fill="#E0E0E0", font=("Consolas", 10, "bold"))

        # Quadrant 3 (Top-Right): 3D Spin Axis
        q3_cx, q3_cy = offset_x + (3 * avail_w // 4), top_bar_h + (avail_h // 4)
        q3_top = top_bar_h
        q3_bot = mid_y
        
        rank_colors = {"A": "#00FF66", "B": "#00E5FF", "C": "#FFC107", "D": "#FF4081"}
        badge_color = rank_colors.get(shot_rank, "#00FF66")
        
        badge_y1 = q3_top + 10
        badge_y2 = q3_top + 32
        self.canvas.create_rectangle(q3_cx - 95, badge_y1, q3_cx - 65, badge_y2, fill=badge_color, outline="")
        self.canvas.create_text(q3_cx - 80, (badge_y1 + badge_y2) // 2, text=shot_rank, fill="#101114", font=("Helvetica", 11, "bold"))
        self.canvas.create_text(q3_cx - 50, (badge_y1 + badge_y2) // 2, text=shot_name.upper(), fill=badge_color, font=("Helvetica", 13, "bold"), anchor="w")

        ball_r = 22
        self.canvas.create_oval(q3_cx - ball_r, q3_cy - ball_r, q3_cx + ball_r, q3_cy + ball_r, fill="#FFFFFF", outline="#D0D5DD", width=2)
        
        axis_rad = math.radians(spin_axis)
        ax1, ay1 = self.rotate_point(q3_cx, q3_cy + 32, q3_cx, q3_cy, axis_rad)
        ax2, ay2 = self.rotate_point(q3_cx, q3_cy - 32, q3_cx, q3_cy, axis_rad)
        self.canvas.create_line(ax1, ay1, ax2, ay2, fill="#FF4081", width=4, arrow=tk.LAST, arrowshape=(12, 16, 5))

        spin_line1 = f"Spin Axis: {abs(spin_axis):.1f}° {'R' if spin_axis > 0 else 'L'}   |   Sidespin: {int(sidespin)} rpm"
        spin_line2 = f"Total Spin: {int(total_spin)} rpm   |   Opt. Potential: {opt_max:.1f} YDS"

        self.canvas.create_text(q3_cx, q3_bot - 34, text=spin_line1, fill="#00E5FF", font=("Consolas", 10, "bold"))
        self.canvas.create_text(q3_cx, q3_bot - 16, text=spin_line2, fill="#8E94A5", font=("Consolas", 9))

        # Quadrant 4 (Bottom-Right): High-Precision Face Impact Location & Strike Coordinates
        q4_cx, q4_cy = offset_x + (3 * avail_w // 4), mid_y + (avail_h // 4)
        q4_top = mid_y
        q4_bot = h - 10

        # Direct telemetry extraction or physics gear-effect computation
        shot_obj = self.current_shot or {}
        ogc = shot_obj.get("open_golf_coach", {}) if isinstance(shot_obj, dict) else {}
        impact_data = (
            shot_obj.get("face_impact") or
            shot_obj.get("impact_location") or
            ogc.get("face_impact") or
            ogc.get("impact_location") or
            ogc.get("face_contact") or {}
        )

        if "lateral_offset_mm" in impact_data:
            h_impact_mm = float(impact_data["lateral_offset_mm"])
        elif "heel_toe_mm" in impact_data:
            h_impact_mm = float(impact_data["heel_toe_mm"])
        elif "horizontal_offset_mm" in impact_data:
            h_impact_mm = float(impact_data["horizontal_offset_mm"])
        elif "x_mm" in impact_data:
            h_impact_mm = float(impact_data["x_mm"])
        else:
            # Positive = Heel strike, Negative = Toe strike
            h_impact_mm = (face_to_path * 0.75) + (sidespin / 400.0)

        if "vertical_offset_mm" in impact_data:
            v_impact_mm = float(impact_data["vertical_offset_mm"])
        elif "high_low_mm" in impact_data:
            v_impact_mm = float(impact_data["high_low_mm"])
        elif "y_mm" in impact_data:
            v_impact_mm = float(impact_data["y_mm"])
        else:
            club_baselines = {
                "Driver": 11.5, "3 Wood": 13.0, "5 Wood": 14.5, "3 Hybrid": 16.0,
                "4 Iron": 16.5, "5 Iron": 17.5, "6 Iron": 19.0, "7 Iron": 21.0,
                "8 Iron": 23.5, "9 Iron": 26.5, "PW": 29.0, "GW": 32.0,
                "SW": 35.0, "LW": 38.0
            }
            base_launch = club_baselines.get(self.current_club, 21.0)
            v_impact_mm = (vert_launch - base_launch) * 0.85

        # Clamp offsets to physical face dimensions
        h_impact_mm = max(-24.0, min(24.0, h_impact_mm))
        v_impact_mm = max(-16.0, min(16.0, v_impact_mm))
        total_offset_mm = math.sqrt(h_impact_mm**2 + v_impact_mm**2)

        # Coordinate Tags & Strike Tier Styling
        if abs(h_impact_mm) < 1.0:
            h_text = "↔ 0.0 mm CENTER"
            h_badge_col = "#00FF66"
        elif h_impact_mm > 0:
            h_text = f"↔ {abs(h_impact_mm):.1f} mm HEEL"
            h_badge_col = "#FF1744" if abs(h_impact_mm) > 8.0 else ("#FFEA00" if abs(h_impact_mm) > 3.0 else "#00E5FF")
        else:
            h_text = f"↔ {abs(h_impact_mm):.1f} mm TOE"
            h_badge_col = "#FF1744" if abs(h_impact_mm) > 8.0 else ("#FFEA00" if abs(h_impact_mm) > 3.0 else "#00E5FF")

        if abs(v_impact_mm) < 1.0:
            v_text = "↕ 0.0 mm FLUSH"
            v_badge_col = "#00FF66"
        elif v_impact_mm > 0:
            v_text = f"↕ {abs(v_impact_mm):.1f} mm HIGH"
            v_badge_col = "#FF1744" if abs(v_impact_mm) > 6.0 else ("#FFEA00" if abs(v_impact_mm) > 2.5 else "#00E5FF")
        else:
            v_text = f"↕ {abs(v_impact_mm):.1f} mm LOW"
            v_badge_col = "#FF1744" if abs(v_impact_mm) > 6.0 else ("#FFEA00" if abs(v_impact_mm) > 2.5 else "#00E5FF")

        if total_offset_mm < 3.0:
            strike_rank = "CENTER FLUSH"
            strike_color = "#00FF66"
        elif total_offset_mm < 8.0:
            h_part = "HEEL" if h_impact_mm > 1.5 else ("TOE" if h_impact_mm < -1.5 else "")
            v_part = "HIGH" if v_impact_mm > 1.5 else ("THIN" if v_impact_mm < -1.5 else "")
            strike_rank = f"{h_part} {v_part}".strip() or "OFF-CENTER"
            strike_color = "#FFEA00"
        else:
            h_part = "EXTREME HEEL" if h_impact_mm > 0 else "EXTREME TOE"
            v_part = "HIGH" if v_impact_mm > 2.5 else ("THIN" if v_impact_mm < -2.5 else "")
            strike_rank = f"{h_part} {v_part}".strip()
            strike_color = "#FF1744"

        # Top Pill Badges (Exact Strike Coordinates)
        badge_y = q4_top + 20
        badge_w = 135
        # Lateral Pill
        self.canvas.create_rectangle(q4_cx - badge_w - 6, badge_y - 11, q4_cx - 6, badge_y + 11, fill="#121622", outline=h_badge_col, width=1)
        self.canvas.create_text(q4_cx - (badge_w // 2) - 6, badge_y, text=h_text, fill=h_badge_col, font=("Consolas", 8, "bold"))
        # Vertical Pill
        self.canvas.create_rectangle(q4_cx + 6, badge_y - 11, q4_cx + badge_w + 6, badge_y + 11, fill="#121622", outline=v_badge_col, width=1)
        self.canvas.create_text(q4_cx + (badge_w // 2) + 6, badge_y, text=v_text, fill=v_badge_col, font=("Consolas", 8, "bold"))

        # Clubface Graphic
        if self.face_img:
            self.img_cache["q4_face"] = ImageTk.PhotoImage(self.face_img)
            self.canvas.create_image(q4_cx, q4_cy, image=self.img_cache["q4_face"], anchor="c")

        # Sweet Spot Origin (0,0) on Scorelines
        center_x = q4_cx - 20
        center_y = q4_cy - 5
        self.canvas.create_line(center_x - 14, center_y, center_x + 14, center_y, fill="#3A445C", width=1, dash=(2, 2))
        self.canvas.create_line(center_x, center_y - 14, center_x, center_y + 14, fill="#3A445C", width=1, dash=(2, 2))
        self.canvas.create_oval(center_x - 2, center_y - 2, center_x + 2, center_y + 2, fill="#00E5FF", outline="")

        # Impact Contact Location
        scale_px = 1.75
        impact_x = center_x + int(h_impact_mm * scale_px)
        impact_y = center_y - int(v_impact_mm * scale_px)

        # Vector Line from Sweet Spot to Impact
        if total_offset_mm >= 2.0:
            self.canvas.create_line(center_x, center_y, impact_x, impact_y, fill=strike_color, width=1, dash=(3, 2))

        # Precision Strike Reticle
        self.canvas.create_oval(impact_x - 12, impact_y - 12, impact_x + 12, impact_y + 12, fill="", outline=strike_color, width=2)
        self.canvas.create_oval(impact_x - 6, impact_y - 6, impact_x + 6, impact_y + 6, fill="", outline=strike_color, width=1)
        self.canvas.create_oval(impact_x - 3, impact_y - 3, impact_x + 3, impact_y + 3, fill=strike_color, outline="")

        # Footer Metrics
        self.canvas.create_text(q4_cx, q4_bot - 24, text=f"🎯 STRIKE: {strike_rank}  ({total_offset_mm:.1f} mm Offset)", fill=strike_color, font=("Helvetica", 9, "bold"))
        self.canvas.create_text(q4_cx, q4_bot - 8, text=f"Distance Efficiency: {eff_pct:.0f}%", fill="#00E5FF", font=("Consolas", 8, "bold"))

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

        self.canvas.create_polygon(rotated_pts, fill="#1B3B1B", outline="#00FF66", width=3)
        self.canvas.create_polygon(rotated_pts, fill="#4A2E13", outline="", stipple="gray50")

        path_len = 190
        px1, py1 = self.rotate_point(cx, cy + path_len // 2, cx, cy, angle_rad)
        px2, py2 = self.rotate_point(cx, cy - path_len // 2, cx, cy, angle_rad)
        self.canvas.create_line(px1, py1, px2, py2, fill="#00E5FF", width=3, arrow=tk.LAST, arrowshape=(12, 15, 5))

        self.canvas.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline="#FF1744", width=2)
        self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#FF1744", outline="")
        self.canvas.create_text(cx, cy + 22, text="🎯 PHYSICAL BALL ORIGIN", fill="#FF1744", font=("Helvetica", 8, "bold"))
        self.canvas.create_text(cx, 55, text=f"DIVOT PROJECTOR  •  {shot_name.upper()}", fill="#00FF66", font=("Helvetica", 14, "bold"))

    def draw_my_bag_viewport(self, avail_w, h, offset_x=0):
        # 1. Background
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill="#0E1017", outline="")

        self.bag_club_card_rects.clear()
        self.bag_edit_btn_rects.clear()
        self.bag_move_up_rects.clear()
        self.bag_move_down_rects.clear()

        # 2. Top Toolbar (y: 52 to 98)
        bar_y1, bar_y2 = 52, 98
        self.canvas.create_rectangle(offset_x, bar_y1, offset_x + avail_w, bar_y2, fill="#131622", outline="#212636")

        total_shots = sum(len(s.get("shots", [])) for s in self.sessions)
        sess_shots = len(self.session_shots)
        display_shots = sess_shots if self.bag_scope == "session" else total_shots
        scope_str = "Current Session" if self.bag_scope == "session" else "All-Time History"

        self.canvas.create_text(offset_x + 18, 66, text="MY BAG MAPPING & GAPPING MATRIX", fill="#00E5FF", font=("Helvetica", 11, "bold"), anchor="w")
        self.canvas.create_text(offset_x + 18, 84, text=f"{len(self.bag)} Clubs in Bag  •  {display_shots} Shots ({scope_str})", fill="#8E94A5", font=("Helvetica", 8), anchor="w")

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
        self.canvas.create_rectangle(p1_x1, py1, p1_x2, py2, fill="#0D2A1C" if is_sess else "#1A1E2B", outline="#00FF66" if is_sess else "#2D3446")
        self.canvas.create_text((p1_x1 + p1_x2) // 2, (py1 + py2) // 2, text="Current Session", fill="#00FF66" if is_sess else "#8E94A5", font=("Helvetica", 8, "bold" if is_sess else "normal"), anchor="center")

        is_all = (self.bag_scope == "all_time")
        self.canvas.create_rectangle(p2_x1, py1, p2_x2, py2, fill="#0D2A1C" if is_all else "#1A1E2B", outline="#00FF66" if is_all else "#2D3446")
        self.canvas.create_text((p2_x1 + p2_x2) // 2, (py1 + py2) // 2, text="All-Time History", fill="#00FF66" if is_all else "#8E94A5", font=("Helvetica", 8, "bold" if is_all else "normal"), anchor="center")

        # Add Club to Bag Button (Far Right)
        add_x1 = offset_x + avail_w - 146
        add_x2 = offset_x + avail_w - 16
        self.bag_add_club_btn_rect = (add_x1, py1, add_x2, py2)
        self.canvas.create_rectangle(add_x1, py1, add_x2, py2, fill="#00FF66", outline="")
        self.canvas.create_text((add_x1 + add_x2) // 2, (py1 + py2) // 2, text="+ Add Club to Bag", fill="#08090C", font=("Helvetica", 8, "bold"), anchor="center")

        # 3. Dual-Pane Dimensions
        content_y = 104
        content_h = h - content_y - 12
        left_w = int(avail_w * 0.54)
        right_w = avail_w - left_w - 18
        right_x = offset_x + left_w + 12

        self._draw_bag_rack_pane(offset_x + 6, content_y, left_w, content_h)
        self._draw_bag_gapping_ladder_pane(right_x, content_y, right_w, content_h)

    def _draw_bag_rack_pane(self, x1, y1, w, h):
        self.canvas.create_rectangle(x1, y1, x1 + w, y1 + h, fill="#12141D", outline="#212636")
        self.canvas.create_text(x1 + 16, y1 + 16, text="BAG EQUIPMENT & SHOT AVERAGES", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")
        self.canvas.create_text(x1 + w - 16, y1 + 16, text="Click card to Select  •  Edit Specs for Details", fill="#6A7285", font=("Helvetica", 8), anchor="e")

        card_area_y1 = y1 + 30
        curr_y = card_area_y1 - self.bag_scroll_offset

        for cat in BAG_CATEGORIES:
            cat_clubs = [c for c in self.bag if c.get("category") == cat]
            if not cat_clubs:
                continue

            # Category Header Bar
            if y1 + 24 <= curr_y <= y1 + h - 10:
                self.canvas.create_rectangle(x1 + 8, curr_y, x1 + w - 8, curr_y + 18, fill="#171A24", outline="#222736")
                self.canvas.create_text(x1 + 16, curr_y + 9, text=f"{cat} ({len(cat_clubs)})", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")
            curr_y += 22

            for c in cat_clubs:
                c_name = c.get("name", "")
                card_h = 62
                cy1 = curr_y
                cy2 = cy1 + card_h

                if y1 + 20 <= cy1 <= y1 + h or y1 + 20 <= cy2 <= y1 + h:
                    cx1 = x1 + 8
                    cx2 = x1 + w - 8
                    self.bag_club_card_rects.append((cx1, cy1, cx2, cy2, c_name))

                    is_active = (self.current_club == c_name)
                    bg_col = "#1E2419" if is_active else "#151822"
                    border_col = "#FFEA00" if is_active else "#262C3C"
                    c_color = self.get_club_color(c_name)

                    self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill=bg_col, outline=border_col, width=1.5 if is_active else 1)
                    self.canvas.create_rectangle(cx1, cy1, cx1 + 4, cy2, fill=c_color, outline="")

                    # Line 1: Name, Loft, Active badge, Specs
                    name_x = cx1 + 12
                    self.canvas.create_text(name_x, cy1 + 12, text=c_name, fill="#FFFFFF", font=("Helvetica", 10, "bold"), anchor="w")
                    
                    loft = c.get("loft_deg", 0.0)
                    loft_str = f"{loft:.1f}°" if loft else ""
                    if loft_str:
                        self.canvas.create_text(name_x + 95, cy1 + 12, text=loft_str, fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

                    specs_parts = [p for p in [c.get("brand", ""), c.get("model", ""), c.get("shaft", "")] if p]
                    specs_str = " • ".join(specs_parts)
                    if len(specs_str) > 26:
                        specs_str = specs_str[:24] + "..."
                    self.canvas.create_text(name_x + 135, cy1 + 12, text=specs_str, fill="#8E94A5", font=("Helvetica", 8), anchor="w")

                    if is_active:
                        badge_x2 = cx2 - 130
                        badge_x1 = badge_x2 - 54
                        self.canvas.create_rectangle(badge_x1, cy1 + 4, badge_x2, cy1 + 19, fill="#2E3310", outline="#FFEA00")
                        self.canvas.create_text((badge_x1 + badge_x2) // 2, cy1 + 11, text="ACTIVE", fill="#FFEA00", font=("Helvetica", 7, "bold"))

                    # Action buttons: Edit Specs, Move Up, Move Down
                    btn_ey1 = cy1 + 6
                    btn_ey2 = btn_ey1 + 20
                    edit_x1 = cx2 - 120
                    edit_x2 = cx2 - 54
                    self.bag_edit_btn_rects.append((edit_x1, btn_ey1, edit_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(edit_x1, btn_ey1, edit_x2, btn_ey2, fill="#1C2130", outline="#2E374D")
                    self.canvas.create_text((edit_x1 + edit_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="Edit Specs", fill="#00E5FF", font=("Helvetica", 7, "bold"))

                    up_x1 = cx2 - 48
                    up_x2 = cx2 - 28
                    self.bag_move_up_rects.append((up_x1, btn_ey1, up_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(up_x1, btn_ey1, up_x2, btn_ey2, fill="#181B26", outline="#2E374D")
                    self.canvas.create_text((up_x1 + up_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="▲", fill="#8E94A5", font=("Helvetica", 8))

                    dn_x1 = cx2 - 24
                    dn_x2 = cx2 - 4
                    self.bag_move_down_rects.append((dn_x1, btn_ey1, dn_x2, btn_ey2, c_name))
                    self.canvas.create_rectangle(dn_x1, btn_ey1, dn_x2, btn_ey2, fill="#181B26", outline="#2E374D")
                    self.canvas.create_text((dn_x1 + dn_x2) // 2, (btn_ey1 + btn_ey2) // 2, text="▼", fill="#8E94A5", font=("Helvetica", 8))

                    # Line 2 & 3: Performance stats
                    stats = self.get_bag_club_stats(c_name, scope=self.bag_scope)
                    if stats["shot_count"] > 0:
                        carry_str = f"Carry: {stats['avg_carry']:.1f}y (±{stats['std_carry']:.1f}y)"
                        tot_str = f"Total: {stats['avg_total']:.1f}y"
                        cnt_str = f"{stats['shot_count']} shots"
                        self.canvas.create_text(name_x, cy1 + 31, text=f"{carry_str}   |   {tot_str}   |   {cnt_str}", fill="#00FF66", font=("Consolas", 8, "bold"), anchor="w")

                        sub_stats = f"Ball: {stats['avg_ball_speed']:.1f}mph  •  Smash: {stats['avg_smash']:.2f}  •  Launch: {stats['avg_launch']:.1f}°  •  Spin: {stats['avg_spin']:.0f}rpm"
                        self.canvas.create_text(name_x, cy1 + 48, text=sub_stats, fill="#8E94A5", font=("Consolas", 8), anchor="w")
                    else:
                        self.canvas.create_text(name_x, cy1 + 38, text="No shots recorded for this club in selected scope", fill="#464E62", font=("Helvetica", 8, "italic"), anchor="w")

                curr_y += card_h + 5

    def _draw_bag_gapping_ladder_pane(self, x1, y1, w, h):
        self.canvas.create_rectangle(x1, y1, x1 + w, y1 + h, fill="#12141D", outline="#212636")
        self.canvas.create_text(x1 + 16, y1 + 16, text="DISTANCE GAPPING LADDER", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")

        gapping = self.calculate_bag_gapping(scope=self.bag_scope)
        grade_text = f"Consistency: {gapping['consistency_grade']}  •  Mean Gap: {gapping['mean_gap']:.1f} yds"
        self.canvas.create_text(x1 + w - 16, y1 + 16, text=grade_text, fill=gapping['consistency_color'], font=("Helvetica", 8, "bold"), anchor="e")

        ladder_top = y1 + 44
        ladder_bot = y1 + h - 26
        ladder_h = ladder_bot - ladder_top
        min_yds = 0.0
        max_yds = 320.0

        grid_steps = [50, 100, 150, 200, 250, 300]
        for yds in grid_steps:
            gy = ladder_bot - int(((yds - min_yds) / (max_yds - min_yds)) * ladder_h)
            self.canvas.create_line(x1 + 65, gy, x1 + w - 20, gy, fill="#1C2130", dash=(2, 4))
            self.canvas.create_text(x1 + 45, gy, text=f"{yds}y", fill="#5A6275", font=("Consolas", 8), anchor="e")

        clubs_with_shots = gapping["clubs"]
        if not clubs_with_shots:
            self.canvas.create_text(x1 + w // 2, y1 + h // 2, text="No shot data recorded for current scope.\nHit shots or switch to All-Time History to view your visual gapping ladder.", fill="#464E62", font=("Helvetica", 10), justify="center")
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
            self.canvas.create_text(x1 + 95, cy, text=c["name"], fill=c["color"], font=("Helvetica", 8, "bold"), anchor="e")

            # Min-Max Whisker
            min_c = c.get("min_carry", carry)
            max_c = c.get("max_carry", carry)
            wx1 = bar_x1 + int((min_c / max_yds) * bar_avail_w)
            wx2 = bar_x1 + int((max_c / max_yds) * bar_avail_w)
            wx1 = max(bar_x1, min(bar_x2, wx1))
            wx2 = max(bar_x1, min(bar_x2, wx2))
            self.canvas.create_line(wx1, cy, wx2, cy, fill="#3A4358", width=3)
            self.canvas.create_line(wx1, cy - 4, wx1, cy + 4, fill="#3A4358", width=1.5)
            self.canvas.create_line(wx2, cy - 4, wx2, cy + 4, fill="#3A4358", width=1.5)

            # Center Dot / Mean marker
            cx_pos = bar_x1 + int((carry / max_yds) * bar_avail_w)
            cx_pos = max(bar_x1, min(bar_x2, cx_pos))
            self.canvas.create_oval(cx_pos - 4, cy - 4, cx_pos + 4, cy + 4, fill=c["color"], outline="#FFFFFF", width=1)

            # Yardage readout on right
            self.canvas.create_text(bar_x2 + 10, cy, text=f"{carry:.1f} yds", fill="#FFFFFF", font=("Consolas", 8, "bold"), anchor="w")

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
                self.canvas.create_rectangle(bx + 4, mid_y - badge_h // 2, bx + 4 + badge_w, mid_y + badge_h // 2, fill="#0F141F", outline=step["color"])
                self.canvas.create_text(bx + 4 + badge_w // 2, mid_y, text=step["status_text"], fill=step["color"], font=("Consolas", 7, "bold"), anchor="center")

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
            ogc = s.get("open_golf_coach", {})
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
                fp = ogc.get("club_face_to_path_degrees", {}).get("right_handed", 0.0)
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
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill="#0E1017", outline="")

        self.fitting_submode_rects.clear()
        self.fitting_club_chip_rects.clear()
        self.fitting_baseline_chip_rects.clear()
        self.fitting_dot_rects.clear()

        top_y = 58
        bot_y = h - 14

        # 2. Unified Top Fitting Toolbar (y: 58 to 100)
        bar_y1, bar_y2 = top_y, top_y + 42
        self.canvas.create_rectangle(offset_x + 10, bar_y1, offset_x + avail_w - 10, bar_y2, fill="#121520", outline="#22283A")

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
            self.canvas.create_rectangle(sm_rect[0], sm_rect[1], sm_rect[2], sm_rect[3], fill="#0E2838" if is_active else "#181B26", outline="#00E5FF" if is_active else "#282E40")
            self.canvas.create_text((sm_rect[0] + sm_rect[2]) // 2, (sm_rect[1] + sm_rect[3]) // 2, text=sm_label, fill="#00E5FF" if is_active else "#8E94A5", font=("Helvetica", 8, "bold" if is_active else "normal"))
            sub_x += sm_w + 6

        # Vertical separator between view modes and club chips
        sep_x = sub_x + 8
        self.canvas.create_line(sep_x, bar_y1 + 6, sep_x, bar_y2 - 6, fill="#252B3B", width=1)

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

            bg = "#0E2838" if is_active else "#181B26"
            border = c_color if is_active else "#282E40"
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill=bg, outline=border, width=2 if is_active else 1)

            # Color dot
            mid_y_chip = (cy1 + cy2) // 2
            self.canvas.create_oval(cx1 + 8, mid_y_chip - 4, cx1 + 16, mid_y_chip + 4, fill=c_color, outline="")
            self.canvas.create_text(cx1 + 22, mid_y_chip, text=chip_text, fill="#FFFFFF" if is_active else "#8E94A5", font=("Helvetica", 8, "bold" if is_active else "normal"), anchor="w")

            # Dedicated non-overlapping Baseline pill
            if is_baseline:
                bx1 = cx2 - 42
                bx2 = cx2 - 6
                by1 = cy1 + 3
                by2 = cy2 - 3
                self.fitting_baseline_chip_rects.append((bx1, by1, bx2, by2, c_name))
                self.canvas.create_rectangle(bx1, by1, bx2, by2, fill="#0D2618", outline="#00FF66", width=1)
                self.canvas.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text="BASE", fill="#00FF66", font=("Helvetica", 7, "bold"), anchor="center")

            chip_x += chip_w + 8

        # D. + New Club button (Far right of top toolbar)
        add_w = 92
        add_x2 = offset_x + avail_w - 24
        add_x1 = add_x2 - add_w
        self.fitting_add_club_rect = (add_x1, bar_y1 + 7, add_x2, bar_y2 - 7)
        self.canvas.create_rectangle(add_x1, bar_y1 + 7, add_x2, bar_y2 - 7, fill="#0D261A", outline="#00FF66", width=1)
        self.canvas.create_text((add_x1 + add_x2) // 2, (bar_y1 + bar_y2) // 2, text="+ New Club", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="center")

        # 3. Dual-Pane Dimensions & Splitter
        content_top = bar_y2 + 8
        content_h = bot_y - content_top
        plot_w = int(avail_w * self.fitting_splitter_ratio)
        plot_w = max(260, min(avail_w - 240, plot_w))

        split_x1 = offset_x + plot_w + 3
        split_x2 = split_x1 + 8
        self.fitting_splitter_rect = (split_x1 - 4, content_top, split_x2 + 4, bot_y)

        gap_x1 = split_x2 + 6
        gap_w = (offset_x + avail_w) - gap_x1 - 12

        # Calculate fitting stats for all competitor clubs
        stats_by_club = {}
        grouped_shots = {}
        for c_name in session_clubs:
            st = self._calculate_club_fitting_stats(c_name)
            if st and st["count"] > 0:
                stats_by_club[c_name] = st
            c_items = [(idx, s) for idx, s in enumerate(self.session_shots) if s.get("club") == c_name and not s.get("excluded", False)]
            if c_items:
                grouped_shots[c_name] = c_items

        chart_top = content_top
        chart_h = bot_y - chart_top
        plot_x1 = offset_x + 10
        plot_x2 = offset_x + plot_w
        max_x_yds = 350.0
        max_h_yds = 60.0

        # Draw Left Pane Overlaid Charts
        self._draw_fitting_overlaid_charts(plot_x1, chart_top, plot_x2, bot_y, max_x_yds, max_h_yds, stats_by_club, grouped_shots)

        # Draw Splitter Handle
        is_dragging = self.fitting_splitter_dragging
        self.canvas.create_rectangle(split_x1, content_top, split_x2, bot_y, fill="#00E5FF" if is_dragging else "#161924", outline="#00E5FF" if is_dragging else "#252B3B")
        mid_y = (content_top + bot_y) // 2
        for dy in [-16, -8, 0, 8, 16]:
            self.canvas.create_line(split_x1 + 2, mid_y + dy, split_x2 - 2, mid_y + dy, fill="#FFFFFF" if is_dragging else "#50586D", width=1)

        # Draw Right Pane Head-to-Head Delta Matrix & Best Fit Summary
        self._draw_fitting_h2h_matrix(gap_x1, content_top, gap_w, bot_y, stats_by_club, session_clubs)

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
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill="#12141D", outline="#232736")
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="OVERLAID DISPERSION & CONFIDENCE ELLIPSES", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        plot_w = plot_x2 - plot_x1
        cx = (plot_x1 + plot_x2) // 2
        tee_y = plot_y2 - 16
        plot_h = tee_y - plot_y1 - 26
        max_lat_yds = 45.0

        # Centerline & Lateral guides
        self.canvas.create_line(cx, tee_y, cx, plot_y1 + 22, fill="#2B3142", width=2, dash=(6, 4))
        for lat in [-30, -15, 15, 30]:
            lx = cx + int((lat / max_lat_yds) * (plot_w * 0.45))
            self.canvas.create_line(lx, tee_y, lx, plot_y1 + 24, fill="#1C202C", width=1, dash=(2, 4))
            self.canvas.create_text(lx, plot_y2 - 6, text=f"{abs(lat)}y{'L' if lat < 0 else 'R'}", fill="#5A6175", font=("Consolas", 7))

        # Concentric distance arcs
        for yds in [50, 100, 150, 200, 250, 300, 350]:
            frac = yds / max_range_yds
            arc_y = tee_y - int(frac * plot_h)
            self.canvas.create_line(plot_x1 + 10, arc_y, plot_x2 - 10, arc_y, fill="#1E2332", width=1, dash=(3, 3))
            self.canvas.create_text(plot_x1 + 20, arc_y, text=f"{yds}y", fill="#6B7285", font=("Consolas", 7))

        if not stats_by_club:
            self.canvas.create_text(cx, (plot_y1 + plot_y2) // 2, text="No shots recorded yet for fitting clubs", fill="#464E62", font=("Helvetica", 9))
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
            self.canvas.create_line(cen_x - 6, cen_y, cen_x + 6, cen_y, fill="#FFFFFF", width=2)
            self.canvas.create_line(cen_x, cen_y - 6, cen_x, cen_y + 6, fill="#FFFFFF", width=2)
            # Label badge
            self.canvas.create_text(cen_x, cen_y - ry1 - 8, text=f"{c_name}: {mu_c:.1f}y (±{std_c:.1f}y)", fill=c_color, font=("Helvetica", 7, "bold"))

        # Render Dots for each shot
        for c_name, items in grouped_shots.items():
            c_color = self.get_club_color(c_name)
            for real_idx, s in items:
                ogc = s.get("open_golf_coach", {})
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
                self.canvas.create_oval(dx - r, dy - r, dx + r, dy + r, fill="#FFEA00" if is_sel else c_color, outline="#FFFFFF" if is_sel else "")

    def _draw_fitting_side_chart(self, plot_x1, plot_y1, plot_x2, plot_y2, margin_x, chart_w, max_x_yds, max_h_yds, stats_by_club, grouped_shots):
        self.canvas.create_rectangle(plot_x1, plot_y1, plot_x2, plot_y2, fill="#12141D", outline="#232736")
        self.canvas.create_text(plot_x1 + 14, plot_y1 + 14, text="TRAJECTORY PROFILES & APEX HEIGHT COMPARISON", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        base_y = plot_y2 - 22
        chart_h = max(30, base_y - plot_y1 - 32)

        # X distance ticks
        for t in [0, 50, 100, 150, 200, 250, 300, 350]:
            tx = margin_x + int((t / max_x_yds) * chart_w)
            self.canvas.create_line(tx, plot_y1 + 24, tx, base_y, fill="#1D202C", width=1, dash=(2, 2))
            self.canvas.create_text(tx, base_y + 10, text=str(t), fill="#5A6174", font=("Consolas", 7))

        # Y height grid lines
        for hy in [0, 20, 40, 60]:
            ty = base_y - int((hy / max_h_yds) * chart_h)
            self.canvas.create_line(margin_x, ty, margin_x + chart_w, ty, fill="#1D202C", width=1, dash=(2, 2))
            self.canvas.create_text(margin_x - 14, ty, text=f"{hy}y", fill="#5A6174", font=("Consolas", 7))

        # Ground baseline
        self.canvas.create_line(margin_x, base_y, margin_x + chart_w, base_y, fill="#00FF66", width=1)

        if not stats_by_club:
            self.canvas.create_text(margin_x + chart_w // 2, (plot_y1 + plot_y2) // 2, text="No trajectory data recorded yet", fill="#464E62", font=("Helvetica", 9))
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
            self.canvas.create_oval(apex_x_px - 3, apex_y_px - 3, apex_x_px + 3, apex_y_px + 3, fill=c_color, outline="#FFFFFF")
            self.canvas.create_text(apex_x_px, apex_y_px - 8, text=f"{c_name}: {st['avg_apex_ft']:.0f}ft", fill=c_color, font=("Helvetica", 7, "bold"))

            # Carry Landing Flag marker
            land_x = margin_x + int((avg_c / max_x_yds) * chart_w)
            self.canvas.create_oval(land_x - 4, base_y - 4, land_x + 4, base_y + 4, fill=c_color, outline="#FFFFFF")

    def _draw_fitting_h2h_matrix(self, gap_x1, top_y, gap_w, bot_y, stats_by_club, session_clubs):
        self.canvas.create_rectangle(gap_x1, top_y, gap_x1 + gap_w, bot_y, fill="#12141D", outline="#232736")
        self.canvas.create_text(gap_x1 + 14, top_y + 16, text="HEAD-TO-HEAD STAT MATRIX & DELTAS", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")

        baseline_name = self.fitting_baseline_club or (session_clubs[0] if session_clubs else None)
        base_st = stats_by_club.get(baseline_name)

        if not stats_by_club or len(stats_by_club) == 0:
            self.canvas.create_text(gap_x1 + gap_w // 2, top_y + 160, text="No competitor clubs recorded.\nHit shots or select clubs from the top bar to compare.", fill="#464E62", font=("Helvetica", 10), justify="center")
            return

        # Baseline indicator strip
        base_text = f"Baseline Club: {baseline_name}" if baseline_name else "Baseline"
        self.canvas.create_text(gap_x1 + gap_w - 14, top_y + 16, text=base_text, fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="e")

        clubs_to_render = [c for c in session_clubs if c in stats_by_club]
        if not clubs_to_render:
            return

        # Side-by-side club columns
        num_clubs = min(3, len(clubs_to_render))
        card_w = (gap_w - 20 - (num_clubs - 1) * 10) // num_clubs
        card_start_y = top_y + 34
        card_h = max(240, bot_y - card_start_y - 85)

        for col_i, c_name in enumerate(clubs_to_render[:num_clubs]):
            st = stats_by_club[c_name]
            cx1 = gap_x1 + 10 + col_i * (card_w + 10)
            cx2 = cx1 + card_w
            cy1 = card_start_y
            cy2 = cy1 + card_h
            c_color = st["color"]
            is_base = (c_name == baseline_name)

            # Club Card Container
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill="#161924", outline=c_color if is_base else "#252B3B", width=2 if is_base else 1)
            # Top Club Name Banner
            self.canvas.create_rectangle(cx1, cy1, cx2, cy1 + 24, fill="#1C2030", outline="")
            self.canvas.create_rectangle(cx1, cy1, cx1 + 5, cy1 + 24, fill=c_color, outline="")
            self.canvas.create_text(cx1 + 12, cy1 + 12, text=c_name, fill="#FFFFFF", font=("Helvetica", 8, "bold"), anchor="w")
            self.canvas.create_text(cx2 - 8, cy1 + 12, text=f"{st['count']} shots", fill="#8E94A5", font=("Consolas", 7), anchor="e")

            # Metrics with Deltas vs Baseline
            metrics = [
                ("Carry", f"{st['avg_carry']:.1f} yds", st['avg_carry'] - (base_st['avg_carry'] if base_st else st['avg_carry']), "yds", True),
                ("Total", f"{st['avg_total']:.1f} yds", st['avg_total'] - (base_st['avg_total'] if base_st else st['avg_total']), "yds", True),
                ("Ball Speed", f"{st['avg_ball_speed']:.1f} mph", st['avg_ball_speed'] - (base_st['avg_ball_speed'] if base_st else st['avg_ball_speed']), "mph", True),
                ("Smash", f"{st['avg_smash']:.2f}", st['avg_smash'] - (base_st['avg_smash'] if base_st else st['avg_smash']), "", True),
                ("Launch", f"{st['avg_launch']:.1f}°", st['avg_launch'] - (base_st['avg_launch'] if base_st else st['avg_launch']), "°", None),
                ("Total Spin", f"{int(st['avg_spin'])} rpm", st['avg_spin'] - (base_st['avg_spin'] if base_st else st['avg_spin']), "rpm", None),
                ("Apex", f"{st['avg_apex_ft']:.0f} ft", st['avg_apex_ft'] - (base_st['avg_apex_ft'] if base_st else st['avg_apex_ft']), "ft", None),
                ("Closure Rate", f"{int(st['avg_closure_rate'])} °/s", st['avg_closure_rate'] - (base_st['avg_closure_rate'] if base_st else st['avg_closure_rate']), "°/s", None),
                ("Dispersion (σ)", f"±{st['std_offline']:.1f}y", st['std_offline'] - (base_st['std_offline'] if base_st else st['std_offline']), "y", False),
                ("Ellipse Area", f"{int(st['ellipse_area'])} yd²", st['ellipse_area'] - (base_st['ellipse_area'] if base_st else st['ellipse_area']), "yd²", False),
            ]

            row_y = cy1 + 32
            row_h = (card_h - 40) // len(metrics)
            for m_label, m_val, delta, unit, higher_is_better in metrics:
                self.canvas.create_text(cx1 + 10, row_y + 4, text=m_label, fill="#7E8799", font=("Helvetica", 7), anchor="w")
                
                # Primary Val
                self.canvas.create_text(cx1 + card_w // 2 + 4, row_y + 4, text=m_val, fill="#FFFFFF", font=("Consolas", 7, "bold"), anchor="w")

                # Delta vs baseline (if not baseline itself)
                if not is_base and base_st:
                    if abs(delta) > 0.05:
                        if higher_is_better is True:
                            d_col = "#00FF66" if delta > 0 else "#FF4081"
                        elif higher_is_better is False:
                            d_col = "#00FF66" if delta < 0 else "#FF4081" # Lower dispersion is better
                        else:
                            d_col = "#00E5FF"
                        d_str = f"{delta:+.1f}{unit}" if isinstance(delta, float) else f"{int(delta):+d}{unit}"
                    else:
                        d_col = "#5A6175"
                        d_str = "0.0"
                    self.canvas.create_text(cx2 - 8, row_y + 4, text=d_str, fill=d_col, font=("Consolas", 7, "bold"), anchor="e")

                row_y += row_h

        # 5. Best Fit Summary Award Banner (Bottom of right pane)
        summary_y1 = bot_y - 72
        summary_y2 = bot_y - 8
        self.canvas.create_rectangle(gap_x1 + 10, summary_y1, gap_x1 + gap_w - 10, summary_y2, fill="#0E1624", outline="#00E5FF", width=1)
        self.canvas.create_text(gap_x1 + 20, summary_y1 + 14, text="FITTING WINNER & RECOMMENDATION", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")

        # Calculate winners
        best_carry_club = max(clubs_to_render, key=lambda c: stats_by_club[c]["avg_carry"])
        best_tight_club = min(clubs_to_render, key=lambda c: stats_by_club[c]["ellipse_area"])
        best_smash_club = max(clubs_to_render, key=lambda c: stats_by_club[c]["avg_smash"])

        w1 = f"Longest Carry: {best_carry_club} ({stats_by_club[best_carry_club]['avg_carry']:.1f} yds)"
        w2 = f"Tightest Dispersion: {best_tight_club} ({int(stats_by_club[best_tight_club]['ellipse_area'])} yd²)"
        w3 = f"Highest Efficiency: {best_smash_club} ({stats_by_club[best_smash_club]['avg_smash']:.2f} smash)"

        self.canvas.create_text(gap_x1 + 20, summary_y1 + 34, text=f"• {w1}", fill="#00FF66", font=("Helvetica", 8, "bold"), anchor="w")
        self.canvas.create_text(gap_x1 + 20, summary_y1 + 50, text=f"• {w2}   |   • {w3}", fill="#FFFFFF", font=("Helvetica", 8), anchor="w")


    def draw_swing_lab_viewport(self, avail_w, h, offset_x=0):
        # 1. Background
        self.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill="#0A0D14", outline="")

        top_y = 58
        bot_y = h - 14
        bar_y1, bar_y2 = top_y, top_y + 44
        bar_w = avail_w - 20
        bar_x1 = offset_x + 10
        bar_x2 = bar_x1 + bar_w

        # 2. Top Toolbar
        self.canvas.create_rectangle(bar_x1, bar_y1, bar_x2, bar_y2, fill="#121622", outline="#22283A")

        # Get latest pressure sample
        latest = None
        if hasattr(obs_server, "pressure_manager") and obs_server.pressure_manager:
            latest = obs_server.pressure_manager.latest_frame
        if not latest and self.current_shot and self.current_shot.get("pressure_trace"):
            trace = self.current_shot["pressure_trace"]
            if trace: latest = trace[-1]

        phase_str = latest.get("phase", "Address").upper() if latest else "READY"
        total_kg = latest.get("total_kg", 80.0) if latest else 80.0
        force_bw = latest.get("force_bw", 1.0) if latest else 1.0
        pct_l = latest.get("pct_left", 50.0) if latest else 50.0
        pct_r = latest.get("pct_right", 50.0) if latest else 50.0
        torque_nm = latest.get("torque_nm", 0.0) if latest else 0.0
        cop_x = latest.get("cop_x", 0.0) if latest else 0.0
        cop_y = latest.get("cop_y", 0.0) if latest else 0.0

        # 1. Phase Pill (Generous width for long phase strings like FOLLOW-THROUGH)
        p_col = "#00FF66" if phase_str in ("ADDRESS", "READY") else ("#FFB800" if "BACK" in phase_str else ("#FF3366" if "IMPACT" in phase_str else "#00E5FF"))
        p_pill_w = max(142, len(phase_str) * 8 + 36)
        pill_x1 = bar_x1 + 8
        pill_x2 = pill_x1 + p_pill_w
        self.canvas.create_rectangle(pill_x1, bar_y1 + 8, pill_x2, bar_y2 - 8, fill="#0D1F2D", outline=p_col)
        self.canvas.create_text((pill_x1 + pill_x2) // 2, (bar_y1 + bar_y2) // 2, text=f"● {phase_str}", fill=p_col, font=("Helvetica", 8, "bold"), anchor="center")

        # 2. Weight & Force Stats (Left-aligned, dedicated width)
        wt_x1 = pill_x2 + 14
        wt_w = 135
        wt_x2 = wt_x1 + wt_w
        self.canvas.create_text(wt_x1, (bar_y1 + bar_y2) // 2 - 6, text="TOTAL WEIGHT", fill="#6B7280", font=("Helvetica", 7, "bold"), anchor="w")
        self.canvas.create_text(wt_x1, (bar_y1 + bar_y2) // 2 + 7, text=f"{total_kg:.1f} kg ({force_bw:.2f} BW)", fill="#FFFFFF", font=("Consolas", 8, "bold"), anchor="w")

        # 3. L/R Balance Gauge (Strict left-to-right flow, no backwards anchor!)
        bg_x1 = wt_x2 + 14
        lbl_l_w = 38
        b_bar_x1 = bg_x1 + lbl_l_w
        b_bar_w = 60 if avail_w < 950 else 75
        b_bar_x2 = b_bar_x1 + b_bar_w
        b_bar_cy = (bar_y1 + bar_y2) // 2

        self.canvas.create_text(bg_x1, b_bar_cy, text=f"{int(pct_l)}% L", fill="#00E5FF", font=("Consolas", 8, "bold"), anchor="w")
        self.canvas.create_rectangle(b_bar_x1, b_bar_cy - 4, b_bar_x2, b_bar_cy + 4, fill="#1E2330", outline="#2C3446")
        fill_x = b_bar_x1 + int((pct_l / 100.0) * (b_bar_x2 - b_bar_x1))
        self.canvas.create_rectangle(b_bar_x1, b_bar_cy - 4, fill_x, b_bar_cy + 4, fill="#00E5FF", outline="")
        self.canvas.create_line((b_bar_x1 + b_bar_x2) // 2, b_bar_cy - 7, (b_bar_x1 + b_bar_x2) // 2, b_bar_cy + 7, fill="#FFFFFF", width=1)
        self.canvas.create_text(b_bar_x2 + 6, b_bar_cy, text=f"{int(pct_r)}% R", fill="#FF4081", font=("Consolas", 8, "bold"), anchor="w")
        bg_x2 = b_bar_x2 + 44

        # 4. Torque
        torq_x1 = bg_x2 + 12
        self.canvas.create_text(torq_x1, (bar_y1 + bar_y2) // 2 - 6, text="TORQUE", fill="#6B7280", font=("Helvetica", 7, "bold"), anchor="w")
        self.canvas.create_text(torq_x1, (bar_y1 + bar_y2) // 2 + 7, text=f"{torque_nm:+.1f} N·m", fill="#00FF66" if torque_nm >= 0 else "#FF3366", font=("Consolas", 8, "bold"), anchor="w")

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
        btn_y1 = (bar_y1 + bar_y2 - btn_h) // 2
        btn_y2 = btn_y1 + btn_h

        # Check if simulator/demo is active
        is_demo_on = obs_server.pressure_manager.is_simulator if hasattr(obs_server, "pressure_manager") else False

        self.swing_lab_demo_rect = (demo_x1, btn_y1, demo_x2, btn_y2)
        demo_bg = "#122534" if is_demo_on else "#161A24"
        demo_border = "#00E5FF" if is_demo_on else "#2A3448"
        demo_txt = "■ Stop Demo" if is_demo_on else "▶ Demo Swing"
        demo_col = "#00E5FF" if is_demo_on else "#D0D5DD"
        self.canvas.create_rectangle(demo_x1, btn_y1, demo_x2, btn_y2, fill=demo_bg, outline=demo_border, width=1)
        self.canvas.create_text((demo_x1 + demo_x2) // 2, (btn_y1 + btn_y2) // 2, text=demo_txt, fill=demo_col, font=("Helvetica", 8, "bold" if is_demo_on else "normal"), anchor="center")

        self.swing_lab_hw_rect = (hw_x1, btn_y1, hw_x2, btn_y2)
        self.canvas.create_rectangle(hw_x1, btn_y1, hw_x2, btn_y2, fill="#161A24", outline="#2A3448", width=1)
        self.canvas.create_text((hw_x1 + hw_x2) // 2, (btn_y1 + btn_y2) // 2, text="⚙ Hardware", fill="#D0D5DD", font=("Helvetica", 8), anchor="center")

        self.swing_lab_tare_rect = (tare_x1, btn_y1, tare_x2, btn_y2)
        self.canvas.create_rectangle(tare_x1, btn_y1, tare_x2, btn_y2, fill="#161A24", outline="#2A3448", width=1)
        self.canvas.create_text((tare_x1 + tare_x2) // 2, (btn_y1 + btn_y2) // 2, text="⚖ Tare Zero", fill="#D0D5DD", font=("Helvetica", 8), anchor="center")

        # 3. Main Workspace Split (Left: Heatmap, Right: COP & Curves)
        content_y1 = bar_y2 + 10
        content_h = bot_y - content_y1
        left_w = int(bar_w * 0.48)
        right_w = bar_w - left_w - 10
        left_x1 = bar_x1
        left_x2 = left_x1 + left_w
        right_x1 = left_x2 + 10
        right_x2 = right_x1 + right_w

        # --- LEFT PANE: DUAL-FOOT PRESSURE HEATMAP ---
        self.canvas.create_rectangle(left_x1, content_y1, left_x2, bot_y, fill="#10131D", outline="#22283A")
        self.canvas.create_text(left_x1 + 14, content_y1 + 16, text="🦶 DUAL-FOOT PRESSURE HEATMAP", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")

        # Draw Footbeds
        foot_w = (left_w - 50) // 2
        foot_h = content_h - 70
        l_foot_x1 = left_x1 + 16
        r_foot_x1 = l_foot_x1 + foot_w + 18
        foot_y1 = content_y1 + 38

        # Left Foot Box & Right Foot Box
        self.draw_single_foot_heatmap(l_foot_x1, foot_y1, foot_w, foot_h, is_left=True, latest=latest)
        self.draw_single_foot_heatmap(r_foot_x1, foot_y1, foot_w, foot_h, is_left=False, latest=latest)

        # --- RIGHT PANE: COP TRAJECTORY & FORCE CURVES ---
        cop_h = int(content_h * 0.56)
        curves_h = content_h - cop_h - 10
        cop_y1 = content_y1
        cop_y2 = cop_y1 + cop_h
        curves_y1 = cop_y2 + 10
        curves_y2 = bot_y

        # Top Right: COP Stance Box
        self.canvas.create_rectangle(right_x1, cop_y1, right_x2, cop_y2, fill="#10131D", outline="#22283A")
        self.canvas.create_text(right_x1 + 14, cop_y1 + 16, text="🎯 CENTER OF PRESSURE (COP) TRAIL", fill="#00E5FF", font=("Helvetica", 9, "bold"), anchor="w")
        self.draw_cop_trajectory_canvas(right_x1, cop_y1 + 28, right_w, cop_h - 32, latest=latest)

        # Bottom Right: Timeline Curves
        self.canvas.create_rectangle(right_x1, curves_y1, right_x2, curves_y2, fill="#10131D", outline="#22283A")
        self.canvas.create_text(right_x1 + 14, curves_y1 + 14, text="📈 WEIGHT TRANSFER & FORCE CURVES", fill="#00E5FF", font=("Helvetica", 8, "bold"), anchor="w")
        self.draw_force_timeline_canvas(right_x1, curves_y1 + 26, right_w, curves_h - 30)

    def draw_single_foot_heatmap(self, x1, y1, w, h, is_left=True, latest=None):
        x2, y2 = x1 + w, y1 + h
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#151926", outline="#242B3E", width=1)
        foot_label = "LEAD FOOT (LEFT)" if is_left else "TRAIL FOOT (RIGHT)"
        self.canvas.create_text((x1 + x2) // 2, y1 + 14, text=foot_label, fill="#8E94A5", font=("Helvetica", 7, "bold"))

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
        self.canvas.create_polygon(pts, fill="#0F121C", outline="#283046", width=2)

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
            glow_col = "#FF3366" if intensity > 0.75 else ("#FFB800" if intensity > 0.5 else ("#00FF66" if intensity > 0.25 else "#00E5FF"))
            self.canvas.create_oval(sx - rad, sy - rad, sx + rad, sy + rad, fill="", outline=glow_col, width=2)
            self.canvas.create_oval(sx - rad // 2, sy - rad // 2, sx + rad // 2, sy + rad // 2, fill=glow_col, outline="")
            self.canvas.create_text(sx, sy + rad + 9, text=f"{kg:.1f}kg", fill="#FFFFFF", font=("Consolas", 7, "bold"))

        # Foot Total Badge
        self.canvas.create_rectangle(x1 + 10, y2 - 24, x2 - 10, y2 - 6, fill="#111624", outline="#22283A")
        self.canvas.create_text((x1 + x2) // 2, y2 - 15, text=f"Total: {int(tot_foot)}%", fill="#00E5FF" if is_left else "#FF4081", font=("Helvetica", 8, "bold"))

    def draw_cop_trajectory_canvas(self, x1, y1, w, h, latest=None):
        x2, y2 = x1 + w, y1 + h
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        max_r = min(w, h) // 2 - 20

        # Grid lines & Rings
        for r_frac, label in [(0.33, "50mm"), (0.66, "100mm"), (1.0, "150mm")]:
            r = int(max_r * r_frac)
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="", outline="#1A2234", dash=(2, 4))
            self.canvas.create_text(cx + r + 4, cy - 6, text=label, fill="#475569", font=("Helvetica", 6), anchor="w")

        # Crosshairs
        self.canvas.create_line(x1 + 20, cy, x2 - 20, cy, fill="#1E293B", width=1)
        self.canvas.create_line(cx, y1 + 10, cx, y2 - 10, fill="#1E293B", width=1)
        self.canvas.create_text(cx - max_r + 10, cy - 8, text="◀ LEAD (L)", fill="#00E5FF", font=("Helvetica", 6, "bold"))
        self.canvas.create_text(cx + max_r - 10, cy - 8, text="TRAIL (R) ▶", fill="#FF4081", font=("Helvetica", 6, "bold"))
        self.canvas.create_text(cx + 6, y1 + 14, text="▲ TOES", fill="#64748B", font=("Helvetica", 6))
        self.canvas.create_text(cx + 6, y2 - 14, text="▼ HEELS", fill="#64748B", font=("Helvetica", 6))

        # Scale: 150mm maps to max_r
        scale = max_r / 150.0

        # Draw Trail from history
        trail = self.swing_lab_history
        if self.current_shot and self.current_shot.get("pressure_trace"):
            trail = self.current_shot["pressure_trace"]

        if len(trail) > 1:
            pts = []
            for item in trail[-120:]:
                tx = cx + int(item.get("cop_x", 0.0) * scale)
                ty = cy - int(item.get("cop_y", 0.0) * scale)
                pts.append((tx, ty, item.get("phase", "Address")))
            
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i + 1]
                ph = p2[2]
                seg_col = "#00FF66" if "ADDR" in ph.upper() else ("#FFB800" if "BACK" in ph.upper() else ("#FF3366" if "IMPACT" in ph.upper() else "#00E5FF"))
                self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=seg_col, width=2)

        # Current COP Bullseye Dot
        cur_cop_x = latest.get("cop_x", 0.0) if latest else 0.0
        cur_cop_y = latest.get("cop_y", 0.0) if latest else 0.0
        dot_x = cx + int(cur_cop_x * scale)
        dot_y = cy - int(cur_cop_y * scale)

        self.canvas.create_oval(dot_x - 12, dot_y - 12, dot_x + 12, dot_y + 12, fill="", outline="#00E5FF", width=2)
        self.canvas.create_oval(dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5, fill="#00E5FF", outline="#FFFFFF")
        self.canvas.create_text(dot_x + 14, dot_y, text=f"({cur_cop_x:+.0f}, {cur_cop_y:+.0f})", fill="#FFFFFF", font=("Consolas", 7, "bold"), anchor="w")

    def draw_force_timeline_canvas(self, x1, y1, w, h):
        x2, y2 = x1 + w, y1 + h
        self.canvas.create_rectangle(x1 + 10, y1 + 4, x2 - 10, y2 - 6, fill="#0C0E16", outline="#1A2234")

        trail = self.swing_lab_history
        if self.current_shot and self.current_shot.get("pressure_trace"):
            trail = self.current_shot["pressure_trace"]

        if len(trail) < 2:
            self.canvas.create_text((x1 + x2) // 2, (y1 + y2) // 2, text="Awaiting Swing Data...", fill="#475569", font=("Helvetica", 8))
            return

        graph_x1 = x1 + 20
        graph_x2 = x2 - 20
        graph_y1 = y1 + 10
        graph_y2 = y2 - 12
        gw = graph_x2 - graph_x1
        gh = graph_y2 - graph_y1

        # Center 50% line
        mid_y = graph_y1 + gh // 2
        self.canvas.create_line(graph_x1, mid_y, graph_x2, mid_y, fill="#1E293B", dash=(2, 4))
        self.canvas.create_text(graph_x1 - 4, mid_y, text="50%", fill="#475569", font=("Helvetica", 6), anchor="e")

        samples = trail[-100:]
        n = len(samples)

        # Plot Left % (Cyan) and Right % (Magenta) Curves
        pts_l = []
        pts_r = []
        for i, s in enumerate(samples):
            px = graph_x1 + int((i / float(max(1, n - 1))) * gw)
            pct_l = s.get("pct_left", 50.0)
            pct_r = s.get("pct_right", 100.0 - pct_l)
            py_l = graph_y2 - int((pct_l / 100.0) * gh)
            py_r = graph_y2 - int((pct_r / 100.0) * gh)
            pts_l.append((px, py_l))
            pts_r.append((px, py_r))

        for i in range(len(pts_l) - 1):
            self.canvas.create_line(pts_l[i][0], pts_l[i][1], pts_l[i+1][0], pts_l[i+1][1], fill="#00E5FF", width=2)
            self.canvas.create_line(pts_r[i][0], pts_r[i][1], pts_r[i+1][0], pts_r[i+1][1], fill="#FF4081", width=2)

        # Legend
        leg_x2 = x2 - 20
        # Right Foot % Legend (Magenta)
        self.canvas.create_line(leg_x2 - 82, y1 + 10, leg_x2 - 64, y1 + 10, fill="#FF4081", width=2)
        self.canvas.create_text(leg_x2 - 60, y1 + 10, text="Right Foot %", fill="#FF4081", font=("Helvetica", 7, "bold"), anchor="w")

        # Left Foot % Legend (Cyan)
        self.canvas.create_line(leg_x2 - 164, y1 + 10, leg_x2 - 146, y1 + 10, fill="#00E5FF", width=2)
        self.canvas.create_text(leg_x2 - 142, y1 + 10, text="Left Foot %", fill="#00E5FF", font=("Helvetica", 7, "bold"), anchor="w")

    def draw_balance_hardware_modal(self, w, h):
        # Modal dark backdrop
        self.canvas.create_rectangle(0, 0, w, h, fill="#000000", stipple="gray50")
        mw, mh = 580, 540
        mx1, my1 = (w - mw) // 2, (h - mh) // 2
        mx2, my2 = mx1 + mw, my1 + mh
        self.balance_modal_box_rect = (mx1, my1, mx2, my2)

        # Modal Window Container
        self.canvas.create_rectangle(mx1, my1, mx2, my2, fill="#121622", outline="#00E5FF", width=2)
        self.canvas.create_text(mx1 + 20, my1 + 22, text="⚙️ WII BALANCE BOARD HARDWARE & PAIRING", fill="#00E5FF", font=("Helvetica", 10, "bold"), anchor="w")

        # Close button [X]
        self.balance_modal_close_rect = (mx2 - 36, my1 + 10, mx2 - 12, my1 + 34)
        self.canvas.create_rectangle(mx2 - 36, my1 + 10, mx2 - 12, my1 + 34, fill="#1E222E", outline="#383E50")
        self.canvas.create_text(mx2 - 24, my1 + 22, text="✕", fill="#FFFFFF", font=("Helvetica", 9, "bold"))

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
        bg1 = "#0E2838" if not is_dual else "#161A24"
        bd1 = "#00E5FF" if not is_dual else "#2A3448"
        col1 = "#00E5FF" if not is_dual else "#94A3B8"
        self.canvas.create_rectangle(m1_x1, mode_y1, m1_x2, mode_y2, fill=bg1, outline=bd1, width=2 if not is_dual else 1)
        self.canvas.create_text((m1_x1 + m1_x2) // 2, (mode_y1 + mode_y2) // 2, text="🦶 1 Board (Single Mat)", fill=col1, font=("Helvetica", 8, "bold" if not is_dual else "normal"))

        self.balance_modal_mode_2_rect = (m2_x1, mode_y1, m2_x2, mode_y2)
        bg2 = "#0E2838" if is_dual else "#161A24"
        bd2 = "#00E5FF" if is_dual else "#2A3448"
        col2 = "#00E5FF" if is_dual else "#94A3B8"
        self.canvas.create_rectangle(m2_x1, mode_y1, m2_x2, mode_y2, fill=bg2, outline=bd2, width=2 if is_dual else 1)
        self.canvas.create_text((m2_x1 + m2_x2) // 2, (mode_y1 + mode_y2) // 2, text="🦶🦶 2 Boards (Dual Plate)", fill=col2, font=("Helvetica", 8, "bold" if is_dual else "normal"))

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
            self.canvas.create_rectangle(mx1 + 20, card_y1, mx2 - 20, card_y2, fill="#0F172A", outline="#38BDF8" if wiz_phase != "idle" else "#1E293B")

            # Status Message
            if wiz_phase == "waiting_left":
                p_text = "🦶 Step on the board under your LEFT foot (>5kg)"
                p_col = "#00FF66"
            elif wiz_phase == "waiting_right":
                p_text = "🦶 Now step on the board under your RIGHT foot (>5kg)"
                p_col = "#FFB800"
            elif wiz_phase == "complete":
                p_text = "✓ Both boards assigned (Left: Board A, Right: Board B)"
                p_col = "#00E5FF"
            else:
                p_text = "Step on boards to assign Left & Right feet:"
                p_col = "#CBD5E1"

            self.canvas.create_text(mx1 + 32, card_y1 + 14, text=p_text, fill=p_col, font=("Helvetica", 8, "bold"), anchor="w")
            self.canvas.create_text(mx1 + 32, card_y1 + 32, text=f"Board A: {w_a:.1f} kg   |   Board B: {w_b:.1f} kg", fill="#94A3B8", font=("Consolas", 8), anchor="w")

            # Step simulation chips during wizard
            if wiz_phase in ("waiting_left", "waiting_right"):
                sa_x1 = mx1 + 32
                sa_x2 = sa_x1 + 105
                sb_x1 = sa_x2 + 8
                sb_x2 = sb_x1 + 105
                s_y1 = card_y1 + 44
                s_y2 = s_y1 + 18

                self.balance_modal_step_a_rect = (sa_x1, s_y1, sa_x2, s_y2)
                self.canvas.create_rectangle(sa_x1, s_y1, sa_x2, s_y2, fill="#1E293B", outline="#00E5FF")
                self.canvas.create_text((sa_x1 + sa_x2) // 2, (s_y1 + s_y2) // 2, text="🦶 Step Board A", fill="#00E5FF", font=("Helvetica", 7, "bold"))

                self.balance_modal_step_b_rect = (sb_x1, s_y1, sb_x2, s_y2)
                self.canvas.create_rectangle(sb_x1, s_y1, sb_x2, s_y2, fill="#1E293B", outline="#FF4081")
                self.canvas.create_text((sb_x1 + sb_x2) // 2, (s_y1 + s_y2) // 2, text="🦶 Step Board B", fill="#FF4081", font=("Helvetica", 7, "bold"))
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
            btn_bg = "#0284C7" if wiz_phase != "idle" else "#1E293B"
            self.canvas.create_rectangle(b_x1, b_y1, b_x2, b_y2, fill=btn_bg, outline="#38BDF8")
            self.canvas.create_text((b_x1 + b_x2) // 2, (b_y1 + b_y2) // 2, text=btn_lbl, fill="#FFFFFF", font=("Helvetica", 8, "bold"))

            next_y = card_y2 + 8
        else:
            self.balance_modal_assign_btn_rect = None
            self.balance_modal_step_a_rect = None
            self.balance_modal_step_b_rect = None

        # --- SECTION 1: BLUETOOTH PAIRING PIN CARD ---
        from src.hardware.pressure.bluetooth_windows import (
            get_host_bluetooth_mac,
            mac_to_wii_pin,
            mac_to_wii_pin_display,
            format_mac_display,
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
        self.canvas.create_rectangle(mx1 + 20, pin_card_y1, mx2 - 20, pin_card_y2, fill="#171B2A", outline="#22283A")
        self.canvas.create_text(mx1 + 32, pin_card_y1 + 14, text="WINDOWS BLUETOOTH PAIRING PIN", fill="#6B7280", font=("Helvetica", 7, "bold"), anchor="w")
        self.canvas.create_text(mx1 + 32, pin_card_y1 + 28, text=f"Host Adapter MAC: {mac_disp}", fill="#94A3B8", font=("Consolas", 8), anchor="w")

        # Big Glowing PIN Box
        p_box_y1 = pin_card_y1 + 40
        p_box_y2 = p_box_y1 + 44
        self.canvas.create_rectangle(mx1 + 32, p_box_y1, mx2 - 32, p_box_y2, fill="#0B0F17", outline="#00E5FF", width=1)
        self.canvas.create_text((mx1 + mx2) // 2, (p_box_y1 + p_box_y2) // 2, text=pin_disp, fill="#00E5FF", font=("Consolas", 16, "bold"))

        # Action Buttons under PIN (Copy PIN + Open BT Settings)
        act_y1 = p_box_y2 + 8
        act_y2 = act_y1 + 28
        half_w = (mx2 - mx1 - 74) // 2
        btn_copy_x1 = mx1 + 32
        btn_copy_x2 = btn_copy_x1 + half_w
        btn_open_x1 = btn_copy_x2 + 10
        btn_open_x2 = mx2 - 32

        self.balance_modal_copy_pin_rect = (btn_copy_x1, act_y1, btn_copy_x2, act_y2)
        self.canvas.create_rectangle(btn_copy_x1, act_y1, btn_copy_x2, act_y2, fill="#0E2838", outline="#00E5FF")
        self.canvas.create_text((btn_copy_x1 + btn_copy_x2) // 2, (act_y1 + act_y2) // 2, text="📋 Copy PIN to Clipboard", fill="#00E5FF", font=("Helvetica", 8, "bold"))

        self.balance_modal_bt_settings_rect = (btn_open_x1, act_y1, btn_open_x2, act_y2)
        self.canvas.create_rectangle(btn_open_x1, act_y1, btn_open_x2, act_y2, fill="#1E2A3A", outline="#38BDF8")
        self.canvas.create_text((btn_open_x1 + btn_open_x2) // 2, (act_y1 + act_y2) // 2, text="🌐 Open Bluetooth Settings", fill="#38BDF8", font=("Helvetica", 8, "bold"))

        # --- SECTION 2: HARDWARE CONTROLS ---
        hw_y1 = pin_card_y2 + 10
        hw_y2 = hw_y1 + 40
        is_sim = pm.is_simulator if pm else False

        self.balance_modal_tare_rect = (mx1 + 20, hw_y1, mx1 + 265, hw_y2)
        self.canvas.create_rectangle(mx1 + 20, hw_y1, mx1 + 265, hw_y2, fill="#1A2234", outline="#00FF66")
        self.canvas.create_text((mx1 + 20 + mx1 + 265) // 2, (hw_y1 + hw_y2) // 2, text="⚖️ Tare / Zero Baseline", fill="#00FF66", font=("Helvetica", 8, "bold"))

        self.balance_modal_sim_rect = (mx1 + 280, hw_y1, mx2 - 20, hw_y2)
        sim_col = "#00E5FF" if is_sim else "#475569"
        self.canvas.create_rectangle(mx1 + 280, hw_y1, mx2 - 20, hw_y2, fill="#151926", outline=sim_col)
        self.canvas.create_text((mx1 + 280 + mx2 - 20) // 2, (hw_y1 + hw_y2) // 2, text=f"Simulator Mode: {'[ON]' if is_sim else '[OFF]'}", fill="#FFFFFF", font=("Helvetica", 8, "bold"))

        # --- SECTION 3: STEP-BY-STEP PAIRING INSTRUCTIONS ---
        guide_y1 = hw_y2 + 8
        guide_y2 = my2 - 12
        self.canvas.create_rectangle(mx1 + 20, guide_y1, mx2 - 20, guide_y2, fill="#141824", outline="#1F2536")
        self.canvas.create_text(mx1 + 32, guide_y1 + 12, text="PAIRING & CALIBRATION INSTRUCTIONS", fill="#64748B", font=("Helvetica", 7, "bold"), anchor="w")

        steps = [
            "1. Press red SYNC button on board(s) (4 LEDs blink) → Open BT Settings → Paste PIN.",
            "2. For 2-Board setups: Select '2 Boards' above and click 'Start Wizard' to identify feet.",
            "3. Step on Left board first, then Right board when prompted.",
            "4. Stand evenly on board(s) and click 'Tare Zero' to calibrate baseline."
        ]
        for idx, s in enumerate(steps):
            self.canvas.create_text(mx1 + 32, guide_y1 + 26 + (idx * 14), text=s, fill="#CBD5E1", font=("Helvetica", 7), anchor="w")

def main():
    t_ws = threading.Thread(target=websocket_worker, daemon=True)
    t_ws.start()

    # Start OBS Studio Browser Source Overlay Server on port 9321
    obs_server.launch_obs_server_thread()

    root = tk.Tk()
    root.geometry("1150x780")
    app = ShanktuaryApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass

if __name__ == "__main__":
    main()

