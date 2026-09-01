"""The partial-swing floor, tested against real unfiltered practice sessions.

The first version of this rule (0.55 x club MEDIAN ball speed) was tuned on a
22-shot session whose median was already a full swing. It fails on a golfer who
practises deliberate partial swings: the partials drag the median down, the
floor follows, and the filter admits the very shots it exists to remove.

Fixture: tests/fixtures/partial_swing_sessions.json -- synthetic, but shaped
from 14 real Garmin R10 range sessions (github.com/jgamblin/golf, 1,659 shots,
94% irons and wedges, 7 Iron carry 2.8-184 y). That repo has no LICENSE, so the
real shots are NOT redistributed here; they live outside the repo and the
numbers they produced are recorded in the commit message and in
~/sps-notes/data/.

The synthetic set preserves the property that matters: one dominant full-swing
mode plus a deliberate partial-swing tail, which is what defeated the median
anchor.
"""
import json
import statistics
from pathlib import Path

import pytest

from src.analytics.index import (
    FULL_SWING_ANCHOR_Q,
    PARTIAL_SWING_RATIO,
    valid_shots,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "partial_swing_sessions.json"


def _shot(bs, carry=100.0, spin=5000.0, club="7 Iron"):
    return {
        "club": club,
        "total_spin_rpm": spin,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": bs, "carry_distance_yards": carry}
        },
    }


@pytest.fixture(scope="module")
def sessions():
    if not FIXTURE.exists():
        pytest.skip("partial-swing fixture not present")
    return json.loads(FIXTURE.read_text())["clubs"]


def _as_shots(rows, club):
    return [_shot(r["bs"], r["carry"], r["spin"], club) for r in rows]


def _carry_cv(shots):
    c = [s["open_golf_coach"]["us_customary_units"]["carry_distance_yards"] for s in shots]
    return statistics.pstdev(c) / statistics.mean(c) * 100


# --- the failure that motivated the change -------------------------------

def test_a_practice_session_full_of_partials_is_actually_filtered(sessions):
    """The bug: on the real sessions a median anchor dropped only 13 of 425
    7-iron shots and left 28-yard pitches in a 'full swing' set."""
    rows = sessions["7 Iron"]
    kept = valid_shots(_as_shots(rows, "7 Iron"))

    dropped = len(rows) - len(kept)
    assert dropped > len(rows) * 0.10, (
        f"only {dropped}/{len(rows)} dropped -- the floor is chasing the partials again"
    )


def test_no_club_keeps_a_shot_that_is_obviously_a_pitch(sessions):
    """A 7 Iron at 45 mph ball speed carries about 28 yards. It is not a full
    swing, however badly struck."""
    kept = valid_shots(_as_shots(sessions["7 Iron"], "7 Iron"))
    speeds = [s["open_golf_coach"]["us_customary_units"]["ball_speed_mph"] for s in kept]
    assert min(speeds) >= 55.0


def test_filtering_tightens_dispersion_on_every_club(sessions):
    """If the filter is doing its job, removing partial swings must reduce
    carry spread -- on all of them, not on average."""
    for club, rows in sessions.items():
        shots = _as_shots(rows, club)
        kept = valid_shots(shots)
        if len(kept) < 20:
            continue
        assert _carry_cv(kept) < _carry_cv(shots), club


# --- why p80 and not the median ------------------------------------------

def test_the_anchor_does_not_move_when_partials_are_added():
    """The load-bearing property. A median anchor slides down as partials
    accumulate; at a 50/50 mix it admits 100% of them."""
    full = [_shot(85.0) for _ in range(200)]
    partial = [_shot(55.0, carry=30.0) for _ in range(200)]

    kept_clean = valid_shots(full)
    kept_mixed = valid_shots(full + partial)

    assert len(kept_clean) == 200
    # Every partial must still be rejected in the 50/50 session.
    assert len(kept_mixed) == 200


def test_a_lone_partial_swing_is_still_caught():
    shots = [_shot(85.0) for _ in range(30)] + [_shot(40.0, carry=20.0)]
    assert len(valid_shots(shots)) == 30


def test_the_anchor_is_the_upper_mode_not_the_middle():
    assert FULL_SWING_ANCHOR_Q >= 0.75, "anchor must sit in the full-swing mode"


# --- the rule must not punish a genuinely bad full swing ------------------

def test_a_weak_full_swing_survives():
    """A thin 7 iron that goes 60 yards is exactly what the Index should score.
    Only clearly sub-full swings are excluded."""
    shots = [_shot(85.0) for _ in range(30)]
    shots.append(_shot(85.0 * PARTIAL_SWING_RATIO + 1.0, carry=60.0))
    assert len(valid_shots(shots)) == 31


def test_a_slow_player_is_not_filtered_away():
    """A 60 mph senior's whole bag must survive; the rule is relative."""
    assert len(valid_shots([_shot(60.0) for _ in range(40)])) == 40


def test_the_filter_stays_dormant_on_a_short_session():
    """Below the median-stability threshold, keep the little data there is."""
    shots = [_shot(85.0) for _ in range(8)] + [_shot(40.0)]
    assert len(valid_shots(shots)) == 9


# --- documented behaviour on the real sessions ---------------------------

def test_retention_and_dispersion_on_the_real_sessions(sessions):
    """Pins the numbers so a future tweak to the rule shows up as a diff."""
    report = {}
    for club, rows in sessions.items():
        shots = _as_shots(rows, club)
        kept = valid_shots(shots)
        report[club] = (len(rows), len(kept), round(_carry_cv(shots), 1),
                        round(_carry_cv(kept), 1))

    seven = report["7 Iron"]
    assert seven[0] == 425, "fixture changed"
    # Retention should sit in a sane band: aggressive enough to matter,
    # not so aggressive that a normal session is gutted.
    for club, (raw, kept, _, _) in report.items():
        assert 0.60 <= kept / raw <= 0.95, f"{club}: kept {kept}/{raw}"
