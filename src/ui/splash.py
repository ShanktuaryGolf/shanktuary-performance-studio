"""Shanktuary launch splash — the shot-source onboarding screen.

Implements the approved splash design: a branded left panel and a right
column carrying three steps — connect to a shot source, pick a club, start
the session.

Why this exists
---------------
GSPro ingestion (src/gspro/, a port of bpgpitt10/SimRead) opens SPS to people
who have never owned a Nova. Selecting that source used to require setting an
``SPS_SHOT_SOURCE`` environment variable, which is not a thing you can ask a
sim-golf user to do. This screen is where the choice is actually made, and it
persists through src.gspro.settings so it is made only once.

Behaviour:
  * Shown before the main window on first run, or whenever the user reopens it
    from the tools menu.
  * Choosing GSPro reports live whether GSPro.db was actually found — an
    honest "not found" with the searched path beats a green light that lies.
  * "Start Session" persists the choice and wakes the poller supervisor, so
    no restart is needed.

Rendering uses the APPROVED desktop palette (navy/teal/gold — src/ui/tokens.py),
matching the redesigned desktop shell, not the legacy compat `theme` module's
hunter-green scheme. See DESIGN_SYSTEM.md. Brand imagery (shield/wordmark,
Nova, GSPro logos) is the same approved PNGs used elsewhere in the app.
"""

from __future__ import annotations

import math
import os
import random
import tkinter as tk

import theme
from src.gspro import settings as gspro_settings
from src.gspro.locate import locate_gspro_database_path
from src.ui import tokens

from .asset_paths import asset_path

# The two ingestion paths a user can choose between on the splash.
# GSPro first, Nova second — matches the approved mockup's left-to-right order.
SOURCE_CARDS = (
    ("gspro", "gspro_logo.png", "Play on your favorite\nGSPro courses."),
    ("nova", "nova_logo.png", "Connect to your\nNOVA launch monitor."),
)


class SplashScreen:
    """Modal shot-source picker drawn on a Tk canvas.

    Usage:
        result = SplashScreen(root).run()   # blocks until Start/close
        # result is None if the user closed the window, else a settings dict
    """

    W, H = 1100, 620

    def __init__(self, root, clubs=None, current_club="7 Iron", club_specs=None):
        self.root = root
        self.clubs = list(clubs or ["Driver", "5 Iron", "7 Iron", "9 Iron", "PW"])
        self.current_club = current_club if current_club in self.clubs else self.clubs[0]
        # Optional {club_name: {"brand":..., "model":..., "loft_deg":...}} so
        # the club row can show the user's real gear instead of a placeholder.
        self.club_specs = club_specs or {}

        settings = gspro_settings.load_settings(refresh=True)
        # Pre-select what the user already chose; "both" highlights GSPro
        # since that is the non-default half of the pairing.
        self.source = "gspro" if settings["source"] in ("gspro", "both") else "nova"
        self.source_locked = settings["source_locked"]
        self.always_show = bool(settings.get("always_show_splash", False))

        self.result = None
        self._club_menu_open = False
        self._hit_rects = []          # (x1, y1, x2, y2, action, payload)
        self._images = []             # keep PhotoImage refs alive
        self._image_cache = {}        # (path, target_h) -> PhotoImage, across redraws
        self._hero_cache = {}         # (w, h) -> PhotoImage
        self._alive = True            # False once the window is destroyed
        self._last_status_state = None

        self.win = tk.Toplevel(root)
        self.win.title("Welcome to Shanktuary")
        self.win.configure(bg=tokens.PAGE_BG)
        self.win.resizable(False, False)

        scr_w = self.win.winfo_screenwidth()
        scr_h = self.win.winfo_screenheight()
        w = min(self.W, max(880, scr_w - 80))
        h = min(self.H, max(560, scr_h - 120))
        self.w, self.h = w, h
        self.win.geometry(
            f"{w}x{h}+{max(0, (scr_w - w) // 2)}+{max(0, (scr_h - h) // 3)}"
        )

        self.canvas = tk.Canvas(
            self.win, width=w, height=h, bg=tokens.PAGE_BG, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_click)

        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Only make the splash transient for a master that is actually on
        # screen. A transient child of a WITHDRAWN root is never mapped by
        # the window manager: the window is 1x1 and invisible, yet grab_set
        # and wait_window still succeed, so the app hangs on a splash nobody
        # can see. Reopened from the Tools menu the main window IS visible,
        # and transient is the correct behaviour there.
        try:
            master_visible = bool(root.winfo_viewable())
        except Exception:
            master_visible = False
        if master_visible:
            self.win.transient(root)

        self.win.update_idletasks()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

        # A grab on an unmapped window locks the app out of its own UI, so
        # only take one once the window is really on screen.
        try:
            if self.win.winfo_viewable():
                self.win.grab_set()
        except tk.TclError:
            pass

        self._draw()
        # Live status while the user reads this screen: Nova connects about
        # half a second after launch, so a static card would say "searching"
        # for the entire session.
        self._last_status_state = (self._nova_state(), self._gspro_state()[0])
        self.win.after(500, self._poll_status)

    # -- helpers ---------------------------------------------------------
    def _rounded(self, x1, y1, x2, y2, r, fill, outline="", width=1):
        """Filled rounded rectangle (Tk has no native primitive)."""
        r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        ids = [
            self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=""),
            self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=""),
        ]
        for cx, cy in ((x1, y1), (x2 - 2 * r, y1), (x1, y2 - 2 * r), (x2 - 2 * r, y2 - 2 * r)):
            ids.append(
                self.canvas.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, fill=fill, outline="")
            )
        if outline:
            ids.append(
                self.canvas.create_line(
                    x1 + r, y1, x2 - r, y1, fill=outline, width=width
                )
            )
            ids.append(
                self.canvas.create_line(
                    x1 + r, y2, x2 - r, y2, fill=outline, width=width
                )
            )
            ids.append(
                self.canvas.create_line(
                    x1, y1 + r, x1, y2 - r, fill=outline, width=width
                )
            )
            ids.append(
                self.canvas.create_line(
                    x2, y1 + r, x2, y2 - r, fill=outline, width=width
                )
            )
            for cx, cy, start in (
                (x1, y1, 90), (x2 - 2 * r, y1, 0),
                (x1, y2 - 2 * r, 180), (x2 - 2 * r, y2 - 2 * r, 270),
            ):
                ids.append(
                    self.canvas.create_arc(
                        cx, cy, cx + 2 * r, cy + 2 * r, start=start, extent=90,
                        style="arc", outline=outline, width=width,
                    )
                )
        return ids

    def _hit(self, rect, action, payload=None):
        self._hit_rects.append((rect[0], rect[1], rect[2], rect[3], action, payload))

    def _load_image(self, attr_key, path, target_h):
        """Load and scale a transparent PNG once per (path, height); cache across redraws."""
        key = (path, int(target_h))
        cached = self._image_cache.get(key)
        if cached is not None:
            self._images.append(cached)
            return cached
        try:
            from PIL import Image, ImageTk

            im = Image.open(path).convert("RGBA")
            ratio = target_h / max(1, im.height)
            target_w = max(1, round(im.width * ratio))
            im = im.resize((target_w, int(target_h)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(im)
        except Exception:
            photo = None
        self._image_cache[key] = photo
        if photo is not None:
            self._images.append(photo)
        return photo

    def _club_subtitle(self, club):
        """Brand/model/loft line for a club, or "" when unknown.

        Only reports what the bag actually stores — an unspecced club shows
        nothing rather than an invented model name.
        """
        spec = self.club_specs.get(club) or {}
        if not isinstance(spec, dict):
            return ""
        parts = []
        gear = " ".join(
            str(spec.get(k, "")).strip() for k in ("brand", "model")
        ).strip()
        if gear:
            parts.append(gear)
        try:
            loft = float(spec.get("loft_deg") or 0)
            if loft > 0:
                parts.append(f"{loft:g}°")
        except (TypeError, ValueError):
            pass
        return "  ·  ".join(parts)

    def _gspro_state(self):
        """(found, path) for the GSPro database, honestly reported."""
        settings = gspro_settings.load_settings(refresh=True)
        path = settings["db_path"] or locate_gspro_database_path()
        return os.path.isfile(path), path

    def _nova_state(self):
        """(connected, host) for the Nova link, or (False, "") if unknown.

        Imported lazily so the splash stays importable without the studio
        module (the renderers and tests build it standalone).
        """
        try:
            import shanktuary_performance_studio as studio

            return (bool(studio.nova_status.get("connected")),
                    str(studio.nova_status.get("host") or ""))
        except Exception:
            return False, ""

    def _poll_status(self):
        """Repaint while the splash is open so status lines go live.

        Nova connects ~0.5s after launch — typically while the user is still
        reading this screen. Without polling the card would say "searching"
        for the whole session and the user would think their monitor was
        broken.
        """
        if not self._alive:
            return
        try:
            state = (self._nova_state(), self._gspro_state()[0])
            if state != self._last_status_state:
                self._last_status_state = state
                self._draw()
            self.win.after(500, self._poll_status)
        except tk.TclError:
            self._alive = False

    # -- hero composite (left panel background art) ----------------------
    def _hero_image(self, w, h):
        """Dark navy panel: topo-contour texture + club-and-ball composite.

        Built once per panel size with PIL, then cached as a PhotoImage.
        Uses the approved flat iron_side.png cutout (no photoshoot asset
        exists in the repo) composited with a procedural ball and a soft
        vignette so it reads as one coherent hero image, not a sticker.
        """
        key = (int(w), int(h))
        cached = self._hero_cache.get(key)
        if cached is not None:
            self._images.append(cached)
            return cached

        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageTk

            def rgb(hexcol):
                hexcol = hexcol.lstrip("#")
                return tuple(int(hexcol[i:i + 2], 16) for i in (0, 2, 4))

            teal_line = rgb(tokens.TEAL_LINE)

            iw, ih = max(1, int(w)), max(1, int(h))
            img = Image.new("RGB", (iw, ih), rgb(tokens.RAIL_BG))
            px = img.load()
            top = rgb("#122F3A")
            bottom = rgb("#0A1E27")
            for y in range(ih):
                ty = y / max(1, ih - 1)
                row = tuple(round(top[i] + (bottom[i] - top[i]) * ty) for i in range(3))
                for x in range(iw):
                    px[x, y] = row

            d = ImageDraw.Draw(img, "RGBA")

            def terrain(x):
                broad = (ih * 0.065) * math.sin(x / 260.0 * math.tau + .4)
                mid = (ih * 0.029) * math.sin(x / 120.0 * math.tau + 1.3)
                fine = (ih * 0.011) * math.sin(x / 55.0 * math.tau + 2.1)
                return broad + mid + fine

            spacing = max(18, ih // 18)
            bands = max(6, ih // spacing + 4)
            for band in range(-2, bands):
                base_y = band * spacing
                scale = .9 + band * .01
                pts = [(x, base_y + terrain(x) * scale) for x in range(-20, iw + 21, 8)]
                alpha = 30 if band % 3 else 42
                d.line(pts, fill=(teal_line[0], teal_line[1], teal_line[2], alpha), width=1)

            # Club + ball composite, from the approved flat product cutout.
            iron_path = asset_path("iron_side.png")
            if os.path.isfile(iron_path):
                iron = Image.open(iron_path).convert("RGBA")
                target_h = int(ih * 0.46)
                ratio = target_h / max(1, iron.height)
                iron = iron.resize(
                    (max(1, round(iron.width * ratio)), target_h),
                    Image.Resampling.LANCZOS,
                )
                iron = iron.rotate(-18, expand=True, resample=Image.Resampling.BICUBIC)

                ball_d = max(8, int(ih * 0.15))
                ball = self._build_ball(ball_d)

                ball_x = int(iw * 0.30)
                ball_y = int(ih * 0.60)

                iron_bbox = iron.getbbox() or (0, 0, iron.width, iron.height)
                club_x = ball_x - int(iron.width * 0.18)
                club_y = ball_y - iron_bbox[3] + int(ball_d * 0.42)
                img.paste(iron, (club_x, club_y), iron)

                shadow = Image.new("RGBA", (ball_d * 2, int(ball_d * 0.6)), (0, 0, 0, 0))
                sd = ImageDraw.Draw(shadow)
                sd.ellipse((0, 0, ball_d * 2, int(ball_d * 0.6)), fill=(0, 0, 0, 90))
                shadow = shadow.filter(ImageFilter.GaussianBlur(6))
                img.paste(
                    shadow,
                    (ball_x - ball_d // 2, ball_y + ball_d - int(ball_d * 0.25)),
                    shadow,
                )
                img.paste(ball, (ball_x, ball_y), ball)

            # Soft vignette — corners recede without crushing the panel.
            vign = Image.new("L", (iw, ih), 200)
            vd = ImageDraw.Draw(vign)
            vd.ellipse((-iw * 0.35, -ih * 0.25, iw * 1.35, ih * 1.35), fill=255)
            vign = vign.filter(ImageFilter.GaussianBlur(max(60, ih // 4)))
            dark = Image.new("RGB", (iw, ih), rgb("#050F15"))
            img = Image.composite(img, dark, vign)

            photo = ImageTk.PhotoImage(img)
        except Exception:
            photo = None

        self._hero_cache[key] = photo
        if photo is not None:
            self._images.append(photo)
        return photo

    @staticmethod
    def _build_ball(diameter):
        """A simple lit/dimpled sphere — no photo asset exists for this."""
        from PIL import Image, ImageDraw

        im = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        px = im.load()
        r = diameter / 2
        cx, cy = r, r
        lx, ly = r * 0.60, r * 0.50
        for y in range(diameter):
            for x in range(diameter):
                dx, dy = x - cx, y - cy
                dist = math.hypot(dx, dy)
                if dist > r:
                    continue
                ldx, ldy = x - lx, y - ly
                ldist = math.hypot(ldx, ldy)
                light = max(0.0, 1.0 - ldist / (r * 1.1))
                base = 175 + int(80 * light)
                edge_fade = 1.0 - (dist / r) ** 4 * 0.20
                val = max(100, min(255, int(base * edge_fade)))
                a = 255
                if dist > r - 1.2:
                    a = int(255 * (r - dist))
                px[x, y] = (val, val, val, a)
        d = ImageDraw.Draw(im, "RGBA")
        rnd = random.Random(7)
        for _ in range(max(60, int(diameter * diameter * 0.02))):
            ang = rnd.uniform(0, math.tau)
            rad = rnd.uniform(0, r * 0.94)
            x = cx + rad * math.cos(ang)
            y = cy + rad * math.sin(ang)
            if 0 <= x < diameter and 0 <= y < diameter:
                d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(60, 60, 60, 55))
        return im

    # -- painting --------------------------------------------------------
    def _draw(self):
        self.canvas.delete("all")
        self._hit_rects = []
        self._images = []

        # Paint the page background explicitly rather than relying on the
        # canvas's own bg, which some X/Wayland setups leave unpainted.
        self.canvas.create_rectangle(0, 0, self.w, self.h, fill=tokens.PAGE_BG, outline="")

        split = int(self.w * 0.42)
        self._draw_left(split)
        self._draw_right(split)

    def _draw_left(self, split):
        c = self.canvas

        hero = self._hero_image(split, self.h)
        if hero is not None:
            c.create_image(0, 0, image=hero, anchor="nw")
        else:
            c.create_rectangle(0, 0, split, self.h, fill=tokens.RAIL_BG, outline="")
        c.create_line(split, 0, split, self.h, fill=tokens.HAIRLINE)

        # Brand: the square shield scales cleanly as an icon, with the
        # wordmark set in live text (gold, per the approved brand direction).
        y = 40
        text_x = 40
        shield = self._load_image("shield", asset_path("shanktuary_shield.png"), 40)
        if shield is not None:
            c.create_image(40, y, image=shield, anchor="nw")
            text_x = 40 + 40 + 12

        c.create_text(text_x, y + 2, text="SHANKTUARY", fill=tokens.GOLD,
                      font=(theme.ui_font(), 18, "bold"), anchor="nw")
        c.create_text(text_x + 1, y + 26, text="P E R F O R M A N C E   G O L F   S T U D I O",
                      fill=tokens.TEAL_TEXT, font=(theme.ui_font(), 7), anchor="nw")
        y += 92

        c.create_text(40, y, text="W E L C O M E   T O", fill=tokens.TEAL_TEXT,
                      font=(theme.ui_font(), 10), anchor="nw")
        y += 28
        c.create_text(38, y, text="YOUR", fill=tokens.TEXT,
                      font=(theme.ui_font(), 34, "bold"), anchor="nw")
        y += 44
        c.create_text(38, y, text="SHANKTUARY.", fill=tokens.TEXT,
                      font=(theme.ui_font(), 34, "bold"), anchor="nw")
        y += 56

        c.create_line(40, y, 96, y, fill=tokens.GOLD, width=2)
        y += 22
        c.create_text(40, y, text="Connect. Choose. Play.", fill=tokens.TEXT,
                      font=(theme.ui_font(), 12, "bold"), anchor="nw")
        y += 22
        c.create_text(40, y, text="Let's get you ready to play your best.",
                      fill=tokens.TEXT_2, font=(theme.ui_font(), 10), anchor="nw")

        c.create_text(40, self.h - 32, text="\u201c  I N   P U R S U I T   O F   P U R E .",
                      fill=tokens.TEAL_SOFT, font=(theme.ui_font(), 9), anchor="nw")

    def _step_label(self, x, y, number, text):
        c = self.canvas
        c.create_oval(x, y, x + 20, y + 20, outline=tokens.HAIRLINE, width=1)
        c.create_text(x + 10, y + 10, text=str(number), fill=tokens.TEXT_2,
                      font=(theme.ui_font(), 9), anchor="center")
        c.create_text(x + 32, y + 10, text=text, fill=tokens.TEXT_2,
                      font=(theme.ui_font(), 9), anchor="w")
        return y + 34

    def _draw_right(self, split):
        c = self.canvas
        c.create_rectangle(split, 0, self.w, self.h, fill=tokens.PAGE_BG, outline="")
        x = split + 44
        right = self.w - 44
        y = 40

        # Caption only — no "STEP 1 OF 3" counter or progress dots.
        # All three numbered steps live on THIS screen, so a wizard counter
        # promised two more screens that never existed. The numbered circles
        # below carry the sequence on their own. (The approved mockup shows
        # both, which is an inconsistency in the mockup itself.)
        c.create_text((x + right) // 2, y + 8, text="S E S S I O N   S E T U P",
                      fill=tokens.TEXT_3, font=(theme.ui_font(), 8), anchor="center")
        y += 34

        # ---- Step 1: shot source -------------------------------------
        y = self._step_label(x, y, 1, "C O N N E C T   T O")
        card_h = 132
        gap = 16
        card_w = (right - x - gap) // 2
        gspro_found, gspro_path = self._gspro_state()

        for i, (key, logo_name, blurb) in enumerate(SOURCE_CARDS):
            cx1 = x + i * (card_w + gap)
            cx2 = cx1 + card_w
            selected = self.source == key
            # Gold = current/active, per DESIGN_SYSTEM.md — one selection
            # rule for both cards rather than a per-brand accent colour.
            self._rounded(
                cx1, y, cx2, y + card_h, 10,
                fill=tokens.ACTIVE_BG if selected else tokens.SURFACE,
                outline=tokens.GOLD if selected else tokens.HAIRLINE,
            )
            # Radio indicator
            rx = cx2 - 26
            c.create_oval(rx - 8, y + 14, rx + 8, y + 30,
                          outline=tokens.GOLD if selected else tokens.HAIRLINE, width=1)
            if selected:
                c.create_oval(rx - 4, y + 18, rx + 4, y + 26,
                              fill=tokens.GOLD, outline="")

            logo = self._load_image(key, asset_path(logo_name), 30)
            if logo is not None:
                c.create_image((cx1 + cx2) // 2, y + 46, image=logo, anchor="center")
            else:
                c.create_text((cx1 + cx2) // 2, y + 46, text=key.upper(),
                              fill=tokens.TEXT if selected else tokens.TEXT_2,
                              font=(theme.ui_font(), 20, "bold"), anchor="center")
            c.create_text((cx1 + cx2) // 2, y + 84, text=blurb, fill=tokens.TEXT_3,
                          font=(theme.ui_font(), 9), anchor="center", justify="center")

            # Live availability line — the same honesty for both sources:
            # say what is actually true right now, never a hopeful default.
            if key == "gspro":
                if gspro_found:
                    note, col = "database found", tokens.TEAL_TEXT
                else:
                    note, col = "database not found", theme.WARN
            else:
                nova_up, nova_host = self._nova_state()
                if nova_up:
                    note, col = f"connected · {nova_host}", tokens.TEAL_TEXT
                else:
                    note, col = "searching…", tokens.TEXT_3
            c.create_text((cx1 + cx2) // 2, y + card_h - 16, text=note,
                          fill=col, font=(theme.ui_font(), 8), anchor="center")

            if not self.source_locked:
                self._hit((cx1, y, cx2, y + card_h), "source", key)

        y += card_h + 10

        if self.source_locked:
            c.create_text(x, y, text="Source is fixed by the SPS_SHOT_SOURCE environment variable.",
                          fill=theme.WARN, font=(theme.ui_font(), 8), anchor="nw")
            y += 18

        if self.source == "gspro" and not gspro_found:
            c.create_text(x, y, text=f"Looked in: {gspro_path}", fill=tokens.TEXT_3,
                          font=(theme.ui_font(), 8), anchor="nw")
            y += 16
            c.create_text(x, y, text="Set SPS_GSPRO_DB to point at your GSPro.db if it lives elsewhere.",
                          fill=tokens.TEXT_3, font=(theme.ui_font(), 8), anchor="nw")
            y += 16
        y += 12

        # ---- Step 2: club --------------------------------------------
        y = self._step_label(x, y, 2, "S E L E C T   C L U B")
        sel_h = 58
        self._rounded(x, y, right, y + sel_h, 10, fill=tokens.SURFACE, outline=tokens.HAIRLINE)
        # Real gear from the user's bag when we have it (the mockup's
        # "Mizuno JPX Forged" subtitle). Absent specs simply show no
        # subtitle — never a made-up club model.
        subtitle = self._club_subtitle(self.current_club)
        if subtitle:
            c.create_text(x + 20, y + 18, text=self.current_club.upper(),
                          fill=tokens.TEXT, font=(theme.ui_font(), 13, "bold"), anchor="w")
            c.create_text(x + 20, y + 39, text=subtitle, fill=tokens.TEXT_3,
                          font=(theme.ui_font(), 8), anchor="w")
        else:
            c.create_text(x + 20, y + sel_h // 2, text=self.current_club.upper(),
                          fill=tokens.TEXT, font=(theme.ui_font(), 14, "bold"), anchor="w")
        # Chevron drawn as a polygon — the unicode arrow glyph is missing
        # from several Linux UI fonts and renders as a blank box.
        chx, chy = right - 26, y + sel_h // 2
        c.create_polygon(chx - 6, chy - 3, chx + 6, chy - 3, chx, chy + 4,
                         fill=tokens.TEXT_2, outline="")
        self._hit((x, y, right, y + sel_h), "club_menu")
        club_row_y = y
        y += sel_h + 22

        # ---- Step 3: start -------------------------------------------
        y = self._step_label(x, y, 3, "Y O U ' R E   R E A D Y")
        btn_h = 52
        self._rounded(x, y, right, y + btn_h, 10, fill=tokens.GOLD)
        c.create_text((x + right) // 2, y + btn_h // 2, text="START SESSION",
                      fill="#0B1410", font=(theme.ui_font(), 13, "bold"), anchor="center")
        ax, ay = right - 30, y + btn_h // 2
        c.create_line(ax - 9, ay, ax + 7, ay, fill="#0B1410", width=2)
        c.create_polygon(ax + 3, ay - 5, ax + 10, ay, ax + 3, ay + 5,
                         fill="#0B1410", outline="")
        self._hit((x, y, right, y + btn_h), "start")
        y += btn_h + 18

        c.create_text((x + right) // 2, y, text="Your data is private and stays on this machine.",
                      fill=tokens.TEXT_3, font=(theme.ui_font(), 8), anchor="n")
        y += 22

        # "Show this on every launch" — the honest way to keep the setup
        # screen. Some users want to confirm their monitor is live before
        # every session; others want to get straight to hitting balls.
        box = 13
        label = "Show this screen on every launch"
        # Centre the checkbox+label as a unit. Measure the text rather than
        # guessing a pixel offset, which drifts with the resolved UI font.
        probe = c.create_text(-1000, -1000, text=label,
                              font=(theme.ui_font(), 8), anchor="w")
        bbox = c.bbox(probe)
        c.delete(probe)
        text_w = (bbox[2] - bbox[0]) if bbox else 170
        total_w = box + 9 + text_w
        bx = (x + right) // 2 - total_w // 2
        by = y
        self._rounded(bx, by, bx + box, by + box, 3,
                      fill=tokens.GOLD if self.always_show else tokens.SURFACE,
                      outline=tokens.GOLD if self.always_show else tokens.HAIRLINE)
        if self.always_show:
            # Tick, drawn as lines (glyph coverage varies by font).
            c.create_line(bx + 3, by + 7, bx + 5, by + 10, fill="#0B1410", width=2)
            c.create_line(bx + 5, by + 10, bx + 10, by + 3, fill="#0B1410", width=2)
        c.create_text(bx + box + 9, by + box // 2, text=label,
                      fill=tokens.TEXT_2, font=(theme.ui_font(), 8), anchor="w")
        self._hit((bx - 4, by - 4, bx + total_w + 4, by + box + 4), "always")

        # Club dropdown paints last so it overlays the steps below it.
        if self._club_menu_open:
            self._draw_club_menu(x, club_row_y + sel_h + 4, right)

    def _draw_club_menu(self, x, y, right):
        """Club list, laid out so EVERY club is reachable.

        A single 9-item column silently hid the wedges and putter, and was
        tall enough to flip upward over the club row. Two columns fit a full
        15-club bag below the row with nothing truncated.
        """
        c = self.canvas
        clubs = list(self.clubs)
        if not clubs:
            return

        row_h = 28
        cols = 2 if len(clubs) > 8 else 1
        rows = -(-len(clubs) // cols)          # ceil
        menu_h = row_h * rows + 8
        col_w = (right - x) // cols

        # Keep the menu on screen; only flip up if it genuinely cannot fit.
        if y + menu_h > self.h - 8:
            y = max(8, self.h - 8 - menu_h)

        self._rounded(x, y, right, y + menu_h, 8,
                      fill=tokens.SURFACE_2, outline=tokens.HAIRLINE)

        for i, club in enumerate(clubs):
            col = i // rows
            row = i % rows
            cx1 = x + col * col_w
            cx2 = cx1 + col_w
            cy = y + 4 + row * row_h

            active = club == self.current_club
            if active:
                self._rounded(cx1 + 4, cy, cx2 - 4, cy + row_h, 6,
                              fill=tokens.ACTIVE_BG)
            c.create_text(cx1 + 14, cy + row_h // 2, text=club,
                          fill=tokens.GOLD if active else tokens.TEXT_2,
                          font=(theme.ui_font(), 9), anchor="w")
            sub = self._club_subtitle(club)
            if sub:
                # Loft alone in two-column mode — the full brand/model line
                # does not fit in half the width without colliding.
                short = sub.split("·")[-1].strip() if cols > 1 else sub
                c.create_text(cx2 - 12, cy + row_h // 2, text=short,
                              fill=tokens.TEXT_3, font=(theme.ui_font(), 8),
                              anchor="e")
            self._hit((cx1, cy, cx2, cy + row_h), "club", club)

    # -- interaction -----------------------------------------------------
    def _on_click(self, event):
        # Later rects paint on top, so hit-test in reverse registration order.
        for x1, y1, x2, y2, action, payload in reversed(self._hit_rects):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if action == "source":
                    self.source = payload
                    self._club_menu_open = False
                elif action == "club_menu":
                    self._club_menu_open = not self._club_menu_open
                elif action == "always":
                    self.always_show = not self.always_show
                    self._club_menu_open = False
                elif action == "club":
                    self.current_club = payload
                    self._club_menu_open = False
                elif action == "start":
                    self._start()
                    return
                self._draw()
                return
        # A click on empty space closes the dropdown.
        if self._club_menu_open:
            self._club_menu_open = False
            self._draw()

    def _start(self):
        self.result = {
            "source": self.source,
            "club": self.current_club,
            "always_show": self.always_show,
        }
        gspro_settings.save_settings(
            source=None if self.source_locked else self.source,
            onboarded=True,
            always_show_splash=self.always_show,
        )
        self._close()

    def _on_close(self):
        self.result = None
        self._close()

    def _close(self):
        self._alive = False          # stop the status poller
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass

    def run(self):
        """Block until the splash closes; returns the chosen settings or None.

        If the window never became viewable (no WM, odd remote display), do
        not wait on it — a hidden modal that blocks forever looks exactly
        like the app failing to launch. Fall through with defaults instead.
        """
        try:
            if not self.win.winfo_exists():
                return None
            if not self.win.winfo_viewable():
                self.win.update()
            if not self.win.winfo_viewable():
                print("[splash] window could not be displayed; continuing without it")
                self._close()
                return None
        except tk.TclError:
            return None

        self.root.wait_window(self.win)
        return self.result


def should_show_splash():
    """True when the setup splash should open on launch.

    Shown when the user has not onboarded yet, or when they ticked "Show
    this screen on every launch" (useful for confirming the launch monitor
    is live before a session). ``SPS_SKIP_SPLASH=1`` overrides both.
    """
    if os.environ.get("SPS_SKIP_SPLASH", "").strip() in ("1", "true", "yes"):
        return False
    settings = gspro_settings.load_settings(refresh=True)
    return (not settings["onboarded"]) or settings.get("always_show_splash", False)
