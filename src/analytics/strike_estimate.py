"""Approximate strike location, built only from the golfer's own marks.

The Nova measures ball flight, not face contact, and the ball-flight
inversions that were tried (smash residual, sidespin residual) proved
unfalsifiable on real data. So the only honest "approximate strike" is:

  none    -- no marks for this club: the sweet spot, drawn as a wide ring.
  median  -- the median of the golfer's marks for this club, ring radius =
             their spread. "Where you usually hit it."
  model   -- a per-club ball-flight -> mark regression, used ONLY when it
             beats the plain median on held-out marks. Promoted per club,
             re-evaluated on every call, and the label says so.

Every estimate is drawn as a ring, never a dot, and is labelled EST. A mark
or a reported reading always outranks it (see `contact_location`).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from .strike import FACE_MAX_H_MM, FACE_MAX_V_MM, contact_location, finite_number

MIN_RADIUS_MM = 5.0          # a tight cluster still reads as approximate
MAX_RADIUS_MM = 16.0
MODEL_MIN_MARKS = 20         # below this a fit is noise; stay on the median
MODEL_MIN_GAIN = 0.85        # model must cut held-out error to <= 85% of the median's
_FEATURES = ("spin_axis_degrees", "vertical_launch_angle_degrees", "total_spin_rpm")


@dataclass(frozen=True)
class StrikeEstimate:
    horizontal_mm: float
    vertical_mm: float
    radius_mm: float
    basis: str            # "none" | "median" | "model"
    marks: int

    @property
    def label(self) -> str:
        if self.basis == "none":
            return "EST · no marks yet"
        n = f"{self.marks} mark{'' if self.marks == 1 else 's'}"
        if self.basis == "model":
            return f"EST · model from {n}"
        return f"EST · usual spot from {n}"


def _identity(shot: dict[str, Any]):
    return shot.get("timestamp_ns") or shot.get("shotId")


def _features(shot: dict[str, Any]) -> list[float] | None:
    vals = []
    for key in _FEATURES:
        v = finite_number(shot.get(key))
        if v is None:
            return None
        vals.append(float(v))
    return vals


def labelled_marks(shot: dict[str, Any], history: list[dict[str, Any]]):
    """(features_or_None, h, v) for every marked shot of the same club,
    excluding the shot being estimated (by identity and by object)."""
    club = shot.get("club") if isinstance(shot, dict) else None
    ident = _identity(shot) if isinstance(shot, dict) else None
    out = []
    for s in history:
        if not isinstance(s, dict) or s is shot or s.get("club") != club:
            continue
        if ident is not None and _identity(s) == ident:
            continue
        c = contact_location(s)
        if c.source != "marked" or not c.complete:
            continue
        out.append((_features(s), float(c.horizontal_mm), float(c.vertical_mm)))
    return out


def _fit(rows):
    """Least squares y = b0 + b·x for each axis, via normal equations.
    Returns (coef_h, coef_v) or None when the system is singular."""
    xs = [[1.0] + r[0] for r in rows]
    n, k = len(xs), len(xs[0])
    # Standardise features so a 6000-rpm column does not swamp the solve.
    means = [sum(x[j] for x in xs) / n for j in range(k)]
    sds = [max(1e-9, statistics.pstdev([x[j] for x in xs])) if j else 1.0 for j in range(k)]
    z = [[(x[j] - means[j]) / sds[j] if j else 1.0 for j in range(k)] for x in xs]
    # Ridge: a tiny diagonal keeps the solve stable on collinear features.
    ata = [[sum(a[i] * a[j] for a in z) + (1e-3 if i == j and i else 0.0) for j in range(k)] for i in range(k)]

    def solve(rhs):
        m = [row[:] + [rhs[i]] for i, row in enumerate(ata)]
        for col in range(k):
            piv = max(range(col, k), key=lambda r: abs(m[r][col]))
            if abs(m[piv][col]) < 1e-12:
                return None
            m[col], m[piv] = m[piv], m[col]
            for r in range(k):
                if r != col:
                    f = m[r][col] / m[col][col]
                    for cc in range(col, k + 1):
                        m[r][cc] -= f * m[col][cc]
        return [m[i][k] / m[i][i] for i in range(k)]

    ch = solve([sum(a[i] * r[1] for a, r in zip(z, rows)) for i in range(k)])
    cv = solve([sum(a[i] * r[2] for a, r in zip(z, rows)) for i in range(k)])
    if ch is None or cv is None:
        return None
    return (ch, cv, means, sds)


def _predict(model, feats):
    ch, cv, means, sds = model
    x = [1.0] + feats
    z = [(x[j] - means[j]) / sds[j] if j else 1.0 for j in range(len(x))]
    return (sum(a * b for a, b in zip(ch, z)), sum(a * b for a, b in zip(cv, z)))


def _median_point(rows):
    return (statistics.median(r[1] for r in rows), statistics.median(r[2] for r in rows))


def _err(pred, actual):
    return ((pred[0] - actual[0]) ** 2 + (pred[1] - actual[1]) ** 2) ** 0.5


def _model_beats_median(rows) -> bool:
    """5-fold held-out comparison on this club's marks only."""
    if len(rows) < MODEL_MIN_MARKS:
        return False
    folds = 5
    e_model = e_median = 0.0
    for f in range(folds):
        test = [r for i, r in enumerate(rows) if i % folds == f]
        train = [r for i, r in enumerate(rows) if i % folds != f]
        if not test or len(train) < 4:
            return False
        model = _fit(train)
        if model is None:
            return False
        med = _median_point(train)
        for r in test:
            actual = (r[1], r[2])
            e_median += _err(med, actual)
            e_model += _err(_predict(model, r[0]), actual)
    return e_median > 0 and e_model <= MODEL_MIN_GAIN * e_median


def _clamp(h, v):
    return (max(-FACE_MAX_H_MM, min(FACE_MAX_H_MM, h)),
            max(-FACE_MAX_V_MM, min(FACE_MAX_V_MM, v)))


def estimate(shot: dict[str, Any], history: list[dict[str, Any]]) -> StrikeEstimate:
    """The honest approximation for `shot`, from the golfer's marks in `history`."""
    rows = labelled_marks(shot, history)
    if not rows:
        return StrikeEstimate(0.0, 0.0, MAX_RADIUS_MM, "none", 0)
    h, v = _median_point(rows)
    # Spread: median distance of the marks from their median point.
    spread = statistics.median(_err((h, v), (r[1], r[2])) for r in rows) if len(rows) > 1 else 0.0
    radius = max(MIN_RADIUS_MM, min(MAX_RADIUS_MM, spread * 1.5))
    basis = "median"
    feats = _features(shot) if isinstance(shot, dict) else None
    with_feats = [r for r in rows if r[0] is not None]
    if feats is not None and _model_beats_median(with_feats):
        model = _fit(with_feats)
        if model is not None:
            h, v = _predict(model, feats)
            basis = "model"
    h, v = _clamp(h, v)
    return StrikeEstimate(round(h, 1), round(v, 1), round(radius, 1), basis, len(rows))
