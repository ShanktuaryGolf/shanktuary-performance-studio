"""Shanktuary Performance Studio - Pressure & Force Plate Hardware Subsystem."""

from .base import (
    BoardBackend,
    BoardOrientation,
    DualPlateReading,
    SensorReading,
    TareOffsets,
    get_board_dimensions,
    remap_for_orientation,
)

try:
    from .dual_wbb_backend import DualWbbBackend
except Exception:
    DualWbbBackend = None

from .connection import AssignmentPhase, BoardAssignmentWizard, connect_board
from .simulator import SimulatorBackend

__all__ = [
    "BoardBackend",
    "BoardOrientation",
    "DualPlateReading",
    "SensorReading",
    "TareOffsets",
    "get_board_dimensions",
    "remap_for_orientation",
    "DualWbbBackend",
    "SimulatorBackend",
    "connect_board",
]
