"""Eighth-pass Shot view: material depth, confidence ellipse, split session band."""

from __future__ import annotations

import math
import random
import statistics

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk

import overview_redesign_v7 as v7
import theme

BLUE = v7.BLUE
BLUE_LINE = v7.BLUE_LINE
BLUE_TEXT = v7.BLUE_TEXT
ORANGE = v7.ORANGE
GOLD = v7.GOLD
GOOD = v7.GOOD
_values = v7._values
_movement = v7._movement
_side = v7._side
_ui_font = v7._ui_font
_mix = v7._mix
_club_speed = v7._club_speed
_sparkline = v7._sparkline

SOFT_LINE = v7.SOFT_LINE
GRID_LINE = v7.GRID_LINE
SESSION_DOT = v7.SESSION_DOT
SECTION_TEXT = v7.SECTION_TEXT

CONFIDENCE = 0.90
# For a 2-D normal distribution P(R<=r)=1-exp(-r^2/2).  This makes the
# percentage on the screen mathematically match the ellipse rather than
# relabelling a 2-sigma box as "95%".
CONF_RADIUS = math.sqrt(-2.0 * math.log(1.0 - CONFIDENCE))


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _material_image(app, cache_name, w, h, *, top, bottom, left, right,
                    mottle=.065, fibers=.032, grain=.020, seed=81):
    """Layer several nearly invisible material scales instead of one glow."""
    iw, ih = max(1, int(w)), max(1, int(h))
    key_name = f"_{cache_name}_key"
    img_name = f"_{cache_name}_img"
    key = (iw, ih, top, bottom, left, right, mottle, fibers, grain)
    if getattr(app, key_name, None) == key:
        return getattr(app, img_name)

    # Base: restrained vertical + horizontal colour movement.
    base = Image.new("RGB", (iw, ih), _rgb(top))
    bd = ImageDraw.Draw(base)
    ta, tb = _rgb(top), _rgb(bottom)
    for yy in range(0, ih, 4):
        t = yy / max(1, ih - 1)
        t = t * t * (3 - 2 * t)
        col = tuple(round(a + (b - a) * t) for a, b in zip(ta, tb))
        bd.rectangle((0, yy, iw, min(ih, yy + 4)), fill=col)

    horiz = Image.new("RGB", (iw, ih), _rgb(left))
    hd = ImageDraw.Draw(horiz)
    la, lb = _rgb(left), _rgb(right)
    for xx in range(0, iw, 4):
        t = xx / max(1, iw - 1)
        col = tuple(round(a + (b - a) * t) for a, b in zip(la, lb))
        hd.rectangle((xx, 0, min(iw, xx + 4), ih), fill=col)
    base = Image.blend(base, horiz, .28)

    # Low-frequency cloudy/mottled material. It should be perceived, not seen.
    try:
        sw, sh = max(12, iw // 42), max(10, ih // 42)
        low = Image.effect_noise((sw, sh), 58).convert("L")
        low = low.resize((iw, ih), resample=Image.Resampling.BICUBIC)
        low = low.filter(ImageFilter.GaussianBlur(radius=max(3, min(iw, ih) / 170)))
        low_col = ImageOps.colorize(low, black="#03070C", white="#17304A")
        base = Image.blend(base, low_col, mottle)
    except Exception:
        pass

    # Sparse dyed-fabric / brushed fibres at extremely low alpha.  There is a
    # lot of structure underneath, but almost none of any single line survives.
    rng = random.Random(seed + iw * 17 + ih * 31)
    overlay = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    count = max(90, int((iw + ih) / 9))
    for _ in range(count):
        yy = rng.randrange(0, ih)
        x0 = rng.randrange(-iw // 5, iw)
        length = rng.randrange(max(24, iw // 15), max(30, iw // 3))
        rise = rng.choice((-2, -1, 0, 0, 0, 1, 2))
        if rng.random() < .54:
            col = (43, 67, 89, rng.randrange(3, 8))
        else:
            col = (0, 3, 7, rng.randrange(4, 10))
        od.line((x0, yy, x0 + length, yy + rise), fill=col, width=1)
    for _ in range(max(20, count // 5)):
        xx = rng.randrange(0, iw)
        y0 = rng.randrange(0, ih)
        length = rng.randrange(15, max(18, ih // 4))
        col = (29, 48, 67, rng.randrange(2, 6))
        od.line((xx, y0, xx + rng.choice((-1, 0, 1)), y0 + length), fill=col, width=1)
    textured = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    base = Image.blend(base, textured, min(1.0, fibers / .032)) if fibers < .032 else textured

    # Micro-grain breaks up the remaining computer-flat surface.
    if grain:
        try:
            micro = Image.effect_noise((iw, ih), 18).convert("L")
            micro_col = ImageOps.colorize(micro, black="#05080D", white="#1C2A39")
            base = Image.blend(base, micro_col, grain)
        except Exception:
            pass

    photo = ImageTk.PhotoImage(base)
    setattr(app, img_name, photo)
    setattr(app, key_name, key)
    return photo


def _depth_background(app, x0, y0, x1, y1):
    img = _material_image(
        app, "overview_v8_bg", x1 - x0, y1 - y0,
        top="#0C151F", bottom="#05080D",
        left="#07101A", right="#0B1622",
        mottle=.078, fibers=.032, grain=.020, seed=91,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _ribbon_surface(app, x0, y0, x1, y1):
    img = _material_image(
        app, "overview_v8_ribbon", x1 - x0, y1 - y0,
        top="#142237", bottom="#09101A",
        left="#11263D", right="#0A111B",
        mottle=.045, fibers=.020, grain=.012, seed=97,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _session_surface(app, x0, y0, x1, y1):
    img = _material_image(
        app, "overview_v8_session", x1 - x0, y1 - y0,
        top="#0A141F", bottom="#05080D",
        left="#08111B", right="#0A1018",
        mottle=.060, fibers=.025, grain=.018, seed=103,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")
    # Deliberately no blue-to-orange rule. A neutral hairline marks the mode
    # change without visually echoing the shot-movement graphic.
    app.canvas.create_line(x0, y0, x1, y0, fill=_mix(theme.HAIRLINE, theme.TEXT_3, .12))


def _draw_dispersion(app, x0, y0, x1, y1, shots):
    c = app.canvas
    club = (app.current_shot or {}).get("club") or app.current_club
    v7._section_title(c, x0, y0, "Dispersion", f"{club} · carry landing pattern")

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

    carry_half = CONF_RADIUS * max(1.5, sc)
    raw_min = min(min(carries), mc - carry_half)
    raw_max = max(max(carries), mc + carry_half)
    raw_span = max(8.0, raw_max - raw_min)
    pad = raw_span * .08
    cmin, cmax = raw_min - pad, raw_max + pad

    lateral_extent = max(
        5.0,
        max(abs(v) for v in offs),
        abs(mo) + CONF_RADIUS * max(1.0, so),
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
    c.create_oval(x0 + 120, y1 - 18, x0 + 126, y1 - 12,
                  fill=SESSION_DOT, outline="")
    c.create_text(x0 + 132, y1 - 15, text=f"Session ({len(points)})",
                  fill=theme.TEXT_2, font=(_ui_font(), 10), anchor="w")


def _draw_session_bottom(app, x0, y0, x1, y1, shots):
    """Bring back overall session data, beside a deliberately narrower trends panel."""
    c = app.canvas
    vals = [_values(s) for s in shots]
    if not vals:
        return

    club = (app.current_shot or {}).get("club") or app.current_club
    speeds = [_club_speed(s) for s in shots]
    avg = lambda key: statistics.mean(v[key] for v in vals)
    avg_club = statistics.mean(speeds) if speeds else 0.0

    total_w = x1 - x0
    summary_w = total_w * .32
    divider = x0 + summary_w

    # Summary header: count belongs on the same line, not on a second row.
    c.create_text(x0, y0 + 15, text=f"Session · {club}", fill=SECTION_TEXT,
                  font=(_ui_font(), 14, "bold"), anchor="nw")
    c.create_text(divider - 18, y0 + 18, text=f"{len(vals)} shots",
                  fill=theme.TEXT_2, font=(_ui_font(), 10, "bold"), anchor="ne")

    summary = [
        ("Avg Carry", f"{avg('carry'):.1f} yds"),
        ("Avg Total", f"{avg('total'):.1f} yds"),
        ("Avg Ball Speed", f"{avg('ball'):.1f} mph"),
        ("Avg Club Speed", f"{avg_club:.1f} mph"),
        ("Avg VLA", f"{avg('launch'):.1f}°"),
        ("Avg Spin", f"{avg('spin'):.0f} rpm"),
        ("Avg Offline", f"{_side(avg('offline'))} yds"),
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
                      font=(_ui_font(), 9, "bold"), anchor="nw")
        c.create_text(xx, yy + 18, text=value, fill=SECTION_TEXT,
                      font=(_ui_font(), 11, "bold"), anchor="nw")

    c.create_line(divider + 2, y0 + 12, divider + 2, y1 - 8, fill=SOFT_LINE)

    trend_x0 = divider + 30
    c.create_text(trend_x0, y0 + 15, text="Session Trends", fill=SECTION_TEXT,
                  font=(_ui_font(), 14, "bold"), anchor="nw")
    c.create_text(x1, y0 + 18, text=f"Last {min(16, len(vals))} shots",
                  fill=theme.TEXT_2, font=(_ui_font(), 10, "bold"), anchor="ne")

    recent = vals[-min(16, len(vals)):]
    carries = [v["carry"] for v in recent]
    balls = [v["ball"] for v in recent]
    spins = [v["spin"] for v in recent]
    offlines = [v["offline"] for v in recent]
    starts = [_movement(v)[0] for v in recent]
    moves = [_movement(v)[1] for v in recent]

    def sd(arr, unit=""):
        if len(arr) <= 1:
            return "SD —"
        s = statistics.pstdev(arr)
        if unit == "rpm":
            return f"SD {s:.0f} rpm"
        return f"SD {s:.1f}{(' ' + unit) if unit else ''}"

    rows_left = [
        ("Carry", f"Avg {statistics.mean(carries):.1f} yds", sd(carries, "yds"), carries, BLUE_LINE),
        ("Spin", f"Avg {statistics.mean(spins):.0f} rpm", sd(spins, "rpm"), spins, GOLD),
        ("Offline", f"Avg {_side(statistics.mean(offlines))} yds", sd(offlines, "yds"), offlines, ORANGE),
    ]
    rows_right = [
        ("Start Line", f"Avg {_side(statistics.mean(starts))} yds", sd(starts, "yds"), starts, BLUE_TEXT),
        ("Curve Movement",
         f"Avg {abs(statistics.mean(moves)):.1f}{'L' if statistics.mean(moves) < 0 else 'R'} yds",
         sd(moves, "yds"), moves, ORANGE),
        ("Ball Speed", f"Avg {statistics.mean(balls):.1f} mph", sd(balls, "mph"), balls, GOOD),
    ]

    trend_w = x1 - trend_x0
    gap = 28
    tw = (trend_w - gap) / 2
    row_step_t = min(56, max(47, (y1 - y0 - 57) / 3))

    def draw_rows(rows, bx0, bx1):
        yy = y0 + 54
        for label, avg_text, detail, arr, color in rows:
            c.create_text(bx0, yy, text=label, fill=theme.TEXT_2,
                          font=(_ui_font(), 10, "bold"), anchor="nw")
            c.create_text(bx0, yy + 21, text=avg_text, fill=SECTION_TEXT,
                          font=(_ui_font(), 12, "bold"), anchor="nw")
            c.create_text(bx0 + 128, yy + 24, text=detail, fill=theme.TEXT_3,
                          font=(_ui_font(), 9), anchor="nw")
            _sparkline(c, bx0 + tw * .63, yy + 23, bx1 - 4, arr, color)
            yy += row_step_t

    draw_rows(rows_left, trend_x0, trend_x0 + tw)
    draw_rows(rows_right, trend_x0 + tw + gap, x1)


def draw_overview(*args, **kwargs):
    # v7.draw_overview resolves these helpers from its module globals at call
    # time, so the v8 pass can stay narrow and leave the already-approved
    # Shape / Strike / Delivery composition alone.
    v7._depth_background = _depth_background
    v7._ribbon_surface = _ribbon_surface
    v7._session_surface = _session_surface
    v7._draw_dispersion = _draw_dispersion
    v7._draw_session_bottom = _draw_session_bottom
    return v7.draw_overview(*args, **kwargs)
