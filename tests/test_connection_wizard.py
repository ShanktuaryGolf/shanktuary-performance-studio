"""Navigation contract independent of display and physical hardware."""

from unittest.mock import Mock

import pytest

from src.ui.connection_wizard import ConnectionWizard


def wizard():
    w = ConnectionWizard.__new__(ConnectionWizard)
    w.controller = Mock()
    w.controller.snapshot.return_value = {"state": "idle", "shot_received": False}
    w.source = "nova"
    w.source_locked = False
    w.page = "choose"
    w.advanced = False
    w.current_club = "7 Iron"
    w.always_show = True
    w._status = {}
    w._discovery_generation = 0
    w._fields = {}
    w._options = {s: {} for s in ("nova", "gspro", "open_connect", "cgp")}
    w._draw = Mock()
    w._close = Mock()
    w.result = None
    return w


def test_continue_is_navigation_not_connection():
    w = wizard()
    w._action("continue")
    assert w.page == "connect"
    w.controller.start.assert_not_called()


def test_another_monitor_selection_starts_listener_and_opens_setup():
    w = wizard()
    w._action("source", "open_connect")
    assert w.source == "open_connect"
    w.controller.select_source.assert_called_once_with("open_connect")
    w.controller.start.assert_called_once_with("open_connect", {"port": 921})
    assert w.page == "connect"


def test_reselect_does_not_reset_connection():
    w = wizard()
    w._action("source", "nova")
    w.controller.select_source.assert_not_called()


def test_back_stops_and_preserves_selection_club_options():
    w = wizard()
    w.source = "open_connect"
    w.page = "connect"
    w._fields = {"port": Mock(get=lambda: " 922 ")}
    w._action("back")
    assert w.page == "choose" and w.source == "open_connect"
    assert w._options["open_connect"]["port"] == "922"
    assert w.current_club == "7 Iron"
    w.controller.stop.assert_called_once()


def test_close_stops_and_cancels():
    w = wizard()
    w._on_close()
    w.controller.stop.assert_called_once()
    w._close.assert_called_once()
    assert w.result is None


@pytest.mark.parametrize("state", ["idle", "listening", "connected", "error"])
def test_non_ready_cannot_finish(state):
    w = wizard()
    w.controller.snapshot.return_value = {"state": state, "shot_received": True}
    w._action("finish")
    assert w.result is None
    w.controller.save_selection.assert_not_called()


def test_socket_ready_without_shot_cannot_finish():
    w = wizard()
    w.controller.snapshot.return_value = {"state": "ready", "shot_received": False}
    w._action("finish")
    assert w.result is None


def test_finish_uses_fresh_controller_not_rendered_state():
    w = wizard()
    w._status = {"state": "ready", "shot_received": True}
    w._action("finish")
    assert w.result is None


def test_test_shot_finish_saves_once_and_does_not_stop():
    w = wizard()
    w.controller.snapshot.return_value = {"state": "ready", "shot_received": True}
    w._action("finish")
    assert w.result == {"source": "nova", "club": "7 Iron", "always_show": True}
    w.controller.save_selection.assert_called_once_with("nova", True)
    w.controller.stop.assert_not_called()
    w._close.assert_called_once()


def test_port_error_visible_without_starting_session():
    w = wizard()
    w.controller.start.side_effect = ValueError("Port must be 1–65535")
    w._action("connect")
    assert w._status["state"] == "error" and "Port" in w._status["message"]
    assert not w._status["shot_received"]


def test_explicit_start_uses_current_fields():
    w = wizard()
    w.source = "open_connect"
    w._fields = {"port": Mock(get=lambda: "921"), "host": Mock(get=lambda: "127.0.0.1")}
    w._action("connect")
    w.controller.start.assert_called_once_with(
        "open_connect", {"port": 921, "host": "127.0.0.1"}
    )


def test_network_change_stops_and_invalidates_readiness():
    w = wizard()
    w.source = "open_connect"
    w._status = {"state": "ready", "shot_received": True}
    w._action("network")
    assert not w._status
    assert w._options[w.source] == {"location": "network", "host": "0.0.0.0"}
    w.controller.stop.assert_called_once()
    w.controller.start.assert_not_called()


def test_environment_source_lock_is_respected():
    w = wizard()
    w.source_locked = True
    w._action("source", "cgp")
    assert w.source == "nova"
    w.controller.select_source.assert_not_called()


def test_advanced_expansion_never_discovers_or_connects():
    w = wizard()
    w._action("advanced")
    assert w.advanced
    w.controller.start.assert_not_called()


def test_cgp_discovery_starts_only_after_explicit_navigation():
    w = wizard()
    w.source = "cgp"
    w._devices = []
    w._start_discovery = Mock()
    w._action("continue")
    w._start_discovery.assert_called_once()
    w.controller.start.assert_not_called()


def test_cgp_connection_waits_for_discovery():
    w = wizard()
    w.source = "cgp"
    w._discovering = True
    w._action("connect")
    w.controller.start.assert_not_called()
    assert "discovery" in w._local_message


def test_cgp_needs_selected_device():
    w = wizard()
    w.source = "cgp"
    w._action("connect")
    w.controller.start.assert_not_called()
    assert "select" in w._local_message


def test_locked_both_source_is_passed_unchanged():
    w = wizard()
    w.source = "both"
    w.source_locked = True
    w._options["both"] = {}
    w._action("connect")
    w.controller.start.assert_called_once_with("both", {})


def test_back_invalidates_pending_discovery():
    w = wizard()
    w._discovering = True
    w._action("back")
    assert w._discovery_generation == 1
    assert not w._discovering


@pytest.mark.parametrize("source", ["nova", "gspro", "cgp"])
def test_other_source_selection_does_not_start(source):
    w = wizard()
    w.source = "open_connect"
    w._action("source", source)
    w.controller.start.assert_not_called()


def test_saved_another_choice_continue_starts_listener():
    w = wizard()
    w.source = "open_connect"
    w._action("continue")
    w.controller.start.assert_called_once_with("open_connect", {"port": 921})


def test_reselect_running_another_does_not_restart():
    w = wizard()
    w.source = "open_connect"
    w.controller.snapshot.return_value = {"state": "listening", "shot_received": False}
    w._action("source", "open_connect")
    w.controller.start.assert_not_called()
    assert w.page == "connect"


def test_selected_another_validates_saved_port():
    w = wizard()
    w._options["open_connect"] = {"port": "invalid"}
    w._action("source", "open_connect")
    w.controller.start.assert_not_called()
    assert w._status["state"] == "error"


def test_truthful_open_connect_status_avoids_raw_address():
    w = wizard()
    w.source = "open_connect"
    w.status_var = Mock()
    w._status = {"state": "listening", "message": "Listening on 127.0.0.1:921"}
    w._update_status()
    w.status_var.set.assert_called_once_with("Waiting for connector")


def test_port_owner_not_asserted():
    w = wizard()
    w.source = "open_connect"
    w.status_var = Mock()
    w._status = {"state": "error", "message": "Address already in use"}
    w._update_status()
    message = w.status_var.set.call_args.args[0]
    assert "may" in message and "GSPro" in message and "Advanced" in message


def test_connection_alone_not_reported_as_test_shot():
    w = wizard()
    w.source = "open_connect"
    w.status_var = Mock()
    w._status = {"state": "connected", "shot_received": False}
    w._update_status()
    w.status_var.set.assert_called_once_with("Connected · hit a test shot")


def test_fresh_another_defaults_to_loopback():
    assert ConnectionWizard._saved_open_connect_options({}) == {
        "host": "127.0.0.1",
        "port": "921",
        "location": "local",
    }


def test_previously_explicit_advanced_lan_preference_is_preserved():
    assert ConnectionWizard._saved_open_connect_options(
        {"open_connect_lan": True, "open_connect_port": 922}
    ) == {"host": "0.0.0.0", "port": "922", "location": "network"}


def test_network_listening_is_visible():
    w = wizard()
    w.source = "open_connect"
    w.status_var = Mock()
    w._options["open_connect"] = {"location": "network"}
    w._status = {"state": "listening"}
    w._update_status()
    assert "network listening" in w.status_var.set.call_args.args[0]
