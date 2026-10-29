"""Pure settings tests plus real-Tk tests (display required for the latter)."""
import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from src.ui.scaling import ScaledCanvas, load_choice, resolve_scale, save_choice


@pytest.mark.parametrize("dpi,expected", [(96, 1), (120, 1.25), (144, 1.5), (192, 2), (0, 1), (float("nan"), 1)])
def test_auto_scale(dpi, expected):
    assert resolve_scale("Auto", dpi) == expected


def test_manual_scale_and_persistence(tmp_path):
    path = tmp_path / "display.json"
    assert load_choice(path) == "Auto"
    save_choice("150%", path)
    assert load_choice(path) == "150%"
    assert resolve_scale(load_choice(path), 192) == 1.5
    path.write_text('{"ui_scale": "999%"}')
    assert load_choice(path) == "Auto"
    with pytest.raises(ValueError):
        save_choice("999%", path)


@pytest.fixture
def root():
    if not os.environ.get("DISPLAY"):
        pytest.skip("A real Tk display is required")
    value = tk.Tk()
    value.geometry("1920x1080")
    original_scaling = value.tk.call("tk", "scaling")
    yield value
    value.tk.call("tk", "scaling", original_scaling)
    value.destroy()


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("dpi", [96, 192, 240])
def test_geometry_text_and_click_coordinates(root, scale, dpi):
    root.tk.call("tk", "scaling", dpi / 72)
    canvas = ScaledCanvas(root, scale=scale)
    canvas.pack(fill="both", expand=True)
    root.update()
    rect = canvas.create_rectangle(10, 20, 120, 60, fill="red")
    title = canvas.create_text(20, 22, text="Source", font=("DejaVu Sans", 13), anchor="nw")
    subtitle = canvas.create_text(20, 44, text="Connected", font=("DejaVu Sans", 8), anchor="nw")
    assert canvas.bbox(title)[3] <= canvas.bbox(subtitle)[1]
    assert canvas.coords(rect) == pytest.approx([10, 20, 120, 60])
    assert tk.Canvas.coords(canvas, rect) == pytest.approx([10*scale, 20*scale, 120*scale, 60*scale])
    received = []
    canvas.bind("<Button-1>", lambda event: received.append((event.x, event.y)))
    canvas.event_generate("<Button-1>", x=round(50*scale), y=round(40*scale))
    root.update()
    assert received[-1] == pytest.approx((50, 40), abs=1/scale)
    canvas.destroy()
