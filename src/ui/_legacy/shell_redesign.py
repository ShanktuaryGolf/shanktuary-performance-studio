"""Design-only shell refinements for the Overview sandbox.

Paints a branded wordmark/nav treatment and a compact expandable shot rail on
TOP of the production shell. Interaction rectangles are kept compatible with
the existing handlers, while visual experiments remain isolated to the design
launcher.
"""

import theme

BLUE = getattr(theme, "ACCENT", "#1E6CFF")
BLUE_LINE = getattr(theme, "ACCENT_LINE", "#40A3FF")
BLUE_TEXT = getattr(theme, "ACCENT_TEXT", "#78BAFF")


def _mix_hex(a, b, t):
    try:
        aa = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        bb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        cc = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
        return "#" + "".join(f"{x:02X}" for x in cc)
    except Exception:
        return theme.SURFACE


SHELL_BG = _mix_hex(theme.RAIL, theme.BG, .35)
ROW_SELECTED = _mix_hex(theme.SURFACE_2, BLUE, .10)
ROW_HOVERLESS = _mix_hex(theme.BG, theme.SURFACE, .45)
WORDMARK_BLUE = _mix_hex(BLUE_TEXT, theme.TEXT, .12)


def _draw_nav_icon(c, kind, cx, cy, col):
    """Tiny line icons; intentionally simple and non-emoji."""
    if kind == "Overview":
        for dy, ww in ((-6, 17), (0, 12), (6, 20)):
            c.create_line(cx - ww / 2, cy + dy, cx + ww / 2, cy + dy, fill=col, width=2)
    elif kind == "Quad":
        for ox in (-6, 4):
            for oy in (-6, 4):
                c.create_rectangle(cx + ox, cy + oy, cx + ox + 7, cy + oy + 7, outline=col, width=1)
    elif kind == "Range":
        c.create_line(cx - 10, cy + 6, cx - 3, cy - 5, cx + 2, cy + 1, cx + 8, cy - 7, cx + 11, cy + 6,
                      fill=col, width=1, smooth=True)
        c.create_line(cx - 11, cy + 7, cx + 11, cy + 7, fill=col, width=1)
    elif kind == "Disp":
        for ox, oy, r in ((-7, 4, 2), (-2, -4, 2), (5, 2, 2), (9, -6, 2)):
            c.create_oval(cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r, fill=col, outline="")
        c.create_line(cx, cy - 11, cx, cy + 11, fill=theme.GUIDE)
    elif kind == "Table":
        for i in range(4):
            c.create_line(cx - 10, cy - 8 + i * 6, cx + 10, cy - 8 + i * 6, fill=col, width=1)
        c.create_line(cx - 3, cy - 8, cx - 3, cy + 10, fill=col, width=1)
        c.create_line(cx + 5, cy - 8, cx + 5, cy + 10, fill=col, width=1)
    elif kind == "Nums":
        c.create_text(cx, cy, text="123", fill=col, font=(theme.ui_font(), 7, "bold"), anchor="center")
    elif kind == "Bag":
        c.create_line(cx - 5, cy - 8, cx + 4, cy - 8, cx + 7, cy + 9, cx - 7, cy + 9, cx - 5, cy - 8,
                      fill=col, width=1)
        c.create_line(cx - 1, cy - 12, cx - 3, cy - 3, fill=col, width=1)
        c.create_line(cx + 4, cy - 12, cx + 1, cy - 3, fill=col, width=1)
    elif kind == "Fit":
        for dy, knob in ((-7, -3), (0, 5), (7, 0)):
            c.create_line(cx - 10, cy + dy, cx + 10, cy + dy, fill=col, width=1)
            c.create_oval(cx + knob - 2, cy + dy - 2, cx + knob + 2, cy + dy + 2, fill=col, outline="")
    elif kind == "Lab":
        c.create_line(cx - 11, cy + 3, cx - 7, cy + 3, cx - 3, cy - 6, cx + 1, cy + 8,
                      cx + 5, cy - 2, cx + 11, cy - 2, fill=col, width=1, smooth=True)


def paint_nav(app, h):
    c = app.canvas
    rw = theme.RAIL_W
    c.create_rectangle(0, 0, rw, h, fill=SHELL_BG, outline="")
    c.create_line(rw - 1, 0, rw - 1, h, fill=theme.HAIRLINE)

    # App mark: same electric-blue family, with a deliberately lighter upper
    # half so the icon has depth without introducing another hue.
    c.create_rectangle(14, 15, 50, 51, fill="#185DE0", outline="")
    c.create_rectangle(14, 15, 50, 33, fill="#2D7BFF", outline="")
    c.create_text(32, 33, text="S", fill=theme.TEXT, font=(theme.ui_font(), 15, "bold"), anchor="center")

    app.mode_pill_rects = {}
    y = 84
    for mode_id, label, _tip in theme.NAV_ITEMS:
        active = app.view_mode == mode_id
        app.mode_pill_rects[mode_id] = (4, y, rw - 4, y + 46)
        if active:
            c.create_rectangle(6, y, rw - 6, y + 46, fill=ROW_SELECTED, outline="")
            c.create_rectangle(6, y, 9, y + 46, fill=BLUE, outline="")
        col = theme.TEXT if active else theme.TEXT_3
        icon_col = BLUE_LINE if active else _mix_hex(theme.TEXT_3, theme.TEXT_2, .35)
        _draw_nav_icon(c, label, 32, y + 16, icon_col)
        c.create_text(32, y + 37, text=label, fill=col,
                      font=(theme.ui_font(), 7, "bold" if active else "normal"), anchor="center")
        y += theme.NAV_ITEM_H

    # Setup stays pinned to the bottom but uses the same visual language.
    sy0 = h - 70
    active = app.view_mode == 10
    app.nav_setup_rect = (4, sy0, rw - 4, h - 22)
    if active:
        c.create_rectangle(6, sy0, rw - 6, h - 22, fill=ROW_SELECTED, outline="")
        c.create_rectangle(6, sy0, 9, h - 22, fill=BLUE, outline="")
    col = theme.TEXT if active else theme.TEXT_3
    # Minimal settings sliders instead of the old empty-square glyph.
    for dy, knob in ((0, -3), (6, 4), (12, 0)):
        c.create_line(22, sy0 + 11 + dy, 42, sy0 + 11 + dy, fill=col, width=1)
        c.create_oval(32 + knob - 2, sy0 + 11 + dy - 2, 32 + knob + 2, sy0 + 11 + dy + 2,
                      fill=col, outline="")
    c.create_text(32, h - 31, text="Setup", fill=col, font=(theme.ui_font(), 7), anchor="center")


def paint_sidebar(app, w, h):
    if app.sidebar_collapsed:
        return

    c = app.canvas
    x0 = theme.RAIL_W
    x1 = app.sidebar_width
    width = x1 - x0

    # Cover the production sidebar after it has registered its controls. Then
    # redraw a calmer branded shell while keeping those interaction hooks.
    c.create_rectangle(x0, 0, x1, h, fill=SHELL_BG, outline="")
    c.create_line(x1 - 1, 0, x1 - 1, h, fill=theme.HAIRLINE)

    # Wordmark. This intentionally behaves like product chrome, not a giant
    # logo treatment: crisp wordmark + restrained descriptor.
    c.create_text(x0 + 15, 14, text="SHANKTUARY", fill=theme.TEXT,
                  font=(theme.ui_font(), 12, "bold"), anchor="nw")
    c.create_text(x0 + 15, 33, text="PERFORMANCE GOLF", fill=WORDMARK_BLUE,
                  font=(theme.ui_font(), 6, "bold"), anchor="nw")

    # Replace the old filled left-pointing control with a quiet chevron tucked
    # into the edge. Preserve the production hit rectangle.
    tr = getattr(app, "sidebar_toggle_rect", None)
    if tr:
        c.create_line(tr[0] + 10, (tr[1] + tr[3]) / 2,
                      tr[2] - 9, (tr[1] + tr[3]) / 2 - 7,
                      fill=theme.TEXT_3, width=2)
        c.create_line(tr[2] - 9, (tr[1] + tr[3]) / 2 - 7,
                      tr[0] + 10, (tr[1] + tr[3]) / 2 - 14,
                      fill=theme.TEXT_3, width=2)

    # Session control strip, using the existing click targets but removing the
    # quirky emoji/box language.
    sr = getattr(app, "sidebar_session_btn_rect", None)
    rr = getattr(app, "sidebar_rename_sess_btn_rect", None)
    nr = getattr(app, "sidebar_new_sess_btn_rect", None)
    fr = getattr(app, "sidebar_filter_btn_rect", None)
    active_sess = app.get_active_session() if hasattr(app, "get_active_session") else {}
    sess_title = active_sess.get("name", "Session")
    if len(sess_title) > 15:
        sess_title = sess_title[:13] + "…"

    if sr:
        c.create_rectangle(*sr, fill=ROW_HOVERLESS, outline="")
        c.create_text(sr[0] + 10, (sr[1] + sr[3]) / 2, text=sess_title.upper(),
                      fill=theme.TEXT_2, font=(theme.ui_font(), 7, "bold"), anchor="w")
        c.create_text(sr[2] - 10, (sr[1] + sr[3]) / 2, text="⌄", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 9), anchor="e")
    if rr:
        c.create_text((rr[0] + rr[2]) / 2, (rr[1] + rr[3]) / 2, text="···",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 10, "bold"), anchor="center")
    if nr:
        c.create_rectangle(*nr, fill=BLUE, outline="")
        c.create_text((nr[0] + nr[2]) / 2, (nr[1] + nr[3]) / 2, text="+",
                      fill=theme.TEXT, font=(theme.ui_font(), 12, "bold"), anchor="center")

    if fr:
        label = "ALL CLUBS" if app.club_filter == "ALL" else str(app.club_filter).upper()
        c.create_text(fr[0] + 2, (fr[1] + fr[3]) / 2, text=label,
                      fill=BLUE_TEXT if app.club_filter != "ALL" else theme.TEXT_2,
                      font=(theme.ui_font(), 7, "bold"), anchor="w")
        c.create_text(fr[2] - 2, (fr[1] + fr[3]) / 2, text="⌄", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="e")

    # Compact shot rail. Only the selected row expands; all other rows recede
    # to number + prominent club + carry. This is deliberately list-like rather
    # than a tower of cards.
    filtered = app.get_filtered_shots() if hasattr(app, "get_filtered_shots") else list(app.session_shots)
    items = list(reversed(filtered))
    app.sidebar_shot_card_rects = []
    y = 132
    bottom = h - 44

    for shot in items:
        try:
            real_idx = app.session_shots.index(shot)
        except ValueError:
            continue
        selected = real_idx == app.selected_shot_index
        rh = 72 if selected else 42
        if y + rh > bottom:
            break

        if selected:
            c.create_rectangle(x0 + 8, y, x1 - 8, y + rh, fill=ROW_SELECTED, outline="")
            c.create_rectangle(x0 + 8, y, x0 + 12, y + rh, fill=BLUE, outline="")
        else:
            c.create_line(x0 + 12, y + rh - 1, x1 - 12, y + rh - 1, fill=_mix_hex(theme.HAIRLINE, theme.BG, .55))

        ogc = shot.get("open_golf_coach", {}) or {}
        us = ogc.get("us_customary_units", {}) or {}
        club = str(shot.get("club") or "—")
        carry = float(us.get("carry_distance_yards") or 0.0)
        ball = float(us.get("ball_speed_mph") or 0.0)
        shape = str(ogc.get("shot_name") or "")
        ts = str(shot.get("timestamp") or "")

        num_col = theme.TEXT if selected else theme.TEXT_3
        club_col = BLUE_TEXT if selected else _mix_hex(theme.TEXT_2, theme.TEXT, .10)
        carry_col = theme.TEXT if selected else theme.TEXT_2
        c.create_text(x0 + 20, y + 12, text=f"#{real_idx + 1}", fill=num_col,
                      font=(theme.ui_font(), 8, "bold"), anchor="nw")
        c.create_text(x0 + 62, y + 11, text=club, fill=club_col,
                      font=(theme.ui_font(), 9, "bold"), anchor="nw")
        c.create_text(x1 - 18, y + 10, text=f"{carry:.1f}", fill=carry_col,
                      font=(theme.ui_font(), 11, "bold"), anchor="ne")
        c.create_text(x1 - 18, y + 25, text="YDS", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 6), anchor="ne")

        if selected:
            c.create_text(x0 + 20, y + 42, text=f"{ball:.1f} mph  ·  {shape}", fill=theme.TEXT_2,
                          font=(theme.ui_font(), 7), anchor="nw")
            c.create_text(x0 + 20, y + 58, text=ts, fill=theme.TEXT_3,
                          font=(theme.ui_font(), 7), anchor="nw")

        app.sidebar_shot_card_rects.append((x0 + 8, y, x1 - 8, y + rh, real_idx))
        y += rh + 2

    cr = getattr(app, "sidebar_clear_btn_rect", None)
    if cr:
        c.create_text((x0 + x1) / 2, h - 22, text="Clear session", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 7), anchor="center")
