"""Validate the REAL assets/range/js/physics.js, not a Python paraphrase of it.

The previous version of this file reimplemented the engine in Python and had
already drifted from the shipped JavaScript (different drag/lift coefficients,
different spin decay), so it could pass while the real range flew differently.
This runs the actual module under Node.

Carry reference points come from a held-out validation set of ~10,700 real
shots (TrackMan, a measured-spin Kaggle set, Foresight published rows, Garmin
R10 sessions). See tests/PHYSICS_VALIDATION.md.
"""
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PHYSICS = REPO / "assets" / "range" / "js" / "physics.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def carry(ball_speed, launch, spin, spin_axis=0.0, hla=0.0):
    """Carry in yards from the shipped engine (first ground contact)."""
    script = textwrap.dedent(f"""
        import {{ GolfPhysicsEngine }} from '{PHYSICS.as_uri()}';
        const e = new GolfPhysicsEngine();
        const t = e.calculateTrajectory({{
            ball_speed_mph: {ball_speed},
            vertical_launch_angle_degrees: {launch},
            horizontal_launch_angle_degrees: {hla},
            total_spin_rpm: {spin},
            spin_axis_degrees: {spin_axis},
        }});
        // Carry = FIRST ground contact, interpolated between samples.
        //
        // Do NOT use the last point with inFlight===true: the engine keeps that
        // flag set through the bounce phase, so it reports carry + bounce (10
        // yards long on a driver). Track the descending y crossing instead.
        const GROUND = 0.02135 * 1.09361;   // ball radius, yards
        let hit = null;
        for (let k = 1; k < t.length; k++) {{
            if (t[k - 1].y > GROUND && t[k].y <= GROUND) {{
                const f = (t[k - 1].y - GROUND) / (t[k - 1].y - t[k].y);
                hit = {{
                    x: t[k - 1].x + f * (t[k].x - t[k - 1].x),
                    z: t[k - 1].z + f * (t[k].z - t[k - 1].z),
                }};
                break;
            }}
        }}
        if (!hit) throw new Error('ball never landed');
        console.log(JSON.stringify({{
            carry: Math.hypot(hit.x, hit.z),
            offline: hit.x,
            apex: Math.max(...t.map(p => p.y)),
        }}));
    """)
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise AssertionError(f"node failed: {out.stderr[-400:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- carry accuracy at validated speeds ----------------------------------
# Tolerances are the held-out sd for that band, not hopeful guesses.

@pytest.mark.parametrize("bs,la,spin,expected,tol", [
    # Foresight published reference rows (measured, per club).
    (109, 18.4, 6979, 147, 12),   # 7 iron, slower swing
    (122, 15.1, 6585, 166, 12),   # 7 iron, faster swing
    (98,  23.0, 8025, 126, 12),   # 9 iron
    (91,  24.7, 8873, 117, 12),   # pitching wedge
    (141, 14.0, 2628, 220, 15),   # driver, slower swing
    (165, 11.2, 2685, 270, 16),   # driver, faster swing
])
def test_carry_matches_published_reference_rows(bs, la, spin, expected, tol):
    got = carry(bs, la, spin)["carry"]
    assert abs(got - expected) <= tol, f"{bs}mph -> {got:.1f}y, expected ~{expected}"


def test_the_long_drive_short_bias_is_gone():
    """The defect this refit fixed: the old coefficients flew 12 yards short
    at 160-180 mph because drag did not fall with speed."""
    got = carry(165, 11.2, 2685)["carry"]
    assert got > 255, f"long drive still short: {got:.1f}y"


# --- shape and monotonicity ----------------------------------------------

def test_more_ball_speed_carries_further():
    speeds = [80, 100, 120, 140, 160]
    carries = [carry(s, 14, 4000)["carry"] for s in speeds]
    assert carries == sorted(carries)


def test_there_is_an_optimal_launch_angle():
    """A physical model must have a maximum; a linear regression does not.
    This is why the empirical minigames model could not serve as a benchmark."""
    angles = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    carries = [carry(140, a, 2800)["carry"] for a in angles]
    best = angles[carries.index(max(carries))]
    assert 8 <= best <= 30, f"optimal launch {best} deg is not physical"


def test_spin_axis_curves_the_ball_the_right_way():
    """Positive spin axis = tilt right = fade for a right-hander, and +x is
    right. Getting this backwards made every fade fly as a draw."""
    assert carry(140, 14, 3000, spin_axis=+15)["offline"] > 5
    assert carry(140, 14, 3000, spin_axis=-15)["offline"] < -5


def test_a_wedge_flies_high_and_short():
    r = carry(81, 30.4, 9341)
    assert 80 <= r["carry"] <= 115
    assert r["apex"] > 20


# --- guardrails -----------------------------------------------------------

def test_drag_coefficient_stays_in_a_physical_band():
    """cd is clamped; without it the velocity term explodes as v -> 0 during
    the final descent."""
    src = PHYSICS.read_text()
    assert "Math.max(0.12" in src and "Math.min(0.60" in src


def test_low_speed_is_documented_as_unvalidated():
    """No data source covers ball speeds below ~50 mph. Anyone tuning chip
    flight needs to know they are extrapolating."""
    assert "NOT VALIDATED below" in PHYSICS.read_text()
