import pytest

from src.analytics.index import (
    ConfidenceTier,
    spin_control_by_club,
    spin_control_ratio,
)
from src.analytics.spin_benchmarks import TOUR_SPIN_CV_BY_CLUB


def shot(spin, club="7 Iron", speed=95.0, excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": speed}
        },
    }


def test_tour_level_cv_scores_one():
    target = TOUR_SPIN_CV_BY_CLUB["7 Iron"]
    spins = [7000.0, 7000.0 * (1 + target)]
    assert spin_control_ratio(spins, "7 Iron") == pytest.approx(1.0)


def test_looser_spin_variation_scores_below_one():
    target = TOUR_SPIN_CV_BY_CLUB["7 Iron"]
    delta = target * 2 / (2 ** 0.5)
    spins = [7000.0 * (1 - delta), 7000.0 * (1 + delta)]
    assert spin_control_ratio(spins, "7 Iron") == pytest.approx(0.5)


def test_unbenchmarked_club_is_unrated():
    assert spin_control_ratio([5000.0, 5200.0], "GW") is None


def test_two_shots_are_enough_and_zero_cv_is_perfect():
    assert spin_control_ratio([7000.0], "7 Iron") is None
    assert spin_control_ratio([7000.0, 7000.0], "7 Iron") == 1.0


def test_gate_excluded_shot_does_not_enter_spin_aggregate():
    result = spin_control_by_club([
        shot(7000.0),
        shot(7000.0),
        shot(7000.0, excluded=True),
    ])
    assert result["7 Iron"]["count"] == 2
    assert result["7 Iron"]["confidence"] is ConfidenceTier.UNRATED


def test_unbenchmarked_club_is_omitted_from_aggregate():
    result = spin_control_by_club([
        shot(5000.0, club="GW"),
        shot(5200.0, club="GW"),
    ])
    assert "GW" not in result
