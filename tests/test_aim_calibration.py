"""Aim calibration -- correcting a mis-squared launch monitor.

The Nova has no aim calibration. A device sitting a couple of degrees off
square makes every shot read as a push or a pull, which silently biases any
directional metric. These tests define the correction.
"""
import math

import pytest

from src.analytics.aim import (
    apply_aim,
    load_aim_offset,
    offset_from_geometry,
    offset_from_shots,
    save_aim_offset,
)


def test_zero_offset_leaves_a_shot_untouched():
    shot = {
        "horizontal_launch_angle_degrees": 2.5,
        "open_golf_coach": {
            "us_customary_units": {
                "carry_distance_yards": 158.0,
                "offline_distance_yards": 6.0,
            }
        },
    }

    out = apply_aim(shot, 0.0)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(2.5)
    us = out["open_golf_coach"]["us_customary_units"]
    assert us["offline_distance_yards"] == pytest.approx(6.0)
    assert us["carry_distance_yards"] == pytest.approx(158.0)


def test_offset_is_subtracted_from_horizontal_launch():
    """A device aimed 2 deg right reports shots 2 deg left of the truth."""
    shot = {"horizontal_launch_angle_degrees": 2.5}

    out = apply_aim(shot, 2.0)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(0.5)


def test_a_dead_straight_shot_on_a_skewed_device_reads_straight_after_correction():
    shot = {"horizontal_launch_angle_degrees": -3.0}

    out = apply_aim(shot, -3.0)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(0.0)


def test_the_original_shot_is_not_mutated():
    shot = {"horizontal_launch_angle_degrees": 2.5}

    apply_aim(shot, 2.0)

    assert shot["horizontal_launch_angle_degrees"] == pytest.approx(2.5)


def test_offline_is_rotated_not_just_shifted():
    """Offline is a lateral distance, so correcting aim rotates the landing point.

    A device with a +2 deg zero error reports a genuinely straight 158 y shot as
    starting 2 deg right and finishing ~5.5 y right. Correcting must bring the
    landing point back to the target line, not merely tweak the angle.
    """
    carry = 158.0
    bias = 2.0
    shot = {
        "horizontal_launch_angle_degrees": bias,
        "open_golf_coach": {
            "us_customary_units": {
                "carry_distance_yards": carry,
                "offline_distance_yards": carry * math.sin(math.radians(bias)),
            }
        },
    }

    out = apply_aim(shot, bias)

    us = out["open_golf_coach"]["us_customary_units"]
    assert us["offline_distance_yards"] == pytest.approx(0.0, abs=0.05)
    # Carry is a forward distance and must survive the rotation essentially intact.
    assert us["carry_distance_yards"] == pytest.approx(carry, abs=0.2)


def test_metric_offline_is_corrected_alongside_the_yard_value():
    carry_m = 144.5
    bias = 2.0
    shot = {
        "horizontal_launch_angle_degrees": bias,
        "open_golf_coach": {
            "carry_distance_meters": carry_m,
            "offline_distance_meters": carry_m * math.sin(math.radians(bias)),
            "us_customary_units": {},
        },
    }

    out = apply_aim(shot, bias)

    assert out["open_golf_coach"]["offline_distance_meters"] == pytest.approx(
        0.0, abs=0.05
    )


def test_a_shot_with_no_offline_fields_is_left_alone():
    shot = {"horizontal_launch_angle_degrees": 4.0, "open_golf_coach": {}}

    out = apply_aim(shot, 2.0)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(2.0)
    assert out["open_golf_coach"] == {}


def test_nested_payload_is_not_mutated():
    """The stored history dict must survive a corrected read untouched."""
    shot = {
        "horizontal_launch_angle_degrees": 2.0,
        "open_golf_coach": {
            "us_customary_units": {
                "carry_distance_yards": 158.0,
                "offline_distance_yards": 5.5,
            }
        },
    }

    apply_aim(shot, 2.0)

    us = shot["open_golf_coach"]["us_customary_units"]
    assert us["offline_distance_yards"] == pytest.approx(5.5)


# --------------------------------------------------------------------------
# Deriving the offset from a set of calibration shots
# --------------------------------------------------------------------------


def _shots(*angles):
    return [{"horizontal_launch_angle_degrees": a} for a in angles]


def test_offset_from_shots_needs_a_minimum_sample():
    """Too few shots must refuse to produce a calibration, not guess one."""
    assert offset_from_shots(_shots(2.0, 2.1, 1.9)) is None


def test_offset_from_shots_returns_the_median_start_line():
    shots = _shots(1.8, 2.0, 2.2, 1.9, 2.1, 2.0, 1.7, 2.3, 2.0, 2.1)

    assert offset_from_shots(shots) == pytest.approx(2.0, abs=0.05)


def test_one_wild_pull_cannot_set_the_calibration():
    """A single 20 deg yank must barely move the answer -- hence median, not mean."""
    clean = [2.0] * 9
    assert offset_from_shots(_shots(*clean, -20.0)) == pytest.approx(2.0, abs=0.05)


def test_shots_without_a_launch_angle_are_ignored():
    shots = _shots(2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0)
    shots.append({"ball_speed_meters_per_second": 50.0})

    assert offset_from_shots(shots) == pytest.approx(2.0, abs=0.05)


def test_the_offset_is_clamped_to_a_sane_range():
    """A 30 deg 'aim error' is a mis-set device or a hosel rocket, not calibration."""
    assert offset_from_shots(_shots(*([30.0] * 10))) == pytest.approx(5.0)
    assert offset_from_shots(_shots(*([-30.0] * 10))) == pytest.approx(-5.0)


def test_calibrating_then_applying_zeroes_the_bias():
    """End to end: a skewed device, calibrated, reads straight."""
    raw = _shots(2.4, 1.6, 2.0, 2.2, 1.8, 2.1, 1.9, 2.0, 2.3, 1.7)

    offset = offset_from_shots(raw)
    corrected = [apply_aim(s, offset)["horizontal_launch_angle_degrees"] for s in raw]

    assert sum(corrected) / len(corrected) == pytest.approx(0.0, abs=0.05)


# --------------------------------------------------------------------------
# Persistence -- per user, in the config dir, never in the repo
# --------------------------------------------------------------------------


def test_offset_round_trips_through_the_config_file(tmp_path):
    path = tmp_path / "aim.json"

    save_aim_offset(2.5, path=path)

    assert load_aim_offset(path=path) == pytest.approx(2.5)


def test_a_missing_config_file_means_no_correction(tmp_path):
    assert load_aim_offset(path=tmp_path / "absent.json") == pytest.approx(0.0)


def test_a_corrupt_config_file_means_no_correction(tmp_path):
    path = tmp_path / "aim.json"
    path.write_text("{ this is not json")

    assert load_aim_offset(path=path) == pytest.approx(0.0)


def test_a_stored_offset_beyond_the_sane_range_is_clamped_on_read(tmp_path):
    """Hand-edited config must not be able to skew every shot by 40 degrees."""
    path = tmp_path / "aim.json"
    path.write_text('{"aim_offset_deg": 40.0}')

    assert load_aim_offset(path=path) == pytest.approx(5.0)


def test_saving_creates_the_config_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "aim.json"

    save_aim_offset(-1.5, path=path)

    assert load_aim_offset(path=path) == pytest.approx(-1.5)


# --------------------------------------------------------------------------
# Handedness
# --------------------------------------------------------------------------


def test_the_offset_is_a_device_property_not_a_player_one():
    """The device is skewed the same way whoever swings at it.

    A left-hander hitting from the other side of the same mis-aimed unit still
    has that unit reporting angles shifted the same direction, so the stored
    offset must NOT be mirrored -- it is measured in the device frame.
    """
    lefty = {"horizontal_launch_angle_degrees": 2.5}
    righty = {"horizontal_launch_angle_degrees": 2.5}

    assert (
        apply_aim(lefty, 2.0)["horizontal_launch_angle_degrees"]
        == apply_aim(righty, 2.0)["horizontal_launch_angle_degrees"]
    )


# --------------------------------------------------------------------------
# Deriving the offset from room measurements (the QuadMAX-style path)
# --------------------------------------------------------------------------


def test_a_device_pointing_straight_has_no_offset():
    assert offset_from_geometry(distance_ft=12.0, lateral_in=0.0) == pytest.approx(0.0)


def test_offset_is_the_angle_between_the_aim_point_and_the_target():
    """12 ft to the screen, aim mark 6 in right of target -> atan(0.5/12)."""
    expected = math.degrees(math.atan2(6.0 / 12.0, 12.0))

    got = offset_from_geometry(distance_ft=12.0, lateral_in=6.0)

    assert got == pytest.approx(expected, abs=1e-9)
    assert got == pytest.approx(2.39, abs=0.01)


def test_left_of_target_is_a_negative_offset():
    assert offset_from_geometry(distance_ft=12.0, lateral_in=-6.0) == pytest.approx(
        -2.39, abs=0.01
    )


def test_the_same_lateral_error_matters_less_from_further_away():
    near = offset_from_geometry(distance_ft=8.0, lateral_in=6.0)
    far = offset_from_geometry(distance_ft=16.0, lateral_in=6.0)

    assert near > far > 0


def test_a_zero_or_negative_distance_is_refused():
    """No distance means no angle -- returning 0.0 would look like 'calibrated'."""
    assert offset_from_geometry(distance_ft=0.0, lateral_in=6.0) is None
    assert offset_from_geometry(distance_ft=-3.0, lateral_in=6.0) is None


def test_geometry_result_is_clamped_like_every_other_path():
    assert offset_from_geometry(distance_ft=1.0, lateral_in=48.0) == pytest.approx(5.0)
