"""Live polling of GSPro.db for new driving-range shots.

Port of SimRead's liveEventLoop.ts range-DB path (ISC license). The OCR /
screen-capture fallback is intentionally NOT ported — when the database
exists it is always the better source, and screen capture drags in Windows
window APIs plus an outbound vision provider that SPS should not ship.

Semantics (faithful to SimRead's range-db-only mode):
  * Poll ``SELECT ID, DateCreated, ShotData FROM DrivingRangeShot
    ORDER BY ID DESC LIMIT 1`` every poll_interval seconds (default 0.5).
  * On first successful read, establish a baseline rowId: shots already in
    the database when SPS starts are NOT replayed.
  * A new rowId emits one shot event. GSPro's OGC plugin enriches rows IN
    PLACE after impact (carry/total/offline appear late), so we re-read the
    same row until it carries every REQUIRED_FIELDS entry, then emit — this
    is SimRead's layoutSupport gate and replaces its 3s settle window for
    DB-sourced shots. If a row stays incomplete past PENDING_TIMEOUT_S we
    emit anyway (with _gspro.required_missing) so a shot is never lost.
  * The database file may be locked by a running GSPro process; reads open
    in read-only mode with a short busy timeout, and a transient failure
    never kills the loop (status callback instead).

The poller is transport-agnostic: it calls ``on_shot(payload, meta)`` for
each finalized shot. SPS wires that to shot_queue.put() exactly like the
Nova WebSocket worker does.
"""

import os
import sqlite3
import time

from .locate import locate_gspro_database_path
from .mapper import is_complete, map_gspro_range_shot_to_sps_payload, parse_shot_row

DEFAULT_POLL_INTERVAL_S = 0.5

#: If GSPro's OGC plugin never fills the required distance fields (unusual —
#: GSPro writes carry/total/offline itself), emit anyway after this long so a
#: shot is never lost. The payload carries _gspro.required_missing, and SPS's
#: UI renders absent states honestly. 0 disables the fallback (wait forever,
#: SimRead's exact behavior).
PENDING_TIMEOUT_S = 30.0


def _copy_with_wal(db_path, tmp_dir):
    """Copy GSPro.db (plus -wal/-shm when present) into a temp dir.

    SimRead's approach: reading the copy sees uncheckpointed WAL rows that
    an in-place read-only open would miss while GSPro runs in WAL mode.
    The copy is consistent enough for our purposes — we only ever SELECT,
    and at worst we see the shot a few hundred ms late (the next poll).
    """
    import shutil

    names = [db_path]
    for suffix in ("-wal", "-shm"):
        sidecar = db_path + suffix
        if os.path.isfile(sidecar):
            names.append(sidecar)
    copied = []
    for name in names:
        dest = os.path.join(tmp_dir, os.path.basename(name))
        shutil.copy2(name, dest)
        copied.append(dest)
    return copied[0]


def _connect_readonly(db_path):
    """Open GSPro.db read-only without touching the live file.

    Uses a URI so SQLite never creates -wal/-shm side effects on our end.
    If that open fails (e.g. the file is mid-checkpoint), fall back to
    copying db+wal+shm into a temp dir and reading the copy — SimRead's
    approach, which also sees uncheckpointed WAL rows.
    """
    uri = "file:" + db_path.replace(" ", "%20") + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=1.0)
    except sqlite3.Error:
        import tempfile

        tmp_dir = tempfile.mkdtemp(prefix="sps_gspro_")
        copy_path = _copy_with_wal(db_path, tmp_dir)
        conn = sqlite3.connect(
            "file:" + copy_path.replace(" ", "%20") + "?mode=ro", uri=True, timeout=1.0
        )
        # Close the temp dir once this connection closes (best effort).
        original_close = conn.close

        def close_and_cleanup():
            try:
                original_close()
            finally:
                import shutil

                shutil.rmtree(tmp_dir, ignore_errors=True)

        conn.close = close_and_cleanup  # type: ignore[method-assign]
        return conn


def read_latest(db_path=None, limit=1):
    """Read the newest ``limit`` DrivingRangeShot rows (newest first).

    Returns a list of {"id", "date_created", "shot_data"} dicts. Raises
    sqlite3.Error / FileNotFoundError when the database is unavailable —
    callers (the poller) treat that as a transient status, not fatal.
    """
    db_path = db_path or locate_gspro_database_path()
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"GSPro.db not found at {db_path}")

    conn = _connect_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT ID, DateCreated, ShotData FROM DrivingRangeShot ORDER BY ID DESC LIMIT ?",
            (limit,),
        )
        rows = []
        for row_id, date_created, shot_data in cur.fetchall():
            if not isinstance(row_id, int):
                raise ValueError(f"DrivingRangeShot.ID was not numeric: {row_id!r}")
            if not isinstance(shot_data, str):
                raise ValueError("DrivingRangeShot.ShotData was not text JSON")
            rows.append({"id": row_id, "date_created": date_created, "shot_data": shot_data})
        return rows
    finally:
        conn.close()


class GsproPoller:
    """Background poll loop for GSPro range shots.

    Usage (mirrors SPS's Nova websocket_worker pattern):

        on_shot = lambda payload, meta: shot_queue.put(payload)
        poller = GsproPoller(on_shot=on_shot, on_status=print)
        thread = threading.Thread(target=poller.run, daemon=True)
        thread.start()          # later: poller.stop()

    ``on_shot`` is called from the poller thread with (payload, meta); SPS's
    shot_queue already crosses that boundary safely. ``on_status`` receives
    human-readable state strings for the connection-status UI.
    """

    def __init__(self, on_shot, db_path=None, poll_interval_s=DEFAULT_POLL_INTERVAL_S,
                 on_status=None):
        self.on_shot = on_shot
        self.db_path = db_path or locate_gspro_database_path()
        self.poll_interval_s = max(0.1, float(poll_interval_s))
        self.on_status = on_status or (lambda msg: None)
        self._stop = False

    def stop(self):
        self._stop = True

    # -- internals ----------------------------------------------------------
    def _status(self, message):
        try:
            self.on_status(message)
        except Exception:
            pass  # a broken status callback must never kill the poll loop

    def _read_row(self):
        rows = read_latest(self.db_path, limit=1)
        return rows[0] if rows else None

    def _emit(self, row):
        try:
            payload, meta = map_gspro_range_shot_to_sps_payload(row)
        except ValueError as exc:
            self._status(f"[gspro] skipping malformed row {row['id']}: {exc}")
            return False
        meta["source"] = "gspro"
        try:
            self.on_shot(payload, meta)
            return True
        except Exception as exc:  # a broken consumer must not kill the loop
            self._status(f"[gspro] on_shot failed for row {row['id']}: {exc}")
            return False

    def run(self):
        """Blocking poll loop; call from a daemon thread. Stops via .stop()."""
        self._status(f"[gspro] polling {self.db_path} every {self.poll_interval_s:.1f}s")
        baseline_row_id = None  # None until first successful read
        last_emitted_row_id = None   # row seen but not yet complete (OGC enriching)
        pending_since = {}           # rowId -> monotonic time first seen incomplete
        polls_since_status = 0

        while not self._stop:
            try:
                row = self._read_row()
            except Exception as exc:
                if baseline_row_id is None and polls_since_status % 12 == 0:
                    self._status(f"[gspro] database unavailable ({exc}); retrying")
                time.sleep(self.poll_interval_s)
                continue

            polls_since_status += 1
            if baseline_row_id is None:
                # First successful read: everything already in the DB is
                # history, not a live shot. (SimRead does the same.)
                baseline_row_id = row["id"] if row else 0
                self._status(f"[gspro] connected — baseline row {baseline_row_id}")
                continue

            if row is None or row["id"] <= baseline_row_id:
                if polls_since_status % 6 == 0:
                    self._status(
                        f"[gspro] waiting for a fresh GSPro range shot "
                        f"(last row {row['id'] if row else baseline_row_id})"
                    )
                continue

            # New row — but it may still be missing the distance fields that
            # GSPro's OGC plugin writes in place after impact. Re-read until
            # complete, then emit exactly once per rowId.
            if row["id"] == last_emitted_row_id:
                continue

            try:
                fields = parse_shot_row(row)
            except ValueError as exc:
                self._status(f"[gspro] skipping malformed row {row['id']}: {exc}")
                last_emitted_row_id = row["id"]  # don't retry garbage forever
                pending_since.pop(row["id"], None)
                continue

            if not is_complete(fields):
                now = time.monotonic()
                first_seen = pending_since.setdefault(row["id"], now)
                timed_out = (PENDING_TIMEOUT_S > 0
                             and now - first_seen >= PENDING_TIMEOUT_S)
                if not timed_out and polls_since_status % 6 == 0:
                    self._status(f"[gspro] row {row['id']} still enriching "
                                 f"(waiting for distance fields)")
                if not timed_out:
                    continue

            # Complete, or past the pending timeout — emit exactly once.
            if self._emit(row):
                last_emitted_row_id = row["id"]
                pending_since.pop(row["id"], None)

        self._status("[gspro] polling stopped")
