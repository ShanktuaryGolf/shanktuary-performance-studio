"""Club strike-marker alignment pass.

Keeps the accepted v3 Club layout and credibility states, but redraws the
Impact Location clubface with the exact same lens/ring/dot marker treatment used
on the Shot page's Strike panel. Unknown impact still shows no marker.
"""

from __future__ import annotations

import club_redesign_v1 as v1
import club_redesign_v2 as v2
import club_redesign_v3 as v3
import overview_redesign_v12 as shot_v12
import overview_redesign_v14 as shot_v14
import shanktuary_performance_studio as studio


def draw_top_metric_toolbar(app, *args, **kwargs):
    return v3.draw_top_metric_toolbar(app, *args, **kwargs)


def _redraw_impact_face(app, *args, **kwargs):
    """Replace only the Q4 face graphic/marker; leave all labels untouched."""
    avail_w = args[0] if len(args) > 0 else kwargs.get("avail_w", 0)
    h = args[1] if len(args) > 1 else kwargs.get("h", 0)
    offset_x = kwargs.get("offset_x", 0)
    top_bar_h = kwargs.get("top_bar_h", 108)

    # Mirror the production/v3 optional positional order.
    if len(args) >= 20:
        offset_x = args[19]
    if len(args) >= 21:
        top_bar_h = args[20]

    avail_h = h - top_bar_h - 10
    quad_w = avail_w // 2
    quad_h = avail_h // 2
    mid_x = offset_x + quad_w
    mid_y = top_bar_h + quad_h
    scale = max(0.85, min(2.5, min(quad_w / 380.0, quad_h / 230.0)))

    q4_cx = mid_x + quad_w / 2
    q4_cy = mid_y + quad_h / 2
    face_h = int(126 * scale)
    face_cx = q4_cx + int(32 * scale)
    face_cy = q4_cy + int(2 * scale)

    state, _hx, _vy = v1._impact_state(app)
    mirror = bool(getattr(app, "is_left_handed", False))
    face_img = app.get_scaled_club_asset(studio.FACE_PATH, face_h, mirror=mirror)

    # Cover the old Q4 clubface + dashed/legacy marker precisely enough to avoid
    # disturbing the Vertical/Horizontal copy on the left side of the quadrant.
    if face_img:
        try:
            fw, fh = face_img.width(), face_img.height()
        except Exception:
            fw, fh = int(face_h * 2.25), face_h
    else:
        fw, fh = int(face_h * 2.25), face_h

    pad = max(8, int(12 * scale))
    app.canvas.create_rectangle(
        face_cx - fw / 2 - pad,
        face_cy - fh / 2 - pad,
        face_cx + fw / 2 + pad,
        face_cy + fh / 2 + pad,
        fill=v2.CLUB_BG,
        outline="",
    )

    with v2._club_theme(accent_text=v2.TEAL_TEXT):
        if state == "unknown":
            if face_img:
                app.canvas.create_image(face_cx, face_cy, image=face_img, anchor="c")
        else:
            # Ensure the shared Shot helper is using the accepted gold/teal
            # constants, then reuse it directly so both pages stay identical.
            shot_v14._apply_palette()
            shot_v12._draw_face_with_dynamic_marker(app, face_cx, face_cy, face_h)


def draw_4_quadrant_studio(app, production_draw, *args, **kwargs):
    result = v3.draw_4_quadrant_studio(app, production_draw, *args, **kwargs)
    _redraw_impact_face(app, *args, **kwargs)
    return result
