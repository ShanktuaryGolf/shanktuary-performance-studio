"""Quad-view layout: masks and chips must be sized to their content.

Three reported clipping bugs, all the same root cause — a hardcoded pixel
size that no longer matched the text it was meant to hold:

1. Sidebar shot-card values ("06:24 PM") sat 24px from the card edge and
   read as clipped against the border.
2. The Q2 cleanup mask was a fixed 175x77 block, far wider and taller than
   the "DYNAMIC LOFT"/"ATTACK ANGLE" labels it clears. It reached into the
   bottom-left quadrant and erased the top of the ball-flight arc, so the
   trajectory looked cut off mid-curve.
3. The "DIRECTION ESTIMATE" chip reserved 116*fs (~214px) for ~258px of
   text, so the centred label spilled ~22px past each end of its own badge
   — colliding with "IMPACT LOCATION" and hanging outside the box.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(params=[None, {"lateral_offset_mm": -6.0, "vertical_offset_mm": 3.5}],
                ids=["unavailable", "reported"])
def quad(tmp_path, monkeypatch, request):
    """Both credibility states use the same deterministic native-style shot."""
    from test_quad_impact_panel import _quad_app

    root, app = _quad_app(tmp_path, monkeypatch, "1915x1111", request.param)
    try:
        yield root, app
    finally:
        root.destroy()


def test_impact_caption_and_credibility_badge_do_not_touch(quad):
    from test_quad_impact_panel import _overlap, _tag_box
    _root, app = quad
    assert not _overlap(_tag_box(app, "contact-heading"), _tag_box(app, "contact-credibility"))


def test_the_credibility_badge_fits_inside_the_panel(quad):
    from test_quad_impact_panel import _tag_box
    _root, app = quad
    c = app.canvas
    badge = _tag_box(app, "contact-credibility")
    assert badge[0] > 260
    assert badge[2] <= c.winfo_width() - 16
    expected = "REPORTED" if "face_impact" in app.current_shot else "No face-contact measurement"
    assert c.itemcget(c.find_withtag("contact-credibility")[0], "text") == expected


def _polyline_intersects_rect(coords, rect, stroke_width=0):
    """Check painted segments, not the empty corners of the arc's bbox."""
    pad = stroke_width / 2
    left, top, right, bottom = rect
    bounds = ((left - pad, right + pad), (top - pad, bottom + pad))
    points = list(zip(coords[::2], coords[1::2]))
    for start, end in zip(points, points[1:]):
        lo, hi = 0.0, 1.0
        for origin, target, (minimum, maximum) in zip(start, end, bounds):
            delta = target - origin
            if delta == 0:
                if not minimum <= origin <= maximum:
                    break
                continue
            enter, leave = sorted(((minimum - origin) / delta,
                                   (maximum - origin) / delta))
            lo, hi = max(lo, enter), min(hi, leave)
            if lo > hi:
                break
        else:
            return True
    return False


def test_arc_intersection_ignores_empty_bbox_corners():
    arc = [0, 10, 5, 0, 10, 10]
    assert not _polyline_intersects_rect(arc, (8, 0, 10, 2))
    assert _polyline_intersects_rect(arc, (4, 0, 6, 2))
    assert _polyline_intersects_rect([0, 0, 10, 0], (4, 1, 6, 2), 3)


def test_q2_mask_does_not_erase_the_trajectory_arc(quad):
    """The ball-flight arc must not be painted over after it is drawn."""
    _root, app = quad
    c = app.canvas
    order = list(c.find_all())

    # Club no longer includes a ball-flight panel; it belongs to Shot.
    app.set_mode(9)
    c = app.canvas
    order = list(c.find_all())
    trajectories = c.find_withtag("flight-trajectory")
    assert len(trajectories) == 1, "fixture must render a real derived trajectory"
    traj = trajectories[0]

    tb = c.bbox(traj)
    trajectory = c.coords(traj)
    stroke_width = float(c.itemcget(traj, "width"))
    idx = order.index(traj)
    covering = []
    for item in order[idx + 1:]:
        if c.type(item) != "rectangle":
            continue
        bb = c.bbox(item)
        if not bb:
            continue
        if c.itemcget(item, "fill") and _polyline_intersects_rect(trajectory, bb, stroke_width):
            covering.append((bb, c.itemcget(item, "fill")))

    assert not covering, (
        f"rectangles painted over the trajectory arc {tb}: {covering}"
    )


def test_selected_card_is_tall_enough_for_its_last_row(quad):
    _root, app = quad
    app.set_mode(9)  # Recent Shots now lives only in Shot, not a second global rail.
    c = app.canvas
    card = next(r for r in app.design_shot_card_rects if r[4] == app.selected_shot_index)
    items = []
    for item in c.find_all():
        if c.type(item) != "text": continue
        b = c.bbox(item)
        if card[0] <= (b[0]+b[2])/2 <= card[2] and card[1] <= (b[1]+b[3])/2 <= card[3]:
            items.append(item)
            assert b[1] >= card[1] and b[3] <= card[3], c.itemcget(item, "text")
    assert items, "selected card has no text"


def test_only_one_recent_card_per_shot_is_registered(quad):
    _root, app = quad
    app.set_mode(9)
    indices = [r[4] for r in app.design_shot_card_rects]
    assert indices and len(indices) == len(set(indices))


def test_shot_card_values_clear_the_card_edge(quad):
    _root, app = quad
    app.set_mode(9)
    c = app.canvas
    card = next(r for r in app.design_shot_card_rects if r[4] == app.selected_shot_index)
    values = []
    for item in c.find_all():
        if c.type(item) != "text" or not c.itemcget(item,"text").endswith("yd"): continue
        b = c.bbox(item)
        if card[0] <= b[0] and card[1] <= (b[1]+b[3])/2 <= card[3] and b[2] <= card[2]:
            values.append(b)
            assert b[2] <= card[2] - 24, "carry text collides with selected-shot delete action"
    assert values, "selected card must render its carry value"
