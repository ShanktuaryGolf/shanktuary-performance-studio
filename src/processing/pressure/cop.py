"""Center of Pressure calculation from Wii Balance Board sensor data."""

import math
from dataclasses import dataclass, field

from src.hardware.pressure.base import SensorReading, BOARD_WIDTH, BOARD_LENGTH


@dataclass
class CoPSample:
    """Computed Center of Pressure plus weight distribution."""
    cop_x: float          # mm, positive = right
    cop_y: float          # mm, positive = front/toes
    total_kg: float       # approximate kg
    pct_left: float       # 0-100
    pct_right: float      # 0-100
    pct_front: float      # 0-100
    pct_back: float       # 0-100
    timestamp: float
    raw: SensorReading
    # Per-foot pressure estimation (left = TL+BL, right = TR+BR)
    left_kg: float = 0.0
    right_kg: float = 0.0
    left_pct_front: float = 0.0   # % of left foot's weight on front sensor
    left_pct_back: float = 0.0
    right_pct_front: float = 0.0  # % of right foot's weight on front sensor
    right_pct_back: float = 0.0
    # Body-weight normalized force (requires calibrated bodyweight)
    force_bw: float = 0.0         # total force as fraction of bodyweight (1.0 = 1 BW)


class BodyWeightNormalizer:
    """Establishes bodyweight baseline and normalizes forces to %BW.

    Based on Castro et al. 2015 and Amick et al. 2023 — forces should be
    expressed relative to body weight for meaningful comparison across golfers.

    Call ``calibrate()`` to set BW from a quiet standing period, then
    ``normalize()`` on each sample to get force as a fraction of BW.
    """

    QUIET_STANDING_SAMPLES = 60  # ~1 second at 60 Hz

    def __init__(self) -> None:
        self._samples: list[float] = []
        self._bodyweight_kg: float = 0.0
        self._calibrated = False

    @property
    def bodyweight_kg(self) -> float:
        return self._bodyweight_kg

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def feed(self, total_kg: float) -> None:
        """Feed a quiet-standing sample to build the baseline."""
        if self._calibrated:
            return
        self._samples.append(total_kg)
        if len(self._samples) >= self.QUIET_STANDING_SAMPLES:
            self._bodyweight_kg = sum(self._samples) / len(self._samples)
            self._calibrated = True

    def calibrate(self, bodyweight_kg: float) -> None:
        """Manually set bodyweight (e.g. from user input or scale)."""
        self._bodyweight_kg = bodyweight_kg
        self._calibrated = True

    def normalize(self, total_kg: float) -> float:
        """Return force as fraction of bodyweight (1.0 = 1 BW)."""
        if not self._calibrated or self._bodyweight_kg <= 0:
            return 0.0
        return total_kg / self._bodyweight_kg

    def reset(self) -> None:
        self._samples.clear()
        self._bodyweight_kg = 0.0
        self._calibrated = False


class CoPStabilityMetric:
    """Computes RMS sway and path length from CoP samples.

    Based on Amick et al. 2023 — RMS of CoP displacement is the standard
    metric for postural stability on a force plate. Lower RMS = more stable.

    Path length (total distance traveled by CoP) captures how much
    corrective movement the golfer makes during stance.
    """

    def __init__(self, window: int = 900) -> None:
        """window: number of samples to accumulate (900 = 15s at 60Hz,
        per Amick et al. recommendation of middle 15s of a 30s trial)."""
        self._window = window
        self._x_buf: list[float] = []
        self._y_buf: list[float] = []
        self._path_length: float = 0.0

    def update(self, cop_x: float, cop_y: float) -> None:
        if self._x_buf:
            dx = cop_x - self._x_buf[-1]
            dy = cop_y - self._y_buf[-1]
            self._path_length += math.sqrt(dx * dx + dy * dy)

        self._x_buf.append(cop_x)
        self._y_buf.append(cop_y)

        if len(self._x_buf) > self._window:
            self._x_buf.pop(0)
            self._y_buf.pop(0)

    @property
    def rms_sway_mm(self) -> float:
        """RMS displacement from mean CoP position, in mm."""
        n = len(self._x_buf)
        if n < 2:
            return 0.0
        mean_x = sum(self._x_buf) / n
        mean_y = sum(self._y_buf) / n
        ss = sum((x - mean_x) ** 2 + (y - mean_y) ** 2
                 for x, y in zip(self._x_buf, self._y_buf))
        return math.sqrt(ss / n)

    @property
    def path_length_mm(self) -> float:
        """Total CoP path length in mm over the window."""
        return self._path_length

    @property
    def sample_count(self) -> int:
        return len(self._x_buf)

    def reset(self) -> None:
        self._x_buf.clear()
        self._y_buf.clear()
        self._path_length = 0.0


class CoPCalculator:
    """Computes CoP and weight distribution from raw sensor readings.

    Noise gate: readings below ``noise_floor_kg`` are zeroed out per-sensor
    before CoP computation. Based on Cleland et al. 2023 recommendation
    of a 5% body-mass threshold to exclude sensor noise.

    The default per-sensor noise floor (0.3 kg) filters residual drift after
    taring that would otherwise produce phantom 15-20% pressure readings on
    one side of the board (see SHA-36).
    """

    DEFAULT_NOISE_FLOOR = 0.3  # kg per sensor — filters post-tare drift
    MIN_TOTAL = 2.0  # minimum total load in kg to compute valid CoP

    def __init__(self, noise_floor_kg: float | None = None,
                 board_width: float = BOARD_WIDTH,
                 board_length: float = BOARD_LENGTH) -> None:
        self._noise_floor = noise_floor_kg if noise_floor_kg is not None else self.DEFAULT_NOISE_FLOOR
        self._board_width = board_width
        self._board_length = board_length

    @property
    def noise_floor_kg(self) -> float:
        return self._noise_floor

    @noise_floor_kg.setter
    def noise_floor_kg(self, value: float) -> None:
        self._noise_floor = max(0.0, value)

    def set_noise_floor_from_bodyweight(self, bodyweight_kg: float) -> None:
        """Set noise floor to 5% of body weight (Cleland et al. 2023)."""
        self._noise_floor = bodyweight_kg * 0.05

    def compute(self, reading: SensorReading) -> CoPSample | None:
        """Compute CoP from a sensor reading. Returns None if total load is too low."""
        nf = self._noise_floor
        tl = reading.top_left if reading.top_left >= nf else 0.0
        tr = reading.top_right if reading.top_right >= nf else 0.0
        bl = reading.bottom_left if reading.bottom_left >= nf else 0.0
        br = reading.bottom_right if reading.bottom_right >= nf else 0.0
        total = tl + tr + bl + br

        if total < self.MIN_TOTAL:
            return None

        # CoP in mm relative to board center
        cop_x = (self._board_width / 2) * ((tr + br) - (tl + bl)) / total
        cop_y = (self._board_length / 2) * ((tl + tr) - (bl + br)) / total

        # Weight distribution percentages
        left = tl + bl
        right = tr + br
        front = tl + tr
        back = bl + br

        # Per-foot front/back balance (guard against division by zero)
        if left > 0:
            left_pct_front = 100.0 * tl / left
            left_pct_back = 100.0 * bl / left
        else:
            left_pct_front = 0.0
            left_pct_back = 0.0

        if right > 0:
            right_pct_front = 100.0 * tr / right
            right_pct_back = 100.0 * br / right
        else:
            right_pct_front = 0.0
            right_pct_back = 0.0

        return CoPSample(
            cop_x=cop_x,
            cop_y=cop_y,
            total_kg=total,
            pct_left=100.0 * left / total,
            pct_right=100.0 * right / total,
            pct_front=100.0 * front / total,
            pct_back=100.0 * back / total,
            timestamp=reading.timestamp,
            raw=reading,
            left_kg=left,
            right_kg=right,
            left_pct_front=left_pct_front,
            left_pct_back=left_pct_back,
            right_pct_front=right_pct_front,
            right_pct_back=right_pct_back,
        )
