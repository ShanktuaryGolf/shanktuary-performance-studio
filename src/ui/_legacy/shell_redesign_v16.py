"""Sixteenth-pass shell: fluid topo header texture + gold wordmark crop.

Keeps v15 navigation/sidebar behavior and hit geometry. This pass replaces the
stiff fiber/trajectory texture with subtle topographic contours and derives the
header SHANKTUARY wordmark from the current approved gold lockup asset.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageTk

import shell_redesign_v9 as v9
import shell_redesign_v11 as v11
import shell_redesign_v14 as v14
import theme

NAV_RAIL_W = v14.NAV_RAIL_W
COLLAPSED_GUTTER_W = v14.COLLAPSED_GUTTER_W

GOLD = "#D4A24F"
TEAL = "#58B7B4"
TEAL_BRIGHT = "#8FD7D3"


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _header_surface(app, w, h=52):
    key = (int(w), int(h), "topo-v16")
    if getattr(app, "_brand_header_v16_key", None) == key:
        return app._brand_header_v16_img

    iw, ih = max(1, int(w)), max(1, int(h))
    img = Image.new("RGB", (iw, ih), _rgb("#071722"))
    px = img.load()
    top = _rgb("#0E2A34")
    bottom = _rgb("#06141D")
    left = _rgb("#102D37")
    right = _rgb("#071720")

    # Soft material field; brighter near the brand and quieter near controls.
    for y in range(ih):
        ty = y / max(1, ih - 1)
        for x in range(iw):
            tx = x / max(1, iw - 1)
            vert = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            horiz = tuple(left[i] + (right[i] - left[i]) * min(1.0, tx * 1.18) for i in range(3))
            lift = max(0.0, 1.0 - x / 760.0) * (1.0 - ty * .42)
            vals = []
            for i in range(3):
                v = vert[i] * .64 + horiz[i] * .36
                if i == 1:
                    v += 2.1 * lift
                elif i == 2:
                    v += 2.8 * lift
                vals.append(max(0, min(255, round(v))))
            px[x, y] = tuple(vals)

    d = ImageDraw.Draw(img, "RGBA")

    # Flowing contour families: irregular, layered and intentionally non-parallel.
    # Most live in the left/center brand zone and taper before the utility cluster.
    rng = random.Random(1616)
    max_x = min(iw, 980)
    for band in range(11):
        base_y = 5 + band * 4.4
        phase = rng.uniform(0.0, math.tau)
        amp1 = rng.uniform(2.2, 5.2)
        amp2 = rng.uniform(1.0, 2.8)
        period1 = rng.uniform(175.0, 285.0)
        period2 = rng.uniform(78.0, 145.0)
        slope = rng.uniform(-0.012, 0.012)
        pts = []
        for x in range(-20, max_x + 30, 7):
            y = (
                base_y
                + amp1 * math.sin(x / period1 * math.tau + phase)
                + amp2 * math.sin(x / period2 * math.tau + phase * .57)
                + slope * x
            )
            pts.append((x, y))
        alpha = 17 + (band % 3) * 4
        d.line(pts, fill=(88, 183, 180, alpha), width=1)

    # A few nested, imperfect contour islands create the real topo-map read.
    islands = [
        (430, 24, 118, 25, .18),
        (610, 31, 88, 20, -.12),
        (765, 18, 105, 22, .10),
    ]
    for cx, cy, rx, ry, tilt in islands:
        for ring in range(4):
            shrink = 1.0 - ring * .19
            pts = []
            for step in range(73):
                a = step / 72.0 * math.tau
                wobble = 1.0 + .07 * math.sin(a * 3 + ring) + .035 * math.sin(a * 5 + ring * .6)
                xx = math.cos(a) * rx * shrink * wobble
                yy = math.sin(a) * ry * shrink * (1.0 + .06 * math.cos(a * 4 + ring))
                # small rotation so none of the islands feels mechanically oval
                xr = xx * math.cos(tilt) - yy * math.sin(tilt)
                yr = xx * math.sin(tilt) + yy * math.cos(tilt)
                pts.append((cx + xr, cy + yr))
            d.line(pts, fill=(120, 208, 203, 20 + ring * 3), width=1)

    # Tiny gold contour fragment gives the surface a restrained brand accent.
    gold_pts = []
    for x in range(300, min(max_x, 590), 6):
        y = 39 + 3.0 * math.sin(x / 118.0 * math.tau + .7) + 1.2 * math.sin(x / 57.0 * math.tau)
        gold_pts.append((x, y))
    if len(gold_pts) > 1:
        d.line(gold_pts, fill=(212, 162, 79, 19), width=1)

    # Keep the frame crisp while the interior moves organically.
    d.line((0, 0, iw, 0), fill=(88, 183, 180, 18), width=1)
    d.line((0, ih - 1, iw, ih - 1), fill=(88, 183, 180, 46), width=1)

    app._brand_header_v16_img = ImageTk.PhotoImage(img)
    app._brand_header_v16_key = key
    return app._brand_header_v16_img


def _gold_wordmark(app, target_h=31):
    """Extract only the approved gold SHANKTUARY lettering from the new lockup.

    This avoids the stale white wordmark asset while preserving the exact gold
    artwork already approved in assets/shanktuary_lockup.png.
    """
    key = (v11.LOCKUP_PATH, int(target_h), "gold-word-v16")
    if getattr(app, "_gold_wordmark_v16_key", None) == key:
        return getattr(app, "_gold_wordmark_v16_img", None)

    photo = None
    try:
        im = Image.open(v11.LOCKUP_PATH).convert("RGBA")
        pix = im.load()
        xs, ys = [], []
        # Ignore the standalone icon region on the far left; descriptor is teal,
        # so a warm-color mask isolates the gold wordmark and divider naturally.
        left_cut = int(im.width * .12)
        for y in range(im.height):
            for x in range(left_cut, im.width):
                r, g, b, a = pix[x, y]
                if a > 28 and r > 120 and g > 70 and b < 125 and r > b * 1.45:
                    xs.append(x)
                    ys.append(y)
        if xs and ys:
            pad = 2
            box = (
                max(left_cut, min(xs) - pad), max(0, min(ys) - pad),
                min(im.width, max(xs) + pad + 1), min(im.height, max(ys) + pad + 1),
            )
            crop = im.crop(box)
            ratio = target_h / max(1, crop.height)
            crop = crop.resize((max(1, round(crop.width * ratio)), int(target_h)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(crop)
    except Exception:
        photo = None

    app._gold_wordmark_v16_img = photo
    app._gold_wordmark_v16_key = key
    return photo


def paint_nav(app, h):
    return v14.paint_nav(app, h)


def paint_sidebar(app, w, h):
    return v14.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52
    c.create_image(0, 0, image=_header_surface(app, w, hh), anchor="nw")

    shield = v11._load_brand_image(app, "_brand_shield_v16_img", v11.SHIELD_PATH, 40)
    wordmark = _gold_wordmark(app, 31)

    icon_x = 8
    if shield is not None:
        c.create_image(icon_x, 6, image=shield, anchor="nw")

    word_x = 58
    word_y = 10
    if wordmark is not None:
        c.create_image(word_x, word_y, image=wordmark, anchor="nw")
        word_right = word_x + wordmark.width()
    else:
        word_right = word_x + 190

    divider_x = word_right + 16
    c.create_line(divider_x, 12, divider_x, 40, fill=GOLD, width=1)
    c.create_text(divider_x + 19, 26,
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
