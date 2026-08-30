"""Rotational torque estimation from diagonal loading asymmetry."""

from dataclasses import dataclass
from math import sqrt

from src.hardware.pressure.base import BOARD_LENGTH, BOARD_WIDTH

from .cop import CoPSample
from .filters import LowPassFilter

# Effective lever arm: half-diagonal of the sensor rectangle in metres
_EFF_ARM = sqrt((BOARD_WIDTH / 2) ** 2 + (BOARD_LENGTH / 2) ** 2) / 1000.0


@dataclass
class TorqueSample:
    """Instantaneous rotational torque estimate."""

    torque_nm: float  # N·m, positive = clockwise from above (backswing)
    timestamp: float


class TorqueCalculator:
    """Estimates rotational torque from diagonal loading asymmetry.

    The diagonal difference ``(TR + BL) - (TL + BR)`` is a well-established
    proxy for free moment (Mz) on a force plate with four vertical load cells.

    Positive torque = clockwise viewed from above (backswing for a right-hander).
    Negative torque = counter-clockwise (downswing / follow-through).

    Applies a low-pass filter to reduce noise.
    """

    def __init__(self, alpha: float = 0.3,
                 board_width: float = BOARD_WIDTH,
                 board_length: float = BOARD_LENGTH) -> None:
        self._filter = LowPassFilter(alpha=alpha)
        self._eff_arm = sqrt(
            (board_width / 2) ** 2 + (board_length / 2) ** 2
        ) / 1000.0

    def update(self, sample: CoPSample) -> TorqueSample:
        """Compute torque for this sample.  Always returns a result."""
        raw = sample.raw
        # Sensor values are in kg; multiply by 9.81 to get Newtons
        f_tl, f_tr, f_bl, f_br = [
            v * 9.81
            for v in (raw.top_left, raw.top_right, raw.bottom_left, raw.bottom_right)
        ]
        diag_diff_n = (f_tr + f_bl) - (f_tl + f_br)
        raw_torque = diag_diff_n * self._eff_arm / 2.0
        smoothed = self._filter.update(raw_torque)
        return TorqueSample(torque_nm=smoothed, timestamp=sample.timestamp)

    def reset(self) -> None:
        self._filter.reset()
