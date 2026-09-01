"""Fifteenth-pass shell: textured header + separable brand lockup.

Keeps v14 navigation/sidebar behavior and hit geometry. The header now uses:
- approved standalone S icon PNG
- approved SHANKTUARY wordmark PNG
- live PERFORMANCE GOLF STUDIO text
- restrained navy/teal/gold material texture
"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageTk

import shell_redesign_v9 as v9
import shell_redesign_v11 as v11
import shell_redesign_v14 as v14
import theme

NAV_RAIL_W = v14.NAV_RAIL_W
COLLAPSED_GUTTER_W = v14.COLLAPSED_GUTTER_W

GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_BRIGHT = "#8FD7D3"


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _header_surface(app, w, h=52):
    key = (int(w), int(h))
    if getattr(app, "_brand_header_v15_key", None) == key:
        return app._brand_header_v15_img

    iw, ih = max(1, int(w)), max(1, int(h))
    img = Image.new("RGB", (iw, ih), _rgb("#071722"))
    px = img.load()
    top = _rgb("#0D2933")
    bottom = _rgb("#06141D")
    left = _rgb("#102D37")
    right = _rgb("#071721")

    for y in range(ih):
        ty = y / max(1, ih - 1)
        for x in range(iw):
            tx = x / max(1, iw - 1)
            vert = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            horiz = tuple(left[i] + (right[i] - left[i]) * min(1.0, tx * 1.25) for i in range(3))
            lift = max(0.0, 1.0 - x / 720.0) * (1.0 - ty * .35)
            vals = []
            for i in range(3):
                v = vert[i] * .62 + horiz[i] * .38
                if i == 1:
                    v += 1.8 * lift
                elif i == 2:
                    v += 2.5 * lift
                vals.append(max(0, min(255, round(v))))
            px[x, y] = tuple(vals)

    d = ImageDraw.Draw(img, "RGBA")
    # Fine performance-equipment fibers, restricted to the brand side.
    for x in range(-ih, min(iw, 780), 17):
        d.line((x, ih, x + ih, 0), fill=(88, 183, 180, 7), width=1)
    for x in range(-ih, min(iw, 780), 29):
        d.line((x, 0, x + ih, ih), fill=(227, 188, 112, 4), width=1)

    # Ghosted trajectory signatures: teal geometry + a restrained gold trace.
    traces = [
        ((310, 43), (375, 40), (435, 18), (545, 24), (88, 183, 180, 18)),
        ((345, 46), (405, 42), (465, 28), (575, 31), (143, 215, 211, 9)),
        ((285, 41), (350, 38), (420, 31), (505, 34), (212, 162, 79, 10)),
    ]
    for p0, p1, p2, p3, col in traces:
        pts = []
        for step in range(50):
            t = step / 49.0
            mt = 1.0 - t
            xx = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
            yy = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
            pts.append((xx, yy))
        d.line(pts, fill=col, width=1)

    rng = random.Random(1515)
    for _ in range(24):
        xx = rng.randint(245, min(max(246, iw - 1), 650))
        yy = rng.randint(8, 45)
        d.ellipse((xx, yy, xx + 1, yy + 1), fill=(120, 194, 193, rng.randint(5, 12)))

    d.line((0, 0, iw, 0), fill=(88, 183, 180, 16), width=1)
    d.line((0, ih - 1, iw, ih - 1), fill=(88, 183, 180, 42), width=1)

    app._brand_header_v15_img = ImageTk.PhotoImage(img)
    app._brand_header_v15_key = key
    return app._brand_header_v15_img


def paint_nav(app, h):
    return v14.paint_nav(app, h)


def paint_sidebar(app, w, h):
    return v14.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_header_surface(app, w, hh), anchor="nw")

    # Approved art remains exact; composition is now independent.
    shield = v11._load_brand_image(app, "_brand_shield_v15_img", v11.SHIELD_PATH, 40)
    wordmark = v11._load_brand_image(app, "_brand_wordmark_v15_img", v11.WORDMARK_PATH, 31)

    icon_x = 8
    if shield is not None:
        c.create_image(icon_x, 6, image=shield, anchor="nw")

    word_x = 56
    word_y = 10
    if wordmark is not None:
        c.create_image(word_x, word_y, image=wordmark, anchor="nw")
        word_right = word_x + wordmark.width()
    else:
        word_right = word_x + 180

    divider_x = word_right + 14
    c.create_line(divider_x, 13, divider_x, 39, fill=GOLD, width=1)
    c.create_text(divider_x + 18, 26,
                  text="PERFORMANCE  GOLF  STUDIO",
                  fill=TEAL_BRIGHT,
                  font=(theme.ui_font(), 9, "bold"), anchor="w")

    # Preserve v14's operational control cluster and exact hit geometry.
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
    c.create_oval(status_x, 23, status_x + 8, 31, fill=v9.GOOD, outline="")
    c.create_text(status_x + 14, 27, text="Ready", fill=theme.TEXT_2,
                  font=(v9.v4._font(), 9, "bold"), anchor="w")

    v9._utility_button(c, app.club_btn_rect,
                       f"{getattr(app, 'current_club', 'Club')}  ▼",
                       bool(getattr(app, "show_club_menu", False)))
    hand = "LH" if getattr(app, "is_left_handed", False) else "RH"
    v9._utility_button(c, app.dexterity_btn_rect, hand)
    v9._utility_button(c, app.tools_btn_rect, "Tools  ▼",
                       bool(getattr(app, "show_tools_menu", False)))
    v9._utility_button(c, app.fullscreen_btn_rect, "⛶")

    app.design_club_btn_rect = tuple(app.club_btn_rect) if app.club_btn_rect else None
    app.design_dexterity_btn_rect = tuple(app.dexterity_btn_rect) if app.dexterity_btn_rect else None
    app.design_tools_btn_rect = tuple(app.tools_btn_rect) if app.tools_btn_rect else None
    app.design_fullscreen_btn_rect = tuple(app.fullscreen_btn_rect) if app.fullscreen_btn_rect else None
