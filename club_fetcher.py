"""Lookup factory loft/lie for a brand + model + club list.

Reads club_specs_db.json next to this file. Unknown brand/model returns {}.
No network. Keys match My Bag: loft_deg, lie_deg.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "club_specs_db.json"

_WEDGE_ALIASES = {
    "p": "PW",
    "pw": "PW",
    "pitching": "PW",
    "pitching wedge": "PW",
    "a": "AW",
    "aw": "AW",
    "approach": "AW",
    "approach wedge": "AW",
    "g": "GW",
    "gw": "GW",
    "gap": "GW",
    "gap wedge": "GW",
    "s": "SW",
    "sw": "SW",
    "sand": "SW",
    "sand wedge": "SW",
    "l": "LW",
    "lw": "LW",
    "lob": "LW",
    "lob wedge": "LW",
}

_IRON_RE = re.compile(r"^(\d+)\s*(i|iron)?$", re.IGNORECASE)


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def normalize_club_name(name: str) -> str:
    raw = _norm(name)
    if not raw:
        return ""
    alias = _WEDGE_ALIASES.get(raw)
    if alias:
        return alias
    m = _IRON_RE.match(raw)
    if m:
        return f"{m.group(1)} Iron"
    return str(name).strip()


def _load_sets(path: Path | None = None) -> list[dict]:
    db_path = path or DB_PATH
    try:
        data = json.loads(db_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    sets = data.get("sets")
    return sets if isinstance(sets, list) else []


def fetch_club_specs(
    brand: str,
    model: str,
    club_list,
    *,
    db_path: Path | None = None,
) -> dict:
    """Return {club_name: {loft_deg, lie_deg}} for clubs found in the table.

    club_list may be a list or tuple. Missing brand/model or unknown clubs
    are omitted (empty dict if nothing matches). Does not raise on miss.
    """
    brand_key = _norm(brand)
    model_key = _norm(model)
    if not brand_key or not model_key:
        return {}

    wanted = [normalize_club_name(c) for c in (club_list or [])]
    wanted = [c for c in wanted if c]
    if not wanted:
        return {}

    for entry in _load_sets(db_path):
        if _norm(entry.get("brand", "")) != brand_key:
            continue
        if _norm(entry.get("model", "")) != model_key:
            continue
        clubs = entry.get("clubs") or {}
        out = {}
        for name in wanted:
            spec = clubs.get(name)
            if not isinstance(spec, dict):
                continue
            if "loft_deg" not in spec or "lie_deg" not in spec:
                continue
            out[name] = {
                "loft_deg": float(spec["loft_deg"]),
                "lie_deg": float(spec["lie_deg"]),
            }
        return out
    return {}
