#!/usr/bin/env python3
"""Launch a separate, hardware-enabled, explicitly selected physical-board test with private state."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--empty', action='store_true')
    args = parser.parse_args()
    state = args.state_dir.resolve() / ('run-' + __import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + __import__('uuid').uuid4().hex[:6])
    state.mkdir(parents=True, exist_ok=True)
    root_path = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_path))
    os.environ.update(
        SPS_UI_PREVIEW='1', SPS_SKIP_SPLASH='1', HOME=str(state), USERPROFILE=str(state),
        XDG_DATA_HOME=str(state/'data'), XDG_CONFIG_HOME=str(state/'config'),
        APPDATA=str(state/'appdata'), LOCALAPPDATA=str(state/'localappdata'),
        SPS_SHOT_SOURCE_FILE=str(state/'shot-source.json'),
    )
    for name in ('OPENFP_WS_URL', 'SPS_OPENFP_URL', 'NOVA_IP', 'NOVA_PORT', 'SPS_SHOT_SOURCE', 'SPS_GSPRO_DB', 'SPS_PUREPLAY_PROFILES'):
        os.environ.pop(name, None)
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    choice_root = tk.Tk()
    choice_root.title('Choose physical board source')
    choice_root.geometry('560x370')
    selected = {}
    tk.Label(choice_root, text='PHYSICAL HARDWARE TEST - NO SIMULATED READINGS', wraplength=520).pack(pady=14)
    tk.Label(choice_root, text='Choose only hardware you own and intend to connect.\nWii boards must already be paired and exposed as Windows HID.\nPairing is optional and requires a separate confirmation.', wraplength=520).pack(pady=10)
    tk.Label(choice_root, text='Factory calibration is required for weight readings. If it cannot be read, setup shows diagnostics instead of guessed kg. Keep boards unloaded while connecting.', wraplength=520, fg='#9C341B').pack(pady=10)
    def choose(source, mode):
        url = None
        if source == 'openfp':
            url = simpledialog.askstring('Open-FP hardware address', 'Enter your physical Open-FP board LAN address (not a simulator):', parent=choice_root)
            if not url:
                return
            from src.hardware.pressure.openfp_backend import parse_url
            try:
                parse_url(url)
            except ValueError as exc:
                messagebox.showerror('Invalid address', str(exc), parent=choice_root)
                return
        selected.update(source=source, mode=mode, url=url)
        choice_root.destroy()
    for label, source, mode in [('Connect one Wii Balance Board', 'wbb', 'single'), ('Connect two Wii Balance Boards', 'wbb', 'dual')]:
        tk.Button(choice_root, text=label, command=lambda s=source, m=mode: choose(s,m)).pack(fill='x', padx=35, pady=5)
    choice_root.mainloop()
    if not selected:
        return
    # A git checkout may contain legacy app data: never migrate it into a test.
    import user_data
    user_data.legacy_data_dirs = lambda: []
    from scripts.review_state import prepare_isolated_history
    prepare_isolated_history()
    import obs_server
    import shanktuary_performance_studio as production
    from src.connections.controller import SourceConnections, StudioConnectionSetup
    from src.ui.connection_wizard import ConnectionWizard
    from src.ui.desktop import ShanktuaryDesktopApp

    def blocked(*_args, **_kwargs):
        raise RuntimeError('Launch-monitor connections are disabled in this board-only test.')
    SourceConnections.start = blocked
    StudioConnectionSetup.start = blocked
    def no_discovery(wizard):
        wizard._local_message = 'Device discovery is disabled in this isolated design review.'
        wizard._discovering = False
        wizard._draw()
    ConnectionWizard._start_discovery = no_discovery
    manager = obs_server.pressure_manager
    # Import in preview mode avoids hardware access before the explicit choice.
    # Empty per-run state ensures no previous sample/history/calibration is imported.
    manager.pressure_source = selected['source']
    manager.board_mode = selected['mode']
    manager.openfp_url = selected['url']
    def physical_only(enabled):
        if enabled:
            raise RuntimeError('Simulation disabled in physical test. Use Start-Demo-Only.cmd separately.')
        with manager.lock:
            return manager._set_simulator_unlocked(False)
    manager.set_simulator = physical_only
    os.environ.pop('SPS_UI_PREVIEW', None)
    manager._init_subsystem()

    # A unique loopback-only server cannot replace or expose an installed server.
    server = obs_server.ThreadedHTTPServer(('127.0.0.1', 0), obs_server.OBSHTTPRequestHandler)
    port = server.server_address[1]
    obs_server.OBS_PORT = port
    original_open = webbrowser.open
    def review_open(url, *a, **kw):
        parts = urlsplit(url)
        if parts.hostname in ('localhost', '127.0.0.1') and parts.port == 9321:
            url = urlunsplit((parts.scheme, f'127.0.0.1:{port}', parts.path, parts.query, parts.fragment))
        return original_open(url, *a, **kw)
    webbrowser.open = review_open
    threading.Thread(target=server.serve_forever, daemon=True).start()

    root = tk.Tk()
    root.report_callback_exception = lambda *error: __import__('traceback').print_exception(*error)
    app = ShanktuaryDesktopApp(root)
    original_pairing = app.start_pairing_flow
    def confirm_pairing(*_args, **_kwargs):
        if not messagebox.askyesno('Confirm system-wide Bluetooth pairing', 'Scan first for already-paired boards. Pairing changes Windows Bluetooth bonds and HID services shared with other apps; recovery may remove and recreate a stale bond. No driver installation or administrator changes are performed. Continue with native Windows pairing?', parent=root):
            return
        count = simpledialog.askinteger('How many NEW boards?', 'How many additional unpaired Wii boards do you want to pair now? Already-paired boards do not count.', parent=root, minvalue=1, maxvalue=2)
        if count is not None:
            original_pairing(target_count=count)
    app.start_pairing_flow = confirm_pairing
    from src.ui import lab_demo
    def no_demo(*_args, **_kwargs):
        messagebox.showinfo('Physical test only', 'For clearly separated synthetic data, close this test and run Start-Demo-Only.cmd.', parent=root)
        return False
    lab_demo.toggle = no_demo
    app.view_mode=10
    width=min(1600,max(1100,root.winfo_screenwidth()-40))
    height=min(1000,max(720,root.winfo_screenheight()-100))
    root.geometry(f'{width}x{height}+20+30')
    root.title('Shanktuary Board Test | PHYSICAL SOURCE ONLY | ' + selected['source'] + ' ' + selected['mode'])
    app.draw_screen()
    last=[None]
    def sync_review():
        shot=app.current_shot
        fingerprint=repr(shot)
        if fingerprint != last[0]:
            with obs_server.obs_state.lock:
                obs_server.obs_state.latest_shot=copy.deepcopy(shot)
                obs_server.obs_state.selected_club=app.current_club
            last[0]=fingerprint
        root.after(250,sync_review)
    sync_review()
    def report_window():
        record={'pid':os.getpid(),'mapped':bool(root.winfo_ismapped()),'geometry':root.geometry(),
                'title':root.title(),'state_dir':str(state),'source_dir':str(root_path),
                'review_url':f'http://127.0.0.1:{port}','port':port,'hardware_disabled':False, 'simulated':False, 'source':selected,
                'session_file':production.SESSION_LOG_PATH}
        (state/'review-status.json').write_text(json.dumps(record,indent=2))
        print('REVIEW_READY '+json.dumps(record),flush=True)
    root.after(1500,report_window)
    root.protocol('WM_DELETE_WINDOW',root.destroy)
    try:
        root.mainloop()
    finally:
        manager.running = False
        if manager.thread:
            manager.thread.join(timeout=3)
        with manager.lock:
            if manager.backend and not (manager.thread and manager.thread.is_alive()):
                manager.backend.close()
        server.shutdown()
        server.server_close()


if __name__=='__main__':
    main()
