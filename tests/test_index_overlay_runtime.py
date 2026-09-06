"""Runtime audit of renderIndexData(): actually executes the extracted
function body under Node with a minimal DOM stub, rather than only
grepping for expected substrings (which is what test_index_overlay_widget.py
does). This is the only place that exercises the two states neither that
file nor the widget's own two branches cover:

  * `{}` -- what `GET /api/index` returns for missing/empty/corrupt
    history (no `status` key at all, distinct from `insufficient_coverage`).
  * `null` -- what the `fetch(...).catch()` handler passes on a network/
    parse error.

Both fall through renderIndexData's final `else` branch by inspection; this
pins that they actually do, and that the two real branches produce the
literal DOM state agy's report describes.
"""
import json
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OVERLAY = REPO / "assets" / "overlay.html"

NODE = shutil.which("node")

_DOM_STUB = """
class FakeClassList {
  constructor() { this._set = new Set(); }
  add(c) { this._set.add(c); }
  remove(c) { this._set.delete(c); }
  contains(c) { return this._set.has(c); }
}
class FakeEl {
  constructor(id) { this.id = id; this.innerText = ''; this.style = {}; this.classList = new FakeClassList(); }
}
const elements = {};
for (const id of ['v_index_score', 'v_index_tier', 'v_index_reason', 'w_shanktuary_index']) {
  elements[id] = new FakeEl(id);
}
const document = { getElementById: (id) => elements[id] || null };
"""


def _render_index_data_source() -> str:
    html = OVERLAY.read_text(encoding="utf-8")
    m = re.search(r"function renderIndexData\(data\) \{(.*?)\n    \}", html, re.S)
    assert m, "renderIndexData() not found in overlay.html"
    return "function renderIndexData(data) {" + m.group(1) + "\n}"


def _run(data) -> dict:
    if NODE is None:
        pytest.skip("node not available")
    script = f"""
{_DOM_STUB}
{_render_index_data_source()}
renderIndexData({json.dumps(data)});
console.log(JSON.stringify({{
  score: elements.v_index_score.innerText,
  scoreUnavailable: elements.v_index_score.classList.contains('unavailable'),
  tierText: elements.v_index_tier.innerText,
  tierDisplay: elements.v_index_tier.style.display,
  reason: elements.v_index_reason.innerText,
  cardUnavailable: elements.w_shanktuary_index.classList.contains('metric-unavailable'),
}}));
"""
    import subprocess
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"node execution failed: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_available_state_shows_score_and_tier():
    out = _run({
        "status": "available",
        "score": 78.4,
        "tier": "Index",
        "reason": None,
        "established_clubs": ["Driver", "7 Iron", "PW"],
    })
    assert out["score"] == "78.4"
    assert out["scoreUnavailable"] is False
    assert out["tierText"] == "INDEX"
    assert out["tierDisplay"] == "inline-block"
    assert out["reason"] == "3 established clubs"
    assert out["cardUnavailable"] is False


def test_insufficient_coverage_state_shows_reason_and_suppresses_score():
    out = _run({
        "status": "insufficient_coverage",
        "score": None,
        "tier": None,
        "reason": "Need at least 3 established clubs (have 2)",
        "established_clubs": ["Driver", "7 Iron"],
    })
    assert out["score"] == "--"
    assert out["scoreUnavailable"] is True
    assert out["tierDisplay"] == "none"
    assert out["reason"] == "Need at least 3 established clubs (have 2)"
    assert out["cardUnavailable"] is True


def test_empty_object_state_falls_back_to_unavailable():
    """What /api/index actually returns for missing/empty/corrupt history --
    no 'status' key at all, distinct from insufficient_coverage."""
    out = _run({})
    assert out["score"] == "--"
    assert out["scoreUnavailable"] is True
    assert out["tierDisplay"] == "none"
    assert out["cardUnavailable"] is True


def test_null_data_from_a_fetch_failure_does_not_throw():
    """The fetch(...).catch() handler calls renderIndexData(null) directly."""
    out = _run(None)
    assert out["score"] == "--"
    assert out["scoreUnavailable"] is True
    assert out["cardUnavailable"] is True
