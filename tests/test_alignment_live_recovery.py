"""An interrupted alignment restarts its full hold without saving old samples."""
from unittest.mock import Mock

import pytest

import obs_server
from src.hardware.pressure.base import SensorReading


class Backend:
    is_open = True
    ready = True

    def read(self):
        return None

    def get_diagnostics(self):
        return {"ready": self.ready}


@pytest.fixture
def alignment(monkeypatch, tmp_path):
    monkeypatch.setenv("SPS_UI_PREVIEW", "1")
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    clock = [100.0]
    monkeypatch.setattr(obs_server.time, "time", lambda: clock[0] + 1000)
    monkeypatch.setattr(obs_server.time, "monotonic", lambda: clock[0])
    pm = obs_server.PressureManager()
    pm.backend = Backend()
    pm._save_calibration = Mock()
    pm.balance_multiplier = [1.1, 0.9]

    def feed(offset, left=40, right=30):
        clock[0] = 100 + offset
        reading = SensorReading(left / 2, right / 2, left / 2, right / 2, clock[0])
        pm._latest_raw_reading = reading
        pm._advance_stance_alignment(reading)
        return reading

    feed(0)
    pm.start_stance_alignment(delay_sec=0, duration_sec=4)
    feed(0)
    return pm, clock, feed


def hold(feed, start=0, end=4):
    for index in range(round(start * 10), round(end * 10) + 1):
        feed(index / 10)


def assert_paused_without_save(pm):
    status = pm.get_alignment_status()
    assert status["active"] and status["paused"]
    assert status["remaining_sec"] is None
    assert status["progress"] == 0
    assert "Hold stance still" not in status["message"]
    assert pm._alignment_samples == []
    assert pm.balance_multiplier == [1.1, 0.9]
    pm._save_calibration.assert_not_called()


def test_continuous_fresh_full_hold_saves_once(alignment):
    pm, _, feed = alignment
    hold(feed)
    assert not pm.get_alignment_status()["active"]
    assert pm.balance_multiplier == [0.875, 1.1667]
    pm._save_calibration.assert_called_once()
    feed(4.1)
    pm._save_calibration.assert_called_once()


def test_invalid_after_partial_hold_clears_samples_then_requires_full_recovery(alignment):
    pm, clock, feed = alignment
    hold(feed, end=2)
    assert len(pm._alignment_samples) >= 15
    pm.backend.ready = False
    pm._advance_stance_alignment()
    clock[0] = 120
    assert_paused_without_save(pm)
    pm._finish_stance_alignment()  # a late worker cannot persist the old hold
    assert_paused_without_save(pm)
    pm.backend.ready = True
    hold(feed, start=20, end=23.9)
    assert pm.get_alignment_status()["active"]
    pm._save_calibration.assert_not_called()
    feed(24)
    assert not pm.get_alignment_status()["active"]
    pm._save_calibration.assert_called_once()


def test_no_frames_past_deadline_pauses_independently_of_status_query(alignment, monkeypatch):
    pm, clock, feed = alignment
    hold(feed, end=2)
    clock[0] = 110
    pm.running = True
    monkeypatch.setattr(obs_server.time, "sleep", lambda _: setattr(pm, "running", False))
    pm._loop()  # no fresh read, no HTTP/UI polling, no hardware commands
    assert pm._alignment_paused
    assert_paused_without_save(pm)


def test_long_sample_gap_resets_even_if_watchdog_never_ran(alignment):
    pm, _, feed = alignment
    hold(feed, end=2)
    feed(10)
    assert len(pm._alignment_samples) == 1
    assert pm._alignment_hold_start == 110
    pm._save_calibration.assert_not_called()
    hold(feed, start=10.1, end=14)
    pm._save_calibration.assert_called_once()


def test_live_status_cannot_finish_elapsed_hold_without_new_sample(alignment):
    pm, clock, feed = alignment
    hold(feed, end=3.9)
    clock[0] = 104
    status = pm.get_alignment_status()
    assert status["active"] and not status["paused"]
    assert status["remaining_sec"] is None
    assert status["progress"] < 1
    assert "fresh reading" in status["message"]
    pm._save_calibration.assert_not_called()
    feed(4)
    pm._save_calibration.assert_called_once()


def test_old_final_sample_cannot_be_saved_after_new_unprocessed_reading(alignment):
    pm, clock, feed = alignment
    hold(feed, end=3.9)
    pm._alignment_last_sample_timestamp = 104
    clock[0] = 120
    pm._latest_raw_reading = SensorReading(20, 15, 20, 15, 120)
    pm._finish_stance_alignment()
    assert_paused_without_save(pm)


def test_duplicate_readings_do_not_fill_or_finish_hold(alignment):
    pm, clock, feed = alignment
    reading = feed(1)
    count = len(pm._alignment_samples)
    for _ in range(100):
        pm._advance_stance_alignment(reading)
    assert len(pm._alignment_samples) == count
    clock[0] = 103
    pm._advance_stance_alignment(reading)
    assert_paused_without_save(pm)


def test_unloaded_or_nonfinite_hold_clears_previous_loaded_samples(alignment):
    pm, _, feed = alignment
    hold(feed, end=2)
    feed(2.1, left=0, right=0)
    assert_paused_without_save(pm)
    hold(feed, start=3, end=4)
    feed(4.1, left=float("nan"))
    assert_paused_without_save(pm)


def test_configuration_change_cancels_without_saving(alignment):
    pm, _, feed = alignment
    hold(feed, end=2)
    pm.board_mode = "dual"
    status = pm.get_alignment_status()
    assert not status["active"]
    assert "configuration changed" in status["message"]
    assert not status["configuration_matches"]
    pm._save_calibration.assert_not_called()


def test_recovery_restarts_complete_lead_in_then_hold(alignment):
    pm, clock, feed = alignment
    pm.start_stance_alignment(delay_sec=5, duration_sec=4)
    clock[0] = 120
    assert_paused_without_save(pm)
    feed(20)
    assert pm.get_alignment_status()["remaining_sec"] == 9
    assert pm.get_alignment_status()["in_lead_in"]
    hold(feed, start=20.1, end=28.9)
    pm._save_calibration.assert_not_called()
    feed(29)
    pm._save_calibration.assert_called_once()


def test_disconnected_backend_invalidates_even_recent_data(alignment):
    pm, _, feed = alignment
    hold(feed, end=1)
    pm.backend.is_open = False
    assert_paused_without_save(pm)


@pytest.mark.parametrize("delay,duration", [(-1, 4), (0, 0), (0, float("nan")), (float("inf"), 4)])
def test_invalid_durations_are_rejected(alignment, delay, duration):
    pm, _, _ = alignment
    with pytest.raises(ValueError):
        pm.start_stance_alignment(delay, duration)


def test_replaced_reader_cannot_inherit_partial_hold(alignment):
    pm, _, feed = alignment
    hold(feed, end=2)
    pm.backend = Backend()
    feed(2.1)
    assert len(pm._alignment_samples) == 1
    assert pm._alignment_hold_start == 102.1
    pm._save_calibration.assert_not_called()


def test_sample_from_replaced_reader_is_rejected(alignment):
    pm, _, feed = alignment
    hold(feed, end=2)
    old_backend = pm.backend
    pm.backend = Backend()
    pm._advance_stance_alignment(pm._latest_raw_reading, source_backend=old_backend)
    assert_paused_without_save(pm)
