"""A shot must be able to find its own pressure trace again.

The capture/replay path was fully built but keyed on `shotId`, a field the
Nova payload never contains. Every trace therefore wrote to "None.json.gz",
each shot overwriting the last, and `get_pressure_trace()` looked up None and
found nothing -- so selecting an old shot showed live/stale board data instead
of that swing's trace.

These lock the identity down: distinct shots get distinct files, and a trace
is still retrievable after a restart (a fresh store object, cold cache).
"""
import sys

import pytest

sys.path.insert(0, "/home/sean/sps")

from src.processing.pressure import PressureTraceStore, shot_trace_id


def _frames(n=5, tag=0.0):
    return [{"cop_x": tag + i, "cop_y": 0.0, "total_kg": 80.0,
             "phase": "Impact", "rel_time_s": i * 0.016} for i in range(n)]


def test_nova_shot_without_shotid_still_gets_an_id():
    """The real Nova payload shape -- no shotId, but always timestamp_ns."""
    shot = {"timestamp_ns": 1787606488877579267, "club": "7i"}
    assert shot.get("shotId") is None
    assert shot_trace_id(shot) == "1787606488877579267"


def test_distinct_shots_never_collide():
    """The bug: every shot mapped to the same "None" key."""
    a = {"timestamp_ns": 1787606488877579267}
    b = {"timestamp_ns": 1787609965068996030}
    assert shot_trace_id(a) != shot_trace_id(b)


def test_explicit_shotid_still_wins_if_a_device_sends_one():
    shot = {"shotId": "abc123", "timestamp_ns": 1787606488877579267}
    assert shot_trace_id(shot) == "abc123"


def test_shot_with_no_usable_identity_returns_none():
    assert shot_trace_id({}) is None
    assert shot_trace_id(None) is None
    # A literal "None" string must not become a filename.
    assert shot_trace_id({"shotId": None, "timestamp_ns": None}) is None


def test_two_shots_round_trip_independently(tmp_path):
    """Save two traces, read both back -- the collision regression."""
    store = PressureTraceStore(str(tmp_path))
    a = {"timestamp_ns": 111, "has_pressure_trace": True}
    b = {"timestamp_ns": 222, "has_pressure_trace": True}

    store.save(shot_trace_id(a), _frames(tag=1.0))
    store.save(shot_trace_id(b), _frames(tag=2.0))

    got_a = store.load(shot_trace_id(a))
    got_b = store.load(shot_trace_id(b))
    assert got_a and got_b
    assert got_a[0]["cop_x"] == 1.0
    assert got_b[0]["cop_x"] == 2.0, "second shot overwrote the first"


def test_trace_survives_a_restart(tmp_path):
    """Selecting an old shot in a new session must still replay it."""
    shot = {"timestamp_ns": 999, "has_pressure_trace": True}
    PressureTraceStore(str(tmp_path)).save(shot_trace_id(shot), _frames(tag=7.0))

    # Fresh store == new app launch, nothing cached in memory.
    reloaded = PressureTraceStore(str(tmp_path)).load(shot_trace_id(shot))
    assert reloaded, "trace did not survive a restart"
    assert reloaded[0]["cop_x"] == 7.0


def test_app_lookup_finds_the_right_shots_trace(tmp_path, monkeypatch):
    """End to end through the app's own getter and finder."""
    import shanktuary_performance_studio as studio

    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.trace_store = PressureTraceStore(str(tmp_path))
    app._trace_cache = studio.OrderedDict()
    app.TRACE_CACHE_MAX = 8

    older = {"timestamp_ns": 111, "has_pressure_trace": True}
    newer = {"timestamp_ns": 222, "has_pressure_trace": True}
    app.sessions = [{"shots": [older, newer]}]

    app.trace_store.save(shot_trace_id(older), _frames(tag=1.0))
    app.trace_store.save(shot_trace_id(newer), _frames(tag=2.0))

    # Each shot gets ITS OWN trace, not the most recent one.
    assert app.get_pressure_trace(older)[0]["cop_x"] == 1.0
    assert app.get_pressure_trace(newer)[0]["cop_x"] == 2.0

    # And the capture callback can find the shot it belongs to.
    assert app._find_shot_by_id(shot_trace_id(older)) is older
    assert app._find_shot_by_id(shot_trace_id(newer)) is newer


def test_shot_without_a_trace_reports_nothing(tmp_path):
    import shanktuary_performance_studio as studio

    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.trace_store = PressureTraceStore(str(tmp_path))
    app._trace_cache = studio.OrderedDict()
    app.TRACE_CACHE_MAX = 8
    app.sessions = []

    # No has_pressure_trace flag -> must not invent one.
    assert app.get_pressure_trace({"timestamp_ns": 555}) is None
    assert app.get_pressure_trace(None) is None
