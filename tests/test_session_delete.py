"""Session delete: the destructive path, so edge cases are covered.

Also covers the empty-session cleanup, added because stray "+" clicks
accumulate zero-shot sessions that clutter the switcher.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real app whose session file is a THROWAWAY copy.

    Never point tests at the user's own shanktuary_session_history.json:
    an earlier test clicked "+" against the live file and left six junk
    sessions in it.
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

    # Deterministic fixture: 3 sessions, only the first with shots.
    application.sessions = [
        {"id": "a", "name": "Session 1 - 7 Iron", "created_at": "x",
         "shots": [{"club": "7 Iron"}, {"club": "7 Iron"}]},
        {"id": "b", "name": "Session 2 - 7 Iron", "created_at": "x", "shots": []},
        {"id": "c", "name": "Session 3 - PW", "created_at": "x", "shots": []},
    ]
    application.active_session_index = 0
    root.update()
    yield root, application
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_deleting_an_empty_session_needs_no_confirmation(app):
    _root, application = app
    assert application.delete_session(1) is True
    assert len(application.sessions) == 2
    assert [s["name"] for s in application.sessions] == [
        "Session 1 - 7 Iron", "Session 3 - PW"]


def test_deleting_a_session_with_shots_asks_first_and_can_be_cancelled(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: False)
    assert application.delete_session(0) is False
    assert len(application.sessions) == 3, "cancelled delete still removed it"
    assert len(application.sessions[0]["shots"]) == 2


def test_confirmed_delete_of_a_session_with_shots_removes_it(app, monkeypatch):
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    assert application.delete_session(0) is True
    assert len(application.sessions) == 2
    assert application.sessions[0]["name"] == "Session 2 - 7 Iron"


def test_active_index_follows_when_an_earlier_session_is_deleted(app):
    _root, application = app
    application.active_session_index = 2      # "Session 3 - PW"
    application.delete_session(1)             # remove the one before it
    assert application.sessions[application.active_session_index]["name"] == \
        "Session 3 - PW", "active session changed identity after delete"


def test_deleting_the_active_session_leaves_a_valid_index(app):
    _root, application = app
    application.active_session_index = 2
    application.delete_session(2)
    assert 0 <= application.active_session_index < len(application.sessions)
    assert application.get_active_session() is not None


def test_the_last_session_is_cleared_not_removed(app, monkeypatch):
    """The app must always have somewhere to put the next shot."""
    _root, application = app
    import tkinter.messagebox as mb

    monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
    application.sessions = [application.sessions[0]]
    application.active_session_index = 0

    application.delete_session(0)
    assert len(application.sessions) == 1, "app was left with zero sessions"
    assert application.sessions[0]["shots"] == [], "shots were not cleared"


def test_out_of_range_index_is_a_no_op(app):
    _root, application = app
    assert application.delete_session(99) is False
    assert application.delete_session(-1) is False
    assert len(application.sessions) == 3


def test_clear_empty_sessions_keeps_shots_and_the_active_one(app):
    _root, application = app
    application.active_session_index = 0      # has shots
    removed = application.delete_empty_sessions()
    assert removed == 2
    assert [s["name"] for s in application.sessions] == ["Session 1 - 7 Iron"]


def test_clear_empty_never_removes_the_active_session_even_if_empty(app):
    _root, application = app
    application.active_session_index = 1      # empty, but active
    application.delete_empty_sessions()
    names = [s["name"] for s in application.sessions]
    assert "Session 2 - 7 Iron" in names, "deleted the session the user is on"
    assert "Session 1 - 7 Iron" in names, "deleted a session holding shots"


def test_delete_persists_to_disk(app, tmp_path):
    import json

    _root, application = app
    application.delete_session(1)
    saved = json.loads((tmp_path / "history.json").read_text())
    assert [s["name"] for s in saved["sessions"]] == [
        "Session 1 - 7 Iron", "Session 3 - PW"]


def test_dropdown_exposes_a_delete_target_for_every_session(app):
    """Each row needs its own ✕ hit target, decoding to the right index."""
    _root, application = app
    application.show_session_dropdown = True
    application.draw_screen()

    deletes = [item for item in application.session_menu_items if item[4] <= -1000]
    assert len(deletes) == len(application.sessions)
    decoded = sorted(-1000 - item[4] for item in deletes)
    assert decoded == list(range(len(application.sessions)))


def test_clicking_a_row_switches_and_clicking_its_x_deletes(app):
    _root, application = app
    application.show_session_dropdown = True
    application.draw_screen()

    class _Evt:
        pass

    # The ✕ of row 1 must delete, not switch.
    target = [i for i in application.session_menu_items if i[4] == -1001][0]
    evt = _Evt()
    evt.x = (target[0] + target[2]) // 2
    evt.y = (target[1] + target[3]) // 2
    application.handle_mouse_press(evt)

    assert len(application.sessions) == 2, "✕ did not delete the row"
    assert [s["name"] for s in application.sessions] == [
        "Session 1 - 7 Iron", "Session 3 - PW"]
