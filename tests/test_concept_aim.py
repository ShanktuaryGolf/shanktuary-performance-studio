"""The redesigned Aim dialog changes presentation, never native shot values."""
import math
from types import SimpleNamespace

import pytest

from src.ui import concept_aim as ui


def app():
    return SimpleNamespace(
        aim_modal_distance="20", aim_modal_lateral="12", concept_aim_tab="measure",
        show_aim_modal=True, aim_calibrating=False, aim_calib_shots=[],
        aim_offset_deg=0, draw_screen=lambda: None,
        concept_aim_rects=[((0,0,100,40),"nudge:0.1")],
    )


def test_measurement_preview_retains_feet_inches_contract():
    a=app()
    assert ui.angle(a)==pytest.approx(math.degrees(math.atan2(12,240)))
    a.aim_modal_distance=""
    assert ui.angle(a) is None


def test_nudge_changes_draft_geometry_only_and_preserves_units():
    a=app()
    a.set_aim_offset=lambda value: pytest.fail("Draft control must not persist calibration")
    before=ui.angle(a)
    assert ui.handle_click(a,10,10)
    assert ui.angle(a)==pytest.approx(before+0.1,abs=0.0001)
    assert a.aim_modal_distance=="20"
    assert a.aim_offset_deg==0


def test_side_control_changes_signed_draft_not_saved_offset():
    a=app()
    a.concept_aim_rects=[((0,0,100,40),"left")]
    ui.handle_click(a,10,10)
    assert float(a.aim_modal_lateral)==-12
    assert a.aim_offset_deg==0


def test_shot_calibration_cancel_stops_transient_collection():
    a=app()
    a.concept_aim_tab="shots"
    a.aim_calibrating=True
    a.aim_calib_shots=[{"test":1}]
    a.concept_aim_rects=[((0,0,100,40),"cancel")]
    ui.handle_click(a,10,10)
    assert not a.show_aim_modal and not a.aim_calibrating
    assert a.aim_calib_shots==[]
    assert a.aim_offset_deg==0


def test_apply_without_calibration_shots_keeps_modal_open():
    a=app()
    a.concept_aim_tab="shots"
    called=[]
    a.finish_aim_calibration=lambda: called.append(True)
    ui.apply(a)
    assert called==[True] and a.show_aim_modal
