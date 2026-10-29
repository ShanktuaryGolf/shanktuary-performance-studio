"""Real Tools-menu scale controls: placement, hit mapping, bounds and persistence."""
import tkinter as tk

import pytest

import shanktuary_performance_studio as studio
from src.ui.desktop import ShanktuaryDesktopApp
from src.ui.scaling import load_choice


@pytest.mark.parametrize("initial_scale", ["100%", "200%"])
def test_tools_scale_controls(initial_scale, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("requires a graphical display")
    original_scaling = root.tk.call("tk", "scaling")
    try:
        root.geometry("3840x2160")
        app = ShanktuaryDesktopApp(root)
        app.set_ui_scale(initial_scale, persist=False)
        app.view_mode = 10
        root.update()
        assert not hasattr(app, "design_scale_rect")
        assert not hasattr(app, "show_ui_scale")
        # Open the actual top-bar Tools dropdown through its scaled binding.
        def click(rect):
            x = round((rect[0] + rect[2]) / 2 * app.ui_scale - app.canvas.canvasx(0))
            y = round((rect[1] + rect[3]) / 2 * app.ui_scale - app.canvas.canvasy(0))
            app.canvas.event_generate("<Button-1>", x=x, y=y)
            root.update()
        click(app.design_tools_btn_rect)
        assert app.show_tools_menu
        for _ in range(6):
            click(app.ui_scale_controls["minus"])
        assert app.ui_scale == 1
        for _ in range(6):
            click(app.ui_scale_controls["plus"])
        assert app.ui_scale == 2
        assert app.show_tools_menu
        assert load_choice() == "200%"
        click(app.ui_scale_controls["minus"])
        assert app.ui_scale == 1.75
        assert load_choice() == "175%"
        app._display_dpi = 144
        click(app.ui_scale_controls["auto"])
        assert app.ui_scale_choice == "Auto"
        assert app.ui_scale == 1.5
        assert load_choice() == "Auto"
        click(app.design_tools_btn_rect)
        assert not app.show_tools_menu
        assert all(app.canvas.itemcget(item, "text") != "UI SCALE"
                   for item in app.canvas.find_all() if app.canvas.type(item) == "text")
    finally:
        root.tk.call("tk", "scaling", original_scaling)
        for callback in root.tk.call("after", "info"):
            root.after_cancel(callback)
        root.destroy()
