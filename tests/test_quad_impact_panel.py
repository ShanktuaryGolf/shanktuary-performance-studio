"""The Quad view's impact panel must not paint over its own labels.

Reported as "the picture of the iron on the bottom right is blocking text".

Three separate faults were behind it:

1. The redesign hid production's clubface with an opaque rectangle sized from
   its own (larger) image, which erased the panel header and both disclaimer
   lines. Trimming the cover to spare them left a sliver of the old clubhead
   visible instead -- the cover-and-repaint approach cannot win. Production's
   face asset is now suppressed for the duration of the render, so there is
   nothing to cover.

2. The face was sized from quadrant height alone, so it reached back across
   the VERTICAL / HORIZONTAL readouts and down over the footer. It is now
   budgeted against the free space in both axes.

3. The "DIRECTION ESTIMATE" badge used a hardcoded 118px offset and sat on top
   of "IMPACT LOCATION". Production measures the caption at the same spot and
   documents why; the redesign now does too.

These are rendering assertions -- they drive the real app and read canvas
geometry, because occlusion is invisible to a unit test on the helpers.
"""
import pytest


def _quad_app(tmp_path, monkeypatch, geometry="1600x950", contact=None):
    """Render a fixed native-style shot without reading a user's saved history."""
    tk = pytest.importorskip("tkinter")
    import shanktuary_performance_studio as studio

    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "shot.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    try:
        root.geometry(geometry)
        from src.ui import scaling
        from src.ui.desktop import ShanktuaryDesktopApp

        # These bounds are 96-DPI logical geometry, not the host monitor DPI.
        monkeypatch.setattr(scaling, "load_choice", lambda: "100%")
        app = ShanktuaryDesktopApp(root)
        shot = {
            "type": "shot", "club": "7 Iron", "timestamp": "06:24 PM",
            "timestamp_ns": 1700000000000000000,
            "ball_speed_meters_per_second": 48.7,
            "vertical_launch_angle_degrees": 18.4,
            "horizontal_launch_angle_degrees": -2.9,
            "total_spin_rpm": 6979.0,
            "open_golf_coach": {
                "smash_factor": 1.32, "spin_axis_degrees": 7.6,
                "descent_angle_degrees": 45.0, "hang_time_seconds": 5.9,
                "dynamic_loft_degrees": 24.0, "angle_of_attack_degrees": -4.0,
                "club_path_degrees": {"right_handed": 5.78, "left_handed": -5.78},
                "club_face_to_path_degrees": {"right_handed": -2.1, "left_handed": 2.1},
                "club_face_to_target_degrees": {"right_handed": 3.7, "left_handed": -3.7},
                "shot_name": {"right_handed": "Pull Fade", "left_handed": "Push Draw"},
                "us_customary_units": {
                    "carry_distance_yards": 147.0, "total_distance_yards": 158.0,
                    "ball_speed_mph": 109.0, "peak_height_yards": 31.0,
                    "offline_distance_yards": -4.2,
                },
            },
        }
        if contact is not None:
            shot["face_impact"] = contact
        app.get_active_session()["shots"] = [shot]
        app.selected_shot_index = 0
        app.current_shot = shot
        app.view_mode = 1
        app.draw_screen()
        root.update()
        return root, app
    except BaseException:
        root.destroy()
        raise


def _overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _tag_box(app, tag):
    items = app.canvas.find_withtag(tag)
    assert len(items) == 1, f"expected one {tag}, got {items}"
    return app.canvas.bbox(items[0])


def test_only_one_clubface_is_drawn(tmp_path, monkeypatch):
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        _tag_box(app, "contact-artwork")
    finally:
        root.destroy()


def test_the_clubface_clears_the_contact_status(tmp_path, monkeypatch):
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        # Concept stacks status BELOW artwork, retaining the no-occlusion rule.
        assert not _overlap(_tag_box(app, "contact-artwork"), _tag_box(app, "contact-heading"))
    finally:
        root.destroy()


def test_the_footer_disclaimer_is_never_covered(tmp_path, monkeypatch):
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        c = app.canvas
        footers = [i for i in c.find_all() if c.type(i) == "text"
                   and "Nova measures" in c.itemcget(i, "text")]
        assert len(footers) == 1
        assert not _overlap(c.bbox(footers[0]), _tag_box(app, "contact-artwork"))
    finally:
        root.destroy()


def test_the_credibility_badge_does_not_sit_on_the_caption(tmp_path, monkeypatch):
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        heading = _tag_box(app, "contact-heading")
        credibility = _tag_box(app, "contact-credibility")
        assert not _overlap(heading, credibility)
        c = app.canvas
        assert c.itemcget(c.find_withtag("contact-heading")[0], "text") == "Impact unavailable"
        assert c.itemcget(c.find_withtag("contact-credibility")[0], "text") == "No face-contact measurement"
    finally:
        root.destroy()


def test_no_panel_label_is_substantially_covered(tmp_path, monkeypatch):
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        c = app.canvas
        art = _tag_box(app, "contact-artwork")
        # Image transparent margins are part of the allocation: no text may
        # rely on transparency to survive an artwork replacement.
        for item in c.find_all():
            if c.type(item) == "text":
                assert not _overlap(c.bbox(item), art), c.itemcget(item, "text")
    finally:
        root.destroy()
