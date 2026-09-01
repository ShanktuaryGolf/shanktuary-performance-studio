"""Modernized Dispersion tool for the isolated design sandbox.

Keeps the existing three analysis modes but applies the same design system as
Shot: cool neutrals + electric blue, orange only for the current shot, dynamic
chart scaling, cleaner typography, and sorted club gapping.
"""

import math

import theme


BLUE = theme.ACCENT_LINE
BLUE_TEXT = theme.ACCENT_TEXT
ORANGE = theme.WARN
GRID = theme.GUIDE
MUTED = theme.TEXT_3
SOFT = theme.HAIRLINE


def _f(v, default=0.0):
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _shot_vals(shot):
    ogc = shot.get("open_golf_coach", {}) or {}
    us = ogc.get("us_customary_units", {}) or {}
    carry = _f(us.get("carry_distance_yards"))
    total = _f(us.get("total_distance_yards"), carry)
    offline = _f(us.get("offline_distance_yards"))
    apex_ft = _f(us.get("apex_height_feet"))
    if apex_ft <= 0:
        apex_ft = _f(shot.get("apex_height_feet"))
    if apex_ft <= 0:
        apex_yd = _f(us.get("apex_height_yards"))
    else:
        apex_yd = apex_ft / 3.0
    if apex_yd <= 0:
        apex_yd = max(12.0, carry * 0.19)
    return carry, total, offline, apex_yd


def _groups(app):
    groups = {}
    for s in getattr(app, "session_shots", []) or []:
        if s.get("excluded"):
            continue
        club = str(s.get("club") or getattr(app, "current_club", "Club"))
        carry, total, off, apex = _shot_vals(s)
        if carry <= 0:
            continue
        groups.setdefault(club, []).append((s, carry, total, off, apex))
    return groups


def _avg(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _sd(vals):
    if not vals:
        return 0.0
    m = _avg(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5


def _grid(c, x1, y1, x2, y2, nx=5, ny=4):
    for i in range(1, nx):
        x = x1 + (x2 - x1) * i / nx
        c.create_line(x, y1, x, y2, fill=SOFT, dash=(2, 5))
    for i in range(1, ny):
        y = y1 + (y2 - y1) * i / ny
        c.create_line(x1, y, x2, y, fill=SOFT, dash=(2, 5))


def _panel_title(c, x, y, title, subtitle=None):
    c.create_text(x, y, text=title, fill=theme.TEXT_2,
                  font=(theme.ui_font(), 11, "bold"), anchor="w")
    if subtitle:
        c.create_text(x, y + 18, text=subtitle, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="w")


def _trajectory(app, x1, y1, x2, y2, groups):
    c = app.canvas
    c.create_rectangle(x1, y1, x2, y2, fill=theme.BG, outline="")
    _panel_title(c, x1 + 18, y1 + 18, "Trajectory", "side view · session shots")

    shots = [item for rows in groups.values() for item in rows]
    if not shots:
        c.create_text((x1+x2)/2, (y1+y2)/2, text="No shots in session",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 11))
        return

    max_x = max(v[2] if v[2] > 0 else v[1] for v in shots) * 1.14
    max_y = max(v[4] for v in shots) * 1.20
    max_x = max(max_x, 1.0)
    max_y = max(max_y, 1.0)

    px1, px2 = x1 + 50, x2 - 22
    py1, py2 = y1 + 58, y2 - 34
    _grid(c, px1, py1, px2, py2)
    c.create_line(px1, py2, px2, py2, fill=GRID)

    # readable axes without over-labeling
    for i in range(5):
        frac = i / 4
        xv = max_x * frac
        xx = px1 + (px2 - px1) * frac
        c.create_text(xx, py2 + 14, text=f"{xv:.0f}", fill=MUTED,
                      font=(theme.ui_font(), 8), anchor="n")
    for i in range(3):
        frac = i / 2
        yv = max_y * frac
        yy = py2 - (py2 - py1) * frac
        c.create_text(px1 - 10, yy, text=f"{yv:.0f}y", fill=MUTED,
                      font=(theme.ui_font(), 8), anchor="e")

    current = getattr(app, "current_shot", None)
    for club, rows in groups.items():
        for shot, carry, total, off, apex in rows:
            pts = []
            landing = total if total > 0 else carry
            for j in range(41):
                t = j / 40.0
                xxv = landing * t
                yyv = 4.0 * apex * t * (1.0 - t)
                xx = px1 + (xxv / max_x) * (px2 - px1)
                yy = py2 - (yyv / max_y) * (py2 - py1)
                pts.extend((xx, yy))
            sel = shot is current
            col = ORANGE if sel else theme.TEXT_3
            width = 3 if sel else 1
            c.create_line(*pts, fill=col, width=width, smooth=True)


def _dispersion(app, x1, y1, x2, y2, groups):
    c = app.canvas
    c.create_rectangle(x1, y1, x2, y2, fill=theme.BG, outline="")
    _panel_title(c, x1 + 18, y1 + 18, "Landing Pattern", "carry × offline · 90% session spread")

    shots = [item for rows in groups.values() for item in rows]
    if not shots:
        return

    all_carry = [v[1] for v in shots]
    all_off = [v[3] for v in shots]
    carry_lo, carry_hi = min(all_carry), max(all_carry)
    carry_span = max(8.0, carry_hi - carry_lo)
    y_lo = carry_lo - carry_span * 0.30
    y_hi = carry_hi + carry_span * 0.30

    max_off = max(4.0, max(abs(v) for v in all_off) * 1.55)
    # also reserve space for ellipse width so groups do not clip
    for rows in groups.values():
        offs = [r[3] for r in rows]
        max_off = max(max_off, abs(_avg(offs)) + max(2.5, _sd(offs) * 2.15))
    max_off *= 1.08

    px1, px2 = x1 + 52, x2 - 26
    py1, py2 = y1 + 60, y2 - 38
    _grid(c, px1, py1, px2, py2)
    cx = (px1 + px2) / 2
    c.create_line(cx, py1, cx, py2, fill=GRID, width=2, dash=(5, 5))

    def sx(off):
        return cx + (off / max_off) * ((px2 - px1) / 2)

    def sy(carry):
        return py2 - ((carry - y_lo) / max(1e-6, y_hi - y_lo)) * (py2 - py1)

    for frac, label in ((-1, f"{max_off:.0f}L"), (-.5, f"{max_off/2:.0f}L"),
                        (.5, f"{max_off/2:.0f}R"), (1, f"{max_off:.0f}R")):
        xx = cx + frac * ((px2-px1)/2)
        c.create_text(xx, py2 + 15, text=label, fill=MUTED,
                      font=(theme.ui_font(), 8), anchor="n")

    for i in range(3):
        frac = i / 2
        cv = y_lo + (y_hi-y_lo)*frac
        yy = py2 - frac*(py2-py1)
        c.create_text(px1 - 10, yy, text=f"{cv:.0f}y", fill=MUTED,
                      font=(theme.ui_font(), 8), anchor="e")

    ordered = sorted(groups.items(), key=lambda kv: _avg([r[1] for r in kv[1]]), reverse=True)
    current = getattr(app, "current_shot", None)
    for idx, (club, rows) in enumerate(ordered):
        carries = [r[1] for r in rows]
        offs = [r[3] for r in rows]
        mc, mo = _avg(carries), _avg(offs)
        sd_c = max(1.4, _sd(carries))
        sd_o = max(1.1, _sd(offs))
        rx = abs(sx(mo + sd_o * 2.15) - sx(mo))
        ry = abs(sy(mc + sd_c * 2.15) - sy(mc))
        ellipse_col = BLUE if idx == 0 else theme.TEXT_3
        c.create_oval(sx(mo)-rx, sy(mc)-ry, sx(mo)+rx, sy(mc)+ry,
                      outline=ellipse_col, width=2 if idx == 0 else 1,
                      dash=() if idx == 0 else (4, 4))

        # label outside the ellipse instead of on top of the data
        label_x = min(px2 - 10, sx(mo) + rx + 10)
        label_y = max(py1 + 10, sy(mc) - ry - 4)
        c.create_text(label_x, label_y, text=f"{club}  {mc:.0f}y",
                      fill=BLUE_TEXT if idx == 0 else theme.TEXT_2,
                      font=(theme.ui_font(), 9, "bold"), anchor="sw")

        for shot, carry, total, off, apex in rows:
            xx, yy = sx(off), sy(carry)
            sel = shot is current
            r = 6 if sel else 3
            c.create_oval(xx-r, yy-r, xx+r, yy+r,
                          fill=ORANGE if sel else theme.TEXT_2,
                          outline=theme.TEXT if sel else "")


def _gapping(app, x1, y1, x2, y2, groups):
    c = app.canvas
    c.create_rectangle(x1, y1, x2, y2, fill=theme.SURFACE, outline="")
    _panel_title(c, x1 + 18, y1 + 20, "Club Gapping & Spread", "sorted by average carry")

    ordered = sorted(groups.items(), key=lambda kv: _avg([r[1] for r in kv[1]]), reverse=True)
    y = y1 + 66
    prev_avg = None
    for idx, (club, rows) in enumerate(ordered[:7]):
        carries = [r[1] for r in rows]
        offs = [r[3] for r in rows]
        avg_c = _avg(carries)
        sd_c = _sd(carries)
        min_c, max_c = min(carries), max(carries)
        avg_off = _avg(offs)

        if prev_avg is not None:
            gap = prev_avg - avg_c
            c.create_text(x1 + 28, y - 7, text=f"↓ {gap:.1f} yd gap",
                          fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="w")
            y += 12

        card_h = 82
        c.create_rectangle(x1 + 14, y, x2 - 14, y + card_h,
                           fill=theme.BG, outline="")
        c.create_rectangle(x1 + 14, y, x1 + 18, y + card_h,
                           fill=BLUE if idx == 0 else theme.GUIDE, outline="")
        c.create_text(x1 + 28, y + 18, text=club, fill=theme.TEXT,
                      font=(theme.ui_font(), 10, "bold"), anchor="w")
        c.create_text(x2 - 28, y + 18, text=f"{len(rows)} shots", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="e")
        c.create_text(x1 + 28, y + 43, text=f"{avg_c:.1f} yds", fill=BLUE_TEXT,
                      font=(theme.ui_font(), 15, "bold"), anchor="w")
        off_dir = "R" if avg_off > .15 else ("L" if avg_off < -.15 else "")
        lateral = f"{abs(avg_off):.1f}{off_dir} avg" if off_dir else "0.0 avg"
        c.create_text(x1 + 28, y + 65,
                      text=f"{min_c:.0f}–{max_c:.0f} carry  ·  ±{sd_c:.1f} yds  ·  {lateral}",
                      fill=theme.TEXT_2, font=(theme.ui_font(), 8), anchor="w")
        prev_avg = avg_c
        y += card_h + 14


def draw_dispersion_and_gapping(app, avail_w, h, offset_x=0):
    """Design-owned Dispersion tool."""
    c = app.canvas
    c.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline="")

    groups = _groups(app)
    mode = getattr(app, "dispersion_view_submode", "split") or "split"
    if mode not in ("split", "topdown", "side"):
        mode = "split"
        app.dispersion_view_submode = mode

    # clean segmented control, no emoji
    tabs = [("split", "Split"), ("topdown", "Dispersion"), ("side", "Trajectory")]
    tab_y1, tab_y2 = 61, 91
    tab_x = offset_x + 18
    app.design_dispersion_tab_rects = []
    for key, label in tabs:
        tw = 116 if key == "split" else 138
        active = mode == key
        rect = (tab_x, tab_y1, tab_x + tw, tab_y2)
        app.design_dispersion_tab_rects.append((rect, key))
        if active:
            c.create_rectangle(*rect, fill=theme.ACCENT_DEEP, outline=BLUE, width=1)
        else:
            c.create_rectangle(*rect, fill=theme.BG, outline=SOFT, width=1)
        c.create_text((rect[0]+rect[2])/2, (tab_y1+tab_y2)/2, text=label,
                      fill=theme.TEXT if active else theme.TEXT_2,
                      font=(theme.ui_font(), 9, "bold" if active else "normal"))
        tab_x += tw + 8

    content_top = 105
    gap = 12
    right_w = max(300, int(avail_w * .30))
    main_x1 = offset_x + 18
    main_x2 = offset_x + avail_w - right_w - gap - 18
    right_x1 = main_x2 + gap
    right_x2 = offset_x + avail_w - 18
    bottom = h - 14

    # one quiet vertical divider, not boxes everywhere
    c.create_line(right_x1 - gap/2, content_top, right_x1 - gap/2, bottom,
                  fill=SOFT, width=1)

    if mode == "split":
        usable = bottom - content_top
        top_h = int(usable * .45)
        split_y = content_top + top_h
        _trajectory(app, main_x1, content_top, main_x2, split_y - 6, groups)
        c.create_line(main_x1, split_y, main_x2, split_y, fill=SOFT)
        _dispersion(app, main_x1, split_y + 6, main_x2, bottom, groups)
    elif mode == "topdown":
        _dispersion(app, main_x1, content_top, main_x2, bottom, groups)
    else:
        _trajectory(app, main_x1, content_top, main_x2, bottom, groups)

    _gapping(app, right_x1, content_top, right_x2, bottom, groups)
