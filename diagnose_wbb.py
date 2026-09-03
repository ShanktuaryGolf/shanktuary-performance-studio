#!/usr/bin/env python3
"""Diagnostic script for Wii Balance Board on Windows."""

import os
import sys
import time

# The PIN helper lives in src/; make it importable when this script is run
# directly from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    print("    (The pairing PIN below does not need hidapi.)")
    hid = None

# 2. Enumerate all HID devices
devices = []
if hid is None:
    print("\n[!] Skipping HID scan (hidapi unavailable).")
else:
    print("\nScanning for HID devices...")
    try:
        devices = hid.enumerate()
        print(f"Total HID devices found: {len(devices)}")
    except Exception as e:
        print(f"[!] Error enumerating HID devices: {e}")
        devices = []

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
    # Do NOT exit here. "No board found" is exactly when the user needs the
    # pairing PIN printed at the end of this script -- exiting hid the one
    # piece of information that unblocks them.
    print("\n    The pairing PIN is printed at the end of this report.")

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

    try:
        # Use blocking mode during initialization
        dev.set_nonblocking(0)

        # Initialize extension controller
        print("Initializing extension controller...")
        # Write 0x55 to 0xA400F0
        dev.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55] + [0x00] * 15))
        time.sleep(0.05)
        # Write 0x00 to 0xA400FB
        dev.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00] + [0x00] * 15))
        time.sleep(0.05)

        # Read calibration from 0xA40024 (24 bytes)
        print("Reading factory calibration data...")
        dev.write(bytes([0x17, 0x04, 0xA4, 0x00, 0x24, 0x00, 0x18]))
        time.sleep(0.05)

        cal_bytes = bytearray()
        for _ in range(12):
            d = dev.read(64, 100)
            if d and d[0] == 0x21 and len(d) >= 22:
                # 0x21 report: byte 3 is (size-1)<<4 | err
                sz = ((d[3] >> 4) & 0x0F) + 1
                cal_bytes.extend(d[6:6+sz])
                if len(cal_bytes) >= 24:
                    break

        if len(cal_bytes) >= 24:
            import struct
            cals = struct.unpack(">12H", cal_bytes[:24])
            print(f"[✓] Factory calibration loaded:")
            print(f"    0kg  ref (TR,BR,TL,BL): {cals[0]}, {cals[1]}, {cals[2]}, {cals[3]}")
            print(f"    17kg ref (TR,BR,TL,BL): {cals[4]}, {cals[5]}, {cals[6]}, {cals[7]}")
            print(f"    34kg ref (TR,BR,TL,BL): {cals[8]}, {cals[9]}, {cals[10]}, {cals[11]}")
        else:
            print("[!] Factory calibration read skipped (will use adaptive baseline ~100 counts/kg).")

        # Turn LED ON: 0x11, 0x10
        dev.write(bytes([0x11, 0x10]))
        time.sleep(0.05)

        # Set continuous reporting mode: 0x12, 0x04, 0x32
        dev.write(bytes([0x12, 0x04, 0x32]))
        time.sleep(0.05)

        print("\nStreaming live weight in kilograms for 5 seconds (step on the board!)...")
        dev.set_nonblocking(1)
        start_t = time.time()
        packet_count = 0
        baseline = None

        while time.time() - start_t < 5.0:
            data = dev.read(64)
            if data and data[0] == 0x32 and len(data) >= 11:
                packet_count += 1
                import struct
                tr, br, tl, bl = struct.unpack(">HHHH", bytes(data[3:11]))
                if baseline is None:
                    baseline = (tr, br, tl, bl)

                # Weight in kg using factory calibration or adaptive delta
                if len(cal_bytes) >= 24:
                    def interp(raw, c0, c17, c34):
                        if raw <= c0: return 0.0
                        elif raw < c17: return 17.0 * (raw - c0) / max(1, c17 - c0)
                        else: return 17.0 + 17.0 * (raw - c17) / max(1, c34 - c17)
                    kg_tr = interp(tr, cals[0], cals[4], cals[8])
                    kg_br = interp(br, cals[1], cals[5], cals[9])
                    kg_tl = interp(tl, cals[2], cals[6], cals[10])
                    kg_bl = interp(bl, cals[3], cals[7], cals[11])
                else:
                    kg_tr = max(0.0, (tr - baseline[0]) / 100.0)
                    kg_br = max(0.0, (br - baseline[1]) / 100.0)
                    kg_tl = max(0.0, (tl - baseline[2]) / 100.0)
                    kg_bl = max(0.0, (bl - baseline[3]) / 100.0)

                total_kg = kg_tr + kg_br + kg_tl + kg_bl
                if packet_count % 15 == 0:
                    print(f"  Live Weight: {total_kg:5.1f} kg | TL:{kg_tl:4.1f} TR:{kg_tr:4.1f} BL:{kg_bl:4.1f} BR:{kg_br:4.1f}")
            time.sleep(0.01)

        print(f"[✓] Completed streaming test ({packet_count} packets processed).")
    except Exception as e:
        print(f"[!] Error communicating with device: {e}")
    finally:
        dev.close()

# 4. Simultaneous Dual-Board Balance Test (if 2+ boards found)
if len(wbb_candidates) >= 2:
    print("\n" + "=" * 60)
    print("  SIMULTANEOUS DUAL-BOARD BALANCE TEST")
    print("=" * 60)
    print("Opening both boards together...")

    dev1 = hid.device()
    dev2 = hid.device()
    try:
        dev1.open_path(wbb_candidates[0]["path"])
        dev2.open_path(wbb_candidates[1]["path"])
        print("[✓] Opened both board handles!")

        for dev, name in [(dev1, "Board 1"), (dev2, "Board 2")]:
            dev.set_nonblocking(0)
            dev.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55] + [0x00] * 15))
            time.sleep(0.05)
            dev.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00] + [0x00] * 15))
            time.sleep(0.05)
            dev.write(bytes([0x11, 0x10]))
            time.sleep(0.05)
            dev.write(bytes([0x12, 0x04, 0x32]))
            time.sleep(0.05)
            dev.set_nonblocking(1)

        print("\n>>> Stand naturally with ONE foot on Board 1 and ONE foot on Board 2 <<<")
        print("Streaming live balance for 10 seconds (Ctrl+C to stop)...\n")

        start_t = time.time()
        base1 = None
        base2 = None

        while time.time() - start_t < 10.0:
            d1 = dev1.read(64)
            d2 = dev2.read(64)

            w1, w2 = 0.0, 0.0

            if d1 and d1[0] == 0x32 and len(d1) >= 11:
                import struct
                tr, br, tl, bl = struct.unpack(">HHHH", bytes(d1[3:11]))
                if base1 is None:
                    base1 = (tr, br, tl, bl)
                w1 = max(0.0, (tr - base1[0] + br - base1[1] + tl - base1[2] + bl - base1[3]) / 25.0)

            if d2 and d2[0] == 0x32 and len(d2) >= 11:
                import struct
                tr, br, tl, bl = struct.unpack(">HHHH", bytes(d2[3:11]))
                if base2 is None:
                    base2 = (tr, br, tl, bl)
                w2 = max(0.0, (tr - base2[0] + br - base2[1] + tl - base2[2] + bl - base2[3]) / 25.0)

            tot = w1 + w2
            pct1 = (100.0 * w1 / tot) if tot > 0 else 50.0
            pct2 = (100.0 * w2 / tot) if tot > 0 else 50.0
            cop_x_mm = (w2 - w1) / tot * 200.0 if tot > 0 else 0.0

            print(f"\r  Board 1 (L): {w1:5.1f} kg ({pct1:4.1f}%) | Board 2 (R): {w2:5.1f} kg ({pct2:4.1f}%) | Total: {tot:5.1f} kg | CoP X: {cop_x_mm:+6.1f} mm", end="", flush=True)
            time.sleep(0.05)
        print()
    except Exception as e:
        print(f"\n[!] Dual test error: {e}")
    finally:
        dev1.close()
        dev2.close()

print("\n" + "=" * 60)
print("  BLUETOOTH PAIRING PIN")
print("=" * 60)
print("Windows asks for a PIN when you add the board. It is derived from")
print("THIS PC's Bluetooth adapter MAC, so it is different on every machine.")
print("A blinking board light means pairing never completed.\n")

try:
    from src.hardware.pressure.bluetooth_windows import (
        _try_linux_bluetoothctl,
        _try_linux_sysfs,
        _try_powershell_netadapter,
        _try_powershell_pnp,
        _try_registry,
        format_mac_display,
        get_host_bluetooth_mac,
        get_manual_mac_override,
        mac_has_zero_byte,
        mac_to_wii_pin_display,
    )

    override = get_manual_mac_override()
    if override:
        print(f"[i] Manual override in effect: {format_mac_display(override)}")
        print("    (from SHANKTUARY_BT_MAC or host_bt_mac in wbb_calibration.json)\n")

    # Show EVERY method's answer, not just the winner. If two disagree, the
    # PnP one is the liar -- it scrapes any 12 hex digits out of a device id
    # and a BTHENUM id contains the REMOTE address, not the host adapter.
    if sys.platform == "win32":
        methods = [
            ("Registry BTHPORT (authoritative)", _try_registry),
            ("PowerShell NetAdapter", _try_powershell_netadapter),
            ("PowerShell PnP InstanceId (unreliable)", _try_powershell_pnp),
        ]
    else:
        methods = [
            ("Linux sysfs", _try_linux_sysfs),
            ("Linux bluetoothctl", _try_linux_bluetoothctl),
        ]

    print("Detection methods:")
    seen = {}
    for label, fn in methods:
        try:
            got = fn()
        except Exception as e:
            got = None
            print(f"  [!] {label}: raised {e}")
        if got:
            seen[label] = got
            print(f"  [+] {label:40s} {format_mac_display(got)}")
            print(f"      {'':40s} PIN: {mac_to_wii_pin_display(got)}")
        else:
            print(f"  [-] {label:40s} (no result)")

    distinct = set(seen.values())
    if len(distinct) > 1:
        print("\n[!] Methods DISAGREE. Trust the registry value; if pairing")
        print("    fails, try each PIN in turn.")

    mac = get_host_bluetooth_mac()
    print()
    if mac:
        print(f"  Adapter MAC : {format_mac_display(mac)}")
        print(f"  PAIRING PIN : {mac_to_wii_pin_display(mac)}")
        if mac_has_zero_byte(mac):
            print("\n  [!] This PIN contains a NULL byte (shown as ␀). Some")
            print("      Windows prompts cannot accept it. If pairing fails,")
            print("      use a different Bluetooth adapter.")
        print("\n  Enter that PIN when Windows asks. It is raw characters, not")
        print("  digits -- copy it from the app's Setup page rather than")
        print("  retyping it.")
    else:
        print("  [!] Could not determine the host adapter MAC.")
        print("      Find it manually:")
        print("        Windows : Settings > Bluetooth & devices > Device info")
        print("                  or: reg query HKLM\\SYSTEM\\CurrentControlSet"
              "\\Services\\BTHPORT\\Parameters /v LocalDeviceAddress")
        print("        Linux   : bluetoothctl list")
        print("      Then set it permanently, either:")
        print("        set SHANKTUARY_BT_MAC=AABBCCDDEEFF")
        print('        or add "host_bt_mac": "AABBCCDDEEFF" to')
        print("        ~/.shanktuary/wbb_calibration.json")
except Exception as e:
    print(f"[!] PIN helper unavailable: {e}")

print("\n" + "=" * 60)
print("Diagnostic Complete.")
print("=" * 60)
