"""Regression coverage for reconstructed presence-aware desktop readouts."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.connections.presentation import METRIC_PATHS, metric_status, metric_value
from src.gspro import settings
from src.ui._legacy import numbers_redesign_v2 as numbers
from src.ui._legacy import range_redesign_v2 as range_ui
from src.ui._legacy import shell_redesign_v8 as shell
from src.ui._legacy import table_redesign_v1 as table


def put(obj, path, value):
    parts = path.split(".")
    for key in parts[:-1]:
        obj = obj.setdefault(key, {})
    obj[parts[-1]] = value


def shot(source="cgp", **values):
    return {"_source": source, "club": "7 Iron", "open_golf_coach": {"us_customary_units": values}}


@pytest.mark.parametrize("metric", METRIC_PATHS)
def test_missing_and_real_zero_are_distinct(metric):
    current = shot()
    assert metric_value(current, metric) is None
    assert metric_status(current, metric) == "NOT REPORTED"
    put(current, METRIC_PATHS[metric][0][0], 0)
    assert metric_value(current, metric) == 0
    assert metric_status(current, metric) == "REPORTED"


@pytest.mark.parametrize("metric", METRIC_PATHS)
@pytest.mark.parametrize("value", [None, True, False, "0", float("nan"), float("inf"), []])
def test_malformed_fields_are_not_numeric(metric, value):
    current = shot()
    put(current, METRIC_PATHS[metric][0][0], value)
    assert metric_value(current, metric) is None
    assert metric_status(current, metric) == "NOT REPORTED"


@pytest.mark.parametrize("kind,label", [("measured", "REPORTED"), ("source_reported", "REPORTED"),
                                         ("source_estimated", "ESTIMATED"), ("modelled", "MODELLED"),
                                         ("derived", "DERIVED")])
def test_provenance_and_unit_conversion(kind, label):
    current = shot()
    put(current, "ball_speed_meters_per_second", 44.704)
    current["_metric_provenance"] = {"ball_speed_meters_per_second": {"kind": kind}}
    assert metric_value(current, "ball_speed") == pytest.approx(100)
    assert metric_status(current, "ball_speed") == label


@pytest.mark.parametrize("kind,label", [("modelled", "MODELLED"), ("source_estimated", "ESTIMATED")])
def test_derived_unit_alias_inherits_uncertainty(kind, label):
    current = shot(carry_distance_yards=100)
    current["_metric_provenance"] = {
        "open_golf_coach.us_customary_units.carry_distance_yards": {"kind": "derived", "inputs": ["si"]},
        "si": {"kind": "derived", "inputs": ["original"]}, "original": {"kind": kind}}
    assert metric_status(current, "carry") == label


def test_reported_alias_wins_and_reading_is_nonmutating():
    current = shot(carry_distance_yards=200)
    current["open_golf_coach"]["carry_distance_meters"] = 300
    current["_metric_provenance"] = {"open_golf_coach.carry_distance_meters": {"kind": "modelled"}}
    before = copy.deepcopy(current)
    assert metric_value(current, "carry") == 200
    assert metric_status(current, "carry") == "REPORTED"
    assert current == before


def test_cyclic_provenance_is_bounded():
    current = {"total_spin_rpm": 0, "_metric_provenance": {
        "total_spin_rpm": {"kind": "derived", "inputs": ["other"]},
        "other": {"kind": "derived", "inputs": ["total_spin_rpm"]}}}
    assert metric_status(current, "spin") == "DERIVED"


def test_handed_scalars_and_maps_follow_native_contract():
    current = shot()
    current["open_golf_coach"].update(club_path_degrees=4,
                                    club_face_to_path_degrees={"right_handed": 2, "left_handed": -3})
    assert metric_value(current, "club_path", left_handed=True) == -4
    assert metric_value(current, "face_to_path", left_handed=True) == -3


def test_transport_estimated_and_derived_markers_survive_without_enrichment():
    current = {"ball_speed_meters_per_second": 40, "total_spin_rpm": 3000,
               "_cgp": {"estimated_fields": ["ball_speed_meters_per_second"]},
               "_open_connect": {"derived_fields": ["total_spin_rpm"]}}
    assert metric_status(current, "ball_speed") == "ESTIMATED"
    assert metric_status(current, "spin") == "DERIVED"


@pytest.mark.parametrize("source", ["gspro", "cgp", "open_connect"])
def test_numbers_does_not_use_legacy_fallback_arguments(monkeypatch, source):
    monkeypatch.setattr(numbers, "_background", lambda *args, **kwargs: None)
    app = SimpleNamespace(canvas=MagicMock(), current_shot=shot(source), is_left_handed=False)
    numbers.draw_big_numbers_viewport(app, 1100, 720, *([999.0] * 12), hang_time=999)
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert texts.count("--") == 16
    assert texts.count("NOT REPORTED") == 16
    assert not any("999" in text for text in texts)


def test_numbers_shows_actual_reported_club_metrics_and_estimated_flight():
    current = shot()
    current["open_golf_coach"].update(club_speed_meters_per_second=44.704, smash_factor=1.5,
                                    angle_of_attack_degrees=-3, dynamic_loft_degrees=14,
                                    face_closure_rate_dps=0, carry_distance_meters=100)
    current["_metric_provenance"] = {"open_golf_coach.carry_distance_meters": {"kind": "modelled"}}
    app = SimpleNamespace(current_shot=current, is_left_handed=False)
    cards = {card[0]: card for card in numbers._connection_cards(app)}
    assert cards["CLUB SPEED"][1] == "100.0"
    assert cards["SMASH FACTOR"][1] == "1.50"
    assert cards["ATTACK ANGLE"][1] == "-3.0°"
    assert cards["DYNAMIC LOFT"][1] == "14.0°"
    assert cards["CLOSURE RATE"][1] == "0"
    assert cards["CARRY DISTANCE"][4] == "MODELLED"
    assert cards["CLUB SPEED"][4] == "REPORTED"


def test_nova_numbers_retains_existing_clamp_behavior(monkeypatch):
    monkeypatch.setattr(numbers, "_background", lambda *args, **kwargs: None)
    app = SimpleNamespace(canvas=MagicMock(), current_shot=shot("nova"), is_left_handed=False,
                          compute_smash_confidence=lambda *args: {"clamped": True})
    numbers.draw_big_numbers_viewport(app, 1100, 720, *([1.0] * 12))
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert texts.count("UNAVAILABLE") == 2
    assert texts.count("NOT MEASURED") == 2
    assert "NOT REPORTED" not in texts


def table_app(shots, ascending=True):
    canvas = MagicMock()
    canvas.bbox.return_value = None
    return SimpleNamespace(canvas=canvas, session_shots=shots, table_row_rects=[], table_header_rects=[],
                           table_checkbox_rects=[], table_sort_col="carry", table_sort_asc=ascending,
                           table_scroll_offset=0, selected_shot_index=0, is_left_handed=False,
                           compute_smash_confidence=lambda *args: {"clamped": False},
                           calculate_session_averages=MagicMock(return_value={}),
                           resolve_handed=lambda value, default: default if value is None else value)


def test_table_field_means_exclude_missing_and_excluded_include_zero():
    first = shot(carry_distance_yards=100, ball_speed_mph=80)
    absent = shot(ball_speed_mph=100)
    zero = shot(carry_distance_yards=0)
    excluded = dict(shot(carry_distance_yards=999), excluded=True)
    first["_metric_provenance"] = {
        "open_golf_coach.us_customary_units.carry_distance_yards": {"kind": "modelled"}}
    result = table._presence_summary([first, absent, zero, excluded])
    assert result["count"] == 3
    assert result["carry"] == 50
    assert result["field_counts"]["carry"] == 2
    assert result["ball_speed"] == 90
    assert result["club_speed"] is None
    assert "Carry 50.0~y" in table._presence_summary_parts(result)
    assert "Smash --" in table._presence_summary_parts(result)


@pytest.mark.parametrize("ascending,expected", [(True, [2, 3, 0, 1]), (False, [0, 3, 2, 1])])
def test_table_missing_sorts_last_in_both_directions(ascending, expected):
    app = table_app([shot(carry_distance_yards=100), shot(),
                     shot(carry_distance_yards=-1), shot(carry_distance_yards=0)], ascending)
    table.draw_shot_table_viewport(app, 1500, 800)
    assert [rect[-1] for rect in app.table_row_rects] == expected
    app.calculate_session_averages.assert_not_called()


def test_all_nova_table_keeps_legacy_summary_and_defaults():
    app = table_app([shot("nova")])
    table.draw_shot_table_viewport(app, 1500, 800)
    app.calculate_session_averages.assert_called_once()
    assert "1.00" in [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]


def draw_range(monkeypatch, current, history=None, defaults=999):
    monkeypatch.setattr(range_ui, "_scene_background", lambda *args: None)
    app = SimpleNamespace(canvas=MagicMock(), current_shot=current, current_club="7 Iron",
                          session_shots=history if history is not None else [current])
    range_ui.draw_range(app, 1200, 800, *([defaults] * 9))
    return app


def flights(app):
    return [call for call in app.canvas.create_line.call_args_list if call.kwargs.get("smooth")]


@pytest.mark.parametrize("missing", ["carry_distance_yards", "offline_distance_yards", "peak_height_yards"])
@pytest.mark.parametrize("source", ["gspro", "cgp", "open_connect"])
def test_range_requires_all_actual_geometry(monkeypatch, missing, source):
    current = shot(source, carry_distance_yards=180, offline_distance_yards=0, peak_height_yards=20)
    del current["open_golf_coach"]["us_customary_units"][missing]
    app = draw_range(monkeypatch, current)
    assert not flights(app)
    assert not app.canvas.create_oval.called
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert any("Flight unavailable" in text for text in texts)
    assert "NOT REPORTED" in texts
    assert not any("999" in text for text in texts)


def test_range_current_outside_history_cannot_use_fallback_geometry(monkeypatch):
    app = draw_range(monkeypatch, shot(), history=[])
    assert not flights(app)
    assert not app.canvas.create_oval.called


def test_range_zero_apex_is_flat_and_zero_carry_is_displayed(monkeypatch):
    current = shot(carry_distance_yards=180, offline_distance_yards=0, peak_height_yards=0)
    first = draw_range(monkeypatch, current, defaults=999)
    second = draw_range(monkeypatch, current, defaults=0)
    assert len(flights(first)) == 1
    assert flights(first)[0].args == flights(second)[0].args
    ys = flights(first)[0].args[1::2]
    assert all(a >= b for a, b in zip(ys, ys[1:]))
    current["open_golf_coach"]["us_customary_units"]["carry_distance_yards"] = 0
    app = draw_range(monkeypatch, current)
    assert not flights(app)
    metrics = {label: (text, status) for label, text, _, status in range_ui._presence_metrics(current)}
    assert metrics["Carry"] == ("0.0 YDS", "REPORTED")
    assert metrics["Apex"] == ("0.0 YDS", "REPORTED")


def test_range_estimates_labelled_and_incomplete_history_not_drawn(monkeypatch):
    current = shot(carry_distance_yards=180, offline_distance_yards=0, peak_height_yards=20)
    current["_metric_provenance"] = {
        "open_golf_coach.us_customary_units.carry_distance_yards": {"kind": "modelled"}}
    app = draw_range(monkeypatch, current, history=[shot(carry_distance_yards=150), current])
    assert len(flights(app)) == 1
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert "180.0 YDS~" in texts
    assert "MODELLED" in texts


def test_nova_range_keeps_legacy_defaults(monkeypatch):
    app = draw_range(monkeypatch, shot("nova"), defaults=100)
    assert len(flights(app)) == 1
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert "100.0 YDS" in texts
    assert "NOT REPORTED" not in texts


@pytest.mark.parametrize("source", ["gspro", "cgp", "open_connect"])
def test_drawer_missing_values_and_estimates(monkeypatch, source):
    current = shot(source)
    monkeypatch.setattr(shell.v4, "paint_sidebar", lambda *args: None)
    monkeypatch.setattr(shell.v4, "_filtered_shots", lambda app: [(0, current)])
    monkeypatch.setattr(shell.v7, "_draw_chevron", lambda *args: None)
    app = SimpleNamespace(canvas=MagicMock(), sidebar_width=340, selected_shot_index=0)
    shell.paint_sidebar(app, 1200, 800)
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert texts.count("--") == 2
    assert "0.0 yds" not in texts
    app.canvas.reset_mock()
    current["open_golf_coach"]["us_customary_units"].update(carry_distance_yards=0, ball_speed_mph=100)
    current["_metric_provenance"] = {
        "open_golf_coach.us_customary_units.ball_speed_mph": {"kind": "source_estimated"}}
    before = copy.deepcopy(current)
    shell.paint_sidebar(app, 1200, 800)
    texts = [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]
    assert "0.0 yds" in texts
    assert "100.0~ mph" in texts
    assert current == before


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(path))
    monkeypatch.delenv("SPS_SHOT_SOURCE", raising=False)
    monkeypatch.delenv("SPS_GSPRO_DB", raising=False)
    monkeypatch.setattr(settings, "_cache", None)
    return path


@pytest.mark.parametrize("source", ["nova", "both", "gspro", "open_connect", "cgp"])
def test_source_settings_are_backward_compatible_and_exclusive(settings_path, source):
    settings.save_settings(source=source)
    result = settings.load_settings(refresh=True)
    assert result["source"] == source
    assert settings.nova_enabled() is (source in ("nova", "both"))
    assert settings.gspro_enabled() is (source in ("gspro", "both"))
    assert result["open_connect_port"] == 921
    assert result["open_connect_lan"] is False
    assert result["cgp_device"] == ""
    assert result["ogc_enrichment"] is False
    assert result["ogc_club_estimates"] is False


def test_all_preferences_roundtrip_but_runtime_state_never_persists(settings_path):
    service = "Bay._cgp._tcp.local."
    settings.save_settings(source="cgp", open_connect_port=1921, open_connect_lan=True,
                           cgp_device=service, ogc_enrichment=True, ogc_club_estimates=False)
    settings.save_settings(onboarded=True)
    result = settings.load_settings(refresh=True)
    assert result["cgp_device"] == service
    assert result["open_connect_port"] == 1921
    assert result["open_connect_lan"] is True
    assert result["ogc_enrichment"] is True
    assert result["ogc_club_estimates"] is False
    saved = json.loads(settings_path.read_text())
    assert not {"running", "listening", "connected"}.intersection(saved)
    settings.save_settings(ogc_enrichment=False, ogc_club_estimates=True)
    assert settings.load_settings()["ogc_enrichment"] is False
    assert settings.load_settings()["ogc_club_estimates"] is True


@pytest.mark.parametrize("port", [0, -1, 65536, 921.0, True, "921", []])
def test_invalid_ports_rejected_and_corrupt_disk_ports_default(settings_path, port):
    settings.save_settings(source="nova")
    before = settings_path.read_text()
    with pytest.raises(ValueError):
        settings.save_settings(source="cgp", open_connect_port=port)
    assert settings_path.read_text() == before
    settings_path.write_text(json.dumps({"open_connect_port": port}))
    assert settings.load_settings(refresh=True)["open_connect_port"] == 921


@pytest.mark.parametrize("key", ["open_connect_lan", "ogc_enrichment", "ogc_club_estimates"])
@pytest.mark.parametrize("value", ["false", "true", 1, 0, []])
def test_malformed_opt_ins_never_enable_features(settings_path, key, value):
    settings_path.write_text(json.dumps({key: value}))
    assert settings.load_settings(refresh=True)[key] is False
    with pytest.raises(ValueError):
        settings.save_settings(**{key: value})


def test_environment_override_does_not_overwrite_choice(settings_path, monkeypatch):
    settings.save_settings(source="both")
    monkeypatch.setenv("SPS_SHOT_SOURCE", "cgp")
    assert settings.save_settings(open_connect_port=65535)["source"] == "cgp"
    assert json.loads(settings_path.read_text())["source"] == "both"
