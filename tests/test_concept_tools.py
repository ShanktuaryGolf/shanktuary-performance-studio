"""Tools workspace previews remain honest and preserve production actions."""

from types import SimpleNamespace

import pytest
from test_concept_workspaces import Canvas

from src.ui import concept_tools as ui
from src.ui.concept_canvas import _shift_geometry


def app_for_preview(shot=None):
    calls = []
    app = SimpleNamespace(
        canvas=Canvas(),
        current_shot=shot,
        session_shots=[shot] if shot else [],
        is_left_handed=False,
        ui_scale=1,
        ui_scale_choice="Auto",
        show_tools_menu=False,
        copy_to_clipboard=lambda value: calls.append(("copy", value)),
        export_session_report=lambda value: calls.append(("export", value)),
        open_log_folder=lambda: calls.append(("logs",)),
        set_mode=lambda value: calls.append(("mode", value)),
        step_ui_scale=lambda value: calls.append(("scale", value)),
        set_ui_scale=lambda value: calls.append(("set_scale", value)),
        draw_screen=lambda: calls.append(("draw",)),
    )
    return app, calls


def test_tools_empty_previews_show_unavailable_and_all_output_controls():
    app, _ = app_for_preview()
    ui.draw(app, 1328, 876, 272)
    words = app.canvas.words()
    for title in (
        "Broadcast & overlays",
        "Session report",
        "Floor projection",
        "Support",
    ):
        assert title in words
    assert "--" in words
    assert "Unavailable" in words
    assert "No carry data" in words
    assert "0 yd" not in words
    actions = {key for _, key in app.concept_tools_rects}
    assert actions == {
        "legacy_tools",
        "open_config",
        "copy_obs_url",
        "open_editor",
        "export_csv",
        "export_pdf",
        "open_divot",
        "open_tiles",
        "open_layout",
        "set_mode_0",
        "open_log_folder",
        "scale_minus",
        "scale_plus",
        "scale_auto",
    }
    for rect, _ in app.concept_tools_rects:
        assert rect[0] < rect[2] and rect[1] < rect[3]
        assert 272 <= rect[0] < rect[2] <= 1600
        assert rect[3] <= 876


def test_tools_thumbnails_use_real_metrics_without_mutating_source():
    shot = {
        "club": "7 Iron",
        "total_spin_rpm": 6400,
        "open_golf_coach": {
            "us_customary_units": {
                "carry_distance_yards": 151,
                "ball_speed_mph": 112,
                "offline_distance_yards": -3,
            }
        },
    }
    app, _ = app_for_preview(shot)
    ui.draw(app, 1328, 876, 272)
    assert "151 yd" in app.canvas.words()
    assert "6,400 rpm" in app.canvas.words()
    assert "Reported" in app.canvas.words()
    assert "Current session • 1 included shots" in app.canvas.words()
    assert app.session_shots == [shot]
    assert shot["open_golf_coach"]["us_customary_units"]["offline_distance_yards"] == -3


@pytest.mark.parametrize(
    "action,suffix",
    [
        ("open_config", "/config"),
        ("open_editor", "/?edit=true"),
        ("open_divot", "/divot"),
        ("open_tiles", "/tiles"),
        ("open_layout", "/?mode=projector"),
    ],
)
def test_tools_browser_routes_use_runtime_port_once(monkeypatch, action, suffix):
    import obs_server
    import shanktuary_performance_studio as production

    app, calls = app_for_preview()
    urls = []
    monkeypatch.setattr(obs_server, "OBS_PORT", 19321)
    monkeypatch.setattr(production.webbrowser, "open", urls.append)
    ui.draw(app, 1328, 876, 272)
    app.concept_tools_rects = _shift_geometry(app.concept_tools_rects, 124)
    rect = next(rect for rect, key in app.concept_tools_rects if key == action)
    assert ui.handle_click(app, rect[0] + 2, rect[1] + 2)
    assert urls == ["http://localhost:19321" + suffix]
    assert calls == [("draw",)]
    assert not ui.handle_click(app, -1, -1)
    assert len(urls) == 1


@pytest.mark.parametrize(
    "action,expected",
    [
        ("copy_obs_url", ("copy", "http://localhost:9321")),
        ("export_csv", ("export", "csv")),
        ("export_pdf", ("export", "pdf")),
        ("open_log_folder", ("logs",)),
        ("set_mode_0", ("mode", 0)),
        ("scale_minus", ("scale", -1)),
        ("scale_plus", ("scale", 1)),
        ("scale_auto", ("set_scale", "Auto")),
    ],
)
def test_tools_preserve_existing_callbacks(monkeypatch, action, expected):
    import obs_server

    monkeypatch.setattr(obs_server, "OBS_PORT", 9321)
    app, calls = app_for_preview()
    ui.draw(app, 1328, 876, 272)
    rect = next(rect for rect, key in app.concept_tools_rects if key == action)
    assert ui.handle_click(app, rect[0] + 2, rect[1] + 2)
    assert calls == [expected, ("draw",)]


def test_more_commands_retains_complete_legacy_flyout():
    app, calls = app_for_preview()
    ui.draw(app, 1328, 876, 272)
    rect = next(rect for rect, key in app.concept_tools_rects if key == "legacy_tools")
    assert ui.handle_click(app, rect[0] + 2, rect[1] + 2)
    assert app.show_tools_menu
    assert calls == [("draw",)]
