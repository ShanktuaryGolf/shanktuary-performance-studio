# My Bag Mapping & Club Gapping Viewport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Mode 6 `[ My Bag ]` featuring interactive 14-club bag equipment configuration, performance averages aggregation (Session vs All-Time), and a visual yardage gapping step ladder.

**Architecture:** Extend `ShanktuaryApp` data model with a structured `"bag"` specification list persisted in `shanktuary_session_history.json`. Implement a dual-scope performance aggregation engine calculating carry, total, speeds, smash, launch, spin, and consistency deltas. Render a dual-pane viewport containing categorized interactive club cards on the left (Woods, Hybrids, Irons, Wedges) and a dynamic yardage gapping ladder on the right.

**Tech Stack:** Python 3, Tkinter Canvas graphics, JSON persistence, WebSockets / OBS integration.

**Spec:** [`docs/superpowers/specs/2026-08-23-bag-mapping-and-averages-design.md`](docs/superpowers/specs/2026-08-23-bag-mapping-and-averages-design.md)

## Global Constraints
- Mode pill text must be `[ My Bag ]` with clean text and NO emojis on buttons, title banners, or category headers.
- 5 distinct equipment categories: Woods & Drivers, Hybrids & Utilities, Irons, Wedges, Putter (all text-only).
- Must persist bag configurations in `shanktuary_session_history.json` with backward compatibility.
- In-canvas modal only — no secondary OS popup windows.

---

### Task 1: Bag Data Structure, Storage & Default 14-Club Factory

**Files:**
- Modify: `shanktuary_performance_studio.py:230-260,470-520`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `self.bag`, `self.init_default_bag()`, `self.get_bag_club(club_name)`, updated `self.save_session_to_file()`, `self.load_session_history()`.

- [ ] **Step 1: Write the failing test in test_studio_headless.py**
```python
def test_16_bag_data_model_and_persistence(self):
    self.assertTrue(len(self.app.bag) >= 14)
    driver = self.app.get_bag_club("Driver")
    self.assertIsNotNone(driver)
    self.assertEqual(driver.get("category"), "Woods")
```
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement bag data model, default 14-club factory, and JSON load/save in shanktuary_performance_studio.py**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 2: Bag Performance Aggregation Engine (Session vs All-Time)

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `self.get_bag_club_stats(club_name, scope="session")`, `self.calculate_bag_gapping(scope="session")`.

- [ ] **Step 1: Write the failing test for stats aggregation**
```python
def test_17_bag_performance_aggregation(self):
    stats = self.app.get_bag_club_stats("7 Iron", scope="session")
    self.assertIn("avg_carry", stats)
    self.assertIn("shot_count", stats)
```
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement stats aggregation methods with standard deviation and min/max windows**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 3: Mode 6 Top Navigation, Scope Toggle & Toolbar Layout

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `self.view_mode = 6`, `self.bag_scope = "session"`, `[ My Bag ]` pill hit testing, hotkeys `<6>` and `<b>/<B>`, 6-mode cycle.

- [ ] **Step 1: Write failing test for Mode 6 switching and hotkeys**
```python
def test_18_mode_6_navigation_and_hotkeys(self):
    self.app.set_mode(6)
    self.assertEqual(self.app.view_mode, 6)
```
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add Mode 6 pill, hotkeys, and cycle in shanktuary_performance_studio.py**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 4: Left Pane — Interactive Bag Rack & Club Cards

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `draw_my_bag_viewport()`, `self.bag_club_card_rects`, `self.bag_edit_btn_rects`.

- [ ] **Step 1: Write failing test for club card quick-selection across 5 categories (Woods, Hybrids, Irons, Wedges, Putter)**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement categorized club cards with quick selection and equipment specs**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 5: Right Pane — Visual Yardage Gapping Ladder & Consistency Card

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `_draw_bag_gapping_ladder()`, gap step callouts, gapping consistency grade.

- [ ] **Step 1: Write failing test for yardage gapping step calculations**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement dynamic vertical distance ladder and step indicators**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 6: In-Canvas Club Spec Editor Modal & Bag Operations

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Test: `scratch/test_studio_headless.py`

**Interfaces:**
- Produces: `open_club_spec_editor(club_name)`, `draw_club_spec_editor_modal()`, `save_club_specs()`, `remove_club_from_bag()`, `reorder_bag_club()`.

- [ ] **Step 1: Write failing test for modal spec editing, reordering, and club removal**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement in-canvas spec editor modal and bag operations**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 7: Comprehensive Integration & Verification

**Files:**
- Modify: `walkthrough.md`
- Test: `scratch/test_studio_headless.py`, `scratch/test_session_model.py`, `scratch/test_obs_routes.py`

- [ ] **Step 1: Run full verification test suite across all 6 modes**
- [ ] **Step 2: Update walkthrough.md documentation**
