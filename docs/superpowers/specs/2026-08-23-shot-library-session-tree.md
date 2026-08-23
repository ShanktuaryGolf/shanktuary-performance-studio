# Shanktuary Performance Studio: Collapsible Shot Library & Session Tree Spec

## 1. Overview
The goal is to implement a commercial-grade, collapsible **Left Shot Library & Session Tree** in Shanktuary Performance Studio, drawing direct design inspiration from **OpenLaunch Nova** and **Uneekor VIEW** (`ui1.png`, `12.png`, `dataui3.png`, `dataui5.png`).

The drawer provides:
1. Multi-session lifecycle management (`+ New Session`, session switching, session naming, auto-grouping).
2. Granular club filtering (`All Clubs`, `Driver`, `7 Iron`, etc.) for targeted gapping and dispersion analysis.
3. Chronological shot card stream with timestamps, club tags, carry distance, ball speed, and shot shape badges.
4. One-click shot inspection across all studio view modes (4-Quadrant Delivery, Dispersion, Tables, Big Numbers).
5. Seamless collapsible state (`[ ◀ ]` / `[ ▶ ]` or `[ ☰ ]`) with animated/dynamic main viewport layout reflow.

---

## 2. Architecture & Data Model

### A. Session Data Structure
```python
{
    "id": "sess_20260823_104400",
    "name": "Session 1 - 7 Iron Practice",
    "created_at": "2026-08-23 10:44:00",
    "target_club": "7 Iron", # Optional default club
    "shots": [
        # List of full telemetry shot dicts from Nova / Open Golf Coach
    ]
}
```

### B. App State Integration in `ShanktuaryApp`
* `self.sessions`: List of session dicts. Defaults to at least one active session on startup.
* `self.active_session_idx`: Integer index pointing to active session in `self.sessions`.
* `self.selected_shot_idx`: Integer index pointing to currently inspected shot in `self.active_session.shots` (-1 for latest live shot).
* `self.club_filter`: String (`"ALL"` or specific club like `"7 Iron"`).
* `self.sidebar_collapsed`: Boolean (True = collapsed to thin mini-bar/hidden, False = open 260px drawer).
* `self.sidebar_width`: Integer (e.g., 260px).
* `self.sidebar_tab`: String (`"SHOTS"` or `"SESSIONS"`).

---

## 3. UI Layout & Visual Specifications

```
+-------------------------------------------------------------------------------------------------------------------------------+
| [ ☰ ] 🏌️‍♂️ SHANKTUARY STUDIO   🟢 Nova Ready  |  [ 🎯 Quad Studio ] [ 📈 Performance Suite ] [ ⛳ 3D Range ]  |  [ 🏌️ 7 Iron ▼ ]  |
+----------------------+--------------------------------------------------------------------------------------------------------+
| 📁 SHOT LIBRARY [ ◀ ]|                                                                                                        |
| [ + NEW SESSION ]    |                                                                                                        |
| -------------------- |                                                                                                        |
| Active: Session 1    |                                       MAIN VIEWPORT                                                    |
| [ 7 Iron ▼ ] (Filter)|                               (Modes 1, 2, 3, etc. dynamically reflowed)                              |
| -------------------- |                                                                                                        |
| #3: 172.5y (7I)      |                                                                                                        |
|  122.4mph | Baby Draw|                                                                                                        |
|  10:46 AM            |                                                                                                        |
|                      |                                                                                                        |
| #2: 168.1y (7I)      |                                                                                                        |
|  118.2mph | Straight |                                                                                                        |
|  10:45 AM            |                                                                                                        |
|                      |                                                                                                        |
| #1: 164.0y (7I)      |                                                                                                        |
|  116.0mph | Fade     |                                                                                                        |
|  10:44 AM            |                                                                                                        |
|                      |                                                                                                        |
| [ 🗑️ Clear Session ] |                                                                                                        |
+----------------------+--------------------------------------------------------------------------------------------------------+
|  BALL SPEED     CLUB SPEED     SMASH      LAUNCH ANG     TOTAL SPIN     CARRY        TOTAL       OFFLINE (YDS)                    |
|   122.4 mph      88.7 mph      1.38         18.5°        6,204 rpm    172.5 yds    178.2 yds     2.1 R [Straight]                 |
+-------------------------------------------------------------------------------------------------------------------------------+
```

### Visual Aesthetics & Hierarchy:
1. **Drawer Background:** Deep Obsidian Slate (`#12141A`) with subtle border divider (`#232733`).
2. **Session Header Banner:**
   * Displays Active Session Title with edit/new session icon.
   * `[ + New Session ]` button with cyan accent outline.
3. **Filter Ribbon:**
   * Compact club pill filter: `[ All Clubs ▼ ]` allowing instantaneous filtering of the shot list.
4. **Shot Cards:**
   * Card surface: `#181B24` with hover highlight `#222634`.
   * Selected state: High-contrast gold accent `#FFEA00` border with glowing background `#2C2B10`.
   * Card details:
     * Top line: `#N  [Club Tag]  Carry yds` (Consolas 10 bold)
     * Sub line: `Speed mph  •  Shot Shape` (e.g. `122.4 mph • Baby Draw`)
     * Timestamp: `10:46 AM` in muted text (`#70788C`).
5. **Drawer Toggle:**
   * Header hamburger `[ ☰ ]` or drawer collapse button `[ ◀ ]` at top right of the drawer.
   * When collapsed, collapses to a sleek 36px icon strip or zero-width with quick toggle icon.
6. **Dynamic Main Canvas Reflow:**
   * When open, `workspace_x_start = sidebar_w`, width = `w - sidebar_w`. All quadrant dividers, dispersion charts, and data tables automatically adapt to the available width.
