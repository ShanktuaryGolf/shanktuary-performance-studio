"""Approximate strike, honestly: the golfer's own marks are the only source.

With no marks the estimate is the sweet spot with a wide, unlabelled-as-
measured ring. With marks it is the median mark and its spread. A per-shot
model (ball flight -> mark) is used ONLY when it beats the plain median on
held-out marks for that club -- and the label says which one you got.
"""
import itertools

import pytest

from src.analytics import strike_estimate as se

_ids = itertools.count(1_000)   # id(object()) recycles addresses -> shots collide


def _shot(club="7 Iron", h=None, v=None, launch=18.0, spin=6000.0, axis=0.0, bs=40.0, ts=None):
    s = {"club": club, "timestamp_ns": ts if ts is not None else next(_ids),
         "vertical_launch_angle_degrees": launch, "total_spin_rpm": spin,
         "spin_axis_degrees": axis, "ball_speed_meters_per_second": bs,
         "open_golf_coach": {"us_customary_units": {"ball_speed_mph": bs / 0.44704}}}
    if h is not None:
        s["marked_contact"] = {"horizontal_mm": h, "vertical_mm": v, "source": "user"}
    return s


def test_no_marks_gives_a_wide_ring_at_the_sweet_spot_labelled_as_such():
    e = se.estimate(_shot(), [])
    assert e.horizontal_mm == 0.0 and e.vertical_mm == 0.0
    assert e.basis == "none" and e.marks == 0
    assert e.radius_mm >= se.MIN_RADIUS_MM
    assert "no marks" in e.label.lower()


def test_marks_from_other_clubs_do_not_count():
    hist = [_shot("PW", h=-8, v=2) for _ in range(5)]
    e = se.estimate(_shot("7 Iron"), hist)
    assert e.basis == "none" and e.marks == 0


def test_median_of_own_marks_with_spread_as_radius():
    hist = [_shot(h=-6, v=2), _shot(h=-4, v=3), _shot(h=-10, v=1), _shot(h=-5, v=2.5)]
    e = se.estimate(_shot(), hist)
    assert e.basis == "median" and e.marks == 4
    assert e.horizontal_mm == pytest.approx(-5.5, abs=0.06) and e.vertical_mm == pytest.approx(2.25, abs=0.06)
    # Radius reflects the scatter of the marks, floored so a tight cluster
    # never collapses into a "measured" looking dot.
    assert se.MIN_RADIUS_MM <= e.radius_mm < 12
    assert "4 marks" in e.label


def test_the_shot_being_estimated_never_trains_itself():
    target = _shot(h=-20, v=-10, ts=1)
    hist = [target] + [_shot(h=-2, v=1, ts=i + 10) for i in range(3)]
    e = se.estimate(target, hist)
    assert e.marks == 3 and e.horizontal_mm == pytest.approx(-2)


def test_one_mark_is_still_a_median_with_the_floor_radius():
    e = se.estimate(_shot(), [_shot(h=3, v=-1)])
    assert e.basis == "median" and e.marks == 1 and e.radius_mm == se.MIN_RADIUS_MM


def test_model_is_not_used_below_the_mark_floor_even_if_flight_is_perfectly_predictive():
    # Marks track launch exactly, but only 10 of them: still the median.
    hist = [_shot(h=(i - 5) * 2.0, v=0, launch=15 + i) for i in range(10)]
    e = se.estimate(_shot(launch=25), hist)
    assert e.basis == "median"


def test_model_is_promoted_only_when_it_beats_the_median_on_held_out_marks():
    # 24 marks whose heel/toe position follows spin axis: a model should win.
    hist = [_shot(h=(i % 12 - 6) * 1.5, v=(i % 4 - 2) * 1.0, axis=(i % 12 - 6) * 2.0,
                  launch=16 + (i % 4)) for i in range(24)]
    e = se.estimate(_shot(axis=8.0, launch=18), hist)
    assert e.basis == "model" and e.marks == 24
    assert e.horizontal_mm > 2.0            # positive axis -> heel side in this fixture
    assert "model" in e.label.lower()
    # Same count of marks but random with respect to flight: the median stays.
    import random
    rng = random.Random(3)
    noise = [_shot(h=rng.uniform(-10, 10), v=rng.uniform(-6, 6),
                   axis=rng.uniform(-10, 10), launch=rng.uniform(12, 24)) for _ in range(24)]
    e2 = se.estimate(_shot(axis=8.0, launch=18), noise)
    assert e2.basis == "median"


def test_estimate_is_clamped_to_the_drawable_face():
    hist = [_shot(h=23, v=15) for _ in range(3)]
    e = se.estimate(_shot(), hist)
    assert abs(e.horizontal_mm) <= se.FACE_MAX_H_MM and abs(e.vertical_mm) <= se.FACE_MAX_V_MM
