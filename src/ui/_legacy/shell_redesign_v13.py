"""Thirteenth-pass shell: gold/teal navigation + Recent Shots drawer.

This pass intentionally leaves the approved PNG header branding alone. It
updates only the persistent left rail and Recent Shots drawer so the shell
matches the accepted Shot/Club palette:

- deep teal/navy = navigation structure
- antique gold = active/current emphasis
- cool slate = inactive/secondary
"""

import shell_redesign_v4 as v4
import shell_redesign_v7 as v7
import shell_redesign_v8 as v8
import shell_redesign_v10 as v10
import shell_redesign_v11 as v11
import theme

NAV_RAIL_W = 64
COLLAPSED_GUTTER_W = 28
SECTION_H = 22
SECTION_GAP_BEFORE = 30
SECTION_GAP_AFTER = 8

GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"

RAIL_BG = "#081923"
RAIL_EDGE = "#21414A"
SECTION_BG = "#173B42"
SECTION_TEXT = "#E4EAEB"
ACTIVE_BG = "#18313A"
INACTIVE_ICON = "#6F8990"
INACTIVE_TEXT = "#87979D"
GUTTER_BG = "#0B1D27"
GUTTER_EDGE = "#29464F"
SIDEBAR_BG = "#091B24"
SIDEBAR_SELECTED = "#18313A"
SIDEBAR_ROW = "#0D1F29"
SIDEBAR_LINE = "#24434C"


def _section_band(c, y, text):
    c.create_rectangle(0, y, NAV_RAIL_W, y + SECTION_H,
                       fill=SECTION_BG, outline="")
    c.create_text(
        NAV_RAIL_W / 2,
        y + SECTION_H / 2,
        text=text,
        fill=SECTION_TEXT,
        font=(theme.ui_font(), 8, "bold"),
        anchor="center",
    )
    return y + SECTION_H


def _nav_item(app, y, mode_id, display, icon_kind=None, h=44):
    c = app.canvas
    active = app.view_mode == mode_id
    rect = (0, y - 2, NAV_RAIL_W, y + h + 2)
    app.mode_pill_rects[mode_id] = rect
    app.design_mode_rects[mode_id] = rect

    if active:
        c.create_rectangle(5, y, NAV_RAIL_W - 5, y + h,
                           fill=ACTIVE_BG, outline="")
        c.create_rectangle(5, y, 9, y + h, fill=GOLD, outline="")

    txt_col = theme.TEXT if active else INACTIVE_TEXT
    icon_col = GOLD_LIGHT if active else INACTIVE_ICON
    cy = y + 14

    if display == "Club":
        v10._club_face_icon(c, 32, cy, icon_col)
    elif display == "Setup":
        v10._setup_gears(c, 32, cy, icon_col)
    else:
        v10.icons._draw_nav_icon(c, icon_kind or display, 32, cy, icon_col)

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
    c = app.canvas
    c.create_rectangle(0, 0, NAV_RAIL_W, h, fill=RAIL_BG, outline="")
    c.create_line(NAV_RAIL_W - 1, 0, NAV_RAIL_W - 1, h,
                  fill=RAIL_EDGE)

    app.mode_pill_rects = {}
    app.design_mode_rects = {}

    y = 62
    y = _section_band(c, y, "SESSION") + SECTION_GAP_AFTER
    for mode_id, display, icon_kind in (
        (9, "Shot", "Overview"),
        (1, "Club", None),
        (4, "Table", "Table"),
        (5, "Numbers", "Nums"),
    ):
        y = _nav_item(app, y, mode_id, display, icon_kind)

    y += SECTION_GAP_BEFORE
    y = _section_band(c, y, "PRACTICE") + SECTION_GAP_AFTER
    y = _nav_item(app, y, 2, "Range", "Range")

    y += SECTION_GAP_BEFORE
    y = _section_band(c, y, "TOOLS") + SECTION_GAP_AFTER
    for mode_id, display, icon_kind in (
        (3, "Dispersion", "Disp"),
        (6, "Bag", "Bag"),
        (7, "Fit", "Fit"),
        (8, "Lab", "Lab"),
        (10, "Setup", None),
    ):
        y = _nav_item(app, y, mode_id, display, icon_kind)

    if getattr(app, "sidebar_collapsed", False):
        gx1 = NAV_RAIL_W
        gx2 = NAV_RAIL_W + COLLAPSED_GUTTER_W
        c.create_rectangle(gx1, 52, gx2, h, fill=GUTTER_BG, outline="")
        c.create_line(gx2 - 1, 52, gx2 - 1, h, fill=GUTTER_EDGE)

        by1, by2 = 58, 94
        bx1, bx2 = gx1 + 2, gx2 - 2
        app.sidebar_toggle_rect = (bx1, by1, bx2, by2)
        app.design_sidebar_toggle_rect = (gx1, 54, gx2, 98)
        c.create_rectangle(bx1, by1, bx2, by2,
                           fill="#102832", outline="#31535C")
        v7._draw_chevron(c, (bx1 + bx2) / 2, (by1 + by2) / 2, "right")


def _apply_sidebar_palette():
    """Patch the accepted drawer renderer's static color constants in place."""
    v4.BLUE = GOLD
    v4.BLUE_LINE = GOLD_LIGHT
    v4.BLUE_TEXT = TEAL_TEXT
    v4.SIDEBAR_BG = SIDEBAR_BG
    v4.SELECTED = SIDEBAR_SELECTED
    v4.ROW = SIDEBAR_ROW
    v4.SOFT_LINE = SIDEBAR_LINE

    v8.BLUE = GOLD
    v8.BLUE_LINE = GOLD_LIGHT
    v8.BLUE_TEXT = TEAL_TEXT


def paint_sidebar(app, w, h):
    _apply_sidebar_palette()
    v11.paint_sidebar(app, w, h)

    if getattr(app, "sidebar_collapsed", False):
        return

    c = app.canvas
    x1 = app.sidebar_width

    # Replace the old solid-blue New Session button with a dark equipment
    # control: gold is the action cue, not a giant filled block.
    nr = getattr(app, "sidebar_new_sess_btn_rect", None)
    if nr:
        x0, y0, x2, y2 = nr
        c.create_rectangle(x0, y0, x2, y2,
                           fill="#10252E", outline=GOLD, width=1)
        c.create_text((x0 + x2) / 2, (y0 + y2) / 2, text="+",
                      fill=GOLD_LIGHT,
                      font=(theme.ui_font(), 14, "bold"), anchor="center")

    # Make the outer drawer seam consistent with the new rail instead of the
    # older blue-gray shell line.
    c.create_line(x1 - 1, 52, x1 - 1, h, fill=SIDEBAR_LINE)


def paint_top_header(app, w, h, offset_x=0):
    # Header branding stays exactly as approved for this pass.
    return v11.paint_top_header(app, w, h, offset_x=offset_x)
