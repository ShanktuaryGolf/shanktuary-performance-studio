"""Eighth-pass shell: final-painted geometry owns its own hit targets."""

from __future__ import annotations

import shell_redesign_v4 as v4
import shell_redesign_v7 as v7
import theme

BLUE = v7.BLUE
BLUE_LINE = v7.BLUE_LINE
BLUE_TEXT = v7.BLUE_TEXT


def _mix(a, b, t):
    return v7._mix(a, b, t)


def paint_nav(app, h):
    """Use v7 visuals, but save independent hit rectangles that later draws cannot overwrite."""
    v7.paint_nav(app, h)
    rw = theme.RAIL_W

    app.design_mode_rects = {}
    for mode_id, rect in getattr(app, "mode_pill_rects", {}).items():
        x1, y1, x2, y2 = rect
        # A little forgiveness around each visual row, without overlapping its neighbour.
        app.design_mode_rects[mode_id] = (0, y1 - 2, rw, y2 + 2)

    if getattr(app, "sidebar_collapsed", False):
        # This is intentionally separate from sidebar_toggle_rect. Production's
        # draw_top_header runs AFTER the nav and replaces sidebar_toggle_rect
        # with its hidden hamburger coordinates; that was why the visible
        # reopen chevron often did absolutely nothing in v7.
        app.design_sidebar_toggle_rect = (rw - 31, 55, rw, 91)
        c = app.canvas
        c.create_rectangle(rw - 30, 56, rw - 2, 90,
                           fill=_mix(theme.SURFACE_2, BLUE, .07), outline="")
        v7._draw_chevron(c, rw - 15, 73, "right")


def paint_sidebar(app, w, h):
    if getattr(app, "sidebar_collapsed", False):
        app.design_shot_card_rects = []
        return

    # Keep the accepted shell material, session controls and headings.
    v4.paint_sidebar(app, w, h)

    c = app.canvas
    x0 = theme.RAIL_W
    x1 = app.sidebar_width

    # The visible collapse affordance gets a generous, separate design hitbox.
    cy = 164
    app.design_sidebar_toggle_rect = (x1 - 34, cy - 20, x1, cy + 20)
    c.create_rectangle(x1 - 30, cy - 18, x1 - 3, cy + 18,
                       fill=_mix(theme.SURFACE_2, BLUE, .055), outline="")
    v7._draw_chevron(c, x1 - 16, cy, "left")

    # Repaint the shot cards over v4 so the geometry and hierarchy are exact.
    app.design_shot_card_rects = []
    app.sidebar_shot_card_rects = []
    y = 184
    bottom = h - 52
    for real_idx, shot in v4._filtered_shots(app):
        selected = real_idx == app.selected_shot_index
        rh = 120 if selected else 52
        if y + rh > bottom:
            break

        bg = v4.SELECTED if selected else v4.ROW
        c.create_rectangle(x0 + 12, y, x1 - 12, y + rh, fill=bg, outline="")
        if selected:
            c.create_rectangle(x0 + 12, y, x0 + 15, y + rh, fill=BLUE, outline="")

        ogc = shot.get("open_golf_coach", {}) or {}
        us = ogc.get("us_customary_units", {}) or {}
        club = str(shot.get("club") or "—")
        carry = float(us.get("carry_distance_yards") or 0.0)
        ball = float(us.get("ball_speed_mph") or 0.0)
        shape = str(ogc.get("shot_name") or "—")
        ts = str(shot.get("timestamp") or "—")

        # Top line is vertically centred as one unit: number, club, carry + unit.
        top_cy = y + 26
        ncx = x0 + 35
        c.create_oval(ncx - 13, top_cy - 13, ncx + 13, top_cy + 13,
                      fill=BLUE if selected else _mix(theme.SURFACE_2, theme.BG, .18),
                      outline=BLUE_LINE if selected else theme.GUIDE, width=1)
        c.create_text(ncx, top_cy, text=f"{real_idx + 1}",
                      fill=theme.TEXT if selected else theme.TEXT_2,
                      font=(v4._font(), 8, "bold"), anchor="center")
        c.create_text(x0 + 58, top_cy, text=club,
                      fill=theme.TEXT if selected else _mix(theme.TEXT_2, theme.TEXT, .05),
                      font=(v4._font(), 11, "bold"), anchor="w")
        c.create_text(x1 - 22, top_cy, text=f"{carry:.1f} yds",
                      fill=theme.TEXT if selected else theme.TEXT_2,
                      font=(v4._font(), 11, "bold"), anchor="e")

        if selected:
            # Labels need to be labels, not ghost metadata. Values remain a
            # touch brighter but both sides have comparable weight.
            rows = [
                ("Ball Speed", f"{ball:.1f} mph"),
                ("Shape", shape),
                ("Time", ts),
            ]
            for ri, (label, value) in enumerate(rows):
                ry = y + 57 + ri * 24
                c.create_text(x0 + 28, ry, text=label, fill=theme.TEXT_2,
                              font=(v4._font(), 9, "bold"), anchor="nw")
                c.create_text(x1 - 24, ry, text=value, fill=theme.TEXT,
                              font=(v4._font(), 9, "bold"), anchor="ne")

        rect = (x0 + 8, y - 2, x1 - 8, y + rh + 2, real_idx)
        app.design_shot_card_rects.append(rect)
        # Keep production hover/fallback aligned too.
        app.sidebar_shot_card_rects.append(rect)
        y += rh + 8


def paint_top_header(app, w, h, offset_x=0):
    v7.paint_top_header(app, w, h, offset_x=offset_x)

    # The production state is is_left_handed; v7's visual fallback read a
    # non-existent `dexterity` attribute. Repaint from the real state.
    hand = "LH" if getattr(app, "is_left_handed", False) else "RH"
    v7._utility_button(app.canvas, app.dexterity_btn_rect, hand)

    # Freeze final-painted controls into independent design targets. These are
    # checked before production's handler, so later redraw side-effects cannot
    # make only half a visual button clickable.
    app.design_club_btn_rect = tuple(app.club_btn_rect) if app.club_btn_rect else None
    app.design_dexterity_btn_rect = tuple(app.dexterity_btn_rect) if app.dexterity_btn_rect else None
    app.design_tools_btn_rect = tuple(app.tools_btn_rect) if app.tools_btn_rect else None
    app.design_fullscreen_btn_rect = tuple(app.fullscreen_btn_rect) if app.fullscreen_btn_rect else None
