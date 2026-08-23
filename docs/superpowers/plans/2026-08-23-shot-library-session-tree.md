# Collapsible Left Shot Library & Session Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a collapsible Left Shot Library & Session Tree in `shanktuary_performance_studio.py` inspired by OpenLaunch Nova and Uneekor VIEW, supporting multi-session tracking, club filtering, rich shot cards, and instant shot inspection.

**Architecture:** Extend `ShanktuaryApp` with a structured `SessionManager` state model holding multiple sessions and club filters. Create a left drawer renderer (`draw_left_sidebar`) with collapsible states (`sidebar_collapsed`), session switcher, club filter bar, and interactive shot cards. Update canvas layout calculations across all studio modes to dynamically offset by the sidebar width.

**Tech Stack:** Python 3.10+, Tkinter, Pillow (PIL), JSON session persistence.

**Spec:** `docs/superpowers/specs/2026-08-23-shot-library-session-tree.md`

## Global Constraints
- Pure Python & standard Tkinter canvas operations without heavy external GUI dependencies.
- Dark Obsidian Studio theme palette (`#101114`, `#12141A`, `#181B24`, `#222634`, `#00E5FF`, `#FFEA00`, `#00FF66`, `#FF4081`).
- All existing keyboard shortcuts (`1`, `2`, `3`, `4`, `Tab`, `f`/`F11`, `c`/`C`, `Esc`) and WebSocket streaming must remain intact.

---

### Task 1: Multi-Session & Shot Filtering Data Model

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_session_model.py`

**Interfaces:**
- Consumes: Raw Open Golf Coach JSON telemetry payloads from `websocket_worker` via `shot_queue`.
- Produces: `Session` objects with `id`, `name`, `created_at`, `shots`; filter helper `get_filtered_shots(club_filter=None)`.

- [ ] **Step 1: Write test for session data model & filtering**
- [ ] **Step 2: Implement session management methods in `ShanktuaryApp`** (`create_new_session`, `switch_session`, `add_shot_to_session`, `get_active_session`, `get_filtered_shots`, `delete_active_session`).
- [ ] **Step 3: Run test to verify session logic passes**

---

### Task 2: Collapsible Sidebar Shell & Workspace Reflow

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_sidebar_reflow.py`

**Interfaces:**
- Consumes: `self.sidebar_collapsed`, `self.sidebar_width` (260px open, 0px / 36px collapsed).
- Produces: `offset_x` parameter and available width `avail_w` passed to `draw_4_quadrant_studio`, `draw_performance_suite`, and `draw_top_metric_toolbar`.

- [ ] **Step 1: Add hamburger `[ ☰ ]` toggle button to header and `[ ◀ ]` drawer collapse button**
- [ ] **Step 2: Update workspace calculations so all views shift right by `sidebar_w` when expanded**
- [ ] **Step 3: Verify workspace bounds adjust cleanly when toggling collapse**

---

### Task 3: Session Header & Club Filter Dropdown

**Files:**
- Modify: `shanktuary_performance_studio.py`

**Interfaces:**
- Consumes: `self.sessions`, `self.active_session_idx`, `self.club_filter`.
- Produces: Interactive header buttons for `[ + New Session ]`, Session Selector dropdown, and `[ Filter: Club ▼ ]` pill.

- [ ] **Step 1: Implement `draw_sidebar_session_header` with session title and `[ + ]` new session button**
- [ ] **Step 2: Implement club filter selector chip in sidebar (`All Clubs`, `Driver`, `7 Iron`, etc.)**
- [ ] **Step 3: Add click handlers for session switching and filter toggling**

---

### Task 4: Rich Chronological Shot Cards & Click-to-Inspect

**Files:**
- Modify: `shanktuary_performance_studio.py`

**Interfaces:**
- Consumes: Filtered shot list from active session.
- Produces: Clickable shot cards with shot number, timestamp, club pill, carry distance, ball speed, and shape tag. Sets `self.selected_shot_index`.

- [ ] **Step 1: Implement `draw_sidebar_shot_cards` rendering each shot as a styled glass tile**
- [ ] **Step 2: Add hover highlighting and active selection border (`#FFEA00`)**
- [ ] **Step 3: Wire click event to select shot and instantly refresh the 4-quadrant and performance suite views**

---

### Task 5: Integration & Verification

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/verify_complete_studio.py`

- [ ] **Step 1: Run comprehensive UI test script validating multi-session creation, shot ingestion, club filtering, and mode reflow**
- [ ] **Step 2: Test edge cases (empty session, 50+ shots with pagination/scrolling, all-clubs vs single-club filter)**
- [ ] **Step 3: Update walkthrough artifact with detailed usage instructions**
