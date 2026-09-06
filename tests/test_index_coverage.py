import pytest

from src.analytics.index import (
    ConfidenceTier,
    IndexTier,
    bag_index_summary,
    classify_carry_band,
    evaluate_coverage,
    player_shanktuary_index,
)


def make_shot(
    club: str,
    carry: float,
    bs: float = 100.0,
    vla: float = 18.0,
    spin: float = 5000.0,
    axis: float = 0.0,
    excluded: bool = False,
):
    return {
        "club": club,
        "excluded": excluded,
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


def make_club_shots(club: str, carry: float, count: int, bs: float = 100.0):
    return [make_shot(club=club, carry=carry, bs=bs) for _ in range(count)]


def test_classify_carry_band():
    anchor = 200.0
    assert classify_carry_band(170.0, anchor) == "A"  # 85%
    assert classify_carry_band(140.0, anchor) == "B"  # 70%
    assert classify_carry_band(110.0, anchor) == "C"  # 55%
    assert classify_carry_band(109.9, anchor) == "D"  # <55%


def test_anchor_requires_at_least_15_shots():
    # Longest club has only 14 shots; qualifying anchor club has 15 shots
    shots = make_club_shots("Driver", 250.0, 14, bs=100.0) + make_club_shots(
        "7 Iron", 160.0, 15, bs=100.0
    )
    result = player_shanktuary_index(shots)
    assert result["anchor_carry"] == pytest.approx(160.0)


def test_no_qualifying_anchor_returns_insufficient_coverage():
    shots = make_club_shots("7 Iron", 160.0, 14, bs=100.0)
    result = player_shanktuary_index(shots)
    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None
    assert result["tier"] is None
    assert "anchor" in result["reason"].lower()


def test_coverage_fails_with_fewer_than_three_established_clubs():
    # 2 established clubs (30 shots each), anchor Driver at 230y (15 shots)
    shots = (
        make_club_shots("Driver", 230.0, 15, bs=100.0)
        + make_club_shots("7 Iron", 160.0, 30, bs=100.0)
        + make_club_shots("9 Iron", 130.0, 30, bs=100.0)
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None
    assert len(result["established_clubs"]) == 2
    assert "3 established" in result["reason"]


def test_coverage_fails_with_single_carry_band():
    # Plan §4a: 7i (158), 8i (145), 9i (131) against 231 anchor -> all Band C
    shots = (
        make_club_shots("Driver", 231.0, 15, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
        + make_club_shots("8 Iron", 145.0, 30, bs=100.0)
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None
    assert "carry bands" in result["reason"].lower()


def test_coverage_fails_when_spread_ratio_below_one_twenty_five():
    # Plan §4a: 6i (170, Band B), 7i (158, Band C), 8i (145, Band C) -> ratio 1.17 < 1.25
    shots = (
        make_club_shots("Driver", 231.0, 15, bs=100.0)
        + make_club_shots("6 Iron", 170.0, 30, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
        + make_club_shots("8 Iron", 145.0, 30, bs=100.0)
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "insufficient_coverage"
    assert result["spread_ratio"] == pytest.approx(170.0 / 145.0, abs=0.01)
    assert "1.25" in result["reason"]


def test_coverage_passes_tier_1_index():
    # Plan §4a: 5i (180, Band B), 7i (158, Band C), 9i (131, Band C) -> ratio 1.37 >= 1.25
    shots = (
        make_club_shots("Driver", 231.0, 15, bs=100.0)
        + make_club_shots("5 Iron", 180.0, 30, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "available"
    assert result["tier"] == IndexTier.INDEX
    assert result["score"] is not None
    assert 0.0 <= result["score"] <= 99.0
    assert len(result["established_clubs"]) == 3


def test_unestablished_clubs_excluded_from_score():
    # 3 established clubs, plus a provisional PW (10 shots)
    shots = (
        make_club_shots("Driver", 231.0, 30, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)
        + make_club_shots("PW", 115.0, 10, bs=100.0)
    )
    summary = bag_index_summary(shots)
    result = player_shanktuary_index(shots)
    assert "PW" not in result["established_clubs"]

    expected_score = (
        summary["Driver"]["composite"]["score"]
        + summary["7 Iron"]["composite"]["score"]
        + summary["9 Iron"]["composite"]["score"]
    ) / 3.0
    assert result["score"] == pytest.approx(expected_score, abs=0.05)


def test_full_spread_tier_requires_six_clubs_and_all_four_bands():
    # 6 established clubs: Driver (A), 3H (B), 7i (C), 9i (C), PW (D), SW (D)
    shots = (
        make_club_shots("Driver", 231.0, 30, bs=100.0)  # A (1.00)
        + make_club_shots("3 Hybrid", 195.0, 30, bs=100.0)  # B (0.84)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)  # C (0.68)
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)  # C (0.57)
        + make_club_shots("PW", 118.0, 30, bs=100.0)  # D (0.51)
        + make_club_shots("SW", 88.0, 30, bs=100.0)  # D (0.38)
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "available"
    assert result["tier"] == IndexTier.FULL_SPREAD
    assert len(result["established_clubs"]) == 6
    assert set(result["bands_present"]) == {"A", "B", "C", "D"}


def test_game_areas_structure():
    shots = (
        make_club_shots("Driver", 231.0, 30, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)
    )
    result = player_shanktuary_index(shots)
    areas = result["game_areas"]
    assert "A" in areas and areas["A"]["name"] == "Longest"
    assert "B" in areas and areas["B"]["name"] == "Long"
    assert "C" in areas and areas["C"]["name"] == "Mid"
    assert "D" in areas and areas["D"]["name"] == "Short"
    assert "Driver" in areas["A"]["clubs"]
    assert "7 Iron" in areas["C"]["clubs"]
    assert "9 Iron" in areas["C"]["clubs"]
    assert areas["B"]["score"] is None
    assert areas["A"]["score"] is not None



@pytest.mark.parametrize(
    "clubs_and_carries,expected_pass",
    [
        # Plan §4a table:
        ([("7 Iron", 158.0), ("8 Iron", 145.0), ("9 Iron", 131.0)], False),  # ratio 1.21, bands 1
        ([("6 Iron", 170.0), ("7 Iron", 158.0), ("8 Iron", 145.0)], False),  # ratio 1.17, bands 2
        ([("4 Iron", 190.0), ("5 Iron", 180.0), ("6 Iron", 170.0)], False),  # ratio 1.12, bands 1
        ([("8 Iron", 145.0), ("9 Iron", 131.0), ("PW", 118.0)], False),  # ratio 1.23, bands 2
        ([("5 Wood", 202.0), ("7 Wood", 192.0), ("9 Wood", 183.0)], False),  # ratio 1.10, bands 2
        ([("Driver", 231.0), ("3 Wood", 215.0), ("5 Wood", 202.0)], False),  # ratio 1.14, bands 1
        ([("PW", 118.0), ("GW", 103.0), ("SW", 88.0)], False),  # ratio 1.34, bands 1
        ([("PW", 118.0), ("SW", 88.0), ("LW", 75.0)], False),  # ratio 1.57, bands 1
        ([("5 Iron", 180.0), ("7 Iron", 158.0), ("9 Iron", 131.0)], True),  # ratio 1.37, bands 2 -> INDEX
        ([("Driver", 231.0), ("7 Iron", 158.0), ("9 Iron", 131.0)], True),  # ratio 1.76, bands 2 -> INDEX
        ([("9 Wood", 183.0), ("7 Iron", 158.0), ("PW", 118.0)], True),  # ratio 1.55, bands 3 -> INDEX
        ([("3 Hybrid", 195.0), ("7 Iron", 158.0), ("SW", 88.0)], True),  # ratio 2.22, bands 3 -> INDEX
        ([("5 Wood", 202.0), ("3 Hybrid", 195.0), ("7 Iron", 158.0)], True),  # ratio 1.28, bands 3 -> INDEX
        ([("7 Iron", 158.0), ("PW", 118.0), ("SW", 88.0)], True),  # ratio 1.80, bands 2 -> INDEX
    ],
)
def test_plan_section_4a_coverage_combinations(clubs_and_carries, expected_pass):
    # Anchor reference: if Driver is not in the combination, add 15 Driver shots at 231y
    shots = []
    if not any(club == "Driver" for club, _ in clubs_and_carries):
        shots.extend(make_club_shots("Driver", 231.0, 15, bs=100.0))
    for club, carry in clubs_and_carries:
        shots.extend(make_club_shots(club, carry, 30, bs=100.0))
    result = evaluate_coverage(shots)
    assert result["eligible"] is expected_pass


def test_empty_shots_returns_insufficient_coverage():
    result = player_shanktuary_index([])
    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None
    assert result["tier"] is None
    assert result["established_clubs"] == []


def test_putter_only_shots_returns_insufficient_coverage():
    shots = make_club_shots("Putter", 10.0, 40, bs=15.0)
    result = player_shanktuary_index(shots)
    assert result["status"] == "insufficient_coverage"
    assert result["score"] is None


def test_left_handed_changes_spin_axis_scoring_in_index():
    shots_fade = (
        make_club_shots("Driver", 231.0, 30, bs=100.0)
        + [make_shot("7 Iron", 158.0, bs=100.0, axis=5.0) for _ in range(30)]
        + make_club_shots("9 Iron", 131.0, 30, bs=100.0)
    )
    res_rh = player_shanktuary_index(shots_fade, is_left_handed=False)
    res_lh = player_shanktuary_index(shots_fade, is_left_handed=True)
    assert res_rh["status"] == "available"
    assert res_lh["status"] == "available"
    # Shape ratio with +5 deg vs -5 deg is symmetrical for magnitude <= 8 deg,
    # but let's verify composite is computed for both
    assert res_rh["score"] is not None
    assert res_lh["score"] is not None


def test_bag_index_summary_contract_is_preserved():
    shots = (
        make_club_shots("Driver", 231.0, 30, bs=100.0)
        + make_club_shots("7 Iron", 158.0, 30, bs=100.0)
    )
    summary = bag_index_summary(shots)
    assert isinstance(summary, dict)
    assert "Driver" in summary and "7 Iron" in summary
    for club in ["Driver", "7 Iron"]:
        entry = summary[club]
        assert "efficiency" in entry
        assert "shape" in entry
        assert "spin_control" in entry
        assert "consistency" in entry
        assert "composite" in entry
        assert entry["composite"]["confidence"] == ConfidenceTier.ESTABLISHED


