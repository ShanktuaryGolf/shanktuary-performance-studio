# Walkthrough - Shanktuary Performance Studio OBS Suite & Divot Alignment System

All 4 Quadrant visual widgets from Mode 1 (Quad Studio View) + Virtual Divot Projector are now fully implemented, interactive, draggable, resizable, and calibrated for live stream overlays and floor projection!

📁 **Local Workspace Directory:** `/home/sean/sps/`

---

## 🔗 Useful URLs & Access Points

| Page / Interface | URL | Purpose |
| :--- | :--- | :--- |
| **Clean OBS Stream Overlay** | [http://localhost:9321](http://localhost:9321) | Transparent, clean broadcast overlay (no pencil icons or UI frames). |
| **Drag, Drop & Resize Canvas Editor** | [http://localhost:9321/?edit=true](http://localhost:9321/?edit=true) | Move and resize any widget, toggle visibility, and calibrate ball origin. |
| **Fullscreen Floor Projector Mode** | [http://localhost:9321/?mode=projector](http://localhost:9321/?mode=projector) | 100% pitch-black canvas for floor projectors outputting only the divot patch. |
| **Web Configurator Control Panel** | [http://localhost:9321/config](http://localhost:9321/config) | Full telemetry toggles, theme settings, and layout management. |

---

## 🌟 The 5 Visual Widgets Included

1. 🌿 `w_divot` **Virtual Divot Projector:** Rotated turf divot patch with path vector arrow, 1-click physical ball origin positioning, X/Y physical offset calibration, and rotational tilt adjustment (`-45° to +45°`).
2. 🎯 `w_face_impact` **Quad 1: Clubface Impact Location:** Scoreline impact spot (`iron_face.png`) with Heel/Toe & High/Low impact text telemetry + Distance Efficiency %.
3. 📐 `w_overhead_path` **Quad 2: Overhead Address & Path:** Overhead iron graphic (`iron_overhead.png`) with dynamic address rotation + cyan club path vector arrow (1-to-1 sign matched with Quad View).
4. 🏹 `w_side_launch` **Quad 3: Side Launch Trajectory Arc:** Side club profile (`iron_side.png`) + 2D launch angle trajectory arc + apex height.
5. 🌀 `w_spin_axis_3d` **Quad 4: 3D Spin Axis & Rating:** Dynamic Shot Quality Rating Badge (`A / B / C / D`) + Shot Title (`PULL HOOK`, `PURE DRAW`) + rotated 3D spin axis vector arrow.

---

## 🛠️ Key Features Added

* **Interactive Widget Resizing:** Click and drag the cyan `◢` grip handle in the bottom-right corner of any widget in Edit Mode to resize it to any dimensions (e.g. 960x540 for half-screen divot projection!).
* **1-Click Ball Origin Positioning:** In Edit Mode, click anywhere on the Virtual Divot canvas to set the physical ball anchor (`🎯 BALL ORIGIN`) instantly.
* **1-to-1 Rotation Matching:** Clubhead face angle and swing path vector arrows in `overlay.html` match Mode 1 (Quad View) in the desktop app 1-to-1.
* **Clean Broadcast Output:** Removed the floating pencil button for a 100% clean stream overlay in OBS Studio.

---

## 🧪 Local Test Verification Summary

```text
[+] Started OBS Overlay Server on http://localhost:9321
[+] OBS Web Configurator available at http://localhost:9321/config
Contains edit-toggle-btn?: False
Contains 1-to-1 rotate-pathDeg?: True
✓ Clean OBS Overlay Status 200 OK
```

*(Note: Per your workflow preference, all testing was performed strictly locally in `/home/sean/sps`.)*
