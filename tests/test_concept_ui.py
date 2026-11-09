"""Interaction contracts for the expanded concept shell and viewport.

Public control rectangles are expressed in visible canvas coordinates. These
tests click those physical positions, including translated production controls.
"""
from types import SimpleNamespace

import pytest

from src.ui.concept_canvas import ViewportCanvas


def test_viewport_translates_geometry_without_changing_width():
    class Canvas:
        def create_rectangle(self, *coords, **options):
            return coords, options
        def winfo_width(self): return 1600
        def winfo_height(self): return 1000
    canvas = ViewportCanvas(Canvas())
    assert canvas.create_rectangle(260, 52, 500, 100)[0] == (260, 176, 500, 224)
    assert canvas.create_rectangle([260, 52, 500, 100])[0] == (260, 176, 500, 224)
    assert (canvas.winfo_width(), canvas.winfo_height()) == (1600, 876)


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    import tkinter as tk

    import shanktuary_performance_studio as studio
    from src.ui.desktop import ShanktuaryDesktopApp
    monkeypatch.setenv('SPS_SHOT_SOURCE_FILE', str(tmp_path/'source.json'))
    monkeypatch.setattr(studio, 'SESSION_LOG_PATH', str(tmp_path/'history.json'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('graphical display required')
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    app = ShanktuaryDesktopApp(root)
    root.geometry('1600x1000+0+0')
    root.update()
    yield app, root, errors
    root.destroy()


def click(app, root, rect, offset=0):
    x=(rect[0]+rect[2])/2
    y=(rect[1]+rect[3])/2+offset
    app.handle_mouse_press(SimpleNamespace(x=x, y=y, num=1))
    root.update()


@pytest.mark.parametrize('mode',[12,1,4,5,2,3,6,7,8,11,10])
def test_each_workspace_renders_and_nav_selects(desktop, mode):
    app, root, errors = desktop
    click(app, root, app.design_mode_rects[mode])
    assert app.view_mode == mode
    assert app.canvas.find_all()
    assert not errors


def test_header_new_session_and_session_menu(desktop):
    app, root, errors = desktop
    before=len(app.sessions)
    click(app,root,next(r for r,a in app.concept_actions if a=='new'))
    assert len(app.sessions)==before+1
    click(app,root,next(r for r,a in app.concept_actions if a=='sessions'))
    assert app.view_mode == 13
    assert app.concept_history_rects
    assert not errors


def test_combined_overview_preserves_selection_pressure_and_legacy_route(desktop):
    app, root, errors = desktop
    shots = [
        {"club": "Driver", "pressure_trace": []},
        {"club": "7 Iron", "pressure_trace": []},
    ]
    app.get_active_session()["shots"] = shots
    app.current_shot = shots[-1]
    app.selected_shot_index = 1
    app.get_pressure_trace = lambda shot: ([{"rel_time_s": 0, "pct_left": 25, "pct_right": 75}]
                                         if shot is shots[0] else [])
    app.set_mode(9)
    root.update()
    assert app.view_mode == 12
    assert 9 not in app.design_mode_rects
    labels = [app.canvas.itemcget(i, "text") for i in app.canvas.find_all()
              if app.canvas.type(i) == "text"]
    for title in ("Recent Shots", "Session Trends", "Shot Shape Mix", "Pressure & balance", "Pressure transfer"):
        assert title in labels
    old = next(r[:4] for r in app.design_shot_card_rects if r[4] == 0)
    click(app, root, old)
    assert app.current_shot is shots[0]
    labels = [app.canvas.itemcget(i, "text") for i in app.canvas.find_all()
              if app.canvas.type(i) == "text"]
    assert "Lead 25%" in labels
    assert "At impact · selected shot" in labels
    app.handle_scroll_delta(5)
    assert app.canvas.yview()[0] > 0
    app.set_mode(1)
    assert app.canvas.yview()[0] == 0
    assert not errors


def test_tools_menu_opens_and_scale_button_uses_viewport(desktop):
    app,root,errors=desktop
    click(app,root,next(r for r,a in app.concept_actions if a=='tools'))
    assert app.view_mode == 14
    click(app,root,next(r for r,a in app.concept_tools_rects if a=="legacy_tools"))
    assert app.show_tools_menu
    old=app.ui_scale
    click(app,root,app.ui_scale_controls['plus'])
    assert app.ui_scale>old
    assert not errors


def test_dispersion_split_control_uses_rendered_position(desktop):
    app,root,errors=desktop
    app.set_mode(3)
    root.update()
    before=app.dispersion_split_by_ball
    click(app,root,app.dispersion_split_rect)
    assert app.dispersion_split_by_ball != before
    assert not errors


def test_range_browser_button_opens_real_range_url(desktop, monkeypatch):
    import shanktuary_performance_studio as studio
    app, root, errors = desktop
    opened = []
    monkeypatch.setattr(studio.webbrowser, 'open', opened.append)
    app.set_mode(2)
    root.update()
    click(app, root, app.range_launch_web_rect)
    assert opened == ['http://localhost:9321/range']
    assert app.view_mode == 2
    assert not errors


@pytest.mark.parametrize("scale", ["100%", "150%", "200%"])
def test_range_launch_survives_navigation_and_repeat_at_scale(desktop, monkeypatch, scale):
    """Range entry works through real scaled canvas events, not only method calls."""
    import shanktuary_performance_studio as studio
    app, root, errors = desktop
    opened = []
    monkeypatch.setattr(studio.webbrowser, "open", opened.append)
    root.geometry("3840x2160")
    app.set_ui_scale(scale, persist=False)
    root.update()

    def physical_click(rect):
        x = round((rect[0] + rect[2]) / 2 * app.ui_scale - app.canvas.canvasx(0))
        y = round((rect[1] + rect[3]) / 2 * app.ui_scale - app.canvas.canvasy(0))
        app.canvas.event_generate("<Button-1>", x=x, y=y)
        root.update()

    for _ in range(2):
        app.set_mode(12)
        root.update()
        physical_click(app.design_mode_rects[2])
        assert app.view_mode == 2
        physical_click(app.range_launch_web_rect)
        assert app.view_mode == 2
    assert opened == ["http://localhost:9321/range"] * 2
    assert not errors


def test_range_target_menu_stays_above_footer_and_selects(desktop):
    app, root, errors = desktop
    app.set_mode(2)
    root.update()
    target = next(rect for rect, action in app.concept_range_rects if action == 'target')
    click(app, root, target)
    choices = [(rect, action) for rect, action in app.concept_range_rects if action.startswith('target:')]
    assert len(choices) == 6
    for rect, _action in choices:
        assert rect[0] < rect[2] and rect[1] < rect[3]
        assert rect[3] <= target[1]
    click(app, root, next(rect for rect, action in choices if action == 'target:200'))
    assert app.concept_range_target == 200
    assert not app.concept_range_target_open
    assert not errors


def test_aim_dialog_measurements_and_draft_nudge_remain_interactive(desktop):
    app, root, errors = desktop
    app.show_aim_modal=True
    app.concept_aim_tab='measure'
    app.aim_modal_distance='20'
    app.aim_modal_lateral='12'
    app.draw_screen()
    root.update()
    assert app.aim_modal_box_rect[2]-app.aim_modal_box_rect[0] == 850
    previous=app.aim_offset_deg
    click(app,root,next(rect for rect,action in app.concept_aim_rects if action=='nudge:0.1'))
    assert float(app.aim_modal_lateral)>12
    assert app.aim_offset_deg==previous
    click(app,root,app.aim_modal_field_rects['distance'])
    assert app.aim_modal_active_field=='distance'
    click(app,root,next(rect for rect,action in app.concept_aim_rects if action=='cancel'))
    assert not app.show_aim_modal
    assert not errors


def test_index_combine_button_opens_real_browser_range(desktop, monkeypatch):
    import shanktuary_performance_studio as studio
    app,root,errors=desktop
    opened=[]
    monkeypatch.setattr(studio.webbrowser,'open',opened.append)
    app.set_mode(11)
    root.update()
    click(app,root,app.concept_index_combine_rect)
    assert opened==['http://localhost:9321/range']
    assert not errors


def test_dispersion_pages_and_view_tabs_use_visible_hit_targets(desktop):
    app, root, errors = desktop
    shots = [{"club": "7 Iron", "ball": f"Ball {i}", "open_golf_coach": {
        "us_customary_units": {"carry_distance_yards": 140 + i,
        "offline_distance_yards": i - 8, "peak_height_yards": 25}}} for i in range(18)]
    app.get_active_session()["shots"] = shots
    app.dispersion_split_by_ball = True
    app.set_mode(3)
    root.update()
    assert app.dispersion_page_rects
    rect, page = next((r, p) for r, p in app.dispersion_page_rects if p == 1)
    click(app, root, rect)
    assert app.dispersion_group_page == page
    for mode in ('side', 'topdown', 'split'):
        rect = next(r for r, key in app.design_dispersion_tab_rects if key == mode)
        click(app, root, rect)
        assert app.dispersion_view_submode == mode
        assert app.dispersion_group_page == 1
    assert len(app.session_shots) == 18
    assert not errors
