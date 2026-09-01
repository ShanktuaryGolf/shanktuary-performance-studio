"""Club strike-marker alignment pass.

Keeps the accepted v3 Club layout and credibility states, but redraws the
Impact Location clubface with the exact same lens/ring/dot marker treatment used
on the Shot page's Strike panel. Unknown impact still shows no marker.
"""

from __future__ import annotations

from contextlib import contextmanager

import club_redesign_v1 as v1
import club_redesign_v2 as v2
import club_redesign_v3 as v3
import overview_redesign_v12 as shot_v12
import overview_redesign_v14 as shot_v14

import shanktuary_performance_studio as studio


def draw_top_metric_toolbar(app, *args, **kwargs):
    return v3.draw_top_metric_toolbar(app, *args, **kwargs)


@contextmanager
def _without_production_clubface(app):
    """Stop production drawing its Q4 clubface for one render.

    The redesign previously painted an opaque rectangle over production's face
    and drew its own on top. That cover could never be right: sized to hide the
    whole face it erased the panel header and the "Nova measures ball flight"
    disclaimer, and trimmed to spare them it left a sliver of the old clubhead
    showing. Suppressing the asset is exact -- there is nothing to cover.
    """
    original = app.get_scaled_club_asset

    def guarded(path, size, *a, **kw):
        if path == studio.FACE_PATH:
            return None
        return original(path, size, *a, **kw)

    app.get_scaled_club_asset = guarded
    try:
        yield
    finally:
        app.get_scaled_club_asset = original


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

    q4_cy = mid_y + quad_h / 2

    state, _hx, _vy = v1._impact_state(app)
    mirror = bool(getattr(app, "is_left_handed", False))

    # Budget BOTH axes. Horizontally the face must clear the readout column;
    # vertically it must sit between the readouts and the footer disclaimer,
    # which spans the full quadrant width. Production sizes from quadrant
    # height alone, which is why the graphic clipped "FLUSH (EST)" and sat on
    # top of the "Nova measures ball flight" line.
    readout_right = mid_x + int(quad_w * 0.42)
    gutter = max(12, int(10 * scale))
    quad_right = offset_x + 2 * quad_w
    max_face_w = max(120, quad_right - readout_right - gutter * 2)
    # Footer sits ~55px above the quadrant bottom; keep clear of it.
    footer_top = mid_y + quad_h - int(58 * scale / 1.7)
    max_face_h = max(70, footer_top - (mid_y + int(24 * scale)) - gutter)

    face_h = int(126 * scale)
    face_img = app.get_scaled_club_asset(studio.FACE_PATH, face_h, mirror=mirror)
    if face_img:
        try:
            shrink = min(
                1.0,
                max_face_w / max(1, face_img.width()),
                max_face_h / max(1, face_img.height()),
            )
            if shrink < 1.0:
                face_h = max(70, int(face_h * shrink))
                face_img = app.get_scaled_club_asset(
                    studio.FACE_PATH, face_h, mirror=mirror
                )
        except Exception:
            pass

    if face_img:
        try:
            fw = face_img.width()
        except Exception:
            fw = int(face_h * 2.25)
    else:
        fw = int(face_h * 2.25)

    # Centre the face in the space right of the readout column, then clamp so
    # it cannot spill past the quadrant's right edge.
    face_cx = readout_right + gutter + fw / 2
    face_cx = min(face_cx, quad_right - gutter - fw / 2)
    face_cy = q4_cy + int(2 * scale)

    # No cover rectangle. The redesign used to hide production's face behind an
    # opaque rect and draw over it, which could never be sized correctly: big
    # enough to hide the face, it erased the panel header and the "Nova
    # measures ball flight, not face contact" disclaimer; trimmed to spare
    # them, it left a sliver of the old clubhead showing. Production's face
    # asset is suppressed for this render instead -- see
    # _without_production_clubface -- so there is nothing to cover.

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
    with _without_production_clubface(app):
        result = v3.draw_4_quadrant_studio(app, production_draw, *args, **kwargs)
    _redraw_impact_face(app, *args, **kwargs)
    return result
