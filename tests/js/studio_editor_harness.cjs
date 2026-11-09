// Execute the actual draft controller with a minimal DOM, no server/user data.
const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const path = require('path');
class Element {
  constructor(id='') {this.id=id;this.listeners={};this.style={};this.dataset={};this.children=[];this.value='';this.checked=true;this.disabled=false;this.clientWidth=960;this.classList={contains:()=>false};this.contentWindow={postMessage:message=>{this.lastMessage=structuredClone(message);}};}
  addEventListener(type,fn) {(this.listeners[type] ||= []).push(fn);}
  removeEventListener(type,fn) {this.listeners[type]=(this.listeners[type]||[]).filter(f=>f!==fn);}
  dispatchEvent(event) {for(const fn of this.listeners[event.type] || []) fn(event);}
  setAttribute(key,value) {this[key]=value;}
  replaceChildren(...children) {this.children=children;}
  appendChild(child) {this.children.push(child);child.parent=this;}
  remove() {this.parent.children=this.parent.children.filter(child=>child!==this);}
  querySelectorAll() {return this.children.filter(child=>child.dataset.savedPreset);}
  closest() {return {querySelector:()=>({textContent:this.id})};}
  checkValidity() {return true;}
  get options() {return this.children;}
  get selectedOptions() {return this.children.filter(child=>child.value===this.value);}
}
const elements={};
for(const id of ['studioPreviewFrame','studioPreview','studioSelectionCanvas','studioSelectionScale','studioStatus','studioWidgetSelect','studioX','studioY','studioWidth','studioHeight','studioRotation','studioGeometry','studioSnap','studioSave','studioCancel','studioReset','m_carry','m_ball_speed','studioPreset','studioNamePreset','studioPresetName']) elements[id]=new Element(id);
for (const value of ['saved','studio-broadcast']) {const option=new Element();option.value=value;elements.studioPreset.appendChild(option);}
elements.studioPreset.value='saved';
const document=new Element();document.getElementById=id=>elements[id];document.createElement=()=>new Element();document.querySelectorAll=()=>[];
let server={widgets:{carry:{x:100,y:200,w:500,h:300,visible:true,rotation:7,custom:'keep'},ball_speed:{x:600,y:200,w:300,h:100,visible:true}},divot_calibration:{scale:2,offset_x:10},styling:{theme:'studio-teal',unknown:'keep'},custom_server_field:23};
const posts=[];let fail=false;let paused=null;
const window=new Element();const context={document,window,console,structuredClone,URLSearchParams,visualsList:[],metricsList:['carry','ball_speed'],location:{search:process.argv.includes('--projection') ? '?view=projection' : '',origin:'http://test'},Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},ResizeObserver:class{constructor(fn){this.fn=fn;}observe(){this.fn();}},fetch:async (url,opts)=>{
  assert.equal(url, '/api/layout?output=' + (process.argv.includes('--projection') ? 'projection' : 'overlay'));
  if(opts?.method==='POST') {posts.push(JSON.parse(opts.body));if(paused) await paused.promise;if(fail) return {ok:false};const payload=JSON.parse(opts.body);server=context.StudioLayoutModel.mergeChanges(payload.base,payload.draft,server);return {ok:true,json:async()=>({status:'ok'})};}
  return {ok:true,json:async()=>structuredClone(server)};
}};
context.globalThis=context;vm.createContext(context);
for(const file of ['studio-layout-model.js','studio-editor.js','studio-layout-presets.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'../../assets',file),'utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const event=(id,type)=>elements[id].dispatchEvent({type});
(async()=>{
 await tick();const editor=window.StudioEditor;
 assert.equal(editor.getLayout().widgets.carry.x,100);assert.equal(posts.length,0);
 // Numeric geometry, visibility, rotation and preview all remain local.
 elements.studioX.value='240';event('studioX','change');
 elements.studioRotation.value='-12';event('studioRotation','change');
 elements.m_ball_speed.checked=false;event('m_ball_speed','change');
 assert.equal(editor.getLayout().widgets.carry.x,240);
 assert.equal(elements.studioPreviewFrame.lastMessage.layout.widgets.carry.rotation,-12);
 assert.equal(server.widgets.carry.x,100);assert.equal(posts.length,0);
 // Reset one widget keeps other draft work; Cancel restores every field.
 event('studioReset','click');assert.equal(editor.getLayout().widgets.carry.x,100);
 assert.equal(editor.getLayout().widgets.ball_speed.visible,false);
 editor.cancel();assert.equal(editor.isDirty(),false);assert.equal(editor.getLayout().widgets.ball_speed.visible,true);
 // Invalid input never becomes a persisted NaN/null and leaves the old value.
 elements.studioX.value='';event('studioX','change');assert.equal(editor.getLayout().widgets.carry.x,100);
 assert.equal(elements.studioStatus.dataset.state,'error');
 // Exercise dragging: parent iframe is scaled 1:2, with 40px snapping.
 let hit=elements.studioSelectionCanvas.children.find(child=>child.dataset.widget==='carry');
 hit.dispatchEvent({type:'pointerdown',button:0,clientX:100,clientY:100,target:hit,preventDefault(){}});
 window.dispatchEvent({type:'pointermove',clientX:133,clientY:120});window.dispatchEvent({type:'pointerup'});
 assert.equal(editor.getLayout().widgets.carry.x,160);assert.equal(editor.getLayout().widgets.carry.y,240);assert.equal(posts.length,0);
 editor.cancel();
 // Resize rotates pointer delta into widget space, never changes x/y.
 editor.change(layout=>{layout.widgets.carry.rotation=0;});
 hit=elements.studioSelectionCanvas.children.find(child=>child.dataset.widget==='carry');
 hit.dispatchEvent({type:'pointerdown',button:0,clientX:100,clientY:100,target:{classList:{contains:()=>true}},preventDefault(){}});
 window.dispatchEvent({type:'pointermove',clientX:140,clientY:120});window.dispatchEvent({type:'pointerup'});
 assert.equal(editor.getLayout().widgets.carry.w,600);assert.equal(editor.getLayout().widgets.carry.h,360);assert.equal(editor.getLayout().widgets.carry.x,100);
 editor.cancel();
 // Explicit Save merges only changed properties into freshly fetched state.
 editor.change(layout=>{layout.widgets.carry.x=440;layout.projection={rotation_deg:-12};layout.divot_calibration.offset_y=20;});
 server.widgets.ball_speed.x=765;server.widgets.carry.custom='newer';server.styling.theme='clean-light';
 await editor.save();assert.equal(posts.length,1);assert.equal(server.widgets.carry.x,440);
 assert.equal(server.widgets.ball_speed.x,765);assert.equal(server.widgets.carry.custom,'newer');assert.equal(server.styling.theme,'clean-light');assert.equal(server.divot_calibration.scale,2);assert.equal(server.custom_server_field,23);assert.equal(editor.isDirty(),false);
 // Failed save retains the draft and re-enables retry/cancel.
 editor.change(layout=>{layout.widgets.carry.x=777;});fail=true;await editor.save();
 assert.equal(editor.isDirty(),true);assert.equal(editor.getLayout().widgets.carry.x,777);assert.equal(elements.studioSave.disabled,false);assert.match(elements.studioStatus.textContent,/Could not save/);
 editor.cancel();assert.equal(editor.getLayout().widgets.carry.x,440);fail=false;
 // A repeated click while saving cannot post twice or mutate the in-flight draft.
 let release;paused={promise:new Promise(resolve=>{release=resolve;})};
 editor.change(layout=>{layout.widgets.carry.y=400;});const pending=editor.save();await tick();
 await editor.save();editor.change(layout=>{layout.widgets.carry.y=999;});assert.equal(posts.length,3);
 release();await pending;assert.equal(server.widgets.carry.y,400);assert.equal(editor.isDirty(),false);
 // Named presets are draft-only until Save and contain no nested presets.
 elements.studioPresetName.value='Floor practice';event('studioNamePreset','click');
 assert.equal(posts.length,3);assert.equal(editor.getLayout().studio_presets['Floor practice'].widgets.carry.y,400);
 assert.equal(editor.getLayout().studio_presets['Floor practice'].studio_presets,undefined);
 editor.cancel();assert.equal(editor.getLayout().studio_presets,undefined);assert.equal(elements.studioPreset.value,'saved');
 // Forward/inverse projection rotation and immutable three-way merge.
 const M=context.StudioLayoutModel;const pt=M.rotatePoint(400,300,27);const back=M.rotatePoint(pt.x,pt.y,-27);
 assert.ok(Math.abs(back.x-400)<1e-8 && Math.abs(back.y-300)<1e-8);
 const base={widgets:{a:{x:1,y:2}},styling:{theme:'dark'}};const draft=structuredClone(base);draft.widgets.a.x=3;
 const latest=structuredClone(base);latest.widgets.a.y=7;const merged=M.mergeChanges(base,draft,latest);
 assert.equal(merged.widgets.a.x,3);assert.equal(merged.widgets.a.y,7);assert.equal(latest.widgets.a.x,1);
 console.log('PASS: draft, geometry, drag, resize, cancel/reset, merge, failure and repeated Save');
})().catch(error=>{console.error(error);process.exitCode=1;});
