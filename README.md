# Shanktuary Performance Studio

> **Ultimate Golf Launch Monitor Suite for OpenLaunch Nova & OpenGolfCoach**
> *Featuring Live 4-Quadrant Visual Telemetry, High-Contrast Studio Views, Floor Divot Projection, and Built-in OBS Browser Source Server.*

---

## 🌟 Overview & Feature Highlights

Shanktuary Performance Studio is a high-performance launch monitor visualization suite and streaming overlay system designed specifically for **OpenLaunch Nova** and **OpenGolfCoach** compatible launch monitors.

### 🎨 1. Extreme Customizability & Drag & Drop Editor
- **Web Configurator UI ([`http://localhost:9321/config`](http://localhost:9321/config)):** Live control panel to toggle metric cards, adjust themes, and tune display settings.
- **Interactive Drag & Drop Canvas ([`http://localhost:9321/?edit=true`](http://localhost:9321/?edit=true)):** Arrange your stream overlay on a 1920x1080 canvas with 40px grid snapping. Move any widget anywhere on screen.

### 📐 2. Dynamic Canvas Size & Resizable Widgets
- **Corner Resize Grip Handle (`◢`):** Click and drag the bottom-right corner of ANY widget to resize it to your preferred dimensions.
- **Fluid Auto-Scaling HTML5 Canvases:** All graphics (turf divots, clubface impact rings, overhead address vectors, launch arcs, 3D spin axis vectors) scale up 100% crisp and clear regardless of container size (e.g. expand the Virtual Divot to half-screen or full-screen!).

### 🎯 3. Complete 5 Visual Widgets Suite
1. 🌿 **Virtual Divot Projector (`w_divot`):** Rotated turf divot patch with swing path vector arrow, physical ball origin anchor (`🎯 BALL ORIGIN`), X/Y physical offset calibration, and rotational tilt adjustment (`-45° to +45°`).
2. 🎯 **Quad 1: Clubface Impact Location (`w_face_impact`):** Scoreline impact spot (`iron_face.png`) with Heel/Toe & High/Low text telemetry + Distance Efficiency %.
3. 📐 **Quad 2: Overhead Address & Path (`w_overhead_path`):** Overhead iron graphic (`iron_overhead.png`) with dynamic address rotation + cyan club path vector arrow (1-to-1 sign matched with Quad View).
4. 🏹 **Quad 3: Side Launch Trajectory Arc (`w_side_launch`):** Side club profile (`iron_side.png`) + 2D launch angle trajectory arc + apex height.
5. 🌀 **Quad 4: 3D Spin Axis & Rating (`w_spin_axis_3d`):** Dynamic Shot Quality Rating Badge (`A / B / C / D`) + Shot Title (`PULL HOOK`, `PURE DRAW`) + rotated 3D spin axis vector arrow.

### 🎥 4. Floor Projection Support & Fullscreen Mat Mode
- **Fullscreen Floor Projector Mode ([`http://localhost:9321/?mode=projector`](http://localhost:9321/?mode=projector)):** Pitch-black background mode outputting ONLY the high-contrast divot patch and target line for floor projectors.
- **Physical Ball Alignment Calibration:** 1-click canvas positioning, X/Y physical offset shifting, and rotational tilt calibration so the projected divot lines up 100% perfectly on top of your physical golf ball on the mat.

### 📡 5. Automatic OBS Scene Integration
- **Built-in HTTP + WebSocket Server (Port 9321):** Runs automatically in a background thread when Shanktuary launches.
- **Instant OBS Browser Source Setup:** Add `http://localhost:9321` as an OBS Browser Source for a clean, transparent, real-time stream overlay.

---

## 🚀 Quick Start

### Running from Source
```bash
git clone https://github.com/ShanktuaryGolf/shanktuary-performance-studio.git
cd shanktuary-performance-studio
pip install -r requirements.txt
python3 shanktuary_performance_studio.py
```

### OBS & Browser Source URLs
- 🎥 **Clean OBS Browser Source:** `http://localhost:9321`
- ✏️ **Drag & Drop Canvas Editor:** `http://localhost:9321/?edit=true`
- 🎥 **Floor Projector Fullscreen Mode:** `http://localhost:9321/?mode=projector`
- ⚙️ **Web Configurator UI:** `http://localhost:9321/config`

---

## ⌨️ Desktop Hotkeys & Controls
- `[M]` / `[Tab]` — Switch Display Mode (1: 4-Quad Studio, 2: Floor Divot Projector, 3: Performance Suite)
- `[F]` — Toggle Fullscreen
- `[C]` — Clear Session Shot History
- `[Esc]` — Exit App / Fullscreen

---

## 📄 License & Credits
Developed by **Shanktuary Golf** for OpenLaunch Nova & OpenGolfCoach systems.
Distributed under the MIT License.
