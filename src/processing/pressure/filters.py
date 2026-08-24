"""Signal filters for smoothing balance board data."""

import math


class ButterworthLowPass:
    """Second-order Butterworth low-pass filter (IIR).

    Implements a biquad filter designed from the bilinear transform of a
    continuous 2nd-order Butterworth prototype. This gives a flat passband
    with -12 dB/octave rolloff — much cleaner than a first-order IIR.

    Based on Cleland et al. 2023 recommendation of 18 Hz cutoff for
    force plate data, and Pezeshk et al. 2016 (50 Hz for kinetics).

    Args:
        cutoff_hz: Filter cutoff frequency in Hz.
        sample_rate_hz: Expected input sample rate in Hz.
    """

    def __init__(self, cutoff_hz: float = 18.0, sample_rate_hz: float = 60.0) -> None:
        self._cutoff = cutoff_hz
        self._fs = sample_rate_hz
        self._x1 = 0.0
        self._x2 = 0.0
        self._y1 = 0.0
        self._y2 = 0.0
        self._initialized = False
        self._compute_coefficients()

    def _compute_coefficients(self) -> None:
        """Compute biquad coefficients via bilinear transform."""
        w0 = 2.0 * math.pi * self._cutoff / self._fs
        # Pre-warp for bilinear transform
        w_warp = math.tan(w0 / 2.0)
        w2 = w_warp * w_warp
        sqrt2 = math.sqrt(2.0)
        norm = 1.0 / (1.0 + sqrt2 * w_warp + w2)

        self._b0 = w2 * norm
        self._b1 = 2.0 * self._b0
        self._b2 = self._b0
        self._a1 = 2.0 * (w2 - 1.0) * norm
        self._a2 = (1.0 - sqrt2 * w_warp + w2) * norm

    def update(self, x: float) -> float:
        if not self._initialized:
            # Seed the filter with the first sample to avoid startup transient
            self._x1 = self._x2 = x
            self._y1 = self._y2 = x
            self._initialized = True
            return x

        y = (self._b0 * x + self._b1 * self._x1 + self._b2 * self._x2
             - self._a1 * self._y1 - self._a2 * self._y2)

        self._x2 = self._x1
        self._x1 = x
        self._y2 = self._y1
        self._y1 = y
        return y

    def reset(self) -> None:
        self._x1 = self._x2 = 0.0
        self._y1 = self._y2 = 0.0
        self._initialized = False

    @property
    def value(self) -> float | None:
        return self._y1 if self._initialized else None


class LowPassFilter:
    """Simple first-order IIR low-pass filter.

    y[n] = alpha * x[n] + (1 - alpha) * y[n-1]

    Higher alpha = less smoothing (more responsive).
    For 100 Hz input, alpha ~0.1 gives ~1.6 Hz cutoff.
    """

    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha
        self._value: float | None = None

    def update(self, x: float) -> float:
        if self._value is None:
            self._value = x
        else:
            self._value = self.alpha * x + (1.0 - self.alpha) * self._value
        return self._value

    def reset(self) -> None:
        self._value = None

    @property
    def value(self) -> float | None:
        return self._value


class MovingAverage:
    """Simple moving average over a fixed window."""

    def __init__(self, window: int = 10) -> None:
        self._window = window
        self._buf: list[float] = []

    def update(self, x: float) -> float:
        self._buf.append(x)
        if len(self._buf) > self._window:
            self._buf.pop(0)
        return sum(self._buf) / len(self._buf)

    def reset(self) -> None:
        self._buf.clear()
