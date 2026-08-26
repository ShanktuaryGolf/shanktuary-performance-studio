# UI redesign — where things stand

Last updated at the end of the session that built `theme.py` and the nav rail.

## Shipped (live in the app, on `main`)

- **`theme.py`** — design tokens. One neutral ramp, hunter-green accent scale,
  semantic colours reserved for meaning.
- **Left nav rail** (`draw_nav_rail`) — replaces the eight mode pills, renders
  on every view. Registers into `mode_pill_rects` so click handling is
  unchanged.
- **Range view** — themed, apex label removed from the flight arc.
- **Shared chrome** — shot library and top header themed. These render
  everywhere, so this is what made the app look consistent.
- **Shared metric toolbar** — borderless, left-aligned, one accent.
- **StanceCalibrator wired up** — was dead code. Now has manager methods,
  `GET`/`POST /api/pressure/stance`, persistence, and a button in the hardware
  modal. `tests/test_stance_width.py` (6 tests).
- **Bug fixes**: strike scored from the shot's own club (was using the
  dropdown's current value, so scrolling history re-scored old shots);
  balance-board console spam; Overview moved off `view_mode 0` (that is the
  divot projector).

## Not started

Content views still on old styling: **Dispersion, Table, Bag, Fitting,
Big Numbers, Swing Lab**. Overview (`view_mode 9`) has a mockup and a rail
entry but no implementation — it currently falls through to the quad studio.

Four dropdowns unstyled: **session, filter, club, Tools**. Tools has a mockup
ready (`view_tools.png`); the other three do not.

## Open questions from Sean

- **Range** — said "I have questions", started to describe, moved on. Possibly
  related: `/range` (Three.js/WebGPU, browser) and `view_mode 2`
  (`draw_3d_range_viewport`, Tkinter) are different surfaces sharing a name.
  `range_launch_web_rect` is the bridge between them.
- **Fitting** — said "I have questions", never described. My own concern: the
  mockup compares PW vs 52°, which is a distance comparison, not a fitting
  comparison. Real fitting compares the same club in different configs.

## Next up

Highest leverage first:

1. The four dropdowns — small, shared, visible on every view.
2. Overview — it is the landing view and the first thing a tester sees.
3. Remaining content views, one at a time.

## Testing note

Sean has someone lined up to test. Anything half-themed reads as broken, so
prefer finishing shared surfaces over starting new views.

`docs/ui/README.md` has the design rules and the full mockup index.
