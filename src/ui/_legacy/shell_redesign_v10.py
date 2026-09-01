"""Tenth-pass shell: grouped navigation hierarchy only.

This pass deliberately leaves the header branding and Recent Shots sidebar
unchanged. It only clarifies the persistent left rail into Session, Practice,
and Tools groups while preserving design-owned click targets.
"""

import math

import shell_redesign as icons
import shell_redesign_v7 as v7
import shell_redesign_v9 as v9
import theme

BLUE = v9.BLUE
BLUE_LINE = v9.BLUE_LINE
BLUE_TEXT = v9.BLUE_TEXT
ORANGE = v9.ORANGE


def _mix(a, b, t):
    return v9._mix(a, b, t)


def _club_face_icon(c, cx, cy, col):
    """Front-on iron face: compact enough to read at rail size."""
    # slightly trapezoidal face
    pts = (
        cx - 10, cy - 8,
        cx + 8, cy - 7,
        cx + 10, cy + 8,
        cx - 8, cy + 8,
        cx - 10, cy - 8,
    )
    c.create_line(*pts, fill=col, width=1)
    # grooves
    for dy in (-4, 0, 4):
        c.create_line(cx - 7, cy + dy, cx + 7, cy + dy, fill=col, width=1)
    # tiny hosel cue so this reads as a club, not a generic grid
    c.create_line(cx + 8, cy - 6, cx + 12, cy - 10, fill=col, width=1)


def _gear(c, cx, cy, r, col):
    """Simple readable gear glyph drawn with line primitives."""
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=1)
    c.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, outline=col, width=1)
    for i in range(8):
        a = math.radians(i * 45)
        x1 = cx + math.cos(a) * (r + 1)
        y1 = cy + math.sin(a) * (r + 1)
        x2 = cx + math.cos(a) * (r + 4)
        y2 = cy + math.sin(a) * (r + 4)
        c.create_line(x1, y1, x2, y2, fill=col, width=1)


def _setup_gears(c, cx, cy, col):
    _gear(c, cx - 4, cy - 2, 6, col)
    _gear(c, cx + 6, cy + 5, 4, col)


def _group_label(c, y, text, col):
    c.create_text(
        theme.RAIL_W / 2,
        y,
        text=text,
        fill=col,
        font=(theme.ui_font(), 7, "bold"),
        anchor="n",
    )


def _nav_item(app, y, mode_id, display, icon_kind=None, h=44):
    c = app.canvas
    rw = theme.RAIL_W
    active = app.view_mode == mode_id

    # Full visual row is the click target, with small safe padding that never
    # overlaps the next row.
    rect = (0, y - 2, rw, y + h + 2)
    app.mode_pill_rects[mode_id] = rect
    app.design_mode_rects[mode_id] = rect

    if active:
        c.create_rectangle(5, y, rw - 5, y + h, fill=_mix(theme.SURFACE_2, BLUE, .11), outline="")
        c.create_rectangle(5, y, 8, y + h, fill=BLUE, outline="")

    txt_col = theme.TEXT if active else theme.TEXT_3
    icon_col = BLUE_LINE if active else _mix(theme.TEXT_3, theme.TEXT_2, .32)
    cy = y + 14

    if display == "Club":
        _club_face_icon(c, 32, cy, icon_col)
    elif display == "Setup":
        _setup_gears(c, 32, cy, icon_col)
    else:
        icons._draw_nav_icon(c, icon_kind or display, 32, cy, icon_col)

    c.create_text(
        32,
        y + 35,
        text=display,
        fill=txt_col,
        font=(theme.ui_font(), 7, "bold" if active else "normal"),
        anchor="center",
    )
    return y + h + 3


def paint_nav(app, h):
    """Clear hierarchy: Session views, Practice mode, then Tools."""
    c = app.canvas
    rw = theme.RAIL_W
    shell_bg = _mix(theme.RAIL, theme.BG, .42)

    c.create_rectangle(0, 0, rw, h, fill=shell_bg, outline="")
    c.create_line(rw - 1, 0, rw - 1, h, fill=_mix(theme.HAIRLINE, theme.BG, .46))

    app.mode_pill_rects = {}
    app.design_mode_rects = {}

    # More breathing room between group headings and between sections. The
    # labels also intentionally use different tones so the hierarchy is visible
    # even in peripheral vision.
    y = 62
    _group_label(c, y, "SESSION", BLUE_TEXT)
    y += 18
    for mode_id, display, icon_kind in (
        (9, "Shot", "Overview"),
        (1, "Club", None),
        (3, "Dispersion", "Disp"),
        (4, "Table", "Table"),
        (5, "Numbers", "Nums"),
    ):
        y = _nav_item(app, y, mode_id, display, icon_kind)

    y += 24
    _group_label(c, y, "PRACTICE", _mix(ORANGE, theme.TEXT_2, .22))
    y += 18
    y = _nav_item(app, y, 2, "Range", "Range")

    y += 26
    _group_label(c, y, "TOOLS", _mix(theme.TEXT_2, theme.TEXT, .08))
    y += 18
    for mode_id, display, icon_kind in (
        (6, "Bag", "Bag"),
        (7, "Fit", "Fit"),
        (8, "Lab", "Lab"),
        (10, "Setup", None),
    ):
        y = _nav_item(app, y, mode_id, display, icon_kind)

    # Keep the existing reliable reopen affordance when Recent Shots is closed.
    if getattr(app, "sidebar_collapsed", False):
        app.sidebar_toggle_rect = (rw - 24, 57, rw - 3, 84)
        app.design_sidebar_toggle_rect = (rw - 31, 53, rw, 90)
        c.create_rectangle(
            rw - 30, 55, rw - 2, 89,
            fill=_mix(theme.SURFACE_2, BLUE, .07), outline=""
        )
        v7._draw_chevron(c, rw - 15, 72, "right")


def paint_sidebar(app, w, h):
    return v9.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    return v9.paint_top_header(app, w, h, offset_x=offset_x)
