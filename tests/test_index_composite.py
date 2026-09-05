import pytest

from src.analytics.index import ConfidenceTier, bag_index_summary


def shot(bs, vla, spin, axis, club="7 Iron", excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "spin_axis_degrees": axis,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": bs}
        },
    }


IRON_SHOT = dict(bs=90.0, vla=18.0, spin=6500.0, axis=1.0)


def test_composite_weights_efficiency_and_shape_only_for_irons():
    shots = [shot(**IRON_SHOT, club="7 Iron") for _ in range(2)]
    result = bag_index_summary(shots)
    club = result["7 Iron"]

    assert "spin_control" in club  # displayed
    assert "consistency" in club  # displayed
    assert "composite" in club
    from src.analytics.index import efficiency_ratio, shape_ratio

    eff = efficiency_ratio(IRON_SHOT["bs"], IRON_SHOT["vla"], IRON_SHOT["spin"])
    shp = shape_ratio([IRON_SHOT["axis"]] * 2)
    expected = (eff * 20.0 + shp * 10.0) / 30.0 * 99.0
    assert club["composite"]["score"] == pytest.approx(min(99.0, expected), abs=0.01)


def test_composite_uses_woods_weights_for_driver():
    shots = [shot(bs=165.0, vla=11.0, spin=2700.0, axis=0.0, club="Driver") for _ in range(2)]
    result = bag_index_summary(shots)
    from src.analytics.index import efficiency_ratio, shape_ratio

    eff = efficiency_ratio(165.0, 11.0, 2700.0)
    shp = shape_ratio([0.0, 0.0])
    expected = (eff * 30.0 + shp * 15.0) / 45.0 * 99.0
    assert result["Driver"]["composite"]["score"] == pytest.approx(min(99.0, expected), abs=0.01)


def test_composite_score_is_clamped_to_99():
    # Deliberately give a perfect launch and dead-straight shape -- ratios can
    # sit right at or fractionally above 1.0 depending on table interpolation.
    shots = [shot(bs=100.0, vla=31.5, spin=2250.0, axis=0.0, club="7 Iron") for _ in range(2)]
    result = bag_index_summary(shots)
    assert result["7 Iron"]["composite"]["score"] <= 99.0


def test_putter_never_gets_a_composite():
    shots = [shot(**IRON_SHOT, club="Putter") for _ in range(5)]
    result = bag_index_summary(shots)
    assert result == {}


def test_unknown_club_name_has_no_composite():
    shots = [shot(**IRON_SHOT, club="Chipper") for _ in range(5)]
    result = bag_index_summary(shots)
    assert "composite" not in result["Chipper"]


def test_composite_confidence_is_the_weaker_of_the_two_contributing_tiers():
    # 2 shots -> UNRATED for both Efficiency and Shape.
    shots = [shot(**IRON_SHOT, club="7 Iron") for _ in range(2)]
    result = bag_index_summary(shots)
    assert result["7 Iron"]["composite"]["confidence"] is ConfidenceTier.UNRATED


def test_gate_excluded_shots_are_not_scored():
    shots = [shot(**IRON_SHOT, club="7 Iron", excluded=True) for _ in range(5)]
    result = bag_index_summary(shots)
    assert result == {}
