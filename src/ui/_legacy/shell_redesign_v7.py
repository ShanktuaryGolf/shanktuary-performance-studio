"""Seventh-pass shell: reliable hit targets, Shot naming, persistent rail collapse."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageTk

import shell_redesign_v4 as v4
import theme

BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")
GOOD = getattr(theme, "GOOD", "#39A879")


def _mix(a, b, t):
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.BG


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _header_surface(app, w, h=52):
    key = (int(w), int(h))
    if getattr(app, "_brand_header_v7_key", None) != key:
        iw, ih = max(1, int(w)), max(1, int(h))
        top = "#0D1724"
        bottom = "#070B11"
        left = "#102039"
        right = "#060A10"

        vertical = Image.new("RGB", (iw, ih), _rgb(top))
        vd = ImageDraw.Draw(vertical)
        ta, tb = _rgb(top), _rgb(bottom)
        for yy in range(0, ih, 3):
            t = yy / max(1, ih - 1)
            col = tuple(round(a + (b - a) * t) for a, b in zip(ta, tb))
            vd.rectangle((0, yy, iw, min(ih, yy + 3)), fill=col)

        horizontal = Image.new("RGB", (iw, ih), _rgb(left))
        hd = ImageDraw.Draw(horizontal)
        la, lb = _rgb(left), _rgb(right)
        for xx in range(0, iw, 4):
            t = xx / max(1, iw - 1)
            t = t * t * (3 - 2 * t)
            col = tuple(round(a + (b - a) * t) for a, b in zip(la, lb))
            hd.rectangle((xx, 0, min(iw, xx + 4), ih), fill=col)

        img = Image.blend(vertical, horizontal, .35)
        app._brand_header_v7_img = ImageTk.PhotoImage(img)
        app._brand_header_v7_key = key
    return app._brand_header_v7_img


def _draw_app_mark(c, x, y):
    c.create_rectangle(x, y, x + 36, y + 36, fill="#185DE0", outline="")
    c.create_rectangle(x, y, x + 36, y + 18, fill="#2D7BFF", outline="")
    mark = "#EAF3FF"
    c.create_rectangle(x + 9, y + 8, x + 28, y + 11, fill=mark, outline="")
    c.create_rectangle(x + 7, y + 11, x + 10, y + 18, fill=mark, outline="")
    c.create_rectangle(x + 8, y + 17, x + 27, y + 20, fill=mark, outline="")
    c.create_rectangle(x + 25, y + 20, x + 28, y + 27, fill=mark, outline="")
    c.create_rectangle(x + 8, y + 26, x + 27, y + 29, fill=mark, outline="")


def _draw_chevron(c, cx, cy, direction):
    if direction == "left":
        pts = (cx + 3, cy - 6, cx - 3, cy, cx + 3, cy + 6)
    else:
        pts = (cx - 3, cy - 6, cx + 3, cy, cx - 3, cy + 6)
    c.create_line(*pts, fill=theme.TEXT_2, width=2)


def paint_nav(app, h):
    c = app.canvas
    rw = theme.RAIL_W
    shell_bg = _mix(theme.RAIL, theme.BG, .42)
    soft_line = _mix(theme.HAIRLINE, theme.BG, .46)
    selected = _mix(theme.SURFACE_2, BLUE, .11)

    c.create_rectangle(0, 0, rw, h, fill=shell_bg, outline="")
    c.create_line(rw - 1, 0, rw - 1, h, fill=soft_line)

    app.mode_pill_rects = {}
    y = 88
    for mode_id, label, _tip in theme.NAV_ITEMS:
        # Full row is clickable, including the visual breathing room between icons.
        app.mode_pill_rects[mode_id] = (0, y - 4, rw, y + 52)
        active = app.view_mode == mode_id
        if active:
            c.create_rectangle(5, y, rw - 5, y + 48, fill=selected, outline="")
            c.create_rectangle(5, y, 8, y + 48, fill=BLUE, outline="")
        col = theme.TEXT if active else theme.TEXT_3
        icon_col = BLUE_LINE if active else _mix(theme.TEXT_3, theme.TEXT_2, .32)
        v4._draw_nav_icon(c, label, 32, y + 17, icon_col)
        if label == "Overview":
            nav_label = "Shot"
        elif label == "Disp":
            nav_label = "Dispersion"
        elif label == "Nums":
            nav_label = "Numbers"
        else:
            nav_label = label
        c.create_text(32, y + 39, text=nav_label, fill=col,
                      font=(v4._font(), 7, "bold" if active else "normal"),
                      anchor="center")
        y += theme.NAV_ITEM_H

    sy0 = h - 72
    active = app.view_mode == 10
    app.nav_setup_rect = (0, sy0 - 4, rw, h - 16)
    if active:
        c.create_rectangle(5, sy0, rw - 5, h - 20, fill=selected, outline="")
        c.create_rectangle(5, sy0, 8, h - 20, fill=BLUE, outline="")
    col = theme.TEXT if active else theme.TEXT_3
    for dy, knob in ((0, -3), (6, 4), (12, 0)):
        c.create_line(22, sy0 + 12 + dy, 42, sy0 + 12 + dy, fill=col, width=1)
        c.create_oval(32 + knob - 2, sy0 + 10 + dy, 32 + knob + 2, sy0 + 14 + dy,
                      fill=col, outline="")
    c.create_text(32, h - 29, text="Setup", fill=col, font=(v4._font(), 7),
                  anchor="center")

    # Collapsed reopen handle remains inside the rail so workspace painting cannot hide it.
    if getattr(app, "sidebar_collapsed", False):
        app.sidebar_toggle_rect = (rw - 24, 57, rw - 3, 84)
        c.create_rectangle(rw - 24, 57, rw - 3, 84,
                           fill=_mix(theme.SURFACE_2, BLUE, .05), outline="")
        _draw_chevron(c, rw - 13, 70, "right")


def paint_sidebar(app, w, h):
    if getattr(app, "sidebar_collapsed", False):
        return

    v4.paint_sidebar(app, w, h)

    # Stable collapse control on the Recent Shots rail edge, not in the header.
    x1 = app.sidebar_width
    cy = 165
    app.sidebar_toggle_rect = (x1 - 25, cy - 15, x1 - 4, cy + 15)
    c = app.canvas
    c.create_rectangle(x1 - 25, cy - 15, x1 - 4, cy + 15,
                       fill=_mix(theme.SURFACE_2, BLUE, .045), outline="")
    _draw_chevron(c, x1 - 14, cy, "left")


def _utility_button(c, rect, text, active=False):
    if not rect:
        return
    x1, y1, x2, y2 = rect
    fill = _mix(theme.SURFACE, BLUE, .055 if active else .018)
    c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")
    c.create_line(x1, y1, x2, y1, fill=_mix(theme.HAIRLINE, BLUE_LINE, .12))
    c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text,
                  fill=theme.TEXT if active else theme.TEXT_2,
                  font=(v4._font(), 10, "bold" if active else "normal"),
                  anchor="center")


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_header_surface(app, w, hh), anchor="nw")
    c.create_line(0, hh, w, hh, fill=_mix(theme.HAIRLINE, BLUE, .06))

    _draw_app_mark(c, 14, 8)
    brand_x = 68
    c.create_text(brand_x, 14, text="SHANKTUARY", fill=theme.TEXT,
                  font=(v4._font(), 16, "bold"), anchor="nw")
    divider_x = brand_x + 154
    c.create_rectangle(divider_x, 12, divider_x + 3, 40, fill=BLUE, outline="")
    c.create_text(divider_x + 14, 16, text="PERFORMANCE GOLF STUDIO",
                  fill=BLUE_TEXT, font=(v4._font(), 9, "bold"), anchor="nw")

    # Visuals and hit areas are generated from the SAME rectangles.
    right = w - 10
    y1, y2 = 7, 45
    fs_w, tools_w, dex_w, club_w, gap = 38, 86, 58, 112, 7

    app.fullscreen_btn_rect = (right - fs_w, y1, right, y2)
    right -= fs_w + gap
    app.tools_btn_rect = (right - tools_w, y1, right, y2)
    right -= tools_w + gap
    app.dexterity_btn_rect = (right - dex_w, y1, right, y2)
    right -= dex_w + gap
    app.club_btn_rect = (right - club_w, y1, right, y2)

    club_rect = app.club_btn_rect
    status_x = club_rect[0] - 82
    c.create_oval(status_x, 23, status_x + 8, 31, fill=GOOD, outline="")
    c.create_text(status_x + 14, 27, text="Ready", fill=theme.TEXT_2,
                  font=(v4._font(), 9, "bold"), anchor="w")

    _utility_button(c, app.club_btn_rect,
                    f"{getattr(app, 'current_club', 'Club')}  ▼",
                    bool(getattr(app, "show_club_menu", False)))
    hand = str(getattr(app, "dexterity", "RH") or "RH").upper()
    if hand not in ("RH", "LH"):
        hand = "RH"
    _utility_button(c, app.dexterity_btn_rect, hand)
    _utility_button(c, app.tools_btn_rect, "Tools  ▼",
                    bool(getattr(app, "show_tools_menu", False)))
    _utility_button(c, app.fullscreen_btn_rect, "⛶")
