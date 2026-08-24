"""Threshold-based state machine for golf swing phase detection."""

from enum import Enum

from .cop import CoPSample
from .filters import LowPassFilter


class SwingPhase(Enum):
    IDLE = "Idle"
    ADDRESS = "Address"
    BACKSWING = "Backswing"
    TRANSITION = "Transition"
    DOWNSWING = "Downswing"
    IMPACT = "Impact"
    FOLLOW_THROUGH = "Follow-through"


class SwingDetector:
    """Detects golf swing phases from CoP data.

    Uses filtered left-right weight shift (pct_right) to identify phases.
    Right-handed golfer model:
    - Address: balanced (~50% L/R), stable
    - Backswing: weight shifts right (pct_right > 55)
    - Transition: pct_right peaks then reverses
    - Downswing: rapid shift left (pct_right dropping fast)
    - Impact: pct_right minimum (~35-40%)
    - Follow-through: settles left
    """

    # Thresholds (pct_right)
    ADDRESS_ENTER_KG = 30.0       # minimum weight to detect someone standing
    BACKSWING_THRESHOLD = 56.0    # pct_right above this = backswing
    TRANSITION_THRESHOLD = 52.0   # pct_right drops below this after backswing peak
    IMPACT_THRESHOLD = 42.0       # pct_right below this = impact zone
    FOLLOWTHROUGH_SETTLE = 3.0    # rate of change near zero = settled

    # Minimum time in each phase (seconds) to avoid noise transitions
    MIN_PHASE_DURATION = 0.1
    # Sustained time pct_right must stay above BACKSWING_THRESHOLD to exit ADDRESS
    ADDRESS_SUSTAIN = 0.15

    def __init__(self) -> None:
        self._phase = SwingPhase.IDLE
        self._filter_lr = LowPassFilter(alpha=0.10)
        self._phase_enter_time = 0.0
        self._prev_pct_right = 50.0
        self._peak_right = 0.0
        self._above_threshold_since: float | None = None

    def reset(self) -> None:
        self._phase = SwingPhase.IDLE
        self._filter_lr.reset()
        self._phase_enter_time = 0.0
        self._prev_pct_right = 50.0
        self._peak_right = 0.0
        self._above_threshold_since = None

    def update(self, sample: CoPSample) -> SwingPhase:
        pct_r = self._filter_lr.update(sample.pct_right)
        t = sample.timestamp
        dt = t - self._phase_enter_time

        if self._phase == SwingPhase.IDLE:
            if sample.total_kg > self.ADDRESS_ENTER_KG:
                self._enter(SwingPhase.ADDRESS, t)

        elif self._phase == SwingPhase.ADDRESS:
            if sample.total_kg < self.ADDRESS_ENTER_KG:
                self._enter(SwingPhase.IDLE, t)
                self._above_threshold_since = None
            elif pct_r > self.BACKSWING_THRESHOLD:
                if self._above_threshold_since is None:
                    self._above_threshold_since = t
                elif t - self._above_threshold_since >= self.ADDRESS_SUSTAIN:
                    self._peak_right = pct_r
                    self._above_threshold_since = None
                    self._enter(SwingPhase.BACKSWING, t)
            else:
                self._above_threshold_since = None

        elif self._phase == SwingPhase.BACKSWING:
            self._peak_right = max(self._peak_right, pct_r)
            if pct_r < self.TRANSITION_THRESHOLD and dt > self.MIN_PHASE_DURATION:
                self._enter(SwingPhase.TRANSITION, t)

        elif self._phase == SwingPhase.TRANSITION:
            if pct_r < 50.0 and dt > self.MIN_PHASE_DURATION:
                self._enter(SwingPhase.DOWNSWING, t)

        elif self._phase == SwingPhase.DOWNSWING:
            if pct_r < self.IMPACT_THRESHOLD and dt > self.MIN_PHASE_DURATION:
                self._enter(SwingPhase.IMPACT, t)

        elif self._phase == SwingPhase.IMPACT:
            rate = abs(pct_r - self._prev_pct_right)
            if dt > 0.2 and rate < self.FOLLOWTHROUGH_SETTLE:
                self._enter(SwingPhase.FOLLOW_THROUGH, t)

        elif self._phase == SwingPhase.FOLLOW_THROUGH:
            if dt > 1.0:
                self._enter(SwingPhase.ADDRESS, t)

        self._prev_pct_right = pct_r
        return self._phase

    def _enter(self, phase: SwingPhase, t: float) -> None:
        self._phase = phase
        self._phase_enter_time = t

    @property
    def phase(self) -> SwingPhase:
        return self._phase
