"""Complete-frame reuse preserves geometry, z-order and unavailable states."""

import gc
import weakref
from collections import Counter

import pytest

from src.ui.retained_canvas import RetainedCanvas


class Operations:
    def __init__(self):
        self.items = {}
        self.order = []
        self.next_id = 0
        self.calls = Counter()

    def create(self, kind, coords, options):
        self.calls['create'] += 1
        self.next_id += 1
        self.items[self.next_id] = [kind, tuple(coords), dict(options)]
        self.order.append(self.next_id)
        return self.next_id

    def coords(self, selector, *coords):
        matches = self.find(selector)
        if not matches:
            return []
        if coords:
            self.calls['coords'] += 1
            self.items[matches[0]][1] = tuple(coords)
        return list(self.items[matches[0]][1])

    def configure(self, selector, options):
        self.calls['configure'] += 1
        for ident in self.find(selector):
            self.items[ident][2].update(options)

    def delete(self, *selectors):
        self.calls['delete'] += 1
        for selector in selectors:
            for ident in self.find(selector):
                self.items.pop(ident, None)
                self.order.remove(ident)

    def find(self, selector):
        if selector == 'all':
            return list(self.order)
        try:
            ident = int(selector)
        except (ValueError, TypeError):
            return [ident for ident in self.order
                    if selector in self.items[ident][2].get('tags', ())]
        return [ident] if ident in self.items else []

    def reorder(self, items):
        self.calls['reorder'] += 1
        for ident in items:
            self.order.remove(ident)
            self.order.append(ident)


@pytest.fixture
def retained():
    ops = Operations()
    return RetainedCanvas(None, operations=ops), ops


def paint(helper, *, key='lab', text='Measured', count=4):
    with helper.frame(key):
        title = helper.create('text', (10, 20), {'text': text, 'fill': 'white'})
        for i in range(count):
            helper.create('line', (i, 0, i + 1, 2), {'fill': 'teal', 'width': 2})
        return title


def test_identical_warm_frame_has_no_canvas_mutations(retained):
    helper, ops = retained
    first = paint(helper)
    before = ops.calls.copy()
    assert paint(helper) == first
    assert ops.calls == before
    assert helper.item_count == 5


def test_changed_text_and_coordinates_update_only_needed_options(retained):
    helper, ops = retained
    first = paint(helper)
    before = ops.calls.copy()
    assert paint(helper, text='New reading') == first
    assert ops.calls['create'] == before['create']
    assert ops.calls['configure'] == before['configure'] + 1
    with helper.frame('lab'):
        assert helper.create('text', (12, 24), {'text': 'New reading', 'fill': 'white'}) == first
    assert ops.items[first][1] == (12, 24)
    assert ops.items[first][2]['text'] == 'New reading'
    assert helper.item_count == 1


def test_mutation_then_repeat_creation_does_not_drift(retained):
    helper, ops = retained
    for _ in range(30):
        with helper.frame('lab'):
            item = helper.create('text', (10, 20), {'text': 'Header', 'font': ('Sans', -16)})
            helper.move(item, 3, 4)
            helper.configure(item, {'font': ('Sans', -12)})
        assert ops.items[item][1] == (13, 24)
        assert ops.items[item][2]['font'] == ('Sans', -12)
    assert ops.calls['create'] == 1


def test_identical_external_setters_are_suppressed(retained):
    helper, ops = retained
    with helper.frame('lab'):
        item = helper.create('text', (10, 20), {'text': 'Header'})
        before = ops.calls.copy()
        helper.set_coords(item, (10, 20))
        helper.configure(item, {'text': 'Header'})
        assert ops.calls == before


def test_tracking_raw_mutations_restores_next_frame_contract(retained):
    helper, ops = retained
    with helper.frame('lab'):
        item = helper.create('text', (10, 20), {'text': 'Header', 'fill': 'white'})
        ops.coords(item, 50, 60)
        helper.note_coords(item, (50, 60))
        ops.configure(item, {'fill': 'red'})
        helper.note_itemconfigure(item, {'fill': 'red'})
    with helper.frame('lab'):
        assert helper.create('text', (10, 20), {'text': 'Header', 'fill': 'white'}) == item
    assert ops.items[item][1:] == [(10, 20), {'text': 'Header', 'fill': 'white'}]


def test_option_schema_and_type_changes_do_not_leak_defaults(retained):
    helper, ops = retained
    with helper.frame('lab'):
        first = helper.create('text', (10, 20), {'text': 'Header', 'fill': 'red'})
    with helper.frame('lab'):
        second = helper.create('text', (10, 20), {'text': 'Header', 'fill': None})
    assert second != first and first not in ops.items
    assert 'fill' not in ops.items[second][2]
    with helper.frame('lab'):
        third = helper.create('image', (10, 20), {'image': 'photo'})
    assert second not in ops.items and third != second


def test_external_added_option_forces_recreation_not_state_leak(retained):
    helper, ops = retained
    with helper.frame('lab'):
        first = helper.create('text', (10, 20), {'text': 'Header'})
        helper.configure(first, {'state': 'hidden'})
    with helper.frame('lab'):
        second = helper.create('text', (10, 20), {'text': 'Header'})
    assert first not in ops.items and second != first
    assert 'state' not in ops.items[second][2]


@pytest.mark.parametrize('key', [('lab', 1, 1600, 1000), ('lab', 1.5, 1600, 1000),
                                ('lab', 1, 1920, 1080), ('lab', 'other-source')])
def test_key_change_invalidates_old_page_scale_size_or_source(retained, key):
    helper, ops = retained
    first = paint(helper)
    second = paint(helper, key=key)
    assert first not in ops.items and first != second
    assert helper.item_count == 5


def test_leaving_lab_external_clear_then_return_rebuilds(retained):
    helper, ops = retained
    first = paint(helper)
    ops.delete('all')
    helper.invalidate()
    ops.create('text', (1, 1), {'text': 'Other page'})
    second = paint(helper)
    assert second != first
    assert all(item[2].get('text') != 'Other page' for item in ops.items.values())


def test_unavailable_frame_removes_all_old_pressure_items(retained):
    helper, ops = retained
    paint(helper, count=120)
    with helper.frame('lab'):
        helper.create('text', (10, 20), {'text': 'Live pressure unavailable', 'fill': 'white'})
    assert helper.item_count == 1
    assert len(ops.items) == 1
    assert not any(item[0] == 'line' for item in ops.items.values())
    paint(helper, count=120)
    assert helper.item_count == len(ops.items) == 121


def test_growth_shrink_and_menu_order_match_fresh_creation_order(retained):
    helper, ops = retained
    for count in (2, 17, 3, 0, 27, 1):
        with helper.frame('lab'):
            background = helper.create('rectangle', (0, 0, 500, 500), {'fill': 'navy'})
            lines = [helper.create('line', (i, 0, i, 40), {'fill': 'teal'}) for i in range(count)]
            foreground = helper.create('text', (10, 20), {'text': 'Current'})
            menu = helper.create('rectangle', (0, 0, 100, 100), {'fill': 'black'})
            action = helper.create('text', (10, 20), {'text': 'Menu action'})
        assert ops.order == [background, *lines, foreground, menu, action]
        assert helper.item_count == len(ops.items) == count + 4


def test_exception_clears_partial_content_and_allows_recovery(retained):
    helper, ops = retained
    paint(helper)
    with pytest.raises(ValueError, match='failed paint'):
        with helper.frame('lab'):
            helper.create('text', (10, 20), {'text': 'Partial'})
            raise ValueError('failed paint')
    assert not helper.active and not ops.items and helper.item_count == 0
    paint(helper)
    assert helper.item_count == 5


def test_no_nested_or_out_of_frame_creation(retained):
    helper, _ = retained
    with pytest.raises(RuntimeError):
        helper.create('text', (1, 2), {'text': 'No frame'})
    with pytest.raises(RuntimeError):
        with helper.frame('lab'):
            with helper.frame('lab'):
                pass
    assert not helper.active


def test_image_reference_retained_only_until_item_removed(retained):
    helper, ops = retained
    class Image:
        pass
    photo = Image()
    reference = weakref.ref(photo)
    with helper.frame('lab'):
        helper.create('image', (10, 20), {'image': photo})
    del photo
    gc.collect()
    assert reference() is not None
    with helper.frame('lab'):
        pass
    gc.collect()
    assert reference() is None
    assert helper.item_count == len(ops.items) == 0


def test_option_lists_detached_from_caller(retained):
    helper, ops = retained
    tags = ['pressure']
    with helper.frame('lab'):
        item = helper.create('text', (10, 20), {'text': 'Header', 'tags': tags})
    tags.append('changed')
    with helper.frame('lab'):
        helper.create('text', (10, 20), {'text': 'Header', 'tags': tags})
    assert ops.items[item][2]['tags'] == ('pressure', 'changed')


def test_selective_delete_does_not_resurrect_old_item(retained):
    helper, ops = retained
    with helper.frame('lab'):
        item = helper.create('text', (1, 2), {'text': 'Measured', 'tags': ('temp',)})
        helper.delete('temp')
    assert item not in ops.items
    with helper.frame('lab'):
        new_item = helper.create('text', (1, 2), {'text': 'Measured', 'tags': ('temp',)})
    assert new_item != item and helper.item_count == 1


def test_current_items_excludes_old_unpainted_items_and_deleted_measurement(retained):
    helper, ops = retained
    paint(helper, count=20)
    with helper.frame('lab'):
        assert helper.current_items == ()
        title = helper.create('text', (10, 20), {'text': 'Header', 'fill': 'white'})
        assert helper.current_items == (title,)
        measurement = helper.create('text', (-4000, -4000), {'text': 'Measure'})
        assert helper.current_items[-1] == measurement
        helper.delete(measurement)
        assert helper.current_items == (title,)
    assert helper.current_items == tuple(ops.order) == (title,)


@pytest.mark.parametrize('raising', [True, False])
@pytest.mark.parametrize('relative', [True, False])
def test_explicit_layering_survives_frame_finish_and_repeat(retained, raising, relative):
    helper, ops = retained
    for _ in range(3):
        with helper.frame('lab'):
            a = helper.create('rectangle', (0, 0, 50, 50), {'fill': 'black', 'tags': ('move',)})
            b = helper.create('text', (20, 20), {'text': 'Middle'})
            c = helper.create('text', (20, 20), {'text': 'Top', 'tags': ('move',)})
            d = helper.create('image', (20, 20), {'image': 'photo'})
            if raising:
                helper.note_raise('move', b if relative else None)
                expected = [b, a, c, d] if relative else [b, d, a, c]
            else:
                helper.note_lower('move', d if relative else None)
                expected = [b, a, c, d] if relative else [a, c, b, d]
            assert list(helper.current_items) == expected
        assert ops.order == expected


def test_raise_to_self_and_missing_relative_leave_order_unchanged(retained):
    helper, _ = retained
    with helper.frame('lab'):
        a = helper.create('text', (10, 20), {'text': 'A'})
        b = helper.create('text', (10, 20), {'text': 'B'})
        helper.note_raise(a, a)
        helper.note_lower(b, 'missing')
        assert helper.current_items == (a, b)


def test_native_canvas_reuse_geometry_order_and_image_lifetime():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('graphical display required')
    try:
        canvas = tk.Canvas(root, width=300, height=200)
        canvas.pack()
        helper = RetainedCanvas(canvas)
        photo = tk.PhotoImage(master=canvas, width=20, height=20)
        photo.put('teal', to=(0, 0, 20, 20))
        for count in (2, 8, 1, 6):
            with helper.frame(('lab', 1)):
                title = helper.create('text', (30, 20), {'text': 'Raw 12.0 kg', 'fill': 'white'})
                helper.set_coords(title, (60, 30))
                image = helper.create('image', (10, 50), {'image': photo, 'anchor': 'nw'})
                lines = [helper.create('line', (i, 60, i + 1, 90), {'fill': 'red'}) for i in range(count)]
                menu = helper.create('text', (60, 30), {'text': 'Action', 'fill': 'gold'})
            root.update_idletasks()
            assert list(canvas.find_all()) == [title, image, *lines, menu]
            assert canvas.coords(title) == [60, 30]
            assert canvas.itemcget(title, 'text') == 'Raw 12.0 kg'
            assert canvas.bbox(image) == (10, 50, 30, 70)
        with helper.frame(('lab', 1)):
            helper.create('text', (60, 30), {'text': 'Live pressure unavailable', 'fill': 'white'})
        assert helper.item_count == len(canvas.find_all()) == 1
    finally:
        root.destroy()
