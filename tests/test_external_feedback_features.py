"""Per-shot delete, per-club notes, and session notes.

Feature set requested via external feedback: hard-delete a single shot from
the active session, freeform notes on a bag club (surfaced in the spec
editor), and freeform notes on a session (surfaced in the session dropdown).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real app whose session file is a THROWAWAY copy.

    Never point tests at the user's own shanktuary_session_history.json.
    """
    import shanktuary_performance_studio as studio

    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1400x900")
    application = ShanktuaryDesktopApp(root)

    application.sessions = [
        {"id": "a", "name": "Session 1 - 7 Iron", "created_at": "x",
         "shots": [
             {"club": "7 Iron", "timestamp": "1:00", "open_golf_coach": {}},
             {"club": "7 Iron", "timestamp": "1:01", "open_golf_coach": {}},
             {"club": "7 Iron", "timestamp": "1:02", "open_golf_coach": {}},
         ]},
    ]
    application.active_session_index = 0
    application.selected_shot_index = -1
    application.current_shot = None
    root.update()
    yield root, application
    try:
        root.destroy()
    except tk.TclError:
        pass


# ---- Per-shot delete ------------------------------------------------------

def test_deleting_a_shot_asks_first_and_can_be_cancelled(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: False)
    assert application.delete_shot(1) is False
    assert len(application.session_shots) == 3


def test_confirmed_delete_pops_shot(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    assert application.delete_shot(1) is True
    remaining = application.session_shots
    assert len(remaining) == 2
    assert [s["timestamp"] for s in remaining] == ["1:00", "1:02"]


def _session_log_path():
    import shanktuary_performance_studio as studio
    return studio.SESSION_LOG_PATH


def test_confirmed_delete_persists_to_disk(app, monkeypatch):
    _root, application = app
    import json
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    application.delete_shot(0)

    with open(_session_log_path()) as f:
        data = json.load(f)
    saved_shots = data["sessions"][0]["shots"]
    assert len(saved_shots) == 2
    assert [s["timestamp"] for s in saved_shots] == ["1:01", "1:02"]


def test_delete_shot_out_of_range_is_a_noop(app):
    _root, application = app
    assert application.delete_shot(99) is False
    assert len(application.session_shots) == 3
    assert application.delete_shot(-1) is False


def test_delete_shot_reclamps_selection_when_selected_shot_removed(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    application.selected_shot_index = 2
    application.current_shot = application.session_shots[2]

    application.delete_shot(2)
    assert application.selected_shot_index == 1
    assert application.current_shot == application.session_shots[-1]


def test_delete_last_shot_clears_selection(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    application.delete_shot(0)
    application.delete_shot(0)
    application.delete_shot(0)
    assert application.session_shots == []
    assert application.selected_shot_index == -1
    assert application.current_shot is None


def test_draw_screen_registers_shot_delete_rects(app):
    _root, application = app
    application.draw_screen()
    assert isinstance(application.shot_delete_btn_rects, list)
    # 3 fixture shots should each have a registered delete hitbox.
    assert len(application.shot_delete_btn_rects) == 3
    for x1, y1, x2, y2, idx in application.shot_delete_btn_rects:
        assert 0 <= idx < 3


# ---- Club notes -------------------------------------------------------

def test_update_club_specs_notes_round_trips_through_saved_file(app):
    _root, application = app
    import json

    club_name = application.bag[0]["name"]
    application.update_club_specs(club_name, notes="Grip feels loose")

    assert application.get_bag_club(club_name)["notes"] == "Grip feels loose"

    with open(_session_log_path()) as f:
        data = json.load(f)
    saved = next(c for c in data["bag"] if c["name"] == club_name)
    assert saved["notes"] == "Grip feels loose"


def test_add_club_to_bag_notes_round_trips(app):
    _root, application = app
    application.add_club_to_bag(name="Test Wedge", category="Wedges", notes="New gap wedge")
    club = application.get_bag_club("Test Wedge")
    assert club is not None
    assert club["notes"] == "New gap wedge"


def test_open_club_spec_editor_loads_existing_notes(app):
    _root, application = app
    club_name = application.bag[0]["name"]
    application.update_club_specs(club_name, notes="Loft bent 1deg strong")
    application.open_club_spec_editor(club_name)
    assert application.spec_editor_notes == "Loft bent 1deg strong"


def test_save_club_spec_notes_updates_draft_state(app):
    _root, application = app
    club_name = application.bag[0]["name"]
    application.open_club_spec_editor(club_name)
    application._save_club_spec_notes("Updated note text")
    assert application.spec_editor_notes == "Updated note text"


def test_save_spec_editor_values_persists_notes(app):
    _root, application = app
    club_name = application.bag[0]["name"]
    application.open_club_spec_editor(club_name)
    application.spec_editor_notes = "Persisted via save"
    application.save_spec_editor_values()
    assert application.get_bag_club(club_name)["notes"] == "Persisted via save"


# ---- Session notes ------------------------------------------------------

def test_save_session_notes_persists(app):
    _root, application = app
    import json

    application._save_session_notes("Windy range day, ball flew low")
    assert application.get_active_session()["notes"] == "Windy range day, ball flew low"

    with open(_session_log_path()) as f:
        data = json.load(f)
    assert data["sessions"][0]["notes"] == "Windy range day, ball flew low"


def test_draw_session_dropdown_registers_notes_row(app):
    _root, application = app
    application.show_session_dropdown = True
    application.draw_screen()
    codes = [item[-1] for item in application.session_menu_items]
    assert -4 in codes
