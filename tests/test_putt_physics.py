"""Run the shipped putt_physics.js under Node — sliding vs rolling + GSPro rollout."""
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PUTT = REPO / "assets" / "range" / "js" / "putt_physics.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def node(script):
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise AssertionError(f"node failed: {out.stderr[-600:]}")
    lines = [ln for ln in out.stdout.strip().splitlines() if ln]
    return json.loads(lines[-1])


def test_launch_along_z_still_matches_gspro():
    """Stimpmeter-style rollout (already rolling) must keep the GSPro curve."""
    script = textwrap.dedent(f"""
        import {{ simulateFlatPutt }} from '{PUTT.as_uri()}';
        const r = simulateFlatPutt(4.0, 10);
        console.log(JSON.stringify(r));
    """)
    r = node(script)
    assert r["stopped"]
    assert abs(r["errFt"]) < 0.25, r


def test_zero_spin_putt_skids_then_rolls():
    script = textwrap.dedent(f"""
        import {{ PuttSimulation, BALL_RADIUS }} from '{PUTT.as_uri()}';
        const sim = new PuttSimulation({{ stimp: 10, holes: [], greenRadius: 1e9 }});
        sim.position.set(0, BALL_RADIUS, 0);
        sim.hitBall(4.0, 0, 0, 0);
        let t = 0;
        while (sim.isMoving && t < 30) {{
            sim.updatePhysics(1 / 240);
            t += 1 / 240;
        }}
        console.log(JSON.stringify({{
            skidM: sim.skidDistanceM,
            ttfr: sim.timeToFullRollS,
            full: sim.fullRollReached,
            totalM: sim.totalRollM,
            stopped: !sim.isMoving,
        }}));
    """)
    r = node(script)
    assert r["full"] is True
    assert r["stopped"] is True
    assert r["skidM"] > 0.15
    assert r["ttfr"] > 0.05
    assert r["totalM"] > r["skidM"]


def test_pure_roll_launch_has_near_zero_skid():
    script = textwrap.dedent(f"""
        import {{ PuttSimulation, BALL_RADIUS, MPH_TO_MS }} from '{PUTT.as_uri()}';
        const speed = 4.0;
        const rpm = -(speed * MPH_TO_MS / BALL_RADIUS) * 30 / Math.PI;
        const sim = new PuttSimulation({{ stimp: 10, holes: [], greenRadius: 1e9 }});
        sim.position.set(0, BALL_RADIUS, 0);
        sim.hitBall(speed, rpm, 0, 0);
        let t = 0;
        while (sim.isMoving && t < 30) {{
            sim.updatePhysics(1 / 240);
            t += 1 / 240;
        }}
        console.log(JSON.stringify({{
            skidM: sim.skidDistanceM,
            ttfr: sim.timeToFullRollS,
            full: sim.fullRollReached,
        }}));
    """)
    r = node(script)
    assert r["full"] is True
    assert r["skidM"] < 0.08
    assert r["ttfr"] < 0.08


def test_backspin_skids_longer_than_zero_spin():
    script = textwrap.dedent(f"""
        import {{ PuttSimulation, BALL_RADIUS }} from '{PUTT.as_uri()}';
        function run(backspin) {{
            const sim = new PuttSimulation({{ stimp: 10, holes: [], greenRadius: 1e9 }});
            sim.position.set(0, BALL_RADIUS, 0);
            sim.hitBall(4.0, backspin, 0, 0);
            let t = 0;
            while (sim.isMoving && t < 30) {{
                sim.updatePhysics(1 / 240);
                t += 1 / 240;
            }}
            return {{ skidM: sim.skidDistanceM, ttfr: sim.timeToFullRollS }};
        }}
        console.log(JSON.stringify({{ zero: run(0), back: run(400) }}));
    """)
    r = node(script)
    assert r["back"]["skidM"] > r["zero"]["skidM"]
    assert r["back"]["ttfr"] > r["zero"]["ttfr"]
