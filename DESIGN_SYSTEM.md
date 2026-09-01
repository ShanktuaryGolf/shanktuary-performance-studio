# Shanktuary Desktop Design System

This document is the durable visual and implementation guide for the Shanktuary Performance Studio desktop app.

## Architecture

The production data/hardware implementation remains in `shanktuary_performance_studio.py`.
The redesigned desktop entry point is `shanktuary_app.py`, which instantiates `src.ui.ShanktuaryDesktopApp`.

The UI layer deliberately subclasses the production app instead of copying launch-monitor, persistence, OpenGolfCoach, aim-calibration, pressure, or browser-server logic. This keeps future production fixes available to the redesigned desktop automatically.

Public UI files:

- `src/ui/desktop.py` — production desktop adapter and interaction seam
- `src/ui/tokens.py` — approved palette roles
- `DESIGN_SYSTEM.md` — this guide
- `assets/shanktuary_shield.png` — app/header icon
- `assets/shanktuary_lockup.png` — approved gold brand lockup source

`src/ui/_legacy/` contains the frozen renderer snapshot produced during the iterative redesign. It is private implementation detail. New product code should **not** import those versioned files directly. Consolidate them behind the stable methods in `ShanktuaryDesktopApp` as those views are naturally revisited.

## Brand direction

Shanktuary is a premium golf-performance product: technical, modern, calm, and data-forward.

Avoid church/sanctuary imagery, crosses, heraldry, fantasy styling, neon/gamer effects, electric blue, loud orange, excessive glow, and decorative cards with no information hierarchy.

## Color system

Use roles from `src/ui/tokens.py` rather than choosing new colors ad hoc.

| Role | Hex | Use |
| --- | --- | --- |
| Antique Gold | `#D4A24F` | current, active, selected, hero metric, primary action |
| Light Gold | `#E3BC70` | active icons and small high-contrast highlights |
| Core Teal | `#32979A` | supporting analytical accent |
| Teal Line | `#58B7B4` | paths, chart strokes, confidence geometry |
| Teal Text | `#78C4C1` | analytical labels and takeaways |
| Soft Teal | `#698E96` | secondary analytical detail |
| Page Navy | `#0A2029` | general workspace material |
| Rail Navy | `#081923` | persistent navigation |
| Sidebar Navy | `#091B24` | Recent Shots drawer |
| Surface | `#0D2731` | local grouping surface |
| Raised Surface | `#15333D` | selected/raised state |
| Deep Teal | `#173B42` | section bands / structural emphasis |
| Hairline | `#2A4C55` | separators and quiet borders |
| Guide | `#456D76` | targets/reference lines |
| Primary Text | `#F3F6FA` | titles and primary values |
| Secondary Text | `#B3BEC2` | labels/context |
| Muted Text | `#70868C` | units/captions/unavailable |
| Success | `#39A879` | true ready/success state only |
| Danger | `#E34A4A` | true error/danger state only |

### Color-role rules

1. **Gold = current / primary / active.** Do not use it as generic decoration.
2. **Teal = analysis / data / geometry.** Use it for paths, charts, target geometry and technical labels.
3. **White = structure.** Major headings and primary values generally stay white.
4. **Slate = context.** Units, captions, inactive controls and historical points stay muted.
5. **Green/red are semantic only.** They should communicate success or danger, not brand personality.
6. Do not reintroduce electric blue (`#1E6CFF`, `#40A3FF`, `#78BAFF`) or loud orange (`#F47A32`) into redesigned desktop UI.
7. Prefer one composed workspace with spacing and hairlines over a grid of unnecessary cards.

## Navigation hierarchy

**SESSION**
- Shot
- Club
- Table
- Numbers

**PRACTICE**
- Range

**TOOLS**
- Dispersion
- Bag
- Fit
- Lab
- Setup

Persistent shell behavior:

- active nav = gold left rail, light-gold icon, white label
- inactive nav = cool teal/slate
- selected Recent Shot = raised navy/teal with gold current marker
- New Session = dark outlined gold `+`, not a solid gold block
- collapsed Recent Shots uses a dedicated 28px gutter; never overlap the nav
- header uses the standalone S icon, gold SHANKTUARY wordmark, live `PERFORMANCE GOLF STUDIO` text, and faint full-width topo contours

## Page guidance

### Shot

Reading order is **RESULT → SHAPE → CAUSE**.

Top-level metrics include Carry, Total, Ball Speed, Club Speed, VLA/HLA, Spin, Apex and Offline. Spin remains a top-level metric.

- current shot / movement = gold
- analytical geometry / confidence = teal
- historical dispersion = muted teal/slate
- target line is visually stronger than horizontal grid
- Session Trends alternate teal and gold intentionally
- Shot Shape Mix uses Draw teal, Straight slate, Fade gold

### Club

Four quadrants remain:

- Club Path & Face
- Spin
- Launch & Loft
- Impact Location

Impact credibility states are product requirements:

- **Measured**
- **Estimate**
- **Direction Estimate**
- **Unavailable**

Never plot a precise-looking impact marker when location is unavailable. Estimated impact uses the same lens + gold ring + gold dot visual language as Shot → Strike.

### Table

Keep it dense. Current/selected row gets restrained gold emphasis. Reduce row-border noise and keep two-line labels/units legible.

### Numbers

Keep the 4×4 structure. Carry is the hero gold metric; technical status/data uses teal; unavailable values are visibly subdued.

### Range

The desktop range is intentionally simple: a continuous dark-green field below the metric ribbon, a subtly distinct center corridor, teal reference geometry, muted historical flights, and a gold current flight/landing point.

### Dispersion / Bag / Fit / Lab / Setup

Preserve production functionality. Palette adaptation should not replace current upstream product logic. Setup in particular owns current aim-calibration behavior and must stay on the latest production implementation.

## Data credibility and aim correction

Visual work must not change source-of-truth data behavior.

- Native Nova payloads remain stored/forwarded unchanged.
- Aim calibration is applied at read/display boundaries.
- The desktop UI adapter temporarily exposes aim-corrected copies only to historical renderers that predate the aim-calibration feature, then restores native session data immediately.
- Never persist those corrected display copies.
- Preserve Measured / Derived / Estimated / Direction Estimate / Unavailable distinctions.
- Do not style unavailable data like measurements.

## Change checklist

When changing desktop UI:

1. Decide the element role before choosing color: current, analytical, structural, secondary, success, or danger.
2. Use `src/ui/tokens.py` for new work.
3. Keep business/data logic in production modules; keep visual adaptation in `src/ui/`.
4. Preserve hit geometry whenever controls move.
5. Verify Shot, Club, Table, Numbers, Range, Dispersion, Bag, Fit, Lab, Setup, expanded/collapsed Recent Shots, and header controls.
6. Verify aim calibration still changes every affected display without changing stored native payloads.
7. Run the full test suite and cross-platform build before merging.
