#!/usr/bin/env python3
"""Production entry point for the redesigned Shanktuary desktop app."""

import threading

import shanktuary_performance_studio as studio
from src.ui import ShanktuaryDesktopApp


def main():
    # Keep the production connectivity lifecycle exactly aligned with the
    # original entry point: Nova worker + local OBS/browser server + Tk UI.
    t_ws = threading.Thread(target=studio.websocket_worker, daemon=True)
    t_ws.start()
    studio.obs_server.launch_obs_server_thread()

    root = studio.tk.Tk()
    default_w, default_h = 1920, 1080
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    if scr_w >= default_w and scr_h >= default_h:
        win_w, win_h = default_w, default_h
    else:
        win_w = min(default_w, scr_w - 40)
        win_h = min(default_h, scr_h - 80)

    pos_x = max(0, (scr_w - win_w) // 2)
    pos_y = max(0, (scr_h - win_h) // 3)
    root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    root.minsize(1100, 720)

    app = ShanktuaryDesktopApp(root)  # noqa: F841 - Tk callbacks retain it
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
