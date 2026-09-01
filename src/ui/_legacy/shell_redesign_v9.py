"""Ninth-pass shell: a true Shanktuary brand lockup instead of a generic dashboard header."""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageTk

import shell_redesign_v7 as v7
import shell_redesign_v8 as v8
import shell_redesign_v4 as v4
import theme

BLUE = v8.BLUE
BLUE_LINE = v8.BLUE_LINE
BLUE_TEXT = v8.BLUE_TEXT
ORANGE = getattr(theme, "WARN", "#FF7A32")
GOOD = getattr(theme, "GOOD", "#39A879")


def _mix(a, b, t):
    return v7._mix(a, b, t)


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def paint_nav(app, h):
    return v8.paint_nav(app, h)


def paint_sidebar(app, w, h):
    return v8.paint_sidebar(app, w, h)


def _brand_surface(app, w, h=52):
    """Dark equipment-like header with woven texture and ghosted launch traces.

    The texture is deliberately richer near the brand and fades toward the
    utility controls. It should read as material/depth rather than a visible
    decorative pattern.
    """
    key = (int(w), int(h))
    if getattr(app, "_brand_header_v9_key", None) == key:
        return app._brand_header_v9_img

    iw, ih = max(1, int(w)), max(1, int(h))
    img = Image.new("RGB", (iw, ih), _rgb("#07101A"))
    px = img.load()

    top = _rgb("#0D1B2B")
    bottom = _rgb("#070B12")
    left = _rgb("#10233B")
    right = _rgb("#070B11")
    rng = random.Random(9147)

    # Multi-axis base field: no single radial 'light bulb' can be perceived.
    for y in range(ih):
        ty = y / max(1, ih - 1)
        for x in range(iw):
            tx = x / max(1, iw - 1)
            vert = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            horiz = tuple(left[i] + (right[i] - left[i]) * min(1.0, tx * 1.5) for i in range(3))
            brand_lift = max(0.0, 1.0 - x / 620.0) * (0.9 - 0.25 * ty)
            diag = max(0.0, 1.0 - abs((y / max(1, ih)) - (0.82 - x / max(1, iw) * 0.35)) * 2.8)
            vals = []
            for i in range(3):
                v = vert[i] * .55 + horiz[i] * .45
                if i == 2:
                    v += 4.0 * brand_lift + 1.6 * diag
                elif i == 1:
                    v += 2.2 * brand_lift + .7 * diag
                vals.append(max(0, min(255, round(v))))
            px[x, y] = tuple(vals)

    d = ImageDraw.Draw(img, "RGBA")

    # Fine woven/carbon-like fibers. Enough structure to avoid flatness, but
    # subtle enough that the eye never lands on a repeating wallpaper pattern.
    for x in range(-ih, min(iw, 760), 13):
        d.line((x, ih, x + ih, 0), fill=(94, 143, 203, 8), width=1)
    for x in range(-ih, min(iw, 760), 19):
        d.line((x, 0, x + ih, ih), fill=(255, 255, 255, 4), width=1)

    # Ghost launch-monitor traces give the brand region a proprietary golf cue.
    # They intentionally disappear before the utility controls.
    traces = [
        ((208, 42), (282, 37), (355, 14), (468, 20), (82, 163, 255, 22)),
        ((230, 45), (310, 40), (376, 24), (500, 30), (82, 163, 255, 12)),
        ((190, 39), (265, 35), (330, 28), (430, 33), (255, 125, 55, 10)),
    ]
    for p0, p1, p2, p3, col in traces:
        pts = []
        for step in range(61):
            t = step / 60.0
            mt = 1.0 - t
            x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
            y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
            pts.append((x, y))
        d.line(pts, fill=col, width=1)

    # Sparse technical ticks and micro-points, all restricted to the brand zone.
    for x in (300, 350, 400, 450, 500):
        d.line((x, 43, x, 47), fill=(112, 157, 210, 14), width=1)
    for _ in range(28):
        x = rng.randint(175, min(max(176, iw - 1), 565))
        y = rng.randint(7, 46)
        r = rng.choice((1, 1, 1, 2))
        d.ellipse((x-r, y-r, x+r, y+r), fill=(132, 170, 216, rng.randint(5, 12)))

    # Hairline upper highlight + lower equipment seam.
    d.line((0, 0, iw, 0), fill=(78, 151, 255, 18), width=1)
    d.line((0, ih - 1, iw, ih - 1), fill=(89, 130, 175, 34), width=1)

    app._brand_header_v9_img = ImageTk.PhotoImage(img)
    app._brand_header_v9_key = key
    return app._brand_header_v9_img


def _brand_mark(app):
    """A more ownable app mark: angular S + shot-trace/impact cue."""
    if getattr(app, "_brand_mark_v9_img", None) is not None:
        return app._brand_mark_v9_img

    scale = 3
    sz = 42
    im = Image.new("RGBA", (sz * scale, sz * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")

    # Rounded electric-blue tile with a darker performance-equipment lower edge.
    d.rounded_rectangle((0, 0, sz*scale-1, sz*scale-1), radius=8*scale,
                        fill=(24, 93, 224, 255), outline=(73, 151, 255, 245), width=1*scale)
    d.rounded_rectangle((2*scale, 2*scale, (sz-2)*scale, 22*scale), radius=6*scale,
                        fill=(47, 126, 255, 235))
    # Deep diagonal cut stops this from reading like a generic blue app square.
    d.polygon([(0, 31*scale), (42*scale, 18*scale), (42*scale, 42*scale), (0, 42*scale)],
              fill=(15, 70, 179, 92))

    # Chamfered S: a compact performance-stripe mark rather than a font glyph.
    white = (239, 247, 255, 255)
    pts = [
        (10, 9), (33, 9), (29, 14), (15, 14),
        (13, 17), (13, 20), (29, 20), (32, 23),
        (32, 29), (28, 33), (8, 33), (12, 28),
        (26, 28), (27, 26), (27, 25), (12, 25),
        (8, 21), (8, 15),
    ]
    d.polygon([(x*scale, y*scale) for x, y in pts], fill=white)

    # Tiny impact/endpoint cue: one warm point makes the mark feel golf-data driven.
    d.ellipse((30*scale, 9*scale, 34*scale, 13*scale), fill=(255, 125, 55, 255))

    im = im.resize((sz, sz), Image.Resampling.LANCZOS)
    app._brand_mark_v9_img = ImageTk.PhotoImage(im)
    return app._brand_mark_v9_img


def _utility_button(c, rect, text, active=False):
    """Quiet equipment controls: bordered modules, not Tableau-looking blocks."""
    if not rect:
        return
    x1, y1, x2, y2 = rect
    fill = _mix("#09111B", BLUE, .055 if active else .018)
    border = _mix(theme.HAIRLINE, BLUE_LINE, .16 if active else .05)
    c.create_rectangle(x1, y1, x2, y2, fill=fill, outline=border, width=1)
    if active:
        c.create_rectangle(x1, y1, x1 + 2, y2, fill=BLUE, outline="")
    c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text,
                  fill=theme.TEXT if active else theme.TEXT_2,
                  font=(v4._font(), 10, "bold" if active else "normal"), anchor="center")


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_brand_surface(app, w, hh), anchor="nw")

    # Integrated lockup: mark + wordmark + descriptor + shot-trace signature.
    c.create_image(12, 5, image=_brand_mark(app), anchor="nw")

    brand_x = 66
    # Split the name subtly to create a custom lockup without turning it into a logo gimmick.
    c.create_text(brand_x, 8, text="SHANK", fill=theme.TEXT,
                  font=(v4._font(), 17, "bold"), anchor="nw")
    # Measure approximately from the font size; intentional tight join.
    c.create_text(brand_x + 65, 8, text="TUARY", fill=_mix(theme.TEXT, BLUE_TEXT, .22),
                  font=(v4._font(), 17, "bold"), anchor="nw")

    # Tagline belongs to the wordmark, not behind a dashboard divider.
    c.create_oval(brand_x, 34, brand_x + 4, 38, fill=ORANGE, outline="")
    c.create_text(brand_x + 10, 30, text="PERFORMANCE GOLF STUDIO",
                  fill=BLUE_TEXT, font=(v4._font(), 8, "bold"), anchor="nw")

    # One crisp brand trajectory becomes the signature device; the background
    # carries fainter versions of the same idea.
    path_y = 43
    c.create_line(brand_x + 10, path_y, brand_x + 86, path_y,
                  fill=_mix(BLUE_LINE, theme.BG, .42), width=1)
    c.create_line(brand_x + 86, path_y, brand_x + 134, path_y - 7,
                  fill=BLUE_LINE, width=2)
    c.create_oval(brand_x + 132, path_y - 10, brand_x + 137, path_y - 5,
                  fill=ORANGE, outline="")

    # Utility cluster remains operationally separate and visually quieter.
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
    hand = "LH" if getattr(app, "is_left_handed", False) else "RH"
    _utility_button(c, app.dexterity_btn_rect, hand)
    _utility_button(c, app.tools_btn_rect, "Tools  ▼",
                    bool(getattr(app, "show_tools_menu", False)))
    _utility_button(c, app.fullscreen_btn_rect, "⛶")

    # Preserve v8's deterministic design-owned hit targets.
    app.design_club_btn_rect = tuple(app.club_btn_rect) if app.club_btn_rect else None
    app.design_dexterity_btn_rect = tuple(app.dexterity_btn_rect) if app.dexterity_btn_rect else None
    app.design_tools_btn_rect = tuple(app.tools_btn_rect) if app.tools_btn_rect else None
    app.design_fullscreen_btn_rect = tuple(app.fullscreen_btn_rect) if app.fullscreen_btn_rect else None
