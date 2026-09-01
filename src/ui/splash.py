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

Rendering is plain Tk canvas drawing on the shipped `theme` palette, matching
the rest of the desktop; the design's gold CTA is rendered in the app's
established hunter-green accent so the splash does not introduce a second
brand colour.
"""

from __future__ import annotations

import os
import tkinter as tk

import theme
from src.gspro import settings as gspro_settings
from src.gspro.locate import locate_gspro_database_path

from .asset_paths import asset_path

# The two ingestion paths a user can choose between on the splash.
SOURCE_CARDS = (
    ("gspro", "GSPro", "Play on your favorite\nGSPro courses."),
    ("nova", "NOVA", "Connect to your\nNOVA launch monitor."),
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

        self.result = None
        self._club_menu_open = False
        self._hit_rects = []          # (x1, y1, x2, y2, action, payload)
        self._images = []             # keep PhotoImage refs alive

        self.win = tk.Toplevel(root)
        self.win.title("Welcome to Shanktuary")
        self.win.configure(bg=theme.BG)
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
            self.win, width=w, height=h, bg=theme.BG, highlightthickness=0
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

    # -- painting --------------------------------------------------------
    def _draw(self):
        self.canvas.delete("all")
        self._hit_rects = []
        self._images = []

        # Paint the page background explicitly rather than relying on the
        # canvas's own bg, which some X/Wayland setups leave unpainted.
        self.canvas.create_rectangle(0, 0, self.w, self.h, fill=theme.BG, outline="")

        split = int(self.w * 0.42)
        self._draw_left(split)
        self._draw_right(split)

    def _draw_left(self, split):
        c = self.canvas
        c.create_rectangle(0, 0, split, self.h, fill=theme.RAIL, outline="")
        c.create_line(split, 0, split, self.h, fill=theme.HAIRLINE)

        # Brand: the square shield scales cleanly as an icon, with the
        # wordmark set in live text. The full lockup PNG is 610px wide and
        # its tagline turns to mush when squeezed into this panel, so it is
        # deliberately not used here.
        y = 46
        text_x = 40
        try:
            from PIL import Image, ImageTk

            img = Image.open(asset_path("shanktuary_shield.png")).convert("RGBA")
            size = 64
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            img = img.resize((size, size), resample)
            photo = ImageTk.PhotoImage(img)
            self._images.append(photo)
            c.create_image(40, y, image=photo, anchor="nw")
            text_x = 40 + size + 16
        except Exception:
            pass

        c.create_text(text_x, y + 8, text="SHANKTUARY", fill=theme.ACCENT_TEXT,
                      font=(theme.ui_font(), 19, "bold"), anchor="nw")
        c.create_text(text_x + 2, y + 40, text="P E R F O R M A N C E   S T U D I O",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 7), anchor="nw")
        y += 108

        c.create_text(40, y, text="W E L C O M E   T O", fill=theme.ACCENT_TEXT,
                      font=(theme.ui_font(), 10), anchor="nw")
        y += 28
        c.create_text(38, y, text="YOUR", fill=theme.TEXT,
                      font=(theme.ui_font(), 34, "bold"), anchor="nw")
        y += 44
        c.create_text(38, y, text="SHANKTUARY.", fill=theme.TEXT,
                      font=(theme.ui_font(), 34, "bold"), anchor="nw")
        y += 62

        c.create_line(40, y, 96, y, fill=theme.ACCENT_LINE, width=2)
        y += 24
        c.create_text(40, y, text="Connect. Choose. Play.", fill=theme.TEXT,
                      font=(theme.ui_font(), 12, "bold"), anchor="nw")
        y += 24
        c.create_text(40, y, text="Let's get you ready to play your best.",
                      fill=theme.TEXT_2, font=(theme.ui_font(), 10), anchor="nw")

        c.create_text(40, self.h - 44, text="\u201c  I N   P U R S U I T   O F   P U R E .",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 9), anchor="nw")

    def _step_label(self, x, y, number, text):
        c = self.canvas
        c.create_oval(x, y, x + 20, y + 20, outline=theme.HAIRLINE, width=1)
        c.create_text(x + 10, y + 10, text=str(number), fill=theme.TEXT_2,
                      font=(theme.ui_font(), 9), anchor="center")
        c.create_text(x + 32, y + 10, text=text, fill=theme.TEXT_2,
                      font=(theme.ui_font(), 9), anchor="w")
        return y + 34

    def _draw_right(self, split):
        c = self.canvas
        x = split + 44
        right = self.w - 44
        y = 40

        # Caption only — no "STEP 1 OF 3" counter or progress dots.
        # All three numbered steps live on THIS screen, so a wizard counter
        # promised two more screens that never existed. The numbered circles
        # below carry the sequence on their own. (The approved mockup shows
        # both, which is an inconsistency in the mockup itself.)
        c.create_text((x + right) // 2, y + 8, text="S E S S I O N   S E T U P",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="center")
        y += 34

        # ---- Step 1: shot source -------------------------------------
        y = self._step_label(x, y, 1, "C O N N E C T   T O")
        card_h = 132
        gap = 16
        card_w = (right - x - gap) // 2
        gspro_found, gspro_path = self._gspro_state()

        for i, (key, title, blurb) in enumerate(SOURCE_CARDS):
            cx1 = x + i * (card_w + gap)
            cx2 = cx1 + card_w
            selected = self.source == key
            self._rounded(
                cx1, y, cx2, y + card_h, 10,
                fill=theme.ACCENT_DEEP if selected else theme.SURFACE,
                outline=theme.ACCENT_LINE if selected else theme.HAIRLINE,
            )
            # Radio indicator
            rx = cx2 - 26
            c.create_oval(rx - 8, y + 14, rx + 8, y + 30,
                          outline=theme.ACCENT_LINE if selected else theme.HAIRLINE, width=1)
            if selected:
                c.create_oval(rx - 4, y + 18, rx + 4, y + 26,
                              fill=theme.ACCENT_LINE, outline="")

            c.create_text((cx1 + cx2) // 2, y + 46, text=title,
                          fill=theme.TEXT if selected else theme.TEXT_2,
                          font=(theme.ui_font(), 20, "bold"), anchor="center")
            c.create_text((cx1 + cx2) // 2, y + 84, text=blurb, fill=theme.TEXT_3,
                          font=(theme.ui_font(), 9), anchor="center", justify="center")

            # Honest availability line for GSPro: found or not, with no bluffing.
            if key == "gspro":
                if gspro_found:
                    note, col = "database found", theme.ACCENT_TEXT
                else:
                    note, col = "database not found", theme.WARN
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
            c.create_text(x, y, text=f"Looked in: {gspro_path}", fill=theme.TEXT_3,
                          font=(theme.ui_font(), 8), anchor="nw")
            y += 16
            c.create_text(x, y, text="Set SPS_GSPRO_DB to point at your GSPro.db if it lives elsewhere.",
                          fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="nw")
            y += 16
        y += 12

        # ---- Step 2: club --------------------------------------------
        y = self._step_label(x, y, 2, "S E L E C T   C L U B")
        sel_h = 58
        self._rounded(x, y, right, y + sel_h, 10, fill=theme.SURFACE, outline=theme.HAIRLINE)
        # Real gear from the user's bag when we have it (the mockup's
        # "Mizuno JPX Forged" subtitle). Absent specs simply show no
        # subtitle — never a made-up club model.
        subtitle = self._club_subtitle(self.current_club)
        if subtitle:
            c.create_text(x + 20, y + 18, text=self.current_club.upper(),
                          fill=theme.TEXT, font=(theme.ui_font(), 13, "bold"), anchor="w")
            c.create_text(x + 20, y + 39, text=subtitle, fill=theme.TEXT_3,
                          font=(theme.ui_font(), 8), anchor="w")
        else:
            c.create_text(x + 20, y + sel_h // 2, text=self.current_club.upper(),
                          fill=theme.TEXT, font=(theme.ui_font(), 14, "bold"), anchor="w")
        # Chevron drawn as a polygon — the unicode arrow glyph is missing
        # from several Linux UI fonts and renders as a blank box.
        chx, chy = right - 26, y + sel_h // 2
        c.create_polygon(chx - 6, chy - 3, chx + 6, chy - 3, chx, chy + 4,
                         fill=theme.TEXT_2, outline="")
        self._hit((x, y, right, y + sel_h), "club_menu")
        club_row_y = y
        y += sel_h + 22

        # ---- Step 3: start -------------------------------------------
        y = self._step_label(x, y, 3, "Y O U ' R E   R E A D Y")
        btn_h = 52
        self._rounded(x, y, right, y + btn_h, 10, fill=theme.ACCENT)
        c.create_text((x + right) // 2, y + btn_h // 2, text="START SESSION",
                      fill="#0B1410", font=(theme.ui_font(), 13, "bold"), anchor="center")
        ax, ay = right - 30, y + btn_h // 2
        c.create_line(ax - 9, ay, ax + 7, ay, fill="#0B1410", width=2)
        c.create_polygon(ax + 3, ay - 5, ax + 10, ay, ax + 3, ay + 5,
                         fill="#0B1410", outline="")
        self._hit((x, y, right, y + btn_h), "start")
        y += btn_h + 18

        c.create_text((x + right) // 2, y, text="Your data is private and stays on this machine.",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="n")

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
                      fill=getattr(theme, "SURFACE_2", theme.SURFACE),
                      outline=theme.HAIRLINE)

        for i, club in enumerate(clubs):
            col = i // rows
            row = i % rows
            cx1 = x + col * col_w
            cx2 = cx1 + col_w
            cy = y + 4 + row * row_h

            active = club == self.current_club
            if active:
                self._rounded(cx1 + 4, cy, cx2 - 4, cy + row_h, 6,
                              fill=theme.ACCENT_DEEP)
            c.create_text(cx1 + 14, cy + row_h // 2, text=club,
                          fill=theme.ACCENT_TEXT if active else theme.TEXT_2,
                          font=(theme.ui_font(), 9), anchor="w")
            sub = self._club_subtitle(club)
            if sub:
                # Loft alone in two-column mode — the full brand/model line
                # does not fit in half the width without colliding.
                short = sub.split("·")[-1].strip() if cols > 1 else sub
                c.create_text(cx2 - 12, cy + row_h // 2, text=short,
                              fill=theme.TEXT_3, font=(theme.ui_font(), 8),
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
        }
        if not self.source_locked:
            gspro_settings.save_settings(source=self.source, onboarded=True)
        else:
            gspro_settings.save_settings(onboarded=True)
        self._close()

    def _on_close(self):
        self.result = None
        self._close()

    def _close(self):
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
    """True when the user has not yet completed source onboarding.

    ``SPS_SKIP_SPLASH=1`` suppresses it (CI packaging smoke runs, and users
    who never want it).
    """
    if os.environ.get("SPS_SKIP_SPLASH", "").strip() in ("1", "true", "yes"):
        return False
    return not gspro_settings.load_settings(refresh=True)["onboarded"]
