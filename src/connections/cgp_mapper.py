"""Pure CGP Draft 2 shot validation and mapping into the Nova/SPS contract.

Reference: OpenLaunchLabs/common-golf-protocol at
1c343a8aac2b21665e9ce002789dfcc98abe133f (protocol 0.2.0).
Preliminary snapshots are ignored, not merged. Missing measurements stay
missing. Negative total spin means topspin; lateral signs remain target-relative.
"""

import copy
import math
import uuid
from collections import OrderedDict

BALL_FIELDS = ("ball_speed_meters_per_second", "vertical_launch_angle_degrees",
               "horizontal_launch_angle_degrees")
TOTAL = "total_spin_revolutions_per_minute"
AXIS = "spin_axis_degrees"
BACK = "backspin_revolutions_per_minute"
SIDE = "sidespin_revolutions_per_minute"
NUMERIC_FIELDS = BALL_FIELDS + (TOTAL, AXIS, BACK, SIDE, "measured_at_nanoseconds", "shot_number")
MPH_PATH = "open_golf_coach.us_customary_units.ball_speed_mph"
FIELD_NAMES = {
    BALL_FIELDS[0]: [BALL_FIELDS[0], MPH_PATH],
    BALL_FIELDS[1]: [BALL_FIELDS[1], "open_golf_coach." + BALL_FIELDS[1]],
    BALL_FIELDS[2]: [BALL_FIELDS[2], "open_golf_coach." + BALL_FIELDS[2]],
    TOTAL: ["total_spin_rpm", "open_golf_coach.total_spin_rpm"],
    AXIS: [AXIS, "open_golf_coach." + AXIS],
    BACK: ["open_golf_coach.backspin_rpm"],
    SIDE: ["open_golf_coach.sidespin_rpm"],
    "measured_at_nanoseconds": ["_cgp.measured_at_nanoseconds"],
    "shot_number": ["_cgp.shot_number"],
}


def _number(message, field, minimum=None, maximum=None):
    value = message[field]
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except (ValueError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"{field} must be a finite JSON number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} must be at most {maximum}")


def validate_shot(message):
    """Validate known fields while ignoring additive vendor extensions."""
    if not isinstance(message, dict) or message.get("type") != "shot":
        raise ValueError("channel 1 requires a shot object")
    number = message.get("shot_number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("shot_number must be a positive integer")
    for field in BALL_FIELDS:
        if field not in message:
            raise ValueError(f"missing {field}")
    _number(message, BALL_FIELDS[0], 0)
    for field in BALL_FIELDS[1:]:
        _number(message, field, -90, 90)
    if (TOTAL in message) != (AXIS in message):
        raise ValueError("total spin and axis must be sent together")
    if BACK in message or SIDE in message:
        if not all(field in message for field in (TOTAL, AXIS, BACK, SIDE)):
            raise ValueError("spin components require total, axis, backspin and sidespin")
    for field in (TOTAL, BACK, SIDE):
        if field in message:
            _number(message, field)
    if AXIS in message:
        _number(message, AXIS, -90, 90)
        if message[TOTAL] == 0 and message[AXIS] != 0:
            raise ValueError("zero total spin requires zero axis")
    if "final" in message and not isinstance(message["final"], bool):
        raise ValueError("final must be boolean")
    if "measurement_id" in message and not isinstance(message["measurement_id"], str):
        raise ValueError("measurement_id must be a string")
    if "measured_at_nanoseconds" in message:
        value = message["measured_at_nanoseconds"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("measured_at_nanoseconds must be an integer")
    for field, choices in (("player_dexterity", {"right", "left", "unknown"}),
                           ("tee_position", {"tee", "mat", "ground", "unknown"}),
                           ("shot_kind", {"full", "putt", "chip"})):
        if field in message and (not isinstance(message[field], str) or message[field] not in choices):
            raise ValueError(f"invalid {field}")
    estimated = message.get("estimated", [])
    if (not isinstance(estimated, list) or not all(isinstance(f, str) for f in estimated)
            or len(set(estimated)) != len(estimated)):
        raise ValueError("estimated must be an array of unique field names")


def map_cgp_shot_to_sps_payload(message, *, device_name=None):
    """Return a final SPS payload or None; no flight or club data is invented."""
    validate_shot(message)
    if message.get("final", True) is False:
        return None
    payload = {"type": "shot", "_source": "cgp"}
    for field in BALL_FIELDS + (AXIS,):
        if field in message:
            payload[field] = message[field]
    if TOTAL in message:
        payload["total_spin_rpm"] = message[TOTAL]
    ogc = {
        "us_customary_units": {"ball_speed_mph": message[BALL_FIELDS[0]] / 0.44704},
        BALL_FIELDS[1]: message[BALL_FIELDS[1]], BALL_FIELDS[2]: message[BALL_FIELDS[2]],
    }
    for field in ("total_spin_rpm", AXIS):
        if field in payload:
            ogc[field] = payload[field]
    for source, target in ((BACK, "backspin_rpm"), (SIDE, "sidespin_rpm")):
        if source in message:
            ogc[target] = message[source]
    payload["open_golf_coach"] = ogc
    payload["_metric_provenance"] = {
        MPH_PATH: {"kind": "derived", "method": "unit conversion", "version": "sps-1",
                   "inputs": [BALL_FIELDS[0]], "assumptions": [], "flags": [],
                   "calibration_ground_truth": False},
    }
    estimated = [field for field in message.get("estimated", [])
                 if field in message and field in NUMERIC_FIELDS]
    try:
        raw = copy.deepcopy(message)
    except RecursionError as exc:
        raise ValueError("CGP shot nesting is too deep") from exc
    payload["_cgp"] = {
        "shot_number": message["shot_number"], "raw": raw, "estimated": estimated,
        "estimated_fields": [path for field in estimated for path in FIELD_NAMES[field]],
        "derived_fields": [MPH_PATH],
        "missing_fields": [field for field in NUMERIC_FIELDS if field not in message],
    }
    for field in ("measurement_id", "measured_at_nanoseconds", "player_dexterity", "tee_position", "shot_kind"):
        if field in message:
            payload["_cgp"][field] = message[field]
    if device_name is not None:
        payload["_cgp"]["device_name"] = device_name
    # Device monotonic nanoseconds are not wall-clock timestamps. Peer keys
    # are transient transport status, never persisted in shot history.
    return payload


class CGPShotSession:
    """Bounded final-shot replay protection with connection-local counters.

    The newest 4096 final numbers may complete out of order. A stream reset
    does not reset this session. A new connection resets numbers/shot IDs but
    keeps globally unique measurement IDs in the controller-owned memory cache.
    Without measurement_id replay across connections cannot be determined.
    """

    def __init__(self, measurement_ids=None, capacity=4096):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("dedupe capacity must be a positive integer")
        self.measurement_ids = measurement_ids if measurement_ids is not None else OrderedDict()
        self.capacity = capacity
        self._seen_numbers = set()
        self._number_floor = 0
        self.last_shot_number = 0
        self.session_id = uuid.uuid4()

    def ingest(self, message, **provenance):
        payload = map_cgp_shot_to_sps_payload(message, **provenance)
        if payload is None:
            return None
        number = message["shot_number"]
        if number in self._seen_numbers or number <= self._number_floor:
            return None
        self.last_shot_number = max(self.last_shot_number, number)
        self._seen_numbers.add(number)
        if len(self._seen_numbers) > self.capacity:
            oldest = min(self._seen_numbers)
            self._seen_numbers.remove(oldest)
            self._number_floor = oldest
        measurement_id = message.get("measurement_id")
        if measurement_id:
            if measurement_id in self.measurement_ids:
                return None
            self.measurement_ids[measurement_id] = None
            while len(self.measurement_ids) > self.capacity:
                self.measurement_ids.popitem(last=False)
        payload["shotId"] = uuid.uuid5(self.session_id, str(number)).hex
        payload["_cgp"]["session_id"] = self.session_id.hex
        return payload
