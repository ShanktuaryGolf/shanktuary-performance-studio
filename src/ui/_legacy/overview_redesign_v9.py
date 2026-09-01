"""Ninth-pass Shot view: dispersion readability only."""

import statistics

import overview_redesign_v7 as v7
import overview_redesign_v8 as v8
import theme

BLUE_LINE = v7.BLUE_LINE
BLUE_TEXT = v7.BLUE_TEXT
ORANGE = v7.ORANGE
SESSION_DOT = v7.SESSION_DOT
GRID_LINE = v7.GRID_LINE
_values = v7._values
_ui_font = v7._ui_font
_mix = v7._mix
CONF_RADIUS = v8.CONF_RADIUS


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    """Keep the accepted dispersion plot, but make its scale easier to read."""
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    v7._section_title(c, x0, y0, "Dispersion", f"{club} · carry landing pattern")

    points = [(_values(s), s) for s in shots]
    points = [(vv, ss) for vv, ss in points if vv["carry"] > 0]
    if not points:
        return

    # Extra room on the left/bottom is reserved for the larger yardage labels.
    left, right = x0 + 58, x1 - 20
    top, bottom = y0 + 64, y1 - 62
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    carry_half = CONF_RADIUS * max(1.5, sc)
    raw_min = min(min(carries), mc - carry_half)
    raw_max = max(max(carries), mc + carry_half)
    raw_span = max(8.0, raw_max - raw_min)
    pad = raw_span * .06
    cmin, cmax = raw_min - pad, raw_max + pad

    lateral_extent = max(
        5.0,
        max(abs(v) for v in offs),
        abs(mo) + CONF_RADIUS * max(1.0, so),
    )
    omax = lateral_extent * 1.05
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    tx = sx(0)
    for frac in (.34, .67):
        gy = top + ph * frac
        val = cmax - (cmax - cmin) * frac
        c.create_line(left, gy, right, gy, fill=GRID_LINE, dash=(2, 6))
        c.create_text(left - 11, gy, text=f"{val:.0f}", fill=theme.TEXT_2,
                      font=(_ui_font(), 10, "bold"), anchor="e")
    c.create_line(tx, top, tx, bottom, fill=GRID_LINE, dash=(4, 6))

    ex0 = sx(mo - CONF_RADIUS * max(1.0, so))
    ex1 = sx(mo + CONF_RADIUS * max(1.0, so))
    ey0 = sy(mc + carry_half)
    ey1 = sy(mc - carry_half)
    ellipse_col = _mix(BLUE_LINE, theme.BG, .34)
    c.create_oval(ex0, ey0, ex1, ey1, outline=ellipse_col, width=2)
    c.create_text(ex1 - 7, ey0 + 8, text="90% confidence",
                  fill=_mix(BLUE_TEXT, theme.BG, .18),
                  font=(_ui_font(), 9, "bold"), anchor="ne")

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            # Current shot should be unmistakable against the muted session cloud.
            c.create_oval(px - 9, py - 9, px + 9, py + 9,
                          fill=ORANGE, outline="")
        else:
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill=SESSION_DOT, outline="")

    axis_y = bottom + 17
    c.create_text(left, axis_y, text=f"{omax:.0f} L", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="n")
    c.create_text(tx, axis_y + 1, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(right, axis_y, text=f"{omax:.0f} R", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="n")

    # Legend mirrors the actual plot treatment.
    c.create_oval(x0 + 2, y1 - 20, x0 + 14, y1 - 8,
                  fill=ORANGE, outline="")
    c.create_text(x0 + 20, y1 - 14, text="Current shot", fill=theme.TEXT_2,
                  font=(_ui_font(), 10), anchor="w")
    c.create_oval(x0 + 124, y1 - 18, x0 + 130, y1 - 12,
                  fill=SESSION_DOT, outline="")
    c.create_text(x0 + 136, y1 - 15, text=f"Session ({len(points)})",
                  fill=theme.TEXT_2, font=(_ui_font(), 10), anchor="w")


def draw_overview(*args, **kwargs):
    # Keep every other v8 decision intact; this step changes dispersion only.
    v8._draw_dispersion = _draw_dispersion
    return v8.draw_overview(*args, **kwargs)
