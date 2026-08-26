"""Stance-WIDTH calibration wiring (shift left, then right).

Distinct from tests/test_stance_calibration.py, which covers the 50/50
left/right balance alignment. This covers StanceCalibrator being driven by
PressureManager and exposed over the API.
"""
import threading

import pytest

import obs_server
from src.hardware.pressure.base import SensorReading
from src.processing.pressure.cop import CoPSample
from src.processing.pressure.stance import StanceCalibrator, CalibrationState


def _manager():
    """Bare PressureManager with only the stance pieces initialised."""
    pm = obs_server.PressureManager.__new__(obs_server.PressureManager)
    pm.lock = threading.RLock()
    pm.stance_cal = StanceCalibrator()
    pm.stance_width_mm = None
    pm._save_calibration = lambda: None
    return pm


def _sample(t, pct_left, pct_right, cop_x):
    return CoPSample(
        cop_x=cop_x, cop_y=0.0, total_kg=80.0,
        pct_left=pct_left, pct_right=pct_right,
        pct_front=50.0, pct_back=50.0,
        left_pct_front=50.0, left_pct_back=50.0,
        right_pct_front=50.0, right_pct_back=50.0,
        raw=SensorReading(20.0, 20.0, 20.0, 20.0, t), timestamp=t,
    )


def _hold(pm, t0, pct_left, pct_right, cop_x, n=40, dt=0.033):
    t = t0
    for _ in range(n):
        t += dt
        pm.stance_cal.update(_sample(t, pct_left, pct_right, cop_x))
        if pm.stance_cal.state == CalibrationState.DONE and pm.stance_width_mm is None:
            width = pm.stance_cal.stance_width_mm
            if width is not None:
                pm.stance_width_mm = round(width, 1)
    return t


def test_status_idle_before_start():
    pm = _manager()
    st = pm.get_stance_width_status()
    assert st["state"] == "idle"
    assert st["active"] is False
    assert st["stance_width_mm"] is None


def test_start_waits_for_left_foot():
    pm = _manager()
    st = pm.start_stance_width_calibration()
    assert st["state"] == "waiting_left"
    assert st["active"] is True
    assert "LEFT" in st["instruction"]


def test_full_sequence_measures_stance_width():
    pm = _manager()
    pm.start_stance_width_calibration()

    t = _hold(pm, 0.0, 92.0, 8.0, -120.0)
    assert pm.get_stance_width_status()["state"] == "waiting_right"

    _hold(pm, t, 8.0, 92.0, 130.0)
    st = pm.get_stance_width_status()

    assert st["state"] == "done"
    assert st["active"] is False
    # |130 - (-120)|
    assert st["stance_width_mm"] == pytest.approx(250.0)


def test_insufficient_load_does_not_advance():
    """Weight below the 85% threshold must not complete a hold."""
    pm = _manager()
    pm.start_stance_width_calibration()
    _hold(pm, 0.0, 60.0, 40.0, -120.0)
    assert pm.get_stance_width_status()["state"] == "waiting_left"


def test_cancel_returns_to_idle():
    pm = _manager()
    pm.start_stance_width_calibration()
    st = pm.cancel_stance_width_calibration()
    assert st["state"] == "idle"
    assert st["active"] is False


def test_width_survives_a_calibration_save_load_round_trip(tmp_path):
    """stance_width_mm must persist like balance_multiplier does."""
    pm = _manager()
    pm.balance_multiplier = [1.0, 1.0]
    pm.board_mode = "single"
    pm.assigned_left = None
    pm.assigned_right = None
    pm.stance_width_mm = 250.0

    fp = tmp_path / "cal.json"
    obs_server.PressureManager._save_calibration(pm, filepath=str(fp))

    pm2 = _manager()
    pm2.balance_multiplier = [1.0, 1.0]
    pm2.board_mode = "single"
    pm2.assigned_left = None
    pm2.assigned_right = None
    obs_server.PressureManager._load_calibration(pm2, filepath=str(fp))

    assert pm2.stance_width_mm == pytest.approx(250.0)
