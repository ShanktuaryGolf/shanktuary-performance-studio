"""Contract/regression tests for `player_shanktuary_index()`'s `game_areas`
breakdown (plan §5) -- empty bands, single- and multi-club bands, the
rounding rule, and JSON-safety. Black-box only: no changes to
`src/analytics/index.py` unless a concrete defect turns up (none did).
"""
import json

from src.analytics.index import (
    CARRY_BAND_CUTS,
    MIN_SHOTS_ESTABLISHED,
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


def _club(bs, carry, club, count=MIN_SHOTS_ESTABLISHED + 5):
    return [shot(bs=bs, carry=carry, club=club) for _ in range(count)]


BAND_CODES = [code for code, _label, _cut in CARRY_BAND_CUTS]


# --- structure: all 4 band codes always present -----------------------------

def test_game_areas_always_has_all_four_band_codes():
    # Driver only -- below MIN_CLUBS_FOR_INDEX, so this is insufficient
    # coverage, but game_areas must still report the full A-D shape.
    shots = _club(bs=110.0, carry=250.0, club="Driver")
    result = player_shanktuary_index(shots)

    assert result["status"] == "insufficient_coverage"
    assert set(result["game_areas"]) == set(BAND_CODES)


def test_game_areas_present_in_available_response_too():
    shots = (
        _club(bs=110.0, carry=250.0, club="Driver")
        + _club(bs=95.0, carry=150.0, club="7 Iron")
        + _club(bs=90.0, carry=100.0, club="PW")
    )
    result = player_shanktuary_index(shots)
    assert result["status"] == "available"
    assert set(result["game_areas"]) == set(BAND_CODES)


# --- empty bands -------------------------------------------------------------

def test_a_band_with_no_established_club_has_none_score_and_no_clubs():
    # Driver (band A) + PW (band D) -- band B and C are empty.
    shots = _club(bs=110.0, carry=250.0, club="Driver") + _club(bs=90.0, carry=100.0, club="PW")
    result = player_shanktuary_index(shots)

    for code in ("B", "C"):
        area = result["game_areas"][code]
        assert area["score"] is None
        assert area["clubs"] == []


# --- single-club bands --------------------------------------------------------

def test_single_club_band_score_equals_that_clubs_own_composite_score():
    shots = (
        _club(bs=110.0, carry=250.0, club="Driver")
        + _club(bs=95.0, carry=150.0, club="7 Iron")
        + _club(bs=90.0, carry=100.0, club="PW")
    )
    result = player_shanktuary_index(shots)

    band_a = result["game_areas"]["A"]
    assert band_a["clubs"] == ["Driver"]
    assert band_a["score"] == round(result["clubs"]["Driver"]["composite"]["score"], 1)


# --- multi-club bands: the rounding rule --------------------------------------

def test_multi_club_band_score_is_the_rounded_mean_of_member_composites():
    # 7 Iron and Hybrid both land in band C (ratio 0.55-0.70 of the 250y
    # Driver anchor); Driver alone anchors band A.
    shots = (
        _club(bs=110.0, carry=250.0, club="Driver")
        + _club(bs=95.0, carry=150.0, club="7 Iron")   # ratio 0.60
        + _club(bs=97.0, carry=160.0, club="Hybrid")    # ratio 0.64
    )
    result = player_shanktuary_index(shots)

    band_c = result["game_areas"]["C"]
    assert sorted(band_c["clubs"]) == ["7 Iron", "Hybrid"]

    member_scores = [result["clubs"][c]["composite"]["score"] for c in band_c["clubs"]]
    expected = round(sum(member_scores) / len(member_scores), 1)
    assert band_c["score"] == expected

    # the rounding rule is exactly one decimal place, not a raw float
    assert band_c["score"] == round(band_c["score"], 1)


# --- JSON safety ---------------------------------------------------------------

def test_game_areas_is_json_safe_in_every_response_status():
    available_shots = (
        _club(bs=110.0, carry=250.0, club="Driver")
        + _club(bs=95.0, carry=150.0, club="7 Iron")
        + _club(bs=90.0, carry=100.0, club="PW")
    )
    insufficient_shots = _club(bs=110.0, carry=250.0, club="Driver")

    for shots in (available_shots, insufficient_shots):
        result = player_shanktuary_index(shots)
        encoded = json.dumps(result["game_areas"])
        assert "NaN" not in encoded
        assert "Infinity" not in encoded
        decoded = json.loads(encoded)
        assert decoded == result["game_areas"]
        for area in decoded.values():
            assert area["score"] is None or isinstance(area["score"], (int, float))
            assert isinstance(area["clubs"], list)
            assert isinstance(area["name"], str)
