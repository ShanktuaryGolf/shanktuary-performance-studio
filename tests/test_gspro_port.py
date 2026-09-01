"""Tests for the GSPro range-shot port (src/gspro).

Builds a synthetic GSPro.db in SQLite and drives the mapper + poller against
it, asserting the emitted payload matches SPS's Nova shot contract field-for-
field. No network, no Windows paths — the DB is created on disk under tmp_path.

Run:  pytest tests/test_gspro_port.py -v   (from repo root)
"""

import json
import os
import sqlite3
import threading
import time

import pytest

from src.gspro.mapper import (
    GSPRO_INPUT_UNITS,
    MPH_TO_MPS,
    YARDS_TO_METERS,
    is_complete,
    map_gspro_range_shot_to_sps_payload,
    match_gspro_club,
    parse_shot_row,
)
from src.gspro.poller import GsproPoller, read_latest


# ---------------------------------------------------------------------------
# Synthetic GSPro.db helpers
# ---------------------------------------------------------------------------

def _make_db(path):
    """Create an empty GSPro-shaped database (DrivingRangeShot table)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE DrivingRangeShot ("
        "  ID INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  DateCreated TEXT NOT NULL,"
        "  ShotData TEXT NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _insert_shot(conn, shot_data: dict):
    cur = conn.execute(
        "INSERT INTO DrivingRangeShot (DateCreated, ShotData) VALUES (?, ?)",
        ("2026-09-01T12:00:00Z", json.dumps(shot_data)),
    )
    conn.commit()
    return cur.lastrowid


def _full_shot(club="7i"):
    """A complete GSPro ShotData row (imperial units, as stored)."""
    return {
        "club": club,
        "BallSpeed": 150.0,          # mph
        "VLA": 12.0,                 # deg
        "HLA": -3.0,                 # deg (left)
        "TotalSpin": 2800.0,         # rpm
        "rawSpinAxis": 4.5,          # deg (right)
        "BackSpin": 2700.0,
        "SideSpin": 300.0,
        "Carry": 210.0,              # yards
        "TotalDistance": 225.0,      # yards
        "Offline": -8.0,             # yards (left)
        "PeakHeight": 28.0,          # yards
        "Decent": 34.0,              # deg — GSPro spells it "Decent" (sic)
        "ClubSpeed": 95.0,           # mph
        "Path": -1.5,                # deg
        "AoA": -2.0,                 # deg
        "FaceToTarget": 3.0,         # deg
        "FaceToPath": 4.5,           # deg
        "DynamicLoft": 18.5,         # deg
        "CR": 6.0,                   # dps
        "SmashFactor": 1.58,
    }


# ---------------------------------------------------------------------------
# Mapper: unit conversion + field mapping
# ---------------------------------------------------------------------------

class TestMapperUnits:
    def test_speed_converted_mph_to_mps(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, meta = map_gspro_range_shot_to_sps_payload(row)
        assert payload["ball_speed_meters_per_second"] == pytest.approx(150.0 * MPH_TO_MPS)
        assert payload["open_golf_coach"]["club_speed_meters_per_second"] == pytest.approx(95.0 * MPH_TO_MPS)

    def test_distance_converted_yards_to_meters(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        ogc = payload["open_golf_coach"]
        assert ogc["carry_distance_meters"] == pytest.approx(210.0 * YARDS_TO_METERS)
        assert ogc["total_distance_meters"] == pytest.approx(225.0 * YARDS_TO_METERS)
        assert ogc["offline_distance_meters"] == pytest.approx(-8.0 * YARDS_TO_METERS)

    def test_us_customary_preserved(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        us = payload["open_golf_coach"]["us_customary_units"]
        assert us["carry_distance_yards"] == 210.0
        assert us["total_distance_yards"] == 225.0
        assert us["offline_distance_yards"] == -8.0

    def test_spin_and_angles_passthrough(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["total_spin_rpm"] == 2800.0
        assert payload["spin_axis_degrees"] == 4.5
        assert payload["vertical_launch_angle_degrees"] == 12.0
        assert payload["horizontal_launch_angle_degrees"] == -3.0

    def test_source_marker(self):
        row = {"id": 7, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["type"] == "shot"
        assert payload["_source"] == "gspro"
        assert payload["_gspro"]["row_id"] == 7


class TestMapperSpinDerivation:
    def test_total_spin_from_vector_when_absent(self):
        shot = _full_shot()
        del shot["TotalSpin"]
        # back=2700, side=300 -> hypot ~ 2716.64
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["total_spin_rpm"] == pytest.approx(2716.64, abs=0.5)

    def test_explicit_total_spin_wins_over_vector(self):
        shot = _full_shot()  # has TotalSpin=2800 AND back/side
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["total_spin_rpm"] == 2800.0


class TestMapperCarryPrecedence:
    def test_carry_beats_game_and_lm(self):
        shot = _full_shot()
        shot["rawCarryGame"] = 205.0
        shot["rawCarryLM"] = 198.0
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["open_golf_coach"]["carry_distance_meters"] == pytest.approx(210.0 * YARDS_TO_METERS)

    def test_game_carry_used_when_carry_absent(self):
        shot = _full_shot()
        del shot["Carry"]
        shot["rawCarryGame"] = 205.0
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert payload["open_golf_coach"]["carry_distance_meters"] == pytest.approx(205.0 * YARDS_TO_METERS)


class TestMapperAbsence:
    def test_absent_fields_not_emitted(self):
        shot = {"club": "7i", "BallSpeed": 140.0, "Carry": 200.0,
                "TotalDistance": 215.0, "Offline": -5.0}
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        assert "total_spin_rpm" not in payload
        assert "spin_axis_degrees" not in payload
        ogc = payload["open_golf_coach"]
        assert "club_speed_meters_per_second" not in ogc
        # but the present ones are there
        assert "ball_speed_meters_per_second" in payload

    def test_hi_vi_not_mapped_to_face_contact(self):
        shot = _full_shot()
        shot["HI"] = 2.0
        shot["VI"] = -1.5
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(shot)}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        ogc = payload["open_golf_coach"]
        assert "face_contact" not in ogc
        # preserved raw instead (unverified units)
        assert payload["_gspro"]["raw_fields"]["club_face_h_impact"] == 2.0
        assert payload["_gspro"]["raw_fields"]["club_face_v_impact"] == -1.5


class TestMapperMalformed:
    def test_invalid_json_raises(self):
        row = {"id": 1, "date_created": "t", "shot_data": "{not json"}
        with pytest.raises(ValueError):
            map_gspro_range_shot_to_sps_payload(row)

    def test_non_object_json_raises(self):
        row = {"id": 1, "date_created": "t", "shot_data": "[1,2,3]"}
        with pytest.raises(ValueError):
            map_gspro_range_shot_to_sps_payload(row)


class TestCompletenessGate:
    def test_complete_when_required_present(self):
        fields = parse_shot_row({"id": 1, "date_created": "t",
                                 "shot_data": json.dumps(_full_shot())})
        assert is_complete(fields)

    def test_incomplete_when_distance_missing(self):
        shot = _full_shot()
        del shot["Carry"]
        del shot["TotalDistance"]
        fields = parse_shot_row({"id": 1, "date_created": "t",
                                 "shot_data": json.dumps(shot)})
        assert not is_complete(fields)


# ---------------------------------------------------------------------------
# Club matching (phantom-club protection)
# ---------------------------------------------------------------------------

class TestClubMatching:
    BAG = ["Driver", "3 Wood", "5 Wood", "7 Iron", "8 Iron", "9 Iron",
           "Pitching Wedge", "RTX 52", "RTX 60"]

    def test_iron_shorthand(self):
        assert match_gspro_club("7i", self.BAG) == "7 Iron"
        assert match_gspro_club("8 iron", self.BAG) == "8 Iron"

    def test_wedge_by_loft_unique(self):
        # bag has exactly one 52 -> confident loft-only match
        assert match_gspro_club("52 wedge", self.BAG) == "RTX 52"

    def test_pitching_wedge_alias(self):
        assert match_gspro_club("PW", self.BAG) == "Pitching Wedge"

    def test_unmatched_returns_none_not_phantom(self):
        # "4H" not in bag -> None, caller falls back to current selection
        assert match_gspro_club("4H", self.BAG) is None
        assert match_gspro_club("", self.BAG) is None

    def test_ambiguous_wedge_loft_returns_none(self):
        # two 52s in bag -> never guess between them
        bag = ["RTX 52", "Other 52"]
        assert match_gspro_club("52 wedge", bag) is None


# ---------------------------------------------------------------------------
# Poller: baseline, dedup, enrich-in-place, emit-once (synthetic DB on disk)
# ---------------------------------------------------------------------------

class TestPollerEndToEnd:
    def _run_poller(self, db_path, setup_fn, poll_interval=0.1):
        """Start the poller (establishes baseline), then let ``setup_fn`` mutate
        the live DB, and return whatever shots were emitted."""
        emitted = []
        statuses = []
        poller = GsproPoller(
            on_shot=lambda p, m: emitted.append((p, m)),
            db_path=str(db_path),
            poll_interval_s=poll_interval,
            on_status=statuses.append,
        )

        def driver():
            t = threading.Thread(target=poller.run, daemon=True)
            t.start()
            time.sleep(0.3)   # let the baseline row be established first
            setup_fn()        # now insert / enrich new shots in the live DB
            time.sleep(1.2)   # give the poller time to detect + emit
            poller.stop()
            t.join(timeout=3)

        driver()
        return emitted, statuses

    def test_baseline_not_replayed(self, tmp_path):
        db = tmp_path / "GSPro.db"
        conn = _make_db(db)
        # pre-existing shot (history) — must NOT be replayed on start
        _insert_shot(conn, _full_shot())

        emitted, statuses = self._run_poller(
            db, setup_fn=lambda: None)
        assert emitted == []  # baseline row not re-emitted
        conn.close()

    def test_new_complete_shot_emitted_once(self, tmp_path):
        db = tmp_path / "GSPro.db"
        conn = _make_db(db)
        _insert_shot(conn, _full_shot())  # baseline

        def setup():
            time.sleep(0.2)
            _insert_shot(conn, _full_shot(club="8i"))  # new complete shot

        emitted, _ = self._run_poller(db, setup_fn=setup)
        assert len(emitted) == 1
        payload, meta = emitted[0]
        assert payload["_source"] == "gspro"
        assert payload["ball_speed_meters_per_second"] == pytest.approx(150.0 * MPH_TO_MPS)
        assert meta["row_id"] > 1

    def test_incomplete_then_enriched_emitted_once(self, tmp_path):
        db = tmp_path / "GSPro.db"
        conn = _make_db(db)
        _insert_shot(conn, _full_shot())  # baseline

        new_row = None
        def setup():
            nonlocal new_row
            time.sleep(0.2)
            shot = _full_shot()
            del shot["Carry"]          # incomplete at first write
            del shot["TotalDistance"]
            cur = conn.execute(
                "INSERT INTO DrivingRangeShot (DateCreated, ShotData) VALUES (?, ?)",
                ("t", json.dumps(shot)))
            conn.commit()
            new_row = cur.lastrowid
            time.sleep(0.4)
            # OGC plugin enriches the row IN PLACE with distance fields
            full = _full_shot()
            conn.execute("UPDATE DrivingRangeShot SET ShotData=? WHERE ID=?",
                         (json.dumps(full), new_row))
            conn.commit()

        emitted, statuses = self._run_poller(db, setup_fn=setup)
        assert len(emitted) == 1  # exactly once after enrichment
        payload, meta = emitted[0]
        assert "carry_distance_meters" in payload["open_golf_coach"]
        conn.close()

    def test_no_double_emit_on_repeated_polls(self, tmp_path):
        db = tmp_path / "GSPro.db"
        conn = _make_db(db)
        _insert_shot(conn, _full_shot())  # baseline

        def setup():
            time.sleep(0.2)
            _insert_shot(conn, _full_shot(club="9i"))

        emitted, _ = self._run_poller(db, setup_fn=setup, poll_interval=0.1)
        assert len(emitted) == 1  # rowId dedup: one shot, many polls


# ---------------------------------------------------------------------------
# read_latest against synthetic DB
# ---------------------------------------------------------------------------

class TestReadLatest:
    def test_returns_newest_first(self, tmp_path):
        db = tmp_path / "GSPro.db"
        conn = _make_db(db)
        id1 = _insert_shot(conn, _full_shot(club="7i"))
        id2 = _insert_shot(conn, _full_shot(club="8i"))
        rows = read_latest(str(db), limit=5)
        assert [r["id"] for r in rows] == [id2, id1]
        conn.close()

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            read_latest("/nonexistent/GSPro.db")


# ---------------------------------------------------------------------------
# Contract: payload keys SPS actually reads must be present & SI
# ---------------------------------------------------------------------------

class TestNovaContractParity:
    """The GSPro payload must carry the same top-level SI fields + ogc sub-dict
    that SPS's poll_queue()/analytics read from Nova shots."""

    def test_top_level_si_fields(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        for key in ("ball_speed_meters_per_second",
                    "vertical_launch_angle_degrees",
                    "horizontal_launch_angle_degrees",
                    "total_spin_rpm"):
            assert key in payload

    def test_ogc_subdict_keys(self):
        row = {"id": 1, "date_created": "t", "shot_data": json.dumps(_full_shot())}
        payload, _ = map_gspro_range_shot_to_sps_payload(row)
        ogc = payload["open_golf_coach"]
        for key in ("carry_distance_meters", "total_distance_meters",
                    "offline_distance_meters", "club_speed_meters_per_second",
                    "smash_factor", "dynamic_loft_degrees",
                    "angle_of_attack_degrees", "face_closure_rate_dps"):
            assert key in ogc

    def test_input_units_default_imperial(self):
        assert GSPRO_INPUT_UNITS == "imperial"
