"""Shanktuary Index — the shared validity gate and confidence tiers.

Pure functions only: no Tkinter, no server imports, no file I/O. Everything
here is computed from a list of native OGC shot dicts, which are never mutated.

Plan: ~/sps-notes/shanktuary-index-plan-2026-08-30.md §4.

Why a *shared* gate: every attribute (Consistency, Command, Strike, Efficiency,
Shape) must score the same set of shots. If each filtered its own, the rules
would drift and two numbers on the same card would describe different data --
the kind of bug nobody notices until the ratings disagree with each other.
"""
from __future__ import annotations

import enum
import statistics
from typing import Any

from .flight_model import carry_yards, model_optimum
from .spin_benchmarks import TOUR_SPIN_CV_BY_CLUB

# The partial-swing floor: a shot slower than PARTIAL_SWING_RATIO x the club's
# full-swing anchor is a chip or a half swing, not a badly struck full one.
#
# RELATIVE, not an absolute mph floor (plan §9a): an absolute floor would filter
# a 60 mph senior's entire bag while passing a 110 mph player's half swings.
#
# The anchor is the 80th percentile of ball speed, NOT the median. The median
# was wrong and real data proved it: on a golfer who practises deliberate
# partial swings, the partials drag the median down and the floor follows, so
# the filter admits exactly what it exists to remove. Measured on a synthetic
# session of full swings N(85, 4) mixed with partials U(40, 70):
#
#   % partial   median   p80   0.55*median admits   0.75*p80 admits
#         10%     84.5  87.4        30 of 42            7 of 42
#         30%     82.7  87.1        96 of 120          13 of 120
#         50%     71.4  85.8       201 of 201          43 of 201
#
# At a 50/50 mix the median anchor keeps every partial swing. p80 stays pinned
# to the full-swing mode because that mode is, by construction, the top of the
# distribution for any club a player is actually trying to hit full.
#
# 0.75 chosen with the ratio: across 7 clubs of real unfiltered range data it
# keeps ~87% of shots while cutting mean carry CV from 33.5% to 29.2%. Lower
# ratios leave pitches in; higher ones start discarding genuinely bad full
# swings, which are the shots the Index most needs to see.
FULL_SWING_ANCHOR_Q = 0.80
PARTIAL_SWING_RATIO = 0.75

# Below this many shots the anchor is not stable enough to filter against, so
# the partial-swing rule stays dormant rather than discarding scarce data.
MIN_SHOTS_FOR_ANCHOR = 10
# Back-compat alias; the old name said "median" which is no longer the anchor.
MIN_SHOTS_FOR_MEDIAN = MIN_SHOTS_FOR_ANCHOR

MIN_SHOTS_PROVISIONAL = 15
MIN_SHOTS_ESTABLISHED = 30


class ConfidenceTier(enum.IntEnum):
    """How much to trust a club's rating. IntEnum so tiers compare directly."""

    UNRATED = 0
    PROVISIONAL = 1
    ESTABLISHED = 2


def efficiency_ratio(bs_mph: float, vla_deg: float, spin_rpm: float) -> float:
    """Return launch efficiency under one flight model.

    Efficiency is a pure function of vertical launch angle and spin at a given
    ball speed: actual model carry divided by that model's launch-optimal
    carry. It measures launch-condition level, not shot-to-shot variance, and
    is not an independent measurement from Strike.
    """
    actual = carry_yards(float(bs_mph), float(vla_deg), float(spin_rpm))
    optimum = model_optimum(float(bs_mph))
    return actual / optimum


def _efficiency_inputs(shot: dict[str, Any]) -> tuple[float, float, float] | None:
    us = (shot.get("open_golf_coach") or {}).get("us_customary_units") or {}
    try:
        return (
            float(us["ball_speed_mph"]),
            float(shot["vertical_launch_angle_degrees"]),
            float(shot["total_spin_rpm"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def efficiency_by_club(shots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate gated Efficiency scores by club with confidence tiers."""
    grouped: dict[str, list[float]] = {}
    for shot in valid_shots(shots):
        inputs = _efficiency_inputs(shot)
        if inputs is None:
            continue
        club = str(shot.get("club") or "Unknown")
        grouped.setdefault(club, []).append(efficiency_ratio(*inputs))

    result: dict[str, dict[str, Any]] = {}
    for club, scores in grouped.items():
        result[club] = {
            "score": sum(scores) / len(scores),
            "count": len(scores),
            "confidence": club_confidence(len(scores)),
        }
    return result


def spin_control_ratio(actual_spins: list[float], club: str) -> float | None:
    """Compare a club's sample spin CV with its sourced Tour benchmark.

    Spin Control measures repeatability, not spin level. Unbenchmarked clubs
    and samples with fewer than two readings are unrated.
    """
    target_cv = TOUR_SPIN_CV_BY_CLUB.get(club)
    if target_cv is None or len(actual_spins) < 2:
        return None
    values = [float(spin) for spin in actual_spins]
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((spin - mean) ** 2 for spin in values) / (len(values) - 1)
    player_cv = variance ** 0.5 / abs(mean)
    if player_cv == 0:
        return 1.0
    return min(1.0, target_cv / player_cv)


def _spin_values(shot: dict[str, Any]) -> float | None:
    try:
        spin = float(shot["total_spin_rpm"])
    except (KeyError, TypeError, ValueError):
        return None
    return spin if spin > 0 else None


def spin_control_by_club(shots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate sourced Spin Control scores by club after the shared gate."""
    grouped: dict[str, list[float]] = {}
    for shot in valid_shots(shots):
        if shot.get("club") not in TOUR_SPIN_CV_BY_CLUB:
            continue
        spin = _spin_values(shot)
        if spin is not None:
            grouped.setdefault(shot["club"], []).append(spin)

    result: dict[str, dict[str, Any]] = {}
    for club, spins in grouped.items():
        score = spin_control_ratio(spins, club)
        if score is None:
            continue
        result[club] = {
            "score": score,
            "count": len(spins),
            "confidence": club_confidence(len(spins)),
        }
    return result


SHAPE_SPREAD_PLATEAU = 2.5
SHAPE_SPREAD_RATE = 10.0
SHAPE_SPREAD_FLOOR = 20.0
SHAPE_BIAS_FREE_LIMIT = 8.0
SHAPE_BIAS_RATE = 2.2
SHAPE_BIAS_PENALTY_CAP = 30.0


def shape_ratio(
    actual_axes: list[float], is_left_handed: bool = False
) -> float | None:
    """Score spin-axis bias and repeatability as a 0-to-1 ratio.

    The spread curve (SHAPE_SPREAD_*) is a provisional calibration decision
    made 2026-09-05, not a recovered source formula. Plan §9a's "Shape --
    the plateau curve" table is eight examples of intended behavior, not a
    documented formula -- no linear/quadratic/exponential curve reproduces
    all eight exactly, and attempts to reverse-engineer one from the table
    alone were inconclusive. Team vote (claude/copilot/Gemini, ruling by
    Qwen) picked the plateau-then-linear-then-floor shape below because it
    is the closest match, not because it was recovered:

        base(spread) = max(FLOOR, 100 - RATE * max(0, spread - PLATEAU))

    Reproduces six of the table's eight rows exactly. Two rows deviate --
    both by ~1 point, in opposite directions, so this is not a one-sided
    fudge:
        bias=25 deg, spread=2.4 deg: formula scores 70.0, table says 69.0 (+1.0)
        bias=0 deg,  spread=12  deg: formula scores 20.0, table says 21.1 (-1.1)

    The second row is the design-intent anchor ("a 0 deg mean with 12 deg of
    spread ... the two-way miss is the worst result on the board") and the
    formula scores it *lower* than the table's own example, so that intent
    holds with more margin, not less. The full eight-row table is reproduced
    verbatim in tests/test_index_shape.py for provenance.

    The bias penalty (SHAPE_BIAS_*), by contrast, IS an exact plan formula:
    free to +-8 degrees, then 2.2 points per degree, capped at 30.
    """
    values: list[float] = []
    for axis in actual_axes:
        try:
            value = float(axis)
        except (TypeError, ValueError):
            continue
        values.append(-value if is_left_handed else value)
    if len(values) < 2:
        return None

    bias = sum(values) / len(values)
    spread = statistics.stdev(values)
    base_score = max(
        SHAPE_SPREAD_FLOOR,
        100.0
        - SHAPE_SPREAD_RATE * max(0.0, spread - SHAPE_SPREAD_PLATEAU),
    )
    bias_penalty = min(
        SHAPE_BIAS_PENALTY_CAP,
        max(0.0, abs(bias) - SHAPE_BIAS_FREE_LIMIT) * SHAPE_BIAS_RATE,
    )
    return max(0.0, base_score - bias_penalty) / 100.0


def _shape_value(shot: dict[str, Any]) -> float | None:
    try:
        return float(shot["spin_axis_degrees"])
    except (KeyError, TypeError, ValueError):
        return None


def shape_by_club(
    shots: list[dict[str, Any]], is_left_handed: bool = False
) -> dict[str, dict[str, Any]]:
    """Aggregate Shape scores by club after the shared validity gate."""
    grouped: dict[str, list[float]] = {}
    for shot in valid_shots(shots):
        axis = _shape_value(shot)
        if axis is not None:
            grouped.setdefault(str(shot.get("club") or "Unknown"), []).append(axis)

    result: dict[str, dict[str, Any]] = {}
    for club, axes in grouped.items():
        score = shape_ratio(axes, is_left_handed=is_left_handed)
        if score is None:
            continue
        result[club] = {
            "score": score,
            "count": len(axes),
            "confidence": club_confidence(len(axes)),
        }
    return result


CONSISTENCY_RESIDUAL_MIN_SHOTS = 40


def _consistency_inputs(
    shot: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    us = (shot.get("open_golf_coach") or {}).get("us_customary_units") or {}
    try:
        carry = float(us["carry_distance_yards"])
        speed = float(us["ball_speed_mph"])
        vla = float(shot["vertical_launch_angle_degrees"])
        spin = float(shot["total_spin_rpm"])
    except (KeyError, TypeError, ValueError):
        return None
    if carry <= 0 or speed <= 0 or spin <= 0:
        return None
    return carry, speed, vla, spin


def _solve_regression(
    rows: list[tuple[float, float, float, float]],
) -> list[float] | None:
    matrix = [
        [
            sum((1.0, speed, vla, spin)[row] * (1.0, speed, vla, spin)[col] for carry, speed, vla, spin in rows)
            for col in range(4)
        ]
        + [sum(carry * (1.0, speed, vla, spin)[row] for carry, speed, vla, spin in rows)]
        for row in range(4)
    ]
    for pivot in range(4):
        pivot_row = max(range(pivot, 4), key=lambda row: abs(matrix[row][pivot]))
        if abs(matrix[pivot_row][pivot]) < 1e-12:
            return None
        matrix[pivot], matrix[pivot_row] = matrix[pivot_row], matrix[pivot]
        divisor = matrix[pivot][pivot]
        matrix[pivot] = [value / divisor for value in matrix[pivot]]
        for row in range(4):
            if row == pivot:
                continue
            factor = matrix[row][pivot]
            matrix[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[pivot])
            ]
    return [matrix[row][4] for row in range(4)]


def consistency_by_club(
    shots: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Report carry dispersion as raw CV or corrected residual standard error.

    Fewer than 40 gated shots use sample carry CV and are labeled ``RAW``.
    At 40 or more, carry is regressed on ball speed, VLA, and spin, then the
    residual sample standard deviation uses ``n - 4`` degrees of freedom.
    """
    grouped: dict[str, list[tuple[float, float, float, float]]] = {}
    for shot in valid_shots(shots):
        values = _consistency_inputs(shot)
        if values is not None:
            grouped.setdefault(str(shot.get("club") or "Unknown"), []).append(values)

    result: dict[str, dict[str, Any]] = {}
    for club, rows in grouped.items():
        carries = [row[0] for row in rows]
        if len(carries) < 2:
            continue
        if len(rows) < CONSISTENCY_RESIDUAL_MIN_SHOTS:
            mean = sum(carries) / len(carries)
            if mean <= 0:
                continue
            variance = sum((carry - mean) ** 2 for carry in carries) / (len(carries) - 1)
            value = variance**0.5 / mean
            form = "RAW"
        else:
            coefficients = _solve_regression(rows)
            if coefficients is None:
                continue
            residuals = [
                carry
                - sum(coefficient * feature for coefficient, feature in zip(
                    coefficients, (1.0, speed, vla, spin)
                ))
                for carry, speed, vla, spin in rows
            ]
            residual_std = (
                sum(residual**2 for residual in residuals) / (len(rows) - 4)
            ) ** 0.5
            mean = sum(carries) / len(carries)
            if mean <= 0:
                continue
            value = residual_std / mean
            form = "RESIDUAL"
        result[club] = {
            "cv": value,
            "form": form,
            "count": len(rows),
            "confidence": club_confidence(len(rows)),
        }
    return result


# Category weight profiles, plan §9b (Efficiency / Shape columns only --
# Consistency has no source benchmark yet, Command/Strike aren't built, so
# they stay off the weighted total per copilot's scoping call 2026-09-05.
# Renormalized to sum to 1 within each category since only two of the five
# scored columns are in play.
_COMPOSITE_WEIGHTS: dict[str, tuple[float, float]] = {
    # category -> (efficiency weight, shape weight), from the §9b table.
    "woods": (30.0, 15.0),
    "long": (25.0, 15.0),
    "irons": (20.0, 10.0),
    "wedges": (10.0, 10.0),
}


def _club_category(club: str) -> str | None:
    """Map a club name to its §9b weight-table category.

    Not a sourced boundary -- the plan's table names the four categories but
    never draws the exact club cutoffs, so "long irons" here means 3/4 Iron
    and any Hybrid, matching common usage. Putter and unrecognized names are
    excluded (no composite), same treatment as an unbenchmarked club.
    """
    if club == "Putter":
        return None
    if club == "Driver" or "Wood" in club:
        return "woods"
    if "Hybrid" in club or club in ("3 Iron", "4 Iron"):
        return "long"
    if club in ("PW", "GW", "SW", "LW") or "Wedge" in club:
        return "wedges"
    if "Iron" in club:
        return "irons"
    return None


def bag_index_summary(
    shots: list[dict[str, Any]], is_left_handed: bool = False
) -> dict[str, dict[str, Any]]:
    """Per-club card: every scored attribute, plus a weighted composite.

    The composite is Efficiency + Shape only (see _COMPOSITE_WEIGHTS) --
    Spin Control and Consistency are still reported per club for display,
    just not folded into the weighted number yet. Composite confidence is
    the weaker of its two contributing tiers: a club isn't "established"
    overall on the strength of one attribute alone.
    """
    efficiency = efficiency_by_club(shots)
    shape = shape_by_club(shots, is_left_handed=is_left_handed)
    spin_control = spin_control_by_club(shots)
    consistency = consistency_by_club(shots)

    result: dict[str, dict[str, Any]] = {}
    for club in set(efficiency) | set(shape) | set(spin_control) | set(consistency):
        entry: dict[str, Any] = {
            "efficiency": efficiency.get(club),
            "shape": shape.get(club),
            "spin_control": spin_control.get(club),
            "consistency": consistency.get(club),
        }
        eff, shp = efficiency.get(club), shape.get(club)
        category = _club_category(club)
        if eff is not None and shp is not None and category is not None:
            eff_weight, shape_weight = _COMPOSITE_WEIGHTS[category]
            total_weight = eff_weight + shape_weight
            ratio = (eff["score"] * eff_weight + shp["score"] * shape_weight) / total_weight
            entry["composite"] = {
                "score": min(99.0, max(0.0, ratio * 99.0)),
                "confidence": min(eff["confidence"], shp["confidence"]),
            }
        result[club] = entry
    return result


def club_confidence(n_valid: int) -> ConfidenceTier:
    """Map a valid-shot count to its tier.

    Takes the count of shots that PASSED the gate, not the raw count -- a club
    with 30 shots of which 12 were bad reads is not established.
    """
    if n_valid >= MIN_SHOTS_ESTABLISHED:
        return ConfidenceTier.ESTABLISHED
    if n_valid >= MIN_SHOTS_PROVISIONAL:
        return ConfidenceTier.PROVISIONAL
    return ConfidenceTier.UNRATED


def _ball_speed(shot: dict[str, Any]) -> float | None:
    us = (shot.get("open_golf_coach") or {}).get("us_customary_units") or {}
    bs = us.get("ball_speed_mph")
    try:
        bs = float(bs)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return bs if bs > 0 else None


def _is_structurally_valid(shot: dict[str, Any]) -> bool:
    """Rules that need no knowledge of the club's other shots."""
    if shot.get("club") == "Putter":
        # Nova cannot measure a putt. The 'Putter' shots in the real session
        # file are full swings from a mis-set dropdown (53-68 mph, 3500-6000
        # rpm) -- actively misleading rather than merely absent.
        return False
    if shot.get("excluded"):
        return False
    try:
        spin = float(shot.get("total_spin_rpm"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if spin <= 0:
        # Physically impossible; marks a bad read. 3 of 30 in the sample set.
        return False
    return _ball_speed(shot) is not None


def valid_shots(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the subset of ``shots`` every attribute is allowed to score.

    Two passes. The structural rules run first so that bad reads cannot drag
    the ball-speed anchor down and take genuine full swings with them.
    """
    structural = [s for s in shots if _is_structurally_valid(s)]
    if len(structural) < MIN_SHOTS_FOR_ANCHOR:
        return structural

    # _is_structurally_valid guarantees a usable speed, so none of these are None.
    speeds = sorted(bs for s in structural if (bs := _ball_speed(s)) is not None)
    idx = min(len(speeds) - 1, int(len(speeds) * FULL_SWING_ANCHOR_Q))
    anchor = speeds[idx]
    floor = anchor * PARTIAL_SWING_RATIO
    return [s for s in structural if (_ball_speed(s) or 0.0) >= floor]


MIN_CLUBS_FOR_INDEX = 3
MIN_BANDS_FOR_INDEX = 2
MIN_CARRY_SPREAD_RATIO = 1.25
MIN_CLUBS_FOR_FULL_SPREAD = 6
MIN_BANDS_FOR_FULL_SPREAD = 4

CARRY_BAND_CUTS: list[tuple[str, str, float]] = [
    ("A", "Longest", 0.85),
    ("B", "Long", 0.70),
    ("C", "Mid", 0.55),
    ("D", "Short", 0.0),
]


class IndexTier(str, enum.Enum):
    """Overall Shanktuary Index rating tiers, plan §4a."""

    INDEX = "Index"
    FULL_SPREAD = "Full-spread"


def _shot_carry(shot: dict[str, Any]) -> float | None:
    us = (shot.get("open_golf_coach") or {}).get("us_customary_units") or {}
    val = us.get("carry_distance_yards")
    if val is None:
        val = shot.get("carry_distance_yards") or shot.get("carry")
    try:
        c = float(val)  # type: ignore[arg-type]
        return c if c > 0 else None
    except (TypeError, ValueError):
        return None


def _club_mean_carries(
    shots: list[dict[str, Any]],
) -> dict[str, tuple[float, int]]:
    grouped: dict[str, list[float]] = {}
    for shot in valid_shots(shots):
        carry = _shot_carry(shot)
        if carry is not None:
            club = str(shot.get("club") or "Unknown")
            grouped.setdefault(club, []).append(carry)
    result: dict[str, tuple[float, int]] = {}
    for club, carries in grouped.items():
        if carries:
            result[club] = (sum(carries) / len(carries), len(carries))
    return result


def bag_carry_anchor(shots: list[dict[str, Any]]) -> float | None:
    """Longest mean carry among clubs with 15+ recorded valid shots.

    Plan §4a / §9a: Anchor = longest mean carry among clubs with 15+ recorded
    shots -- established or not, but not a club with two shots setting the
    reference for the whole bag. If no club qualifies, returns None.
    """
    carries = _club_mean_carries(shots)
    qualifying = [
        mean_carry
        for club, (mean_carry, count) in carries.items()
        if count >= MIN_SHOTS_PROVISIONAL
    ]
    return max(qualifying) if qualifying else None


def classify_carry_band(carry: float, anchor: float) -> str:
    """Map a carry distance to band 'A', 'B', 'C', or 'D' relative to anchor."""
    if anchor <= 0:
        return "D"
    ratio = carry / anchor
    if ratio >= 0.85:
        return "A"
    if ratio >= 0.70:
        return "B"
    if ratio >= 0.55:
        return "C"
    return "D"


def carry_bands_by_club(
    shots: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute mean carry and band assignment for every club with valid shots."""
    anchor = bag_carry_anchor(shots)
    if anchor is None or anchor <= 0:
        return {}
    club_carries = _club_mean_carries(shots)
    labels = {code: label for code, label, _ in CARRY_BAND_CUTS}
    result: dict[str, dict[str, Any]] = {}
    for club, (mean_carry, count) in club_carries.items():
        band = classify_carry_band(mean_carry, anchor)
        result[club] = {
            "mean_carry": mean_carry,
            "count": count,
            "band": band,
            "band_label": labels.get(band, "Short"),
            "ratio_to_anchor": mean_carry / anchor,
        }
    return result


def evaluate_coverage(
    shots: list[dict[str, Any]],
    bag_summary: dict[str, dict[str, Any]] | None = None,
    is_left_handed: bool = False,
) -> dict[str, Any]:
    """Evaluate whether established clubs clear the §4a coverage gate.

    Rules:
      Tier 1 (Index):
        - >= 3 established clubs (valid shot count >= 30, valid composite)
        - >= 2 distinct carry bands represented among established clubs
        - max(mean_carry) / min(mean_carry) >= 1.25 across established clubs
      Tier 2 (Full-spread):
        - >= 6 established clubs
        - all 4 carry bands (A, B, C, D) present among established clubs
    """
    if bag_summary is None:
        bag_summary = bag_index_summary(shots, is_left_handed=is_left_handed)

    anchor = bag_carry_anchor(shots)
    club_carries = _club_mean_carries(shots)

    established_clubs: list[str] = []
    for club, summary in bag_summary.items():
        composite = summary.get("composite")
        if (
            composite is not None
            and composite.get("confidence") == ConfidenceTier.ESTABLISHED
            and composite.get("score") is not None
            and club in club_carries
        ):
            established_clubs.append(club)

    established_clubs.sort(key=lambda c: club_carries[c][0], reverse=True)

    if anchor is None or anchor <= 0:
        return {
            "eligible": False,
            "tier": None,
            "reason": "No club has enough shots (>= 15) to set a distance anchor",
            "anchor_carry": anchor,
            "established_clubs": established_clubs,
            "bands_present": [],
            "spread_ratio": None,
            "club_bands": {},
            "club_mean_carries": {c: club_carries[c][0] for c in established_clubs},
        }

    club_bands = {
        club: classify_carry_band(club_carries[club][0], anchor)
        for club in established_clubs
    }
    bands_present = sorted(set(club_bands.values()))

    if len(established_clubs) < MIN_CLUBS_FOR_INDEX:
        return {
            "eligible": False,
            "tier": None,
            "reason": f"Need at least {MIN_CLUBS_FOR_INDEX} established clubs (have {len(established_clubs)})",
            "anchor_carry": anchor,
            "established_clubs": established_clubs,
            "bands_present": bands_present,
            "spread_ratio": None,
            "club_bands": club_bands,
            "club_mean_carries": {c: club_carries[c][0] for c in established_clubs},
        }

    if len(bands_present) < MIN_BANDS_FOR_INDEX:
        return {
            "eligible": False,
            "tier": None,
            "reason": f"Need established clubs across at least {MIN_BANDS_FOR_INDEX} carry bands (have {len(bands_present)})",
            "anchor_carry": anchor,
            "established_clubs": established_clubs,
            "bands_present": bands_present,
            "spread_ratio": None,
            "club_bands": club_bands,
            "club_mean_carries": {c: club_carries[c][0] for c in established_clubs},
        }

    carries = [club_carries[c][0] for c in established_clubs]
    min_carry, max_carry = min(carries), max(carries)
    spread_ratio = (max_carry / min_carry) if min_carry > 0 else 0.0

    if spread_ratio < MIN_CARRY_SPREAD_RATIO:
        return {
            "eligible": False,
            "tier": None,
            "reason": f"Need carry spread ratio >= {MIN_CARRY_SPREAD_RATIO:.2f} across established clubs (have {spread_ratio:.2f})",
            "anchor_carry": anchor,
            "established_clubs": established_clubs,
            "bands_present": bands_present,
            "spread_ratio": spread_ratio,
            "club_bands": club_bands,
            "club_mean_carries": {c: club_carries[c][0] for c in established_clubs},
        }

    if (
        len(established_clubs) >= MIN_CLUBS_FOR_FULL_SPREAD
        and len(bands_present) == MIN_BANDS_FOR_FULL_SPREAD
    ):
        tier = IndexTier.FULL_SPREAD
    else:
        tier = IndexTier.INDEX

    return {
        "eligible": True,
        "tier": tier,
        "reason": None,
        "anchor_carry": anchor,
        "established_clubs": established_clubs,
        "bands_present": bands_present,
        "spread_ratio": spread_ratio,
        "club_bands": club_bands,
        "club_mean_carries": {c: club_carries[c][0] for c in established_clubs},
    }


def player_shanktuary_index(
    shots: list[dict[str, Any]],
    is_left_handed: bool = False,
) -> dict[str, Any]:
    """Compute overall player Shanktuary Index from §4a/§5.

    Unestablished clubs are excluded from the score. If the coverage gate is not
    met, returns status='insufficient_coverage' with score=None and explicit reason.
    """
    bag_summary = bag_index_summary(shots, is_left_handed=is_left_handed)
    cov = evaluate_coverage(
        shots, bag_summary=bag_summary, is_left_handed=is_left_handed
    )

    game_areas: dict[str, dict[str, Any]] = {}
    for code, label, _ in CARRY_BAND_CUTS:
        area_clubs = [
            c for c in cov["established_clubs"] if cov["club_bands"].get(c) == code
        ]
        if area_clubs:
            scores = [
                bag_summary[c]["composite"]["score"] for c in area_clubs
            ]
            area_score = round(sum(scores) / len(scores), 1)
        else:
            area_score = None
        game_areas[code] = {
            "name": label,
            "score": area_score,
            "clubs": area_clubs,
        }

    if not cov["eligible"]:
        return {
            "status": "insufficient_coverage",
            "score": None,
            "tier": None,
            "reason": cov["reason"],
            "anchor_carry": cov["anchor_carry"],
            "established_clubs": cov["established_clubs"],
            "bands_present": cov["bands_present"],
            "spread_ratio": cov["spread_ratio"],
            "game_areas": game_areas,
            "clubs": bag_summary,
        }

    established_scores = [
        bag_summary[c]["composite"]["score"] for c in cov["established_clubs"]
    ]
    raw_score = sum(established_scores) / len(established_scores)
    final_score = round(min(99.0, max(0.0, raw_score)), 1)

    return {
        "status": "available",
        "score": final_score,
        "tier": cov["tier"],
        "reason": None,
        "anchor_carry": cov["anchor_carry"],
        "established_clubs": cov["established_clubs"],
        "bands_present": cov["bands_present"],
        "spread_ratio": cov["spread_ratio"],
        "game_areas": game_areas,
        "clubs": bag_summary,
    }


shanktuary_index = player_shanktuary_index
