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


# --- the same bug class in the shell/sidebar renderers -------------------

def test_no_shell_renderer_stringifies_a_handed_field_directly():
    """str(ogc.get("shot_name")) paints {'left_handed': ..., 'right_handed': ...}
    straight onto the sidebar. It did, at (276, 262), over the shot list."""
    import re
    bad = []
    for path in sorted(LEGACY.glob("*.py")):
        src = path.read_text()
        for n, line in enumerate(src.splitlines(), 1):
            if re.search(r'str\(\s*ogc\.get\(\s*["\']shot_(name|rank)["\']', line):
                bad.append(f"{path.name}:{n}")
    assert not bad, "handed field stringified without resolving: " + ", ".join(bad)


def test_shell_shot_name_helper_resolves_handedness():
    import shell_redesign as shell

    handed = {"right_handed": "Pull Fade", "left_handed": "Push Draw"}
    assert shell._shot_shape({"shot_name": handed}) == "Pull Fade"
    assert shell._shot_shape({"shot_name": handed}, FakeApp(True)) == "Push Draw"
    assert shell._shot_shape({"shot_name": "Straight"}) == "Straight"
    assert shell._shot_shape({}) == ""


# --- hero band layout ----------------------------------------------------

def test_the_shot_name_is_clamped_to_its_identity_column():
    """"Straight Fade" at 28pt is wider than the identity column, so it ran
    into the Carry metric. The renderer must shrink it, never overlap."""
    tk = pytest.importorskip("tkinter")
    import overview_redesign_v7 as v7

    assert hasattr(v7, "_fit_shot_name"), "no helper to size the shot name"
    try:
        root = tk.Tk()  # tkfont.measure needs a root window
    except Exception:
        pytest.skip("no display")
    try:
        base = 28
        assert v7._fit_shot_name("Straight Fade", 240, base) < base
        assert v7._fit_shot_name("Draw", 240, base) == base
    finally:
        root.destroy()


def test_no_hero_text_collides_on_the_default_shot_view():
    """Renders the real app and checks the top band for overlapping text."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display")
    try:
        root.geometry("1600x950")
        from src.ui.desktop import ShanktuaryDesktopApp

        app = ShanktuaryDesktopApp(root)
        app.view_mode = 9
        app.draw_screen()
        root.update_idletasks()

        boxes = []
        for item in app.canvas.find_all():
            if app.canvas.type(item) != "text":
                continue
            b = app.canvas.bbox(item)
            if b and 80 < b[1] < 200 and b[0] > 300:
                boxes.append((b, app.canvas.itemcget(item, "text")))

        # Tk bboxes include a pixel or two of glyph padding, and adjacent
        # metric columns legitimately sit tight at narrow window widths. Only
        # a substantial overlap in BOTH axes is a real collision -- the bug
        # this guards against was a 306px label running ~90px into the next
        # column.
        clashes = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, _ = boxes[i]
                d, _ = boxes[j]
                ox = min(a[2], d[2]) - max(a[0], d[0])
                oy = min(a[3], d[3]) - max(a[1], d[1])
                if ox > 3 and oy > 3:
                    clashes.append(
                        f"{boxes[i][1][:18]!r}/{boxes[j][1][:18]!r} ({ox}x{oy}px)"
                    )
        assert not clashes, "overlapping hero text: " + ", ".join(clashes)
    finally:
        root.destroy()
