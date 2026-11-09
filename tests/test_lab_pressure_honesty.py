"""Lab must not substitute live frames or invent anatomical measurements."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.ui import concept_workspaces as ui


class Canvas:
    def __init__(self):
        self.items = []

    def __getattr__(self, name):
        if name.startswith("create_"):
            def create(*coords, **options):
                self.items.append((name, coords, options))
                return len(self.items)
            return create
        raise AttributeError(name)

    def bbox(self, item):
        return None

    def words(self):
        return [options["text"] for _, _, options in self.items if "text" in options]


def lab_app(monkeypatch, trace=None, *, reviewing=True, demo=False):
    import obs_server
    from shanktuary_performance_studio import ShanktuaryApp

    live = {
        "pct_left": 61, "pct_right": 39, "phase": "Address", "total_kg": 80,
        "cop_x": 17, "cop_y": 12, "force_bw": 1.2, "raw_cells": [10, 20, 30, 40],
    }
    monkeypatch.setattr(obs_server, "pressure_manager", SimpleNamespace(latest_frame=live, is_simulator=demo))
    app = ShanktuaryApp.__new__(ShanktuaryApp)
    app.canvas = Canvas()
    app.current_shot = {"id": "selected-shot", "pressure_trace": trace}
    app.is_left_handed = False
    app.is_reviewing_past_shot = lambda: reviewing
    app.get_pressure_trace = lambda shot: shot.get("pressure_trace")
    app.board_is_streaming = lambda: True
    app.swing_lab_history = [dict(live), dict(live)]
    return app, live


@pytest.mark.parametrize("trace", [None, []])
@pytest.mark.parametrize("demo", [False, True])
def test_historical_missing_trace_never_uses_live_metrics_or_curves(monkeypatch, trace, demo):
    app, live = lab_app(monkeypatch, trace, demo=demo)
    before = deepcopy((app.current_shot, app.swing_lab_history, live))
    assert app.pressure_display_trail() == ([], True)
    ui.draw_lab(app, 1300, 900, offset_x=260)
    words = app.canvas.words()
    assert "Historical shot · pressure unavailable" in words
    assert "No pressure captured for this shot" in words
    assert words.count("No pressure trace captured for this shot") == 2
    assert words.count("--") == 6
    assert "61%" not in words and "39%" not in words
    assert "DEMO / SIMULATED" not in words
    assert "No board connected" not in "\n".join(words)
    assert (app.current_shot, app.swing_lab_history, live) == before


def test_historical_trace_uses_selected_sample_even_with_live_demo(monkeypatch):
    trace = [{
        "pct_left": 72, "pct_right": 28, "total_kg": 60, "force_bw": 0.75,
        "cop_x": -9, "cop_y": 5, "phase": "Finish", "raw_cells": [12, 4, 30, 14],
    }]
    app, _ = lab_app(monkeypatch, trace, demo=True)
    before = deepcopy(trace)
    assert app.pressure_display_trail() == (trace, True)
    ui.draw_lab(app, 1300, 900, offset_x=260)
    words = app.canvas.words()
    assert "Historical shot trace · final sample" in words
    assert "72%" in words and "28%" in words
    assert "61%" not in words and "39%" not in words
    assert "12.0 kg" in words and "4.0 kg" in words
    assert "30.0 kg" in words and "14.0 kg" in words
    assert "DEMO / SIMULATED" not in words
    assert trace == before


def test_live_lab_still_uses_streaming_board_frame(monkeypatch):
    app, _ = lab_app(monkeypatch, reviewing=False, demo=True)
    ui.draw_lab(app, 1300, 900, offset_x=260)
    assert "61%" in app.canvas.words() and "39%" in app.canvas.words()
    assert "DEMO / SIMULATED" in app.canvas.words()
    assert app.pressure_display_trail() == (app.swing_lab_history, False)


@pytest.mark.parametrize("raw", [None, [], [20, 20], "20,20,20,20", [None] * 4, [float("nan"), float("inf"), -1, True]])
@pytest.mark.parametrize("is_left", [False, True])
def test_missing_or_invalid_per_cell_data_is_unavailable(raw, is_left):
    from shanktuary_performance_studio import ShanktuaryApp

    app = SimpleNamespace(canvas=Canvas(), is_left_handed=False)
    ShanktuaryApp.draw_single_foot_heatmap(app, 0, 0, 300, 300, is_left=is_left, latest={"pct_left": 61, "pct_right": 39, "raw_cells": raw})
    words = app.canvas.words()
    assert "Per-cell data unavailable" in words
    assert words.count("--") == 2
    assert not any("kg" in word for word in words)
    assert f"Share of load: {61 if is_left else 39}%" in words


@pytest.mark.parametrize("is_left", [False, True])
@pytest.mark.parametrize("left_handed", [False, True])
def test_real_frame_zone_mapping_and_kg_units_are_preserved(is_left, left_handed):
    from shanktuary_performance_studio import ShanktuaryApp
    from src.hardware.pressure import SensorReading
    from src.processing.pressure import CoPCalculator, ShotSynchronizedPressureBuffer

    # Exercise the production frame schema: TL, TR, BL, BR. A side has TWO
    # measured zones, never four invented toe/heel sensors.
    sample = CoPCalculator().compute(SensorReading(10, 20, 30, 40, timestamp=1.0))
    frame = ShotSynchronizedPressureBuffer().push(sample)
    before = deepcopy(frame)
    app = SimpleNamespace(canvas=Canvas(), is_left_handed=left_handed)
    ShanktuaryApp.draw_single_foot_heatmap(app, 0, 0, 300, 300, is_left=is_left, latest=frame)
    words = app.canvas.words()
    side = "LEFT" if is_left else "RIGHT"
    role = "LEAD" if is_left != left_handed else "TRAIL"
    assert f"{role} SIDE ({side})" in words
    assert "Board zones, not foot pressure" in words
    assert [word for word in words if word.endswith(" kg")] == (["10.0 kg", "30.0 kg"] if is_left else ["20.0 kg", "40.0 kg"])
    assert ("Front (TL)" if is_left else "Front (TR)") in words
    assert ("Back (BL)" if is_left else "Back (BR)") in words
    assert f"Share of load: {40 if is_left else 60}%" in words
    assert frame == before


def test_missing_frame_or_missing_side_share_does_not_default_to_half():
    from shanktuary_performance_studio import ShanktuaryApp

    for frame in (None, {}, {"raw_cells": [0, 0, 0, 0]}):
        app = SimpleNamespace(canvas=Canvas(), is_left_handed=False)
        ShanktuaryApp.draw_single_foot_heatmap(app, 0, 0, 300, 300, latest=frame)
        words = app.canvas.words()
        assert "Share of load: --" in words
        assert "50%" not in "\n".join(words)
        if frame:
            assert words.count("0.0 kg") == 2
            assert "Per-cell data unavailable" not in words


@pytest.mark.parametrize("size", [(160, 160), (250, 270)])
@pytest.mark.parametrize("raw", [None, [10, 20, 30, 40]])
def test_board_zone_labels_fit_without_overlap_on_real_canvas(size, raw):
    import tkinter as tk

    from shanktuary_performance_studio import ShanktuaryApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("graphical display required")
    width, height = size
    canvas = tk.Canvas(root, width=width, height=height)
    canvas.pack()
    app = SimpleNamespace(canvas=canvas, is_left_handed=False)
    ShanktuaryApp.draw_single_foot_heatmap(app, 0, 0, width, height, latest={"raw_cells": raw, "pct_left": 40})
    root.update_idletasks()
    boxes = [(canvas.itemcget(item, "text"), canvas.bbox(item)) for item in canvas.find_all() if canvas.type(item) == "text"]
    for label, (x0, y0, x1, y1) in boxes:
        assert 0 <= x0 < x1 <= width, label
        assert 0 <= y0 < y1 <= height, label
    for i, (label, a) in enumerate(boxes):
        for other, b in boxes[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (label, other)
    root.destroy()
