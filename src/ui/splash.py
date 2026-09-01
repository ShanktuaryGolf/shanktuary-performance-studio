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

    def __init__(self, root, clubs=None, current_club="7 Iron"):
        self.root = root
        self.clubs = list(clubs or ["Driver", "5 Iron", "7 Iron", "9 Iron", "PW"])
        self.current_club = current_club if current_club in self.clubs else self.clubs[0]

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
        self.win.transient(root)
        self.win.grab_set()

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

        c.create_text(text_x, y + 14, text="SHANKTUARY", fill=theme.ACCENT_TEXT,
                      font=(theme.ui_font(), 19, "bold"), anchor="nw")
        c.create_text(text_x + 2, y + 42, text="P E R F O R M A N C E   S T U D I O",
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

        # Progress dots — three steps, all visible on one screen.
        c.create_text((x + right) // 2, y, text="S T E P   1   O F   3",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="center")
        y += 20
        dot_cx = (x + right) // 2
        for i, dx in enumerate((-60, 0, 60)):
            fill = theme.ACCENT_LINE if i == 0 else theme.HAIRLINE
            c.create_oval(dot_cx + dx - 4, y - 4, dot_cx + dx + 4, y + 4,
                          fill=fill, outline="")
        c.create_line(dot_cx - 56, y, dot_cx + 56, y, fill=theme.HAIRLINE)
        for i, dx in enumerate((-60, 0, 60)):
            fill = theme.ACCENT_LINE if i == 0 else theme.HAIRLINE
            c.create_oval(dot_cx + dx - 4, y - 4, dot_cx + dx + 4, y + 4,
                          fill=fill, outline="")
        y += 30

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
        c = self.canvas
        row_h = 30
        visible = self.clubs[:9]
        menu_h = row_h * len(visible) + 8
        # Flip upward if the list would run off the bottom edge.
        if y + menu_h > self.h - 8:
            y = max(8, self.h - 8 - menu_h)
        self._rounded(x, y, right, y + menu_h, 8, fill=theme.SURFACE_2 if hasattr(theme, "SURFACE_2") else theme.SURFACE,
                      outline=theme.HAIRLINE)
        cy = y + 4
        for club in visible:
            active = club == self.current_club
            if active:
                self._rounded(x + 4, cy, right - 4, cy + row_h, 6, fill=theme.ACCENT_DEEP)
            c.create_text(x + 18, cy + row_h // 2, text=club,
                          fill=theme.ACCENT_TEXT if active else theme.TEXT_2,
                          font=(theme.ui_font(), 10), anchor="w")
            self._hit((x, cy, right, cy + row_h), "club", club)
            cy += row_h

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
        """Block until the splash closes; returns the chosen settings or None."""
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
