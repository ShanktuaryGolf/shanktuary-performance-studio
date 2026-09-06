"""Combined-surface audit: src/analytics/__init__.py + index.py + obs_server.py.

Read-only audit findings, pinned as regression tests rather than "fixed" in
source, because neither has a real consumer or corrupts the primary contract
today (see docstrings on each test for the reasoning):

  * `GET /api/index`'s backward-compatible flat per-club keys (added
    alongside the overall-result fields) can collide with one of the fixed
    top-level keys ("score", "clubs", etc.) if a club is literally named
    that. `load_index()` already refuses to let a colliding club shadow the
    real field -- it just silently omits that club from the flat view. The
    canonical per-club data under `data["clubs"][name]` is unaffected. No
    UI/JS currently reads the flat view (grep confirms), so this is a
    latent edge case, not touched here -- pinned so a future change can't
    make it worse (e.g. by letting a club clobber `score`/`tier`).
  * Every JSON shape the endpoint can emit is checked end-to-end for
    non-finite floats / non-primitive leakage, on top of the existing
    parse-only assertions in test_index_server.py.
"""
import json
import math

import obs_server
from src.analytics import IndexTier, player_shanktuary_index


def _sample_shot(bs=90.0, carry=None, club="7 Iron"):
    us = {"ball_speed_mph": bs}
    if carry is not None:
        us["carry_distance_yards"] = carry
    return {
        "club": club,
        "total_spin_rpm": 6500.0,
        "vertical_launch_angle_degrees": 18.0,
        "spin_axis_degrees": 1.0,
        "open_golf_coach": {"us_customary_units": us},
    }


def _write_history(tmp_path, shots, is_left_handed=False):
    history_file = tmp_path / "session_history.json"
    history_file.write_text(json.dumps({
        "sessions": [{"shots": shots}],
        "is_left_handed": is_left_handed,
    }))
    return history_file


# --- reserved top-level keys vs. a colliding club name ---------------------

def test_a_club_named_after_a_reserved_key_never_shadows_the_real_field(monkeypatch, tmp_path):
    shots = [_sample_shot(club="clubs") for _ in range(5)]
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", _write_history(tmp_path, shots))

    result = obs_server.obs_state.load_index()

    # the overall-result contract must win -- "clubs" stays the canonical
    # per-club dict, never overwritten by the like-named club's card.
    assert isinstance(result["clubs"], dict)
    assert "efficiency" not in result["clubs"]  # would indicate clobbering
    # the colliding club's data is not lost -- it is still reachable
    # canonically, just absent from the flat back-compat view.
    assert "clubs" in result["clubs"]


def test_a_club_named_score_never_corrupts_the_overall_score_field(monkeypatch, tmp_path):
    shots = [_sample_shot(club="score", bs=999.0) for _ in range(5)]
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", _write_history(tmp_path, shots))

    result = obs_server.obs_state.load_index()

    assert result["score"] is None or isinstance(result["score"], (int, float))
    assert "score" in result["clubs"]  # canonical data still present


# --- JSON safety of the full /api/index shape, both statuses ---------------

def _assert_json_safe(value):
    if isinstance(value, dict):
        for v in value.values():
            _assert_json_safe(v)
    elif isinstance(value, list):
        for v in value:
            _assert_json_safe(v)
    elif isinstance(value, float):
        assert math.isfinite(value), f"non-finite float in /api/index payload: {value!r}"
    elif isinstance(value, (int, str, bool)) or value is None:
        pass
    else:
        raise AssertionError(f"non-JSON-primitive type leaked into /api/index: {type(value)!r}")


def test_available_status_response_is_fully_json_safe(monkeypatch, tmp_path):
    shots = (
        [_sample_shot(bs=105.0, carry=250.0, club="Driver") for _ in range(35)]
        + [_sample_shot(bs=95.0, carry=150.0, club="7 Iron") for _ in range(35)]
        + [_sample_shot(bs=90.0, carry=100.0, club="PW") for _ in range(35)]
    )
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", _write_history(tmp_path, shots))

    result = obs_server.obs_state.load_index()
    assert result["status"] == "available"
    _assert_json_safe(result)
    assert json.loads(json.dumps(result)) == result


def test_insufficient_coverage_response_is_fully_json_safe(monkeypatch, tmp_path):
    shots = [_sample_shot(bs=105.0, carry=250.0, club="Driver") for _ in range(35)]
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", _write_history(tmp_path, shots))

    result = obs_server.obs_state.load_index()
    assert result["status"] == "insufficient_coverage"
    _assert_json_safe(result)
    assert json.loads(json.dumps(result)) == result


def test_tier_serializes_to_its_plain_string_value(monkeypatch, tmp_path):
    shots = (
        [_sample_shot(bs=105.0, carry=250.0, club="Driver") for _ in range(35)]
        + [_sample_shot(bs=95.0, carry=150.0, club="7 Iron") for _ in range(35)]
        + [_sample_shot(bs=90.0, carry=100.0, club="PW") for _ in range(35)]
    )
    result = player_shanktuary_index(shots)
    assert result["tier"] == IndexTier.INDEX
    assert json.loads(json.dumps(result))["tier"] == "Index"
