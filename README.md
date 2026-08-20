# ⛳ Shanktuary Performance Studio

A professional, open-source **Launch Monitor Dashboard & Performance Analytics Suite** for the **OpenLaunch Nova** launch monitor.

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-green.svg)
![OpenLaunch](https://img.shields.io/badge/Hardware-OpenLaunch_Nova-cyan.svg)

---

## 🌟 Key Features

* **Zero-Config mDNS Auto-Discovery:** Automatically discovers any OpenLaunch Nova hardware on your local network using official `_openlaunch-ws._tcp.local.` mDNS zeroconf broadcasting. No IP address setup required!
* **Mode 1 — 4-Quadrant Quad Studio Dashboard:**
  * **Top-Left (Overhead View):** Real clubhead address view (`iron_overhead.png`) with dynamic face angle rotation and Cyan swing path vector arrow.
  * **Bottom-Left (Side Elevation View):** Profile side view (`iron_side.png`) showing dynamic launch angle vector, peak height, and backspin.
  * **Top-Right (3D Spin Axis):** 3D golf ball with tilted red spin axis vector, sidespin, and shot grade badge (`Rank A–D`).
  * **Bottom-Right (Face Impact Location):** Real clubface (`iron_face.png`) with glowing red impact target ring directly on scorelines/leading edge showing **High/Low** and **Heel/Toe** displacement.
* **Mode 2 — Floor Divot Projector View:**
  * High-contrast rotated turf divot patch optimized for hitting mat floor projection.
* **Mode 3 — Performance Suite & Trajectory Comparison Dashboard:**
  * **LAST vs AVERAGE Comparison Table:** Side-by-side comparison table for 10 key metrics (Ball Speed, Launch Angle, Total Spin, Carry, Total Distance, Push/Pull, Sidespin, Descent Angle, Peak Height, Offline).
  * **Multi-Shot Overlaid Trajectory Graph:** 2D side elevation plot (0 to 350 YDS) showing parabolic flight curves for **ALL shots** in your practice session.
  * **Top-Down Shot Dispersion Target Map:** Target centerline map plotting landing markers for every shot + a **90% confidence dispersion ellipse** to visualize shot grouping.
  * **Interactive Session Shot List:** Select any historical shot from the sidebar list or click a landing dot on the dispersion map.
  * **Click-to-Inspect Quad View:** Click `[🔍 INSPECT QUAD VIEW]` to view full 4-Quadrant clubface impact & path analysis for any past shot!
  * **Draggable Sidebar Divider:** Click and drag the cyan divider line to dynamically resize the session stats sidebar.

* **Built-in OBS Studio Browser Source Overlay Server:**
  * **OBS Browser Source URL:** `http://localhost:9321` (1920x1080 transparent HUD overlay for live streaming / video capture).
  * **Interactive Web Configurator (`http://localhost:9321/config`):** Toggle switches to check/uncheck every metric, Virtual Divot Projector canvas, clubface impact ring, and theme styles with instant live sync!

### 1. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/ShanktuaryGolf/shanktuary-performance-studio.git
cd shanktuary-performance-studio
pip install -r requirements.txt
```

### 2. Running the Application

Ensure your OpenLaunch Nova device is powered on and connected to the same network (Wi-Fi or LAN), then run:

```bash
python3 shanktuary_performance_studio.py
```

* The app will automatically discover your Nova hardware via mDNS (`_openlaunch-ws._tcp.local.`) and start receiving live shot telemetry!

---

## 🎮 Keyboard & Mouse Controls

| Key / Action | Function |
| :--- | :--- |
| **`1`**, **`2`**, **`3`** | Jump directly to View Modes 1, 2, or 3 |
| **`M`** or **`Tab`** | Cycle through View Modes (1 $\rightarrow$ 2 $\rightarrow$ 3) |
| **`F`** or **`F11`** | Toggle Fullscreen Mode |
| **`C`** | Clear Session Shot History |
| **`Esc`** | Exit Application |
| **Click & Drag Line** | Resize Session Stats Sidebar in Mode 3 |
| **Click Shot / Dot** | Select any historical shot in Mode 3 |

---

## 🔧 Advanced Configuration

### Environment Variables
You can manually override device discovery or connection settings using environment variables:

```bash
# Override device IP address
export NOVA_IP=192.168.1.100

# Run Shanktuary Performance Studio
python3 shanktuary_performance_studio.py
```

### Session History Logs
All session shots are automatically saved to disk in JSON format at:
```text
shanktuary_session_history.json
```

---

## 🛠️ CLI WebSocket Logger Utility

Include a standalone CLI event listener to print raw Nova WebSocket JSON telemetry:

```bash
python3 listen_nova_events.py
```

---

## 📄 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
