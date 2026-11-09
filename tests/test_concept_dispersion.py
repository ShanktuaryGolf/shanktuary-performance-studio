"""Dispersion summaries, honest estimated paths and reachable group pages."""
import math
from types import SimpleNamespace

import pytest
from test_concept_workspaces import Canvas

from src.ui import concept_workspaces as ui


def shot(club="7 Iron", carry=150, offline=0, apex=25, **extra):
    return {"club": club, "open_golf_coach": {"us_customary_units": {
        "carry_distance_yards": carry, "offline_distance_yards": offline,
        "peak_height_yards": apex, "total_distance_yards": carry + 5}}, **extra}


def app(shots):
    a = SimpleNamespace(canvas=Canvas(), session_shots=shots,
        sessions=[{"shots": shots}], active_session_index=0,
        current_club="7 Iron", is_left_handed=False, view_mode=3,
        dispersion_view_submode="split", dispersion_split_by_ball=False,
        aim_corrected=lambda s: s, get_club_color=lambda _: ui.AQUA)
    a.draw_screen = lambda: ui.draw_dispersion(a, 1300, 900, 260)
    return a


def test_quantile_interpolates_and_does_not_claim_min_max():
    assert ui._percentile([0, 10, 20], .1) == 2
    assert ui._percentile([0, 10, 20], .9) == 18
    assert ui._percentile([7], .9) == 7
    assert ui._percentile([], .9) is None


def test_normal_model_extents_use_lateral_width_carry_depth():
    pairs = [(100, -5), (110, 0), (120, 5)]
    w, d = ui._ellipse_spread(pairs)
    assert d == pytest.approx(2 * w)
    assert w == pytest.approx(2 * math.sqrt(-2 * math.log(.1)) * math.sqrt(50 / 3))
    assert ui._ellipse_spread(pairs[:2]) is None
    assert ui._ellipse_spread([(1, None), (1, float('nan'))]) is None


def test_individual_paths_are_explicit_estimates_missing_apex_not_invented():
    a = app([shot(carry=140), shot(carry=160), shot(apex=None)])
    a.draw_screen()
    paths = [i for i in a.canvas.items if i[2].get('tags') == 'estimated-shot-path']
    assert len(paths) == 2
    assert paths[0][1] != paths[1][1]
    assert all(i[2]['dash'] == (5, 2) for i in paths)
    assert any('not measured flight' in w for w in a.canvas.words())
    assert '90% W × D (yd)' in a.canvas.words()
    assert any('90% normal-model extent:' in w for w in a.canvas.words())
    assert len(a.dispersion_dot_rects) == 3


def test_paging_reaches_all_ball_groups_preserves_tabs_and_clamps_on_change():
    a = app([shot(ball=f"Ball {i}") for i in range(18)])
    a.dispersion_split_by_ball = True
    seen = set()
    while True:
        a.canvas = Canvas()
        a.draw_screen()
        seen.update(r[-1] for r in a.dispersion_club_chip_rects if r[-1] != 'ALL')
        assert [key for rect, key in a.design_dispersion_tab_rects] == ['split', 'topdown', 'side']
        nxt = [(rect, page) for rect, page in a.dispersion_page_rects if page > a.dispersion_group_page]
        if not nxt:
            break
        rect, page = nxt[0]
        assert ui.handle_dispersion_click(a, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
        assert a.dispersion_group_page == page
    assert len(seen) == 18
    a.session_shots = []
    a.draw_screen()
    assert a.dispersion_group_page == 0
    assert a.dispersion_page_rects == []
    assert not ui.handle_dispersion_click(a, 0, 0)


def test_spread_comparison_requires_paired_shots_and_excludes_marked_rows():
    previous = [shot(carry=x, offline=y) for x, y in [(140, -10), (150, 0), (160, 10)]]
    current = [shot(carry=x, offline=y) for x, y in [(145, -5), (150, 0), (155, 5)]]
    current.append(shot(carry=500, offline=100, excluded=True))
    a = app(current)
    a.sessions = [{'shots': previous}, {'shots': current}]
    a.active_session_index = 1
    a.draw_screen()
    assert '17.5 × 17.5' in a.canvas.words()
    assert '35.0 × 35.0' in a.canvas.words()
    assert '-17.5 × -17.5' in a.canvas.words()


def test_selected_ball_group_comparison_does_not_mix_other_balls():
    a = app([shot(ball='A', carry=100), shot(ball='B', carry=200)])
    a.dispersion_split_by_ball = True
    a.dispersion_selected_club = '7 Iron · A'
    a.sessions = [{'shots': [shot(ball='A', carry=90), shot(ball='B', carry=300)]}, {'shots': a.session_shots}]
    a.active_session_index = 1
    a.draw_screen()
    assert '90.0' in a.canvas.words()
    assert '100.0' in a.canvas.words()
    assert '+10.0' in a.canvas.words()
    assert len(a.dispersion_dot_rects) == 1
