"""Seventeenth-pass shell: clean full-width topo contours + trimmed gold wordmark.

Keeps v14 navigation/sidebar behavior and hit geometry. This pass makes the
header contour field behave like real topography: one continuous family of
non-intersecting fluid contours spanning the full ribbon, with lower contrast.
It also removes the trailing gold lockup ornament and the artificial divider.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageTk

import shell_redesign_v9 as v9
import shell_redesign_v11 as v11
import shell_redesign_v14 as v14
import theme

NAV_RAIL_W = v14.NAV_RAIL_W
COLLAPSED_GUTTER_W = v14.COLLAPSED_GUTTER_W

GOLD = "#D4A24F"
TEAL_BRIGHT = "#8FD7D3"


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _header_surface(app, w, h=52):
    key = (int(w), int(h), "topo-v17")
    if getattr(app, "_brand_header_v17_key", None) == key:
        return app._brand_header_v17_img

    iw, ih = max(1, int(w)), max(1, int(h))
    img = Image.new("RGB", (iw, ih), _rgb("#071722"))
    px = img.load()
    top = _rgb("#0D2832")
    bottom = _rgb("#06141D")
    left = _rgb("#102B35")
    right = _rgb("#071720")

    # Quiet navy/teal material field across the entire application header.
    for y in range(ih):
        ty = y / max(1, ih - 1)
        for x in range(iw):
            tx = x / max(1, iw - 1)
            vert = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            horiz = tuple(left[i] + (right[i] - left[i]) * tx for i in range(3))
            vals = tuple(max(0, min(255, round(vert[i] * .66 + horiz[i] * .34))) for i in range(3))
            px[x, y] = vals

    d = ImageDraw.Draw(img, "RGBA")

    # One shared terrain field produces every contour. Because each line is an
    # ordered offset of the same field, contours can bend and compress without
    # ever crossing one another.
    def terrain(x):
        broad = 3.8 * math.sin(x / 330.0 * math.tau + .35)
        middle = 1.9 * math.sin(x / 165.0 * math.tau + 1.15)
        fine = .75 * math.sin(x / 82.0 * math.tau + 2.05)
        # Broad local rises/depressions create the topo-map feel without closed
        # islands that can collide with the open contour family.
        hill_a = 3.2 * math.exp(-((x - iw * .32) / max(120.0, iw * .13)) ** 2)
        hill_b = -2.7 * math.exp(-((x - iw * .67) / max(130.0, iw * .15)) ** 2)
        hill_c = 1.8 * math.exp(-((x - iw * .86) / max(90.0, iw * .10)) ** 2)
        return broad + middle + fine + hill_a + hill_b + hill_c

    spacing = 5.0
    for band in range(-2, 13):
        base_y = 1.0 + band * spacing
        # Tiny scale progression varies contour spacing around terrain features
        # while remaining far below the 5px ordering gap, so no intersections.
        scale = .91 + band * .012
        pts = []
        for x in range(-12, iw + 13, 6):
            y = base_y + terrain(x) * scale
            pts.append((x, y))
        # Slightly faded compared with v16; visible as material, not artwork.
        alpha = 11 if band % 3 else 14
        d.line(pts, fill=(102, 191, 190, alpha), width=1)

    # A few secondary contours share the exact same terrain field and simply
    # sit between primary contours. This adds density without adding crossings.
    for band in (1, 4, 7, 10):
        base_y = 1.0 + (band + .5) * spacing
        pts = [(x, base_y + terrain(x) * (.94 + band * .01))
               for x in range(-12, iw + 13, 7)]
        d.line(pts, fill=(137, 209, 205, 7), width=1)

    # Crisp but quiet frame seams.
    d.line((0, 0, iw, 0), fill=(88, 183, 180, 13), width=1)
    d.line((0, ih - 1, iw, ih - 1), fill=(88, 183, 180, 34), width=1)

    app._brand_header_v17_img = ImageTk.PhotoImage(img)
    app._brand_header_v17_key = key
    return app._brand_header_v17_img


def _warm_components(im):
    """Return connected warm/gold components from the approved lockup."""
    w, h = im.size
    pix = im.load()
    mask = set()
    left_cut = int(w * .12)
    for y in range(h):
        for x in range(left_cut, w):
            r, g, b, a = pix[x, y]
            if a > 28 and r > 120 and g > 70 and b < 135 and r > b * 1.35:
                mask.add((x, y))

    comps = []
    while mask:
        seed = mask.pop()
        stack = [seed]
        xs = [seed[0]]
        ys = [seed[1]]
        while stack:
            x, y = stack.pop()
            for nx in (x - 1, x, x + 1):
                for ny in (y - 1, y, y + 1):
                    if (nx, ny) in mask:
                        mask.remove((nx, ny))
                        stack.append((nx, ny))
                        xs.append(nx)
                        ys.append(ny)
        comps.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, len(xs)))
    return comps


def _gold_wordmark(app, target_h=31):
    """Extract SHANKTUARY only, dropping the trailing lockup ornament."""
    key = (v11.LOCKUP_PATH, int(target_h), "gold-word-v17")
    if getattr(app, "_gold_wordmark_v17_key", None) == key:
        return getattr(app, "_gold_wordmark_v17_img", None)

    photo = None
    try:
        im = Image.open(v11.LOCKUP_PATH).convert("RGBA")
        comps = _warm_components(im)
        if comps:
            # Ignore tiny antialiasing specks, then identify the far-right narrow
            # ornament. Letters are substantially wider; the ornament is a thin
            # vertical component separated from the Y.
            meaningful = [c for c in comps if c[4] >= 5]
            min_x = min(c[0] for c in meaningful)
            max_x = max(c[2] for c in meaningful)
            min_y = min(c[1] for c in meaningful)
            max_y = max(c[3] for c in meaningful)
            span_w = max(1, max_x - min_x)
            span_h = max(1, max_y - min_y)

            trailing = []
            for c in meaningful:
                cw = c[2] - c[0]
                ch = c[3] - c[1]
                if (c[0] > min_x + span_w * .78 and
                        cw < span_w * .055 and
                        ch > cw * 1.45):
                    trailing.append(c)

            keep = [c for c in meaningful if c not in trailing] or meaningful
            min_x = min(c[0] for c in keep)
            max_x = max(c[2] for c in keep)
            min_y = min(c[1] for c in keep)
            max_y = max(c[3] for c in keep)

            pad = 2
            crop = im.crop((
                max(0, min_x - pad), max(0, min_y - pad),
                min(im.width, max_x + pad), min(im.height, max_y + pad),
            ))
            ratio = target_h / max(1, crop.height)
            crop = crop.resize((max(1, round(crop.width * ratio)), int(target_h)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(crop)
    except Exception:
        photo = None

    app._gold_wordmark_v17_img = photo
    app._gold_wordmark_v17_key = key
    return photo


def paint_nav(app, h):
    return v14.paint_nav(app, h)


def paint_sidebar(app, w, h):
    return v14.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_header_surface(app, w, hh), anchor="nw")

    shield = v11._load_brand_image(app, "_brand_shield_v17_img", v11.SHIELD_PATH, 40)
    wordmark = _gold_wordmark(app, 31)

    if shield is not None:
        c.create_image(8, 6, image=shield, anchor="nw")

    word_x = 58
    if wordmark is not None:
        c.create_image(word_x, 10, image=wordmark, anchor="nw")
        word_right = word_x + wordmark.width()
    else:
        word_right = word_x + 190

    # No decorative divider: let spacing do the separation work.
    c.create_text(word_right + 24, 26,
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
