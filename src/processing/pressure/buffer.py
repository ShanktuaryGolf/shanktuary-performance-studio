"""Rolling 60Hz Pre-roll & Post-roll Buffer for Shot-Synchronized Balance Telemetry."""

from collections import deque
from dataclasses import dataclass, asdict
import time
from typing import Optional, List, Dict, Any

from .cop import CoPSample
from .torque import TorqueSample
from .compression import CompressionResult


@dataclass
class SynchronizedPressureFrame:
    """Single timestamped pressure frame."""
    timestamp: float
    rel_time_s: float
    total_kg: float
    force_bw: float
    pct_left: float
    pct_right: float
    left_pct_front: float
    left_pct_back: float
    right_pct_front: float
    right_pct_back: float
    cop_x: float
    cop_y: float
    torque_nm: float
    phase: str
    raw_cells: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ShotSynchronizedPressureBuffer:
    """Maintains a 60Hz circular buffer (default 600 samples = 10s) and handles shot capture."""

    def __init__(self, capacity: int = 600) -> None:
        self.capacity = capacity
        self._ring: deque[Dict[str, Any]] = deque(maxlen=capacity)
        self._recording = False
        self._impact_time: Optional[float] = None
        self._post_impact_frames = 0
        self._post_impact_target = 180  # ~3.0s at 60Hz
        self._captured_shot_callback = None

    def push(
        self,
        sample: CoPSample,
        torque: Optional[TorqueSample] = None,
        compression: Optional[CompressionResult] = None,
        phase: str = "Address",
    ) -> Dict[str, Any]:
        now = sample.timestamp
        frame = {
            "timestamp": now,
            "total_kg": round(sample.total_kg, 2),
            "force_bw": round(sample.force_bw, 3) if hasattr(sample, "force_bw") else 1.0,
            "pct_left": round(sample.pct_left, 1),
            "pct_right": round(sample.pct_right, 1),
            "left_pct_front": round(sample.left_pct_front, 1),
            "left_pct_back": round(sample.left_pct_back, 1),
            "right_pct_front": round(sample.right_pct_front, 1),
            "right_pct_back": round(sample.right_pct_back, 1),
            "cop_x": round(sample.cop_x, 1),
            "cop_y": round(sample.cop_y, 1),
            "torque_nm": round(torque.torque_nm, 2) if torque else 0.0,
            "phase": phase,
            "raw_cells": [
                round(sample.raw.top_left, 2),
                round(sample.raw.top_right, 2),
                round(sample.raw.bottom_left, 2),
                round(sample.raw.bottom_right, 2),
            ],
        }
        self._ring.append(frame)

        if self._recording:
            self._post_impact_frames += 1
            if self._post_impact_frames >= self._post_impact_target:
                self._finalize_shot()

        return frame

    def trigger_shot_impact(self, impact_time: Optional[float] = None, callback=None) -> None:
        """Called when Launch Monitor detects ball impact.

        impact_time must be on the SAME clock as the frame timestamps
        (time.monotonic(), per SensorReading.timestamp convention). When not
        provided, default to the newest frame's timestamp — NOT time.time():
        mixing wall clock with the monotonic sensor clock makes every dt fall
        outside the capture window and shots come back empty.
        """
        if impact_time is None:
            if self._ring:
                impact_time = self._ring[-1]["timestamp"]
            else:
                impact_time = time.monotonic()
        self._impact_time = impact_time
        self._recording = True
        self._post_impact_frames = 0
        self._captured_shot_callback = callback

    def _finalize_shot(self) -> None:
        self._recording = False
        impact_t = self._impact_time
        if impact_t is None:
            impact_t = self._ring[-1]["timestamp"] if self._ring else time.monotonic()
        # Extract [-5.0s, +3.0s] relative to impact
        window = []
        for f in self._ring:
            dt = f["timestamp"] - impact_t
            if -5.0 <= dt <= 3.2:
                item = dict(f)
                item["rel_time_s"] = round(dt, 3)
                window.append(item)

        if self._captured_shot_callback:
            try:
                self._captured_shot_callback(window)
            except Exception as e:
                print(f"[!] Error in pressure shot callback: {e}")

    def get_latest_frame(self) -> Optional[Dict[str, Any]]:
        # Shallow copy: callers (obs_server) serialize/broadcast from other
        # threads; handing out the live ring entry invites mutation races.
        return dict(self._ring[-1]) if self._ring else None
