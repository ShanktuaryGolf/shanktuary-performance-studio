"""Dated Shanktuary Index snapshots, so progress is a series, not a number.

`player_shanktuary_index()` is recomputed from all-time history on every read
and stored nowhere, so the Index view could only ever show *today's* number.
This module keeps a small append-only series beside the session history.

Rules (each one is a test):
- Only an *available* Index is recorded; "not enough data" is not a score.
- Nothing is recorded unless the shot count changed -- relaunching the app
  five times in a day must not produce five identical points.
- Several snapshots on the same calendar day collapse to the latest one.
- A corrupt file is set aside (`.corrupt`), never silently overwritten.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

FILE_NAME = "shanktuary_index_history.json"


def default_path() -> Path:
    import shanktuary_performance_studio as studio  # DATA_DIR lives there

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
    return [e for e in data if isinstance(e, dict) and "score" in e and "at" in e]


def _snapshot(result: dict[str, Any], shot_count: int, now: str) -> dict[str, Any]:
    areas = {}
    for code, area in (result.get("game_areas") or {}).items():
        score = area.get("score") if isinstance(area, dict) else None
        if isinstance(score, (int, float)):
            areas[code] = float(score)
    clubs = {}
    for name, club in (result.get("clubs") or {}).items():
        comp = club.get("composite") if isinstance(club, dict) else None
        score = comp.get("score") if isinstance(comp, dict) else None
        if isinstance(score, (int, float)):
            clubs[name] = float(score)
    return {
        "at": now,
        "score": float(result["score"]),
        "shot_count": int(shot_count),
        "established_clubs": list(result.get("established_clubs") or []),
        "game_areas": areas,
        "clubs": clubs,
    }


def record(result: dict[str, Any], shot_count: int, *,
           path: Path | str | None = None,
           now: str | None = None) -> dict[str, Any] | None:
    """Append a snapshot; return it, or None when nothing was recorded."""
    if result.get("status") != "available":
        return None
    if not isinstance(result.get("score"), (int, float)):
        return None
    p = Path(path) if path else default_path()
    now = now or datetime.now().isoformat(timespec="seconds")
    series = load(p)
    if series and series[-1].get("shot_count") == int(shot_count):
        return None
    entry = _snapshot(result, shot_count, now)
    if series and series[-1]["at"][:10] == now[:10]:
        series[-1] = entry
    else:
        series.append(entry)
    tmp = str(p) + ".tmp"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(series, f, indent=1)
    os.replace(tmp, p)
    return entry


def trend(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest vs previous snapshot and the all-time best."""
    pts = [e for e in series if isinstance(e.get("score"), (int, float))]
    if not pts:
        return None
    latest = pts[-1]
    previous = pts[-2] if len(pts) > 1 else None
    best = max(pts, key=lambda e: e["score"])
    return {
        "latest": float(latest["score"]),
        "previous": float(previous["score"]) if previous else None,
        "delta": round(float(latest["score"]) - float(previous["score"]), 1) if previous else None,
        "best": float(best["score"]),
        "best_at": best["at"],
        "points": len(pts),
    }
