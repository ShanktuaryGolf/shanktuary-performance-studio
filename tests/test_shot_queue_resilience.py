"""Malformed telemetry must neither mutate native nested data nor stop polling."""
import copy
import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import shanktuary_performance_studio as studio


@pytest.fixture
def app(monkeypatch):
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.root = SimpleNamespace(after=Mock())
    app.aim_offset_deg = 0
    app.current_club = '7 Iron'
    app.current_ball = None
    app.bag = []
    app.sessions = [{'shots': []}]
    app.active_session_index = 0
    app.aim_calibrating = False
    app.get_club_color = Mock(return_value='green')
    app._stamp_equipment = Mock()
    app.save_session_to_file = Mock()
    app.draw_screen = Mock()
    app.apply_range_club = Mock()
    app.apply_range_combine = Mock()
    for name in ('shot_queue', 'club_select_queue', 'combine_queue'):
        monkeypatch.setattr(studio, name, queue.Queue())
    monkeypatch.setattr(studio.obs_server.obs_state, 'push_shot', Mock())
    return app


@pytest.mark.parametrize('ogc', [None, [], 'bad', {'us_customary_units': None},
                                  {'us_customary_units': []}])
def test_malformed_optional_objects_are_read_time_only(app, ogc):
    native = {'open_golf_coach': ogc, 'vertical_launch_angle_degrees': 12}
    original = copy.deepcopy(native)
    for offset in (0, 3):
        app.aim_offset_deg = offset
        view = app.aim_corrected(native)
        assert isinstance(view['open_golf_coach'], dict)
        assert isinstance(view['open_golf_coach']['us_customary_units'], dict)
        assert native == original
        assert app.extract_shot_metrics(native)['carry'] == 0


def test_bad_event_and_render_failure_do_not_strand_following_shots(app):
    broken = {'open_golf_coach': None}
    valid = {'open_golf_coach': {}, 'id': 'next'}
    for msg in (None, broken, valid):
        studio.shot_queue.put(msg)
    app.draw_screen.side_effect = [RuntimeError('renderer failed'), None, None]
    studio.club_select_queue.put('7 Iron')
    studio.combine_queue.put({'enabled': False})
    app.poll_queue()
    assert app.sessions[0]['shots'] == [broken, valid]
    assert broken['open_golf_coach'] is None
    assert broken['_data_quality']['suspect']
    assert app.current_shot is valid
    assert app._stamp_equipment.call_count == 2
    assert studio.shot_queue.empty()
    app.apply_range_club.assert_called_once_with('7 Iron')
    app.apply_range_combine.assert_called_once_with({'enabled': False})
    app.root.after.assert_called_once_with(100, app.poll_queue)


def test_control_failure_is_isolated_and_next_tick_is_scheduled(app):
    app.apply_range_club.side_effect = RuntimeError('bad club')
    studio.club_select_queue.put('bad')
    studio.combine_queue.put('next')
    app.poll_queue()
    app.apply_range_combine.assert_called_once_with('next')
    app.root.after.assert_called_once_with(100, app.poll_queue)


def test_unexpected_queue_failure_still_reschedules(app, monkeypatch):
    monkeypatch.setattr(studio, 'shot_queue', SimpleNamespace(get_nowait=Mock(side_effect=RuntimeError('queue failed'))))
    with pytest.raises(RuntimeError, match='queue failed'):
        app.poll_queue()
    app.root.after.assert_called_once_with(100, app.poll_queue)


@pytest.mark.parametrize('nested', [None, {'us_customary_units': None}])
def test_gui_can_redraw_historical_malformed_shot(nested, tmp_path, monkeypatch):
    tk = pytest.importorskip('tkinter')
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('no display available')
    monkeypatch.setenv('SPS_SKIP_SPLASH', '1')
    monkeypatch.setattr(studio, 'SESSION_LOG_PATH', str(tmp_path / 'history.json'))
    from src.ui.desktop import ShanktuaryDesktopApp
    try:
        root.geometry('1400x900')
        application = ShanktuaryDesktopApp(root)
        shot = {'club': '7 Iron', 'open_golf_coach': nested,
                'ball_speed_meters_per_second': 40, 'vertical_launch_angle_degrees': 15}
        application.sessions = [{'id': 'test', 'name': 'Test', 'shots': [shot]}]
        application.active_session_index = 0
        application.selected_shot_index = 0
        application.current_shot = shot
        application.view_mode = 1
        application.draw_screen()
        root.update_idletasks()
        application.persistence_error = 'History was not saved: storage unavailable'
        application.draw_screen()
        texts = [application.canvas.itemcget(item, 'text')
                 for item in application.canvas.find_all()
                 if application.canvas.type(item) == 'text']
        assert application.persistence_error in texts
        assert shot['open_golf_coach'] is nested
    finally:
        root.destroy()
