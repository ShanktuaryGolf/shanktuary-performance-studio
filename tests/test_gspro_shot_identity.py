"""GSPro shots must carry an identity so their pressure traces can be found.

Nova payloads always have timestamp_ns, which shot_trace_id() keys on. GSPro
rows had neither shotId nor timestamp_ns, so every GSPro shot's trace saved
as "None.json.gz", each overwriting the last, and no shot could be reviewed.
"""

import json
import os
import sqlite3
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gspro.poller import GsproPoller  # noqa: E402
from src.processing.pressure import PressureTraceStore, shot_trace_id  # noqa: E402


def _row(row_id, carry):
    shot = {"club": "7 Iron", "Carry": carry, "TotalDistance": carry + 8,
            "Offline": -4.0, "BallSpeed": 105.0, "VLA": 18.0, "HLA": -1.2,
            "TotalSpin": 6200, "rawSpinAxis": -3.0}
    return {"id": row_id, "date_created": "2026-10-20 16:35:42",
            "shot_data": json.dumps(shot)}


def _emit_two():
    got = []
    poller = GsproPoller(on_shot=lambda p, m: got.append(p), db_path="unused.db")
    assert poller._emit(_row(1, 150.0))
    assert poller._emit(_row(2, 152.0))
    return got


def test_gspro_shots_get_distinct_trace_ids():
    a, b = _emit_two()
    assert shot_trace_id(a) is not None
    assert shot_trace_id(b) is not None
    assert shot_trace_id(a) != shot_trace_id(b)


def test_gspro_traces_round_trip_independently(tmp_path):
    a, b = _emit_two()
    store = PressureTraceStore(str(tmp_path))
    store.save(shot_trace_id(a), [{"cop_x": 1.0}])
    store.save(shot_trace_id(b), [{"cop_x": 2.0}])
    assert not (tmp_path / "pressure_traces" / "None.json.gz").exists()
    fresh = PressureTraceStore(str(tmp_path))
    assert fresh.load(shot_trace_id(a))[0]["cop_x"] == 1.0
    assert fresh.load(shot_trace_id(b))[0]["cop_x"] == 2.0


def test_end_to_end_poll_stamps_identity(tmp_path):
    db = tmp_path / "GSPro.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE DrivingRangeShot (ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " DateCreated TEXT, ShotData TEXT)")
    conn.commit()
    got = []
    poller = GsproPoller(on_shot=lambda p, m: got.append(p), db_path=str(db),
                         poll_interval_s=0.1)
    t = threading.Thread(target=poller.run, daemon=True)
    t.start()
    time.sleep(0.3)
    conn.execute("INSERT INTO DrivingRangeShot (DateCreated, ShotData) VALUES (?,?)",
                 ("2026-10-20T16:35:42", _row(0, 150.0)["shot_data"]))
    conn.commit()
    deadline = time.time() + 3
    while not got and time.time() < deadline:
        time.sleep(0.05)
    poller.stop()
    t.join(timeout=2)
    conn.close()
    assert got, "poller did not emit the new row"
    assert isinstance(got[0].get("timestamp_ns"), int)
    assert shot_trace_id(got[0]) == str(got[0]["timestamp_ns"])
