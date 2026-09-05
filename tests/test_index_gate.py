"""The shared validity gate — one rule set every attribute reads.

Per plan §4: if each attribute filtered its own shots the rules would drift and
two numbers on the same card would silently describe different shot sets.
"""
import pytest

from src.analytics.index import (
    MIN_SHOTS_ESTABLISHED,
    MIN_SHOTS_PROVISIONAL,
    PARTIAL_SWING_RATIO,
    ConfidenceTier,
    club_confidence,
    valid_shots,
)


def shot(ball_speed=100.0, spin=5000.0, club="7 Iron", excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "open_golf_coach": {"us_customary_units": {"ball_speed_mph": ball_speed}},
    }


# --- rejection rules ------------------------------------------------------

def test_a_putter_is_never_scored():
    """Nova cannot measure a putt; the stored 'Putter' shots are full swings
    from a mis-set dropdown, which is worse than no data."""
    assert valid_shots([shot(club="Putter")] * 20) == []


def test_an_excluded_shot_is_dropped():
    assert valid_shots([shot(excluded=True)] * 20) == []


def test_negative_spin_is_rejected_as_a_bad_read():
    """3 of 30 real shots carry negative total spin -- physically impossible."""
    assert valid_shots([shot(spin=-471.0)] * 20) == []


def test_zero_spin_is_rejected():
    assert valid_shots([shot(spin=0.0)] * 20) == []


def test_a_missing_ball_speed_is_rejected():
    bad = {"club": "7 Iron", "total_spin_rpm": 5000, "open_golf_coach": {}}
    assert valid_shots([bad] * 20) == []


# --- the partial-swing filter --------------------------------------------

def test_a_chip_is_filtered_out_relative_to_the_club_median():
    """A half-speed swing with the same club is a chip, not a bad full swing."""
    shots = [shot(ball_speed=100.0) for _ in range(19)] + [shot(ball_speed=40.0)]
    out = valid_shots(shots)
    assert len(out) == 19
    assert all(s["open_golf_coach"]["us_customary_units"]["ball_speed_mph"] > 50
               for s in out)


def test_the_filter_is_median_relative_not_absolute():
    """A 60 mph senior must not have their whole bag filtered away."""
    slow = [shot(ball_speed=60.0) for _ in range(20)]
    assert len(valid_shots(slow)) == 20


def test_a_shot_just_above_the_ratio_survives():
    shots = [shot(ball_speed=100.0) for _ in range(19)]
    shots.append(shot(ball_speed=100.0 * PARTIAL_SWING_RATIO + 0.5))
    assert len(valid_shots(shots)) == 20


def test_the_partial_filter_is_dormant_below_ten_shots():
    """With few shots the median is not yet trustworthy, so filtering on it
    would throw away the little data there is."""
    shots = [shot(ball_speed=100.0) for _ in range(8)] + [shot(ball_speed=40.0)]
    assert len(valid_shots(shots)) == 9


def test_the_median_ignores_already_rejected_shots():
    """A cluster of bad-read shots must not drag the median down and take
    good full swings with it."""
    shots = [shot(ball_speed=100.0) for _ in range(12)]
    shots += [shot(ball_speed=20.0, spin=-500.0) for _ in range(8)]
    assert len(valid_shots(shots)) == 12


# --- confidence tiers -----------------------------------------------------

def test_too_few_shots_is_unrated():
    assert club_confidence(14) is ConfidenceTier.UNRATED


def test_fifteen_shots_is_provisional():
    assert club_confidence(MIN_SHOTS_PROVISIONAL) is ConfidenceTier.PROVISIONAL


def test_thirty_shots_is_established():
    assert club_confidence(MIN_SHOTS_ESTABLISHED) is ConfidenceTier.ESTABLISHED


def test_the_tiers_are_ordered_so_they_can_be_compared():
    assert (ConfidenceTier.UNRATED
            < ConfidenceTier.PROVISIONAL
            < ConfidenceTier.ESTABLISHED)


# --- behaviour on the real session file ----------------------------------

def test_the_gate_on_the_real_session_history():
    """Documents the gate behavior on a stable committed fixture."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "fixtures" / "index_gate_session.json"
    shots = json.loads(path.read_text())["shots"]

    seven_iron = [s for s in shots if s.get("club") == "7 Iron"]
    assert len(seven_iron) == 13

    kept = valid_shots(seven_iron)

    # Three malformed-spin shots are rejected.
    assert len(kept) < len(seven_iron)
    assert all(s["total_spin_rpm"] > 0 for s in kept)

    # Putter shots are full swings from a mis-set dropdown -- all dropped.
    assert valid_shots([s for s in shots if s.get("club") == "Putter"]) == []

    # The fixture is intentionally below the established-rating threshold.
    assert club_confidence(len(kept)) is not ConfidenceTier.ESTABLISHED


@pytest.mark.parametrize("n,expected", [
    (0, ConfidenceTier.UNRATED),
    (14, ConfidenceTier.UNRATED),
    (15, ConfidenceTier.PROVISIONAL),
    (29, ConfidenceTier.PROVISIONAL),
    (30, ConfidenceTier.ESTABLISHED),
    (500, ConfidenceTier.ESTABLISHED),
])
def test_the_tier_boundaries(n, expected):
    assert club_confidence(n) is expected
