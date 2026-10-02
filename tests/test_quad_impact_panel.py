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
        from src.ui.desktop import ShanktuaryDesktopApp

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


# A shape this large is the panel background or a full-quadrant wash, not a
# decorative graphic. Panels are painted before their own labels, so counting
# them produces a false positive on every string in the panel.
_PANEL_FILL_W = 500
_PANEL_FILL_H = 320


def _panel_items(app):
    """(kind, z, bbox, text) for the bottom-right quadrant only."""
    ids = list(app.canvas.find_all())
    out = []
    for item in ids:
        box = app.canvas.bbox(item)
        if not box or box[0] < 900 or box[1] < 500:
            continue
        kind = app.canvas.type(item)
        text = app.canvas.itemcget(item, "text") if kind == "text" else ""
        out.append((kind, ids.index(item), box, text))
    return out


def _occluders(items):
    """Graphics that could plausibly hide a label -- backgrounds excluded."""
    out = []
    for kind, z, b, _ in items:
        if kind not in ("rectangle", "image"):
            continue
        if (b[2] - b[0]) >= _PANEL_FILL_W and (b[3] - b[1]) >= _PANEL_FILL_H:
            continue  # panel background
        out.append((z, b))
    return out


# The face artwork is 290x220 drawn at ~90px high, so ~118px wide. It used
# to be padded to a 158px square, which is what the old >150 threshold
# matched -- and that transparent padding was what buried the badge row.
_FACE_MIN_W = 100


def test_only_one_clubface_is_drawn(tmp_path, monkeypatch):
    """Production's face plus the redesign's is what forced the opaque cover
    in the first place. Suppressing the asset should leave exactly one."""
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        faces = [b for kind, _, b, _ in _panel_items(app)
                 if kind == "image" and (b[2] - b[0]) > _FACE_MIN_W]
        assert len(faces) == 1, f"expected 1 clubface, found {len(faces)}: {faces}"
    finally:
        root.destroy()


def test_the_clubface_clears_the_contact_status(tmp_path, monkeypatch):
    """The contact status is above the artwork and must remain unobscured."""
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        items = _panel_items(app)
        faces = [b for kind, _, b, _ in items
                 if kind == "image" and (b[2] - b[0]) > _FACE_MIN_W]
        assert faces, "no clubface image in the panel"
        # The current panel stacks its contact status above the face instead
        # of keeping the old VERTICAL/HORIZONTAL readout beside it.
        face_top = min(b[1] for b in faces)
        readout = [(b, t) for kind, _, b, t in items
                   if kind == "text" and "Approximate strike" in t]
        assert readout, "contact status label not found"
        assert all(b[3] <= face_top for b, _ in readout), (
            f"clubface overlaps the contact status: {readout}; face top={face_top}"
        )
    finally:
        root.destroy()


def test_the_footer_disclaimer_is_never_covered(tmp_path, monkeypatch):
    """'Nova measures ball flight, not face contact' is an honesty label about
    estimated data. Decoration must never be what hides it."""
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        items = _panel_items(app)
        footer = [(z, b) for kind, z, b, t in items
                  if kind == "text" and "Nova measures" in t]
        assert footer, "the Nova disclaimer is missing from the Quad view"

        for tz, tb in footer:
            for z, cb in _occluders(items):
                if z <= tz:
                    continue
                ox = min(tb[2], cb[2]) - max(tb[0], cb[0])
                oy = min(tb[3], cb[3]) - max(tb[1], cb[1])
                assert not (ox > 40 and oy > 8), f"disclaimer covered by {cb}"
    finally:
        root.destroy()


def test_the_credibility_badge_does_not_sit_on_the_caption(tmp_path, monkeypatch):
    """The current credibility badge must clear the impact caption."""
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        items = _panel_items(app)
        caption = next((b for kind, _, b, t in items
                        if kind == "text" and t == "IMPACT LOCATION"), None)
        badge = next((b for kind, _, b, t in items
                      if kind == "text" and t == "UNAVAILABLE"),
                     None)
        assert caption is not None, "impact caption missing"
        assert badge is not None, "native ball-flight-only shot must say UNAVAILABLE"
        assert badge[0] >= caption[2], (
            f"badge starts x{badge[0]} but caption runs to x{caption[2]}"
        )
    finally:
        root.destroy()


def test_no_panel_label_is_substantially_covered(tmp_path, monkeypatch):
    """Catch-all: nothing drawn later may bury a label in this panel."""
    root, app = _quad_app(tmp_path, monkeypatch)
    try:
        items = _panel_items(app)
        texts = [(z, b, t) for kind, z, b, t in items
                 if kind == "text" and t]
        covers = _occluders(items)

        buried = []
        for tz, tb, label in texts:
            for cz, cb in covers:
                if cz <= tz:
                    continue
                ox = min(tb[2], cb[2]) - max(tb[0], cb[0])
                oy = min(tb[3], cb[3]) - max(tb[1], cb[1])
                if ox > (tb[2] - tb[0]) * 0.5 and oy > (tb[3] - tb[1]) * 0.5:
                    buried.append(f"{label[:28]!r} under {cb}")
        assert not buried, "panel text is covered: " + "; ".join(buried)
    finally:
        root.destroy()
