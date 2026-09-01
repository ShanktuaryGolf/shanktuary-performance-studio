"""Fourth-pass Overview based on the accepted high-fidelity mockup.

Goals:
- larger, calmer typography across the whole page
- no visible background illustration; use matte graphite/navy depth + fine grain
- preserve a large dispersion hero and the Start -> Move -> Land explanation
- stack Strike -> Club Delivery -> Ball Flight in the right cause column
- keep the bottom session context readable without returning to card-grid chrome
"""

from __future__ import annotations

import math
import statistics

from PIL import Image, ImageDraw, ImageOps, ImageTk

import overview_redesign_v2 as v2
import theme

BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")
GOOD = getattr(theme, "GOOD", "#39A879")
ORANGE = getattr(theme, "WARN", "#F47A32")
RED = getattr(theme, "DANGER", "#E34A4A")

_values = v2._values
_movement = v2._movement
_side = v2._side
_shape_consistency = v2._shape_consistency

_FONT = None


def _ui_font():
    """A slightly more authored display face when the platform provides one."""
    global _FONT
    if _FONT is not None:
        return _FONT
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families())
        for cand in (
            "Avenir Next", "Inter", "SF Pro Text", "SF Pro Display",
            "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial",
        ):
            if cand in fams:
                _FONT = cand
                return cand
    except Exception:
        pass
    _FONT = theme.ui_font()
    return _FONT


def _mix(a: str, b: str, t: float) -> str:
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.BG


SOFT_LINE = _mix(theme.HAIRLINE, theme.BG, .44)
MUTED_DOT = _mix(theme.TEXT_3, theme.BG, .18)
SESSION_DOT = _mix(theme.TEXT_3, BLUE, .16)
RIBBON = _mix(theme.SURFACE, BLUE, .018)


def _rgb(hex_color: str):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _matte_background(app, x0, y0, x1, y1):
    """Dark dimensional material: gradient + vignette + photographic-like grain."""
    w = max(1, int(x1 - x0))
    h = max(1, int(y1 - y0))
    key = (w, h)
    if getattr(app, "_overview_bg_key", None) != key:
        base = Image.new("RGB", (w, h), _rgb(theme.BG))
        draw = ImageDraw.Draw(base)

        top = _rgb(_mix(theme.BG, "#12345A", .11))
        bottom = _rgb(_mix(theme.BG, "#020408", .16))
        # 3px bands are visually continuous and cheaper than per-pixel loops.
        for yy in range(0, h, 3):
            t = yy / max(1, h - 1)
            eased = t * t * (3 - 2 * t)
            col = tuple(round(a + (b - a) * eased) for a, b in zip(top, bottom))
            draw.rectangle((0, yy, w, min(h, yy + 3)), fill=col)

        # Quiet right-side/navy bloom; no recognizable motif or geometry.
        glow = Image.new("RGB", (w, h), _rgb(theme.BG))
        gd = ImageDraw.Draw(glow)
        for i in range(18, 0, -1):
            frac = i / 18
            radius_x = int(w * (.13 + frac * .26))
            radius_y = int(h * (.12 + frac * .34))
            cx, cy = int(w * .72), int(h * .24)
            col = _rgb(_mix(theme.BG, BLUE, .012 + .022 * frac))
            gd.ellipse((cx - radius_x, cy - radius_y, cx + radius_x, cy + radius_y), fill=col)
        base = Image.blend(base, glow, .18)

        # Fine matte grain. At this opacity it reads as material, not decoration.
        try:
            noise = Image.effect_noise((w, h), 16).convert("L")
            noise_col = ImageOps.colorize(noise, black="#05080D", white="#1A2635")
            base = Image.blend(base, noise_col, .035)
        except Exception:
            pass

        # Very soft edge vignette.
        try:
            mask = Image.radial_gradient("L").resize((w, h))
            mask = mask.point(lambda p: max(0, min(255, int((p - 70) * 0.55))))
            dark = Image.new("RGB", (w, h), _rgb("#020407"))
            base = Image.composite(dark, base, mask)
        except Exception:
            pass

        app._overview_bg_img = ImageTk.PhotoImage(base)
        app._overview_bg_key = key
    app.canvas.create_image(x0, y0, image=app._overview_bg_img, anchor="nw")


def _section_title(c, x, y, title, subtitle=None):
    c.create_text(x, y, text=title, fill=theme.TEXT,
                  font=(_ui_font(), 14, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x, y + 25, text=subtitle, fill=theme.TEXT_3,
                      font=(_ui_font(), 9), anchor="nw")


def _club_shots(app):
    club = (app.current_shot or {}).get("club") or app.current_club
    return [s for s in app.session_shots if (s.get("club") or "") == club]


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

    left, right = x0 + 44, x1 - 18
    top, bottom = y0 + 64, y1 - 48
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    cmin = min(carries + [mc - max(5, sc * 3)])
    cmax = max(carries + [mc + max(5, sc * 3)])
    pad = max(3, (cmax - cmin) * .14)
    cmin, cmax = cmin - pad, cmax + pad
    omax = max(6, max(abs(vv) for vv in offs) * 1.4, abs(mo) + so * 3)
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    # Gentle target rings. They are part of the chart, not background decor.
    tx = sx(0)
    midy = sy(mc)
    ring_col = _mix(theme.GUIDE, theme.BG, .18)
    for frac in (.35, .68, 1.0):
        rw = pw * .28 * frac
        rh = ph * .36 * frac
        c.create_oval(tx - rw, midy - rh, tx + rw, midy + rh,
                      outline=ring_col, width=1)

    for frac in (.25, .5, .75):
        gy = top + ph * frac
        val = cmax - (cmax - cmin) * frac
        c.create_line(left, gy, right, gy, fill=SOFT_LINE, dash=(2, 5))
        c.create_text(left - 9, gy, text=f"{val:.0f}", fill=theme.TEXT_3,
                      font=(_ui_font(), 8), anchor="e")
    c.create_line(tx, top, tx, bottom, fill=theme.GUIDE, dash=(4, 5))

    # 2 sigma landing pattern.
    c.create_oval(sx(mo - 2 * max(1, so)), sy(mc + 2 * max(1.5, sc)),
                  sx(mo + 2 * max(1, so)), sy(mc - 2 * max(1.5, sc)),
                  outline=BLUE_LINE, width=1, dash=(6, 5))

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            c.create_oval(px - 13, py - 13, px + 13, py + 13,
                          outline=BLUE_LINE, width=2)
            c.create_oval(px - 7, py - 7, px + 7, py + 7,
                          fill=BLUE, outline=theme.TEXT, width=1)
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
    c.create_oval(x0 + 2, y1 - 19, x0 + 10, y1 - 11, outline=BLUE_LINE, width=2)
    c.create_text(x0 + 16, y1 - 15, text="Current shot", fill=theme.TEXT_2,
                  font=(_ui_font(), 9), anchor="w")
    c.create_oval(x0 + 103, y1 - 18, x0 + 109, y1 - 12, fill=SESSION_DOT, outline="")
    c.create_text(x0 + 115, y1 - 15, text=f"All shots ({len(points)})", fill=theme.TEXT_2,
                  font=(_ui_font(), 9), anchor="w")
    c.create_text(x1 - 2, y1 - 15,
                  text=f"{cv['carry']:.1f} yds  ·  {_side(cv['offline'])} yds",
                  fill=theme.TEXT, font=(_ui_font(), 10, "bold"), anchor="e")


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    c = app.canvas
    _section_title(c, x0, y0, "Shot Shape & Movement")
    start, move = _movement(v)
    consistency, move_std = _shape_consistency(shots, move)

    c.create_text(x0, y0 + 48, text=v["shape"], fill=theme.TEXT,
                  font=(_ui_font(), 19, "bold"), anchor="nw")
    direction = "RIGHT → LEFT" if move < -1.5 else (
        "LEFT → RIGHT" if move > 1.5 else "MINIMAL CURVE")
    c.create_text(x0, y0 + 80, text=direction, fill=theme.TEXT_2,
                  font=(_ui_font(), 9, "bold"), anchor="nw")

    ax0, ax1 = x0 + 10, x1 - 10
    ay = y0 + min(205, (y1 - y0) * .47)
    scale = max(5.0, abs(start) * 1.35, abs(v["offline"]) * 1.35)
    mid = (ax0 + ax1) / 2
    span = (ax1 - ax0) / 2

    def px(val):
        return mid + val / scale * span

    sx, ex, tx = px(start), px(v["offline"]), px(0.0)
    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE, width=1)
    c.create_line(tx, ay - 54, tx, ay + 58, fill=SOFT_LINE, dash=(3, 5))
    c.create_text(tx, ay + 65, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="n")

    c.create_line(sx, ay, ex, ay, fill=BLUE_LINE, width=3, arrow="last",
                  arrowshape=(12, 14, 6))
    c.create_oval(sx - 8, ay - 8, sx + 8, ay + 8,
                  fill=theme.BG, outline=BLUE_LINE, width=2)
    land_col = _landing_color(v["offline"])
    c.create_oval(ex - 9, ay - 9, ex + 9, ay + 9,
                  fill=land_col, outline=theme.TEXT, width=1)

    # Three clear facts above the line.
    c.create_text(sx, ay - 58, text="START", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="s")
    c.create_text(sx, ay - 38, text=f"{_side(start)} yds", fill=BLUE_TEXT,
                  font=(_ui_font(), 11, "bold"), anchor="s")
    label_x = (sx + ex) / 2
    c.create_text(label_x, ay - 58, text="MOVED", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="s")
    c.create_text(label_x, ay - 38, text=f"{abs(move):.1f} yds", fill=BLUE_TEXT,
                  font=(_ui_font(), 12, "bold"), anchor="s")
    c.create_text(ex, ay + 20, text="LANDED", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="n")
    c.create_text(ex, ay + 42, text=f"{_side(v['offline'])} yds", fill=land_col,
                  font=(_ui_font(), 11, "bold"), anchor="n")

    # Consistency reads as a quiet footer, not another card.
    cy = y1 - 74
    c.create_line(x0, cy - 13, x1, cy - 13, fill=SOFT_LINE)
    c.create_text(x0, cy, text="Shape consistency", fill=theme.TEXT_2,
                  font=(_ui_font(), 10), anchor="nw")
    c.create_text(x1, cy - 4, text=f"{consistency}%", fill=theme.TEXT,
                  font=(_ui_font(), 18, "bold"), anchor="ne")
    bx0, bx1, by = x0, x1, cy + 28
    seg_gap, segs = 4, 10
    seg_w = (bx1 - bx0 - seg_gap * (segs - 1)) / segs
    filled = round(consistency / 10)
    for i in range(segs):
        xx = bx0 + i * (seg_w + seg_gap)
        c.create_rectangle(xx, by, xx + seg_w, by + 7,
                           fill=BLUE if i < filled else _mix(theme.SURFACE_2, theme.BG, .30), outline="")
    club = (app.current_shot or {}).get("club") or app.current_club
    c.create_text(x0, y1 - 12,
                  text=f"{len(shots)} {club} shots · movement σ {move_std:.1f} yds",
                  fill=theme.TEXT_3, font=(_ui_font(), 9), anchor="sw")


def _draw_strike(app, x0, y0, x1, y1):
    c = app.canvas
    _section_title(c, x0, y0, "Strike")
    head, detail, hcol = app.summarize_strike(app.current_shot)
    if hcol == theme.WARN:
        c.create_text(x0, y0 + 26, text="EST.", fill=ORANGE,
                      font=(_ui_font(), 8, "bold"), anchor="nw")

    # Larger clubhead: it should feel like evidence, not a thumbnail.
    face_cx = x0 + (x1 - x0) * .66
    face_cy = y0 + (y1 - y0) * .56
    face_size = max(128, min(180, (y1 - y0) * .78))
    app._draw_overview_face(face_cx, face_cy, face_size)

    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else theme.TEXT
    c.create_text(x0 + 12, y0 + 58, text=head, fill=col,
                  font=(_ui_font(), 15, "bold"), anchor="nw")
    c.create_text(x0 + 12, y0 + 87, text=detail, fill=theme.TEXT_3,
                  font=(_ui_font(), 9), anchor="nw", width=max(100, int((x1 - x0) * .36)))


def _draw_delivery(app, x0, y0, x1, y1, v):
    c = app.canvas
    _section_title(c, x0, y0, "Club Delivery")
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
        c.create_text(x0 + 116, yy - 1, text=value, fill=theme.TEXT,
                      font=(_ui_font(), 10, "bold"), anchor="nw")
        yy += 25

    cx = x0 + (x1 - x0) * .78
    cy = y0 + (y1 - y0) * .58
    span = min(48, (x1 - x0) * .15)
    c.create_line(cx - span, cy, cx + span, cy, fill=theme.GUIDE, dash=(3, 4))
    pdy = -math.tan(math.radians(max(-12, min(12, v['path'])))) * span
    c.create_line(cx - span, cy + pdy, cx + span, cy - pdy,
                  fill=BLUE_LINE, width=2, arrow="last")
    ang = math.radians(max(-16, min(16, v['face_target'])))
    dx, dy = math.sin(ang) * 27, math.cos(ang) * 27
    c.create_line(cx - dx, cy + dy, cx + dx, cy - dy, fill=ORANGE, width=3)


def _draw_flight(app, x0, y0, x1, y1, v):
    c = app.canvas
    _section_title(c, x0, y0, "Ball Flight")
    rows = [
        ("Launch Angle", f"{v['launch']:.1f}°"),
        ("Apex", f"{v['apex'] * 3:.0f} ft"),
        ("Descent Angle", f"{v['descent']:.1f}°"),
        ("Hang Time", f"{v['hang']:.1f} s"),
    ]
    yy = y0 + 40
    for label, value in rows:
        c.create_text(x0, yy, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(x0 + 116, yy - 1, text=value, fill=theme.TEXT,
                      font=(_ui_font(), 10, "bold"), anchor="nw")
        yy += 26

    # Trajectory sketch on the right.
    gx0 = x0 + (x1 - x0) * .56
    gx1 = x1 - 8
    gy1 = y1 - 10
    gy0 = y0 + 35
    if gx1 - gx0 > 60 and gy1 - gy0 > 45:
        pts = []
        for i in range(31):
            t = i / 30
            xx = gx0 + (gx1 - gx0) * t
            yy2 = gy1 - (gy1 - gy0) * (4 * t * (1 - t)) * .78
            pts.extend((xx, yy2))
        c.create_line(*pts, fill=BLUE_LINE, width=2, smooth=True)
        c.create_line(gx0, gy1, gx1, gy1, fill=theme.GUIDE, dash=(4, 5))
        apex_i = len(pts) // 2
        ax, ay = pts[apex_i - apex_i % 2], pts[apex_i - apex_i % 2 + 1]
        c.create_oval(ax - 3, ay - 3, ax + 3, ay + 3, fill=theme.TEXT, outline=BLUE_LINE)


def _sparkline(c, x0, y, x1, vals, color):
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    span = max(.001, hi - lo)
    pts = []
    for i, val in enumerate(vals):
        xx = x0 + (x1 - x0) * (i / max(1, len(vals) - 1))
        yy = y + 9 - ((val - lo) / span) * 18
        pts.extend((xx, yy))
    if len(pts) >= 4:
        c.create_line(*pts, fill=color, width=1, smooth=True)
        for i in range(0, len(pts), 2):
            c.create_oval(pts[i] - 1.5, pts[i + 1] - 1.5, pts[i] + 1.5, pts[i + 1] + 1.5,
                          fill=color, outline="")


def _draw_bottom(app, x0, y0, x1, y1, shots):
    c = app.canvas
    w = x1 - x0
    sw = w * .22
    tw = w * .47
    sx1 = x0 + sw
    tx0, tx1 = sx1 + 26, sx1 + 26 + tw
    rx0 = tx1 + 26

    # Session summary
    _section_title(c, x0, y0, "Session Summary")
    vals = [_values(s) for s in shots]
    if not vals:
        return
    avg = lambda k: statistics.mean(v[k] for v in vals)
    summary = [
        ("Shots", f"{len(vals)}"),
        ("Avg Carry", f"{avg('carry'):.1f} yds"),
        ("Avg Ball Speed", f"{avg('ball'):.1f} mph"),
        ("Avg Launch Angle", f"{avg('launch'):.1f}°"),
        ("Avg Spin Rate", f"{avg('spin'):.0f} rpm"),
        ("Avg Smash Factor", f"{avg('smash'):.2f}"),
    ]
    colw = max(112, (sw - 8) / 2)
    for i, (label, value) in enumerate(summary):
        col, row = i % 2, i // 2
        xx = x0 + col * colw
        yy = y0 + 48 + row * 58
        c.create_text(xx, yy, text=label, fill=theme.TEXT_3,
                      font=(_ui_font(), 8), anchor="nw")
        c.create_text(xx, yy + 21, text=value, fill=theme.TEXT,
                      font=(_ui_font(), 11, "bold"), anchor="nw")

    c.create_line(sx1 + 12, y0 + 4, sx1 + 12, y1 - 4, fill=SOFT_LINE)

    # Recent shots table
    club = (app.current_shot or {}).get("club") or app.current_club
    _section_title(c, tx0, y0, f"Recent Shots ({club})")
    recent = list(reversed(shots))[:5]
    table_y = y0 + 43
    headers = [("#", .00), ("Carry", .09), ("Ball", .25), ("Launch", .42),
               ("Spin", .57), ("Offline", .72), ("Shape", .84)]
    for label, frac in headers:
        c.create_text(tx0 + tw * frac, table_y, text=label, fill=theme.TEXT_3,
                      font=(_ui_font(), 7, "bold"), anchor="nw")
    row_y = table_y + 25
    for i, shot in enumerate(recent):
        vv = _values(shot)
        idx = app.session_shots.index(shot) + 1
        selected = shot is app.current_shot
        if selected:
            c.create_rectangle(tx0 - 5, row_y - 6, tx1, row_y + 17,
                               fill=_mix(theme.SURFACE_2, BLUE, .08), outline="")
            c.create_rectangle(tx0 - 5, row_y - 6, tx0 - 2, row_y + 17, fill=BLUE, outline="")
        cells = [
            (f"{idx}", .00), (f"{vv['carry']:.1f}", .09), (f"{vv['ball']:.1f}", .25),
            (f"{vv['launch']:.1f}°", .42), (f"{vv['spin']:.0f}", .57),
            (_side(vv['offline']), .72), (vv['shape'], .84),
        ]
        for value, frac in cells:
            c.create_text(tx0 + tw * frac, row_y, text=value,
                          fill=theme.TEXT if selected else theme.TEXT_2,
                          font=(_ui_font(), 8, "bold" if selected else "normal"), anchor="nw")
        row_y += 27
    app.overview_viewall_rect = (tx0 + tw * .54, y1 - 30, tx1, y1)
    c.create_text(tx1, y1 - 16, text="View all shots in Table  →", fill=BLUE_TEXT,
                  font=(_ui_font(), 9, "bold"), anchor="e")

    c.create_line(tx1 + 12, y0 + 4, tx1 + 12, y1 - 4, fill=SOFT_LINE)

    # Tendencies
    _section_title(c, rx0, y0, "Tendencies", f"Last {min(16, len(shots))} shots")
    recent_t = shots[-min(16, len(shots)):]
    tv = [_values(s) for s in recent_t]
    starts = [_movement(v)[0] for v in tv]
    moves = [_movement(v)[1] for v in tv]
    offs = [v['offline'] for v in tv]
    carries = [v['carry'] for v in tv]
    cons, _ = _shape_consistency(recent_t, _movement(_values(app.current_shot))[1])
    rows = [
        ("Start Direction", _side(starts[-1]), starts, BLUE_LINE),
        ("Curve Movement", f"{abs(moves[-1]):.1f}{'L' if moves[-1] < 0 else 'R'}", moves, GOOD),
        ("Offline", _side(offs[-1]), offs, ORANGE),
        ("Carry", f"{carries[-1]:.1f}", carries, BLUE_TEXT),
        ("Shape Consistency", f"{cons}%", [cons] * max(2, len(tv)), "#C89A4A"),
    ]
    yy = y0 + 50
    for label, val, arr, color in rows:
        c.create_text(rx0, yy, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(rx0 + 126, yy - 1, text=val, fill=theme.TEXT,
                      font=(_ui_font(), 9, "bold"), anchor="nw")
        _sparkline(c, rx0 + 190, yy + 4, x1 - 2, arr, color)
        yy += 34


def draw_overview(app, avail_w, h, carry, total, ball_speed, club_speed, smash,
                  launch, spin, apex, offline, descent, hang_time, club_path,
                  face_to_path, spin_axis, face_to_target=0.0, shot_name="",
                  smash_clamped=False, offset_x=0, top_bar_h=52):
    c = app.canvas
    _matte_background(app, offset_x, top_bar_h, offset_x + avail_w, h)

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

    margin = max(18, int(avail_w * .015))
    gap = max(20, int(avail_w * .012))
    x0, x1 = offset_x + margin, offset_x + avail_w - margin
    y0 = top_bar_h + 14
    usable_h = h - y0 - 16

    # Headline ribbon: neutral values, one blue accent edge, larger type.
    top_h = max(122, min(145, int(usable_h * .17)))
    c.create_rectangle(x0, y0, x1, y0 + top_h, fill=RIBBON, outline="")
    c.create_line(x0, y0 + top_h, x1, y0 + top_h, fill=SOFT_LINE)
    c.create_rectangle(x0, y0, x0 + 4, y0 + top_h, fill=BLUE, outline="")

    n = len(shots_all)
    idx = app.selected_shot_index + 1 if app.selected_shot_index is not None else n
    identity_w = max(260, min(330, (x1 - x0) * .205))
    ix = x0 + 24
    club = (app.current_shot or {}).get("club") or app.current_club
    c.create_text(ix, y0 + 22, text=f"Shot {idx}  ·  {club}", fill=BLUE_TEXT,
                  font=(_ui_font(), 9, "bold"), anchor="nw")
    c.create_text(ix, y0 + 55, text=(shot_name or "Straight"), fill=theme.TEXT,
                  font=(_ui_font(), 27, "bold"), anchor="nw")

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

    metrics = [
        ("Carry", f"{carry:.1f}", "yds"),
        ("Ball Speed", f"{ball_speed:.1f}", "mph"),
        ("Launch Angle", f"{launch:.1f}°", ""),
        ("Spin Rate", f"{spin:.0f}", "rpm"),
        ("Apex", f"{apex * 3:.0f}", "ft"),
        ("Offline", _side(offline), "yds"),
    ]
    mx0 = x0 + identity_w
    step = (x1 - mx0) / len(metrics)
    value_size = max(22, min(29, int(avail_w / 53)))
    for i, (label, value, unit) in enumerate(metrics):
        xx = mx0 + i * step + 15
        if i > 0:
            c.create_line(mx0 + i * step, y0 + 28, mx0 + i * step, y0 + top_h - 28,
                          fill=SOFT_LINE)
        c.create_text(xx, y0 + 29, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        vid = c.create_text(xx, y0 + 58, text=value, fill=theme.TEXT,
                            font=(_ui_font(), value_size), anchor="nw")
        if unit:
            bb = c.bbox(vid)
            if bb:
                c.create_text(bb[2] + 6, y0 + 75, text=unit, fill=theme.TEXT_3,
                              font=(_ui_font(), 9), anchor="nw")

    # Main: 39% result / 27% shape / 34% cause. Right column stacks cause.
    main_y0 = y0 + top_h + gap
    bottom_h = max(210, min(245, int(usable_h * .27)))
    main_y1 = h - 16 - bottom_h - gap
    main_h = max(330, main_y1 - main_y0)
    main_y1 = main_y0 + main_h

    total_w = x1 - x0
    lw = total_w * .39
    cw = total_w * .27
    dx0, dx1 = x0, x0 + lw
    sx0, sx1 = dx1 + gap, dx1 + gap + cw
    rx0, rx1 = sx1 + gap, x1

    c.create_line(dx1 + gap / 2, main_y0 + 4, dx1 + gap / 2, main_y1 - 4, fill=SOFT_LINE)
    c.create_line(sx1 + gap / 2, main_y0 + 4, sx1 + gap / 2, main_y1 - 4, fill=SOFT_LINE)

    _draw_dispersion(app, dx0, main_y0, dx1, main_y1, shots)
    _draw_shape(app, sx0, main_y0, sx1, main_y1, v, shots)

    # Strike above delivery, then ball flight, as requested.
    strike_h = main_h * .36
    delivery_h = main_h * .31
    sy1 = main_y0 + strike_h
    dy0 = sy1 + 8
    dy1 = dy0 + delivery_h
    fy0 = dy1 + 8
    c.create_line(rx0, sy1 + 2, rx1, sy1 + 2, fill=SOFT_LINE)
    c.create_line(rx0, dy1 + 2, rx1, dy1 + 2, fill=SOFT_LINE)
    _draw_strike(app, rx0, main_y0, rx1, sy1)
    _draw_delivery(app, rx0, dy0, rx1, dy1, v)
    _draw_flight(app, rx0, fy0, rx1, main_y1, v)

    # Bottom context.
    by0, by1 = main_y1 + gap, h - 16
    if by1 - by0 >= 175:
        c.create_line(x0, by0 - 7, x1, by0 - 7, fill=SOFT_LINE)
        _draw_bottom(app, x0, by0, x1, by1, shots)
