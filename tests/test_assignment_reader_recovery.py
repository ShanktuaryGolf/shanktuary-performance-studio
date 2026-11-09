"""Assignment only advances from fresh calibrated samples and owns its handles."""
import threading

import pytest

import obs_server
from src.hardware.pressure.base import SensorReading
from src.hardware.pressure.connection import BoardAssignmentWizard
from src.hardware.pressure.dual_wbb_backend import DualWbbBackend


class Board:
    def __init__(self, calibration="factory"):
        self.is_open = True
        self.calibration = calibration
        self.queue = []
        self.closes = 0
        self.last_packet_timestamp = None
        self.last_sample_timestamp = None
        self.last_error = None

    def sample(self, kg, stamp):
        self.queue.append(SensorReading(kg, 0, 0, 0, stamp))

    def read(self):
        if not self.queue:
            return None
        reading = self.queue.pop(0)
        if isinstance(reading, Exception):
            raise reading
        self.last_packet_timestamp = reading.timestamp
        if self.calibration != "factory":
            return None
        self.last_sample_timestamp = reading.timestamp
        return reading

    def get_diagnostics(self):
        return dict(calibration_status=self.calibration,
                    last_packet_timestamp=self.last_packet_timestamp,
                    last_sample_timestamp=self.last_sample_timestamp,
                    raw_cells={"top_left": 5000}, last_error=self.last_error)

    def close(self):
        self.closes += 1
        self.is_open = False


@pytest.fixture
def manager(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(obs_server.time, "monotonic", lambda: clock[0])
    pm = obs_server.PressureManager.__new__(obs_server.PressureManager)
    pm.lock = threading.RLock()
    pm.is_simulator = False
    pm.board_mode = "dual"
    pm.backend = None
    pm._wiz_backend_a = None
    pm._wiz_backend_b = None
    pm.assignment_wizard = None
    pm.assigned_left = None
    pm.assigned_right = None
    pm.latest_frame = {"timestamp": 50}
    pm._latest_raw_reading = object()
    pm._wiz_health = {}
    pm.enumerate_boards = lambda: [b"device-a", b"device-b"]
    pm.saved = []
    pm._save_calibration = lambda: pm.saved.append(True)
    pm.opened = []

    def create(path=None):
        board = Board()
        pm.opened.append((path, board))
        return board

    pm._create_hardware_backend = create
    pm.clock = clock
    return pm


def start(pm):
    status = pm.start_assignment_wizard()
    assert status["phase"] == "waiting_left"
    return pm._wiz_backend_a, pm._wiz_backend_b


def test_reset_closes_both_readers_once_and_clears_stale_display(manager):
    a, b = start(manager)
    manager.reset_assignment_wizard()
    manager.reset_assignment_wizard()
    assert (a.closes, b.closes) == (1, 1)
    assert manager._wiz_backend_a is manager._wiz_backend_b is None
    assert manager.latest_frame is manager._latest_raw_reading is None
    assert manager.assignment_wizard.phase == "idle"


def test_mode_change_releases_wizard_before_opening_normal_reader(manager):
    a, b = start(manager)
    def reopen(path=None):
        assert a.closes == b.closes == 1
        return Board()
    manager._create_hardware_backend = reopen
    manager.set_board_mode("single")
    assert manager.assignment_wizard.phase == "idle"
    assert manager.backend.is_open


def test_restarting_wizard_releases_previous_readers(manager):
    a, b = start(manager)
    c, d = start(manager)
    assert a.closes == b.closes == 1
    assert c is not a and d is not b
    assert c.closes == d.closes == 0


def test_empty_readers_retry_exact_devices_then_surface_bounded_failure(manager):
    a, b = start(manager)
    for elapsed in (0, 3.1, 6.2, 9.3, 12.4, 100):
        manager.clock[0] = 100 + elapsed
        manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert status["phase"] == "waiting_left"
    assert status["health_state"] == "error"
    assert "cancel and retry" in status["message"]
    assert not status["board_a_weight_valid"]
    assert status["boards"]["a"]["sample_age_seconds"] is None
    assert status["boards"]["a"]["retries"] == 2
    assert status["boards"]["a"]["retry_exhausted"]
    assert [path for path, _ in manager.opened] == [b"device-a", b"device-b"] * 3
    assert a.closes == b.closes == 1
    assert manager.saved == []


def test_zero_calibrated_readings_are_live_not_a_connection_error(manager):
    a, b = start(manager)
    a.sample(0, 100)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert status["health_state"] == "ready"
    assert status["phase"] == "waiting_left"
    assert status["board_a_weight"] == status["board_b_weight"] == 0
    assert status["board_a_weight_valid"]
    assert status["boards"]["a"]["calibration_status"] == "factory"
    assert status["boards"]["a"]["sample_age_seconds"] == 0


def test_uncalibrated_loaded_packets_are_not_fake_zero_kg(manager):
    a, b = start(manager)
    a.calibration = "unavailable"
    a.sample(70, 100)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert status["phase"] == "waiting_left"
    assert not status["board_a_weight_valid"]
    assert status["board_b_weight_valid"]
    assert "factory calibration unavailable" in status["message"]
    assert status["boards"]["a"]["last_packet_timestamp"] == 100
    assert status["boards"]["a"]["last_sample_timestamp"] is None
    assert status["boards"]["a"]["raw_cells"] == {"top_left": 5000}


def test_recovery_needs_fresh_data_from_both_handles(manager):
    a, b = start(manager)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    manager.clock[0] = 103.1
    b.sample(0, 103.1)
    manager._poll_assignment_wizard()
    replacement = manager._wiz_backend_a
    assert replacement is not a and a.closes == 1
    replacement.sample(70, 103.2)
    b.sample(0, 103.2)
    manager.clock[0] = 103.2
    manager._poll_assignment_wizard()
    assert manager.assignment_wizard.phase == "waiting_right"
    assert manager.assignment_wizard.health_state == "ready"
    assert manager.assignment_wizard.left_board == b"device-a"


def test_stale_right_cannot_be_treated_as_current_zero(manager):
    a, b = start(manager)
    a.sample(0, 100)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    manager.clock[0] = 102
    a.sample(70, 102)
    manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert status["phase"] == "waiting_left"
    assert not status["board_b_weight_valid"]
    assert status["boards"]["b"]["sample_age_seconds"] == 2


def test_read_error_does_not_kill_other_reader_or_lose_reason(manager):
    a, b = start(manager)
    a.queue.append(OSError("USB read failed"))
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert a.closes == 1 and b.closes == 0
    assert "USB read failed" in status["boards"]["a"]["last_error"]
    assert not status["boards"]["a"]["is_open"]
    assert status["board_b_weight_valid"]


def test_physical_update_cannot_bypass_waiting_for_readers(manager):
    start(manager)
    status = manager.update_assignment_wizard(70, 0)
    assert status["phase"] == "waiting_left"
    assert manager.saved == []


def test_completion_transfers_existing_handles_and_only_saves_once(manager):
    a, b = start(manager)
    a.sample(70, 100)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    a.sample(35, 100)
    b.sample(35, 100)
    manager._poll_assignment_wizard()
    assert manager.assignment_wizard.phase == "complete"
    assert isinstance(manager.backend, DualWbbBackend)
    assert manager.backend._left is a and manager.backend._right is b
    assert a.closes == b.closes == 0
    assert manager._wiz_backend_a is manager._wiz_backend_b is None
    assert len(manager.opened) == 2 and len(manager.saved) == 1
    manager.update_assignment_wizard(35, 35)
    assert len(manager.opened) == 2 and len(manager.saved) == 1


def test_duplicate_paths_cannot_start_a_two_board_wizard(manager):
    manager.enumerate_boards = lambda: [b"same", b"same"]
    status = manager.start_assignment_wizard()
    assert status["phase"] == "idle"
    assert status["detected"] == 1
    assert manager.assignment_wizard is None


def test_sample_created_during_read_is_not_rejected_as_future(manager):
    a, b = start(manager)
    def during_read():
        manager.clock[0] += .01
        return SensorReading(0, 0, 0, 0, manager.clock[0])
    a.read = b.read = during_read
    manager._poll_assignment_wizard()
    assert manager.assignment_wizard.get_status()["health_state"] == "ready"


def test_reopen_time_cannot_make_the_other_reader_look_fresh(manager):
    a, b = start(manager)
    manager.clock[0] = 104
    a.sample(70, 104)
    def slow_reopen(path):
        manager.clock[0] += 2
        return Board()
    manager._create_hardware_backend = slow_reopen
    manager._poll_assignment_wizard()
    status = manager.assignment_wizard.get_status()
    assert status["phase"] == "waiting_left"
    assert not status["board_a_weight_valid"]
    assert status["boards"]["a"]["sample_age_seconds"] == 2


def test_http_style_weights_cannot_override_live_hardware_readings(manager):
    a, b = start(manager)
    a.sample(0, 100)
    b.sample(0, 100)
    manager._poll_assignment_wizard()
    assert manager.assignment_wizard.health_state == "ready"
    manager.update_assignment_wizard(70, 0)
    assert manager.assignment_wizard.phase == "waiting_left"
    manager.clock[0] = 110
    manager.update_assignment_wizard(70, 70)
    assert manager.assignment_wizard.phase == "waiting_left"
    assert manager.saved == []


def test_cancel_simulator_wizard_restores_existing_demo_mode(manager):
    manager.is_simulator = True
    manager.enumerate_boards = lambda: []
    manager.start_assignment_wizard()
    assert manager.backend is None
    manager.reset_assignment_wizard()
    assert manager.is_simulator
    assert manager.backend is not None and manager.backend.is_open
    assert manager.backend.read() is not None
    manager.backend.close()


def test_simulator_assignment_never_enumerates_or_opens_hardware(manager):
    manager.is_simulator = True
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo assignment touched physical hardware")
    manager.enumerate_boards = forbidden
    manager._create_hardware_backend = forbidden
    status = manager.start_assignment_wizard()
    assert status["phase"] == "waiting_left"
    assert manager._wiz_backend_a is manager._wiz_backend_b is None
    manager.update_assignment_wizard(35, 0)
    assert manager.update_assignment_wizard(35, 35)["is_complete"]
    assert manager.backend.__class__.__name__ == "SimulatorBackend"
    manager.backend.close()


def test_partial_configured_dual_pair_is_closed_not_used_as_single(manager):
    manager.assigned_left, manager.assigned_right = b"device-a", b"device-b"
    survivor = Board()
    manager._create_hardware_backend = lambda path: survivor if path == b"device-a" else None
    manager._set_simulator_unlocked(False)
    assert survivor.closes == 1
    assert manager.backend is None


def test_reconnect_rechecks_wizard_after_reacquiring_lock(manager, monkeypatch):
    """Simulate the UI starting assignment between worker snapshot and reopen."""
    manager.running = True
    manager._last_reconnect_attempt = 0
    rebuilds = []
    manager._set_simulator_unlocked = lambda *_: rebuilds.append(True)
    a, b = Board(), Board()
    class InterleavingLock:
        calls = 0
        def __enter__(self):
            self.calls += 1
            if self.calls == 2:
                manager.assignment_wizard = BoardAssignmentWizard(b"device-a", b"device-b")
                manager.assignment_wizard.start()
                manager._wiz_backend_a, manager._wiz_backend_b = a, b
        def __exit__(self, *_):
            return False
    manager.lock = InterleavingLock()
    monkeypatch.setattr(obs_server.time, "time", lambda: 100)
    monkeypatch.setattr(obs_server.time, "sleep", lambda _: setattr(manager, "running", False))
    manager._loop()
    assert rebuilds == []
    assert manager.assignment_wizard.phase == "waiting_left"
    assert a.closes == b.closes == 0
