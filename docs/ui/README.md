# UI redesign — reference mockups

All ten views at 1600×900. These are the implementation target: the layout,
spacing, and colour decisions here are settled, so building a view means
reproducing its mockup rather than re-litigating the design.

Rendered with PIL (see `scratch/render_*.py`) purely because Tkinter's
postscript export cannot embed the clubface photo. **Every primitive used
maps 1:1 onto a Tkinter Canvas call the app already makes** — rectangles,
rounded polygons, text, lines, `create_image`. Nothing here needs a new
dependency or a framework change.

| View | File | Status |
|------|------|--------|
| Overview | `overview_tab_mockup.png` | mockup |
| Quad | `quad_view_mockup.png` | mockup |
| Range | `view_range.png` | mockup |
| Dispersion | `view_disp.png` | mockup |
| Table | `view_table.png` | mockup |
| Big Numbers | `view_nums.png` | mockup |
| My Bag | `view_bag.png` | mockup |
| Fitting | `view_fit.png` | mockup |
| Swing Lab | `view_lab.png` | mockup |
| Setup / Hardware | `view_setup.png` | mockup |

Shipped so far: `theme.py` (design tokens) and `draw_nav_rail()` (the left
rail, live on all views).

## The rules

**One neutral ramp, one accent, semantic colour only where it means
something.** The old UI carried 195 distinct hex literals across 734 usages,
so colour had stopped signalling anything — cyan marked "offline" in one
panel and "spin axis" in another. Tokens live in `theme.py`.

**Hunter green needs a scale, not a value.** A true hunter (`#355E3B`)
measures 2.55:1 against the app background, which is unreadable for text or
1px strokes. `ACCENT` carries large fills, `ACCENT_LINE` carries strokes,
`ACCENT_TEXT` carries numbers.

**Whitespace groups; borders are a fallback.** Cards use a lifted surface
with hairline dividers *inside* them. No outer boxes.

**Label small and quiet above, value large, unit tertiary beside it.**
Left-aligned so the eye tracks a column.

**Photography is an asset.** The real clubface (`assets/iron_face.png`)
outperforms any abstract diagram — people connect with a picture of a club.
Quad keeps all four club-geometry panels for exactly this reason.

## Honesty in the design

The Nova measures five ball parameters: ball speed, launch angles, total
spin, spin axis. Everything else on screen is derived, and the UI says so.

- **Unavailable values render `--` in `TEXT_3`**, never styled as a
  measurement. `compute_smash_confidence()` detects when OpenGolfCoach's
  estimate has saturated; a clamped value carries no information.
- **`DERIVED` tags** on panels showing D-plane inversions (club path, face
  angles).
- **`ESTIMATE` chip + dashed uncertainty ring** on strike location. A dashed
  zone reads as deliberate; a precise crosshair on data we don't have reads
  as fake.
- **"Attack angle not measured"** stated plainly where Foresight would show a
  number, because that needs camera hardware the Nova lacks.

This is what keeps the Foresight-style layout from looking like a knockoff
that's bluffing.

## Per-view notes

**Overview** — landing view. Primary metrics, three cards (Ball Flight, Club
Delivery, Strike), recent-shot bars, dispersion and tendencies. The
Tendencies panel shows data the app does not compute yet; it is a design
placeholder, not a spec.

**Quad** — Foresight-style, no panel boxes. Four club-geometry panels on one
dark stage with hairline dividers, labels floating as annotations. Uses all
three shipped assets (`iron_overhead`, `iron_side`, `iron_face`).

**Range** — two cameras. A head-on down-range view renders a straight shot as
a vertical line and tells the user nothing about flight, so the arc gets its
own side-elevation panel below.

**Dispersion** — overhead scatter with ±1σ/±2σ covariance ellipses,
trajectory profile, gapping ladder with explicit gap callouts.

**Table** — dense but scannable: zebra striping, accent on the sorted column,
selected row lifted with an accent edge. Strike column colours only when it
is not centre.

**Big Numbers** — projector/sim mode. 4×3 tiles, carry accented with a top
rule. Muted tiles keep their slot rather than disappearing, so the grid
doesn't reflow between shots.

**My Bag** — club table with loft *and* lie, gapping ladder, unmapped-club
count. Generic default lofts flip 21% of strike verdicts, so entering real
specs matters more than it appears.

**Fitting** — two club columns, delta matrix with directional colour,
trajectory overlay, recommendation. Smash is excluded from comparison because
it is a constant at these speeds.

**Swing Lab** — CoP trail with address/transition/impact markers, dual-foot
heatmap, lead/trail balance bar, and weight-transfer / force curves plotted
per foot against a shared phase timeline.

**Setup / Hardware** — board pairing was previously reachable only from Swing
Lab via a small "⚙ Hardware" button, which is hard to find when the thing you
are trying to do is connect a board for the first time. This promotes it to
the rail's Setup slot and keeps every capability of the existing modal:
single/dual mode toggle, Bluetooth pairing, the step-on left/right assignment
wizard with live per-board kg, and tare. Nothing is removed — it is laid out
rather than stacked in a modal.

## Build order

1. ~~`theme.py` — design tokens~~ **done**
2. ~~`draw_nav_rail()` — left rail~~ **done**
3. Overview (`view_mode 9`, currently falls through to the quad studio)
4. Quad rebuild
5. Remaining seven views against the theme

Re-render any mockup with:

```bash
cd scratch
python3 render_full_ui.py /tmp/overview.png     # Overview
python3 render_quad.py    /tmp/quad.png         # Quad
python3 render_views_a.py                       # Range, Disp, Table
python3 render_views_b.py                       # Nums, Bag, Fit, Lab
python3 render_setup.py                         # Setup / Hardware
SPS_PALETTE=hunter python3 render_quad.py out.png   # palette variants
```
