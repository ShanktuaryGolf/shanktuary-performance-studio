"""Headless render contracts: established composition, honest absent metrics."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.connections.pureplay import map_pureplay_shot_to_sps_payload
from src.ui.connection_pages import draw_connection_page


class Canvas:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def draw(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return draw


def make_shot():
    return map_pureplay_shot_to_sps_payload(dict(
        shotId='one', sessionId='session', bFromLaunchMonitor=True,
        ballSpeed=50, ballSpeedRaw=40, vLA=12, hLA=0, totalSpin=3000,
        spinAxis=0, carryDistanceM=150, totalDistanceM=160,
        restTime='2026.11.08-18.00.00', clubHeadSpeed=99, attackAngle=0))[0]


def render(mode, width=1450, height=1000, shot=None):
    shot = shot if shot is not None else make_shot()
    app = SimpleNamespace(canvas=Canvas(), view_mode=mode, current_shot=shot,
                          session_shots=[shot], current_club='7 Iron', is_left_handed=False,
                          aim_corrected=lambda s: s)
    before = deepcopy(shot)
    draw_connection_page(app, width, height, 300)
    assert shot == before
    return app


def texts(app):
    return [kw['text'] for name, _, kw in app.canvas.calls if name == 'create_text']


@pytest.mark.parametrize('width,height', [(1450,1000), (1050,768), (800,900)])
def test_shot_keeps_overview_sections_and_no_invented_shape(width, height):
    app = render(9, width, height)
    text = texts(app)
    for title in ('Shot Overview', 'Dispersion', 'Shot Shape', 'Strike', 'Club Delivery', 'Session'):
        assert title in text
    assert 'Carry or offline not reported\nLanding positions unavailable' in text
    assert 'ESTIMATED' in text
    assert 'NOT REPORTED' in text
    assert not any('Straight' in t or 'Nova' in t or 'FLUSH' in t for t in text)
    assert not any(name == 'create_oval' for name, _, _ in app.canvas.calls)
    assert app.contact_face_geometry is None
    assert app.overview_bar_rects == []
    # Entire main composition stays inside the supplied viewport.
    for name, args, _ in app.canvas.calls:
        if name == 'create_text':
            assert 300 <= args[0] < 300+width
            assert 52 <= args[1] < height


def test_club_keeps_distinct_panels_and_zero_is_reported():
    app = render(1)
    text = texts(app)
    assert all(label in text for label in ('Club Delivery', 'Launch & Delivery', 'Spin', 'Strike'))
    assert '0.0 deg' in text
    assert text.count('--') >= 8
    assert text.count('NOT REPORTED') >= 8
    assert not any('99' in t or 'Nova' in t for t in text)


def test_missing_all_metrics_never_draws_landing_or_launch_geometry():
    app = render(9, shot={'_source': 'pureplay'})
    assert not any(name == 'create_oval' or kw.get('arrow') for name, _, kw in app.canvas.calls)
    assert 'NOT REPORTED' in texts(app)


def test_modelled_shape_shows_handed_label_and_provenance():
    from src.connections.presentation import shot_shape
    shot = make_shot()
    shot['open_golf_coach']['shot_name'] = {'right_handed': 'Straight Fade', 'left_handed': 'Straight Draw'}
    shot['_metric_provenance']['open_golf_coach.shot_name'] = {'kind': 'modelled'}
    assert 'Straight Fade | MODELLED' in texts(render(9, shot=shot))
    assert shot_shape(shot, True) == ('Straight Draw', 'MODELLED')
    shot['shot_name'] = 'Source label'
    assert shot_shape(shot, True) == ('Source label', 'REPORTED')


def test_neutral_clubface_uses_existing_asset_without_a_strike_marker():
    app = render(1)
    marker = object()
    requested = []
    app.canvas.calls.clear()
    app.get_scaled_club_asset = lambda path, size, **kw: requested.append((path, size)) or marker
    draw_connection_page(app, 1450, 1000, 300)
    assert requested and requested[0][0].endswith('.png')
    assert any(name == 'create_image' and kw['image'] is marker for name, _, kw in app.canvas.calls)
    assert not any(name == 'create_oval' for name, _, _ in app.canvas.calls)


def test_routing_keeps_other_sources_on_existing_renderer():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'shanktuary_performance_studio.py').read_text(encoding='utf-8')
    assert "draw_connection_page(self" not in source
    assert 'get("_source") in ("cgp", "open_connect", "gspro") and self.view_mode in (0, 1, 9)' in source


def test_excluded_only_history_is_not_repopulated_in_session():
    shot = make_shot()
    shot['excluded'] = True
    app = render(9, shot=shot)
    assert '0 shots for this club' in texts(app)
    assert not any(name == 'create_oval' for name, _, _ in app.canvas.calls)


def test_current_marker_matches_identity_after_aim_corrected_copy():
    shot = make_shot()
    shot['open_golf_coach']['offline_distance_meters'] = 2
    other = deepcopy(shot)
    other['shotId'] = 'older'
    app = render(9, shot=shot)
    app.session_shots = [other, shot]
    app.aim_corrected = deepcopy
    app.canvas.calls.clear()
    draw_connection_page(app, 1450, 1000, 300)
    widths = [args[2]-args[0] for name, args, _ in app.canvas.calls if name == 'create_oval']
    assert widths == [6, 12]


def test_real_tk_text_bounding_boxes_do_not_overlap():
    import tkinter as tk
    from itertools import combinations

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if "no display name" in str(exc).lower() or "couldn't connect to display" in str(exc).lower():
            pytest.skip(f"Tk display unavailable: {exc}")
        raise
    root.withdraw()
    root.tk.call('tk', 'scaling', 96 / 72)
    try:
        for mode in (1, 9):
            for width, height in ((800, 900), (1450, 1000)):
                app = render(mode, width, height)
                app.canvas = tk.Canvas(root, width=width, height=height)
                draw_connection_page(app, width, height)
                root.update_idletasks()
                items = [item for item in app.canvas.find_all() if app.canvas.type(item) == 'text']
                for first, second in combinations(items, 2):
                    a, b = app.canvas.bbox(first), app.canvas.bbox(second)
                    overlaps = (max(a[0], b[0]) < min(a[2], b[2])
                                and max(a[1], b[1]) < min(a[3], b[3]))
                    assert not overlaps, (mode, width, app.canvas.itemcget(first, 'text'),
                                          app.canvas.itemcget(second, 'text'), a, b)
                app.canvas.destroy()
    finally:
        root.destroy()
