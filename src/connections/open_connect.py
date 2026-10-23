"""Explicit-start GSPro Open Connect v1 TCP receiver and pure SPS mapper.

Protocol: https://gsprogolf.com/GSProConnectV1.html. The framing approach is
shared with Shanktuary Arcade's core/open_connect_adapter.gd: bounded raw,
concatenated, or whitespace-separated JSON objects, not newline framing.

Only the Yards/mph profile is supported: the public specification does not
establish metric speed units. Open Connect is unauthenticated. Loopback is
used by default; callers must explicitly choose 0.0.0.0 for a trusted LAN.
This module never discovers devices, opens firewalls, or starts on import.
"""

import copy
import ipaddress
import json
import math
import queue
import select
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field

DEFAULT_PORT = 921
MPH_TO_MPS = 0.44704
YARDS_TO_METERS = 0.9144
MAX_MESSAGE_BYTES = 65536
MAX_DEPTH = 32
MAX_CLIENTS = 8
MAX_DEVICES = 256
MAX_SHOT_NUMBER = 9007199254740991
FRAME_TIMEOUT_SECONDS = 10.0

BALL_FIELDS = ('Speed', 'HLA', 'VLA', 'TotalSpin', 'SpinAxis', 'BackSpin',
               'SideSpin', 'CarryDistance')
CLUB_FIELDS = ('Speed', 'AngleOfAttack', 'FaceToTarget', 'Lie', 'Loft', 'Path',
               'SpeedAtImpact', 'VerticalFaceImpact', 'HorizontalFaceImpact',
               'ClosureRate')
CLUB_MAPPINGS = (('AngleOfAttack', 'angle_of_attack_degrees'),
                 ('FaceToTarget', 'club_face_to_target_degrees'),
                 ('Path', 'club_path_degrees'),
                 ('ClosureRate', 'face_closure_rate_dps'))


class OpenConnectError(ValueError):
    """Invalid protocol data, safe to describe in a failure response."""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _finite_float(text):
    result = float(text)
    if not math.isfinite(result):
        raise OpenConnectError('JSON numbers must be finite')
    return result


def _bad_constant(text):
    raise OpenConnectError('JSON numbers must be finite')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OpenConnectError('Duplicate JSON keys are not supported')
        result[key] = value
    return result


class OpenConnectJSONStream:
    """Bounded byte framing preserving UTF-8 split anywhere in a TCP stream.

    Encoding, JSON syntax, and framing errors permanently invalidate the
    connection. Do not try to recover by scanning into trailing input.
    """

    def __init__(self, max_bytes=MAX_MESSAGE_BYTES, max_depth=MAX_DEPTH):
        self.max_bytes = max_bytes
        self.max_depth = max_depth
        self.frame = bytearray()
        self.closers = []
        self.in_string = False
        self.escaped = False
        self.pending_since = None
        self.failed = False

    def feed(self, data, now=None):
        """Yield complete objects, keeping an unfinished last frame bounded."""
        if self.failed:
            raise OpenConnectError('Stream is already invalid')
        now = time.monotonic() if now is None else now
        try:
            for byte in data:
                if not self.frame:
                    if byte in (9, 10, 13, 32):
                        continue
                    if byte != 123:
                        raise OpenConnectError('Expected a JSON object')
                    self.pending_since = now
                self.frame.append(byte)
                if len(self.frame) > self.max_bytes:
                    raise OpenConnectError('JSON message exceeds size limit')
                if self.in_string:
                    if self.escaped:
                        self.escaped = False
                    elif byte == 92:
                        self.escaped = True
                    elif byte == 34:
                        self.in_string = False
                    continue
                if byte == 34:
                    self.in_string = True
                elif byte in (123, 91):
                    self.closers.append(125 if byte == 123 else 93)
                    if len(self.closers) > self.max_depth:
                        raise OpenConnectError('JSON nesting exceeds limit')
                elif byte in (125, 93):
                    if not self.closers or self.closers.pop() != byte:
                        raise OpenConnectError('Mismatched JSON delimiters')
                    if not self.closers:
                        try:
                            message = json.loads(
                                self.frame.decode('utf-8', errors='strict'),
                                parse_float=_finite_float,
                                parse_constant=_bad_constant,
                                object_pairs_hook=_unique_object,
                            )
                            json.dumps(message, ensure_ascii=False, allow_nan=False).encode('utf-8', errors='strict')
                        except (UnicodeError, ValueError, RecursionError) as exc:
                            raise OpenConnectError('Malformed UTF-8 JSON object') from exc
                        self.frame.clear()
                        self.pending_since = None
                        yield message
        except OpenConnectError:
            self.failed = True
            raise

    def check_timeout(self, now=None):
        now = time.monotonic() if now is None else now
        if self.pending_since is not None and now - self.pending_since > FRAME_TIMEOUT_SECONDS:
            self.failed = True
            raise OpenConnectError('Incomplete JSON timed out')


def _validate_message(message):
    if not isinstance(message, dict):
        raise OpenConnectError('Expected a JSON object')
    device = message.get('DeviceID')
    if not isinstance(device, str) or not device.strip() or len(device) > 256:
        raise OpenConnectError('DeviceID must be a nonempty string up to 256 characters')
    try:
        device.encode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise OpenConnectError('DeviceID must contain valid Unicode characters') from exc
    if message.get('APIversion') != '1':
        raise OpenConnectError('Only APIversion 1 is supported')
    if message.get('Units', 'Yards') != 'Yards':
        raise OpenConnectError('Only the Yards/mph profile is supported')
    number = message.get('ShotNumber')
    if not _number(number) or not 0 <= number <= MAX_SHOT_NUMBER or int(number) != number:
        raise OpenConnectError('ShotNumber must be an exact nonnegative integer')
    options = message.get('ShotDataOptions')
    if not isinstance(options, dict):
        raise OpenConnectError('Missing ShotDataOptions')
    for key in ('ContainsBallData', 'ContainsClubData'):
        if not isinstance(options.get(key), bool):
            raise OpenConnectError('Missing boolean ' + key)
    for key in ('LaunchMonitorIsReady', 'LaunchMonitorBallDetected', 'IsHeartBeat'):
        if key in options and not isinstance(options[key], bool):
            raise OpenConnectError('Expected boolean ' + key)
    if options.get('IsHeartBeat', False) and options['ContainsBallData']:
        raise OpenConnectError('Heartbeat cannot contain a shot')
    if options['ContainsClubData']:
        club = message.get('ClubData')
        if not isinstance(club, dict):
            raise OpenConnectError('ContainsClubData requires ClubData')
        for key in CLUB_FIELDS:
            if key in club and not _number(club[key]):
                raise OpenConnectError('Invalid ClubData number ' + key)
    if not options['ContainsBallData']:
        return options
    ball = message.get('BallData')
    if not isinstance(ball, dict):
        raise OpenConnectError('ContainsBallData requires BallData')
    for key in ('Speed', 'HLA', 'VLA'):
        if not _number(ball.get(key)):
            raise OpenConnectError('Missing finite BallData number ' + key)
    for key in BALL_FIELDS:
        if key in ball and not _number(ball[key]):
            raise OpenConnectError('Invalid BallData number ' + key)
    if ball['Speed'] <= 0:
        raise OpenConnectError('Ball speed must be positive')
    if not -180 <= ball['HLA'] <= 180 or not -90 <= ball['VLA'] <= 90:
        raise OpenConnectError('Launch angle is outside supported bounds')
    if 'TotalSpin' in ball:
        if not 0 <= ball['TotalSpin'] <= 30000:
            raise OpenConnectError('Total spin is outside supported bounds')
        if 'SpinAxis' not in ball:
            raise OpenConnectError('TotalSpin requires SpinAxis')
    elif not all(key in ball for key in ('BackSpin', 'SideSpin')):
        raise OpenConnectError('Need TotalSpin/SpinAxis or BackSpin/SideSpin')
    if 'SpinAxis' in ball and abs(ball['SpinAxis']) > 180:
        raise OpenConnectError('Spin axis is outside supported bounds')
    if any(abs(ball[key]) > 30000 for key in ('BackSpin', 'SideSpin') if key in ball):
        raise OpenConnectError('Spin component is outside supported bounds')
    return options


def map_open_connect_shot_to_sps_payload(message):
    """Return (payload, metadata); status/heartbeat payloads return None.

    Optional absence is not zero. Raw sender extensions (including estimate
    flags) survive intact. Open Connect has no standardized measurement-quality
    schema, so source values are reported, never certified measured. Only
    documented/established metric meanings are mapped; face impact, Lie, Loft
    and SpeedAtImpact remain raw instead of masquerading as Nova metrics.
    """
    options = _validate_message(message)
    meta = {
        'device_id': message['DeviceID'], 'shot_number': int(message['ShotNumber']),
        'api_version': '1', 'input_units': 'Yards/mph',
        'measurement_provenance': 'sender_reported',
        'raw_message': copy.deepcopy(message), 'reported_fields': [],
        'missing_fields': [], 'derived_fields': [], 'alias_fields': [],
    }
    if not options['ContainsBallData']:
        return None, meta
    ball = message['BallData']
    club = message.get('ClubData', {}) if options['ContainsClubData'] else {}
    payload = {'type': 'shot', '_source': 'open_connect'}
    ogc = {'us_customary_units': {}}
    provenance = {}
    prefix = 'open_golf_coach.'
    us_prefix = prefix + 'us_customary_units.'

    def put(path, value, source_field=None, *, inputs=(), method=None, assumptions=()):
        parent = payload
        parts = path.split('.')
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
        parent[parts[-1]] = value
        entry = {
            'kind': 'derived' if inputs else 'source_reported',
            'method': method or 'Open Connect v1', 'version': 'sps-1',
            'inputs': list(inputs), 'assumptions': list(assumptions),
            'flags': [], 'calibration_ground_truth': False,
        }
        if source_field is not None:
            entry['source_field'] = source_field
        provenance[path] = entry

    payload['open_golf_coach'] = ogc
    # Canonical native mph/yards precede SI conversions, preventing cycles in
    # provenance. Unit aliases are available with optional enrichment disabled.
    put(us_prefix + 'ball_speed_mph', ball['Speed'], 'BallData.Speed')
    put('ball_speed_meters_per_second', ball['Speed'] * MPH_TO_MPS,
        inputs=[us_prefix + 'ball_speed_mph'], method='mph to meters per second')
    put('vertical_launch_angle_degrees', ball['VLA'], 'BallData.VLA')
    put('horizontal_launch_angle_degrees', ball['HLA'], 'BallData.HLA')
    put(prefix + 'vertical_launch_angle_degrees', ball['VLA'],
        inputs=['vertical_launch_angle_degrees'], method='value alias')
    for fields, group, known in ((ball, 'BallData', BALL_FIELDS), (club, 'ClubData', CLUB_FIELDS)):
        for key in known:
            meta['reported_fields' if key in fields else 'missing_fields'].append(group + '.' + key)
    for source, target in (('BackSpin', 'backspin_rpm'), ('SideSpin', 'sidespin_rpm')):
        if source in ball:
            put(prefix + target, ball[source], 'BallData.' + source)
    for source, target in (('TotalSpin', 'total_spin_rpm'), ('SpinAxis', 'spin_axis_degrees')):
        if source in ball:
            put(target, ball[source], 'BallData.' + source)
        else:
            assumptions = []
            if source == 'TotalSpin':
                value, method = math.hypot(ball['BackSpin'], ball['SideSpin']), 'spin vector magnitude'
            else:
                value = math.degrees(math.atan2(ball['SideSpin'], ball['BackSpin']))
                method = 'spin vector atan2'
                if ball['BackSpin'] == 0 and ball['SideSpin'] == 0:
                    value = 0.0
                    meta['zero_spin_axis_convention'] = True
                    assumptions = ['Zero spin uses canonical axis 0, not a measured angle']
            put(target, value, inputs=[prefix + 'backspin_rpm', prefix + 'sidespin_rpm'],
                method=method, assumptions=assumptions)
        put(prefix + target, payload[target], inputs=[target], method='value alias')
    if 'CarryDistance' in ball:
        put(us_prefix + 'carry_distance_yards', ball['CarryDistance'], 'BallData.CarryDistance')
        put(prefix + 'carry_distance_meters', ball['CarryDistance'] * YARDS_TO_METERS,
            inputs=[us_prefix + 'carry_distance_yards'], method='yards to meters')
    if 'Speed' in club:
        put(us_prefix + 'club_speed_mph', club['Speed'], 'ClubData.Speed')
        put(prefix + 'club_speed_meters_per_second', club['Speed'] * MPH_TO_MPS,
            inputs=[us_prefix + 'club_speed_mph'], method='mph to meters per second')
    for source, target in CLUB_MAPPINGS:
        if source in club:
            put(prefix + target, club[source], 'ClubData.' + source)
    meta['derived_fields'] = sorted(path for path, entry in provenance.items() if entry['kind'] == 'derived')
    meta['alias_fields'] = sorted(path for path, entry in provenance.items()
                                  if entry['method'] == 'value alias' or path.startswith(us_prefix))
    payload['_metric_provenance'] = provenance
    payload['_open_connect'] = meta
    return payload, meta


@dataclass
class _Client:
    sock: socket.socket
    parser: OpenConnectJSONStream = field(default_factory=OpenConnectJSONStream)
    outgoing: bytearray = field(default_factory=bytearray)
    player_revision: int = -1
    close_after_write: bool = False
    close_deadline: float = 0.0


class OpenConnectListener:
    """Explicit lifecycle; one I/O thread; bounded clients/buffers/history.

    start() binds synchronously and returns the actual (host, port); port=0 is
    available for loopback tests. on_status receives a dict with status,
    message, connected. Callbacks must be quick and must not touch Tk widgets.
    Dedupe survives TCP reconnects, but explicit stop/start begins a new session.
    The queue must support put(payload, block=False), like queue.Queue.
    """

    def __init__(self, shot_queue, on_status=None):
        self.shot_queue = shot_queue
        self.on_status = on_status
        self._operations = threading.RLock()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._listener = None
        self._clients = {}
        self._high_water = {}
        self._session_id = None
        self._player = None
        self._player_revision = 0
        self.address = None

    @property
    def running(self):
        with self._lock:
            return self._listener is not None and not self._stop.is_set()

    def _status(self, status, message, connected=False):
        if self.on_status is not None:
            try:
                self.on_status({'status': status, 'message': message, 'connected': connected})
            except Exception:
                pass  # A broken UI callback must not take down input.

    def start(self, host='127.0.0.1', port=DEFAULT_PORT):
        with self._operations:
            self.stop()
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError('Previous Open Connect thread has not stopped')
            host = '127.0.0.1' if host == 'localhost' else host
            try:
                address = ipaddress.ip_address(host)
                if not (address.is_loopback or host == '0.0.0.0'):
                    raise ValueError('Use loopback or explicitly opt into LAN with 0.0.0.0')
                if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
                    raise ValueError('Port must be 1 to 65535 (0 for tests)')
                family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
                listener = socket.socket(family, socket.SOCK_STREAM)
                try:
                    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    else:
                        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind((host, port))
                    listener.listen(MAX_CLIENTS)
                    listener.setblocking(False)
                except Exception:
                    listener.close()
                    raise
            except (OSError, ValueError) as exc:
                self._status('error', f'Open Connect cannot listen: {exc}. Close the other receiver or choose another port.')
                raise
            with self._lock:
                self._stop = threading.Event()
                self._listener = listener
                self._clients = {}
                self._high_water = {}
                self._session_id = uuid.uuid4()
                self.address = listener.getsockname()[:2]
                self._thread = threading.Thread(target=self._run,
                                                args=(listener, self._clients, self._stop),
                                                name='open-connect-input', daemon=True)
                self._status('listening', f'Open Connect listening on {self.address[0]}:{self.address[1]}')
                self._thread.start()
            return self.address

    def stop(self):
        with self._operations:
            with self._lock:
                self._stop.set()
                listener, self._listener = self._listener, None
                clients = list(self._clients.values())
                thread = self._thread
                self.address = None
            for sock in ([listener] if listener else []) + [c.sock for c in clients]:
                self._close_socket(sock)
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=0.75)
            if thread is None or not thread.is_alive():
                self._thread = None
            self._status('stopped', 'Open Connect stopped')

    def reset_duplicate_history(self):
        with self._lock:
            if self.running:
                return False
            self._high_water.clear()
            return True

    def set_player(self, handed, club):
        """Advertise a real UI selection. No player is invented by default."""
        if handed not in ('RH', 'LH') or not isinstance(club, str) or not club.strip() or len(club) > 16:
            raise ValueError('Player requires RH/LH and a nonempty club code up to 16 characters')
        with self._lock:
            self._player = {'Handed': handed, 'Club': club}
            self._player_revision += 1

    @staticmethod
    def _close_socket(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    def _drop(self, client, clients, stop):
        with self._lock:
            clients.pop(client.sock, None)
            connected = bool(clients)
        self._close_socket(client.sock)
        if not stop.is_set():
            self._status('connected' if connected else 'listening',
                         'Open Connect connected' if connected else 'Open Connect listening; connector disconnected',
                         connected)

    @staticmethod
    def _reply(client, code, message, **extra):
        # No trailing newline: some existing connector splitters reject one.
        data = json.dumps({'Code': code, 'Message': message, **extra},
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(client.outgoing) + len(data) > MAX_MESSAGE_BYTES:
            raise OpenConnectError('Client is not reading responses')
        client.outgoing.extend(data)

    def _receive(self, client, message, stop):
        try:
            payload, meta = map_open_connect_shot_to_sps_payload(message)
            if payload is None:
                self._reply(client, 200, 'Status received')
                options = message['ShotDataOptions']
                readiness = 'device readiness unknown'
                if 'LaunchMonitorIsReady' in options:
                    readiness = 'device ready' if options['LaunchMonitorIsReady'] else 'device not ready'
                self._status('connected', 'Open Connect connected; ' + readiness, True)
                return
            device, number = meta['device_id'], meta['shot_number']
            with self._lock:
                if stop.is_set():
                    return
                if number <= self._high_water.get(device, -1):
                    self._reply(client, 200, 'Duplicate or old shot received; not replayed')
                    return
                if device not in self._high_water and len(self._high_water) >= MAX_DEVICES:
                    raise OpenConnectError('Device history full; stop and restart the listener')
                payload['shotId'] = uuid.uuid5(self._session_id, f'{device}\0{number}').hex
                meta['session_id'] = self._session_id.hex
                self.shot_queue.put(payload, block=False)
                self._high_water[device] = number
            self._reply(client, 200, 'Shot received')
        except (OpenConnectError, queue.Full) as exc:
            self._reply(client, 501, str(exc) or 'Shot queue is full; retry later')

    def _run(self, listener, clients, stop):
        try:
            while not stop.is_set():
                with self._lock:
                    snapshot = list(clients.values())
                    player, revision = self._player, self._player_revision
                for client in snapshot:
                    try:
                        client.parser.check_timeout()
                        if player is not None and client.player_revision != revision and not client.close_after_write:
                            self._reply(client, 201, 'GSPro Player Information', Player=player)
                            client.player_revision = revision
                    except OpenConnectError:
                        self._drop(client, clients, stop)
                with self._lock:
                    snapshot = list(clients.values())
                reads = [listener] + [c.sock for c in snapshot if not c.close_after_write]
                writes = [c.sock for c in snapshot if c.outgoing]
                readable, writable, _ = select.select(reads, writes, [], 0.1)
                if stop.is_set():
                    break
                if listener in readable:
                    try:
                        conn, _ = listener.accept()
                    except (BlockingIOError, ConnectionAbortedError):
                        conn = None
                    if conn is not None:
                        conn.setblocking(False)
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        with self._lock:
                            if stop.is_set() or len(clients) >= MAX_CLIENTS:
                                self._close_socket(conn)
                            else:
                                clients[conn] = _Client(conn)
                                self._status('connected', 'Open Connect connected; device readiness unknown', True)
                for client in snapshot:
                    try:
                        if client.sock in readable:
                            data = client.sock.recv(8192)
                            if not data:
                                self._drop(client, clients, stop)
                                continue
                            try:
                                for message in client.parser.feed(data):
                                    if stop.is_set():
                                        break
                                    self._receive(client, message, stop)
                            except OpenConnectError as exc:
                                self._reply(client, 501, str(exc))
                                client.close_after_write = True
                                client.close_deadline = time.monotonic() + 0.25
                        if client.sock in writable and client.outgoing:
                            sent = client.sock.send(client.outgoing)
                            del client.outgoing[:sent]
                        if client.close_after_write and (not client.outgoing or time.monotonic() > client.close_deadline):
                            self._drop(client, clients, stop)
                    except BlockingIOError:
                        continue
                    except (OSError, OpenConnectError):
                        self._drop(client, clients, stop)
        except (OSError, ValueError) as exc:
            if not stop.is_set():
                self._status('error', f'Open Connect listener stopped: {exc}')
        finally:
            with self._lock:
                snapshot = list(clients.values())
                clients.clear()
                if self._listener is listener:
                    self._listener = None
                    self.address = None
            for client in snapshot:
                self._close_socket(client.sock)
            self._close_socket(listener)
