"""The browser surfaces must agree with the desktop app about aim.

obs_server owns browser/API/WebSocket state, so the correction has to be
applied there too -- otherwise the overlay on stream shows a different offline
number than the shot table three feet away.
"""
import json

import pytest

import obs_server
from src.analytics.aim import save_aim_offset


@pytest.fixture
def aim_file(tmp_path, monkeypatch):
    """Point obs_server at a throwaway aim file and clear its cache."""
    path = tmp_path / "aim.json"
    monkeypatch.setattr(obs_server, "AIM_FILE", path)
    obs_server.obs_state.invalidate_aim_cache()
    yield path
    obs_server.obs_state.invalidate_aim_cache()


SHOT = {
    "shotId": "abc123",
    "horizontal_launch_angle_degrees": 2.0,
    "open_golf_coach": {
        "us_customary_units": {
            "carry_distance_yards": 158.0,
            "offline_distance_yards": 5.5,
        }
    },
}


def test_uncalibrated_server_serves_the_shot_unchanged(aim_file):
    out = obs_server.obs_state.aim_corrected(SHOT)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(2.0)


def test_server_applies_a_saved_offset(aim_file):
    save_aim_offset(2.0, path=aim_file)

    out = obs_server.obs_state.aim_corrected(SHOT)

    assert out["horizontal_launch_angle_degrees"] == pytest.approx(0.0)
    us = out["open_golf_coach"]["us_customary_units"]
    assert abs(us["offline_distance_yards"]) < abs(5.5)


def test_recalibrating_takes_effect_without_a_restart(aim_file):
    """A user calibrating mid-session must not have to restart OBS."""
    save_aim_offset(0.0, path=aim_file)
    assert obs_server.obs_state.aim_corrected(SHOT)[
        "horizontal_launch_angle_degrees"
    ] == pytest.approx(2.0)

    save_aim_offset(2.0, path=aim_file)
    obs_server.obs_state.invalidate_aim_cache()

    assert obs_server.obs_state.aim_corrected(SHOT)[
        "horizontal_launch_angle_degrees"
    ] == pytest.approx(0.0)


def test_the_stored_shot_is_never_mutated_by_serving_it(aim_file):
    save_aim_offset(2.0, path=aim_file)
    original = json.dumps(SHOT, sort_keys=True)

    obs_server.obs_state.aim_corrected(SHOT)

    assert json.dumps(SHOT, sort_keys=True) == original


def test_latest_shot_is_stored_raw_and_corrected_on_read(aim_file):
    """push_shot preserves the native payload; correction happens at read."""
    save_aim_offset(2.0, path=aim_file)

    obs_server.obs_state.latest_shot = dict(SHOT)

    assert obs_server.obs_state.latest_shot[
        "horizontal_launch_angle_degrees"
    ] == pytest.approx(2.0)
    assert obs_server.obs_state.latest_shot_for_display()[
        "horizontal_launch_angle_degrees"
    ] == pytest.approx(0.0)


def test_no_latest_shot_is_handled(aim_file):
    obs_server.obs_state.latest_shot = None

    assert obs_server.obs_state.latest_shot_for_display() is None
