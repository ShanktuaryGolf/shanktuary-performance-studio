"""Fifth-pass Overview: current-shot clarity over dashboard density.

This pass keeps the accepted v4 visual language but removes two redundant
areas now that Recent Shots lives in the left rail:
- no miniature Ball Flight panel
- no duplicate Recent Shots table at the bottom

It also makes the top ribbon more useful between shots by pairing Carry/Total
and Ball/Club speed, enlarging labels/units, and giving shot number + club more
presence. The reclaimed bottom area becomes session consistency/trend context.
"""

from __future__ import annotations

import statistics

import overview_redesign_v4 as v4
import theme

BLUE = v4.BLUE
BLUE_LINE = v4.BLUE_LINE
BLUE_TEXT = v4.BLUE_TEXT
GOOD = v4.GOOD
ORANGE = v4.ORANGE
GOLD = getattr(theme, "GOLD", "#C89A4A")
SOFT_LINE = v4.SOFT_LINE
RIBBON = v4.RIBBON

_values = v4._values
_movement = v4._movement
_side = v4._side
_shape_consistency = v4._shape_consistency
_ui_font = v4._ui_font
_mix = v4._mix


def _club_speed(shot):
    ogc = (shot or {}).get("open_golf_coach", {}) or {}
    us = ogc.get("us_customary_units", {}) or {}
    return float(us.get("club_speed_mph") or 0.0)


def _draw_pair_metric(c, x0, y0, x1, label, value, unit,
                      secondary_label, secondary_value, secondary_unit):
    """One primary metric with a quieter companion directly underneath."""
    c.create_text(x0, y0, text=label, fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    vid = c.create_text(x0, y0 + 29, text=value, fill=theme.TEXT,
                        font=(_ui_font(), 29, "bold"), anchor="nw")
    bb = c.bbox(vid)
    if unit and bb:
        c.create_text(bb[2] + 7, y0 + 49, text=unit, fill=theme.TEXT_2,
                      font=(_ui_font(), 11, "bold"), anchor="nw")

    line_y = y0 + 77
    c.create_line(x0, line_y, x1 - 12, line_y, fill=SOFT_LINE)
    c.create_text(x0, line_y + 12, text=secondary_label, fill=theme.TEXT_3,
                  font=(_ui_font(), 9), anchor="nw")
    sid = c.create_text(x0 + 58, line_y + 10, text=secondary_value, fill=theme.TEXT_2,
                        font=(_ui_font(), 13, "bold"), anchor="nw")
    sbb = c.bbox(sid)
    if secondary_unit and sbb:
        c.create_text(sbb[2] + 5, line_y + 14, text=secondary_unit,
                      fill=theme.TEXT_3, font=(_ui_font(), 9), anchor="nw")


def _draw_single_metric(c, x0, y0, label, value, unit=""):
    c.create_text(x0, y0, text=label, fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    vid = c.create_text(x0, y0 + 33, text=value, fill=theme.TEXT,
                        font=(_ui_font(), 28, "bold"), anchor="nw")
    bb = c.bbox(vid)
    if unit and bb:
        c.create_text(bb[2] + 7, y0 + 52, text=unit, fill=theme.TEXT_2,
                      font=(_ui_font(), 11, "bold"), anchor="nw")


def _sparkline(c, x0, y, x1, vals, color):
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    span = max(.001, hi - lo)
    pts = []
    for i, val in enumerate(vals):
        xx = x0 + (x1 - x0) * (i / max(1, len(vals) - 1))
        yy = y + 10 - ((val - lo) / span) * 20
        pts.extend((xx, yy))
    if len(pts) >= 4:
        c.create_line(*pts, fill=color, width=2, smooth=True)
        for i in range(0, len(pts), 2):
            c.create_oval(pts[i] - 1.5, pts[i + 1] - 1.5,
                          pts[i] + 1.5, pts[i + 1] + 1.5,
                          fill=color, outline="")


def _stat_sigma(vals, unit=""):
    if len(vals) <= 1:
        return "—"
    sig = statistics.pstdev(vals)
    if unit == "rpm":
        return f"σ {sig:.0f} {unit}"
    if unit:
        return f"σ {sig:.1f} {unit}"
    return f"σ {sig:.1f}"


def _draw_session_bottom(app, x0, y0, x1, y1, shots):
    """Averages on the left; consistency/trends across the remaining width."""
    c = app.canvas
    vals = [_values(s) for s in shots]
    if not vals:
        return

    club = (app.current_shot or {}).get("club") or app.current_club
    speeds = [_club_speed(s) for s in shots]
    avg = lambda key: statistics.mean(v[key] for v in vals)
    avg_club = statistics.mean(speeds) if speeds else 0.0

    left_w = (x1 - x0) * .30
    split = x0 + left_w
    v4._section_title(c, x0, y0, f"Session · {club}", f"{len(shots)} shots")

    summary = [
        ("Avg Carry", f"{avg('carry'):.1f} yds"),
        ("Avg Total", f"{avg('total'):.1f} yds"),
        ("Avg Ball Speed", f"{avg('ball'):.1f} mph"),
        ("Avg Club Speed", f"{avg_club:.1f} mph"),
        ("Avg Launch", f"{avg('launch'):.1f}°"),
        ("Avg Spin", f"{avg('spin'):.0f} rpm"),
        ("Avg Offline", f"{_side(avg('offline'))} yds"),
        ("Avg Smash", f"{avg('smash'):.2f}"),
    ]
    colw = max(130, (left_w - 26) / 2)
    for i, (label, value) in enumerate(summary):
        col, row = i % 2, i // 2
        xx = x0 + col * colw
        yy = y0 + 52 + row * 43
        c.create_text(xx, yy, text=label, fill=theme.TEXT_3,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(xx, yy + 18, text=value, fill=theme.TEXT,
                      font=(_ui_font(), 11, "bold"), anchor="nw")

    c.create_line(split + 8, y0 + 4, split + 8, y1 - 4, fill=SOFT_LINE)

    trend_x0 = split + 34
    v4._section_title(c, trend_x0, y0, "Session Trends & Consistency",
                      "Pattern information that the Recent Shots rail does not show")

    recent = vals[-min(16, len(vals)):]
    recent_shots = shots[-min(16, len(shots)):]
    carries = [v["carry"] for v in recent]
    spins = [v["spin"] for v in recent]
    offlines = [v["offline"] for v in recent]
    starts = [_movement(v)[0] for v in recent]
    moves = [_movement(v)[1] for v in recent]
    current_move = _movement(_values(app.current_shot))[1]
    consistency, move_std = _shape_consistency(recent_shots, current_move)

    left_rows = [
        ("Carry", f"{carries[-1]:.1f} yds",
         f"avg {statistics.mean(carries):.1f} · {_stat_sigma(carries, 'yds')}", carries, BLUE_LINE),
        ("Spin", f"{spins[-1]:.0f} rpm",
         f"avg {statistics.mean(spins):.0f} · {_stat_sigma(spins, 'rpm')}", spins, GOLD),
        ("Offline", f"{_side(offlines[-1])} yds",
         f"avg {_side(statistics.mean(offlines))} · {_stat_sigma(offlines, 'yds')}", offlines, ORANGE),
    ]
    right_rows = [
        ("Start Line", f"{_side(starts[-1])} yds",
         f"avg {_side(statistics.mean(starts))} · {_stat_sigma(starts, 'yds')}", starts, BLUE_TEXT),
        ("Curve Movement", f"{abs(moves[-1]):.1f}{'L' if moves[-1] < 0 else 'R'} yds",
         f"avg {abs(statistics.mean(moves)):.1f} · σ {move_std:.1f} yds", moves, GOOD),
        ("Shape Consistency", f"{consistency}%",
         "same-direction curve over recent shots", [consistency] * max(2, len(recent)), GOLD),
    ]

    trend_w = x1 - trend_x0
    col_gap = 28
    col_w = (trend_w - col_gap) / 2

    def draw_rows(rows, bx0, bx1):
        yy = y0 + 58
        for label, value, detail, arr, color in rows:
            c.create_text(bx0, yy, text=label, fill=theme.TEXT_2,
                          font=(_ui_font(), 10, "bold"), anchor="nw")
            c.create_text(bx0, yy + 22, text=value, fill=theme.TEXT,
                          font=(_ui_font(), 13, "bold"), anchor="nw")
            c.create_text(bx0 + 112, yy + 25, text=detail, fill=theme.TEXT_3,
                          font=(_ui_font(), 8), anchor="nw")
            spark_x0 = bx0 + col_w * .63
            _sparkline(c, spark_x0, yy + 24, bx1 - 4, arr, color)
            yy += 58

    draw_rows(left_rows, trend_x0, trend_x0 + col_w)
    draw_rows(right_rows, trend_x0 + col_w + col_gap, x1)


def draw_overview(app, avail_w, h, carry, total, ball_speed, club_speed, smash,
                  launch, spin, apex, offline, descent, hang_time, club_path,
                  face_to_path, spin_axis, face_to_target=0.0, shot_name="",
                  smash_clamped=False, offset_x=0, top_bar_h=52):
    c = app.canvas
    v4._matte_background(app, offset_x, top_bar_h, offset_x + avail_w, h)

    app.overview_viewall_rect = None
    app.overview_prev_rect = None
    app.overview_next_rect = None
    app.overview_bar_rects = []

    shots_all = list(app.session_shots)
    shots = v4._club_shots(app)
    v = _values(app.current_shot)
    v.update({
        "carry": carry, "total": total, "ball": ball_speed, "smash": smash,
        "launch": launch, "spin": spin, "apex": apex, "offline": offline,
        "descent": descent, "hang": hang_time, "path": club_path,
        "face_path": face_to_path, "axis": spin_axis,
        "face_target": face_to_target, "shape": shot_name or v["shape"],
    })

    margin = max(18, int(avail_w * .015))
    gap = max(20, int(avail_w * .012))
    x0, x1 = offset_x + margin, offset_x + avail_w - margin
    y0 = top_bar_h + 14
    usable_h = h - y0 - 16

    # --- Current-shot ribbon -------------------------------------------------
    top_h = max(148, min(164, int(usable_h * .19)))
    c.create_rectangle(x0, y0, x1, y0 + top_h, fill=RIBBON, outline="")
    c.create_line(x0, y0 + top_h, x1, y0 + top_h, fill=SOFT_LINE)
    c.create_rectangle(x0, y0, x0 + 4, y0 + top_h, fill=BLUE, outline="")

    n = len(shots_all)
    idx = app.selected_shot_index + 1 if app.selected_shot_index is not None else n
    identity_w = max(270, min(330, (x1 - x0) * .205))
    ix = x0 + 24
    club = (app.current_shot or {}).get("club") or app.current_club
    c.create_text(ix, y0 + 22, text=f"Shot {idx}", fill=theme.TEXT_2,
                  font=(_ui_font(), 12, "bold"), anchor="nw")
    c.create_text(ix + 78, y0 + 20, text=club, fill=BLUE_TEXT,
                  font=(_ui_font(), 15, "bold"), anchor="nw")
    c.create_text(ix, y0 + 58, text=(shot_name or "Straight"), fill=theme.TEXT,
                  font=(_ui_font(), 28, "bold"), anchor="nw")

    cur = app.selected_shot_index if app.selected_shot_index is not None else n - 1
    for j, (glyph, delta) in enumerate((("‹", -1), ("›", 1))):
        bx = x0 + identity_w - 70 + j * 32
        live = 0 <= cur + delta < n
        c.create_text(bx + 11, y0 + top_h - 22, text=glyph,
                      fill=theme.TEXT_2 if live else theme.TEXT_3,
                      font=(_ui_font(), 14), anchor="center")
        rect = (bx, y0 + top_h - 34, bx + 24, y0 + top_h - 8) if live else None
        if delta < 0:
            app.overview_prev_rect = rect
        else:
            app.overview_next_rect = rect

    mx0 = x0 + identity_w
    step = (x1 - mx0) / 6
    for i in range(1, 6):
        xx = mx0 + i * step
        c.create_line(xx, y0 + 24, xx, y0 + top_h - 24, fill=SOFT_LINE)

    _draw_pair_metric(c, mx0 + 16, y0 + 22, mx0 + step,
                      "Carry", f"{carry:.1f}", "yds",
                      "Total", f"{total:.1f}", "yds")
    _draw_pair_metric(c, mx0 + step + 16, y0 + 22, mx0 + step * 2,
                      "Ball Speed", f"{ball_speed:.1f}", "mph",
                      "Club", f"{club_speed:.1f}", "mph")
    _draw_single_metric(c, mx0 + step * 2 + 16, y0 + 22,
                        "Launch Angle", f"{launch:.1f}°")
    _draw_single_metric(c, mx0 + step * 3 + 16, y0 + 22,
                        "Spin Rate", f"{spin:.0f}", "rpm")
    _draw_single_metric(c, mx0 + step * 4 + 16, y0 + 22,
                        "Apex", f"{apex * 3:.0f}", "ft")
    _draw_single_metric(c, mx0 + step * 5 + 16, y0 + 22,
                        "Offline", _side(offline), "yds")

    # --- Main instrument field ---------------------------------------------
    main_y0 = y0 + top_h + gap
    bottom_h = max(205, min(232, int(usable_h * .255)))
    main_y1 = h - 16 - bottom_h - gap
    main_h = max(350, main_y1 - main_y0)
    main_y1 = main_y0 + main_h

    total_w = x1 - x0
    lw = total_w * .40
    cw = total_w * .29
    dx0, dx1 = x0, x0 + lw
    sx0, sx1 = dx1 + gap, dx1 + gap + cw
    rx0, rx1 = sx1 + gap, x1

    c.create_line(dx1 + gap / 2, main_y0 + 4, dx1 + gap / 2,
                  main_y1 - 4, fill=SOFT_LINE)
    c.create_line(sx1 + gap / 2, main_y0 + 4, sx1 + gap / 2,
                  main_y1 - 4, fill=SOFT_LINE)

    v4._draw_dispersion(app, dx0, main_y0, dx1, main_y1, shots)
    v4._draw_shape(app, sx0, main_y0, sx1, main_y1, v, shots)

    # Right side now has only information that adds something beyond the ribbon.
    # Strike gets the visual emphasis; delivery sits directly below it.
    strike_h = main_h * .55
    sy1 = main_y0 + strike_h
    dy0 = sy1 + 12
    c.create_line(rx0, sy1 + 4, rx1, sy1 + 4, fill=SOFT_LINE)
    v4._draw_strike(app, rx0, main_y0, rx1, sy1)
    v4._draw_delivery(app, rx0, dy0, rx1, main_y1, v)

    # --- Session pattern ----------------------------------------------------
    by0, by1 = main_y1 + gap, h - 16
    if by1 - by0 >= 170:
        c.create_line(x0, by0 - 7, x1, by0 - 7, fill=SOFT_LINE)
        _draw_session_bottom(app, x0, by0, x1, by1, shots)
