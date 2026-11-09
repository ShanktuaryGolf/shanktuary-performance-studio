"""Connection-stage presentation must never invent shot measurements."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.ui.connection_wizard import ConnectionWizard


@pytest.mark.parametrize("state,received", [("connected", False), ("listening", False), ("ready", True), ("ready", False)])
def test_live_stage_keeps_source_honesty_and_real_actions(monkeypatch, state, received):
    wizard = ConnectionWizard.__new__(ConnectionWizard)
    wizard._status = {"state": state, "shot_received": received}
    wizard.source = "pureplay"
    wizard.source_locked = False
    wizard._options = {"pureplay": {}}
    wizard._widgets = []
    wizard.win = object()
    wizard.h = 820
    wizard.canvas = Mock()
    wizard._rounded = Mock()
    wizard._text = Mock()
    wizard._button = Mock()
    wizard._hit = Mock()
    wizard._px = lambda n: round(n)
    wizard._draw_connect_footer = Mock()
    monkeypatch.setattr("src.ui.connection_wizard.tk.StringVar", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr("src.ui.connection_wizard.tk.Label", Mock())
    monkeypatch.setattr("src.ui.concept_art.range_landscape", Mock(return_value=True))
    wizard._draw_test_shot(300, 1252)
    texts = [call.args[2] for call in wizard._text.call_args_list]
    canvas_texts = [call.kwargs.get("text", "") for call in wizard.canvas.create_text.call_args_list]
    assert "PurePlay" in texts
    assert not any("154" in text or "112 mph" in text for text in texts + canvas_texts)
    expected = "Test shot received" if state == "ready" and received else "—"
    assert expected in canvas_texts
    wizard._draw_connect_footer.assert_called_once_with(300, 1252)
    actions = [call.args[4] for call in wizard._button.call_args_list]
    assert "stop" in actions and "metrics" in actions
    assert all(call.args[1] == "source" for call in wizard._hit.call_args_list)


def test_live_stage_does_not_bypass_finish_gate():
    wizard = ConnectionWizard.__new__(ConnectionWizard)
    wizard._status = {"state": "connected", "shot_received": False}
    wizard._draw_test_shot = Mock()
    wizard._draw_connect(300, 1252)
    wizard._draw_test_shot.assert_called_once_with(300, 1252)
