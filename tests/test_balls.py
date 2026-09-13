"""Balls in the bag: a second equipment variable, stamped on every shot."""
import json

import pytest

import shanktuary_performance_studio as studio


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    a = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    a.sessions = [{"name": "S1", "shots": []}]
    a.active_session_index = 0
    a.clubs = list(studio.DEFAULT_CLUBS)
    a.bag = []
    a.is_left_handed = False
    a.balls = []
    a.current_ball = None
    return a


def test_add_ball_dedupes_and_selects(app):
    assert app.add_ball("Pro V1") == "Pro V1"
    assert app.add_ball("  pro v1 ") == "Pro V1"      # same ball, case/space-insensitive
    assert app.add_ball("Chrome Soft") == "Chrome Soft"
    assert [b["name"] for b in app.balls] == ["Pro V1", "Chrome Soft"]
    assert app.current_ball == "Chrome Soft"
    assert app.add_ball("") is None


def test_remove_ball_clears_selection_but_not_history(app):
    app.add_ball("Pro V1")
    app.sessions[0]["shots"].append({"club": "7 Iron", "ball": "Pro V1"})
    app.remove_ball("Pro V1")
    assert app.balls == []
    assert app.current_ball is None
    assert app.sessions[0]["shots"][0]["ball"] == "Pro V1"   # stamped history is immutable


def test_balls_and_selection_round_trip_through_the_history_file(app, tmp_path):
    app.add_ball("Pro V1"); app.add_ball("Chrome Soft"); app.set_current_ball("Pro V1")
    app.save_session_to_file()
    data = json.loads((tmp_path / "history.json").read_text())
    assert data["balls"] == [{"name": "Pro V1"}, {"name": "Chrome Soft"}]
    assert data["current_ball"] == "Pro V1"
    fresh = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    fresh.sessions = []; fresh.clubs = list(studio.DEFAULT_CLUBS); fresh.bag = []
    fresh.balls = []; fresh.current_ball = None; fresh.is_left_handed = False
    fresh.load_session_history()
    assert [b["name"] for b in fresh.balls] == ["Pro V1", "Chrome Soft"]
    assert fresh.current_ball == "Pro V1"


def test_old_history_without_balls_loads_with_none_selected(app, tmp_path):
    (tmp_path / "history.json").write_text(json.dumps({"sessions": [], "bag": [], "is_left_handed": False}))
    app.load_session_history()
    assert app.balls == [] and app.current_ball is None


def test_incoming_shot_is_stamped_with_the_current_ball(app, monkeypatch):
    """poll_queue stamps `ball` beside `club`; no ball selected -> key absent."""
    app.add_ball("Pro V1")
    stamped = app._stamp_equipment({"club": "7 Iron"})
    assert stamped["ball"] == "Pro V1"
    app.set_current_ball(None)
    assert "ball" not in app._stamp_equipment({"club": "7 Iron"})


def test_poll_queue_uses_the_stamp(monkeypatch):
    src = open(studio.__file__).read()
    body = src[src.index("    def poll_queue(self):"):src.index("    def apply_range_club(")]
    assert "_stamp_equipment" in body


# --- UI ---------------------------------------------------------------------------

def test_dispersion_groups_split_by_ball_only_when_toggled(app):
    app.sessions[0]["shots"] = [
        {"club": "7 Iron", "ball": "Pro V1"}, {"club": "7 Iron", "ball": "Chrome Soft"},
        {"club": "7 Iron"}, {"club": "PW", "ball": "Pro V1"}, {"club": "PW", "excluded": True},
    ]
    app.dispersion_selected_club = "ALL"
    app.dispersion_split_by_ball = False
    assert sorted(app._dispersion_groups()) == ["7 Iron", "PW"]
    app.dispersion_split_by_ball = True
    groups = app._dispersion_groups()
    assert sorted(groups) == ["7 Iron · Chrome Soft", "7 Iron · Pro V1", "7 Iron · no ball", "PW · Pro V1"]
    assert len(groups["7 Iron · Pro V1"]) == 1
    app.dispersion_selected_club = "PW"
    assert list(app._dispersion_groups()) == ["PW · Pro V1"]


def test_series_colour_keeps_the_club_hue_and_varies_by_ball(app):
    app.balls = [{"name": "Pro V1"}, {"name": "Chrome Soft"}]
    base = app.get_club_color("7 Iron")
    a = app.get_club_color("7 Iron · Pro V1")
    b = app.get_club_color("7 Iron · Chrome Soft")
    none = app.get_club_color("7 Iron · no ball")
    assert len({base, a, b, none}) == 4
    def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    # All three are lightness variants of the same hue: channel ORDER is preserved.
    order = sorted(range(3), key=lambda i: rgb(base)[i])
    for h in (a, b, none):
        assert sorted(range(3), key=lambda i: rgb(h)[i]) == order, (base, h)


def test_split_toggle_is_offered_only_when_balls_exist_and_is_wired(tmp_path, monkeypatch):
    """Real app, isolated stores: draws Dispersion, then clicks the toggle."""
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    import obs_server
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.geometry("1600x950")
        a = studio.ShanktuaryApp(root)
        a.sessions = [{"name": "S", "shots": [{"club": "7 Iron", "ball": "Pro V1"}]}]
        a.active_session_index = 0
        a.balls = []
        a.set_mode(3)
        root.update_idletasks()
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert not any("Split by ball" in t for t in texts)
        a.balls = [{"name": "Pro V1"}]
        a.draw_screen(); root.update_idletasks()
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert any("Split by ball" in t for t in texts)
        assert a.dispersion_split_rect is not None
        x1, y1, x2, y2 = a.dispersion_split_rect
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert a.dispersion_split_by_ball is True
    finally:
        root.destroy()


def test_redesigned_dispersion_offers_split_and_colours_series(tmp_path, monkeypatch):
    """The shipped Dispersion page (src.ui) is the redesign; it must split too."""
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    import obs_server
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    from src.ui import ShanktuaryDesktopApp
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.geometry("1600x950")
        a = ShanktuaryDesktopApp(root)
        def shot(carry, off, ball=None):
            s = {"club": "7 Iron", "open_golf_coach": {"us_customary_units": {
                "carry_distance_yards": carry, "offline_distance_yards": off}}}
            if ball:
                s["ball"] = ball
            return s
        a.sessions = [{"name": "S", "shots": [
            shot(150, 3, "Pro V1"), shot(146, -4, "Chrome Soft"), shot(140, 0),
        ]}]
        a.active_session_index = 0
        a.balls = [{"name": "Pro V1"}, {"name": "Chrome Soft"}]
        a.dispersion_view_submode = "topdown"
        a.set_mode(3); root.update_idletasks()
        assert a.dispersion_split_rect is not None
        x1, y1, x2, y2 = a.dispersion_split_rect
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert a.dispersion_split_by_ball is True
        root.update_idletasks()
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        labels = [t for t in texts if t.startswith("7 Iron · ")]
        assert {t.split("  ")[0] for t in labels} == {"7 Iron · Pro V1", "7 Iron · Chrome Soft", "7 Iron · no ball"}
        # Series must be told apart by colour, not only by label.
        fills = {a.canvas.itemcget(i, "fill") for i in a.canvas.find_all()
                 if a.canvas.type(i) == "text" and a.canvas.itemcget(i, "text").startswith("7 Iron · ")
                 and a.canvas.itemcget(i, "text").endswith("y")}   # chart labels "club · ball  150y"
        assert len(fills) == 3
    finally:
        root.destroy()


def test_my_bag_ball_picker_rows_and_clicks(tmp_path, monkeypatch):
    """Ball chips on the My Bag toolbar: click selects, ✕ removes, + prompts."""
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    import obs_server
    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.geometry("1600x950")
        a = studio.ShanktuaryApp(root)
        a.balls = [{"name": "Pro V1"}, {"name": "Chrome Soft"}]
        a.current_ball = "Pro V1"
        a.set_mode(6)
        root.update_idletasks()
        texts = [a.canvas.itemcget(i, "text") for i in a.canvas.find_all() if a.canvas.type(i) == "text"]
        assert "BALLS" in texts
        assert any(t == "Pro V1" for t in texts) and any(t == "Chrome Soft" for t in texts)
        chips = {name: r for *r, name in a.bag_ball_chip_rects}
        assert set(chips) == {"Pro V1", "Chrome Soft"}
        # Select Chrome Soft by clicking its chip.
        x1, y1, x2, y2 = chips["Chrome Soft"]
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert a.current_ball == "Chrome Soft"
        # Remove Pro V1 via its ✕ zone.
        rem = {name: r for *r, name in a.bag_ball_remove_rects}
        x1, y1, x2, y2 = rem["Pro V1"]
        monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a_, **k: True)
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert [b["name"] for b in a.balls] == ["Chrome Soft"]
        # + Add ball prompts and adds.
        monkeypatch.setattr("tkinter.simpledialog.askstring", lambda *a_, **k: "TP5")
        x1, y1, x2, y2 = a.bag_add_ball_rect
        a.handle_mouse_press(type("E", (), {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "num": 1})())
        assert [b["name"] for b in a.balls] == ["Chrome Soft", "TP5"]
        assert a.current_ball == "TP5"
        # Toolbar chips must not run into the scope pills on the right.
        right_limit = a.bag_scope_session_rect[0]
        for *r, _ in a.bag_ball_chip_rects:
            assert r[2] <= right_limit, (r, right_limit)
    finally:
        root.destroy()
