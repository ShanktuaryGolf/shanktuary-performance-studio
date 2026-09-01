"""Second-pass Overview refinements for the isolated design sandbox.

This module deliberately layers on top of overview_redesign.py so we can keep
iterating on the live between-shots experience without touching production UI.
"""

from __future__ import annotations

import math
import statistics

import overview_redesign as v1
import theme

GOOD = getattr(theme, "GOOD", "#39A879")
ORANGE = getattr(theme, "WARN", "#F47A32")
RED = getattr(theme, "DANGER", "#E34A4A")
GOLD = getattr(theme, "GOLD", "#C89A4A")
BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")

_values = v1._values
_movement = v1._movement
_side = v1._side
_shape_consistency = v1._shape_consistency


def _mix_hex(a: str, b: str, t: float) -> str:
    """Tiny local colour blender for subdued geometry on dark surfaces."""
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.HAIRLINE


MOTIF = _mix_hex(theme.SURFACE, BLUE, 0.09)
MOTIF_2 = _mix_hex(theme.SURFACE, BLUE_LINE, 0.14)


def _panel(app, x0, y0, x1, y1, title, subtitle=None):
    c = app.canvas
    c.create_rectangle(x0, y0, x1, y1, fill=theme.SURFACE,
                       outline=theme.HAIRLINE, width=1)
    # A faint top edge gives the dark cards some depth without glassmorphism.
    c.create_line(x0 + 1, y0 + 1, x1 - 1, y0 + 1, fill=MOTIF_2)
    c.create_text(x0 + 15, y0 + 14, text=title, fill=theme.TEXT,
                  font=(theme.ui_font(), 10, "bold"), anchor="nw")
    if subtitle:
        c.create_text(x0 + 15, y0 + 32, text=subtitle, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="nw")


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    _panel(app, x0, y0, x1, y1, "DISPERSION", f"{club} · carry landing pattern")

    points = [(_values(s), s) for s in shots]
    points = [(vv, ss) for vv, ss in points if vv["carry"] > 0]
    if not points:
        return

    left, right = x0 + 54, x1 - 22
    top, bottom = y0 + 58, y1 - 42
    carries = [vv["carry"] for vv, _ in points]
    offs = [vv["offline"] for vv, _ in points]
    mc, mo = statistics.mean(carries), statistics.mean(offs)
    sc = statistics.pstdev(carries) if len(carries) > 1 else 2.5
    so = statistics.pstdev(offs) if len(offs) > 1 else 2.0

    cmin = min(carries + [mc - max(5, sc * 3)])
    cmax = max(carries + [mc + max(5, sc * 3)])
    pad = max(3, (cmax - cmin) * .16)
    cmin, cmax = cmin - pad, cmax + pad
    omax = max(6, max(abs(vv) for vv in offs) * 1.35, abs(mo) + so * 3)
    pw, ph = right - left, bottom - top

    def sx(off):
        return left + (off + omax) / (2 * omax) * pw

    def sy(car):
        return bottom - (car - cmin) / max(.01, cmax - cmin) * ph

    # Background target/dispersion motif: deliberately barely visible.
    midx, midy = sx(0), sy(mc)
    for frac in (0.34, 0.67, 1.0):
        rw = pw * 0.43 * frac
        rh = ph * 0.38 * frac
        c.create_oval(midx - rw, midy - rh, midx + rw, midy + rh,
                      outline=MOTIF, width=1)

    for frac in (.25, .5, .75):
        gy = top + ph * frac
        val = cmax - (cmax - cmin) * frac
        c.create_line(left, gy, right, gy, fill=theme.HAIRLINE, dash=(2, 5))
        c.create_text(left - 9, gy, text=f"{val:.0f}", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7), anchor="e")

    tx = sx(0)
    c.create_line(tx, top, tx, bottom, fill=theme.GUIDE, dash=(4, 5))
    c.create_text(left, bottom + 13, text=f"{omax:.0f}L", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 8), anchor="n")
    c.create_text(tx, bottom + 13, text="TARGET", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 8), anchor="n")
    c.create_text(right, bottom + 13, text=f"{omax:.0f}R", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 8), anchor="n")

    # 2-sigma session pattern.
    c.create_oval(sx(mo - 2 * max(1, so)), sy(mc + 2 * max(1.5, sc)),
                  sx(mo + 2 * max(1, so)), sy(mc - 2 * max(1.5, sc)),
                  outline=BLUE_LINE, width=1, dash=(5, 5))

    for vv, shot in points:
        px, py = sx(vv["offline"]), sy(vv["carry"])
        if shot is app.current_shot:
            c.create_oval(px - 12, py - 12, px + 12, py + 12,
                          outline=BLUE_LINE, width=2)
            c.create_oval(px - 6, py - 6, px + 6, py + 6,
                          fill=BLUE, outline=theme.TEXT, width=1)
        else:
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill="#50657F", outline="")

    cv = _values(app.current_shot)
    c.create_text(x0 + 15, y1 - 15,
                  text="● CURRENT     ● SESSION     ╌ 2σ PATTERN",
                  fill=theme.TEXT_3, font=(theme.ui_font(), 7), anchor="sw")
    c.create_text(x1 - 15, y1 - 15,
                  text=f"{cv['carry']:.1f} yds  ·  {_side(cv['offline'])} yds",
                  fill=theme.TEXT_2, font=(theme.ui_font(), 8, "bold"), anchor="se")


def _landing_color(offline):
    miss = abs(offline)
    if miss <= 3.0:
        return GOOD
    if miss <= 8.0:
        return ORANGE
    return RED


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "SHOT SHAPE & MOVEMENT")
    start, move = _movement(v)
    consistency, move_std = _shape_consistency(shots, move)
    recent_n = min(15, len(shots))

    c.create_text(x0 + 16, y0 + 44, text=v["shape"], fill=theme.TEXT,
                  font=(theme.ui_font(), 20, "bold"), anchor="nw")
    direction = "RIGHT → LEFT" if move < -1.5 else (
        "LEFT → RIGHT" if move > 1.5 else "MINIMAL CURVE")
    c.create_text(x0 + 16, y0 + 76, text=direction, fill=theme.TEXT_2,
                  font=(theme.ui_font(), 8, "bold"), anchor="nw")

    # Horizontal start -> movement -> landing explanation.
    ax0, ax1 = x0 + 28, x1 - 28
    ay = y0 + min(176, (y1 - y0) * .50)
    scale = max(5.0, abs(start) * 1.35, abs(v["offline"]) * 1.35)
    mid = (ax0 + ax1) / 2
    span = (ax1 - ax0) / 2

    def px(val):
        return mid + val / scale * span

    sx, ex, tx = px(start), px(v["offline"]), px(0.0)
    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE, width=1)
    c.create_line(tx, ay - 39, tx, ay + 39, fill=theme.HAIRLINE, dash=(2, 4))
    c.create_text(tx, ay + 43, text="TARGET", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7, "bold"), anchor="n")

    # Soft target halo gives the visual a little personality without becoming
    # decorative chrome.
    c.create_oval(tx - 15, ay - 15, tx + 15, ay + 15, outline=MOTIF_2)
    c.create_oval(tx - 5, ay - 5, tx + 5, ay + 5, outline=MOTIF_2)

    # Always draw the line FROM start TO landing and put the arrow on "last".
    # v1 used arrow="first" for left-moving shots, which made the arrow point
    # back toward the start instead of showing the actual curve direction.
    c.create_line(sx, ay, ex, ay, fill=BLUE, width=4, arrow="last",
                  arrowshape=(12, 14, 6))

    c.create_oval(sx - 6, ay - 6, sx + 6, ay + 6,
                  fill=theme.SURFACE, outline=BLUE_LINE, width=2)
    land_col = _landing_color(v["offline"])
    c.create_oval(ex - 7, ay - 7, ex + 7, ay + 7,
                  fill=land_col, outline=theme.TEXT, width=1)

    c.create_text(sx, ay - 34, text="START", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7, "bold"), anchor="s")
    c.create_text(sx, ay - 20, text=f"{_side(start)} yds",
                  fill=BLUE_TEXT, font=(theme.ui_font(), 10, "bold"), anchor="s")

    # Movement label is intentionally attached to the line itself: this is the
    # new derived metric we want golfers to learn to read.
    label_x = (sx + ex) / 2
    c.create_text(label_x, ay - 12,
                  text=f"MOVED {abs(move):.1f} YDS  {'←' if move < 0 else ('→' if move > 0 else '·')}",
                  fill=BLUE_TEXT, font=(theme.ui_font(), 11, "bold"), anchor="s")

    c.create_text(ex, ay + 19, text="LANDED", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 7, "bold"), anchor="n")
    c.create_text(ex, ay + 34, text=f"{_side(v['offline'])} yds",
                  fill=land_col, font=(theme.ui_font(), 10, "bold"), anchor="n")

    # Consistency block: percentage plus the two facts that explain it.
    cy = y1 - 72
    c.create_line(x0 + 16, cy - 13, x1 - 16, cy - 13, fill=theme.HAIRLINE)
    c.create_text(x0 + 16, cy, text="SHAPE CONSISTENCY", fill=theme.TEXT_3,
                  font=(theme.ui_font(), 8, "bold"), anchor="nw")
    c.create_text(x1 - 16, cy - 5, text=f"{consistency}%", fill=theme.TEXT,
                  font=(theme.ui_font(), 17, "bold"), anchor="ne")

    bx0, bx1, by = x0 + 16, x1 - 16, cy + 27
    seg_gap = 3
    segs = 10
    seg_w = (bx1 - bx0 - seg_gap * (segs - 1)) / segs
    filled = round(consistency / 10)
    for i in range(segs):
        xx = bx0 + i * (seg_w + seg_gap)
        c.create_rectangle(xx, by, xx + seg_w, by + 7,
                           fill=BLUE if i < filled else theme.SURFACE_2, outline="")
    c.create_text(x0 + 16, y1 - 12,
                  text=f"{recent_n} {((app.current_shot or {}).get('club') or app.current_club)} shots  ·  movement σ {move_std:.1f} yds",
                  fill=theme.TEXT_3, font=(theme.ui_font(), 8), anchor="sw")


def _draw_strike(app, x0, y0, x1, y1):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "STRIKE")
    head, detail, hcol = app.summarize_strike(app.current_shot)

    if hcol == theme.WARN:
        c.create_text(x1 - 14, y0 + 15, text="ESTIMATED", fill=ORANGE,
                      font=(theme.ui_font(), 7, "bold"), anchor="ne")

    # Put the clubface on the left and the answer on the right. The original
    # vertical stack made the graphic feel ornamental instead of explanatory.
    face_cx = x0 + (x1 - x0) * .35
    app._draw_overview_face(face_cx, y0 + (y1 - y0) * .61,
                            max(76, min(116, (y1 - y0) * .58)))

    text_x = x0 + (x1 - x0) * .68
    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else theme.TEXT
    c.create_text(text_x, y0 + 48, text=head, fill=col,
                  font=(theme.ui_font(), 14, "bold"), anchor="nw")
    c.create_text(text_x, y0 + 72, text=detail, fill=theme.TEXT_3,
                  font=(theme.ui_font(), 8), anchor="nw")


def _draw_flight(app, x0, y0, x1, y1, v):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "BALL FLIGHT")
    rows = [("Launch", f"{v['launch']:.1f}°"), ("Apex", f"{v['apex'] * 3:.0f} ft"),
            ("Descent", f"{v['descent']:.1f}°"), ("Hang", f"{v['hang']:.1f} s")]
    yy = y0 + 43
    for label, val in rows:
        c.create_text(x0 + 14, yy, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="nw")
        c.create_text(x0 + 86, yy, text=val, fill=theme.TEXT,
                      font=(theme.ui_font(), 9, "bold"), anchor="nw")
        yy += 20

    gx0, gx1 = x0 + max(128, (x1 - x0) * .47), x1 - 13
    gy0, gy1 = y0 + 43, y1 - 20
    pts = []
    for i in range(31):
        t = i / 30
        pts.extend([gx0 + t * (gx1 - gx0),
                    gy1 - 4 * t * (1 - t) * (gy1 - gy0) * .83])
    c.create_line(pts, fill=BLUE_LINE, width=2, smooth=True)
    c.create_line(gx0, gy1, gx1, gy1, fill=theme.GUIDE, dash=(3, 4))
    # Tiny apex point makes the flight visual read as data, not decoration.
    apex_x = (gx0 + gx1) / 2
    apex_y = gy1 - (gy1 - gy0) * .83
    c.create_oval(apex_x - 3, apex_y - 3, apex_x + 3, apex_y + 3,
                  fill=BLUE, outline=theme.TEXT)


def _draw_delivery(app, x0, y0, x1, y1, v):
    c = app.canvas
    _panel(app, x0, y0, x1, y1, "CLUB DELIVERY")
    rows = [
        ("Club path", f"{abs(v['path']):.1f}° {'in-to-out' if v['path'] >= 0 else 'out-to-in'}"),
        ("Face to path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"),
        ("Face to target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"),
        ("Spin axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]
    yy = y0 + 42
    for label, val in rows:
        c.create_text(x0 + 14, yy, text=label, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="nw")
        c.create_text(x0 + 102, yy, text=val, fill=theme.TEXT,
                      font=(theme.ui_font(), 9), anchor="nw")
        yy += 19

    cx, cy = x1 - max(48, (x1 - x0) * .15), (y0 + y1) / 2 + 7
    span = min(52, (y1 - y0) * .29)
    c.create_line(cx - span, cy, cx + span, cy, fill=theme.GUIDE, dash=(3, 4))
    pdy = -math.tan(math.radians(max(-12, min(12, v['path'])))) * span
    c.create_line(cx - span, cy + pdy, cx + span, cy - pdy,
                  fill=BLUE_LINE, width=2, arrow="last")
    ang = math.radians(max(-16, min(16, v['face_target'])))
    dx, dy = math.sin(ang) * 28, math.cos(ang) * 28
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
    sw, rw = w * .22, w * .50
    sx0, sx1 = x0, x0 + sw
    rx0, rx1 = sx1 + gap, sx1 + gap + rw
    tx0, tx1 = rx1 + gap, x1

    _panel(app, sx0, y0, sx1, y1, "SESSION SUMMARY")
    vals = [_values(s) for s in shots]
    vals = [vv for vv in vals if vv["carry"] > 0]
    if vals:
        def avg(key):
            return statistics.mean(vv[key] for vv in vals)

        stats = [("SHOTS", str(len(vals))), ("AVG CARRY", f"{avg('carry'):.1f} yds"),
                 ("AVG BALL", f"{avg('ball'):.1f} mph"), ("AVG LAUNCH", f"{avg('launch'):.1f}°"),
                 ("AVG SPIN", f"{avg('spin'):.0f} rpm"), ("AVG SMASH", f"{avg('smash'):.2f}")]
        mid = (sx0 + sx1) / 2
        available = max(110, y1 - y0 - 58)
        row_step = min(50, available / 3)
        for i, (lb, val) in enumerate(stats):
            col, row = i % 2, i // 2
            xx = sx0 + 14 if col == 0 else mid + 4
            yy = y0 + 47 + row * row_step
            c.create_text(xx, yy, text=lb, fill=theme.TEXT_3,
                          font=(theme.ui_font(), 7), anchor="nw")
            c.create_text(xx, yy + 18, text=val, fill=theme.TEXT,
                          font=(theme.ui_font(), 9, "bold"), anchor="nw")

    _panel(app, rx0, y0, rx1, y1, "RECENT SHOTS")
    recent = shots[-5:][::-1]
    headers = ["#", "CARRY", "TOTAL", "BALL", "LAUNCH", "SPIN", "OFF", "SHAPE"]
    widths = [.06, .12, .12, .12, .12, .13, .13, .20]
    tx = rx0 + 12
    tw = rx1 - rx0 - 24
    xx = tx
    for head, frac in zip(headers, widths):
        c.create_text(xx, y0 + 41, text=head, fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7, "bold"), anchor="nw")
        xx += tw * frac

    row_y = y0 + 66
    row_step = min(29, max(24, (y1 - y0 - 100) / max(1, len(recent))))
    for shot in recent:
        vv = _values(shot)
        selected = shot is app.current_shot
        try:
            idx = app.session_shots.index(shot)
        except ValueError:
            idx = 0
        if selected:
            c.create_rectangle(tx - 5, row_y - 5, rx1 - 9, row_y + 18,
                               fill=theme.ACCENT_DEEP, outline="")
            c.create_rectangle(tx - 5, row_y - 5, tx - 2, row_y + 18,
                               fill=BLUE, outline="")
        app.overview_bar_rects.append((tx - 5, row_y - 5, rx1 - 9, row_y + 20, idx))
        row = [str(idx + 1), f"{vv['carry']:.1f}", f"{vv['total']:.1f}", f"{vv['ball']:.1f}",
               f"{vv['launch']:.1f}°", f"{vv['spin']:.0f}", _side(vv['offline']), vv['shape']]
        xx = tx
        for text, frac in zip(row, widths):
            c.create_text(xx, row_y, text=text,
                          fill=theme.TEXT if selected else theme.TEXT_2,
                          font=(theme.ui_font(), 8, "bold" if selected else "normal"), anchor="nw")
            xx += tw * frac
        row_y += row_step

    link = c.create_text((rx0 + rx1) / 2, y1 - 14, text="View all shots in Table  ›",
                         fill=BLUE_TEXT, font=(theme.ui_font(), 8, "bold"), anchor="s")
    bb = c.bbox(link)
    if bb:
        app.overview_viewall_rect = (bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6)

    _panel(app, tx0, y0, tx1, y1, "TENDENCIES", f"Last {min(15, len(shots))} shots")
    series = [_values(s) for s in shots[-15:]]
    starts = [_movement(vv)[0] for vv in series]
    moves = [_movement(vv)[1] for vv in series]
    offs = [vv["offline"] for vv in series]
    carries = [vv["carry"] for vv in series]
    cons = []
    for i, mv in enumerate(moves):
        cons.append(_shape_consistency(shots[:max(1, len(shots) - len(series) + i + 1)], mv)[0])

    rows = [("Start direction", starts, BLUE_LINE),
            ("Curve movement", moves, GOOD),
            ("Offline", offs, ORANGE),
            ("Carry", carries, BLUE_TEXT),
            ("Shape consistency", cons, GOLD)]
    yy = y0 + 53
    row_step = min(31, max(26, (y1 - y0 - 74) / len(rows)))
    for label, vals_, col in rows:
        c.create_text(tx0 + 14, yy, text=label, fill=theme.TEXT_2,
                      font=(theme.ui_font(), 8), anchor="nw")
        if vals_:
            val = f"{vals_[-1]:.0f}%" if label == "Shape consistency" else (
                f"{vals_[-1]:.1f}" if label == "Carry" else _side(vals_[-1], .2))
            c.create_text(tx0 + (tx1 - tx0) * .52, yy, text=val, fill=theme.TEXT,
                          font=(theme.ui_font(), 8, "bold"), anchor="nw")
            _spark(c, tx0 + (tx1 - tx0) * .67, yy - 1, tx1 - 12, yy + 13, vals_, col)
        yy += row_step


def draw_overview(app, *args, **kwargs):
    """Run the v1 layout using refined v2 component renderers.

    Keeping layout and component iteration separate makes it easy to decide
    later whether the next pass needs geometry changes or just visual polish.
    """
    v1._panel = _panel
    v1._draw_dispersion = _draw_dispersion
    v1._draw_shape = _draw_shape
    v1._draw_strike = _draw_strike
    v1._draw_flight = _draw_flight
    v1._draw_delivery = _draw_delivery
    v1._draw_bottom = _draw_bottom
    return v1.draw_overview(app, *args, **kwargs)
