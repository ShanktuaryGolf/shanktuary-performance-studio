"""User-marked contact: training labels, never an estimate.

The golfer looks at the face (tape, foot spray, impact sticker) and clicks
where the ball hit. That click becomes `marked_contact` on the shot, in the
same mm convention as any sensor reading (+horizontal = heel, +vertical =
high), so one drawing routine serves both -- but a mark is always labelled
as the golfer's, never as measured.
"""
import csv
import json

import pytest

import shanktuary_performance_studio as studio
from src.analytics import strike
from src.analytics.strike import FaceGeometry, contact_location

# --- model --------------------------------------------------------------------

def test_marked_contact_is_read_with_its_own_source():
    shot = {"marked_contact": {"horizontal_mm": -6.0, "vertical_mm": 3.5}}
    c = contact_location(shot)
    assert c.complete and c.source == "marked"
    assert c.headline == "Marked by you"
    assert c.horizontal_text == "Toe · 6.0 mm" and c.vertical_text == "High · 3.5 mm"
    assert c.badge == "MARKED"


def test_a_reported_reading_outranks_a_mark():
    shot = {"face_impact": {"lateral_offset_mm": 2.0, "vertical_offset_mm": 0.0},
            "marked_contact": {"horizontal_mm": -6.0, "vertical_mm": 3.5}}
    c = contact_location(shot)
    assert c.source == "reported" and c.horizontal_mm == 2.0 and c.badge == "REPORTED"


def test_a_mark_needs_both_axes_and_finite_numbers():
    assert not contact_location({"marked_contact": {"horizontal_mm": 1.0}}).available
    assert not contact_location({"marked_contact": {"horizontal_mm": "x", "vertical_mm": 1}}).available
    assert not contact_location({"marked_contact": None}).available


def test_face_geometry_round_trips_and_rejects_off_face_clicks():
    g = FaceGeometry(cx=500, cy=300, size=120, left_handed=False)
    for h, v in ((0, 0), (10, -5), (-20, 12)):
        px, py = g.mm_to_px(h, v)
        back = g.px_to_mm(px, py)
        assert back is not None
        assert abs(back[0] - h) < 1e-6 and abs(back[1] - v) < 1e-6
    # Heel is +h; for a right-hander heel is drawn to the RIGHT of the sweet spot.
    sx, sy = g.mm_to_px(0, 0)
    hx, _ = g.mm_to_px(10, 0)
    assert hx > sx
    lefty = FaceGeometry(cx=500, cy=300, size=120, left_handed=True)
    lx, _ = lefty.mm_to_px(10, 0)
    assert lx < lefty.mm_to_px(0, 0)[0]
    # Beyond the artwork's playable face -> no mark.
    far = g.mm_to_px(40, 0)
    assert g.px_to_mm(*far) is None


def test_mark_and_clear_stamp_the_shot_and_save(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "h.json"))
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = [{"name": "S", "shots": [{"club": "7 Iron"}]}]
    app.active_session_index = 0
    app.clubs = list(studio.DEFAULT_CLUBS); app.bag = []; app.is_left_handed = False
    app.balls = []; app.current_ball = None
    shot = app.sessions[0]["shots"][0]
    app.mark_contact(shot, -6.04, 3.46)
    assert shot["marked_contact"]["horizontal_mm"] == -6.0
    assert shot["marked_contact"]["vertical_mm"] == 3.5
    assert shot["marked_contact"]["source"] == "user"
    assert "marked_at" in shot["marked_contact"]
    saved = json.loads((tmp_path / "h.json").read_text())
    assert saved["sessions"][0]["shots"][0]["marked_contact"]["horizontal_mm"] == -6.0
    app.clear_contact_mark(shot)
    assert "marked_contact" not in shot
    saved = json.loads((tmp_path / "h.json").read_text())
    assert "marked_contact" not in saved["sessions"][0]["shots"][0]


def test_session_csv_carries_marks_as_training_labels(tmp_path):
    from src.analytics import session_report as sr
    session = {"name": "S", "shots": [
        {"club": "7 Iron", "ball_speed_meters_per_second": 40, "marked_contact": {"horizontal_mm": -6, "vertical_mm": 3}},
        {"club": "7 Iron", "ball_speed_meters_per_second": 41},
    ]}
    p = tmp_path / "s.csv"
    sr.write_csv(session, p)
    rows = list(csv.DictReader(p.open()))
    assert rows[0]["marked_contact_h_mm"] == "-6.0" and rows[0]["marked_contact_v_mm"] == "3.0"
    assert rows[1]["marked_contact_h_mm"] == "" and rows[1]["marked_contact_v_mm"] == ""


# --- UI --------------------------------------------------------------------------

def _tk_app(tmp_path, monkeypatch, cls=None):
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    import obs_server
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.geometry("1600x950")
    if cls is None:
        from src.ui import ShanktuaryDesktopApp as cls
    a = cls(root)
    a.sessions = [{"name": "S", "shots": [
        {"club": "7 Iron", "ball_speed_meters_per_second": 40, "timestamp_ns": 1},
        {"club": "7 Iron", "ball_speed_meters_per_second": 40, "timestamp_ns": 2,
         "marked_contact": {"horizontal_mm": 8.0, "vertical_mm": -4.0}},
    ]}]
    a.active_session_index = 0
    a.balls = []
    a.selected_shot_index = 0
    a.current_shot = a.sessions[0]["shots"][0]
    return root, a


def _ovals_tagged(a, tag):
    return [i for i in a.canvas.find_withtag(tag)]


def test_shot_view_face_has_no_marker_until_marked_then_click_marks(tmp_path, monkeypatch):
    root, a = _tk_app(tmp_path, monkeypatch)
    try:
        a.set_mode(9); root.update_idletasks()     # 9 = Shot (overview)
        assert a.contact_face_rect is not None, "Shot view must register the clickable face"
        assert not _ovals_tagged(a, "contact-marker"), "no mark yet -> no marker drawn"
        # Unmarked: the approximate ring and an honest label on the Shot view too.
        assert _items(a, "contact-estimate")
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert any(t.startswith("EST · usual spot from 1 mark") for t in texts), texts
        # Other marked shots of the same club appear as faint peers.
        assert len(_ovals_tagged(a, "contact-peer")) == 1
        g = a.contact_face_geometry
        px, py = g.mm_to_px(-6.0, 3.5)
        a.handle_mouse_press(type("E", (), {"x": int(px), "y": int(py), "num": 1})())
        mc = a.current_shot["marked_contact"]
        assert abs(mc["horizontal_mm"] - (-6.0)) <= 0.5 and abs(mc["vertical_mm"] - 3.5) <= 0.5
        root.update_idletasks()
        assert len(_ovals_tagged(a, "contact-marker")) == 1
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert any("Marked by you" in t for t in texts)
        assert not any("Estimated" in t for t in texts)
        assert not any(t.startswith("EST") for t in texts)      # marked: no estimate shown
        # A click on the "clear" affordance removes it.
        assert a.contact_clear_rect is not None
        x1, y1, x2, y2 = a.contact_clear_rect
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert "marked_contact" not in a.current_shot
    finally:
        root.destroy()


def test_quad_view_face_is_clickable_too(tmp_path, monkeypatch):
    root, a = _tk_app(tmp_path, monkeypatch)
    try:
        a.set_mode(1); root.update_idletasks()     # 1 = Quad
        assert a.contact_face_rect is not None
        g = a.contact_face_geometry
        px, py = g.mm_to_px(4.0, 1.0)
        a.handle_mouse_press(type("E", (), {"x": int(px), "y": int(py), "num": 1})())
        assert "marked_contact" in a.current_shot
    finally:
        root.destroy()


def test_strike_module_has_no_fabricated_marker_paths():
    """The old v11 face painted an orange lens from the headline text."""
    import inspect

    from src.ui._legacy import overview_redesign_v11 as v11
    src = inspect.getsource(v11)
    assert "_draw_face_with_clear_marker" not in src
    assert "if \"Low\" in head" not in src


# --- approximate strike (ring, never a dot) -----------------------------------

def _items(a, tag):
    return [i for i in a.canvas.find_withtag(tag) if a.canvas.type(i) == "oval"]


def test_quad_face_is_large_and_shows_the_usual_spot_ring_until_marked(tmp_path, monkeypatch):
    root, a = _tk_app(tmp_path, monkeypatch)
    try:
        a.set_mode(1); root.update_idletasks()
        x1, y1, x2, y2 = a.contact_face_rect
        # The face owns the panel: at least 200px tall (was 90), so a mark
        # lands within ~0.3mm of the cursor instead of ~0.8mm.
        assert y2 - y1 >= 200, (y2 - y1)
        assert a.contact_face_geometry.size >= 200
        # One other 7-iron mark exists -> a ring at that spot, labelled EST.
        rings = _items(a, "contact-estimate")
        assert len(rings) == 1 and a.canvas.type(rings[0]) == "oval"
        assert a.canvas.itemcget(rings[0], "fill") == ""      # hollow: a zone, not a point
        bb = a.canvas.bbox(rings[0])
        assert bb[2] - bb[0] >= 2 * 5 * a.contact_face_geometry.px_per_mm - 2  # >= MIN_RADIUS
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert any("EST" in t and "1 mark" in t for t in texts), texts
        assert not _items(a, "contact-marker")
        # Marking replaces the ring with a hard marker; clearing brings it back.
        g = a.contact_face_geometry
        px, py = g.mm_to_px(-6.0, 3.5)
        a.handle_mouse_press(type("E", (), {"x": int(px), "y": int(py), "num": 1})())
        root.update_idletasks()
        assert len(_items(a, "contact-marker")) == 1 and not _items(a, "contact-estimate")
        assert a.contact_clear_rect is not None
        cx1, cy1, cx2, cy2 = a.contact_clear_rect
        a.handle_mouse_press(type("E", (), {"x": (cx1 + cx2) // 2, "y": (cy1 + cy2) // 2, "num": 1})())
        root.update_idletasks()
        assert not _items(a, "contact-marker") and len(_items(a, "contact-estimate")) == 1
    finally:
        root.destroy()


def test_quad_panel_has_no_median_table_and_no_text_collisions(tmp_path, monkeypatch):
    root, a = _tk_app(tmp_path, monkeypatch)
    try:
        a.set_mode(1); root.update_idletasks()
        w, h = 1600, 950
        items = [(a.canvas.bbox(i), a.canvas.itemcget(i, "text")) for i in a.canvas.find_all()
                 if a.canvas.type(i) == "text" and a.canvas.bbox(i)]
        panel = [(b, t) for b, t in items if b[0] > w * .58 and b[1] > h * .55]
        assert not any("SESSION MEDIAN" in t for _, t in panel)
        assert any(t == "IMPACT LOCATION" for _, t in panel)
        ov = [(t, u) for j, (b, t) in enumerate(panel) for d, u in panel[j + 1:]
              if min(b[2], d[2]) > max(b[0], d[0]) and min(b[3], d[3]) > max(b[1], d[1])]
        assert ov == []
        # No text under the face artwork either.
        fx1, fy1, fx2, fy2 = a.contact_face_rect
        under = [t for b, t in panel if min(b[2], fx2) > max(b[0], fx1) and min(b[3], fy2) > max(b[1], fy1)]
        assert under == [], under
    finally:
        root.destroy()


def test_no_marks_at_all_gives_a_sweet_spot_ring_labelled_no_marks(tmp_path, monkeypatch):
    root, a = _tk_app(tmp_path, monkeypatch)
    try:
        del a.sessions[0]["shots"][1]["marked_contact"]
        a.set_mode(1); root.update_idletasks()
        assert len(_items(a, "contact-estimate")) == 1
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert any("no marks yet" in t for t in texts)
    finally:
        root.destroy()
