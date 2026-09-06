"""Pure-function tests for club_fetcher (no Tkinter, no network)."""
import json

from club_fetcher import fetch_club_specs, normalize_club_name


def test_paradym_x_4_iron_matches_callaway_sheet():
    result = fetch_club_specs("Callaway", "Paradym X", ["4 Iron"])
    assert result == {"4 Iron": {"loft_deg": 18.5, "lie_deg": 61.0}}


def test_paradym_x_4_through_pw():
    clubs = ["4 Iron", "5 Iron", "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW"]
    result = fetch_club_specs("Callaway", "Paradym X", clubs)
    assert set(result) == set(clubs)
    assert result["7 Iron"] == {"loft_deg": 27.5, "lie_deg": 62.5}
    assert result["PW"] == {"loft_deg": 41.0, "lie_deg": 64.0}


def test_aliases_and_casefold():
    result = fetch_club_specs("callaway", "paradym  x", ["4I", "pw"])
    assert result["4 Iron"]["loft_deg"] == 18.5
    assert result["PW"]["lie_deg"] == 64.0


def test_unknown_model_returns_empty():
    assert fetch_club_specs("Callaway", "Not A Real Set", ["7 Iron"]) == {}


def test_unknown_club_in_known_set_omitted():
    result = fetch_club_specs("Callaway", "Paradym X", ["7 Iron", "2 Iron"])
    assert result == {"7 Iron": {"loft_deg": 27.5, "lie_deg": 62.5}}


def test_empty_or_blank_inputs_return_empty():
    assert fetch_club_specs("", "Paradym X", ["7 Iron"]) == {}
    assert fetch_club_specs("Callaway", "Paradym X", []) == {}


def test_normalize_club_name():
    assert normalize_club_name("4i") == "4 Iron"
    assert normalize_club_name("pitching wedge") == "PW"


def test_db_values_are_numbers():
    from pathlib import Path
    from club_fetcher import DB_PATH

    data = json.loads(Path(DB_PATH).read_text(encoding="utf-8"))
    clubs = data["sets"][0]["clubs"]
    for spec in clubs.values():
        assert isinstance(spec["loft_deg"], (int, float))
        assert isinstance(spec["lie_deg"], (int, float))
