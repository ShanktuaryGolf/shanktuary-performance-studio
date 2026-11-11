"""CoP decay uses elapsed time; stale/live/review/demo stay distinct."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_concept_ui import desktop  # noqa: F401
from test_lab_pressure_honesty import Canvas

import obs_server
from shanktuary_performance_studio import ShanktuaryApp
from src.ui import concept_workspaces
from src.ui.desktop import ShanktuaryDesktopApp
from src.ui.lab_pressure_view import (
    COP_TRAIL_SECONDS,
    cop_trail_segments,
    current_live_frame,
    sync_live_history,
)


def frame(stamp=100, x=10, load=80):
    return {'timestamp': stamp, 'cop_x': x, 'cop_y': 12, 'total_kg': load,
            'raw_cells': [10, 20, 20, 30], 'pct_left': 37.5, 'pct_right': 62.5,
            'phase': 'Address'}


def manager(latest=None):
    return SimpleNamespace(backend=SimpleNamespace(is_open=True), latest_frame=latest,
                           pressure_source='wbb', board_mode='dual', is_simulator=False,
                           assigned_left='a', assigned_right='b')


@pytest.mark.parametrize('hz', [10, 20, 100])
def test_elapsed_time_not_sample_count_controls_decay(hz):
    frames = [frame(98 + i / hz) for i in range(2 * hz + 1)]
    before = deepcopy(frames)
    segments = cop_trail_segments(frames, 100)
    assert segments
    assert min(first['timestamp'] for first, _, _ in segments) >= 100 - COP_TRAIL_SECONDS
    assert segments[0][2] < segments[-1][2] == 1
    assert cop_trail_segments(frames, 102) == []
    assert frames == before


def test_repeated_stationary_paints_fade_without_refreshing_history():
    frames = [frame(99.5), frame(99.6)]
    first = cop_trail_segments(frames, 100)[0][2]
    second = cop_trail_segments(frames, 100.5)[0][2]
    assert 0 < second < first
    assert cop_trail_segments(frames, 102) == []


def test_stored_review_retains_loaded_trace_when_final_sample_is_unloaded():
    samples = [frame(1), frame(1.1), frame(1.2, load=0)]
    assert len(cop_trail_segments(samples, 10000, stored=True)) == 1


@pytest.mark.parametrize('change', [{'timestamp': None}, {'timestamp': float('nan')},
                                   {'timestamp': 101}, {'cop_x': float('inf')},
                                   {'cop_y': True}, {'total_kg': 0}])
def test_bad_or_unloaded_points_break_path(change):
    bad = frame(99.9)
    bad.update(change)
    assert cop_trail_segments([frame(99.8), bad, frame(100)], 100) == []


def test_stale_disconnect_and_invalid_sensor_fail_closed():
    pm = manager(frame())
    assert current_live_frame(pm, 100) is pm.latest_frame
    assert current_live_frame(pm, 101.6) is None
    pm.backend.is_open = False
    assert current_live_frame(pm, 100) is None
    class Invalid:
        is_open = True
        def get_diagnostics(self):
            return {'recovery_blocked': True}
    pm.backend = Invalid()
    assert current_live_frame(pm, 100) is None
    for stamp in (None, float('nan'), float('inf'), 101, True):
        pm.backend = SimpleNamespace(is_open=True)
        pm.latest_frame = frame(stamp)
        assert current_live_frame(pm, 100) is None


def test_history_deduplicates_resumes_and_never_changes_stored_trace():
    pm = manager(frame())
    stored = [frame(1)]
    app = SimpleNamespace(swing_lab_history=[], current_shot={'pressure_trace': stored})
    for _ in range(10):
        assert sync_live_history(app, pm, 100) is pm.latest_frame
    assert len(app.swing_lab_history) == 1
    assert sync_live_history(app, pm, 102) is None
    assert app.swing_lab_history == []
    pm.latest_frame = frame(103)
    sync_live_history(app, pm, 103)
    assert app.swing_lab_history == [pm.latest_frame]
    assert stored == [frame(1)]


@pytest.mark.parametrize('attribute,value', [('pressure_source', 'openfp'), ('board_mode', 'single'),
                                           ('assigned_left', 'different'), ('is_simulator', True),
                                           ('backend', SimpleNamespace(is_open=True))])
def test_source_change_rejects_old_frame_until_new_data(attribute, value):
    pm = manager(frame())
    app = SimpleNamespace(swing_lab_history=[])
    sync_live_history(app, pm, 100)
    setattr(pm, attribute, value)
    assert sync_live_history(app, pm, 100) is None
    assert app.swing_lab_history == []
    pm.latest_frame = frame(100.1, x=40)
    sync_live_history(app, pm, 100.1)
    assert app.swing_lab_history == [pm.latest_frame]


def painter(monkeypatch, samples, *, reviewing=False, demo=False):
    monkeypatch.setattr('time.monotonic', lambda: 100)
    app = ShanktuaryApp.__new__(ShanktuaryApp)
    app.canvas = Canvas()
    app.is_left_handed = False
    app.swing_lab_history = samples
    app.pressure_display_trail = lambda: (samples, reviewing)
    app.is_reviewing_past_shot = lambda: reviewing
    app.lab_demo_running = demo
    app.lab_demo_started = 96  # Demo's clock now equals 8, not 100.
    return app


def tagged(app, name):
    return [item for item in app.canvas.items if item[2].get('tags') == name]


def test_historical_painter_keeps_path_without_fabricating_unloaded_dot(monkeypatch):
    samples = [frame(1), frame(1.1), frame(1.2, load=0)]
    app = painter(monkeypatch, samples, reviewing=True)
    app.draw_cop_trajectory_canvas(0, 0, 400, 300, latest=samples[-1])
    assert tagged(app, 'cop-trail')
    assert not tagged(app, 'cop-current')


def test_demo_painter_uses_elapsed_preview_clock(monkeypatch):
    samples = [frame(7.7), frame(7.8), frame(8)]
    app = painter(monkeypatch, samples, demo=True)
    app.draw_cop_trajectory_canvas(0, 0, 400, 300, latest=samples[-1])
    assert len(tagged(app, 'cop-trail')) == 2
    assert tagged(app, 'cop-current')


def test_live_painter_never_draws_stale_current_dot(monkeypatch):
    samples = [frame(95), frame(95.1)]
    app = painter(monkeypatch, samples)
    app.draw_cop_trajectory_canvas(0, 0, 400, 300, latest=samples[-1])
    assert not tagged(app, 'cop-trail') and not tagged(app, 'cop-current')


def test_live_lab_does_not_borrow_last_shot_on_disconnect(monkeypatch):
    pm = manager(frame(10))
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    app = painter(monkeypatch, [frame(10)])
    app.current_shot = {'pressure_trace': [frame(1, x=88)]}
    app.get_pressure_trace = lambda shot: shot['pressure_trace']
    concept_workspaces.draw_lab(app, 1300, 900, 260)
    words = app.canvas.words()
    assert 'Live pressure unavailable' in words
    assert 'Local board data' not in words
    assert not tagged(app, 'cop-current')
    assert not any(word.endswith(' kg') for word in words)


def test_first_fresh_frame_does_not_use_old_force_curve(monkeypatch):
    pm = manager(frame(100))
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    app = painter(monkeypatch, [pm.latest_frame])
    app.pressure_display_trail = lambda: ([frame(1), frame(1.1)], True)
    app.draw_force_timeline_canvas(0, 0, 400, 300)
    assert 'No swing captured yet' in app.canvas.words()
    assert 'No pressure trace captured for this shot' not in app.canvas.words()


def test_desktop_repaints_stationary_and_stale_lab(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('time.monotonic', lambda: clock[0])
    pm = manager(frame(100))
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    app = SimpleNamespace(swing_lab_history=[], view_mode=8, show_board_assign_modal=False,
                          root=SimpleNamespace(after=Mock()), tick_setup_flow=Mock(), draw_screen=Mock(),
                          poll_pressure_stream=Mock())
    for moment in (100, 100.2, 102):
        clock[0] = moment
        ShanktuaryDesktopApp.poll_pressure_stream(app)
    assert app.draw_screen.call_count == 3
    assert app.swing_lab_history == []
    assert app.root.after.call_count == 3


def test_desktop_clears_history_and_repaints_when_manager_removed(monkeypatch):
    monkeypatch.setattr('time.monotonic', lambda: 100)
    monkeypatch.setattr(obs_server, 'pressure_manager', None)
    app = SimpleNamespace(swing_lab_history=[frame(99.9)], view_mode=8,
                          show_board_assign_modal=False, root=SimpleNamespace(after=Mock()),
                          tick_setup_flow=Mock(), draw_screen=Mock(), poll_pressure_stream=Mock())
    ShanktuaryDesktopApp.poll_pressure_stream(app)
    assert app.swing_lab_history == []
    app.draw_screen.assert_called_once()
    app.tick_setup_flow.assert_not_called()


def test_historical_string_coordinates_draw_validated_numbers(monkeypatch):
    samples = [dict(frame(1), cop_x='20', cop_y='12'), dict(frame(1.1), cop_x='21', cop_y='13')]
    app = painter(monkeypatch, samples, reviewing=True)
    app.draw_cop_trajectory_canvas(0, 0, 400, 300, latest=samples[-1])
    assert tagged(app, 'cop-trail') and tagged(app, 'cop-current')


def test_removed_then_restored_manager_does_not_reintroduce_old_frame():
    pm = manager(frame(100))
    app = SimpleNamespace(swing_lab_history=[])
    sync_live_history(app, pm, 100)
    assert sync_live_history(app, None, 100.1) is None
    assert sync_live_history(app, pm, 100.2) is None
    assert app.swing_lab_history == []
    pm.latest_frame = frame(100.3)
    assert sync_live_history(app, pm, 100.3) is pm.latest_frame
    assert app.swing_lab_history == [pm.latest_frame]


@pytest.mark.parametrize("scale", [.735, 1, 1.25, 2])
def test_whole_lab_panel_headers_clear_captions_and_graph_annotations(monkeypatch, scale):
    import tkinter as tk

    from src.ui.concept_canvas import ViewportCanvas
    from src.ui.lab_demo import demo_frame
    from src.ui.scaling import ScaledCanvas

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("graphical display required")
    try:
        import theme
        root.tk.call("tk", "scaling", 96 / 72 * scale)
        monkeypatch.setattr(theme, "_UI_FONT", theme._resolve_ui_font())
        real = ScaledCanvas(root, scale=scale, width=1560 * scale, height=1024 * scale)
        real.pack()
        app = ShanktuaryDesktopApp.__new__(ShanktuaryDesktopApp)
        app.root = root
        app.canvas = ViewportCanvas(real)
        app.view_mode = 8
        app.is_left_handed = False
        app.current_shot = app.lab_demo_selected_shot = None
        app.lab_demo_running = True
        app.lab_demo_started = 100
        app.lab_demo_frames = [demo_frame(4 - i * .05) for i in reversed(range(81))]
        app.swing_lab_history = []
        app.is_reviewing_past_shot = lambda: False
        monkeypatch.setattr('time.monotonic', lambda: 100)
        monkeypatch.setattr(obs_server, 'pressure_manager', None)
        assert app.pressure_display_trail()[0] is app.lab_demo_frames
        assert any(item['phase'] == 'Impact' for item in app.lab_demo_frames)
        concept_workspaces.draw_lab(app, 1300, 900, 260)
        root.update_idletasks()
        for item in real.find_withtag("estimated-foot-label"):
            font = real.tk.splitlist(real.itemcget(item, "font"))
            assert abs(int(font[1])) >= max(1, round(9 * scale)), (real.itemcget(item, "text"), font)
        title_ids = real.find_withtag("lab-panel-title")
        caption = real.bbox(real.find_withtag("lab-foot-caption")[0])
        foot_title = next(i for i in title_ids if real.itemcget(i, "text") == "Estimated foot load")
        assert real.bbox(foot_title)[3] <= caption[1]
        sides = [i for i in real.find_withtag("estimated-foot-label")
                 if "SIDE (" in real.itemcget(i, "text")]
        assert len(sides) == 2
        assert caption[3] <= min(real.bbox(i)[1] for i in sides)
        lower_titles = [i for i in title_ids
                        if real.itemcget(i, "text") in ("Weight transfer", "Force curve")]
        assert len(lower_titles) == 2
        annotations = [i for i in real.find_all() if real.type(i) == "text"
                       and real.itemcget(i, "text") in ("impact", "lead", "trail", "total")]
        assert annotations
        for title in lower_titles:
            a = real.bbox(title)
            for item in annotations:
                b = real.bbox(item)
                assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (scale, real.itemcget(title, "text"))
    finally:
        root.destroy()


@pytest.mark.parametrize("scale", [.735, 1, 1.5])
def test_actual_desktop_demo_keeps_foot_captions_readable(desktop, scale):
    from src.ui import lab_demo

    app, root, errors = desktop
    app.set_ui_scale("100%", persist=False)
    app.ui_scale = app.canvas.ui_scale = scale
    root.tk.call("tk", "scaling", 96 / 72 * scale)
    app.view_mode = 8
    try:
        lab_demo.toggle(app)
        root.update()
        app.draw_screen()
        root.update_idletasks()
        labels = app.canvas.find_withtag("estimated-foot-label")
        assert len(labels) >= 14
        boxes = []
        for item in labels:
            value = app.canvas.itemcget(item, "text")
            font = root.tk.splitlist(app.canvas.itemcget(item, "font"))
            assert abs(int(font[1])) >= max(1, round(9 * scale)), (value, font)
            boxes.append((value, app.canvas.bbox(item)))
        for index, (label, a) in enumerate(boxes):
            for other, b in boxes[index + 1:]:
                assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (scale, label, other)
        assert not errors
    finally:
        lab_demo.stop(app)
