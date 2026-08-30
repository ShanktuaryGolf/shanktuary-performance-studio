"""Base types and abstract backend for Wii Balance Board data."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

# Board physical dimensions in mm (landscape orientation)
BOARD_WIDTH = 433.0   # left-right
BOARD_LENGTH = 238.0  # front-back


class BoardOrientation(Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


def get_board_dimensions(
    orientation: BoardOrientation = BoardOrientation.LANDSCAPE,
) -> tuple[float, float]:
    """Return (width_lr, length_fb) in mm for the given orientation."""
    if orientation == BoardOrientation.PORTRAIT:
        return BOARD_LENGTH, BOARD_WIDTH
    return BOARD_WIDTH, BOARD_LENGTH


def remap_for_orientation(
    reading: "SensorReading", orientation: BoardOrientation,
) -> "SensorReading":
    """Remap sensor values for a rotated board. Landscape is identity.

    For 90-degree clockwise rotation (portrait):
      Physical left edge becomes front, right edge becomes back.
    """
    if orientation == BoardOrientation.LANDSCAPE:
        return reading
    return SensorReading(
        top_left=reading.bottom_left,
        top_right=reading.top_left,
        bottom_left=reading.bottom_right,
        bottom_right=reading.top_right,
        timestamp=reading.timestamp,
    )


@dataclass
class SensorReading:
    """Raw reading from the 4 load cells, plus timestamp."""
    top_left: float
    top_right: float
    bottom_left: float
    bottom_right: float
    timestamp: float  # time.monotonic()

    @property
    def total(self) -> float:
        return self.top_left + self.top_right + self.bottom_left + self.bottom_right

    @property
    def total_kg(self) -> float:
        """Total weight in kg (sum of all 4 calibrated sensors)."""
        return self.total

    @property
    def total_weight(self) -> float:
        """Alias for total weight in kg."""
        return self.total


@dataclass
class DualPlateReading:
    """Reading from two separate plates (e.g. Dual Wii Balance Boards)."""
    left: SensorReading
    right: SensorReading
    left_beam_raw: int = 0
    right_beam_raw: int = 0
    timestamp: float = 0.0
    device_timestamp_us: int = 0


@dataclass
class TareOffsets:
    """Per-sensor tare offsets to zero out resting values."""
    top_left: float = 0.0
    top_right: float = 0.0
    bottom_left: float = 0.0
    bottom_right: float = 0.0

    def apply(self, reading: SensorReading) -> SensorReading:
        """Return a new SensorReading with tare offsets subtracted.

        Values are clamped to zero — negative weight is physically impossible
        and unclamped negatives cause asymmetric zeroing that produces phantom
        pressure readings on one side of the board (see SHA-36).
        """
        return SensorReading(
            top_left=max(0.0, reading.top_left - self.top_left),
            top_right=max(0.0, reading.top_right - self.top_right),
            bottom_left=max(0.0, reading.bottom_left - self.bottom_left),
            bottom_right=max(0.0, reading.bottom_right - self.bottom_right),
            timestamp=reading.timestamp,
        )

    @classmethod
    def from_readings(cls, readings: list[SensorReading]) -> "TareOffsets":
        """Average multiple readings to compute stable tare offsets."""
        n = len(readings)
        if n == 0:
            return cls()
        return cls(
            top_left=sum(r.top_left for r in readings) / n,
            top_right=sum(r.top_right for r in readings) / n,
            bottom_left=sum(r.bottom_left for r in readings) / n,
            bottom_right=sum(r.bottom_right for r in readings) / n,
        )


class BoardBackend(ABC):
    """Abstract interface for balance board data sources."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @abstractmethod
    def open(self) -> None:
        """Initialize the connection / data source."""

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""

    def shutdown(self) -> None:
        """Power off the board hardware. Default: just close."""
        self.close()

    @abstractmethod
    def read(self) -> SensorReading | None:
        """Non-blocking read. Returns a SensorReading if new data is available, else None."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Whether the backend is currently active."""
