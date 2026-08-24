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

- **Virtual Divot Graphics:** High-contrast turf patch + swing path vector arrow.
- **🎯 1-Click Physical Ball Origin Calibration:**
  - Click anywhere on the divot canvas to set the red `🎯 BALL ORIGIN` target anchor.
  - Adjust **X / Y Offset** shifting and **Rotational Tilt (`-45° to +45°`)** so the projected divot lines up 100% perfectly on top of your physical golf ball on your hitting mat.
- **Fullscreen Floor Projector Mode ([`http://localhost:9321/?mode=projector`](http://localhost:9321/?mode=projector)):**
  - Pitch-black background mode outputting ONLY the high-contrast divot patch for floor projectors.

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
- **Credits:** See `ATTRIBUTIONS.md` for full engine and asset credits.

---

## 🚀 Quick Start & Installation

### Running from Source
```bash
git clone https://github.com/ShanktuaryGolf/shanktuary-performance-studio.git
cd shanktuary-performance-studio
pip install -r requirements.txt
python3 shanktuary_performance_studio.py
```

### OBS & Browser Source URLs
- 🎥 **Clean OBS Browser Source:** `http://localhost:9321`
- 🎥 **Floor Projector Fullscreen Mode:** `http://localhost:9321/?mode=projector`
- ⚙️ **Web Configurator UI:** `http://localhost:9321/config` (open in your browser outside of OBS)
- ✏️ **Drag & Drop Canvas Editor:** `http://localhost:9321/?edit=true` (open in your browser outside of OBS)


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
