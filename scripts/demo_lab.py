#!/usr/bin/env python3
"""Isolated graphical Lab demo: no server, hardware, user-data reads or writes.

Run: python scripts/demo_lab.py
Click Demo swing, watch the changing load/CoP/force, then Stop demo.
The selected fixture remains pressure-unavailable. Select another fixture while
running to verify that history selection stops the preview instead of attaching
simulated readings to a real shot. Hardware and Tare are inert in this harness.
"""
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Must precede every production import: obs_server creates its manager at import.
# Keep configuration, logs and platform-specific user data inside a disposable
# process-local directory, and prevent hardware workers from being started.
_STATE_DIR = tempfile.TemporaryDirectory(prefix="sps-lab-demo-")
STATE = Path(_STATE_DIR.name)
os.environ.update(
    SPS_UI_PREVIEW="1",
    SPS_DISABLE_LEGACY_MIGRATION="1",
    HOME=str(STATE),
    USERPROFILE=str(STATE),
    APPDATA=str(STATE / "AppData" / "Roaming"),
    LOCALAPPDATA=str(STATE / "AppData" / "Local"),
    XDG_DATA_HOME=str(STATE / "data"),
    XDG_CONFIG_HOME=str(STATE / "config"),
    XDG_CACHE_HOME=str(STATE / "cache"),
    XDG_STATE_HOME=str(STATE / "state"),
    SPS_SHOT_SOURCE_FILE=str(STATE / "source.json"),
)
# Do not instantiate ShanktuaryApp: its constructor migrates legacy sessions.
# This harness only binds its pressure drawing methods to in-memory fixtures.

from shanktuary_performance_studio import ShanktuaryApp  # noqa: E402
from src.ui.concept_workspaces import draw_lab  # noqa: E402
from src.ui.desktop import ShanktuaryDesktopApp  # noqa: E402
from src.ui.lab_demo import toggle  # noqa: E402


def main():
    root = tk.Tk()
    root.title("Lab isolated demo · synthetic preview · no data saved")
    root.geometry("1300x900")
    canvas = tk.Canvas(root, highlightthickness=0, bg="#0d1c21")
    canvas.pack(fill="both", expand=True)
    app = SimpleNamespace(root=root, canvas=canvas, current_shot={"id": "fixture A"},
                          view_mode=8, is_left_handed=False, swing_lab_history=[])
    app.is_reviewing_past_shot = lambda: True
    app.get_pressure_trace = lambda shot: None
    app.board_is_streaming = lambda: False
    app.pressure_display_trail = lambda: ShanktuaryDesktopApp.pressure_display_trail(app)
    for name in ("draw_cop_trajectory_canvas", "draw_single_foot_heatmap", "draw_force_timeline_canvas"):
        setattr(app, name, getattr(ShanktuaryApp, name).__get__(app))

    def draw():
        canvas.delete("all")
        draw_lab(app, canvas.winfo_width(), canvas.winfo_height())
        canvas.create_text(250, 24, text=f"Selected history fixture: {app.current_shot['id']} (no pressure)", fill="white")

    def select():
        app.current_shot = {"id": "fixture B" if app.current_shot['id'] == 'fixture A' else 'fixture A'}
        draw()

    def click(event):
        x0, y0, x1, y1 = app.swing_lab_demo_rect
        if x0 <= event.x <= x1 and y0 <= event.y <= y1:
            toggle(app)

    app.draw_screen = draw
    tk.Button(root, text="Select another history fixture", command=select).place(x=550, y=8)
    canvas.bind("<Button-1>", click)
    canvas.bind("<Configure>", lambda event: draw())
    root.mainloop()


if __name__ == "__main__":
    main()
