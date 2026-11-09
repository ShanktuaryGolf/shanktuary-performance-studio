/* Pure layout operations shared by the integrated editor and its tests. */
(function(root) {
  const clone = value => structuredClone(value);
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const rect = widget => ({x:finite(widget?.x),y:finite(widget?.y),w:finite(widget?.w,140),h:finite(widget?.h,70),rotation:finite(widget?.rotation)});
  const rotatePoint = (x, y, degrees, cx = 960, cy = 540) => {
    const a = degrees * Math.PI / 180;
    return {x:cx+(x-cx)*Math.cos(a)-(y-cy)*Math.sin(a),y:cy+(x-cx)*Math.sin(a)+(y-cy)*Math.cos(a)};
  };
  // Three-way merge: apply only values changed in this editor to freshly read
  // server state. Other editors' unrelated positions/settings remain intact.
  function mergeChanges(base, draft, latest) {
    const result = clone(latest || {});
    for (const [key,value] of Object.entries(draft || {})) {
      if (JSON.stringify(value) === JSON.stringify(base?.[key])) continue;
      const next = value && typeof value === 'object' && !Array.isArray(value)
        ? mergeChanges(base?.[key],value,Object.hasOwn(result,key) ? result[key] : {}) : clone(value);
      Object.defineProperty(result,key,{value:next,writable:true,enumerable:true,configurable:true});
    }
    return result;
  }
  root.StudioLayoutModel = {clone,finite,rect,rotatePoint,mergeChanges};
})(globalThis);
