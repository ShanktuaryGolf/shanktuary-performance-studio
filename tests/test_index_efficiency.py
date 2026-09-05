import csv
from pathlib import Path

import pytest

from src.analytics.flight_model import TABLE_PATH
from src.analytics.index import (
    ConfidenceTier,
    efficiency_by_club,
    efficiency_ratio,
)


def shot(ball_speed, vla, spin, club="7 Iron", excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": ball_speed}
        },
    }


def optimum_row(ball_speed):
    with TABLE_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return next(row for row in rows if float(row["ball_speed_mph"]) == ball_speed)


def test_optimal_launch_scores_as_one():
    row = optimum_row(90.0)
    ratio = efficiency_ratio(
        90.0,
        float(row["optimal_vla_deg"]),
        float(row["optimal_spin_rpm"]),
    )
    assert ratio == pytest.approx(1.0, abs=0.002)


def test_poor_launch_scores_below_optimal():
    assert efficiency_ratio(90.0, 5.0, 1000.0) < 0.9


def test_efficiency_ratio_clamps_speed_to_model_table():
    low = efficiency_ratio(10.0, 20.0, 4500.0)
    high = efficiency_ratio(250.0, 20.0, 4500.0)
    assert low > 0.0
    assert high > 0.0


def test_gate_excluded_shot_does_not_enter_club_aggregate():
    shots = [
        shot(90.0, 20.0, 4500.0),
        shot(90.0, 20.0, 4500.0, excluded=True),
    ]
    result = efficiency_by_club(shots)
    assert result["7 Iron"]["count"] == 1
    assert result["7 Iron"]["confidence"] is ConfidenceTier.UNRATED
