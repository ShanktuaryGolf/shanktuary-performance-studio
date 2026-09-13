"""Eleventh-pass Shot view: Club Delivery composition and strike-marker polish only."""

import math

import overview_redesign_v7 as v7
import overview_redesign_v10 as v10

import shanktuary_performance_studio as studio
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
    path_known = v.get("path_known", True)
    face_path_known = v.get("face_path_known", True)
    if not path_known and not face_path_known:
        return "Club delivery not reported by this source"

    path = float(v.get("path", 0.0))
    face_path = float(v.get("face_path", 0.0))

    if not path_known:
        p = "Path not reported"
    elif path > 0.7:
        p = "In-to-out delivery"
    elif path < -0.7:
        p = "Out-to-in delivery"
    else:
        p = "Neutral path"

    if not face_path_known:
        f = "face not reported"
    elif abs(face_path) <= 0.6:
        f = "face nearly square to path"
    elif face_path > 0:
        f = "face open to path"
    else:
        f = "face closed to path"
    return f"{p} · {f}"


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
    # Strike is no longer an estimate (contact is reported or unavailable),
    # so the old "· Estimated" tag beside the title would now be a lie.
    del tx, title_cy

    # The panel is ~330px wide. Text beside a 176px clubface left a ~115px
    # column that wrapped "Location unavailable" onto four lines and pushed
    # the Boards line into the Path & Face panel below. So the face sits in
    # the top-right beside the Strike heading, small, and the text runs at
    # full panel width UNDER it, stacking from measured bboxes.
    face_size = max(84, min(120, (y1 - y0) * .42, (x1 - x0) * .32))
    face_w = face_size * 290 / 220  # the artwork is 290x220
    face_cx = x1 - face_w / 2
    face_cy = y0 + 20 + face_size * .5
    # One face for Shot and Quad: reported reading, the golfer's mark, or
    # nothing. It also registers the click-to-mark hit rect.
    from src.ui.contact_panel import draw_contact_face
    app.contact_clear_rect = None
    est = draw_contact_face(app, face_cx, face_cy, face_size,
                            left_limit=x0, right_limit=x1)
    text_w = int(x1 - x0)

    strike_y = y0 + 43
    c.create_text(x0, strike_y, text="Strike", fill=theme.TEXT_2,
                  font=(_ui_font(), 11, "bold"), anchor="nw")
    from src.analytics.strike import contact_location
    contact = contact_location(app.current_shot)
    head, detail = contact.headline, contact.detail
    if contact.source is None:
        # Approximate strike from the golfer's own marks (or the sweet spot
        # with none): say so, and keep the click-to-mark invitation.
        head = "Approximate"
        detail = (est.label if est is not None else "EST") + " · click the face to mark it"
    col = SECTION_TEXT
    # Headline shares the row with the face: budget it to the face's left edge.
    head_id = c.create_text(x0, strike_y + 24, text=head, fill=col,
                            font=(_ui_font(), 14, "bold"), anchor="nw",
                            width=max(110, int(x1 - face_w - 12 - x0)))
    hbb = c.bbox(head_id)
    y = max((hbb[3] + 4) if hbb else (strike_y + 52), int(face_cy + face_size * .5) + 6)
    detail_id = c.create_text(x0, y, text=detail, fill=theme.TEXT_3,
                              font=(_ui_font(), 10), anchor="nw", width=text_w)
    if contact.source == "marked":
        dbb0 = c.bbox(detail_id)
        cid = c.create_text(x0, (dbb0[3] + 2) if dbb0 else (y + 16), text="clear mark",
                            fill=BLUE_TEXT, font=(_ui_font(), 9), anchor="nw")
        cbb = c.bbox(cid)
        if cbb:
            app.contact_clear_rect = (cbb[0] - 4, cbb[1] - 2, cbb[2] + 4, cbb[3] + 2)
        detail_id = cid

    # Boards, if this shot has a saved trace: measured, and ours alone.
    from src.analytics.pressure_result import shot_line
    line = shot_line(app.current_shot, getattr(app, "is_left_handed", False))
    if line:
        dbb = c.bbox(detail_id)
        py = (dbb[3] + 10) if dbb else (y + 30)
        lbl = c.create_text(x0, py, text="Boards", fill=theme.TEXT_2,
                            font=(_ui_font(), 11, "bold"), anchor="nw")
        lbb = c.bbox(lbl)
        ly = (lbb[3] + 4) if lbb else (py + 22)
        line_id = c.create_text(x0, ly, text=line, fill=BLUE_TEXT,
                                font=(_ui_font(), 12, "bold"), anchor="nw", width=text_w)
        lbb2 = c.bbox(line_id)
        if lbb2 and lbb2[3] > y1:
            # Out of room: drop the caption rather than paint into the divider.
            c.delete(lbl)
            c.coords(line_id, x0, py)
            lbb2 = c.bbox(line_id)
            if lbb2 and lbb2[3] > y1:
                c.delete(line_id)


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
        ("Path", f"{abs(v['path']):.1f}° {'in→out' if v['path'] >= 0 else 'out→in'}"
                 if v.get("path_known", True) else "not measured"),
        ("Face / Path", f"{abs(v['face_path']):.1f}° {'open' if v['face_path'] >= 0 else 'closed'}"
                        if v.get("face_path_known", True) else "not measured"),
        ("Face / Target", f"{abs(v['face_target']):.1f}° {'open' if v['face_target'] >= 0 else 'closed'}"
                          if v.get("face_target_known", True) else "not measured"),
        ("Spin Axis", f"{abs(v['axis']):.1f}° {'R' if v['axis'] > 0 else 'L'}"),
    ]

    yy = y0 + 55
    for label, value in rows:
        c.create_text(x0, yy, text=label, fill=theme.TEXT_2,
                      font=(_ui_font(), 9), anchor="nw")
        c.create_text(x0 + table_w * .47, yy - 1, text=value,
                      fill=SECTION_TEXT if value != "not measured" else theme.TEXT_3,
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

    if v.get("path_known", True):
        path_deg = max(-12.0, min(12.0, v["path"]))
        dx = math.tan(math.radians(path_deg)) * length * mirror
        x_start, y_start = cx - dx, cy + length
        x_end, y_end = cx + dx, cy - length
        c.create_line(x_start, y_start, x_end, y_end, fill=BLUE_LINE, width=3,
                      arrow="last", arrowshape=(11, 13, 5))
        c.create_text(x_end + (8 if mirror > 0 else -8), y_end + 8, text="PATH",
                      fill=BLUE_TEXT, font=(_ui_font(), 8, "bold"),
                      anchor="w" if mirror > 0 else "e")
    else:
        # No fabricated dead-straight travel line -- a dashed neutral guide
        # with no arrow makes the absence visible instead of implying data.
        c.create_line(cx, cy + length, cx, cy - length,
                      fill=theme.TEXT_3, width=2, dash=(3, 5))
        c.create_text(cx + (10 if mirror > 0 else -10), cy - length + 8,
                      text="PATH N/A", fill=theme.TEXT_3,
                      font=(_ui_font(), 8, "bold"),
                      anchor="w" if mirror > 0 else "e")

    if v.get("face_target_known", True):
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
