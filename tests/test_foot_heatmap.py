"""An illustrative footprint must not imply additional measured sensors."""

import tkinter as tk
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops


@pytest.fixture
def renderer(monkeypatch, tmp_path):
    # Importing src.ui currently imports the application. Keep that existing
    # startup path away from physical hardware and the user's saved settings.
    monkeypatch.setenv("SPS_UI_PREVIEW", "1")
    for name in ("HOME", "USERPROFILE", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "LOCALAPPDATA"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "source.json"))
    from src.ui import foot_heatmap

    return foot_heatmap


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


@pytest.mark.parametrize("is_left", [True, False])
@pytest.mark.parametrize("left_handed", [True, False])
def test_raw_mapping_handedness_and_source_are_preserved(renderer, is_left, left_handed):
    frame = {"raw_cells": [10, 20, 30, 40], "pct_left": 40, "pct_right": 60}
    before = deepcopy(frame)
    app = SimpleNamespace(canvas=Canvas(), is_left_handed=left_handed)
    renderer.draw_estimated_foot_heatmap(app, 0, 0, 250, 270, is_left, frame)
    words = app.canvas.words()
    role = "LEAD" if is_left != left_handed else "TRAIL"
    assert f"{role} SIDE ({'LEFT' if is_left else 'RIGHT'})" in words
    assert "Estimated foot load" in words
    assert "Not plantar pressure" in words
    assert ("Front (TL)" if is_left else "Front (TR)") in words
    assert ("Back (BL)" if is_left else "Back (BR)") in words
    assert [word for word in words if word.endswith(" kg")] == (
        ["10.0 kg", "30.0 kg"] if is_left else ["20.0 kg", "40.0 kg"]
    )
    assert f"Share of load: {40 if is_left else 60}%" in words
    assert frame == before


@pytest.mark.parametrize("raw", [None, [], [1, 2], [1] * 5, "1,2,3,4", [None] * 4,
                                  [float("nan"), float("inf"), -1, True]])
@pytest.mark.parametrize("is_left", [True, False])
def test_invalid_cells_leave_shape_unheated(renderer, raw, is_left):
    canvas = Canvas()
    app = SimpleNamespace(canvas=canvas, is_left_handed=False)
    renderer.draw_estimated_foot_heatmap(
        app, 0, 0, 160, 160, is_left, {"raw_cells": raw, "pct_left": 61, "pct_right": 39},
    )
    assert "Per-cell data unavailable" in canvas.words()
    assert canvas.words().count("--") == 2
    assert f"Share of load: {61 if is_left else 39}%" in canvas.words()
    assert any(options.get("tags") == "estimated-foot-shape" for _, _, options in canvas.items)
    assert not any(options.get("tags") == "estimated-foot-gradient" for _, _, options in canvas.items)


def test_partial_side_keeps_measured_value_without_inventing_other_zone(renderer):
    frame = {"raw_cells": [12, 20, None, 40], "pct_left": 33}
    canvas = Canvas()
    renderer.draw_estimated_foot_heatmap(SimpleNamespace(canvas=canvas), 0, 0, 250, 270, latest=frame)
    assert "12.0 kg" in canvas.words()
    assert canvas.words().count("--") == 1
    assert "Per-cell data unavailable" in canvas.words()
    assert not any(options.get("tags") == "estimated-foot-gradient" for _, _, options in canvas.items)
    assert renderer.read_side_loads(frame, False).available


@pytest.mark.parametrize("share", [None, True, -1, 101, float("nan"), float("inf"), "bad"])
def test_absent_or_invalid_share_never_defaults_to_half(renderer, share):
    canvas = Canvas()
    renderer.draw_estimated_foot_heatmap(
        SimpleNamespace(canvas=canvas), 0, 0, 160, 160,
        latest={"raw_cells": [0, 0, 0, 0], "pct_left": share},
    )
    words = canvas.words()
    assert words.count("0.0 kg") == 2
    assert "Share of load: --" in words
    assert "Per-cell data unavailable" not in words
    assert "50%" not in "\n".join(words)


def test_both_sides_use_same_frame_scale_not_fixed_anatomical_split(renderer):
    frame = {"raw_cells": [10, 20, 30, 40]}
    left, right = (renderer.read_side_loads(frame, side) for side in (True, False))
    assert left.maximum == right.maximum == 40
    assert renderer._levels(left) == (32, 96)
    assert renderer._levels(right) == (64, 128)
    # Changing only measured front load changes its endpoint, not a fabricated
    # toe/heel share; no 60/40 or similar anatomical allocation is applied.
    changed = renderer.read_side_loads({"raw_cells": [0, 20, 30, 40]})
    assert renderer._levels(changed) == (0, 96)


@pytest.mark.parametrize("total, status", [(0, "No load detected"), (0.5, "Low load · under 1 kg"),
                                          (None, "Low load · under 1 kg")])
def test_unloaded_board_noise_never_normalizes_to_hot(renderer, total, status):
    frame = {"raw_cells": [0, 0.2, 0.3, 0], "total_kg": total}
    before = deepcopy(frame)
    for side in (True, False):
        loads = renderer.read_side_loads(frame, side)
        assert renderer._levels(loads) == (0, 0)
        canvas = Canvas()
        renderer.draw_estimated_foot_heatmap(SimpleNamespace(canvas=canvas), 0, 0, 160, 160, side, frame)
        assert status in canvas.words()
        assert ("0.3 kg" if side else "0.2 kg") in canvas.words()
    assert frame == before


def test_reported_total_takes_precedence_and_missing_cells_are_not_zero(renderer):
    # A valid total can include processing/calibration not represented by the
    # raw displayed zones. Honor it for this display-only threshold.
    frame = {"raw_cells": [1, 2, 3, 4], "total_kg": 0}
    assert renderer.read_side_loads(frame).low_load
    assert renderer._levels(renderer.read_side_loads(frame)) == (0, 0)
    for total in (True, float("nan"), -1):
        loads = renderer.read_side_loads({**frame, "total_kg": total})
        assert loads.total == 10
        assert not loads.low_load
    partial = renderer.read_side_loads({"raw_cells": [0.1, None, 0.2, None]})
    assert partial.total is None
    assert not partial.low_load
    missing = renderer.read_side_loads({"total_kg": 0})
    assert renderer._levels(missing) == (None, None)
    assert not missing.low_load
    sensor_noise = renderer.read_side_loads({"raw_cells": [0.2] * 4, "total_kg": 0})
    assert sensor_noise.total == 0
    assert renderer._levels(sensor_noise) == (0, 0)


@pytest.mark.parametrize("total", [1, 20, 80])
def test_loaded_frames_keep_shared_relative_scale(renderer, total):
    loads = renderer.read_side_loads({"raw_cells": [1, 2, 3, 4], "total_kg": total})
    assert not loads.low_load
    assert renderer._levels(loads) == (32, 96)


def test_color_depends_only_on_longitudinal_position(renderer):
    image = renderer._foot_pixels(160, 280, True, 128, 0)
    mask, edge = renderer._masks(160, 280, True)
    for row in (90, 140, 200, 240):
        interior = [image.getpixel((col, row))[:3] for col in range(image.width)
                    if mask.getpixel((col, row)) == 255 and edge.getpixel((col, row)) == 0]
        assert len(interior) > 10
        assert len(set(interior)) == 1
        assert interior[0] == renderer._color(1 - row / (image.height - 1))


@pytest.mark.parametrize("levels", [(0, 0), (128, 20), (10, 128), (None, None)])
def test_left_and_right_rasters_are_exact_mirrors(renderer, levels):
    left = renderer._foot_pixels(133, 211, True, *levels)
    right = renderer._foot_pixels(133, 211, False, *levels)
    difference = ImageChops.difference(left.transpose(Image.Transpose.FLIP_LEFT_RIGHT), right)
    assert difference.getextrema() == ((0, 0),) * 4


def test_zero_is_neutral_and_missing_is_distinct(renderer):
    zero = renderer._foot_pixels(120, 240, True, 0, 0)
    missing = renderer._foot_pixels(120, 240, True, None, None)
    pixel = (50, 150)  # Interior, away from the outline.
    assert zero.getpixel(pixel)[:3] == renderer._rgb(renderer.T.SURFACE_2)
    assert missing.getpixel(pixel)[:3] == renderer._rgb(renderer.T.SURFACE)
    assert zero.getpixel(pixel)[3] == missing.getpixel(pixel)[3] == 255
    assert renderer._levels(renderer.read_side_loads({"raw_cells": [0] * 4})) == (0, 0)


@pytest.mark.parametrize("size", [(160, 160), (250, 270), (700, 900)])
@pytest.mark.parametrize("raw", [None, [0] * 4, [10, 20, 30, 40]])
def test_headless_geometry_is_bounded_and_work_is_bounded(renderer, size, raw):
    width, height = size
    canvas = Canvas()
    renderer.draw_estimated_foot_heatmap(
        SimpleNamespace(canvas=canvas), 23, 17, width, height,
        latest={"raw_cells": raw, "pct_left": 40},
    )
    assert len(canvas.items) < 110
    for _, coordinates, _ in canvas.items:
        assert all(23 <= value <= 23 + width for value in coordinates[::2])
        assert all(17 <= value <= 17 + height for value in coordinates[1::2])


def test_tiny_panels_do_not_draw_clipped_text(renderer):
    canvas = Canvas()
    renderer.draw_estimated_foot_heatmap(SimpleNamespace(canvas=canvas), 0, 0, 80, 100)
    assert canvas.items == []


def test_font_shrinking_keeps_scaled_canvas_pixel_scale(renderer):
    class ScaledRecorder(Canvas):
        ui_scale = 2

        def __init__(self):
            super().__init__()
            self.updates = []

        def create_text(self, *coords, **options):
            self.physical_size = abs(options["font"][1]) * self.ui_scale
            self.items.append(("create_text", coords, options))
            return 1

        def bbox(self, item):
            return (0, 0, self.physical_size * 8 / self.ui_scale, 20)

        def itemconfigure(self, item, **options):
            self.physical_size = abs(options["font"][1])
            self.updates.append(options["font"])

    canvas = ScaledRecorder()
    renderer._label(canvas, 80, 30, "Long value", 13, renderer.T.TEXT, 80)
    assert canvas.updates[0][1] == -24
    assert canvas.updates[-1][1] == -20
    assert canvas.bbox(1)[2] <= 80


def test_geometry_cache_is_bounded(renderer):
    renderer._masks.cache_clear()
    for width in range(20, 50):
        renderer._masks(width, 80, True)
    info = renderer._masks.cache_info()
    assert info.maxsize == 16
    assert info.currsize == 16
    renderer._masks(49, 80, True)
    assert renderer._masks.cache_info().hits == info.hits + 1


def _root_or_skip():
    try:
        return tk.Tk()
    except tk.TclError:
        pytest.skip("graphical display required")


@pytest.mark.parametrize("size", [(160, 160), (250, 200), (250, 220), (250, 270)])
@pytest.mark.parametrize("raw", [None, [0] * 4, [10, 20, 30, 40]])
def test_real_canvas_labels_fit_without_overlapping(renderer, size, raw, monkeypatch):
    root = _root_or_skip()
    monkeypatch.setattr(renderer.theme, "_UI_FONT", renderer.theme._resolve_ui_font())
    width, height = size
    canvas = tk.Canvas(root, width=width, height=height)
    canvas.pack()
    renderer.draw_estimated_foot_heatmap(
        SimpleNamespace(canvas=canvas), 0, 0, width, height,
        latest={"raw_cells": raw, "pct_left": 40},
    )
    root.update_idletasks()
    boxes = [(canvas.itemcget(item, "text"), canvas.bbox(item))
             for item in canvas.find_all() if canvas.type(item) == "text"]
    assert len(canvas.find_withtag("estimated-foot-image")) == 1
    for label, (x0, y0, x1, y1) in boxes:
        assert 0 <= x0 < x1 <= width, label
        assert 0 <= y0 < y1 <= height, label
    for i, (label, a) in enumerate(boxes):
        for other, b in boxes[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (label, other)
    root.destroy()


def test_native_image_cache_stays_bounded_over_live_frames(renderer, monkeypatch):
    root = _root_or_skip()
    monkeypatch.setattr(renderer.theme, "_UI_FONT", renderer.theme._resolve_ui_font())
    canvas = tk.Canvas(root, width=250, height=270)
    canvas.pack()
    app = SimpleNamespace(canvas=canvas)
    for load in range(40):
        canvas.delete("all")
        renderer.draw_estimated_foot_heatmap(app, 0, 0, 250, 270,
                                             latest={"raw_cells": [load, 40, 20, 40]})
        root.update_idletasks()
    assert len(canvas._estimated_foot_cache) == renderer._PHOTO_CACHE_SIZE
    assert len(canvas.find_all()) < 15
    root.destroy()


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_scaled_canvas_card_headers_and_values_do_not_overlap(renderer, scale, monkeypatch):
    from src.ui.scaling import ScaledCanvas

    root = _root_or_skip()
    monkeypatch.setattr(renderer.theme, "_UI_FONT", renderer.theme._resolve_ui_font())
    try:
        canvas = ScaledCanvas(root, scale=scale, width=250 * scale, height=270 * scale)
        canvas.pack()
        renderer.draw_estimated_foot_heatmap(
            SimpleNamespace(canvas=canvas), 0, 0, 250, 270,
            latest={"raw_cells": [10, 20, 30, 40], "pct_left": 40},
        )
        root.update_idletasks()
        boxes = [(canvas.itemcget(item, "text"), canvas.bbox(item))
                 for item in canvas.find_all() if canvas.type(item) == "text"]
        for label, (x0, y0, x1, y1) in boxes:
            assert 0 <= x0 < x1 <= 250, label
            assert 0 <= y0 < y1 <= 270, label
        for i, (label, a) in enumerate(boxes):
            for other, b in boxes[i + 1:]:
                assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (scale, label, other)
    finally:
        root.destroy()
