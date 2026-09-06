"""Tests for Shanktuary Index overlay widget registration, API consumption, and response states."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OVERLAY = REPO / "assets" / "overlay.html"
CONFIG = REPO / "assets" / "config.html"


@pytest.fixture(scope="module")
def overlay_html():
    return OVERLAY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config_html():
    return CONFIG.read_text(encoding="utf-8")


# --- 1. Widget Registration --------------------------------------------------

def test_index_widget_registered_in_all_widget_ids(overlay_html):
    """The widget ID must be registered in ALL_WIDGET_IDS for layout lifecycle."""
    m = re.search(r"const ALL_WIDGET_IDS = \[(.*?)\];", overlay_html, re.S)
    assert m, "ALL_WIDGET_IDS array not found in overlay.html"
    ids = [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]
    assert "shanktuary_index" in ids, "shanktuary_index is missing from ALL_WIDGET_IDS"


def test_index_widget_registered_in_default_layout():
    """Default layout in obs_server.py must define coordinates and visibility."""
    import sys
    sys.path.insert(0, str(REPO))
    from obs_server import DEFAULT_LAYOUT

    widgets = DEFAULT_LAYOUT.get("widgets", {})
    assert "shanktuary_index" in widgets, "shanktuary_index missing from DEFAULT_LAYOUT['widgets']"
    cfg = widgets["shanktuary_index"]
    assert cfg.get("visible") is True
    assert isinstance(cfg.get("x"), int)
    assert isinstance(cfg.get("y"), int)
    assert isinstance(cfg.get("w"), int)
    assert isinstance(cfg.get("h"), int)


def test_index_widget_in_overlay_dom(overlay_html):
    """Overlay must include the widget card element with expected child elements."""
    assert 'id="w_shanktuary_index"' in overlay_html
    assert 'onclick="hideWidget(\'shanktuary_index\')"' in overlay_html
    assert 'id="v_index_score"' in overlay_html
    assert 'id="v_index_tier"' in overlay_html
    assert 'id="v_index_reason"' in overlay_html


def test_index_widget_in_toolbar_select(overlay_html):
    """Canvas editor dropdown must offer shanktuary_index toggle."""
    assert '<option value="shanktuary_index">Shanktuary Index</option>' in overlay_html


def test_index_widget_in_config_html(config_html):
    """Web configurator must provide a toggle checkbox and include widget in visualsList."""
    assert 'id="v_shanktuary_index"' in config_html
    m = re.search(r"const visualsList = \[(.*?)\];", config_html, re.S)
    assert m, "visualsList not found in config.html"
    visuals = [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]
    assert "shanktuary_index" in visuals, "shanktuary_index missing from config.html visualsList"


# --- 2. /api/index Consumption & Event Wiring ---------------------------------

def test_load_index_data_fetches_api_index(overlay_html):
    """Overlay script must define loadIndexData fetching /api/index."""
    fn = re.search(r"function loadIndexData\(\) \{(.*?)\n    \}", overlay_html, re.S)
    assert fn, "loadIndexData() function not found in overlay.html"
    body = fn.group(1)
    assert "fetch('/api/index')" in body or 'fetch("/api/index")' in body
    assert "renderIndexData" in body


def test_index_updated_on_websocket_messages_and_startup(overlay_html):
    """Index must update on init/layout_update and shot events, as well as on load."""
    ws_fn = re.search(r"function initWebSocket\(\) \{(.*?)\n    \}", overlay_html, re.S)
    assert ws_fn, "initWebSocket not found"
    ws_body = ws_fn.group(1)
    assert "loadIndexData()" in ws_body, "loadIndexData not called in WebSocket message handler"

    # Must also be called on initial script run
    startup = overlay_html.split("initWebSocket();")[0][-200:]
    assert "loadIndexData();" in startup, "loadIndexData() not invoked at startup"


# --- 3. Both Response States: Available vs Insufficient Coverage -------------

def test_render_index_data_handles_available_state(overlay_html):
    """Available status must display score, tier, and club summary."""
    fn = re.search(r"function renderIndexData\(data\) \{(.*?)\n    \}", overlay_html, re.S)
    assert fn, "renderIndexData() not found in overlay.html"
    body = fn.group(1)

    # Available branch assertions
    assert "data.status === 'available'" in body or 'data.status === "available"' in body
    assert "scoreEl.innerText" in body
    assert "tierEl.innerText" in body
    assert "scoreEl.classList.remove('unavailable')" in body
    assert "cardEl.classList.remove('metric-unavailable')" in body


def test_render_index_data_handles_insufficient_coverage_state(overlay_html):
    """Insufficient coverage status must display explicit reason, suppress score, and hide tier."""
    fn = re.search(r"function renderIndexData\(data\) \{(.*?)\n    \}", overlay_html, re.S)
    assert fn, "renderIndexData() not found in overlay.html"
    body = fn.group(1)

    assert "data.status === 'insufficient_coverage'" in body or 'data.status === "insufficient_coverage"' in body
    assert "data.reason" in body
    assert "scoreEl.classList.add('unavailable')" in body
    assert "cardEl.classList.add('metric-unavailable')" in body
    assert "tierEl.style.display = 'none'" in body
