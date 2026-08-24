"""Compression strength and angle tracking during golf swings."""

import math
from dataclasses import dataclass
from enum import Enum

from .cop import CoPSample
from .filters import LowPassFilter, MovingAverage
from .swing import SwingPhase
from .velocity import CoPVelocity


@dataclass
class CompressionResult:
    """Result of compression analysis for a single swing."""
    peak_force_ratio: float   # e.g. 1.3 means 130% of bodyweight
    angle_deg: float          # degrees, 0° = right/target, 90° = forward
    timestamp: float


class _State(Enum):
    IDLE = "idle"
    CALIBRATING = "calibrating"
    TRACKING = "tracking"
    DONE = "done"


class CompressionCalculator:
    """Tracks compression strength and force angle during golf swings.

    - During ADDRESS: accumulates total_kg to establish baseline bodyweight.
    - During DOWNSWING/IMPACT: tracks peak total_kg and captures CoP velocity
      angle at the moment of peak force.
    - On FOLLOW_THROUGH entry: finalizes a CompressionResult.
    """

    # Minimum samples during ADDRESS before baseline is considered valid
    MIN_BASELINE_SAMPLES = 10

    def __init__(self, filter_alpha: float = 0.15) -> None:
        self._state = _State.IDLE
        self._baseline_avg = MovingAverage(window=50)
        self._force_filter = LowPassFilter(alpha=filter_alpha)
        self._baseline_kg: float = 0.0
        self._baseline_count: int = 0
        self._peak_kg: float = 0.0
        self._peak_velocity: CoPVelocity | None = None
        self._peak_timestamp: float = 0.0
        self._result: CompressionResult | None = None

    def reset(self) -> None:
        """Clear all state for next swing."""
        self._state = _State.IDLE
        self._baseline_avg.reset()
        self._force_filter.reset()
        self._baseline_kg = 0.0
        self._baseline_count = 0
        self._peak_kg = 0.0
        self._peak_velocity = None
        self._peak_timestamp = 0.0
        self._result = None

    def update(
        self,
        sample: CoPSample,
        phase: SwingPhase,
        velocity: CoPVelocity | None,
    ) -> CompressionResult | None:
        """Process one sample. Returns a CompressionResult when a swing completes."""
        if self._state == _State.IDLE:
            if phase == SwingPhase.ADDRESS:
                self._state = _State.CALIBRATING
                self._baseline_avg.reset()
                self._force_filter.reset()
                self._baseline_count = 0
                # fall through to calibrating

            else:
                return None

        if self._state == _State.CALIBRATING:
            if phase == SwingPhase.ADDRESS:
                self._baseline_kg = self._baseline_avg.update(sample.total_kg)
                self._baseline_count += 1
                return None

            if phase in (SwingPhase.BACKSWING, SwingPhase.TRANSITION,
                         SwingPhase.DOWNSWING, SwingPhase.IMPACT):
                if self._baseline_count < self.MIN_BASELINE_SAMPLES:
                    # Not enough baseline data — skip this swing
                    self._state = _State.IDLE
                    return None
                self._state = _State.TRACKING
                self._peak_kg = 0.0
                self._peak_velocity = None
                self._force_filter.reset()
                # fall through to tracking

            else:
                # Unexpected phase — reset
                self._state = _State.IDLE
                return None

        if self._state == _State.TRACKING:
            if phase in (SwingPhase.BACKSWING, SwingPhase.TRANSITION,
                         SwingPhase.DOWNSWING, SwingPhase.IMPACT):
                filtered_kg = self._force_filter.update(sample.total_kg)
                if filtered_kg > self._peak_kg:
                    self._peak_kg = filtered_kg
                    self._peak_velocity = velocity
                    self._peak_timestamp = sample.timestamp
                return None

            if phase == SwingPhase.FOLLOW_THROUGH:
                # Finalize result
                if self._baseline_kg > 0 and self._peak_kg > 0:
                    ratio = self._peak_kg / self._baseline_kg
                    angle = self._compute_angle(self._peak_velocity)
                    self._result = CompressionResult(
                        peak_force_ratio=ratio,
                        angle_deg=angle,
                        timestamp=self._peak_timestamp,
                    )
                    self._state = _State.DONE
                    return self._result
                else:
                    self._state = _State.IDLE
                    return None

            # Phase went back to ADDRESS or IDLE unexpectedly
            self._state = _State.IDLE
            return None

        if self._state == _State.DONE:
            if phase == SwingPhase.ADDRESS:
                # New swing starting — reset for next cycle
                self._state = _State.CALIBRATING
                self._baseline_avg.reset()
                self._force_filter.reset()
                self._baseline_count = 0
                self._peak_kg = 0.0
                self._peak_velocity = None
                self._result = None
                self._baseline_kg = self._baseline_avg.update(sample.total_kg)
                self._baseline_count = 1
            return None

        return None

    @staticmethod
    def _compute_angle(velocity: CoPVelocity | None) -> float:
        """Compute angle in degrees from CoP velocity. 0° = right, 90° = forward."""
        if velocity is None:
            return 0.0
        return math.degrees(math.atan2(velocity.dy_dt, velocity.dx_dt))

    @property
    def result(self) -> CompressionResult | None:
        return self._result
