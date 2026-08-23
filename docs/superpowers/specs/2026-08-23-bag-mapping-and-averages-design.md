# Design Specification: My Bag Mapping & Club Gapping Viewport

## 1. Overview & Purpose
Shanktuary Performance Studio provides a 6th dedicated viewport mode: **`[ My Bag ]` (Bag Mapping & Club Averages)**. This subsystem allows golfers to map out their full equipment bag (Drivers, Woods, Hybrids, Irons, Wedges), configure custom equipment specifications (Brand, Model, Loft °, Shaft), view aggregated performance averages (Carry, Total, Speeds, Smash, Launch, Spin) across Session and All-Time history scopes, and analyze distance step gapping through an interactive visual ladder.

---

## 2. Data Model & Persistence Architecture

### 2.1 Bag Configuration Structure
Saved under `"bag"` in `shanktuary_session_history.json`:

```json
{
  "bag": [
    {
      "name": "Driver",
      "category": "Woods",
      "brand": "TaylorMade",
      "model": "Qi10 LS",
      "loft_deg": 9.0,
      "shaft": "Ventus Black 6X"
    },
    {
      "name": "3 Wood",
      "category": "Woods",
      "brand": "Callaway",
      "model": "Paradym Ai Smoke",
      "loft_deg": 15.0,
      "shaft": "Fujikura Speeder NX"
    },
    {
      "name": "7 Iron",
      "category": "Irons",
      "brand": "Titleist",
      "model": "T150",
      "loft_deg": 32.0,
      "shaft": "Dynamic Gold 120"
    }
  ],
  "sessions": [...],
  "custom_clubs": [...]
}
```

### 2.2 Default Bag Initialization
If no bag is configured in storage, the app initializes the standard 14-club bag:
1. Driver (Woods, 10.5°)
2. 3 Wood (Woods, 15.0°)
3. 5 Wood (Woods, 18.0°)
4. 3 Hybrid (Hybrids, 19.0°)
5. 4 Iron (Irons, 21.0°)
6. 5 Iron (Irons, 24.0°)
7. 6 Iron (Irons, 27.0°)
8. 7 Iron (Irons, 31.0°)
9. 8 Iron (Irons, 35.0°)
10. 9 Iron (Irons, 40.0°)
11. PW (Wedges, 45.0°)
12. GW (Wedges, 50.0°)
13. SW (Wedges, 54.0°)
14. LW (Wedges, 58.0°)

### 2.3 Performance Aggregation Engine
Computes club metrics across two selectable scopes:
- **`current_session`**: Shots from `self.get_active_session()`.
- **`all_time`**: All non-excluded shots across all historical sessions in `self.sessions`.

**Calculated Metrics per Club:**
- `shot_count`: Count of non-excluded shots.
- `avg_carry`, `min_carry`, `max_carry`, `std_carry` ($\pm\text{yds}$).
- `avg_total`: Carry + Rollout distance (yds).
- `avg_ball_speed` & `avg_club_speed` (mph).
- `avg_smash`: Smash Factor efficiency ($v_{\text{ball}} / v_{\text{club}}$).
- `avg_launch`: Vertical launch angle (°).
- `avg_spin`: Total spin rate (rpm).
- `avg_offline`: Lateral offline deviation (yds L/R).

---

## 3. UI Components & Layout (Mode 6)

### 3.1 Top Toolbar
- **Title Banner:** `MY BAG MAPPING & GAPPING MATRIX`
- **Bag Summary:** Displays total clubs in bag and total shots recorded.
- **Aggregation Scope Toggle:**
  - `[ ⚡ Current Session ]` *(Default)*
  - `[ 🌐 All-Time History ]`
- **Actions:**
  - `[ ＋ Add Club to Bag ]` (Opens in-canvas modal).

### 3.2 Left Pane: Interactive Bag Rack (55% Width)
- **Categorized Sections (5 Distinct Equipment Groups - Clean Text):**
  - Woods & Drivers
  - Hybrids & Utilities
  - Irons
  - Wedges
  - Putter
- **Club Cards:**
  - **Quick-Select Hit Zone:** Single-click on card immediately selects the club as active hitting club.
  - **Active State Indicator:** Border highlighted in neon gold (`#FFEA00`) with `[ ACTIVE ]` badge.
  - **Signature Color Strip:** Color-coded accent strip on left border.
  - **Equipment Specs Line:** Brand, Model, Loft °, and Shaft type.
  - **Performance Metrics Line 1:** Carry Avg $\pm\sigma$ and Total Avg.
  - **Performance Metrics Line 2:** Ball Speed, Smash Factor, Launch Angle, Total Spin.
  - **Actions:**
    - `[ ⚙️ Edit Specs ]` Button.
    - `[ ▲ ]` / `[ ▼ ]` Reorder Buttons.

### 3.3 Right Pane: Visual Yardage Gapping Ladder (45% Width)
- **Vertical Yardage Axis:** 50y to 320y+.
- **Horizontal Club Bars:** Plotted at mean carry distance with min/max dispersion whiskers.
- **Gapping Step Indicators:**
  - 🟢 **Healthy Step** ($10\text{–}16\text{ yds}$): e.g. `+12.4y gap`
  - 🟡 **Wide Step** ($> 18\text{ yds}$): e.g. `⚠️ +22.0y gap`
  - 🔴 **Collision / Flat Spot** ($< 7\text{ yds}$): e.g. `⚠️ +2.1y collision`
- **Consistency Card:**
  - Average Bag Gap: e.g. `12.8 yds`.
  - Consistency Grade: `A (Optimal)`.

### 3.4 In-Canvas Club Spec Editor Modal
- Modal Card with:
  - Club Name (Text entry)
  - Category (Dropdown / Selector)
  - Brand & Model (Text entry)
  - Loft Degrees (Number entry)
  - Shaft Specs (Text entry)
  - Actions: `[ ✓ Save Specs ]`, `[ 🗑️ Remove from Bag ]`, `[ Cancel ]`.

---

## 4. Navigation & Keybindings
- Mode 6 top header pill: `[ My Bag ]`.
- Hotkeys: <kbd>6</kbd> and <kbd>b</kbd> / <kbd>B</kbd> switch directly to Mode 6.
- <kbd>Tab</kbd> / <kbd>m</kbd> cycles across all 6 modes (1 ➔ 2 ➔ 3 ➔ 4 ➔ 5 ➔ 6 ➔ 1).

---

## 5. Verification Plan
- **Unit Tests (`scratch/test_studio_headless.py`):**
  - `test_16_bag_data_model_and_persistence`: Verify bag load/save, default 14-club fallback, and custom equipment specs.
  - `test_17_bag_performance_aggregation`: Verify accurate stats calculation across Session vs All-Time scopes.
  - `test_18_bag_gapping_ladder_calculations`: Verify gap step deltas, overlap warnings, and consistency scoring.
  - `test_19_bag_interactive_actions`: Test quick selection, reordering, in-canvas modal editing, and club deletion.
