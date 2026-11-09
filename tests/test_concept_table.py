from types import SimpleNamespace

from src.ui import concept_table as ui


class Canvas:
    def __init__(self):
        self.words = []

    def create_text(self, *a, **kw):
        self.words.append(kw["text"])

    def create_polygon(self, *a, **kw):
        pass

    def create_rectangle(self, *a, **kw):
        pass

    def create_line(self, *a, **kw):
        pass

    def create_oval(self, *a, **kw):
        pass


def app(shots):
    return SimpleNamespace(
        canvas=Canvas(),
        session_shots=shots,
        aim_corrected=lambda shot: dict(shot),
        is_left_handed=False,
        table_sort_col="index",
        table_sort_asc=True,
        table_scroll_offset=0,
        selected_shot_index=0,
        draw_screen=lambda: None,
    )


def test_missing_metrics_stay_unavailable_and_inclusion_is_registered():
    a = app([{"club": "7 Iron", "id": "one", "_source": "pureplay"}])
    ui.draw(a, 1340, 900, 260)
    assert a.canvas.words.count("—") >= 9
    assert a.table_checkbox_rects[0][-1] == 0
    assert len(a.table_row_rects) == 1
    assert not a.session_shots[0].get("excluded", False)
    assert len(a.table_header_rects) == 13


def test_missing_sort_values_stay_last_and_zero_is_not_missing():
    a = app(
        [
            {"id": "missing"},
            {"id": "zero", "total_spin_rpm": 0},
            {"id": "real", "total_spin_rpm": 5000},
        ]
    )
    a.table_sort_col = "spin"
    a.table_sort_asc = False
    assert [s["id"] for _, s in ui._rows(a)] == ["real", "zero", "missing"]
    assert ui._format(a, a.session_shots[1], "spin")[0] == "0"


def test_details_preserves_technical_fields_and_filter_preserves_real_indices():
    a = app(
        [{"club": "Driver"}, {"club": "7 Iron"}, {"club": "7 Iron", "excluded": True}]
    )
    a.concept_table_club = "7 Iron"
    a.concept_table_included_only = True
    a.concept_table_details = True
    ui.draw(a, 1340, 900, 260)
    assert [row[-1] for row in a.table_row_rects] == [1]
    assert {row[-1] for row in a.table_header_rects} >= {
        "path",
        "face",
        "push_pull",
        "descent",
    }


def test_export_and_session_note_use_existing_actions():
    a = app([])
    calls = []
    a.export_session_report = calls.append
    a.edit_session_notes = lambda: calls.append("notes")
    ui.draw(a, 1340, 900, 260)
    for rect, action in list(a.concept_table_rects):
        if action in ("csv", "pdf", "notes"):
            assert ui.handle_click(a, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    assert calls == ["csv", "pdf", "notes"]
