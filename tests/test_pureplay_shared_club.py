"""PurePlay uses Nova's actual Club renderer, without invented measurements."""
import copy
import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.ui._legacy import club_redesign_v1 as club
from src.ui.contact_panel import draw_contact_face


def app_for(shot):
    return SimpleNamespace(canvas=MagicMock(), current_shot=shot, is_left_handed=False,
        session_shots=[shot], get_scaled_club_asset=lambda *a, **k: None,
        resolve_handed=lambda v, default=0: v if isinstance(v, (int, float)) else default,
        rotate_point=lambda x,y,cx,cy,a: (cx+(x-cx)*math.cos(a)-(y-cy)*math.sin(a),
                                         cy+(x-cx)*math.sin(a)+(y-cy)*math.cos(a)))


def texts(app):
    return [call.kwargs.get("text", "") for call in app.canvas.create_text.call_args_list]


def test_toolbar_same_six_metrics_ignores_missing_fallbacks():
    app = app_for({"_source": "pureplay", "ball_speed_meters_per_second": 0})
    club.draw_top_metric_toolbar(app, 1200, *([999]*8))
    assert "0.0 MPH" in texts(app)
    assert texts(app).count("--") == 5
    assert not any("999" in t for t in texts(app))
    assert app.canvas.create_rectangle.call_count == 1


def test_toolbar_labels_modelled_and_keeps_source_values():
    app = app_for({"_source": "pureplay", "open_golf_coach": {"carry_distance_meters": 100,
        "club_speed_meters_per_second": 20}, "_metric_provenance": {
        "open_golf_coach.carry_distance_meters": {"kind": "source_estimated"},
        "open_golf_coach.club_speed_meters_per_second": {"kind": "modelled"}}})
    before = copy.deepcopy(app.current_shot)
    club.draw_top_metric_toolbar(app, 1200, *([999]*8))
    assert "CARRY · EST" in texts(app)
    assert "CLUB SPEED · MODELLED" in texts(app)
    assert app.current_shot == before


def test_missing_spin_no_directional_axis_or_fake_shape():
    app = app_for({"_source": "pureplay"})
    app.canvas.bbox.return_value = None
    club.polish_club_page(app, 1200, 950, *([999]*13), "Straight", "A", 999)
    assert not any(c.kwargs.get("arrow") for c in app.canvas.create_line.call_args_list)
    assert "Shape not reported" in texts(app)
    assert not any("999" in str(t) or "Straight" == t for t in texts(app))


def test_pureplay_contact_no_estimated_ring_but_manual_mark_allowed():
    app = app_for({"_source": "pureplay", "club": "7 Iron"})
    draw_contact_face(app, 200, 200, 150)
    assert not app.canvas.create_oval.called
    assert app.contact_face_geometry is not None
    app.current_shot["face_impact"] = {"x_mm": 0, "y_mm": 0}
    draw_contact_face(app, 200, 200, 150)
    assert any(c.kwargs.get("tags") == "contact-marker" for c in app.canvas.create_oval.call_args_list)


def test_real_shared_desktop_club_path_preserves_artwork_and_unknowns():
    import tkinter as tk

    from src.ui.desktop import ShanktuaryDesktopApp
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    try:
        app = object.__new__(ShanktuaryDesktopApp)
        app.canvas = tk.Canvas(root, width=1200, height=950)
        app.current_shot = {"_source": "pureplay", "club": "7 Iron"}
        app.current_club = "7 Iron"
        app.bag = []
        app.sessions = [{"shots": [app.current_shot]}]
        app.active_session_index = app.selected_shot_index = 0
        app.is_left_handed = False
        assets = []
        app.get_scaled_club_asset = lambda path, *a, **kw: assets.append(path)
        app.get_rotated_overhead_asset = lambda *a, **kw: assets.append("overhead")
        app.draw_4_quadrant_studio(1200, 950, *([999]*13), "Straight", "A", 999)
        labels = [app.canvas.itemcget(i,"text") for i in app.canvas.find_all()
                  if app.canvas.type(i) == "text"]
        assert "overhead" in assets and len(assets) >= 3
        assert "IMPACT LOCATION" in labels
        assert "Shape not reported" in labels
        assert not any("999" in t or t == "Straight" for t in labels)
        assert not app.canvas.find_withtag("contact-estimate")
        assert all(app.canvas.itemcget(i,"smooth") in ("0", "false", "") for i in app.canvas.find_all()
                   if app.canvas.type(i) == "line")
    finally:
        root.destroy()
