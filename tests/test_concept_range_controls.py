from types import SimpleNamespace

from src.ui.concept_metrics import handle_range_click


def app():
    return SimpleNamespace(
        session_shots=[{"id": 1}, {"id": 2}],
        draw_screen=lambda: None,
        concept_range_rects=[((1, 1, 20, 20), "clear")],
    )


def test_clear_display_keeps_session_data_and_is_reversible():
    a = app()
    original = a.session_shots
    assert handle_range_click(a, 10, 10)
    assert a.concept_range_after == 2
    assert a.session_shots is original
    assert original == [{"id": 1}, {"id": 2}]
    assert handle_range_click(a, 10, 10)
    assert a.concept_range_after == 0


def test_target_picker_changes_only_display_target_then_closes():
    a = app()
    a.concept_range_rects = [((1, 1, 20, 20), "target")]
    assert handle_range_click(a, 10, 10)
    assert a.concept_range_target_open
    a.concept_range_rects = [((1, 1, 20, 20), "target:200")]
    assert handle_range_click(a, 10, 10)
    assert a.concept_range_target == 200
    assert not a.concept_range_target_open
    assert a.session_shots == [{"id": 1}, {"id": 2}]


def test_downrange_projection_uses_distance_depth_not_side_profile():
    from src.ui.concept_metrics import downrange_trajectory, project_downrange
    bounds=(260,180,1600,930)
    tee=project_downrange(0,0,0,bounds)
    landing=project_downrange(150,0,0,bounds)
    assert tee[0] == landing[0] == 930
    assert landing[1] < tee[1]
    assert project_downrange(150,-10,0,bounds)[0] < landing[0]
    assert project_downrange(150,10,0,bounds)[0] > landing[0]
    assert project_downrange(150,0,20,bounds)[1] < landing[1]
    points=downrange_trajectory(150,29,-10,bounds,1.0)
    assert points[0] == tee
    assert points[-1] == project_downrange(150,-10,0,bounds)
    assert any(p[0] > tee[0] for p in points[1:8])  # real start line before draw
    assert points[-1][0] < tee[0]
