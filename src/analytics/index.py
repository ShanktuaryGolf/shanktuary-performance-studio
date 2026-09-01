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
from statistics import median
from typing import Any

# A shot slower than this fraction of the club's own median ball speed is a
# chip or a half swing, not a bad full swing. Median-RELATIVE by decision in
# plan §9a: an absolute mph floor would filter a 60 mph senior's entire bag
# while letting a 110 mph player's half swings through.
PARTIAL_SWING_RATIO = 0.55

# Below this many shots the median is not stable enough to filter against, so
# the partial-swing rule stays dormant rather than discarding scarce data.
MIN_SHOTS_FOR_MEDIAN = 10

MIN_SHOTS_PROVISIONAL = 15
MIN_SHOTS_ESTABLISHED = 30


class ConfidenceTier(enum.IntEnum):
    """How much to trust a club's rating. IntEnum so tiers compare directly."""

    UNRATED = 0
    PROVISIONAL = 1
    ESTABLISHED = 2


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
    the ball-speed median down and take genuine full swings with them.
    """
    structural = [s for s in shots if _is_structurally_valid(s)]
    if len(structural) < MIN_SHOTS_FOR_MEDIAN:
        return structural

    # _is_structurally_valid guarantees a usable speed, so none of these are None.
    speeds = [bs for s in structural if (bs := _ball_speed(s)) is not None]
    floor = median(speeds) * PARTIAL_SWING_RATIO
    return [s for s in structural if (_ball_speed(s) or 0.0) >= floor]
