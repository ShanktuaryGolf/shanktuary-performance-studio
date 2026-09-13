"""Pressure vs result: link balance-board metrics to the shots they produced.

The sentence no ball-only product can print is "your best 7 irons had 65%
lead-foot at impact; your worst had 57%". Everything here is descriptive --
a comparison of two groups of your own shots -- not a cause, and the
threshold for even writing the sentence is a gap you could feel.

Only shots that carry `pressure_metrics` (i.e. a trace actually saved) and
that pass the Index full-swing gate take part. Missing metrics on a shot
stay missing: they are dropped from that average, never read as 0.
"""
from __future__ import annotations

import statistics
from typing import Any

from .index import valid_shots

MIN_TRACED = 6
MEANINGFUL_GAP_PCT = 4.0   # lead-foot percentage points


def _pct(v: float) -> str:
    """Half-up whole percent: f"{64.5:.0f}" gives '64' (banker's rounding)."""
    return str(int(v + 0.5)) if v >= 0 else str(-int(-v + 0.5))


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n


def _carry(shot: dict[str, Any]) -> float | None:
    us = (shot.get("open_golf_coach") or {}).get("us_customary_units") or {}
    return _num(us.get("carry_distance_yards"))


def lead_pct(shot: dict[str, Any], is_left_handed: bool = False) -> float | None:
    """Lead-foot load at impact. Right plate for a lefty (Swing Lab convention)."""
    pm = shot.get("pressure_metrics") or {}
    left = _num(pm.get("pct_left_at_impact"))
    if left is None:
        return None
    return round(100.0 - left, 1) if is_left_handed else left


def _group(shots: list[dict[str, Any]], is_left_handed: bool) -> dict[str, Any]:
    carries = [c for s in shots if (c := _carry(s)) is not None]
    leads = [v for s in shots if (v := lead_pct(s, is_left_handed)) is not None]
    torques = [v for s in shots if (v := _num((s.get("pressure_metrics") or {}).get("peak_torque_nm"))) is not None]
    return {
        "n": len(shots),
        "carry": round(statistics.mean(carries), 1) if carries else None,
        "pct_lead_at_impact": round(statistics.mean(leads), 1) if leads else None,
        "n_pct_lead": len(leads),
        "peak_torque_nm": round(statistics.mean(torques), 1) if torques else None,
    }


def compare(club: str, shots: list[dict[str, Any]], is_left_handed: bool = False) -> dict[str, Any]:
    """Best-third vs worst-third by carry, among traced full swings of `club`."""
    mine = [s for s in shots if isinstance(s, dict) and s.get("club") == club]
    full = [s for s in valid_shots(mine) if _carry(s) is not None]
    traced = [s for s in full if isinstance(s.get("pressure_metrics"), dict)]
    untraced = len(full) - len(traced)
    base = {"club": club, "traced": len(traced), "untraced": untraced}
    if len(traced) < MIN_TRACED:
        return {**base, "status": "insufficient",
                "reason": f"needs {MIN_TRACED} traced full swings (have {len(traced)})",
                "best": None, "worst": None, "headline": None}
    ordered = sorted(traced, key=_carry)
    k = max(2, len(ordered) // 3)
    worst, best = _group(ordered[:k], is_left_handed), _group(ordered[-k:], is_left_handed)
    return {**base, "status": "available", "best": best, "worst": worst,
            "headline": _headline(club, best, worst)}


def _plural(club: str) -> str:
    c = club.lower()
    return c + "s" if c[-1:].isdigit() or c.endswith("iron") or c.endswith("wood") or c.endswith("hybrid") else c


def _headline(club: str, best: dict, worst: dict) -> str | None:
    b, w = best.get("pct_lead_at_impact"), worst.get("pct_lead_at_impact")
    if b is None or w is None:
        return None
    name = _plural(club)
    if abs(b - w) >= MEANINGFUL_GAP_PCT:
        return f"Best {name}: {_pct(b)}% lead foot at impact · worst: {_pct(w)}%"
    return f"Lead-foot at impact ~{_pct((b + w) / 2)}% on best and worst {name}"


def shot_line(shot: dict[str, Any], is_left_handed: bool = False) -> str | None:
    """One-line pressure summary for a single shot, or None without a trace."""
    if not isinstance(shot, dict) or not isinstance(shot.get("pressure_metrics"), dict):
        return None
    parts = []
    lead = lead_pct(shot, is_left_handed)
    if lead is not None:
        parts.append(f"{_pct(lead)}% lead foot")
    torque = _num(shot["pressure_metrics"].get("peak_torque_nm"))
    if torque is not None:
        parts.append(f"{torque:.1f} N·m peak")
    return " · ".join(parts) if parts else None
