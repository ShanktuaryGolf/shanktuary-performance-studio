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


def test_diagnostics_queries_each_child_once_without_polling(pair, monkeypatch):
    dual, left, right, _ = pair
    calls = []

    def diagnostics(backend):
        calls.append(backend)
        return {"last_sample_timestamp": 99.8, "last_packet_timestamp": 99.9}

    monkeypatch.setattr(FakeBackend, "get_diagnostics", diagnostics, raising=False)
    result = dual.get_diagnostics()
    assert calls == [left, right]
    assert left.read_count == right.read_count == 0
    assert result["ready"] is False  # no aggregate cache was populated
    assert result["left"]["child_diagnostics"]["fresh"] is True
    assert result["left"]["child_diagnostics"]["sample_age_seconds"] == 0.2
    assert result["left"]["child_diagnostics"]["packet_age_seconds"] == 0.1


def test_missing_child_diagnostics_does_not_invent_live_observations(pair):
    dual, left, right, _ = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    assert dual.read() is not None
    result = dual.get_diagnostics()
    assert result["ready"] is True
    child = result["left"]["child_diagnostics"]
    assert child["device_id"] is None
    assert child["sample_age_seconds"] is None
    assert child["packet_age_seconds"] is None
    assert child["fresh"] is child["packet_fresh"] is False


@pytest.fixture
def hid_pair(monkeypatch):
    import src.hardware.pressure.hid_backend as hb

    class Device:
        def __init__(self):
            self.packets = deque()
            self.reads = 0

        def read(self, *args):
            self.reads += 1
            return self.packets.popleft() if self.packets else []

        def write(self, *args):
            pytest.fail("Diagnostics must not send HID commands")

        def open_path(self, *args):
            pytest.fail("Diagnostics must not open HID handles")

        def close(self):
            pytest.fail("Diagnostics must not close HID handles")

    now = [100.0]
    monkeypatch.setattr(hb.time, "monotonic", lambda: now[0])
    left = hb.HidBackend(b"\\\\?\\HID#left-\xff")
    right = hb.HidBackend("\\\\?\\HID#right")
    for board in (left, right):
        board._device = Device()
        board._calibration = hb.DEFAULT_CALIBRATION
    return DualWbbBackend(left, right), left, right, now


def extension_packet(value):
    import struct
    return bytes([0x32, 0, 0]) + struct.pack(">4H", *([value] * 4))


def test_zero_child_keeps_current_peer_diagnostics_after_caches_clear(hid_pair):
    dual, left, right, now = hid_pair
    for board in (left, right):
        board._device.packets.append(extension_packet(2800))
    assert dual.read() is not None
    now[0] = 100.1
    left._device.packets.append(extension_packet(0))
    right._device.packets.append(extension_packet(2900))
    assert dual.read() is None
    assert dual.last_dual_reading is None
    reads = (left._device.reads, right._device.reads)

    result = dual.get_diagnostics()
    assert not result["ready"]
    assert result["left"]["error"] == "invalid_sensor_data"
    assert result["right"]["error"] == "waiting_for_sample"  # aggregate cache only
    a = result["left"]["child_diagnostics"]
    b = result["right"]["child_diagnostics"]
    assert result["left"]["device_id"].encode("latin-1") == left._device_path
    assert result["right"]["device_id"] == right._device_path
    assert a["device_id"] == result["left"]["device_id"]
    assert a["sensor_data_status"] == "invalid_zero_payload"
    assert a["recovery_blocked"] and not a["fresh"]
    assert a["packet_fresh"] and a["packet_count"] == 2
    assert a["sample_age_seconds"] == 0.1
    assert a["packet_age_seconds"] == 0
    assert a["zero_extension_count"] == a["zero_extension_streak"] == 1
    assert set(a["raw_cells"].values()) == {0}
    assert b["fresh"] and b["packet_fresh"]
    assert b["sample_age_seconds"] == b["packet_age_seconds"] == 0
    assert b["last_sample_timestamp"] == 100.1
    assert b["packet_count"] == 2
    assert set(b["raw_cells"].values()) == {2900}

    now[0] = 102
    later = dual.get_diagnostics()["right"]["child_diagnostics"]
    assert later["sample_age_seconds"] == later["packet_age_seconds"] == 1.9
    assert not later["fresh"] and not later["packet_fresh"]
    assert (left._device.reads, right._device.reads) == reads
    assert left.is_open and right.is_open
    assert dual._left_reading is dual._right_reading is None


def test_child_evidence_stays_bounded_and_detached(hid_pair):
    dual, left, right, _ = hid_pair
    for board in (left, right):
        board._device.packets.extend(extension_packet(2800) for _ in range(30))
    assert dual.read() is not None
    reads = (left._device.reads, right._device.reads)
    for _ in range(3):
        child = dual.get_diagnostics()["left"]["child_diagnostics"]
        assert child["packet_count"] == 30
        assert len(child["recent_packets"]) == 8
        assert child["recent_packets"][0]["length"] == 11
        child["recent_packets"][0]["length"] = 0
        child["raw_cells"]["top_left"] = 0
        assert left.get_diagnostics()["raw_cells"]["top_left"] == 2800
    assert (left._device.reads, right._device.reads) == reads


@pytest.mark.parametrize("sample_stamp,packet_stamp,expected_age,fresh,packet_fresh", [
    (98.5, 100, 1.5, True, True),
    (98.499, 100, 1.501, False, True),
    (100.01, 100.01, -0.01, False, False),
    (float("nan"), float("inf"), None, False, False),
    (None, None, None, False, False),
])
def test_child_freshness_uses_original_unrounded_timestamps(
        hid_pair, sample_stamp, packet_stamp, expected_age, fresh, packet_fresh):
    dual, left, _, _ = hid_pair
    left._last_sample_timestamp = sample_stamp
    left._last_packet_timestamp = packet_stamp
    child = dual.get_diagnostics()["left"]["child_diagnostics"]
    assert child["sample_age_seconds"] == expected_age
    assert child["fresh"] is fresh
    assert child["packet_fresh"] is packet_fresh


def test_closed_or_uncalibrated_child_never_claims_fresh_weight(hid_pair):
    dual, left, _, _ = hid_pair
    left._last_sample_timestamp = left._last_packet_timestamp = 100
    left._calibration = None
    child = dual.get_diagnostics()["left"]["child_diagnostics"]
    assert not child["fresh"] and child["packet_fresh"]
    left._device = None
    child = dual.get_diagnostics()["left"]["child_diagnostics"]
    assert not child["fresh"] and not child["packet_fresh"]


def test_board_loads_return_only_observed_calibrated_samples(pair):
    dual, left, right, _ = pair
    left.samples.append(sample(99.8))
    right.samples.append(sample(99.9, 2))
    assert dual.get_board_loads() == {
        side: {"device_id": None, "total_kg": None, "timestamp": None,
               "fresh": False, "error": "waiting_for_sample"}
        for side in ("left", "right")
    }
    assert left.read_count == right.read_count == 0
    assert dual.read() is not None
    assert dual.get_board_loads() == {
        "left": {"device_id": None, "total_kg": 10, "timestamp": 99.8,
                 "fresh": True, "error": None},
        "right": {"device_id": None, "total_kg": 20, "timestamp": 99.9,
                  "fresh": True, "error": None},
    }


def test_board_loads_do_not_convert_raw_diagnostic_cells_to_weight(hid_pair):
    dual, left, right, _ = hid_pair
    for board in (left, right):
        board._raw_cells = dict.fromkeys(
            ("top_left", "top_right", "bottom_left", "bottom_right"), 2800)
        board._last_sample_timestamp = board._last_packet_timestamp = 100
        board._device.packets.append(extension_packet(2800))
    for side in dual.get_board_loads().values():
        assert side["total_kg"] is None and side["timestamp"] is None
        assert side["error"] == "waiting_for_sample"
    assert left._device.reads == right._device.reads == 0


@pytest.mark.parametrize("invalid_side", ["left", "right"])
def test_board_loads_keep_healthy_peer_when_zero_payload_clears_pair(hid_pair, invalid_side):
    dual, left, right, now = hid_pair
    boards = {"left": left, "right": right}
    healthy_side = "right" if invalid_side == "left" else "left"
    for board in boards.values():
        board._device.packets.append(extension_packet(2800))
    assert dual.read() is not None
    now[0] = 100.1
    boards[invalid_side]._device.packets.append(extension_packet(0))
    boards[healthy_side]._device.packets.append(extension_packet(2900))
    assert dual.read() is None
    assert dual.last_dual_reading is None
    reads = (left._device.reads, right._device.reads)

    result = dual.get_board_loads()
    assert result["left"]["device_id"].encode("latin-1") == left._device_path
    assert result["right"]["device_id"] == right._device_path
    assert result[invalid_side]["total_kg"] is None
    assert result[invalid_side]["timestamp"] is None
    assert not result[invalid_side]["fresh"]
    assert result[invalid_side]["error"] == "invalid_sensor_data"
    assert result[healthy_side]["total_kg"] == 85.0  # calibrated kg, not ADC counts
    assert result[healthy_side]["timestamp"] == 100.1
    assert result[healthy_side]["fresh"]
    assert result[healthy_side]["error"] is None
    assert dual._left_reading is dual._right_reading is dual._last_dual is None
    assert not dual.get_diagnostics()["ready"]

    now[0] = 101.7
    expired = dual.get_board_loads()[healthy_side]
    assert expired["total_kg"] is expired["timestamp"] is None
    assert not expired["fresh"] and expired["error"] == "stale_sample"
    assert result[healthy_side]["total_kg"] == 85.0
    assert (left._device.reads, right._device.reads) == reads
    assert left.is_open and right.is_open


def test_board_loads_are_passive_detached_and_leave_aggregate_caches_unchanged(pair, monkeypatch):
    dual, left, right, _ = pair
    calls = []

    def diagnostics(backend):
        calls.append(backend)
        return {"recovery_blocked": getattr(backend, "invalid", False)}

    monkeypatch.setattr(FakeBackend, "get_diagnostics", diagnostics, raising=False)
    original = sample(100)
    left.samples.append(original)
    right.samples.append(sample(100, 2))
    assert dual.read() is not None
    caches = (dual._left_reading, dual._right_reading, dual._last_dual)
    original.top_left = 999
    original.timestamp = 0

    def forbid_io(*args, **kwargs):
        pytest.fail("Load accessor must not read, open, close, or shut down a child")

    for method in ("read", "open", "close", "shutdown"):
        monkeypatch.setattr(FakeBackend, method, forbid_io)
    calls.clear()
    result = dual.get_board_loads()
    assert calls == [left, right]
    assert result["left"]["total_kg"] == 10
    assert result["left"]["timestamp"] == 100
    result["left"]["total_kg"] = 999
    result["right"]["timestamp"] = 0
    assert dual.get_board_loads()["left"]["total_kg"] == 10
    assert dual.get_board_loads()["right"]["timestamp"] == 100

    left.invalid = True
    assert dual.get_board_loads()["left"]["error"] == "invalid_sensor_data"
    assert all(before is after for before, after in zip(
        caches, (dual._left_reading, dual._right_reading, dual._last_dual)))
    left.invalid = False
    assert dual.get_board_loads()["left"]["error"] == "waiting_for_sample"
    assert dual.get_board_loads()["right"]["total_kg"] == 20


@pytest.mark.parametrize("during_read", [False, True])
def test_board_loads_discard_disconnected_child_only(pair, during_read):
    dual, left, right, clock = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100, 2))
    assert dual.read() is not None
    clock.return_value = 100.1
    if during_read:
        right.disconnect_on_read = True
        right.samples.append(sample(100.1, 3))
        left.samples.append(sample(100.1))
    else:
        right.close()
    assert dual.read() is None
    loads = dual.get_board_loads()
    assert loads["left"]["total_kg"] == 10
    assert loads["right"]["total_kg"] is loads["right"]["timestamp"] is None
    assert loads["right"]["error"] == "disconnected"
    right.open()
    assert dual.get_board_loads()["right"]["error"] == "waiting_for_sample"


@pytest.mark.parametrize("operation", ["close", "shutdown", "reopen"])
def test_board_loads_are_cleared_on_close_shutdown_and_reopen(pair, operation):
    dual, left, right, _ = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    assert dual.read() is not None
    if operation == "reopen":
        right.close()
    else:
        getattr(dual, operation)()
        assert all(side["error"] == "disconnected" for side in dual.get_board_loads().values())
    dual.open()
    assert all(side["error"] == "waiting_for_sample" for side in dual.get_board_loads().values())
    assert dual._left_reading is dual._right_reading is dual._last_dual is None


@pytest.mark.parametrize("timestamp,error", [
    (98.5, None),
    (98.499, "stale_sample"),
    (100.001, "stale_sample"),
    (float("nan"), "invalid_sample"),
    (float("inf"), "invalid_sample"),
    (-float("inf"), "invalid_sample"),
])
def test_board_loads_validate_original_sample_timestamp(pair, timestamp, error):
    dual, left, right, _ = pair
    left.samples.append(sample(timestamp))
    right.samples.append(sample(100))
    dual.read()
    load = dual.get_board_loads()["left"]
    assert load["error"] == error
    assert load["fresh"] is (error is None)
    assert load["total_kg"] == (10 if error is None else None)
    assert load["timestamp"] == (timestamp if error is None else None)


@pytest.mark.parametrize("scale,error", [
    (0, None), (1, None), (-1, "invalid_sample"),
    (float("nan"), "invalid_sample"),
    (float("inf"), "invalid_sample"),
    (-float("inf"), "invalid_sample"),
])
def test_board_loads_require_finite_nonnegative_kg(pair, scale, error):
    dual, left, right, _ = pair
    left.samples.append(sample(100, scale))
    right.samples.append(sample(100))
    dual.read()
    load = dual.get_board_loads()["left"]
    assert load["error"] == error
    assert load["fresh"] is (error is None)
    assert load["total_kg"] == (10 * scale if error is None else None)


def test_board_loads_never_refresh_timestamps_without_child_samples(pair):
    dual, left, right, clock = pair
    left.samples.append(sample(100))
    right.samples.append(sample(100))
    assert dual.read() is not None
    for timestamp in (100.1, 100.5, 101.5):
        clock.return_value = timestamp
        assert dual.read() is None
        assert dual.get_board_loads()["left"]["timestamp"] == 100
    clock.return_value = 101.50001
    assert dual.get_board_loads()["left"]["total_kg"] is None


def test_board_loads_never_keep_history_or_resurrect_uncalibrated_data(hid_pair):
    dual, left, right, now = hid_pair
    for index in range(20):
        now[0] = 100 + index / 100
        for board in (left, right):
            board._device.packets.append(extension_packet(2800 + index))
        dual.read()
    assert set(dual._observed_readings) == {"left", "right"}
    assert all(isinstance(reading, SensorReading) for reading in dual._observed_readings.values())
    assert dual.get_board_loads()["left"]["timestamp"] == now[0]
    calibration = left._calibration
    left._calibration = None
    load = dual.get_board_loads()["left"]
    assert load["error"] == "calibration_unavailable"
    assert load["total_kg"] is load["timestamp"] is None
    left._calibration = calibration
    assert dual.get_board_loads()["left"]["error"] == "waiting_for_sample"
    assert dual.get_board_loads()["right"]["fresh"]
