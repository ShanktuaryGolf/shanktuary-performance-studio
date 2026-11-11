"""Concept painters preserve source availability and production hit targets."""

from types import SimpleNamespace

import theme
from src.ui import concept_workspaces as ui


class Canvas:
    def __init__(self):
        self.items = []

    def _add(self, kind, *coords, **options):
        self.items.append((kind, coords, options))
        return len(self.items)

    def create_polygon(self, *coords, **options):
        return self._add("polygon", *coords, **options)

    def create_rectangle(self, *coords, **options):
        return self._add("rectangle", *coords, **options)

    def create_text(self, *coords, **options):
        return self._add("text", *coords, **options)

    def create_line(self, *coords, **options):
        return self._add("line", *coords, **options)

    def create_oval(self, *coords, **options):
        return self._add("oval", *coords, **options)

    def bbox(self, item):
        # This recorder has no font engine. Match Tk's unavailable-geometry
        # result so painters can use their explicit fallback layout.
        return None

    def words(self):
        return [opt["text"] for _, _, opt in self.items if "text" in opt]


def test_palette_restores_global_theme_and_methods_after_error():
    canvas = Canvas()
    app = SimpleNamespace(canvas=canvas)
    original_color = theme.BG
    original_rectangle = canvas.create_rectangle
    try:
        with ui.palette(app, rounded=True):
            assert theme.BG == ui.PALETTE["BG"]
            canvas.create_rectangle(0, 0, 100, 50, fill=theme.SURFACE)
            raise ValueError("intentional")
    except ValueError:
        pass
    assert theme.BG == original_color
    assert canvas.create_rectangle == original_rectangle
    assert canvas.items[0][0] == "polygon"


def test_bag_preserves_scope_edit_reorder_and_unavailable_carry():
    app = SimpleNamespace(
        canvas=Canvas(),
        bag=[{"name": "7 Iron", "loft_deg": 34}],
        bag_scope="session",
        current_club="7 Iron",
        bag_scroll_offset=0,
        _draw_bag_ball_row=lambda *args: 30,
        get_bag_club_stats=lambda *args, **kwargs: {
            "shot_count": 0,
            "avg_carry": 0,
            "std_carry": 0,
        },
        calculate_bag_gapping=lambda **kwargs: {"clubs": []},
    )
    ui.draw_bag(app, 1300, 900, offset_x=260)
    words = app.canvas.words()
    assert "--" in words
    assert "0 yd" not in words
    assert app.bag_scope_all_rect != app.bag_scope_session_rect
    assert app.bag_club_card_rects[0][-1] == "7 Iron"
    assert app.bag_edit_btn_rects[0][-1] == "7 Iron"
    assert app.bag_move_up_rects[0][-1] == "7 Iron"
    assert app.bag_move_down_rects[0][-1] == "7 Iron"


def test_fit_preserves_tabs_and_does_not_plot_unavailable_telemetry():
    app = SimpleNamespace(
        canvas=Canvas(),
        get_fitting_clubs=lambda: ["7 Iron", "8 Iron"],
        fitting_baseline_club="7 Iron",
        current_club="7 Iron",
        fitting_submode="split",
        is_left_handed=False,
        session_shots=[{"club": "7 Iron", "_source": "pureplay"}],
        aim_corrected=lambda shot: dict(shot),
    )
    ui.draw_fit(app, 1300, 900, offset_x=260)
    assert len(app.fitting_submode_rects) == 3
    assert [rect[-1] for rect in app.concept_fit_selector_rects] == ["base", "test"]
    assert app.fitting_baseline_chip_rects == []
    assert app.fitting_club_chip_rects == []
    assert app.concept_fit_test_club == "8 Iron"
    assert app.fitting_dot_rects == []
    assert "--" in app.canvas.words()
    assert app.session_shots == [{"club": "7 Iron", "_source": "pureplay"}]


def test_index_reads_nested_production_composite(monkeypatch):
    import shanktuary_performance_studio as production

    monkeypatch.setattr(
        production,
        "player_shanktuary_index",
        lambda *a, **k: {
            "status": "available",
            "score": 72.4,
            "established_clubs": ["7 Iron"],
            "clubs": {"7 Iron": {"composite": {"score": 74.1}}},
            "game_areas": {},
        },
    )
    app = SimpleNamespace(
        canvas=Canvas(),
        sessions=[],
        is_left_handed=False,
        _draw_index_progress=lambda *args: 400,
        _draw_index_combine=lambda *args: None,
        _pressure_sentence_for=lambda name: None,
    )
    ui.draw_index(app, 1300, 900, offset_x=260)
    assert "72.4" in app.canvas.words()
    assert "74.1" in app.canvas.words()
    assert "7 Iron" in app.canvas.words()


def test_lab_empty_state_does_not_fabricate_foot_pressure(monkeypatch):
    import obs_server

    monkeypatch.setattr(
        obs_server,
        "pressure_manager",
        SimpleNamespace(latest_frame=None, is_simulator=False),
    )
    feet = []
    app = SimpleNamespace(
        canvas=Canvas(),
        current_shot=None,
        is_left_handed=False,
        is_reviewing_past_shot=lambda: False,
        draw_force_timeline_canvas=lambda *args, **kwargs: None,
        draw_single_foot_heatmap=lambda *args, **kwargs: feet.append(args),
    )
    ui.draw_lab(app, 1300, 900, offset_x=260)
    assert not feet
    assert "Awaiting pressure data" in app.canvas.words()
    assert "--" in app.canvas.words()
    assert app.swing_lab_tare_rect
    assert app.swing_lab_demo_rect


def test_setup_overview_swallows_hidden_detail_hits_and_routes_actions():
    calls = []
    app = SimpleNamespace(
        concept_setup_page="overview",
        concept_setup_actions={"details": (10, 10, 100, 40)},
        draw_screen=lambda: calls.append("draw"),
    )
    assert ui.handle_setup_click(app, 500, 500) is True
    assert ui.handle_setup_click(app, 20, 20) is True
    assert app.concept_setup_page == "details"
    assert ui.handle_setup_click(app, 500, 500) is False
    assert calls == ["draw"]


def test_dispersion_keeps_missing_carry_out_of_gapping():
    shot = {"club": "7 Iron", "_source": "pureplay"}
    app = SimpleNamespace(
        canvas=Canvas(),
        session_shots=[shot],
        sessions=[{"shots": [shot]}],
        active_session_index=0,
        current_club="7 Iron",
        is_left_handed=False,
        dispersion_view_submode="split",
        dispersion_split_by_ball=False,
        aim_corrected=lambda value: dict(value),
    )
    ui.draw_dispersion(app, 1300, 900, offset_x=260)
    assert len(app.design_dispersion_tab_rects) == 3
    assert app.dispersion_split_rect
    assert "No carry data available" in app.canvas.words()
    # The graph can label its coordinate origin. No missing measurement may
    # become a zero-valued gapping row or a plotted point.
    measurement_labels = [
        options["text"]
        for _, _, options in app.canvas.items
        if "text" in options and options.get("tags") != "comparison-axis"
    ]
    assert "0 yd" not in measurement_labels
    assert app.dispersion_dot_rects == []
    assert app.session_shots == [shot]


def test_fit_native_selectors_keep_all_clubs_and_independent_baseline(monkeypatch):
    """Menus retain keyboard navigation and have no invisible canvas hits."""
    import tkinter as tk

    menus = []
    draws = []

    class Menu:
        def __init__(self, *args, **kwargs):
            self.commands = {}
            self.destroyed = False
            self.released = False
            menus.append(self)

        def add_command(self, label, command):
            self.commands[label] = command

        def focus_force(self):
            self.focused = True

        def add_separator(self):
            pass

        def bind(self, event, command):
            self.escape = command

        def unpost(self):
            self.unposted = True

        def tk_popup(self, *position):
            self.position = position

        def grab_release(self):
            self.released = True

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(tk, "Menu", Menu)
    names = ["7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW"]
    shot = {"club": "7 Iron", "_source": "pureplay"}
    app = SimpleNamespace(
        canvas=Canvas(),
        get_fitting_clubs=lambda: names,
        fitting_baseline_club="7 Iron",
        current_club="7 Iron",
        fitting_submode="split",
        is_left_handed=False,
        session_shots=[shot],
        aim_corrected=lambda value: dict(value),
        draw_screen=lambda: draws.append(True),
        root=SimpleNamespace(winfo_pointerx=lambda: 50, winfo_pointery=lambda: 60,
                             focus_get=lambda: None),
    )
    ui.draw_fit(app, 1328, 876, 272)
    base, test = app.concept_fit_selector_rects
    assert ui.handle_fit_click(app, test[0] + 2, test[1] + 2)
    assert set(menus[-1].commands) == set(names[1:]) | {"Cancel"}
    assert menus[-1].position == (50, 60)
    assert not menus[-1].released
    assert menus[-1].focused
    # A dismissed menu has not changed either selection.
    assert app.fitting_baseline_club == app.current_club == "7 Iron"
    menus[-1].commands["SW"]()
    assert app.concept_fit_test_club == app.current_club == "SW"
    assert app.fitting_baseline_club == "7 Iron"
    assert ui.handle_fit_click(app, base[0] + 2, base[1] + 2)
    assert menus[-2].destroyed
    assert set(menus[-1].commands) == set(names) | {"Cancel"}
    menus[-1].commands["PW"]()
    assert app.fitting_baseline_club == "PW"
    assert app.current_club == "SW"
    assert app.session_shots == [shot]
    assert len(draws) == 2

    assert ui.handle_fit_click(app, base[0] + 2, base[1] + 2)
    menus[-1].escape()
    assert app._concept_fit_menu is None
    assert menus[-1].destroyed and menus[-1].released
    assert app.fitting_baseline_club == "PW"
    assert ui.handle_fit_click(app, test[0] + 2, test[1] + 2)
    menus[-1].commands["Cancel"]()
    assert app.concept_fit_test_club == "SW"


def test_fit_apex_converts_yards_to_feet_without_changing_source():
    shot = {
        "club": "7 Iron",
        "total_spin_rpm": 6400,
        "open_golf_coach": {
            "us_customary_units": {
                "carry_distance_yards": 150,
                "peak_height_yards": 30,
                "offline_distance_yards": 0,
            }
        },
    }
    app = SimpleNamespace(
        canvas=Canvas(),
        get_fitting_clubs=lambda: ["7 Iron", "8 Iron"],
        fitting_baseline_club="7 Iron",
        current_club="7 Iron",
        fitting_submode="split",
        is_left_handed=False,
        session_shots=[shot],
        aim_corrected=lambda value: dict(value),
    )
    ui.draw_fit(app, 1328, 876, 272)
    assert "90 ft" in app.canvas.words()
    assert "Reported" in app.canvas.words()
    assert "--" in app.canvas.words()
    assert len(app.fitting_dot_rects) == 1
    assert shot["open_golf_coach"]["us_customary_units"]["peak_height_yards"] == 30


def test_index_keeps_distinct_combine_card_and_dated_progress(monkeypatch):
    import shanktuary_performance_studio as production
    from src.analytics import combine, index_history

    monkeypatch.setattr(
        production,
        "player_shanktuary_index",
        lambda *a, **k: {
            "status": "available",
            "score": 72.4,
            "established_clubs": ["7 Iron"],
            "clubs": {"7 Iron": {"composite": {"score": 74.1}}},
            "game_areas": {},
        },
    )
    monkeypatch.setattr(
        index_history,
        "load",
        lambda: [
            {"at": "2026-10-01", "score": 70.0},
            {"at": "2026-11-01", "score": 72.4},
        ],
    )
    monkeypatch.setattr(combine, "load", lambda: [])
    app = SimpleNamespace(
        canvas=Canvas(),
        sessions=[],
        is_left_handed=False,
        _pressure_sentence_for=lambda name: None,
    )
    ui.draw_index(app, 1328, 876, 272)
    assert "Combine" in app.canvas.words()
    assert "+2.4" in app.canvas.words()
    assert "74.1" in app.canvas.words()
    assert "No combine yet • start one from the 3D Range" in app.canvas.words()
    tags = [options.get("tags") for _, _, options in app.canvas.items]
    assert "index-score-pane" in tags
    assert "index-combine-pane" in tags
    assert "index-sparkline" in tags
    assert app.concept_index_combine_rect


def test_setup_tab_shortcuts_keep_real_actions_and_honest_board_state(monkeypatch):
    import obs_server

    monkeypatch.setattr(
        obs_server,
        "pressure_manager",
        SimpleNamespace(is_simulator=False, backend=None),
    )
    calls = []
    app = SimpleNamespace(
        canvas=Canvas(),
        is_left_handed=False,
        aim_offset_deg=0,
        ui_scale_choice="Auto",
        open_shot_source_picker=lambda: calls.append("source"),
        open_log_folder=lambda: calls.append("logs"),
        draw_screen=lambda: calls.append("draw"),
    )
    ui.draw_setup(app, 1328, 876, 272)
    assert "No local board connected" in app.canvas.words()
    assert app.canvas.words().count("Not assigned") == 2
    assert all(
        key in app.concept_setup_actions
        for key in ("overview", "details", "display", "data", "logs", "aim", "boards")
    )
    for action in ("data", "logs", "display", "aim", "boards"):
        rect = app.concept_setup_actions[action]
        assert ui.handle_setup_click(app, rect[0] + 2, rect[1] + 2)
    assert app.show_tools_menu
    assert app.show_aim_modal
    assert app.concept_setup_page == "details"
    assert "source" in calls and "logs" in calls


def test_index_combine_whole_button_routes_existing_range_launcher():
    calls = []
    app = SimpleNamespace(
        concept_index_combine_rect=(100, 200, 300, 260),
        launch_3d_range=lambda: calls.append("range"),
    )
    assert ui.handle_index_click(app, 102, 202)
    assert calls == ["range"]
    assert not ui.handle_index_click(app, 99, 200)
    assert calls == ["range"]
