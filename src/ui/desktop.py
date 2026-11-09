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

import overview_redesign_v15 as shot_ui  # noqa: E402,F401 - retained compatibility export
import remaining_pages_palette_v1 as legacy_palette  # noqa: E402


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
        # Resolve after Tk exists: import-time fallback can otherwise remain a
        # bitmap Helvetica face on Linux and distort the approved typography.
        theme._UI_FONT = theme._resolve_ui_font()
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

        self.sidebar_width = 260
        self.sidebar_collapsed = True
        self.concept_ui = True
        # The approved Session Overview is the landing workspace.
        self.view_mode = 12
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
        canvas = ScaledCanvas(
            frame, scale=self.ui_scale, bg=theme.BG, highlightthickness=0
        )
        # Scrolling is an explicit fallback when a large accessibility scale
        # cannot fit a complete workspace; never silently shrink the chosen UI.
        horizontal = studio.tk.Scrollbar(
            frame, orient="horizontal", command=canvas.xview
        )
        vertical = studio.tk.Scrollbar(frame, orient="vertical", command=canvas.yview)

        def show_scrollbar(bar, side, fill, first, last):
            bar.set(first, last)
            needed = float(first) > 0.0001 or float(last) < 0.9999
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
        return logical_font(
            self.root,
            family=font_spec[0],
            size=size,
            weight="bold" if "bold" in font_spec else "normal",
        ).measure(text)

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
        options = [
            scale for scale in presets if (scale - self.ui_scale) * direction > 0.001
        ]
        if options:
            scale = min(options) if direction > 0 else max(options)
            self.set_ui_scale(f"{round(scale * 100)}%")

    def draw_tools_display_controls(self, x1, y, x2):
        """Compact size controls live inside Tools, not in the persistent bar."""
        c = self.canvas
        c.create_text(
            x1 + 20,
            y + 17,
            text="UI SCALE",
            fill=theme.TEXT_3,
            font=(theme.ui_font(), 8),
            anchor="w",
        )
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
        c.create_text(
            right - 150,
            y + 18,
            text=f"{round(self.ui_scale * 100)}%",
            fill="#D4A24F",
            font=(theme.ui_font(), 10, "bold"),
        )
        auto = controls["auto"]
        c.create_text(
            (auto[0] + auto[2]) / 2,
            y + 18,
            text="Auto",
            fill="#D4A24F" if self.ui_scale_choice == "Auto" else theme.TEXT_3,
            font=(theme.ui_font(), 9),
        )
        c.create_line(x1 + 20, y + 48, x2 - 20, y + 48, fill="#24434C")
        return y + 68

    def pressure_display_trail(self):
        from .lab_demo import active

        if active(self):
            return self.lab_demo_frames, False
        return studio.ShanktuaryApp.pressure_display_trail(self)

    def poll_pressure_stream(self):
        """Keep sensor collection responsive without repainting static Setup 30Hz.

        Device processing still owns its full-rate data. The desktop redraws
        live Lab at 10Hz and connection/calibration status at 4Hz, and lets Tk
        drain input events between frames even at high accessibility scaling.
        """
        import time

        try:
            pm = getattr(studio.obs_server, "pressure_manager", None)
            if pm:
                latest = pm.latest_frame
                if latest and latest is not getattr(
                    self, "_last_concept_pressure_frame", None
                ):
                    self._last_concept_pressure_frame = latest
                    self.swing_lab_history.append(latest)
                    self.swing_lab_history[:] = self.swing_lab_history[-200:]
                self.tick_setup_flow()
                now = time.monotonic()
                live = self.view_mode in (8, 12) and latest is not getattr(
                    self, "_last_concept_painted_frame", None
                )
                interval = 0.1 if live else 0.25
                if (
                    live or self.view_mode == 10 or self.show_board_assign_modal
                ) and now - getattr(
                    self, "_last_concept_pressure_paint", 0
                ) >= interval:
                    self.draw_screen()
                    self._last_concept_pressure_paint = time.monotonic()
                    self._last_concept_painted_frame = latest
        except Exception:
            pass
        self.root.after(100, self.poll_pressure_stream)

    def draw_screen(self):
        """Compose the live production workspace beneath the concept shell.

        The viewport retains production control coordinates, translated only
        at the painting/input boundary. Native payloads and device state remain
        untouched.
        """
        from . import tokens
        # Keep old shortcuts and saved view IDs routed to the unified landing.
        if self.view_mode == 9:
            self.view_mode = 12
        from .concept_canvas import (
            ViewportCanvas,
            restore_hit_geometry,
            translate_hit_geometry,
        )

        if isinstance(getattr(self, "canvas", None), ScaledCanvas):
            populated_overview = self.view_mode == 12 and (
                bool(self.session_shots) or self.current_shot is not None
            )
            self.canvas.minimum_size = (1600, 1450 if populated_overview else 1000)
            self.canvas.update_scrollregion()
        restore_hit_geometry(self)
        real_canvas = self.canvas
        old_rail_w = theme.RAIL_W
        self.sidebar_collapsed = True
        theme.RAIL_W = tokens.NAV_RAIL_W
        self.canvas = ViewportCanvas(real_canvas)
        try:
            with legacy_palette._page_palette(self):
                return super().draw_screen()
        finally:
            self.canvas = real_canvas
            translate_hit_geometry(self)
            theme.RAIL_W = old_rail_w

    def _toggle_design_sidebar(self):
        self.concept_recent_collapsed = not getattr(
            self, "concept_recent_collapsed", False
        )
        self.draw_screen()

    def toggle_sidebar(self, event=None):
        self._toggle_design_sidebar()

    def handle_scroll_delta(self, delta, mouse_x=None):
        if self.view_mode == 12:
            self.canvas.yview_scroll(delta, "units")
            return
        if mouse_x is None:
            physical_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
            mouse_x = self.canvas.canvasx(physical_x) / self.ui_scale
        if self.view_mode == 13:
            from .concept_history import handle_scroll
            return handle_scroll(self, delta, mouse_x)
        return super().handle_scroll_delta(delta, mouse_x)

    def set_mode(self, mode):
        self.canvas.yview_moveto(0)
        return super().set_mode(12 if mode == 9 else mode)

    # ---- Session pages -------------------------------------------------
    def draw_session_history(self, avail_w, h, offset_x=0):
        from .concept_history import draw
        return draw(self, avail_w, h, offset_x)

    def draw_tools_workspace(self, avail_w, h, offset_x=0):
        from .concept_tools import draw
        return draw(self, avail_w, h, offset_x)

    def draw_session_overview(self, avail_w, h, offset_x=0):
        from .concept_overview import draw

        return draw(self, avail_w, h, offset_x)

    def draw_overview_viewport(self, avail_w, h, *args, offset_x=0, **kwargs):
        from .concept_session import draw_shot

        return draw_shot(self, avail_w, h, offset_x)

    def draw_top_metric_toolbar(self, *args, **kwargs):
        return None

    def draw_4_quadrant_studio(self, avail_w, h, *args, offset_x=0, **kwargs):
        from .concept_session import draw_club

        return draw_club(self, avail_w, h, offset_x)

    def draw_shot_table_viewport(self, avail_w, h, offset_x=0):
        from .concept_table import draw

        return draw(self, avail_w, h, offset_x)

    def draw_big_numbers_viewport(self, avail_w, h, *args, offset_x=0, **kwargs):
        from .concept_metrics import numbers

        return numbers(self, avail_w, h, offset_x)

    def draw_3d_range_viewport(self, avail_w, h, *args, offset_x=0, **kwargs):
        from .concept_metrics import range_page

        return range_page(self, avail_w, h, offset_x)

    def draw_dispersion_and_gapping(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_dispersion

        return draw_dispersion(self, avail_w, h, offset_x)

    def draw_my_bag_viewport(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_bag

        return draw_bag(self, avail_w, h, offset_x)

    def draw_fitting_viewport(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_fit

        return draw_fit(self, avail_w, h, offset_x)

    def draw_swing_lab_viewport(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_lab

        return draw_lab(self, avail_w, h, offset_x)

    def draw_shanktuary_index_viewport(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_index

        return draw_index(self, avail_w, h, offset_x)

    def draw_setup_viewport(self, avail_w, h, offset_x=0):
        from .concept_workspaces import draw_setup

        return draw_setup(self, avail_w, h, offset_x)

    def _draw_concept_dialog(self, name, *args, **kwargs):
        """Retain production forms and callbacks with the shared material layer."""
        from .concept_workspaces import palette

        with palette(self, rounded=True):
            return getattr(studio.ShanktuaryApp, name)(self, *args, **kwargs)

    def draw_board_assign_modal(self, *args, **kwargs):
        from .concept_calibration import draw_board_calibration

        return draw_board_calibration(self, *args, **kwargs)

    def draw_pairing_modal(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_pairing_modal", *args, **kwargs)

    def draw_club_spec_editor_modal(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_club_spec_editor_modal", *args, **kwargs)

    def draw_autofill_set_modal(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_autofill_set_modal", *args, **kwargs)

    def draw_custom_club_modal(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_custom_club_modal", *args, **kwargs)

    def draw_aim_measure_modal(self, *args, **kwargs):
        from .concept_aim import draw

        return draw(self, *args, **kwargs)

    def draw_tools_flyout_menu(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_tools_flyout_menu", *args, **kwargs)

    def draw_session_dropdown(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_session_dropdown", *args, **kwargs)

    def draw_filter_dropdown(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_filter_dropdown", *args, **kwargs)

    def draw_club_dropdown(self, *args, **kwargs):
        return self._draw_concept_dialog("draw_club_dropdown", *args, **kwargs)

    def handle_key_press(self, event):
        if (
            getattr(self, "show_aim_modal", False)
            and getattr(self, "concept_aim_tab", "measure") == "shots"
        ):
            if event.keysym == "Escape":
                self.show_aim_modal = False
                self.aim_calibrating = False
                self.aim_calib_shots = []
            elif event.keysym in ("Return", "KP_Enter"):
                self.apply_aim_measurements()
            self.draw_screen()
            return "break"
        return super().handle_key_press(event)

    def apply_aim_measurements(self):
        from .concept_aim import apply

        return apply(self)

    # ---- Persistent shell ---------------------------------------------
    def draw_left_sidebar(self, w, h):
        # Recent shots are now in the Shot workspace, not a second global rail.
        return None

    def draw_nav_rail(self, h):
        from . import concept_shell

        proxy = self.canvas
        real = getattr(proxy, "_canvas", proxy)
        self.canvas = real
        try:
            shell_height = min(real.winfo_height(), 1000) if self.view_mode == 12 else real.winfo_height()
            concept_shell.paint(self, real.winfo_width(), shell_height)
            if real.winfo_height() > shell_height:
                real.create_rectangle(0, shell_height, concept_shell.RAIL, real.winfo_height(),
                                      fill=concept_shell.T.RAIL_BG, outline="")
        finally:
            self.canvas = proxy

    def draw_top_header(self, w, h, offset_x=0):
        return None

    def draw_connection_workspace(self, width, height, offset_x=0):
        from . import concept_session

        painter = (
            concept_session.draw_club
            if self.view_mode == 1
            else concept_session.draw_shot
        )
        return painter(self, width, height, offset_x)

    # ---- Final-shell hit testing --------------------------------------
    def handle_mouse_press(self, event):
        from .concept_shell import RAIL

        translated = event
        modal = any(
            getattr(self, flag, False)
            for flag in (
                "show_pairing_modal",
                "show_board_assign_modal",
                "show_aim_modal",
                "show_spec_editor_modal",
                "show_autofill_modal",
                "show_custom_club_modal",
            )
        )
        if modal:
            if getattr(self, "show_board_assign_modal", False) and self._design_hit(
                getattr(self, "board_modal_back_rect", None), translated.x, translated.y
            ):
                from .concept_boards import previous_step

                previous_step(self)
                return
            if self.show_aim_modal:
                from .concept_aim import handle_click

                if handle_click(self, translated.x, translated.y):
                    return
            return studio.ShanktuaryApp.handle_mouse_press(self, translated)
        if any(
            getattr(self, flag, False)
            for flag in (
                "show_session_dropdown",
                "show_filter_dropdown",
                "show_club_menu",
                "show_tools_menu",
            )
        ):
            if getattr(self, "show_tools_menu", False):
                for action, rect in self.ui_scale_controls.items():
                    if self._design_hit(rect, translated.x, translated.y):
                        if action == "auto":
                            self.set_ui_scale("Auto")
                        else:
                            self.step_ui_scale(-1 if action == "minus" else 1)
                        return
            return studio.ShanktuaryApp.handle_mouse_press(self, translated)
        for mode, rect in getattr(self, "design_mode_rects", {}).items():
            if self._design_hit(rect, event.x, event.y):
                self.set_mode(mode)
                return
        for rect, action in getattr(self, "concept_actions", []):
            if self._design_hit(rect, event.x, event.y):
                if action == "new":
                    self.create_new_session()
                elif action == "sessions":
                    self.set_mode(13)
                    return
                elif action == "club":
                    self.show_club_menu = True
                elif action == "tools":
                    self.set_mode(14)
                    return
                elif action == "hand":
                    self.is_left_handed = not self.is_left_handed
                self.draw_screen()
                return
        if event.x < RAIL or event.y < 152:
            return
        if self.view_mode == 8:
            from .lab_demo import active, toggle

            if self._design_hit(getattr(self, "swing_lab_demo_rect", None), event.x, event.y):
                toggle(self)
                return
            # A preview must never tare the connected hardware by accident.
            if active(self) and self._design_hit(
                getattr(self, "swing_lab_tare_rect", None), event.x, event.y
            ):
                return
        if self.view_mode in (9, 1, 12):
            from .concept_session import handle_session_click

            if handle_session_click(self, translated.x, translated.y):
                return
            from src.ui.contact_panel import handle_face_click

            if handle_face_click(self, translated.x, translated.y):
                return
        for x0, y0, x1, y1, shot_index in getattr(self, "design_shot_card_rects", []):
            rect = (x0, y0, x1, y1)
            if self.view_mode in (9, 12) and self._design_hit(
                rect, translated.x, translated.y
            ):
                if 0 <= shot_index < len(self.session_shots):
                    self.selected_shot_index = shot_index
                    self.current_shot = self.session_shots[shot_index]
                    self.draw_screen()
                return
        if self.view_mode == 13:
            from .concept_history import handle_click
            if handle_click(self, translated.x, translated.y):
                return
        if self.view_mode == 14:
            from .concept_tools import handle_click
            if handle_click(self, translated.x, translated.y):
                return
        if self.view_mode == 12:
            from .concept_overview import handle_click

            if handle_click(self, translated.x, translated.y):
                return
        if self.view_mode == 2:
            from .concept_metrics import handle_range_click

            if handle_range_click(self, translated.x, translated.y):
                return
        if self.view_mode == 4:
            from .concept_table import handle_click

            if handle_click(self, translated.x, translated.y):
                return
        if self.view_mode == 7:
            from .concept_workspaces import handle_fit_click

            if handle_fit_click(self, translated.x, translated.y):
                return
        if self.view_mode == 11:
            from .concept_workspaces import handle_index_click

            if handle_index_click(self, translated.x, translated.y):
                return
        if self.view_mode == 10:
            from .concept_workspaces import handle_setup_click

            if handle_setup_click(self, translated.x, translated.y):
                return
        if self.view_mode == 3:
            from .concept_workspaces import handle_dispersion_click

            if handle_dispersion_click(self, translated.x, translated.y):
                return
            for rect, submode in getattr(self, "design_dispersion_tab_rects", []):
                if self._design_hit(rect, translated.x, translated.y):
                    self.dispersion_view_submode = submode
                    self.draw_screen()
                    return
        old_rail = theme.RAIL_W
        theme.RAIL_W = RAIL
        try:
            return studio.ShanktuaryApp.handle_mouse_press(self, translated)
        finally:
            theme.RAIL_W = old_rail

    def handle_mouse_hover(self, event):
        return super().handle_mouse_hover(event)

    def handle_mouse_drag(self, event):
        from .concept_shell import RAIL

        old_rail = theme.RAIL_W
        theme.RAIL_W = RAIL
        try:
            return super().handle_mouse_drag(event)
        finally:
            theme.RAIL_W = old_rail

    def handle_mouse_release(self, event):
        return super().handle_mouse_release(event)
