"""Pressure vs result: what the boards say about your best and worst shots."""
import pytest

from src.analytics import pressure_result as pr


def _shot(carry, pct_left=None, torque=None, club="7 Iron", bs=105.0, **extra):
    s = {"club": club, "total_spin_rpm": 6500.0, "vertical_launch_angle_degrees": 18.0,
         "open_golf_coach": {"us_customary_units": {"ball_speed_mph": bs, "carry_distance_yards": carry}}}
    if pct_left is not None or torque is not None:
        s["pressure_metrics"] = {"pct_left_at_impact": pct_left, "peak_torque_nm": torque,
                                 "peak_pct_right_backswing": 60.0, "frame_count": 400}
    s.update(extra)
    return s


def test_splits_traced_full_swings_into_best_and_worst_thirds_by_carry():
    shots = [_shot(140 + i, pct_left=55 + i, torque=20 + i) for i in range(12)]  # 12 traced
    shots += [_shot(150) for _ in range(5)]                                        # untraced
    r = pr.compare("7 Iron", shots)
    assert r["traced"] == 12 and r["untraced"] == 5
    assert r["best"]["n"] == 4 and r["worst"]["n"] == 4
    assert r["best"]["carry"] == pytest.approx(149.5)
    assert r["worst"]["carry"] == pytest.approx(141.5)
    assert r["best"]["pct_lead_at_impact"] == pytest.approx(64.5)
    assert r["worst"]["pct_lead_at_impact"] == pytest.approx(56.5)
    assert r["best"]["peak_torque_nm"] == pytest.approx(29.5)
    assert r["status"] == "available"


def test_needs_at_least_six_traced_shots():
    shots = [_shot(140 + i, pct_left=55 + i) for i in range(5)]
    r = pr.compare("7 Iron", shots)
    assert r["status"] == "insufficient"
    assert r["traced"] == 5
    assert "6" in r["reason"]


def test_uses_the_index_full_swing_gate_and_ignores_other_clubs():
    shots = [_shot(140 + i, pct_left=55 + i) for i in range(9)]
    shots += [_shot(4.0, pct_left=99.0, bs=8.0) for _ in range(6)]            # tops: traced but not full swings
    shots += [_shot(100, pct_left=10.0, club="PW") for _ in range(6)]        # another club
    r = pr.compare("7 Iron", shots)
    assert r["traced"] == 9
    assert r["worst"]["pct_lead_at_impact"] < 60


def test_missing_metric_on_some_shots_does_not_become_zero():
    shots = [_shot(140 + i, pct_left=(None if i % 2 else 60.0), torque=None) for i in range(12)]
    r = pr.compare("7 Iron", shots)
    assert r["best"]["pct_lead_at_impact"] == pytest.approx(60.0)
    assert r["best"]["peak_torque_nm"] is None
    assert r["best"]["n_pct_lead"] == 2


def test_sentence_is_only_written_when_the_gap_is_meaningful():
    shots = [_shot(140 + i, pct_left=55 + i) for i in range(12)]
    r = pr.compare("7 Iron", shots)
    assert r["headline"] == "Best 7 irons: 65% lead foot at impact · worst: 57%"
    lefty = pr.compare("7 Iron", shots, is_left_handed=True)
    assert lefty["best"]["pct_lead_at_impact"] == pytest.approx(35.5)
    flat = [_shot(140 + i, pct_left=60.0) for i in range(12)]
    assert pr.compare("7 Iron", flat)["headline"] == "Lead-foot at impact ~60% on best and worst 7 irons"


def test_per_shot_line_for_the_shot_view():
    assert pr.shot_line(_shot(150, pct_left=72.3, torque=31.5)) == "72% lead foot · 31.5 N·m peak"
    assert pr.shot_line(_shot(150, pct_left=72.3)) == "72% lead foot"
    assert pr.shot_line(_shot(150)) is None
    # Lead foot is the RIGHT plate for a lefty (same convention as Swing Lab).
    assert pr.shot_line(_shot(150, pct_left=72.3), is_left_handed=True) == "28% lead foot"


# --- surfaced in the UI ---------------------------------------------------------

def _canvas_texts(canvas):
    return [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]


def test_shot_view_delivery_panel_shows_pressure_line_and_drops_estimated_tag():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        from types import SimpleNamespace

        import overview_redesign_v11 as v11

        import shanktuary_app  # noqa: F401  (registers the private renderer path)
        canvas = tk.Canvas(root, width=900, height=600)
        app = SimpleNamespace(canvas=canvas, is_left_handed=False,
                              current_shot=_shot(150, pct_left=72.3, torque=31.5),
                              summarize_strike=lambda s: ("Location unavailable", "x", "#fff"),
                              get_scaled_club_asset=lambda *a, **k: None)
        v11._draw_strike(app, 20, 20, 420, 300)
        texts = _canvas_texts(canvas)
        assert "72% lead foot · 31.5 N·m peak" in texts
        assert "· Estimated" not in texts
        # Nothing may leave the box, and no text may sit under the face marker.
        ovals = [canvas.bbox(i) for i in canvas.find_all() if canvas.type(i) == "oval"]
        boxes = [(canvas.bbox(i), canvas.itemcget(i, "text")) for i in canvas.find_all()
                 if canvas.type(i) == "text"]
        for b, s in boxes:
            assert b[3] <= 300 and b[2] <= 422, (s, b)
            for o in ovals:
                assert not (min(b[2], o[2]) > max(b[0], o[0]) and min(b[3], o[3]) > max(b[1], o[1])), (s, b, o)
        for j, (b, s) in enumerate(boxes):
            for d, u in boxes[j + 1:]:
                assert not (min(b[2], d[2]) > max(b[0], d[0]) and min(b[3], d[3]) > max(b[1], d[1])), (s, u)
        canvas.delete("all")
        app.current_shot = _shot(150)
        v11._draw_strike(app, 20, 20, 420, 300)
        assert not any("lead foot" in t for t in _canvas_texts(canvas))
    finally:
        root.destroy()


def test_index_detail_pane_prints_the_pressure_sentence_per_club():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        import shanktuary_performance_studio as studio
        shots = [_shot(140 + i, pct_left=55 + i) for i in range(12)]
        canvas = tk.Canvas(root, width=1900, height=980)
        app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
        app.canvas, app.root, app.sessions, app.is_left_handed = canvas, root, [{"shots": shots}], False
        result = {"status": "insufficient_coverage", "reason": "x", "game_areas": {},
                  "established_clubs": [], "clubs": {"7 Iron": {"composite": {"score": 60.0, "confidence": 1}}}}
        studio.ShanktuaryApp._draw_index_detail_pane(app, 700, 104, 1100, 800, result)
        texts = _canvas_texts(canvas)
        assert "Best 7 irons: 65% lead foot at impact · worst: 57%" in texts, texts
    finally:
        root.destroy()
