"""Current identified board loads never come from a completion snapshot."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_concept_board_workspace import desktop_workspace as desktop_workspace
from test_concept_board_workspace import render
from test_concept_board_workspace import workspace as workspace

from src.ui import concept_boards as ui


class CurrentLoads:
    is_open = True
    ready = True
    recovery_blocked = False

    def __init__(self, stamp):
        self.loads = {
            'left': dict(device_id='board-one', total_kg=31.4, timestamp=stamp, fresh=True),
            'right': dict(device_id='board-two', total_kg=47.2, timestamp=stamp, fresh=True),
        }
        self.observations = 0

    def get_board_loads(self):
        self.observations += 1
        return deepcopy(self.loads)

    def get_diagnostics(self):
        return {'ready': self.ready, 'recovery_blocked': self.recovery_blocked}


def install(pm):
    stamp = ui.time.monotonic()
    pm.backend = CurrentLoads(stamp)
    pm.latest_frame = {'timestamp': stamp, 'total_kg': 999, 'pct_left': 50, 'pct_right': 50}
    return pm.backend


def cards(monkeypatch):
    result, original = [], ui._draw_board
    def observe(canvas, rect, label, load, role):
        result.append((label, load, role))
        return original(canvas, rect, label, load, role)
    monkeypatch.setattr(ui, '_draw_board', observe)
    return result


@pytest.mark.parametrize('guided', [False, True])
def test_dual_loads_after_assignment_are_current_not_historical(workspace, monkeypatch, guided):
    app, pm = workspace
    install(pm)
    pm.assignment_wizard = SimpleNamespace(get_status=lambda: {
        'phase': 'complete', 'is_complete': True,
        'board_a_weight': 88, 'board_b_weight': 99,
        'board_a_weight_valid': True, 'board_b_weight_valid': True})
    if guided:
        app.setup_flow_steps, app.setup_flow_index = ['assign'], 0
    observed = cards(monkeypatch)
    before = list(pm.calls)
    words = render(app, guided)
    assert observed == [('Board A', 31.4, 'LEFT'), ('Board B', 47.2, 'RIGHT')]
    assert not {'88.0', '99.0', '499.5', '999.0'} & set(words)
    assert pm.calls == before


def test_enumeration_reorder_preserves_identity(workspace, monkeypatch):
    app, pm = workspace
    backend = install(pm)
    backend.loads['left']['device_id'] = b'board-one'
    pm.devices.reverse()
    observed = cards(monkeypatch)
    render(app)
    assert observed == [('Board A', 47.2, 'RIGHT'), ('Board B', 31.4, 'LEFT')]


def test_valid_peer_displays_independently_of_invalid_aggregate(workspace, monkeypatch):
    app, pm = workspace
    backend = install(pm)
    backend.ready = False
    backend.loads['left'].update(fresh=False, total_kg=None, timestamp=None)
    observed = cards(monkeypatch)
    assert render(app).count('No live load') == 1
    assert observed == [('Board A', None, 'LEFT'), ('Board B', 47.2, 'RIGHT')]
    assert not ui.snapshot(pm)['streaming']


@pytest.mark.parametrize('change', [
    {'timestamp': 0}, {'timestamp': float('nan')}, {'timestamp': float('inf')},
    {'total_kg': float('nan')}, {'total_kg': float('inf')}, {'total_kg': -1},
    {'fresh': False}, {'timestamp': None}, {'device_id': None},
])
def test_invalid_or_unavailable_child_never_uses_fallback_weight(workspace, monkeypatch, change):
    app, pm = workspace
    backend = install(pm)
    backend.loads['left'].update(change)
    observed = cards(monkeypatch)
    render(app)
    assert observed[0][1] is None and observed[1][1] == 47.2


def test_future_data_unavailable_and_valid_zero_preserved(workspace, monkeypatch):
    app, pm = workspace
    backend = install(pm)
    backend.loads['left']['timestamp'] = ui.time.monotonic() + 10
    backend.loads['right']['total_kg'] = 0
    observed = cards(monkeypatch)
    assert '0.0' in render(app)
    assert observed[0][1] is None and observed[1][1] == 0


def test_samples_expire_without_new_data(workspace, monkeypatch):
    app, pm = workspace
    clock = [100.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    backend = install(pm)
    assert '31.4' in render(app)
    clock[0] = 101.6
    assert render(app).count('No live load') == 2
    assert backend.observations == 2


def test_duplicate_and_extra_device_do_not_fill_wrong_card(workspace, monkeypatch):
    app, pm = workspace
    backend = install(pm)
    backend.loads['right']['device_id'] = 'board-one'
    assert render(app).count('No live load') == 2
    backend.loads['right']['device_id'] = 'board-three'
    observed = cards(monkeypatch)
    render(app)
    assert observed[0][1] == 31.4 and observed[1][1] is None
    pm.devices += ['board-three']
    app.board_device_page = 1
    observed.clear()
    render(app)
    assert observed[0] == ('Board C', 47.2, 'Unassigned')
    assert observed[1][1] is None


def test_active_assignment_matches_handles_not_scan_order(workspace, monkeypatch):
    app, pm = workspace
    pm.backend = None
    pm.devices.reverse()
    pm.assignment_wizard = SimpleNamespace(
        board_a=b'board-one', board_b=b'board-two', left_board=b'board-one', right_board=b'board-two',
        get_status=lambda: {'phase': 'waiting_right', 'board_a_weight': 18.2,
                            'board_b_weight': 29.7, 'board_a_weight_valid': True,
                            'board_b_weight_valid': True})
    app.setup_flow_steps, app.setup_flow_index = ['assign'], 0
    observed = cards(monkeypatch)
    render(app, guided=True)
    assert observed == [('Board A', 29.7, 'RIGHT'), ('Board B', 18.2, 'LEFT')]


def test_single_preserves_live_total_and_rejects_invalid_state(workspace):
    app, pm = workspace
    backend = install(pm)
    pm.board_mode, pm.devices = 'single', ['board-one']
    pm.latest_frame['total_kg'] = 62.3
    assert '62.3' in render(app)
    assert backend.observations == 0
    backend.recovery_blocked = True
    assert '62.3' not in render(app)
    assert render(app).count('No live load') == 1


def test_demo_does_not_mix_in_hardware_child_weights(workspace):
    app, pm = workspace
    backend = install(pm)
    pm.is_simulator = True
    words = render(app)
    assert backend.observations == 0
    assert not {'31.4', '47.2'} & set(words)
    assert 'DEMO / SIMULATED' in words and not ui.snapshot(pm)['ready']


def test_demo_assignment_preserves_explicit_simulated_weights(workspace, monkeypatch):
    app, pm = workspace
    pm.is_simulator, pm.devices = True, []
    pm.assignment_wizard = SimpleNamespace(
        board_a='Board A', board_b='Board B', left_board=None, right_board=None,
        get_status=lambda: {'phase': 'waiting_left', 'board_a_weight': 11, 'board_b_weight': 22})
    app.setup_flow_steps, app.setup_flow_index = ['assign'], 0
    observed = cards(monkeypatch)
    assert 'DEMO / SIMULATED' in render(app, guided=True)
    assert [item[1] for item in observed] == [11, 22]


def test_openfp_uses_existing_plate_readings(workspace):
    app, pm = workspace
    backend = install(pm)
    pm.pressure_source = 'openfp'
    backend.last_dual_reading = SimpleNamespace(
        timestamp=ui.time.monotonic(), left=SimpleNamespace(total=0), right=SimpleNamespace(total=52.6))
    words = render(app)
    assert '0.0' in words and '52.6' in words
    assert not {'31.4', '47.2'} & set(words)
    assert backend.observations == 0


def test_passive_load_query_holds_manager_lock(workspace, monkeypatch):
    _, pm = workspace
    install(pm)
    locked = []
    class Lock:
        def __enter__(self):
            locked.append(True)
        def __exit__(self, *args):
            locked.pop()
    pm.lock = Lock()
    original = CurrentLoads.get_board_loads
    def verify(owner):
        assert locked
        return original(owner)
    monkeypatch.setattr(CurrentLoads, 'get_board_loads', verify)
    assert ui.snapshot(pm)['board_loads']['board-one'] == 31.4
    assert locked == []


@pytest.mark.parametrize('scale', ['100%', '150%', '200%'])
def test_native_dual_cards_update_and_expire_independently(desktop_workspace, monkeypatch, scale):
    app, root, pm, errors = desktop_workspace
    clock = [100.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    backend = install(pm)
    pm.devices.reverse()
    app.set_ui_scale(scale, persist=False)
    app.set_mode(10)
    app.concept_setup_page = 'details'
    app.draw_screen()
    root.update()
    def words():
        return [app.canvas.itemcget(item, 'text') for item in app.canvas.find_all()
                if app.canvas.type(item) == 'text']
    assert '31.4' in words() and '47.2' in words()
    backend.ready = False
    backend.loads['left'].update(total_kg=None, timestamp=None, fresh=False)
    app.draw_screen()
    root.update()
    assert '31.4' not in words() and '47.2' in words()
    assert words().count('No live load') == 1
    clock[0] = 102
    app.draw_screen()
    root.update()
    assert words().count('No live load') == 2
    assert not errors


def test_real_dual_accessor_reaches_cards_without_more_device_reads(workspace, monkeypatch):
    from test_dual_sample_freshness import FakeBackend, sample

    from src.hardware.pressure.dual_wbb_backend import DualWbbBackend

    app, pm = workspace
    clock = [100.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(FakeBackend, 'get_diagnostics',
                        lambda self: {'recovery_blocked': getattr(self, 'invalid', False)}, raising=False)
    left, right = FakeBackend(), FakeBackend()
    left._device_path, right._device_path = b'board-one', b'board-two'
    pm.backend = DualWbbBackend(left, right)
    left.samples.append(sample(100, 2))
    right.samples.append(sample(100, 3))
    assert pm.backend.read() is not None
    assert '20.0' in render(app) and '30.0' in render(app)
    assert (left.read_count, right.read_count) == (1, 1)
    clock[0] = 100.1
    left.invalid = True
    right.samples.append(sample(100.1, 4))
    assert pm.backend.read() is None
    words = render(app)
    assert '20.0' not in words and '40.0' in words
    assert words.count('No live load') == 1
    assert (left.read_count, right.read_count) == (2, 2)
