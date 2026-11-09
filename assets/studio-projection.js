/* Projection uses the same unsaved draft, pixel calibration and Save as /config.
 * No physical unit conversion or unmeasured launch data is invented here. */
(() => {
  if (new URLSearchParams(location.search).get('view') !== 'projection') return;
  const editor = window.StudioEditor;
  const main = document.querySelector('.studio-main');
  main.querySelector('h1').textContent = 'Floor projection setup';
  main.querySelector('.studio-page-header p').textContent = 'Configure floor widgets independently from your OBS overlay. Both start from your existing layout.';
  const nav = document.querySelector('.studio-rail nav');
  nav.querySelector('[aria-current]').removeAttribute('aria-current');
  nav.querySelector('[data-projection-link]').setAttribute('aria-current','page');
  const existingControls = main.querySelector('.container');existingControls.hidden = false;
  const controls = document.createElement('section');controls.className = 'container projection-controls';
  controls.innerHTML = `
    <h1>Origin (ball) position</h1>
    <p class="subtitle">Offsets in canvas pixels, relative to the divot center.</p>
    <label class="projection-field">Origin X <input id="projector-x" type="number" step="1" value="0"><span>px</span></label>
    <label class="projection-field">Origin Y <input id="projector-y" type="number" step="1" value="0"><span>px</span></label>
    <h2 class="section-title">Rotation (layout)</h2>
    <div class="projection-range-labels"><span>−180°</span><span>+180°</span></div>
    <input id="projector-layout-rotation" type="range" min="-180" max="180" step="1" value="0" aria-label="Whole layout rotation">
    <label class="projection-field">Angle <input id="projector-layout-angle" type="number" step="1" value="0" aria-label="Whole layout rotation degrees"><span>°</span></label>
    <h2 class="section-title">Selected widget rotation</h2>
    <p id="projector-selected-name" class="subtitle">Select a widget in the preview.</p>
    <div class="projection-widget-rotation"><button class="studio-button" id="projector-rotate-left" type="button" aria-label="Rotate selected widget minus five degrees">↶ −5°</button><input id="projector-widget-angle" type="number" step="1" value="0" aria-label="Selected widget rotation degrees"><button class="studio-button" id="projector-rotate-right" type="button" aria-label="Rotate selected widget plus five degrees">↷ +5°</button></div>
    <details class="projection-divot-tilt"><summary>Divot direction alignment</summary>
      <label class="projection-field">Divot tilt <input id="projector-tilt" type="number" step="1" value="0"><span>°</span></label>
      <p class="studio-preview-note">Divot tilt adjusts only the illustrative direction. Layout rotation turns the entire projector output.</p>
    </details>
    <button class="studio-button" id="projector-reset" type="button">Reset alignment</button>
    <p class="studio-preview-note">Reset clears origin, layout rotation, divot tilt and widget rotations in this preview. Positions and sizes stay unchanged.</p>
    <div class="studio-layout-actions"><button class="studio-button primary" id="projector-save" type="button" disabled>Save floor projection</button><button class="studio-button" id="projector-cancel" type="button" disabled>Cancel floor changes</button></div>`;
  existingControls.after(controls);
  const frame = document.getElementById('studioPreviewFrame');
  const toolbar = document.getElementById('studioCanvasHeader');
  toolbar.innerHTML = '<strong>Projection content</strong>';
  const views = [['Divot only', '/divot'], ['Metric tiles only', '/tiles'], ['Whole layout', '/?mode=projector']];
  views.forEach(([label,url],index) => {
    const button = document.createElement('button');button.type = 'button';button.className = 'studio-button';button.textContent = label;
    button.setAttribute('aria-pressed',String(index === 2));if (index === 2) button.classList.add('primary');
    button.addEventListener('click',()=>{
      toolbar.querySelectorAll('button').forEach(b=>{b.classList.toggle('primary',b === button);b.setAttribute('aria-pressed',String(b === button));});
      editor.setRole(['divot','tiles','whole'][index]);frame.src = url;
    });toolbar.appendChild(button);
  });
  frame.title = 'Live floor projection output';
  frame.src = '/?mode=projector';
  main.querySelector('.studio-preview-note').textContent = 'Black emits no light on the mat. Changes stay in this preview until saved. Until the first shot arrives, the overlay shows sample data. Divot shape is illustrative; direction reflects path.';
  const $ = id => document.getElementById(id);
  const allInputs = controls.querySelectorAll('input,button');allInputs.forEach(input=>input.disabled = true);
  function numberInput(id,update,eventName = 'change') {
    $(id).addEventListener(eventName,()=>{
      if ($(id).value.trim() === '' || !Number.isFinite(Number($(id).value))) {$(id).reportValidity();return;}
      editor.change(layout=>update(layout,Number($(id).value)));
    });
  }
  const calibration = key => (layout,value)=>{layout.divot_calibration = {...layout.divot_calibration,[key]:value};};
  numberInput('projector-x',calibration('offset_x'));numberInput('projector-y',calibration('offset_y'));numberInput('projector-tilt',calibration('tilt_deg'));
  const rotateLayout = (layout,value)=>{layout.projection = {...layout.projection,rotation_deg:value};};
  numberInput('projector-layout-rotation',rotateLayout,'input');numberInput('projector-layout-angle',rotateLayout);
  numberInput('projector-widget-angle',(layout,value)=>{const id = editor.getSelected();if (layout.widgets[id]) layout.widgets[id].rotation = value;});
  for (const [id,delta] of [['projector-rotate-left',-5],['projector-rotate-right',5]]) $(id).addEventListener('click',()=>editor.change(layout=>{
    const widget = layout.widgets[editor.getSelected()];if (widget) widget.rotation = (Number(widget.rotation)||0)+delta;
  }));
  $('projector-reset').addEventListener('click',()=>editor.change(layout=>{
    layout.divot_calibration = {...layout.divot_calibration,offset_x:0,offset_y:0,tilt_deg:0};
    layout.projection = {...layout.projection,rotation_deg:0};
    Object.values(layout.widgets).forEach(widget=>{widget.rotation = 0;});
  },'Alignment reset in preview · Save to apply or Cancel to restore.'));
  $('projector-save').addEventListener('click',()=>editor.save());$('projector-cancel').addEventListener('click',()=>editor.cancel());
  document.addEventListener('studio-layout-change',event=>{
    const {layout,selected,dirty,saving,role} = event.detail;
    allInputs.forEach(input=>input.disabled = saving);
    const c = layout.divot_calibration || {};
    $('projector-x').value = c.offset_x || 0;$('projector-y').value = c.offset_y || 0;$('projector-tilt').value = c.tilt_deg || 0;
    $('projector-layout-angle').value = layout.projection?.rotation_deg || 0;
    $('projector-layout-rotation').value = (((Number(layout.projection?.rotation_deg)||0)+180)%360+360)%360-180;
    $('projector-widget-angle').value = layout.widgets[selected]?.rotation || 0;
    $('projector-selected-name').textContent = document.getElementById('studioWidgetSelect').selectedOptions[0]?.textContent || 'Select a widget';
    $('projector-save').disabled = saving || !dirty;$('projector-cancel').disabled = saving || !dirty;
    // The divot-only surface is fullscreen regardless of its saved rectangle.
    for (const id of ['studioX','studioY','studioWidth','studioHeight']) $(id).disabled = role === 'divot';
  });
})();
