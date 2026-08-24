"""Stance width calibration via weight-shift detection."""

from enum import Enum, auto

from .cop import CoPSample


class CalibrationState(Enum):
    IDLE = auto()
    WAITING_LEFT = auto()
    WAITING_RIGHT = auto()
    DONE = auto()


_INSTRUCTIONS = {
    CalibrationState.IDLE: "",
    CalibrationState.WAITING_LEFT: "Shift weight to LEFT foot (>85%)",
    CalibrationState.WAITING_RIGHT: "Shift weight to RIGHT foot (>85%)",
    CalibrationState.DONE: "Calibration complete!",
}


class StanceCalibrator:
    """Determines stance width by having the user shift weight left then right.

    The user must hold >85% weight on one side for 1 second for each foot.
    The stance width is the horizontal distance between the two CoP positions.
    """

    WEIGHT_THRESHOLD = 85.0  # pct on one side to register
    HOLD_DURATION = 1.0      # seconds the user must hold

    def __init__(self) -> None:
        self._state = CalibrationState.IDLE
        self._hold_start: float = 0.0
        self._hold_samples: list[float] = []  # cop_x values during hold
        self._left_cop_x: float = 0.0
        self._right_cop_x: float = 0.0
        self._stance_width: float | None = None

    @property
    def state(self) -> CalibrationState:
        return self._state

    @property
    def instruction(self) -> str:
        return _INSTRUCTIONS[self._state]

    @property
    def stance_width_mm(self) -> float | None:
        return self._stance_width

    def start(self) -> None:
        """Begin the calibration sequence."""
        self._state = CalibrationState.WAITING_LEFT
        self._hold_start = 0.0
        self._hold_samples.clear()
        self._stance_width = None

    def update(self, sample: CoPSample) -> None:
        """Feed a new sample into the calibration state machine."""
        if self._state == CalibrationState.WAITING_LEFT:
            self._check_hold(sample, sample.pct_left, is_left=True)
        elif self._state == CalibrationState.WAITING_RIGHT:
            self._check_hold(sample, sample.pct_right, is_left=False)

    def _check_hold(self, sample: CoPSample, pct: float, *, is_left: bool) -> None:
        if pct >= self.WEIGHT_THRESHOLD:
            if not self._hold_samples:
                self._hold_start = sample.timestamp
            self._hold_samples.append(sample.cop_x)

            elapsed = sample.timestamp - self._hold_start
            if elapsed >= self.HOLD_DURATION:
                mean_x = sum(self._hold_samples) / len(self._hold_samples)
                if is_left:
                    self._left_cop_x = mean_x
                    self._state = CalibrationState.WAITING_RIGHT
                    self._hold_samples.clear()
                else:
                    self._right_cop_x = mean_x
                    self._stance_width = abs(self._right_cop_x - self._left_cop_x)
                    self._state = CalibrationState.DONE
                    self._hold_samples.clear()
        else:
            # Weight dropped below threshold — restart hold timer
            self._hold_samples.clear()

    def reset(self) -> None:
        self._state = CalibrationState.IDLE
        self._hold_start = 0.0
        self._hold_samples.clear()
        self._left_cop_x = 0.0
        self._right_cop_x = 0.0
        self._stance_width = None
