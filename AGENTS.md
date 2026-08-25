# Shanktuary Performance Studio — Agent Instructions

Python/Tkinter desktop app for OpenLaunch Nova launch-monitor telemetry, with a
built-in browser/OBS overlay server and a Three.js/WebGPU 3D driving range.
`shanktuary_performance_studio.py` runs the GUI + Nova WebSocket client;
`obs_server.py` serves browser UI/APIs/WebSocket on port 9321; `assets/` holds
browser presentation (overlay, configurator, `range/` WebGPU client); `src/`
holds the importable pressure-sensor hardware/processing package.

## Dev environment

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Deps: Pillow, zeroconf, hidapi, pyserial. Release CI builds on Python 3.10
(`.github/workflows/build-releases.yml`); a local `.venv` here runs 3.14.

## Run

```bash
python3 shanktuary_performance_studio.py      # full desktop app + server
python3 listen_nova_events.py                 # diagnose Nova device WebSocket only
```

Browser URLs once running: `http://localhost:9321` (OBS overlay),
`/config` (configurator), `/?edit=true` (drag/drop canvas), `/range` (WebGPU
driving range), `/?mode=projector` (floor projector fullscreen).

## Test

```bash
python3 -m pytest tests/ -v
python3 -m pytest tests/test_pressure_cop.py -v
python3 -m pytest tests/test_pressure_cop.py::TestPressureCOP::test_centered_load -v
python3 -m pytest tests/test_pressure_integration.py -v   # integration, starts threaded HTTP server
python3 -m pytest tests/test_range_server.py -v           # /range static asset routes
```

Tests mix plain `pytest` functions and `unittest.TestCase` — always run
through pytest. No lint command is configured in this repo.

## Build (release)

```bash
pyinstaller --noconfirm --onedir --windowed --add-data "assets:assets" shanktuary_performance_studio.py  # Linux/macOS
pyinstaller --noconfirm --onedir --windowed --add-data "assets;assets" shanktuary_performance_studio.py  # Windows
```

## Conventions

- Keep boundaries: Tkinter process owns desktop/Nova discovery state,
  `obs_server.py` owns browser/API/WebSocket state, `assets/` owns browser
  presentation, `src/` owns reusable pressure hardware/biomechanics logic.
- Nova discovery order: `NOVA_IP`/`NOVA_PORT` env vars, then
  `_openlaunch-ws._tcp.local.` mDNS, then `openlaunch-nova.local`, then
  fallback host. Don't bypass or hard-code a new path.
- Preserve the native Nova shot payload when forwarding; normalize/derive
  display values at the UI boundary, not on the incoming event.
- Use `obs_state.push_shot()` / `obs_state.broadcast()` for server state and
  browser updates — don't create a second event bus. WebSocket message types:
  `init`, `shot`, `pressure`, `shot_pressure`, `layout_update`.
- Key HTTP routes to keep stable: `/api/shot`, `/api/layout`,
  `/api/pressure/status`, `/api/pressure/shot`, `/api/pressure/tare`,
  `/api/pressure/simulator`, `/api/pressure/pin`.
- Hardware I/O belongs in `src/hardware/pressure` `BoardBackend`
  implementations; calculations belong in `src/processing/pressure`. Expose
  public symbols via each package's `__init__.py`.
- `SensorReading.timestamp` is a monotonic sensor clock. Apply tare offsets
  before CoP/torque/swing processing; do board-orientation remapping at the
  hardware boundary. Preserve the four-cell reading shape.
- `PressureManager` publishes frames at ~30 Hz; shot capture uses an
  impact-centered pre/post window. Keep `raw_cells`, `phase`, CoP percentages,
  and relative timing fields intact when extending frames.
- Resolve web assets via `obs_server.get_assets_dir()` so both source and
  PyInstaller-frozen runs work. New assets need both `--add-data` separator
  variants added to the PyInstaller command.

## Pitfalls

- Runtime state is user data, not repo content: layouts at
  `~/.config/shanktuary/overlay_layout.json`, shot history beside the
  executable/source dir. Never commit machine-specific state.
- `build/`, `dist/`, `AppDir/`, and packaged archives are generated output —
  edit source in the Python modules, `src/`, or `assets/` instead.
- `.gitignore` excludes all `*.json`, `scratch/`, and `.agents/` — double
  check before assuming a JSON config file is tracked.
- Integration tests start a real threaded HTTP server on a non-default port;
  use their fixtures rather than spinning up another server in-process.
- For deterministic pressure/API tests, prefer the simulator backend over a
  physical board.
