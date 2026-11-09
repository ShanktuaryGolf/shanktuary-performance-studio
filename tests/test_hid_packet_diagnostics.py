"""Passive packet evidence and rejection of impossible all-zero ADC payloads."""
import struct
from types import SimpleNamespace

import pytest

import src.hardware.pressure.hid_backend as hb


class Device:
    def __init__(self):
        self.packets = []
        self.writes = []
        self.reads = 0
        self.write_error = None
        self.write_result = None

    def write(self, data):
        self.writes.append(bytes(data))
        if self.write_error:
            raise self.write_error
        return len(data) if self.write_result is None else self.write_result

    def read(self, *args):
        self.reads += 1
        return self.packets.pop(0) if self.packets else []

    def open_path(self, path):
        pass

    def set_nonblocking(self, value):
        pass

    def close(self):
        pass


def packet(value, report_id=0x32):
    return bytes([report_id, 0, 0]) + struct.pack('>4H', *([value] * 4))


@pytest.fixture
def rig(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(hb, 'time', SimpleNamespace(
        monotonic=lambda: now[0], sleep=lambda seconds: None))
    monkeypatch.setattr(hb.sys, 'platform', 'linux')
    backend = hb.HidBackend(b'board')
    device = Device()
    backend._device = device
    backend._calibration = hb.DEFAULT_CALIBRATION
    return backend, device, now


@pytest.mark.parametrize('report_id', [0x32, 0x34])
def test_zero_rejected_then_idle_and_load_resume(rig, report_id):
    backend, device, now = rig
    device.packets = [packet(0, report_id)]
    assert backend.read() is None
    diag = backend.get_diagnostics()
    assert diag['sensor_data_status'] == 'invalid_zero_payload'
    assert diag['recovery_blocked'] is True
    assert diag['last_error'] == hb.INVALID_ZERO_PAYLOAD
    assert diag['last_sample_timestamp'] is None
    assert set(diag['raw_cells'].values()) == {0}
    assert diag['zero_extension_count'] == diag['zero_extension_streak'] == 1
    assert diag['last_nonzero_extension_timestamp'] is None
    device.packets = [packet(2400, report_id)]
    now[0] += 1
    assert backend.read().total == 0
    diag = backend.get_diagnostics()
    assert diag['sensor_data_status'] == 'valid'
    assert diag['recovery_blocked'] is False
    assert diag['last_error'] is None
    assert diag['last_nonzero_extension_timestamp'] == now[0]
    assert diag['zero_extension_count'] == 1
    assert diag['zero_extension_streak'] == 0
    device.packets = [packet(2800, report_id)]
    assert backend.read().total == 68


def test_latest_zero_wins_and_does_not_refresh_sample(rig):
    backend, device, now = rig
    device.packets = [packet(2800)]
    timestamp = backend.read().timestamp
    now[0] += 1
    device.packets = [packet(2900), packet(0), bytes([0x22, 0, 0, 0x12, 0])]
    assert backend.read() is None
    diag = backend.get_diagnostics()
    assert diag['last_sample_timestamp'] == timestamp
    assert diag['last_packet_timestamp'] == now[0]
    assert diag['sensor_data_status'] == 'invalid_zero_payload'
    # A non-extension packet does not clear the current invalid payload.
    device.packets = [bytes([0x20, 0, 0, 2, 0, 0, 180])]
    assert backend.read() is None
    assert backend.get_diagnostics()['last_error'] == hb.INVALID_ZERO_PAYLOAD
    device.packets = [packet(0), packet(2800)]
    assert backend.read().total == 68


def test_nonzero_uncalibrated_is_not_kg(rig):
    backend, device, now = rig
    backend._calibration = None
    device.packets = [packet(2800)]
    assert backend.read() is None
    assert backend.get_diagnostics()['sensor_data_status'] == 'uncalibrated'


def test_packet_evidence_bounded_and_independent(rig):
    backend, device, now = rig
    for report_id in range(256):
        backend._observe_packet(bytes([report_id]) + bytes(range(80)))
    diag = backend.get_diagnostics()
    assert diag['packet_count'] == 256
    assert len(diag['report_counts']) == len(diag['last_packets_by_report']) == 256
    assert set(diag['report_counts'].values()) == {1}
    assert len(diag['recent_packets']) == 8
    assert diag['last_packet'] == dict(timestamp=10.0, report_id=255, length=81,
                                       hex=(bytes([255]) + bytes(range(63))).hex())
    diag['last_packet']['hex'] = 'changed'
    diag['recent_packets'][0]['length'] = 0
    diag['last_packets_by_report'][255]['length'] = 0
    diag['report_counts'][255] = 0
    fresh = backend.get_diagnostics()
    assert fresh['last_packet']['length'] == 81
    assert fresh['recent_packets'][0]['length'] == 81
    assert fresh['last_packets_by_report'][255]['length'] == 81
    assert fresh['report_counts'][255] == 1
    backend._observe_packet(bytes([255]))
    assert backend.get_diagnostics()['report_counts'][255] == 2
    assert backend.get_diagnostics()['packet_count'] == 257


def test_ack_status_and_write_observation(rig):
    backend, device, now = rig
    for error in range(12):
        backend._observe_packet(bytes([0x22, 0, 0, 0x16, error]))
    backend._observe_packet(bytes([0x22, 0]))  # truncated ACK ignored
    device.packets = [bytes([0x20, 0, 0, 0x12, 0, 0, 190])]
    assert backend.read() is None
    diag = backend.get_diagnostics()
    assert len(diag['recent_acks']) == 8
    assert diag['recent_acks'][0]['error'] == 4
    assert diag['recent_acks'][-1] == dict(timestamp=10.0, report_id=0x16, error=11)
    assert diag['last_status'] == dict(timestamp=10.0, flags=0x12,
                                      extension_present=True, battery=190)
    assert device.writes == [bytes([0x12, 0x04, 0x32])]
    assert device.reads == 2
    assert diag['recent_writes'] == [dict(timestamp=10.0, hex='120432',
                                          requested_length=3, return_count=3, error=None)]
    backend._observe_packet(bytes([0x20, 0, 0]))
    assert backend.get_diagnostics()['last_status'] == diag['last_status']
    for _ in range(12):
        backend._write(bytes(range(80)))
    device.write_result = 1
    assert backend._write(b'abc') == 1
    device.write_error = OSError('write failed')
    with pytest.raises(OSError):
        backend._write(b'def')
    diag = backend.get_diagnostics()
    assert len(diag['first_writes']) == 8
    assert diag['first_writes'][0]['hex'] == '120432'
    assert len(diag['first_acks']) == 8
    assert diag['first_acks'][0]['error'] == 0
    assert diag['first_acks'][-1]['error'] == 7
    diag['first_writes'][0]['hex'] = 'changed'
    diag['first_acks'][0]['error'] = 99
    assert backend.get_diagnostics()['first_writes'][0]['hex'] == '120432'
    assert backend.get_diagnostics()['first_acks'][0]['error'] == 0
    assert len(diag['recent_writes']) == 8
    assert diag['recent_writes'][0]['requested_length'] == 80
    assert diag['recent_writes'][0]['hex'] == bytes(range(64)).hex()
    assert diag['recent_writes'][-2]['return_count'] == 1
    assert diag['recent_writes'][-1]['error'] == 'write failed'
    assert diag['recent_writes'][-1]['return_count'] is None
    diag['recent_writes'][0]['hex'] = 'changed'
    diag['recent_acks'][0]['error'] = 99
    diag['last_status']['battery'] = 0
    assert backend.get_diagnostics()['recent_writes'][0]['hex'] != 'changed'
    assert backend.get_diagnostics()['recent_acks'][0]['error'] == 4
    assert backend.get_diagnostics()['last_status']['battery'] == 190


def test_existing_open_shutdown_command_sequence_unchanged(rig, monkeypatch):
    backend, device, now = rig
    backend._device = None
    monkeypatch.setattr(hb, 'hid', SimpleNamespace(device=lambda: device))
    calibration = struct.pack('>12H', *([2400] * 4 + [2800] * 4 + [3200] * 4))
    device.packets = [bytes([0x21, 0, 0, 0xf0, 0, 0x24]) + calibration[:16],
                      bytes([0x21, 0, 0, 0x70, 0, 0x34]) + calibration[16:]]
    backend.open()
    assert device.reads == 2
    assert backend.get_diagnostics()['packet_count'] == 2
    backend.shutdown()
    assert device.writes == [
        bytes([0x16, 0x04, 0xA4, 0, 0xF0, 1, 0x55] + [0] * 15),
        bytes([0x16, 0x04, 0xA4, 0, 0xFB, 1, 0] + [0] * 15),
        bytes([0x17, 0x04, 0xA4, 0, 0x24, 0, 0x18]),
        bytes([0x11, 0x10]), bytes([0x12, 0x04, 0x32]),
        bytes([0x11, 0]), bytes([0x12, 0, 0x30]),
    ]
    assert len(backend.get_diagnostics()['recent_writes']) == 7
