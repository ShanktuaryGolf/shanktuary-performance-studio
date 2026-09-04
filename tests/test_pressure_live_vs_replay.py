"""Live pressure must keep updating; reviewing an old shot must replay it.

Regression: the CoP trail and force/transfer timeline preferred ANY stored
trace on current_shot over live board data. While traces were broken that was
invisible (every lookup returned None). Once traces actually saved, the
just-landed shot always had one, so those panels froze on it and stopped
updating live -- while the metric strip, which preferred live, kept working.

Precedence these lock in:
  1. Deliberately reviewing an older shot  -> that shot's stored trace
  2. Boards streaming fresh frames         -> live
  3. Otherwise                             -> stored trace if any, else live
"""
import sys
import time

import pytest

sys.path.insert(0, "/home/sean/sps")

from src.processing.pressure import PressureTraceStore, shot_trace_id


def _frames(n=6, tag=0.0, ts=None):
    base = time.time() if ts is None else ts
    return [{"cop_x": tag, "cop_y": 0.0, "total_kg": 80.0, "phase": "Impact",
             "timestamp": base + i * 0.016} for i in range(n)]


@pytest.fixture
def app(tmp_path):
    import shanktuary_performance_studio as studio
    import obs_server

    a = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    a.trace_store = PressureTraceStore(str(tmp_path))
    a._trace_cache = studio.OrderedDict()
    a.TRACE_CACHE_MAX = 8

    older = {"timestamp_ns": 111, "has_pressure_trace": True}
    newer = {"timestamp_ns": 222, "has_pressure_trace": True}
    a.trace_store.save(shot_trace_id(older), _frames(tag=1.0))
    a.trace_store.save(shot_trace_id(newer), _frames(tag=2.0))

    session = {"shots": [older, newer]}
    a.sessions = [session]
    a.active_session_index = 0
    a.selected_shot_index = 1          # newest selected, as after a shot lands
    a.current_shot = newer
    a.swing_lab_history = _frames(tag=9.0)   # "live" frames

    sentinel = object()
    original = getattr(obs_server, "pressure_manager", sentinel)

    class PM:
        latest_frame = None

    obs_server.pressure_manager = PM()

    yield a, obs_server, older, newer

    if original is sentinel:
        try:
            del obs_server.pressure_manager
        except AttributeError:
            pass
    else:
        obs_server.pressure_manager = original


def _go_live(obs_server):
    obs_server.pressure_manager.latest_frame = {"timestamp": time.time(),
                                                "total_kg": 80.0}


def test_live_wins_on_the_newest_shot(app):
    """The regression: after a shot lands the panels must stay live."""
    a, obs, _older, _newer = app
    _go_live(obs)

    trail, is_stored = a.pressure_display_trail()
    assert not is_stored, "panels froze on the stored trace instead of live"
    assert trail[0]["cop_x"] == 9.0


def test_selecting_an_older_shot_replays_that_shot(app):
    a, obs, older, _newer = app
    _go_live(obs)                      # boards still streaming...
    a.selected_shot_index = 0          # ...but the user clicked back
    a.current_shot = older

    trail, is_stored = a.pressure_display_trail()
    assert is_stored, "reviewing an old shot must show its trace"
    assert trail[0]["cop_x"] == 1.0, "showed the wrong shot's trace"


def test_stale_board_frames_do_not_count_as_live(app):
    """latest_frame lingers after the boards stop; presence != liveness."""
    a, obs, _older, _newer = app
    obs.pressure_manager.latest_frame = {"timestamp": time.time() - 30.0}

    trail, is_stored = a.pressure_display_trail()
    assert is_stored, "a 30s-old frame must not be treated as live"
    assert trail[0]["cop_x"] == 2.0


def test_no_boards_falls_back_to_the_stored_trace(app):
    a, obs, _older, _newer = app
    obs.pressure_manager.latest_frame = None

    trail, is_stored = a.pressure_display_trail()
    assert is_stored
    assert trail[0]["cop_x"] == 2.0


def test_no_boards_and_no_trace_gives_live_history(app):
    a, obs, _older, _newer = app
    obs.pressure_manager.latest_frame = None
    a.current_shot = None

    trail, is_stored = a.pressure_display_trail()
    assert not is_stored
    assert trail[0]["cop_x"] == 9.0


def test_is_reviewing_past_shot_only_for_older_selections(app):
    a, _obs, older, _newer = app

    a.selected_shot_index = 1
    assert not a.is_reviewing_past_shot(), "newest selected is the live case"

    a.selected_shot_index = 0
    a.current_shot = older
    assert a.is_reviewing_past_shot()

    a.selected_shot_index = -1
    assert not a.is_reviewing_past_shot()


def test_board_liveness_thresholds(app):
    a, obs, _older, _newer = app

    obs.pressure_manager.latest_frame = None
    assert not a.board_is_streaming()

    obs.pressure_manager.latest_frame = {"timestamp": time.time()}
    assert a.board_is_streaming()

    obs.pressure_manager.latest_frame = {"timestamp": time.time() - 5.0}
    assert not a.board_is_streaming()

    # A frame with no timestamp is trusted rather than discarded.
    obs.pressure_manager.latest_frame = {"total_kg": 80.0}
    assert a.board_is_streaming()
