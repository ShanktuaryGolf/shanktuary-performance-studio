"""Combine: a fixed skills test scored with the Index's own math.

Ten full swings per station, three stations from your bag (short / mid /
long). Each station scores like a club in the Index -- same gate, same
efficiency and shape ratios, same 0-99 scale -- so a Combine score reads
as "what the Index would say if this were your whole history". No new
formula, so the two can never disagree.
"""
import json

import pytest

from src.analytics import combine as cb


def _shot(club, bs=40.0, vla=18.0, spin=6000, axis=0.0, station=None, **extra):
    """bs in m/s; the Index gate reads ball_speed_mph from the OGC block."""
    s = {"club": club, "ball_speed_meters_per_second": bs,
         "vertical_launch_angle_degrees": vla, "total_spin_rpm": spin,
         "spin_axis_degrees": axis, "timestamp_ns": id(object()),
         "open_golf_coach": {"us_customary_units": {"ball_speed_mph": bs / 0.44704}}}
    if station is not None:
        s["combine_station"] = station
    s.update(extra)
    return s


# --- protocol ----------------------------------------------------------------------

def test_protocol_from_a_bag_picks_short_mid_long_from_clubs_you_own():
    bag = [{"name": "PW"}, {"name": "7 Iron"}, {"name": "4 Hybrid"}, {"name": "60° Wedge"}, {"name": "5 Iron"}]
    p = cb.protocol_for_bag(bag)
    assert [s["role"] for s in p["stations"]] == ["short", "mid", "long"]
    assert p["stations"][0]["club"] in ("PW", "60° Wedge")
    assert p["stations"][1]["club"] == "7 Iron"
    assert p["stations"][2]["club"] == "4 Hybrid"
    assert p["shots_per_station"] == cb.SHOTS_PER_STATION == 10


def test_protocol_with_a_thin_bag_is_reported_not_faked():
    p = cb.protocol_for_bag([{"name": "7 Iron"}])
    assert p["stations"] == [] and "need" in p["reason"].lower()
    p = cb.protocol_for_bag([{"name": "7 Iron"}, {"name": "PW"}])
    assert [s["role"] for s in p["stations"]] == ["short", "mid"] or p["stations"] == []


# --- scoring -----------------------------------------------------------------------

def test_score_uses_index_math_and_only_counts_this_stations_club():
    stations = [{"role": "mid", "club": "7 Iron"}]
    shots = [_shot("7 Iron", station="mid") for _ in range(10)]
    shots.append(_shot("PW", station="mid"))            # wrong club at the station: ignored
    r = cb.score(stations, shots)
    st = r["stations"][0]
    assert st["counted"] == 10 and st["needed"] == 10 and st["complete"]
    from src.analytics.index import efficiency_ratio, shape_ratio
    eff = efficiency_ratio(40 / 0.44704, 18.0, 6000)
    shp = shape_ratio([0.0] * 10)
    assert st["efficiency"] == pytest.approx(eff, abs=1e-9)
    assert st["shape"] == pytest.approx(shp, abs=1e-9)
    assert 0 <= st["score"] <= 99
    assert r["score"] == st["score"]                    # one station -> its score


def test_partial_swings_and_bad_reads_do_not_count():
    stations = [{"role": "mid", "club": "7 Iron"}]
    # The partial-swing floor in valid_shots only engages with >=10 structurally
    # valid shots, so surround the chip with a realistic run of full swings.
    shots = [_shot("7 Iron", station="mid") for _ in range(6)]
    shots += [_shot("7 Iron", bs=8.0, station="mid"),   # chip
              _shot("7 Iron", spin=0, station="mid")]  # bad read (structurally dropped)
    shots += [_shot("7 Iron", station="mid") for _ in range(5)]
    r = cb.score(stations, shots)
    st = r["stations"][0]
    # 11 good swings -> the first ten count; chip and bad read are never among them.
    assert st["counted"] == 10 and st["complete"]
    kept = cb.station_shots("mid", "7 Iron", shots)
    assert all(s["ball_speed_meters_per_second"] == 40.0 and s["total_spin_rpm"] == 6000 for s in kept)
    # With only nine good swings the station is still open.
    r2 = cb.score(stations, shots[:-2])
    assert r2["stations"][0]["counted"] == 9 and not r2["stations"][0]["complete"]
    assert r2["status"] == "in_progress" and r2["score"] is None


def test_overall_is_the_mean_of_complete_stations_and_is_none_until_all_done():
    stations = [{"role": "short", "club": "PW"}, {"role": "mid", "club": "7 Iron"}]
    shots = [_shot("PW", axis=0.0, station="short") for _ in range(10)]
    shots += [_shot("7 Iron", axis=25.0, station="mid") for _ in range(10)]
    r = cb.score(stations, shots)
    assert r["status"] == "complete"
    a, b = (s["score"] for s in r["stations"])
    assert r["score"] == pytest.approx((a + b) / 2, abs=0.05)
    assert a > b                                          # straight beats a 25° axis
    # Remove one 7 iron: incomplete overall, but the finished station still reports.
    r2 = cb.score(stations, shots[:-1])
    assert r2["status"] == "in_progress" and r2["score"] is None
    assert r2["stations"][0]["complete"] and not r2["stations"][1]["complete"]


def test_extra_shots_beyond_ten_use_the_first_ten_only():
    """A combine is a fixed count, not 'keep swinging until the number looks good'."""
    stations = [{"role": "mid", "club": "7 Iron"}]
    good = [_shot("7 Iron", axis=0.0, station="mid") for _ in range(10)]
    great = [_shot("7 Iron", axis=0.0, bs=48.0, vla=17, spin=6200, station="mid") for _ in range(5)]
    r_good = cb.score(stations, good)
    r_more = cb.score(stations, good + great)
    assert r_more["stations"][0]["counted"] == 10
    assert r_more["score"] == r_good["score"]


# --- history ---------------------------------------------------------------------------

def test_combine_history_records_only_complete_runs(tmp_path):
    path = tmp_path / "combine_history.json"
    stations = [{"role": "mid", "club": "7 Iron"}]
    incomplete = cb.score(stations, [_shot("7 Iron", station="mid")] * 3)
    assert cb.record(incomplete, session_id="s1", path=path) is None
    complete = cb.score(stations, [_shot("7 Iron", station="mid") for _ in range(10)])
    rec = cb.record(complete, session_id="s1", path=path, now="2026-09-11T10:00:00")
    assert rec["score"] == complete["score"] and rec["session_id"] == "s1"
    # Same session re-recorded (e.g. re-save) replaces, never duplicates.
    cb.record(complete, session_id="s1", path=path, now="2026-09-11T10:05:00")
    hist = cb.load(path)
    assert len(hist) == 1 and hist[0]["date"] == "2026-09-11T10:05:00"
    assert json.loads(path.read_text())[0]["stations"][0]["club"] == "7 Iron"


def test_summary_gives_best_and_latest(tmp_path):
    hist = [{"date": "2026-09-01T00:00:00", "score": 61.0, "session_id": "a"},
            {"date": "2026-09-11T00:00:00", "score": 58.5, "session_id": "b"}]
    s = cb.summary(hist)
    assert s["best"] == 61.0 and s["latest"] == 58.5 and s["runs"] == 2
    assert cb.summary([]) is None


# --- app wiring -------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    a = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    a.sessions = [{"id": "sess_1", "name": "S1", "shots": []}]
    a.active_session_index = 0
    a.clubs = list(studio.DEFAULT_CLUBS)
    a.bag = [{"name": "PW"}, {"name": "7 Iron"}, {"name": "4 Hybrid"}]
    a.is_left_handed = False
    a.balls = []
    a.current_ball = None
    a.current_club = "7 Iron"
    a.combine_run = None
    a.copy_feedback = ""
    a.draw_screen = lambda: None
    return a


def _run(*clubs):
    roles = {"PW": "short", "7 Iron": "mid", "4 Hybrid": "long"}
    return {"stations": [{"role": roles[c], "club": c} for c in clubs], "session_id": "sess_1"}


def test_range_run_is_applied_and_ended(app):
    app.apply_range_combine(_run("PW", "7 Iron", "4 Hybrid"))
    assert [s["role"] for s in app.combine_run["stations"]] == ["short", "mid", "long"]
    assert "PW first" in app.copy_feedback
    app.apply_range_combine(None)
    assert app.combine_run is None


def test_garbage_from_the_range_is_ignored(app):
    app.apply_range_combine({"stations": []})
    app.apply_range_combine("start")
    assert app.combine_run is None


def test_combine_station_for_current_club(app):
    assert app.combine_station() is None                      # no run
    app.apply_range_combine(_run("PW", "7 Iron", "4 Hybrid"))
    assert app.combine_station() == "mid"                     # 7 Iron
    app.current_club = "PW"
    assert app.combine_station() == "short"
    app.current_club = "5 Iron"
    assert app.combine_station() is None                      # not a station club


def test_incoming_shot_is_stamped_with_the_station_of_its_club(app):
    assert "combine_station" not in app._stamp_equipment({"club": "7 Iron"})
    app.apply_range_combine(_run("PW", "7 Iron", "4 Hybrid"))
    assert app._stamp_equipment({"club": "7 Iron"})["combine_station"] == "mid"
    app.current_club = "5 Iron"
    msg = app._stamp_equipment({"club": "5 Iron", "combine_station": "stale"})
    assert "combine_station" not in msg


def test_save_records_a_complete_run_and_never_blocks_the_save(app, tmp_path, monkeypatch):
    app.apply_range_combine(_run("PW", "7 Iron"))
    shots = [_shot("PW", station="short") for _ in range(10)]
    shots += [_shot("7 Iron", station="mid") for _ in range(9)]
    app.sessions[0]["shots"] = shots
    app.save_session_to_file()
    assert not (tmp_path / cb.FILE_NAME).exists()             # incomplete: nothing recorded
    shots.append(_shot("7 Iron", station="mid"))
    app.save_session_to_file()
    hist = cb.load(tmp_path / cb.FILE_NAME)
    assert len(hist) == 1 and hist[0]["session_id"] == "sess_1"
    # A failure inside the combine bookkeeping must never take the save down.
    monkeypatch.setattr(cb, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    (tmp_path / "history.json").unlink()
    app.save_session_to_file()
    assert (tmp_path / "history.json").exists()


def _index_pane_app(tmp_path, monkeypatch, tk):
    """Real app on isolated stores, Index view, with a 3-club history so the pane draws."""
    import shanktuary_performance_studio as studio
    from src.analytics import index_history as ih
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    import obs_server
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    monkeypatch.setattr(ih, "default_path", lambda: tmp_path / ih.FILE_NAME)
    monkeypatch.setattr(cb, "default_path", lambda: tmp_path / cb.FILE_NAME)
    root = tk.Tk()
    root.geometry("1600x950")
    a = studio.ShanktuaryApp(root)
    def mk(club, carry, i):
        return _shot(club, bs=(105 + i % 3) * 0.44704, vla=18.0, spin=6500 + i * 20, axis=1.0,
                     open_golf_coach={"us_customary_units": {"ball_speed_mph": 105 + i % 3,
                                                            "carry_distance_yards": carry + i % 4}})
    shots = [mk(c, y, i) for c, y in (("4 Iron", 165), ("7 Iron", 150), ("PW", 110)) for i in range(31)]
    a.sessions = [{"id": "sess_x", "name": "S", "shots": shots}]
    a.active_session_index = 0
    a.bag = [{"name": "PW"}, {"name": "7 Iron"}, {"name": "4 Hybrid"}]
    return root, a


def _pane_texts(a):
    return [(a.canvas.bbox(i), a.canvas.itemcget(i, "text")) for i in a.canvas.find_all()
            if a.canvas.type(i) == "text" and a.canvas.bbox(i)]


def _overlaps(items):
    return [(t, u) for j, (b, t) in enumerate(items) for d, u in items[j + 1:]
            if min(b[2], d[2]) > max(b[0], d[0]) and min(b[3], d[3]) > max(b[1], d[1])]


def test_index_score_pane_shows_combine_history_and_live_progress(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        root, a = _index_pane_app(tmp_path, monkeypatch, tk)
    except tk.TclError:
        pytest.skip("no display")
    try:
        cb.record(cb.score([{"role": "mid", "club": "7 Iron"}],
                           [_shot("7 Iron", station="mid") for _ in range(10)]),
                  session_id="old", path=tmp_path / cb.FILE_NAME, now="2026-09-01T10:00:00")
        a.set_mode(11); root.update_idletasks()
        texts = _pane_texts(a)
        joined = " | ".join(t for _, t in texts)
        assert "COMBINE" in joined and "Latest" in joined and "Best" in joined
        assert not any("/10" in t for _, t in texts)          # no run -> no progress line
        # Start a run and land 7 PW swings: the progress line appears.
        a.apply_range_combine(_run("PW", "7 Iron", "4 Hybrid"))
        a.sessions[0]["shots"] += [_shot("PW", station="short") for _ in range(7)]
        a.draw_screen(); root.update_idletasks()
        texts = _pane_texts(a)
        prog = [t for _, t in texts if "/10" in t]
        assert prog and "PW 7/10" in prog[0] and "7 Iron 0/10" in prog[0] and "4H 0/10" in prog[0]
        # Everything in the score pane stays inside it and nothing overlaps.
        x1, y1, x2, y2 = a.canvas.bbox(a.canvas.find_withtag("index-score-pane")[0])
        pane = [(b, t) for b, t in texts if x1 <= b[0] and b[2] <= x2 + 2 and y1 <= b[1]]
        assert any("COMBINE" == t for _, t in pane)
        assert all(b[3] <= y2 + 2 for b, _ in pane), [(b, t) for b, t in pane if b[3] > y2 + 2]
        assert _overlaps(pane) == []
    finally:
        root.destroy()
