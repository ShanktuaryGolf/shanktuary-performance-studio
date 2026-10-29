"""The desktop Table uses identical column geometry for labels and data."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.ui._legacy import table_redesign_v1 as table


@pytest.mark.parametrize("width", [780, 1200, 1600, 3500])
def test_column_layout_fills_available_width_without_collapsed_columns(width):
    columns = table._column_layout(312, 312 + width)
    assert columns[0][3] == 312
    assert columns[-1][4] == 312 + width
    for index, (key, _, _, left, right, x, anchor) in enumerate(columns):
        assert right > left
        if index:
            assert columns[index - 1][4] == left
        if key == "club":
            assert (x, anchor) == (left + 9, "w")
        else:
            assert (x, anchor) == ((left + right) / 2, "center")


@pytest.mark.parametrize("width,height", [(1200, 720), (1600, 1080), (3500, 2160)])
@pytest.mark.parametrize("sort_column", ["index", "carry", "ball_speed", "offline"])
def test_rendered_titles_units_rows_and_sort_targets_share_columns(monkeypatch, width, height, sort_column):
    monkeypatch.setattr(table.theme, "ui_font", lambda: "DejaVu Sans")
    canvas = MagicMock()
    canvas.bbox.return_value = (0, 0, 100, 20)
    app = SimpleNamespace(
        canvas=canvas, table_row_rects=[], table_header_rects=[],
        table_checkbox_rects=[], session_shots=[{"club": "7 Iron"}],
        calculate_session_averages=lambda: None,
        compute_smash_confidence=lambda *_: {"clamped": False},
        resolve_handed=lambda value, default: value or default,
        table_sort_col=sort_column, table_sort_asc=True,
        table_scroll_offset=0, selected_shot_index=0,
    )
    table.draw_shot_table_viewport(app, width, height, offset_x=300)
    columns = table._column_layout(312, 300 + width - 12)
    texts = canvas.create_text.call_args_list
    # The first text is the summary. Header text is followed by its optional unit.
    cursor = 1
    for column, hitbox in zip(columns, app.table_header_rects):
        key, title, unit, left, right, x, anchor = column
        assert hitbox[0] == left and hitbox[2] == right and hitbox[4] == key
        call = texts[cursor]
        assert call.args[0] == x
        assert call.kwargs["anchor"] == anchor
        assert call.kwargs["text"] == title
        cursor += 1
        if unit:
            call = texts[cursor]
            assert call.args[0] == x and call.kwargs["anchor"] == anchor
            assert call.kwargs["text"] == unit
            cursor += 1
    for column, call in zip(columns, texts[cursor:]):
        assert call.args[0] == column[5]
        assert call.kwargs["anchor"] == column[6]
    assert len(texts[cursor:]) == len(columns)
    assert len(canvas.create_polygon.call_args_list) == 1
