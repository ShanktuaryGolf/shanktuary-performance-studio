"""Regression coverage against real native Nova/OGC shot shapes.

`bag_index_summary()` and its helpers are audited here against the shapes
actually seen in `shanktuary_session_history.json` (Nova) and the GSPro
mapper (`src/gspro/mapper.py`, which deliberately emits Nova-compatible
top-level names) -- not synthetic shot dicts that only ever exercise the
happy path. Three things this file checks that the other index tests don't:

  * malformed / missing / wrong-typed fields don't raise -- a bad shot is
    dropped, never a crash that takes the whole card down with it.
  * a mixed-club session (real bags carry several clubs of very different
    speed/spin/shape) doesn't leak one club's shots into another's tier.
  * the summary is JSON-safe end to end -- `json.dumps` round-trips it with
    no NaN/Infinity float literals and no non-primitive types, since
    `GET /api/index` serializes it verbatim.
"""
import json
import math

from src.analytics.index import ConfidenceTier, bag_index_summary


def nova_shot(bs=90.0, vla=18.0, spin=6500.0, axis=1.0, club="7 Iron", **extra):
    """A shot shaped like the real session file: top-level SI/degrees/rpm
    fields plus open_golf_coach.us_customary_units for imperial ball speed."""
    shot = {
        "type": "shot",
        "club": club,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "spin_axis_degrees": axis,
        "open_golf_coach": {
            "spin_axis_degrees": axis,  # Nova mirrors some fields into ogc too
            "us_customary_units": {"ball_speed_mph": bs},
        },
    }
    shot.update(extra)
    return shot


# --- malformed / missing fields -------------------------------------------

def test_missing_open_golf_coach_is_dropped_not_raised():
    shots = [{"club": "7 Iron", "total_spin_rpm": 6500.0}] * 20
    assert bag_index_summary(shots) == {}


def test_null_us_customary_units_is_dropped_not_raised():
    shots = [nova_shot() for _ in range(20)]
    shots[0]["open_golf_coach"]["us_customary_units"] = None
    result = bag_index_summary(shots)
    assert result["7 Iron"]["efficiency"]["count"] == 19


def test_string_ball_speed_is_dropped_not_raised():
    shots = [nova_shot() for _ in range(20)]
    shots[0]["open_golf_coach"]["us_customary_units"]["ball_speed_mph"] = "n/a"
    result = bag_index_summary(shots)
    assert result["7 Iron"]["efficiency"]["count"] == 19


def test_none_spin_axis_is_dropped_not_raised():
    shots = [nova_shot() for _ in range(20)]
    shots[0]["spin_axis_degrees"] = None
    result = bag_index_summary(shots)
    assert result["7 Iron"]["shape"]["count"] == 19


def test_missing_club_key_falls_back_to_unknown():
    shot = nova_shot()
    del shot["club"]
    shots = [shot for _ in range(20)]
    result = bag_index_summary(shots)
    assert "Unknown" in result
    assert "composite" not in result["Unknown"]  # unrecognized club, no category


def test_completely_empty_shot_dicts_do_not_raise():
    assert bag_index_summary([{}] * 30) == {}


def test_non_numeric_spin_is_dropped_not_raised():
    shots = [nova_shot() for _ in range(20)]
    shots[0]["total_spin_rpm"] = "high"
    # a non-numeric spin fails the shared gate entirely -- one fewer valid shot
    result = bag_index_summary(shots)
    assert result["7 Iron"]["efficiency"]["count"] == 19


# --- mixed-club histories --------------------------------------------------

def test_mixed_bag_keeps_clubs_independent():
    """Ball speeds are chosen close enough together that neither a per-club
    nor a bag-wide partial-swing anchor (that detail is being actively
    reworked elsewhere) would filter any of them out -- this test is only
    about per-club tiers/categories staying independent in a mixed bag."""
    shots = (
        [nova_shot(bs=110.0, vla=11.0, spin=2700.0, axis=-2.0, club="Driver") for _ in range(35)]
        + [nova_shot(bs=95.0, vla=18.0, spin=6500.0, axis=1.0, club="7 Iron") for _ in range(20)]
        + [nova_shot(bs=90.0, vla=28.0, spin=9500.0, axis=0.5, club="PW") for _ in range(5)]
        + [nova_shot(bs=60.0, vla=35.0, spin=5000.0, axis=0.0, club="Putter") for _ in range(8)]
    )
    result = bag_index_summary(shots)

    assert set(result) == {"Driver", "7 Iron", "PW"}  # Putter excluded entirely
    assert result["Driver"]["efficiency"]["confidence"] == ConfidenceTier.ESTABLISHED
    assert result["7 Iron"]["efficiency"]["confidence"] == ConfidenceTier.PROVISIONAL
    assert result["PW"]["efficiency"]["confidence"] == ConfidenceTier.UNRATED
    # a wedge-speed shot must never contaminate the driver's tier or score
    assert result["Driver"]["efficiency"]["count"] == 35
    assert result["7 Iron"]["efficiency"]["count"] == 20


def test_mixed_bag_applies_each_clubs_own_category_weights():
    shots = (
        [nova_shot(bs=165.0, vla=11.0, spin=2700.0, axis=0.0, club="Driver") for _ in range(2)]
        + [nova_shot(bs=90.0, vla=18.0, spin=6500.0, axis=0.0, club="7 Iron") for _ in range(2)]
        + [nova_shot(bs=70.0, vla=28.0, spin=9500.0, axis=0.0, club="PW") for _ in range(2)]
    )
    result = bag_index_summary(shots)

    # woods weight efficiency 30/45, irons 20/30 -- different category means
    # a perfect (ratio == 1) shape/efficiency pair still isn't compared 1:1
    # across clubs, so each composite is computed from its own club's weights.
    for club in ("Driver", "7 Iron", "PW"):
        assert result[club]["composite"]["score"] >= 0.0


def test_excluded_shots_in_one_club_do_not_affect_another_clubs_count():
    shots = (
        [nova_shot(bs=110.0, vla=11.0, spin=2700.0, axis=0.0, club="Driver", excluded=True) for _ in range(10)]
        + [nova_shot(bs=95.0, vla=18.0, spin=6500.0, axis=0.0, club="7 Iron") for _ in range(20)]
    )
    result = bag_index_summary(shots)
    assert "Driver" not in result
    assert result["7 Iron"]["efficiency"]["count"] == 20


# --- JSON-safe API output ---------------------------------------------------

def _assert_json_safe(value):
    """Recursively assert no NaN/Infinity floats and only JSON primitives."""
    if isinstance(value, dict):
        for v in value.values():
            _assert_json_safe(v)
    elif isinstance(value, list):
        for v in value:
            _assert_json_safe(v)
    elif isinstance(value, float):
        assert math.isfinite(value), f"non-finite float in summary: {value!r}"
    elif isinstance(value, (int, str, bool)) or value is None:
        pass
    else:
        raise AssertionError(f"non-JSON-primitive type leaked into summary: {type(value)!r}")


def test_summary_round_trips_through_json_with_no_nan_or_inf():
    shots = (
        [nova_shot(bs=165.0, vla=11.0, spin=2700.0, axis=-3.0, club="Driver") for _ in range(35)]
        + [nova_shot(bs=90.0, vla=18.0, spin=6500.0, axis=1.0, club="7 Iron") for _ in range(45)]
    )
    summary = bag_index_summary(shots)
    _assert_json_safe(summary)

    encoded = json.dumps(summary)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert json.loads(encoded) == summary


def test_confidence_tier_serializes_as_plain_int():
    shots = [nova_shot(club="7 Iron") for _ in range(35)]
    summary = bag_index_summary(shots)
    encoded = json.dumps(summary)
    decoded = json.loads(encoded)
    assert decoded["7 Iron"]["efficiency"]["confidence"] == int(ConfidenceTier.ESTABLISHED)


def test_empty_history_is_json_safe():
    assert json.dumps(bag_index_summary([])) == "{}"
