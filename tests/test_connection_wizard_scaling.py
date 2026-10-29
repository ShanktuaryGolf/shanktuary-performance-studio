"""Real-Tk checks for the scaled connection wizard and scrolled hit targets."""
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.ui.connection_wizard import ConnectionWizard


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_wizard_scale_widgets_and_scrolled_clicks(scale):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("requires a graphical display")
    original_scaling = root.tk.call("tk", "scaling")
    root._sps_ui_scale = scale
    root.tk.call("tk", "scaling", scale * 96 / 72)
    controller = SimpleNamespace(settings={}, snapshot=lambda: {"state": "idle"}, stop=Mock())
    wizard = ConnectionWizard(root, controller)
    try:
        root.update()
        assert (wizard.w, wizard.h) == (1280, 820)
        assert wizard.canvas.ui_scale == scale
        # Put the bottom/right continue action into view. Bind converts display
        # coordinates once, including scroll, before logical hit testing.
        target = next(rect for rect in wizard._hit_rects if rect[4] == "continue")
        wizard.canvas.xview_moveto(1)
        wizard.canvas.yview_moveto(1)
        root.update()
        x = round((target[0] + target[2]) / 2 * scale - wizard.canvas.canvasx(0))
        y = round((target[1] + target[3]) / 2 * scale - wizard.canvas.canvasy(0))
        original = wizard._action
        wizard._action = Mock()
        wizard.canvas.event_generate("<Button-1>", x=x, y=y)
        root.update()
        wizard._action.assert_called_once_with("continue", None)
        wizard._action = original
        wizard.source = "gspro"
        wizard.page = "connect"
        wizard._draw()
        root.update()
        entries = [widget for widget in wizard._widgets if isinstance(widget, tk.Entry)]
        assert len(entries) == 1
        assert entries[0].winfo_height() == round(38 * scale)
        wizard._show_metric_options()
        root.update()
        dialogs = [widget for widget in wizard.win.winfo_children() if isinstance(widget, tk.Toplevel)]
        assert dialogs[-1].winfo_width() == round(560 * scale)
        assert dialogs[-1].winfo_height() == round(330 * scale)
        dialogs[-1].destroy()
        wizard.win.geometry("700x500")
        root.update()
        assert wizard.canvas.xview()[1] < 1
        assert wizard.canvas.yview()[1] < 1
        bars = [widget for widget in wizard.win.winfo_children() if isinstance(widget, tk.Scrollbar)]
        assert len(bars) == 2
        assert all(bar.winfo_ismapped() for bar in bars)
    finally:
        wizard._close()
        root.tk.call("tk", "scaling", original_scaling)
        root.destroy()
