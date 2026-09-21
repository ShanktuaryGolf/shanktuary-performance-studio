"""Guided, full-screen pairing flow for Wii Balance Boards.

Why this exists
---------------
Pairing used to be one "Pair Board" button whose entire narrative lived in a
console the user cannot see in a --windowed build. With two boards that was
not just opaque but wrong: every click re-targeted the first board found, so
a user with one board already paired could never reach the second, and the
already-paired branch would tear the working bond down instead.

This drives pairing as explicit numbered steps -- "Press SYNC on board 1",
then "board 2" -- so the user always knows which board to touch, what the app
is doing right now, and what happened. Addresses of boards already paired in
this run are excluded from each subsequent search, which is what makes the
two-board case work at all.

State only. Rendering lives in the Tk layer and the Bluetooth work is injected
via `pair_fn`/`paired_fn`, so the whole flow can be tested without a radio.
"""

from __future__ import annotations

import threading
import time

# Phases
IDLE = "idle"
PROMPT = "prompt"          # waiting for the user to press SYNC and confirm
SEARCHING = "searching"    # inquiry + pairing in flight
STEP_OK = "step_ok"        # one board done, more to go
DONE = "done"
FAILED = "failed"


class PairingFlow:
    """Sequential pairing of one or two balance boards.

    Typical use from the UI:

        flow = PairingFlow(target_count=2)
        flow.start()                 # -> PROMPT for board 1
        flow.confirm_sync_pressed()  # user pressed SYNC -> SEARCHING
        ... flow.status() each redraw ...
        flow.retry()  /  flow.cancel()
    """

    #: How long the board answers an inquiry after SYNC. Windows counts the
    #: inquiry window in 1.28s units; 8 ~= 10s, comfortably inside the window.
    DISCOVERY_MULT = 8

    def __init__(self, target_count: int = 1, pair_fn=None, paired_fn=None):
        if target_count not in (1, 2):
            raise ValueError("target_count must be 1 or 2")
        self.target_count = target_count
        self._pair_fn = pair_fn
        self._paired_fn = paired_fn

        self.phase = IDLE
        self.step = 1                      # which board we are on (1-based)
        self.paired: list[dict] = []       # results for boards done so far
        self.error = ""
        self.detail = ""                   # live progress line
        self._thread = None
        self._lock = threading.RLock()
        self._cancelled = False
        self._started_at = 0.0

    # -- lifecycle ------------------------------------------------------
    def start(self):
        """Begin the flow, prompting for the first board."""
        with self._lock:
            self.phase = PROMPT
            self.step = 1
            self.paired = []
            self.error = ""
            self.detail = ""
            self._cancelled = False
        return self.status()

    def cancel(self):
        """Abandon the flow. A search already in flight is left to finish on
        its own thread -- we simply stop caring about its result."""
        with self._lock:
            self._cancelled = True
            self.phase = IDLE
            self.detail = ""
        return self.status()

    def retry(self):
        """Re-prompt for the CURRENT step after a failure.

        Deliberately keeps `paired` intact: a board that paired successfully
        must not have to be re-done because a later one failed.
        """
        with self._lock:
            if self.phase not in (FAILED, PROMPT, STEP_OK):
                return self.status()
            self.phase = PROMPT
            self.error = ""
            self.detail = ""
            self._cancelled = False
        return self.status()

    def confirm_sync_pressed(self):
        """User says SYNC is blinking. Start the search on a worker thread."""
        with self._lock:
            if self.phase not in (PROMPT, STEP_OK):
                return self.status()
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self.phase = SEARCHING
            self.error = ""
            self.detail = "Looking for the board..."
            self._cancelled = False
            self._started_at = time.time()

        self._thread = threading.Thread(target=self._run_search, daemon=True)
        self._thread.start()
        return self.status()

    def advance(self):
        """Move from a completed step to the next prompt (or finish)."""
        with self._lock:
            if self.phase != STEP_OK:
                return self.status()
            if len(self.paired) >= self.target_count:
                self.phase = DONE
            else:
                self.step = len(self.paired) + 1
                self.phase = PROMPT
                self.detail = ""
        return self.status()

    # -- worker ---------------------------------------------------------
    def _run_search(self):
        already = [b["address"] for b in self.paired]
        # Also skip boards bonded before this flow started, so "pair the
        # second board" cannot silently re-select the first one.
        try:
            if self._paired_fn:
                for b in self._paired_fn() or []:
                    addr = b.get("address") if isinstance(b, dict) else None
                    if addr and addr not in already:
                        already.append(addr)
        except Exception:
            pass

        try:
            if self._pair_fn is None:
                raise RuntimeError("no pairing backend configured")
            result = self._pair_fn(
                discovery_timeout_mult=self.DISCOVERY_MULT,
                exclude_addresses=already,
                log=self._log,
            )
        except Exception as e:
            result = {"success": False, "message": f"Pairing error: {e}"}

        with self._lock:
            if self._cancelled:
                return
            if result.get("success"):
                self.paired.append({
                    "address": result.get("address", ""),
                    "method": result.get("method", ""),
                    "message": result.get("message", ""),
                })
                self.detail = ""
                if len(self.paired) >= self.target_count:
                    self.phase = DONE
                else:
                    self.phase = STEP_OK
            else:
                self.phase = FAILED
                self.error = result.get("message") or "Pairing failed."
                self.detail = ""

    def _log(self, line):
        """Surface the library's progress as a live UI line.

        The console narration is invisible in a --windowed build, so the one
        piece of it the user actually needs -- what is happening right now --
        is mirrored into the flow state.
        """
        text = str(line)
        for marker, friendly in (
            ("Scanning for", "Searching for the board..."),
            ("Found ", "Found the board — pairing..."),
            ("Sent ", "Sending the pairing PIN..."),
            ("already paired", "Board was already paired — reconnecting..."),
            ("Cleared previous bond", "Clearing the old pairing..."),
            ("Removed stale bond", "Cleared a stale pairing..."),
        ):
            if marker in text:
                with self._lock:
                    self.detail = friendly
                return

    # -- view model -----------------------------------------------------
    def status(self) -> dict:
        """Everything the UI needs for one redraw."""
        with self._lock:
            done = len(self.paired)
            dual = self.target_count == 2
            which = "FIRST" if self.step == 1 else "SECOND"

            if self.phase == PROMPT:
                headline = (f"Press SYNC on the {which} board" if dual
                            else "Press SYNC on the board")
                sub = ("Open the battery cover underneath and press the small "
                       "red SYNC button — its lights will blink.")
                action = "I pressed SYNC"
            elif self.phase == SEARCHING:
                headline = ("Pairing the " + which.lower() + " board..." if dual
                            else "Pairing the board...")
                sub = self.detail or "Looking for the board..."
                action = ""
            elif self.phase == STEP_OK:
                headline = "First board paired"
                sub = "Now do the same on your second board."
                action = "Next board"
            elif self.phase == DONE:
                headline = ("Both boards paired" if dual else "Board paired")
                sub = ("You can close this and assign left/right." if dual
                       else "You can close this — the board is ready.")
                action = "Done"
            elif self.phase == FAILED:
                headline = "That didn't work"
                sub = self.error
                action = "Try again"
            else:
                headline = ""
                sub = ""
                action = ""

            return {
                "phase": self.phase,
                "step": self.step,
                "target_count": self.target_count,
                "paired_count": done,
                "paired": list(self.paired),
                "headline": headline,
                "sub": sub,
                "action_label": action,
                "error": self.error,
                "detail": self.detail,
                "busy": self.phase == SEARCHING,
                "can_cancel": self.phase != SEARCHING,
                "elapsed": (time.time() - self._started_at
                            if self.phase == SEARCHING else 0.0),
            }


def make_pairing_flow(target_count: int = 1) -> PairingFlow:
    """Build a flow wired to the real Win32 pairing helpers."""
    from src.hardware.pressure import list_paired_boards, pair_balance_board
    return PairingFlow(target_count=target_count,
                       pair_fn=pair_balance_board,
                       paired_fn=list_paired_boards)
