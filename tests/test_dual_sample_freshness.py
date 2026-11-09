"""Dual-board aggregation must never manufacture new hardware samples."""
from collections import deque
from unittest.mock import patch

import pytest

from src.hardware.pressure.base import BoardBackend, BoardOrientation, SensorReading
from src.hardware.pressure.dual_wbb_backend import DualWbbBackend


class FakeBackend(BoardBackend):
    def __init__(self):
        self.samples = deque()
        self.opened = True
        self.read_count = 0
        self.disconnect_on_read = False
        self.continuous_sample = None

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    @property
    def is_open(self):
        return self.opened

    def read(self):
        self.read_count += 1
        if self.disconnect_on_read:
            self.opened = False
        return self.samples.popleft() if self.samples else self.continuous_sample


def sample(timestamp, scale=1):
    return SensorReading(scale, 2 * scale, 3 * scale, 4 * scale, timestamp)


@pytest.fixture
def pair():
    left, right = FakeBackend(), FakeBackend()
    dual = DualWbbBackend(left, right)
    with patch('src.hardware.pressure.dual_wbb_backend.time.monotonic', return_value=100) as clock:
        yield dual, left, right, clock


def test_two_fresh_boards_combine_with_source_timestamp(pair):
    dual, left, right, _ = pair
    left.samples.append(sample(99.8))
    right.samples.append(sample(99.9, 10))
    result = dual.read()
    assert result == SensorReading(3, 30, 7, 70, 99.9)
    assert dual.last_dual_reading.timestamp == 99.9
    assert dual.last_dual_reading.left.timestamp == 99.8
    assert dual.last_dual_reading.right.timestamp == 99.9


def test_no_new_samples_never_refreshes_timestamp(pair):
    dual, left, right, clock = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    dual.read()
    previous = dual.last_dual_reading
    clock.return_value = 100.5
    assert dual.read() is None
    assert dual.last_dual_reading is previous
    assert previous.timestamp == 100
    clock.return_value = 101.6
    # Expiry also works when consumers only inspect the property.
    assert dual.last_dual_reading is None


def test_stale_source_suppresses_new_other_source_and_recovers(pair):
    dual, left, right, clock = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    assert dual.read() is not None
    clock.return_value = 102
    right.samples.append(sample(102))
    assert dual.read() is None
    assert dual.last_dual_reading is None
    assert dual.get_diagnostics()['left']['error'] == 'stale_sample'
    left.samples.append(sample(102.1))
    clock.return_value = 102.1
    result = dual.read()
    assert result.timestamp == 102.1
    assert dual.get_diagnostics()['ready'] is True


def test_asymmetric_arrivals_require_both_then_allow_fresh_cached_peer(pair):
    dual, left, right, clock = pair
    left.samples.append(sample(100))
    assert dual.read() is None
    assert dual.get_diagnostics()['right']['error'] == 'waiting_for_sample'
    clock.return_value = 100.1
    right.samples.append(sample(100.1))
    assert dual.read().timestamp == 100.1
    clock.return_value = 100.2
    left.samples.append(sample(100.2, 2))
    assert dual.read() == SensorReading(6, 3, 14, 7, 100.2)


@pytest.mark.parametrize('during_read', [False, True])
def test_disconnected_child_suppresses_and_clears_cached_pair(pair, during_read):
    dual, left, right, _ = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    dual.read()
    if during_read:
        right.disconnect_on_read = True
        right.samples.append(sample(100))
    else:
        right.close()
        assert dual.last_dual_reading is None
    assert dual.read() is None
    assert dual.last_dual_reading is None
    assert dual.get_diagnostics()['ready'] is False
    right.open()
    right.disconnect_on_read = False
    left.samples.append(sample(100))
    assert dual.read() is None  # no sample from reopened right board
    right.samples.append(sample(100))
    assert dual.read() is not None


def test_polling_is_bounded_even_with_continuous_sources(pair):
    dual, left, right, _ = pair
    left.continuous_sample = sample(100)
    right.continuous_sample = sample(100)
    assert dual.read() is not None
    assert left.read_count == right.read_count == 1


def test_portrait_mapping_stays_per_plate(pair):
    dual, left, right, _ = pair
    dual.orientation = BoardOrientation.PORTRAIT
    left.samples.append(sample(100))
    right.samples.append(sample(100, 10))
    assert dual.read() == SensorReading(4, 40, 6, 60, 100)
    assert dual.last_dual_reading.left == sample(100)


@pytest.mark.parametrize('timestamp', [98.49, 100.01, float('nan')])
def test_invalid_or_expired_source_timestamp_is_not_fresh(pair, timestamp):
    dual, left, right, _ = pair
    left.samples.append(sample(timestamp))
    right.samples.append(sample(100))
    assert dual.read() is None
    assert dual.last_dual_reading is None


def test_exact_freshness_boundary(pair):
    dual, left, right, clock = pair
    left.samples.append(sample(98.5))
    right.samples.append(sample(100))
    assert dual.read() is not None
    clock.return_value = 100.001
    assert dual.last_dual_reading is None


def test_close_clears_data_before_reopen(pair):
    dual, left, right, _ = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    dual.read()
    dual.close()
    dual.open()
    assert dual.read() is None
    assert dual.last_dual_reading is None


def test_reopen_after_child_disconnect_requires_new_pair(pair):
    dual, left, right, _ = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    dual.read()
    right.close()
    dual.open()
    left.samples.append(sample(100))
    assert dual.read() is None
    assert dual.last_dual_reading is None


def test_invalid_sensor_payload_immediately_invalidates_cached_pair(pair, monkeypatch):
    dual, left, right, clock = pair
    monkeypatch.setattr(FakeBackend, "get_diagnostics",
                        lambda self: {"recovery_blocked": getattr(self, "invalid", False)},
                        raising=False)
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    assert dual.read() is not None
    clock.return_value = 100.1
    left.invalid = True
    right.samples.append(sample(100.1))
    assert dual.read() is None
    assert dual.last_dual_reading is None
    assert dual.get_diagnostics()["left"]["error"] == "invalid_sensor_data"
    assert not dual.get_diagnostics()["ready"]
    assert left.is_open and right.is_open  # no reconnect or close side effect
    left.invalid = False
    left.samples.append(sample(100.2))
    clock.return_value = 100.2
    assert dual.read() is None  # discarded cached peer cannot be resurrected
    right.samples.append(sample(100.3))
    clock.return_value = 100.3
    assert dual.read() is not None


def test_invalid_payload_property_does_not_expose_previous_healthy_pair(pair, monkeypatch):
    dual, left, right, _ = pair
    monkeypatch.setattr(FakeBackend, "get_diagnostics",
                        lambda self: {"recovery_blocked": getattr(self, "invalid", False)},
                        raising=False)
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    dual.read()
    left.invalid = True
    assert dual.last_dual_reading is None
    assert left.read_count == right.read_count == 1
