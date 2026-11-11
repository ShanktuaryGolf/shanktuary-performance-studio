"""Reuse complete Lab paints without retaining obsolete pressure primitives.

Painters still describe a whole frame. This helper operates *after* coordinate,
font and image scaling, and reuses items only when their type and option schema
match. The caller must route all creates (including device-sized images) and
subsequent coordinate/configuration mutations through the same helper.

Use only on the Tk thread. Ordinary pages continue using normal Canvas calls.
"""

import tkinter as tk
from contextlib import contextmanager
from dataclasses import dataclass


class _CanvasOperations:
    """Unscaled base-class calls, avoiding overridden Canvas entry points."""

    def __init__(self, canvas):
        self.canvas = canvas

    def create(self, kind, coords, options):
        return tk.Canvas._create(self.canvas, kind, coords, options)

    def coords(self, item, *coords):
        return tk.Canvas.coords(self.canvas, item, *coords)

    def configure(self, item, options):
        return tk.Canvas.itemconfigure(self.canvas, item, **options)

    def delete(self, *items):
        return tk.Canvas.delete(self.canvas, *items)

    def find(self, selector):
        return tk.Canvas.find_withtag(self.canvas, selector)

    def reorder(self, items):
        # Only Tk's own widget path and integer item IDs enter the script.
        # Quote complete Tcl words, never interpolate painter text/options.
        commands = [tk._join((self.canvas._w, "raise", str(int(item)))) for item in items]
        if commands:
            self.canvas.tk.call("eval", "\n".join(commands))


@dataclass
class _Item:
    ident: int
    coords: tuple
    options: dict
    schema: tuple
    reusable: bool = True


class RetainedCanvas:
    """Bounded item pools for one complete, explicitly keyed paint at a time.

    ``frame(key)`` clears old content on key changes (page/size/scale), trims
    unused items on success and clears partial content on an exception.
    ``create`` takes physical coordinates and already transformed options.
    ``set_coords``/``configure``/``move``/``delete`` preserve mutation tracking.
    Call ``invalidate`` after a normal external delete-all. Intercept the
    painter's initial delete-all *inside* a retained frame without deleting it.
    """

    def __init__(self, canvas, *, operations=None):
        self.canvas = canvas
        self._ops = operations if operations is not None else _CanvasOperations(canvas)
        self.active = False
        self._key = None
        self._pools = {}
        self._items = {}
        self._cursors = {}
        self._order = []
        self._previous_order = []

    @property
    def item_count(self):
        return len(self._items)

    @property
    def current_items(self):
        """Fresh painter's stacking list, excluding last frame's unused items."""
        return tuple(self._order if self.active else self._previous_order)

    def invalidate(self):
        """Forget items after external clearing, releasing image/font owners."""
        self._key = None
        self._pools.clear()
        self._items.clear()
        self._cursors.clear()
        self._order.clear()
        self._previous_order.clear()

    @contextmanager
    def frame(self, key):
        if self.active:
            raise RuntimeError("Retained canvas frames cannot be nested")
        if key != self._key:
            self._ops.delete("all")
            self.invalidate()
            self._key = key
        self.active = True
        self._cursors = {}
        self._order = []
        try:
            yield self
            self._finish()
        except BaseException:
            self._ops.delete("all")
            self.invalidate()
            raise
        finally:
            self.active = False

    def create(self, kind, coords, options):
        if not self.active:
            raise RuntimeError("Create requires an active retained frame")
        coords = tuple(coords)
        # Tk ignores None-valued options. Keep that default-setting schema
        # separate from an explicit value, and detach mutable option lists.
        options = {key: tuple(value) if isinstance(value, list) else value
                   for key, value in options.items() if value is not None}
        schema = (kind, tuple(sorted(options)))
        pool = self._pools.setdefault(schema, [])
        index = self._cursors.get(schema, 0)
        self._cursors[schema] = index + 1
        item = pool[index] if index < len(pool) else None
        if item is not None and not item.reusable:
            self._ops.delete(item.ident)
            self._items.pop(item.ident, None)
            item = None
        if item is None:
            item = _Item(self._ops.create(kind, coords, options), coords, options, schema)
            if index < len(pool):
                pool[index] = item
            else:
                pool.append(item)
            self._items[item.ident] = item
        else:
            self.set_coords(item.ident, coords)
            self.configure(item.ident, options)
        self._order.append(item.ident)
        return item.ident

    def _matching(self, selector):
        try:
            ident = int(selector)
        except (TypeError, ValueError):
            return [self._items[item] for item in self._ops.find(selector) if item in self._items]
        item = self._items.get(ident)
        return [item] if item is not None else []

    def set_coords(self, selector, coords):
        """Set physical coordinates; suppress an identical numeric-ID setter."""
        coords = tuple(coords)
        matches = self._matching(selector)
        # Canvas.coords applies to the first matching item, not every tag hit.
        item = matches[0] if matches else None
        if item is None or item.coords != coords:
            self._ops.coords(selector, *coords)
        if item is not None:
            item.coords = coords

    def note_coords(self, selector, coords):
        """Record a setter already performed by the caller (physical units)."""
        matches = self._matching(selector)
        if matches:
            matches[0].coords = tuple(coords)

    def configure(self, selector, options):
        """Apply changed options, preserving references to Tk images/fonts."""
        options = {key: tuple(value) if isinstance(value, list) else value
                   for key, value in options.items() if value is not None}
        matches = self._matching(selector)
        if len(matches) == 1:
            item = matches[0]
            changed = {key: value for key, value in options.items()
                       if key not in item.options or item.options[key] != value}
        else:
            changed = options
        if changed:
            self._ops.configure(selector, changed)
        self.note_itemconfigure(selector, options)

    def note_itemconfigure(self, selector, options):
        for item in self._matching(selector):
            if any(key not in item.schema[1] for key in options):
                # Recreating resets options absent from the next create call
                # to Tk defaults rather than leaking a previous item's state.
                item.reusable = False
            item.options.update(options)

    def move(self, selector, dx, dy):
        matches = self._matching(selector)
        if not matches:
            # No retained entry: preserve ordinary Canvas behavior.
            for ident in self._ops.find(selector):
                coords = self._ops.coords(ident)
                self._ops.coords(ident, *(v + (dy if i % 2 else dx)
                                         for i, v in enumerate(coords)))
            return
        for item in matches:
            self.set_coords(item.ident, tuple(value + (dy if i % 2 else dx)
                                               for i, value in enumerate(item.coords)))

    def note_move(self, selector, dx, dy):
        for item in self._matching(selector):
            item.coords = tuple(value + (dy if i % 2 else dx)
                                for i, value in enumerate(item.coords))

    def _note_stack(self, selector, relative, *, raising):
        order = self._order if self.active else self._previous_order
        selected_ids = {item.ident for item in self._matching(selector)}
        selected = [ident for ident in order if ident in selected_ids]
        if not selected:
            return
        remaining = [ident for ident in order if ident not in selected_ids]
        if relative is None:
            index = len(remaining) if raising else 0
        else:
            relative_ids = {item.ident for item in self._matching(relative)}
            indices = [index for index, ident in enumerate(remaining) if ident in relative_ids]
            if not indices:
                return  # Relative item is missing or belongs to the moved group.
            index = max(indices) + 1 if raising else min(indices)
        order[:] = remaining[:index] + selected + remaining[index:]

    def note_raise(self, selector, above=None):
        """Record a completed raw tag_raise without losing it at frame finish."""
        self._note_stack(selector, above, raising=True)

    def note_lower(self, selector, below=None):
        """Record a completed raw tag_lower; selected items retain relative order."""
        self._note_stack(selector, below, raising=False)

    def delete(self, *selectors):
        self.note_delete(*selectors)
        return self._ops.delete(*selectors)

    def note_delete(self, *selectors):
        if "all" in selectors:
            self.invalidate()
            return
        for selector in selectors:
            for item in self._matching(selector):
                item.reusable = False
                self._items.pop(item.ident, None)
                self._order = [ident for ident in self._order if ident != item.ident]

    def _finish(self):
        unused = []
        for schema, pool in list(self._pools.items()):
            used = self._cursors.get(schema, 0)
            unused.extend(item.ident for item in pool[used:])
            del pool[used:]
            if not pool:
                del self._pools[schema]
        if unused:
            self._ops.delete(*unused)
            for ident in unused:
                self._items.pop(ident, None)
        if self._order != self._previous_order:
            self._ops.reorder(self._order)
        self._previous_order = list(self._order)
