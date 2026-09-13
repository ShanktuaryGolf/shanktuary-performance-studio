"""Source-level ACs for putting range tiles (8+2 scope)."""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
METRICS = (REPO / "assets" / "range" / "js" / "metrics.js").read_text(encoding="utf-8")
WS = (REPO / "assets" / "range" / "js" / "websocket.js").read_text(encoding="utf-8")
PUTT = (REPO / "assets" / "range" / "js" / "putt_physics.js").read_text(encoding="utf-8")


def test_face_to_target_is_in_the_catalog():
    assert "faceToTarget:" in METRICS
    assert "Face to Target" in METRICS


def test_skid_and_time_to_full_roll_are_always_est():
    assert "skid:" in METRICS
    assert "timeToFullRoll:" in METRICS
    skid = METRICS.split("skid:")[1].split("timeToFullRoll:")[0]
    ttfr = METRICS.split("timeToFullRoll:")[1].split("};")[0]
    assert "est: true" in skid
    assert "est: true" in ttfr


def test_total_roll_is_always_est():
    block = METRICS.split("totalRoll:")[1].split("skid:")[0]
    assert "est: true" in block


def test_putt_default_strip_is_the_locked_eight():
    assert "PUTT_DEFAULT_STRIP" in METRICS
    block = METRICS.split("PUTT_DEFAULT_STRIP = [")[1].split("]")[0]
    keys = [k.strip().strip("'\"") for k in block.split(",") if k.strip().strip("'\"")]
    assert keys == [
        "ballSpeed", "hla", "launch", "faceToPath",
        "clubPath", "dynamicLoft", "faceToTarget", "totalRoll",
    ]
    assert "carry" not in keys
    assert "skid" not in keys
    assert "timeToFullRoll" not in keys


def test_full_swing_default_strip_is_untouched():
    block = METRICS.split("export const DEFAULT_STRIP = [")[1].split("]")[0]
    assert "'carry'" in block or '"carry"' in block
    assert "totalRoll" not in block


def test_putt_strip_has_its_own_storage_key():
    assert "sps_range_putt_strip_metrics" in METRICS
    assert "loadPuttStripLayout" in METRICS
    assert "savePuttStripLayout" in METRICS
    assert "sps_range_strip_metrics" in METRICS


def test_face_to_target_extracted_without_zero_fallback():
    assert "club_face_to_target_degrees" in WS
    assert "handedOrNull" in WS
    assert "faceToTarget" in WS
    # The known-zero lie: parseFloat(...) ?? 0.0 on this field.
    extract = WS.split("function extractShotTelemetry")[1].split("return {")[0]
    assert "handedOrNull(" in extract
    assert "club_face_to_target_degrees ?? 0" not in extract


def test_putt_mode_loads_putt_layout_instead_of_forcing_five_keys():
    assert "PUTT_STRIP" not in WS
    assert "loadPuttStripLayout()" in WS
    assert "justEntered" in WS
    assert "savedStripBeforePutt" in WS
    assert "savePuttStripLayout(stripLayout)" in WS


def test_persist_split_does_not_write_full_swing_key_while_putting():
    assert "function persistStripLayout" in WS
    body = WS.split("function persistStripLayout")[1].split("function ")[0]
    assert "savePuttStripLayout" in body
    assert "saveStripLayout" in body
    assert "puttingActive" in body


def test_skid_model_lives_in_putt_physics():
    assert "applySlidingFriction" in PUTT
    assert "SLIDE_MU" in PUTT
    assert "fullRollReached" in PUTT
    assert "skidDistanceM" in PUTT
    assert "timeToFullRollS" in PUTT
