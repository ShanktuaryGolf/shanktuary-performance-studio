# Copilot instructions

## Project overview

Shanktuary Performance Studio is a Python/Tkinter desktop application for OpenLaunch Nova launch-monitor telemetry. The main process in `shanktuary_performance_studio.py` starts the GUI, a background Nova WebSocket client, and the OBS/browser server. `obs_server.py` serves the browser UI and static assets on port `9321`, exposes JSON APIs, and broadcasts shot and pressure events to WebSocket clients.

The browser-facing surfaces are under `assets/`: `overlay.html` is the OBS/telemetry view, `config.html` is the layout configurator, and `range/` contains the Three.js/WebGPU driving range and its physics, camera, renderer, and WebSocket code. The desktop client receives Nova JSON `shot` messages and forwards them through the shared `obs_server.obs_state`.

The pressure subsystem is a separate, importable Python package under `src/`. Hardware backends produce `SensorReading` values; processing computes center of pressure, torque, swing phase, and shot-synchronized frames. `obs_server.PressureManager` owns the backend and worker thread, optionally uses the simulator, and publishes pressure frames at roughly 30 Hz. Keep the pressure frame dictionary/schema compatible with the browser consumers and API tests.

## Commands

Install runtime and test dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run the desktop application (starts the GUI and localhost server):

```bash
python3 shanktuary_performance_studio.py
```

Run the Nova event listener directly when diagnosing the device WebSocket:

```bash
python3 listen_nova_events.py
```

Run the complete test suite:

```bash
python3 -m pytest tests/ -v
```

Run one test module or one test:

```bash
python3 -m pytest tests/test_pressure_cop.py -v
python3 -m pytest tests/test_pressure_cop.py::TestPressureCOP::test_centered_load -v
```

There is no repository lint configuration or lint command. Release builds use PyInstaller as shown in `.github/workflows/build-releases.yml`:

```bash
pyinstaller --noconfirm --onedir --windowed --add-data "assets:assets" shanktuary_performance_studio.py  # Linux/macOS
pyinstaller --noconfirm --onedir --windowed --add-data "assets;assets" shanktuary_performance_studio.py  # Windows
```

## Repository conventions

- Preserve the native Nova payload when forwarding shots. Normalize or derive display values at the UI boundary rather than changing the incoming event shape unexpectedly.
- Use `obs_state.push_shot()` and `obs_state.broadcast()` for server state and browser updates; do not create a second event bus. The server's WebSocket is a simple JSON message protocol with `init`, `shot`, `pressure`, `shot_pressure`, and `layout_update` message types.
- Keep HTTP API behavior stable. Important routes include `/api/shot`, `/api/layout`, `/api/pressure/status`, `/api/pressure/shot`, `/api/pressure/tare`, `/api/pressure/simulator`, and `/api/pressure/pin`. Use the existing JSON response/error format.
- Put reusable hardware and biomechanics logic in `src/hardware/pressure` or `src/processing/pressure`, and expose public symbols through the corresponding `__init__.py` files. Keep device I/O in backends and calculations in processing modules.
- Pressure timestamps are monotonic sensor timestamps; shot capture uses an impact-centered pre/post window. Keep `raw_cells`, `phase`, CoP percentages, and relative timing fields intact when extending synchronized frames.
- Tests use both `pytest` functions/fixtures and `unittest.TestCase`; run them through pytest. Integration tests start the threaded HTTP server and use a non-default port where needed.
- Resolve web assets through `obs_server.get_assets_dir()` so both source runs and PyInstaller-frozen runs work. When adding an asset, ensure the PyInstaller `--add-data` bundle includes it.
- Runtime layout/session state is user data: layouts are stored at `~/.config/shanktuary/overlay_layout.json`, and shot history is written beside the executable/source data directory. Do not commit machine-specific state.
- Treat `build/`, `dist/`, `AppDir/`, packaged archives, and other generated binaries as build output. Make source changes in the Python modules, `src/`, or `assets/`, not in copied bundled files.
- Follow the repository workflow guidance in `markdowns/AGENTS.md` when it applies, including the Superpowers startup workflow.
