"""Twelfth-pass shell: strong section ribbons for the left navigation.

The underlying destinations, icons, sidebar, header branding, and hit targets
remain unchanged. This pass makes Session / Practice / Tools read as true
sections rather than small captions floating between nav items.
"""

import shell_redesign_v10 as v10
import shell_redesign_v11 as v11
import shell_redesign_v7 as v7
import theme


# The nav itself remains a compact 64px rail. When Recent Shots is collapsed,
# the design launcher reserves a separate gutter immediately to its right so
# the reopen affordance never floats over SESSION / Shot.
NAV_RAIL_W = 64
COLLAPSED_GUTTER_W = 28

SECTION_H = 22
SECTION_GAP_BEFORE = 30
SECTION_GAP_AFTER = 8


def _section_band(c, y, text):
    """Full-width, consistent blue ribbon for a navigation section."""
    rw = NAV_RAIL_W
    c.create_rectangle(0, y, rw, y + SECTION_H, fill=theme.ACCENT, outline="")
    c.create_text(
        rw / 2,
        y + SECTION_H / 2,
        text=text,
        fill=theme.TEXT,
        font=(theme.ui_font(), 8, "bold"),
        anchor="center",
    )
    return y + SECTION_H


def _nav_item(app, y, mode_id, display, icon_kind=None):
    """Use v10's accepted item drawing while pinning it to the real 64px rail.

    During a collapsed draw the launcher temporarily widens theme.RAIL_W only
    so production lays out the WORKSPACE after the drawer gutter. That must not
    make the visible nav itself wider.
    """
    old = theme.RAIL_W
    theme.RAIL_W = NAV_RAIL_W
    try:
        return v10._nav_item(app, y, mode_id, display, icon_kind)
    finally:
        theme.RAIL_W = old


def paint_nav(app, h):
    c = app.canvas
    rw = NAV_RAIL_W
    shell_bg = v10._mix(theme.RAIL, theme.BG, .42)

    c.create_rectangle(0, 0, rw, h, fill=shell_bg, outline="")
    c.create_line(rw - 1, 0, rw - 1, h,
                  fill=v10._mix(theme.HAIRLINE, theme.BG, .46))

    app.mode_pill_rects = {}
    app.design_mode_rects = {}

    # SESSION — live-shot review views only.
    y = 62
    y = _section_band(c, y, "SESSION") + SECTION_GAP_AFTER
    for mode_id, display, icon_kind in (
        (9, "Shot", "Overview"),
        (1, "Club", None),
        (4, "Table", "Table"),
        (5, "Numbers", "Nums"),
    ):
        y = _nav_item(app, y, mode_id, display, icon_kind)

    # PRACTICE — deliberate whitespace before the next ribbon so the previous
    # section visibly ends before the next one begins.
    y += SECTION_GAP_BEFORE
    y = _section_band(c, y, "PRACTICE") + SECTION_GAP_AFTER
    y = _nav_item(app, y, 2, "Range", "Range")

    # TOOLS — analysis and setup utilities. Dispersion belongs here because it
    # is a multi-shot analysis workspace rather than a single-shot session view.
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
        # Dedicated drawer gutter: visually separate from the 64px navigation
        # rail and structurally outside every nav hitbox.
        gx1 = rw
        gx2 = rw + COLLAPSED_GUTTER_W
        c.create_rectangle(gx1, 52, gx2, h,
                           fill=v10._mix(theme.RAIL, theme.BG, .18), outline="")
        c.create_line(gx2 - 1, 52, gx2 - 1, h,
                      fill=v10._mix(theme.HAIRLINE, theme.BG, .28))

        by1, by2 = 58, 94
        bx1, bx2 = gx1 + 2, gx2 - 2
        app.sidebar_toggle_rect = (bx1, by1, bx2, by2)
        app.design_sidebar_toggle_rect = (gx1, 54, gx2, 98)
        c.create_rectangle(
            bx1, by1, bx2, by2,
            fill=v10._mix(theme.SURFACE_2, theme.ACCENT, .07),
            outline=v10._mix(theme.HAIRLINE, theme.ACCENT_LINE, .16),
        )
        v7._draw_chevron(c, (bx1 + bx2) / 2, (by1 + by2) / 2, "right")


def paint_sidebar(app, w, h):
    return v11.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    return v11.paint_top_header(app, w, h, offset_x=offset_x)
