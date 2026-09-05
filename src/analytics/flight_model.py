"""Ball-flight model for the Efficiency attribute — solved, not sourced.

Plan: ~/sps-notes/shanktuary-index-plan-2026-08-30.md §6b.

The Shanktuary Index needs a "launch-optimal carry" benchmark to score
Efficiency (= actual carry / optimal carry at that ball speed). No vendor
publishes that curve, so §6b solves it instead: port the flight portion of
the range's own ball-flight engine to Python and sweep vertical launch angle
x total spin at each ball speed to find the carry-maximizing combination.

This is a direct line-for-line port of the in-air physics in
assets/range/js/physics.js -- specifically the aerodynamic model from commit
0c1afb9 ("refit ball flight against ~10,700 real shots", 2026-08-31), NOT the
coefficients that were live when the plan doc was written a day earlier. The
plan's originally-printed reference table (114.5y / 160.4y / 203.2y / 242.3y /
277.6y at 80/100/120/140/160 mph) came from the pre-refit model and is stale;
it will not reproduce here. See the port-verification note in this repo's
history for the confirmation these two engines agree to ~0.1y on arbitrary
inputs, and shanktuary-index-plan-2026-08-30.md §6b for the updated table.

Roll and bounce are intentionally NOT ported: Efficiency scores carry, and
carry is defined as the horizontal distance at first ground contact -- the
JS engine's post-bounce roll model doesn't affect that number.

Validation status (inherited from the JS engine, commit 0c1afb9): fitted
against ~10,700 real shots from four independent sources (TrackMan drives, a
measured-spin Kaggle set, Foresight's published per-club reference rows, and
Garmin R10 range sessions); held-out accuracy 69% -> 83% of shots within 10
yards, sd 11.4 -> 8.5. NOT validated below ~50 mph ball speed -- no source in
the fit covers that range, so chips and putts are extrapolation here. This
doesn't bite the Index today because the shared validity gate (index.py)
filters partial swings out before Efficiency ever sees them, but it belongs
on record so a future slice doesn't assume otherwise.

The model does not agree with OGC's own carry estimate in absolute terms (see
§6b: +8.1y mean over the 10 fastest real shots in the sample session). That is
fine and expected -- Efficiency never compares this model's output to OGC's.
Both the player's shot and the optimum it's judged against are computed by
THIS model, so a shared bias cancels by construction. Never take one side of
the ratio from here and the other from a sourced/vendor table -- that turns a
cancelling bias into a real +8.3-point error (§9a).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

GRAVITY = 9.81  # m/s^2
AIR_DENSITY = 1.225  # kg/m^3
BALL_MASS = 0.04593  # kg
BALL_RADIUS = 0.02135  # m
BALL_AREA = math.pi * BALL_RADIUS ** 2
DT = 0.01  # s, matches physics.js's 10ms tick
MAX_STEPS = 2500

MPH_TO_MS = 0.44704
M_TO_YD = 1.09361

TABLE_PATH = Path(__file__).parent / "data" / "efficiency_optimum_carry.csv"

# Sweep grid for finding the carry-maximizing (VLA, spin) pair at each ball
# speed. Matches the resolution used to generate the committed table -- keep
# these in sync with TABLE_PATH if you regenerate it.
_VLA_RANGE_DEG = [v / 10 for v in range(100, 451, 5)]  # 10.0 .. 45.0 by 0.5
_SPIN_RANGE_RPM = list(range(1000, 6001, 250))
_BALL_SPEED_RANGE_MPH = list(range(40, 191, 2))


def carry_yards(
    ball_speed_mph: float,
    vla_deg: float,
    spin_rpm: float,
    spin_axis_deg: float = 0.0,
    hla_deg: float = 0.0,
) -> float:
    """Carry distance (horizontal, at first ground contact) in yards.

    Straight port of the in-air loop in physics.js's calculateTrajectory --
    same integration step, same drag/lift model, same spin decay. Bounce and
    roll are not simulated because carry doesn't need them.
    """
    speed_ms = ball_speed_mph * MPH_TO_MS
    vla = math.radians(vla_deg)
    hla = math.radians(hla_deg)
    axis = math.radians(spin_axis_deg)

    vx = speed_ms * math.cos(vla) * math.sin(hla)
    vy = speed_ms * math.sin(vla)
    vz = -speed_ms * math.cos(vla) * math.cos(hla)

    spin = spin_rpm
    x = 0.0
    y = BALL_RADIUS
    z = 0.0

    for step in range(MAX_STEPS):
        v = math.sqrt(vx * vx + vy * vy + vz * vz)
        if v > 0.5:
            spin *= math.exp(-DT / 24.5)
            spin_rad_s = spin * 2 * math.pi / 60.0
            spin_ratio = min(0.6, (BALL_RADIUS * spin_rad_s) / v)

            cd = max(0.12, min(0.60,
                0.22 + 0.38 * spin_ratio + 0.05 * (60.0 / max(v, 10.0) - 1.0)))
            cl = min(0.27, 0.09 + 0.95 * spin_ratio)

            drag = 0.5 * AIR_DENSITY * BALL_AREA * cd * v * v
            lift = 0.5 * AIR_DENSITY * BALL_AREA * cl * v * v

            ax = -(drag * (vx / v)) / BALL_MASS + (lift * math.sin(axis)) / BALL_MASS
            ay = -GRAVITY - (drag * (vy / v)) / BALL_MASS + (lift * math.cos(axis)) / BALL_MASS
            az = -(drag * (vz / v)) / BALL_MASS

            vx += ax * DT
            vy += ay * DT
            vz += az * DT
        else:
            vy -= GRAVITY * DT

        x += vx * DT
        y += vy * DT
        z += vz * DT

        if y <= BALL_RADIUS and step > 10:
            break

    return math.hypot(x, z) * M_TO_YD


def _sweep_optimum(ball_speed_mph: float) -> tuple[float, float, float]:
    """Grid-search (VLA, spin) for max carry at one ball speed.

    Returns (best_vla_deg, best_spin_rpm, best_carry_yd). Straight shots only
    (spin_axis=0, hla=0) -- lateral curve only shortens carry, never helps it.
    """
    best_carry = -1.0
    best_vla = best_spin = 0.0
    for vla in _VLA_RANGE_DEG:
        for spin in _SPIN_RANGE_RPM:
            carry = carry_yards(ball_speed_mph, vla, spin)
            if carry > best_carry:
                best_carry = carry
                best_vla, best_spin = vla, spin
    return best_vla, best_spin, best_carry


_table_cache: list[tuple[float, float]] | None = None  # (ball_speed_mph, optimal_carry_yd)


def _load_table() -> list[tuple[float, float]]:
    global _table_cache
    if _table_cache is None:
        with open(TABLE_PATH, newline="") as f:
            rows = list(csv.DictReader(f))
        _table_cache = [(float(r["ball_speed_mph"]), float(r["optimal_carry_yd"])) for r in rows]
    return _table_cache


def model_optimum(ball_speed_mph: float) -> float:
    """Launch-optimal carry (yards) at a given ball speed.

    Linearly interpolates the committed sweep table (generated by running
    this module directly -- see __main__ below). Clamps to the table's ends
    rather than extrapolating past what was actually swept.
    """
    table = _load_table()
    if ball_speed_mph <= table[0][0]:
        return table[0][1]
    if ball_speed_mph >= table[-1][0]:
        return table[-1][1]
    for (bs0, c0), (bs1, c1) in zip(table, table[1:]):
        if bs0 <= ball_speed_mph <= bs1:
            frac = (ball_speed_mph - bs0) / (bs1 - bs0)
            return c0 + frac * (c1 - c0)
    raise AssertionError("unreachable: ball_speed_mph within table bounds but no bracket found")


def generate_table() -> None:
    """Regenerate TABLE_PATH from the current carry_yards() model.

    Run this file directly (`python -m src.analytics.flight_model`) whenever
    carry_yards() changes -- e.g. if physics.js gets refit again. Table and
    generator live in the same file on purpose: there is no reference value
    to fall back to (per §6b, the plan's original table was itself generated
    this way and went stale within a day), so keeping them side by side is
    the only guard against drift.
    """
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TABLE_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ball_speed_mph", "optimal_vla_deg", "optimal_spin_rpm", "optimal_carry_yd"])
        for bs in _BALL_SPEED_RANGE_MPH:
            vla, spin, carry = _sweep_optimum(bs)
            writer.writerow([bs, vla, spin, round(carry, 3)])


if __name__ == "__main__":
    generate_table()
    print(f"wrote {TABLE_PATH}")
