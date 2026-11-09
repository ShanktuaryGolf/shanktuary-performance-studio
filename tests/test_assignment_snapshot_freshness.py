"""Completed assignment diagnostics are history, not a live weight feed."""
from copy import deepcopy

import pytest

import src.hardware.pressure.connection as connection
from src.hardware.pressure.connection import AssignmentPhase, BoardAssignmentWizard


@pytest.fixture
def wizard(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(connection.time, "monotonic", lambda: now[0])
    wizard = BoardAssignmentWizard("device-a", "device-b")
    wizard.start()
    wizard.board_diagnostics = {
        key: dict(device_id=f"device-{key}", fresh=True, is_open=True,
                  last_sample_timestamp=99.9, last_packet_timestamp=100,
                  sample_age_seconds=0.1, packet_age_seconds=0,
                  raw_cells={"top_left": 2800})
        for key in ("a", "b")
    }
    return wizard, now


def complete(wizard):
    assert wizard.update(70, 0)[0] == AssignmentPhase.WAITING_RIGHT
    assert wizard.update(35, 36)[0] == AssignmentPhase.COMPLETE


def test_completion_immediately_marks_weights_and_diagnostics_historical(wizard):
    wiz, _ = wizard
    complete(wiz)
    status = wiz.get_status()
    assert status["phase"] == "complete" and status["is_complete"]
    assert "successfully assigned" in status["message"]
    assert status["diagnostics_source"] == "assignment_completion_snapshot"
    assert status["snapshot_timestamp"] == 100
    assert status["board_a_weight"] == 35 and status["board_b_weight"] == 36
    assert not status["board_a_weight_valid"] and not status["board_b_weight_valid"]
    for key in ("a", "b"):
        detail = status["boards"][key]
        assert detail["historical"] and detail["fresh_at_snapshot"]
        assert not detail["fresh"]
        assert detail["sample_age_seconds"] == 0.1
        assert detail["packet_age_seconds"] == 0
    assert (wiz.left_board, wiz.right_board) == ("device-a", "device-b")


def test_snapshot_ages_increase_without_mutating_saved_observations(wizard):
    wiz, now = wizard
    complete(wiz)
    saved = deepcopy(wiz.board_diagnostics)
    first = wiz.get_status()
    now[0] = 108.25
    second = wiz.get_status()
    assert second["snapshot_timestamp"] == first["snapshot_timestamp"] == 100
    assert second["boards"]["a"]["sample_age_seconds"] == 8.35
    assert second["boards"]["a"]["packet_age_seconds"] == 8.25
    assert second["boards"]["a"]["last_sample_timestamp"] == 99.9
    assert second["boards"]["a"]["fresh_at_snapshot"]
    assert not second["board_a_weight_valid"]
    assert wiz.board_diagnostics == saved
    second["boards"]["a"]["raw_cells"]["top_left"] = 0
    assert wiz.board_diagnostics == saved


def test_completed_status_never_polls_or_substitutes_current_hardware(wizard):
    wiz, now = wizard

    class Board:
        def read(self):
            pytest.fail("Completed wizard must not read hardware")

        def get_diagnostics(self):
            pytest.fail("Completed wizard must not substitute live diagnostics")

        def open(self):
            pytest.fail("Completed wizard must not open handles")

        def close(self):
            pytest.fail("Completed wizard must not close handles")

    wiz.board_a, wiz.board_b = Board(), Board()
    complete(wiz)
    now[0] += 10
    status = wiz.get_status()
    assert status["boards"]["a"]["raw_cells"] == {"top_left": 2800}
    assert status["boards"]["a"]["sample_age_seconds"] == 10.1
    assert not status["board_a_weight_valid"]
    assert wiz.left_board is wiz.board_a and wiz.right_board is wiz.board_b


@pytest.mark.parametrize("timestamp", [None, float("nan"), float("inf"), "unknown"])
def test_snapshot_missing_or_invalid_timestamps_do_not_claim_current_ages(wizard, timestamp):
    wiz, _ = wizard
    for detail in wiz.board_diagnostics.values():
        detail["last_sample_timestamp"] = timestamp
        detail["last_packet_timestamp"] = timestamp
    complete(wiz)
    detail = wiz.get_status()["boards"]["a"]
    assert detail["sample_age_seconds"] is None
    assert detail["packet_age_seconds"] is None
    assert not detail["fresh"]


def test_no_diagnostics_still_cannot_mark_completed_demo_weights_current(wizard):
    wiz, _ = wizard
    wiz.board_diagnostics = {}
    complete(wiz)
    status = wiz.get_status()
    assert status["boards"] == {}
    assert status["is_complete"]
    assert not status["board_a_weight_valid"] and not status["board_b_weight_valid"]


def test_repeated_update_preserves_completion_snapshot(wizard):
    wiz, now = wizard
    complete(wiz)
    now[0] = 120
    phase, _ = wiz.update(70, 0)
    status = wiz.get_status()
    assert phase == AssignmentPhase.COMPLETE
    assert status["snapshot_timestamp"] == 100
    assert status["board_a_weight"] == 35 and status["board_b_weight"] == 36
    assert (wiz.left_board, wiz.right_board) == ("device-a", "device-b")


def test_active_assignment_retains_freshness_semantics(wizard):
    wiz, _ = wizard
    status = wiz.get_status()
    assert status["diagnostics_source"] == "assignment"
    assert status["snapshot_timestamp"] is None
    assert status["board_a_weight_valid"] and status["board_b_weight_valid"]
    assert status["boards"]["a"]["fresh"]
    assert "historical" not in status["boards"]["a"]


@pytest.mark.parametrize("operation", ["reset", "start"])
def test_reset_and_restart_remove_completion_metadata(wizard, operation):
    wiz, _ = wizard
    complete(wiz)
    getattr(wiz, operation)()
    status = wiz.get_status()
    assert not status["is_complete"]
    assert status["snapshot_timestamp"] is None
    assert status["diagnostics_source"] == "assignment"
    assert status["boards"] == {}
