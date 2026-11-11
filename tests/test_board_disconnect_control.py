"""Session disconnect never changes bonds, calibration or unrelated devices."""
import threading
import time
from unittest.mock import Mock

from test_pressure_backend_race import _manager

import obs_server
from src.hardware.pressure.base import BoardBackend
from src.hardware.pressure.dual_wbb_backend import DualWbbBackend
from src.hardware.pressure.hid_backend import HidBackend


class Board(BoardBackend):
    def __init__(self):
        self.active = True
        self.closes = 0
        self.reading = False
        self.overlap = False

    def open(self):
        self.active = True

    @property
    def is_open(self):
        return self.active

    def read(self):
        self.reading = True
        time.sleep(.015)
        self.reading = False
        return None

    def close(self):
        self.overlap |= self.reading
        self.closes += 1
        self.active = False


def manager(board):
    pm = _manager()
    pm.backend = board
    pm.is_simulator = False
    pm.pressure_source = "wbb"
    pm.hardware_paused = False
    pm.board_mode = "dual"
    pm.assigned_left = b"left-exact-id"
    pm.assigned_right = b"right-exact-id"
    pm._save_calibration = Mock(side_effect=AssertionError("must not write settings"))
    return pm


def test_disconnect_preserves_settings_and_is_idempotent():
    left, right, unrelated = Board(), Board(), Board()
    pm = manager(DualWbbBackend(left, right))
    pm.latest_frame = {"total_kg": 50}
    pm.balance_multiplier = [1.2, .9]
    pm.stance_width_mm = 430
    result = pm.disconnect_boards()
    assert result["status"] == "disconnected"
    assert result["powered_off"] is None
    assert "not confirmed" in result["message"]
    assert pm.backend is None and pm.latest_frame is None
    assert pm.hardware_paused
    assert pm.assigned_left == b"left-exact-id"
    assert pm.assigned_right == b"right-exact-id"
    assert pm.balance_multiplier == [1.2, .9] and pm.stance_width_mm == 430
    assert left.closes == right.closes == 1 and unrelated.closes == 0
    assert pm.disconnect_boards() == result
    assert left.closes == right.closes == 1
    pm._save_calibration.assert_not_called()


def test_disconnect_waits_for_read_and_stops_retries(monkeypatch):
    board = Board()
    pm = manager(board)
    pm._create_hardware_backend = Mock(side_effect=AssertionError("unexpected retry"))
    monkeypatch.setattr(obs_server.obs_state, "broadcast", lambda *_: None)
    worker = threading.Thread(target=pm._loop, daemon=True)
    worker.start()
    deadline = time.monotonic() + 1
    while not board.reading and time.monotonic() < deadline:
        time.sleep(.001)
    assert board.reading
    try:
        pm.disconnect_boards()
        pm._last_reconnect_attempt = 0  # immediately eligible, except pause latch
        time.sleep(.06)
        assert not board.overlap
        assert pm.backend is None and pm.latest_frame is None
        pm._create_hardware_backend.assert_not_called()
    finally:
        pm.running = False
        worker.join(1)


def test_reconfigure_and_wizard_do_not_undo_pause():
    pm = manager(Board())
    pm.disconnect_boards()
    pm._create_hardware_backend = Mock(side_effect=AssertionError("unexpected open"))
    pm.set_board_mode("single")
    pm.set_simulator(False)
    pm.reopen_backend()
    status = pm.start_assignment_wizard()
    assert status["phase"] == "idle" and "Resume" in status["message"]
    assert pm.hardware_paused and pm.backend is None
    pm._create_hardware_backend.assert_not_called()


def test_resume_is_explicit_and_does_not_tare_or_pair():
    pm = manager(Board())
    pm.disconnect_boards()
    replacement = Board()
    pm.board_mode = "single"
    pm._create_hardware_backend = Mock(return_value=replacement)
    assert pm.resume_boards()["status"] == "resumed"
    assert not pm.hardware_paused and pm.backend is replacement
    assert pm.resume_boards()["status"] == "already_active"
    pm._create_hardware_backend.assert_called_once_with()
    pm._save_calibration.assert_not_called()


def test_demo_and_other_source_are_not_disconnected():
    board = Board()
    pm = manager(board)
    pm.is_simulator = True
    assert pm.disconnect_boards()["status"] == "unavailable"
    pm.is_simulator = False
    pm.pressure_source = "openfp"
    assert pm.disconnect_boards()["status"] == "unavailable"
    assert board.closes == 0 and not pm.hardware_paused


def test_close_failure_is_honest_and_other_board_still_closed():
    left, right = Board(), Board()
    left.close = Mock(side_effect=OSError("test close failure"))
    pm = manager(DualWbbBackend(left, right))
    result = pm.disconnect_boards()
    assert result["status"] == "stopped_with_warning"
    assert result["powered_off"] is None and pm.hardware_paused
    assert right.closes == 1


def test_hid_pending_read_quarantine_does_not_claim_release(monkeypatch):
    from src.hardware.pressure import hid_backend
    monkeypatch.setattr(hid_backend.sys, "platform", "win32")
    monkeypatch.setattr(hid_backend, "_settle_pending_read", lambda _: False)
    monkeypatch.setattr(hid_backend, "_UNSETTLED_HANDLES", [])
    backend = HidBackend(b"known-path")
    device = Mock()
    backend._device = device
    result = backend.disconnect_for_session()
    assert not result["released"] and result["powered_off"] is None
    device.close.assert_not_called()
    device.write.assert_not_called()
    assert hid_backend._UNSETTLED_HANDLES == [device]


def test_disconnect_closes_wizard_readers_once_and_preserves_assignment():
    pm = manager(None)
    board = Board()
    pm._wiz_backend_a = pm._wiz_backend_b = board
    wizard = Mock(phase="waiting_left")
    pm.assignment_wizard = wizard
    pm.disconnect_boards()
    assert board.closes == 1
    wizard.reset.assert_called_once_with()
    assert pm.assigned_left == b"left-exact-id"
    assert pm._wiz_backend_a is None and pm._wiz_backend_b is None


def test_pause_does_not_block_other_hardware_source():
    pm = manager(Board())
    pm.disconnect_boards()
    other = Board()
    pm.pressure_source = "openfp"
    pm._create_openfp_backend = Mock(return_value=other)
    pm._set_simulator_unlocked(False)
    assert pm.backend is other and pm.hardware_paused


def test_disconnect_waits_for_inflight_frame_then_clears_it(monkeypatch):
    from src.hardware.pressure.base import SensorReading
    board = Board()
    board.read = lambda: SensorReading(10, 10, 10, 10, time.monotonic())
    pm = manager(board)
    entered, release = threading.Event(), threading.Event()
    original_push = pm.buffer.push

    def slow_push(*args, **kwargs):
        entered.set()
        assert release.wait(1)
        return original_push(*args, **kwargs)

    pm.buffer.push = slow_push
    monkeypatch.setattr(obs_server.obs_state, "broadcast", lambda *_: None)
    worker = threading.Thread(target=pm._loop, daemon=True)
    worker.start()
    closer = threading.Thread(target=pm.disconnect_boards)
    try:
        assert entered.wait(1)
        closer.start()
        time.sleep(.015)
        assert closer.is_alive()  # cannot close native source mid-frame
        release.set()
        closer.join(1)
        assert not closer.is_alive()
        time.sleep(.03)
        assert pm.backend is None and pm.latest_frame is None
        assert pm._latest_raw_reading is None
    finally:
        release.set()
        pm.running = False
        worker.join(1)
        if closer.ident:
            closer.join(1)


def test_prior_quarantined_handle_stays_an_incomplete_release(monkeypatch):
    from src.hardware.pressure import hid_backend
    monkeypatch.setattr(hid_backend.sys, "platform", "win32")
    monkeypatch.setattr(hid_backend, "_settle_pending_read", lambda _: False)
    monkeypatch.setattr(hid_backend, "_UNSETTLED_HANDLES", [])
    backend = HidBackend(b"known-path")
    backend._device = Mock()
    backend.close()  # e.g. read failure before the Disconnect click
    assert not backend.is_open
    assert not backend.disconnect_for_session()["released"]


def test_completed_alignment_marker_survives_disconnect_and_resume():
    pm = manager(Board())
    pm._alignment_active = False
    pm._alignment_status_msg = "✓ Calibration complete"
    pm.disconnect_boards()
    assert pm._alignment_status_msg == "✓ Calibration complete"
    pm.board_mode = "single"
    pm._create_hardware_backend = Mock(return_value=Board())
    pm.resume_boards()
    assert pm._alignment_status_msg == "✓ Calibration complete"


def test_active_alignment_is_stopped_without_saving_calibration():
    pm = manager(Board())
    pm._alignment_active = True
    pm._alignment_samples = [1, 2]
    pm.disconnect_boards()
    assert not pm._alignment_active and pm._alignment_samples == []
    assert "stopped" in pm._alignment_status_msg
    pm._save_calibration.assert_not_called()


def test_slow_close_does_not_hold_display_lock_and_resume_is_blocked():
    pm = manager(Board())
    entered, release = threading.Event(), threading.Event()
    board = pm.backend
    original_close = board.close

    def slow_close():
        entered.set()
        assert release.wait(1)
        original_close()

    board.close = slow_close
    closer = threading.Thread(target=pm.disconnect_boards)
    closer.start()
    try:
        assert entered.wait(1)
        acquired = pm.lock.acquire(timeout=.05)
        assert acquired, "UI status polling would freeze behind close"
        pm.lock.release()
        assert pm.resume_boards()["status"] == "busy"
        assert pm.disconnect_boards()["status"] == "disconnecting"
        assert pm.backend is None and pm.hardware_paused
        pm._create_hardware_backend = Mock(side_effect=AssertionError("unexpected open"))
        pm.reopen_backend()
        pm._create_hardware_backend.assert_not_called()
    finally:
        release.set()
        closer.join(1)
    assert not pm._disconnect_in_progress
    assert board.closes == 1


def test_tk_heartbeat_continues_while_handle_settles():
    import tkinter as tk

    import pytest

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("native display unavailable")
    root.withdraw()
    pm = manager(Board())
    entered, release = threading.Event(), threading.Event()
    board = pm.backend
    original_close = board.close

    def slow_close():
        entered.set()
        assert release.wait(1)
        original_close()

    board.close = slow_close
    closer = threading.Thread(target=pm.disconnect_boards)
    closer.start()
    assert entered.wait(1)
    timer = threading.Timer(.4, release.set)
    timer.start()
    beats = []
    start = time.monotonic()

    def heartbeat():
        with pm.lock:  # mirrors the regular live UI status snapshot
            assert pm.backend is None
        beats.append(time.monotonic() - start)
        root.after(10, heartbeat)

    root.after(5, heartbeat)
    root.after(100, root.quit)
    try:
        root.mainloop()
        assert len(beats) >= 3
        assert max(beats) < .3
    finally:
        release.set()
        timer.cancel()
        closer.join(1)
        root.destroy()


def test_resume_opens_off_lock_and_rejects_concurrent_resume():
    pm = manager(Board())
    pm.disconnect_boards()
    pm.board_mode = "single"
    candidate = Board()
    entered, release = threading.Event(), threading.Event()

    def slow_open():
        entered.set()
        assert release.wait(1)
        return candidate

    pm._create_hardware_backend = Mock(side_effect=slow_open)
    opener = threading.Thread(target=pm.resume_boards)
    opener.start()
    try:
        assert entered.wait(1)
        acquired = pm.lock.acquire(timeout=.05)
        assert acquired, "UI polling would freeze behind HID open"
        pm.lock.release()
        assert pm.resume_boards()["status"] == "busy"
        assert pm.disconnect_boards()["status"] == "connecting"
        assert pm.backend is None and pm.hardware_paused
    finally:
        release.set()
        opener.join(1)
    assert pm.backend is candidate and not pm.hardware_paused
    assert not pm._disconnect_in_progress
    pm._create_hardware_backend.assert_called_once_with()


def test_resume_discards_candidate_if_settings_change_during_open():
    pm = manager(Board())
    pm.disconnect_boards()
    pm.board_mode = "single"
    candidate = Board()

    def changed_open():
        pm.set_board_mode("dual")  # latched pause prevents another open
        return candidate

    pm._create_hardware_backend = Mock(side_effect=changed_open)
    result = pm.resume_boards()
    assert result["status"] == "cancelled"
    assert pm.board_mode == "dual" and pm.hardware_paused and pm.backend is None
    assert candidate.closes == 1 and not pm._disconnect_in_progress


def test_incomplete_dual_resume_closes_only_partial_candidate():
    pm = manager(Board())
    pm.disconnect_boards()
    candidate = Board()
    pm._create_hardware_backend = Mock(side_effect=[candidate, None])
    assert pm.resume_boards()["status"] == "resumed"
    assert candidate.closes == 1 and pm.backend is None
    assert not pm.hardware_paused and not pm._disconnect_in_progress
    assert pm.assigned_left == b"left-exact-id" and pm.assigned_right == b"right-exact-id"
