"""Design-branch Overview renderer for the live between-shots dashboard.

The design launcher delegates Overview rendering here so visual experiments
stay isolated from the production monolith until the direction is ready.
"""

from __future__ import annotations

import math
import statistics

import theme

GOOD = getattr(theme, "GOOD", "#39A879")
ORANGE = getattr(theme, "WARN", "#F47A32")
RED = getattr(theme, "DANGER", "#E34A4A")
BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")


def _values(shot):
    ogc = (shot or {}).get("open_golf_coach", {}) or {}
    us = ogc.get("us_customary_units", {}) or {}
    return {
        "carry": float(us.get("carry_distance_yards") or 0.0),
        "total": float(us.get("total_distance_yards") or 0.0),
        "ball": float(us.get("ball_speed_mph") or 0.0),
        "smash": float(ogc.get("smash_factor") or 0.0),
        "launch": float((shot or {}).get("vertical_launch_angle_degrees") or 0.0),
        "hlaunch": float((shot or {}).get("horizontal_launch_angle_degrees") or 0.0),
        "spin": float(ogc.get("total_spin_rpm") or (shot or {}).get("total_spin_rpm") or 0.0),
        "axis": float(ogc.get("spin_axis_degrees") or 0.0),
        "apex": float(us.get("peak_height_yards") or 0.0),
        "offline": float(us.get("offline_distance_yards") or 0.0),
        "descent": float(ogc.get("descent_angle_degrees") or 0.0),
        "hang": float(ogc.get("hang_time_seconds") or 0.0),
        "path": float(ogc.get("club_path_degrees") or 0.0),
        "face_path": float(ogc.get("club_face_to_path_degrees") or 0.0),
        "face_target": float(ogc.get("club_face_to_target_degrees") or 0.0),
        "shape": str(ogc.get("shot_name") or "Straight"),
    }


def _movement(v):
    start = math.tan(math.radians(v["hlaunch"])) * v["carry"]
    return start, v["offline"] - start


def _side(v, threshold=0.12):
    if abs(v) <= threshold:
        return "0.0"
    return f"{abs(v):.1f}{'R' if v > 0 else 'L'}"


def _club_shots(app):
    club = (app.current_shot or {}).get("club") or app.current_club
    shots = [s for s in app.session_shots if not s.get("excluded", False)]
    subset = [s for s in shots if s.get("club") == club]
    return subset or shots


def _shape_consistency(shots, movement):
    def cls(v):
        if v > 1.5:
            return 1
        if v < -1.5:
            return -1
        return 0
    vals = [_movement(_values(s))[1] for s in shots[-15:] if _values(s)["carry"] > 0]
    if not vals:
        return 0, 0.0
    same = sum(1 for v in vals if cls(v) == cls(movement))
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return round(100 * same / len(vals)), std


def _panel(app, x0, y0, x1, y1, title, subtitle=None):
    c = app.canvas
    c.create_rectangle(x0, y0, x1, y1, fill=theme.SURFACE,
                       outline=theme.HAIRLINE, width=1)
    c.create_text(x0 + 14, y0 + 13, text=title, fill=theme.TEXT,
                  font=(theme.ui_font(), 9, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x0 + 14, y0 + 29, text=subtitle, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7), anchor="nw")


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    _panel(app, x0, y0, x1, y1, "DISPERSION", f"{club} · carry landing pattern")
    points = [(_values(s), s) for s in shots]
    points = [(v, s) for v, s in points if v["carry"] > 0]
    if not points:
        return
    left, right = x0 + 45, x1 - 18
    top, bottom = y0 + 50, y1 - 38
    carries = [v["carry"] for v, _ in points]
    offs = [v["offline"] for v, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0
    cmin = min(carries + [mc - max(5, sc * 3)])
    cmax = max(carries + [mc + max(5, sc * 3)])
    pad = max(3, (cmax - cmin) * .15)
    cmin, cmax = cmin - pad, cmax + pad
    omax = max(6, max(abs(v) for v in offs) * 1.35, abs(mo) + so * 3)
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    for frac in (.25, .5, .75):
        gy = top + ph * frac
        c.create_line(left, gy, right, gy, fill=theme.HAIRLINE, dash=(2, 5))
    tx = sx(0)
    c.create_line(tx, top, tx, bottom, fill=theme.GUIDE, dash=(4, 5))
    c.create_text(left, bottom + 12, text=f"{omax:.0f}L", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="n")
    c.create_text(tx, bottom + 12, text="TARGET", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="n")
    c.create_text(right, bottom + 12, text=f"{omax:.0f}R", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="n")

    c.create_oval(sx(mo - 2 * max(1, so)), sy(mc + 2 * max(1.5, sc)),
                  sx(mo + 2 * max(1, so)), sy(mc - 2 * max(1.5, sc)),
                  outline=BLUE_LINE, width=1, dash=(5, 5))
    for v, shot in points:
        px, py = sx(v["offline"]), sy(v["carry"])
        if shot is app.current_shot:
            c.create_oval(px - 10, py - 10, px + 10, py + 10,
                          outline=BLUE_LINE, width=2)
            c.create_oval(px - 5, py - 5, px + 5, py + 5,
                          fill=BLUE, outline=theme.TEXT)
        else:
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill="#4B607A", outline="")
    c.create_text(x0 + 14, y1 - 13,
                  text="● current   ● session   ╌ 2σ pattern",
                  fill=theme.TEXT_3, font=(theme.ui_font(), 7), anchor="sw")


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "SHOT SHAPE & MOVEMENT")
    start, move = _movement(v)
    consistency, move_std = _shape_consistency(shots, move)
    c.create_text(x0 + 16, y0 + 42, text=v["shape"], fill=theme.TEXT,
                  font=(theme.ui_font(), 18, "bold"), anchor="nw")
    direction = "Right to left" if move < -1.5 else ("Left to right" if move > 1.5 else "Minimal curve")
    c.create_text(x0 + 16, y0 + 69, text=direction, fill=theme.TEXT_2,
                  font=(theme.ui_font(), 8), anchor="nw")

    ax0, ax1 = x0 + 22, x1 - 22
    ay = y0 + min(160, (y1 - y0) * .47)
    scale = max(6, abs(start) * 1.25, abs(v["offline"]) * 1.25, abs(move) * .8)
    mid = (ax0 + ax1) / 2
    span = (ax1 - ax0) / 2
    px = lambda val: mid + val / scale * span
    sx, ex, tx = px(start), px(v["offline"]), px(0)
    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE)
    c.create_line(tx, ay - 26, tx, ay + 27, fill=theme.HAIRLINE, dash=(2, 4))
    c.create_text(tx, ay + 29, text="TARGET", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="n")
    c.create_oval(sx - 5, ay - 5, sx + 5, ay + 5, fill=BLUE_LINE, outline="")
    c.create_oval(ex - 6, ay - 6, ex + 6, ay + 6,
                  fill=theme.TEXT, outline=BLUE_LINE, width=2)
    c.create_line(sx, ay, ex, ay, fill=BLUE, width=3,
                  arrow="last" if ex >= sx else "first", arrowshape=(10, 12, 5))
    c.create_text(sx, ay - 27, text=f"START  {_side(start)} yds",
                  fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="s")
    c.create_text((sx + ex) / 2, ay - 9, text=f"MOVED {_side(move, .4)} yds",
                  fill=BLUE_TEXT, font=(theme.ui_font(), 10, "bold"), anchor="s")
    c.create_text(ex, ay + 13, text=f"LANDED  {_side(v['offline'])} yds",
                  fill=theme.TEXT, font=(theme.ui_font(), 8, "bold"), anchor="n")

    c.create_text(x0 + 16, y1 - 61, text="SHAPE CONSISTENCY",
                  fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="nw")
    c.create_text(x1 - 16, y1 - 65, text=f"{consistency}%", fill=theme.TEXT,
                  font=(theme.ui_font(), 15, "bold"), anchor="ne")
    bx0, bx1, by = x0 + 16, x1 - 16, y1 - 31
    c.create_rectangle(bx0, by, bx1, by + 7, fill=theme.SURFACE_2, outline="")
    c.create_rectangle(bx0, by, bx0 + (bx1 - bx0) * consistency / 100, by + 7,
                       fill=BLUE, outline="")
    c.create_text(x0 + 16, y1 - 12,
                  text=f"Last {min(15, len(shots))} shots · movement σ {move_std:.1f} yds",
                  fill=theme.TEXT_3, font=(theme.ui_font(), 7), anchor="sw")


def _draw_strike(app, x0, y0, x1, y1):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "STRIKE")
    head, detail, hcol = app.summarize_strike(app.current_shot)
    if hcol == theme.WARN:
        c.create_text(x1 - 14, y0 + 14, text="ESTIMATED", fill=ORANGE,
                      font=(theme.ui_font(), 7, "bold"), anchor="ne")
    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else theme.TEXT
    c.create_text(x1 - 14, y0 + 42, text=head, fill=col,
                  font=(theme.ui_font(), 14, "bold"), anchor="ne")
    c.create_text(x1 - 14, y0 + 64, text=detail, fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="ne")
    app._draw_overview_face((x0 + x1) / 2, y0 + (y1 - y0) * .68,
                            max(62, min(100, (y1 - y0) * .43)))


def _draw_flight(app, x0, y0, x1, y1, v):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "BALL FLIGHT")
    rows = [("Launch", f"{v['launch']:.1f}°"), ("Apex", f"{v['apex'] * 3:.0f} ft"),
            ("Descent", f"{v['descent']:.1f}°"), ("Hang", f"{v['hang']:.1f} s")]
    yy = y0 + 40
    for label, val in rows:
        c.create_text(x0 + 14, yy, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7), anchor="nw")
        c.create_text(x0 + 82, yy, text=val, fill=theme.TEXT,
                      font=(theme.ui_font(), 8, "bold"), anchor="nw")
        yy += 19
    gx0, gx1 = x0 + max(125, (x1 - x0) * .47), x1 - 12
    gy0, gy1 = y0 + 42, y1 - 18
    pts = []
    for i in range(21):
        t = i / 20
        pts.extend([gx0 + t * (gx1 - gx0), gy1 - 4 * t * (1 - t) * (gy1 - gy0) * .82])
    c.create_line(pts, fill=BLUE_LINE, width=2, smooth=True)
    c.create_line(gx0, gy1, gx1, gy1, fill=theme.GUIDE, dash=(3, 4))


def _draw_delivery(app, x0, y0, x1, y1, v):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "CLUB DELIVERY")
    rows = [
        ("Club path", f"{abs(v['path']):.1f}° {'in-to-out' if v['path'] >= 0 else 'out-to-in'}"),
        ("Face to path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"),
        ("Face to target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"),
        ("Spin axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]
    yy = y0 + 39
    for label, val in rows:
        c.create_text(x0 + 14, yy, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7), anchor="nw")
        c.create_text(x0 + 99, yy, text=val, fill=theme.TEXT,
                      font=(theme.ui_font(), 8), anchor="nw")
        yy += 18
    cx, cy = x1 - max(45, (x1 - x0) * .15), (y0 + y1) / 2 + 7
    span = min(50, (y1 - y0) * .27)
    c.create_line(cx - span, cy, cx + span, cy, fill=theme.GUIDE, dash=(3, 4))
    pdy = -math.tan(math.radians(max(-12, min(12, v['path'])))) * span
    c.create_line(cx - span, cy + pdy, cx + span, cy - pdy,
                  fill=BLUE_LINE, width=2, arrow="last")
    ang = math.radians(max(-16, min(16, v['face_target'])))
    dx, dy = math.sin(ang) * 27, math.cos(ang) * 27
    c.create_line(cx - dx, cy + dy, cx + dx, cy - dy, fill=ORANGE, width=3)


def _spark(c, x0, y0, x1, y1, vals, color):
    if len(vals) < 2:
        return
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo -= 1
        hi += 1
    pts = []
    for i, val in enumerate(vals):
        pts += [x0 + i / (len(vals) - 1) * (x1 - x0),
                y1 - (val - lo) / (hi - lo) * (y1 - y0)]
    c.create_line(pts, fill=color, width=1, smooth=True)


def _draw_bottom(app, x0, y0, x1, y1, shots):
    c = app.canvas
    gap = 12
    w = x1 - x0
    sw, rw = w * .25, w * .48
    sx0, sx1 = x0, x0 + sw
    rx0, rx1 = sx1 + gap, sx1 + gap + rw
    tx0, tx1 = rx1 + gap, x1

    _panel(app, sx0, y0, sx1, y1, "SESSION SUMMARY")
    vals = [_values(s) for s in shots]
    vals = [v for v in vals if v["carry"] > 0]
    if vals:
        avg = lambda key: statistics.mean(v[key] for v in vals)
        stats = [("SHOTS", str(len(vals))), ("AVG CARRY", f"{avg('carry'):.1f} yds"),
                 ("AVG BALL", f"{avg('ball'):.1f} mph"), ("AVG LAUNCH", f"{avg('launch'):.1f}°"),
                 ("AVG SPIN", f"{avg('spin'):.0f} rpm"), ("AVG SMASH", f"{avg('smash'):.2f}")]
        mid = (sx0 + sx1) / 2
        for i, (lb, val) in enumerate(stats):
            col, row = i % 2, i // 2
            xx = sx0 + 14 if col == 0 else mid + 5
            yy = y0 + 47 + row * 46
            c.create_text(xx, yy, text=lb, fill=theme.TEXT_3,
                          font=(theme.ui_font(), 7), anchor="nw")
            c.create_text(xx, yy + 17, text=val, fill=theme.TEXT,
                          font=(theme.ui_font(), 9, "bold"), anchor="nw")

    _panel(app, rx0, y0, rx1, y1, "RECENT SHOTS")
    recent = shots[-5:][::-1]
    headers = ["#", "CARRY", "TOTAL", "BALL", "LAUNCH", "SPIN", "OFF", "SHAPE"]
    widths = [.06, .12, .12, .12, .12, .13, .13, .20]
    tx = rx0 + 12
    tw = rx1 - rx0 - 24
    xx = tx
    for head, frac in zip(headers, widths):
        c.create_text(xx, y0 + 40, text=head, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 6), anchor="nw")
        xx += tw * frac
    row_y = y0 + 63
    for shot in recent:
        v = _values(shot)
        selected = shot is app.current_shot
        try:
            idx = app.session_shots.index(shot)
        except ValueError:
            idx = 0
        if selected:
            c.create_rectangle(tx - 5, row_y - 4, rx1 - 9, row_y + 17,
                               fill=theme.ACCENT_DEEP, outline="")
        app.overview_bar_rects.append((tx - 5, row_y - 4, rx1 - 9, row_y + 19, idx))
        row = [str(idx + 1), f"{v['carry']:.1f}", f"{v['total']:.1f}", f"{v['ball']:.1f}",
               f"{v['launch']:.1f}°", f"{v['spin']:.0f}", _side(v['offline']), v['shape']]
        xx = tx
        for text, frac in zip(row, widths):
            c.create_text(xx, row_y, text=text,
                          fill=theme.TEXT if selected else theme.TEXT_2,
                          font=(theme.ui_font(), 7, "bold" if selected else "normal"), anchor="nw")
            xx += tw * frac
        row_y += 26
    link = c.create_text((rx0 + rx1) / 2, y1 - 14, text="View all shots in Table  ›",
                         fill=BLUE_TEXT, font=(theme.ui_font(), 8), anchor="s")
    bb = c.bbox(link)
    if bb:
        app.overview_viewall_rect = (bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6)

    _panel(app, tx0, y0, tx1, y1, "TENDENCIES", f"Last {min(15, len(shots))} shots")
    series = [_values(s) for s in shots[-15:]]
    starts = [_movement(v)[0] for v in series]
    moves = [_movement(v)[1] for v in series]
    offs = [v["offline"] for v in series]
    carries = [v["carry"] for v in series]
    cons = []
    for i, mv in enumerate(moves):
        cons.append(_shape_consistency(shots[:max(1, len(shots) - len(series) + i + 1)], mv)[0])
    rows = [("Start direction", starts, BLUE_LINE), ("Curve movement", moves, GOOD),
            ("Offline", offs, ORANGE), ("Carry", carries, BLUE_TEXT),
            ("Shape consistency", cons, getattr(theme, "GOLD", "#C89A4A"))]
    yy = y0 + 52
    for label, vals_, col in rows:
        c.create_text(tx0 + 14, yy, text=label, fill=theme.TEXT_2,
                      font=(theme.ui_font(), 7), anchor="nw")
        if vals_:
            val = f"{vals_[-1]:.0f}%" if label == "Shape consistency" else (
                f"{vals_[-1]:.1f}" if label == "Carry" else _side(vals_[-1], .2))
            c.create_text(tx0 + (tx1 - tx0) * .52, yy, text=val, fill=theme.TEXT,
                          font=(theme.ui_font(), 7, "bold"), anchor="nw")
            _spark(c, tx0 + (tx1 - tx0) * .66, yy - 1, tx1 - 12, yy + 12, vals_, col)
        yy += 29


def draw_overview(app, avail_w, h, carry, total, ball_speed, club_speed, smash,
                  launch, spin, apex, offline, descent, hang_time, club_path,
                  face_to_path, spin_axis, face_to_target=0.0, shot_name="",
                  smash_clamped=False, offset_x=0, top_bar_h=52):
    c = app.canvas
    c.create_rectangle(offset_x, top_bar_h, offset_x + avail_w, h,
                       fill=theme.BG, outline="")
    app.overview_viewall_rect = None
    app.overview_prev_rect = None
    app.overview_next_rect = None
    app.overview_bar_rects = []

    shots_all = list(app.session_shots)
    shots = _club_shots(app)
    v = _values(app.current_shot)
    v.update({"carry": carry, "total": total, "ball": ball_speed, "smash": smash,
              "launch": launch, "spin": spin, "apex": apex, "offline": offline,
              "descent": descent, "hang": hang_time, "path": club_path,
              "face_path": face_to_path, "axis": spin_axis,
              "face_target": face_to_target, "shape": shot_name or v["shape"]})

    margin = max(10, int(avail_w * .012))
    gap = max(9, int(avail_w * .009))
    x0, x1 = offset_x + margin, offset_x + avail_w - margin
    y0 = top_bar_h + 10
    usable = h - y0 - 12

    top_h = max(108, min(126, int(usable * .17)))
    c.create_rectangle(x0, y0, x1, y0 + top_h, fill=theme.SURFACE,
                       outline=theme.HAIRLINE)
    c.create_rectangle(x0, y0, x0 + 4, y0 + top_h, fill=BLUE, outline="")
    n = len(shots_all)
    idx = app.selected_shot_index + 1 if app.selected_shot_index is not None else n
    identity_w = max(220, min(280, (x1 - x0) * .20))
    ix = x0 + 18
    club = ((app.current_shot or {}).get("club") or app.current_club).upper()
    c.create_text(ix, y0 + 17, text=f"SHOT {idx}  ·  {club}", fill=BLUE_TEXT,
                  font=(theme.ui_font(), 8, "bold"), anchor="nw")
    c.create_text(ix, y0 + 43, text=(shot_name or "Straight").upper(), fill=theme.TEXT,
                  font=(theme.ui_font(), 19, "bold"), anchor="nw")

    cur = app.selected_shot_index if app.selected_shot_index is not None else n - 1
    for j, (glyph, delta) in enumerate((("‹", -1), ("›", 1))):
        bx = x0 + identity_w - 58 + j * 28
        live = 0 <= cur + delta < n
        c.create_text(bx + 10, y0 + top_h - 20, text=glyph,
                      fill=theme.TEXT_2 if live else theme.TEXT_3,
                      font=(theme.ui_font(), 11), anchor="center")
        rect = (bx, y0 + top_h - 30, bx + 20, y0 + top_h - 10) if live else None
        if delta < 0:
            app.overview_prev_rect = rect
        else:
            app.overview_next_rect = rect

    metrics = [("CARRY", f"{carry:.1f}", "yds"), ("BALL SPEED", f"{ball_speed:.1f}", "mph"),
               ("LAUNCH ANGLE", f"{launch:.1f}°", ""), ("SPIN RATE", f"{spin:.0f}", "rpm"),
               ("APEX", f"{apex * 3:.0f}", "ft"),
               ("OFFLINE", _side(offline), "yds")]
    mx0 = x0 + identity_w
    step = (x1 - mx0) / len(metrics)
    vsize = max(18, min(25, int(avail_w / 58)))
    for i, (label, value, unit) in enumerate(metrics):
        xx = mx0 + i * step + 14
        c.create_text(xx, y0 + 21, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="nw")
        vid = c.create_text(xx, y0 + 44, text=value, fill=theme.TEXT,
                            font=(theme.ui_font(), vsize), anchor="nw")
        if unit:
            bb = c.bbox(vid)
            if bb:
                c.create_text(bb[2] + 5, y0 + 58, text=unit, fill=theme.TEXT_3,
                              font=(theme.ui_font(), 8), anchor="nw")
        if i < len(metrics) - 1:
            c.create_line(mx0 + (i + 1) * step, y0 + 20,
                          mx0 + (i + 1) * step, y0 + 83, fill=theme.HAIRLINE)

    main_y0 = y0 + top_h + gap
    bottom_min = max(170, int(usable * .27))
    main_h = max(285, min(int(usable * .51), h - main_y0 - bottom_min - gap - 10))
    main_y1 = main_y0 + main_h
    total_w = x1 - x0
    lw, cw = total_w * .43, total_w * .29
    dx0, dx1 = x0, x0 + lw
    sx0, sx1 = dx1 + gap, dx1 + gap + cw
    rx0, rx1 = sx1 + gap, x1
    _draw_dispersion(app, dx0, main_y0, dx1, main_y1, shots)
    _draw_shape(app, sx0, main_y0, sx1, main_y1, v, shots)

    rg = 10
    rh = main_y1 - main_y0
    strike_h, flight_h = rh * .34, rh * .33
    _draw_strike(app, rx0, main_y0, rx1, main_y0 + strike_h)
    fy0 = main_y0 + strike_h + rg
    fy1 = fy0 + flight_h - rg
    _draw_flight(app, rx0, fy0, rx1, fy1, v)
    _draw_delivery(app, rx0, fy1 + rg, rx1, main_y1, v)

    by0, by1 = main_y1 + gap, h - 12
    if by1 - by0 >= 145:
        _draw_bottom(app, x0, by0, x1, by1, shots)
