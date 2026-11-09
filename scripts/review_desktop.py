#!/usr/bin/env python3
"""Launch a separate, hardware-disabled development review with private state."""
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
    state = args.state_dir.resolve()
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
        raise RuntimeError('Hardware connections are disabled in this isolated design review.')
    SourceConnections.start = blocked
    StudioConnectionSetup.start = blocked
    def no_discovery(wizard):
        wizard._local_message = 'Device discovery is disabled in this isolated design review.'
        wizard._discovering = False
        wizard._draw()
    ConnectionWizard._start_discovery = no_discovery
    manager = obs_server.pressure_manager
    manager._create_hardware_backend = blocked
    manager._create_openfp_backend = blocked
    manager.enumerate_boards = lambda *a, **k: []

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
    def preview_block(*_args, **_kwargs):
        app.copy_feedback = 'Design review: hardware connections disabled'
        app.draw_screen()
    app.start_pairing_flow = preview_block
    app.start_guided_setup = preview_block
    # Only review-owned state is ever loaded/saved by this interpreter.
    if not args.empty and not any(session.get('shots') for session in app.sessions):
        shots=[]
        for index, carry in enumerate((149,153,151,148,154,157,152,156,150,154)):
            shots.append({
                'id':f'review-{index}', 'club':'7 Iron', '_source':'gspro', '_review_sample':True,
                'vertical_launch_angle_degrees':18.2, 'horizontal_launch_angle_degrees':1.1,
                'total_spin_rpm':6470, 'ball_speed_meters_per_second':50.06848,
                'open_golf_coach':{
                    'shot_name':('Draw','Straight','Fade')[index%3], 'total_spin_rpm':6470,
                    'us_customary_units':{'carry_distance_yards':carry,'total_distance_yards':carry+8,
                        'ball_speed_mph':112,'peak_height_yards':29,'offline_distance_yards':index%7-3},
                },
            })
        app.sessions=[{'id':'review-sample','name':'REVIEW · SAMPLE DATA','shots':shots}]
        app.active_session_index=0
        app.selected_shot_index=len(shots)-1
        app.current_shot=shots[-1]
        app.current_club='7 Iron'
        app.save_session_to_file()
    app.view_mode=12
    width=min(1600,max(1100,root.winfo_screenwidth()-40))
    height=min(1000,max(720,root.winfo_screenheight()-100))
    root.geometry(f'{width}x{height}+20+30')
    root.title('Shanktuary Design Review · ISOLATED COPY · SAMPLE DATA')
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
                'review_url':f'http://127.0.0.1:{port}','port':port,'hardware_disabled':True,
                'session_file':production.SESSION_LOG_PATH}
        (state/'review-status.json').write_text(json.dumps(record,indent=2))
        print('REVIEW_READY '+json.dumps(record),flush=True)
    root.after(1500,report_window)
    root.protocol('WM_DELETE_WINDOW',root.destroy)
    try:
        root.mainloop()
    finally:
        server.shutdown()
        server.server_close()


if __name__=='__main__':
    main()
