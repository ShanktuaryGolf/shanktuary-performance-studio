"""Eleventh-pass Shot view: Club Delivery composition and strike-marker polish only."""

import math

import shanktuary_performance_studio as studio
import overview_redesign_v7 as v7
import overview_redesign_v10 as v10
import theme

BLUE_LINE = v7.BLUE_LINE
BLUE_TEXT = v7.BLUE_TEXT
ORANGE = v7.ORANGE
GOOD = v7.GOOD
GRID_LINE = v7.GRID_LINE
SECTION_TEXT = v7.SECTION_TEXT
_ui_font = v7._ui_font
_mix = v7._mix


def _delivery_takeaway(v):
    path = float(v.get("path", 0.0))
    face_path = float(v.get("face_path", 0.0))

    if path > 0.7:
        p = "In-to-out delivery"
    elif path < -0.7:
        p = "Out-to-in delivery"
    else:
        p = "Neutral path"

    if abs(face_path) <= 0.6:
        f = "face nearly square to path"
    elif face_path > 0:
        f = "face open to path"
    else:
        f = "face closed to path"
    return f"{p} · {f}"


def _draw_face_with_clear_marker(app, cx, cy, size):
    """Draw the production clubface with a higher-contrast impact marker."""
    c = app.canvas
    img = app.get_scaled_club_asset(
        studio.FACE_PATH, int(size), mirror=getattr(app, "is_left_handed", False)
    )
    if img:
        c.create_image(cx, cy, image=img, anchor="c")
    else:
        # Preserve a useful fallback if the image asset is unavailable.
        c.create_oval(cx - size * .34, cy - size * .28,
                      cx + size * .34, cy + size * .28,
                      fill=theme.SURFACE_2, outline=theme.GUIDE)

    # Match the estimator geometry used by the production helper, but replace
    # the dotted orange ring with a calmer high-contrast impact lens.
    left_handed = bool(getattr(app, "is_left_handed", False))
    sdx = (43.5 / 220.0) * size * (1 if left_handed else -1)
    sdy = (-40.0 / 220.0) * size
    ssx, ssy = cx + sdx, cy + sdy

    head, _, _ = app.summarize_strike(app.current_shot)
    dy = 0.0
    if "Low" in head:
        dy = size * 0.14
    elif "High" in head:
        dy = -size * 0.14

    mx, my = ssx + size * 0.05, ssy + dy

    # Keep the sweet-spot reference subtle and neutral.
    guide = _mix(theme.GUIDE, theme.TEXT_2, .10)
    for d in (-5, 4):
        c.create_line(ssx + d, ssy, ssx + d + 2, ssy, fill=guide)
        c.create_line(ssx, ssy + d, ssx, ssy + d + 2, fill=guide)

    lens_r = max(8, size * .075)
    ring_r = max(11, size * .105)
    lens = _mix(theme.BG, "#172231", .48)
    c.create_oval(mx - lens_r, my - lens_r, mx + lens_r, my + lens_r,
                  fill=lens, outline="")
    c.create_oval(mx - ring_r, my - ring_r, mx + ring_r, my + ring_r,
                  fill="", outline=ORANGE, width=2)
    dot_r = max(3, size * .022)
    c.create_oval(mx - dot_r, my - dot_r, mx + dot_r, my + dot_r,
                  fill=ORANGE, outline="")


def _draw_strike(app, x0, y0, x1, y1):
    """Top half of the cohesive Club Delivery panel."""
    c = app.canvas
    title_id = c.create_text(x0, y0, text="Club Delivery", fill=SECTION_TEXT,
                             font=(_ui_font(), 14, "bold"), anchor="nw")
    bb = c.bbox(title_id)
    if bb:
        tx = bb[2] + 8
        title_cy = (bb[1] + bb[3]) / 2
    else:
        tx = x0 + 96
        title_cy = y0 + 9
    # Use the measured title centerline, rather than a guessed y-offset.
    c.create_text(tx, title_cy, text="· Estimated", fill=ORANGE,
                  font=(_ui_font(), 11, "bold"), anchor="w")

    strike_y = y0 + 43
    c.create_text(x0, strike_y, text="Strike", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")

    head, detail, _ = app.summarize_strike(app.current_shot)
    col = GOOD if ("center" in head.lower() or "pure" in head.lower()) else SECTION_TEXT
    c.create_text(x0, strike_y + 28, text=head, fill=col,
                  font=(_ui_font(), 15, "bold"), anchor="nw")
    c.create_text(x0, strike_y + 55, text=detail, fill=theme.TEXT_3,
                  font=(_ui_font(), 10), anchor="nw",
                  width=max(110, int((x1 - x0) * .34)))

    # Lower the clubface a touch so it clears the title/subhead visually.
    face_cx = x0 + (x1 - x0) * .73
    face_cy = y0 + (y1 - y0) * .62
    face_size = max(132, min(176, (y1 - y0) * .72, (x1 - x0) * .55))
    _draw_face_with_clear_marker(app, face_cx, face_cy, face_size)


def _draw_delivery(app, x0, y0, x1, y1, v):
    """Bottom half: interpretation, metrics, and top-down path/face geometry."""
    c = app.canvas
    w = x1 - x0

    c.create_text(x0, y0 + 2, text="Path & Face", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    c.create_text(x0, y0 + 25, text=_delivery_takeaway(v), fill=BLUE_TEXT,
                  font=(_ui_font(), 9, "bold"), anchor="nw")

    table_w = w * .43
    rows = [
        ("Path", f"{abs(v['path']):.1f}° {'in→out' if v['path'] >= 0 else 'out→in'}"),
        ("Face / Path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"),
        ("Face / Target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"),
        ("Spin Axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]

    yy = y0 + 55
    for label, value in rows:
        c.create_text(x0, yy, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(x0 + table_w * .47, yy - 1, text=value, fill=SECTION_TEXT,
                      font=(_ui_font(), 10, "bold"), anchor="nw")
        yy += 24

    gx0, gx1 = x0 + table_w + 8, x1 - 6
    cx = (gx0 + gx1) / 2
    cy = y0 + (y1 - y0) * .62
    length = min(58, max(36, (y1 - y0) * .28))
    mirror = -1 if getattr(app, "is_left_handed", False) else 1

    c.create_line(cx, cy + length + 13, cx, cy - length - 18,
                  fill=GRID_LINE, dash=(3, 5))
    c.create_text(cx, cy - length - 22, text="TARGET", fill=theme.TEXT_3,
                  font=(_ui_font(), 8, "bold"), anchor="s")

    path_deg = max(-12.0, min(12.0, v["path"]))
    dx = math.tan(math.radians(path_deg)) * length * mirror
    x_start, y_start = cx - dx, cy + length
    x_end, y_end = cx + dx, cy - length
    c.create_line(x_start, y_start, x_end, y_end, fill=BLUE_LINE, width=3,
                  arrow="last", arrowshape=(11, 13, 5))
    c.create_text(x_end + (8 if mirror > 0 else -8), y_end + 8, text="PATH",
                  fill=BLUE_TEXT, font=(_ui_font(), 8, "bold"),
                  anchor="w" if mirror > 0 else "e")

    face_deg = max(-16.0, min(16.0, v["face_target"])) * mirror
    theta = math.radians(face_deg)
    half = 28
    fx = math.cos(theta) * half
    fy = math.sin(theta) * half
    c.create_line(cx - fx, cy - fy, cx + fx, cy + fy, fill=ORANGE, width=4)
    c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                  fill=theme.TEXT_2, outline=theme.BG)
    c.create_text(cx + fx + 7, cy + fy, text="FACE", fill=ORANGE,
                  font=(_ui_font(), 8, "bold"), anchor="w")


def draw_overview(*args, **kwargs):
    # Step 4 changes the right-side Club Delivery content only. The previous
    # navigation, dispersion, and Shot Shape passes remain untouched.
    v7._draw_strike = _draw_strike
    v7._draw_delivery = _draw_delivery
    return v10.draw_overview(*args, **kwargs)
