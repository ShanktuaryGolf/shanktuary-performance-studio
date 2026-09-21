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
from .windows_pairing import is_available as native_pairing_available
from .windows_pairing import list_paired_boards, pair_balance_board

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
    "native_pairing_available",
    "list_paired_boards",
    "pair_balance_board",
]
