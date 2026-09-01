"""Regression tests for bugs found running the GSPro poller end to end.

1. The poll loop skipped its sleep on the idle/enriching paths, so it spun a
   CPU core at 100% and emitted ~3 MB of duplicate status text in 15 seconds.
2. Repeated status lines were emitted on every poll, burying real events.
3. The club key's case sensitivity silently dropped the club name, which
   would mis-attribute GSPro shots to whatever club the UI had selected.
"""

import json
import os
import sqlite3
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gspro.mapper import parse_shot_row  # noqa: E402
from src.gspro.poller import GsproPoller  # noqa: E402


def _make_db(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE DrivingRangeShot (ID INTEGER PRIMARY KEY AUTOINCREMENT,"
        " DateCreated TEXT, ShotData TEXT)"
    )
    for shot in rows:
        conn.execute(
            "INSERT INTO DrivingRangeShot (DateCreated, ShotData) VALUES (?,?)",
            ("2026-09-01T10:00:00", json.dumps(shot)),
        )
    conn.commit()
    return conn


def _complete_shot(**over):
    shot = {
        "club": "7 Iron", "Carry": 150.0, "TotalDistance": 158.0,
        "Offline": -4.0, "BallSpeed": 105.0, "VLA": 18.0, "HLA": -1.2,
        "TotalSpin": 6200, "rawSpinAxis": -3.0,
    }
    shot.update(over)
    return shot


# -- club key casing -----------------------------------------------------

def test_club_is_read_from_either_key_casing():
    """SimRead uses lowercase 'club'; a PascalCase 'Club' must still work."""
    for key in ("club", "Club"):
        row = {
            "id": 1, "date_created": "x",
            "shot_data": json.dumps({key: "8 Iron", "Carry": 168.0}),
        }
        assert parse_shot_row(row).get("club") == "8 Iron", key


def test_absent_club_stays_none_rather_than_inventing_one():
    row = {"id": 1, "date_created": "x", "shot_data": json.dumps({"Carry": 168.0})}
    assert parse_shot_row(row).get("club") is None


# -- poll loop pacing ----------------------------------------------------

def test_idle_loop_paces_itself_instead_of_busy_spinning(tmp_path):
    """The idle path must sleep. Without it the loop ran thousands of polls
    per second; here we assert it stays near the configured interval."""
    db = tmp_path / "GSPro.db"
    conn = _make_db(db, [_complete_shot()])
    conn.close()

    polls = []
    original = GsproPoller._read_row

    def counting_read(self):
        polls.append(time.monotonic())
        return original(self)

    GsproPoller._read_row = counting_read
    try:
        poller = GsproPoller(on_shot=lambda p, m: None, db_path=str(db),
                             poll_interval_s=0.1, on_status=lambda m: None)
        t = threading.Thread(target=poller.run, daemon=True)
        t.start()
        time.sleep(1.0)
        poller.stop()
        t.join(timeout=3)
    finally:
        GsproPoller._read_row = original

    # ~10 polls expected in 1s at 0.1s interval. The pre-fix busy loop did
    # tens of thousands; anything above a small multiple means no sleep.
    assert len(polls) <= 30, f"poll loop is busy-spinning: {len(polls)} polls in 1s"
    assert len(polls) >= 3, f"poll loop is not running: {len(polls)} polls"


def test_idle_status_is_not_repeated_every_poll(tmp_path):
    """Identical consecutive status lines must be emitted once, not forever."""
    db = tmp_path / "GSPro.db"
    conn = _make_db(db, [_complete_shot()])
    conn.close()

    messages = []
    poller = GsproPoller(on_shot=lambda p, m: None, db_path=str(db),
                         poll_interval_s=0.05, on_status=messages.append)
    t = threading.Thread(target=poller.run, daemon=True)
    t.start()
    time.sleep(1.0)
    poller.stop()
    t.join(timeout=3)

    waiting = [m for m in messages if "waiting for a fresh" in m]
    assert len(waiting) <= 2, f"idle status repeated {len(waiting)} times"


def test_stop_is_honoured_promptly(tmp_path):
    db = tmp_path / "GSPro.db"
    conn = _make_db(db, [_complete_shot()])
    conn.close()

    poller = GsproPoller(on_shot=lambda p, m: None, db_path=str(db),
                         poll_interval_s=0.1, on_status=lambda m: None)
    t = threading.Thread(target=poller.run, daemon=True)
    t.start()
    time.sleep(0.3)
    poller.stop()
    t.join(timeout=3)
    assert not t.is_alive(), "poller did not stop"


def test_a_new_row_is_emitted_and_the_baseline_is_not_replayed(tmp_path):
    db = tmp_path / "GSPro.db"
    conn = _make_db(db, [_complete_shot(club="7 Iron")])

    got = []
    poller = GsproPoller(on_shot=lambda p, m: got.append(p), db_path=str(db),
                         poll_interval_s=0.05, on_status=lambda m: None)
    t = threading.Thread(target=poller.run, daemon=True)
    t.start()
    time.sleep(0.4)
    assert got == [], "pre-existing row was replayed as a live shot"

    conn.execute(
        "INSERT INTO DrivingRangeShot (DateCreated, ShotData) VALUES (?,?)",
        ("2026-09-01T10:05:00", json.dumps(_complete_shot(club="8 Iron"))),
    )
    conn.commit()

    deadline = time.time() + 5
    while time.time() < deadline and not got:
        time.sleep(0.05)
    poller.stop()
    t.join(timeout=3)
    conn.close()

    assert len(got) == 1, f"expected exactly one shot, got {len(got)}"
    assert got[0]["_source"] == "gspro"
    assert got[0]["_gspro"]["club"] == "8 Iron"
