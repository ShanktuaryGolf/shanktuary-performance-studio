"""Unit tests for Auto-Fill Iron Set feature."""
from unittest.mock import MagicMock
import pytest

from club_fetcher import fetch_club_specs
import shanktuary_performance_studio as studio


class DummyApp:
    """Lightweight test harness for ShanktuaryPerformanceStudio autofill methods."""

    def __init__(self):
        self.bag = []
        self.clubs = []
        self.current_club = "7 Iron"
        self.copy_feedback = ""
        self.show_club_menu = False
        self.show_tools_menu = False
        self.show_session_dropdown = False
        self.show_filter_dropdown = False
        self.show_custom_club_modal = False
        self.show_spec_editor_modal = False
        self.show_autofill_modal = False

        self.autofill_brand = "Callaway"
        self.autofill_model = "Paradym X"
        self.autofill_active_field = "model"
        self.autofill_selected_clubs = {"4 Iron", "5 Iron", "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW"}

        self.root = MagicMock()
        self.save_session_to_file = MagicMock()
        self.draw_screen = MagicMock()
        self.clear_copy_feedback = MagicMock()

    get_bag_club = studio.ShanktuaryApp.get_bag_club
    update_club_specs = studio.ShanktuaryApp.update_club_specs
    add_club_to_bag = studio.ShanktuaryApp.add_club_to_bag
    apply_fetched_club_specs = studio.ShanktuaryApp.apply_fetched_club_specs
    open_autofill_modal = studio.ShanktuaryApp.open_autofill_modal
    apply_autofill_specs = studio.ShanktuaryApp.apply_autofill_specs


def test_open_autofill_modal():
    app = DummyApp()
    app.open_autofill_modal()
    assert app.show_autofill_modal is True
    assert app.show_spec_editor_modal is False
    assert app.autofill_active_field == "model"
    app.draw_screen.assert_called_once()


def test_apply_autofill_specs_success():
    app = DummyApp()
    app.autofill_brand = "Callaway"
    app.autofill_model = "Paradym X"
    app.autofill_selected_clubs = {"4 Iron", "7 Iron", "PW"}

    app.apply_autofill_specs()

    assert app.show_autofill_modal is False
    assert len(app.bag) == 3

    c4 = app.get_bag_club("4 Iron")
    assert c4 is not None
    assert c4["brand"] == "Callaway"
    assert c4["model"] == "Paradym X"
    assert c4["loft_deg"] == 18.5
    assert c4["lie_deg"] == 61.0
    assert c4["category"] == "Irons"

    c7 = app.get_bag_club("7 Iron")
    assert c7 is not None
    assert c7["loft_deg"] == 27.5
    assert c7["lie_deg"] == 62.5
    assert c7["category"] == "Irons"

    cpw = app.get_bag_club("PW")
    assert cpw is not None
    assert cpw["loft_deg"] == 41.0
    assert cpw["lie_deg"] == 64.0
    assert cpw["category"] == "Wedges"

    assert "Updated 3 club(s)" in app.copy_feedback


def test_apply_autofill_specs_updates_existing_club():
    app = DummyApp()
    # Pre-populate 7 Iron with generic/zero specs
    app.add_club_to_bag("7 Iron", category="Irons", brand="", model="", loft_deg=0.0, lie_deg=0.0)
    assert len(app.bag) == 1

    app.autofill_brand = "Callaway"
    app.autofill_model = "Paradym X"
    app.autofill_selected_clubs = {"7 Iron"}

    app.apply_autofill_specs()

    assert len(app.bag) == 1
    c7 = app.get_bag_club("7 Iron")
    assert c7["loft_deg"] == 27.5
    assert c7["lie_deg"] == 62.5
    assert c7["brand"] == "Callaway"
    assert c7["model"] == "Paradym X"


def test_apply_autofill_specs_unknown_model():
    app = DummyApp()
    app.autofill_brand = "Nonexistent"
    app.autofill_model = "UnknownModel"
    app.autofill_selected_clubs = {"7 Iron"}

    app.apply_autofill_specs()

    assert len(app.bag) == 0
    assert "No specs found" in app.copy_feedback


def test_apply_autofill_specs_empty_selection():
    app = DummyApp()
    app.autofill_brand = "Callaway"
    app.autofill_model = "Paradym X"
    app.autofill_selected_clubs = set()

    app.apply_autofill_specs()

    assert len(app.bag) == 0
    assert "Select brand, model, and at least one club" in app.copy_feedback
