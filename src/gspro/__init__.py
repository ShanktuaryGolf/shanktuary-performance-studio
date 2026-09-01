"""GSPro driving-range shot ingestion (port of bpgpitt10/SimRead, ISC).

SimRead reads GSPro's stored range-shot SQLite database and streams new
shots as structured events. This package ports the file-based reader to
Python stdlib (sqlite3) so SPS can ingest GSPro shots without a Node.js
runtime: GSPro becomes the common shot-data source regardless of which
launch monitor feeds it, and each parsed row is mapped into the same
shot payload shape the Nova WebSocket delivers today.

Public API:
    locate_gspro_database_path()  -- find GSPro.db (env override supported)
    parse_shot_row(row)           -- raw DB row -> gsproFields dict
    map_gspro_range_shot_to_sps_payload(row) -- full SPS shot payload
    GsproPoller                   -- live poll loop (rowId dedup,
                                      provisional/final events)

The screen-capture/OCR fallback from the original SimRead is deliberately
NOT ported: when GSPro.db exists it is always the better source.
"""

from .locate import locate_gspro_database_path
from .mapper import (
    is_complete,
    match_gspro_club,
    map_gspro_range_shot_to_sps_payload,
    parse_shot_row,
)
from .poller import GsproPoller, read_latest

__all__ = [
    "GsproPoller",
    "locate_gspro_database_path",
    "is_complete",
    "match_gspro_club",
    "parse_shot_row",
    "map_gspro_range_shot_to_sps_payload",
    "read_latest",
]
