"""Flight model — verifies the Python port agrees with the shipped JS engine.

Plan: ~/sps-notes/shanktuary-index-plan-2026-08-30.md §6b. The acceptance bar
here is agreement with assets/range/js/physics.js (the model users' balls
actually fly under today), not with the plan doc's original reference table --
that table predates the 2026-08-31 aerodynamics refit (commit 0c1afb9) and is
stale by construction.

The cross-engine values below were captured by running identical inputs
through both engines via Node (physics.js's calculateTrajectory) and this
module's carry_yards(); see that commit's history for how they were produced.
"""
import pytest

from src.analytics.flight_model import carry_yards, model_optimum

# (ball_speed_mph, vla_deg, spin_rpm) -> carry_yd, straight shot (axis=hla=0),
# cross-checked against assets/range/js/physics.js's calculateTrajectory().
JS_CROSS_CHECK = [
    (80, 31.5, 3000, 106.227),
    (100, 31.5, 3000, 151.299),
    (120, 29.5, 2250, 195.870),
    (140, 26.0, 2250, 236.663),
    (160, 24.0, 2250, 274.502),
    (90, 20.0, 4500, 113.511),
    (110, 35.0, 1500, 171.678),
    (75, 45.0, 6000, 81.798),
    (130, 15.0, 2000, 197.029),
]


def test_matches_shipped_js_engine():
    for bs, vla, spin, expected_yd in JS_CROSS_CHECK:
        got = carry_yards(bs, vla, spin)
        assert got == pytest.approx(expected_yd, abs=0.1), (bs, vla, spin)


def test_model_optimum_is_monotonic_increasing_with_ball_speed():
    # Faster swings should never have a *lower* achievable carry ceiling.
    speeds = [50, 80, 110, 140, 170]
    optimums = [model_optimum(s) for s in speeds]
    assert optimums == sorted(optimums)


def test_model_optimum_clamps_at_table_bounds():
    from src.analytics.flight_model import _load_table
    table = _load_table()
    assert model_optimum(table[0][0] - 10) == table[0][1]
    assert model_optimum(table[-1][0] + 10) == table[-1][1]


def test_efficiency_ratio_rewards_optimal_launch_over_poor_launch():
    bs = 90.0
    good = carry_yards(bs, 20.0, 4500) / model_optimum(bs)
    bad = carry_yards(bs, 5.0, 1000) / model_optimum(bs)
    assert good > bad
    assert 0.0 < bad < good <= 1.0 + 1e-6
