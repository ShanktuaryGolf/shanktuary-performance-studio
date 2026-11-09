"""Wizard measurements come only from the current queue-accepted native shot."""

import queue
import threading
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.connections.controller import SourceConnections, StudioConnectionSetup
from src.ui.connection_wizard import ConnectionWizard


def native_shot(**fields):
    return {
        "type": "shot",
        "ball_speed_meters_per_second": 44.704,
        "vertical_launch_angle_degrees": 17.2,
        "total_spin_rpm": 5100,
        "open_golf_coach": {"carry_distance_meters": 137.16},
        **fields,
    }


@pytest.fixture
def connection():
    controller = SourceConnections(queue.Queue())
    controller.start("nova")
    yield controller
    controller.stop()


def test_no_accepted_snapshot_from_connection_or_ready_status_alone(connection):
    assert connection.snapshot()["accepted_shot"] is None
    connection._status.update(state="ready", shot_received=True)
    assert connection.snapshot()["accepted_shot"] is None
    assert connection.queue.empty()


def test_snapshot_is_independent_of_native_queue_and_other_snapshots(connection):
    native = native_shot()
    original = deepcopy(native)
    connection.input_queue("nova").put(native)
    first = connection.snapshot()["accepted_shot"]
    expected = {**original, "_source": "nova", "_input_generation": connection._generation}
    assert first == expected
    assert native == original
    assert connection.queue.qsize() == 1
    queued = connection.queue.get_nowait()
    queued["open_golf_coach"]["carry_distance_meters"] = 999
    native["open_golf_coach"]["carry_distance_meters"] = 888
    first["open_golf_coach"]["carry_distance_meters"] = 777
    assert connection.snapshot()["accepted_shot"] == expected
    assert connection.accepts(queued)
    assert connection.queue.empty()


@pytest.mark.parametrize("change", ["stop", "restart", "source", "select"])
def test_lifecycle_clears_accepted_shot_and_rejects_old_sink(connection, change):
    sink = connection.input_queue("nova")
    sink.put(native_shot())
    old = connection.queue.get_nowait()
    if change == "stop":
        connection.stop()
    elif change == "restart":
        connection.start("nova")
    elif change == "source":
        connection.start("gspro")
    else:
        connection.select_source("gspro")
    assert connection.snapshot()["accepted_shot"] is None
    assert not connection.snapshot()["shot_received"]
    sink.put(native_shot(total_spin_rpm=9999))
    assert connection.queue.empty()
    assert not connection.accepts(old)
    assert connection.snapshot()["accepted_shot"] is None


def test_stale_generation_cannot_replace_new_source_shot(connection):
    old_sink = connection.input_queue("nova")
    connection.start("gspro")
    connection.input_queue("gspro").put(native_shot(total_spin_rpm=2200))
    expected = connection.snapshot()["accepted_shot"]
    old_sink.put(native_shot(total_spin_rpm=9999))
    assert connection.snapshot()["accepted_shot"] == expected
    assert expected["_source"] == "gspro"
    assert connection.queue.qsize() == 1


@pytest.mark.parametrize("maxsize", [0, 1])
def test_full_queue_invalidates_metrics_without_accepting_rejected_shot(maxsize):
    destination = queue.Queue(maxsize=maxsize)
    controller = SourceConnections(destination)
    controller.start("nova")
    try:
        sink = controller.input_queue("nova")
        sink.put(native_shot())
        for _ in range(0 if maxsize else 255):
            destination.put_nowait({})
        before = destination.qsize()
        with pytest.raises(queue.Full):
            sink.put(native_shot(total_spin_rpm=9999))
        assert destination.qsize() == before
        assert controller.snapshot()["accepted_shot"] is None
        assert not controller.snapshot()["shot_received"]
        assert controller.snapshot()["state"] == "error"
    finally:
        controller.stop()


@pytest.fixture
def connector(monkeypatch):
    started = threading.Event()
    clients = []

    class Client:
        def __init__(self, sink, on_status):
            self.sink = sink
            self.status = on_status
            clients.append(self)

        def start(self, **kwargs):
            started.set()

        def stop(self):
            pass

    monkeypatch.setattr("src.connections.open_connect.OpenConnectListener", Client)
    controller = SourceConnections(queue.Queue())
    controller.start_open_connect()
    assert started.wait(2)
    yield controller, clients[0]
    controller.stop()


@pytest.mark.parametrize("status", [
    {"state": "error"},
    {"state": "idle"},
    {"status": "disconnected"},
    {"status": "stopped"},
    {"status": "listening", "connected": False},
    {"shot_received": False},
])
def test_invalid_status_clears_metrics_until_another_accepted_shot(connector, status):
    controller, client = connector
    client.sink.put(native_shot())
    assert controller.snapshot()["accepted_shot"] is not None
    client.status(status)
    assert controller.snapshot()["accepted_shot"] is None
    client.status({"status": "connected", "connected": True})
    assert controller.snapshot()["accepted_shot"] is None
    client.sink.put(native_shot(total_spin_rpm=2400))
    assert controller.snapshot()["accepted_shot"]["total_spin_rpm"] == 2400


def test_stale_status_callback_does_not_erase_new_source_metrics(connector):
    controller, client = connector
    controller.start("gspro")
    controller.input_queue("gspro").put(native_shot(total_spin_rpm=2300))
    expected = controller.snapshot()["accepted_shot"]
    client.status({"status": "disconnected"})
    assert controller.snapshot()["accepted_shot"] == expected


@pytest.mark.parametrize("source", ["nova", "gspro", "both"])
def test_legacy_disconnect_clears_metrics_and_reconnect_requires_new_shot(source):
    values = {"source": source}
    settings = SimpleNamespace(
        load_settings=lambda: dict(values),
        save_settings=lambda **kwargs: {**values, **kwargs},
    )
    legacy = {"connected": True}
    controller = SourceConnections(queue.Queue())
    adapter = StudioConnectionSetup(controller, settings, legacy_status=lambda _: legacy)
    adapter.start(source)
    try:
        legacy["connected"] = True
        sink = controller.input_queue("nova" if source == "both" else source)
        sink.put(native_shot())
        assert adapter.snapshot()["accepted_shot"] is not None
        legacy["connected"] = False
        assert adapter.snapshot()["accepted_shot"] is None
        assert controller.snapshot()["accepted_shot"] is None
        legacy["connected"] = True
        assert adapter.snapshot()["accepted_shot"] is None
        assert adapter.snapshot()["state"] == "connected"
        sink.put(native_shot(total_spin_rpm=0))
        assert adapter.snapshot()["accepted_shot"]["total_spin_rpm"] == 0
    finally:
        adapter.stop()


@pytest.fixture
def wizard(monkeypatch):
    current = ConnectionWizard.__new__(ConnectionWizard)
    current._status = {"state": "ready", "shot_received": True}
    current.source = "pureplay"
    current.source_locked = False
    current._options = {"pureplay": {}}
    current._widgets = []
    current.win = Mock()
    current.h = 820
    current.canvas = Mock()
    current._rounded = Mock()
    current._text = Mock()
    current._button = Mock()
    current._hit = Mock()
    current._px = round
    current._draw_connect_footer = Mock()
    monkeypatch.setattr("src.ui.connection_wizard.tk.StringVar", Mock())
    monkeypatch.setattr("src.ui.connection_wizard.tk.Label", Mock())
    monkeypatch.setattr("src.ui.concept_art.range_landscape", Mock(return_value=True))
    return current


def strip_texts(wizard):
    wizard._draw_test_shot(300, 1252)
    return [call.args[2] for call in wizard._text.call_args_list if 547 <= call.args[1] <= 630]


@pytest.mark.parametrize("state,received", [("ready", True), ("ready", False), ("connected", False)])
def test_without_accepted_payload_metric_strip_is_empty(wizard, state, received):
    wizard._status.update(state=state, shot_received=received)
    texts = strip_texts(wizard)
    assert texts.count("—") == 4
    assert texts.count("Not Reported") == 4
    assert ["Carry (yd)", "Ball speed (mph)", "Launch (°)", "Spin (rpm)"] == texts[::3]


def test_actual_metrics_are_converted_and_source_labelled_without_mutation(wizard):
    shot = native_shot(_source="pureplay")
    original = deepcopy(shot)
    wizard._status["accepted_shot"] = shot
    texts = strip_texts(wizard)
    assert texts[1::3] == ["150.0", "100.0", "17.2", "5100"]
    assert texts.count("Reported") == 4
    assert "Test shot · PurePlay" in [call.args[2] for call in wizard._text.call_args_list]
    assert shot == original


def test_real_zero_estimates_and_missing_metrics_are_distinct(wizard):
    wizard._status["accepted_shot"] = {
        "_source": "pureplay",
        "ball_speed_meters_per_second": 0,
        "total_spin_rpm": 0,
        "open_golf_coach": {"carry_distance_meters": 0},
        "_metric_provenance": {
            "ball_speed_meters_per_second": {"kind": "source_estimated"},
            "open_golf_coach.carry_distance_meters": {"kind": "modelled"},
            "total_spin_rpm": {"kind": "derived"},
        },
    }
    texts = strip_texts(wizard)
    assert texts[1::3] == ["0.0", "0.0", "—", "0"]
    assert texts[2::3] == ["Modelled", "Estimated", "Not Reported", "Derived"]


@pytest.mark.parametrize("status", ["connected", "listening", "error", "ready"])
def test_stale_payload_is_not_displayed_without_ready_acceptance(wizard, status):
    wizard._status.update(state=status, shot_received=False, accepted_shot=native_shot(_source="pureplay"))
    assert strip_texts(wizard).count("—") == 4


def test_payload_from_other_source_is_not_displayed(wizard):
    wizard._status["accepted_shot"] = native_shot(_source="nova")
    assert strip_texts(wizard).count("—") == 4


@pytest.mark.parametrize("source,label", [("nova", "Nova"), ("gspro", "GSPro")])
def test_both_source_uses_actual_accepted_source_label(wizard, source, label):
    wizard.source = "both"
    wizard._status["accepted_shot"] = native_shot(_source=source)
    assert "150.0" in strip_texts(wizard)
    assert f"Test shot · {label}" in [call.args[2] for call in wizard._text.call_args_list]


def test_next_accepted_shot_repaints_metrics_but_steady_snapshot_does_not(wizard):
    wizard._alive = True
    wizard.page = "connect"
    wizard._discovery_results = queue.Queue()
    wizard._status["accepted_shot"] = native_shot(_source="pureplay")
    wizard.controller = Mock()
    state = deepcopy(wizard._status)
    wizard.controller.snapshot.side_effect = lambda: deepcopy(state)
    wizard._draw = Mock()
    wizard._remember_fields = Mock()
    wizard._update_status = Mock()
    wizard._poll_status()
    wizard._draw.assert_not_called()
    wizard._update_status.assert_called_once()
    state["accepted_shot"]["total_spin_rpm"] = 4400
    wizard._poll_status()
    wizard._draw.assert_called_once()
    assert wizard._status["accepted_shot"]["total_spin_rpm"] == 4400


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("accepted", [False, True])
def test_metric_strip_stays_in_its_columns_at_desktop_scales(scale, accepted):
    import tkinter as tk

    from src.ui import tokens as T

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("requires a graphical display")
    original_scaling = root.tk.call("tk", "scaling")
    root._sps_ui_scale = scale
    root.tk.call("tk", "scaling", scale * 96 / 72)
    status = {
        "state": "ready" if accepted else "connected",
        "shot_received": accepted,
        "accepted_shot": native_shot(_source="pureplay") if accepted else None,
    }
    controller = SimpleNamespace(
        settings={"source": "pureplay"}, snapshot=lambda: deepcopy(status), stop=Mock(),
    )
    current = None
    try:
        current = ConnectionWizard(root, controller)
        current.page = "connect"
        current._status = deepcopy(status)
        current._draw()
        root.update()
        x, right = T.NAV_RAIL_W + 28, current.w - 28
        mid = x + (right - x) * .65
        stride = (mid - x - 42) / 4
        checked = 0
        for item in current.canvas.find_all():
            if current.canvas.type(item) != "text":
                continue
            tx, ty = current.canvas.coords(item)
            if ty not in (556, 576, 610) or tx >= mid:
                continue
            column = int((tx - x - 14) / stride)
            left = x + 14 + column * stride
            box = current.canvas.bbox(item)
            assert left + 8 <= box[0] < box[2] <= left + stride - 6
            assert 547 <= box[1] < box[3] <= 630
            checked += 1
        assert checked == 12
    finally:
        if current is not None:
            current._close()
        root.tk.call("tk", "scaling", original_scaling)
        root.destroy()
