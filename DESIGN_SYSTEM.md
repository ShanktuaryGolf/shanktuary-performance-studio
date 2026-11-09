# Shanktuary Performance Studio design system

The desktop is a premium golf-analysis workspace with a deep navy foundation,
illuminated teal panels, aqua analytical geometry and warm gold emphasis. The
November 2026 full-studio concept set supersedes the earlier compact icon-rail
layout. It does not authorize fabricated measurements or connection states.

## Architecture

`shanktuary_app.py` instantiates `src.ui.desktop.ShanktuaryDesktopApp`, a visual
adapter over the production `ShanktuaryApp`. Production code continues to own
shot-source connections, history, aim calibration, pressure, exports and device
workflows. Native incoming payloads are never changed by a painter.

The current UI modules are:

- `concept_shell.py`: labeled navigation, title, session/club controls and actual
  connection status.
- `concept_canvas.py`: the 124px header translation and public hit-coordinate
  conversion. Public hit rectangles describe visible, unscaled canvas pixels.
  Local painter geometry is restored before each frame to prevent drift.
- `concept_session.py`: Shot and Club; live metric provenance, trajectory,
  dispersion, trends, shape mix, contact and shot-history controls.
- `concept_overview.py`: Session Overview landing page; latest shot, pressure/balance and session summary.
- `concept_metrics.py`: Numbers and desktop Range.
- `concept_workspaces.py`: Bag, Fit, Lab, Index, Setup and Dispersion. Detailed
  production Fit and Setup controls remain reachable from their overview pages.
- `concept_art.py`: cached decorative scenery.
- `concept_boards.py`: the shared Pair / Assign / 50–50 / Stance width / Ready
  board workspace, including the guided flow. Pairing, source selection, manual
  assignment, calibration and tare use production actions. Readiness requires
  fresh hardware data and successful calibration for the current configuration.
- `connection_wizard.py`: source choice and connection setup. Existing explicit
  connection actions and test-shot readiness gates are unchanged. The supported
  Nova + GSPro mode remains available under Advanced connections.
- `tokens.py`: desktop color roles.

`_legacy/` remains private compatibility implementation for retained detailed
views. New code should use the public desktop adapter and current modules.

## Visual roles

- Page and navigation: deep navy, `PAGE_BG` and `RAIL_BG`.
- Grouping: subtle illuminated surfaces, rounded 12px corners and quiet teal
  borders. Use `concept_shell.panel` for shared material and bounded caching.
- Aqua: active navigation, analysis, chart geometry, primary setup controls.
- Gold: current shot/landing point, Carry emphasis, selected table row and
  section labels. Do not use gold to imply measured or ready state.
- White: primary text. Slate: captions and unavailable values.
- Green/red: actual success/error only.

Use token roles, not ad-hoc colors, for new UI work. Browser tokens live in
`theme.BROWSER_STUDIO`; regenerate `assets/theme.css` using
`python scripts/gen_theme_css.py`. `assets/studio-browser.css` consumes those
scoped roles without recoloring unrelated compatibility surfaces.

## Navigation and composition

SESSION: Overview (landing), Shot, Club, Table, Numbers.
PRACTICE: Range, Index.
TOOLS: Dispersion, Bag, Fit, Lab, Setup.

The labeled rail is 272 logical pixels. A larger workspace header holds the
page title, session picker, current-club picker, New Session and true source
status. The Shot workspace contains Recent Shots rather than a second global
rail. Previous/next history navigation, deletion confirmation, per-shot contact
marking and session tools remain available.

Shot reads RESULT → SHAPE → CAUSE, then Session Trends and Shot Shape Mix.
Club keeps four quadrants. Numbers keeps a 4×4 grid with Carry emphasized.
Range scenery is decorative; live flight curves and landing positions are
separate, calculated from available shot data. The downrange camera projects
distance into depth, lateral offline across the scene, and elevation vertically.
Target rings share that camera. Carry, apex and offline are required; a missing
metric never creates a made-up flight. Shot/Overview use explicitly labeled
side-profile charts on a flat chart field, not a perspective range grid.

## Data credibility

Use `src.connections.presentation.metric_value` and `metric_status` for
source-aware display. Distinguish Reported/Native, Derived, Estimate/Modelled and
Unavailable. A measured zero must not become missing, and missing data must not
be rendered as zero. Do not display the concept artwork's sample numbers or
proposed remote links as live information.

Aim correction belongs at the read/display boundary. Never persist corrected
copies. Contact markers need actual supplied or user-marked coordinates;
history-backed estimates remain clearly labeled and visually distinct.

## Verification

Run `python -m pytest tests/ -v` with an actual graphical display for UI coverage.
Headless runs skip graphical tests and are not a full UI pass. Run scoped lint,
the packaged-startup smoke check and native interaction tests at multiple UI
scales. Test repeated navigation, menus, Close/Cancel, source readiness, shot
selection, contact marking and modal ownership. Record any obsolete visual
assertions separately from actual behavioral failures.

`scripts/preview_concept.py` runs the real app with explicitly labeled sample
fixtures in isolated user-data directories. Its canvas exports are render
artifacts, not proof of a live launch monitor or pressure-board connection.

## Visual verification runtime

On the Linux cloud QA host, use the system Python with Tk 8.6/Xft for native
antialiased Canvas text. The bundled Tk 9 build exposes bitmap X11 fonts only
and is not a representative typography preview. This changes the QA runtime,
not application text rendering or saved settings. Continue testing click
geometry, clipping and exports with the actual native font metrics.

The concept images differ in header height and represent illustrative data.
The integrated desktop keeps one stable shared header across workspaces;
pressure imagery must remain truthful to available board-load measurements.
Existing saved browser overlays are preserved; concept presets require an
explicit selection before saving. No visual fidelity pass authorizes releases.
