"""Balance point (CoP) velocity calculation via finite difference."""

from dataclasses import dataclass

from .cop import CoPSample
from .filters import LowPassFilter


@dataclass
class CoPVelocity:
    """Instantaneous CoP velocity."""
    dx_dt: float   # mm/s, positive = moving right
    dy_dt: float   # mm/s, positive = moving forward
    speed: float   # mm/s, magnitude
    timestamp: float


class VelocityCalculator:
    """Computes CoP velocity from successive CoPSamples using finite difference.

    Applies a low-pass filter to the speed output to reduce noise.
    Resets when the time gap between samples exceeds 0.1 s (data discontinuity).
    """

    MAX_DT = 0.1  # seconds — gap larger than this triggers reset

    def __init__(self, alpha: float = 0.3) -> None:
        self._prev: CoPSample | None = None
        self._speed_filter = LowPassFilter(alpha=alpha)

    def update(self, sample: CoPSample) -> CoPVelocity | None:
        """Return velocity for this sample, or None if not enough data yet."""
        prev = self._prev
        self._prev = sample

        if prev is None:
            return None

        dt = sample.timestamp - prev.timestamp
        if dt <= 0 or dt > self.MAX_DT:
            # Discontinuity — reset filter and wait for next pair
            self._speed_filter.reset()
            return None

        dx_dt = (sample.cop_x - prev.cop_x) / dt
        dy_dt = (sample.cop_y - prev.cop_y) / dt
        raw_speed = (dx_dt ** 2 + dy_dt ** 2) ** 0.5
        smoothed = self._speed_filter.update(raw_speed)

        return CoPVelocity(
            dx_dt=dx_dt,
            dy_dt=dy_dt,
            speed=smoothed,
            timestamp=sample.timestamp,
        )

    def reset(self) -> None:
        self._prev = None
        self._speed_filter.reset()
