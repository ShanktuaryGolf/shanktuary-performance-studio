"""Shot-name labels must follow the aim correction.

OpenGolfCoach computes shot_name ("Pull Fade", "Straight Draw") from the raw
device-frame angles. Once an aim offset is applied the start-line half of that
label is stale: a shot that becomes dead straight still reads "Pull Fade", so
the shot list looks unchanged after calibrating even though every number moved.
"""
import pytest

from src.analytics.aim import relabel_shot_name


def test_an_uncalibrated_shot_keeps_its_label_verbatim():
    assert relabel_shot_name("Pull Fade", -5.2, 0.0) == "Pull Fade"


def test_the_start_word_follows_the_corrected_start_line():
    """A 'pull' that was really the device pointing left becomes straight."""
    assert relabel_shot_name("Pull Fade", -0.5, 2.0) == "Straight Fade"


def test_a_straight_shot_can_become_a_push():
    assert relabel_shot_name("Straight Draw", 4.5, -2.0) == "Push Draw"


def test_a_straight_shot_can_become_a_pull():
    assert relabel_shot_name("Straight Fade", -4.5, 2.0) == "Pull Fade"


def test_the_curve_word_is_never_touched():
    """Spin axis is unaffected by where the device points, so curve is valid."""
    for curve in ("Hook", "Draw", "Fade", "Slice"):
        out = relabel_shot_name(f"Pull {curve}", 0.0, 2.0)
        assert out == f"Straight {curve}"


def test_a_bare_curve_label_gains_no_start_word():
    """'Fade' with no start word is OGC's phrasing; do not invent one."""
    assert relabel_shot_name("Fade", 0.2, 2.0) == "Fade"


def test_a_bare_start_word_is_still_corrected():
    assert relabel_shot_name("Pull", -0.4, 2.0) == "Straight"
    assert relabel_shot_name("Push", -5.0, 2.0) == "Pull"


def test_the_baby_branch_is_left_alone():
    """OGC names near-zero shots by sign under its own rule we cannot recover."""
    assert relabel_shot_name("Baby Push Draw", -1.0, 2.0) == "Baby Push Draw"


def test_worm_burner_is_left_alone():
    """A launch-angle verdict, not a direction one."""
    assert relabel_shot_name("Worm Burner", -0.2, 2.0) == "Worm Burner"


def test_an_empty_or_missing_name_is_survived():
    assert relabel_shot_name("", 1.0, 2.0) == ""
    assert relabel_shot_name(None, 1.0, 2.0) is None


@pytest.mark.parametrize(
    "hla,expected",
    [
        (-3.01, "Pull"),
        (-2.99, "Straight"),
        (0.0, "Straight"),
        (2.99, "Straight"),
        (3.01, "Push"),
    ],
)
def test_the_start_thresholds_match_opengolfcoach(hla, expected):
    """+-3.0 deg, recovered from real data: 28/28 shots, and both +-2.5 and
    +-3.5 misclassify. See tests/test_aim_labels.py::test_recovered_threshold.
    """
    assert relabel_shot_name("Straight Fade", hla, 1.0).split()[0] == expected


def test_recovered_threshold_reproduces_every_stored_label():
    """The +-3.0 boundary is a recovered OGC constant, not a chosen one.

    The calibration data is a local session-history file rather than a tracked
    repository fixture. Keep validating it when present, but do not make a clean
    checkout or CI environment fail simply because that private/local history is
    intentionally absent.
    """
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "shanktuary_session_history.json"
    if not path.exists():
        pytest.skip("local shanktuary_session_history.json fixture is not present")

    data = json.loads(path.read_text())
    shots = [s for sess in data["sessions"] for s in sess.get("shots", [])]

    checked = 0
    for s in shots:
        name = s["open_golf_coach"]["shot_name"]["right_handed"]
        if "Baby" in name or "Worm" in name:
            continue
        if not any(w in name for w in ("Pull", "Push", "Straight")):
            continue
        hla = s["horizontal_launch_angle_degrees"]
        # Relabelling with a zero offset must reproduce OGC exactly.
        assert relabel_shot_name(name, hla, 0.0) == name
        checked += 1

    assert checked >= 25, f"expected the real session to exercise this, got {checked}"
