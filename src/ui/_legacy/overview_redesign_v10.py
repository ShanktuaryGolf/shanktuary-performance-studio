"""Tenth-pass Shot view: shot-shape geometry and label polish only."""

import overview_redesign_v7 as v7
import overview_redesign_v9 as v9
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


def _draw_shape(app, x0, y0, x1, y1, v, shots):
    """Keep the accepted shape composition while making geometry literal."""
    c = app.canvas
    v7._section_title(c, x0, y0, "Shot Shape")
    start, move = _movement(v)

    direction = "Right → Left" if move < -1.5 else (
        "Left → Right" if move > 1.5 else "Minimal curve")

    # Shape and direction share the same visual centerline instead of looking
    # slightly top/bottom aligned against one another.
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

    # The stronger dotted center guide speaks for itself; no TARGET tag.
    target_col = _mix(theme.GUIDE, BLUE_TEXT, .30)
    c.create_line(tx, ay - 54, tx, ay + 55, fill=target_col,
                  width=2, dash=(5, 5))

    # Keep the arrowhead out of the finish marker so the movement direction is
    # immediately legible. The geometry can naturally run either direction.
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

    # Start / Finish labels follow the actual points. For near-overlapping
    # markers, nudge them outward while keeping both attached above the line.
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

    label_y = ay - 48
    value_y = ay - 29
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


def draw_overview(*args, **kwargs):
    # Step 3 changes Shot Shape only. Dispersion remains owned by v9.
    v7._draw_shape = _draw_shape
    return v9.draw_overview(*args, **kwargs)
