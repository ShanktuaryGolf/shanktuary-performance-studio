/* One draft for geometry, visibility, themes and projector alignment.
 * Loading, selecting, dragging, Reset and Cancel never write user data. */
(() => {
  const M = StudioLayoutModel;
  const output = new URLSearchParams(location.search).get('view') === 'projection' ? 'projection' : 'overlay';
  const outputLabel = output === 'projection' ? 'Floor projection' : 'OBS overlay';
  const layoutUrl = '/api/layout?output=' + output;
  const $ = id => document.getElementById(id);
  const frame = $('studioPreviewFrame'), preview = $('studioPreview');
  const canvas = $('studioSelectionCanvas'), scaleLayer = $('studioSelectionScale');
  const status = $('studioStatus'), selection = $('studioWidgetSelect');
  const geometry = {x:$('studioX'),y:$('studioY'),w:$('studioWidth'),h:$('studioHeight'),rotation:$('studioRotation')};
  let saved = null, draft = null, selected = '', saving = false;
  let role = new URLSearchParams(location.search).get('view') === 'projection' ? 'whole' : 'overlay';
  const labels = {};
  document.querySelectorAll('#studioPreset,#studioNamePreset,#studioPresetName,[data-overlay-theme]').forEach(control => {control.disabled = true;});
  for (const id of [...visualsList,...metricsList]) {
    const input = $('v_'+id) || $('m_'+id);
    labels[id] = input?.closest('label')?.querySelector('.toggle-label')?.textContent || id.replaceAll('_',' ');
    if (input) input.disabled = true;
    input?.addEventListener('change', () => {
      if (!draft) return;
      change(layout => {layout.widgets[id] = {...layout.widgets[id],visible:input.checked};});
    });
  }
  const allowed = id => role === 'divot' ? id === 'divot' : role === 'tiles' ? id !== 'divot' : true;
  const visible = id => allowed(id) && (role === 'divot' || draft.widgets[id]?.visible !== false);
  const layoutRotation = () => role === 'overlay' ? 0 : M.finite(draft?.projection?.rotation_deg);
  const dirty = () => JSON.stringify(draft) !== JSON.stringify(saved);
  function notify(text, error = false) {
    status.textContent = text;
    status.dataset.state = error ? 'error' : dirty() ? 'draft' : 'ready';
  }
  function sync() {
    if (!draft) return;
    const ids = Object.keys(draft.widgets || {}).filter(allowed);
    if (!ids.includes(selected)) selected = ids.find(visible) || ids[0] || '';
    selection.replaceChildren(...ids.map(id => {
      const option = document.createElement('option');option.value = id;
      option.textContent = labels[id] + (visible(id) ? '' : ' (hidden)');return option;
    }));
    selection.value = selected;
    $('studioGeometry').disabled = saving || !selected;
    const r = M.rect(draft.widgets[selected]);
    for (const [key,input] of Object.entries(geometry)) input.value = r[key];
    for (const id of [...visualsList,...metricsList]) {
      const input = $('v_'+id) || $('m_'+id);
      if (input) {input.checked = draft.widgets[id]?.visible !== false;input.disabled = saving;}
    }
    document.querySelectorAll('[data-overlay-theme]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.overlayTheme === (['broadcast-dark','clean-light'].includes(draft.styling?.theme) ? draft.styling.theme : 'studio-teal'))));
    document.querySelectorAll('#studioPreset,#studioNamePreset,#studioPresetName,[data-overlay-theme]').forEach(control => {control.disabled = saving;});
    $('studioSave').disabled = saving || !dirty();
    $('studioCancel').disabled = saving || !dirty();
    $('studioReset').disabled = saving || !selected;
    canvas.replaceChildren();
    canvas.style.transform = `rotate(${layoutRotation()}deg)`;
    for (const id of ids.filter(visible)) {
      const widget = M.rect(draft.widgets[id]);
      const hit = document.createElement('div');
      hit.className = 'studio-widget-hit' + (id === selected ? ' selected' : '');
      hit.dataset.widget = id;hit.tabIndex = 0;hit.setAttribute('role','button');
      hit.setAttribute('aria-label', 'Select '+labels[id]);
      Object.assign(hit.style,{left:widget.x+'px',top:widget.y+'px',width:widget.w+'px',height:widget.h+'px',transform:`rotate(${widget.rotation}deg)`});
      if (role === 'divot') Object.assign(hit.style,{left:'0',top:'0',width:'1920px',height:'1080px'});
      hit.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {event.preventDefault();selected = id;sync();}
      });
      if (id === selected && role !== 'divot') {
        const handle = document.createElement('span');handle.className = 'studio-resize-handle';
        handle.setAttribute('aria-hidden','true');hit.appendChild(handle);
      }
      hit.addEventListener('pointerdown', event => beginDrag(event,id));
      canvas.appendChild(hit);
    }
    frame.contentWindow.postMessage({type:'studio-layout-preview',layout:draft},location.origin);
    document.dispatchEvent(new CustomEvent('studio-layout-change',{detail:{layout:M.clone(draft),selected,dirty:dirty(),saving,role}}));
  }
  function change(mutator, message = 'Unsaved preview · Save layout to update connected output.') {
    if (!draft || saving) return;
    mutator(draft);sync();notify(message);
  }
  function select(id) {selected = id;sync();}
  selection.addEventListener('change',()=>select(selection.value));
  for (const [key,input] of Object.entries(geometry)) input.addEventListener('change',() => {
    if (!draft || !selected) return;
    if (input.value.trim() === '' || !Number.isFinite(Number(input.value)) || !input.checkValidity()) {
      notify('Enter a valid size, position or angle. Width must be at least 100 px and height at least 50 px.',true);sync();return;
    }
    change(layout => {layout.widgets[selected] = {...layout.widgets[selected],[key]:Number(input.value)};});
  });
  function beginDrag(event,id) {
    if (saving || !draft || event.button !== 0) return;
    event.preventDefault();selected = id;
    const resize = event.target.classList.contains('studio-resize-handle');
    const start = M.rect(draft.widgets[id]);
    const origin = {x:event.clientX,y:event.clientY};
    const scale = preview.clientWidth/1920;
    const angle = layoutRotation();
    sync();
    if (role === 'divot') return; // This role is intentionally fullscreen.
    const move = e => {
      let delta = M.rotatePoint((e.clientX-origin.x)/scale,(e.clientY-origin.y)/scale,-angle,0,0);
      const snap = value => $('studioSnap').checked ? Math.round(value/40)*40 : Math.round(value);
      if (resize) {
        delta = M.rotatePoint(delta.x,delta.y,-start.rotation,0,0);
        draft.widgets[id].w = Math.max(100,snap(start.w+delta.x));
        draft.widgets[id].h = Math.max(50,snap(start.h+delta.y));
      } else {
        draft.widgets[id].x = snap(start.x+delta.x);draft.widgets[id].y = snap(start.y+delta.y);
      }
      sync();notify('Unsaved preview · Save layout to update connected output.');
    };
    const end = () => {window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);};
    window.addEventListener('pointermove',move);window.addEventListener('pointerup',end);window.addEventListener('pointercancel',end);
  }
  async function save() {
    if (!draft || saving || !dirty()) return;
    saving = true;sync();notify('Saving layout…');
    try {
      // The server merges changed fields under its write lock, avoiding a
      // read/modify/write race between two open configurator windows.
      const response = await fetch(layoutUrl,{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Layout-Merge':'1'},body:JSON.stringify({base:saved,draft})});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if ((await response.json()).status !== 'ok') throw new Error('Save was not confirmed');
      const confirmed = await fetch(layoutUrl);
      if (!confirmed.ok) throw new Error('Saved, but reload failed');
      const persisted = await confirmed.json();
      saved = M.clone(persisted);draft = M.clone(persisted);
      notify(outputLabel + ' saved · Only this output updated');
      document.dispatchEvent(new Event('studio-layout-saved'));
    } catch (error) {notify(`Could not save layout: ${error.message}. Your preview is still here; retry Save.`,true);}
    finally {saving = false;sync();}
  }
  function cancel() {
    if (!saved || saving) return;
    draft = M.clone(saved);sync();notify('Changes cancelled · Saved layout restored in preview');
    document.dispatchEvent(new Event('studio-layout-cancelled'));
  }
  $('studioSave').textContent = 'Save ' + outputLabel;
  $('studioCancel').textContent = 'Cancel ' + outputLabel + ' changes';
  $('studioSave').addEventListener('click',save);
  $('studioCancel').addEventListener('click',cancel);
  $('studioReset').addEventListener('click',() => {
    if (!saved?.widgets[selected]) return;
    change(layout => {layout.widgets[selected] = M.clone(saved.widgets[selected]);},'Selected widget restored to its saved settings · Other changes kept.');
  });
  frame.addEventListener('load',sync);
  window.addEventListener('message',event => {
    if (event.origin === location.origin && event.source === frame.contentWindow && event.data?.type === 'studio-preview-ready') sync();
  });
  new ResizeObserver(() => {
    const scale = preview.clientWidth/1920;
    frame.style.transform = `scale(${scale})`;scaleLayer.style.transform = `scale(${scale})`;
  }).observe(preview);
  window.addEventListener('beforeunload',event => {if (draft && dirty()) {event.preventDefault();event.returnValue = '';}});
  window.StudioEditor = {change,select,save,cancel,getLayout:()=>draft ? M.clone(draft) : null,getSaved:()=>saved ? M.clone(saved) : null,
    getSelected:()=>selected,setRole:next=>{role = next;sync();},isDirty:dirty};
  // Keep the historic configurator entry point available for integrations.
  window.saveLayout = save;
  const load = () => fetch(layoutUrl).then(r => {if (!r.ok) throw new Error(`HTTP ${r.status}`);return r.json();}).then(layout => {
    layout.widgets ||= {...layout.visuals,...layout.metrics};
    saved = M.clone(layout);draft = M.clone(layout);sync();notify(outputLabel + ' loaded · Independent layout; changes stay in preview until saved');
    document.dispatchEvent(new Event('studio-layout-ready'));
  }).catch(() => notify('Could not load the layout. Load your saved layout before saving. Check that Performance Studio is running, then reload.',true));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',load,{once:true});
  else load();
})();
