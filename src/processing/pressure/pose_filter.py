"""Butterworth filtering for pose trajectory data with auto cutoff selection.

Applies per-channel second-order Butterworth low-pass filters to computed
golf pose angles. Different body regions get different cutoff frequencies
based on their expected motion bandwidth:

- **Trunk channels** (hip/shoulder rotation, spine, torso/pelvis bends):
  slower-moving, default ~6 Hz cutoff.
- **Limb channels** (elbow and wrist angles): faster-moving, default ~12 Hz.

The auto-cutoff logic scales these defaults by the ratio of measured sample
rate to a reference rate (30 fps), clamped to a sensible range. This means
the filter adapts automatically when cameras run at different frame rates.

Reference: Winter, D.A. (2009). *Biomechanics and Motor Control of Human
Movement*, 4th ed. — recommends 6 Hz for gait kinematics; golf swing limb
segments are faster, hence the 12 Hz default for extremities.
"""

from __future__ import annotations

from .filters import ButterworthLowPass

# Reference sample rate used to derive default cutoffs
_REF_SAMPLE_RATE = 30.0

# Default cutoffs (Hz) at the reference sample rate
_TRUNK_CUTOFF_HZ = 6.0
_LIMB_CUTOFF_HZ = 12.0

# Absolute bounds so auto-scaling doesn't produce nonsensical values
_MIN_CUTOFF_HZ = 3.0
_MAX_CUTOFF_HZ = 20.0

# Channel names grouped by motion bandwidth
TRUNK_CHANNELS = frozenset({
    "hip_rotation_deg",
    "shoulder_rotation_deg",
    "x_factor_deg",
    "spine_angle_deg",
    "torso_forward_bend_deg",
    "torso_side_bend_deg",
    "pelvis_forward_bend_deg",
    "pelvis_side_bend_deg",
    "com_sway_mm",
    "hip_hinge_deg",
    "spine_angle_vs_vertical_deg",
})

LIMB_CHANNELS = frozenset({
    "left_elbow_angle_deg",
    "right_elbow_angle_deg",
    "left_wrist_angle_deg",
    "right_wrist_angle_deg",
    "left_knee_flex_deg",
    "right_knee_flex_deg",
    "left_arm_torso_angle_deg",
    "right_arm_torso_angle_deg",
})

ALL_CHANNELS = TRUNK_CHANNELS | LIMB_CHANNELS


def auto_cutoff(channel: str, sample_rate_hz: float) -> float:
    """Compute a cutoff frequency for *channel* at the given sample rate.

    Scales the default cutoff linearly with the ratio of actual sample rate
    to the reference rate, then clamps to [_MIN_CUTOFF_HZ, _MAX_CUTOFF_HZ].
    The cutoff is also clamped below Nyquist (sample_rate / 2).
    """
    base = _LIMB_CUTOFF_HZ if channel in LIMB_CHANNELS else _TRUNK_CUTOFF_HZ
    scaled = base * (sample_rate_hz / _REF_SAMPLE_RATE)
    nyquist = sample_rate_hz / 2.0
    return min(max(scaled, _MIN_CUTOFF_HZ), _MAX_CUTOFF_HZ, nyquist * 0.9)


class PoseTrajectoryFilter:
    """Per-channel Butterworth filtering for pose angle trajectories.

    Lazily creates a :class:`ButterworthLowPass` for each channel on first
    use, with auto-selected cutoff based on channel type and sample rate.

    Args:
        sample_rate_hz: Expected input frame rate (used for auto cutoff).
            Defaults to 30 fps.
        cutoff_overrides: Optional dict mapping channel names to explicit
            cutoff frequencies, bypassing auto selection for those channels.
        enabled: If False, ``filter()`` is a pass-through (returns input
            values unchanged). Lets callers toggle filtering without
            removing the filter from the pipeline.
    """

    def __init__(
        self,
        sample_rate_hz: float = 30.0,
        cutoff_overrides: dict[str, float] | None = None,
        enabled: bool = True,
    ) -> None:
        self._fs = sample_rate_hz
        self._overrides = cutoff_overrides or {}
        self._filters: dict[str, ButterworthLowPass] = {}
        self.enabled = enabled

    def _get_filter(self, channel: str) -> ButterworthLowPass:
        """Return (or lazily create) the filter for *channel*."""
        filt = self._filters.get(channel)
        if filt is None:
            fc = self._overrides.get(channel, auto_cutoff(channel, self._fs))
            filt = ButterworthLowPass(cutoff_hz=fc, sample_rate_hz=self._fs)
            self._filters[channel] = filt
        return filt

    def filter_value(self, channel: str, value: float) -> float:
        """Filter a single channel value. Returns filtered (or raw if disabled)."""
        if not self.enabled:
            return value
        return self._get_filter(channel).update(value)

    def filter(self, values: dict[str, float | None]) -> dict[str, float | None]:
        """Filter a dict of ``{channel: value}`` in one call.

        None values are passed through unchanged (the channel's filter state
        is not updated for None — this handles missing limb detections).
        """
        out: dict[str, float | None] = {}
        for ch, val in values.items():
            if val is None or not self.enabled:
                out[ch] = val
            else:
                out[ch] = self._get_filter(ch).update(val)
        return out

    def reset(self) -> None:
        """Reset all channel filters (e.g. on recording restart)."""
        for filt in self._filters.values():
            filt.reset()
        self._filters.clear()

    @property
    def sample_rate_hz(self) -> float:
        return self._fs

    @sample_rate_hz.setter
    def sample_rate_hz(self, value: float) -> None:
        """Update sample rate and rebuild filters with new cutoffs."""
        if value != self._fs:
            self._fs = value
            self._filters.clear()
