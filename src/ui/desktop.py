"""Production desktop app with the approved Shanktuary visual layer.

The launch-monitor connection, OpenGolfCoach data, aim calibration, persistence,
pressure capture, and browser server remain owned by the production
`ShanktuaryApp`.  This subclass changes desktop rendering and hit geometry only.

The renderer snapshot in `_legacy/` is intentionally isolated behind this file.
New product code should depend on `ShanktuaryDesktopApp`, not versioned renderer
modules directly.  That gives the project a stable seam while the historical
iterative renderers are progressively consolidated.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys

import shanktuary_performance_studio as studio
import theme

# The approved renderer snapshot predates package-relative imports. Keep its
# internal module names private to this UI layer instead of scattering v1...v17
# files through the repository root. PyInstaller is given this directory via
# --paths in the build workflow.
_LEGACY_DIR = Path(__file__).resolve().parent / "_legacy"
if str(_LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_DIR))

import club_redesign_v4 as club_ui  # noqa: E402
import numbers_redesign_v2 as numbers_ui  # noqa: E402
import overview_redesign_v15 as shot_ui  # noqa: E402
import range_redesign_v3 as range_ui  # noqa: E402
import remaining_pages_palette_v1 as legacy_palette  # noqa: E402
import shell_redesign_v17 as shell_ui  # noqa: E402
import table_redesign_v2 as table_ui  # noqa: E402


@contextmanager
def _aim_corrected_display_shots(app):
    """Expose aim-corrected copies to renderers that predate aim calibration.

    Upstream intentionally stores the native Nova payload and applies aim
    correction at read boundaries. The approved Shot/Table/Range renderers were
    designed before that feature and read `current_shot` / `session_shots`
    directly. For the duration of one renderer call, replace only the active
    session's display list with corrected copies, then restore the native data.

    No persistence or event payload is ever modified.
    """
    if not hasattr(app, "aim_corrected"):
        yield
        return

    try:
        session = app.get_active_session()
    except Exception:
        yield
        return

    native_shots = session.get("shots", [])
    native_current = getattr(app, "current_shot", None)
    if not native_shots and native_current is None:
        yield
        return

    corrected = []
    for shot in native_shots:
        try:
            corrected.append(app.aim_corrected(shot))
        except Exception:
            corrected.append(shot)

    session["shots"] = corrected
    idx = getattr(app, "selected_shot_index", -1)
    if isinstance(idx, int) and 0 <= idx < len(corrected):
        app.current_shot = corrected[idx]
    elif native_current is not None:
        try:
            app.current_shot = app.aim_corrected(native_current)
        except Exception:
            app.current_shot = native_current

    try:
        yield
    finally:
        session["shots"] = native_shots
        app.current_shot = native_current


class ShanktuaryDesktopApp(studio.ShanktuaryApp):
    """Production Shanktuary app with the approved desktop design system."""

    @staticmethod
    def _design_hit(rect, x, y):
        return bool(rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3])

    def __init__(self, root):
        # These are referenced by overridden painters during base __init__.
        self.design_sidebar_toggle_rect = None
        self.design_shot_card_rects = []
        self.design_mode_rects = {}
        self.design_club_btn_rect = None
        self.design_dexterity_btn_rect = None
        self.design_tools_btn_rect = None
        self.design_fullscreen_btn_rect = None
        self.design_dispersion_tab_rects = []

        super().__init__(root)

        self.sidebar_width = 300
        # Shot is the default landing workspace in the redesigned navigation.
        self.view_mode = 9
        self.canvas.config(cursor="arrow")
        self.canvas.bind(
            "<Motion>",
            lambda _event: self.canvas.config(cursor="arrow"),
            add="+",
        )
        root.title(f"Shanktuary Performance Studio {studio.APP_VERSION}")
        self.draw_screen()

    def draw_screen(self):
        """Reserve a dedicated drawer gutter only while Recent Shots is closed."""
        old_rail_w = theme.RAIL_W
        try:
            if getattr(self, "sidebar_collapsed", False):
                theme.RAIL_W = shell_ui.NAV_RAIL_W + shell_ui.COLLAPSED_GUTTER_W
            return super().draw_screen()
        finally:
            theme.RAIL_W = old_rail_w

    def _toggle_design_sidebar(self):
        self.sidebar_collapsed = not bool(getattr(self, "sidebar_collapsed", False))
        self.show_session_menu = False
        self.show_filter_menu = False
        self.show_club_menu = False
        self.show_tools_menu = False
        self.sidebar_width = 300
        self.draw_screen()

    # ---- Session pages -------------------------------------------------
    def draw_overview_viewport(self, *args, **kwargs):
        with _aim_corrected_display_shots(self):
            return shot_ui.draw_overview(self, *args, **kwargs)

    def draw_top_metric_toolbar(self, *args, **kwargs):
        if self.view_mode == 1:
            return club_ui.draw_top_metric_toolbar(self, *args, **kwargs)
        return studio.ShanktuaryApp.draw_top_metric_toolbar(self, *args, **kwargs)

    def draw_4_quadrant_studio(self, *args, **kwargs):
        def production_draw(*a, **k):
            return studio.ShanktuaryApp.draw_4_quadrant_studio(self, *a, **k)

        # Aim correction affects start-line presentation, while strike location
        # itself is unchanged. Exposing a corrected current shot keeps any text
        # derived from shot_name/HLA consistent with the rest of the app.
        with _aim_corrected_display_shots(self):
            return club_ui.draw_4_quadrant_studio(
                self, production_draw, *args, **kwargs
            )

    def draw_shot_table_viewport(self, avail_w, h, offset_x=0):
        with _aim_corrected_display_shots(self):
            return table_ui.draw_shot_table_viewport(
                self, avail_w, h, offset_x=offset_x
            )

    def draw_big_numbers_viewport(
        self, avail_w, h, carry, total, ball_speed, club_speed, smash, launch,
        spin, spin_axis, club_path, face_to_path, apex, offline,
        closure_rate=0.0, attack_angle=0.0, dynamic_loft=0.0,
        hang_time=0.0, offset_x=0,
    ):
        return numbers_ui.draw_big_numbers_viewport(
            self, avail_w, h, carry, total, ball_speed, club_speed, smash,
            launch, spin, spin_axis, club_path, face_to_path, apex, offline,
            closure_rate=closure_rate, attack_angle=attack_angle,
            dynamic_loft=dynamic_loft, hang_time=hang_time, offset_x=offset_x,
        )

    # ---- Practice / tools ---------------------------------------------
    def draw_3d_range_viewport(self, *args, **kwargs):
        with _aim_corrected_display_shots(self):
            return range_ui.draw_range(self, *args, **kwargs)

    def draw_dispersion_and_gapping(self, avail_w, h, offset_x=0):
        with _aim_corrected_display_shots(self):
            return legacy_palette.draw_dispersion_and_gapping(
                self, avail_w, h, offset_x=offset_x
            )

    def draw_my_bag_viewport(self, *args, **kwargs):
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_my_bag_viewport(self, *a, **k),
            *args, **kwargs,
        )

    def draw_fitting_viewport(self, *args, **kwargs):
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_fitting_viewport(self, *a, **k),
            *args, **kwargs,
        )

    def draw_swing_lab_viewport(self, *args, **kwargs):
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_swing_lab_viewport(self, *a, **k),
            *args, **kwargs,
        )

    def draw_setup_viewport(self, *args, **kwargs):
        # Keep the latest upstream aim-calibration implementation intact; only
        # recolor its production primitives into the approved desktop palette.
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_setup_viewport(self, *a, **k),
            *args, **kwargs,
        )

    # ---- Persistent shell ---------------------------------------------
    def draw_left_sidebar(self, w, h):
        # Upstream's base sidebar already applies aim correction. The approved
        # overlay predates that feature, so expose corrected copies only to it.
        studio.ShanktuaryApp.draw_left_sidebar(self, w, h)
        with _aim_corrected_display_shots(self):
            shell_ui.paint_sidebar(self, w, h)

    def draw_nav_rail(self, h):
        studio.ShanktuaryApp.draw_nav_rail(self, h)
        shell_ui.paint_nav(self, h)

    def draw_top_header(self, w, h, offset_x=0):
        studio.ShanktuaryApp.draw_top_header(self, w, h, offset_x=offset_x)
        shell_ui.paint_top_header(self, w, h, offset_x=offset_x)

    # ---- Final-shell hit testing --------------------------------------
    def handle_mouse_press(self, event):
        x, y = event.x, event.y

        if getattr(self, "view_mode", None) == 3:
            for rect, submode in getattr(self, "design_dispersion_tab_rects", []):
                if self._design_hit(rect, x, y):
                    self.dispersion_view_submode = submode
                    self.draw_screen()
                    return

        if getattr(self, "sidebar_collapsed", False):
            gx1 = shell_ui.NAV_RAIL_W
            gx2 = gx1 + shell_ui.COLLAPSED_GUTTER_W
            drawer_hotzone = (gx1, 52, gx2, 100)
        else:
            drawer_hotzone = (
                self.sidebar_width - 48, 138,
                self.sidebar_width + 8, 194,
            )

        if (
            self._design_hit(getattr(self, "design_sidebar_toggle_rect", None), x, y)
            or self._design_hit(drawer_hotzone, x, y)
        ):
            self._toggle_design_sidebar()
            return

        if not getattr(self, "sidebar_collapsed", False):
            for x1, y1, x2, y2, shot_idx in getattr(self, "design_shot_card_rects", []):
                if x1 <= x <= x2 and y1 <= y <= y2:
                    if 0 <= shot_idx < len(self.session_shots):
                        self.selected_shot_index = shot_idx
                        self.current_shot = self.session_shots[shot_idx]
                        self.show_club_menu = False
                        self.show_tools_menu = False
                        self.draw_screen()
                    return

        for mode_id, rect in getattr(self, "design_mode_rects", {}).items():
            if self._design_hit(rect, x, y):
                self.show_club_menu = False
                self.show_tools_menu = False
                self.set_mode(mode_id)
                return

        if self._design_hit(getattr(self, "design_club_btn_rect", None), x, y):
            self.show_club_menu = not getattr(self, "show_club_menu", False)
            self.show_tools_menu = False
            self.draw_screen()
            return

        if self._design_hit(getattr(self, "design_dexterity_btn_rect", None), x, y):
            self.is_left_handed = not getattr(self, "is_left_handed", False)
            self.show_club_menu = False
            self.show_tools_menu = False
            self.draw_screen()
            return

        if self._design_hit(getattr(self, "design_tools_btn_rect", None), x, y):
            self.show_tools_menu = not getattr(self, "show_tools_menu", False)
            self.show_club_menu = False
            self.draw_screen()
            return

        if self._design_hit(getattr(self, "design_fullscreen_btn_rect", None), x, y):
            self.toggle_fullscreen()
            return

        # Everything not owned by the redesigned shell (Setup calibration,
        # table checkboxes, bag editing, pressure controls, etc.) remains the
        # latest upstream interaction logic.
        return studio.ShanktuaryApp.handle_mouse_press(self, event)
