"""Read-only presence/provenance helpers for the shared desktop renderers."""
from src.connections.presentation import metric_status, metric_value, shot_shape

OVERVIEW_KEYS = {"carry": "carry", "total": "total", "ball": "ball_speed",
    "club": "club_speed", "smash": "smash", "launch": "launch", "hlaunch": "horizontal_launch",
    "spin": "spin", "axis": "spin_axis", "apex": "apex", "offline": "offline",
    "descent": "descent", "hang": "hang_time", "path": "club_path",
    "face_path": "face_to_path", "face_target": "face_to_target"}


def is_pureplay(shot):
    return isinstance(shot, dict) and shot.get("_source") == "pureplay"


def overview_values(shot, app=None):
    left = bool(getattr(app, "is_left_handed", False))
    raw = {key: metric_value(shot, metric, left) for key, metric in OVERVIEW_KEYS.items()}
    result = {key: value if value is not None else 0.0 for key, value in raw.items()}
    result["_available"] = {key for key, value in raw.items() if value is not None}
    result["_status"] = {key: metric_status(shot, metric, left) for key, metric in OVERVIEW_KEYS.items()}
    result["_pureplay"] = True
    for key in ("path", "face_path", "face_target"):
        result[key + "_known"] = key in result["_available"]
    result["shape"], result["_shape_status"] = shot_shape(shot, left)
    result["shape"] = result["shape"] or "Unavailable"
    return result


def known(values, *keys):
    return not values.get("_pureplay") or all(key in values["_available"] for key in keys)


def marker(values, *keys):
    return "~" if values.get("_pureplay") and any(
        values["_status"].get(key) in ("ESTIMATED", "MODELLED") for key in keys) else ""


def display(values, key, spec=".1f", unit=""):
    if not known(values, key):
        return "--"
    return f"{values[key]:{spec}}{marker(values, key)}{unit}"
