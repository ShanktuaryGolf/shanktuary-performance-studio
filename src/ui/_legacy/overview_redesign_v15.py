"""Fifteenth-pass Shot view: hierarchy, target guides, and color-role polish.

Keeps v14's navy/teal material and gold emphasis, then:
- removes the boxed Session surface while retaining a top separator
- strengthens section-title hierarchy
- makes Dispersion's vertical TARGET guide clearly dominant and horizontal
  carry guides slightly easier to read
- restores gold for Fade in Session Shape Mix
- alternates teal/gold sparklines across Session Trends
- lifts historical dispersion points slightly off the background
"""

import statistics

import overview_redesign_v7 as v7
import overview_redesign_v8 as v8
import overview_redesign_v9 as v9
import overview_redesign_v10 as v10
import overview_redesign_v11 as v11
import overview_redesign_v12 as v12
import overview_redesign_v14 as v14
import theme

GOLD = v14.GOLD
TEAL = v14.TEAL
TEAL_LINE = v14.TEAL_LINE
TEAL_TEXT = v14.TEAL_TEXT
TEAL_SOFT = v14.TEAL_SOFT

TITLE_TEXT = "#E1E7E8"
H_GRID = "#29454F"
TARGET_GUIDE = "#507D86"
SESSION_DOT = "#587D88"


def _section_title(c, x, y, title, subtitle=None):
    """Give major workspace labels enough contrast to anchor each panel."""
    c.create_text(x, y, text=title, fill=TITLE_TEXT,
                  font=(v7._ui_font(), 15, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x, y + 27, text=subtitle, fill=theme.TEXT_3,
                      font=(v7._ui_font(), 10), anchor="nw")


def _session_surface(app, x0, y0, x1, y1):
    """No bottom container box: the page material simply continues through."""
    app.canvas.create_line(x0, y0, x1, y0, fill="#35515B", width=1)


def _draw_shape_mix(c, x0, y0, x1, shots):
    counts, total = v7._shape_mix(shots)
    if not total:
        return

    # Fade returning to gold was the stronger visual read. Gold here describes
    # a category, while the much larger current-shot markers still own emphasis.
    colors = {
        "Draw": TEAL_LINE,
        "Straight": v7.STRAIGHT,
        "Fade": GOLD,
    }
    c.create_text(x0, y0, text="Session Shape Mix", fill=theme.TEXT_2,
                  font=(v7._ui_font(), 10, "bold"), anchor="nw")
    bar_y = y0 + 28
    bar_h = 10
    bw = x1 - x0

    visible = [name for name in ("Draw", "Straight", "Fade") if counts[name] > 0]
    cur = x0
    for i, name in enumerate(visible):
        frac = counts[name] / total
        end = x1 if i == len(visible) - 1 else cur + bw * frac
        v7._draw_segment(
            c, cur, end, bar_y, bar_h, colors[name],
            round_left=(i == 0), round_right=(i == len(visible) - 1),
        )
        cur = end

    legend_y = bar_y + 24
    lx = x0
    for name in ("Draw", "Straight", "Fade"):
        pct = round(100 * counts[name] / total)
        c.create_oval(lx, legend_y + 2, lx + 7, legend_y + 9,
                      fill=colors[name], outline="")
        c.create_text(lx + 13, legend_y + 6, text=f"{name} {pct}%",
                      fill=theme.TEXT_2,
                      font=(v7._ui_font(), 9, "bold"), anchor="w")
        lx += max(98, bw / 3)


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    """Accepted plot with a clearer target axis and slightly stronger grid."""
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    _section_title(c, x0, y0, "Dispersion", f"{club} · carry landing pattern")

    points = [(v7._values(s), s) for s in shots]
    points = [(vv, ss) for vv, ss in points if vv["carry"] > 0]
    if not points:
        return

    left, right = x0 + 58, x1 - 20
    top, bottom = y0 + 64, y1 - 62
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    carry_half = v8.CONF_RADIUS * max(1.5, sc)
    raw_min = min(min(carries), mc - carry_half)
    raw_max = max(max(carries), mc + carry_half)
    raw_span = max(8.0, raw_max - raw_min)
    pad = raw_span * .06
    cmin, cmax = raw_min - pad, raw_max + pad

    lateral_extent = max(
        5.0,
        max(abs(v) for v in offs),
        abs(mo) + v8.CONF_RADIUS * max(1.0, so),
    )
    omax = lateral_extent * 1.05
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    tx = sx(0)
    # Horizontal carry guides come up only one notch.
    for frac in (.34, .67):
        gy = top + ph * frac
        val = cmax - (cmax - cmin) * frac
        c.create_line(left, gy, right, gy, fill=H_GRID, dash=(2, 6))
        c.create_text(left - 11, gy, text=f"{val:.0f}", fill=theme.TEXT_2,
                      font=(v7._ui_font(), 10, "bold"), anchor="e")

    # Target is the plot's visual anchor, so the vertical guide is intentionally
    # more prominent than the horizontal grid while remaining below data marks.
    c.create_line(tx, top, tx, bottom, fill=TARGET_GUIDE, width=2, dash=(4, 6))

    ex0 = sx(mo - v8.CONF_RADIUS * max(1.0, so))
    ex1 = sx(mo + v8.CONF_RADIUS * max(1.0, so))
    ey0 = sy(mc + carry_half)
    ey1 = sy(mc - carry_half)
    ellipse_col = v7._mix(TEAL_LINE, "#102C35", .20)
    c.create_oval(ex0, ey0, ex1, ey1, outline=ellipse_col, width=2)
    c.create_text(ex1 - 7, ey0 + 8, text="90% confidence",
                  fill=v7._mix(TEAL_TEXT, theme.BG, .12),
                  font=(v7._ui_font(), 9, "bold"), anchor="ne")

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            c.create_oval(px - 9, py - 9, px + 9, py + 9,
                          fill=GOLD, outline="")
        else:
            c.create_oval(px - 4.5, py - 4.5, px + 4.5, py + 4.5,
                          fill=SESSION_DOT, outline="")

    axis_y = bottom + 17
    c.create_text(left, axis_y, text=f"{omax:.0f} L", fill=theme.TEXT_2,
                  font=(v7._ui_font(), 11, "bold"), anchor="n")
    c.create_text(tx, axis_y + 1, text="TARGET", fill=TEAL_SOFT,
                  font=(v7._ui_font(), 9, "bold"), anchor="n")
    c.create_text(right, axis_y, text=f"{omax:.0f} R", fill=theme.TEXT_2,
                  font=(v7._ui_font(), 11, "bold"), anchor="n")

    c.create_oval(x0 + 2, y1 - 20, x0 + 14, y1 - 8,
                  fill=GOLD, outline="")
    c.create_text(x0 + 20, y1 - 14, text="Current shot", fill=theme.TEXT_2,
                  font=(v7._ui_font(), 10), anchor="w")
    c.create_oval(x0 + 124, y1 - 18, x0 + 130, y1 - 12,
                  fill=SESSION_DOT, outline="")
    c.create_text(x0 + 136, y1 - 15, text=f"Session ({len(points)})",
                  fill=theme.TEXT_2, font=(v7._ui_font(), 10), anchor="w")


def _draw_session_bottom(app, x0, y0, x1, y1, shots):
    """Accepted Session layout with stronger titles and alternating trend colors."""
    c = app.canvas
    vals = [v7._values(s) for s in shots]
    if not vals:
        return

    club = (app.current_shot or {}).get("club") or app.current_club
    speeds = [v7._club_speed(s) for s in shots]
    avg = lambda key: statistics.mean(v[key] for v in vals)
    avg_club = statistics.mean(speeds) if speeds else 0.0

    total_w = x1 - x0
    summary_w = total_w * .32
    divider = x0 + summary_w

    c.create_text(x0, y0 + 15, text=f"Session · {club}", fill=TITLE_TEXT,
                  font=(v7._ui_font(), 15, "bold"), anchor="nw")
    c.create_text(divider - 18, y0 + 18, text=f"{len(vals)} shots",
                  fill=theme.TEXT_2, font=(v7._ui_font(), 10, "bold"), anchor="ne")

    summary = [
        ("Avg Carry", f"{avg('carry'):.1f} yds"),
        ("Avg Total", f"{avg('total'):.1f} yds"),
        ("Avg Ball Speed", f"{avg('ball'):.1f} mph"),
        ("Avg Club Speed", f"{avg_club:.1f} mph"),
        ("Avg VLA", f"{avg('launch'):.1f}°"),
        ("Avg Spin", f"{avg('spin'):.0f} rpm"),
        ("Avg Offline", f"{v7._side(avg('offline'))} yds"),
        ("Avg Smash", f"{avg('smash'):.2f}"),
    ]
    inner_w = summary_w - 22
    col_w = inner_w / 2
    available = max(138, y1 - y0 - 55)
    row_step = min(43, available / 4)
    for i, (label, value) in enumerate(summary):
        col, row = i % 2, i // 2
        xx = x0 + col * col_w
        yy = y0 + 51 + row * row_step
        c.create_text(xx, yy, text=label, fill=theme.TEXT_2,
                      font=(v7._ui_font(), 9, "bold"), anchor="nw")
        c.create_text(xx, yy + 18, text=value, fill=TITLE_TEXT,
                      font=(v7._ui_font(), 11, "bold"), anchor="nw")

    c.create_line(divider + 2, y0 + 12, divider + 2, y1 - 8,
                  fill=v7._mix(theme.HAIRLINE, TEAL_SOFT, .10))

    trend_x0 = divider + 30
    c.create_text(trend_x0, y0 + 15, text="Session Trends", fill=TITLE_TEXT,
                  font=(v7._ui_font(), 15, "bold"), anchor="nw")
    c.create_text(x1, y0 + 18, text=f"Last {min(16, len(vals))} shots",
                  fill=theme.TEXT_2, font=(v7._ui_font(), 10, "bold"), anchor="ne")

    recent = vals[-min(16, len(vals)):]
    carries = [v["carry"] for v in recent]
    balls = [v["ball"] for v in recent]
    spins = [v["spin"] for v in recent]
    offlines = [v["offline"] for v in recent]
    starts = [v7._movement(v)[0] for v in recent]
    moves = [v7._movement(v)[1] for v in recent]

    def sd(arr, unit=""):
        if len(arr) <= 1:
            return "SD —"
        s = statistics.pstdev(arr)
        if unit == "rpm":
            return f"SD {s:.0f} rpm"
        return f"SD {s:.1f}{(' ' + unit) if unit else ''}"

    # Checkerboard alternation keeps the six sparklines lively without adding
    # a third analytical hue.
    rows_left = [
        ("Carry", f"Avg {statistics.mean(carries):.1f} yds", sd(carries, "yds"), carries, TEAL_LINE),
        ("Spin", f"Avg {statistics.mean(spins):.0f} rpm", sd(spins, "rpm"), spins, GOLD),
        ("Offline", f"Avg {v7._side(statistics.mean(offlines))} yds", sd(offlines, "yds"), offlines, TEAL_LINE),
    ]
    rows_right = [
        ("Start Line", f"Avg {v7._side(statistics.mean(starts))} yds", sd(starts, "yds"), starts, GOLD),
        ("Curve Movement",
         f"Avg {abs(statistics.mean(moves)):.1f}{'L' if statistics.mean(moves) < 0 else 'R'} yds",
         sd(moves, "yds"), moves, TEAL_LINE),
        ("Ball Speed", f"Avg {statistics.mean(balls):.1f} mph", sd(balls, "mph"), balls, GOLD),
    ]

    trend_w = x1 - trend_x0
    gap = 28
    tw = (trend_w - gap) / 2
    row_step_t = min(56, max(47, (y1 - y0 - 57) / 3))

    def draw_rows(rows, bx0, bx1):
        yy = y0 + 54
        for label, avg_text, detail, arr, color in rows:
            c.create_text(bx0, yy, text=label, fill=theme.TEXT_2,
                          font=(v7._ui_font(), 10, "bold"), anchor="nw")
            c.create_text(bx0, yy + 21, text=avg_text, fill=TITLE_TEXT,
                          font=(v7._ui_font(), 12, "bold"), anchor="nw")
            c.create_text(bx0 + 128, yy + 24, text=detail, fill=theme.TEXT_3,
                          font=(v7._ui_font(), 9), anchor="nw")
            v7._sparkline(c, bx0 + tw * .63, yy + 23, bx1 - 4, arr, color)
            yy += row_step_t

    draw_rows(rows_left, trend_x0, trend_x0 + tw)
    draw_rows(rows_right, trend_x0 + tw + gap, x1)


def _apply_polish():
    v14._apply_palette()

    # Hierarchy / copied constants.
    v7.SECTION_TEXT = TITLE_TEXT
    v7.SESSION_DOT = SESSION_DOT
    v7._section_title = _section_title
    v7._draw_shape_mix = _draw_shape_mix

    v8.SECTION_TEXT = TITLE_TEXT
    v8.SESSION_DOT = SESSION_DOT
    v8._session_surface = _session_surface
    v8._draw_session_bottom = _draw_session_bottom

    v9.SESSION_DOT = SESSION_DOT
    v9._draw_dispersion = _draw_dispersion

    v10.SECTION_TEXT = TITLE_TEXT
    v11.SECTION_TEXT = TITLE_TEXT
    v12.NEUTRAL_POINT = v7.NEUTRAL_POINT


def draw_overview(*args, **kwargs):
    _apply_polish()
    return v12.draw_overview(*args, **kwargs)
