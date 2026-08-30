"""Bluetooth pairing helper for Wii Balance Board.

On Linux: automated via bluetoothctl.
On Windows: manual pairing through Windows Bluetooth settings.
"""

import sys


def connect_board() -> None:
    """Platform-dispatched board connection helper."""
    if sys.platform == "linux":
        _connect_linux()
    elif sys.platform == "win32":
        _connect_windows()
    else:
        print(f"Unsupported platform: {sys.platform}")
        print("Pair the Wii Balance Board manually via your OS Bluetooth settings.")


def _connect_linux() -> None:
    """Scan for and pair the Wii Balance Board using bluetoothctl."""
    import subprocess
    import time

    WBB_OUI = "00:1E:35"  # Nintendo OUI prefix for Wii accessories
    timeout = 15

    print(f"Scanning for Wii Balance Board ({timeout}s)...")
    print("Press the red SYNC button inside the battery compartment.")

    # Start scanning
    subprocess.run(["bluetoothctl", "scan", "on"], timeout=2,
                   capture_output=True, text=True)
    time.sleep(timeout)
    subprocess.run(["bluetoothctl", "scan", "off"], timeout=2,
                   capture_output=True, text=True)

    # List discovered devices
    result = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True)
    mac = None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            addr = parts[1]
            name = " ".join(parts[2:])
            if addr.startswith(WBB_OUI) or "Balance" in name or "Wii" in name:
                mac = addr
                break

    if mac is None:
        print("Wii Balance Board not found. Make sure the SYNC button was pressed.")
        return

    # Pair, trust, connect
    for cmd in [f"pair {mac}", f"trust {mac}", f"connect {mac}"]:
        result = subprocess.run(
            ["bluetoothctl", cmd.split()[0], mac],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"bluetoothctl {cmd} failed: {result.stderr.strip()}")
            return
        time.sleep(1)

    print(f"Connected to {mac}")


def _connect_windows() -> None:
    """Print instructions for pairing the board on Windows."""
    print("=== Wii Balance Board — Windows Pairing ===")
    print()
    print("1. Open Windows Settings > Bluetooth & devices")
    print("2. Click 'Add device' > Bluetooth")
    print("3. Press the red SYNC button inside the board's battery compartment")
    print("4. Select 'Nintendo RVL-WBC-01' when it appears")
    print("5. Once paired, click 'Connect Board' in the app")


from enum import Enum
from typing import Any, Optional, Tuple


class AssignmentPhase(str, Enum):
    IDLE = "idle"
    WAITING_LEFT = "waiting_left"
    WAITING_RIGHT = "waiting_right"
    COMPLETE = "complete"


class BoardAssignmentWizard:
    """Manages the interactive step-on-board calibration process.
    
    1. Phase WAITING_LEFT:
       User is prompted: 'Step on the board under your LEFT foot'
       Watches Board A and Board B.
       When one board registers > weight_threshold (default 5.0 kg) and the other < weight_threshold:
       Assigns that board as Left and the remaining board as candidate Right.
       Advances to WAITING_RIGHT.
       
    2. Phase WAITING_RIGHT:
       User is prompted: 'Now step on the board under your RIGHT foot'
       Watches the assigned Right board.
       When it registers > weight_threshold:
       Advances to COMPLETE.
    """
    WEIGHT_THRESHOLD = 5.0  # kg

    def __init__(self, board_a: Any | None = None, board_b: Any | None = None, threshold: float = 5.0):
        self.board_a = board_a
        self.board_b = board_b
        self.threshold = threshold
        self.phase = AssignmentPhase.IDLE
        self.left_board = None
        self.right_board = None
        self.board_a_weight = 0.0
        self.board_b_weight = 0.0
        self.message = ""

    def start(self, board_a: Any | None = None, board_b: Any | None = None):
        if board_a is not None:
            self.board_a = board_a
        if board_b is not None:
            self.board_b = board_b
        self.phase = AssignmentPhase.WAITING_LEFT
        self.left_board = None
        self.right_board = None
        self.board_a_weight = 0.0
        self.board_b_weight = 0.0
        self.message = "Step on the board under your LEFT foot (>5kg)"

    def reset(self):
        self.phase = AssignmentPhase.IDLE
        self.left_board = None
        self.right_board = None
        self.board_a_weight = 0.0
        self.board_b_weight = 0.0
        self.message = ""

    def update(self, weight_a: float, weight_b: float) -> tuple[AssignmentPhase, str]:
        self.board_a_weight = max(0.0, weight_a)
        self.board_b_weight = max(0.0, weight_b)

        if self.phase == AssignmentPhase.WAITING_LEFT:
            diff = self.board_a_weight - self.board_b_weight
            if self.board_a_weight > self.threshold and diff >= self.threshold:
                self.left_board = self.board_a
                self.right_board = self.board_b
                self.phase = AssignmentPhase.WAITING_RIGHT
                self.message = "Now step on the board under your RIGHT foot"
            elif self.board_b_weight > self.threshold and -diff >= self.threshold:
                self.left_board = self.board_b
                self.right_board = self.board_a
                self.phase = AssignmentPhase.WAITING_RIGHT
                self.message = "Now step on the board under your RIGHT foot"

        elif self.phase == AssignmentPhase.WAITING_RIGHT:
            right_weight = self.board_a_weight if self.right_board == self.board_a else self.board_b_weight
            if right_weight > self.threshold:
                self.phase = AssignmentPhase.COMPLETE
                self.message = "✓ Both boards successfully assigned!"

        return self.phase, self.message

    def get_status(self) -> dict:
        return {
            "phase": self.phase.value if hasattr(self.phase, "value") else str(self.phase),
            "message": self.message,
            "board_a_weight": round(self.board_a_weight, 1),
            "board_b_weight": round(self.board_b_weight, 1),
            "is_complete": self.phase == AssignmentPhase.COMPLETE,
        }
