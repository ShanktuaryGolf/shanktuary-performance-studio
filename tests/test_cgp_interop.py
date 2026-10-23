"""Real loopback-only QUIC and optional pinned upstream-device interoperability.

Set CGP_REFERENCE_DIR to the exact upstream checkout. Only the unchanged
reference Connection/minimum Device definitions and framing helpers are
loaded from their AST. Its module-level TLS monkeypatch and persistent key
helper are NEVER executed. All listener tests bind 127.0.0.1 and certificates
are ephemeral in-memory Ed25519 identities, never files or saved credentials.
"""

import ast
import asyncio
import datetime
import json
import os
import pathlib
import random
import ssl
import struct
import subprocess
import types
from collections import OrderedDict
from queue import Queue

import pytest

pytest.importorskip("aioquic")
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import (
    HandshakeCompleted,
    StopSendingReceived,
    StreamDataReceived,
    StreamReset,
)
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID

from src.connections.cgp import CGPClient, CGPDevice
from src.connections.cgp_transport import ALPN, connect_client, frame

REFERENCE_COMMIT = "1c343a8aac2b21665e9ce002789dfcc98abe133f"
SHOT = {"type": "shot", "shot_number": 1, "ball_speed_meters_per_second": 67.3,
        "vertical_launch_angle_degrees": 12.1, "horizontal_launch_angle_degrees": -1.4}


def server_configuration(alpn=ALPN):
    key = ed25519.Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "loopback-cgp-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, None))
    config = QuicConfiguration(is_client=False, alpn_protocols=[alpn], verify_mode=ssl.CERT_NONE,
                               idle_timeout=90)
    config.certificate, config.private_key = cert, key
    return config


async def wait_until(predicate, seconds=4):
    deadline = asyncio.get_running_loop().time() + seconds
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("loopback condition not reached")
        await asyncio.sleep(.01)


class LoopbackDevice(QuicConnectionProtocol):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buffers, self.messages, self.declined = {}, [], []
        type(self).instances.append(self)

    def publish(self, channel, messages):
        sid = self._quic.get_next_available_stream_id(is_unidirectional=True)
        self._quic.send_stream_data(sid, struct.pack(">I", channel) + b"".join(frame(m) for m in messages))
        self.transmit()

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            self.publish(0, [{"type": "info", "protocol_version": "0.2.0", "name": "Loopback device"}])
            self.publish(1, [dict(SHOT, final=False, total_spin_revolutions_per_minute=2000, spin_axis_degrees=1),
                             dict(SHOT, final=True), dict(SHOT, final=True)])
            self.publish(4, [{"type": "status", "ready": True, "battery_percent": 50}])
            self.publish(3, [{"type": "club", "club_speed_meters_per_second": 45}])
        elif isinstance(event, StreamDataReceived):
            # Independent test-side whole-buffer reader, not the product decoder.
            buf = self.buffers.setdefault(event.stream_id, bytearray())
            buf.extend(event.data)
            if len(buf) < 4:
                return
            channel, offset = struct.unpack(">I", buf[:4])[0], 4
            while len(buf) >= offset + 4:
                length = struct.unpack(">I", buf[offset:offset + 4])[0]
                if len(buf) < offset + 4 + length:
                    break
                message = json.loads(buf[offset + 4:offset + 4 + length])
                record = (channel, message)
                if record not in self.messages:
                    self.messages.append(record)
                offset += 4 + length
        elif isinstance(event, StopSendingReceived):
            self.declined.append((event.stream_id, event.error_code))


def test_real_quic_final_only_state_status_decline_and_stop():
    async def scenario():
        LoopbackDevice.instances = []
        server = await serve("127.0.0.1", 0, configuration=server_configuration(), create_protocol=LoopbackDevice)
        statuses = []
        client = CGPClient(Queue(), statuses.append)
        try:
            port = server._transport.get_extra_info("sockname")[1]
            client.start(CGPDevice("Loopback", "127.0.0.1", port))
            await wait_until(lambda: client.shot_queue.qsize() == 1 and any(s["status"] == "device_status" for s in statuses))
            await wait_until(lambda: len(LoopbackDevice.instances[0].messages) >= 2)
            payload = client.shot_queue.get_nowait()
            assert "total_spin_rpm" not in payload
            assert "peer_fingerprint" not in payload["_cgp"]
            assert any(len(s.get("peer_fingerprint", "")) == 64 for s in statuses)
            assert any(s.get("trust") == "unregistered maker" for s in statuses)
            incoming = LoopbackDevice.instances[0].messages
            assert incoming[0][0] == 0 and incoming[0][1]["channels"] == [0, 6]
            assert incoming[1] == (6, {"type": "state", "ready": True, "mode": "range"})
            await wait_until(lambda: bool(LoopbackDevice.instances[0].declined))
            assert LoopbackDevice.instances[0].declined[0][1] == 1
            await asyncio.to_thread(client.stop)
            assert not client.is_running and client.shot_queue.empty()
        finally:
            await asyncio.to_thread(client.stop)
            server.close()
    asyncio.run(scenario())


def test_wrong_draft_alpn_fails_instead_of_half_working():
    async def scenario():
        server = await serve("127.0.0.1", 0, configuration=server_configuration("common-golf/draft-1"),
                             create_protocol=LoopbackDevice)
        queue = Queue()
        try:
            port = server._transport.get_extra_info("sockname")[1]
            with pytest.raises(ConnectionError):
                await connect_client(CGPDevice("Wrong draft", "127.0.0.1", port), queue,
                                     lambda *a, **k: None, OrderedDict())
            assert queue.empty()
        finally:
            server.close()
    asyncio.run(scenario())


def _load_reference():
    directory = os.environ.get("CGP_REFERENCE_DIR")
    if not directory:
        pytest.skip("Set CGP_REFERENCE_DIR to the pinned upstream checkout")
    root = pathlib.Path(directory)
    assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == REFERENCE_COMMIT
    source = root / "examples/common_golf.py"
    cg = types.ModuleType("cgp_test_reference")
    cg.__dict__.update({"asyncio": asyncio, "json": json, "struct": struct,
                        "serialization": serialization, "x509": x509,
                        "QuicConnectionProtocol": QuicConnectionProtocol,
                        "HandshakeCompleted": HandshakeCompleted, "StreamDataReceived": StreamDataReceived,
                        "StopSendingReceived": StopSendingReceived, "StreamReset": StreamReset,
                        "ALPN": ALPN, "PROTOCOL_VERSION": "0.2.0", "NOT_INTERESTED": 1, "MALFORMED": 2,
                        "MAX_MESSAGE_BYTES": 65535, "KEEP_ALIVE_SECONDS": 15,
                        "CHANNEL": {"info": 0, "shot": 1, "state": 6, "result": 7}})
    tree = ast.parse(source.read_text())
    allowed = {"frame", "unframe", "fingerprint", "Connection"}
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in allowed]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), cg.__dict__)
    device_source = root / "examples/device_minimum.py"
    tree = ast.parse(device_source.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Device"]
    namespace = {"cg": cg, "asyncio": asyncio, "random": random}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(device_source), "exec"), namespace)
    return namespace["Device"]


def test_pinned_upstream_minimum_device_ephemeral_certificate():
    reference = _load_reference()
    async def scenario():
        server = await serve("127.0.0.1", 0, configuration=server_configuration(), create_protocol=reference)
        queue, statuses = Queue(), []
        port = server._transport.get_extra_info("sockname")[1]
        task = asyncio.create_task(connect_client(CGPDevice("Reference minimum", "127.0.0.1", port), queue,
                                                  lambda *a, **k: statuses.append((a, k)), OrderedDict()))
        try:
            await wait_until(lambda: not queue.empty(), seconds=6)
            payload = queue.get_nowait()
            assert payload["_source"] == "cgp" and payload["_cgp"]["shot_number"] == 1
            assert 30 <= payload["ball_speed_meters_per_second"] <= 75
            assert "total_spin_rpm" not in payload
            assert any(args[0] == "connected" for args, _ in statuses)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            server.close()
    asyncio.run(scenario())


def test_stop_during_real_unanswered_handshake_is_prompt():
    async def scenario():
        loop = asyncio.get_running_loop()
        blackhole, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0))
        statuses = []
        client = CGPClient(Queue(), statuses.append)
        try:
            client.start(CGPDevice("Silent device", "127.0.0.1", blackhole.get_extra_info("sockname")[1]))
            await wait_until(lambda: any(s["status"] == "connecting" for s in statuses))
            await asyncio.sleep(.05)
            start = loop.time()
            await asyncio.to_thread(client.stop)
            assert loop.time() - start < 2.5
            assert not client.is_running
        finally:
            await asyncio.to_thread(client.stop)
            blackhole.close()
    asyncio.run(scenario())


def test_controller_real_quic_restart_keeps_replay_cache_and_invalidates_old_queue():
    from src.connections.controller import SourceConnections

    class ReplayDevice(LoopbackDevice):
        instances = []
        def publish(self, channel, messages):
            if channel == 1:
                messages = [dict(SHOT, measurement_id="globally-unique-replayed-shot"),
                            dict(SHOT, shot_number=2, measurement_id=f"new-shot-{len(self.instances)}")]
            super().publish(channel, messages)

    async def scenario():
        server = await serve("127.0.0.1", 0, configuration=server_configuration(), create_protocol=ReplayDevice)
        queue = Queue()
        controller = SourceConnections(queue)
        device = CGPDevice("Restart", "127.0.0.1", server._transport.get_extra_info("sockname")[1])
        try:
            controller.start_cgp(device)
            await wait_until(lambda: queue.qsize() == 2)
            previous = queue.get_nowait()
            assert controller.accepts(previous)
            queue.get_nowait()
            old_client = controller._client
            controller.start_cgp(device)
            await wait_until(lambda: len(ReplayDevice.instances) == 2 and queue.qsize() == 1)
            current = queue.get_nowait()
            assert current["_cgp"]["measurement_id"] == "new-shot-2"
            assert not controller.accepts(previous) and controller.accepts(current)
            assert previous["shotId"] != current["shotId"]
            assert not old_client.is_running
            client = controller._client
            controller.stop()
            await wait_until(lambda: not client.is_running)
            assert not controller.accepts(current) and queue.empty()
        finally:
            client = controller._client
            controller.stop()
            if client is not None:
                await asyncio.to_thread(client.stop)
            server.close()
    asyncio.run(scenario())


def test_controller_peer_disconnect_clears_test_shot_readiness():
    from src.connections.controller import SourceConnections

    async def scenario():
        LoopbackDevice.instances = []
        server = await serve("127.0.0.1", 0, configuration=server_configuration(), create_protocol=LoopbackDevice)
        controller = SourceConnections(Queue())
        try:
            controller.start_cgp(CGPDevice("Disconnect", "127.0.0.1", server._transport.get_extra_info("sockname")[1]))
            await wait_until(lambda: controller.snapshot().get("state") == "ready")
            assert controller.snapshot()["shot_received"]
            LoopbackDevice.instances[0].close(reason_phrase="test disconnect")
            await wait_until(lambda: controller.snapshot().get("state") == "idle")
            assert controller.snapshot().get("connected") is False
        finally:
            client = controller._client
            controller.stop()
            if client is not None:
                await asyncio.to_thread(client.stop)
            server.close()
    asyncio.run(scenario())
