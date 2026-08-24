"""Synthetic golf swing data generator for UI development without a physical board."""

import math
import time

from .base import BoardBackend, SensorReading


class SimulatorBackend(BoardBackend):
    """Generates synthetic golf swing data at ~100 Hz.

    Models a right-handed golfer's weight shift:
    - Address: balanced, slight front bias
    - Backswing: weight shifts right + back
    - Transition: quick shift left
    - Downswing: weight moves left + front
    - Impact: max left/front
    - Follow-through: settles left/front
    Then loops.
    """

    SWING_PERIOD = 3.0  # seconds for a full swing cycle
    BASE_LOAD = 20.0  # base load per sensor in kg (~80 kg total / 4)

    def __init__(self) -> None:
        self._running = False
        self._start_time = 0.0
        self._last_emit = 0.0
        self._interval = 1.0 / 100.0  # 100 Hz

    def open(self) -> None:
        self._running = True
        self._start_time = time.monotonic()
        self._last_emit = 0.0

    def close(self) -> None:
        self._running = False

    @property
    def is_open(self) -> bool:
        return self._running

    def read(self) -> SensorReading | None:
        if not self._running:
            return None

        now = time.monotonic()
        if now - self._last_emit < self._interval:
            return None
        self._last_emit = now

        t = (now - self._start_time) % self.SWING_PERIOD
        phase = t / self.SWING_PERIOD  # 0..1

        # Weight shift pattern (left-right): negative=left, positive=right
        # Backswing peaks right at phase ~0.3, impact peaks left at ~0.6
        lr_shift = 0.35 * math.sin(2 * math.pi * (phase - 0.05))

        # Front-back shift: slight front at address, back during backswing, front at impact
        fb_shift = 0.15 * math.sin(2 * math.pi * (phase + 0.1)) + 0.05

        # Add subtle noise
        noise_t = now * 17.0
        noise = 0.02 * math.sin(noise_t) + 0.01 * math.sin(noise_t * 2.7)

        base = self.BASE_LOAD

        # Distribute load: positive lr_shift = more right, positive fb_shift = more front
        right_factor = 1.0 + lr_shift + noise
        left_factor = 1.0 - lr_shift - noise
        front_factor = 1.0 + fb_shift
        back_factor = 1.0 - fb_shift

        tl = base * left_factor * front_factor
        tr = base * right_factor * front_factor
        bl = base * left_factor * back_factor
        br = base * right_factor * back_factor

        return SensorReading(
            top_left=max(0, tl),
            top_right=max(0, tr),
            bottom_left=max(0, bl),
            bottom_right=max(0, br),
            timestamp=now,
        )
