"""Contact evidence, not an inversion of ball-flight estimates.

Coordinates use the existing SPS payload convention: +horizontal = heel,
+vertical = high. Handedness changes the drawing, never the stored values.
"""
import math
import statistics
from dataclasses import dataclass

MIN_CONTEXT_SHOTS = 3


def flight_context(shot, session_shots):
    """Descriptive same-club session medians, never contact diagnoses.

    Exclude the selected shot (including display copies), bad reads, and
    partial swings. Count valid peers separately for each metric.
    """
    from .index import valid_shots

    shot = shot if isinstance(shot, dict) else {}
    club = shot.get("club")
    identity = shot.get("timestamp_ns") or shot.get("shotId")
    # Full swings only, through the same gate the Index scores against: a
    # median polluted by chips reads 59 mph against an 88 mph driver-ish swing.
    peers = [s for s in valid_shots(list(session_shots))
             if s is not shot and s.get("club") == club
             and not (identity is not None and
                      (s.get("timestamp_ns") or s.get("shotId")) == identity)]
    rows = []
    for label, field, unit, factor in (
        ("Launch", "vertical_launch_angle_degrees", "°", 1),
        ("Spin", "total_spin_rpm", "rpm", 1),
        ("Ball speed", "ball_speed_meters_per_second", "mph", 1 / 0.44704),
    ):
        def value(s):
            n = finite_number(s.get(field))
            if n is None or (field != "vertical_launch_angle_degrees" and n < 0):
                return None
            return n * factor

        values = [v for s in peers if (v := value(s)) is not None]
        current = value(shot)
        median = statistics.median(values) if len(values) >= MIN_CONTEXT_SHOTS else None
        rows.append({"label": label, "unit": unit, "value": current,
                     "median": median, "count": len(values),
                     "delta": current - median if current is not None and median is not None else None})
    return rows


def finite_number(value):
    if isinstance(value, (bool, dict, list)) or value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _axis_text(value, positive, negative):
    if value is None:
        return "Not reported"
    direction = positive if value > 0 else negative if value < 0 else "Centre"
    return f"{direction} · {abs(value):.1f} mm"


@dataclass(frozen=True)
class ContactLocation:
    horizontal_mm: float | None = None
    vertical_mm: float | None = None
    # "reported": a contact object in the launch-monitor payload.
    # "marked":   the golfer clicked the face (tape / spray / sticker).
    source: str | None = None

    @property
    def complete(self):
        return self.horizontal_mm is not None and self.vertical_mm is not None

    @property
    def available(self):
        return self.horizontal_mm is not None or self.vertical_mm is not None

    @property
    def badge(self):
        if self.source == "marked":
            return "MARKED"
        return "REPORTED" if self.available else "UNAVAILABLE"

    @property
    def horizontal_text(self):
        return _axis_text(self.horizontal_mm, "Heel", "Toe")

    @property
    def vertical_text(self):
        return _axis_text(self.vertical_mm, "High", "Low")

    @property
    def headline(self):
        if self.source == "marked":
            return "Marked by you"
        return "Contact reported" if self.available else "Location unavailable"

    @property
    def detail(self):
        if self.available:
            return f"{self.horizontal_text} / {self.vertical_text}"
        return "Contact cannot be located from ball flight alone"


# Schematic geometry of the generic iron artwork (290x220 image, drawn at
# `size` = its height). The sweet-spot offset and mm scale were the values
# the old marker already used; they are kept in ONE place so drawing and
# click-to-mm stay inverse of each other.
FACE_SWEET_DX = 43.5 / 220     # towards the heel edge of the artwork
FACE_SWEET_DY = 40 / 220       # above artwork centre
FACE_PX_PER_MM = (131 / 220) / 52
FACE_MAX_H_MM = 24
FACE_MAX_V_MM = 16
# Opaque rows of the 220px-tall artwork (alpha bbox 4..132): the lower 40% is
# transparent padding, so anything laid out from the image height sits in air.
FACE_OPAQUE_TOP = 4 / 220
FACE_OPAQUE_BOTTOM = 132 / 220


@dataclass(frozen=True)
class FaceGeometry:
    """Pixel <-> mm mapping for the drawn face. Handedness flips heel/toe."""
    cx: float
    cy: float
    size: float
    left_handed: bool = False

    @property
    def sweet_spot(self):
        sign = 1 if self.left_handed else -1
        return (self.cx + FACE_SWEET_DX * self.size * sign,
                self.cy - FACE_SWEET_DY * self.size)

    @property
    def px_per_mm(self):
        return FACE_PX_PER_MM * self.size

    def mm_to_px(self, horizontal_mm, vertical_mm):
        sx, sy = self.sweet_spot
        h_sign = -1 if self.left_handed else 1
        return (sx + horizontal_mm * self.px_per_mm * h_sign,
                sy - vertical_mm * self.px_per_mm)

    def px_to_mm(self, px, py):
        """Inverse of mm_to_px; None when the click is off the playable face."""
        sx, sy = self.sweet_spot
        h_sign = -1 if self.left_handed else 1
        h = (px - sx) / self.px_per_mm * h_sign
        v = (sy - py) / self.px_per_mm
        if abs(h) > FACE_MAX_H_MM or abs(v) > FACE_MAX_V_MM:
            return None
        return (h, v)


def contact_location(shot):
    """Accept explicit finite coordinates only; never invent the other axis.

    Use the first usable contact object, without mixing coordinates from
    separate objects. Payload presence is 'reported', not proof of a sensor.
    """
    if not isinstance(shot, dict):
        return ContactLocation()
    ogc = shot.get("open_golf_coach")
    for owner in (shot, ogc if isinstance(ogc, dict) else {}):
        for key in ("face_impact", "impact_location", "face_contact"):
            data = owner.get(key)
            if not isinstance(data, dict):
                continue
            axes = []
            for aliases in (("lateral_offset_mm", "heel_toe_mm", "horizontal_offset_mm", "x_mm"),
                            ("vertical_offset_mm", "high_low_mm", "y_mm")):
                value = next((number for alias in aliases
                              if (number := finite_number(data.get(alias))) is not None), None)
                axes.append(value)
            result = ContactLocation(*axes, source="reported")
            if result.available:
                return result
    # The golfer's own mark: both axes required, never mixed with a reading.
    mark = shot.get("marked_contact")
    if isinstance(mark, dict):
        h = finite_number(mark.get("horizontal_mm"))
        v = finite_number(mark.get("vertical_mm"))
        if h is not None and v is not None:
            return ContactLocation(h, v, source="marked")
    return ContactLocation()
