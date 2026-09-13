"""Session report: CSV + PDF export of one session, from a pure module."""
import csv
import json

import pytest

from src.analytics import session_report as sr


def _shot(i, club="7 Iron", carry=150.0, bs=105.0, offline=2.0, spin=6500.0, **extra):
    s = {"shot_number": i, "timestamp_ns": 1000 + i, "club": club, "timestamp": "10:0%d PM" % (i % 10),
         "ball_speed_meters_per_second": bs / 2.23694,
         "vertical_launch_angle_degrees": 18.0 + i * 0.1,
         "horizontal_launch_angle_degrees": -1.0,
         "total_spin_rpm": spin, "spin_axis_degrees": 2.5,
         "open_golf_coach": {"smash_factor": 1.3,
                             "club_path_degrees": {"right_handed": 1.5, "left_handed": -1.5},
                             "club_face_to_path_degrees": {"right_handed": -0.5, "left_handed": 0.5},
                             "shot_name": {"right_handed": "Draw", "left_handed": "Fade"},
                             "us_customary_units": {"ball_speed_mph": bs, "carry_distance_yards": carry,
                                                    "total_distance_yards": carry + 8,
                                                    "offline_distance_yards": offline,
                                                    "apex_height_feet": 90.0}}}
    s.update(extra)
    return s


SESSION = {"name": "Session 3 - 7 Iron", "created_at": "2026-09-02 19:27", "notes": "windy",
           "shots": [_shot(1), _shot(2, carry=160), _shot(3, club="PW", carry=110, bs=85),
                     _shot(4, carry=0, bs=0, _data_quality={"suspect": True, "issues": ["x"]})]}


def test_rows_are_one_per_shot_with_handed_fields_resolved():
    rows = sr.shot_rows(SESSION, is_left_handed=False)
    assert len(rows) == 4
    assert rows[0]["club"] == "7 Iron"
    assert rows[0]["carry_yds"] == 150.0
    assert rows[0]["club_path_deg"] == 1.5
    assert rows[0]["shot_name"] == "Draw"
    lefty = sr.shot_rows(SESSION, is_left_handed=True)
    assert lefty[0]["club_path_deg"] == -1.5
    assert lefty[0]["shot_name"] == "Fade"


def test_absent_fields_are_blank_not_zero():
    bare = {"name": "s", "shots": [{"club": "7 Iron", "ball_speed_meters_per_second": 40.0}]}
    row = sr.shot_rows(bare)[0]
    assert row["carry_yds"] == ""
    assert row["club_path_deg"] == ""
    assert row["ball_speed_mph"] == pytest.approx(89.5, abs=0.1)


def test_suspect_shots_are_flagged_and_excluded_from_summary():
    rows = sr.shot_rows(SESSION)
    assert rows[3]["flag"] == "suspect: x"
    summary = sr.club_summary(SESSION)
    seven = next(c for c in summary if c["club"] == "7 Iron")
    assert seven["shots"] == 2
    assert seven["avg_carry_yds"] == 155.0
    assert seven["carry_sd_yds"] == 5.0
    assert seven["avg_offline_yds"] == 2.0
    pw = next(c for c in summary if c["club"] == "PW")
    assert pw["shots"] == 1
    assert pw["carry_sd_yds"] == ""


def test_summary_excludes_partial_swings_and_says_how_many():
    full = [_shot(i, carry=150 + i % 5, bs=105 + i % 3) for i in range(12)]
    whiffs = [_shot(20 + i, carry=3.0, bs=8.0) for i in range(5)]  # device-registered tops
    sess = {"name": "s", "shots": full + whiffs}
    seven = sr.club_summary(sess)[0]
    assert seven["shots"] == 12
    assert 150 <= seven["avg_carry_yds"] <= 155
    assert sr.excluded_count(sess) == {"flagged": 0, "partial_or_misread": 5}
    # ...and the CSV still carries every shot: the raw log is not curated.
    assert len(sr.shot_rows(sess)) == 17


def test_csv_roundtrips_through_the_stdlib_reader(tmp_path):
    out = tmp_path / "s.csv"
    sr.write_csv(SESSION, out)
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert rows[0]["club"] == "7 Iron"
    assert rows[0]["carry_yds"] == "150.0"
    assert rows[3]["flag"].startswith("suspect")
    assert list(rows[0].keys())[:4] == ["shot", "time", "club", "shot_name"]


def test_pdf_is_written_with_pillow_only(tmp_path):
    out = tmp_path / "s.pdf"
    sr.write_pdf(SESSION, out, index_result={"status": "available", "score": 61.2},
                 index_trend={"delta": 1.4, "best": 63.0, "best_at": "2026-09-05T10:00:00", "points": 3})
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page") >= 2  # summary page + at least one shot page


def test_pdf_summary_page_carries_the_facts_that_matter(tmp_path):
    """Render the summary page to an image and check the text we drew."""
    page = sr.render_summary_page(SESSION, index_result={"status": "available", "score": 61.2},
                                  index_trend={"delta": 1.4, "best": 63.0, "best_at": "2026-09-05T10:00:00", "points": 3})
    drawn = sr._debug_drawn_text(page)
    assert "Session 3 - 7 Iron" in drawn
    assert "Shanktuary Index 61.2" in drawn
    assert "+1.4 vs last snapshot" in drawn
    assert any("7 Iron" in t and "155.0" in t for t in drawn), drawn
    assert any("suspect" in t.lower() for t in drawn)
    assert any("Nova measures ball flight" in t for t in drawn)


def test_every_drawn_string_fits_inside_the_page():
    """A flag like 'suspect: negative total_spin_rpm (-471)' ran off the right edge."""
    sess = {"name": "s", "created_at": "2026-09-02", "shots": [
        _shot(i, _data_quality={"suspect": True, "issues": ["negative total_spin_rpm (-471)"]})
        for i in range(60)]}
    for page in [sr.render_summary_page(sess)] + sr.render_shot_pages(sess):
        for (x, y, w, h, s) in page.placed:
            assert x >= 0 and x + w <= sr.PAGE_W, (s, x, w)
            assert y >= 0 and y + h <= sr.PAGE_H, (s, y, h)


def test_default_filenames_are_safe_and_dated(tmp_path):
    name = sr.default_filename({"name": "Session 3 - 7 Iron / test", "created_at": "2026-09-02 19:27"}, "csv")
    assert name == "shanktuary_2026-09-02_Session-3-7-Iron-test.csv"


# --- app wiring ---------------------------------------------------------------

def test_tools_menu_offers_session_export_and_handles_it():
    """Rendered rows must have handlers (dead-button guard, same as test_tools_menu)."""
    import re
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent / "shanktuary_performance_studio.py").read_text()
    section = re.search(r'\("SESSION REPORT", \[(.*?)\]\),', src, re.S)
    assert section, "no SESSION REPORT section in the tools menu"
    assert "export_csv" in section.group(1) and "export_pdf" in section.group(1)
    handler = re.search(r"if self\.show_tools_menu:(.*?)\n            self\.show_tools_menu = False", src, re.S)
    assert 'action == "export_csv"' in handler.group(1)
    assert 'action == "export_pdf"' in handler.group(1)


def test_tools_menu_subtitles_fit_inside_the_panel(tmp_path, monkeypatch):
    """A 7px overrun past the panel edge is invisible to the source-level guard."""
    tk = pytest.importorskip("tkinter")
    import shanktuary_performance_studio as studio
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "h.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.geometry("1600x950")
        app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
        app.root = root
        app.canvas = tk.Canvas(root, width=1600, height=950)
        app.tools_menu_items = []
        app.tools_btn_rect = (1180, 60, 1240, 90)
        app.show_tools_menu = True
        studio.ShanktuaryApp.draw_tools_flyout_menu(app, 1600, 950)
        root.update_idletasks()
        right = max(r[2] for r in app.tools_menu_items)
        for i in app.canvas.find_all():
            if app.canvas.type(i) != "text":
                continue
            b = app.canvas.bbox(i)
            assert b[2] <= right + 2, (app.canvas.itemcget(i, "text"), b, right)
    finally:
        root.destroy()


def test_export_core_writes_next_to_history_and_returns_path(tmp_path, monkeypatch):
    """The core (no dialog) is what the menu calls after the user picks a path."""
    import shanktuary_performance_studio as studio
    from src.analytics import index_history as ih

    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = [SESSION]
    app.active_session_index = 0
    app.is_left_handed = False
    app.copy_feedback = None
    out_csv = app._export_session_report("csv", tmp_path / "x.csv")
    out_pdf = app._export_session_report("pdf", tmp_path / "x.pdf")
    assert out_csv.exists() and out_csv.stat().st_size > 100
    assert out_pdf.read_bytes().startswith(b"%PDF")
    assert not (tmp_path / ih.FILE_NAME).exists()  # exporting never writes history

