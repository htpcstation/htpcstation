"""Tests for getSectionSort and getSectionGenre slots (Task 001).

Covers:
  - getSectionSort returns the correct QML sort key for a stored API sort string
  - getSectionSort returns '' when the section has no stored sort
  - getSectionSort returns '' when the stored API sort string is not in _SORT_MAP_REVERSE
  - getSectionGenre returns the stored genre key for a section
  - getSectionGenre returns '' when the section has no stored genre
  - _SORT_MAP_REVERSE is the exact inverse of _SORT_MAP
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.plex_library import PlexLibrary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lib() -> PlexLibrary:
    """Create a PlexLibrary instance with mocked external dependencies."""
    from backend.config import Config

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount"), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"):
        config = MagicMock(spec=Config)
        config.plex_server_id = "srv1"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)
    return lib


# ---------------------------------------------------------------------------
# _SORT_MAP_REVERSE
# ---------------------------------------------------------------------------


class TestSortMapReverse:
    def test_reverse_map_is_exact_inverse_of_sort_map(self) -> None:
        """_SORT_MAP_REVERSE must be the perfect inverse of _SORT_MAP."""
        sort_map = PlexLibrary._SORT_MAP
        reverse_map = PlexLibrary._SORT_MAP_REVERSE
        assert len(reverse_map) == len(sort_map)
        for qml_key, api_sort in sort_map.items():
            assert reverse_map[api_sort] == qml_key


# ---------------------------------------------------------------------------
# getSectionSort
# ---------------------------------------------------------------------------


class TestGetSectionSort:
    def test_returns_qml_key_for_stored_api_sort(self) -> None:
        """getSectionSort translates a stored API sort string back to QML key."""
        lib = _make_lib()
        lib._section_sort["movies1"] = "audienceRating:desc"
        assert lib.getSectionSort("movies1") == "rating"

    def test_returns_empty_string_when_no_stored_sort(self) -> None:
        """getSectionSort returns '' when the section has no stored sort."""
        lib = _make_lib()
        assert lib.getSectionSort("unknown_section") == ""

    def test_returns_empty_string_for_default_sort(self) -> None:
        """getSectionSort returns '' when stored API sort is '' (default order)."""
        lib = _make_lib()
        lib._section_sort["movies1"] = ""
        assert lib.getSectionSort("movies1") == ""

    def test_returns_az_sort_correctly(self) -> None:
        lib = _make_lib()
        lib._section_sort["sec"] = "titleSort:asc"
        assert lib.getSectionSort("sec") == "az"

    def test_returns_za_sort_correctly(self) -> None:
        lib = _make_lib()
        lib._section_sort["sec"] = "titleSort:desc"
        assert lib.getSectionSort("sec") == "za"

    def test_returns_recent_sort_correctly(self) -> None:
        lib = _make_lib()
        lib._section_sort["sec"] = "addedAt:desc"
        assert lib.getSectionSort("sec") == "recent"

    def test_returns_year_desc_sort_correctly(self) -> None:
        lib = _make_lib()
        lib._section_sort["sec"] = "year:desc"
        assert lib.getSectionSort("sec") == "year_desc"

    def test_returns_year_asc_sort_correctly(self) -> None:
        lib = _make_lib()
        lib._section_sort["sec"] = "year:asc"
        assert lib.getSectionSort("sec") == "year_asc"

    def test_unknown_api_sort_returns_empty_string(self) -> None:
        """getSectionSort returns '' for an API sort string not in _SORT_MAP_REVERSE."""
        lib = _make_lib()
        lib._section_sort["sec"] = "some_unknown_sort:asc"
        assert lib.getSectionSort("sec") == ""


# ---------------------------------------------------------------------------
# getSectionGenre
# ---------------------------------------------------------------------------


class TestGetSectionGenre:
    def test_returns_stored_genre_key(self) -> None:
        """getSectionGenre returns the stored genre key for a section."""
        lib = _make_lib()
        lib._section_genre["movies1"] = "/library/sections/1/genre/5"
        assert lib.getSectionGenre("movies1") == "/library/sections/1/genre/5"

    def test_returns_empty_string_when_no_stored_genre(self) -> None:
        """getSectionGenre returns '' when the section has no stored genre."""
        lib = _make_lib()
        assert lib.getSectionGenre("unknown_section") == ""

    def test_returns_empty_string_when_genre_cleared(self) -> None:
        """getSectionGenre returns '' when genre was explicitly cleared."""
        lib = _make_lib()
        lib._section_genre["sec"] = ""
        assert lib.getSectionGenre("sec") == ""
