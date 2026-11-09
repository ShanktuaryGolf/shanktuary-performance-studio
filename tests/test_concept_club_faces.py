"""Club-specific artwork keeps marks in one reversible, schematic mm model."""
from pathlib import Path

import pytest
from PIL import Image

from src.ui.concept_art import club_face_kind, club_face_layout


@pytest.mark.parametrize('club,kind', [
    ('Driver','driver'),('1W','driver'),('3 Wood','driver'),('4 Hybrid','driver'),
    ('5h','driver'),('Putter','putter'),('PT','putter'),('7 Iron','iron'),
    ('PW','iron'),('Pitching Wedge','iron'),('60°','iron'),('', 'iron')])
def test_club_family(club, kind):
    assert club_face_kind(club) == kind


@pytest.mark.parametrize('club', ['7 Iron', 'Driver', 'Putter'])
@pytest.mark.parametrize('left', [False, True])
@pytest.mark.parametrize('rect', [(0,0,300,180),(250,100,650,400),(0,0,120,70)])
def test_art_fits_and_marks_roundtrip(club, left, rect):
    path, bounds, geom = club_face_layout(club, rect, left)
    assert Path(path).is_file()
    assert bounds[0] >= rect[0] and bounds[1] >= rect[1]
    assert bounds[2] <= rect[2] and bounds[3] <= rect[3]
    for h,v in [(0,0),(-24,16),(24,-16),(8,4)]:
        x,y = geom.mm_to_px(h,v)
        assert geom.px_to_mm(x,y) == pytest.approx((h,v))
        assert bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]
    assert geom.px_to_mm(*geom.mm_to_px(25,0)) is None
    with Image.open(path) as source:
        assert source.size == (1536,1024)
        assert source.mode == 'RGBA'


def test_handedness_mirrors_schematic_not_data():
    rect=(0,0,300,180)
    _,bounds,rh=club_face_layout('Driver',rect,False)
    _,_,lh=club_face_layout('Driver',rect,True)
    for h,v in [(0,0),(20,10),(-20,-10)]:
        rx,ry=rh.mm_to_px(h,v)
        lx,ly=lh.mm_to_px(h,v)
        assert lx == pytest.approx(bounds[0]+bounds[2]-rx)
        assert ly == pytest.approx(ry)


def test_selected_shot_controls_art_and_payload_is_untouched():
    from copy import deepcopy

    from test_concept_session import App

    from src.ui.concept_session import contact
    shots = [{'club': 'Driver', '_source': 'pureplay'},
             {'club': 'Putter', '_source': 'pureplay'},
             {'club': '7 Iron', '_source': 'pureplay'}]
    app = App(shots)
    app.current_club = 'Putter'
    calls = []
    app.get_scaled_club_asset = lambda path, *args, **kwargs: calls.append(path)
    before = deepcopy(shots)
    for index, kind in enumerate(('driver','putter','iron')):
        app.current_shot = shots[index]
        contact(app, (0,0,350,300))
        assert calls[-1].endswith(f'studio_{kind}_face.png')
    app.current_shot = {'_source': 'pureplay'}
    contact(app, (0,0,350,300))
    assert calls[-1].endswith('studio_putter_face.png')
    assert shots == before


@pytest.mark.parametrize('club', ['7 Iron','Driver','Putter'])
def test_contact_boundary_tolerance_does_not_expand_playable_face(club):
    _, _, geom = club_face_layout(club, (0,0,300,180))
    for h,v in [(24,16),(-24,-16),(24,-16),(-24,16)]:
        assert geom.px_to_mm(*geom.mm_to_px(h,v)) == pytest.approx((h,v))
    for h,v in [(24.0001,0),(-24.0001,0),(0,16.0001),(0,-16.0001)]:
        assert geom.px_to_mm(*geom.mm_to_px(h,v)) is None
