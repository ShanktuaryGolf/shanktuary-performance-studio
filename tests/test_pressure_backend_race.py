"""The pressure worker must never read a board while another thread closes it.

Regression: clicking Setup -> "Start step-on wizard" crashed the app on
Windows. start_assignment_wizard() (UI thread) closes the live backend while
the pressure worker is inside backend.read() on the same handle. hidapi's
native read runs without the GIL, so close-during-read is a native
use-after-free -- a hard crash with no Python traceback. The worker snapshot
the backend under the lock but then read it unlocked.
"""
import threading
import time

import obs_server
from src.hardware.pressure import SensorReading, TareOffsets
from src.processing.pressure import (
    CoPCalculator,
    ShotSynchronizedPressureBuffer,
    SwingDetector,
    TorqueCalculator,
)


class RacyBoard:
    """Stands in for a HID board: a slow read that must not overlap close."""

    def __init__(self):
        self.is_open = True
        self.in_read = False
        self.overlaps = 0
        self.reads = 0

    def read(self):
        self.in_read = True
        try:
            time.sleep(0.004)          # native read window, GIL released
            self.reads += 1
            if not self.is_open:
                self.overlaps += 1     # read finished on a closed handle
            return SensorReading(20.0, 20.0, 20.0, 20.0,
                                 timestamp=time.monotonic())
        finally:
            self.in_read = False

    def close(self):
        if self.in_read:
            self.overlaps += 1
        self.is_open = False


def _manager():
    pm = obs_server.PressureManager.__new__(obs_server.PressureManager)
    pm.lock = threading.RLock()
    pm.backend = None
    pm.assignment_wizard = None
    pm._wiz_backend_a = None
    pm._wiz_backend_b = None
    pm._latest_raw_reading = None
    pm._last_reconnect_attempt = time.time()   # suppress auto-reconnect
    pm.is_simulator = True                     # ...and hardware reopen
    pm.tare_offsets = TareOffsets()
    pm.balance_multiplier = [1.0, 1.0]
    pm._alignment_active = False
    pm.cop_calc = CoPCalculator()
    pm.torque_calc = TorqueCalculator()
    pm.swing_det = SwingDetector()
    pm.buffer = ShotSynchronizedPressureBuffer(capacity=60)
    pm.stance_cal = obs_server.StanceCalibrator()
    pm.latest_frame = None
    pm.running = True
    return pm


def test_closing_the_backend_never_overlaps_a_worker_read(monkeypatch):
    monkeypatch.setattr(obs_server.obs_state, "broadcast", lambda *_a, **_k: None)
    pm = _manager()
    boards = []
    worker = threading.Thread(target=pm._loop, daemon=True)
    worker.start()
    try:
        for _ in range(40):
            board = RacyBoard()
            boards.append(board)
            with pm.lock:
                pm.backend = board
            time.sleep(0.01)
            # Exactly what start_assignment_wizard does on the UI thread.
            with pm.lock:
                pm.backend.close()
                pm.backend = None
    finally:
        pm.running = False
        worker.join(timeout=2)

    assert sum(b.reads for b in boards) > 0, "worker never read -- test is vacuous"
    assert sum(b.overlaps for b in boards) == 0, \
        "a board was closed while the worker was mid-read (native crash on Windows)"
