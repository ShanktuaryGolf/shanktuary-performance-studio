"""CGP Draft 2 QUIC framing and channel ownership; imported only on demand.

The self-signed Ed25519 certificate proves possession of a key, not a vendor
or physical-device identity. Unknown peers are unregistered makers. No TLS
hooks are monkeypatched and no client credentials are generated or persisted.
"""

import asyncio
import json
import math
import re
import ssl
import struct
from collections import OrderedDict
from contextlib import suppress
from queue import Full

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import (
    ConnectionTerminated,
    HandshakeCompleted,
    StopSendingReceived,
    StreamDataReceived,
    StreamReset,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .cgp_mapper import CGPShotSession

ALPN = "common-golf/draft-2"
PROTOCOL_VERSION = "0.2.0"
MAX_MESSAGE_BYTES = 65535
MAX_PENDING_STREAMS = 32
MAX_RETIRED_STREAMS = 1024
NOT_INTERESTED = 1
MALFORMED = 2
IDLE_TIMEOUT_SECONDS = 90.0
KEEP_ALIVE_SECONDS = 15.0
CONNECT_TIMEOUT_SECONDS = 10.0
READ_CHANNELS = {0: "info", 1: "shot", 4: "status"}
LIMITATION = "Final ball shots only; club, flight, control and CGP Open Connect compatibility channels are not supported."


def frame(message):
    if not isinstance(message, dict):
        raise ValueError("CGP messages must be JSON objects")
    body = json.dumps(message, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not 0 < len(body) <= MAX_MESSAGE_BYTES:
        raise ValueError("CGP frame exceeds the 65,535-byte limit")
    return struct.pack(">I", len(body)) + body


def _object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON field")
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite JSON number")


def _finite_float(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def decode_object(data):
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("CGP message is not a JSON object")
    return value


class FramedJSONBuffer:
    """Incremental decoding with at most one bounded frame buffered per stream."""

    def __init__(self):
        self.buffer = bytearray()
        self.length = None

    def feed(self, data, end_stream=False):
        offset = 0
        while offset < len(data):
            target = 4 if self.length is None else self.length
            take = min(target - len(self.buffer), len(data) - offset)
            self.buffer.extend(data[offset:offset + take])
            offset += take
            if len(self.buffer) < target:
                break
            if self.length is None:
                self.length = struct.unpack(">I", self.buffer)[0]
                self.buffer.clear()
                if not 0 < self.length <= MAX_MESSAGE_BYTES:
                    raise ValueError("CGP frame length must be 1 through 65,535")
            else:
                message = decode_object(bytes(self.buffer))
                self.buffer.clear()
                self.length = None
                yield message
        if end_stream and (self.buffer or self.length is not None):
            raise ValueError("CGP stream ended inside a frame")


def _peer_fingerprint(quic):
    # Isolated read-only aioquic implementation detail. No global TLS changes.
    cert = getattr(quic.tls, "_peer_certificate", None)
    if cert is None or not isinstance(cert.public_key(), Ed25519PublicKey):
        raise ValueError("CGP requires an Ed25519 device certificate")
    return cert.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw).hex()


def _validate_info(message):
    version = message.get("protocol_version")
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("info requires a protocol_version string")
    for name in ("name", "vendor", "model", "serial", "firmware_version"):
        if name in message and not isinstance(message[name], str):
            raise ValueError(f"info {name} must be a string")
    channels = message.get("channels", [])
    if (not isinstance(channels, list)
            or any(isinstance(c, bool) or not isinstance(c, int) or c < 0 for c in channels)):
        raise ValueError("info channels must be nonnegative integers")


def _validate_status(message):
    for name in ("ready", "ball_detected"):
        if name in message and message[name] is not None and not isinstance(message[name], bool):
            raise ValueError(f"status {name} must be boolean or null")
    for name in ("battery_percent", "uptime_seconds"):
        value = message.get(name)
        if value is not None:
            try:
                valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                         and math.isfinite(value) and value >= 0)
            except (ValueError, OverflowError):
                valid = False
            if not valid or (name == "battery_percent" and value > 100):
                raise ValueError(f"invalid status {name}")
    if message.get("message") is not None and not isinstance(message["message"], str):
        raise ValueError("status message must be a string or null")


class CGPProtocol(QuicConnectionProtocol):
    def __init__(self, *args, shot_queue, on_status, device, measurement_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.shot_queue, self.on_status, self.device = shot_queue, on_status, device
        self.session = CGPShotSession(measurement_ids)
        self.peer_fingerprint = None
        self.device_info, self.device_status = {}, {}
        self._prefixes, self._buffers, self._channels = {}, {}, {}
        self._incoming, self._outgoing = {}, {}
        self._dead, self._stopped = OrderedDict(), OrderedDict()
        self._retired_before = -1
        self._keepalive = None
        self._ready = False
        self.handshake_error = None

    def _publish(self, channel, message):
        sid = self._quic.get_next_available_stream_id(is_unidirectional=True)
        self._outgoing[sid] = channel
        self._quic.send_stream_data(sid, struct.pack(">I", channel) + frame(message))
        self.transmit()
        return sid

    def _close_incoming(self, sid):
        self._dead[sid] = None
        if len(self._dead) > MAX_RETIRED_STREAMS:
            oldest = min(self._dead)
            del self._dead[oldest]
            self._retired_before = max(self._retired_before, oldest)
        self._prefixes.pop(sid, None)
        self._buffers.pop(sid, None)
        channel = self._channels.pop(sid, None)
        if self._incoming.get(channel) == sid:
            del self._incoming[channel]
        if channel == 4:
            self.device_status = {}

    def _discard(self, sid, code, reason, ended=False):
        if not ended:
            self._quic.stop_stream(sid, code)
        self._close_incoming(sid)
        self.transmit()
        self.on_status("limited" if code == NOT_INTERESTED else "warning", reason)

    def _message(self, channel, message):
        if message.get("type") != READ_CHANNELS[channel]:
            raise ValueError(f"channel {channel} requires type={READ_CHANNELS[channel]}")
        if channel == 0:
            _validate_info(message)
            self.device_info = dict(message)
            # protocol_version is descriptive; ALPN alone selects the wire format.
            self.on_status("info", f"CGP device: {message.get('name', self.device.name)}",
                           device_info=dict(self.device_info))
        elif channel == 4:
            _validate_status(message)
            for name in ("ready", "ball_detected", "battery_percent", "uptime_seconds", "message"):
                if name in message:
                    if message[name] is None:
                        self.device_status.pop(name, None)
                    else:
                        self.device_status[name] = message[name]
            self.on_status("device_status", "CGP device status updated", device_status=dict(self.device_status))
        else:
            payload = self.session.ingest(message, device_name=self.device.name)
            if payload is not None:
                try:
                    self.shot_queue.put_nowait(payload)
                except Full:
                    self.on_status("warning", "CGP shot queue is full; this shot was not imported")

    def _receive(self, event):
        sid = event.stream_id
        if (not self._ready or sid in self._dead
                or (sid <= self._retired_before and sid not in self._channels and sid not in self._prefixes)):
            return
        data = event.data
        if sid not in self._channels:
            # We are the QUIC client. Accepted device channels must arrive on
            # server-initiated unidirectional streams (low bits 11).
            if sid & 3 != 3:
                self._discard(sid, NOT_INTERESTED, "CGP stream direction is not supported", event.end_stream)
                return
            if sid not in self._prefixes and len(self._prefixes) >= MAX_PENDING_STREAMS:
                self._discard(sid, NOT_INTERESTED, "Too many incomplete CGP channel prefixes", event.end_stream)
                return
            prefix = self._prefixes.setdefault(sid, bytearray())
            take = min(4 - len(prefix), len(data))
            prefix.extend(data[:take])
            data = data[take:]
            if len(prefix) < 4:
                if event.end_stream:
                    self._discard(sid, MALFORMED, "CGP stream ended inside its channel prefix", True)
                return
            channel = struct.unpack(">I", prefix)[0]
            self._prefixes.pop(sid, None)
            if channel not in READ_CHANNELS or channel in self._incoming:
                reason = (f"CGP channel {channel} already has an open stream" if channel in self._incoming
                          else f"CGP channel {channel} declined. {LIMITATION}")
                self._discard(sid, NOT_INTERESTED, reason, event.end_stream)
                return
            self._channels[sid] = channel
            self._incoming[channel] = sid
            self._buffers[sid] = FramedJSONBuffer()
        channel = self._channels[sid]
        try:
            for message in self._buffers[sid].feed(data, event.end_stream):
                self._message(channel, message)
        except ValueError as exc:
            self._discard(sid, MALFORMED, f"Malformed CGP channel {channel}: {exc}", event.end_stream)
            return
        if event.end_stream:
            self._close_incoming(sid)

    def quic_event_received(self, event):
        # Deliberately do not invoke the base StreamReader/Writer handler;
        # CGP owns framing and receive-only streams must never get a local FIN.
        if isinstance(event, HandshakeCompleted):
            try:
                if event.alpn_protocol != ALPN:
                    raise ValueError(f"device must negotiate {ALPN}")
                self.peer_fingerprint = _peer_fingerprint(self._quic)
            except ValueError as exc:
                self.handshake_error = str(exc)
                self.close(reason_phrase=self.handshake_error)
                return
            self._ready = True
            self._publish(0, {"type": "info", "protocol_version": PROTOCOL_VERSION,
                              "name": "Shanktuary Performance Studio", "channels": [0, 6]})
            self._publish(6, {"type": "state", "ready": True, "mode": "range"})
            self.on_status("connected", f"Connected to {self.device.name}. {LIMITATION}",
                           peer_fingerprint=self.peer_fingerprint, trust="unregistered maker")
            self._keepalive = asyncio.create_task(self._keep_alive())
        elif isinstance(event, StreamDataReceived):
            self._receive(event)
        elif isinstance(event, StreamReset):
            self._close_incoming(event.stream_id)
        elif isinstance(event, StopSendingReceived):
            self._stopped[event.stream_id] = None
            while len(self._stopped) > MAX_RETIRED_STREAMS:
                self._stopped.popitem(last=False)
            self.on_status("limited", f"Device declined CGP channel {self._outgoing.get(event.stream_id)} (code {event.error_code})")
        elif isinstance(event, ConnectionTerminated):
            self._ready = False
            if self._keepalive is not None:
                self._keepalive.cancel()
            self.on_status("disconnected", f"CGP connection closed: {event.reason_phrase or 'peer disconnected'}")

    async def _keep_alive(self):
        try:
            while not self._closed.is_set():
                await asyncio.sleep(KEEP_ALIVE_SECONDS)
                if not self._closed.is_set():
                    await self.ping()
        except (asyncio.CancelledError, ConnectionError):
            pass

    async def shutdown(self):
        if self._keepalive is not None:
            self._keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await self._keepalive
        self.close()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.wait_closed(), timeout=1.0)


async def connect_client(device, shot_queue, on_status, measurement_ids):
    # CGP explicitly ignores CA and date validation and permits no client
    # certificate. We identify the peer's Ed25519 key transiently, not as trusted.
    configuration = QuicConfiguration(is_client=True, alpn_protocols=[ALPN],
                                      verify_mode=ssl.CERT_NONE, idle_timeout=IDLE_TIMEOUT_SECONDS)
    def factory(*args, **kwargs):
        return CGPProtocol(*args, shot_queue=shot_queue, on_status=on_status,
                           device=device, measurement_ids=measurement_ids, **kwargs)
    async with connect(device.host, device.port, configuration=configuration,
                       create_protocol=factory, wait_connected=False) as protocol:
        try:
            # aioquic does not transmit the Initial with wait_connected=False.
            protocol.transmit()
            await asyncio.wait_for(protocol.wait_connected(), CONNECT_TIMEOUT_SECONDS)
            if protocol.handshake_error:
                raise ValueError(protocol.handshake_error)
            await protocol.wait_closed()
        finally:
            await protocol.shutdown()
