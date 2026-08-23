# Shanktuary Performance Studio UI & Navigation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul `shanktuary_performance_studio.py` to replace engineering keyboard legends with a commercial-grade top header navigation bar, segmented mode pills, active club selector, telemetry ribbon, and a dedicated `[ ⚙️ Tools ▼ ]` flyout menu including the `/config` OBS widget manager.

**Architecture:** A unified Tkinter desktop interface with state-driven segmented tabs (`Quad Studio`, `Performance Suite`, `3D Range`, `Divot Floor`), active club context (`Driver` through `LW`), and an interactive flyout dialog for broadcasting, mat projection, and device diagnostics.

**Tech Stack:** Python 3, Tkinter, Pillow (`PIL`), WebSockets, mDNS/Zeroconf.

**Spec:** `docs/superpowers/specs/2026-08-23-performance-studio-ui-redesign.md`

## Global Constraints
- Do NOT remove keyboard shortcuts; keep them silently active in the background (`1`, `2`, `3`, `4`, `Tab`, `F`, `C`, `Esc`).
- The top header must dynamically adapt to window resizing and fullscreen.
- The `[ ⚙️ Tools ▼ ]` menu must include direct 1-click launch for `/config` (`http://localhost:9321/config.html`), copy OBS overlay URL, floor projector, and Nova status.
- All incoming shots must be tagged with the currently selected club.

---

### Task 1: Header Navigation & Mode Switcher Architecture

**Files:**
- Modify: `shanktuary_performance_studio.py`

**Interfaces:**
- Consumes: `self.view_mode`, `self.session_shots`, `self.current_shot`
- Produces: `draw_top_header()`, `handle_header_clicks()`, `set_mode(mode_id)`

- [ ] **Step 1: Define Club List & Header State in `PerformanceStudioApp.__init__`**
```python
self.clubs = ["Driver", "3 Wood", "5 Wood", "3 Hybrid", "4 Iron", "5 Iron", "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW"]
self.current_club = "7 Iron"
self.show_tools_menu = False
self.show_club_menu = False
self.header_height = 56
self.mode_pill_rects = {}
self.club_btn_rect = None
self.tools_btn_rect = None
self.fullscreen_btn_rect = None
self.tools_menu_rects = {}
self.club_menu_rects = {}
```

- [ ] **Step 2: Implement `draw_top_header()`**
Render branding, `🟢 Nova Ready` badge, segmented mode switcher pills (`[ 🎯 Quad Studio ]`, `[ 📈 Performance Suite ]`, `[ ⛳ 3D Range ]`), club selector pill `[ 🏌️ 7 Iron ▼ ]`, tools button `[ ⚙️ Tools ▼ ]`, and fullscreen button `[ ⛶ ]`.

- [ ] **Step 3: Implement Mouse Hit-Testing for Header Buttons & Dropdowns in `handle_mouse_press()`**
Add click handlers for mode pills, club selector toggle, and tools flyout toggle.

---

### Task 2: Studio Tools Flyout Menu & `/config` OBS Integration

**Files:**
- Modify: `shanktuary_performance_studio.py`

**Interfaces:**
- Consumes: `self.show_tools_menu`, `obs_server.OBS_PORT`
- Produces: `draw_tools_flyout_menu()`, `handle_tools_menu_click(action)`

- [ ] **Step 1: Implement `draw_tools_flyout_menu()`**
Draw dark glass flyout panel with sections:
1. 🎥 **Broadcast & Overlays:**
   - Button: `[ 🎛️ Open OBS Overlay Config (/config) ]` -> `webbrowser.open(f"http://localhost:{OBS_PORT}/config.html")`
   - Button: `[ 📋 Copy OBS Browser Source URL ]` -> copies `f"http://localhost:{OBS_PORT}/overlay.html"` to clipboard.
   - Button: `[ ⛳ Open 3D Range Source ]` -> `webbrowser.open(f"http://localhost:{OBS_PORT}/range")`
2. 🎯 **Floor Mat Projection:**
   - Button: `[ 🎯 Switch to Mat Divot Projector View ]` -> switches to Mode 2.
3. 📡 **Nova Hardware & Diagnostics:**
   - Shows connection status and host IP.
4. 📁 **Session Management:**
   - Button: `[ 🗑️ Clear Current Session ]`

- [ ] **Step 2: Implement Click Actions & Clipboard Support**
Handle clicks on the flyout options and dismiss the menu on outside click.

---

### Task 3: Club Selector Dropdown & Shot Tagging

**Files:**
- Modify: `shanktuary_performance_studio.py`

**Interfaces:**
- Consumes: `self.show_club_menu`, `self.clubs`
- Produces: `draw_club_dropdown()`, `select_club(club_name)`

- [ ] **Step 1: Implement `draw_club_dropdown()`**
Render a scrollable/grid dropdown card with all 14 clubs when `self.show_club_menu` is active.

- [ ] **Step 2: Tag Incoming Shots with Active Club**
In `poll_queue()`, attach `msg["club"] = self.current_club` before appending to `self.session_shots`.

---

### Task 4: UI Cleanup & Verification

**Files:**
- Modify: `shanktuary_performance_studio.py`

- [ ] **Step 1: Remove Bottom Debug Footer String**
Delete `[M/Tab] Mode (1: 4-Quad...)` and adjust canvas vertical heights for edge-to-edge drawing.

- [ ] **Step 2: Verify All Interactions**
Test mode switching, `/config` launching, club selection, and live telemetry rendering.
