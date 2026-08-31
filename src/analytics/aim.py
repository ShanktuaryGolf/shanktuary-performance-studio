"""Aim calibration.

The Nova has no aim calibration of its own. A unit that sits a couple of
degrees off square reports every shot as a push (or a pull), which silently
biases every directional readout built on top of it.

The correction is applied at the READ boundary, never on the incoming event:
AGENTS.md requires the native Nova payload to be preserved when forwarding, and
shots recorded before a user calibrated must be corrected too. So this module
takes a stored shot and returns a corrected copy.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from pathlib import Path
from typing import Any

# A device can plausibly sit a few degrees off square. Beyond this the number is
# a mis-set device or a bad sample, not a calibration, so refuse to trust it.
MAX_AIM_OFFSET_DEG = 5.0

# A standard deviation from a handful of samples is noise, and one pull would
# dominate. Ten is the smallest set worth calling a calibration.
MIN_CALIBRATION_SHOTS = 10

# User state, never repo content -- this value is specific to one person's
# room and device placement.
AIM_FILE = Path.home() / ".config" / "shanktuary" / "aim.json"


def _clamp(v: float) -> float:
    return max(-MAX_AIM_OFFSET_DEG, min(MAX_AIM_OFFSET_DEG, float(v)))


def load_aim_offset(path: Path | None = None) -> float:
    """Read the saved offset, or 0.0 when absent or unreadable.

    A missing or corrupt file must degrade to "no correction" rather than
    raising: an aim file is a convenience, and losing it should never stop the
    app from showing shots.
    """
    p = Path(path) if path is not None else AIM_FILE
    try:
        data = json.loads(p.read_text())
        return _clamp(float(data.get("aim_offset_deg", 0.0)))
    except Exception:
        return 0.0


def save_aim_offset(offset_deg: float, path: Path | None = None) -> None:
    """Persist the offset atomically, creating the config dir if needed."""
    p = Path(path) if path is not None else AIM_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"aim_offset_deg": _clamp(offset_deg)}, indent=1))
    os.replace(tmp, p)


def offset_from_shots(shots: list[dict[str, Any]]) -> float | None:
    """Derive an aim offset from a set of shots hit at one fixed target.

    Returns the **median** start line, not the mean: a single pulled shot must
    not be able to move the calibration. Returns ``None`` when there are too few
    usable shots -- refusing to answer is better than guessing a correction that
    then biases everything downstream.
    """
    angles = [
        float(s["horizontal_launch_angle_degrees"])
        for s in shots
        if isinstance(s, dict) and s.get("horizontal_launch_angle_degrees") is not None
    ]
    if len(angles) < MIN_CALIBRATION_SHOTS:
        return None
    median = statistics.median(angles)
    return max(-MAX_AIM_OFFSET_DEG, min(MAX_AIM_OFFSET_DEG, median))


def offset_from_geometry(distance_ft: float, lateral_in: float) -> float | None:
    """Derive the aim offset from two measurements anyone can take with a tape.

    ``distance_ft``  how far the device sits from the thing it is aimed at
                     (screen, net, target mark).
    ``lateral_in``   how far that aim point sits to the RIGHT of the real
                     target line, in inches. Negative is left.

    This is the path for a user who cannot answer "how many degrees off is
    it?" -- nobody can eyeball that -- but can measure a distance and an
    offset. Returns ``None`` when the distance is missing, because a zero
    result would render as "calibrated" and be indistinguishable from a
    device that is genuinely square.
    """
    try:
        d_in = float(distance_ft) * 12.0
        lat = float(lateral_in)
    except (TypeError, ValueError):
        return None
    if d_in <= 0.0:
        return None
    return _clamp(math.degrees(math.atan2(lat, d_in)))


# OpenGolfCoach's start-line vocabulary and the boundary between the words.
# The +-3.0 threshold is RECOVERED, not chosen: it reproduces all 28 stored
# non-Baby / non-Worm-Burner labels exactly, while +-2.5 and +-3.5 both
# misclassify. See tests/test_aim_labels.py.
OGC_START_WORDS = ("Pull", "Push", "Straight")
OGC_STRAIGHT_BAND_DEG = 3.0

# OGC branches we deliberately do not touch: "Baby ..." applies its own
# near-zero naming rule, and "Worm Burner" is a launch-angle verdict rather
# than a direction one.
_OGC_OPAQUE = ("Baby", "Worm")


def relabel_shot_name(name: str | None, corrected_hla_deg: float,
                      offset_deg: float) -> str | None:
    """Re-word the start-line half of an OGC shot name after an aim correction.

    OGC derives ``shot_name`` from the raw device-frame angles, so once an
    offset is applied the start-line word is stale -- a shot that is now dead
    straight would still read "Pull Fade", making a calibrated shot list look
    identical to an uncalibrated one.

    Only the start-line word changes. Spin axis is a property of the ball, not
    of where the device points, so the curve word ("Draw", "Fade", ...) stays
    exactly as OGC reported it.
    """
    if not name or not offset_deg:
        return name
    if any(tok in name for tok in _OGC_OPAQUE):
        return name

    words = name.split()
    if not any(w in OGC_START_WORDS for w in words):
        return name

    if corrected_hla_deg < -OGC_STRAIGHT_BAND_DEG:
        start = "Pull"
    elif corrected_hla_deg > OGC_STRAIGHT_BAND_DEG:
        start = "Push"
    else:
        start = "Straight"

    return " ".join(start if w in OGC_START_WORDS else w for w in words)


def _rotate(carry: float, offline: float, offset_deg: float) -> tuple[float, float]:
    """Rotate a landing point about the tee by ``-offset_deg``.

    Offline is a lateral *distance*, not an angle, so removing a device's aim
    error is a rotation of the landing point -- not a subtraction. Carry is the
    down-range component and changes only in the second order.
    """
    a = math.radians(-float(offset_deg))
    cos_a, sin_a = math.cos(a), math.sin(a)
    return (carry * cos_a - offline * sin_a, carry * sin_a + offline * cos_a)


def _corrected_pair(container: dict[str, Any], carry_key: str, offline_key: str,
                    offset_deg: float) -> dict[str, Any] | None:
    """Return a copy of ``container`` with one carry/offline pair rotated."""
    if offline_key not in container:
        return None
    carry = float(container.get(carry_key) or 0.0)
    offline = float(container.get(offline_key) or 0.0)
    new_carry, new_offline = _rotate(carry, offline, offset_deg)
    out = dict(container)
    out[offline_key] = new_offline
    if carry_key in container:
        out[carry_key] = new_carry
    return out


def apply_aim(shot: dict[str, Any], offset_deg: float) -> dict[str, Any]:
    """Return a copy of ``shot`` with the aim offset removed.

    ``offset_deg`` is where the device points relative to the target line: a
    device aimed 2 deg right of target reports shots 2 deg left of where they
    really went, so the offset is subtracted from the reported angle.
    """
    out = dict(shot)
    hla = out.get("horizontal_launch_angle_degrees")
    if hla is not None:
        hla = float(hla) - float(offset_deg)
        out["horizontal_launch_angle_degrees"] = hla

    ogc = shot.get("open_golf_coach")
    if not isinstance(ogc, dict):
        return out

    new_ogc = _corrected_pair(
        ogc, "carry_distance_meters", "offline_distance_meters", offset_deg
    )
    new_ogc = dict(ogc) if new_ogc is None else new_ogc

    # shot_name is OGC's verdict on the RAW start line, so it goes stale the
    # moment the angles move. Without this a corrected shot list looks
    # identical to an uncorrected one -- the numbers change but every label
    # still reads "Pull Fade".
    if hla is not None:
        name = ogc.get("shot_name")
        if isinstance(name, dict):
            new_ogc["shot_name"] = {
                k: relabel_shot_name(v, hla if k == "right_handed" else -hla,
                                     offset_deg)
                for k, v in name.items()
            }
        elif isinstance(name, str):
            new_ogc["shot_name"] = relabel_shot_name(name, hla, offset_deg)

    us = ogc.get("us_customary_units")
    if isinstance(us, dict):
        new_us = _corrected_pair(
            us, "carry_distance_yards", "offline_distance_yards", offset_deg
        )
        if new_us is not None:
            new_ogc["us_customary_units"] = new_us

    out["open_golf_coach"] = new_ogc
    return out
