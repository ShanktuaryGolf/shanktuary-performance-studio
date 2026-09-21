"""The guided pairing flow must make two-board pairing possible and legible.

Reported: with one board already paired, trying to pair both removed the
working board and never paired the second. Root cause was that every attempt
re-targeted the first board discovery returned; the already-paired branch then
tore its bond down. A user cannot see the console in a --windowed build, so
the failure was also completely silent.

These tests cover the state machine only -- no Bluetooth, no Tk.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hardware.pressure.pairing_flow import (
    DONE,
    FAILED,
    PROMPT,
    SEARCHING,
    STEP_OK,
    PairingFlow,
)

BOARD_1 = "001E35AAAAAA"
BOARD_2 = "001E35BBBBBB"


def _settle(flow, timeout=3.0):
    """Wait for the worker thread to leave SEARCHING."""
    end = time.time() + timeout
    while time.time() < end:
        if flow.status()["phase"] != SEARCHING:
            return flow.status()
        time.sleep(0.01)
    raise AssertionError("pairing flow never left SEARCHING")


class FakePairer:
    """Stands in for the Win32 pairing call, recording what it was asked for."""

    def __init__(self, boards, fail_with=None):
        self.boards = list(boards)
        self.fail_with = fail_with
        self.calls = []

    def __call__(self, discovery_timeout_mult=8, exclude_addresses=None,
                 log=print):
        excluded = list(exclude_addresses or [])
        self.calls.append(excluded)
        if self.fail_with:
            return {"success": False, "message": self.fail_with}
        remaining = [b for b in self.boards if b not in excluded]
        if not remaining:
            return {"success": False,
                    "message": "Only the board you already paired answered."}
        log(f"[i] Found Nintendo RVL-WBC-01 at {remaining[0]}")
        return {"success": True, "message": "paired", "address": remaining[0],
                "radio_address": "38FC983BB4DC", "method": "callback",
                "boards_seen": len(remaining)}


class TestSingleBoardFlow:
    def test_prompts_then_pairs(self):
        pairer = FakePairer([BOARD_1])
        flow = PairingFlow(target_count=1, pair_fn=pairer)

        st = flow.start()
        assert st["phase"] == PROMPT
        assert "SYNC" in st["headline"]
        assert st["action_label"] == "I pressed SYNC"

        flow.confirm_sync_pressed()
        st = _settle(flow)
        assert st["phase"] == DONE
        assert st["paired_count"] == 1

    def test_single_board_prompt_does_not_say_first(self):
        """With one board there is no 'first' -- that wording only confuses."""
        flow = PairingFlow(target_count=1, pair_fn=FakePairer([BOARD_1]))
        st = flow.start()
        assert "FIRST" not in st["headline"]


class TestTwoBoardFlow:
    def test_pairs_two_distinct_boards(self):
        pairer = FakePairer([BOARD_1, BOARD_2])
        flow = PairingFlow(target_count=2, pair_fn=pairer)

        flow.start()
        assert "FIRST" in flow.status()["headline"]

        flow.confirm_sync_pressed()
        st = _settle(flow)
        assert st["phase"] == STEP_OK, st
        assert st["paired_count"] == 1

        st = flow.advance()
        assert st["phase"] == PROMPT
        assert "SECOND" in st["headline"]

        flow.confirm_sync_pressed()
        st = _settle(flow)
        assert st["phase"] == DONE
        assert st["paired_count"] == 2

        got = [p["address"] for p in st["paired"]]
        assert got == [BOARD_1, BOARD_2], f"paired the same board twice: {got}"

    def test_second_search_excludes_the_first_board(self):
        """The core bug: without this the second attempt re-targets board 1."""
        pairer = FakePairer([BOARD_1, BOARD_2])
        flow = PairingFlow(target_count=2, pair_fn=pairer)

        flow.start()
        flow.confirm_sync_pressed()
        _settle(flow)
        flow.advance()
        flow.confirm_sync_pressed()
        _settle(flow)

        assert pairer.calls[0] == []
        assert BOARD_1 in pairer.calls[1], (
            f"second search did not exclude the first board: {pairer.calls[1]}"
        )

    def test_boards_paired_before_the_flow_are_excluded(self):
        """The reported scenario: one board was ALREADY paired beforehand, so
        it must not be re-selected when the user asks for two."""
        pairer = FakePairer([BOARD_1, BOARD_2])
        flow = PairingFlow(
            target_count=2, pair_fn=pairer,
            paired_fn=lambda: [{"address": BOARD_1}],
        )
        flow.start()
        flow.confirm_sync_pressed()
        st = _settle(flow)

        assert BOARD_1 in pairer.calls[0]
        assert st["paired"][0]["address"] == BOARD_2, (
            "flow re-paired the board that was already paired"
        )

    def test_a_working_board_is_kept_when_the_second_fails(self):
        """A failure on board 2 must not cost the user board 1."""
        pairer = FakePairer([BOARD_1, BOARD_2])
        flow = PairingFlow(target_count=2, pair_fn=pairer)
        flow.start()
        flow.confirm_sync_pressed()
        _settle(flow)
        flow.advance()

        pairer.fail_with = "No balance board answered."
        flow.confirm_sync_pressed()
        st = _settle(flow)

        assert st["phase"] == FAILED
        assert st["paired_count"] == 1, "lost the already-paired board"

        st = flow.retry()
        assert st["phase"] == PROMPT
        assert st["paired_count"] == 1
        assert "SECOND" in st["headline"]


class TestUserFacingMessaging:
    def test_failure_message_is_shown_not_just_logged(self):
        flow = PairingFlow(target_count=1,
                           pair_fn=FakePairer([], fail_with="Board is asleep."))
        flow.start()
        flow.confirm_sync_pressed()
        st = _settle(flow)

        assert st["phase"] == FAILED
        assert st["sub"] == "Board is asleep."
        assert st["action_label"] == "Try again"

    def test_progress_detail_is_surfaced_during_search(self):
        """The console narration is invisible in a windowed build, so the
        'what is happening now' line has to reach the UI."""
        flow = PairingFlow(target_count=1, pair_fn=FakePairer([BOARD_1]))
        flow.start()
        flow.confirm_sync_pressed()
        _settle(flow)
        # The fake logs a "Found ..." line, which maps to a friendly string.
        assert flow.paired[0]["address"] == BOARD_1

    def test_searching_state_reports_busy_and_blocks_cancel(self):
        import threading
        release = threading.Event()

        def _slow(**kw):
            release.wait(timeout=3)
            return {"success": True, "address": BOARD_1, "message": "ok",
                    "method": "callback"}

        flow = PairingFlow(target_count=1, pair_fn=_slow)
        flow.start()
        flow.confirm_sync_pressed()
        for _ in range(100):
            if flow.status()["busy"]:
                break
            time.sleep(0.01)

        st = flow.status()
        assert st["busy"] is True
        assert st["can_cancel"] is False
        release.set()
        _settle(flow)

    def test_double_confirm_does_not_start_two_searches(self):
        pairer = FakePairer([BOARD_1])
        flow = PairingFlow(target_count=1, pair_fn=pairer)
        flow.start()
        flow.confirm_sync_pressed()
        flow.confirm_sync_pressed()
        _settle(flow)
        assert len(pairer.calls) == 1, "impatient clicking started two searches"


class TestGuards:
    def test_rejects_silly_target_counts(self):
        for n in (0, 3, -1):
            with pytest.raises(ValueError):
                PairingFlow(target_count=n)

    def test_cancel_returns_to_idle(self):
        flow = PairingFlow(target_count=2, pair_fn=FakePairer([BOARD_1]))
        flow.start()
        st = flow.cancel()
        assert st["phase"] == "idle"

    def test_pairing_error_is_caught_not_raised(self):
        def _boom(**kw):
            raise RuntimeError("radio exploded")

        flow = PairingFlow(target_count=1, pair_fn=_boom)
        flow.start()
        flow.confirm_sync_pressed()
        st = _settle(flow)
        assert st["phase"] == FAILED
        assert "radio exploded" in st["sub"]
