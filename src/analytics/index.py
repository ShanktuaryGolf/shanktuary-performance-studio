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
from typing import Any

from .flight_model import carry_yards, model_optimum

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
