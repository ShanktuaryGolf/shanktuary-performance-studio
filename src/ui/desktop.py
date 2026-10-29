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

import sys
from contextlib import contextmanager
from pathlib import Path

import shanktuary_performance_studio as studio
import theme

from .scaling import (
    CHOICES,
    ScaledCanvas,
    configure_root,
    logical_font,
    resolve_scale,
    save_choice,
)

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
        self.ui_scale_choice, self.ui_scale = configure_root(root)
        self._display_dpi = root._sps_original_dpi
        self.ui_scale_controls = {}
        # These are referenced by overridden painters during base __init__.
        self.design_sidebar_toggle_rect = None
        self.design_shot_card_rects = []
        self.design_shot_delete_rects = []
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

    def _make_canvas(self, root):
        frame = studio.tk.Frame(root, bg=theme.BG)
        frame.pack(fill="both", expand=True)
        canvas = ScaledCanvas(frame, scale=self.ui_scale, bg=theme.BG,
                              highlightthickness=0)
        # Scrolling is an explicit fallback when a large accessibility scale
        # cannot fit a complete workspace; never silently shrink the chosen UI.
        horizontal = studio.tk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
        vertical = studio.tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        def show_scrollbar(bar, side, fill, first, last):
            bar.set(first, last)
            needed = float(first) > .0001 or float(last) < .9999
            if needed and not bar.winfo_manager():
                options = {"before": canvas} if canvas.winfo_manager() else {}
                bar.pack(side=side, fill=fill, **options)
            elif not needed and bar.winfo_manager():
                bar.pack_forget()
        canvas.configure(
            xscrollcommand=lambda a, b: show_scrollbar(horizontal, "bottom", "x", a, b),
            yscrollcommand=lambda a, b: show_scrollbar(vertical, "right", "y", a, b),
        )
        self._display_scrollbars = horizontal, vertical
        return canvas

    def _canvas_font(self, **kwargs):
        return logical_font(kwargs.pop("root", self.root), **kwargs)

    def _text_width(self, text, font_spec):
        size = font_spec[1] if len(font_spec) > 1 else 10
        return logical_font(self.root, family=font_spec[0], size=size,
                            weight="bold" if "bold" in font_spec else "normal").measure(text)

    def set_ui_scale(self, choice, *, persist=True):
        if choice not in CHOICES:
            raise ValueError("Unsupported UI scale")
        if persist:
            save_choice(choice)
        self.ui_scale_choice = choice
        self.ui_scale = resolve_scale(choice, self._display_dpi)
        self.root._sps_ui_scale = self.ui_scale
        self.root.tk.call("tk", "scaling", 96 / 72 * self.ui_scale)
        self.canvas.ui_scale = self.ui_scale
        self.canvas._scaled_images.clear()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.draw_screen()

    def step_ui_scale(self, direction):
        """Move one preset without jumping at bounds or losing Auto there."""
        presets = [int(choice[:-1]) / 100 for choice in CHOICES if choice != "Auto"]
        options = [scale for scale in presets if (scale - self.ui_scale) * direction > .001]
        if options:
            scale = min(options) if direction > 0 else max(options)
            self.set_ui_scale(f"{round(scale * 100)}%")

    def draw_tools_display_controls(self, x1, y, x2):
        """Compact size controls live inside Tools, not in the persistent bar."""
        c = self.canvas
        c.create_text(x1 + 20, y + 17, text="UI SCALE", fill=theme.TEXT_3,
                      font=(theme.ui_font(), 8), anchor="w")
        right = x2 - 16
        controls = {
            "minus": (right - 216, y + 2, right - 184, y + 34),
            "plus": (right - 116, y + 2, right - 84, y + 34),
            "auto": (right - 62, y + 2, right, y + 34),
        }
        self.ui_scale_controls = controls
        for action in ("minus", "plus"):
            rect = controls[action]
            enabled = self.ui_scale > 1 if action == "minus" else self.ui_scale < 2
            c.create_rectangle(*rect, fill="#18313A", outline="#24434C")
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            color = theme.TEXT if enabled else theme.TEXT_3
            # Draw signs as strokes, avoiding font-specific missing glyphs.
            c.create_line(cx - 5, cy, cx + 5, cy, fill=color, width=1.5)
            if action == "plus":
                c.create_line(cx, cy - 5, cx, cy + 5, fill=color, width=1.5)
        c.create_text(right - 150, y + 18, text=f"{round(self.ui_scale * 100)}%",
                      fill="#D4A24F", font=(theme.ui_font(), 10, "bold"))
        auto = controls["auto"]
        c.create_text((auto[0] + auto[2]) / 2, y + 18, text="Auto",
                      fill="#D4A24F" if self.ui_scale_choice == "Auto" else theme.TEXT_3,
                      font=(theme.ui_font(), 9))
        c.create_line(x1 + 20, y + 48, x2 - 20, y + 48, fill="#24434C")
        return y + 68

    def draw_screen(self):
        """Reserve a dedicated drawer gutter only while Recent Shots is closed."""
        if isinstance(getattr(self, "canvas", None), ScaledCanvas):
            self.canvas.minimum_size = (1600 if getattr(self, "view_mode", 9) == 4 else 1100,
                                        1050 if getattr(self, "show_tools_menu", False) else 900)
            self.canvas.update_scrollregion()
        old_rail_w = theme.RAIL_W
        try:
            if getattr(self, "sidebar_collapsed", False):
                theme.RAIL_W = shell_ui.NAV_RAIL_W + shell_ui.COLLAPSED_GUTTER_W
            return super().draw_screen()
        finally:
            theme.RAIL_W = old_rail_w

    def _toggle_design_sidebar(self):
        self.sidebar_collapsed = not bool(getattr(self, "sidebar_collapsed", False))
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.show_club_menu = False
        self.show_tools_menu = False
        self.sidebar_width = 300
        self.draw_screen()

    def handle_scroll_delta(self, delta, mouse_x=None):
        if mouse_x is None:
            physical_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
            mouse_x = self.canvas.canvasx(physical_x) / self.ui_scale
        return super().handle_scroll_delta(delta, mouse_x)

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

    def draw_shanktuary_index_viewport(self, *args, **kwargs):
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_shanktuary_index_viewport(self, *a, **k),
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

    def draw_board_assign_modal(self, *args, **kwargs):
        # This modal is painted from draw_screen, outside the Setup page's
        # palette scope, so it rendered in the legacy hunter-green tokens
        # while every surface behind it was navy/teal/gold.
        return legacy_palette.draw_production_page(
            self,
            lambda *a, **k: studio.ShanktuaryApp.draw_board_assign_modal(self, *a, **k),
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
        if any(getattr(self, flag, False) for flag in (
            "show_pairing_modal", "show_board_assign_modal", "show_aim_modal",
            "show_spec_editor_modal", "show_autofill_modal", "show_custom_club_modal",
        )):
            return studio.ShanktuaryApp.handle_mouse_press(self, event)
        if getattr(self, "show_tools_menu", False):
            for action, rect in self.ui_scale_controls.items():
                if self._design_hit(rect, x, y):
                    try:
                        if action == "auto":
                            self.set_ui_scale("Auto")
                        else:
                            self.step_ui_scale(-1 if action == "minus" else 1)
                    except OSError as exc:
                        from tkinter import messagebox
                        messagebox.showerror("Display size", f"Could not save display size: {exc}", parent=self.root)
                    return

        # Full-window takeovers owned by the production class. The redesigned
        # shell's hit rects are still live underneath them, so a click on the
        # modal's own button would otherwise be stolen by whatever design rect
        # happens to sit at those coordinates -- the button looks dead, or the
        # page behind it silently changes.
        if getattr(self, "show_pairing_modal", False):
            return studio.ShanktuaryApp.handle_mouse_press(self, event)

        if getattr(self, "show_board_assign_modal", False):
            return studio.ShanktuaryApp.handle_mouse_press(self, event)

        if getattr(self, "view_mode", None) in (9, 1):   # Shot, Quad
            from src.ui.contact_panel import handle_face_click
            if handle_face_click(self, x, y):
                return

        if getattr(self, "view_mode", None) == 3:
            for rect, submode in getattr(self, "design_dispersion_tab_rects", []):
                if self._design_hit(rect, x, y):
                    self.dispersion_view_submode = submode
                    self.draw_screen()
                    return
            if self._design_hit(getattr(self, "dispersion_split_rect", None), x, y):
                self.dispersion_split_by_ball = not getattr(self, "dispersion_split_by_ball", False)
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
            for x1, y1, x2, y2, shot_idx in getattr(self, "design_shot_delete_rects", []):
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self.delete_shot(shot_idx)
                    return

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
