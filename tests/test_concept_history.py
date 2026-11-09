"""History layout and native-callback contracts, without a graphical display."""
from copy import deepcopy
from types import SimpleNamespace

from src.ui import concept_history as ui
from src.ui.concept_canvas import restore_hit_geometry, translate_hit_geometry


class Canvas:
    def __init__(self):
        self.words = []
        self.items = []

    def create_text(self, *args, **kwargs):
        self.words.append(kwargs["text"])
        self.items.append(("text", args, kwargs))

    def __getattr__(self, name):
        if name.startswith("create_"):
            return lambda *args, **kwargs: self.items.append((name, args, kwargs))
        raise AttributeError(name)


def app(shots=None):
    sessions = [
        {"id": "older", "name": "Older session", "created_at": "2026-11-07 10:00", "shots": []},
        {"id": "active", "name": "Practice", "created_at": "2026-11-08 11:00", "notes": "Keep a steady tempo.", "shots": shots or []},
    ]
    a = SimpleNamespace(
        canvas=Canvas(), sessions=sessions, active_session_index=1,
        session_shots=sessions[1]["shots"], aim_corrected=lambda s: dict(s),
        is_left_handed=False, selected_shot_index=len(shots or []) - 1,
        current_shot=(shots or [None])[-1], land_dot_coords=[], root=None,
        calls=[],
    )
    a.get_active_session = lambda: a.sessions[a.active_session_index]
    a.draw_screen = lambda: ui.draw(a, 1328, 876, 272)
    a.save_session_to_file = lambda: a.calls.append(("save",))
    a.switch_session = lambda index: a.calls.append(("session", index))
    a.create_new_session = lambda: a.calls.append(("new",))
    a.rename_active_session = lambda: a.calls.append(("rename",))
    a.delete_session = lambda index, confirm=True: a.calls.append(("delete_session", index, confirm))
    a.delete_shot = lambda index, confirm=True: a.calls.append(("delete_shot", index, confirm))
    a.delete_empty_sessions = lambda: a.calls.append(("empty",))
    a.edit_session_notes = lambda: a.calls.append(("notes",))
    a.export_session_report = lambda kind: a.calls.append(("export", kind))
    return a


def click(a, action, payload=None):
    rect = next(rect for rect, candidate, data in a.concept_history_rects
                if candidate == action and (payload is None or data == payload))
    assert ui.handle_click(a, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def shot(index, club="7 Iron", **extra):
    return {"id": str(index), "club": club, "total_spin_rpm": 6000 + index,
            "ball_speed_meters_per_second": 50,
            "open_golf_coach": {"shot_name": "Straight", "us_customary_units": {
                "carry_distance_yards": 150 + index, "peak_height_yards": 28}}, **extra}


def test_three_columns_use_real_sessions_and_do_not_invent_missing_metrics():
    a = app([{"id": "partial", "club": "Driver"}])
    original = deepcopy(a.sessions)
    a.draw_screen()
    assert {"Sessions", "Notes", "Practice", "Shot 1", "Older session"}.issubset(a.canvas.words)
    assert "Trajectory unavailable" in a.canvas.words
    assert a.canvas.words.count("Unavailable") >= 6
    assert a.sessions == original
    assert not any(item[2].get("tags") == "flight-trajectory" for item in a.canvas.items)
    assert all(292 <= rect[0] < rect[2] <= 1580 and 64 <= rect[1] < rect[3] <= 811
               for rect, *_ in a.concept_history_rects)


def test_native_actions_keep_deletion_confirmation_and_export_whole_session():
    a = app([shot(1)])
    a.draw_screen()
    for action in ("new", "rename", "notes", "csv", "pdf", "delete_shot"):
        click(a, action)
    click(a, "session", 0)
    click(a, "menu", "session")
    click(a, "delete_session")
    assert a.calls == [("new",), ("rename",), ("notes",), ("export", "csv"),
                       ("export", "pdf"), ("delete_shot", 0, True),
                       ("session", 0), ("delete_session", 1, True)]


def test_filters_sort_and_checkbox_preserve_native_indices():
    a = app([shot(0), shot(1, "Driver"), shot(2), shot(3, excluded=True)])
    a.draw_screen()
    click(a, "menu", "club")
    click(a, "filter", ("club", "7 Iron"))
    click(a, "menu", "inclusion")
    click(a, "filter", ("inclusion", True))
    assert [index for index, _ in ui.history_rows(a)] == [2, 0]
    click(a, "include", 2)
    assert a.session_shots[2]["excluded"] is True
    assert not a.session_shots[0].get("excluded")
    assert [index for index, _ in ui.history_rows(a)] == [0]
    assert a.calls == [("save",)]


def test_numeric_zero_sorts_before_missing_and_does_not_become_unavailable():
    a = app([{"id": "none"}, {"id": "zero", "total_spin_rpm": 0}, shot(2)])
    a.concept_history_sort = "spin"
    a.concept_history_ascending = True
    assert [s["id"] for _, s in ui.history_rows(a)] == ["zero", "2", "none"]
    a.draw_screen()
    assert "0" in a.canvas.words


def test_pagination_and_preview_are_real_shots_and_page_clamps_after_delete():
    a = app([shot(i) for i in range(23)])
    a.draw_screen()
    assert "Showing 1–8 of 23 shots" in a.canvas.words
    click(a, "page", 1)
    assert a.concept_history_page == 1
    assert [data for _, action, data in a.concept_history_rects if action == "shot"] == list(range(14, 6, -1))
    click(a, "shot", 11)
    assert a.current_shot is a.session_shots[11]
    click(a, "step", -1)
    assert a.selected_shot_index == 10
    a.session_shots[:] = a.session_shots[:2]
    a.draw_screen()
    assert a.concept_history_page == 0


def test_public_hit_translation_and_menu_dismissal_are_not_click_through():
    a = app([shot(1)])
    a.draw_screen()
    native = deepcopy(a.concept_history_rects)
    translate_hit_geometry(a)
    rect = next(rect for rect, action, _ in a.concept_history_rects if action == "csv")
    expected = next(rect for rect, action, _ in native if action == "csv")
    assert rect[1] == expected[1] + 124
    restore_hit_geometry(a)
    assert a.concept_history_rects == native
    click(a, "menu", "session")
    click(a, "csv")  # Outside-menu click only dismisses the menu.
    assert a._history_menu is None
    assert a.calls == []
    click(a, "csv")
    assert a.calls == [("export", "csv")]


def test_session_order_and_scroll_reach_long_history():
    a = app()
    a.sessions += [{"id": f"extra-{i}", "name": f"Session {i}", "shots": []} for i in range(15)]
    a.draw_screen()
    assert [index for index, _ in ui.session_order(a)][:2] == [1, 0]
    ui.handle_scroll(a, 5, 350)
    assert a.concept_history_session_offset == 5
    click(a, "order")
    assert a.concept_history_session_offset == 0
    assert ui.session_order(a)[-1][0] == 1


def test_duration_requires_actual_timestamps_and_never_guesses_clock_dates():
    assert ui.duration_label([]) == "—"
    assert ui.duration_label([{"timestamp": "11:30 AM"}, {"timestamp": "11:45 AM"}]) == "—"
    assert ui.duration_label([{"timestamp_ns": 0}, {"timestamp_ns": 120_000_000_000}]) == "2 min"
    assert ui.duration_label([{"timestamp": "2026-11-08T11:30:00"}, {"timestamp": "2026-11-08T12:02:00"}]) == "32 min"


def test_notes_search_cancel_and_shot_note_save(monkeypatch):
    from tkinter import simpledialog

    a = app([shot(0, notes="Smooth tempo"), shot(1, notes="Better contact")])
    a.draw_screen()
    monkeypatch.setattr(simpledialog, "askstring", lambda *args, **kwargs: "tempo")
    click(a, "search")
    assert [index for index, _ in ui.history_rows(a)] == [0]
    monkeypatch.setattr(simpledialog, "askstring", lambda *args, **kwargs: None)
    click(a, "search")
    assert a.concept_history_search == "tempo"
    monkeypatch.setattr(simpledialog, "askstring", lambda *args, **kwargs: "Tempo improved")
    click(a, "shot_notes", 0)
    assert a.session_shots[0]["notes"] == "Tempo improved"
    assert a.calls == [("save",)]


def test_changing_sessions_clears_stale_filters_but_not_saved_notes():
    a = app([shot(1)])
    a.draw_screen()
    a.concept_history_search = "stale"
    a.concept_history_club = "Driver"
    a.active_session_index = 0
    a.session_shots = a.sessions[0]["shots"]
    a.draw_screen()
    assert a.concept_history_search == ""
    assert a.concept_history_club is None
    assert a.sessions[1]["notes"] == "Keep a steady tempo."
