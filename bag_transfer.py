#!/usr/bin/env python3
"""
Export / import My Bag club specs between machines.

The bag lives inside shanktuary_session_history.json alongside your shot
history, so copying that file between machines would overwrite the sessions
on the target. This moves ONLY the club specs and leaves shot history alone.

Export on the machine with the good specs:

    python3 bag_transfer.py export my_bag.json

Copy my_bag.json to the other machine (USB, cloud drive, email), then:

    python3 bag_transfer.py import my_bag.json

Import merges by club name: clubs in the file are updated or added, clubs
only on the target are left untouched, and shot history is never modified.
A timestamped backup of the history file is written before any change.

Use --dry-run with import to preview without writing.

The history file is located next to the app (the executable when frozen,
the source directory otherwise). Pass --file to point at it explicitly:

    python3 bag_transfer.py import my_bag.json --file "C:\\path\\to\\shanktuary_session_history.json"
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

HISTORY_NAME = "shanktuary_session_history.json"
BAG_KEYS = ("bag", "custom_clubs", "is_left_handed")


def default_history_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, HISTORY_NAME)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def cmd_export(args):
    src = args.file or default_history_path()
    if not os.path.exists(src):
        sys.exit(f"error: no history file at {src}\n"
                 f"       run the app once, or pass --file")
    data = load_json(src)
    if not isinstance(data, dict):
        sys.exit("error: history file is in an old list-only format with no bag")

    bag = data.get("bag") or []
    if not bag:
        sys.exit("error: no clubs found in the bag")

    payload = {
        "_format": "shanktuary_bag_export",
        "_version": 1,
        "_exported": datetime.now().isoformat(timespec="seconds"),
        "bag": bag,
        "custom_clubs": data.get("custom_clubs", []),
        "is_left_handed": bool(data.get("is_left_handed", False)),
    }
    save_json_atomic(args.outfile, payload)

    print(f"exported {len(bag)} clubs -> {args.outfile}")
    withspec = [c for c in bag if c.get("loft_deg")]
    print(f"  {len(withspec)} with a loft set")
    for c in bag:
        loft = c.get("loft_deg") or 0.0
        lie = c.get("lie_deg") or 0.0
        brand = " ".join(x for x in (c.get("brand"), c.get("model")) if x and x != "Generic")
        bits = []
        if loft:
            bits.append(f"loft {loft:.1f}")
        if lie:
            bits.append(f"lie {lie:.1f}")
        print(f"    {c.get('name',''):<10} {'  '.join(bits):<22} {brand}")


def cmd_import(args):
    if not os.path.exists(args.infile):
        sys.exit(f"error: {args.infile} not found")
    payload = load_json(args.infile)
    if payload.get("_format") != "shanktuary_bag_export":
        sys.exit("error: not a bag export file (wrong _format)")

    dst = args.file or default_history_path()
    incoming = payload.get("bag") or []
    if not incoming:
        sys.exit("error: export file contains no clubs")

    if os.path.exists(dst):
        data = load_json(dst)
        if not isinstance(data, dict):
            # old list-only format: preserve those sessions
            data = {"sessions": data if isinstance(data, list) else []}
    else:
        print(f"note: no history at {dst}, creating a fresh one")
        data = {"sessions": []}

    existing = data.get("bag") or []
    by_name = {c.get("name"): c for c in existing if isinstance(c, dict)}

    updated, added = [], []
    for club in incoming:
        name = club.get("name")
        if not name:
            continue
        if name in by_name:
            before = dict(by_name[name])
            by_name[name].update(club)
            if before != by_name[name]:
                updated.append(name)
        else:
            existing.append(dict(club))
            by_name[name] = existing[-1]
            added.append(name)

    data["bag"] = existing
    merged_custom = list(dict.fromkeys(
        list(data.get("custom_clubs") or []) + list(payload.get("custom_clubs") or [])
    ))
    data["custom_clubs"] = merged_custom
    data["is_left_handed"] = payload.get("is_left_handed", data.get("is_left_handed", False))

    nsess = len(data.get("sessions") or [])
    nshots = sum(len(s.get("shots", [])) for s in (data.get("sessions") or [])
                 if isinstance(s, dict))

    print(f"target: {dst}")
    print(f"  updated {len(updated)} clubs: {', '.join(updated) or '(none)'}")
    print(f"  added   {len(added)} clubs: {', '.join(added) or '(none)'}")
    print(f"  preserved {nsess} sessions / {nshots} shots")

    if args.dry_run:
        print("\ndry run, nothing written")
        return

    if os.path.exists(dst):
        backup = f"{dst}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(dst, backup)
        print(f"  backup: {backup}")

    save_json_atomic(dst, data)
    print("done -- restart the app to see the specs")


def main():
    ap = argparse.ArgumentParser(
        description="Move My Bag club specs between machines without touching shot history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="write club specs to a portable file")
    e.add_argument("outfile", nargs="?", default="my_bag.json")
    e.add_argument("--file", help="path to shanktuary_session_history.json")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import", help="merge club specs from a portable file")
    i.add_argument("infile", nargs="?", default="my_bag.json")
    i.add_argument("--file", help="path to shanktuary_session_history.json")
    i.add_argument("--dry-run", action="store_true", help="preview without writing")
    i.set_defaults(func=cmd_import)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
