"""Opt-in, missing-only local OpenGolfCoach adapter; never training truth.

Official package opengolfcoach==0.3.0, OpenLaunchLabs/open-golf-coach.
Reviewed upstream source 5a9dcc43ef86c8005ded5a9dfd56a7d586962d4d.
Runtime provenance records package version, not an unverified build SHA.
No network calls or installation occur here. Unknown values are not zeroes.
"""
import copy
import importlib.metadata
import json
import math

OGC_VERSION = "0.3.0"
OGC = "open_golf_coach."
BALL = ("ball_speed_meters_per_second", "vertical_launch_angle_degrees", "horizontal_launch_angle_degrees")
SPIN = ("total_spin_rpm", "spin_axis_degrees", "backspin_rpm", "sidespin_rpm")
FLIGHT = ("carry_distance_meters", "total_distance_meters", "offline_distance_meters", "peak_height_meters", "descent_angle_degrees", "hang_time_seconds")
CLUB = ("club_speed_meters_per_second", "smash_factor", "club_path_degrees", "club_face_to_target_degrees", "club_face_to_path_degrees")
OTHER = ("angle_of_attack_degrees", "dynamic_loft_degrees", "face_closure_rate_dps")
ALIASES = {"ball_speed_meters_per_second": ("ball_speed_mph", .44704),
           "club_speed_meters_per_second": ("club_speed_mph", .44704),
           "carry_distance_meters": ("carry_distance_yards", .9144),
           "total_distance_meters": ("total_distance_yards", .9144),
           "offline_distance_meters": ("offline_distance_yards", .9144),
           "peak_height_meters": ("peak_height_yards", .9144)}
ENVIRONMENT = {"elevation_meters": 0., "temperature_kelvin": 298.15, "humidity_percent": 50.}


def _number(v):
    try:
        return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    except (ValueError, OverflowError):
        return False


def _get(obj, path, default=None):
    for p in path.split('.'):
        if not isinstance(obj, dict) or p not in obj:
            return default
        obj = obj[p]
    return obj


def _present(obj, path):
    absent = object()
    return _get(obj, path, absent) is not absent


def _put(obj, path, value):
    parts = path.split('.')
    for p in parts[:-1]:
        if p in obj and not isinstance(obj[p], dict):
            return False
        obj = obj.setdefault(p, {})
    if parts[-1] in obj:
        return False
    obj[parts[-1]] = copy.deepcopy(value)
    return True


def _path(field):
    return field if field in BALL + SPIN[:2] else OGC + field


def _local_calculator(inputs):
    if importlib.metadata.version('opengolfcoach') != OGC_VERSION:
        raise RuntimeError('unsupported OpenGolfCoach version')
    from opengolfcoach import calculate_derived_values
    return json.loads(calculate_derived_values(json.dumps(inputs, allow_nan=False)))


def _saturated(speed, launch, spin):
    # Upstream effective-COR bounds, NOT statistical confidence.
    bands = ((40, .55, 28, 15, 9000, 4000), (50, .66, 20, 12, 7000, 2500),
             (60, .72, 16, 10, 5000, 2000), (math.inf, .83, 12, 8, 2500, 1500))
    _, base, optimal, tolerance, optimal_spin, spin_tol = next(b for b in bands if speed <= b[0])
    lp = min(abs(max(-5, min(70, launch)) - optimal) / tolerance, 3) ** 1.25 * .06
    divisor = spin_tol if spin >= optimal_spin else spin_tol * 1.5
    sp = min(abs(spin - optimal_spin) / divisor, 3) ** 1.15 * .08
    kp = ((1200 - spin) / 1200) ** 1.3 * .05 if spin < 1200 else 0
    return base - lp - sp - kp <= .52 or base - lp - sp - kp >= .83


def calibration_shot(shot):
    """Recover pre-enrichment data; remove known estimates/derivations.

    Remaining source-reported data is NOT automatically measurement truth.
    Consumers still require independently verified calibration targets.
    """
    result = copy.deepcopy(_get(shot, '_enrichment.raw_shot', shot))
    paths = list(_get(result, '_cgp.estimated_fields', []))
    for path, meta in result.get('_metric_provenance', {}).items():
        if meta.get('kind') in {'derived', 'modelled', 'source_estimated', 'estimated'}:
            paths.append(path)
    for path in paths:
        parts = path.split('.')
        parent = result if len(parts) == 1 else _get(result, '.'.join(parts[:-1]), {})
        if isinstance(parent, dict):
            parent.pop(parts[-1], None)
    return result


def enrich_shot(shot, *, enabled=False, estimate_club=False, calculator=None):
    """Independent display shot, preserving every existing value including 0.

    Disabled calls only label source provenance. An injected local calculator
    accepts a dictionary and returns {'open_golf_coach': {...}}. Re-enrichment
    uses the original snapshot, never previous model outputs as new inputs.
    """
    if not isinstance(shot, dict):
        raise TypeError('shot must be a dictionary')
    original = _get(shot, '_enrichment.raw_shot', shot) if enabled else shot
    if not isinstance(original, dict):
        return copy.deepcopy(shot)
    result = copy.deepcopy(original)
    provenance = result.setdefault('_metric_provenance', {})
    if not isinstance(provenance, dict):
        return result
    source = result.get('_source', 'unknown')
    estimated = _get(result, '_cgp.estimated_fields', [])
    source_meta = result.get('_cgp' if source == 'cgp' else '_open_connect', {})
    derived = source_meta.get('derived_fields', [])
    for field in BALL + SPIN + FLIGHT + CLUB + OTHER:
        paths = [field, OGC + field]
        if field in ALIASES:
            paths.append(OGC + 'us_customary_units.' + ALIASES[field][0])
        for path in paths:
            if not _present(result, path):
                continue
            kind = ('source_estimated' if path in estimated else 'derived' if path in derived
                    else 'measured' if source == 'cgp' else 'source_reported')
            provenance.setdefault(path, {'kind': kind, 'method': source,
                                         'calibration_ground_truth': kind == 'measured'})
    if not enabled:
        return result
    status = {'status': 'derived_only', 'version': OGC_VERSION,
              'raw_shot': copy.deepcopy(original), 'modelled_fields': [],
              'calibration_ground_truth': False}
    result['_enrichment'] = status

    def add(path, v, kind='derived', inputs=(), assumptions=(), flags=()):
        if isinstance(v, (int, float)) and not _number(v):
            return
        if _put(result, path, v):
            provenance[path] = {'kind': kind, 'method': 'OpenGolfCoach' if kind == 'modelled' else 'mathematical conversion',
                                'version': OGC_VERSION if kind == 'modelled' else 'sps-1',
                                'inputs': list(inputs), 'assumptions': list(assumptions),
                                'flags': list(flags), 'calibration_ground_truth': False}
            if kind == 'modelled':
                status['modelled_fields'].append(path)

    def value(field):
        for path in (_path(field), field, OGC + field):
            if _present(result, path):
                v = _get(result, path)
                return (v if _number(v) else None), path
        return None, _path(field)

    def units():
        for field, (imperial, factor) in ALIASES.items():
            path = OGC + 'us_customary_units.' + imperial
            metric, mp = value(field)
            imp = _get(result, path)
            if metric is not None:
                add(path, metric / factor, inputs=[mp])
            elif _number(imp) and not _present(result, _path(field)):
                add(_path(field), imp * factor, inputs=[path])
    units()
    total, tp = value(SPIN[0]); axis, ap = value(SPIN[1])
    back, bp = value(SPIN[2]); side, sp = value(SPIN[3])
    if total is not None and axis is not None and -90 <= axis <= 90:
        angle = math.radians(axis)
        add(OGC + SPIN[2], total * math.cos(angle), inputs=[tp, ap])
        add(OGC + SPIN[3], (abs(total) if source == 'cgp' else total) * math.sin(angle), inputs=[tp, ap])
    elif back is not None and side is not None and back >= 0:
        add(SPIN[0], math.hypot(back, side), inputs=[bp, sp])
        add(SPIN[1], math.degrees(math.atan2(side, back)), inputs=[bp, sp])
    total, tp = value(SPIN[0]); axis, ap = value(SPIN[1])
    back, bp = value(SPIN[2]); side, sp = value(SPIN[3])
    speed, speed_path = value(BALL[0]); club_speed, cp = value(CLUB[0])
    if speed is not None and club_speed is not None and speed >= 0 and club_speed > 0:
        if not any(_present(result, p) for p in ('smash_factor', OGC + 'smash_factor')):
            add(OGC + 'smash_factor', speed / club_speed, inputs=[speed_path, cp])
    required = BALL + SPIN[:2]
    inputs = {key: value(key)[0] for key in required}
    missing = [key for key, v in inputs.items() if v is None]
    if missing:
        status.update(reason='missing_inputs', missing_inputs=missing)
        return result
    if total < 0 or (back is not None and back < 0):
        status['reason'] = 'topspin_not_supported_by_ogc_adapter'
        return result
    # Conservative adapter envelope, not a validated accuracy guarantee.
    if not (0 < speed <= 100 and 0 <= inputs[BALL[1]] <= 70 and -90 <= inputs[BALL[2]] <= 90
            and 0 <= total <= 20000 and -90 <= axis <= 90):
        status['reason'] = 'outside_adapter_operating_envelope'
        return result
    if total == 0 and axis != 0:
        status['reason'] = 'inconsistent_zero_spin_axis'
        return result
    expected = (total * math.cos(math.radians(axis)), total * math.sin(math.radians(axis)))
    if back is not None and side is not None and not all(math.isclose(a, b, rel_tol=.01, abs_tol=2) for a, b in zip((back, side), expected)):
        status['reason'] = 'inconsistent_spin_representations'
        return result
    assumptions = ['Still air; level landing surface', 'Typical fairway rollout']
    for key, default in ENVIRONMENT.items():
        env = result.get(key)
        if env is None:
            inputs[key] = default
            assumptions.append(f'{key}={default}')
        elif _number(env):
            inputs[key] = env
        else:
            status['reason'] = 'invalid_environment'
            return result
    if not (-500 <= inputs['elevation_meters'] <= 5000 and 233 <= inputs['temperature_kelvin'] <= 333 and 0 <= inputs['humidity_percent'] <= 100):
        status['reason'] = 'invalid_environment'
        return result
    pressure = result.get('pressure_pascals')
    if pressure is not None:
        if not _number(pressure) or not 40000 <= pressure <= 110000:
            status['reason'] = 'invalid_environment'
            return result
        inputs['pressure_pascals'] = pressure
    else:
        assumptions.append('Pressure derived from elevation')
    try:
        output = (calculator or _local_calculator)(copy.deepcopy(inputs)).get('open_golf_coach')
        if not isinstance(output, dict):
            raise ValueError('missing OpenGolfCoach output')
    except Exception as exc:
        status.update(status='unavailable', reason='local_engine_failed', error_type=type(exc).__name__)
        return result
    dependencies = [value(key)[1] for key in required] + list(ENVIRONMENT)
    if pressure is not None:
        dependencies.append('pressure_pascals')
    for field in FLIGHT:
        if any(_present(result, p) for p in (field, OGC + field)):
            continue
        candidate = output.get(field)
        if _number(candidate) and (field == 'offline_distance_meters' or candidate >= 0):
            add(OGC + field, candidate, 'modelled', dependencies, assumptions)
    if estimate_club:
        saturated = _saturated(speed, inputs[BALL[1]], total)
        status['club_estimate_saturated'] = saturated
        assumptions = ['Club category inferred from ball speed, not selected club',
                       'Fixed 200 g head; simplified collision/D-plane model']
        for field in CLUB:
            if any(_present(result, p) for p in (field, OGC + field)):
                continue
            if field in CLUB[:2] and (saturated or club_speed is not None):
                continue
            if total == 0 and field in CLUB[2:]:
                continue
            candidate = output.get(field)
            valid = _number(candidate) and candidate > 0
            if field in CLUB[2:]:
                valid = (isinstance(candidate, dict) and set(candidate) == {'right_handed', 'left_handed'}
                         and all(_number(v) and abs(v) <= 180 for v in candidate.values()))
            if valid:
                add(OGC + field, candidate, 'modelled', dependencies, assumptions, ['heuristic_not_measured'])
    units()
    status['status'] = 'enriched' if status['modelled_fields'] else 'derived_only'
    return result
