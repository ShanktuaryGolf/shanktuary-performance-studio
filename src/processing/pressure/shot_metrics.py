"""Derived per-shot metrics from a captured pressure trace.

The raw trace is ~480 frames (-5s..+3s at 60Hz) and costs ~200 KB of JSON per
shot, so it is not kept in the session file. These summary metrics are: they
are what swing analysis actually consumes, and they cost ~250 bytes.

Every metric is computed from measured board samples. Where the trace cannot
support a metric -- no impact frame, no backswing detected, a board that was
never connected -- the value is None rather than a plausible-looking default.
A missing number is honest; an invented one silently corrupts whatever reads
it later.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Phase strings written by SwingDetector via the buffer. Compared
# case-insensitively on a prefix so "Backswing"/"BACKSWING" both match.
_BACKSWING = "backswing"
_TRANSITION = "transition"
_DOWNSWING = "downswing"
_IMPACT = "impact"


def _phase(frame: dict[str, Any]) -> str:
    return str(frame.get("phase", "")).strip().lower()


def _phase_span(frames: list[dict[str, Any]], name: str) -> float | None:
    """Duration in seconds that the trace spent in a phase, or None."""
    times: list[float] = []
    for f in frames:
        t = f.get("rel_time_s")
        if t is not None and _phase(f).startswith(name):
            times.append(float(t))
    if len(times) < 2:
        return None
    return round(max(times) - min(times), 3)


def _impact_frame(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The frame at impact.

    Prefer an explicit IMPACT phase; otherwise fall back to the frame nearest
    rel_time_s == 0, which is where the launch monitor said impact occurred.
    """
    tagged = [f for f in frames if _phase(f).startswith(_IMPACT)]
    if tagged:
        return tagged[0]
    dated = [f for f in frames if f.get("rel_time_s") is not None]
    if not dated:
        return None
    return min(dated, key=lambda f: abs(f["rel_time_s"]))


def _cop_speed_mm_s(frames: list[dict[str, Any]]) -> float | None:
    """Peak centre-of-pressure speed across the trace.

    CoP coordinates are already in mm (see CoPCalculator); rel_time_s is
    seconds. Frames with a zero or negative dt are skipped rather than
    producing an infinite speed.
    """
    peak = None
    prev = None
    for f in frames:
        t = f.get("rel_time_s")
        x, y = f.get("cop_x"), f.get("cop_y")
        if t is None or x is None or y is None:
            continue
        if prev is not None:
            dt = t - prev[0]
            if dt > 0:
                dx = x - prev[1]
                dy = y - prev[2]
                speed = ((dx * dx + dy * dy) ** 0.5) / dt
                if peak is None or speed > peak:
                    peak = speed
        prev = (t, x, y)
    return round(peak, 1) if peak is not None else None


def derive_pressure_metrics(
    frames: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Summarise a captured pressure trace.

    Returns None when there is nothing to summarise, so callers can simply
    skip attaching the key rather than storing an empty shell.
    """
    if not frames:
        return None

    pre = [f for f in frames
           if f.get("rel_time_s") is not None and f["rel_time_s"] <= 0.0]

    # Trail-foot load during the backswing. pct_right is the raw board value;
    # handedness is applied at the UI boundary, not here, matching the
    # convention used elsewhere for Nova fields.
    backswing = [f for f in frames if _phase(f).startswith(_BACKSWING)]
    load_window = backswing or pre
    rights = [f["pct_right"] for f in load_window if f.get("pct_right") is not None]
    peak_pct_right = round(max(rights), 1) if rights else None

    imp = _impact_frame(frames)
    pct_left_at_impact = None
    torque_at_impact = None
    if imp is not None:
        if imp.get("pct_left") is not None:
            pct_left_at_impact = round(float(imp["pct_left"]), 1)
        if imp.get("torque_nm") is not None:
            torque_at_impact = round(float(imp["torque_nm"]), 2)

    forces = [f["force_bw"] for f in frames if f.get("force_bw") is not None]
    peak_force_bw = round(max(forces), 3) if forces else None

    torques = [abs(float(f["torque_nm"])) for f in frames
               if f.get("torque_nm") is not None]
    peak_torque_nm = round(max(torques), 2) if torques else None

    # Balance at finish: the last half second of the trace.
    finish = [f for f in frames
              if f.get("rel_time_s") is not None and f["rel_time_s"] >= 2.5]
    finish_lefts = [f["pct_left"] for f in finish if f.get("pct_left") is not None]
    pct_left_at_finish = (round(sum(finish_lefts) / len(finish_lefts), 1)
                          if finish_lefts else None)

    metrics = {
        "peak_pct_right_backswing": peak_pct_right,
        "pct_left_at_impact": pct_left_at_impact,
        "pct_left_at_finish": pct_left_at_finish,
        "peak_force_bw": peak_force_bw,
        "peak_torque_nm": peak_torque_nm,
        "torque_at_impact_nm": torque_at_impact,
        "peak_cop_speed_mm_s": _cop_speed_mm_s(frames),
        "backswing_duration_s": _phase_span(frames, _BACKSWING),
        "transition_duration_s": _phase_span(frames, _TRANSITION),
        "downswing_duration_s": _phase_span(frames, _DOWNSWING),
        "frame_count": len(frames),
    }

    # A trace of nothing but idle frames yields all-None; treat that as no
    # data rather than storing a row of nulls against the shot.
    measured = [k for k, v in metrics.items()
                if v is not None and k != "frame_count"]
    if not measured:
        return None
    return metrics
