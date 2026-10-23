"""Presence/provenance-aware display metrics; never mutate source payloads.

Speeds are mph, distances yards (including apex), angles degrees, remaining
units native. None means unavailable; a finite reported zero remains zero.
"""

import math

OGC = "open_golf_coach."
US = OGC + "us_customary_units."
METRIC_PATHS = {
    "carry": ((OGC + "carry_distance_meters", 1 / .9144), (US + "carry_distance_yards", 1)),
    "total": ((OGC + "total_distance_meters", 1 / .9144), (US + "total_distance_yards", 1)),
    "ball_speed": (("ball_speed_meters_per_second", 1 / .44704), (US + "ball_speed_mph", 1),
                   (OGC + "ball_speed_meters_per_second", 1 / .44704)),
    "club_speed": ((OGC + "club_speed_meters_per_second", 1 / .44704), (US + "club_speed_mph", 1)),
    "smash": ((OGC + "smash_factor", 1),),
    "launch": (("vertical_launch_angle_degrees", 1), (OGC + "vertical_launch_angle_degrees", 1)),
    "horizontal_launch": (("horizontal_launch_angle_degrees", 1),),
    "spin": (("total_spin_rpm", 1), (OGC + "total_spin_rpm", 1)),
    "spin_axis": (("spin_axis_degrees", 1), (OGC + "spin_axis_degrees", 1)),
    "closure_rate": ((OGC + "face_closure_rate_dps", 1), ("face_closure_rate_dps", 1),
                     (OGC + "closure_rate_dps", 1)),
    "apex": ((OGC + "peak_height_meters", 1 / .9144), (US + "peak_height_yards", 1)),
    "offline": ((OGC + "offline_distance_meters", 1 / .9144), (US + "offline_distance_yards", 1)),
    "club_path": ((OGC + "club_path_degrees", 1),),
    "face_to_path": ((OGC + "club_face_to_path_degrees", 1),),
    "face_to_target": ((OGC + "club_face_to_target_degrees", 1),),
    "attack_angle": ((OGC + "angle_of_attack_degrees", 1), ("angle_of_attack_degrees", 1)),
    "dynamic_loft": ((OGC + "dynamic_loft_degrees", 1), ("dynamic_loft_degrees", 1)),
    "hang_time": ((OGC + "hang_time_seconds", 1),),
    "descent": ((OGC + "descent_angle_degrees", 1),),
    "backspin": ((OGC + "backspin_rpm", 1), ("backspin_rpm", 1)),
    "sidespin": ((OGC + "sidespin_rpm", 1), ("sidespin_rpm", 1)),
}
_HANDED_SCALARS = {"club_path", "face_to_path", "face_to_target"}
_STATUS_RANK = {"REPORTED": 0, "DERIVED": 1, "ESTIMATED": 2, "MODELLED": 3}


def _get(shot, path):
    for part in path.split("."):
        if not isinstance(shot, dict):
            return None
        shot = shot.get(part)
    return shot


def _number(value):
    try:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value))
    except (ValueError, OverflowError):
        return False


def _path_status(shot, path, seen=()):
    if path in seen or len(seen) >= 64:
        return "DERIVED"
    provenance = shot.get("_metric_provenance")
    meta = provenance.get(path) if isinstance(provenance, dict) else None
    if isinstance(meta, dict):
        kind = meta.get("kind")
        if kind == "modelled":
            return "MODELLED"
        if kind == "source_estimated":
            return "ESTIMATED"
        if kind in ("measured", "source_reported"):
            return "REPORTED"
        if kind == "derived":
            inputs = meta.get("inputs")
            inherited = [_path_status(shot, item, seen + (path,))
                         for item in inputs if isinstance(item, str)] if isinstance(inputs, list) else []
            return max(["DERIVED", *inherited], key=_STATUS_RANK.__getitem__)
    cgp = shot.get("_cgp")
    estimated = cgp.get("estimated_fields") if isinstance(cgp, dict) else None
    if isinstance(estimated, (list, tuple)) and path in estimated:
        return "ESTIMATED"
    receiver = shot.get("_open_connect")
    derived = receiver.get("derived_fields") if isinstance(receiver, dict) else None
    if isinstance(derived, (list, tuple)) and path in derived:
        return "DERIVED"
    return "REPORTED"


def _metric(shot, key, left_handed):
    if not isinstance(shot, dict):
        return None, "NOT REPORTED"
    candidates = []
    for path, factor in METRIC_PATHS.get(key, ()):
        value = _get(shot, path)
        if isinstance(value, dict):
            hand = "left_handed" if left_handed else "right_handed"
            value = value.get(hand, value.get("right_handed"))
        elif left_handed and key in _HANDED_SCALARS and _number(value):
            value = -value
        if _number(value):
            converted = value * factor
            if _number(converted):
                candidates.append((converted, _path_status(shot, path)))
    if not candidates:
        return None, "NOT REPORTED"
    # A reported alias outranks an inferred representation. Two reported
    # representations retain the canonical SI priority above.
    return min(candidates, key=lambda candidate: _STATUS_RANK[candidate[1]])


def metric_value(shot, key, left_handed=False):
    """Present finite metric in display units, else None (never invented zero)."""
    return _metric(shot, key, left_handed)[0]


def metric_status(shot, key, left_handed=False):
    """REPORTED, DERIVED, ESTIMATED, MODELLED, or NOT REPORTED."""
    return _metric(shot, key, left_handed)[1]
