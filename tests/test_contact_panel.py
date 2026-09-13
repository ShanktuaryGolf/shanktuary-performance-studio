"""Exercise the real Tk painter with no hardware or persistence."""
import tkinter as tk
from types import SimpleNamespace

import pytest


@pytest.fixture
def canvas():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    c = tk.Canvas(root, width=800, height=500)
    yield c
    root.destroy()


@pytest.mark.parametrize("width,height", [(390,290), (600,420)])
@pytest.mark.parametrize("impact", [None, {"x_mm": 0}, {"x_mm": -8, "y_mm": 3}])
def test_panel_evidence_context_and_text_bounds(canvas, width, height, impact):
    from src.ui.contact_panel import draw_contact_panel
    shot = {"club": "7 Iron", "timestamp_ns": 4, "vertical_launch_angle_degrees": 25,
            "total_spin_rpm": 6000, "ball_speed_meters_per_second": 40,
            "open_golf_coach": {"us_customary_units": {"ball_speed_mph": 88}}}
    if impact is not None:
        shot["face_impact"] = impact
    app = SimpleNamespace(canvas=canvas, current_shot=shot, is_left_handed=False,
                          session_shots=[{**shot, "timestamp_ns": i,
                                          "vertical_launch_angle_degrees": 20,
                                          "total_spin_rpm": 5000} for i in range(4)],
                          get_scaled_club_asset=lambda *a, **kw: None)
    draw_contact_panel(app, 0, 0, width, height)
    texts = [(canvas.itemcget(i, "text"), canvas.bbox(i)) for i in canvas.find_all()
             if canvas.type(i) == "text"]
    labels = [t for t, _ in texts]
    assert "IMPACT LOCATION" in labels
    # The median table is gone (it lives on Club Delivery); the face is the panel.
    assert "SAME-CLUB SESSION MEDIAN" not in labels
    assert ("REPORTED" in labels) == (impact is not None)
    complete = bool(impact and "y_mm" in impact)
    assert len(canvas.find_withtag("contact-marker")) == (1 if complete else 0)
    # Anything short of a complete reading gets the approximate ring + EST label.
    rings = [i for i in canvas.find_withtag("contact-estimate") if canvas.type(i) == "oval"]
    assert len(rings) == (0 if complete else 1)
    assert any(t.startswith("EST ·") for t in labels) == (not complete)
    for text, bbox in texts:
        assert bbox[0] >= 0 and bbox[2] <= width, (text, bbox)
        assert bbox[1] >= 0 and bbox[3] <= height, (text, bbox)
    for j, (t, b) in enumerate(texts):
        for u, d in texts[j+1:]:
            assert min(b[2],d[2]) <= max(b[0],d[0]) or min(b[3],d[3]) <= max(b[1],d[1]), (t,u)


@pytest.mark.parametrize("lefty", [False, True])
def test_face_marker_requires_both_axes_and_mirrors_only_drawing(canvas, lefty):
    from src.ui.contact_panel import draw_contact_face
    app = SimpleNamespace(canvas=canvas, is_left_handed=lefty,
                          get_scaled_club_asset=lambda *a, **kw: None,
                          current_shot={"face_impact": {"x_mm": 8, "y_mm": 0}})
    draw_contact_face(app, 200, 160, 140)
    marker = canvas.find_withtag("contact-marker")
    assert len(marker) == 1
    bbox = canvas.coords(marker[0])
    center = 200 + (43.5 / 220 * 140) * (1 if lefty else -1)
    assert ((bbox[0]+bbox[2])/2 < center) == lefty
    canvas.delete("all")
    app.current_shot = {"face_impact": {"x_mm": 8}}
    draw_contact_face(app, 200, 160, 140)
    assert not canvas.find_withtag("contact-marker")


def test_production_and_redesigned_quad_render_the_shared_panel(canvas):
    import shanktuary_app
    import shanktuary_performance_studio as studio
    from src.ui.desktop import ShanktuaryDesktopApp

    for app_class in (studio.ShanktuaryApp, ShanktuaryDesktopApp):
        app = object.__new__(app_class)
        app.canvas = canvas
        app.current_shot = {"club": "7 Iron", "vertical_launch_angle_degrees": 20}
        app.current_club = "7 Iron"
        app.bag = []
        app.sessions = [{"shots": [app.current_shot]}]
        app.active_session_index = 0
        app.selected_shot_index = 0
        app.is_left_handed = False
        app.get_scaled_club_asset = lambda *a, **kw: None
        app.get_rotated_overhead_asset = lambda *a, **kw: None
        app.draw_4_quadrant_studio(1200, 950, 0, 0, 0, 20, 0, 0, 6000, 6000,
                                  0, 25, 45, 150, 90, "Straight", "A", 1.24)
        labels = [canvas.itemcget(i, "text") for i in canvas.find_all()
                  if canvas.type(i) == "text"]
        assert labels.count("IMPACT LOCATION") == 1
        assert not canvas.find_withtag("contact-marker")
        assert len([i for i in canvas.find_withtag("contact-estimate") if canvas.type(i) == "oval"]) == 1
        assert not any(t in ("ESTIMATE", "DIR EST", "CENTER FLUSH") for t in labels)
        canvas.delete("all")


def _fake_face(size=140):
    """Mimic get_scaled_club_asset: scaled by HEIGHT, native 290x220 aspect."""
    from PIL import Image, ImageTk
    height = int(size)
    return ImageTk.PhotoImage(Image.new("RGB", (int(height * 290 / 220), height), "#101820"))


def test_no_drawn_item_escapes_the_panel_box(canvas):
    """Text-only bounds checks missed the club graphic leaving the panel."""
    from src.ui.contact_panel import draw_contact_panel
    shot = {"club": "7 Iron", "vertical_launch_angle_degrees": 20,
            "total_spin_rpm": 6000, "ball_speed_meters_per_second": 40}
    app = SimpleNamespace(canvas=canvas, current_shot=shot, is_left_handed=False,
                          session_shots=[], get_scaled_club_asset=lambda *a, **k: _fake_face())
    x0, y0, x1, y1 = 900, 470, 1580, 940
    draw_contact_panel(app, x0, y0, x1, y1)
    escaped = []
    for item in canvas.find_all():
        box = canvas.bbox(item)
        if not box:
            continue
        if box[0] < x0 or box[2] > x1 or box[1] < y0 or box[3] > y1:
            kind = canvas.type(item)
            label = canvas.itemcget(item, "text") if kind == "text" else kind
            escaped.append((label[:24], box))
    assert not escaped, f"items escape the panel box: {escaped}"
