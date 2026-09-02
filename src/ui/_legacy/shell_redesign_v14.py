"""Fourteenth-pass shell: install the new global Shanktuary branding.

Keeps the accepted v13 gold/teal navigation and Recent Shots treatment, while
replacing the old church-era header art with the exact new horizontal lockup
asset and fixing the duplicate New Session + control.
"""

import shell_redesign_v9 as v9
import shell_redesign_v11 as v11
import shell_redesign_v13 as v13

import theme

NAV_RAIL_W = v13.NAV_RAIL_W
COLLAPSED_GUTTER_W = v13.COLLAPSED_GUTTER_W


def _fit_text(canvas, text, max_px, font):
    """Shorten ``text`` with an ellipsis until it fits ``max_px``.

    Measures the real rendered width instead of assuming a character count:
    the UI font is resolved at runtime, so "19 characters" is a different
    pixel width on different machines. Defined here rather than imported
    from v4 — v4 imports this module's ancestors, so importing it back
    would be circular.
    """
    text = str(text)
    if max_px <= 0:
        return ""

    def width(s):
        probe = canvas.create_text(-4000, -4000, text=s, font=font, anchor="nw")
        bbox = canvas.bbox(probe)
        canvas.delete(probe)
        return (bbox[2] - bbox[0]) if bbox else 0

    if width(text) <= max_px:
        return text
    for n in range(len(text) - 1, 0, -1):
        candidate = text[:n].rstrip() + "…"
        if width(candidate) <= max_px:
            return candidate
    return "…"


def paint_nav(app, h):
    return v13.paint_nav(app, h)


def paint_sidebar(app, w, h):
    """Keep v13's drawer, but expose exactly one New Session + button."""
    v13.paint_sidebar(app, w, h)

    if getattr(app, "sidebar_collapsed", False):
        return

    c = app.canvas
    x1 = app.sidebar_width
    control_y = 75

    # v4's accepted drawer hard-coded a filled + at the far right, while v13
    # also repainted production's separate new-session rect. Both are gone
    # now (v13's copy was removed), so only production's own + underneath
    # needs covering — and that cover must not extend over the session
    # label, which reaches toward it.
    nr = getattr(app, "sidebar_new_sess_btn_rect", None)
    if nr:
        nx1, ny1, nx2, ny2 = nr
        # Cover production's button only where the label does not run: the
        # label baseline sits at control_y..control_y+14, and a full-height
        # wipe here clipped its tail.
        c.create_rectangle(nx1 - 2, ny1 - 2, nx2 + 2, ny2 + 2,
                           fill=v13.SIDEBAR_BG, outline="")

    bx1, by1 = x1 - 46, control_y - 6
    bx2, by2 = x1 - 16, control_y + 24
    c.create_rectangle(bx1 - 2, by1 - 2, bx2 + 2, by2 + 2,
                       fill=v13.SIDEBAR_BG, outline="")
    c.create_rectangle(bx1, by1, bx2, by2,
                       fill="#10252E", outline=v13.GOLD, width=1)
    c.create_text((bx1 + bx2) / 2, (by1 + by2) / 2,
                  text="+", fill=v13.GOLD_LIGHT,
                  font=(theme.ui_font(), 14, "bold"), anchor="center")

    # Make the visible geometry the real click target as well.
    app.sidebar_new_sess_btn_rect = (bx1, by1, bx2, by2)

    # Session label LAST. Everything above wipes rectangles over the drawer
    # (production's + button position, the old + slot), and those wipes ran
    # after v4 painted the label — clipping its tail to "Session 1 - 7 Iro".
    # Repainting the button face and label here, once all covering is done,
    # is the only ordering where nothing can eat it.
    sr = getattr(app, "sidebar_session_btn_rect", None)
    if sr:
        active = app.get_active_session() if hasattr(app, "get_active_session") else {}
        title = str(active.get("name", "Session"))
        text_left = theme.RAIL_W + 18
        # Free space runs to the chevron, which sits just left of the + button.
        chevron_x = x1 - 66
        avail = chevron_x - text_left - 6

        c.create_rectangle(sr[0], sr[1], sr[2], sr[3],
                           fill=v13.SIDEBAR_ROW, outline="")
        c.create_text(text_left, control_y,
                      text=_fit_text(c, title, avail,
                                     (theme.ui_font(), 9, "bold")),
                      fill=theme.TEXT_2,
                      font=(theme.ui_font(), 9, "bold"), anchor="nw")
        c.create_text(chevron_x, control_y + 1, text="⌄", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 10), anchor="nw")


def paint_top_header(app, w, h, offset_x=0):
    """Global header using the exact new horizontal PNG lockup."""
    c = app.canvas
    hh = 52

    # Fully cover production/older design branding first. The new lockup carries
    # all brand personality, so the ribbon itself stays restrained and premium.
    c.create_rectangle(0, 0, w, hh, fill="#071722", outline="")
    c.create_line(0, hh - 1, w, hh - 1, fill="#24434C", width=1)

    lockup = v11._load_brand_image(
        app, "_brand_lockup_v14_img", v11.LOCKUP_PATH, 44
    )
    if lockup is not None:
        c.create_image(10, 4, image=lockup, anchor="nw")

    # Preserve the accepted operational controls and exact hit geometry.
    right = w - 10
    y1, y2 = 7, 45
    fs_w, tools_w, dex_w, club_w, gap = 38, 86, 58, 112, 7

    app.fullscreen_btn_rect = (right - fs_w, y1, right, y2)
    right -= fs_w + gap
    app.tools_btn_rect = (right - tools_w, y1, right, y2)
    right -= tools_w + gap
    app.dexterity_btn_rect = (right - dex_w, y1, right, y2)
    right -= dex_w + gap
    app.club_btn_rect = (right - club_w, y1, right, y2)

    club_rect = app.club_btn_rect
    status_x = club_rect[0] - 82
    c.create_oval(status_x, 23, status_x + 8, 31,
                  fill=v9.GOOD, outline="")
    c.create_text(status_x + 14, 27, text="Ready", fill=theme.TEXT_2,
                  font=(v9.v4._font(), 9, "bold"), anchor="w")

    v9._utility_button(
        c, app.club_btn_rect,
        f"{getattr(app, 'current_club', 'Club')}  ▼",
        bool(getattr(app, "show_club_menu", False)),
    )
    hand = "LH" if getattr(app, "is_left_handed", False) else "RH"
    v9._utility_button(c, app.dexterity_btn_rect, hand)
    v9._utility_button(
        c, app.tools_btn_rect, "Tools  ▼",
        bool(getattr(app, "show_tools_menu", False)),
    )
    v9._utility_button(c, app.fullscreen_btn_rect, "⛶")

    app.design_club_btn_rect = tuple(app.club_btn_rect) if app.club_btn_rect else None
    app.design_dexterity_btn_rect = tuple(app.dexterity_btn_rect) if app.dexterity_btn_rect else None
    app.design_tools_btn_rect = tuple(app.tools_btn_rect) if app.tools_btn_rect else None
    app.design_fullscreen_btn_rect = tuple(app.fullscreen_btn_rect) if app.fullscreen_btn_rect else None
