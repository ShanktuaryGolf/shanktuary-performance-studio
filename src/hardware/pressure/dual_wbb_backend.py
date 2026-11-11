"""Dual Wii Balance Board backend -- two WBBs as left/right foot plates."""

import math
import time
from dataclasses import replace

from .base import (
    BoardBackend,
    BoardOrientation,
    DualPlateReading,
    SensorReading,
    remap_for_orientation,
)


class DualWbbBackend(BoardBackend):
    """Merges two single-WBB backends into a dual-plate system.

    Each sub-backend reads one physical Wii Balance Board.
    The left/right assignment is determined externally (e.g. via
    BoardAssignDialog) before constructing this backend.
    """

    SAMPLE_MAX_AGE_S = 1.5

    def __init__(self, left: BoardBackend, right: BoardBackend) -> None:
        self._left = left
        self._right = right
        self._last_dual: DualPlateReading | None = None
        self._left_reading: SensorReading | None = None
        self._right_reading: SensorReading | None = None
        # Display observations are independent of pair readiness. A bad peer
        # must not erase the other board's latest calibrated observation.
        self._observed_readings: dict[str, SensorReading | None] = {
            "left": None, "right": None,
        }
        self._orientation = BoardOrientation.LANDSCAPE

    @property
    def orientation(self) -> BoardOrientation:
        return self._orientation

    @orientation.setter
    def orientation(self, value: BoardOrientation) -> None:
        self._orientation = value

    def open(self) -> None:
        if not self.is_open:
            self._clear_readings()
            self._clear_observed_readings()
        if not self._left.is_open:
            self._left.open()
        if not self._right.is_open:
            self._right.open()

    def _clear_readings(self) -> None:
        self._left_reading = None
        self._right_reading = None
        self._last_dual = None

    def close(self) -> None:
        self._clear_readings()
        self._clear_observed_readings()
        self._left.close()
        self._right.close()

    def disconnect_for_session(self) -> dict:
        """Release exactly these two readers, reporting partial failure."""
        self._clear_readings()
        self._clear_observed_readings()
        results = {}
        for side, board in (("left", self._left), ("right", self._right)):
            try:
                results[side] = board.disconnect_for_session()
            except Exception as exc:
                results[side] = {"released": False, "error": str(exc)}
        return {"released": all(r.get("released", False) for r in results.values()),
                "powered_off": None, "boards": results}

    def shutdown(self) -> None:
        """Request shutdown for both boards; power-off is not confirmed."""
        self._clear_readings()
        self._clear_observed_readings()
        self._left.shutdown()
        self._right.shutdown()

    def _clear_observed_readings(self) -> None:
        self._observed_readings = {"left": None, "right": None}

    def _observe_board_reading(
            self, side: str, backend: BoardBackend,
            reading: SensorReading | None) -> bool:
        available = backend.is_open and not self._invalid_sensor_data(backend)
        if not available:
            self._observed_readings[side] = None
        elif reading is not None:
            # SensorReading is mutable, including through last_dual_reading.
            # Retain only a detached copy of the most recent child result.
            self._observed_readings[side] = replace(reading)
        return available

    @property
    def is_open(self) -> bool:
        return self._left.is_open and self._right.is_open

    def read(self) -> SensorReading | None:
        """Non-blocking read merging both boards.

        Mapping (each board's 4 cells combine into one foot):
          top_left     = left foot front (TL+TR of left board)
          bottom_left  = left foot back  (BL+BR of left board)
          top_right    = right foot front (TL+TR of right board)
          bottom_right = right foot back  (BL+BR of right board)
        """
        # Each backend owns queue draining. In particular, a simulator may
        # produce data on every call, so draining here could loop forever.
        if not self.is_open:
            self._observe_board_reading("left", self._left, None)
            self._observe_board_reading("right", self._right, None)
            self._clear_readings()
            return None
        lr = self._left.read()
        rr = self._right.read()
        left_available = self._observe_board_reading("left", self._left, lr)
        right_available = self._observe_board_reading("right", self._right, rr)
        # A child can detect a disconnection during read(). Discard even a
        # final queued sample rather than presenting a disconnected pair.
        if not (left_available and right_available):
            self._clear_readings()
            return None
        if lr is not None:
            self._left_reading = lr
        if rr is not None:
            self._right_reading = rr

        now = time.monotonic()
        if not (self._is_fresh(self._left_reading, now)
                and self._is_fresh(self._right_reading, now)):
            self._last_dual = None
            return None
        if lr is None and rr is None:
            return None

        left = self._left_reading
        right = self._right_reading
        # Date the aggregate by the newest contributing sample, not this
        # poll. Both source timestamps remain available on the dual reading.
        timestamp = max(left.timestamp, right.timestamp)

        self._last_dual = DualPlateReading(
            left=left,
            right=right,
            timestamp=timestamp,
            device_timestamp_us=0,
        )

        # Remap each plate individually for orientation BEFORE combining.
        # Applying remap to the combined view would scramble the left/right
        # foot axis into front/back.
        if self._orientation != BoardOrientation.LANDSCAPE:
            left = remap_for_orientation(left, self._orientation)
            right = remap_for_orientation(right, self._orientation)

        return SensorReading(
            top_left=left.top_left + left.top_right,
            bottom_left=left.bottom_left + left.bottom_right,
            top_right=right.top_left + right.top_right,
            bottom_right=right.bottom_left + right.bottom_right,
            timestamp=timestamp,
        )

    @property
    def last_dual_reading(self) -> DualPlateReading | None:
        if (not self.is_open or self._invalid_sensor_data(self._left)
                or self._invalid_sensor_data(self._right)):
            self._clear_readings()
        elif self._last_dual is not None:
            now = time.monotonic()
            if not (self._is_fresh(self._last_dual.left, now)
                    and self._is_fresh(self._last_dual.right, now)):
                self._last_dual = None
        return self._last_dual

    @staticmethod
    def _invalid_sensor_data(backend) -> bool:
        method = getattr(type(backend), "get_diagnostics", None)
        if method is None:
            return False
        return bool(method(backend).get("recovery_blocked"))

    def _is_fresh(self, reading: SensorReading | None, now: float) -> bool:
        return (reading is not None
                and 0 <= now - reading.timestamp <= self.SAMPLE_MAX_AGE_S)

    def get_board_loads(self) -> dict:
        """Return each child's current calibrated load without polling it.

        Only observations from the existing read() path are eligible. This
        accessor does not change aggregate caches or readiness, and returns
        detached scalar snapshots rather than internal SensorReading objects.
        The caller owns synchronization with read() and lifecycle operations.
        """
        now = time.monotonic()
        sides = {}
        for side, backend in (("left", self._left), ("right", self._right)):
            child = self._child_diagnostics(backend, now)
            reading = self._observed_readings[side]
            total = None
            if not child["is_open"]:
                error = "disconnected"
            elif child.get("recovery_blocked"):
                error = "invalid_sensor_data"
            elif child.get("calibration_status") == "unavailable":
                error = "calibration_unavailable"
            elif reading is None:
                error = "waiting_for_sample"
            else:
                total = reading.total_kg
                if (not math.isfinite(reading.timestamp)
                        or not math.isfinite(total) or total < 0):
                    error = "invalid_sample"
                elif not self._is_fresh(reading, now):
                    error = "stale_sample"
                else:
                    error = None
            if error in ("disconnected", "invalid_sensor_data", "calibration_unavailable"):
                # A later recovery requires a new actual sample, not revival
                # of an observation made before the child became unavailable.
                self._observed_readings[side] = None
            sides[side] = {
                "device_id": child["device_id"],
                "total_kg": total if error is None else None,
                "timestamp": reading.timestamp if error is None else None,
                "fresh": error is None,
                "error": error,
            }
        return sides

    def _child_diagnostics(self, backend, now: float) -> dict:
        """Read a child's existing, bounded diagnostics, never its HID queue.

        These observations belong to the physical child, independently of
        the aggregate cache (which is cleared when either child is invalid).
        Backends without diagnostics remain unknown, not inferred from a
        cached aggregate reading.
        """
        method = getattr(type(backend), "get_diagnostics", None)
        detail = dict(method(backend)) if method else {}
        path = getattr(backend, "_device_path", None)
        if path is not None:
            # Match saved HID identities without adding a bytes repr or
            # replacing any byte values in the device path.
            detail["device_id"] = path.decode("latin-1") if isinstance(path, bytes) else str(path)
        else:
            detail.setdefault("device_id", None)
        detail["is_open"] = backend.is_open
        for source, target in (("last_sample_timestamp", "sample_age_seconds"),
                               ("last_packet_timestamp", "packet_age_seconds")):
            stamp = detail.get(source)
            age = now - stamp if isinstance(stamp, (int, float)) else None
            detail[target] = round(age, 3) if age is not None and math.isfinite(age) else None
        stamp = detail.get("last_sample_timestamp")
        packet = detail.get("last_packet_timestamp")
        detail["fresh"] = bool(
            backend.is_open and not detail.get("recovery_blocked")
            and detail.get("calibration_status") != "unavailable"
            and isinstance(stamp, (int, float)) and 0 <= now - stamp <= self.SAMPLE_MAX_AGE_S
        )
        detail["packet_fresh"] = bool(
            backend.is_open and isinstance(packet, (int, float))
            and 0 <= now - packet <= self.SAMPLE_MAX_AGE_S
        )
        detail["sample_max_age_s"] = self.SAMPLE_MAX_AGE_S
        return detail

    def get_diagnostics(self) -> dict:
        """Describe cached readiness and current child observations passively.

        Each child is queried once. HidBackend's packet/write histories are
        already bounded; no reads, writes, retries, or new handles occur here.
        """
        now = time.monotonic()
        sides = {}
        for name, backend, reading in (
            ("left", self._left, self._left_reading),
            ("right", self._right, self._right_reading),
        ):
            child = self._child_diagnostics(backend, now)
            invalid = bool(child.get("recovery_blocked"))
            fresh = backend.is_open and not invalid and self._is_fresh(reading, now)
            sides[name] = {
                "device_id": child["device_id"],
                "child_diagnostics": child,
                "is_open": backend.is_open,
                "timestamp": reading.timestamp if reading is not None else None,
                "fresh": fresh,
                "error": ("disconnected" if not backend.is_open else
                          "invalid_sensor_data" if invalid else
                          "waiting_for_sample" if reading is None else
                          "stale_sample" if not fresh else None),
            }
        return {
            "sample_max_age_s": self.SAMPLE_MAX_AGE_S,
            "ready": sides["left"]["fresh"] and sides["right"]["fresh"],
            **sides,
        }
