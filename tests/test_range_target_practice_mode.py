"""Tests for Target Practice standalone mode in WebGL Driving Range (/range).

Verifies:
1. Target Practice is registered as a mode in #game-modes-drawer with data-mode="target_practice".
2. #target-scorecard starts hidden (display:none) and is only displayed when target_practice mode is active.
3. scoreTargetShot is strictly gated on currentRangeMode === 'target_practice'.
4. State reset (resetTargetScore) is invoked on entry into target_practice mode.
5. Target Challenge (data-mode="challenge") remains separate and unaffected.
"""
from pathlib import Path
import re
import pytest

REPO = Path(__file__).resolve().parent.parent
RANGE_HTML = REPO / "assets" / "range" / "index.html"
RANGE_WS_JS = REPO / "assets" / "range" / "js" / "websocket.js"


@pytest.fixture(scope="module")
def range_html():
    return RANGE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def websocket_js():
    return RANGE_WS_JS.read_text(encoding="utf-8")


def test_target_practice_mode_card_in_drawer(range_html):
    """Target Practice must have a card in #game-modes-drawer with data-mode='target_practice'."""
    drawer_start = range_html.find('id="game-modes-drawer"')
    assert drawer_start != -1, "#game-modes-drawer missing from range/index.html"

    drawer_sub = range_html[drawer_start:drawer_start + 4000]
    assert 'data-mode="target_practice"' in drawer_sub, "target_practice mode card missing from drawer"
    assert "Target Practice" in drawer_sub, "Target Practice title missing from drawer"
    assert 'id="tag-target-practice"' in drawer_sub, "tag-target-practice badge missing from drawer"


def test_target_challenge_remains_distinct_mode(range_html):
    """Target Challenge must remain in drawer as a separate mode (data-mode='challenge')."""
    drawer_start = range_html.find('id="game-modes-drawer"')
    drawer_sub = range_html[drawer_start:drawer_start + 4000]
    assert 'data-mode="challenge"' in drawer_sub, "Target Challenge mode card missing"
    assert "Target Challenge" in drawer_sub, "Target Challenge title missing"


def test_target_scorecard_initially_hidden(range_html):
    """#target-scorecard must start with display:none to not show as an always-on widget."""
    scorecard_match = re.search(r'<div[^>]*id=["\']target-scorecard["\'][^>]*>', range_html)
    assert scorecard_match, "#target-scorecard not found in range/index.html"
    tag = scorecard_match.group(0)
    assert 'display:none' in tag.replace(" ", ""), "#target-scorecard must be hidden by default"


def test_websocket_mode_switching_gates_scorecard(websocket_js):
    """setGameMode must show targetScorecard only in target_practice mode, hidden in other modes."""
    assert "targetScorecard" in websocket_js, "targetScorecard element reference missing"
    assert re.search(r"targetScorecard\.style\.display\s*=\s*mode\s*===\s*['\"]target_practice['\"]\s*\?\s*['\"]['\"]\s*:\s*['\"]none['\"]", websocket_js), (
        "targetScorecard visibility must be conditionally set based on mode === 'target_practice'"
    )


def test_websocket_mode_handles_target_practice(websocket_js):
    """setGameMode must handle mode === 'target_practice' with title and state reset."""
    assert "mode === 'target_practice'" in websocket_js or 'mode === "target_practice"' in websocket_js
    assert "resetTargetScore()" in websocket_js, "resetTargetScore() must be called"
    assert "Target Practice" in websocket_js, "Target Practice title must be set"


def test_score_target_shot_gated_to_target_practice_mode(websocket_js):
    """scoreTargetShot must only be executed when currentRangeMode === 'target_practice'."""
    pattern = re.compile(
        r"if\s*\([^)]*currentRangeMode\s*===\s*['\"]target_practice['\"][^)]*\)\s*\{\s*scoreTargetShot\(",
        re.DOTALL
    )
    assert pattern.search(websocket_js), (
        "scoreTargetShot must be gated to currentRangeMode === 'target_practice'"
    )


def test_reset_target_score_resets_all_fields(websocket_js):
    """resetTargetScore function must reset streaks, hits, shot count, and deviation."""
    m = re.search(r"function\s+resetTargetScore\s*\(\)\s*\{(.*?renderTargetScorecard\(\);\s*\})", websocket_js, re.DOTALL)
    assert m, "resetTargetScore function definition not found"
    body = m.group(1)
    assert "targetScore.currentStreak = 0" in body
    assert "targetScore.bestStreak = 0" in body
    assert "targetScore.hits = 0" in body
    assert "targetScore.shotCount = 0" in body
    assert "targetScore.totalDeviation = 0" in body
    assert "renderTargetScorecard()" in body


def test_target_practice_custom_distance_input_in_html(range_html):
    """Target practice scorecard (#target-scorecard) must provide a numeric distance input."""
    scorecard_start = range_html.find('id="target-scorecard"')
    assert scorecard_start != -1, "#target-scorecard missing from range/index.html"
    scorecard_sub = range_html[scorecard_start:scorecard_start + 1200]
    assert '<input' in scorecard_sub and 'type="number"' in scorecard_sub, "Missing numeric input in #target-scorecard"
    assert 'id="target-scorecard-custom-dist"' in scorecard_sub, "#target-scorecard-custom-dist input missing from scorecard"
    assert 'id="btn-set-target-scorecard-dist"' in scorecard_sub, "#btn-set-target-scorecard-dist button missing from scorecard"


def test_target_practice_custom_distance_wiring_in_websocket(websocket_js):
    """Custom target distance input in #target-scorecard must be wired to updateTarget and localStorage."""
    assert "target-scorecard-custom-dist" in websocket_js, "target-scorecard-custom-dist missing in websocket.js"
    assert "btn-set-target-scorecard-dist" in websocket_js, "btn-set-target-scorecard-dist missing in websocket.js"
    assert "updateTarget" in websocket_js, "updateTarget missing in websocket.js"
    assert "sps_range_target_dist" in websocket_js, "sps_range_target_dist storage key missing"
    assert "tgtScorecardCustomDist.value = currentTargetYards" in websocket_js, (
        "tgtScorecardCustomDist must be kept in sync with currentTargetYards"
    )

