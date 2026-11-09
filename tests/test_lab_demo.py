"""Lab preview is isolated from both live hardware and stored shot history."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.ui import lab_demo


class Root:
    def __init__(self):
        self.pending = {}

    def after(self, delay, callback):
        key = len(self.pending) + 1
        self.pending[key] = callback
        return key

    def after_cancel(self, key):
        self.pending.pop(key, None)


def test_start_stop_repeat_and_selection_preserve_user_data(monkeypatch):
    import obs_server

    manager = SimpleNamespace(latest_frame={"hardware": True}, is_simulator=False)
    monkeypatch.setattr(obs_server, "pressure_manager", manager)
    shot = {"id": "history", "pressure_trace": None}
    app = SimpleNamespace(root=Root(), current_shot=shot, view_mode=8,
                          swing_lab_history=[{"real": True}],
                          session_shots=[shot], draw_screen=lambda: None)
    before = deepcopy((shot, app.swing_lab_history, app.session_shots, manager.__dict__))
    assert lab_demo.toggle(app)
    assert len(app.lab_demo_frames) == 81
    assert all(frame["simulated"] for frame in app.lab_demo_frames)
    assert len({frame["pct_left"] for frame in app.lab_demo_frames}) > 20
    assert lab_demo.toggle(app) is False
    assert not app.root.pending
    assert app.lab_demo_frames == []
    assert lab_demo.toggle(app)
    app.current_shot = {"id": "other"}
    assert not lab_demo.active(app)
    assert not app.root.pending
    assert (shot, app.swing_lab_history, app.session_shots, manager.__dict__) == before
    assert app.current_shot["id"] == "other"
    assert lab_demo.toggle(app)
    app.view_mode = 13
    assert not lab_demo.active(app)


def test_preview_uses_synthetic_frames_without_changing_historical_selection(monkeypatch):
    from test_lab_pressure_honesty import lab_app

    from src.ui import concept_workspaces
    from src.ui.desktop import ShanktuaryDesktopApp

    app, _ = lab_app(monkeypatch)
    app.root = Root()
    app.view_mode = 8
    app.draw_screen = lambda: None
    app.pressure_display_trail = lambda: ShanktuaryDesktopApp.pressure_display_trail(app)
    original = app.current_shot
    lab_demo.toggle(app)
    concept_workspaces.draw_lab(app, 1300, 900, offset_x=260)
    assert "SIMULATED · preview only · not saved" in app.canvas.words()
    assert "Stop demo" in app.canvas.words()
    assert app.pressure_display_trail() == (app.lab_demo_frames, False)
    assert app.current_shot is original
    lab_demo.toggle(app)
    app.canvas.items.clear()
    concept_workspaces.draw_lab(app, 1300, 900, offset_x=260)
    assert "Historical shot · pressure unavailable" in app.canvas.words()
    assert app.pressure_display_trail() == ([], True)


@pytest.mark.parametrize("seconds", [0, 1, 2, 2.7, 3, 4, 400])
def test_demo_frame_is_self_consistent_and_marked(seconds):
    frame = lab_demo.demo_frame(seconds)
    assert frame["simulated"] is True
    assert sum(frame["raw_cells"]) == pytest.approx(frame["total_kg"], abs=.03)
    assert frame["pct_left"] + frame["pct_right"] == pytest.approx(100)
    assert frame["force_bw"] == pytest.approx(frame["total_kg"] / 80, abs=.001)
    assert frame["torque_nm"] is None
