import pytest

from src.analytics.index import ConfidenceTier, consistency_by_club


def shot(speed, vla, spin, carry, club="7 Iron", excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "open_golf_coach": {
            "us_customary_units": {
                "ball_speed_mph": speed,
                "carry_distance_yards": carry,
            }
        },
    }


def test_small_samples_report_raw_sample_carry_cv():
    result = consistency_by_club([
        shot(90.0, 18.0, 5000.0, 100.0),
        shot(90.0, 18.0, 5000.0, 110.0),
    ])
    assert result["7 Iron"]["cv"] == pytest.approx((50.0**0.5) / 105.0)
    assert result["7 Iron"]["form"] == "RAW"
    assert result["7 Iron"]["count"] == 2
    assert result["7 Iron"]["confidence"] is ConfidenceTier.UNRATED


def test_forty_shots_switch_to_dof_corrected_residual_std():
    shots = []
    for index in range(40):
        speed = 100.0 + index
        vla = 12.0 + (index % 7) / 10.0
        spin = 4000.0 + ((index * 11) % 40) * 100.0
        expected = 50.0 + 0.5 * speed + 2.0 * vla + 0.01 * spin
        shots.append(shot(speed, vla, spin, expected + (1.0 if index % 2 else -1.0)))

    result = consistency_by_club(shots)
    assert result["7 Iron"]["cv"] == pytest.approx(
        ((40.0 / 36.0) ** 0.5) / (50.0 + 0.5 * 119.5 + 2.0 * 12.3 + 0.01 * 5950),
        abs=0.0001,
    )
    assert result["7 Iron"]["form"] == "RESIDUAL"
    assert result["7 Iron"]["count"] == 40
    assert result["7 Iron"]["confidence"] is ConfidenceTier.ESTABLISHED


def test_thirty_nine_shots_remain_raw():
    shots = [shot(100.0 + index, 12.0, 4000.0, 150.0) for index in range(39)]
    assert consistency_by_club(shots)["7 Iron"]["form"] == "RAW"


def test_gate_excluded_shots_do_not_enter_consistency():
    result = consistency_by_club([
        shot(90.0, 18.0, 5000.0, 100.0),
        shot(90.0, 18.0, 5000.0, 110.0, excluded=True),
    ])
    assert "7 Iron" not in result


def test_missing_carry_or_predictor_is_skipped():
    result = consistency_by_club([
        shot(90.0, 18.0, 5000.0, 100.0),
        {**shot(90.0, 18.0, 5000.0, 110.0), "vertical_launch_angle_degrees": None},
    ])
    assert "7 Iron" not in result


def test_zero_mean_carry_is_unrated():
    result = consistency_by_club([
        shot(90.0, 18.0, 5000.0, 0.0),
        shot(90.0, 18.0, 5000.0, 0.0),
    ])
    assert "7 Iron" not in result
