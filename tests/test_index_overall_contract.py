"""Contract tests for the overall player Shanktuary Index (plan §4a/§5).

These pin the *shape* and coverage-gate boundary behavior of
`player_shanktuary_index()` / `evaluate_coverage()` as a black box -- they
do not exercise or modify the coverage-gate math itself (owned by @agy's
slice). Ball speeds are kept close together across clubs so the shared
partial-swing gate (still being reworked in `valid_shots()`) never enters
into it; carry distances are set explicitly and far enough apart to drive
band/spread behavior independent of that gate.
"""
import json

import pytest

from src.analytics.index import (
    MIN_SHOTS_ESTABLISHED,
    MIN_SHOTS_PROVISIONAL,
    ConfidenceTier,
    IndexTier,
    evaluate_coverage,
    player_shanktuary_index,
)


def shot(bs, carry, vla=15.0, spin=6000.0, axis=0.0, club="7 Iron"):
    return {
        "club": club,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "spin_axis_degrees": axis,
        "open_golf_coach": {
            "us_customary_units": {
                "ball_speed_mph": bs,
                "carry_distance_yards": carry,
            }
        },
    }


def _club(bs, carry, club, count):
    return [shot(bs=bs, carry=carry, club=club) for _ in range(count)]


# Three clubs, comfortably established, carries spread across bands A/C/D
# (ratio 250/100 = 2.5 >= the 1.25 spread rule).
THREE_ESTABLISHED = (
    _club(bs=110.0, carry=250.0, club="Driver", count=MIN_SHOTS_ESTABLISHED + 5)
    + _club(bs=95.0, carry=150.0, club="7 Iron", count=MIN_SHOTS_ESTABLISHED + 5)
    + _club(bs=90.0, carry=100.0, club="PW", count=MIN_SHOTS_ESTABLISHED + 5)
)


# --- exactly 3 established clubs: the eligibility floor ------------------

def test_three_established_clubs_are_eligible_for_the_index_tier():
    result = player_shanktuary_index(THREE_ESTABLISHED)

    assert result["status"] == "available"
    assert result["tier"] == IndexTier.INDEX
    assert len(result["established_clubs"]) == 3
    assert set(result["established_clubs"]) == {"Driver", "7 Iron", "PW"}
    assert result["score"] is not None
    assert 0.0 <= result["score"] <= 99.0


def test_coverage_gate_is_exactly_met_at_three_established_clubs():
    cov = evaluate_coverage(THREE_ESTABLISHED)
    assert cov["eligible"] is True
    assert len(cov["established_clubs"]) == 3
    assert cov["reason"] is None


# --- exactly 2 established clubs: below the floor -------------------------

def test_two_established_clubs_is_insufficient_coverage():
    shots = (
        _club(bs=110.0, carry=250.0, club="Driver", count=MIN_SHOTS_ESTABLISHED + 5)
        + _club(bs=95.0, carry=150.0, club="7 Iron", count=MIN_SHOTS_ESTABLISHED + 5)
    )
    result = player_shanktuary_index(shots)

    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None
    assert result["tier"] is None
    assert result["reason"] is not None
    assert len(result["established_clubs"]) == 2


def test_coverage_gate_rejects_exactly_two_established_clubs():
    shots = (
        _club(bs=110.0, carry=250.0, club="Driver", count=MIN_SHOTS_ESTABLISHED + 5)
        + _club(bs=95.0, carry=150.0, club="7 Iron", count=MIN_SHOTS_ESTABLISHED + 5)
    )
    cov = evaluate_coverage(shots)
    assert cov["eligible"] is False
    assert "3" in cov["reason"]  # names the floor it failed


# --- unestablished clubs are excluded from the score -----------------------

def test_unestablished_club_is_excluded_from_established_clubs_and_score():
    unestablished_count = MIN_SHOTS_PROVISIONAL - 1  # below PROVISIONAL, so UNRATED
    shots = THREE_ESTABLISHED + _club(
        bs=100.0, carry=200.0, club="GW", count=unestablished_count
    )
    result = player_shanktuary_index(shots)

    assert "GW" not in result["established_clubs"]
    assert result["status"] == "available"
    # GW still shows up in the full per-club card, just not in the score
    assert "GW" in result["clubs"]
    assert result["clubs"]["GW"]["efficiency"]["confidence"] != ConfidenceTier.ESTABLISHED
    for area in result["game_areas"].values():
        assert "GW" not in area["clubs"]


def test_unestablished_club_does_not_shift_the_score():
    baseline = player_shanktuary_index(THREE_ESTABLISHED)["score"]
    shots = THREE_ESTABLISHED + _club(
        bs=40.0, carry=20.0, club="GW", count=MIN_SHOTS_PROVISIONAL - 1
    )
    with_extra = player_shanktuary_index(shots)["score"]
    assert with_extra == baseline


# --- JSON serialization of the proposed result shape -----------------------

def test_available_result_round_trips_through_json():
    result = player_shanktuary_index(THREE_ESTABLISHED)
    encoded = json.dumps(result)
    decoded = json.loads(encoded)

    assert decoded["status"] == "available"
    assert decoded["tier"] == "Index"  # str enum serializes to its plain value
    assert decoded["score"] == result["score"]
    assert decoded["established_clubs"] == result["established_clubs"]


def test_insufficient_coverage_result_round_trips_through_json():
    shots = _club(bs=110.0, carry=250.0, club="Driver", count=MIN_SHOTS_ESTABLISHED + 5)
    result = player_shanktuary_index(shots)
    encoded = json.dumps(result)
    decoded = json.loads(encoded)

    assert decoded["status"] == "insufficient_coverage"
    assert decoded["tier"] is None
    assert decoded["score"] is None
    assert isinstance(decoded["reason"], str)


def test_empty_history_result_is_json_safe():
    result = player_shanktuary_index([])
    assert json.loads(json.dumps(result))["status"] == "insufficient_coverage"
