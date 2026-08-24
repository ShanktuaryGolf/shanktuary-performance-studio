#!/usr/bin/env python3
"""Diagnostic script for Wii Balance Board on Windows."""

import sys
import time

print("=" * 60)
print("  Wii Balance Board Windows Diagnostic Tool")
print("=" * 60)
print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")
print()

# 1. Test hidapi import
try:
    import hid
    print("[✓] hidapi module is installed successfully.")
except ImportError:
    print("[✗] hidapi is NOT installed!")
    print("    Please run: pip install hidapi")
    sys.exit(1)

# 2. Enumerate all HID devices
print("\nScanning for HID devices...")
try:
    devices = hid.enumerate()
    print(f"Total HID devices found: {len(devices)}")
except Exception as e:
    print(f"[!] Error enumerating HID devices: {e}")
    sys.exit(1)

wbb_candidates = []
for idx, d in enumerate(devices):
    vid = d.get("vendor_id", 0)
    pid = d.get("product_id", 0)
    prod = str(d.get("product_string", ""))
    mfg = str(d.get("manufacturer_string", ""))
    path = d.get("path", b"")
    
    # Check for Nintendo VID 0x057E or keywords
    is_nintendo = (vid == 0x057E)
    is_wbb = is_nintendo or "balance" in prod.lower() or "rvl-wbc" in prod.lower() or "rvl-wbc" in str(path).lower() or "wii" in prod.lower()
    
    if is_wbb:
        wbb_candidates.append(d)
        print(f"\n[★ MATCH] Found candidate #{len(wbb_candidates)}:")
        print(f"    Vendor ID : 0x{vid:04X} ({mfg})")
        print(f"    Product ID: 0x{pid:04X} ({prod})")
        print(f"    Path      : {path}")

if not wbb_candidates:
    print("\n[!] No Wii Balance Board found in HID devices.")
    print("    Checklist:")
    print("    1. Is Bluetooth turned ON in Windows?")
    print("    2. Did you press the red SYNC button in the battery compartment (LEDs blinking)?")
    print("    3. Is 'Nintendo RVL-WBC-01' listed as 'Connected' in Windows Bluetooth Settings?")
    print("\nListing first 10 other HID devices found:")
    for d in devices[:10]:
        print(f"  VID: 0x{d.get('vendor_id', 0):04X} PID: 0x{d.get('product_id', 0):04X} | {d.get('product_string', '')} | {d.get('manufacturer_string', '')}")
    sys.exit(0)

# 3. Test opening each candidate
print(f"\nTesting connection to {len(wbb_candidates)} board(s)...")
for idx, cand in enumerate(wbb_candidates):
    print(f"\n--- Testing Board #{idx + 1} ---")
    dev = hid.device()
    try:
        if cand.get("path"):
            dev.open_path(cand["path"])
        else:
            dev.open(cand["vendor_id"], cand["product_id"])
        print(f"[✓] Successfully opened HID device handle!")
    except Exception as e:
        print(f"[✗] Failed to open device handle: {e}")
        continue

    # Try sending wake report
    try:
        dev.set_nonblocking(0)
        # Turn LED ON: 0x11, 0x10
        ret_led = dev.write(bytes([0x11, 0x10]))
        print(f"[✓] Sent LED ON report (ret={ret_led}). Look at the board: is the blue LED solid?")
        time.sleep(0.1)

        # Set continuous reporting mode: 0x12, 0x04, 0x32
        ret_rep = dev.write(bytes([0x12, 0x04, 0x32]))
        print(f"[✓] Sent Reporting Mode 0x32 report (ret={ret_rep})")
        time.sleep(0.1)

        # Try reading for 3 seconds
        print("Reading sensor packets for 3 seconds (try stepping on the board)...")
        dev.set_nonblocking(1)
        start_t = time.time()
        packet_count = 0
        while time.time() - start_t < 3.0:
            data = dev.read(64)
            if data:
                packet_count += 1
                report_id = data[0]
                if packet_count <= 5 or packet_count % 30 == 0:
                    print(f"  [Packet #{packet_count}] Report ID: 0x{report_id:02X}, Len: {len(data)}, Hex: {bytes(data[:12]).hex()}")
            time.sleep(0.01)

        print(f"[✓] Received {packet_count} data packets in 3 seconds.")
        if packet_count == 0:
            print("[!] No packets received. Trying alternate reporting mode (0x12, 0x00, 0x32)...")
            dev.write(bytes([0x12, 0x00, 0x32]))
    except Exception as e:
        print(f"[!] Error communicating with device: {e}")
    finally:
        dev.close()

print("\n" + "=" * 60)
print("Diagnostic Complete.")
print("=" * 60)
