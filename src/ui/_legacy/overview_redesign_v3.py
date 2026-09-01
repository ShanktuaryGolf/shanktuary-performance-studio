"""Third-pass Overview: fewer boxes, more atmosphere, clearer cause/effect.

Keeps the useful v2 data visuals, but turns the central workspace into one
continuous instrument surface separated by spacing and hairlines rather than a
matrix of bordered cards.
"""

from __future__ import annotations

import math

import overview_redesign_v2 as v2
import theme

BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")
ORANGE = getattr(theme, "WARN", "#F47A32")
GOOD = getattr(theme, "GOOD", "#39A879")

_values = v2._values


def _mix(a, b, t):
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.BG


ATMOS_1 = _mix(theme.BG, BLUE, .018)
ATMOS_2 = _mix(theme.BG, BLUE, .032)
ATMOS_LINE = _mix(theme.BG, BLUE_LINE, .085)
SOFT_LINE = _mix(theme.HAIRLINE, theme.BG, .38)


def _panel(app, x0, y0, x1, y1, title, subtitle=None):
    """Borderless section heading; spacing does the grouping."""
    c = app.canvas
    c.create_text(x0 + 10, y0 + 11, text=title, fill=theme.TEXT,
                  font=(theme.ui_font(), 10, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x0 + 10, y0 + 29, text=subtitle, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="nw")


# v2 helpers resolve _panel from their own module globals at call time, so this
# lets us reuse their charts while removing the card chrome.
v2._panel = _panel


def _texture(app, x0, y0, x1, y1):
    c = app.canvas
    h = y1 - y0
    # Almost-flat vertical gradation. Enough to keep the canvas from feeling
    # like a single CSS hex, not enough to interfere with charts.
    bands = [ATMOS_2, ATMOS_1, theme.BG, ATMOS_1, theme.BG]
    for i, col in enumerate(bands):
        by0 = y0 + h * i / len(bands)
        by1 = y0 + h * (i + 1) / len(bands)
        c.create_rectangle(x0, by0, x1, by1, fill=col, outline="")

    # Sparse shot-geometry motif: a few long arcs/diagonals, intentionally
    # clipped by the functional UI that draws on top.
    cx = x0 + (x1 - x0) * .52
    cy = y0 + h * .42
    for r in (170, 255, 345):
        c.create_oval(cx - r * 1.55, cy - r * .43, cx + r * 1.55, cy + r * .43,
                      outline=ATMOS_LINE, width=1)
    for offset in (-120, 20, 155):
        c.create_line(x0 + 40, y0 + h * .72 + offset,
                      x1 - 40, y0 + h * .32 + offset,
                      fill=ATMOS_LINE, width=1)


def _draw_strike_compact(app, x0, y0, x1, y1):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "STRIKE")
    head, detail, hcol = app.summarize_strike(app.current_shot)
    if hcol == theme.WARN:
        c.create_text(x1 - 8, y0 + 12, text="EST.", fill=ORANGE,
                      font=(theme.ui_font(), 7, "bold"), anchor="ne")

    face_cx = x0 + (x1 - x0) * .34
    face_cy = y0 + (y1 - y0) * .61
    app._draw_overview_face(face_cx, face_cy,
                            max(64, min(94, (y1 - y0) * .48)))
    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else theme.TEXT
    tx = x0 + (x1 - x0) * .58
    c.create_text(tx, y0 + 50, text=head, fill=col,
                  font=(theme.ui_font(), 12, "bold"), anchor="nw")
    c.create_text(tx, y0 + 72, text=detail, fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7), anchor="nw", width=max(70, int((x1 - tx) - 8)))


def _draw_delivery_compact(app, x0, y0, x1, y1, v):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "CLUB DELIVERY")
    rows = [
        ("Path", f"{abs(v['path']):.1f}° {'in→out' if v['path'] >= 0 else 'out→in'}"),
        ("Face/path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"),
        ("Face/target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"),
        ("Spin axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]
    yy = y0 + 42
    for label, value in rows:
        c.create_text(x0 + 10, yy, text=label.upper(), fill=theme.TEXT_3,
                      font=(theme.ui_font(), 6, "bold"), anchor="nw")
        c.create_text(x0 + 72, yy - 1, text=value, fill=theme.TEXT,
                      font=(theme.ui_font(), 8, "bold"), anchor="nw")
        yy += 20

    # Mini path/face glyph: blue travel direction + orange clubface.
    cx = x0 + (x1 - x0) * .74
    cy = y1 - 34
    span = min(38, (x1 - x0) * .17)
    c.create_line(cx - span, cy, cx + span, cy, fill=theme.GUIDE, dash=(3, 4))
    pdy = -math.tan(math.radians(max(-12, min(12, v['path'])))) * span
    c.create_line(cx - span, cy + pdy, cx + span, cy - pdy,
                  fill=BLUE_LINE, width=2, arrow="last")
    ang = math.radians(max(-16, min(16, v['face_target'])))
    dx, dy = math.sin(ang) * 22, math.cos(ang) * 22
    c.create_line(cx - dx, cy + dy, cx + dx, cy - dy, fill=ORANGE, width=3)


def draw_overview(app, avail_w, h, carry, total, ball_speed, club_speed, smash,
                  launch, spin, apex, offline, descent, hang_time, club_path,
                  face_to_path, spin_axis, face_to_target=0.0, shot_name="",
                  smash_clamped=False, offset_x=0, top_bar_h=52):
    c = app.canvas
    _texture(app, offset_x, top_bar_h, offset_x + avail_w, h)

    app.overview_viewall_rect = None
    app.overview_prev_rect = None
    app.overview_next_rect = None
    app.overview_bar_rects = []

    shots_all = list(app.session_shots)
    shots = v2.v1._club_shots(app)
    v = _values(app.current_shot)
    v.update({"carry": carry, "total": total, "ball": ball_speed, "smash": smash,
              "launch": launch, "spin": spin, "apex": apex, "offline": offline,
              "descent": descent, "hang": hang_time, "path": club_path,
              "face_path": face_to_path, "axis": spin_axis,
              "face_target": face_to_target, "shape": shot_name or v["shape"]})

    margin = max(12, int(avail_w * .013))
    gap = max(14, int(avail_w * .011))
    x0, x1 = offset_x + margin, offset_x + avail_w - margin
    y0 = top_bar_h + 10
    usable = h - y0 - 12

    # Headline band: one continuous surface, not six metric cards.
    top_h = max(104, min(120, int(usable * .16)))
    band_col = _mix(theme.SURFACE, BLUE, .018)
    c.create_rectangle(x0, y0, x1, y0 + top_h, fill=band_col, outline="")
    c.create_line(x0, y0 + top_h, x1, y0 + top_h, fill=SOFT_LINE)
    c.create_rectangle(x0, y0, x0 + 4, y0 + top_h, fill=BLUE, outline="")

    n = len(shots_all)
    idx = app.selected_shot_index + 1 if app.selected_shot_index is not None else n
    identity_w = max(220, min(270, (x1 - x0) * .19))
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

    metrics = [
        ("CARRY", f"{carry:.1f}", "yds"),
        ("BALL SPEED", f"{ball_speed:.1f}", "mph"),
        ("LAUNCH", f"{launch:.1f}°", ""),
        ("SPIN", f"{spin:.0f}", "rpm"),
        ("APEX", f"{apex * 3:.0f}", "ft"),
        ("OFFLINE", v2._side(offline), "yds"),
    ]
    mx0 = x0 + identity_w
    step = (x1 - mx0) / len(metrics)
    vsize = max(18, min(24, int(avail_w / 60)))
    for i, (label, value, unit) in enumerate(metrics):
        xx = mx0 + i * step + 13
        c.create_text(xx, y0 + 21, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8, "bold"), anchor="nw")
        vid = c.create_text(xx, y0 + 45, text=value, fill=theme.TEXT,
                            font=(theme.ui_font(), vsize), anchor="nw")
        if unit:
            bb = c.bbox(vid)
            if bb:
                c.create_text(bb[2] + 5, y0 + 58, text=unit, fill=theme.TEXT_3,
                              font=(theme.ui_font(), 8), anchor="nw")

    # Main instrument field. No boxes: just three regions and two quiet
    # dividers. Result -> Shape -> Cause.
    main_y0 = y0 + top_h + gap
    bottom_min = max(170, int(usable * .26))
    main_h = max(295, min(int(usable * .53), h - main_y0 - bottom_min - gap - 10))
    main_y1 = main_y0 + main_h
    total_w = x1 - x0
    lw, cw = total_w * .43, total_w * .29
    dx0, dx1 = x0, x0 + lw
    sx0, sx1 = dx1 + gap, dx1 + gap + cw
    rx0, rx1 = sx1 + gap, x1

    c.create_line(dx1 + gap / 2, main_y0 + 6, dx1 + gap / 2, main_y1 - 6, fill=SOFT_LINE)
    c.create_line(sx1 + gap / 2, main_y0 + 6, sx1 + gap / 2, main_y1 - 6, fill=SOFT_LINE)

    v2._draw_dispersion(app, dx0, main_y0, dx1, main_y1, shots)
    v2._draw_shape(app, sx0, main_y0, sx1, main_y1, v, shots)

    # Cause region: Strike and Delivery are peers and live next to one another.
    pair_gap = 12
    cause_top_h = main_h * .54
    half = (rx1 - rx0 - pair_gap) / 2
    str_x1 = rx0 + half
    del_x0 = str_x1 + pair_gap
    c.create_line(str_x1 + pair_gap / 2, main_y0 + 8,
                  str_x1 + pair_gap / 2, main_y0 + cause_top_h - 8, fill=SOFT_LINE)
    _draw_strike_compact(app, rx0, main_y0, str_x1, main_y0 + cause_top_h)
    _draw_delivery_compact(app, del_x0, main_y0, rx1, main_y0 + cause_top_h, v)

    flight_y0 = main_y0 + cause_top_h + 12
    c.create_line(rx0, flight_y0 - 6, rx1, flight_y0 - 6, fill=SOFT_LINE)
    v2._draw_flight(app, rx0, flight_y0, rx1, main_y1, v)

    # Bottom context is still dense, but its three zones are separated by
    # whitespace/hairlines rather than boxes.
    by0, by1 = main_y1 + gap, h - 12
    if by1 - by0 >= 145:
        v2._draw_bottom(app, x0, by0, x1, by1, shots)
        bw = x1 - x0
        sw, rw = bw * .25, bw * .48
        sep1 = x0 + sw + 6
        sep2 = x0 + sw + 12 + rw + 6
        c.create_line(sep1, by0 + 8, sep1, by1 - 8, fill=SOFT_LINE)
        c.create_line(sep2, by0 + 8, sep2, by1 - 8, fill=SOFT_LINE)
