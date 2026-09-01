# Shanktuary Performance Studio

> **Ultimate Launch Monitor & Performance Suite for OpenLaunch Nova & OpenGolfCoach**  
> *Featuring Live 4-Quadrant Visual Telemetry, High-Contrast Quad Studio Views, Floor Divot Projection, Session Dispersion Analysis, and Built-in OBS Stream Overlays.*

---

## 🌟 Complete Feature Overview

Shanktuary Performance Studio is a comprehensive launch monitor visualization, performance analysis, and streaming overlay system designed specifically for **OpenLaunch Nova** and **OpenGolfCoach** compatible launch monitors.

### 📡 1. Zero-Config mDNS Auto-Discovery
- **Automatic Connection:** Connects automatically to your Nova hardware over Wi-Fi/LAN via mDNS (`_openlaunch-ws._tcp.local.`) without typing IP addresses or port numbers.

---

### 🎯 2. Mode 1: 4-Quadrant Quad Studio View
*(Press `[1]` or `[Tab]` to switch to Mode 1)*

- ↖️ **Top-Left — Overhead Address & Path:** Overhead iron graphic (`iron_overhead.png`) with dynamic address face angle rotation (`Open` / `Closed`) + cyan club path vector arrow (`In-To-Out` / `Out-To-In`).
- ↗️ **Top-Right — 3D Spin Axis & Shot Quality Rating:** Live Shot Quality Rating Badge (`A / B / C / D`) + Shot Title (`PULL HOOK`, `PURE DRAW`) + rotated 3D spin axis vector arrow + total spin.
- ↙️ **Bottom-Left — Side Launch Trajectory Arc:** Side club profile (`iron_side.png`) + 2D launch angle trajectory arc + apex height & descent angle.
- ↘️ **Bottom-Right — Clubface Impact Location:** Real-time scoreline impact mapping directly on iron face graphics (`iron_face.png`) displaying exact **Heel/Toe (mm)** and **High/Low (mm)** impact measurements + **Distance Efficiency %**.

---

### 🌿 3. Mode 2: Floor Divot Projector View & Alignment
*(Press `[1]` / `[2]` or `[Tab]` to switch to Mode 2)*

- **Virtual Divot Graphics:** Torn turf scar oriented to the measured club path.
  The divot's shape is presentational and constant — the Nova measures club
  path direction, not divot depth or size — so only its rotation reflects data.
- **🎯 1-Click Physical Ball Origin Calibration:**
  - Click anywhere on the divot canvas to set the red `🎯 BALL ORIGIN` target anchor.
  - Adjust **X / Y Offset** shifting and **Rotational Tilt (`-45° to +45°`)** so the projected divot lines up 100% perfectly on top of your physical golf ball on your hitting mat.
  - The divot begins **at** the ball and runs toward the target, matching a real
    iron strike (ball first, then turf).
- **Two independent floor-projection surfaces**, so each can be its own browser
  window aimed at its own part of the mat:
  - [`/divot`](http://localhost:9321/divot) — fullscreen divot target, nothing else.
  - [`/tiles`](http://localhost:9321/tiles) — the metric cards you placed in the
    editor, without the divot.
  - `/?mode=projector` keeps your whole layout on one surface, and `/projector`
    is kept as an alias of `/divot`.
  - Colours invert automatically in projector mode: a projector cannot emit
    black, so cards become bright with dark text.
- **Widget rotation:** in the canvas editor, click a widget to select it, then
  rotate it from the toolbar. A golfer at address views the mat from the side,
  so cards often need turning once projected onto the floor.

---

### 📊 4. Mode 3: Performance & Trajectory Dispersion Suite
*(Press `[3]` or `[Tab]` to switch to Mode 3)*

- **Overlaid 2D Flight Trajectories:** Side-view flight curves for ALL shots hit during your session (0–350 YDS).
- **Top-Down Landing Dispersion Map:** Shows landing spots + 90% confidence shot grouping ellipse.
- **LAST vs SESSION AVERAGE Table:** Side-by-side telemetry comparison table for 10 live metrics (Ball Speed, Club Speed, Carry, Total, Smash, Launch Angle, Push/Pull, Total Spin, Spin Axis, Offline).
- **Click-to-Inspect Quad View:** Click any shot in your session history list or landing dot on the map to inspect its full 4-Quadrant clubface impact & path analysis!

---

### 🎥 5. OBS Stream Overlay & Web Configurator
*(Runs automatically on `http://localhost:9321`)*

- **Built-in HTTP + WebSocket Server (Port 9321):** Automatic background server for transparent OBS Studio Browser Source overlays.
- **Web Configurator Control Panel ([`http://localhost:9321/config`](http://localhost:9321/config)):** Live control panel for toggling telemetry cards, switching themes, and managing saved layout presets.
- **Interactive Drag & Drop Canvas ([`http://localhost:9321/?edit=true`](http://localhost:9321/?edit=true)):** Arrange any widget on a 1920x1080 canvas with 40px grid snapping.
- **Corner Resize Grip Handles (`◢`):** Click and drag the bottom-right corner of ANY widget container to resize it to any dimensions (e.g. half-screen or full-screen divots!).
- **Fluid Vector Scaling:** All graphics scale 100% crisp and clear at any size.
- **Pristine Broadcast Output:** Clean broadcast canvas with zero stream icons or pencil overlays.

---

### 🏔️ 6. WebGPU 3D Driving Range
*(Available at [`http://localhost:9321/range`](http://localhost:9321/range) or by pressing `[4]`)*

- **Immersive 3D Physics:** Powered by the Minigames physics trajectory engine for realistic ball flight rendering.
- **Dynamic Camera System:** Press `[V]` to cycle between multiple camera views (Follow, TV Tower, Behind).
- **Credits:** See the License & Credits section below for engine and asset credits.

---

## 🚀 Quick Start & Installation

### Running from Source
```bash
git clone https://github.com/ShanktuaryGolf/shanktuary-performance-studio.git
cd shanktuary-performance-studio
pip install -r requirements.txt
python3 shanktuary_app.py
```

`shanktuary_app.py` is the redesigned production desktop entry point. It starts the normal Nova websocket worker and OBS/browser server, then applies the desktop UI layer in `src/ui/` over the production implementation in `shanktuary_performance_studio.py`. Hardware, OpenGolfCoach processing, aim calibration, persistence, pressure capture, and browser/API behavior remain owned by the production app.

For desktop visual conventions, palette roles, data-credibility rules, and maintainership guidance, see [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).

### OBS & Browser Source URLs
- 🎥 **Clean OBS Browser Source:** `http://localhost:9321`
- 🌿 **Floor Projector — Divot only:** `http://localhost:9321/divot`
- 📊 **Floor Projector — Metric tiles only:** `http://localhost:9321/tiles`
- 🎥 **Floor Projector — Whole layout:** `http://localhost:9321/?mode=projector`
- ⚙️ **Web Configurator UI:** `http://localhost:9321/config` (open in your browser outside of OBS)
- ✏️ **Drag & Drop Canvas Editor:** `http://localhost:9321/?edit=true` (open in your browser outside of OBS)
- 🏔️ **WebGPU 3D Driving Range:** `http://localhost:9321/range`

All of these are also reachable from the desktop app under **Tools**.

### Desktop UI maintenance

The stable desktop seam is `src/ui/desktop.py`, and new desktop styling should use roles from `src/ui/tokens.py`. The approved iterative renderer snapshot is isolated under `src/ui/_legacy/`; it is implementation detail, not a public API. As views are revisited, those renderers can be consolidated behind `ShanktuaryDesktopApp` without changing production data or hardware code.

Before merging desktop changes, run:

```bash
python -m pytest -q
```

The GitHub Actions workflow runs the suite before packaging Linux, Windows, and macOS builds.

---

## ⌨️ Desktop Hotkeys & Controls
- `[M]` / `[Tab]` — Switch Display Mode (1: 4-Quad Studio, 2: Floor Divot Projector, 3: Performance Suite)
- `[4]` — Launch WebGPU 3D Driving Range
- `[F]` — Toggle Fullscreen
- `[C]` — Clear Session Shot History
- `[Esc]` — Exit App / Fullscreen

---

## 📄 License & Credits
Developed by **Shanktuary Golf** for OpenLaunch Nova & OpenGolfCoach systems.  
Distributed under the MIT License.

### 3D asset attribution

The WebGPU 3D Driving Range ships the following models under
**CC-BY-4.0**, which requires that credit stay with the distributed work:

* **"Pine tree"** — [Andriy Shekh](https://sketchfab.com/sheh5262) · [source](https://sketchfab.com/3d-models/pine-tree-e52769d653cd4e52a4acff3041961e65)
* **"Wooden Sign With Roof"** — [KenVeel](https://sketchfab.com/KenVeel) · [source](https://sketchfab.com/3d-models/wooden-sign-with-roof-d3c14c892ce54564b7fde91c73896ca3)

Rendering uses [three.js](https://threejs.org) (MIT).
