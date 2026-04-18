"""
Basic unit tests for NeedsFinder using mocked data.
Run with: pytest
"""
from unittest.mock import MagicMock, patch
from src.tracker.needs_finder import NeedsFinder


def _make_obs(code: str, name: str) -> dict:
    return {
        "speciesCode": code,
        "comName": name,
        "sciName": f"Testus {code}",
        "obsDt": "2026-04-15 08:00",
        "locName": "Test Hotspot",
        "lat": 47.6,
        "lng": -122.3,
        "howMany": 1,
    }


def test_local_needs_excludes_seen_species():
    client = MagicMock()
    client.recent_observations_nearby.return_value = [
        _make_obs("norsho", "Northern Shoveler"),
        _make_obs("mallar3", "Mallard"),
    ]

    personal = MagicMock()
    personal.species_seen_this_year.return_value = {"mallar3"}

    finder = NeedsFinder(client, personal)
    needs = finder.local_needs(47.6, -122.3)

    codes = [n.species_code for n in needs]
    assert "mallar3" not in codes
    assert "norsho" in codes


def test_local_needs_empty_when_all_seen():
    client = MagicMock()
    client.recent_observations_nearby.return_value = [_make_obs("mallar3", "Mallard")]

    personal = MagicMock()
    personal.species_seen_this_year.return_value = {"mallar3"}

    finder = NeedsFinder(client, personal)
    needs = finder.local_needs(47.6, -122.3)
    assert needs == []
