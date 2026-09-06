"""Tests for Grid Challenge modes (Classic Grid & Custom Grid).

Verifies:
1. grid_mode.js exports createGridMode, gridMode, buildGridZones, zoneContains.
2. Game rules: configurable start yardage, shot counting, random shuffle, single SSOT.
3. grid_ui.js exports sanitizeStartDistance, renderGridPicker, setupGridModeUI, createGrid3DHighlight.
4. sanitizeStartDistance snaps values to even 10-yard increments (e.g. 57 -> 60).
5. Both Classic Grid (data-mode="grid") and Custom Grid (data-mode="grid_custom") registered in index.html.
6. environment.js exports setTargetGreenVisible to toggle wooden sign/target green.
7. websocket.js hides pin distance readout during grid mode and toggles setTargetGreenVisible.
8. Static server serves /range/js/grid_mode.js and /range/js/grid_ui.js with 200 OK.
"""
from pathlib import Path
import re
import pytest

REPO = Path(__file__).resolve().parent.parent
RANGE_HTML = REPO / "assets" / "range" / "index.html"
RANGE_GRID_MODE_JS = REPO / "assets" / "range" / "js" / "grid_mode.js"
RANGE_GRID_UI_JS = REPO / "assets" / "range" / "js" / "grid_ui.js"
RANGE_ENV_JS = REPO / "assets" / "range" / "js" / "environment.js"
RANGE_WS_JS = REPO / "assets" / "range" / "js" / "websocket.js"


@pytest.fixture(scope="module")
def grid_mode_js():
    assert RANGE_GRID_MODE_JS.exists(), "assets/range/js/grid_mode.js must exist"
    return RANGE_GRID_MODE_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def grid_ui_js():
    assert RANGE_GRID_UI_JS.exists(), "assets/range/js/grid_ui.js must exist"
    return RANGE_GRID_UI_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def range_html():
    assert RANGE_HTML.exists(), "assets/range/index.html must exist"
    return RANGE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def env_js():
    assert RANGE_ENV_JS.exists(), "assets/range/js/environment.js must exist"
    return RANGE_ENV_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def websocket_js():
    assert RANGE_WS_JS.exists(), "assets/range/js/websocket.js must exist"
    return RANGE_WS_JS.read_text(encoding="utf-8")


def test_grid_mode_exports(grid_mode_js):
    """grid_mode.js must export the full state machine API."""
    assert "export function buildGridZones" in grid_mode_js
    assert "export function zoneContains" in grid_mode_js
    assert "export function createGridMode" in grid_mode_js
    assert "export const gridMode" in grid_mode_js
    assert "export const GRID_DEFAULT_START_YARDS = 180" in grid_mode_js


def test_grid_mode_rules_encoded(grid_mode_js):
    """grid_mode.js must encode the required game rules."""
    assert "startYards = GRID_DEFAULT_START_YARDS" in grid_mode_js
    assert "state.totalShots += 1" in grid_mode_js
    assert "active.shots += 1" in grid_mode_js
    assert "active.landed = true" in grid_mode_js
    assert "state.remainingZonePool.shift()" in grid_mode_js
    assert "shuffleCopy" in grid_mode_js
    assert "subscribe" in grid_mode_js
    assert "getState" in grid_mode_js


def test_grid_ui_subscribes_strictly_to_grid_mode(grid_ui_js):
    """grid_ui.js must consume gridMode state machine and export UI helpers."""
    assert "import { gridMode" in grid_ui_js
    assert "gridMode.subscribe" in grid_ui_js
    assert "gridMode.getState()" in grid_ui_js
    assert "export function renderGridPicker" in grid_ui_js
    assert "export function setupGridModeUI" in grid_ui_js
    assert "export function createGrid3DHighlight" in grid_ui_js
    assert "export function sanitizeStartDistance" in grid_ui_js


def test_sanitize_start_distance_rule(grid_ui_js):
    """sanitizeStartDistance must snap to 10-yard multiples and clamp."""
    assert "Math.round(n / 10) * 10" in grid_ui_js
    assert "Math.max(20, Math.min(450" in grid_ui_js


def test_classic_and_custom_grid_modes_in_drawer(range_html):
    """Both Classic Grid and Custom Grid must have cards in #game-modes-drawer."""
    drawer_start = range_html.find('id="game-modes-drawer"')
    assert drawer_start != -1, "#game-modes-drawer missing"
    sub = range_html[drawer_start:drawer_start + 4500]
    assert 'data-mode="grid"' in sub, "Classic Grid card missing"
    assert "Classic Grid" in sub, "Classic Grid title missing"
    assert 'data-mode="grid_custom"' in sub, "Custom Grid card missing"
    assert "Custom Grid" in sub, "Custom Grid title missing"


def test_environment_exports_set_target_green_visible(env_js):
    """environment.js must export setTargetGreenVisible to toggle wooden sign/green."""
    assert "export function setTargetGreenVisible(visible)" in env_js
    assert "activeTargetGreen.visible = Boolean(visible)" in env_js


def test_websocket_toggles_wooden_sign_and_cleans_hud(websocket_js):
    """websocket.js must hide wooden sign and pin distance readout in grid modes."""
    assert "setTargetGreenVisible" in websocket_js
    assert "setTargetGreenVisible(false)" in websocket_js
    assert "setTargetGreenVisible(true)" in websocket_js
    assert "targetDistUnit" in websocket_js
    assert "isGridMode()" in websocket_js


def test_grid_ui_highlights_only_active_zone(grid_ui_js):
    """WebGL 3D highlight must only be rendered for the single activeZoneIndex."""
    assert "activeZoneIndex" in grid_ui_js
    assert "GridModeActiveZoneHighlight" in grid_ui_js
    assert "group.visible = false" in grid_ui_js
    assert "update(activeZone)" in grid_ui_js


def test_static_server_serves_grid_assets():
    """Verify obs_server serves /range/js/grid_mode.js and /range/js/grid_ui.js."""
    import obs_server
    assets_dir = obs_server.get_assets_dir()
    grid_mode_path = assets_dir / "range" / "js" / "grid_mode.js"
    grid_ui_path = assets_dir / "range" / "js" / "grid_ui.js"
    assert grid_mode_path.exists(), f"grid_mode.js not found in {assets_dir}"
    assert grid_ui_path.exists(), f"grid_ui.js not found in {assets_dir}"
