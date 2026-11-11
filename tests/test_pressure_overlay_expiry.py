"""Execute live-only overlay expiry under Node; no browser/OBS settings touched."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
HTML = Path(__file__).resolve().parents[1] / "assets" / "overlay.html"


def run_js(body):
    if NODE is None:
        pytest.skip("node unavailable")
    html = HTML.read_text(encoding="utf-8")
    code = html[html.index("    const pressureTrail = [];"):html.index("    function drawPressureHeatmap(")]
    prelude = """
const elements = {};
for (const id of ['v_wbb_phase','v_wbb_pct_left','v_wbb_pct_right','v_wbb_fill_l',
                 'obsHeatmapCanvas','obsCopCanvas','v_carry']) {
  elements[id] = {innerText: 'saved', style: {}, width:100,height:100,offsetParent:null,
                 getContext: () => ({clearRect: () => {elements[id].cleared=true;}})};
}
const document = {getElementById: id => elements[id] || null};
let callbacks = new Map(), cancelled = [], next=0;
function setTimeout(fn, delay) {callbacks.set(++next,{fn,delay});return next;}
function clearTimeout(id) {cancelled.push(id);callbacks.delete(id);}
function drawPressureHeatmap() {}
function drawPressureCOP() {}
function state() {return {phase:elements.v_wbb_phase.innerText,
 left:elements.v_wbb_pct_left.innerText,right:elements.v_wbb_pct_right.innerText,
 fill:elements.v_wbb_fill_l.style.width,trail:pressureTrail.length,
 heatmapCleared:!!elements.obsHeatmapCanvas.cleared,
 copCleared:!!elements.obsCopCanvas.cleared,carry:elements.v_carry.innerText};}
"""
    result = subprocess.run([NODE, "-e", prelude + code + body], text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_expired_live_sample_clears_numbers_and_plots_not_saved_shot():
    result = run_js("""
handleLivePressureFrame({pct_left:63,pct_right:37,phase:'backswing'});
const before=state(), timer=callbacks.get(next);
timer.fn();
console.log(JSON.stringify({before, after:state(),delay:timer.delay}));
""")
    assert result["before"]["left"] == "63% L"
    assert result["delay"] == 1500
    after = result["after"]
    assert after["phase"] == "PRESSURE UNAVAILABLE"
    assert after["left"] == "-- L" and after["right"] == "-- R"
    assert after["trail"] == 0 and after["fill"] == "0%"
    assert after["heatmapCleared"] and after["copCleared"]
    assert after["carry"] == "saved"


def test_new_frame_cancels_expiry_and_old_callback_cannot_clear_it():
    result = run_js("""
handleLivePressureFrame({pct_left:60,pct_right:40});
const old=callbacks.get(next).fn;
handleLivePressureFrame({pct_left:40,pct_right:60});
old();
console.log(JSON.stringify({state:state(),cancelled,pending:callbacks.size}));
""")
    assert result["state"]["left"] == "40% L"
    assert result["state"]["trail"] == 2
    assert result["cancelled"] == [1] and result["pending"] == 1


def test_no_timer_or_changes_without_live_frames_and_stream_can_resume():
    result = run_js("""
handleLivePressureFrame(null);
const initial=state(), pending=callbacks.size;
handleLivePressureFrame({pct_left:60,pct_right:40});
callbacks.get(next).fn();
handleLivePressureFrame({pct_left:55,pct_right:45,phase:'address'});
console.log(JSON.stringify({initial,pending,resumed:state()}));
""")
    assert result["pending"] == 0 and result["initial"]["phase"] == "saved"
    assert result["resumed"]["phase"] == "ADDRESS"
    assert result["resumed"]["left"] == "55% L"
    assert result["resumed"]["trail"] == 1
