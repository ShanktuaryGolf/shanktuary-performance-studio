"""On-disk store for captured pressure traces.

A trace is ~480 frames (-5s..+3s around impact) and serialises to ~200 KB.
The session history file is rewritten in full after every shot, so putting
traces inline would mean a ~100 MB rewrite 3 seconds after each swing once a
few hundred shots have accumulated. They live in their own directory instead,
one compressed file per shot, loaded on demand.

Layout:
    <base>/pressure_traces/<shot_id>.json.gz

Shot ids come from the Nova payload (`shotId`); shots without one fall back
to a timestamp-derived key assigned at capture time.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from typing import Any, Dict, List, Optional

TRACE_DIR_NAME = "pressure_traces"

# Ids reach the filesystem, so restrict them rather than trusting the device.
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")

# Guard against a runaway buffer filling the disk. A legitimate trace at 60Hz
# over 8.2s is ~490 frames.
MAX_FRAMES = 2000


def _safe_id(shot_id: Any) -> str:
    return _SAFE_ID.sub("_", str(shot_id))[:80] or "unknown"


class PressureTraceStore:
    """Reads and writes per-shot pressure traces beside the session file."""

    def __init__(self, base_dir: str) -> None:
        self.dir = os.path.join(base_dir, TRACE_DIR_NAME)

    def path_for(self, shot_id: Any) -> str:
        return os.path.join(self.dir, f"{_safe_id(shot_id)}.json.gz")

    def save(self, shot_id: Any, frames: list[dict[str, Any]]) -> str | None:
        """Write a trace. Returns the path, or None if nothing was written.

        Failures are reported and swallowed: losing a trace must never take
        the shot itself down with it.
        """
        if not frames:
            return None
        try:
            os.makedirs(self.dir, exist_ok=True)
            path = self.path_for(shot_id)
            tmp = path + ".tmp"
            payload = {
                "shot_id": str(shot_id),
                "frame_count": len(frames),
                "frames": frames[:MAX_FRAMES],
            }
            # Atomic swap, matching save_session_to_file(): a crash mid-write
            # leaves the previous trace intact rather than a truncated one.
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            os.replace(tmp, path)
            return path
        except Exception as e:
            print(f"[!] Could not save pressure trace for {shot_id}: {e}")
            return None

    def load(self, shot_id: Any) -> list[dict[str, Any]] | None:
        """Read a trace back, or None when absent or unreadable."""
        path = self.path_for(shot_id)
        if not os.path.isfile(path):
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
            frames = data.get("frames")
            return frames if isinstance(frames, list) else None
        except Exception as e:
            print(f"[!] Could not read pressure trace for {shot_id}: {e}")
            return None

    def has(self, shot_id: Any) -> bool:
        return os.path.isfile(self.path_for(shot_id))
