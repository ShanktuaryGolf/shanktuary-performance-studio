"""Approved range layouts are live controller clients, not a screenshot facade."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RANGE = ROOT / 'assets/range'


def run_node(source):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    subprocess.run([node, '--input-type=module', '-e', source], cwd=ROOT, check=True,
                   capture_output=True, text=True)


def test_shell_contains_both_reference_layouts_and_preserves_merged_overview():
    html = (RANGE / 'index.html').read_text()
    for id_ in ('range-picker', 'range-workspace', 'range-scene', 'range-session-rail',
                'range-start-mode', 'range-start-combine', 'range-end-combine',
                'range-combine-progress', 'range-metrics-mount', 'range-renderer-error'):
        assert f'id="{id_}"' in html
    assert 'data-desktop-workspace="Overview"' in html
    assert 'data-desktop-workspace="Shot"' not in html
    assert 'CONCEPT' not in html
    assert 'Sample data' not in html
    assert '/range/studio-range.css' in html
    css = (RANGE / 'studio-range.css').read_text()
    assert 'grid-template-columns: minmax(0, 1fr) var(--range-rail)' in css
    assert 'studio-range [hidden]' in css
    assert '#range-renderer-error' in css


def test_selecting_modes_is_staged_and_start_resume_cameras_are_wired():
    run_node(r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
class Element {
  constructor(id = '') { this.id=id; this.dataset={}; this.hidden=false; this.disabled=false; this.textContent=''; this.children=[]; this.handlers={}; this.attrs={}; this.classes=new Set(); this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key)}; }
  appendChild(el) { this.children.push(el); }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,fn) { this.handlers[k]=fn; }
  async click() { if(!this.disabled) return this.handlers.click?.({target:this}); }
  querySelector(q) { return this.parts?.[q] || null; }
}
const ids=new Map(); const get=id=>{if(!ids.has(id)) ids.set(id,new Element(id)); return ids.get(id)};
const modes=['practice','challenge','target_practice','ladder','closest-pin','long-drive','grid','grid_custom','combine'];
const cards=modes.map(mode=>{const e=new Element();e.dataset.mode=mode;e.parts={'.game-mode-desc':new Element(),'.game-mode-title':new Element()};e.parts['.game-mode-desc'].textContent='Rules: '+mode;e.parts['.game-mode-title'].textContent=mode;return e});
const cameras=[1,2,0,1,2,0].map(mode=>{const e=new Element();e.dataset.rangeCamera=String(mode);return e});
const desktop=new Element();desktop.dataset.desktopWorkspace='Overview';
const body=new Element();
globalThis.document={body,getElementById:get,querySelectorAll:q=>q==='.game-mode-card'?cards:q==='[data-range-camera]'?cameras:q==='[data-desktop-workspace]'?[desktop]:[]};
globalThis.window={dispatchEvent(){},location:{reload(){}}};
get('range-source-status').parts={em:new Element()};
const source=fs.readFileSync('assets/range/js/studio_shell.js','utf8');
const {studioShell}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const started=[],cameraCalls=[],combineCalls=[];
studioShell.bind({startMode:m=>started.push(m),camera:m=>cameraCalls.push(m),combine:a=>combineCalls.push(a)});
for(const [index, mode] of modes.entries()) {
  studioShell.showPicker();
  await cards[index].click();
  assert.equal(started.length,index,'selection must not start or reset any mode');
  assert.equal(cards[index].attrs['aria-pressed'],'true');
  await get('range-start-mode').click(); await Promise.resolve();
  assert.equal(started.at(-1),mode);
  assert.equal(body.dataset.rangeMode,mode);
  assert.equal(get('range-picker').hidden,true);
  assert.equal(get('range-workspace').hidden,false);
}
assert.deepEqual(combineCalls,[],'entering combine must not create a run');
await get('range-start-combine').click();await get('range-end-combine').click();
assert.deepEqual(combineCalls,['start','end']);
studioShell.showPicker();await cards[1].click();await get('range-resume').click();
assert.equal(body.dataset.rangeMode,'combine','cancel selection preserves current session');
assert.equal(started.length,9,'resume does not reset game scores');
for(const camera of cameras) await camera.click();
assert.deepEqual(cameraCalls,[1,2,0,1,2,0]);
studioShell.setCamera(2); assert.equal(cameras[1].attrs['aria-pressed'],'true');
studioShell.setEngine(false);assert.equal(get('range-renderer-error').hidden,false);
assert.match(get('range-engine-label').textContent,/unavailable/);
await desktop.click();assert.match(get('range-desktop-message').textContent,/desktop workspace/);
""")


def test_metric_badges_preserve_missing_derived_estimated_and_sample_data():
    run_node(r"""
import assert from 'node:assert/strict';import fs from 'node:fs';
const {readMetric,DEFAULT_STRIP}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/range/js/metrics.js','utf8')).toString('base64'));
assert.deepEqual(DEFAULT_STRIP,['carry','total','ballSpeed','launch','totalSpin','apex','descent','smash']);
assert.equal(readMetric('ballSpeed',null,{}).sourceLabel,'Unavailable');
assert.equal(readMetric('ballSpeed',{ballSpeed:NaN},{}).sourceLabel,'Unavailable');
assert.equal(readMetric('ballSpeed',{ballSpeed:142},{}).sourceLabel,'Native');
assert.equal(readMetric('launch',{verticalLaunchAngle:0},{}).text,'0.0');
assert.equal(readMetric('carry',{derived:{carry:true}},{carryYds:200}).sourceLabel,'Derived');
assert.equal(readMetric('smash',{smash:1.49},{smashClamped:true}).sourceLabel,'Unavailable');
assert.equal(readMetric('ballSpeed',{ballSpeed:142,source:'demo'},{}).sourceLabel,'Sample');
for(const [kind,label] of [['source_reported','Reported'],['derived','Derived'],['modelled','Modelled'],['source_estimated','Estimate']]) {
 assert.equal(readMetric('ballSpeed',{ballSpeed:142,external:true,metricProvenance:{ballSpeed:kind}},{}).sourceLabel,label);
}
""")


def test_renderer_recovers_without_webgl_and_uses_inset_size_when_available():
    run_node(r"""
import assert from 'node:assert/strict';import fs from 'node:fs';
const {initRenderer}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/range/js/renderer.js','utf8')).toString('base64'));
class Node {constructor(){this.position={set(){}};this.shadow={mapSize:{},camera:{}}} add(){} updateProjectionMatrix(){} }
const canvas={};const viewport={clientWidth:810,clientHeight:480};
globalThis.document={body:viewport,getElementById:id=>id==='three-canvas'?canvas:viewport};
globalThis.window={innerWidth:1584,innerHeight:990,devicePixelRatio:1,addEventListener(){}};
globalThis.THREE={Scene:Node,Color:Node,FogExp2:Node,PerspectiveCamera:Node,AmbientLight:Node,HemisphereLight:Node,DirectionalLight:Node,WebGLRenderer:class{constructor(){throw Error('No WebGL')}}};
assert.equal(initRenderer().renderer,null);
let size;
THREE.WebGLRenderer=class {constructor(){this.shadowMap={}}setSize(...args){size=args}setPixelRatio(){}};
const available=initRenderer();assert.equal(available.camera.aspect,810/480);assert.deepEqual(size,[810,480,false]);
""")


def test_combine_uses_server_protocol_and_requires_explicit_start():
    js = (RANGE / 'js/websocket.js').read_text()
    combine_branch = js.split("} else if (mode === 'combine') {")[1].split("} else if")[0]
    assert "postCombine('start')" not in combine_branch
    assert 'loadCombine()' in combine_branch
    assert 'needed: status.protocol.shots_per_station' in js
    assert "scoreValue.textContent = r.score.toFixed(1)" in js
    assert "track.setAttribute('aria-valuenow', String(st.counted))" in js
    assert "action === 'start' && combineStatus?.active" in js
    assert "studioShell || document.getElementById('hud-scale')" in js
    assert "studioShell?.bind({" in js
