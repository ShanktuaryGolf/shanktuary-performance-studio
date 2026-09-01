"""Fourteenth-pass Shot view: richer navy/teal material + cleaner color roles.

This stays page-local. It keeps the accepted gold/teal Shot palette from v13,
but lightens the underlying navy, introduces a subtle teal undertone, increases
teal contrast, and removes gold/green from non-emphasis trend/category colors.
"""

import overview_redesign_v4 as v4
import overview_redesign_v5 as v5
import overview_redesign_v7 as v7
import overview_redesign_v8 as v8
import overview_redesign_v9 as v9
import overview_redesign_v10 as v10
import overview_redesign_v11 as v11
import overview_redesign_v12 as v12
import overview_redesign_v13 as v13
import theme

# Richer antique gold, and a slightly more present teal than v13.
GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
BRONZE = "#A7793A"
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_MID = "#4FA3A3"
TEAL_SOFT = "#698E96"
TEAL_ALT = "#5D9E9F"


def _shot_background(app, x0, y0, x1, y1):
    """Lighter deep navy with a restrained teal undertone."""
    img = v8._material_image(
        app, "overview_v14_bg", x1 - x0, y1 - y0,
        top="#0E2733", bottom="#07151E",
        left="#0A2933", right="#091923",
        mottle=.070, fibers=.030, grain=.018, seed=141,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _shot_ribbon(app, x0, y0, x1, y1):
    """Slightly raised navy/teal ribbon; gold remains the only hero accent."""
    img = v8._material_image(
        app, "overview_v14_ribbon", x1 - x0, y1 - y0,
        top="#132E3C", bottom="#0A1A24",
        left="#102D39", right="#0A1821",
        mottle=.042, fibers=.018, grain=.011, seed=147,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")


def _shot_session(app, x0, y0, x1, y1):
    """Session zone stays anchored, but no longer collapses into near-black."""
    img = v8._material_image(
        app, "overview_v14_session", x1 - x0, y1 - y0,
        top="#0C222D", bottom="#07151D",
        left="#09242D", right="#091821",
        mottle=.052, fibers=.021, grain=.016, seed=153,
    )
    app.canvas.create_image(x0, y0, image=img, anchor="nw")
    app.canvas.create_line(
        x0, y0, x1, y0,
        fill=v7._mix(theme.HAIRLINE, TEAL_SOFT, .14),
    )


def _draw_shape_mix(c, x0, y0, x1, shots):
    """Direction categories stay analytical; gold is reserved for emphasis."""
    counts, total = v7._shape_mix(shots)
    if not total:
        return

    colors = {
        "Draw": TEAL_LINE,
        "Straight": v7.STRAIGHT,
        "Fade": TEAL_SOFT,
    }
    c.create_text(x0, y0, text="Session Shape Mix",
                  fill=theme.TEXT_2,
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


def _apply_palette():
    # Start from v13 so every copied import-time constant is already covered.
    v13._apply_palette()

    # Stronger Shot-local accent colors.
    v4.BLUE = GOLD
    v4.BLUE_LINE = TEAL_LINE
    v4.BLUE_TEXT = TEAL_TEXT
    v4.ORANGE = GOLD
    v4.SESSION_DOT = v4._mix(theme.TEXT_3, TEAL, .18)

    v5.BLUE = GOLD
    v5.BLUE_LINE = TEAL_LINE
    v5.BLUE_TEXT = TEAL_TEXT
    v5.ORANGE = GOLD
    v5.GOLD = TEAL_MID

    v7.BLUE = GOLD
    v7.BLUE_LINE = TEAL_LINE
    v7.BLUE_TEXT = TEAL_TEXT
    v7.ORANGE = GOLD
    v7.GOLD = TEAL_MID
    v7.SESSION_DOT = v7._mix(theme.TEXT_3, TEAL, .20)
    v7.ELLIPSE = v7._mix(TEAL_LINE, "#102C35", .20)
    v7.NEUTRAL_POINT = v7._mix(theme.TEXT_2, TEAL, .10)
    v7._draw_shape_mix = _draw_shape_mix

    # v8 owns the accepted material and session-trend helpers.
    v8.BLUE = GOLD
    v8.BLUE_LINE = TEAL_LINE
    v8.BLUE_TEXT = TEAL_TEXT
    # Session trends should not use gold for generic metrics.
    v8.ORANGE = TEAL_ALT
    v8.GOLD = TEAL_MID
    v8.GOOD = "#4DA69B"
    v8.SESSION_DOT = v7.SESSION_DOT
    v8._depth_background = _shot_background
    v8._ribbon_surface = _shot_ribbon
    v8._session_surface = _shot_session

    # Current shot / movement / strike remain gold. Analytical geometry is teal.
    v9.BLUE_LINE = TEAL_LINE
    v9.BLUE_TEXT = TEAL_TEXT
    v9.ORANGE = GOLD
    v9.SESSION_DOT = v7.SESSION_DOT

    v10.BLUE_LINE = TEAL_LINE
    v10.BLUE_TEXT = TEAL_TEXT
    v10.ORANGE = GOLD
    v10.NEUTRAL_POINT = v7.NEUTRAL_POINT

    v11.BLUE_LINE = TEAL_LINE
    v11.BLUE_TEXT = TEAL_TEXT
    v11.ORANGE = GOLD

    v12.BLUE_LINE = TEAL_LINE
    v12.BLUE_TEXT = TEAL_TEXT
    v12.ORANGE = GOLD
    v12.NEUTRAL_POINT = v7.NEUTRAL_POINT


def draw_overview(*args, **kwargs):
    _apply_palette()
    return v12.draw_overview(*args, **kwargs)
