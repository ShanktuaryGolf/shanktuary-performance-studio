"""Empty Overview actions use visible geometry and existing production flows."""
from copy import deepcopy

import pytest
from test_concept_ui import desktop  # noqa: F401 - shared graphical fixture


def physical_click(app, root, rect):
    x = round((rect[0] + rect[2]) / 2 * app.ui_scale - app.canvas.canvasx(0))
    y = round((rect[1] + rect[3]) / 2 * app.ui_scale - app.canvas.canvasy(0))
    app.canvas.event_generate("<Button-1>", x=x, y=y)
    root.update()


@pytest.mark.parametrize("scale", ["100%", "150%", "200%"])
def test_empty_overview_ctas_after_cancel_and_repeated_navigation(desktop, monkeypatch, scale):
    app, root, errors = desktop
    root.geometry("3840x2160")
    app.set_ui_scale(scale, persist=False)
    app.sessions = [{"id": "empty-test", "name": "Empty test session", "shots": []}]
    app.active_session_index = 0
    app.current_shot = None
    app.selected_shot_index = -1
    before = deepcopy(app.sessions)
    calls = []
    # The source picker returns no choice when cancelled; verify that the
    # visible action reaches it without creating or modifying a session.
    monkeypatch.setattr(app, "open_shot_source_picker", lambda: calls.append("source"))
    for _ in range(2):
        for action, mode in (("source", 12), ("boards", 10), ("history", 13)):
            app.set_mode(12)
            root.update()
            rect = next(r for r, key in app.concept_overview_rects if key == action)
            physical_click(app, root, rect)
            assert app.view_mode == mode
            if action == "boards":
                assert app.concept_setup_page == "details"
                assert "overview" in app.concept_setup_actions
            elif action == "history":
                assert app.concept_history_rects
    assert calls == ["source", "source"]
    assert app.sessions == before
    assert app.current_shot is None
    assert not errors


def test_overview_scroll_extent_contracts_after_last_shot_removed(desktop):
    app, root, errors = desktop
    root.geometry("1600x1000")
    app.set_ui_scale("100%", persist=False)
    shot = {"club": "7 Iron"}
    app.sessions = [{"id": "scroll-test", "name": "Scroll test", "shots": [shot]}]
    app.active_session_index = 0
    app.current_shot = shot
    app.selected_shot_index = 0
    app.set_mode(12)
    root.update()
    assert app.canvas.minimum_size == (1600, 1450)
    app.handle_scroll_delta(5)
    root.update()
    assert app.canvas.yview()[0] > 0

    app.sessions[0]["shots"] = []
    app.current_shot = None
    app.selected_shot_index = -1
    app.draw_screen()
    root.update()
    assert app.canvas.minimum_size == (1600, 1000)
    assert float(app.canvas.cget("scrollregion").split()[3]) == 1000
    assert {action for _, action in app.concept_overview_rects} == {"source", "boards", "history"}
    assert not errors
