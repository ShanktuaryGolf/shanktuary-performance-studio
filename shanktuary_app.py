#!/usr/bin/env python3
"""Production entry point for the redesigned Shanktuary desktop app.

Usage:
    python shanktuary_app.py              # normal launch
    python shanktuary_app.py --splash     # force the setup splash
    python shanktuary_app.py --no-splash  # skip it even on first run
"""

import argparse
import os
import sys
import threading

# Smoke launches must disable import-time pressure hardware probing too.
if "--smoke-test" in sys.argv[1:]:
    os.environ["SPS_UI_PREVIEW"] = "1"

# Mirror the console into ~/.shanktuary/logs/ BEFORE the studio import.
# Importing it initialises the pressure subsystem and prints several lines;
# installing the tee inside main() came too late to capture them, and a
# crash during that import would never reach the log at all.
from src.session_log import install as _install_session_log

_LOG_FILE = _install_session_log()

import shanktuary_performance_studio as studio  # noqa: E402
from src.ui import ShanktuaryDesktopApp, should_show_splash  # noqa: E402
from src.ui.scaling import configure_root  # noqa: E402


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
    group.add_argument(
        "--smoke-test", action="store_true",
        help="render the desktop and sidebar once, then exit (packaging check)",
    )
    return parser.parse_args(argv)


def smoke_test():
    """Exercise the real UI, including Pillow's lazily loaded native Tk bridge.

    No main connection workers or HTTP server are started. Set SPS_UI_PREVIEW=1
    to disable import-time pressure hardware probing, and use an isolated HOME
    and XDG_DATA_HOME: importing the app and creating its UI uses normal logging
    and user-data paths, just as a production launch does.
    """
    root = studio.tk.Tk()
    callback_errors = []
    root.report_callback_exception = lambda *error: callback_errors.append(error)
    try:
        root.geometry("1920x1080")
        app = ShanktuaryDesktopApp(root)
        root.update()
        app.draw_screen()
        root.update()
        if callback_errors:
            _, error, traceback = callback_errors[0]
            raise error.with_traceback(traceback)
        # This image is created by the actual sidebar renderer with ImageTk,
        # not by a smoke-only import that could hide a missing PyInstaller hook.
        image = getattr(app, "_brand_header_v17_img", None)
        if image is None or image.width() <= 0 or image.height() <= 0:
            raise RuntimeError("Sidebar ImageTk image was not rendered")
        if not app.canvas.find_all():
            raise RuntimeError("Desktop canvas was not rendered")
        print("SPS_SMOKE_TEST_OK: desktop and sidebar rendered", flush=True)
    finally:
        studio.source_connections.stop()
        root.destroy()


def main(argv=None):
    args = parse_args(argv)

    if args.smoke_test:
        smoke_test()
        return

    if _LOG_FILE:
        print(f"[+] Logging to {_LOG_FILE}")

    show_setup = args.splash or (should_show_splash() and not args.no_splash)

    # Keep the production connectivity lifecycle exactly aligned with the
    # original entry point: Nova worker + local OBS/browser server + Tk UI.
    t_ws = threading.Thread(target=studio.websocket_worker, daemon=True)
    t_ws.start()

    # GSPro range-shot poller. This is a supervisor: it starts and stops the
    # poll loop as the user's shot source changes, so choosing GSPro on the
    # splash takes effect without an app restart.
    t_gspro = threading.Thread(target=studio.gspro_worker, daemon=True)
    t_gspro.start()

    if os.environ.get("SPS_UI_PREVIEW") != "1":
        studio.obs_server.launch_obs_server_thread()
    else:
        print("[preview] OBS server disabled; connection readiness remains real")

    root = studio.tk.Tk()
    _, display_scale = configure_root(root)
    default_w, default_h = round(1920 * display_scale), round(1080 * display_scale)
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
    if show_setup:
        root.withdraw()
        try:
            bag_specs = studio.load_bag_specs_for_splash()
            clubs = list(bag_specs) or list(studio.DEFAULT_CLUBS)
            from src.ui.connection_wizard import ConnectionWizard
            splash_choice = ConnectionWizard(
                root, controller=studio.connection_setup_controller(), clubs=clubs, club_specs=bag_specs
            ).run()
        except Exception as exc:
            # A splash failure must never block the app the user paid for.
            print(f"[splash] skipped: {exc}")
        root.deiconify()
        # Wake the supervisor so a GSPro choice starts polling immediately.
        studio.gspro_reconfigure.set()

    root.bind("<Destroy>", lambda event: studio.source_connections.stop() if event.widget is root else None, add="+")
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
