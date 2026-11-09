"""Public Lab controls and animated preview against an isolated desktop."""
import time
from copy import deepcopy

from test_concept_ui import click, desktop  # noqa: F401


def test_lab_demo_public_start_stop_and_history_selection(desktop):
    import obs_server

    app, root, errors = desktop
    first = {"id": "fixture A", "club": "7 Iron"}
    second = {"id": "fixture B", "club": "7 Iron"}
    app.sessions = [{"id": "lab-preview-test", "name": "Lab test fixtures",
                     "shots": [first, second]}]
    app.active_session_index = 0
    app.current_shot = first
    app.selected_shot_index = 0
    app.set_mode(8)
    root.update()
    manager = obs_server.pressure_manager
    backend = manager.backend
    simulator = manager.is_simulator
    before = deepcopy(app.session_shots)
    assert app.is_reviewing_past_shot()
    click(app, root, app.swing_lab_demo_rect)
    assert app.lab_demo_running
    frame = app.lab_demo_frames[-1]
    until = time.monotonic() + .35
    while time.monotonic() < until:
        root.update()
        time.sleep(.01)
    assert app.lab_demo_frames[-1] != frame
    assert app.pressure_display_trail()[0] is app.lab_demo_frames
    assert app.current_shot is first
    click(app, root, app.swing_lab_tare_rect)
    assert app.lab_demo_running
    click(app, root, app.swing_lab_demo_rect)
    assert not app.lab_demo_running
    assert app.pressure_display_trail() == ([], True)
    click(app, root, app.swing_lab_demo_rect)
    app.current_shot = second
    app.selected_shot_index = 1
    app.draw_screen()
    assert not app.lab_demo_running
    assert app.current_shot is second
    assert app.session_shots == before
    assert manager.backend is backend
    assert manager.is_simulator == simulator
    assert not errors
