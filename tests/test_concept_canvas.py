"""Viewport painting and public interaction geometry have a single boundary."""
from types import SimpleNamespace

from src.analytics.strike import FaceGeometry
from src.ui.concept_canvas import (
    ViewportCanvas,
    restore_hit_geometry,
    translate_hit_geometry,
)


class Canvas:
    def create_rectangle(self, *coords, **kwargs):
        return coords

    def bbox(self, *args):
        return (10, 144, 80, 174)

    def winfo_height(self):
        return 1000

    def winfo_width(self):
        return 1600


def test_paint_translation_does_not_change_dimensions_or_local_bbox():
    c = ViewportCanvas(Canvas())
    assert c.create_rectangle(10, 20, 80, 50) == (10, 144, 80, 174)
    assert c.bbox(1) == (10, 20, 80, 50)
    assert c.winfo_height() == 876
    assert c.winfo_width() == 1600


def test_public_hits_move_once_and_restore_before_each_frame():
    app = SimpleNamespace(
        table_row_rects=[(280, 200, 900, 240, 7)],
        concept_session_rects=[((300, 70, 330, 100), 'step', -1)],
        design_mode_rects={9: (16, 130, 246, 174)},
        concept_setup_actions={'aim': (700, 500, 900, 540)},
        land_dot_coords=[(600, 400, 5)],
        contact_face_geometry=FaceGeometry(700, 350, 200, False),
    )
    for _ in range(3):
        translate_hit_geometry(app)
        assert app.table_row_rects == [(280, 324, 900, 364, 7)]
        assert app.concept_session_rects[0][0] == (300, 194, 330, 224)
        assert app.design_mode_rects[9] == (16, 130, 246, 174)
        assert app.land_dot_coords == [(600, 524, 5)]
        assert app.contact_face_geometry.cy == 474
        restore_hit_geometry(app)
        assert app.contact_face_geometry.cy == 350
        assert app.table_row_rects == [(280, 200, 900, 240, 7)]
