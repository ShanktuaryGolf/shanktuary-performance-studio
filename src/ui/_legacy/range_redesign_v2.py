"""Second Range pass: night performance field with perspective + live shot traces.

This stays code-drawn (no scenic bitmap dependency) and preserves the existing
Range interaction contract. The goal is a restrained simulator/range scene that
belongs to the navy/teal/gold Shanktuary design system rather than a flat chart.
"""

from __future__ import annotations

import math
import random
import statistics

from PIL import Image, ImageDraw, ImageOps, ImageTk

import theme

GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_BRIGHT = "#8FD7D3"
TEXT = "#F3F6FA"
TEXT_2 = "#B3BEC2"
TEXT_3 = "#70868C"

SKY_TOP = "#091B28"
SKY_BOTTOM = "#0B2631"
GROUND = "#071713"
FAIRWAY = "#0A211E"
FAIRWAY_EDGE = "#2A5A60"
GRID = "#315C63"
MUTED_TRACE = "#2F5960"
MUTED_DOT = "#4D7980"


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    aa, bb = _rgb(a), _rgb(b)
    vals = tuple(round(aa[i] + (bb[i] - aa[i]) * t) for i in range(3))
    return "#" + "".join(f"{v:02X}" for v in vals)


def _scene_background(app, w, h, horizon_rel):
    """Cached twilight range environment; intentionally abstract, not scenic art."""
    key = (int(w), int(h), int(horizon_rel), "range-v2-night")
    if getattr(app, "_range_v2_bg_key", None) == key:
        return app._range_v2_bg_img

    iw, ih = max(1, int(w)), max(1, int(h))
    horizon = max(80, min(ih - 120, int(horizon_rel)))
    img = Image.new("RGB", (iw, ih), _rgb(SKY_TOP))
    d = ImageDraw.Draw(img, "RGBA")

    # Twilight sky: subtle vertical + horizontal depth.
    top = _rgb(SKY_TOP)
    bottom = _rgb(SKY_BOTTOM)
    left = _rgb("#0C2531")
    right = _rgb("#071A24")
    for y in range(0, horizon + 1, 2):
        ty = y / max(1, horizon)
        for x in range(0, iw, 8):
            tx = x / max(1, iw - 1)
            v = tuple(top[i] + (bottom[i] - top[i]) * ty for i in range(3))
            q = tuple(left[i] + (right[i] - left[i]) * tx for i in range(3))
            col = tuple(round(v[i] * .78 + q[i] * .22) for i in range(3))
            d.rectangle((x, y, min(iw, x + 8), min(horizon, y + 2)), fill=col)

    # Sparse pinpoints keep the top from becoming a dead flat field.
    rng = random.Random(2202)
    for _ in range(max(30, iw // 26)):
        x = rng.randrange(0, iw)
        y = rng.randrange(12, max(13, horizon - 34))
        a = rng.randint(16, 46)
        d.point((x, y), fill=(180, 221, 220, a))

    # Three mountain layers. The irregular silhouettes provide depth while
    # staying dark enough that the live golf geometry remains dominant.
    def ridge_points(base_y, amp, phase, scale):
        pts = [(0, ih)]
        for x in range(-20, iw + 30, 24):
            y = (
                base_y
                - amp * (.45 + .55 * abs(math.sin(x / (132.0 * scale) + phase)))
                - amp * .24 * math.sin(x / (57.0 * scale) + phase * 1.7)
            )
            pts.append((x, y))
        pts.extend([(iw, ih), (0, ih)])
        return pts

    d.polygon(ridge_points(horizon + 18, 30, .4, 1.25), fill=(16, 42, 52, 255))
    d.polygon(ridge_points(horizon + 28, 24, 1.2, .92), fill=(11, 34, 42, 255))
    d.polygon(ridge_points(horizon + 38, 20, 2.1, .70), fill=(8, 27, 33, 255))

    # Ground field.
    d.rectangle((0, horizon, iw, ih), fill=_rgb(GROUND) + (255,))

    # Broad center fairway/range surface with subtle longitudinal texture.
    far_half = iw * .17
    near_half = iw * .54
    cx = iw / 2
    fairway = [
        (cx - far_half, horizon), (cx + far_half, horizon),
        (cx + near_half, ih), (cx - near_half, ih),
    ]
    d.polygon(fairway, fill=_rgb(FAIRWAY) + (255,))

    # Side-bank topo cues: faint, non-crossing contour families clipped by eye
    # to the rough zones. This echoes the brand header without turning the field
    # into a literal map.
    for side in (-1, 1):
        side_center = iw * (.16 if side < 0 else .84)
        for band in range(9):
            base_y = horizon + 58 + band * max(20, (ih - horizon) / 13)
            pts = []
            for step in range(45):
                t = step / 44.0
                x = side_center + side * (t - .5) * iw * .30
                y = base_y + 8 * math.sin(t * math.tau + band * .38) + 3 * math.sin(t * math.tau * 2 + .7)
                # Keep contours out of the central performance corridor.
                edge = cx + side * (far_half + (near_half - far_half) * max(0, min(1, (y - horizon) / max(1, ih - horizon))))
                if side < 0:
                    x = min(x, edge - 18)
                else:
                    x = max(x, edge + 18)
                pts.append((x, y))
            d.line(pts, fill=(88, 183, 180, 11), width=1)

    # Soft lane texture down the fairway.
    for frac in (.28, .50, .72):
        near_x = cx + (frac - .5) * near_half * 2
        far_x = cx + (frac - .5) * far_half * 2
        d.line((near_x, ih, far_x, horizon), fill=(88, 183, 180, 13), width=1)

    try:
        noise = Image.effect_noise((iw, ih), 9).convert("L")
        noise_col = ImageOps.colorize(noise, black="#06100F", white="#17333A")
        img = Image.blend(img, noise_col, .015)
    except Exception:
        pass

    app._range_v2_bg_img = ImageTk.PhotoImage(img)
    app._range_v2_bg_key = key
    return app._range_v2_bg_img


def _shot_values(shot):
    shot = shot or {}
    ogc = shot.get("open_golf_coach", {}) or {}
    us = ogc.get("us_customary_units", {}) or {}
    carry = float(us.get("carry_distance_yards") or shot.get("carry_distance_yards") or 0.0)
    offline = float(us.get("offline_distance_yards") or shot.get("offline_distance_yards") or 0.0)
    apex = us.get("apex_height_yards") or us.get("max_height_yards")
    if apex is None:
        apex_m = ogc.get("apex_height_meters") or ogc.get("max_height_meters")
        apex = float(apex_m or 0.0) * 1.09361
    return carry, offline, float(apex or 0.0)


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
    c.create_line(x1, 65, x1, 102, fill="#1E4149")


def draw_range(app, avail_w, h, carry_yds, total_yds, ball_speed, club_speed,
               apex_yds, offline_yds, total_spin, vert_launch, horiz_launch,
               offset_x=0):
    c = app.canvas
    app.range_launch_web_rect = None

    x0, x1 = offset_x, offset_x + avail_w
    top_y = 52
    metric_bottom = 112
    horizon_y = max(metric_bottom + 130, top_y + int((h - top_y) * .28))
    ground_y = h - 18
    cx = (x0 + x1) / 2

    c.create_image(
        x0, top_y,
        image=_scene_background(app, avail_w, h - top_y, horizon_y - top_y),
        anchor="nw",
    )

    field_h = ground_y - horizon_y
    far_half = avail_w * .17
    near_half = avail_w * .54

    def y_for_distance(dist):
        # Perceptual perspective rather than linear charting: distant yardages
        # compress toward the horizon while the scoring zone stays readable.
        frac = max(0.0, min(1.0, dist / 350.0)) ** .78
        return ground_y - frac * field_h * .965

    def half_width_at(y):
        t = max(0.0, min(1.0, (y - horizon_y) / max(1.0, field_h)))
        return far_half + (near_half - far_half) * t

    def x_for_offline(off, y):
        hw = half_width_at(y)
        return cx + max(-1.0, min(1.0, off / 42.0)) * hw * .80

    # Performance corridor edges and internal lanes.
    c.create_line(cx - near_half, ground_y, cx - far_half, horizon_y,
                  fill=FAIRWAY_EDGE, width=2)
    c.create_line(cx + near_half, ground_y, cx + far_half, horizon_y,
                  fill=FAIRWAY_EDGE, width=2)
    c.create_line(cx, ground_y, cx, horizon_y,
                  fill=_mix(TEAL_LINE, GROUND, .40), width=1, dash=(5, 7))
    for frac in (-.48, .48):
        c.create_line(cx + near_half * frac, ground_y,
                      cx + far_half * frac, horizon_y,
                      fill=_mix(GRID, GROUND, .38), width=1)

    # Yard grid: center placards for precision, side labels only at major marks.
    for dist in range(50, 351, 50):
        yy = y_for_distance(dist)
        hw = half_width_at(yy) * .88
        major = dist % 100 == 0
        c.create_line(cx - hw, yy, cx + hw, yy,
                      fill=_mix(GRID, GROUND, .17 if major else .34),
                      dash=(3, 7), width=1)
        box_w = 40
        c.create_rectangle(cx - box_w / 2, yy - 9, cx + box_w / 2, yy + 9,
                           fill="#10272E", outline="#31565D")
        c.create_text(cx, yy, text=str(dist), fill=TEAL_TEXT,
                      font=(theme.ui_font(), 7, "bold"), anchor="center")
        if major:
            side_x = cx + hw + 26
            c.create_text(side_x, yy, text=str(dist), fill=_mix(TEXT_2, GROUND, .34),
                          font=(theme.ui_font(), 10), anchor="w")

    shots = _club_session_shots(app)[-14:]
    numeric = []
    for shot in shots:
        carry, off, shot_apex = _shot_values(shot)
        if carry > 0:
            numeric.append((carry, off, shot_apex, shot))

    # Session landing zone / confidence cue. This is deliberately subtle and
    # computed from the same club-only shot set used for historical traces.
    if len(numeric) >= 3:
        carries = [v[0] for v in numeric]
        offs = [v[1] for v in numeric]
        mc, mo = statistics.mean(carries), statistics.mean(offs)
        sc = statistics.pstdev(carries)
        so = statistics.pstdev(offs)
        cy = y_for_distance(mc)
        cx_land = x_for_offline(mo, cy)
        y_top = y_for_distance(mc + max(2.0, sc * 2.0))
        y_bot = y_for_distance(mc - max(2.0, sc * 2.0))
        x_left = x_for_offline(mo - max(2.0, so * 2.0), cy)
        x_right = x_for_offline(mo + max(2.0, so * 2.0), cy)
        c.create_oval(x_left, y_top, x_right, y_bot,
                      fill="", outline=_mix(TEAL_LINE, GROUND, .34), width=1)
        # second quiet ring gives the scoring zone some depth without a glow.
        c.create_oval(
            cx_land - (x_right - x_left) * .66,
            cy - (y_bot - y_top) * .66,
            cx_land + (x_right - x_left) * .66,
            cy + (y_bot - y_top) * .66,
            fill="", outline=_mix(TEAL_LINE, GROUND, .55), width=1,
        )

    # Historical flights and landing dots. Draw current last so it owns the scene.
    def draw_flight(carry, off, apex, current=False):
        if carry <= 0:
            return
        land_y = y_for_distance(carry)
        land_x = x_for_offline(off, land_y)
        pts = []
        steps = 34
        apex_px = max(34.0, min(150.0, (apex or apex_yds or 30.0) * 3.0))
        for i in range(steps + 1):
            t = i / steps
            dist = carry * t
            base_y = y_for_distance(dist)
            xx = cx + (land_x - cx) * (t ** 1.45)
            lift = apex_px * (math.sin(math.pi * t) ** 1.22)
            yy = base_y - lift
            pts.extend((xx, yy))
        if current:
            c.create_line(*pts, fill=GOLD, width=3, smooth=True)
            c.create_oval(land_x - 8, land_y - 8, land_x + 8, land_y + 8,
                          fill=GOLD, outline=GOLD_LIGHT, width=1)
            c.create_oval(land_x - 13, land_y - 13, land_x + 13, land_y + 13,
                          fill="", outline=TEAL_LINE, width=2)
            label = f"{carry:.1f} YDS"
            lx = land_x + 42 if land_x < cx + avail_w * .28 else land_x - 42
            c.create_rectangle(lx - 42, land_y - 36, lx + 42, land_y - 17,
                               fill="#0D242B", outline=GOLD)
            c.create_text(lx, land_y - 26, text=label, fill=GOLD_LIGHT,
                          font=(theme.ui_font(), 8, "bold"), anchor="center")
        else:
            c.create_line(*pts, fill=MUTED_TRACE, width=1, smooth=True)
            c.create_oval(land_x - 3, land_y - 3, land_x + 3, land_y + 3,
                          fill=MUTED_DOT, outline="")

    current_row = None
    for carry, off, apex, shot in numeric:
        if shot is app.current_shot:
            current_row = (carry, off, apex)
        else:
            draw_flight(carry, off, apex, current=False)
    if current_row:
        draw_flight(*current_row, current=True)
    else:
        draw_flight(carry_yds, offline_yds, apex_yds, current=True)

    # Top metrics stay visually integrated with the shell and Shot page.
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

    # Secondary action: visible, but never louder than the live shot.
    btn_w, btn_h = 248, 38
    bx2 = x1 - 16
    bx1 = bx2 - btn_w
    by2 = h - 12
    by1 = by2 - btn_h
    app.range_launch_web_rect = (bx1, by1, bx2, by2)
    c.create_rectangle(bx1, by1, bx2, by2, fill="#0B2027", outline=GOLD, width=1)
    c.create_text((bx1 + bx2) / 2, (by1 + by2) / 2,
                  text="Open 3D WebGPU Range  ↗", fill=GOLD_LIGHT,
                  font=(theme.ui_font(), 9, "bold"), anchor="center")
