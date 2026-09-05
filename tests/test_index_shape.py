"""Shape (Index Attribute #3) tests.

Plan §9a "Shape -- the plateau curve" table, verbatim (bias deg / spread deg
/ base / penalty / score / read):

    bias  spread   base    pen  score   read
        0     3.5   90.0    0.0   90.0   dead straight, tight
        6     3.5   90.0    0.0   90.0   committed fade      <- same as straight
        8     3.5   90.0    0.0   90.0   strong fade
       12     3.5   90.0    8.8   81.2   big cut
       20     3.5   90.0   26.4   63.6   slice, but repeatable
        0    12.0   21.1    0.0   21.1   two-way miss        <- worst outcome
       -7     4.0   85.0    0.0   85.0   draw player
       25     2.4   99.0   30.0   69.0   severe slice, very repeatable

The parametrized cases below pin the PROVISIONAL formula's output (see
shape_ratio's docstring): six rows match the table exactly; the last two
deviate by +1.0 and -1.1 respectively (table values 69.0 / 21.1).
"""

import pytest

from src.analytics.index import ConfidenceTier, shape_by_club, shape_ratio


def shot(axis, club="7 Iron", speed=95.0, excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "spin_axis_degrees": axis,
        "total_spin_rpm": 7000.0,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": speed}
        },
    }


@pytest.mark.parametrize(
    ("bias", "spread", "expected_score"),
    [
        (0.0, 3.5, 90.0),
        (6.0, 3.5, 90.0),
        (8.0, 3.5, 90.0),
        (12.0, 3.5, 81.2),
        (20.0, 3.5, 63.6),
        (-7.0, 4.0, 85.0),
        (0.0, 12.0, 20.0),
        (25.0, 2.4, 70.0),
    ],
)
def test_shape_ratio_follows_provisional_spread_curve(
    bias, spread, expected_score
):
    values = [bias - spread / 2**0.5, bias + spread / 2**0.5]
    assert shape_ratio(values) == pytest.approx(expected_score / 100.0)


def test_shape_ratio_handles_zero_spread_as_perfect_repeatability():
    assert shape_ratio([10.0, 10.0]) == pytest.approx(0.956)


def test_two_shots_are_required_for_shape_spread():
    assert shape_ratio([6.0]) is None


def test_two_way_miss_scores_worse_than_repeatable_shapes():
    assert shape_ratio([-12.0, 12.0]) < shape_ratio([18.0, 22.0])


def test_left_handed_shape_flips_signed_bias():
    right_handed = shape_ratio([10.0, 14.0])
    left_handed = shape_ratio([-10.0, -14.0], is_left_handed=True)
    assert left_handed == pytest.approx(right_handed)


def test_shape_aggregate_uses_gate_and_skips_missing_axis():
    result = shape_by_club([
        shot(3.0),
        shot(5.0),
        shot(7.0, excluded=True),
        {**shot(9.0), "spin_axis_degrees": None},
    ])
    assert result["7 Iron"]["count"] == 2
    assert result["7 Iron"]["confidence"] is ConfidenceTier.UNRATED


def test_shape_aggregate_resolves_left_handed_sign():
    result = shape_by_club(
        [shot(-10.0), shot(-14.0)],
        is_left_handed=True,
    )
    assert result["7 Iron"]["score"] == pytest.approx(shape_ratio([10.0, 14.0]))
