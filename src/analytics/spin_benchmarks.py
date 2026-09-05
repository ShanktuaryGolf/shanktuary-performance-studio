"""Backspin norms by club, for the Spin Control attribute.

Plan: ~/sps-notes/shanktuary-index-plan-2026-08-30.md §6 item 4. Unlike
Efficiency (§6b, solved from the range's own flight model), Spin Control's
benchmark is genuinely sourced -- this is the one attribute where TrackMan's
published data is the right call, per the plan's ordering.

Source: TrackMan's official "PGA Tour Averages" chart (spin mean, rpm), cross-
referenced against a second, independent transcription (SwingLab's
coach/data/pga_tour.json, cited there as "TrackMan PGA Tour Averages 2024")
for spin std -- the two agree on every mean they share, which is why the std
figures are trusted despite coming from the second source rather than the
chart itself.
  https://teeituprva.com/wp-content/uploads/2019/03/PGA-AVERAGES-INTERACTIVE.pdf

Only clubs where BOTH mean and std are published are listed here. The chart
gives spin mean for 5-Wood, Hybrid and 3/4-Iron too, but no variance -- and a
CV needs variance, not just a mean. Rather than borrow a neighboring club's
std (which is exactly the kind of plausible-looking invented number §6
prohibits), those clubs are left out on purpose. Wedges beyond PW (GW/SW/LW)
have no tour chart entry at all; every wedge-spin figure found elsewhere was
an unsourced blog "ballpark range", not a citable measurement.

Callers must treat a club missing from TOUR_SPIN_CV_BY_CLUB as UNRATED for
Spin Control, never as zero or average -- see spin_control_ratio() in
index.py.
"""
from __future__ import annotations

# club name (matches the "club" field on a shot dict, e.g. my_bag.json's
# naming) -> (spin mean rpm, spin std rpm), tour data only.
TOUR_SPIN_RPM_BY_CLUB: dict[str, tuple[float, float]] = {
    "Driver": (2686.0, 300.0),
    "3 Wood": (3655.0, 400.0),
    "5 Iron": (5361.0, 500.0),
    "6 Iron": (6231.0, 500.0),
    "7 Iron": (7097.0, 500.0),
    "8 Iron": (7998.0, 600.0),
    "9 Iron": (8647.0, 600.0),
    "PW": (9304.0, 700.0),
}

# Tour coefficient of variation per club (std / mean), the target Spin
# Control measures a player's own CV against. Derived, not separately cited --
# recompute from TOUR_SPIN_RPM_BY_CLUB if that table ever changes.
TOUR_SPIN_CV_BY_CLUB: dict[str, float] = {
    club: std / mean for club, (mean, std) in TOUR_SPIN_RPM_BY_CLUB.items()
}
