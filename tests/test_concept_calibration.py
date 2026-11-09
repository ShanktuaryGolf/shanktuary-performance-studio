"""Guided calibration concept follows real production flow transitions."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_guided_setup_flow import FakePM

import obs_server
import shanktuary_performance_studio as production
from src.ui.concept_calibration import draw_board_calibration


class Canvas:
    def __init__(self):
        self.calls = []

    def __getattr__(self, key):
        def call(*args, **kwargs):
            self.calls.append((key, args, kwargs))
        return call


@pytest.fixture
def flow(monkeypatch):
    app = production.ShanktuaryApp.__new__(production.ShanktuaryApp)
    app.canvas = Canvas()
    app.root = SimpleNamespace(after=Mock())
    app.draw_screen = Mock()
    app.clear_copy_feedback = Mock()
    pm = FakePM()
    monkeypatch.setattr(obs_server, "pressure_manager", pm)
    return app, pm


def render(app, pm):
    calls_before = list(pm.calls)
    app.canvas.calls.clear()
    draw_board_calibration(app, 1600, 876)
    assert pm.calls == calls_before, "rendering must not perform device actions"
    return [kwargs["text"] for name, _, kwargs in app.canvas.calls if name == "create_text"]


def test_full_guided_flow_keeps_production_advancement(flow):
    app, pm = flow
    app.start_guided_setup()
    assert "Step onto your left board" in render(app, pm)
    assert app.board_modal_cancel_rect and app.board_modal_skip_rect
    assert app.board_modal_done_rect is None
    pm.assignment_wizard.complete()
    app.tick_setup_flow()
    assert "Stand in your address position" in render(app, pm)
    pm.finish_align()
    app.tick_setup_flow()
    assert "Measure stance width" in render(app, pm)
    assert not any("420 mm" in text for text in render(app, pm))
    pm.finish_width(420)
    app.tick_setup_flow()
    texts = render(app, pm)
    assert "Setup flow finished" in texts
    assert "Measured stance width: 420 mm" in texts
    assert app.board_modal_done_rect
    assert app.board_modal_cancel_rect is None and app.board_modal_skip_rect is None


def test_refused_assignment_shows_error_not_connected_claim(flow):
    app, pm = flow
    pm._boards = 1
    app.start_guided_setup()
    texts = render(app, pm)
    assert "Setup needs attention" in texts
    assert any("2 boards" in text for text in texts)
    assert "Both boards assigned" not in texts
    assert app.board_modal_done_rect is None


def test_single_board_skips_assignment_and_unknown_width_not_invented(flow):
    app, pm = flow
    pm.board_mode = "single"
    app.start_guided_setup()
    texts = render(app, pm)
    assert "Single board" in texts and "Board B" not in texts
    assert app.setup_flow_steps == ["align", "width"]
    app._skip_setup_flow_step()
    app._skip_setup_flow_step()
    texts = render(app, pm)
    assert "Setup flow finished" in texts
    assert not any("Measured stance width:" in text for text in texts)
    assert any("Skipped steps are not calibrated" in text for text in texts)


@pytest.mark.parametrize("action", ["cancel", "skip"])
def test_existing_modal_click_handlers_remain_authoritative(flow, action):
    app, pm = flow
    app.start_guided_setup()
    render(app, pm)
    app.show_pairing_modal = False
    rect = getattr(app, f"board_modal_{action}_rect")
    event = SimpleNamespace(x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2)
    app.handle_mouse_press(event)
    if action == "cancel":
        assert not app.show_board_assign_modal
        assert "assign_reset" in pm.calls and "width_cancel" in pm.calls
    else:
        assert app._flow_step() == "align"
        assert "align" in pm.calls
