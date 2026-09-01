"""Sixth-pass shell: unified branded header over the design sandbox."""

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
    if getattr(app, "_brand_header_key", None) != key:
        iw, ih = max(1, int(w)), max(1, int(h))
        img = Image.new("RGB", (iw, ih), _rgb(theme.BG))
        draw = ImageDraw.Draw(img)

        left = _rgb(_mix(theme.BG, "#173A65", .20))
        right = _rgb(_mix(theme.BG, "#02060C", .22))
        for xx in range(0, iw, 4):
            t = xx / max(1, iw - 1)
            eased = t * t * (3 - 2 * t)
            col = tuple(round(a + (b - a) * eased) for a, b in zip(left, right))
            draw.rectangle((xx, 0, min(iw, xx + 4), ih), fill=col)

        # A restrained blue illumination around the brand; it should read as
        # depth, not a visible glow effect.
        glow = Image.new("RGB", (iw, ih), _rgb(theme.BG))
        gd = ImageDraw.Draw(glow)
        cx, cy = int(iw * .16), int(ih * .45)
        for i in range(12, 0, -1):
            f = i / 12
            rx = int(iw * (.045 + .11 * f))
            ry = int(ih * (.30 + .55 * f))
            gd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry),
                       fill=_rgb(_mix(theme.BG, BLUE, .018 + .055 * f)))
        img = Image.blend(img, glow, .18)

        app._brand_header_img = ImageTk.PhotoImage(img)
        app._brand_header_key = key
    return app._brand_header_img


def _draw_app_mark(c, x, y):
    """Abstract S/performance-bars mark on the accepted two-tone blue tile."""
    c.create_rectangle(x, y, x + 36, y + 36, fill="#185DE0", outline="")
    c.create_rectangle(x, y, x + 36, y + 18, fill="#2D7BFF", outline="")

    mark = "#EAF3FF"
    # Crisp segmented S: the horizontal segments also read like performance bars.
    c.create_rectangle(x + 9, y + 8, x + 28, y + 11, fill=mark, outline="")
    c.create_rectangle(x + 7, y + 11, x + 10, y + 18, fill=mark, outline="")
    c.create_rectangle(x + 8, y + 17, x + 27, y + 20, fill=mark, outline="")
    c.create_rectangle(x + 25, y + 20, x + 28, y + 27, fill=mark, outline="")
    c.create_rectangle(x + 8, y + 26, x + 27, y + 29, fill=mark, outline="")


def paint_nav(app, h):
    # Header is painted after nav in draw_screen, so the legacy tile drawn here
    # is intentionally covered by paint_top_header(). Keep v4's nav treatment.
    v4.paint_nav(app, h)


def paint_sidebar(app, w, h):
    v4.paint_sidebar(app, w, h)


def _utility_button(c, rect, text, active=False):
    if not rect:
        return
    x1, y1, x2, y2 = rect
    fill = _mix(theme.SURFACE, BLUE, .055 if active else .018)
    c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")
    c.create_line(x1, y1, x2, y1, fill=_mix(theme.HAIRLINE, BLUE_LINE, .12))
    c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text,
                  fill=theme.TEXT if active else theme.TEXT_2,
                  font=(v4._font(), 10, "bold" if active else "normal"), anchor="center")


def paint_top_header(app, w, h, offset_x=0):
    """Replace the legacy 'Shanktuary Studio' bar with a branded product shell."""
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_header_surface(app, w, hh), anchor="nw")
    c.create_line(0, hh, w, hh, fill=_mix(theme.HAIRLINE, BLUE, .06))

    # Product identity: mark + wordmark + blue divider + descriptor.
    _draw_app_mark(c, 15, 8)
    brand_x = 70
    c.create_text(brand_x, 14, text="SHANKTUARY", fill=theme.TEXT,
                  font=(v4._font(), 16, "bold"), anchor="nw")
    divider_x = brand_x + 154
    c.create_rectangle(divider_x, 12, divider_x + 3, 40, fill=BLUE, outline="")
    c.create_text(divider_x + 14, 16, text="PERFORMANCE GOLF STUDIO",
                  fill=BLUE_TEXT, font=(v4._font(), 9, "bold"), anchor="nw")

    # Preserve the existing sidebar collapse hit target while replacing its old
    # glyph with a conventional chevron.
    tr = getattr(app, "sidebar_toggle_rect", None)
    if tr and not getattr(app, "sidebar_collapsed", False):
        cx, cy = (tr[0] + tr[2]) / 2, (tr[1] + tr[3]) / 2
        c.create_line(cx - 4, cy - 6, cx + 2, cy, cx - 4, cy + 6,
                      fill=theme.TEXT_3, width=2)

    # Existing production hit rectangles are retained. Repaint the controls so
    # the demo still behaves normally while status moves into the utility cluster.
    club_rect = getattr(app, "club_btn_rect", None)
    dex_rect = getattr(app, "dexterity_btn_rect", None)
    tools_rect = getattr(app, "tools_btn_rect", None)
    fs_rect = getattr(app, "fullscreen_btn_rect", None)

    if club_rect:
        status_x = club_rect[0] - 82
        c.create_oval(status_x, 23, status_x + 8, 31, fill=GOOD, outline="")
        c.create_text(status_x + 14, 27, text="Ready", fill=theme.TEXT_2,
                      font=(v4._font(), 9, "bold"), anchor="w")

    _utility_button(c, club_rect, f"{getattr(app, 'current_club', 'Club')}  ▼",
                    bool(getattr(app, "show_club_menu", False)))
    hand = str(getattr(app, "dexterity", "RH") or "RH").upper()
    if hand not in ("RH", "LH"):
        hand = "RH"
    _utility_button(c, dex_rect, hand)
    _utility_button(c, tools_rect, "Tools  ▼", bool(getattr(app, "show_tools_menu", False)))
    _utility_button(c, fs_rect, "⛶")
