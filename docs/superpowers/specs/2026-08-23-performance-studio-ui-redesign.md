# Shanktuary Performance Studio: UI & Navigation Architecture Spec

**Date:** August 23, 2026  
**Status:** Approved for Implementation Planning  
**Target:** `shanktuary_performance_studio.py` & OBS/Range Ecosystem

---

## 1. Executive Summary & Problem Statement
Currently, `shanktuary_performance_studio.py` relies on engineering-style keyboard shortcuts (`[M/Tab] Mode 1, 2, 3`, `[4] 3D Range`, `[F] Fullscreen`, `[C] Clear`) displayed in a bottom legend text string, along with disconnected floating buttons. 

This redesign replaces all cryptic shortcut legends with a **consumer-grade, modern commercial golf studio navigation system** (modeled after the clarity of TrackMan TPS and Foresight FSX Pro), while preserving fast hotkeys in the background.

---

## 2. Navigation & UI Architecture

### 2.1 Unified Top App Header Bar
Height: `56px` across the top of the canvas (`#12141A` surface with subtle bottom border `#242834`).

```
+-------------------------------------------------------------------------------------------------------------------------------+
|  🏌️‍♂️ SHANKTUARY STUDIO  [🟢 Nova Ready]  |  [ 🎯 Quad Studio ] [ 📈 Performance Suite ] [ ⛳ 3D Range ]  |  [ 🏌️ 7 Iron ▼ ]  [ ⚙️ Tools ▼ ]  [ ⛶ ]  |
+-------------------------------------------------------------------------------------------------------------------------------+
```

1. **Left Branding & Live Hardware Badge:**
   * Logo text: `🏌️‍♂️ SHANKTUARY STUDIO` (Cyan bold `#00E5FF`).
   * Live Connection Pill: `🟢 Nova Ready` (`#00FF66` background badge) or `🟡 Connecting...` (`#FFEA00` pulse) with tooltip showing device IP.

2. **Center Segmented Mode Switcher:**
   * Pill-style tabs for the 3 primary practice modes:
     * **`[ 🎯 Quad Studio ]`** (Mode 1: 4-Quadrant impact delivery & trajectory analysis)
     * **`[ 📈 Performance Suite ]`** (Mode 3: Session history list, gapping matrix, and interactive dispersion map)
     * **`[ ⛳ 3D Range ]`** (Mode 4: Launches/switches to the WebGPU 3D driving range)
   * The active tab is highlighted with an illuminated cyan border and dark-teal fill (`#00E5FF33`).

3. **Right Utility Controls:**
   * **Active Club Dropdown Pill:** `[ 🏌️ 7-Iron ▼ ]` (Selects active club from Driver, 3W, 5W, 3H, 4I–9I, PW, GW, SW, LW; automatically tags all incoming shots).
   * **Studio Tools Submenu Button:** `[ ⚙️ Tools ▼ ]` (Opens the flyout menu for streaming, projector, and hardware diagnostics).
   * **Fullscreen Toggle Button:** `[ ⛶ ]` (Toggles fullscreen mode).

---

### 2.2 Dedicated `[ ⚙️ Tools ▼ ]` Submenu Flyout
Clicking **`[ ⚙️ Tools ▼ ]`** opens a polished glass popup card (`#161922` with `#00E5FF` border glow) containing clearly separated utility sections:

```
+-------------------------------------------------------------+
| ⚙️ STUDIO TOOLS & STREAMING                                 |
+-------------------------------------------------------------+
| 🎥 BROADCAST & OVERLAYS                                     |
|   • [ 🎛️ Open OBS Overlay Config (/config) ]                |
|       Opens http://localhost:9321/config.html to configure  |
|       overlay widgets (Divot, Face, Path, Spin, Tiles).     |
|   • [ 📋 Copy OBS Browser Source URL ]                      |
|       Copies http://localhost:9321/overlay.html (1080p).    |
|   • [ ⛳ Open 3D Range Browser Source ]                     |
|                                                             |
| 🎯 FLOOR MAT PROJECTION                                     |
|   • [ 🎯 Switch to Mat Divot Projector View ]               |
|   • [ 📐 Calibrate Projection Offset & Scale ]              |
|                                                             |
| 📡 NOVA HARDWARE & DIAGNOSTICS                              |
|   • Status: Connected to 192.168.40.249:2920 (mDNS)         |
|   • [ 🔄 Re-Scan / Reconnect Nova ]                         |
|                                                             |
| 📁 SESSION MANAGEMENT                                       |
|   • [ 💾 Export Session History (CSV / JSON) ]              |
|   • [ 🗑️ Clear Current Session ]                            |
+-------------------------------------------------------------+
```

---

### 2.3 High-Contrast Primary Telemetry Ribbon
Positioned immediately below the header (`58px` height):
* **Data Tiles:** `BALL SPEED`, `CLUB SPEED`, `SMASH FACTOR`, `LAUNCH ANGLE`, `TOTAL SPIN`, `CARRY`, `TOTAL`, `OFFLINE`.
* **Value Styling:** Large monospace bold text (`#FFFFFF`), with colored offline deviation badges (Cyan for straight $\le 5\text{y}$, Yellow for moderate push/pull $5\text{–}15\text{y}$, Red for severe miss $> 15\text{y}$).

---

### 2.4 Cleanup of Engineering Artifacts
* **Remove Footer Text:** Delete the raw string `[M/Tab] Mode (1: 4-Quad, 2: Divot...)`.
* **Retain Background Hotkeys:** Keyboard shortcuts (`1`, `2`, `3`, `4`, `Tab`, `F`/`F11`, `C`, `Esc`) continue to function silently without visual clutter.
* **Remove Floating Single Buttons:** The standalone `[🏔️ 3D RANGE]` and `[C] CLEAR SHOTS` buttons are cleanly integrated into the header and tools menu.

---

## 3. Implementation Interfaces & Components

### 3.1 Files Touched
1. `shanktuary_performance_studio.py`:
   * Update header rendering, segmented tab click handling, dropdown state management, and tools modal rendering.
   * Add club tracking state (`self.current_club = "7 Iron"`) and session shot tagging.
   * Connect `/config` launcher button to `webbrowser.open("http://localhost:9321/config.html")`.

---

## 4. Verification Plan
1. **Visual UI Inspection:** Launch `shanktuary_performance_studio.py`, verify that the top header, club selector, segmented tabs, and data ribbon render cleanly at multiple window resolutions and fullscreen.
2. **Tools Submenu Interaction:** Click `[ ⚙️ Tools ▼ ]` and verify all buttons:
   * Clicking `[ 🎛️ Open OBS Overlay Config (/config) ]` launches `http://localhost:9321/config.html`.
   * Clicking `[ 🎯 Switch to Mat Divot Projector View ]` switches to floor projection.
   * Clicking `[ ⛳ 3D Range ]` opens the 3D visualizer.
   * Selecting a club updates the active club tag.
3. **Session & Shot Flow:** Push mock shots via WebSocket and verify that metrics update seamlessly without UI glitching.
