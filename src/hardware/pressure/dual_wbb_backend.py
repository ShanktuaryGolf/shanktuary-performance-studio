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
        if not self._left.is_open:
            self._left.open()
        if not self._right.is_open:
            self._right.open()

    def close(self) -> None:
        self._left.close()
        self._right.close()

    def shutdown(self) -> None:
        """Power off both boards."""
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
        # Drain both boards, keeping latest reading from each
        lr = self._left.read()
        while lr is not None:
            self._left_reading = lr
            lr = self._left.read()

        rr = self._right.read()
        while rr is not None:
            self._right_reading = rr
            rr = self._right.read()

        if self._left_reading is None or self._right_reading is None:
            return None

        left = self._left_reading
        right = self._right_reading

        now = time.monotonic()

        self._last_dual = DualPlateReading(
            left=left,
            right=right,
            timestamp=now,
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
            timestamp=now,
        )

    @property
    def last_dual_reading(self) -> DualPlateReading | None:
        return self._last_dual
