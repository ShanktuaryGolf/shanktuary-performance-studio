"""Production, explicitly started connection setup in the Studio design system.

The controller owns hardware, generation gates and persistence. This window only
requests actions. Selecting Another launch monitor explicitly starts its local
listener; drawing, launch and Back never start one. Other sources keep Connect.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog

import theme
from src.ui import tokens as T
from src.ui.asset_paths import asset_path
from src.ui.splash import SplashScreen


class ConnectionWizard(SplashScreen):
    W, H = 1280, 820
    hero_club_height = 0.40
    hero_ball_y = 0.70

    def __init__(
        self, root, controller, clubs=None, current_club="7 Iron", club_specs=None
    ):
        self.root, self.controller = root, controller
        self.clubs = list(clubs or ["Driver", "5 Iron", "7 Iron", "9 Iron", "PW"])
        self.current_club = (
            current_club if current_club in self.clubs else self.clubs[0]
        )
        self.club_specs = club_specs or {}
        settings = dict(getattr(controller, "settings", {}) or {})
        self.source = settings.get("source", "nova")
        if self.source not in ("nova", "gspro", "open_connect", "cgp", "both"):
            self.source = "nova"
        self.source_locked = bool(settings.get("source_locked", False))
        self.always_show = bool(settings.get("always_show_splash", False))
        self.result = None
        self.page = "choose"
        self.advanced = self.source == "cgp"
        self._alive = True
        self._images, self._image_cache, self._hero_cache = [], {}, {}
        self._hit_rects = []
        self._club_menu_open = False
        self._widgets = []
        self._status = {}
        self._local_message = ""
        self._discovery_results = queue.Queue()
        self._discovery_generation = 0
        self._discovering = False
        self._devices = []
        self._fields = {}
        self._options = {
            s: {} for s in ("nova", "gspro", "open_connect", "cgp", "both")
        }
        self._options["open_connect"] = self._saved_open_connect_options(settings)
        self._options["nova"] = {
            "host": settings.get("nova_host", ""),
            "discovery": True,
        }
        self._options["gspro"] = {"db_path": settings.get("db_path", "")}
        self._options["cgp"] = {
            "host": settings.get("cgp_host", ""),
            "port": str(settings.get("cgp_port", 921)),
        }
        for options in self._options.values():
            options["ogc_enrichment"] = bool(settings.get("ogc_enrichment", False))
            options["ogc_club_estimates"] = bool(
                settings.get("ogc_club_estimates", False)
            )
        self.win = tk.Toplevel(root)
        self.win.title("Shanktuary · Connection")
        self.win.configure(bg=T.PAGE_BG)
        self.w = min(self.W, self.win.winfo_screenwidth() - 40)
        viewport_h = min(self.H, self.win.winfo_screenheight() - 70)
        self.h = self.H
        self.win.geometry(f"{self.w}x{viewport_h}+20+20")
        self.win.resizable(False, False)
        self.canvas = tk.Canvas(self.win, bg=T.PAGE_BG, highlightthickness=0)
        if viewport_h < self.h:
            scroll = tk.Scrollbar(
                self.win, orient="vertical", command=self.canvas.yview
            )
            scroll.pack(side="right", fill="y")
            self.canvas.configure(
                yscrollcommand=scroll.set, scrollregion=(0, 0, self.w, self.h)
            )
            self.canvas.bind(
                "<Button-4>", lambda _: self.canvas.yview_scroll(-1, "units")
            )
            self.canvas.bind(
                "<Button-5>", lambda _: self.canvas.yview_scroll(1, "units")
            )
            self.canvas.bind(
                "<MouseWheel>",
                lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"),
            )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_click)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        if root.winfo_viewable():
            self.win.transient(root)
        self.win.update_idletasks()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        if self.win.winfo_viewable():
            self.win.grab_set()
        self._draw()
        self.win.after(200, self._poll_status)

    @staticmethod
    def _saved_open_connect_options(settings):
        network = bool(settings.get("open_connect_lan", False))
        return {
            "host": "0.0.0.0" if network else "127.0.0.1",
            "port": str(settings.get("open_connect_port", 921)),
            "location": "network" if network else "local",
        }

    def _text(self, x, y, text, size=10, color=None, bold=False, width=None):
        return self.canvas.create_text(
            x,
            y,
            text=text,
            anchor="nw",
            fill=color or T.TEXT_2,
            font=(theme.ui_font(), size, "bold" if bold else "normal"),
            width=width or 0,
        )

    def _button(self, x, y, w, text, action, primary=False, enabled=True):
        self._rounded(
            x,
            y,
            x + w,
            y + 42,
            7,
            T.GOLD
            if primary and enabled
            else T.SURFACE_2
            if not enabled
            else T.PAGE_BG,
            T.HAIRLINE,
        )
        self._text(
            x + 20,
            y + 13,
            text,
            9,
            "#0A2029" if primary and enabled else T.TEXT_2 if enabled else T.TEXT_3,
            True,
        )
        if enabled:
            self._hit((x, y, x + w, y + 42), action)

    def _draw(self):
        for widget in self._widgets:
            widget.destroy()
        self._widgets, self._fields, self._images, self._hit_rects = [], {}, [], []
        self.canvas.delete("all")
        split = int(self.w * 0.344)
        self._draw_left(split)
        x, right = split + 42, self.w - 42
        self._text(x, 38, "S E S S I O N   S E T U P", 8, T.TEXT_3)
        self._text(
            x,
            87,
            "①  CHOOSE    ───    ②  CONNECT & TEST    ───    ③  PLAY",
            9,
            T.TEAL_TEXT,
        )
        if self.page == "choose":
            self._draw_choose(x, right)
        else:
            self._draw_connect(x, right)

    def _draw_choose(self, x, right):
        self._text(x, 135, "What would you like to connect?", 21, T.TEXT, True)
        self._text(
            x,
            180,
            "Choose the setup you use. We’ll help you connect and check a shot.",
            10,
        )
        cards = [
            (
                "nova",
                "nova_logo.png",
                "Connect my Nova",
                "Connect directly to your launch monitor.\nNo GSPro required.",
            ),
            (
                "gspro",
                "gspro_logo.png",
                "Use GSPro",
                "Read shots from GSPro installed\non this computer.",
            ),
            (
                "open_connect",
                None,
                "Another launch monitor",
                "Use your usual compatible connector.\nSelecting this starts local listening.",
            ),
        ]
        for i, (source, logo, title, note) in enumerate(cards):
            y = 223 + i * 116
            selected = self.source == source or (
                self.source == "both" and source == "nova"
            )
            self._rounded(
                x,
                y,
                right,
                y + 104,
                9,
                T.ACTIVE_BG if selected else T.SURFACE,
                T.GOLD if selected else T.HAIRLINE,
            )
            if logo:
                im = self._load_image(source, asset_path(logo), 28)
                if im:
                    self.canvas.create_image(x + 88, y + 52, image=im)
            else:
                self._text(x + 69, y + 33, "♧", 26, T.TEAL_TEXT)
            self._text(x + 174, y + 20, title, 12, T.TEXT, True)
            self._text(x + 174, y + 49, note, 9, width=right - x - 220)
            self.canvas.create_oval(
                right - 39,
                y + 45,
                right - 24,
                y + 60,
                outline=T.GOLD if selected else T.HAIRLINE,
                width=3 if selected else 1,
            )
            if not self.source_locked:
                self._hit((x, y, right, y + 104), "source", source)
        self._text(x, 578, "Not sure which to choose?  Help me choose", 8, T.TEAL_TEXT)
        self._hit((x, 573, x + 300, 603), "help")
        self._text(
            right - 220,
            578,
            "Local listening when you choose it.",
            8,
            T.TEXT_3,
        )
        self.canvas.create_line(x, 612, right, 612, fill=T.HAIRLINE)
        self._text(
            x,
            630,
            "Advanced connections   ·   CGP Draft 2   [EXPERIMENTAL]",
            8,
            T.GOLD if self.source == "cgp" else T.TEXT_3,
        )
        self._hit((x, 612, right, 666), "advanced")
        if self.advanced:
            self._text(
                x,
                654,
                "Select CGP Draft 2  →  Requires a compatible CGP device.",
                9,
                T.TEAL_TEXT,
            )
            if not self.source_locked:
                self._hit((x, 650, right, 680), "source", "cgp")
        if self.source_locked:
            self._text(x, 677, "Source is fixed by SPS_SHOT_SOURCE.", 9, T.GOLD)
        y = self.h - 116
        self.canvas.create_line(x, y - 20, right, y - 20, fill=T.HAIRLINE)
        self._button(x, y, 82, "Close", "close")
        self._button(right - 236, y, 236, "CONTINUE     →", "continue", True)
        self._text(
            x + 190,
            self.h - 56,
            "You can change your setup later in Connection.",
            8,
            T.TEXT_3,
        )

    def _entry(self, x, y, w, label, key, default=""):
        self._text(x, y, label.upper(), 8, T.TEXT_3)
        var = tk.StringVar(value=self._options[self.source].get(key, default))
        entry = tk.Entry(
            self.win,
            textvariable=var,
            bg=T.PAGE_BG,
            fg=T.TEXT,
            insertbackground=T.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=T.HAIRLINE,
            highlightcolor=T.TEAL_TEXT,
            font=(theme.ui_font(), 10),
        )
        self.canvas.create_window(
            x, y + 20, window=entry, width=w, height=38, anchor="nw"
        )
        self._widgets.append(entry)
        self._fields[key] = var

    def _draw_connect(self, x, right):
        self._text(x, 135, "Connect your shot source.", 21, T.TEXT, True)
        self._text(
            x, 180, "Connect your setup, then hit a test shot. All right here.", 10
        )
        mid = x + int((right - x) * 0.56)
        bottom = self.h - 130
        self._rounded(x, 223, mid, bottom, 9, T.SURFACE, T.HAIRLINE)
        self._rounded(mid + 18, 223, right, bottom, 9, T.SURFACE, T.HAIRLINE)
        ix, iw = x + 20, mid - x - 40
        title = {
            "nova": "Connect your Nova",
            "both": "Nova + GSPro · legacy setting",
            "gspro": "Read your GSPro shots",
            "open_connect": "Set up your connector",
            "cgp": "CGP Draft 2 · Experimental",
        }[self.source]
        self._text(ix, 244, title, 11, T.TEXT, True)
        if self.source == "open_connect":
            self._text(
                ix, 280, "Open your usual connector.", 15, T.TEXT, True, width=iw
            )
            self._text(
                ix,
                329,
                "Choose its GSPro / Open Connect output, if available. Then hit a test shot.",
                11,
                width=iw,
            )
            self._text(
                ix,
                414,
                (
                    "Using your saved network setting. Studio is reachable on your network. Review Advanced to change it."
                    if self._options["open_connect"].get("location") == "network"
                    else "Studio listens here automatically. No address entry or extra Start button is needed for the normal local setup."
                ),
                10,
                T.TEAL_TEXT,
                width=iw,
            )
            self._text(
                ix,
                492,
                "A compatible connector is required. This does not make every launch monitor compatible.",
                9,
                T.TEXT_2,
                width=iw,
            )
            self._text(ix, 555, "Connector setup help  →", 10, T.TEAL_TEXT)
            self._hit((ix, 549, mid - 20, 582), "connector_help")
            self._text(ix, 619, "Advanced connection settings  →", 9, T.TEXT_3)
            self._hit((ix, 610, mid - 20, 650), "connection_options")
        elif self.source in ("nova", "both"):
            self._text(
                ix,
                280,
                "Connect directly to Nova. No GSPro required.\nYour monitor and Studio must be on the same network.",
                10,
                width=iw,
            )
            self._text(
                ix,
                355,
                "Discovery begins only when you press Connect.\nStudio uses your existing Nova discovery settings.",
                9,
                T.TEAL_TEXT,
                width=iw,
            )
            self._text(
                ix,
                422,
                "Discovery: configured address, local network,\nthen the standard Nova hostname.",
                9,
                width=iw,
            )
        elif self.source == "gspro":
            self._text(
                ix,
                280,
                "Read new range shots from your local GSPro database. This does not connect to a remote GSPro computer.",
                10,
                width=iw,
            )
            self._entry(ix, 370, iw, "GSPro database path (optional)", "db_path")
            self._button(ix, 445, 160, "Browse for GSPro.db", "browse")
            self._text(
                ix,
                515,
                "Start reading, open the GSPro range, then hit a new shot. Existing shots do not count as a connection test.",
                9,
                T.TEAL_TEXT,
                width=iw,
            )
        else:
            self._text(
                ix,
                280,
                "Experimental Draft 2. Final ball shots only. Separate club, flight and control data are not imported. Device names and self-signed identities are not verified. Reconnect manually if disconnected.",
                9,
                width=iw,
            )
            self._button(
                ix,
                373,
                iw,
                "SEARCHING…" if self._discovering else "REFRESH DEVICES",
                "discover",
                enabled=not self._discovering,
            )
            self._text(ix, 434, "COMPATIBLE DEVICES", 8, T.TEXT_3)
            chosen = self._options["cgp"].get("device")
            devices = self._menu_button(
                chosen.name if chosen else "Find and select a device",
                [(d.name, d) for d in self._devices],
                lambda d: self._options["cgp"].update(device=d),
            )
            self.canvas.create_window(
                ix, 458, window=devices, width=iw, height=35, anchor="nw"
            )
            self._widgets.append(devices)
            self._text(
                ix,
                519,
                "Select your compatible CGP source, then press Connect. Device discovery never connects automatically.",
                9,
                T.TEAL_TEXT,
                width=iw,
            )
        action = (
            "START LISTENER"
            if self.source == "open_connect"
            else "START READING"
            if self.source == "gspro"
            else "CONNECT"
        )
        if self.source != "open_connect":
            self._button(ix, bottom - 63, iw, action, "connect", True)
        sx = mid + 38
        self._text(sx, 244, "Connection check", 11, T.TEXT, True)
        self.status_var = tk.StringVar(value="Not started")
        label = tk.Label(
            self.win,
            textvariable=self.status_var,
            bg=T.PAGE_BG,
            fg=T.TEXT_2,
            anchor="w",
            justify="left",
            wraplength=right - sx - 30,
            padx=10,
            pady=10,
            font=(theme.ui_font(), 9),
        )
        self.canvas.create_window(
            sx,
            277,
            window=label,
            width=right - sx - 20,
            height=90 if self.source == "open_connect" else 61,
            anchor="nw",
        )
        self._widgets.append(label)
        checks = [
            ("1  Start your connection", "Studio waits for your explicit action."),
            (
                "2  Wait for your source",
                "Listening is not the same as a connected monitor.",
            ),
            ("3  Hit a test shot", "We’ll confirm when a new shot arrives."),
            ("✓  Ready to play", "Available after a test shot arrives."),
        ]
        if self.source == "open_connect":
            checks = [
                (
                    "1  Waiting for connector",
                    "Wait for your connector to reach Studio.",
                ),
                ("2  Connected", "Connection alone does not confirm a shot."),
                ("3  Test shot received", "A valid new shot unlocks Start Session."),
            ]
        for i, (heading, note) in enumerate(checks):
            yy = (385 + i * 65) if self.source == "open_connect" else (357 + i * 65)
            self._text(sx, yy, heading, 9)
            self._text(sx + 20, yy + 23, note, 8, T.TEXT_3, width=right - sx - 38)
        if self.source not in ("nova", "both"):
            self._text(sx, 599, "Optional metric estimates  →", 8, T.TEAL_TEXT)
            self._hit((sx, 594, right - 20, 620), "metrics")
        retry = self.source == "open_connect" and self._status.get("state") in (
            "idle",
            "error",
            None,
        )
        self._button(
            sx,
            bottom - 63,
            right - sx - 20,
            "RETRY CONNECTION" if retry else "STOP CONNECTION",
            "connect" if retry else "stop",
        )
        y = self.h - 101
        self._button(x, y, 98, "←  Back", "back")
        self._button(
            right - 210,
            y,
            210,
            "START SESSION",
            "finish",
            True,
            self._status.get("shot_received", False)
            and self._status.get("state") == "ready",
        )
        club = self._menu_button(
            self.current_club,
            [(c, c) for c in self.clubs],
            lambda c: setattr(self, "current_club", c),
        )
        self.canvas.create_window(x + 120, y + 20, window=club, anchor="w", width=150)
        self._widgets.append(club)
        self._text(x + 120, y - 18, "SESSION CLUB", 8, T.TEXT_3)
        self.always_var = tk.BooleanVar(value=self.always_show)
        check = tk.Checkbutton(
            self.win,
            text="Show this on every launch",
            variable=self.always_var,
            command=self._set_always,
            bg=T.PAGE_BG,
            fg=T.TEXT_2,
            selectcolor=T.SURFACE,
            highlightthickness=0,
            activebackground=T.PAGE_BG,
            activeforeground=T.TEXT,
            font=(theme.ui_font(), 8),
        )
        self.canvas.create_window(x + 120, y + 57, window=check, anchor="w")
        self._widgets.append(check)
        self._update_status()

    def _menu_button(self, label, choices, on_select):
        button = tk.Menubutton(
            self.win,
            text=label + "  ▾",
            bg=T.SURFACE,
            fg=T.TEXT,
            activebackground=T.ACTIVE_BG,
            activeforeground=T.TEXT,
            relief="flat",
            anchor="w",
            font=(theme.ui_font(), 10),
            padx=10,
            pady=8,
        )
        menu = tk.Menu(
            button,
            tearoff=False,
            bg=T.SURFACE,
            fg=T.TEXT,
            activebackground=T.ACTIVE_BG,
            activeforeground=T.GOLD,
        )
        button.configure(menu=menu)

        def choose(label, value):
            on_select(value)
            button.configure(text=label + "  ▾")

        for text, value in choices:
            menu.add_command(label=text, command=lambda t=text, v=value: choose(t, v))
        return button

    def _set_always(self):
        self.always_show = self.always_var.get()

    def _remember_fields(self):
        self._options[self.source].update(
            {k: v.get().strip() for k, v in self._fields.items()}
        )

    def _poll_status(self):
        if not self._alive:
            return
        try:
            try:
                generation, devices, error = self._discovery_results.get_nowait()
            except queue.Empty:
                pass
            else:
                if generation == self._discovery_generation:
                    self._discovering = False
                    previous = self._options["cgp"].get("device")
                    self._devices = devices
                    self._options["cgp"].pop("device", None)
                    if previous:
                        match = next(
                            (
                                d
                                for d in devices
                                if d.service_name == previous.service_name
                            ),
                            None,
                        )
                        if match:
                            self._options["cgp"]["device"] = match
                    self._local_message = (
                        error
                        or f"{len(devices)} compatible CGP device(s) found. Select one to connect."
                    )
                    self._remember_fields()
                    self._draw()
            previous_state = self._status.get("state")
            previous_ready = self._status.get("state") == "ready" and self._status.get(
                "shot_received", False
            )
            self._status = dict(self.controller.snapshot() or {})
            ready = self._status.get("state") == "ready" and self._status.get(
                "shot_received", False
            )
            if self.page == "connect":
                if ready != previous_ready or (
                    self.source == "open_connect"
                    and previous_state != self._status.get("state")
                ):
                    self._remember_fields()
                    self._draw()
                else:
                    self._update_status()
            self.win.after(250, self._poll_status)
        except tk.TclError:
            self._alive = False

    def _update_status(self):
        if hasattr(self, "status_var"):
            if self.source == "open_connect" and not getattr(
                self, "_local_message", ""
            ):
                state = self._status.get("state")
                message = str(self._status.get("message") or "")
                if state == "error" and any(
                    term in message.lower() for term in ("in use", "errno 98", "10048")
                ):
                    message = "Port in use. Another app, such as GSPro, may own it. Close that app or change the port in Advanced."
                elif state in ("listening", "connected", "ready", "connecting", "idle"):
                    message = {
                        "listening": "Waiting for connector · network listening"
                        if self._options["open_connect"].get("location") == "network"
                        else "Waiting for connector",
                        "connected": "Connected · hit a test shot",
                        "ready": "Test shot received · ready to play",
                        "connecting": "Starting listener…",
                        "idle": "Connection stopped",
                    }[state]
                self.status_var.set(message or "Waiting for connector")
                return
            self.status_var.set(
                getattr(self, "_local_message", "")
                or self._status.get("message")
                or {
                    "idle": "Not started",
                    "listening": "Listening · waiting for connector",
                    "connected": "Connected · hit a test shot",
                    "ready": "Test shot received · ready to play",
                    "error": "Connection failed",
                }.get(self._status.get("state"), "Not started")
            )

    def _on_click(self, event):
        for x1, y1, x2, y2, action, payload in reversed(self._hit_rects):
            if x1 <= event.x <= x2 and y1 <= self.canvas.canvasy(event.y) <= y2:
                self._action(action, payload)
                return

    def _action(self, action, payload=None):
        self._remember_fields()
        self._local_message = ""
        if action == "source" and not self.source_locked:
            if payload != self.source:
                self._discovery_generation += 1
                self._discovering = False
                self.controller.select_source(payload)
                self.source = payload
                self._status = {}
            if payload == "open_connect":
                self.page = "connect"
                if self.controller.snapshot().get("state") not in (
                    "listening",
                    "connected",
                    "ready",
                    "connecting",
                ):
                    self._start_connection()
        elif action == "advanced":
            self.advanced = not self.advanced
        elif action == "continue":
            self.page = "connect"
            if self.source == "open_connect":
                self._start_connection()
            if self.source == "cgp" and not self._devices:
                self._start_discovery()
        elif action == "back":
            self._discovery_generation += 1
            self._discovering = False
            self.controller.stop()
            self._status = {}
            self.page = "choose"
        elif action == "close":
            self._on_close()
            return
        elif action in ("local", "network"):
            self.controller.stop()
            self._status = {}
            self._options[self.source].update(
                location=action, host="127.0.0.1" if action == "local" else "0.0.0.0"
            )
        elif action == "browse":
            path = filedialog.askopenfilename(
                parent=self.win,
                title="Select GSPro database",
                filetypes=[("SQLite database", "*.db"), ("All files", "*")],
            )
            if path:
                self._options[self.source]["db_path"] = path
        elif action == "metrics":
            self._show_metric_options()
        elif action == "discover":
            self._start_discovery()
        elif action == "connection_options":
            self._show_connection_options()
        elif action == "connector_help":
            self._show_connector_help()
        elif action == "connect":
            self._start_connection()
        elif action == "stop":
            self.controller.stop()
            self._status = {}
        elif action == "finish":
            # Re-read authoritative state: a rendered button can become stale.
            state = self.controller.snapshot() or {}
            if state.get("state") != "ready" or not state.get("shot_received"):
                self._status = dict(state)
            else:
                self.controller.save_selection(self.source, self.always_show)
                self.result = {
                    "source": self.source,
                    "club": self.current_club,
                    "always_show": self.always_show,
                }
                self._close()
                return
        elif action == "help":
            from tkinter import messagebox

            messagebox.showinfo(
                "Choose your connection",
                "Nova: direct Nova connection.\n\nGSPro: read range shots from GSPro on this computer.\n\nAnother launch monitor: a compatible OpenConnect connector is required.\n\nCGP Draft 2: experimental, for compatible CGP devices only.",
                parent=self.win,
            )
        self._draw()

    def _start_connection(self):
        try:
            options = dict(self._options[self.source])
            if self.source == "cgp" and getattr(self, "_discovering", False):
                raise ValueError(
                    "Wait for device discovery to finish before connecting."
                )
            if self.source == "cgp" and not options.get("device"):
                raise ValueError("Find and select a compatible CGP device first.")
            if self.source == "open_connect":
                options["port"] = int(options.get("port", 921))
                if not 1 <= options["port"] <= 65535:
                    raise ValueError("Port must be between 1 and 65535.")
            self.controller.start(self.source, options)
            self._status = dict(self.controller.snapshot() or {})
        except (ValueError, OSError, RuntimeError) as exc:
            self._status = {
                "state": "error",
                "message": str(exc),
                "shot_received": False,
            }
            self._local_message = str(exc)

    def _show_connector_help(self):
        from tkinter import messagebox

        messagebox.showinfo(
            "Connector setup help",
            "Springbok, RELA and other compatible connectors use the same Open Connect receiver here, not separate Studio modes.\n\nOpen your usual connector and choose its GSPro / Open Connect output if that option is available. Names and supported outputs vary by connector and version.\n\nFor the usual local setup, no address entry is needed. If GSPro or another receiver already occupies the port, close that receiver or review Advanced settings. This is setup guidance, not a claim that your hardware has been tested.",
            parent=self.win,
        )

    def _show_connection_options(self):
        dialog = tk.Toplevel(self.win)
        dialog.title("Advanced connection settings")
        dialog.configure(bg=T.PAGE_BG)
        dialog.transient(self.win)
        dialog.geometry("540x365")
        options = self._options["open_connect"]
        location = tk.StringVar(value=options.get("location", "local"))
        port = tk.StringVar(value=str(options.get("port", 921)))
        tk.Label(
            dialog,
            text="Advanced connection settings",
            bg=T.PAGE_BG,
            fg=T.TEXT,
            font=(theme.ui_font(), 15, "bold"),
        ).pack(anchor="w", padx=24, pady=(22, 12))
        for text, value in [
            ("This computer only (recommended)", "local"),
            ("Allow a connector on my network", "network"),
        ]:
            tk.Radiobutton(
                dialog,
                text=text,
                variable=location,
                value=value,
                bg=T.PAGE_BG,
                fg=T.TEXT_2,
                selectcolor=T.SURFACE,
                activebackground=T.PAGE_BG,
                activeforeground=T.TEXT,
            ).pack(anchor="w", padx=24, pady=5)
        tk.Label(dialog, text="Port", bg=T.PAGE_BG, fg=T.TEXT_2).pack(
            anchor="w", padx=24, pady=(12, 4)
        )
        tk.Entry(
            dialog,
            textvariable=port,
            bg=T.SURFACE,
            fg=T.TEXT,
            insertbackground=T.TEXT,
            relief="flat",
        ).pack(anchor="w", padx=24, ipady=6)
        error = tk.StringVar()
        tk.Label(
            dialog,
            textvariable=error,
            bg=T.PAGE_BG,
            fg=T.GOLD,
            wraplength=490,
            justify="left",
        ).pack(anchor="w", padx=24, pady=8)
        tk.Label(
            dialog,
            text="Default: 921. Change it only if your connector supports another port.\nNetwork mode exposes the listener to your network; no firewall settings are changed.",
            bg=T.PAGE_BG,
            fg=T.TEXT_3,
            justify="left",
            wraplength=490,
        ).pack(anchor="w", padx=24)

        def close():
            dialog.destroy()
            if self._alive:
                self.win.grab_set()

        def apply():
            try:
                number = int(port.get())
                if not 1 <= number <= 65535:
                    raise ValueError()
            except ValueError:
                error.set("Port must be a whole number between 1 and 65535.")
                return
            options.update(
                port=number,
                location=location.get(),
                host="127.0.0.1" if location.get() == "local" else "0.0.0.0",
            )
            self._local_message = ""
            self._start_connection()
            close()
            self._draw()

        tk.Button(
            dialog,
            text="APPLY & RECONNECT",
            command=apply,
            bg=T.GOLD,
            fg=T.PAGE_BG,
            relief="flat",
            padx=16,
            pady=8,
        ).pack(anchor="e", padx=24, pady=12)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.grab_set()

    def _show_metric_options(self):
        dialog = tk.Toplevel(self.win)
        dialog.title("Optional metric estimates")
        dialog.configure(bg=T.PAGE_BG)
        dialog.transient(self.win)
        dialog.geometry("560x330")
        tk.Label(
            dialog,
            text="Optional estimates, not measurements",
            bg=T.PAGE_BG,
            fg=T.TEXT,
            font=(theme.ui_font(), 15, "bold"),
        ).pack(anchor="w", padx=24, pady=(24, 14))
        tk.Label(
            dialog,
            text="OpenGolfCoach runs locally and only fills missing metrics.\nMeasured values and their provenance stay unchanged.\nChanges take effect on your next explicit connection start.",
            justify="left",
            bg=T.PAGE_BG,
            fg=T.TEXT_2,
            font=(theme.ui_font(), 10),
        ).pack(anchor="w", padx=24)
        variables = {}
        for key, text in [
            (
                "ogc_enrichment",
                "Fill missing flight metrics locally with OpenGolfCoach",
            ),
            ("ogc_club_estimates", "Allow speculative club estimates (not measured)"),
        ]:
            var = tk.BooleanVar(value=self._options[self.source].get(key, False))
            variables[key] = var
            tk.Checkbutton(
                dialog,
                text=text,
                variable=var,
                bg=T.PAGE_BG,
                fg=T.TEXT_2,
                selectcolor=T.SURFACE,
                activebackground=T.PAGE_BG,
                activeforeground=T.TEXT,
                highlightthickness=0,
                font=(theme.ui_font(), 10),
            ).pack(anchor="w", padx=24, pady=10)

        def close():
            values = {key: var.get() for key, var in variables.items()}
            if any(
                self._options[self.source].get(key, False) != value
                for key, value in values.items()
            ):
                self.controller.stop()
                self._status = {}
                self._options[self.source].update(values)
                self._local_message = (
                    "Metric options changed. Start the connection to apply them."
                )
            dialog.destroy()
            self._draw()
            if self._alive:
                self.win.grab_set()

        tk.Button(
            dialog,
            text="DONE",
            command=close,
            bg=T.GOLD,
            fg=T.PAGE_BG,
            relief="flat",
            padx=24,
            pady=8,
        ).pack(anchor="e", padx=24, pady=10)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.grab_set()

    def _start_discovery(self):
        if self._discovering:
            return
        self._discovering = True
        self._discovery_generation += 1
        generation = self._discovery_generation

        def find():
            try:
                from src.connections.cgp import discover

                devices, error = list(discover(timeout=3)), ""
            except Exception as exc:
                devices, error = [], f"Discovery failed: {exc}"
            self._discovery_results.put((generation, devices, error))

        threading.Thread(target=find, daemon=True).start()

    def _on_close(self):
        self._discovery_generation += 1
        self.controller.stop()
        self.result = None
        self._close()
