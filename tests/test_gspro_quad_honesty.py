"""Quad view must not fabricate club-delivery data GSPro never sent.

GSPro's driving-range DB only reports ball-flight fields (Carry, BallSpeed,
VLA, HLA, spin) -- it has no Path/FaceToPath/FaceToTarget columns, so
src/gspro/mapper.py correctly leaves ogc.club_path_degrees etc. absent
from the payload. The quad view was reading that absence as 0.0 and
rendering a fake dead-straight, dead-centre shot for EVERY GSPro shot --
indistinguishable from a real flush strike. This locks in the fix: those
specific readouts must say "not measured" instead of drawing invented
zeros.
"""

import pytest


def _quad_app_with_shot(ogc_extra=None):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display")
    root.geometry("1600x950")
    from src.ui.desktop import ShanktuaryDesktopApp

    app = ShanktuaryDesktopApp(root)
    app.view_mode = 1  # Quad

    ogc = {
        "us_customary_units": {
            "ball_speed_mph": 145.0,
            "carry_distance_yards": 210.0,
        },
    }
    if ogc_extra:
        ogc.update(ogc_extra)

    shot = {
        "type": "shot",
        "_source": "gspro",
        "club": "7 Iron",
        "ball_speed_meters_per_second": 64.8,
        "vertical_launch_angle_degrees": 18.2,
        "horizontal_launch_angle_degrees": 1.5,
        "open_golf_coach": ogc,
    }
    sess = app.get_active_session()
    sess["shots"] = [shot]
    app.selected_shot_index = 0
    app.current_shot = shot

    app.draw_screen()
    root.update_idletasks()
    return root, app


def _canvas_texts(app):
    out = []
    for item in app.canvas.find_all():
        if app.canvas.type(item) == "text":
            out.append(app.canvas.itemcget(item, "text"))
    return out


def test_gspro_shot_with_no_club_data_shows_not_measured():
    """The exact scenario reported: GSPro shot, no Path/FaceToPath/FaceToTarget."""
    root, app = _quad_app_with_shot(ogc_extra={})
    try:
        texts = _canvas_texts(app)
        joined = " | ".join(texts)
        assert "not measured" in joined, (
            "quad view has no 'not measured' state for missing club data "
            f"-- texts were: {texts}"
        )
        # Specifically CLUB PATH's own readout, not just some other caption.
        idx = texts.index("CLUB PATH")
        assert texts[idx + 1] == "not measured", (
            f"CLUB PATH should read 'not measured' with no source data, got {texts[idx + 1]!r}"
        )
        # The fabricated-zero symptom: a fake "Neutral path" claim with no
        # real data behind it must not appear.
        assert "Neutral path" not in joined, (
            "quad view is still claiming a neutral/flush path with no "
            "club-path data present -- this is the bug being fixed"
        )
    finally:
        root.destroy()


def test_shot_with_real_club_data_still_shows_real_values():
    """A Nova-style shot WITH club_path_degrees must render the real number,
    not fall back to the honest-absence path meant for GSPro."""
    root, app = _quad_app_with_shot(ogc_extra={
        "club_path_degrees": 4.2,
        "club_face_to_path_degrees": -1.1,
        "club_face_to_target_degrees": 3.1,
    })
    try:
        texts = _canvas_texts(app)
        joined = " | ".join(texts)
        assert "4.2°" in joined, f"real club path value missing -- texts: {texts}"
        # Check specifically that CLUB PATH's own value isn't "not measured"
        # (attack angle legitimately says "not measured" elsewhere in this
        # view -- that assertion must not be confused by it).
        idx = texts.index("CLUB PATH")
        assert texts[idx + 1] != "not measured", (
            "CLUB PATH shows 'not measured' despite real data being present"
        )
    finally:
        root.destroy()


def test_zero_club_path_is_distinguishable_from_missing_club_path():
    """A genuinely dead-neutral 0.0° path (real data) must still render as
    0.0°, not be swallowed by the 'missing' branch."""
    root, app = _quad_app_with_shot(ogc_extra={
        "club_path_degrees": 0.0,
        "club_face_to_path_degrees": 0.0,
    })
    try:
        texts = _canvas_texts(app)
        joined = " | ".join(texts)
        assert "0.0°" in joined, (
            f"a real 0.0-degree measurement was swallowed as 'not measured' -- texts: {texts}"
        )
    finally:
        root.destroy()


def _overview_app_with_shot(ogc_extra=None):
    """Same fixture, but landing on Overview (view_mode 9) -- the default
    landing page and the actual live code path the reported bug hit
    (src/ui/_legacy/overview_redesign*.py, not the base-file draw_overview_viewport)."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display")
    root.geometry("1600x950")
    from src.ui.desktop import ShanktuaryDesktopApp

    app = ShanktuaryDesktopApp(root)
    app.view_mode = 9  # Overview -- the landing view

    ogc = {
        "us_customary_units": {
            "ball_speed_mph": 145.0,
            "carry_distance_yards": 210.0,
        },
    }
    if ogc_extra:
        ogc.update(ogc_extra)

    shot = {
        "type": "shot",
        "_source": "gspro",
        "club": "7 Iron",
        "ball_speed_meters_per_second": 64.8,
        "vertical_launch_angle_degrees": 18.2,
        "horizontal_launch_angle_degrees": 1.5,
        "open_golf_coach": ogc,
    }
    sess = app.get_active_session()
    sess["shots"] = [shot]
    app.selected_shot_index = 0
    app.current_shot = shot

    app.draw_screen()
    root.update_idletasks()
    return root, app


def test_overview_gspro_shot_with_no_club_data_does_not_claim_neutral_path():
    """The exact live bug: Overview (default landing page) fabricated a
    'Neutral path · face nearly square to path' takeaway for shots GSPro
    never reported club data for."""
    root, app = _overview_app_with_shot(ogc_extra={})
    try:
        texts = _canvas_texts(app)
        joined = " | ".join(texts)
        assert "Neutral path" not in joined, (
            "Overview's delivery takeaway still claims a neutral/flush path "
            f"with no club data present -- texts: {texts}"
        )
        assert "not measured" in joined or "not reported" in joined, (
            f"Overview has no honest absence state for missing club data -- texts: {texts}"
        )
    finally:
        root.destroy()


def test_overview_shot_with_real_club_data_shows_real_values():
    root, app = _overview_app_with_shot(ogc_extra={
        "club_path_degrees": 5.5,
        "club_face_to_path_degrees": -0.8,
        "club_face_to_target_degrees": 2.0,
    })
    try:
        texts = _canvas_texts(app)
        joined = " | ".join(texts)
        assert "5.5°" in joined, f"real club path value missing from Overview -- texts: {texts}"
    finally:
        root.destroy()
