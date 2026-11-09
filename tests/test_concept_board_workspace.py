"""Unified calibration retains real actions and truthful interrupted state."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_guided_setup_flow import FakePM

import obs_server
from src.ui import concept_boards as ui
from src.ui.desktop import ShanktuaryDesktopApp


class Canvas:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record

    def words(self):
        return [kwargs['text'] for name, _, kwargs in self.calls if name == 'create_text']


class Manager(FakePM):
    def __init__(self):
        super().__init__()
        self.pressure_source = 'wbb'
        self.devices = ['board-one', 'board-two']
        self.assigned_left, self.assigned_right = self.devices
        self.backend = SimpleNamespace(is_open=True)
        self.latest_frame = {'timestamp': ui.time.monotonic()}

    def enumerate_boards(self, max_age_sec=1):
        return list(self.devices)

    def cancel_stance_alignment(self):
        self.calls.append('align_cancel')
        self._align_active = False
        self._align_msg = 'Alignment cancelled'


@pytest.fixture
def workspace(monkeypatch):
    app = ShanktuaryDesktopApp.__new__(ShanktuaryDesktopApp)
    app.canvas = Canvas()
    app.root = SimpleNamespace(after=Mock())
    app.draw_screen = Mock()
    app.clear_copy_feedback = Mock()
    app.view_mode = 10
    app.concept_setup_page = 'details'
    app.show_pairing_modal = app.show_board_assign_modal = app.show_aim_modal = False
    pm = Manager()
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    monkeypatch.setattr(ui, '_pin_details', lambda app: ('PIN unavailable', 'Use Bluetooth settings to pair.'))
    app.setup_pin_text = ''
    return app, pm


def render(app, guided=False):
    app.canvas.calls.clear()
    ui.draw(app, 1328, 876, 272, guided=guided)
    return app.canvas.words()


def click(app, rect):
    app.handle_mouse_press(SimpleNamespace(x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2))


def test_all_five_stages_share_one_workspace_and_existing_actions(workspace):
    app, pm = workspace
    before = list(pm.calls)
    words = render(app)
    assert all(label in words for _, label in ui.STAGES)
    assert 'Pair boards (local)' in words
    assert 'Start step-on wizard  →' in words
    assert 'Ready for practice' not in words
    assert app.setup_pair_rect and app.setup_align_rect and app.setup_stance_rect and app.setup_tare_rect
    assert app.setup_mode_1_rect and app.setup_mode_2_rect
    assert app.setup_assign_left_rects[0][1] == 'board-one'
    assert app.setup_assign_right_rects[1][1] == 'board-two'
    assert pm.calls == before, 'paint must not start device operations'


def test_no_devices_no_fake_load_assignment_or_ready(workspace):
    app, pm = workspace
    pm.devices = []
    pm.backend.is_open = False
    words = render(app)
    assert 'No balance board detected' in words
    assert 'Pair your balance boards.' in words
    assert 'Pair Board  →' in words
    assert app.setup_guided_rect is None
    app.start_pairing_flow = Mock()
    rect = app.board_workspace_rects['primary_pair']
    ui.handle_click(app, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    app.start_pairing_flow.assert_called_once()
    assert 'Not yet calibrated' in words
    assert words.count('—') == 2
    assert not app.setup_assign_left_rects and not app.setup_assign_right_rects
    assert not ui.snapshot(pm)['ready']


def test_demo_is_never_reported_as_verified_hardware(workspace):
    app, pm = workspace
    pm.finish_align()
    pm.finish_width()
    assert ui.snapshot(pm)['ready']
    pm.latest_frame = {'timestamp': 0}
    assert not ui.snapshot(pm)['ready']
    pm.latest_frame = {'timestamp': ui.time.monotonic()}
    pm.is_simulator = True
    words = render(app)
    assert 'DEMO / SIMULATED' in words
    assert 'Demo / simulated · not connected hardware' in words
    assert not ui.snapshot(pm)['paired'] and not ui.snapshot(pm)['ready']


def test_scan_refreshes_real_enumeration_and_multiple_device_pages(workspace):
    app, pm = workspace
    pm.devices += ['board-three']
    enum = Mock(wraps=pm.enumerate_boards)
    pm.enumerate_boards = enum
    render(app)
    rect = app.board_workspace_rects['scan']
    assert ui.handle_click(app, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    enum.assert_called_with(max_age_sec=0)
    assert '3 paired board(s)' in app.copy_feedback
    rect = app.board_workspace_rects['devices']
    ui.handle_click(app, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    render(app)
    assert app.setup_assign_left_rects[0][1] == 'board-three'


@pytest.mark.parametrize('action', ['cancel', 'skip', 'back', 'restart'])
def test_interrupt_alignment_stops_sampler_without_background_completion(workspace, action):
    app, pm = workspace
    app.start_guided_setup()
    pm.assignment_wizard.complete()
    app.tick_setup_flow()
    assert app._flow_step() == 'align' and pm._align_active
    render(app, guided=True)
    if action == 'restart':
        app.start_guided_setup()
    else:
        click(app, getattr(app, f'board_modal_{action}_rect'))
    assert not pm._align_active
    assert 'align_cancel' in pm.calls
    if action == 'cancel':
        assert not app.show_board_assign_modal
    elif action == 'skip':
        assert app._flow_step() == 'width'
        assert app.setup_flow_skipped == ['align']
    else:
        assert app._flow_step() == 'assign'
    assert not ui.snapshot(pm)['ready']


def test_modal_swallows_source_and_pairing_clicks_and_done_clears(workspace):
    app, pm = workspace
    render(app)
    pair = app.setup_pair_rect
    app.start_pairing_flow = Mock()
    app.start_guided_setup()
    render(app, guided=True)
    assert not app.setup_pair_rect and not app.setup_pressure_source_rects
    click(app, pair)
    app.start_pairing_flow.assert_not_called()
    app._skip_setup_flow_step()
    app._skip_setup_flow_step()
    app._skip_setup_flow_step()
    words = render(app, guided=True)
    assert app.setup_flow_done
    assert 'Setup flow finished' in words
    assert 'Ready for practice' not in words
    assert any('Skipped:' in word for word in words)
    click(app, app.board_modal_done_rect)
    assert not app.show_board_assign_modal
    render(app)
    assert app.setup_pair_rect


def test_repeated_open_back_and_modes_cannot_reuse_stale_hit_targets(workspace):
    app, pm = workspace
    from src.ui.concept_workspaces import handle_setup_click
    for _ in range(3):
        render(app)
        rect = app.concept_setup_actions['overview']
        assert handle_setup_click(app, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
        assert app.concept_setup_page == 'overview'
        app.concept_setup_page = 'details'
    pm.pressure_source = 'openfp'
    pm.backend.last_dual_reading = None
    words = render(app)
    assert 'FORCE PLATES' in words and 'MODE' not in words
    assert app.setup_openfp_url_rect and app.setup_openfp_dash_rect
    assert app.setup_pair_rect is None and app.setup_wizard_rect is None
    assert not app.setup_assign_left_rects and not app.setup_mode_1_rect
    pm.pressure_source = 'wbb'
    render(app)
    assert app.setup_openfp_url_rect is None and app.setup_pair_rect


def test_openfp_load_must_be_fresh_and_reported(workspace):
    app, pm = workspace
    pm.pressure_source = 'openfp'
    pm.backend.last_dual_reading = SimpleNamespace(timestamp=0, left=SimpleNamespace(total=99), right=SimpleNamespace(total=99))
    assert render(app).count('—') == 2
    pm.backend.last_dual_reading.timestamp = ui.time.monotonic()
    pm.backend.last_dual_reading.left.total = 0
    pm.backend.last_dual_reading.right.total = 42.1
    words = render(app)
    assert '0.0' in words and '42.1' in words


def test_real_alignment_cancel_does_not_save_and_old_configuration_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(obs_server, 'CALIBRATION_FILE', str(tmp_path/'calibration.json'))
    pm = obs_server.PressureManager()
    pm._save_calibration = Mock()
    pm.start_stance_alignment()
    pm._alignment_samples = [(40, 30)]*40
    pm.cancel_stance_alignment()
    pm._finish_stance_alignment()  # a worker finishing after Cancel must be harmless
    pm._save_calibration.assert_not_called()
    assert pm.get_alignment_status()['message'] == 'Alignment cancelled'
    assert pm.balance_multiplier == [1, 1]
    pm.start_stance_alignment()
    pm._alignment_samples = [(40, 30)]*40
    pm._finish_stance_alignment()
    assert pm.get_alignment_status()['configuration_matches']
    pm.board_mode = 'dual'
    assert not pm.get_alignment_status()['configuration_matches']
    assert not ui.snapshot(pm)['aligned']


@pytest.fixture
def desktop_workspace(tmp_path, monkeypatch):
    import tkinter as tk

    import shanktuary_performance_studio as production

    monkeypatch.setenv('SPS_UI_PREVIEW', '1')
    monkeypatch.setenv('SPS_SHOT_SOURCE_FILE', str(tmp_path/'source.json'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    monkeypatch.setattr(production, 'SESSION_LOG_PATH', str(tmp_path/'history.json'))
    monkeypatch.setattr(obs_server, 'CALIBRATION_FILE', str(tmp_path/'calibration.json'))
    pm = Manager()
    pm.latest_frame = None
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('graphical display required')
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    app = ShanktuaryDesktopApp(root)
    root.geometry('1600x1000+0+0')
    root.update()
    yield app, root, pm, errors
    root.destroy()


@pytest.mark.parametrize('scale', ['100%', '150%', '200%'])
def test_native_workspace_back_skip_cancel_and_repeated_navigation(desktop_workspace, scale):
    app, root, pm, errors = desktop_workspace
    app.set_ui_scale(scale, persist=False)
    root.update()

    def physical_click(rect):
        # Bring the intended button into the scrollable native viewport first.
        app.canvas.xview_moveto(0)
        app.canvas.yview_moveto(0)
        x = round((rect[0]+rect[2])/2*app.ui_scale - app.canvas.canvasx(0))
        y = round((rect[1]+rect[3])/2*app.ui_scale - app.canvas.canvasy(0))
        app.canvas.event_generate('<Button-1>', x=x, y=y)
        root.update()

    app.set_mode(10)
    physical_click(app.concept_setup_actions['details'])
    assert app.concept_setup_page == 'details'
    assert app.setup_pair_rect and app.setup_guided_rect
    physical_click(app.setup_guided_rect)
    assert app.show_board_assign_modal
    pm.assignment_wizard.complete()
    app.tick_setup_flow()
    app.draw_screen()
    physical_click(app.board_modal_back_rect)
    assert app._flow_step() == 'assign'
    assert not pm._align_active
    physical_click(app.board_modal_skip_rect)
    assert app._flow_step() == 'align'
    physical_click(app.board_modal_cancel_rect)
    assert not app.show_board_assign_modal and not pm._align_active
    physical_click(app.concept_setup_actions['overview'])
    assert app.concept_setup_page == 'overview'
    physical_click(app.concept_setup_actions['details'])
    physical_click(app.setup_guided_rect)
    assert app.setup_flow_skipped == []
    physical_click(app.board_modal_cancel_rect)
    assert not errors


def test_native_workspace_text_and_controls_are_bounded(desktop_workspace):
    app, root, pm, errors = desktop_workspace
    app.set_ui_scale('100%', persist=False)
    app.set_mode(10)
    app.concept_setup_page = 'details'
    app.draw_screen()
    root.update()
    for guided in (False, True):
        if guided:
            app.start_guided_setup()
            app.draw_screen()
            root.update()
        for item in app.canvas.find_all():
            if app.canvas.type(item) != 'text':
                continue
            box = app.canvas.bbox(item)
            if box and box[0] >= 272:
                assert box[2] <= 1600 and box[3] <= 1000, (app.canvas.itemcget(item, 'text'), box)
        for name in ('board_modal_cancel_rect', 'board_modal_skip_rect') if guided else ('setup_pair_rect', 'setup_guided_rect', 'setup_tare_rect'):
            rect = getattr(app, name)
            assert 272 <= rect[0] < rect[2] <= 1600
            assert 176 <= rect[1] < rect[3] <= 1000
    assert not errors


def test_keyboard_cancel_owns_flow_and_stops_alignment(workspace):
    app, pm = workspace
    app.start_guided_setup(['align', 'width'])
    assert app.handle_key_press(SimpleNamespace(keysym='Escape')) == 'break'
    assert not app.show_board_assign_modal and not pm._align_active
    app.start_guided_setup(['align', 'width'])
    assert app.handle_key_press(SimpleNamespace(keysym='s')) == 'break'
    assert app._flow_step() == 'width' and not pm._align_active


def test_native_manual_assignment_and_tare_keep_production_handlers(desktop_workspace):
    app, root, pm, errors = desktop_workspace
    app.set_ui_scale('100%', persist=False)
    app.set_mode(10)
    app.concept_setup_page = 'details'
    pm.assign_boards = Mock(return_value={'status': 'ok', 'connected': True})
    pm.tare = Mock(return_value=False)
    app.draw_screen()
    root.update()
    click(app, app.setup_assign_left_rects[1][0])
    pm.assign_boards.assert_called_once_with('board-two', 'board-one')
    click(app, app.setup_tare_rect)
    pm.tare.assert_called_once()
    assert app.copy_feedback == 'No pressure data available to tare'
    pm.tare.return_value = True
    click(app, app.setup_tare_rect)
    assert app.copy_feedback == '✓ Boards tared'
    assert not errors


@pytest.mark.parametrize('mode', ['single', 'dual'])
def test_openfp_mode_choices_explicitly_switch_back_to_wii(workspace, mode):
    app, pm = workspace
    pm.pressure_source = 'openfp'
    calls = []
    def select_source(source):
        calls.append(('source', source))
        pm.pressure_source = source
    def select_mode(selected):
        calls.append(('mode', selected))
        pm.board_mode = selected
    pm.set_pressure_source = select_source
    pm.set_board_mode = select_mode
    render(app)
    assert calls == []
    rect = app.board_workspace_rects['switch_wbb_' + mode]
    assert ui.handle_click(app, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    assert calls == [('source', 'wbb'), ('mode', mode)]
    render(app)
    assert not any(key.startswith('switch_wbb_') for key in app.board_workspace_rects)
    assert app.setup_mode_1_rect and app.setup_mode_2_rect
    pm.pressure_source = 'openfp'
    render(app, guided=True)
    assert not any(key.startswith('switch_wbb_') for key in app.board_workspace_rects)
