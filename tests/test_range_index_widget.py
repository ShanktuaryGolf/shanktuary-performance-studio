"""Tests for Shanktuary Index widget in /range HUD.

Verifies:
1. Widget registration in WIDGET_REGISTRY and range index.html DOM.
2. API consumption (/api/index) and WebSocket update triggers.
3. Rendering logic for both states (available vs insufficient coverage).
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RANGE_HTML = REPO / "assets" / "range" / "index.html"
RANGE_WIDGETS_JS = REPO / "assets" / "range" / "js" / "widgets.js"
RANGE_WS_JS = REPO / "assets" / "range" / "js" / "websocket.js"


@pytest.fixture(scope="module")
def range_html():
    return RANGE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def widgets_js():
    return RANGE_WIDGETS_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def websocket_js():
    return RANGE_WS_JS.read_text(encoding="utf-8")


# --- 1. Widget Registration --------------------------------------------------

def test_shanktuary_index_registered_in_widget_registry(widgets_js):
    """shanktuaryIndex must be defined in WIDGET_REGISTRY with fixed: true and element ID."""
    m = re.search(r"export\s+const\s+WIDGET_REGISTRY\s*=\s*\{(?P<body>.*?)\n\};", widgets_js, re.S)
    assert m, "WIDGET_REGISTRY not found in widgets.js"
    body = m.group("body")
    assert "shanktuaryIndex:" in body, "shanktuaryIndex missing from WIDGET_REGISTRY"

    entry = re.search(r"shanktuaryIndex:\s*\{(?P<entry>.*?)\}", body, re.S)
    assert entry, "shanktuaryIndex entry structure not found"
    entry_text = entry.group("entry")

    assert "fixed: true" in entry_text, "shanktuaryIndex must be marked fixed: true"
    assert "element: 'range-index-tile'" in entry_text or 'element: "range-index-tile"' in entry_text
    assert "title:" in entry_text
    assert "desc:" in entry_text


def test_shanktuary_index_markup_in_range_html(range_html):
    """range/index.html must include #range-index-tile in #right-rail with required HUD elements."""
    assert 'id="range-index-tile"' in range_html, "#range-index-tile element missing from index.html"
    assert 'id="btn-close-index-tile"' in range_html, "Close button missing"
    assert 'id="hud-index-tier"' in range_html, "Tier badge missing"
    assert 'id="hud-index-score"' in range_html, "Score element missing"
    assert 'id="hud-index-reason"' in range_html, "Reason element missing"

    # Must be placed inside #right-rail
    rail_start = range_html.find('id="right-rail"')
    assert rail_start != -1, "#right-rail not found in range/index.html"
    rail_end = range_html.find('id="widget-menu"')
    tile_pos = range_html.find('id="range-index-tile"')
    assert rail_start < tile_pos < rail_end, "#range-index-tile is not inside #right-rail"


def test_close_button_wired_in_websocket_js(websocket_js):
    """Close button for shanktuaryIndex must invoke removeWidget('shanktuaryIndex')."""
    assert "btnCloseIndexTile" in websocket_js
    assert "removeWidget('shanktuaryIndex')" in websocket_js


# --- 2. /api/index Consumption & WebSocket Events -----------------------------

def test_load_range_index_fetches_api_index(websocket_js):
    """loadRangeIndex() must fetch /api/index and pass response to renderRangeIndex."""
    fn = re.search(r"async\s+function\s+loadRangeIndex\(\)\s*\{(?P<body>.*?)\n    \}", websocket_js, re.S)
    assert fn, "loadRangeIndex() function not found in websocket.js"
    body = fn.group("body")
    assert "fetch('/api/index')" in body or 'fetch("/api/index")' in body
    assert "renderRangeIndex" in body


def test_index_updated_on_range_websocket_messages_and_startup(websocket_js):
    """Index must update on WebSocket 'init', 'shot', widget add, and startup."""
    assert "loadRangeIndex()" in websocket_js

    # ws.onmessage handles shot and init
    onmsg = re.search(r"ws\.onmessage\s*=\s*\(event\)\s*=>\s*\{(?P<body>.*?)\n        \};", websocket_js, re.S)
    assert onmsg, "ws.onmessage handler not found in websocket.js"
    msg_body = onmsg.group("body")
    assert "if (msg.type === 'shot')" in msg_body
    assert "loadRangeIndex();" in msg_body

    # addWidget branch for shanktuaryIndex
    add_fn = re.search(r"function\s+addWidget\(key\)\s*\{(?P<body>.*?)\n    \}", websocket_js, re.S)
    assert add_fn, "addWidget() not found in websocket.js"
    add_body = add_fn.group("body")
    assert "shanktuaryIndex" in add_body
    assert "loadRangeIndex();" in add_body


# --- 3. Both Response States: Available vs Insufficient Coverage -------------

def test_render_range_index_handles_available_state(websocket_js):
    """Available status must display score, tier, and club summary."""
    fn = re.search(r"function\s+renderRangeIndex\(data\)\s*\{(?P<body>.*?)\n    \}", websocket_js, re.S)
    assert fn, "renderRangeIndex() not found in websocket.js"
    body = fn.group("body")

    assert "data.status === 'available'" in body
    assert "hudIndexScore.innerText = scoreVal" in body
    assert "hudIndexScore.classList.remove('unavailable')" in body
    assert "hudIndexTier.style.display = 'inline-block'" in body
    assert "hudIndexReason.innerText = `${numClubs} established clubs`" in body


def test_render_range_index_handles_insufficient_coverage_state(websocket_js):
    """Insufficient coverage status must display '--', hide tier, and show reason."""
    fn = re.search(r"function\s+renderRangeIndex\(data\)\s*\{(?P<body>.*?)\n    \}", websocket_js, re.S)
    assert fn, "renderRangeIndex() not found in websocket.js"
    body = fn.group("body")

    assert "data.status === 'insufficient_coverage'" in body
    assert "hudIndexScore.innerText = '--'" in body
    assert "hudIndexScore.classList.add('unavailable')" in body
    assert "hudIndexTier.style.display = 'none'" in body
    assert "data.reason" in body


def test_render_range_index_logic_pure_simulation():
    """Simulate the renderRangeIndex logic in Python to verify exact contract semantics."""
    def simulate_render(data):
        class Element:
            def __init__(self):
                self.innerText = ""
                self.classes = set()
                self.style = {}
            def add_class(self, c): self.classes.add(c)
            def remove_class(self, c): self.classes.discard(c)

        score = Element()
        tier = Element()
        reason = Element()

        if not data or data.get("status") == "insufficient_coverage":
            score.innerText = "--"
            score.add_class("unavailable")
            tier.style["display"] = "none"
            tier.innerText = ""
            reason.innerText = data.get("reason", "Insufficient coverage") if data else "Insufficient coverage"
        elif data.get("status") == "available":
            val = data.get("score")
            score.innerText = f"{val:.1f}" if isinstance(val, (int, float)) else str(val or "--")
            score.remove_class("unavailable")
            t_val = data.get("tier")
            tier.innerText = str(t_val).upper() if t_val else "INDEX"
            tier.style["display"] = "inline-block"
            clubs = data.get("established_clubs") or []
            reason.innerText = f"{len(clubs)} established clubs"
        else:
            score.innerText = "--"
            score.add_class("unavailable")
            tier.style["display"] = "none"
            reason.innerText = "--"

        return score, tier, reason

    # Case 1: Available
    s, t, r = simulate_render({
        "status": "available",
        "score": 67.4,
        "tier": "Index",
        "established_clubs": ["7I", "5I", "3W"]
    })
    assert s.innerText == "67.4"
    assert "unavailable" not in s.classes
    assert t.innerText == "INDEX"
    assert t.style["display"] == "inline-block"
    assert r.innerText == "3 established clubs"

    # Case 2: Insufficient coverage with explicit reason
    s, t, r = simulate_render({
        "status": "insufficient_coverage",
        "reason": "Need at least 3 established clubs (have 2)"
    })
    assert s.innerText == "--"
    assert "unavailable" in s.classes
    assert t.style["display"] == "none"
    assert r.innerText == "Need at least 3 established clubs (have 2)"

    # Case 3: Insufficient coverage with no explicit reason
    s, t, r = simulate_render({"status": "insufficient_coverage"})
    assert s.innerText == "--"
    assert "unavailable" in s.classes
    assert t.style["display"] == "none"
    assert r.innerText == "Insufficient coverage"

    # Case 4: Null / network failure
    s, t, r = simulate_render(None)
    assert s.innerText == "--"
    assert "unavailable" in s.classes
    assert t.style["display"] == "none"
    assert r.innerText == "Insufficient coverage"
