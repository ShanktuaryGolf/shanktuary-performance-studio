"""Sixth-pass Overview: calmer charting, clearer movement, more dimensional depth."""

from __future__ import annotations

import statistics

from PIL import Image, ImageDraw, ImageOps, ImageTk

import overview_redesign_v4 as v4
import overview_redesign_v5 as v5
import theme

BLUE = v4.BLUE
BLUE_LINE = v4.BLUE_LINE
BLUE_TEXT = v4.BLUE_TEXT
GOOD = v4.GOOD
ORANGE = v4.ORANGE
RED = getattr(theme, "DANGER", "#E34A4A")
GOLD = getattr(theme, "GOLD", "#C89A4A")

_values = v4._values
_movement = v4._movement
_side = v4._side
_ui_font = v4._ui_font
_mix = v4._mix
_club_speed = v5._club_speed
_draw_pair_metric = v5._draw_pair_metric
_draw_single_metric = v5._draw_single_metric
_sparkline = v5._sparkline
_stat_sigma = v5._stat_sigma

SOFT_LINE = _mix(theme.HAIRLINE, theme.BG, .50)
GRID_LINE = _mix(theme.GUIDE, theme.BG, .50)
SESSION_DOT = _mix(theme.TEXT_3, BLUE, .12)
ELLIPSE = _mix(BLUE_LINE, theme.BG, .32)
SECTION_TEXT = _mix(theme.TEXT, theme.TEXT_2, .52)
SHAPE_TEXT = _mix(theme.TEXT, theme.TEXT_2, .28)
STRAIGHT = _mix(theme.TEXT_2, theme.BG, .18)


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _section_title(c, x, y, title, subtitle=None):
    """Section hierarchy without making every title another white focal point."""
    c.create_text(x, y, text=title, fill=SECTION_TEXT,
                  font=(_ui_font(), 13, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x, y + 24, text=subtitle, fill=theme.TEXT_3,
                      font=(_ui_font(), 9), anchor="nw")


# v4's Strike/Delivery helpers resolve this global dynamically.
v4._section_title = _section_title


def _depth_background(app, x0, y0, x1, y1):
    """Noticeable-but-subtle graphite/navy lighting instead of a flat fill."""
    w, h = max(1, int(x1 - x0)), max(1, int(y1 - y0))
    key = (w, h)
    if getattr(app, "_overview_v6_bg_key", None) != key:
        img = Image.new("RGB", (w, h), _rgb(theme.BG))
        draw = ImageDraw.Draw(img)

        top = _rgb(_mix(theme.BG, "#183B62", .20))
        bottom = _rgb(_mix(theme.BG, "#010409", .30))
        for yy in range(0, h, 4):
            t = yy / max(1, h - 1)
            eased = t * t * (3 - 2 * t)
            col = tuple(round(a + (b - a) * eased) for a, b in zip(top, bottom))
            draw.rectangle((0, yy, w, min(h, yy + 4)), fill=col)

        # Broad upper-right blue light. Large enough to create dimensionality,
        # weak enough that there is no obvious circle or 'glow' to look at.
        glow = Image.new("RGB", (w, h), _rgb(theme.BG))
        gd = ImageDraw.Draw(glow)
        cx, cy = int(w * .72), int(h * .23)
        for i in range(20, 0, -1):
            f = i / 20
            rx = int(w * (.10 + .34 * f))
            ry = int(h * (.10 + .38 * f))
            gd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry),
                       fill=_rgb(_mix(theme.BG, BLUE, .018 + .070 * f)))
        img = Image.blend(img, glow, .24)

        # A quiet left-side lift keeps the hero chart from falling into black.
        lift = Image.new("RGB", (w, h), _rgb(theme.BG))
        ld = ImageDraw.Draw(lift)
        for xx in range(0, max(1, int(w * .42)), 5):
            f = 1 - xx / max(1, w * .42)
            ld.rectangle((xx, 0, xx + 5, h),
                         fill=_rgb(_mix(theme.BG, "#122238", .035 * f)))
        img = Image.blend(img, lift, .16)

        try:
            noise = Image.effect_noise((w, h), 15).convert("L")
            noise_col = ImageOps.colorize(noise, black="#05090E", white="#1A2634")
            img = Image.blend(img, noise_col, .026)
        except Exception:
            pass

        app._overview_v6_bg_img = ImageTk.PhotoImage(img)
        app._overview_v6_bg_key = key
    app.canvas.create_image(x0, y0, image=app._overview_v6_bg_img, anchor="nw")


def _ribbon_surface(app, x0, y0, x1, y1):
    """A lifted current-shot surface with real gradation rather than flat blue."""
    w, h = max(1, int(x1 - x0)), max(1, int(y1 - y0))
    key = (w, h)
    if getattr(app, "_overview_v6_ribbon_key", None) != key:
        img = Image.new("RGB", (w, h), _rgb(theme.SURFACE))
        draw = ImageDraw.Draw(img)
        left = _rgb(_mix(theme.SURFACE, BLUE, .085))
        right = _rgb(_mix(theme.SURFACE, theme.BG, .18))
        for xx in range(0, w, 4):
            t = xx / max(1, w - 1)
            col = tuple(round(a + (b - a) * t) for a, b in zip(left, right))
            draw.rectangle((xx, 0, min(w, xx + 4), h), fill=col)
        # Slightly brighter top edge / darker bottom edge for surface depth.
        for yy in range(0, h, 4):
            f = yy / max(1, h - 1)
            overlay = _mix("#182535", "#07101A", f)
            draw.rectangle((0, yy, w, min(h, yy + 4)),
                           fill=_rgb(_mix(overlay, "#000000", .02)))
        # Re-apply a horizontal blue tint after the vertical depth pass.
        blue_layer = Image.new("RGB", (w, h), _rgb(theme.BG))
        bd = ImageDraw.Draw(blue_layer)
        for xx in range(0, w, 4):
            f = max(0.0, 1 - xx / max(1, w * .55))
            bd.rectangle((xx, 0, min(w, xx + 4), h),
                         fill=_rgb(_mix(theme.BG, BLUE, .055 * f)))
        img = Image.blend(img, blue_layer, .16)
        app._overview_v6_ribbon_img = ImageTk.PhotoImage(img)
        app._overview_v6_ribbon_key = key
    app.canvas.create_image(x0, y0, image=app._overview_v6_ribbon_img, anchor="nw")


def _club_shots(app):
    club = (app.current_shot or {}).get("club") or app.current_club
    shots = [s for s in app.session_shots if not s.get("excluded", False)]
    subset = [s for s in shots if (s.get("club") or "") == club]
    return subset or shots


def _landing_color(offline):
    miss = abs(offline)
    if miss <= 3.0:
        return GOOD
    if miss <= 8.0:
        return ORANGE
    return RED


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    _section_title(c, x0, y0, "Dispersion", f"{club} · carry landing pattern")

    points = [(_values(s), s) for s in shots]
    points = [(vv, ss) for vv, ss in points if vv["carry"] > 0]
    if not points:
        return

    left, right = x0 + 46, x1 - 18
    top, bottom = y0 + 62, y1 - 48
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    cmin = min(carries + [mc - max(5, sc * 3)])
    cmax = max(carries + [mc + max(5, sc * 3)])
    pad = max(3, (cmax - cmin) * .14)
    cmin, cmax = cmin - pad, cmax + pad
    omax = max(6, max(abs(v) for v in offs) * 1.4, abs(mo) + so * 3)
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    tx = sx(0)
    # Only functional chart guides remain: two carry guides + target line.
    for frac in (.34, .67):
        gy = top + ph * frac
        val = cmax - (cmax - cmin) * frac
        c.create_line(left, gy, right, gy, fill=GRID_LINE, dash=(2, 6))
        c.create_text(left - 9, gy, text=f"{val:.0f}", fill=theme.TEXT_3,
                      font=(_ui_font(), 8), anchor="e")
    c.create_line(tx, top, tx, bottom, fill=GRID_LINE, dash=(4, 6))

    # Axis-aligned 2σ landing pattern: solid, subdued, still a useful pop of blue.
    c.create_oval(sx(mo - 2 * max(1, so)), sy(mc + 2 * max(1.5, sc)),
                  sx(mo + 2 * max(1, so)), sy(mc - 2 * max(1.5, sc)),
                  outline=ELLIPSE, width=2)

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            # Current shot: one larger blue mark. No halo, no extra ring.
            c.create_oval(px - 8, py - 8, px + 8, py + 8,
                          fill=BLUE, outline="")
        else:
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill=SESSION_DOT, outline="")

    c.create_text(left, bottom + 15, text=f"{omax:.0f}L", fill=theme.TEXT_3,
                  font=(_ui_font(), 8), anchor="n")
    c.create_text(tx, bottom + 15, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="n")
    c.create_text(right, bottom + 15, text=f"{omax:.0f}R", fill=theme.TEXT_3,
                  font=(_ui_font(), 8), anchor="n")

    cv = _values(app.current_shot)
    c.create_oval(x0 + 2, y1 - 19, x0 + 12, y1 - 9, fill=BLUE, outline="")
    c.create_text(x0 + 18, y1 - 14, text="Current shot", fill=theme.TEXT_2,
                  font=(_ui_font(), 9), anchor="w")
    c.create_oval(x0 + 112, y1 - 18, x0 + 118, y1 - 12, fill=SESSION_DOT, outline="")
    c.create_text(x0 + 124, y1 - 15, text=f"Session ({len(points)})", fill=theme.TEXT_2,
                  font=(_ui_font(), 9), anchor="w")
    c.create_text(x1 - 2, y1 - 15,
                  text=f"{cv['carry']:.1f} yds  ·  {_side(cv['offline'])} yds",
                  fill=SECTION_TEXT, font=(_ui_font(), 10, "bold"), anchor="e")


def _shape_bucket(v):
    move = _movement(v)[1]
    if move < -1.5:
        return "Draw"
    if move > 1.5:
        return "Fade"
    return "Straight"


def _shape_mix(shots):
    counts = {"Draw": 0, "Straight": 0, "Fade": 0}
    for s in shots:
        vv = _values(s)
        if vv["carry"] <= 0:
            continue
        counts[_shape_bucket(vv)] += 1
    total = sum(counts.values())
    return counts, total


def _draw_shape_mix(c, x0, y0, x1, shots):
    counts, total = _shape_mix(shots)
    if not total:
        return
    colors = {"Draw": BLUE_LINE, "Straight": STRAIGHT, "Fade": ORANGE}
    c.create_text(x0, y0, text=f"Session shape mix · {total} shots",
                  fill=theme.TEXT_2, font=(_ui_font(), 9, "bold"), anchor="nw")
    bar_y = y0 + 25
    bw = x1 - x0
    cur = x0
    for name in ("Draw", "Straight", "Fade"):
        frac = counts[name] / total
        if frac <= 0:
            continue
        end = cur + bw * frac
        c.create_rectangle(cur, bar_y, end, bar_y + 9, fill=colors[name], outline="")
        cur = end

    legend_y = bar_y + 20
    lx = x0
    for name in ("Draw", "Straight", "Fade"):
        pct = round(100 * counts[name] / total)
        c.create_oval(lx, legend_y + 2, lx + 6, legend_y + 8,
                      fill=colors[name], outline="")
        c.create_text(lx + 11, legend_y + 5, text=f"{name} {pct}%",
                      fill=theme.TEXT_2, font=(_ui_font(), 8, "bold"), anchor="w")
        lx += max(88, bw / 3)


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    c = app.canvas
    _section_title(c, x0, y0, "Shot Shape")
    start, move = _movement(v)

    direction = "RIGHT → LEFT" if move < -1.5 else (
        "LEFT → RIGHT" if move > 1.5 else "MINIMAL CURVE")
    shape_id = c.create_text(x0, y0 + 43, text=v["shape"], fill=SHAPE_TEXT,
                             font=(_ui_font(), 18, "bold"), anchor="nw")
    bb = c.bbox(shape_id)
    direction_x = (bb[2] + 13) if bb else x0 + 120
    c.create_text(direction_x, y0 + 48, text=f"·  {direction}", fill=ORANGE,
                  font=(_ui_font(), 11, "bold"), anchor="nw")

    # Movement is the actual insight in this region.
    hero_y = y0 + 96
    c.create_text(x0, hero_y, text="Movement", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="nw")
    move_dir = "R" if move > 0.12 else ("L" if move < -0.12 else "")
    c.create_text(x0, hero_y + 20, text=f"{abs(move):.1f} yds {move_dir}".strip(),
                  fill=ORANGE, font=(_ui_font(), 25, "bold"), anchor="nw")

    ax0, ax1 = x0 + 12, x1 - 12
    ay = y0 + min(205, (y1 - y0) * .48)
    scale = max(5.0, abs(start) * 1.35, abs(v["offline"]) * 1.35)
    mid = (ax0 + ax1) / 2
    span = (ax1 - ax0) / 2

    def px(val):
        return mid + val / scale * span

    sx, ex, tx = px(start), px(v["offline"]), px(0.0)
    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE, width=1)
    c.create_line(tx, ay - 42, tx, ay + 46, fill=SOFT_LINE, dash=(3, 6))
    c.create_line(sx, ay, ex, ay, fill=BLUE_LINE, width=4, arrow="last",
                  arrowshape=(13, 15, 6))
    c.create_oval(sx - 8, ay - 8, sx + 8, ay + 8,
                  fill=theme.BG, outline=BLUE_LINE, width=2)
    land_col = _landing_color(v["offline"])
    c.create_oval(ex - 9, ay - 9, ex + 9, ay + 9,
                  fill=land_col, outline=theme.TEXT_2, width=1)

    # Start and finish are supporting facts and share one baseline below the graphic.
    fact_y = ay + 31
    c.create_text(sx, fact_y, text=f"START  {_side(start)} yds",
                  fill=theme.TEXT_2, font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(ex, fact_y, text=f"FINISH  {_side(v['offline'])} yds",
                  fill=land_col, font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(tx, ay + 59, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="n")

    # Replace the opaque 'consistency %' with the actual session distribution.
    mix_y = y1 - 82
    c.create_line(x0, mix_y - 14, x1, mix_y - 14, fill=SOFT_LINE)
    _draw_shape_mix(c, x0, mix_y, x1, shots)


def _draw_session_bottom(app, x0, y0, x1, y1, shots):
    """Session averages + trends; shape mix now lives where shape is explained."""
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
    _section_title(c, x0, y0, f"Session · {club}", f"{len(shots)} shots")

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
        c.create_text(xx, yy + 18, text=value, fill=SECTION_TEXT,
                      font=(_ui_font(), 11, "bold"), anchor="nw")

    c.create_line(split + 8, y0 + 4, split + 8, y1 - 4, fill=SOFT_LINE)

    trend_x0 = split + 34
    _section_title(c, trend_x0, y0, "Session Trends",
                   "Pattern information the Recent Shots rail does not show")

    recent = vals[-min(16, len(vals)):]
    carries = [v["carry"] for v in recent]
    balls = [v["ball"] for v in recent]
    spins = [v["spin"] for v in recent]
    offlines = [v["offline"] for v in recent]
    starts = [_movement(v)[0] for v in recent]
    moves = [_movement(v)[1] for v in recent]

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
         f"avg {abs(statistics.mean(moves)):.1f} · {_stat_sigma(moves, 'yds')}", moves, ORANGE),
        ("Ball Speed", f"{balls[-1]:.1f} mph",
         f"avg {statistics.mean(balls):.1f} · {_stat_sigma(balls, 'mph')}", balls, GOOD),
    ]

    trend_w = x1 - trend_x0
    col_gap = 28
    col_w = (trend_w - col_gap) / 2

    def draw_rows(rows, bx0, bx1):
        yy = y0 + 58
        for label, value, detail, arr, color in rows:
            c.create_text(bx0, yy, text=label, fill=theme.TEXT_2,
                          font=(_ui_font(), 10, "bold"), anchor="nw")
            c.create_text(bx0, yy + 22, text=value, fill=SECTION_TEXT,
                          font=(_ui_font(), 13, "bold"), anchor="nw")
            c.create_text(bx0 + 112, yy + 25, text=detail, fill=theme.TEXT_3,
                          font=(_ui_font(), 8), anchor="nw")
            _sparkline(c, bx0 + col_w * .63, yy + 24, bx1 - 4, arr, color)
            yy += 58

    draw_rows(left_rows, trend_x0, trend_x0 + col_w)
    draw_rows(right_rows, trend_x0 + col_w + col_gap, x1)


def draw_overview(app, avail_w, h, carry, total, ball_speed, club_speed, smash,
                  launch, spin, apex, offline, descent, hang_time, club_path,
                  face_to_path, spin_axis, face_to_target=0.0, shot_name="",
                  smash_clamped=False, offset_x=0, top_bar_h=52):
    c = app.canvas
    _depth_background(app, offset_x, top_bar_h, offset_x + avail_w, h)

    app.overview_viewall_rect = None
    app.overview_prev_rect = None
    app.overview_next_rect = None
    app.overview_bar_rects = []

    shots_all = list(app.session_shots)
    shots = _club_shots(app)
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
    _ribbon_surface(app, x0, y0, x1, y0 + top_h)
    c.create_line(x0, y0 + top_h, x1, y0 + top_h, fill=SOFT_LINE)
    c.create_rectangle(x0, y0, x0 + 4, y0 + top_h, fill=BLUE, outline="")

    n = len(shots_all)
    idx = app.selected_shot_index + 1 if app.selected_shot_index is not None else n
    identity_w = max(270, min(330, (x1 - x0) * .205))
    ix = x0 + 24
    club = (app.current_shot or {}).get("club") or app.current_club
    c.create_text(ix, y0 + 22, text=f"Shot {idx}", fill=theme.TEXT_2,
                  font=(_ui_font(), 12, "bold"), anchor="nw")
    c.create_text(ix + 78, y0 + 19, text=club, fill=BLUE_TEXT,
                  font=(_ui_font(), 16, "bold"), anchor="nw")
    c.create_text(ix, y0 + 58, text=(shot_name or "Straight"), fill=SECTION_TEXT,
                  font=(_ui_font(), 28, "bold"), anchor="nw")

    # Recent Shots rail is now the navigation mechanism: no redundant arrows.
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

    _draw_dispersion(app, dx0, main_y0, dx1, main_y1, shots)
    _draw_shape(app, sx0, main_y0, sx1, main_y1, v, shots)

    # Right side: Strike then Club Delivery. No redundant Ball Flight thumbnail.
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
