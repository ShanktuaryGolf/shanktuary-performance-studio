#!/usr/bin/env python3
"""Render the real desktop with isolated, explicitly marked preview data.

Run from a graphical desktop. No device workers, HTTP server or saved user
sessions are loaded. The optional canvas exports are render artifacts, not
screenshots of a live device connection.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATE = Path(tempfile.mkdtemp(prefix="sps-concept-preview-"))
os.environ.update(
    SPS_UI_PREVIEW="1", HOME=str(STATE), USERPROFILE=str(STATE),
    APPDATA=str(STATE / "appdata"), LOCALAPPDATA=str(STATE / "localappdata"),
    XDG_DATA_HOME=str(STATE / "data"), XDG_CONFIG_HOME=str(STATE / "config"),
    SPS_SHOT_SOURCE_FILE=str(STATE / "source.json"),
)
for name in ("OPENFP_WS_URL", "SPS_OPENFP_URL", "NOVA_IP", "NOVA_PORT",
             "SPS_SHOT_SOURCE", "SPS_GSPRO_DB", "SPS_PUREPLAY_PROFILES"):
    os.environ.pop(name, None)
# Existing source checkouts can contain legacy history; do not import it.
import user_data  # noqa: E402

user_data.legacy_data_dirs = lambda: []
from scripts.review_state import prepare_isolated_history

prepare_isolated_history()


def sample_shots():
    """Deterministic fixture data; never enters production storage."""
    result = []
    for index, carry in enumerate((149, 153, 151, 148, 154, 157, 152, 156, 150, 154)):
        result.append({
            "id": f"preview-{index}", "club": "7 Iron", "_source": "gspro",
            "vertical_launch_angle_degrees": 18.2,
            "horizontal_launch_angle_degrees": 1.1,
            "total_spin_rpm": 6470, "ball_speed_meters_per_second": 50.06848,
            "open_golf_coach": {
                "shot_name": "Draw" if index % 3 == 0 else "Straight" if index % 3 == 1 else "Fade",
                "total_spin_rpm": 6470,
                "us_customary_units": {"carry_distance_yards": carry,
                    "total_distance_yards": carry + 8, "ball_speed_mph": 112,
                    "peak_height_yards": 29, "offline_distance_yards": index % 7 - 3},
            },
        })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=int, default=9)
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--boards", action="store_true", help="Preview the board setup workspace without hardware fixtures")
    parser.add_argument("--club", default="7 Iron", help="Explicit preview club fixture")
    parser.add_argument("--aim", action="store_true", help="Preview measurement dialog with20ft/12in fixture")
    parser.add_argument("--offline", type=float, help="Override sample lateral landing in yards for projection QA")
    parser.add_argument("--projection-keys", action="store_true", help="Preview only: F6 straight, F7 left, F8 right")
    parser.add_argument("--borderless", action="store_true", help="Unconstrained test window for full-size render capture")
    parser.add_argument("--export", type=Path)
    parser.add_argument("--size", default="1600x1000")
    args = parser.parse_args()
    import tkinter as tk

    from src.ui.desktop import ShanktuaryDesktopApp
    root = tk.Tk()
    errors = []
    def report_error(*error):
        import traceback
        errors.append(error)
        traceback.print_exception(*error)
    root.report_callback_exception = report_error
    root.geometry(args.size + "+0+0")
    app = ShanktuaryDesktopApp(root)
    root.overrideredirect(args.borderless)
    root.geometry(args.size + "+0+0")
    app.sessions = [{"id": "preview", "name": "PREVIEW · SAMPLE DATA", "shots": [] if args.empty else sample_shots()}]
    if args.offline is not None:
        for shot in app.sessions[0]["shots"]:
            shot["open_golf_coach"]["us_customary_units"]["offline_distance_yards"] = args.offline
    app.active_session_index = 0
    app.current_club = args.club
    for shot in app.session_shots:
        shot["club"] = args.club
    app.current_shot = app.session_shots[-1] if app.session_shots else None
    app.selected_shot_index = len(app.session_shots) - 1
    app.view_mode = args.mode
    if args.boards:
        app.view_mode = 10
        app.concept_setup_page = "details"
    if args.aim:
        app.show_aim_modal = True
        app.concept_aim_tab = "measure"
        app.aim_modal_distance = "20"
        app.aim_modal_lateral = "12"
    if args.projection_keys:
        def lateral_preview(value):
            for shot in app.session_shots:
                shot["open_golf_coach"]["us_customary_units"]["offline_distance_yards"] = value
            app.view_mode = 2
            app.draw_screen()
        for key, value in (("<F6>", 0), ("<F7>", -20), ("<F8>", 20)):
            root.bind(key, lambda event, value=value: lateral_preview(value))
    root.title("Shanktuary redesign · PREVIEW / SAMPLE DATA")
    root.update()
    app.draw_screen()
    root.update()
    if errors:
        raise errors[0][1]
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)
        for mode in (12, 9, 1, 4, 5, 2, 3, 6, 7, 8, 11, 10, 13, 14):
            app.view_mode = mode
            app.draw_screen()
            root.update()
            if errors:
                raise errors[0][1]
            import tkinter.font as tkfont
            for item in app.canvas.find_all():
                if app.canvas.type(item) != "text":
                    continue
                spec = app.canvas.itemcget(item, "font")
                font = tkfont.Font(root=root, font=spec)
                face = "Helvetica-Bold" if font.cget("weight") == "bold" else "Helvetica"
                root.tk.call("set", f"previewFontMap({spec})", (face, abs(font.cget("size"))))
            app.canvas.postscript(fontmap="previewFontMap", file=str(args.export / f"mode-{mode}.ps"),
                                  colormode="color", x=0, y=0, width=1600, height=1000,
                                  pagewidth="1600p", pageheight="1000p")
        print("PREVIEW_RENDER_OK: all 14 workspaces", flush=True)
        app.view_mode = args.mode
        app.draw_screen()
    print(f"PREVIEW_WINDOW_ID={root.winfo_id()}", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
