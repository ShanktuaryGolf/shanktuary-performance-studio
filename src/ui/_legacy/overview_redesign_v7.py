"""Seventh-pass Shot view: clearer hierarchy, neutral geometry, session separation."""

from __future__ import annotations

import math
import statistics

from PIL import Image, ImageDraw, ImageOps, ImageTk

import overview_redesign_v4 as v4
import overview_redesign_v5 as v5
import overview_redesign_v6 as v6
import theme

BLUE = v4.BLUE
BLUE_LINE = v4.BLUE_LINE
BLUE_TEXT = v4.BLUE_TEXT
ORANGE = v4.ORANGE
GOLD = getattr(theme, "GOLD", "#C89A4A")
GOOD = v4.GOOD

_values = v4._values
_movement = v4._movement
_side = v4._side
_ui_font = v4._ui_font
_mix = v4._mix
_club_speed = v5._club_speed
_draw_pair_metric = v5._draw_pair_metric
_sparkline = v5._sparkline

SOFT_LINE = _mix(theme.HAIRLINE, theme.BG, .50)
GRID_LINE = _mix(theme.GUIDE, theme.BG, .54)
SESSION_DOT = _mix(theme.TEXT_3, BLUE, .12)
ELLIPSE = _mix(BLUE_LINE, theme.BG, .40)
SECTION_TEXT = _mix(theme.TEXT, theme.TEXT_2, .52)
SHAPE_TEXT = _mix(theme.TEXT, theme.TEXT_2, .30)
NEUTRAL_POINT = _mix(theme.TEXT_2, BLUE, .08)
STRAIGHT = _mix(theme.TEXT_2, theme.BG, .16)
SESSION_BG_TOP = _mix(theme.BG, "#112033", .22)
SESSION_BG_BOTTOM = _mix(theme.BG, "#02060B", .20)


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _section_title(c, x, y, title, subtitle=None):
    c.create_text(x, y, text=title, fill=SECTION_TEXT,
                  font=(_ui_font(), 14, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x, y + 25, text=subtitle, fill=theme.TEXT_3,
                      font=(_ui_font(), 10), anchor="nw")


def _linear_surface(app, cache_prefix, w, h, top, bottom, left, right, grain=.022):
    key_name = f"_{cache_prefix}_key"
    img_name = f"_{cache_prefix}_img"
    key = (int(w), int(h))
    if getattr(app, key_name, None) == key:
        return getattr(app, img_name)

    iw, ih = max(1, int(w)), max(1, int(h))

    vertical = Image.new("RGB", (iw, ih), _rgb(top))
    vd = ImageDraw.Draw(vertical)
    ta, tb = _rgb(top), _rgb(bottom)
    for yy in range(0, ih, 4):
        t = yy / max(1, ih - 1)
        t = t * t * (3 - 2 * t)
        col = tuple(round(a + (b - a) * t) for a, b in zip(ta, tb))
        vd.rectangle((0, yy, iw, min(ih, yy + 4)), fill=col)

    horizontal = Image.new("RGB", (iw, ih), _rgb(left))
    hd = ImageDraw.Draw(horizontal)
    la, lb = _rgb(left), _rgb(right)
    for xx in range(0, iw, 4):
        t = xx / max(1, iw - 1)
        t = t * t * (3 - 2 * t)
        col = tuple(round(a + (b - a) * t) for a, b in zip(la, lb))
        hd.rectangle((xx, 0, min(iw, xx + 4), ih), fill=col)

    img = Image.blend(vertical, horizontal, .30)

    # A diagonal, non-radial lift. No identifiable glow shape.
    diag = Image.new("RGB", (iw, ih), _rgb(theme.BG))
    dd = ImageDraw.Draw(diag)
    steps = 72
    for i in range(steps):
        f = i / max(1, steps - 1)
        x = int(-iw * .18 + f * iw * 1.36)
        tint = _mix(theme.BG, "#17304A", .028 * (1 - abs(.48 - f) * 1.25))
        dd.polygon([(x - iw, 0), (x, 0), (x + ih, ih), (x + ih - iw, ih)],
                   fill=_rgb(tint))
    img = Image.blend(img, diag, .10)

    if grain:
        try:
            noise = Image.effect_noise((iw, ih), 15).convert("L")
            noise_col = ImageOps.colorize(noise, black="#05080D", white="#192636")
            img = Image.blend(img, noise_col, grain)
        except Exception:
            pass

    photo = ImageTk.PhotoImage(img)
    setattr(app, img_name, photo)
    setattr(app, key_name, key)
    return photo


def _depth_background(app, x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    img = _linear_surface(
        app, "overview_v7_bg", w, h,
        top="#0D1723", bottom="#05080D",
        left="#07101A", right="#0A1421", grain=.025,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _ribbon_surface(app, x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    img = _linear_surface(
        app, "overview_v7_ribbon", w, h,
        top="#152236", bottom="#0A101A",
        left="#13253B", right="#0B111A", grain=.014,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _session_surface(app, x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    img = _linear_surface(
        app, "overview_v7_session", w, h,
        top=SESSION_BG_TOP, bottom=SESSION_BG_BOTTOM,
        left="#07111C", right="#0B1018", grain=.018,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")

    # Explicit transition: cool current-shot area -> warmer session analysis edge.
    steps = 80
    for i in range(steps):
        t = i / max(1, steps - 1)
        col = _mix(BLUE_LINE, ORANGE, t)
        sx0 = x0 + (x1 - x0) * i / steps
        sx1 = x0 + (x1 - x0) * (i + 1) / steps
        app.canvas.create_rectangle(sx0, y0, sx1 + 1, y0 + 2, fill=col, outline="")


def _club_shots(app):
    club = (app.current_shot or {}).get("club") or app.current_club
    shots = [s for s in app.session_shots if not s.get("excluded", False)]
    subset = [s for s in shots if (s.get("club") or "") == club]
    return subset or shots


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    _section_title(c, x0, y0, "Dispersion", f"{club} · carry landing pattern")

    points = [(_values(s), s) for s in shots]
    points = [(vv, ss) for vv, ss in points if vv["carry"] > 0]
    if not points:
        return

    left, right = x0 + 46, x1 - 18
    top, bottom = y0 + 64, y1 - 48
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    carry_half = 2 * max(1.5, sc)
    raw_min = min(min(carries), mc - carry_half)
    raw_max = max(max(carries), mc + carry_half)
    raw_span = max(8.0, raw_max - raw_min)
    pad = raw_span * .08
    cmin, cmax = raw_min - pad, raw_max + pad

    lateral_extent = max(
        5.0,
        max(abs(v) for v in offs),
        abs(mo) + 2 * max(1.0, so),
    )
    omax = lateral_extent * 1.08

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
        c.create_text(left - 9, gy, text=f"{val:.0f}", fill=theme.TEXT_3,
                      font=(_ui_font(), 8), anchor="e")
    c.create_line(tx, top, tx, bottom, fill=GRID_LINE, dash=(4, 6))

    ex0, ex1 = sx(mo - 2 * max(1, so)), sx(mo + 2 * max(1, so))
    ey0, ey1 = sy(mc + carry_half), sy(mc - carry_half)
    c.create_oval(ex0, ey0, ex1, ey1, outline=ELLIPSE, width=2)
    c.create_text(ex1 - 7, ey0 + 8, text="2σ dispersion", fill=_mix(BLUE_TEXT, theme.BG, .22),
                  font=(_ui_font(), 9, "bold"), anchor="ne")

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            c.create_oval(px - 8, py - 8, px + 8, py + 8, fill=BLUE, outline="")
        else:
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill=SESSION_DOT, outline="")

    c.create_text(left, bottom + 15, text=f"{omax:.0f}L", fill=theme.TEXT_3,
                  font=(_ui_font(), 9), anchor="n")
    c.create_text(tx, bottom + 15, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(right, bottom + 15, text=f"{omax:.0f}R", fill=theme.TEXT_3,
                  font=(_ui_font(), 9), anchor="n")

    c.create_oval(x0 + 2, y1 - 19, x0 + 12, y1 - 9, fill=BLUE, outline="")
    c.create_text(x0 + 18, y1 - 14, text="Current shot", fill=theme.TEXT_2,
                  font=(_ui_font(), 10), anchor="w")
    c.create_oval(x0 + 120, y1 - 18, x0 + 126, y1 - 12, fill=SESSION_DOT, outline="")
    c.create_text(x0 + 132, y1 - 15, text=f"Session ({len(points)})", fill=theme.TEXT_2,
                  font=(_ui_font(), 10), anchor="w")


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


def _draw_segment(c, x0, x1, y0, h, color, round_left=False, round_right=False):
    r = h / 2
    left = x0 + (r if round_left else 0)
    right = x1 - (r if round_right else 0)
    if right > left:
        c.create_rectangle(left, y0, right, y0 + h, fill=color, outline="")
    if round_left:
        c.create_oval(x0, y0, x0 + h, y0 + h, fill=color, outline="")
    if round_right:
        c.create_oval(x1 - h, y0, x1, y0 + h, fill=color, outline="")


def _draw_shape_mix(c, x0, y0, x1, shots):
    counts, total = _shape_mix(shots)
    if not total:
        return

    colors = {"Draw": BLUE_LINE, "Straight": STRAIGHT, "Fade": ORANGE}
    c.create_text(x0, y0, text="Session Shape Mix",
                  fill=theme.TEXT_2, font=(_ui_font(), 10, "bold"), anchor="nw")
    bar_y = y0 + 28
    bar_h = 10
    bw = x1 - x0

    visible = [name for name in ("Draw", "Straight", "Fade") if counts[name] > 0]
    cur = x0
    for i, name in enumerate(visible):
        frac = counts[name] / total
        end = x1 if i == len(visible) - 1 else cur + bw * frac
        _draw_segment(
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
                      fill=theme.TEXT_2, font=(_ui_font(), 9, "bold"), anchor="w")
        lx += max(98, bw / 3)


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    c = app.canvas
    _section_title(c, x0, y0, "Shot Shape")
    start, move = _movement(v)

    direction = "Right → Left" if move < -1.5 else (
        "Left → Right" if move > 1.5 else "Minimal curve")
    shape_id = c.create_text(x0, y0 + 43, text=v["shape"], fill=SHAPE_TEXT,
                             font=(_ui_font(), 18, "bold"), anchor="nw")
    bb = c.bbox(shape_id)
    direction_x = (bb[2] + 12) if bb else x0 + 120
    c.create_text(direction_x, y0 + 46, text=f"·  {direction}", fill=ORANGE,
                  font=(_ui_font(), 13, "bold"), anchor="nw")

    hero_y = y0 + 95
    c.create_text(x0, hero_y, text="Movement", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    move_dir = "R" if move > 0.12 else ("L" if move < -0.12 else "")
    c.create_text(x0, hero_y + 23, text=f"{abs(move):.1f} yds {move_dir}".strip(),
                  fill=ORANGE, font=(_ui_font(), 28, "bold"), anchor="nw")

    ax0, ax1 = x0 + 14, x1 - 14
    ay = y0 + min(216, (y1 - y0) * .49)
    scale = max(5.0, abs(start) * 1.35, abs(v["offline"]) * 1.35)
    mid = (ax0 + ax1) / 2
    span = (ax1 - ax0) / 2

    def px(val):
        return mid + val / scale * span

    sx, ex, tx = px(start), px(v["offline"]), px(0.0)
    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE, width=1)
    c.create_line(tx, ay - 42, tx, ay + 43, fill=SOFT_LINE, dash=(3, 6))
    c.create_line(sx, ay, ex, ay, fill=BLUE_LINE, width=4, arrow="last",
                  arrowshape=(13, 15, 6))
    c.create_oval(sx - 8, ay - 8, sx + 8, ay + 8,
                  fill=theme.BG, outline=BLUE_LINE, width=2)
    c.create_oval(ex - 9, ay - 9, ex + 9, ay + 9,
                  fill=NEUTRAL_POINT, outline=theme.TEXT_2, width=1)

    # Labels are fixed to the panel edges so nearly-straight shots never collide.
    fact_y = ay + 31
    c.create_text(x0 + 4, fact_y, text="START", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="nw")
    c.create_text(x0 + 4, fact_y + 19, text=f"{_side(start)} yds", fill=BLUE_TEXT,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    c.create_text(x1 - 4, fact_y, text="FINISH", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="ne")
    c.create_text(x1 - 4, fact_y + 19, text=f"{_side(v['offline'])} yds",
                  fill=SECTION_TEXT, font=(_ui_font(), 11, "bold"), anchor="ne")
    c.create_text(tx, fact_y + 47, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="n")

    mix_y = y1 - 86
    c.create_line(x0, mix_y - 14, x1, mix_y - 14, fill=SOFT_LINE)
    _draw_shape_mix(c, x0, mix_y, x1, shots)


def _draw_strike(app, x0, y0, x1, y1):
    c = app.canvas
    title_id = c.create_text(x0, y0, text="Strike", fill=SECTION_TEXT,
                             font=(_ui_font(), 14, "bold"), anchor="nw")
    bb = c.bbox(title_id)
    tx = (bb[2] + 8) if bb else x0 + 50
    c.create_text(tx, y0 + 1, text="· Estimated", fill=ORANGE,
                  font=(_ui_font(), 11, "bold"), anchor="nw")

    head, detail, _hcol = app.summarize_strike(app.current_shot)
    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else SECTION_TEXT
    c.create_text(x0, y0 + 53, text=head, fill=col,
                  font=(_ui_font(), 15, "bold"), anchor="nw")
    c.create_text(x0, y0 + 81, text=detail, fill=theme.TEXT_3,
                  font=(_ui_font(), 10), anchor="nw",
                  width=max(110, int((x1 - x0) * .34)))

    face_cx = x0 + (x1 - x0) * .73
    face_cy = y0 + (y1 - y0) * .54
    face_size = max(136, min(188, (y1 - y0) * .76, (x1 - x0) * .55))
    app._draw_overview_face(face_cx, face_cy, face_size)


def _draw_delivery(app, x0, y0, x1, y1, v):
    c = app.canvas
    _section_title(c, x0, y0, "Club Delivery")

    w = x1 - x0
    table_w = w * .43
    rows = [
        ("Path", f"{abs(v['path']):.1f}° {'in→out' if v['path'] >= 0 else 'out→in'}"),
        ("Face / Path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"),
        ("Face / Target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"),
        ("Spin Axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]
    yy = y0 + 39
    for label, value in rows:
        c.create_text(x0, yy, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(x0 + table_w * .47, yy - 1, text=value, fill=SECTION_TEXT,
                      font=(_ui_font(), 10, "bold"), anchor="nw")
        yy += 24

    gx0, gx1 = x0 + table_w + 8, x1 - 6
    cx = (gx0 + gx1) / 2
    cy = y0 + (y1 - y0) * .60
    length = min(62, (y1 - y0) * .30)
    hand = str(getattr(app, "dexterity", "RH") or "RH").upper()
    mirror = -1 if hand == "LH" else 1

    # Target is always up-screen. A RH in-to-out path travels lower-left -> upper-right;
    # LH mirrors that geometry.
    c.create_line(cx, cy + length + 13, cx, cy - length - 18,
                  fill=GRID_LINE, dash=(3, 5))
    c.create_text(cx, cy - length - 22, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="s")

    path_deg = max(-12.0, min(12.0, v["path"]))
    dx = math.tan(math.radians(path_deg)) * length * mirror
    x_start, y_start = cx - dx, cy + length
    x_end, y_end = cx + dx, cy - length
    c.create_line(x_start, y_start, x_end, y_end, fill=BLUE_LINE, width=3,
                  arrow="last", arrowshape=(11, 13, 5))
    c.create_text(x_end + (8 if mirror > 0 else -8), y_end + 8, text="PATH",
                  fill=BLUE_TEXT, font=(_ui_font(), 8, "bold"),
                  anchor="w" if mirror > 0 else "e")

    # Clubface line at impact. Open/closed mirrors with handedness.
    face_deg = max(-16.0, min(16.0, v["face_target"])) * mirror
    theta = math.radians(face_deg)
    half = 28
    fx = math.cos(theta) * half
    fy = math.sin(theta) * half
    c.create_line(cx - fx, cy - fy, cx + fx, cy + fy, fill=ORANGE, width=4)
    c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                  fill=theme.TEXT_2, outline=theme.BG)
    c.create_text(cx + fx + 7, cy + fy, text="FACE", fill=ORANGE,
                  font=(_ui_font(), 8, "bold"), anchor="w")


def _sd(vals, unit=""):
    if len(vals) <= 1:
        return "SD —"
    val = statistics.pstdev(vals)
    if unit == "rpm":
        return f"SD {val:.0f} {unit}"
    return f"SD {val:.1f}{(' ' + unit) if unit else ''}"


def _draw_session_bottom(app, x0, y0, x1, y1, shots):
    c = app.canvas
    vals = [_values(s) for s in shots]
    if not vals:
        return

    club = (app.current_shot or {}).get("club") or app.current_club
    recent = vals[-min(16, len(vals)):]
    carries = [v["carry"] for v in recent]
    balls = [v["ball"] for v in recent]
    spins = [v["spin"] for v in recent]
    offlines = [v["offline"] for v in recent]
    starts = [_movement(v)[0] for v in recent]
    moves = [_movement(v)[1] for v in recent]

    c.create_text(x0, y0 + 16, text=f"Session Pattern · {club}", fill=SECTION_TEXT,
                  font=(_ui_font(), 14, "bold"), anchor="nw")
    c.create_text(x1, y0 + 18, text=f"{len(vals)} shots", fill=theme.TEXT_2,
                  font=(_ui_font(), 10, "bold"), anchor="ne")

    rows_left = [
        ("Carry", f"Avg {statistics.mean(carries):.1f} yds", _sd(carries, "yds"), carries, BLUE_LINE),
        ("Spin", f"Avg {statistics.mean(spins):.0f} rpm", _sd(spins, "rpm"), spins, GOLD),
        ("Offline", f"Avg {_side(statistics.mean(offlines))} yds", _sd(offlines, "yds"), offlines, ORANGE),
    ]
    rows_right = [
        ("Start Line", f"Avg {_side(statistics.mean(starts))} yds", _sd(starts, "yds"), starts, BLUE_TEXT),
        ("Curve Movement",
         f"Avg {abs(statistics.mean(moves)):.1f}{'L' if statistics.mean(moves) < 0 else 'R'} yds",
         _sd(moves, "yds"), moves, ORANGE),
        ("Ball Speed", f"Avg {statistics.mean(balls):.1f} mph", _sd(balls, "mph"), balls, GOOD),
    ]

    total_w = x1 - x0
    gap = 34
    col_w = (total_w - gap) / 2

    def draw_rows(rows, bx0, bx1):
        yy = y0 + 54
        for label, avg_text, detail, arr, color in rows:
            c.create_text(bx0, yy, text=label, fill=theme.TEXT_2,
                          font=(_ui_font(), 10, "bold"), anchor="nw")
            c.create_text(bx0, yy + 22, text=avg_text, fill=SECTION_TEXT,
                          font=(_ui_font(), 13, "bold"), anchor="nw")
            c.create_text(bx0 + 135, yy + 25, text=detail, fill=theme.TEXT_3,
                          font=(_ui_font(), 9), anchor="nw")
            _sparkline(c, bx0 + col_w * .64, yy + 24, bx1 - 4, arr, color)
            yy += 56

    draw_rows(rows_left, x0, x0 + col_w)
    draw_rows(rows_right, x0 + col_w + gap, x1)


def _fmt_hla(hla):
    if abs(hla) < .05:
        return "0.0°"
    return f"{abs(hla):.1f}° {'R' if hla > 0 else 'L'}"


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
    _draw_pair_metric(c, mx0 + step * 2 + 16, y0 + 22, mx0 + step * 3,
                      "VLA", f"{launch:.1f}°", "",
                      "HLA", _fmt_hla(v.get("hlaunch", 0.0)), "")
    v5._draw_single_metric(c, mx0 + step * 3 + 16, y0 + 22,
                           "Spin Rate", f"{spin:.0f}", "rpm")
    v5._draw_single_metric(c, mx0 + step * 4 + 16, y0 + 22,
                           "Apex", f"{apex * 3:.0f}", "ft")
    v5._draw_single_metric(c, mx0 + step * 5 + 16, y0 + 22,
                           "Offline", _side(offline), "yds")

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

    strike_h = main_h * .55
    sy1 = main_y0 + strike_h
    dy0 = sy1 + 12
    c.create_line(rx0, sy1 + 4, rx1, sy1 + 4, fill=SOFT_LINE)
    _draw_strike(app, rx0, main_y0, rx1, sy1)
    _draw_delivery(app, rx0, dy0, rx1, main_y1, v)

    by0, by1 = main_y1 + gap, h - 16
    if by1 - by0 >= 170:
        _session_surface(app, x0, by0 - 7, x1, by1)
        _draw_session_bottom(app, x0, by0 - 7, x1, by1, shots)
