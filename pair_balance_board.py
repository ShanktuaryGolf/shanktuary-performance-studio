"""Pair a Wii Balance Board from the command line (Windows).

Standalone so pairing can be tested and debugged without launching the GUI,
and so a failure prints a real reason instead of vanishing into a --windowed
build with no console.

    python3 pair_balance_board.py            # find a board and pair it
    python3 pair_balance_board.py --info     # radios + PIN only, pair nothing
    python3 pair_balance_board.py --forget   # drop existing bonds first
    python3 pair_balance_board.py --timeout 12

Why this exists at all: the board's PIN is six raw binary bytes, which the
Windows "Add a device" PIN box cannot carry (control characters are rejected,
non-ASCII is re-encoded). This sends the PIN through the Win32 Bluetooth API
instead, where it is passed as bytes plus an explicit length.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.hardware.pressure import windows_pairing as wp  # noqa: E402
from src.hardware.pressure.bluetooth_windows import (  # noqa: E402
    describe_pin_entry,
    format_mac_display,
    get_host_bluetooth_mac,
    mac_to_wii_pin_display,
)


def show_info() -> int:
    print("=" * 60)
    print("  WII BALANCE BOARD — PAIRING INFO")
    print("=" * 60)

    if not wp.is_available():
        print(f"\n[!] Native pairing unavailable on {sys.platform}.")
        print("    The Win32 Bluetooth API (bthprops.cpl) is Windows-only.")
        print("    On Linux, pair with bluetoothctl instead.")
    else:
        radios = wp.list_radios()
        if not radios:
            print("\n[!] No Bluetooth radio found. Is Bluetooth switched on?")
            return 1
        print(f"\nLive Bluetooth radio(s): {len(radios)}")
        for r in radios:
            pin = wp.pin_bytes_for_host(r["address"])
            print(f"  {format_mac_display(r['address'])}  {r['name']}")
            print(f"    PIN bytes : {' '.join(f'{b:02X}' for b in pin)}")
            print(f"    PIN shown : {mac_to_wii_pin_display(r['address'])}")
            print(f"    {describe_pin_entry(r['address'])}")

    mac = get_host_bluetooth_mac()
    print(f"\nApp-resolved adapter MAC: "
          f"{format_mac_display(mac) if mac else '(none)'}")
    if mac:
        print(f"  {describe_pin_entry(mac)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pair a Wii Balance Board.")
    ap.add_argument("--info", action="store_true",
                    help="Show radios and PIN details, pair nothing.")
    ap.add_argument("--forget", action="store_true",
                    help="Remove any existing bond before pairing.")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="Discovery time in seconds (default 10).")
    args = ap.parse_args()

    if args.info:
        return show_info()

    if not wp.is_available():
        print(f"[!] Native pairing is Windows-only (this is {sys.platform}).")
        print("    On Linux use: python3 -c "
              "'from src.hardware.pressure import connect_board; connect_board()'")
        return 2

    # Windows counts the inquiry window in units of 1.28s.
    mult = max(1, min(48, round(args.timeout / 1.28)))

    print("=" * 60)
    print("  WII BALANCE BOARD — PAIRING")
    print("=" * 60)
    print("\nPress the red SYNC button inside the battery compartment NOW.")
    print("The board only answers for about 20 seconds after SYNC.\n")

    result = wp.pair_balance_board(discovery_timeout_mult=mult,
                                   forget_existing=args.forget,
                                   log=print)

    print("\n" + "-" * 60)
    if result["success"]:
        print(f"[OK] {result['message']}")
        print(f"     Board  : {format_mac_display(result['address'])}")
        print(f"     Radio  : {format_mac_display(result['radio_address'])}")
        print(f"     Method : {result['method']}")
        print("\nThe board's light should now be solid. Start the app and")
        print("open the Setup page to confirm it is detected.")
        return 0

    print(f"[FAIL] {result['message']}")
    print(f"       Boards seen during discovery: {result['boards_seen']}")
    print("\nThings worth trying:")
    print("  * Press SYNC again immediately before re-running this.")
    print("  * Re-run with --forget to clear a stale/half-finished bond.")
    print("  * Remove 'Nintendo RVL-WBC-01' in Windows Bluetooth settings.")
    print("  * Fresh batteries — a weak board drops the link mid-pairing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
