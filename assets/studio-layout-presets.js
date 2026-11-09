/* Built-in and named saved compositions share the editor's explicit Save. */
(() => {
  const editor = window.StudioEditor;
  const selector = document.getElementById('studioPreset');
  if (!editor || !selector) return;
  const preset = {
    carry:{x:230,y:140,w:600,h:330,visible:true},
    total_spin:{x:1080,y:140,w:650,h:330,visible:true},
    side_launch:{x:90,y:560,w:1080,h:470,visible:true},
    wbb_heatmap:{x:1210,y:560,w:650,h:370,visible:true},
    wbb_balance_bar:{x:1210,y:940,w:650,h:90,visible:true}
  };
  const capture = layout => structuredClone({widgets:layout.widgets,styling:layout.styling || {},divot_calibration:layout.divot_calibration || {},projection:layout.projection || {rotation_deg:0}});
  function refresh() {
    const current = selector.value;
    selector.querySelectorAll('[data-saved-preset]').forEach(option => option.remove());
    for (const name of Object.keys(editor.getLayout()?.studio_presets || {})) {
      const option = document.createElement('option');option.value = 'named:'+name;option.dataset.savedPreset = 'true';option.textContent = name;selector.appendChild(option);
    }
    selector.value = [...selector.options].some(option => option.value === current) ? current : 'saved';
  }
  selector.addEventListener('change', () => {
    const value = selector.value;
    editor.change(layout => {
      if (value === 'studio-broadcast') {
        for (const [id,widget] of Object.entries(layout.widgets || {})) widget.visible = id in preset;
        for (const [id,rect] of Object.entries(preset)) layout.widgets[id] = {...layout.widgets[id],...rect,rotation:0};
        layout.styling = {...layout.styling,preset:'studio-broadcast'};
      } else {
        const composition = value === 'saved' ? capture(editor.getSaved()) : layout.studio_presets?.[value.slice(6)];
        if (composition) Object.assign(layout,structuredClone(composition));
      }
    },'Layout preset preview · Not saved. Save layout to apply.');
  });
  document.querySelectorAll('[data-overlay-theme]').forEach(swatch => swatch.addEventListener('click',() => {
    editor.change(layout => {layout.styling = {...layout.styling,theme:swatch.dataset.overlayTheme};},'Theme preview · Not saved. Save layout to apply.');
  }));
  document.getElementById('studioNamePreset').addEventListener('click',() => {
    const input = document.getElementById('studioPresetName');
    const name = input.value.trim();
    if (!name) {input.reportValidity();return;}
    editor.change(layout => {
      const entries = Object.entries(layout.studio_presets || {}).filter(([key]) => key !== name);
      layout.studio_presets = Object.fromEntries([...entries,[name,capture(layout)]]);
    },'Named preset added to preview · Save layout to keep it.');
    refresh();selector.value = 'named:'+name;input.value = '';
  });
  document.addEventListener('studio-layout-change',refresh);
  for (const event of ['studio-layout-saved','studio-layout-cancelled']) document.addEventListener(event,()=>{selector.value = 'saved';refresh();});
})();
