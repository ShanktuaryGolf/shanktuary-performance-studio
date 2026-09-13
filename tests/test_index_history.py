"""Index history: a dated series so the number can be seen going up."""
import json

import pytest

from src.analytics import index_history as ih


def _result(score, clubs=("7 Iron",), status="available", areas=None):
    return {
        "status": status, "score": score, "tier": None,
        "established_clubs": list(clubs),
        "game_areas": areas or {"C": {"name": "Mid", "score": score, "clubs": list(clubs)}},
        "clubs": {c: {"composite": {"score": score}} for c in clubs},
    }


def test_record_appends_one_dated_snapshot(tmp_path):
    path = tmp_path / "index_history.json"
    ih.record(_result(61.2), shot_count=40, path=path, now="2026-09-11T20:00:00")
    data = json.loads(path.read_text())
    assert data == [{
        "at": "2026-09-11T20:00:00", "score": 61.2, "shot_count": 40,
        "established_clubs": ["7 Iron"],
        "game_areas": {"C": 61.2}, "clubs": {"7 Iron": 61.2},
    }]


def test_same_day_same_data_collapses_to_latest(tmp_path):
    path = tmp_path / "h.json"
    ih.record(_result(60.0), shot_count=40, path=path, now="2026-09-11T10:00:00")
    ih.record(_result(60.5), shot_count=41, path=path, now="2026-09-11T11:00:00")
    ih.record(_result(62.0), shot_count=50, path=path, now="2026-09-12T09:00:00")
    scores = [e["score"] for e in ih.load(path)]
    assert scores == [60.5, 62.0]


def test_unavailable_index_is_not_recorded(tmp_path):
    path = tmp_path / "h.json"
    assert ih.record(_result(None, status="insufficient_coverage"), 5, path=path) is None
    assert not path.exists()


def test_unchanged_shot_count_is_not_recorded_again(tmp_path):
    path = tmp_path / "h.json"
    ih.record(_result(60.0), 40, path=path, now="2026-09-11T10:00:00")
    assert ih.record(_result(60.0), 40, path=path, now="2026-09-13T10:00:00") is None
    assert len(ih.load(path)) == 1


def test_corrupt_file_is_set_aside_not_overwritten(tmp_path):
    path = tmp_path / "h.json"
    path.write_text("{not json")
    assert ih.load(path) == []
    ih.record(_result(60.0), 40, path=path, now="2026-09-11T10:00:00")
    assert len(ih.load(path)) == 1
    assert (tmp_path / "h.json.corrupt").read_text() == "{not json"


def test_trend_reports_delta_from_previous_and_best():
    series = [
        {"at": "2026-09-01T10:00:00", "score": 58.0, "shot_count": 20},
        {"at": "2026-09-05T10:00:00", "score": 63.0, "shot_count": 30},
        {"at": "2026-09-11T10:00:00", "score": 61.0, "shot_count": 40},
    ]
    t = ih.trend(series)
    assert t == {"latest": 61.0, "previous": 63.0, "delta": -2.0,
                 "best": 63.0, "best_at": "2026-09-05T10:00:00", "points": 3}
    assert ih.trend([]) is None
    assert ih.trend(series[:1])["delta"] is None


# --- wiring into the app -----------------------------------------------------

def _shot(bs, carry, club="7 Iron"):
    return {"club": club, "total_spin_rpm": 6500.0,
            "vertical_launch_angle_degrees": 18.0, "spin_axis_degrees": 1.0,
            "open_golf_coach": {"us_customary_units": {
                "ball_speed_mph": bs, "carry_distance_yards": carry}}}


def _app(tmp_path, monkeypatch, sessions):
    import shanktuary_performance_studio as studio

    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = sessions
    app.clubs = list(studio.DEFAULT_CLUBS)
    app.bag = []
    app.is_left_handed = False
    return app


def test_saving_the_session_records_an_index_snapshot(tmp_path, monkeypatch):
    clubs = {"4 Iron": 165, "7 Iron": 150, "9 Iron": 125, "PW": 110}
    shots = [_shot(105 + i % 3, carry + i % 4, club)
             for club, carry in clubs.items() for i in range(31)]
    app = _app(tmp_path, monkeypatch, [{"name": "S1", "shots": shots}])
    app.save_session_to_file()
    series = ih.load(tmp_path / ih.FILE_NAME)
    assert len(series) == 1
    assert series[0]["shot_count"] == len(shots)
    assert isinstance(series[0]["score"], float)


def test_saving_with_too_little_data_records_nothing(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, [{"name": "S1", "shots": [_shot(100, 150)]}])
    app.save_session_to_file()
    assert not (tmp_path / ih.FILE_NAME).exists()
    assert (tmp_path / "history.json").exists()  # the save itself still happened


def test_a_history_failure_never_blocks_the_session_save(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, [{"name": "S1", "shots": [_shot(100, 150)]}])

    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ih, "record", boom)
    app.save_session_to_file()
    assert (tmp_path / "history.json").exists()


def test_index_view_shows_trend_and_sparkline(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        import shanktuary_performance_studio as studio

        monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
        path = tmp_path / ih.FILE_NAME
        for day, score, n in (("01", 58.0, 20), ("05", 63.0, 30), ("11", 61.0, 40)):
            ih.record(_result(score), n, path=path, now=f"2026-09-{day}T10:00:00")
        clubs = {"4 Iron": 165, "7 Iron": 150, "9 Iron": 125, "PW": 110}
        shots = [_shot(105 + i % 3, carry + i % 4, club)
                 for club, carry in clubs.items() for i in range(31)]
        canvas = tk.Canvas(root, width=1900, height=980)
        app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
        app.canvas, app.root, app.sessions, app.is_left_handed = canvas, root, [{"shots": shots}], False
        studio.ShanktuaryApp.draw_shanktuary_index_viewport(app, 1900, 980)
        root.update_idletasks()
        texts = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        assert "PROGRESS" in texts
        assert "-2.0 vs last snapshot" in texts, texts
        assert any("Best 63.0" in t for t in texts), texts
        assert len(canvas.find_withtag("index-sparkline")) == 1
        # Nothing drawn for progress may collide with the score pane's own labels.
        # Only the score pane (left third) and below the toolbar; the toolbar's
        # title/subtitle overlap is pre-existing and not this feature's.
        boxes = [(canvas.bbox(i), canvas.itemcget(i, "text")) for i in canvas.find_all()
                 if canvas.type(i) == "text" and canvas.bbox(i)
                 and canvas.bbox(i)[1] > 104 and canvas.bbox(i)[2] < 1900 * 0.32]
        for j, (b, t) in enumerate(boxes):
            for d, u in boxes[j + 1:]:
                overlap = min(b[2], d[2]) > max(b[0], d[0]) and min(b[3], d[3]) > max(b[1], d[1])
                assert not overlap, (t, u)
    finally:
        root.destroy()


def test_index_view_without_history_says_so(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        import shanktuary_performance_studio as studio

        monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
        clubs = {"4 Iron": 165, "7 Iron": 150, "9 Iron": 125, "PW": 110}
        shots = [_shot(105 + i % 3, carry + i % 4, club)
                 for club, carry in clubs.items() for i in range(31)]
        canvas = tk.Canvas(root, width=1900, height=980)
        app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
        app.canvas, app.root, app.sessions, app.is_left_handed = canvas, root, [{"shots": shots}], False
        studio.ShanktuaryApp.draw_shanktuary_index_viewport(app, 1900, 980)
        texts = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
        assert any("No history yet" in t for t in texts), texts
        assert not canvas.find_withtag("index-sparkline")
    finally:
        root.destroy()

