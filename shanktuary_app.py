#!/usr/bin/env python3
"""Production entry point for the redesigned Shanktuary desktop app.

Usage:
    python shanktuary_app.py              # normal launch
    python shanktuary_app.py --splash     # force the setup splash
    python shanktuary_app.py --no-splash  # skip it even on first run
"""

import argparse
import threading

import shanktuary_performance_studio as studio
from src.ui import ShanktuaryDesktopApp, SplashScreen, should_show_splash


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="shanktuary_app",
        description="Shanktuary Performance Studio",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--splash", action="store_true",
        help="always show the shot-source setup splash, even after onboarding "
             "(for testing; does not erase your saved settings)",
    )
    group.add_argument(
        "--no-splash", action="store_true",
        help="never show the splash, even on a first run",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Keep the production connectivity lifecycle exactly aligned with the
    # original entry point: Nova worker + local OBS/browser server + Tk UI.
    t_ws = threading.Thread(target=studio.websocket_worker, daemon=True)
    t_ws.start()

    # GSPro range-shot poller. This is a supervisor: it starts and stops the
    # poll loop as the user's shot source changes, so choosing GSPro on the
    # splash takes effect without an app restart.
    t_gspro = threading.Thread(target=studio.gspro_worker, daemon=True)
    t_gspro.start()

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

    # First run: ask which shot source this user actually owns before the
    # main window appears. GSPro users never touch an environment variable.
    #
    # The root is withdrawn so its empty grey canvas does not sit on top of
    # the splash. That is safe ONLY because SplashScreen explicitly calls
    # deiconify() on itself: a Toplevel under a withdrawn master is not
    # mapped by default (the original bug — an invisible modal that hung the
    # launch), but an explicit deiconify maps it regardless. See
    # tests/test_splash_visibility.py, which locks both halves of this in.
    splash_choice = None
    if args.splash or (should_show_splash() and not args.no_splash):
        root.withdraw()
        try:
            bag_specs = studio.load_bag_specs_for_splash()
            clubs = list(bag_specs) or list(studio.DEFAULT_CLUBS)
            splash_choice = SplashScreen(
                root, clubs=clubs, club_specs=bag_specs
            ).run()
        except Exception as exc:
            # A splash failure must never block the app the user paid for.
            print(f"[splash] skipped: {exc}")
        root.deiconify()
        # Wake the supervisor so a GSPro choice starts polling immediately.
        studio.gspro_reconfigure.set()

    app = ShanktuaryDesktopApp(root)  # noqa: F841 - Tk callbacks retain it
    if splash_choice and splash_choice.get("club") in getattr(app, "clubs", []):
        app.current_club = splash_choice["club"]
        app.draw_screen()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
