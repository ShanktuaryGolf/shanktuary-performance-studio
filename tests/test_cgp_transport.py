"""Bounded parser, stream ownership, lifecycle and network-free mDNS tests."""

import asyncio
import struct
import threading
import time
from queue import Queue
from types import SimpleNamespace

import pytest

from src.connections.cgp import CGPClient, CGPDevice, _device_from_info, discover

pytest.importorskip("aioquic")
from aioquic.quic.events import StopSendingReceived, StreamDataReceived, StreamReset

from src.connections.cgp_transport import (
    MALFORMED,
    MAX_MESSAGE_BYTES,
    MAX_PENDING_STREAMS,
    MAX_RETIRED_STREAMS,
    NOT_INTERESTED,
    CGPProtocol,
    FramedJSONBuffer,
    frame,
)

SHOT = {"type": "shot", "shot_number": 1, "ball_speed_meters_per_second": 50,
        "vertical_launch_angle_degrees": 12, "horizontal_launch_angle_degrees": -1}


def wire(channel, message):
    return struct.pack(">I", channel) + frame(message)


def test_fragmented_concatenated_unicode_frames():
    decoder = FramedJSONBuffer()
    messages = []
    for byte in frame({"name": "Golf ⛳"}) + frame({"ready": True}):
        messages.extend(decoder.feed(bytes([byte])))
        assert len(decoder.buffer) <= MAX_MESSAGE_BYTES
    assert messages == [{"name": "Golf ⛳"}, {"ready": True}]
    assert list(decoder.feed(b"", True)) == []


def test_maximum_frame_size_accepted():
    body = b'{"x":"' + b"a" * (MAX_MESSAGE_BYTES - 8) + b'"}'
    assert len(body) == MAX_MESSAGE_BYTES
    result = list(FramedJSONBuffer().feed(struct.pack(">I", len(body)) + body + frame({}), True))
    assert len(result[0]["x"]) == MAX_MESSAGE_BYTES - 8
    assert result[1] == {}


@pytest.mark.parametrize("body", [b"[]", b"null", b"1", b"{}{}", b'{"x":NaN}', b'{"x":Infinity}',
                                    b'{"x":1e999}', b'{"x":1,"x":2}', b'{"x":"\xff"}', b'{"x":',
                                    b"\xef\xbb\xbf{}", b'{"x":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"])
def test_invalid_json_rejected(body):
    with pytest.raises(ValueError):
        list(FramedJSONBuffer().feed(struct.pack(">I", len(body)) + body))


@pytest.mark.parametrize("length", [0, 65536, 2**32 - 1])
def test_invalid_length_rejected_before_allocation(length):
    decoder = FramedJSONBuffer()
    with pytest.raises(ValueError):
        list(decoder.feed(struct.pack(">I", length)))
    assert not decoder.buffer


@pytest.mark.parametrize("data", [b"\x00", b"\x00\x00\x00", struct.pack(">I", 20), struct.pack(">I", 20) + b"{}"])
def test_fin_inside_frame_rejected(data):
    with pytest.raises(ValueError):
        list(FramedJSONBuffer().feed(data, True))


def protocol_fixture():
    class FakeQuic:
        def __init__(self):
            self.stopped = []
        def stop_stream(self, sid, code):
            self.stopped.append((sid, code))
    statuses, queue = [], Queue()
    protocol = CGPProtocol(FakeQuic(), shot_queue=queue, on_status=lambda *a, **k: statuses.append((a, k)),
                           device=CGPDevice("Fixture", "127.0.0.1", 12345))
    protocol.transmit = lambda: None
    protocol._ready = True
    return protocol, queue, statuses


def event(protocol, sid, data, ended=False):
    protocol.quic_event_received(StreamDataReceived(data=data, stream_id=sid, end_stream=ended))


def test_duplicate_channels_ownership_stream_reset_and_counter():
    async def scenario():
        protocol, queue, _ = protocol_fixture()
        event(protocol, 3, wire(1, SHOT))
        event(protocol, 7, wire(1, SHOT))
        assert protocol._quic.stopped == [(7, NOT_INTERESTED)]
        protocol.quic_event_received(StreamReset(error_code=0, stream_id=3))
        event(protocol, 11, wire(1, SHOT), True)
        assert queue.qsize() == 1
        event(protocol, 15, wire(1, dict(SHOT, shot_number=2)), True)
        assert queue.qsize() == 2
        assert not protocol._buffers
        for sid, channel in ((19, 6), (23, 7), (27, 3), (31, 5), (35, 8), (39, 1000)):
            event(protocol, sid, wire(channel, {}))
            assert protocol._quic.stopped[-1] == (sid, NOT_INTERESTED)
        event(protocol, 1, wire(2, {}))  # Bidirectional compatibility is explicitly unsupported.
        assert protocol._quic.stopped[-1] == (1, NOT_INTERESTED)
    asyncio.run(scenario())


def test_malformed_stream_isolated_and_channel_can_reopen():
    async def scenario():
        protocol, queue, _ = protocol_fixture()
        event(protocol, 3, struct.pack(">II", 1, 65536))
        assert protocol._quic.stopped == [(3, MALFORMED)]
        event(protocol, 3, wire(1, SHOT), True)
        event(protocol, 7, wire(1, SHOT), True)
        assert queue.qsize() == 1
        event(protocol, 11, b"\x00", True)
        assert protocol._quic.stopped == [(3, MALFORMED)]  # Ended streams cannot be STOP_SENDING.
    asyncio.run(scenario())


def test_status_patches_and_reopening_snapshot():
    async def scenario():
        protocol, _, statuses = protocol_fixture()
        event(protocol, 3, wire(4, {"type": "status", "ready": True, "battery_percent": 80}))
        event(protocol, 3, frame({"type": "status", "ready": None, "message": "Ball missing"}))
        assert protocol.device_status == {"battery_percent": 80, "message": "Ball missing"}
        protocol.quic_event_received(StreamReset(error_code=0, stream_id=3))
        event(protocol, 7, wire(4, {"type": "status", "ready": True}))
        assert protocol.device_status == {"ready": True}
        protocol.quic_event_received(StopSendingReceived(error_code=1, stream_id=2))
        assert statuses[-1][0][0] == "limited"
    asyncio.run(scenario())


def test_shots_before_info_and_information_only_version():
    async def scenario():
        protocol, queue, _ = protocol_fixture()
        event(protocol, 3, wire(1, SHOT))
        event(protocol, 7, wire(0, {"type": "info", "protocol_version": "99.0.0", "name": "New"}))
        assert queue.qsize() == 1
        assert protocol.device_info["protocol_version"] == "99.0.0"
    asyncio.run(scenario())


def test_pending_and_retired_stream_bookkeeping_bounded():
    async def scenario():
        protocol, queue, _ = protocol_fixture()
        event(protocol, 3, wire(1, SHOT))
        for number in range(1, MAX_RETIRED_STREAMS + 100):
            event(protocol, number * 4 + 3, wire(1000, {}))
        assert len(protocol._dead) == MAX_RETIRED_STREAMS
        event(protocol, 3, frame(dict(SHOT, shot_number=2)))
        assert queue.qsize() == 2  # Tombstone pruning must not retire a live old stream.
        for number in range(MAX_PENDING_STREAMS + 100):
            event(protocol, (number + MAX_RETIRED_STREAMS + 200) * 4 + 3, b"\x00")
        assert len(protocol._prefixes) == MAX_PENDING_STREAMS
        assert len(protocol._dead) == MAX_RETIRED_STREAMS
    asyncio.run(scenario())


def test_discovery_keeps_service_name_and_never_trusts_txt_key():
    info = SimpleNamespace(name="Monitor._common-golf._udp.local.", port=4567,
                           properties={b"vendor": b"Vendor", b"fingerprint": b"fake"},
                           parsed_scoped_addresses=lambda: ["::", "ff02::1", "fe80::1%2", "192.168.1.5"])
    device = _device_from_info(info)
    assert device.name == "Monitor"
    assert device.service_name == info.name
    assert device.host == "192.168.1.5"
    assert device.vendor == "Vendor"
    assert not hasattr(device, "fingerprint")


@pytest.mark.parametrize("timeout", [0, -1, 31, True, "3"])
def test_discovery_timeouts_bounded(timeout):
    with pytest.raises(ValueError):
        discover(timeout)


def test_discovery_resolves_removes_and_cleans_up_without_network(monkeypatch):
    zc = pytest.importorskip("zeroconf.asyncio")
    state = {"closed": False, "cancelled": False, "slow_cancelled": False}
    class FakeZeroconf:
        zeroconf = object()
        async def async_close(self):
            state["closed"] = True
    class FakeInfo:
        properties = {b"vendor": b"Fixture"}
        port = 12345
        def __init__(self, service_type, name):
            self.name = name
        def parsed_addresses(self):
            return ["127.0.0.1"]
        async def async_request(self, zeroconf, timeout):
            if self.name.startswith("Slow"):
                try:
                    await asyncio.sleep(100)
                finally:
                    state["slow_cancelled"] = True
            if self.name.startswith("Broken"):
                raise OSError("fixture resolution failure")
            return True
    class FakeBrowser:
        def __init__(self, zeroconf, service_type, listener):
            for name in ("Live", "Removed", "Slow", "Broken"):
                listener.add_service(zeroconf, service_type, name + "." + service_type)
            listener.remove_service(zeroconf, service_type, "Removed." + service_type)
        async def async_cancel(self):
            state["cancelled"] = True
    monkeypatch.setattr(zc, "AsyncZeroconf", FakeZeroconf)
    monkeypatch.setattr(zc, "AsyncServiceBrowser", FakeBrowser)
    monkeypatch.setattr(zc, "AsyncServiceInfo", FakeInfo)
    assert [d.name for d in discover(.01)] == ["Live"]
    assert all(state.values())


def test_stop_cancels_pending_connection_and_restart_has_no_leaked_worker(monkeypatch):
    import src.connections.cgp_transport as transport
    started, cancelled = threading.Event(), threading.Event()
    async def pending(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(transport, "connect_client", pending)
    client = CGPClient(Queue())
    for _ in range(2):
        started.clear()
        cancelled.clear()
        client.start(CGPDevice("Fixture", "127.0.0.1", 12345))
        assert started.wait(2)
        before = time.monotonic()
        client.stop()
        assert time.monotonic() - before < 2
        assert cancelled.is_set() and not client.is_running
    client.stop()


def test_terminal_error_not_overwritten_by_disconnected(monkeypatch):
    import src.connections.cgp_transport as transport
    async def failed(*args):
        raise ValueError("test failure")
    monkeypatch.setattr(transport, "connect_client", failed)
    statuses = []
    client = CGPClient(Queue(), statuses.append)
    client.start(CGPDevice("Fixture", "127.0.0.1", 12345))
    client._thread.join(2)
    assert statuses[-1]["status"] == "error"
    assert "test failure" in statuses[-1]["message"]
    assert statuses[-1]["connected"] is False
