"""The three calibrations run as ONE guided pass.

Board assignment, 50/50 stance calibration and stance-width measurement used
to be three separate buttons. The user stands on the boards for all three, so
running them separately meant three step-on/step-off cycles for what is really
one setup. These lock in that the flow chains, advances on hardware success,
and can be skipped or cancelled per step without stranding the rest.
"""
import sys

import pytest

sys.path.insert(0, "/home/sean/sps")

tk = pytest.importorskip("tkinter")


class FakeWizard:
    """Stands in for BoardAssignmentWizard."""

    threshold = 5.0

    def __init__(self):
        self.phase = "waiting_left"
        self.board_a, self.board_b = "A", "B"
        self.left_board = self.right_board = None

    def complete(self):
        self.phase = "complete"
        self.left_board, self.right_board = "A", "B"

    def get_status(self):
        return {
            "phase": self.phase,
            "is_complete": self.phase == "complete",
            "board_a_weight": 0.0,
            "board_b_weight": 0.0,
            "message": "",
        }

    def reset(self):
        self.phase = "idle"


class FakePM:
    """Minimal PressureManager surface the flow touches."""

    def __init__(self, board_mode="dual", boards=2):
        self.board_mode = board_mode
        self.is_simulator = False
        self._boards = boards
        self.assignment_wizard = None
        self.stance_width_mm = None
        self.calls = []
        self._align_active = False
        self._align_msg = ""
        self._width_state = "idle"

    # -- assignment --
    def start_assignment_wizard(self):
        self.calls.append("assign")
        if self._boards < 2:
            self.assignment_wizard = None
            return {"phase": "idle", "is_complete": False,
                    "message": "1 of 2 boards detected."}
        self.assignment_wizard = FakeWizard()
        return self.assignment_wizard.get_status()

    def reset_assignment_wizard(self):
        self.calls.append("assign_reset")
        if self.assignment_wizard:
            self.assignment_wizard.reset()
        return {"phase": "idle"}

    # -- 50/50 --
    def start_stance_alignment(self, duration_sec=4.0):
        self.calls.append("align")
        self._align_active = True
        self._align_msg = ""
        return {"status": "started"}

    def finish_align(self, ok=True):
        self._align_active = False
        self._align_msg = "✓ 50/50 Stance Calibrated" if ok else "Alignment failed: stand still"

    def get_alignment_status(self):
        return {"active": self._align_active, "message": self._align_msg,
                "remaining_sec": 1.0, "progress": 0.5, "in_lead_in": False}

    # -- stance width --
    def start_stance_width_calibration(self):
        self.calls.append("width")
        self._width_state = "waiting_left"
        return self.get_stance_width_status()

    def cancel_stance_width_calibration(self):
        self.calls.append("width_cancel")
        self._width_state = "idle"
        return self.get_stance_width_status()

    def finish_width(self, mm=420.0):
        self._width_state = "done"
        self.stance_width_mm = mm

    def get_stance_width_status(self):
        return {"state": self._width_state,
                "active": self._width_state not in ("idle", "done"),
                "instruction": "Shift left",
                "stance_width_mm": self.stance_width_mm}


@pytest.fixture
def app_and_pm():
    import shanktuary_performance_studio as studio
    import obs_server

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.geometry("1600x900")

    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.root = root
    app.canvas = tk.Canvas(root, width=1600, height=900)
    app.setup_flow_steps = []
    app.setup_flow_index = 0
    app.setup_flow_done = False
    app.setup_flow_error = ""
    app.show_board_assign_modal = False

    sentinel = object()
    original = getattr(obs_server, "pressure_manager", sentinel)
    pm = FakePM()
    obs_server.pressure_manager = pm

    yield app, pm, studio

    if original is sentinel:
        try:
            del obs_server.pressure_manager
        except AttributeError:
            pass
    else:
        obs_server.pressure_manager = original
    try:
        root.destroy()
    except Exception:
        pass


def test_dual_flow_runs_all_three_steps_in_order(app_and_pm):
    app, pm, _ = app_and_pm
    app.start_guided_setup()

    assert app.setup_flow_steps == ["assign", "align", "width"]
    assert app.show_board_assign_modal, "the flow must take over the screen"
    assert pm.calls == ["assign"], "only the first step may start"

    # Finishing assignment hands straight off to 50/50 -- no extra click.
    pm.assignment_wizard.complete()
    app.tick_setup_flow()
    assert app._flow_step() == "align"
    assert pm.calls == ["assign", "align"]

    # Finishing 50/50 hands off to stance width.
    pm.finish_align()
    app.tick_setup_flow()
    assert app._flow_step() == "width"
    assert pm.calls == ["assign", "align", "width"]

    pm.finish_width()
    app.tick_setup_flow()
    assert app.setup_flow_done, "flow should be complete after the last step"


def test_single_board_mode_skips_assignment(app_and_pm):
    """With one board there is no left/right to tell apart."""
    app, pm, _ = app_and_pm
    pm.board_mode = "single"
    app.start_guided_setup()

    assert app.setup_flow_steps == ["align", "width"]
    assert pm.calls == ["align"], "must not run board assignment on one board"


def test_skip_advances_without_running_the_step(app_and_pm):
    app, pm, _ = app_and_pm
    app.start_guided_setup()

    app._skip_setup_flow_step()
    assert app._flow_step() == "align", "skip must move to the next step"
    assert "align" in pm.calls

    app._skip_setup_flow_step()
    assert app._flow_step() == "width"


def test_cancel_stops_everything_mid_flow(app_and_pm):
    app, pm, _ = app_and_pm
    app.start_guided_setup()
    app._cancel_setup_flow()

    assert app.setup_flow_steps == []
    assert not app.setup_flow_done
    # Both cancellable subsystems must be told to stand down.
    assert "assign_reset" in pm.calls
    assert "width_cancel" in pm.calls


def test_a_failed_step_reports_and_does_not_advance(app_and_pm):
    app, pm, _ = app_and_pm
    app.start_guided_setup()
    pm.assignment_wizard.complete()
    app.tick_setup_flow()          # -> align
    assert app._flow_step() == "align"

    pm.finish_align(ok=False)
    app.tick_setup_flow()
    assert app._flow_step() == "align", "a failed step must not silently pass"
    assert "failed" in app.setup_flow_error.lower()


def test_one_board_refusal_surfaces_instead_of_a_dead_prompt(app_and_pm):
    app, pm, _ = app_and_pm
    pm._boards = 1
    app.start_guided_setup()

    assert app.setup_flow_error, "refusal must be reported to the caller"
    assert "2 boards" in app.setup_flow_error


def test_modal_renders_every_step_without_overlapping_text(app_and_pm):
    """The room-readable prompt must stay legible on all three steps."""
    app, pm, studio = app_and_pm
    app.start_guided_setup()
    w, h = 1600, 900

    for expected in ("assign", "align", "width"):
        assert app._flow_step() == expected
        app.canvas.delete("all")
        studio.ShanktuaryApp.draw_board_assign_modal(app, w, h)
        app.root.update_idletasks()

        texts = []
        for item in app.canvas.find_all():
            if app.canvas.type(item) != "text":
                continue
            bb = app.canvas.bbox(item)
            if bb:
                texts.append((app.canvas.itemcget(item, "text"), bb))

        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                (t1, a), (t2, b) = texts[i], texts[j]
                overlap = (a[0] < b[2] and b[0] < a[2]
                           and a[1] < b[3] and b[1] < a[3])
                assert not overlap, f"{expected}: {t1!r} overlaps {t2!r}"

        for text, bb in texts:
            assert bb[1] >= 0 and bb[3] <= h, f"{expected}: {text!r} off-screen"

        # Advance to the next step the way the hardware would.
        if expected == "assign":
            pm.assignment_wizard.complete()
        elif expected == "align":
            pm.finish_align()
        else:
            pm.finish_width()
        app.tick_setup_flow()

    assert app.setup_flow_done
