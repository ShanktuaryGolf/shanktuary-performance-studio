"""Focused visual polish for the desktop Range view.

Keeps the existing interaction contract (including range_launch_web_rect) but
recomposes the legacy range so it belongs to the accepted navy/teal/gold UI.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageOps, ImageTk

import theme

GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_SOFT = "#698E96"
PAGE_BG = "#0A2029"
SURFACE = "#0D2731"
SURFACE_2 = "#15333D"
HAIRLINE = "#2A4C55"
GUIDE = "#456D76"
TEXT = "#F3F6FA"
TEXT_2 = "#B3BEC2"
TEXT_3 = "#70868C"


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    aa, bb = _rgb(a), _rgb(b)
    out = tuple(round(aa[i] + (bb[i] - aa[i]) * t) for i in range(3))
    return "#" + "".join(f"{v:02X}" for v in out)


def _background(app, w, h):
    key = (int(w), int(h))
    if getattr(app, "_range_v1_bg_key", None) == key:
        return app._range_v1_bg_img

    iw, ih = max(1, int(w)), max(1, int(h))
    img = Image.new("RGB", (iw, ih), _rgb("#071822"))
    d = ImageDraw.Draw(img)
    top, bottom = _rgb("#0D2B35"), _rgb("#07131A")
    left, right = _rgb("#0A2530"), _rgb("#071A22")

    for y in range(0, ih, 3):
        ty = y / max(1, ih - 1)
        for x in range(0, iw, 6):
            tx = x / max(1, iw - 1)
            vert = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            horiz = tuple(left[i] + (right[i] - left[i]) * tx for i in range(3))
            col = tuple(round(vert[i] * .70 + horiz[i] * .30) for i in range(3))
            d.rectangle((x, y, min(iw, x + 6), min(ih, y + 3)), fill=col)

    # Quiet technical texture: material, not wallpaper.
    for x in range(-ih, min(iw, 900), 27):
        d.line((x, ih, x + ih, 0), fill=(88, 183, 180, 8), width=1)
    try:
        noise = Image.effect_noise((iw, ih), 11).convert("L")
        noise_col = ImageOps.colorize(noise, black="#061018", white="#17333C")
        img = Image.blend(img, noise_col, .018)
    except Exception:
        pass

    app._range_v1_bg_img = ImageTk.PhotoImage(img)
    app._range_v1_bg_key = key
    return app._range_v1_bg_img


def _shot_values(shot):
    shot = shot or {}
    ogc = shot.get("open_golf_coach", {}) or {}
    us = ogc.get("us_customary_units", {}) or {}
    carry = float(us.get("carry_distance_yards") or shot.get("carry_distance_yards") or 0.0)
    offline = float(us.get("offline_distance_yards") or shot.get("offline_distance_yards") or 0.0)
    return carry, offline


def _club_session_shots(app):
    current = app.current_shot or {}
    club = current.get("club") or getattr(app, "current_club", "")
    shots = [s for s in getattr(app, "session_shots", []) if not s.get("excluded", False)]
    subset = [s for s in shots if (s.get("club") or "") == club]
    return subset or shots


def _metric(c, x0, x1, label, value, value_color=TEXT):
    c.create_text(x0 + 18, 68, text=label.upper(), fill=TEXT_3,
                  font=(theme.ui_font(), 7, "bold"), anchor="nw")
    c.create_text(x0 + 18, 89, text=value, fill=value_color,
                  font=(theme.ui_font(), 11, "bold"), anchor="w")
    c.create_line(x1, 65, x1, 102, fill="#1F414A")


def draw_range(app, avail_w, h, carry_yds, total_yds, ball_speed, club_speed,
               apex_yds, offline_yds, total_spin, vert_launch, horiz_launch,
               offset_x=0):
    c = app.canvas
    app.range_launch_web_rect = None

    x0, x1 = offset_x, offset_x + avail_w
    top_y = 52
    metric_bottom = 112
    horizon_y = top_y + int((h - top_y) * .205)
    horizon_y = max(metric_bottom + 80, horizon_y)
    ground_y = h - 18
    cx = (x0 + x1) / 2

    c.create_image(x0, top_y, image=_background(app, avail_w, h - top_y), anchor="nw")

    # Low, restrained ridgeline so the sky has depth without becoming scenic.
    ridge_y = horizon_y - 20
    ridge = [
        x0, horizon_y,
        x0 + avail_w * .12, ridge_y - 5,
        x0 + avail_w * .29, ridge_y + 12,
        x0 + avail_w * .47, ridge_y - 9,
        x0 + avail_w * .66, ridge_y + 5,
        x0 + avail_w * .86, ridge_y - 4,
        x1, horizon_y,
    ]
    c.create_polygon(ridge, fill="#0A2028", outline="")
    c.create_line(*ridge, fill="#274E57", width=1)

    # Ground and a subtly distinct fairway/corridor.
    c.create_rectangle(x0, horizon_y, x1, ground_y, fill="#071611", outline="")
    far_half = avail_w * .145
    near_half = avail_w * .47
    fairway = (cx - far_half, horizon_y, cx + far_half, horizon_y,
               cx + near_half, ground_y, cx - near_half, ground_y)
    c.create_polygon(fairway, fill="#0A1D1A", outline="#28565B", width=2)

    range_span = ground_y - horizon_y

    def y_for_distance(dist):
        frac = max(0.0, min(1.0, dist / 350.0)) ** .72
        return ground_y - frac * range_span * .965

    def half_width_at(y):
        t = (y - horizon_y) / max(1.0, range_span)
        return far_half + (near_half - far_half) * max(0.0, min(1.0, t))

    # Reference geometry stays teal and progressively quieter with distance.
    c.create_line(cx, ground_y, cx, horizon_y, fill=TEAL_SOFT, width=1, dash=(5, 7))
    for dist in range(50, 351, 50):
        yy = y_for_distance(dist)
        hw = half_width_at(yy) * .78
        guide_col = _mix(GUIDE, PAGE_BG, .18 if dist < 250 else .33)
        c.create_line(cx - hw, yy, cx + hw, yy, fill=guide_col, dash=(2, 7))
        box_w = 38
        c.create_rectangle(cx - box_w / 2, yy - 10, cx + box_w / 2, yy + 10,
                           fill="#102933", outline="#315760")
        c.create_text(cx, yy, text=str(dist), fill=TEAL_TEXT,
                      font=(theme.ui_font(), 7, "bold"), anchor="center")

        if dist in (100, 150, 200, 250, 300):
            fx = cx + half_width_at(yy) * .12
            c.create_line(fx, yy + 1, fx, yy - 21, fill=TEAL_SOFT, width=1)
            c.create_polygon(fx, yy - 21, fx + 11, yy - 17, fx, yy - 13,
                             fill=TEAL_TEXT, outline="")

    # Historical shot traces are intentionally subordinate.
    shots = _club_session_shots(app)[-12:]
    for shot in shots:
        carry, off = _shot_values(shot)
        if carry <= 0:
            continue
        ly = y_for_distance(carry)
        hw = half_width_at(ly)
        lx = cx + max(-1.0, min(1.0, off / 45.0)) * hw
        is_current = shot is app.current_shot
        color = GOLD if is_current else "#335F66"
        width = 3 if is_current else 1
        pts = []
        for i in range(17):
            t = i / 16.0
            # Smooth lateral movement that develops late in flight.
            xx = cx + (lx - cx) * (t ** 1.55)
            yy = ground_y + (ly - ground_y) * (t ** .86)
            pts.extend((xx, yy))
        c.create_line(*pts, fill=color, width=width, smooth=True)
        r = 8 if is_current else 3
        c.create_oval(lx - r, ly - r, lx + r, ly + r,
                      fill=GOLD if is_current else "#456E74", outline="")
        if is_current:
            c.create_oval(lx - 13, ly - 13, lx + 13, ly + 13,
                          fill="", outline=TEAL_LINE, width=2)
            label = f"{carry:.1f} YDS"
            c.create_rectangle(lx - 41, ly - 35, lx + 41, ly - 16,
                               fill="#0F2A33", outline=TEAL_LINE)
            c.create_text(lx, ly - 25, text=label, fill=TEAL_TEXT,
                          font=(theme.ui_font(), 8, "bold"), anchor="center")

    # Rebuilt top metric ribbon: same information, calmer hierarchy.
    c.create_rectangle(x0, top_y, x1, metric_bottom, fill="#0A222B", outline="")
    c.create_line(x0, metric_bottom, x1, metric_bottom, fill="#31545D")
    metrics = [
        ("Carry", f"{carry_yds:.1f} YDS", TEAL_TEXT),
        ("Total", f"{total_yds:.1f} YDS", TEXT),
        ("Ball Speed", f"{ball_speed:.1f} MPH", TEXT),
        ("Club Speed", f"{club_speed:.1f} MPH", TEXT),
        ("Launch", f"{vert_launch:.1f}°", TEXT),
        ("Total Spin", f"{total_spin:.0f} RPM", TEXT),
        ("Apex", f"{apex_yds:.1f} YDS", TEXT),
        ("Offline", f"{abs(offline_yds):.1f} {'R' if offline_yds > 0 else 'L' if offline_yds < 0 else ''} YDS".replace("  ", " "), TEXT),
    ]
    step = avail_w / len(metrics)
    for i, (label, value, col) in enumerate(metrics):
        _metric(c, x0 + i * step, x0 + (i + 1) * step, label, value, col)

    # Quiet outlined action instead of the old solid-gold slab.
    btn_w, btn_h = 238, 36
    bx2 = x1 - 16
    bx1 = bx2 - btn_w
    by2 = h - 12
    by1 = by2 - btn_h
    app.range_launch_web_rect = (bx1, by1, bx2, by2)
    c.create_rectangle(bx1, by1, bx2, by2, fill="#0D252D", outline=GOLD, width=1)
    c.create_text((bx1 + bx2) / 2, (by1 + by2) / 2,
                  text="Open 3D WebGPU Range  ↗", fill=GOLD_LIGHT,
                  font=(theme.ui_font(), 9, "bold"), anchor="center")
