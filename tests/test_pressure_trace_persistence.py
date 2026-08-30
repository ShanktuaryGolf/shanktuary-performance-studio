"""Tests for pressure trace persistence: derived metrics and the trace store.

Covers the bug these were written for -- a captured trace never reaching the
session file, because the capture completes ~3s after the shot is saved and
lands on a *copy* of the shot dict.
"""

import json
import os
import tempfile

import pytest

from src.processing.pressure.shot_metrics import derive_pressure_metrics
from src.processing.pressure.trace_store import PressureTraceStore


def make_frame(rel_t, phase="Address", pct_left=50.0, force_bw=1.0,
               torque=0.0, cop_x=0.0, cop_y=0.0):
    return {
        "timestamp": 1000.0 + rel_t,
        "rel_time_s": round(rel_t, 3),
        "total_kg": 80.0,
        "force_bw": force_bw,
        "pct_left": pct_left,
        "pct_right": round(100.0 - pct_left, 1),
        "left_pct_front": 50.0,
        "left_pct_back": 50.0,
        "right_pct_front": 50.0,
        "right_pct_back": 50.0,
        "cop_x": cop_x,
        "cop_y": cop_y,
        "torque_nm": torque,
        "phase": phase,
        "raw_cells": [5.0, 5.0, 5.0, 5.0],
    }


def realistic_trace():
    """A swing: address, backswing loading right, downswing, impact, finish."""
    frames = []
    # Address, -5.0s .. -1.2s
    for i in range(60):
        frames.append(make_frame(-5.0 + i * 0.0633, "Address", pct_left=50.0))
    # Backswing: weight moves onto the trail foot (pct_right rises to 62)
    for i in range(48):
        pct_left = 50.0 - (12.0 * i / 47.0)
        frames.append(make_frame(-1.2 + i * 0.0167, "Backswing",
                                 pct_left=round(pct_left, 1)))
    # Transition
    for i in range(13):
        frames.append(make_frame(-0.4 + i * 0.0167, "Transition",
                                 pct_left=38.0 + i))
    # Downswing into impact: weight drives to the lead foot
    for i in range(15):
        frames.append(make_frame(-0.19 + i * 0.0127, "Downswing",
                                 pct_left=51.0 + i * 1.4,
                                 force_bw=1.0 + i * 0.02,
                                 torque=i * 2.0,
                                 cop_x=i * 3.0))
    frames.append(make_frame(0.0, "Impact", pct_left=72.0, force_bw=1.31,
                             torque=31.5, cop_x=48.0))
    # Finish
    for i in range(60):
        frames.append(make_frame(0.05 + i * 0.05, "Follow-through",
                                 pct_left=80.0))
    return frames


class TestDerivedMetrics:
    def test_empty_trace_returns_none(self):
        assert derive_pressure_metrics(None) is None
        assert derive_pressure_metrics([]) is None

    def test_realistic_swing_produces_metrics(self):
        m = derive_pressure_metrics(realistic_trace())
        assert m is not None
        # Trail foot loaded to ~62% during the backswing
        assert m["peak_pct_right_backswing"] == pytest.approx(62.0, abs=0.5)
        # Lead foot at impact
        assert m["pct_left_at_impact"] == pytest.approx(72.0, abs=0.5)
        assert m["peak_force_bw"] == pytest.approx(1.31, abs=0.01)
        assert m["peak_torque_nm"] == pytest.approx(31.5, abs=0.1)
        assert m["frame_count"] == len(realistic_trace())

    def test_phase_durations(self):
        m = derive_pressure_metrics(realistic_trace())
        assert m["backswing_duration_s"] > 0
        assert m["downswing_duration_s"] > 0
        assert m["transition_duration_s"] > 0

    def test_cop_speed_is_positive(self):
        m = derive_pressure_metrics(realistic_trace())
        assert m["peak_cop_speed_mm_s"] > 0

    def test_missing_fields_yield_none_not_defaults(self):
        """A metric with no supporting data must be None, never a plausible
        stand-in -- an invented number silently corrupts later analysis."""
        bare = [{"rel_time_s": 0.0, "phase": "Address"}]
        m = derive_pressure_metrics(bare)
        assert m is None or m.get("peak_force_bw") is None

    def test_idle_trace_returns_none(self):
        """All-None metrics should not be stored as a row of nulls."""
        frames = [{"rel_time_s": i * 0.1, "phase": "Idle"} for i in range(20)]
        assert derive_pressure_metrics(frames) is None

    def test_impact_falls_back_to_nearest_zero(self):
        """Without an explicit Impact phase, rel_time_s==0 defines impact."""
        frames = [make_frame(-0.1, "Downswing", pct_left=60.0),
                  make_frame(0.01, "Downswing", pct_left=70.0),
                  make_frame(0.2, "Follow-through", pct_left=80.0)]
        m = derive_pressure_metrics(frames)
        assert m["pct_left_at_impact"] == pytest.approx(70.0, abs=0.1)

    def test_zero_dt_frames_do_not_produce_infinite_speed(self):
        frames = [make_frame(0.0, cop_x=0.0), make_frame(0.0, cop_x=50.0)]
        m = derive_pressure_metrics(frames)
        speed = (m or {}).get("peak_cop_speed_mm_s")
        assert speed is None or speed < 1e6


class TestTraceStore:
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            frames = realistic_trace()
            path = store.save("shot-123", frames)
            assert path and os.path.isfile(path)
            assert store.has("shot-123")
            back = store.load("shot-123")
            assert back is not None
            assert len(back) == len(frames)
            assert back[0]["phase"] == frames[0]["phase"]

    def test_missing_trace_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            assert store.load("never-saved") is None
            assert store.has("never-saved") is False

    def test_empty_frames_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            assert store.save("x", []) is None
            assert store.has("x") is False

    def test_unsafe_shot_id_cannot_escape_directory(self):
        """Shot ids come from the device and reach the filesystem."""
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            store.save("../../etc/passwd", [make_frame(0.0)])
            written = []
            for root, _dirs, files in os.walk(d):
                written += [os.path.join(root, f) for f in files]
            assert written, "nothing written"
            for p in written:
                assert os.path.realpath(p).startswith(os.path.realpath(d))

    def test_compression_is_worth_it(self):
        """The whole reason traces are not inline in the session file."""
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            frames = realistic_trace()
            path = store.save("sz", frames)
            raw = len(json.dumps(frames, indent=2))
            on_disk = os.path.getsize(path)
            assert on_disk < raw / 4, (
                f"expected >4x saving, got {raw} -> {on_disk}")

    def test_corrupt_file_returns_none_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            store.save("bad", [make_frame(0.0)])
            with open(store.path_for("bad"), "wb") as f:
                f.write(b"this is not gzip")
            assert store.load("bad") is None

    def test_frame_cap_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            store = PressureTraceStore(d)
            huge = [make_frame(i * 0.01) for i in range(5000)]
            store.save("huge", huge)
            back = store.load("huge")
            assert len(back) <= 2000
