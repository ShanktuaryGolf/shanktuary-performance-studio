"""Read-only PurePlay schema-1 shot folder input. No game/network writes.

Only new valid PurePlay records are admitted, independently of input hardware. Existing sessions are baselined
on each explicit start, including existing files temporarily unreadable at start.
"""
import copy
import hashlib
import json
import math
import os
import threading
from pathlib import Path

MAX_SESSION_BYTES = 16 * 1024 * 1024
MAX_SEEN_SHOTS = 100000


def locate_pureplay_profiles_path():
    override = os.environ.get('SPS_PUREPLAY_PROFILES', '').strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    local = os.environ.get('LOCALAPPDATA')
    base = Path(local) if local else Path.home() / 'AppData' / 'Local'
    return str(base / 'Pureplaygolf' / 'Saved' / 'Profiles')


def _number(value):
    return (type(value) in (int, float) and math.isfinite(value))


def _identity(value):
    return isinstance(value, str) and 0 < len(value) <= 128


def map_pureplay_shot_to_sps_payload(shot, profile_id='0'):
    """Map a schema-1 PurePlay shot, preserving unknowns and input provenance.

    Source flags do not certify measurement quality. Flight values are game
    estimates. Club defaults/impact units are unverified and kept raw only.
    """
    if not isinstance(shot, dict):
        raise ValueError('Expected a PurePlay shot object')
    if not _identity(shot.get('shotId')) or not _identity(shot.get('sessionId')):
        raise ValueError('Missing shot/session identity')
    speed = shot.get('ballSpeedRaw', shot.get('ballSpeed'))
    vla = shot.get('vLARaw', shot.get('vLA'))
    hla = shot.get('hLA')
    if not all(_number(v) for v in (speed, vla, hla)) or not 0 < speed <= 150:
        raise ValueError('Missing or invalid ball launch data')
    if not -90 <= vla <= 90 or not -180 <= hla <= 180:
        raise ValueError('Launch angle outside supported bounds')
    if not shot.get('restTime'):
        raise ValueError('Shot has not finished')
    meta = dict(profile_id=str(profile_id), shot_id=shot['shotId'],
                session_id=shot['sessionId'], captured_at=shot.get('capturedAt'),
                club=shot.get('clubDisplayName') or shot.get('clubType'),
                input_units='m/s, meters, degrees, rpm', schema_version=1,
                raw_shot=copy.deepcopy(shot), measurement_provenance='pureplay_reported_unverified',
                launch_monitor_flag=shot.get('bFromLaunchMonitor'),
                limitations=['PurePlay data is not independently hardware-verified; input flags are retained, not trusted',
                             'Angle signs not yet verified',
                             'Club fields and impact coordinates remain raw: defaults/units unverified'])
    payload = dict(type='shot', _source='pureplay',
                   shotId="pureplay-" + hashlib.sha256(
                       f"{profile_id}:{shot['shotId']}".encode()).hexdigest(), _pureplay=meta)
    provenance = payload['_metric_provenance'] = {}

    def put(path, value, field, estimated=False):
        if not _number(value):
            return
        target = payload
        parts = path.split('.')
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        provenance[path] = dict(kind='source_estimated' if estimated else 'source_reported',
                                source='pureplay', source_field=field,
                                method='PurePlay session JSON', version='1',
                                calibration_ground_truth=False)

    put('ball_speed_meters_per_second', speed, 'ballSpeedRaw/ballSpeed')
    put('vertical_launch_angle_degrees', vla, 'vLARaw/vLA')
    put('horizontal_launch_angle_degrees', hla, 'hLA')
    spin = shot.get('spinRaw', shot.get('totalSpin'))
    axis = shot.get('spinAxisRaw', shot.get('spinAxis'))
    if _number(spin) and 0 <= spin <= 30000:
        put('total_spin_rpm', spin, 'spinRaw/totalSpin')
    if _number(axis) and -180 <= axis <= 180:
        put('spin_axis_degrees', axis, 'spinAxisRaw/spinAxis')
    # Do not mix rawShot (neutral-flight model) with in-game course outcomes.
    for source, target in (('carryDistanceM', 'carry_distance_meters'),
                           ('totalDistanceM', 'total_distance_meters'),
                           ('apexHeightM', 'peak_height_meters')):
        value = shot.get(source)
        # Training records currently use zero as an unavailable apex sentinel.
        if _number(value) and value >= 0 and not (source == 'apexHeightM' and value == 0):
            put('open_golf_coach.' + target, value, source, estimated=True)
    return payload, meta


class PureplayPoller:
    """Explicit-start bounded poller; retry partial writes without duplicate shots."""
    def __init__(self, on_shot, profiles_path=None, on_status=None, poll_interval=0.5):
        self.profiles_path = Path(profiles_path or locate_pureplay_profiles_path())
        self.on_shot = on_shot
        self.on_status = on_status or (lambda status: None)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread = None
        self._seen = set()
        self._baseline_pending = set()
        self._signatures = {}
        self._started = False
        self._unverified_shots = 0
        self._status = dict(state='idle', message='Not reading PurePlay', shot_received=False)

    def status(self):
        return dict(self._status)

    def _report(self, **status):
        self._status.update(status)
        self.on_status(dict(self._status))

    def _files(self):
        if not self.profiles_path.is_dir():
            raise FileNotFoundError('PurePlay Profiles folder not found. Choose its folder and start reading.')
        # Never read launcher credentials, profile identity files or outbox data.
        return sorted(path for path in self.profiles_path.glob('*/shots/session-*.json')
                      if not path.is_symlink() and not path.parent.is_symlink()
                      and not path.parent.parent.is_symlink())

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._seen.clear()
        self._unverified_shots = 0
        self._signatures.clear()
        self._started = False
        self._baseline_pending.clear()
        # Capture baseline before returning, avoiding the thread-start window.
        self.poll_once()
        if self._status['state'] == 'error':
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name='PurePlay-reader')
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._report(state='idle', message='PurePlay reader stopped', shot_received=False)

    def _run(self):
        while not self._stop.wait(self.poll_interval):
            self.poll_once()

    def poll_once(self):
        try:
            files = self._files()
        except OSError as exc:
            self._report(state='error', message=str(exc), shot_received=False)
            return
        if not self._started:
            self._baseline_pending.update(files)
            self._started = True
        problems = 0
        for path in files:
            if self._stop.is_set():
                return
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if self._signatures.get(path) == signature:
                    continue
                if stat.st_size > MAX_SESSION_BYTES:
                    raise ValueError('Session file exceeds 16 MiB')
                with path.open('rb') as stream:
                    raw = stream.read(MAX_SESSION_BYTES + 1)
                if len(raw) > MAX_SESSION_BYTES:
                    raise ValueError('Session file exceeds 16 MiB')
                document = json.loads(raw.decode('utf-8-sig'))
                if (not isinstance(document, dict) or type(document.get('schemaVersion')) is not int
                        or document['schemaVersion'] != 1 or not isinstance(document.get('shots'), list)):
                    raise ValueError('Unsupported PurePlay session schema')
                after = path.stat()
                if (after.st_mtime_ns, after.st_size) != signature:
                    raise ValueError('Session changed while reading')
                baseline = path in self._baseline_pending
                retry = False
                for shot in document['shots']:
                    if not isinstance(shot, dict) or not _identity(shot.get('shotId')):
                        continue
                    identity = (path.parent.parent.name, shot['shotId'])
                    if identity in self._seen:
                        continue
                    if len(self._seen) >= MAX_SEEN_SHOTS:
                        self._stop.set()
                        self._report(state='error', message='PurePlay session limit reached; restart reading.', shot_received=False)
                        return
                    if baseline:
                        self._seen.add(identity)
                        continue
                    try:
                        if shot.get('sessionId') != document.get('sessionId'):
                            raise ValueError('Session identity mismatch')
                        payload, meta = map_pureplay_shot_to_sps_payload(shot, identity[0])
                    except ValueError:
                        retry = True
                        continue
                    try:
                        self.on_shot(payload, meta)
                    except Exception as exc:
                        self._report(state="error", message=f"PurePlay shot delivery failed: {exc}", shot_received=False)
                        return
                    self._status["shot_received"] = True
                    if shot.get("bFromLaunchMonitor") is not True:
                        self._unverified_shots += 1
                    self._seen.add(identity)
                self._baseline_pending.discard(path)
                if not retry:
                    self._signatures[path] = signature
                else:
                    problems += 1
            except (OSError, ValueError, RecursionError, OverflowError):
                problems += 1
        self._report(state='connected', message=(
            f'Reading PurePlay; retrying {problems} incomplete or unsupported session file(s).'
            if problems else 'Test shot received from PurePlay. Data is source-reported, not hardware-verified.'
            if self._status['shot_received'] else 'Reading PurePlay. Hit a new shot; existing saved history is skipped.'))
