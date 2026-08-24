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
        time.sleep(0.1)

        cal_bytes = bytearray()
        for _ in range(5):
            d = dev.read(64, timeout_ms=300)
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
            print("[!] Factory calibration read skipped (will use adaptive baseline).")

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
                    kg_tr = max(0.0, (tr - baseline[0]) / 25.0)
                    kg_br = max(0.0, (br - baseline[1]) / 25.0)
                    kg_tl = max(0.0, (tl - baseline[2]) / 25.0)
                    kg_bl = max(0.0, (bl - baseline[3]) / 25.0)

                total_kg = kg_tr + kg_br + kg_tl + kg_bl
                if packet_count % 15 == 0:
                    print(f"  Live Weight: {total_kg:5.1f} kg | TL:{kg_tl:4.1f} TR:{kg_tr:4.1f} BL:{kg_bl:4.1f} BR:{kg_br:4.1f}")
            time.sleep(0.01)

        print(f"[✓] Completed streaming test ({packet_count} packets processed).")
    except Exception as e:
        print(f"[!] Error communicating with device: {e}")
    finally:
        dev.close()

print("\n" + "=" * 60)
print("Diagnostic Complete.")
print("=" * 60)
