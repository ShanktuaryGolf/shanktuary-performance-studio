"""The redesigned renderers must survive the real Nova payload.

Six OpenGolfCoach fields are dicts keyed right_handed/left_handed, not scalars:
club_path_degrees, club_face_to_path_degrees, club_face_to_target_degrees,
shot_name, shot_rank, shot_color_rgb.

The design-integration renderers called float() and str() on them directly,
which crashed the app during __init__ for anyone with saved shots. CI and a
fresh install both passed because neither has any shots to draw.
"""
import sys
from pathlib import Path

import pytest

LEGACY = Path(__file__).resolve().parent.parent / "src" / "ui" / "_legacy"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

import overview_redesign as base  # noqa: E402


def handed_shot():
    """A shot shaped like the real payload, with handed dicts throughout."""
    return {
        "vertical_launch_angle_degrees": 18.4,
        "horizontal_launch_angle_degrees": -2.9,
        "total_spin_rpm": 6979.0,
        "open_golf_coach": {
            "smash_factor": 1.32,
            "spin_axis_degrees": 7.6,
            "descent_angle_degrees": 45.0,
            "hang_time_seconds": 5.9,
            "club_path_degrees": {"right_handed": 5.78, "left_handed": -5.78},
            "club_face_to_path_degrees": {"right_handed": -2.1, "left_handed": 2.1},
            "club_face_to_target_degrees": {"right_handed": 3.7, "left_handed": -3.7},
            "shot_name": {"right_handed": "Pull Fade", "left_handed": "Push Draw"},
            "us_customary_units": {
                "carry_distance_yards": 147.0,
                "total_distance_yards": 158.0,
                "ball_speed_mph": 109.0,
                "peak_height_yards": 31.0,
                "offline_distance_yards": -4.2,
            },
        },
    }


class FakeApp:
    """Stands in for ShanktuaryApp.resolve_handed without a Tk root."""

    def __init__(self, left_handed=False):
        self.is_left_handed = left_handed

    def resolve_handed(self, val, default=0.0):
        if isinstance(val, dict):
            key = "left_handed" if self.is_left_handed else "right_handed"
            return val.get(key, val.get("right_handed", default))
        if val is None:
            return default
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return -val if self.is_left_handed else val
        return val


def test_handed_fields_do_not_crash_the_renderer():
    """The blocking bug: float() on a dict raised TypeError during __init__."""
    v = base._values(handed_shot())
    assert isinstance(v["path"], float)
    assert isinstance(v["face_path"], float)
    assert isinstance(v["face_target"], float)


def test_a_shot_name_renders_as_text_not_a_dict():
    """str() on the dict would paint {'right_handed': 'Pull Fade', ...}."""
    assert base._values(handed_shot())["shape"] == "Pull Fade"


def test_without_an_app_the_right_handed_value_is_used():
    v = base._values(handed_shot())
    assert v["path"] == pytest.approx(5.78)
    assert v["shape"] == "Pull Fade"


def test_a_left_handed_player_gets_their_own_values():
    """Handedness is a property of the player, so the renderer must honour it
    rather than always reading right_handed."""
    v = base._values(handed_shot(), FakeApp(left_handed=True))
    assert v["path"] == pytest.approx(-5.78)
    assert v["face_path"] == pytest.approx(2.1)
    assert v["shape"] == "Push Draw"


def test_a_right_handed_app_matches_the_no_app_default():
    assert base._values(handed_shot(), FakeApp()) == base._values(handed_shot())


def test_plain_scalar_fields_still_work():
    """Not every payload uses handed dicts; older shots store plain numbers."""
    shot = handed_shot()
    shot["open_golf_coach"]["club_path_degrees"] = 4.0
    shot["open_golf_coach"]["shot_name"] = "Straight"
    v = base._values(shot)
    assert v["path"] == pytest.approx(4.0)
    assert v["shape"] == "Straight"


def test_an_empty_shot_does_not_crash():
    v = base._values(None)
    assert v["carry"] == 0.0
    assert v["shape"] == "Straight"


def test_a_missing_open_golf_coach_block_does_not_crash():
    assert base._values({"vertical_launch_angle_degrees": 12.0})["path"] == 0.0
