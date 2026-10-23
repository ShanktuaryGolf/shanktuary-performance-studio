"""Draft 2 fixtures: validation, missing values, signed spin and provenance."""

from collections import OrderedDict

import pytest

from src.connections.cgp_mapper import CGPShotSession, map_cgp_shot_to_sps_payload


def shot(**changes):
    value = {"type": "shot", "shot_number": 12, "ball_speed_meters_per_second": 67.3,
             "vertical_launch_angle_degrees": 12.1, "horizontal_launch_angle_degrees": -1.4}
    value.update(changes)
    return value


def test_minimum_fixture_and_truthful_unit_aliases():
    raw = shot()
    payload = map_cgp_shot_to_sps_payload(raw)
    assert payload["_source"] == "cgp"
    assert payload["ball_speed_meters_per_second"] == 67.3
    assert "total_spin_rpm" not in payload
    assert "spin_axis_degrees" not in payload
    assert "timestamp_ns" not in payload
    ogc = payload["open_golf_coach"]
    assert ogc["us_customary_units"]["ball_speed_mph"] == pytest.approx(67.3 / .44704)
    for missing in ("total_spin_rpm", "club_speed_meters_per_second", "carry_distance_meters", "backspin_rpm"):
        assert missing not in ogc
    assert payload["_cgp"]["raw"] == raw
    raw["anything"] = "changed"
    assert "anything" not in payload["_cgp"]["raw"]


def test_signed_spin_estimated_fields_and_raw_extensions():
    raw = shot(total_spin_revolutions_per_minute=-2750, spin_axis_degrees=3.2,
               backspin_revolutions_per_minute=-2745, sidespin_revolutions_per_minute=154,
               player_dexterity="left", tee_position="mat", shot_kind="chip", measurement_id="unique",
               measured_at_nanoseconds=12345, estimated=["total_spin_revolutions_per_minute", "absent", "vendor_value"],
               vendor_value=99, extension={"value": "raw"})
    payload = map_cgp_shot_to_sps_payload(raw, device_name="Fixture")
    assert payload["total_spin_rpm"] == -2750
    assert payload["spin_axis_degrees"] == 3.2
    assert payload["open_golf_coach"]["backspin_rpm"] == -2745
    assert payload["open_golf_coach"]["sidespin_rpm"] == 154
    assert payload["open_golf_coach"]["total_spin_rpm"] == -2750
    assert payload["_cgp"]["raw"] == raw
    assert payload["_cgp"]["estimated"] == ["total_spin_revolutions_per_minute"]
    assert payload["_cgp"]["estimated_fields"] == ["total_spin_rpm", "open_golf_coach.total_spin_rpm"]
    assert payload["_cgp"]["player_dexterity"] == "left"


def test_zero_values_remain_present():
    payload = map_cgp_shot_to_sps_payload(shot(ball_speed_meters_per_second=0,
                                            total_spin_revolutions_per_minute=0, spin_axis_degrees=0))
    assert payload["total_spin_rpm"] == 0
    assert payload["ball_speed_meters_per_second"] == 0
    assert payload["spin_axis_degrees"] == 0


@pytest.mark.parametrize("changes", [
    {"type": "club"}, {"shot_number": 0}, {"shot_number": True}, {"shot_number": 1.5},
    {"ball_speed_meters_per_second": "67"}, {"ball_speed_meters_per_second": True},
    {"ball_speed_meters_per_second": float("nan")}, {"ball_speed_meters_per_second": float("inf")},
    {"ball_speed_meters_per_second": -1}, {"ball_speed_meters_per_second": 10 ** 1000},
    {"vertical_launch_angle_degrees": 91}, {"horizontal_launch_angle_degrees": -91},
    {"total_spin_revolutions_per_minute": 2700}, {"spin_axis_degrees": 0},
    {"total_spin_revolutions_per_minute": 0, "spin_axis_degrees": 1},
    {"total_spin_revolutions_per_minute": 1, "spin_axis_degrees": 91},
    {"backspin_revolutions_per_minute": 1200},
    {"total_spin_revolutions_per_minute": 1200, "spin_axis_degrees": 0, "sidespin_revolutions_per_minute": 0},
    {"final": 1}, {"final": None}, {"measurement_id": 1}, {"measured_at_nanoseconds": True},
    {"measured_at_nanoseconds": 1.5}, {"player_dexterity": "RH"}, {"tee_position": []},
    {"shot_kind": "drive"}, {"estimated": "spin_axis_degrees"},
    {"estimated": [1]}, {"estimated": ["shot_number", "shot_number"]},
])
def test_known_malformed_fields_are_rejected(changes):
    with pytest.raises(ValueError):
        map_cgp_shot_to_sps_payload(shot(**changes))


@pytest.mark.parametrize("missing", ["shot_number", "ball_speed_meters_per_second",
                                     "vertical_launch_angle_degrees", "horizontal_launch_angle_degrees"])
def test_required_fields_not_filled_with_zeros(missing):
    raw = shot()
    del raw[missing]
    with pytest.raises(ValueError):
        map_cgp_shot_to_sps_payload(raw)


def test_final_only_complete_snapshots_are_not_merged():
    session = CGPShotSession()
    assert session.ingest(shot(final=False, total_spin_revolutions_per_minute=2500, spin_axis_degrees=2)) is None
    payload = session.ingest(shot(final=True))
    assert payload is not None and "total_spin_rpm" not in payload
    assert session.ingest(shot()) is None
    assert session.ingest(shot(shot_number=11)) is not None  # Delayed final may finish out of order.
    assert session.ingest(shot(shot_number=11)) is None


def test_connection_reset_counter_and_global_replay_cache():
    cache = OrderedDict()
    first = CGPShotSession(cache)
    assert first.ingest(shot(measurement_id="same")) is not None
    second = CGPShotSession(cache)
    assert second.ingest(shot(shot_number=1, measurement_id="same")) is None
    assert second.ingest(shot(shot_number=2, measurement_id="new")) is not None
    assert CGPShotSession(cache).ingest(shot(shot_number=1)) is not None


def test_number_and_measurement_caches_are_bounded():
    session = CGPShotSession(capacity=2)
    for number in range(1, 4):
        assert session.ingest(shot(shot_number=number, measurement_id=str(number)))
    assert list(session.measurement_ids) == ["2", "3"]
    assert len(session._seen_numbers) == 2
    assert session.ingest(shot(shot_number=1)) is None


def test_session_ids_keep_pressure_trace_identity_unique():
    first, second = CGPShotSession().ingest(shot()), CGPShotSession().ingest(shot())
    assert first["shotId"] != second["shotId"]
    assert first["_cgp"]["session_id"] != second["_cgp"]["session_id"]
    assert len(first["shotId"]) == 32


def test_estimate_tags_follow_every_alias_and_unit_conversion_has_inputs():
    payload = map_cgp_shot_to_sps_payload(shot(estimated=["ball_speed_meters_per_second", "horizontal_launch_angle_degrees"]))
    mph = "open_golf_coach.us_customary_units.ball_speed_mph"
    assert set(payload["_cgp"]["estimated_fields"]) == {
        "ball_speed_meters_per_second", mph, "horizontal_launch_angle_degrees",
        "open_golf_coach.horizontal_launch_angle_degrees"}
    assert payload["_cgp"]["derived_fields"] == [mph]
    assert payload["_metric_provenance"][mph]["kind"] == "derived"
    assert payload["_metric_provenance"][mph]["inputs"] == ["ball_speed_meters_per_second"]
