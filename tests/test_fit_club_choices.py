"""Fit selection and new-club scope never promote temporary equipment to Bag."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import shanktuary_performance_studio as studio


def app_stub():
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = [{"id": "one", "shots": [{"club": "7 Iron", "payload": {"keep": 1}}]}]
    app.active_session_index = 0
    app.bag = [{"name": name, "loft_deg": 20} for name in
               ("Driver", "3 Wood", "5 Wood", "3 Hybrid", "7 Iron", "9 Iron", "SW", "Putter")]
    app.clubs = [club["name"] for club in app.bag]
    app.current_club = "7 Iron"
    app.root = SimpleNamespace(after=lambda *a: None)
    app.draw_screen = lambda: None
    app.saved = []
    app.save_session_to_file = lambda: app.saved.append(deepcopy((app.sessions, app.bag, app.clubs)))
    app.open_club_spec_editor = lambda name: setattr(app, "edited", name)
    return app


def test_candidates_include_entire_bag_session_and_unhit_custom_clubs():
    app = app_stub()
    app.sessions[0]["fitting_clubs"] = ["Demo wedge", "7 Iron"]
    app.sessions[0]["shots"].append({"club": "Old test"})
    clubs = app.get_fitting_clubs()
    assert {c["name"] for c in app.bag} <= set(clubs)
    assert {"Old test", "Demo wedge"} <= set(clubs)
    assert len(clubs) == len(set(clubs))


def test_session_only_default_preserves_bag_and_global_custom_names():
    app = app_stub()
    before_bag, before_names, before_shots = deepcopy((app.bag, app.clubs, app.session_shots))
    app.add_custom_club("  Demo wedge  ")
    app.add_custom_club("Demo wedge")
    assert app.bag == before_bag and app.clubs == before_names
    assert app.session_shots == before_shots
    assert app.sessions[0]["fitting_clubs"] == ["Demo wedge"]
    assert app.current_club == app.concept_fit_test_club == "Demo wedge"
    assert not hasattr(app, "edited")
    # Session metadata survives saving without entering the legacy custom_clubs
    # list that load_session_history automatically adopts into My Bag.
    sessions, bag, names = app.saved[-1]
    assert sessions[0]["fitting_clubs"] == ["Demo wedge"]
    assert "Demo wedge" not in names and bag == before_bag
    app.sessions.append({"id": "two", "shots": []})
    app.active_session_index = 1
    app.current_club = "7 Iron"
    assert "Demo wedge" not in app.get_fitting_clubs()


def test_permanent_choice_adds_once_and_opens_specs():
    app = app_stub()
    app.add_custom_club("Demo wedge", persist_to_bag=True)
    app.add_custom_club("Demo wedge", persist_to_bag=True)
    assert sum(club["name"] == "Demo wedge" for club in app.bag) == 1
    assert app.clubs.count("Demo wedge") == 1
    assert app.edited == "Demo wedge"
    assert app.concept_fit_test_club == "Demo wedge"


def test_open_resets_destination_to_session():
    app = app_stub()
    app.custom_club_scope = "bag"
    app.open_custom_club_modal()
    assert app.custom_club_scope == "session"
    assert app.show_custom_club_modal


@pytest.mark.parametrize("height", [720, 900, 1080, 1440])
@pytest.mark.parametrize("angle", [-90, -45, 0, 30, 75])
def test_overhead_sprite_stays_inside_top_card(height, angle):
    from test_concept_session import App

    from src.ui.concept_session import draw_club
    app = App([{"club": "7 Iron", "open_golf_coach": {
        "club_face_to_target_degrees": {"right_handed": angle}}}])
    sizes = []
    def image(size, rotation, **kwargs):
        sizes.append(kwargs["max_extent"])
        return "overhead"
    app.get_rotated_overhead_asset = image
    draw_club(app, 1320, height, 260)
    _, coords, _ = next(item for item in app.canvas.items
                        if item[0] == "create_image" and item[2].get("image") == "overhead")
    extent = sizes[0]
    top = 186
    middle = top + (height - 110 - top - 14) * .45 + 7
    assert coords[1] - extent / 2 >= top + 89
    assert coords[1] + extent / 2 <= middle - 7


@pytest.mark.parametrize("angle", [-90, -45, 0, 30, 75])
def test_actual_rotated_asset_is_bounded(monkeypatch, angle):
    monkeypatch.setattr(studio.ImageTk, "PhotoImage", lambda image: image)
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app._cached_image = lambda key: None
    app._cache_image = lambda key, image: image
    for limit in (40, 100, 250):
        image = app.get_rotated_overhead_asset(250, angle, max_extent=limit)
        assert image is not None
        assert max(image.size) <= limit
