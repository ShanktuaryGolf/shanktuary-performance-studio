"""PurePlay uses the actual Nova Overview composition, not a parallel page."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.ui.desktop import shot_ui
from src.ui.source_display import known, overview_values

v7 = shot_ui.v7
v8 = shot_ui.v8


def source_shot(source="pureplay"):
    return {"_source": source, "club": "PW", "shotId": "one", "ball_speed_meters_per_second": 20,
            "vertical_launch_angle_degrees": 20, "horizontal_launch_angle_degrees": 0,
            "total_spin_rpm": 3000, "spin_axis_degrees": 0,
            "open_golf_coach": {"carry_distance_meters": 30, "total_distance_meters": 40,
                "offline_distance_meters": 0, "peak_height_meters": 3,
                "shot_name": {"right_handed": "Straight", "left_handed": "Straight"}},
            "_metric_provenance": {"open_golf_coach.carry_distance_meters": {"kind": "source_estimated"}}}


def render(monkeypatch, shot):
    monkeypatch.setattr(v7, "_linear_surface", lambda *a, **k: object())
    monkeypatch.setattr(v8, "_material_image", lambda *a, **k: object())
    canvas = MagicMock()
    canvas.bbox.return_value = None
    canvas.find_withtag.return_value = []
    app = SimpleNamespace(canvas=canvas, current_shot=shot, session_shots=[shot], sessions=[{"shots": [shot]}],
        current_club="PW", selected_shot_index=0, is_left_handed=False,
        get_scaled_club_asset=lambda *a, **k: None)
    before = deepcopy(shot)
    shot_ui.draw_overview(app, 1600, 1080, *([0] * 15), offset_x=300)
    assert shot == before
    return app


def texts(app):
    return [c.kwargs.get("text", "") for c in app.canvas.create_text.call_args_list]


def test_shared_overview_contains_original_analytical_sections(monkeypatch):
    app = render(monkeypatch, source_shot())
    t = texts(app)
    assert "Session Trends" in t and "Shot Shape" in t and "Path & Face" in t
    assert "Avg Smash" in t and "Avg VLA" in t and "Curve Movement" in t
    assert "Location unavailable" in t
    assert "--" in t
    assert any("~" in x for x in t)
    assert not any(c.kwargs.get("tags") == "contact-estimate" for c in app.canvas.create_oval.call_args_list)


def test_absence_suppresses_geometry_but_real_zero_stays_known(monkeypatch):
    s = source_shot()
    assert known(overview_values(s), "offline", "hlaunch")
    del s["open_golf_coach"]["offline_distance_meters"]
    app = render(monkeypatch, s)
    t = texts(app)
    assert "Carry / offline unavailable" in t
    assert "Movement unavailable" in t
    assert "Avg --" in t
    assert "PATH N/A" in t


def test_no_parallel_pureplay_routing():
    source = (Path(__file__).resolve().parents[1]/"shanktuary_performance_studio.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    draw = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "draw_screen")
    names = [n.func.attr for n in ast.walk(draw) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "draw_overview_viewport" in names and "draw_4_quadrant_studio" in names
    assert "draw_connection_page" not in ast.unparse(draw)


def test_mixed_session_statistics_exclude_missing_pureplay_fields(monkeypatch):
    import overview_redesign_v15 as v15
    s = source_shot()
    app = render(monkeypatch, s)
    app.canvas.reset_mock()
    nova = {"club": "PW", "open_golf_coach": {"us_customary_units": {"carry_distance_yards": 100}}}
    absent = {"_source": "pureplay", "club": "PW"}
    zero = {"_source": "pureplay", "club": "PW", "open_golf_coach": {"carry_distance_meters": 0}}
    v15._draw_session_bottom(app, 320, 800, 1850, 1060, [nova, absent, zero])
    assert "50.0 yds" in texts(app)
    assert "Avg 50.0 yds" in texts(app)


def test_complete_source_uses_same_background_and_chart_geometry(monkeypatch):
    pure = source_shot()
    pv = overview_values(pure)
    nova = deepcopy(pure)
    nova["_source"] = "nova"
    nova["open_golf_coach"].update(total_spin_rpm=3000, spin_axis_degrees=0,
        us_customary_units={"carry_distance_yards": pv["carry"], "total_distance_yards": pv["total"],
            "ball_speed_mph": pv["ball"], "peak_height_yards": pv["apex"], "offline_distance_yards":0})
    a = render(monkeypatch, pure)
    b = render(monkeypatch, nova)
    # The actual shared chart helpers use the same data, geometry and artwork calls.
    import overview_redesign_v15 as v15
    a.canvas.reset_mock(); b.canvas.reset_mock()
    v15._draw_dispersion(a, 320, 250, 900, 780, [pure])
    v15._draw_dispersion(b, 320, 250, 900, 780, [nova])
    for name in ("create_line", "create_oval"):
        assert getattr(a.canvas, name).call_args_list == getattr(b.canvas, name).call_args_list
    a.canvas.reset_mock(); b.canvas.reset_mock()
    import overview_redesign_v12 as v12
    v12._draw_shape(a, 930, 250, 1350, 780, pv, [pure])
    v12._draw_shape(b, 930, 250, 1350, 780, v7._values(nova), [nova])
    for name in ("create_line", "create_oval"):
        assert getattr(a.canvas, name).call_args_list == getattr(b.canvas, name).call_args_list
