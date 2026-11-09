"""Factory-only HID measurements and truthful connection diagnostics."""
import struct
from types import SimpleNamespace

import pytest

import src.hardware.pressure.hid_backend as hb

CAL = struct.pack('>12H', *([2400] * 4 + [2800] * 4 + [3200] * 4))


def chunk(address, data, error=0):
    return bytes([0x21, 0, 0, ((len(data) - 1) << 4) | error,
                  address >> 8, address & 255]) + data


def sample(value=2800):
    return bytes([0x32, 0, 0]) + struct.pack('>4H', *([value] * 4))


class Clock:
    now = 10.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Device:
    def __init__(self, clock, packets=()):
        self.clock = clock
        self.packets = list(packets)
        self.reads = 0
        self.closed = False

    def open_path(self, path):
        pass

    def set_nonblocking(self, value):
        pass

    def write(self, data):
        return len(data)

    def read(self, size, timeout_ms=0):
        self.reads += 1
        if self.packets:
            packet = self.packets.pop(0)
            if isinstance(packet, Exception):
                raise packet
            return packet
        self.clock.sleep(timeout_ms / 1000)
        return []

    def close(self):
        self.closed = True


@pytest.fixture
def setup(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(hb, 'time', clock)
    monkeypatch.setattr(hb.sys, 'platform', 'linux')

    def make(packets=()):
        device = Device(clock, packets)
        monkeypatch.setattr(hb, 'hid', SimpleNamespace(device=lambda: device))
        backend = hb.HidBackend(b'board')
        return backend, device, clock
    return make


def test_late_interleaved_out_of_order_calibration(setup):
    backend, device, clock = setup(
        [bytes([0x22])] * 30 + [chunk(0x34, CAL[16:]), bytes([0x20]),
                                chunk(0x24, CAL[:16])])
    backend.open()
    assert backend.get_diagnostics()['calibration_status'] == 'factory'
    assert backend.get_diagnostics()['last_sample_timestamp'] is None
    device.packets = [sample()]
    reading = backend.read()
    assert reading.total == 68
    assert reading.timestamp == backend.get_diagnostics()['last_sample_timestamp']
    assert backend.get_diagnostics()['raw_cells']['top_left'] == 2800
    assert backend.get_diagnostics()['last_error'] is None


@pytest.mark.parametrize('packets', [
    [chunk(0x24, CAL[:16])],  # incomplete
    [chunk(0x24, CAL[:16]), chunk(0x24, CAL[:16])],  # duplicate isn't completion
    [chunk(0x24, CAL[:16], error=1), chunk(0x34, CAL[16:])],
    [chunk(0x25, CAL[:16]), chunk(0x34, CAL[16:])],  # missing first byte
    [chunk(0x24, CAL[:16])[:-1], chunk(0x34, CAL[16:])],  # truncated
    [chunk(0x24, CAL[:16]), chunk(0x38, CAL[16:])],  # outside request
    [bytes([0x21, 0, 0])],
    [chunk(0x24, CAL[:16]), chunk(0x24, b'\x00' * 16), chunk(0x34, CAL[16:])],
])
def test_invalid_calibration_cannot_produce_kg(setup, packets):
    backend, device, clock = setup(packets)
    backend.open()
    assert backend.is_open
    assert backend.get_diagnostics()['calibration_status'] == 'unavailable'
    assert backend.get_diagnostics()['last_error']
    device.packets = [sample(4000)]
    assert backend.read() is None
    diagnostics = backend.get_diagnostics()
    assert diagnostics['raw_cells']['top_left'] == 4000
    assert diagnostics['last_packet_timestamp'] == clock.now
    assert diagnostics['last_sample_timestamp'] is None
    device.packets = [sample(4200)]
    assert backend.read() is None  # no fabricated delta calibration either


@pytest.mark.parametrize('values', [[0] * 12, [2400] * 12,
                                   [2400] * 4 + [2300] * 4 + [3200] * 4,
                                   [2400] * 4 + [2800] * 4 + [2700] * 4])
def test_reject_invalid_reference_intervals(setup, values):
    data = struct.pack('>12H', *values)
    backend, device, clock = setup([chunk(0x24, data[:16]), chunk(0x34, data[16:])])
    backend.open()
    assert backend.get_diagnostics()['calibration_status'] == 'unavailable'
    assert 'strictly increasing' in backend.get_diagnostics()['last_error']


@pytest.mark.parametrize('size', [0, 23, 25])
def test_parser_requires_exact_full_payload(size):
    with pytest.raises(ValueError):
        hb.HidBackend._parse_calibration(b'\x01' * size)


def test_silent_open_is_not_streaming_and_deadline_bounded(setup, capsys):
    backend, device, clock = setup()
    start = clock.now
    backend.open()
    assert clock.now - start < hb.CALIBRATION_TIMEOUT + 0.3
    assert device.reads <= hb.CALIBRATION_MAX_READS
    assert backend.get_diagnostics() == {
        'calibration_status': 'unavailable', 'last_packet_timestamp': None,
        'last_sample_timestamp': None, 'raw_cells': None,
        'last_error': 'Factory calibration unavailable: incomplete response',
        'is_open': True,
    }
    assert 'streaming' not in capsys.readouterr().out


def test_busy_input_bounded_by_read_count(setup):
    backend, device, clock = setup([bytes([0x22])] * 1000)
    backend.open()
    assert device.reads == hb.CALIBRATION_MAX_READS
    assert backend.get_diagnostics()['last_sample_timestamp'] is None


def test_raw_reports_during_initialization_are_observed(setup):
    backend, device, clock = setup([sample(4000)])
    backend.open()
    assert backend.get_diagnostics()['raw_cells']['bottom_right'] == 4000
    assert backend.get_diagnostics()['last_sample_timestamp'] is None


def test_disconnect_does_not_publish_queued_sample(setup):
    backend, device, clock = setup([chunk(0x24, CAL[:16]), chunk(0x34, CAL[16:])])
    backend.open()
    device.packets = [sample(), OSError('disconnected')]
    assert backend.read() is None
    diagnostics = backend.get_diagnostics()
    assert not diagnostics['is_open']
    assert 'disconnected' in diagnostics['last_error']
    assert diagnostics['last_sample_timestamp'] is None


def test_close_failure_is_reported(setup, monkeypatch):
    backend, device, clock = setup()
    backend.open()
    monkeypatch.setattr(hb, '_UNSETTLED_HANDLES', [])

    def fail():
        raise OSError('close failed')
    device.close = fail
    backend.close()
    assert not backend.is_open
    assert 'close failed' in backend.get_diagnostics()['last_error']
    assert device in hb._UNSETTLED_HANDLES


def test_open_failure_is_closed_and_reported(setup):
    backend, device, clock = setup([OSError('gone')])
    with pytest.raises(OSError):
        backend.open()
    assert not backend.is_open
    assert device.closed
    assert 'initialization failed' in backend.get_diagnostics()['last_error']


def test_reopen_resets_stale_diagnostics(setup):
    backend, device, clock = setup([chunk(0x24, CAL[:16]), chunk(0x34, CAL[16:])])
    backend.open()
    device.packets = [sample()]
    assert backend.read() is not None
    backend.close()
    backend.open()
    assert backend.get_diagnostics()['last_sample_timestamp'] is None
    assert backend.get_diagnostics()['raw_cells'] is None
    assert backend.get_diagnostics()['calibration_status'] == 'unavailable'


def test_packet_timestamp_does_not_refresh_last_sample(setup):
    backend, device, clock = setup([chunk(0x24, CAL[:16]), chunk(0x34, CAL[16:])])
    backend.open()
    device.packets = [sample()]
    reading = backend.read()
    clock.sleep(1)
    device.packets = [bytes([0x22])]
    assert backend.read() is None
    diagnostics = backend.get_diagnostics()
    assert diagnostics['last_sample_timestamp'] == reading.timestamp
    assert diagnostics['last_packet_timestamp'] > reading.timestamp


def test_raw_cell_names_and_snapshot_isolation(setup):
    backend, device, clock = setup()
    backend.open()
    device.packets = [bytes([0x32, 0, 0]) + struct.pack('>4H', 1, 2, 3, 4)]
    assert backend.read() is None
    diagnostics = backend.get_diagnostics()
    assert diagnostics['raw_cells'] == dict(top_right=1, bottom_right=2,
                                             top_left=3, bottom_left=4)
    diagnostics['raw_cells']['top_left'] = 999
    assert backend.get_diagnostics()['raw_cells']['top_left'] == 3


def test_bad_chunk_does_not_poison_later_complete_valid_response(setup):
    backend, device, clock = setup([chunk(0x24, CAL[:16], error=8),
                                   chunk(0x24, CAL[:16]), chunk(0x34, CAL[16:])])
    backend.open()
    assert backend.get_diagnostics()['calibration_status'] == 'factory'
    assert backend.get_diagnostics()['last_error'] is None
