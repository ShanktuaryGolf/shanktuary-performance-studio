"""Dual Wii Balance Board backend -- two WBBs as left/right foot plates."""

import time

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
        self._left.close()
        self._right.close()

    def shutdown(self) -> None:
        """Power off both boards."""
        self._clear_readings()
        self._left.shutdown()
        self._right.shutdown()

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
            self._clear_readings()
            return None
        lr = self._left.read()
        rr = self._right.read()
        # A child can detect a disconnection during read(). Discard even a
        # final queued sample rather than presenting a disconnected pair.
        if (not self.is_open or self._invalid_sensor_data(self._left)
                or self._invalid_sensor_data(self._right)):
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

    def get_diagnostics(self) -> dict:
        """Describe availability without refreshing or consuming samples."""
        now = time.monotonic()
        sides = {}
        for name, backend, reading in (
            ("left", self._left, self._left_reading),
            ("right", self._right, self._right_reading),
        ):
            invalid = self._invalid_sensor_data(backend)
            fresh = backend.is_open and not invalid and self._is_fresh(reading, now)
            sides[name] = {
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
