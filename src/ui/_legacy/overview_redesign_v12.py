"""Twelfth-pass Shot view: Shot Shape spacing + live strike-marker movement."""

import math

import overview_redesign_v7 as v7
import overview_redesign_v10 as v10
import overview_redesign_v11 as v11

import shanktuary_performance_studio as studio
import theme

BLUE_LINE = v7.BLUE_LINE
BLUE_TEXT = v7.BLUE_TEXT
ORANGE = v7.ORANGE
SHAPE_TEXT = v7.SHAPE_TEXT
NEUTRAL_POINT = v7.NEUTRAL_POINT
SECTION_TEXT = v7.SECTION_TEXT
SOFT_LINE = v7.SOFT_LINE
_movement = v7._movement
_side = v7._side
_ui_font = v7._ui_font
_mix = v7._mix


# ---------------------------------------------------------------------------
# Shot Shape
# ---------------------------------------------------------------------------

def _draw_shape(app, x0, y0, x1, y1, v, shots):
    """Put START/FINISH beneath the line and shorten the target guide."""
    c = app.canvas
    v7._section_title(c, x0, y0, "Shot Shape")
    start, move = _movement(v)

    direction = "Right → Left" if move < -1.5 else (
        "Left → Right" if move > 1.5 else "Minimal curve")

    shape_y = y0 + 54
    shape_id = c.create_text(x0, shape_y, text=v["shape"], fill=SHAPE_TEXT,
                             font=(_ui_font(), 18, "bold"), anchor="w")
    bb = c.bbox(shape_id)
    direction_x = (bb[2] + 12) if bb else x0 + 120
    c.create_text(direction_x, shape_y, text=f"·  {direction}", fill=ORANGE,
                  font=(_ui_font(), 13, "bold"), anchor="w")

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

    sx = px(start)
    ex = px(v["offline"])
    tx = px(0.0)

    c.create_line(ax0, ay, ax1, ay, fill=theme.GUIDE, width=1)

    # Shorter above the horizontal axis; only a small tail extends below it.
    target_col = _mix(theme.GUIDE, BLUE_TEXT, .30)
    c.create_line(tx, ay - 30, tx, ay + 18, fill=target_col,
                  width=2, dash=(5, 5))

    delta = ex - sx
    if abs(delta) > 24:
        sign = 1 if delta > 0 else -1
        line_start = sx + sign * 10
        arrow_end = ex - sign * 16
        c.create_line(line_start, ay, arrow_end, ay, fill=BLUE_LINE, width=4,
                      arrow="last", arrowshape=(13, 15, 6))
    else:
        c.create_line(sx, ay, ex, ay, fill=BLUE_LINE, width=4)

    c.create_oval(sx - 8, ay - 8, sx + 8, ay + 8,
                  fill=theme.BG, outline=BLUE_LINE, width=2)
    c.create_oval(ex - 9, ay - 9, ex + 9, ay + 9,
                  fill=NEUTRAL_POINT, outline=theme.TEXT_2, width=1)

    def clamp(val, lo, hi):
        return max(lo, min(hi, val))

    start_lx, finish_lx = sx, ex
    if abs(sx - ex) < 96:
        if sx <= ex:
            start_lx -= 42
            finish_lx += 42
        else:
            start_lx += 42
            finish_lx -= 42

    start_lx = clamp(start_lx, ax0 + 42, ax1 - 42)
    finish_lx = clamp(finish_lx, ax0 + 42, ax1 - 42)

    # The screen has room here. Keeping facts below the geometry avoids the
    # Movement hero entirely and makes the start/finish relationship obvious.
    label_y = ay + 28
    value_y = ay + 47
    c.create_text(start_lx, label_y, text="START", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(start_lx, value_y, text=f"{_side(start)} yds", fill=BLUE_TEXT,
                  font=(_ui_font(), 11, "bold"), anchor="n")
    c.create_text(finish_lx, label_y, text="FINISH", fill=theme.TEXT_3,
                  font=(_ui_font(), 9, "bold"), anchor="n")
    c.create_text(finish_lx, value_y, text=f"{_side(v['offline'])} yds",
                  fill=SECTION_TEXT, font=(_ui_font(), 11, "bold"), anchor="n")

    mix_y = y1 - 86
    c.create_line(x0, mix_y - 14, x1, mix_y - 14, fill=SOFT_LINE)
    v7._draw_shape_mix(c, x0, mix_y, x1, shots)


# ---------------------------------------------------------------------------
# Strike marker
# ---------------------------------------------------------------------------

_CLUB_LAUNCH = {
    "Driver": 11.5, "3 Wood": 13.0, "5 Wood": 14.5, "3 Hybrid": 16.0,
    "4 Iron": 16.5, "5 Iron": 17.5, "6 Iron": 19.0, "7 Iron": 21.0,
    "8 Iron": 23.5, "9 Iron": 26.5, "PW": 29.0, "GW": 32.0,
    "SW": 35.0, "LW": 38.0,
}
_CLUB_SPIN = {
    "Driver": 2700, "3 Wood": 3600, "5 Wood": 4300, "3 Hybrid": 4800,
    "4 Iron": 4800, "5 Iron": 5300, "6 Iron": 6200, "7 Iron": 7000,
    "8 Iron": 7800, "9 Iron": 8500, "PW": 9300, "GW": 10000,
    "SW": 10500, "LW": 11000,
}
_CLUB_BALL_SPEED = {
    "Driver": 160.0, "3 Wood": 150.0, "5 Wood": 140.0, "3 Hybrid": 130.0,
    "4 Iron": 125.0, "5 Iron": 120.0, "6 Iron": 115.0, "7 Iron": 105.0,
    "8 Iron": 95.0, "9 Iron": 90.0, "PW": 85.0, "GW": 80.0,
    "SW": 75.0, "LW": 70.0,
}


def _num(value, default=0.0):
    try:
        if isinstance(value, dict):
            # OGC occasionally exposes handed values as nested payloads.
            for key in ("right_handed", "left_handed", "value"):
                if key in value:
                    return float(value[key] or default)
            return default
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _impact_offsets_mm(app):
    """Compatibility seam: no ball-only strike inference, no missing-axis zero."""
    from src.analytics.strike import contact_location

    contact = contact_location(app.current_shot)
    return contact.horizontal_mm, contact.vertical_mm


def draw_overview(*args, **kwargs):
    # v10 installs its Shot Shape helper each draw; replace that helper itself.
    v10._draw_shape = _draw_shape
    # v11's Strike renderer now draws the shared contact face itself.
    return v11.draw_overview(*args, **kwargs)
