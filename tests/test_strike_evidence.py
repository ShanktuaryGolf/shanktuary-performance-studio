"""Contact location requires independent evidence, not a ball-flight proxy."""
from types import SimpleNamespace


def test_ball_flight_does_not_claim_centre_strike():
    import shanktuary_performance_studio as studio

    app = SimpleNamespace(
        current_club="7 Iron",
        get_bag_club=lambda club: {"loft_deg": 30},
        compute_smash_confidence=lambda *args: {"clamped": False},
    )
    shot = {
        "club": "7 Iron", "vertical_launch_angle_degrees": 20.4,
        "ball_speed_meters_per_second": 45, "total_spin_rpm": 6000,
        "open_golf_coach": {"smash_factor": 1.37},
    }
    headline, detail, _ = studio.ShanktuaryApp.summarize_strike(app, shot)
    assert headline == "Location unavailable"
    assert "ball flight" in detail


def test_partial_coordinates_never_fill_the_missing_axis():
    from src.analytics.strike import contact_location

    result = contact_location({"impact_location": {"heel_toe_mm": 0}})
    assert result.horizontal_mm == 0
    assert result.vertical_mm is None
    assert not result.complete
    assert result.horizontal_text == "Centre · 0.0 mm"
    assert result.vertical_text == "Not reported"


def test_explicit_coordinates_are_not_recomputed_or_mirrored():
    from src.analytics.strike import contact_location

    result = contact_location({"open_golf_coach": {
        "face_contact": {"x_mm": -8, "y_mm": 3},
    }})
    assert result.complete
    assert result.horizontal_text == "Toe · 8.0 mm"
    assert result.vertical_text == "High · 3.0 mm"


def test_invalid_coordinates_are_not_measured_zero():
    from src.analytics.strike import contact_location

    for bad in (None, "", "nan", float("inf"), {}, True):
        result = contact_location({"face_impact": {"x_mm": bad, "y_mm": 0}})
        assert result.horizontal_mm is None
        assert result.vertical_mm == 0
        assert not result.complete


def _shot(ts, vla, mph, spin, club="7 Iron"):
    return {"timestamp_ns": ts, "club": club, "vertical_launch_angle_degrees": vla,
            "total_spin_rpm": spin, "ball_speed_meters_per_second": mph / 2.23694,
            "open_golf_coach": {"us_customary_units": {"ball_speed_mph": mph}}}


def test_context_compares_only_full_swing_peers_without_mutation():
    from copy import deepcopy
    from src.analytics.strike import flight_context

    selected = _shot(99, 25, 88, 6000)
    full = [_shot(i, 18 + i, 86 + i, 6000) for i in range(12)]
    chips = [_shot(50 + i, 40, 40, 3000) for i in range(4)]  # partial swings
    shots = full + chips + [selected, _shot(60, 20, 88, 6000, club="PW")]
    before = deepcopy(shots)
    context = flight_context(dict(selected), shots)
    assert context[0]["count"] == 12         # chips excluded by the full-swing gate
    assert context[0]["median"] == 23.5      # full swings only, never the chips
    assert context[0]["delta"] == 1.5
    assert shots == before                   # never mutates session history


def test_context_needs_three_peers_and_preserves_zero_launch():
    from src.analytics.strike import flight_context

    shot = _shot(1, 0, 80, 5000, club="Putter")
    rows = flight_context(shot, [_shot(2, 2, 80, 5000, club="Putter")])
    assert rows[0]["value"] == 0
    assert rows[0]["median"] is None
    assert rows[1]["value"] == 5000


def test_quad_and_shot_use_reported_contact_not_ball_flight():
    import club_redesign_v1 as quad
    import overview_redesign_v12 as shot_view

    import shanktuary_app  # establishes the private renderer import path
    import shanktuary_performance_studio as studio

    app = SimpleNamespace(current_shot={"club": "7 Iron", "vertical_launch_angle_degrees": 4,
                          "ball_speed_meters_per_second": 35, "total_spin_rpm": 4000},
                          current_club="PW", bag=[], is_left_handed=False,
                          compute_smash_confidence=lambda *a: {"clamped": True})
    assert quad._impact_state(app) == ("unknown", None, None)
    assert shot_view._impact_offsets_mm(app) == (None, None)
    app.current_shot["face_impact"] = {"x_mm": -4, "y_mm": 2}
    assert quad._impact_state(app) == ("reported", -4, 2)
    assert shot_view._impact_offsets_mm(app) == (-4, 2)
    assert studio.ShanktuaryApp.summarize_strike(app, app.current_shot)[:2] == (
        "Contact reported", "Toe · 4.0 mm / High · 2.0 mm")
