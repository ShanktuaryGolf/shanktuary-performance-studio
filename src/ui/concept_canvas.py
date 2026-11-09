"""Viewport adapter: retain production hit geometry below the expanded header."""

from __future__ import annotations


class ViewportCanvas:
    def __init__(self, canvas, dy=124):
        object.__setattr__(self, "_canvas", canvas)
        object.__setattr__(self, "dy", dy)

    def __getattr__(self, name):
        target = getattr(self._canvas, name)
        if name.startswith("create_"):

            def create(*coords, **kwargs):
                flat = (
                    list(coords[0])
                    if len(coords) == 1 and isinstance(coords[0], (list, tuple))
                    else list(coords)
                )
                shifted = [v + self.dy if i % 2 else v for i, v in enumerate(flat)]
                return target(*shifted, **kwargs)

            return create
        return target

    def __setattr__(self, name, value):
        # Palette adapters temporarily replace create_* methods on this proxy.
        object.__setattr__(self, name, value)

    def winfo_height(self):
        return self._canvas.winfo_height() - self.dy

    def winfo_width(self):
        return self._canvas.winfo_width()

    def bbox(self, *args):
        box = self._canvas.bbox(*args)
        return (box[0], box[1] - self.dy, box[2], box[3] - self.dy) if box else box

    def coords(self, item, *coords):
        if coords:
            flat = (
                list(coords[0])
                if len(coords) == 1 and isinstance(coords[0], (tuple, list))
                else list(coords)
            )
            return self._canvas.coords(
                item, *[v + self.dy if i % 2 else v for i, v in enumerate(flat)]
            )
        return [
            v - self.dy if i % 2 else v for i, v in enumerate(self._canvas.coords(item))
        ]


def _shift_geometry(value, dy):
    """Translate a rectangle, rectangle entry, or mapping of entries."""
    if isinstance(value, dict):
        return {k: _shift_geometry(v, dy) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        if len(value) >= 4 and all(isinstance(v, (int, float)) for v in value[:4]):
            out = [value[0], value[1] + dy, value[2], value[3] + dy, *value[4:]]
        else:
            out = [_shift_geometry(v, dy) for v in value]
        return tuple(out) if isinstance(value, tuple) else out
    return value


def restore_hit_geometry(app):
    for name, value in getattr(app, "_concept_native_hits", {}).items():
        setattr(app, name, value)
    app._concept_native_hits = {}


def translate_hit_geometry(app, dy=124):
    """Public hit boxes always describe visible, unscaled canvas coordinates.

    Painters retain their original local coordinates, while consumers, tests,
    hover handlers and accessibility use the same positions the user sees.
    Restore the local values before the next frame to avoid accumulating shifts.
    """
    from dataclasses import replace

    excluded = {
        "design_mode_rects",
        "concept_actions",
        "design_tools_btn_rect",
        "design_club_btn_rect",
        "design_dexterity_btn_rect",
        "design_fullscreen_btn_rect",
        "sidebar_session_btn_rect",
        "sidebar_new_sess_btn_rect",
        "dispersion_dot_rects",
        "fitting_dot_rects",
    }
    saved = {}
    for name, value in list(vars(app).items()):
        if name in excluded or name.startswith("_"):
            continue
        if name.endswith(("_rect", "_rects", "_chips")) or name in {
            "session_menu_items",
            "filter_menu_items",
            "tools_menu_items",
            "ui_scale_controls",
            "concept_setup_actions",
            "concept_session_actions",
        }:
            saved[name] = value
            setattr(app, name, _shift_geometry(value, dy))
    if getattr(app, "contact_face_geometry", None) is not None:
        saved["contact_face_geometry"] = app.contact_face_geometry
        app.contact_face_geometry = replace(
            app.contact_face_geometry, cy=app.contact_face_geometry.cy + dy
        )
    for name in ("dispersion_dot_rects", "fitting_dot_rects"):
        if hasattr(app, name):
            points = getattr(app, name)
            saved[name] = points
            setattr(app, name, [(x, y + dy, *tail) for x, y, *tail in points])
    saved["land_dot_coords"] = app.land_dot_coords
    app.land_dot_coords = [(x, y + dy, *tail) for x, y, *tail in app.land_dot_coords]
    app._concept_native_hits = saved
