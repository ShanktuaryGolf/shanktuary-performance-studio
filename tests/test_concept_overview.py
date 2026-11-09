"""Overview follows shot selection and never implies live data is at impact."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.ui import concept_overview as ui


@pytest.fixture(autouse=True)
def isolate_pressure_composition(monkeypatch):
    # Shot composition is independently covered by real-app integration tests.
    monkeypatch.setattr(ui, "draw_shot", lambda *args: None)


class Canvas:
    def __init__(self):
        self.items = []

    def __getattr__(self, name):
        if name.startswith("create_"):

            def create(*coords, **kw):
                self.items.append((name, coords, kw))
                return len(self.items)

            return create
        raise AttributeError(name)


class App:
    def __init__(self, shots):
        self.canvas = Canvas()
        self.session_shots = shots
        self.current_shot = shots[0] if shots else None
        self.selected_shot_index = 0
        self.current_club = "7 iron"
        self.is_left_handed = False
        self.swing_lab_history = []
        self.modes = []
        self.sessions = []
        self.source_picker_calls = 0

    def aim_corrected(self, shot):
        return deepcopy(shot)

    def get_pressure_trace(self, shot):
        return shot.get("pressure_trace", [])

    def board_is_streaming(self):
        return False

    def set_mode(self, mode):
        self.modes.append(mode)

    def open_shot_source_picker(self):
        self.source_picker_calls += 1


def test_selected_historical_capture_wins_over_live_and_latest_shot():
    old = {"club": "Driver", "pressure_trace": [{"rel_time_s": -0.2, "pct_left": 20}, {"rel_time_s": 0, "pct_left": 12}]}
    latest = {
        "club": "7 iron",
        "pressure_trace": [
            {"rel_time_s": -0.3, "pct_left": 40, "pct_right": 60},
            {"rel_time_s": 0.02, "pct_left": 71, "pct_right": 29},
            {"rel_time_s": 0.8, "pct_left": 88, "pct_right": 12},
        ],
    }
    app = App([old, latest])
    app.board_is_streaming = lambda: True
    before = deepcopy(app.session_shots)
    ui.draw(app, 1320, 900, 260)
    texts = [kw.get("text", "") for _, _, kw in app.canvas.items]
    assert "At impact · selected shot" in texts
    assert "Lead 12%" in texts
    assert app.current_shot is old
    assert app.session_shots == before
    assert any(
        kw.get("tags") == "overview-pressure-trace" for _, _, kw in app.canvas.items
    )


def test_empty_state_has_no_fabricated_trace_or_load():
    app = App([])
    ui.draw(app, 1320, 900, 260)
    texts = [kw.get("text", "") for _, _, kw in app.canvas.items]
    assert "Local boards not connected" in texts
    assert "No pressure data" in texts
    assert "No shots received" in texts
    assert "No recorded sessions" in texts
    assert texts.count("Unavailable") == 4
    assert not any("%" in str(label) and not str(label).endswith("%")
                   and "Lead load %" not in str(label) for label in texts)
    assert not any(
        kw.get("tags") == "overview-pressure-trace" for _, _, kw in app.canvas.items
    )


def test_summary_is_labelled_and_has_no_invented_trace():
    app = App([])
    trace, frame, label = ui.pressure_view(
        app, {"pressure_metrics": {"pct_left_at_impact": 0}}
    )
    assert trace == []
    assert frame == {"pct_left": 0, "pct_right": 100}
    assert label == "At impact · summary only"


def test_stale_live_data_is_not_shown_and_demo_is_explicit(monkeypatch):
    import obs_server

    frame = {"pct_left": 60, "pct_right": 40}
    monkeypatch.setattr(
        obs_server,
        "pressure_manager",
        SimpleNamespace(latest_frame=frame, is_simulator=True),
    )
    app = App([])
    assert ui.pressure_view(app, None)[1] is None
    app.board_is_streaming = lambda: True
    assert ui.pressure_view(app, None)[1] is frame
    assert ui.pressure_view(app, None)[2] == "DEMO · live load, not shot-synced"


def test_distant_trace_sample_does_not_claim_at_impact():
    shot = {"pressure_trace": [{"rel_time_s": -0.7, "pct_left": 23}]}
    assert ui.pressure_view(App([shot]), shot)[2] == "Recorded trace · final sample"


def test_navigation_preserves_selected_shot_and_existing_modes():
    app = App([{"club": "Driver"}, {"club": "7 iron"}])
    ui.draw(app, 1320, 900, 260)
    for rect, action in app.concept_overview_rects:
        assert ui.handle_click(app, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    assert app.modes == [8, 4]
    assert app.current_shot is app.session_shots[0]
    assert app.selected_shot_index == 0


def test_invalid_measurements_are_unavailable():
    for value in (float("nan"), float("inf"), True, "broken", None):
        assert ui.finite(value) is None
    assert ui._percentage({"pct_left": 101}, "pct_left") is None



def test_historical_shot_without_pressure_never_uses_live_frame(monkeypatch):
    import obs_server
    frame = {"pct_left": 60, "pct_right": 40}
    monkeypatch.setattr(obs_server, "pressure_manager", SimpleNamespace(latest_frame=frame, is_simulator=False))
    app = App([{"club": "Driver"}, {"club": "7 Iron"}])
    app.board_is_streaming = lambda: True
    assert ui.pressure_view(app, app.current_shot) == ([], None, "No pressure captured for this shot")


@pytest.mark.parametrize("action, mode", [("source", None), ("boards", 10), ("history", 13)])
def test_empty_actions_use_existing_paths_without_mutating_data(action, mode):
    app = App([])
    before = deepcopy(app.sessions)
    for _ in range(2):
        ui.draw(app, 1320, 900, 260)
        rect = next(rect for rect, key in app.concept_overview_rects if key == action)
        assert ui.handle_click(app, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    assert app.source_picker_calls == (2 if action == "source" else 0)
    assert app.modes == ([mode, mode] if mode is not None else [])
    if action == "boards":
        assert app.concept_setup_page == "details"
    assert app.session_shots == []
    assert app.sessions == before
    assert app.current_shot is None
    assert not ui.handle_click(app, -1, -1)


def test_empty_then_populated_replaces_actions_and_preserves_shot_analysis(monkeypatch):
    app = App([])
    called = []
    monkeypatch.setattr(ui, "draw_shot", lambda *args: called.append(args))
    ui.draw(app, 1320, 900, 260)
    assert not called
    assert {action for _, action in app.concept_overview_rects} == {"source", "boards", "history"}
    shot = {"club": "Driver", "pressure_metrics": {"pct_left_at_impact": 62}}
    app.session_shots = [shot]
    app.current_shot = shot
    app.canvas.items.clear()
    ui.draw(app, 1320, 900, 260)
    assert len(called) == 1
    assert app.current_shot is shot
    assert {action for _, action in app.concept_overview_rects} == {"pressure", "session"}
    labels = [kw.get("text", "") for _, _, kw in app.canvas.items]
    assert "Start connection setup" not in labels
    assert "Connect local boards" not in labels
    assert "Open session" not in labels
    assert "Lead 62%" in labels


def test_empty_composition_clears_old_shot_and_contact_hit_regions():
    app = App([])
    for name in ("concept_session_rects", "design_shot_card_rects", "design_shot_delete_rects"):
        setattr(app, name, [(0, 0, 1600, 1000)])
    app.contact_face_rect = app.contact_clear_rect = (0, 0, 1600, 1000)
    app.contact_face_geometry = object()
    ui.draw(app, 1320, 900, 260)
    assert not app.concept_session_rects
    assert not app.design_shot_card_rects
    assert not app.design_shot_delete_rects
    assert app.contact_face_rect is app.contact_clear_rect is app.contact_face_geometry is None


def test_recent_session_uses_only_recorded_history_without_changing_selection():
    app = App([])
    app.sessions = [
        {"name": "Older session", "shots": [{"club": "Driver"}]},
        {"name": "Practice yesterday", "created_at": "2026-11-08 18:30",
         "shots": [{"club": "7 Iron"}, {"club": "Driver"}]},
        {"name": "New empty session", "shots": []},
    ]
    before = deepcopy(app.sessions)
    ui.draw(app, 1320, 900, 260)
    labels = [kw.get("text", "") for _, _, kw in app.canvas.items]
    assert "Practice yesterday" in labels
    assert "2026-11-08 18:30 · 2 shots" in labels
    assert "Older session" not in labels
    assert "New empty session" not in labels
    assert "Saved locally" not in labels  # Persistence success is not inferred.
    assert not any("remote" in str(label).lower() for label in labels)
    assert app.current_shot is None
    assert app.sessions == before


def test_empty_session_shows_fresh_demo_load_as_live_not_shot_data(monkeypatch):
    import obs_server

    app = App([])
    frame = {"pct_left": 60, "pct_right": 40}
    monkeypatch.setattr(obs_server, "pressure_manager",
                        SimpleNamespace(latest_frame=frame, is_simulator=True))
    app.board_is_streaming = lambda: True
    app.swing_lab_history = [dict(frame, rel_time_s=-0.1), dict(frame, rel_time_s=0)]
    ui.draw(app, 1320, 900, 260)
    labels = [kw.get("text", "") for _, _, kw in app.canvas.items]
    assert "DEMO · live load, not shot-synced" in labels
    assert "60%" in labels and "40%" in labels
    assert "Local boards not connected" not in labels
    assert "Connect local boards" not in labels
    assert "Open board setup" in labels
    assert "No shots received" in labels
    assert app.current_shot is None
    assert app.session_shots == []


@pytest.mark.parametrize("mode, shots, selected, height", [
    (12, [], None, 1000),
    (9, [], None, 1000),
    (12, [{"club": "Driver"}], None, 1450),
    (12, [], {"club": "Driver"}, 1450),
    (1, [{"club": "Driver"}], {"club": "Driver"}, 1000),
])
def test_overview_scroll_extent_matches_actual_content(monkeypatch, mode, shots, selected, height):
    from contextlib import nullcontext

    from src.ui import desktop

    class Canvas:
        minimum_size = None
        updates = 0

        def update_scrollregion(self):
            self.updates += 1

    monkeypatch.setattr(desktop, "ScaledCanvas", Canvas)
    monkeypatch.setattr(desktop.legacy_palette, "_page_palette", lambda app: nullcontext())
    base = desktop.ShanktuaryDesktopApp.__mro__[1]
    monkeypatch.setattr(base, "draw_screen", lambda app: None)
    app = desktop.ShanktuaryDesktopApp.__new__(desktop.ShanktuaryDesktopApp)
    app.canvas = Canvas()
    app.view_mode = mode
    app.sessions = [{"shots": shots}]
    app.active_session_index = 0
    app.current_shot = selected
    app.land_dot_coords = []
    desktop.ShanktuaryDesktopApp.draw_screen(app)
    assert app.canvas.minimum_size == (1600, height)
    assert app.canvas.updates == 1
    assert app.view_mode == (12 if mode == 9 else mode)
    assert app.session_shots is shots
    assert app.current_shot is selected
