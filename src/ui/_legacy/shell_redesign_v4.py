"""Polished shell treatment for the Overview v4 design sandbox."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageOps, ImageTk

import shell_redesign as v3
import theme

BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")

_FONT = None


def _font():
    global _FONT
    if _FONT is not None:
        return _FONT
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families())
        for cand in (
            "Avenir Next", "Inter", "SF Pro Text", "SF Pro Display",
            "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial",
        ):
            if cand in fams:
                _FONT = cand
                return cand
    except Exception:
        pass
    _FONT = theme.ui_font()
    return _FONT


def _mix(a, b, t):
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.RAIL


SHELL_BG = _mix(theme.RAIL, theme.BG, .42)
SIDEBAR_BG = _mix(theme.BG, "#11233B", .055)
SELECTED = _mix(theme.SURFACE_2, BLUE, .11)
ROW = _mix(theme.SURFACE, theme.BG, .24)
ROW_MUTED = _mix(theme.TEXT_3, theme.BG, .32)
SOFT_LINE = _mix(theme.HAIRLINE, theme.BG, .46)


def _sidebar_material(app, x0, y0, x1, y1):
    """Tiny amount of matte grain so the shell has texture without an image."""
    w, h = max(1, int(x1 - x0)), max(1, int(y1 - y0))
    key = (w, h)
    if getattr(app, "_sidebar_texture_key", None) != key:
        base = Image.new("RGB", (w, h), tuple(int(SIDEBAR_BG[i:i + 2], 16) for i in (1, 3, 5)))
        try:
            noise = Image.effect_noise((w, h), 14).convert("L")
            noise_col = ImageOps.colorize(noise, black="#07101A", white="#1C2C40")
            base = Image.blend(base, noise_col, .055)
        except Exception:
            pass
        draw = ImageDraw.Draw(base)
        # Restrained top-left blue illumination around the wordmark only.
        for yy in range(min(120, h)):
            t = 1 - yy / max(1, min(120, h))
            col = _mix(SIDEBAR_BG, BLUE, .026 * t)
            draw.line((0, yy, w, yy), fill=col)
        app._sidebar_texture = ImageTk.PhotoImage(base)
        app._sidebar_texture_key = key
    app.canvas.create_image(x0, y0, image=app._sidebar_texture, anchor="nw")


def paint_nav(app, h):
    c = app.canvas
    rw = theme.RAIL_W
    c.create_rectangle(0, 0, rw, h, fill=SHELL_BG, outline="")
    c.create_line(rw - 1, 0, rw - 1, h, fill=SOFT_LINE)

    # Two-tone blue mark from the accepted brand pass.
    c.create_rectangle(15, 17, 49, 51, fill="#185DE0", outline="")
    c.create_rectangle(15, 17, 49, 34, fill="#2D7BFF", outline="")
    c.create_text(32, 34, text="S", fill=theme.TEXT,
                  font=(_font(), 15, "bold"), anchor="center")

    app.mode_pill_rects = {}
    y = 88
    for mode_id, label, _tip in theme.NAV_ITEMS:
        active = app.view_mode == mode_id
        app.mode_pill_rects[mode_id] = (5, y, rw - 5, y + 48)
        if active:
            c.create_rectangle(6, y, rw - 6, y + 48, fill=SELECTED, outline="")
            c.create_rectangle(6, y, 9, y + 48, fill=BLUE, outline="")
        col = theme.TEXT if active else theme.TEXT_3
        icon_col = BLUE_LINE if active else _mix(theme.TEXT_3, theme.TEXT_2, .32)
        v3._draw_nav_icon(c, label, 32, y + 17, icon_col)
        nav_label = "Dispersion" if label == "Disp" else ("Numbers" if label == "Nums" else label)
        c.create_text(32, y + 39, text=nav_label, fill=col,
                      font=(_font(), 7, "bold" if active else "normal"), anchor="center")
        y += theme.NAV_ITEM_H

    sy0 = h - 72
    active = app.view_mode == 10
    app.nav_setup_rect = (5, sy0, rw - 5, h - 20)
    if active:
        c.create_rectangle(6, sy0, rw - 6, h - 20, fill=SELECTED, outline="")
        c.create_rectangle(6, sy0, 9, h - 20, fill=BLUE, outline="")
    col = theme.TEXT if active else theme.TEXT_3
    for dy, knob in ((0, -3), (6, 4), (12, 0)):
        c.create_line(22, sy0 + 12 + dy, 42, sy0 + 12 + dy, fill=col, width=1)
        c.create_oval(32 + knob - 2, sy0 + 10 + dy, 32 + knob + 2, sy0 + 14 + dy,
                      fill=col, outline="")
    c.create_text(32, h - 29, text="Setup", fill=col, font=(_font(), 7), anchor="center")


def _filtered_shots(app):
    """Return (real index, shot) pairs without relying on production helper quirks."""
    pairs = list(enumerate(app.session_shots))
    cf = str(getattr(app, "club_filter", "ALL") or "ALL")
    if cf != "ALL":
        pairs = [(i, s) for i, s in pairs if str(s.get("club") or "") == cf]
    pairs.reverse()
    return pairs


def paint_sidebar(app, w, h):
    if app.sidebar_collapsed:
        return

    c = app.canvas
    x0 = theme.RAIL_W
    x1 = app.sidebar_width
    _sidebar_material(app, x0, 0, x1, h)
    c.create_line(x1 - 1, 0, x1 - 1, h, fill=SOFT_LINE)

    # Wordmark is intentionally allowed to stay uppercase as brand typography;
    # the rest of the UI moves away from all-caps labels.
    c.create_text(x0 + 18, 19, text="SHANKTUARY", fill=theme.TEXT,
                  font=(_font(), 14, "bold"), anchor="nw")
    c.create_text(x0 + 18, 43, text="PERFORMANCE GOLF", fill=BLUE_TEXT,
                  font=(_font(), 7, "bold"), anchor="nw")

    # Replace the production collapse oddity with a conventional chevron.
    tr = getattr(app, "sidebar_toggle_rect", None)
    if tr:
        cx, cy = (tr[0] + tr[2]) / 2, (tr[1] + tr[3]) / 2
        c.create_line(cx - 4, cy - 7, cx + 3, cy, cx - 4, cy + 7,
                      fill=theme.TEXT_3, width=2)

    # Session + new session strip.
    sr = getattr(app, "sidebar_session_btn_rect", None)
    nr = getattr(app, "sidebar_new_sess_btn_rect", None)
    fr = getattr(app, "sidebar_filter_btn_rect", None)
    active_sess = app.get_active_session() if hasattr(app, "get_active_session") else {}
    sess_title = str(active_sess.get("name", "Session"))
    if len(sess_title) > 19:
        sess_title = sess_title[:17] + "…"

    control_y = 75
    if sr:
        # Paint at a stable location while keeping the production click target.
        c.create_text(x0 + 18, control_y, text=sess_title, fill=theme.TEXT_2,
                      font=(_font(), 9, "bold"), anchor="nw")
        c.create_text(x1 - 66, control_y + 1, text="⌄", fill=theme.TEXT_3,
                      font=(_font(), 10), anchor="nw")
    if nr:
        c.create_rectangle(x1 - 46, control_y - 6, x1 - 16, control_y + 24,
                           fill=BLUE, outline="")
        c.create_text(x1 - 31, control_y + 9, text="+", fill=theme.TEXT,
                      font=(_font(), 14, "bold"), anchor="center")

    filter_y = 111
    label = "All Clubs" if getattr(app, "club_filter", "ALL") == "ALL" else str(app.club_filter)
    c.create_text(x0 + 18, filter_y, text=label, fill=theme.TEXT_2,
                  font=(_font(), 9, "bold"), anchor="nw")
    if fr:
        c.create_text(x1 - 26, filter_y + 1, text="⌄", fill=theme.TEXT_3,
                      font=(_font(), 10), anchor="nw")

    c.create_line(x0 + 16, 139, x1 - 16, 139, fill=SOFT_LINE)
    c.create_text(x0 + 18, 154, text="Recent Shots", fill=theme.TEXT,
                  font=(_font(), 12, "bold"), anchor="nw")

    # Selected shot expands; everything else is compact and visually recessed.
    app.sidebar_shot_card_rects = []
    y = 184
    bottom = h - 52
    for real_idx, shot in _filtered_shots(app):
        selected = real_idx == app.selected_shot_index
        rh = 116 if selected else 52
        if y + rh > bottom:
            break

        bg = SELECTED if selected else ROW
        c.create_rectangle(x0 + 12, y, x1 - 12, y + rh, fill=bg, outline="")
        if selected:
            c.create_rectangle(x0 + 12, y, x0 + 15, y + rh, fill=BLUE, outline="")

        ogc = shot.get("open_golf_coach", {}) or {}
        us = ogc.get("us_customary_units", {}) or {}
        club = str(shot.get("club") or "—")
        carry = float(us.get("carry_distance_yards") or 0.0)
        ball = float(us.get("ball_speed_mph") or 0.0)
        shape = str(ogc.get("shot_name") or "—")
        ts = str(shot.get("timestamp") or "")

        # Number is a small circular locator, club and carry are the dominant facts.
        ncx, ncy = x0 + 35, y + 25
        c.create_oval(ncx - 13, ncy - 13, ncx + 13, ncy + 13,
                      fill=BLUE if selected else _mix(theme.SURFACE_2, theme.BG, .18),
                      outline=BLUE_LINE if selected else theme.GUIDE, width=1)
        c.create_text(ncx, ncy, text=f"{real_idx + 1}",
                      fill=theme.TEXT if selected else theme.TEXT_2,
                      font=(_font(), 8, "bold"), anchor="center")
        c.create_text(x0 + 58, y + 15, text=club,
                      fill=theme.TEXT if selected else _mix(theme.TEXT_2, theme.TEXT, .05),
                      font=(_font(), 11, "bold"), anchor="nw")
        c.create_text(x1 - 24, y + 14, text=f"{carry:.1f}",
                      fill=theme.TEXT if selected else theme.TEXT_2,
                      font=(_font(), 12, "bold"), anchor="ne")
        c.create_text(x1 - 21, y + 32, text="yds", fill=theme.TEXT_3,
                      font=(_font(), 7), anchor="ne")

        if selected:
            detail_y = y + 54
            c.create_text(x0 + 28, detail_y, text="Ball Speed", fill=theme.TEXT_3,
                          font=(_font(), 8), anchor="nw")
            c.create_text(x1 - 24, detail_y, text=f"{ball:.1f} mph", fill=theme.TEXT_2,
                          font=(_font(), 9, "bold"), anchor="ne")
            c.create_text(x0 + 28, detail_y + 24, text="Shape", fill=theme.TEXT_3,
                          font=(_font(), 8), anchor="nw")
            c.create_text(x1 - 24, detail_y + 24, text=shape, fill=theme.TEXT_2,
                          font=(_font(), 9, "bold"), anchor="ne")
            c.create_text(x0 + 28, detail_y + 49, text=ts, fill=theme.TEXT_3,
                          font=(_font(), 8), anchor="nw")

        app.sidebar_shot_card_rects.append((x0 + 12, y, x1 - 12, y + rh, real_idx))
        y += rh + 8

    cr = getattr(app, "sidebar_clear_btn_rect", None)
    if cr:
        c.create_text((x0 + x1) / 2, h - 25, text="Clear session", fill=theme.TEXT_3,
                      font=(_font(), 8), anchor="center")
