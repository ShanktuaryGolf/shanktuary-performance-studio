"""Shared contact presentation. Ball-flight comparisons are not strike estimates."""
import tkinter.font as tkfont

import theme
from src.analytics.index import valid_shots
from src.analytics.strike import (
    FACE_MAX_H_MM,
    FACE_MAX_V_MM,
    FACE_OPAQUE_BOTTOM,
    FACE_OPAQUE_TOP,
    FaceGeometry,
    contact_location,
)
from src.analytics.strike_estimate import estimate as strike_estimate

from . import tokens


def draw_contact_face(app, cx, cy, size, left_limit=None, right_limit=None,
                      register=True):
    """Schematic face shared by Shot and Quad. Click-to-mark lives here.

    Draws (in order): the artwork, faint peers (other marked shots of the
    same club this session), and the current shot's contact -- a reported
    reading or the golfer's mark. Registers `app.contact_face_rect` and
    `app.contact_face_geometry` so a click on the face becomes a mark.

    The artwork is wider than it is tall, so the CLAMP uses the real image
    width -- sizing the centre from `size` alone pushed the graphic past the
    panel edge while every text assertion still passed.
    """
    import shanktuary_performance_studio as studio

    c = app.canvas
    lefty = bool(getattr(app, "is_left_handed", False))
    # Unpadded: the square-padded variant is 158px tall for a 90px face and
    # its transparent margin sat on top of the badge row above it.
    try:
        image = app.get_scaled_club_asset(studio.FACE_PATH, int(size), mirror=lefty,
                                          pad_square=False)
    except TypeError:   # test doubles with the old signature
        image = app.get_scaled_club_asset(studio.FACE_PATH, int(size), mirror=lefty)
    width = size * 290 / 220
    if image:
        try:
            width, _height = image.width(), image.height()
        except Exception:
            width = size * 290 / 220
        if left_limit is not None:
            cx = max(cx, left_limit + width / 2)
        if right_limit is not None:
            cx = min(cx, right_limit - width / 2)
        c.create_image(cx, cy, image=image, anchor="c")
    else:
        c.create_rectangle(cx - size * .48, cy - size * .30,
                           cx + size * .48, cy + size * .30,
                           outline=tokens.GUIDE, fill="")

    geom = FaceGeometry(cx=cx, cy=cy, size=size, left_handed=lefty)
    if register:
        app.contact_face_geometry = geom
        # Hit rect = the opaque clubhead, not the artwork's transparent padding.
        top = cy - size / 2
        app.contact_face_rect = (cx - width / 2, top + FACE_OPAQUE_TOP * size,
                                 cx + width / 2, top + FACE_OPAQUE_BOTTOM * size)

    # Peers: the golfer's other marks for this club, faint, so a pattern
    # (say, everything toe-side) shows up without any estimator.
    current = getattr(app, "current_shot", None)
    club = current.get("club") if isinstance(current, dict) else None
    pr = max(2, size * .009)
    for s in getattr(app, "session_shots", []) or []:
        if s is current or not isinstance(s, dict) or s.get("club") != club:
            continue
        peer = contact_location(s)
        if peer.source != "marked" or not peer.complete:
            continue
        px, py = geom.mm_to_px(peer.horizontal_mm, peer.vertical_mm)
        # Hollow, dark ring: readable on the grey artwork, clearly not the
        # current shot's filled marker.
        c.create_oval(px-pr, py-pr, px+pr, py+pr, fill="", outline=tokens.PAGE_BG,
                      width=1, tags="contact-peer")

    contact = contact_location(current)
    if not contact.complete:
        # Approximate strike: a hollow ring at "where you usually hit it",
        # sized by the spread of your marks. Never a dot, never unlabelled --
        # the caller writes the EST label from the returned estimate.
        est = strike_estimate(current if isinstance(current, dict) else {},
                              all_shots(app))
        ex, ey = geom.mm_to_px(est.horizontal_mm, est.vertical_mm)
        er = est.radius_mm * geom.px_per_mm
        # Tk has no alpha: a stipple gives the zone a translucent wash so it
        # reads as an AREA, with a solid teal rim so it is not mistaken for
        # one more peer ring. Hollow (fill="" for the hit-test/oval type
        # check) is kept for the rim; the wash is a second, stippled oval.
        c.create_oval(ex-er, ey-er, ex+er, ey+er, fill=tokens.TEAL, outline="",
                      stipple="gray25", tags="contact-estimate-wash")
        c.create_oval(ex-er, ey-er, ex+er, ey+er, fill="", outline=tokens.TEAL_LINE,
                      width=3, tags="contact-estimate")
        # Small centre tick so the ring reads as "around here", not a target.
        t = max(3, size * .012)
        c.create_line(ex-t, ey, ex+t, ey, fill=tokens.TEAL_LINE, width=2, tags="contact-estimate")
        c.create_line(ex, ey-t, ex, ey+t, fill=tokens.TEAL_LINE, width=2, tags="contact-estimate")
        if c.find_withtag("contact-peer"):
            c.tag_raise("contact-estimate-wash", "contact-peer")
            c.tag_raise("contact-estimate", "contact-peer")
        return est
    # Generic iron artwork: schematic coordinates, not a calibrated club model.
    # Do not pin an out-of-artwork reading to an apparently exact edge location.
    hx, vy = contact.horizontal_mm, contact.vertical_mm
    if abs(hx) > FACE_MAX_H_MM or abs(vy) > FACE_MAX_V_MM:
        return
    mx, my = geom.mm_to_px(hx, vy)
    r = max(4, size * .035)
    fill = tokens.GOLD if contact.source == "reported" else tokens.TEAL_TEXT
    c.create_oval(mx-r, my-r, mx+r, my+r, fill=fill,
                  outline=tokens.TEXT, width=1, tags="contact-marker")
    return None


def all_shots(app):
    """Every stored shot across sessions: marks accumulate over days, and an
    estimate from one session's two marks would be noise."""
    out = []
    for sess in getattr(app, "sessions", None) or []:
        if isinstance(sess, dict):
            out.extend(x for x in (sess.get("shots") or []) if isinstance(x, dict))
    if not out:
        out = [x for x in (getattr(app, "session_shots", []) or []) if isinstance(x, dict)]
    return out


def handle_face_click(app, x, y):
    """Turn a click on the registered face into a mark. Returns True if handled."""
    rect = getattr(app, "contact_face_rect", None)
    geom = getattr(app, "contact_face_geometry", None)
    shot = getattr(app, "current_shot", None)
    if not rect or geom is None or not isinstance(shot, dict):
        return False
    clear = getattr(app, "contact_clear_rect", None)
    if clear and clear[0] <= x <= clear[2] and clear[1] <= y <= clear[3]:
        app.clear_contact_mark(shot)
        app.draw_screen()
        return True
    if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
        return False
    mm = geom.px_to_mm(x, y)
    if mm is None:
        return True   # on the artwork but off the playable face: swallow
    if contact_location(shot).source == "reported":
        return True   # never overwrite a real reading with a click
    app.mark_contact(shot, *mm)
    app.draw_screen()
    return True


def draw_contact_panel(app, x0, y0, x1, y1):
    """Quad's contact panel: the face IS the panel.

    Header row, one status line, the face as large as the panel allows
    (the artwork is 290x220, so height is the binding axis), an EST label
    under the ring when the strike is approximate, and one footer line.
    Rows are placed from measured bboxes, never fixed offsets.
    """
    c = app.canvas
    width, height = x1-x0, y1-y0
    scale = max(.85, min(1.25, width / 520, height / 350))
    pad = max(12, int(16*scale))
    small = tkfont.Font(root=c, family=theme.ui_font(), size=max(7, int(9*scale)))
    body = tkfont.Font(root=c, family=theme.ui_font(), size=max(8, int(10*scale)))
    bold = tkfont.Font(root=c, family=theme.ui_font(), size=max(9, int(11*scale)), weight="bold")
    left, right = x0+pad, x1-pad

    def text(x, yy, value, font=body, color=tokens.TEXT_2, anchor="nw", budget=None):
        if budget is not None:
            while value and font.measure(value) > budget:
                value = value[:-2].rstrip("…") + "…" if len(value) > 2 else ""
        return c.create_text(x, yy, text=value, fill=color, font=font, anchor=anchor)

    def bottom(item, fallback):
        bb = c.bbox(item)
        return bb[3] if bb else fallback

    contact = contact_location(app.current_shot)
    app.contact_clear_rect = None

    # Header: title left, source badge right.
    y = y0 + pad
    hid = text(left, y, "IMPACT LOCATION", small, tokens.TEXT_3)
    text(right, y, contact.badge, small,
         tokens.TEAL_TEXT if contact.available else tokens.TEXT_3, "ne")
    y = bottom(hid, y + 14) + 6

    # Status: what we know, in one line. "clear mark" shares the row.
    if contact.complete:
        status = f"{contact.headline} — {contact.horizontal_text} / {contact.vertical_text}"
    elif contact.available:
        status = f"{contact.headline} — {contact.horizontal_text} / {contact.vertical_text}"
    else:
        status = "Approximate strike — click the face where you felt it"
    clear_w = 0
    if contact.source == "marked":
        cid = text(right, y, "clear mark", small, tokens.TEAL_TEXT, "ne")
        bb = c.bbox(cid)
        if bb:
            app.contact_clear_rect = (bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2)
            clear_w = (bb[2] - bb[0]) + 16
    sid = text(left, y, status, bold if contact.complete else body,
               tokens.TEXT if contact.complete else tokens.TEXT_2,
               budget=(right - left) - clear_w)
    y = bottom(sid, y + 16) + 8

    # Footer reserved first so the face can take everything in between.
    foot_h = small.metrics("linespace")
    foot_y = y1 - pad - foot_h
    label_h = small.metrics("linespace") + 4          # EST label under the face
    avail_h = foot_y - 6 - label_h - y
    avail_w = right - left
    # Artwork aspect is 290:220 and `size` is the image HEIGHT, but only the
    # top 60% of that height is opaque: budget the visible clubhead, not the
    # transparent padding, or the face floats above an empty band.
    visible = FACE_OPAQUE_BOTTOM - FACE_OPAQUE_TOP
    size = max(90, min(avail_h / visible, avail_w * 220 / 290))
    face_cx = (left + right) / 2
    face_cy = y - FACE_OPAQUE_TOP * size + size / 2
    est = draw_contact_face(app, face_cx, face_cy, size, left_limit=left, right_limit=right)
    y = face_cy - size / 2 + FACE_OPAQUE_BOTTOM * size + 6

    if est is not None:
        # Label the ring for what it is, and where it points.
        where = f"{est.label} · {_axis_short(est.horizontal_mm, 'heel', 'toe')} / {_axis_short(est.vertical_mm, 'high', 'low')}"
        if est.basis == "none":
            where = est.label + " · ring at the sweet spot"
        eid = text(face_cx, y, where, small, tokens.TEAL_TEXT, anchor="n", budget=avail_w)
        y = bottom(eid, y + label_h)

    text(left, foot_y, "Nova measures ball flight, not face contact", small,
         tokens.TEXT_3, budget=avail_w)


def _axis_short(value, positive, negative):
    if abs(value) < 0.05:
        return "centre"
    return f"{abs(value):.0f} mm {positive if value > 0 else negative}"


def full_swing_peers(shot, session_shots):
    """Same-club full swings, via the one gate the Index already uses."""
    shot = shot if isinstance(shot, dict) else {}
    club = shot.get("club")
    identity = shot.get("timestamp_ns") or shot.get("shotId")
    return [s for s in valid_shots(list(session_shots))
            if s is not shot and s.get("club") == club
            and not (identity is not None and
                     (s.get("timestamp_ns") or s.get("shotId")) == identity)]
