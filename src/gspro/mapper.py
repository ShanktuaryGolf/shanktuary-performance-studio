"""Map GSPro DrivingRangeShot rows into SPS shot payloads.

Port of SimRead's mapGsproRangeShotToFrame.ts (ISC license), adapted to the
exact payload shape SPS already consumes from the Nova WebSocket:

    {
      "type": "shot",
      "ball_speed_meters_per_second": ...,   # SI at top level, like Nova
      "vertical_launch_angle_degrees": ...,
      "horizontal_launch_angle_degrees": ...,
      "total_spin_rpm": ...,
      "spin_axis_degrees": ...,
      "open_golf_coach": { ...SI club/derived metrics... ,
                           "us_customary_units": {...} },
      "_source": "gspro",                    # additive provenance marker
      "_gspro": { row_id, date_created, club (raw), extracted_fields,
                  missing_fields, ogc_eligible, ... }
    }

Unit policy: GSPro stores imperial values by default (mph / yards). This
mapper converts to SI for the top-level and open_golf_coach fields and
keeps the original imperial numbers in us_customary_units so the HUD can
display them unchanged. If a machine runs GSPro configured for metric,
set GSPRO_INPUT_UNITS = "metric" (module constant) — verify on a live
machine before trusting that path.

Honest-data rules (per SPS conventions):
  * Only fields actually present in ShotData are emitted; absent metrics
    are simply missing from the payload (the UI renders absent states).
  * HI/VI impact-location values are NOT mapped into ogc.face_contact:
    GSPro's unit for them is unverified, and SPS reads that dict as mm.
    They are preserved raw in _gspro.raw_fields instead.
  * spin_axis_degrees passes through with GSPro's sign convention; verify
    against known fade/slice shots on a live machine before trusting curve
    direction (TrackMan-style: positive = right).
"""

import json
import math
import re

# --- Unit constants -------------------------------------------------------
MPH_TO_MPS = 0.44704
YARDS_TO_METERS = 0.9144

#: "imperial" (GSPro default) or "metric". Verify on a live machine before
#: relying on the metric path.
GSPRO_INPUT_UNITS = "imperial"

# --- Field catalog (ported from SimRead's KNOWN_FIELD_TARGETS) ------------
KNOWN_FIELD_TARGETS = [
    "club", "carry", "carryGame", "carryLm", "totalDistance", "offline",
    "ballSpeed", "vla", "hla", "backSpin", "sideSpin", "spinAxis", "spin",
    "totalSpin", "peakHeight", "descentAngle", "distToPin", "clubSpeed",
    "clubPath", "clubAoa", "faceToTarget", "faceToPath", "clubLie",
    "clubLoft", "dynamicLoft", "closureRate", "clubFaceHImpact",
    "clubFaceVImpact", "smashFactor",
]

#: GSPro ShotData key -> gsproFields target. Order matters only for the
#: TotalSpin/Spin fallback (first present wins, matching SimRead).
NUMERIC_MAPPINGS = [
    ("Carry", "carry"),
    ("rawCarryGame", "carryGame"),
    ("rawCarryLM", "carryLm"),
    ("TotalDistance", "totalDistance"),
    ("Offline", "offline"),
    ("BallSpeed", "ballSpeed"),
    ("VLA", "vla"),
    ("HLA", "hla"),
    ("BackSpin", "backSpin"),
    ("SideSpin", "sideSpin"),
    ("rawSpinAxis", "spinAxis"),
    ("TotalSpin", "totalSpin"),
    ("Spin", "totalSpin"),
    ("PeakHeight", "peakHeight"),
    ("Decent", "descentAngle"),  # GSPro spells it "Decent" (sic)
    ("DistanceToPin", "distToPin"),
    ("ClubSpeed", "clubSpeed"),
    ("Path", "clubPath"),
    ("AoA", "clubAoa"),
    ("FaceToTarget", "faceToTarget"),
    ("FaceToPath", "faceToPath"),
    ("Lie", "clubLie"),
    ("Loft", "clubLoft"),
    ("DynamicLoft", "dynamicLoft"),
    ("CR", "closureRate"),
    ("HI", "clubFaceHImpact"),
    ("VI", "clubFaceVImpact"),
    ("SmashFactor", "smashFactor"),
]

#: Fields GSPro must fill in (possibly after its OGC plugin enriches the row)
#: before a shot is considered complete. Ported from SimRead's
#: REQUIRED_LAYOUT_FIELDS / hasRequiredShotFields.
REQUIRED_FIELDS = ("carry", "totalDistance", "offline")

#: Ball metrics needed to call OpenGolfCoach enrichment (SimRead's
#: OGC_INPUT_FIELDS). A GSPro shot missing any of these is not eligible for
#: the step-3 enrichment pass.
OGC_INPUT_FIELDS = ("ballSpeed", "vla", "hla", "spin", "spinAxis")


def _to_number(value):
    """Finite number or None (ported from SimRead's toNumber)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _to_str(value):
    if isinstance(value, str) and value.strip():
        return value
    return None


def parse_shot_row(row):
    """Parse one raw DB row into gsproFields.

    ``row`` is a mapping with keys id / date_created / shot_data (as returned
    by read_latest) or the 3-tuple (id, date_created, shot_data). Returns a
    dict of extracted fields (imperial units as stored), plus "club" when
    present. Raises ValueError on malformed ShotData JSON — callers decide
    whether to skip or surface the row.
    """
    if isinstance(row, tuple):
        row = {"id": row[0], "date_created": row[1], "shot_data": row[2]}

    shot_data_raw = row["shot_data"]
    try:
        parsed = json.loads(shot_data_raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"DrivingRangeShot.ShotData is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("DrivingRangeShot.ShotData JSON was not an object")

    fields = {}
    # SimRead reads a lowercase "club" key while every other GSPro field is
    # PascalCase. Accept either spelling: if the key case ever differs the
    # only symptom is the club silently falling back to the UI selection,
    # which quietly mis-attributes shots to the wrong club.
    club = _to_str(parsed.get("club"))
    if club is None:
        club = _to_str(parsed.get("Club"))
    if club is not None:
        fields["club"] = club

    for source_key, target in NUMERIC_MAPPINGS:
        value = _to_number(parsed.get(source_key))
        if value is not None and target not in fields:
            fields[target] = value

    # Total spin resolution (ported from SimRead's deriveTotalSpin):
    # explicit TotalSpin/Spin first, else magnitude of the back/side vector.
    total_spin = fields.get("totalSpin")
    if total_spin is None and "backSpin" in fields and "sideSpin" in fields:
        total_spin = round(math.hypot(fields["backSpin"], fields["sideSpin"]), 2)
    if total_spin is not None:
        fields["totalSpin"] = total_spin
        fields["spin"] = total_spin

    return fields


def _resolve_carry(fields):
    """Carry priority (ported from SimRead's buildResolvedShot):
    Carry > rawCarryGame > rawCarryLM."""
    for key in ("carry", "carryGame", "carryLm"):
        if fields.get(key) is not None:
            return fields[key]
    return None


def _convert(value, kind):
    """Convert an as-stored GSPro value to SI. ``kind``: 'speed' | 'distance'.

    Returns (si_value, imperial_value). With GSPRO_INPUT_UNITS == "metric"
    the stored value is already SI and no conversion happens.
    """
    if value is None:
        return None, None
    if GSPRO_INPUT_UNITS == "imperial":
        factor = MPH_TO_MPS if kind == "speed" else YARDS_TO_METERS
        return value * factor, value
    return value, value / (MPH_TO_MPS if kind == "speed" else YARDS_TO_METERS)


def map_gspro_range_shot_to_sps_payload(row):
    """Map a raw GSPro row to the SPS shot payload shape.

    Returns (payload, meta) where ``meta`` carries extraction diagnostics:
      {"row_id", "date_created", "extracted_fields", "missing_fields",
       "required_missing", "ogc_eligible", "ogc_missing"}
    The payload is safe to put on SPS's shot_queue as-is; poll_queue() will
    stamp club/timestamp and validate it like any Nova shot.
    """
    fields = parse_shot_row(row)

    row_id = row["id"] if isinstance(row, dict) else row[0]
    date_created = (row.get("date_created") if isinstance(row, dict) else row[1])

    payload = {"type": "shot", "_source": "gspro"}

    # --- Top-level SI ball metrics (Nova-compatible names) -----------------
    ball_mps, _ = _convert(fields.get("ballSpeed"), "speed")
    if ball_mps is not None:
        payload["ball_speed_meters_per_second"] = ball_mps
    if fields.get("vla") is not None:
        payload["vertical_launch_angle_degrees"] = fields["vla"]
    if fields.get("hla") is not None:
        payload["horizontal_launch_angle_degrees"] = fields["hla"]
    if fields.get("totalSpin") is not None:
        payload["total_spin_rpm"] = fields["totalSpin"]
    # Sign convention unverified — see module docstring.
    if fields.get("spinAxis") is not None:
        payload["spin_axis_degrees"] = fields["spinAxis"]

    # --- open_golf_coach sub-dict (SI) -------------------------------------
    ogc = {}
    us_units = {}

    carry_yd = _resolve_carry(fields)
    if carry_yd is not None:
        carry_m, carry_us = _convert(carry_yd, "distance")
        ogc["carry_distance_meters"] = carry_m
        us_units["carry_distance_yards"] = carry_us

    total_yd = fields.get("totalDistance")
    if total_yd is not None:
        total_m, total_us = _convert(total_yd, "distance")
        ogc["total_distance_meters"] = total_m
        us_units["total_distance_yards"] = total_us

    offline_yd = fields.get("offline")
    if offline_yd is not None:
        off_m, off_us = _convert(offline_yd, "distance")
        ogc["offline_distance_meters"] = off_m
        us_units["offline_distance_yards"] = off_us

    peak_yd = fields.get("peakHeight")
    if peak_yd is not None:
        _, peak_us = _convert(peak_yd, "distance")
        us_units["peak_height_yards"] = peak_us

    if fields.get("descentAngle") is not None:
        ogc["descent_angle_degrees"] = fields["descentAngle"]
    if fields.get("backSpin") is not None:
        ogc["backspin_rpm"] = fields["backSpin"]
    if fields.get("sideSpin") is not None:
        ogc["sidespin_rpm"] = fields["sideSpin"]

    club_mps, _ = _convert(fields.get("clubSpeed"), "speed")
    if club_mps is not None:
        ogc["club_speed_meters_per_second"] = club_mps
    if fields.get("smashFactor") is not None:
        ogc["smash_factor"] = fields["smashFactor"]
    if fields.get("dynamicLoft") is not None:
        ogc["dynamic_loft_degrees"] = fields["dynamicLoft"]
    if fields.get("clubAoa") is not None:
        ogc["angle_of_attack_degrees"] = fields["clubAoa"]
    if fields.get("closureRate") is not None:
        ogc["face_closure_rate_dps"] = fields["closureRate"]
    # Handedness: GSPro stores scalars in its own frame. SPS's resolve_handed()
    # treats scalars as right-handed and flips for LH — same contract Nova uses.
    if fields.get("clubPath") is not None:
        ogc["club_path_degrees"] = fields["clubPath"]
    if fields.get("faceToPath") is not None:
        ogc["club_face_to_path_degrees"] = fields["faceToPath"]
    if fields.get("faceToTarget") is not None:
        ogc["club_face_to_target_degrees"] = fields["faceToTarget"]
    # Mirror launch angle inside ogc (some SPS code paths read it there first).
    if fields.get("vla") is not None:
        ogc["vertical_launch_angle_degrees"] = fields["vla"]

    if us_units:
        ogc["us_customary_units"] = us_units
    if ogc:
        payload["open_golf_coach"] = ogc

    # --- Provenance / diagnostics (additive, never touches native fields) --
    extracted = sorted(k for k in fields if k != "club")
    missing = [k for k in KNOWN_FIELD_TARGETS if k not in fields]
    required_missing = [k for k in REQUIRED_FIELDS if fields.get(k) is None]
    ogc_missing = [k for k in OGC_INPUT_FIELDS if fields.get(k) is None]

    payload["_gspro"] = {
        "row_id": row_id,
        "date_created": date_created,
        "club": fields.get("club"),  # raw GSPro bag string; SPS overwrites
                                     # top-level club with its own selection
        "extracted_fields": extracted,
        "missing_fields": missing,
        "required_missing": required_missing,
        "ogc_eligible": not ogc_missing,
        "ogc_missing": ogc_missing,
        # Unverified-unit fields preserved raw (NOT mapped into face_contact).
        "raw_fields": {
            k: v for k, v in (
                ("club_face_h_impact", fields.get("clubFaceHImpact")),
                ("club_face_v_impact", fields.get("clubFaceVImpact")),
                ("distance_to_pin_yards_as_stored", fields.get("distToPin")),
            ) if v is not None
        },
    }

    meta = {
        "row_id": row_id,
        "date_created": date_created,
        "extracted_fields": extracted,
        "missing_fields": missing,
        "required_missing": required_missing,
        "ogc_eligible": not ogc_missing,
        "ogc_missing": ogc_missing,
    }
    return payload, meta


def is_complete(fields):
    """True when the row carries every REQUIRED_FIELDS entry (SimRead's
    layoutSupport gate). GSPro's OGC plugin enriches rows in place after a
    shot; the poller re-reads until this passes."""
    return all(fields.get(k) is not None for k in REQUIRED_FIELDS)


# --- Club-name matching ----------------------------------------------------
# GSPro stores the club string from ITS bag config ("7i", "PW", "4H"), which
# does not necessarily match SPS's canonical names ("7 Iron"). Unmatched clubs
# must fall back to the app's current selection — a phantom club name would
# corrupt per-club scoring (the data-audit lesson).

_CLUB_ALIASES = {
    "driver": "driver", "drvr": "driver", "drv": "driver",
    "3w": "3 wood", "5w": "5 wood", "7w": "7 wood",
    "4h": "4 hybrid", "5h": "5 hybrid", "3h": "3 hybrid",
    "pw": "pitching wedge", "gw": "gap wedge", "sw": "sand wedge", "lw": "lob wedge",
}


def _club_key(name):
    """Normalize a club name to a comparable lowercase key, or None.

    Handles the common GSPro/launch-monitor shorthand: '7i' -> '7 iron',
    '4H' -> '4 hybrid', 'PW' -> 'pitching wedge', '52 Wedge' -> 'wedge 52'.
    """
    if not isinstance(name, str):
        return None
    s = name.strip().lower()
    if not s:
        return None
    # "7i" / "7 iron" / "iron 7"
    m = re.match(r"^(\d{1,2})\s*(?:i|iron)?$", s) or re.match(r"^iron\s+(\d{1,2})$", s)
    if m:
        return f"{m.group(1)} iron"
    # "3w" / "3 wood" / "fairway 3"
    m = re.match(r"^(\d)\s*(?:w|wood)?$", s) or re.match(r"^(?:wood|fairway)\s+(\d)$", s)
    if m:
        return f"{m.group(1)} wood"
    # "4h" / "4 hybrid"
    m = re.match(r"^(\d)\s*(?:h|hybrid)?$", s) or re.match(r"^hybrid\s+(\d)$", s)
    if m:
        return f"{m.group(1)} hybrid"
    # wedges by loft: "52 wedge", "60w", "rtx 52"
    m = (re.search(r"(?:^|\D)(\d{2})\s*(?:deg|°)?(?:\s*wedge|\s*w\b|$)", s)
         or re.match(r"^(\d{2})\s*w$", s))
    if m:
        return f"wedge {m.group(1)}"
    # bare wedge names and aliases
    for word in ("pitching wedge", "gap wedge", "sand wedge", "lob wedge"):
        if s == word or s.startswith(word):
            return word
    if s in _CLUB_ALIASES:
        return _CLUB_ALIASES[s]
    # unrecognized free text -> itself (exact-match only, no guessing)
    return s


def match_gspro_club(raw_name, bag_names):
    """Match a GSPro club string against SPS's actual bag names.

    Returns the CANONICAL bag name on a confident match, else None — callers
    fall back to their current selection rather than inventing a new club.
    Comparison is by normalized key, so '7i' matches '7 Iron' and 'PW'
    matches 'Pitching Wedge'.
    """
    if not raw_name or not bag_names:
        return None
    target = _club_key(raw_name)
    if target is None:
        return None
    hits = [name for name in bag_names if _club_key(name) == target]
    if len(hits) == 1:
        return hits[0]
    # Multiple bag clubs normalize to the same key (e.g. two "52" wedges):
    # never guess between them — fall through to the loft-only pass below,
    # which also requires uniqueness, else None.
    # Second pass: loft-only wedge match ("52" vs "RTX 52") — only when the
    # bag has exactly one club with that loft, so we never guess between two.
    m = re.match(r"^wedge (\d{2})$", target)
    if m:
        loft = m.group(1)
        hits = [n for n in bag_names
                if _club_key(n) == f"wedge {loft}"
                or re.search(rf"(?:^|\D){loft}(?:\s*w|$)", str(n), re.I)]
        if len(hits) == 1:
            return hits[0]
    return None
