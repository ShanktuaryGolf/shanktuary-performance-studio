"""Run on a graphical desktop; fixture isolates every persisted data file."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_concept_ui import click, desktop  # noqa: F401


def key(app, root, name):
    app.handle_key_press(SimpleNamespace(keysym=name, char=""))
    root.update()


@pytest.mark.parametrize("dismissal", ["escape", "outside", "cancel", "select"])
def test_fit_popup_dismisses_and_reopens(desktop, dismissal):
    app, root, errors = desktop
    app.set_mode(7)
    root.update()
    base, test = app.concept_fit_selector_rects
    before = app.fitting_baseline_club
    click(app, root, test[:4])
    menu = app._concept_fit_menu
    assert menu.winfo_ismapped()
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
              if menu.type(i) != "separator"]
    assert set(c["name"] for c in app.bag) - {before} <= set(labels)
    assert menu.grab_current() == menu
    if dismissal == "escape":
        assert root.focus_get() == menu
        menu.event_generate("<Escape>")
    elif dismissal == "outside":
        menu.event_generate("<ButtonPress-1>", x=-20, y=-20)
        menu.event_generate("<ButtonRelease-1>", x=-20, y=-20)
    elif dismissal == "cancel":
        menu.invoke(menu.index("end"))
    else:
        selected = labels[-2]
        menu.invoke(labels.index(selected))
        assert app.current_club == selected
    root.update()
    assert not menu.winfo_exists() or not menu.winfo_ismapped()
    assert root.grab_current() is None
    assert app.fitting_baseline_club == before
    click(app, root, base[:4])
    menu = app._concept_fit_menu
    assert menu.winfo_ismapped()
    menu.invoke(menu.index("end"))
    root.update()
    app.set_mode(1)
    root.update()
    assert app.view_mode == 1 and not errors


def test_new_club_scope_cancel_and_keyboard_default(desktop):
    app, root, errors = desktop
    app.set_mode(7)
    root.update()
    bag, names = deepcopy(app.bag), list(app.clubs)
    click(app, root, app.fitting_add_club_rect)
    assert app.show_custom_club_modal and app.custom_club_scope == "session"
    app.custom_club_input_text = "Session trial wedge"
    key(app, root, "Return")
    assert app.bag == bag and app.clubs == names
    assert app.current_club == "Session trial wedge"
    assert "Session trial wedge" in app.get_fitting_clubs()
    assert not app.show_spec_editor_modal
    # A permanent choice does not survive cancelling/reopening the form.
    click(app, root, app.fitting_add_club_rect)
    permanent = next(r[:4] for r in app.custom_club_scope_rects if r[4] == "bag")
    click(app, root, permanent)
    assert app.custom_club_scope == "bag"
    key(app, root, "Escape")
    assert app.bag == bag
    click(app, root, app.fitting_add_club_rect)
    assert app.custom_club_scope == "session"
    app.custom_club_input_text = "Permanent trial wedge"
    permanent = next(r[:4] for r in app.custom_club_scope_rects if r[4] == "bag")
    click(app, root, permanent)
    click(app, root, app.custom_club_modal_add_rect)
    assert app.get_bag_club("Permanent trial wedge") is not None
    assert app.show_spec_editor_modal
    assert not errors


def test_new_club_cancel_outside_and_empty_confirm_are_noops(desktop):
    app, root, errors = desktop
    app.set_mode(7)
    root.update()
    original = deepcopy((app.bag, app.clubs, app.sessions))
    for action in ("cancel", "outside", "empty"):
        click(app, root, app.fitting_add_club_rect)
        if action == "cancel":
            app.custom_club_input_text = "Discard this club"
            click(app, root, app.custom_club_modal_cancel_rect)
        elif action == "outside":
            app.custom_club_input_text = "Discard this club"
            app.handle_mouse_press(SimpleNamespace(x=10, y=10, num=1))
            root.update()
        else:
            key(app, root, "Return")
        assert not app.show_custom_club_modal
        assert (app.bag, app.clubs, app.sessions) == original
    assert not errors
