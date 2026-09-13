"""Combine: a fixed skills test scored with the Index's own math.

Three stations from the golfer's bag (short / mid / long), ten full swings
each. A station scores exactly like a club in the Index -- the same
validity gate, `efficiency_ratio`, `shape_ratio`, category weights and
0-99 scale -- so a Combine number reads as "what the Index would say about
these thirty swings". There is deliberately no second formula.

Shots are tagged `combine_station` when they land during a run, so a
session can hold warm-up swings and combine swings side by side.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .index import (
    _COMPOSITE_WEIGHTS,
    _club_category,
    _efficiency_inputs,
    _shape_value,
    efficiency_ratio,
    shape_ratio,
    valid_shots,
)

SHOTS_PER_STATION = 10
FILE_NAME = "shanktuary_combine_history.json"

# Station roles map onto the Index's weight-table categories.
_ROLE_CATEGORIES = {
    "short": ("wedges",),
    "mid": ("irons",),
    "long": ("long", "woods"),
}
_ROLE_ORDER = ("short", "mid", "long")

# Preferred club per role when the bag offers several: the "stock" club a
# golfer is most likely to have a real number for.
_ROLE_PREFERENCE = {
    "short": ("PW", "GW", "SW"),
    "mid": ("7 Iron", "6 Iron", "8 Iron"),
    "long": ("4 Hybrid", "5 Hybrid", "3 Hybrid", "5 Wood", "4 Iron", "3 Wood", "Driver"),
}


def _bag_names(bag: list[dict[str, Any]] | None) -> list[str]:
    out = []
    for c in bag or []:
        name = c.get("name") if isinstance(c, dict) else None
        if name:
            out.append(str(name))
    return out


def protocol_for_bag(bag: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Pick one club per role from what the golfer actually owns."""
    names = _bag_names(bag)
    stations = []
    for role in _ROLE_ORDER:
        cats = _ROLE_CATEGORIES[role]
        candidates = [n for n in names if _club_category(n) in cats]
        if not candidates:
            continue
        pick = next((p for p in _ROLE_PREFERENCE[role] if p in candidates), candidates[0])
        stations.append({"role": role, "club": pick})
    if len(stations) < 2:
        return {"stations": [], "shots_per_station": SHOTS_PER_STATION,
                "reason": "Need at least two of: a wedge, a mid iron, a long club in the bag"}
    return {"stations": stations, "shots_per_station": SHOTS_PER_STATION, "reason": None}


def station_shots(role: str, club: str, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The first SHOTS_PER_STATION *valid* full swings tagged for this station."""
    tagged = [s for s in shots if isinstance(s, dict)
              and s.get("combine_station") == role and s.get("club") == club]
    kept = valid_shots(tagged)
    return kept[:SHOTS_PER_STATION]


def _station_score(club: str, kept: list[dict[str, Any]], is_left_handed: bool) -> dict[str, Any]:
    eff_inputs = [i for i in (_efficiency_inputs(s) for s in kept) if i is not None]
    axes = [a for a in (_shape_value(s) for s in kept) if a is not None]
    eff = sum(efficiency_ratio(*i) for i in eff_inputs) / len(eff_inputs) if eff_inputs else None
    shp = shape_ratio(axes, is_left_handed=is_left_handed) if axes else None
    category = _club_category(club)
    score = None
    if eff is not None and shp is not None and category is not None:
        w_eff, w_shp = _COMPOSITE_WEIGHTS[category]
        ratio = (eff * w_eff + shp * w_shp) / (w_eff + w_shp)
        score = round(min(99.0, max(0.0, ratio * 99.0)), 1)
    return {"efficiency": eff, "shape": shp, "score": score}


def score(stations: list[dict[str, Any]], shots: list[dict[str, Any]],
          is_left_handed: bool = False) -> dict[str, Any]:
    """Score a run. Overall is None until every station has its ten swings."""
    out_stations = []
    for st in stations:
        role, club = st["role"], st["club"]
        kept = station_shots(role, club, shots)
        complete = len(kept) >= SHOTS_PER_STATION
        entry = {"role": role, "club": club, "counted": len(kept),
                 "needed": SHOTS_PER_STATION, "complete": complete,
                 "efficiency": None, "shape": None, "score": None}
        if kept:
            entry.update(_station_score(club, kept, is_left_handed))
        if not complete:
            # Report progress, but never a headline number for a partial station.
            entry["score"] = None
        out_stations.append(entry)
    done = [s for s in out_stations if s["complete"] and s["score"] is not None]
    all_done = bool(out_stations) and len(done) == len(out_stations)
    overall = round(sum(s["score"] for s in done) / len(done), 1) if all_done else None
    return {
        "status": "complete" if all_done else ("in_progress" if out_stations else "no_protocol"),
        "score": overall,
        "stations": out_stations,
        "shots_per_station": SHOTS_PER_STATION,
    }


# --- history ---------------------------------------------------------------------

def default_path() -> Path:
    import shanktuary_performance_studio as studio

    return Path(studio.SESSION_LOG_PATH).parent / FILE_NAME


def load(path: Path | str | None = None) -> list[dict[str, Any]]:
    p = Path(path) if path else default_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            os.replace(p, str(p) + ".corrupt")
        except OSError:
            pass
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and "score" in e and "date" in e]


def record(result: dict[str, Any], *, session_id: str, path: Path | str | None = None,
           now: str | None = None) -> dict[str, Any] | None:
    """Persist a COMPLETE run; a re-save of the same session replaces its entry."""
    if result.get("status") != "complete" or result.get("score") is None:
        return None
    p = Path(path) if path else default_path()
    entry = {
        "date": now or datetime.now().isoformat(timespec="seconds"),
        "session_id": session_id,
        "score": float(result["score"]),
        "stations": [{"role": s["role"], "club": s["club"], "score": s["score"]}
                     for s in result["stations"]],
    }
    hist = [e for e in load(p) if e.get("session_id") != session_id]
    hist.append(entry)
    hist.sort(key=lambda e: e["date"])
    tmp = str(p) + ".tmp"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hist, f, indent=2)
    os.replace(tmp, p)
    return entry


def summary(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not history:
        return None
    ordered = sorted(history, key=lambda e: e["date"])
    best = max(ordered, key=lambda e: e["score"])
    return {"runs": len(ordered), "latest": ordered[-1]["score"], "latest_date": ordered[-1]["date"],
            "best": best["score"], "best_date": best["date"]}
