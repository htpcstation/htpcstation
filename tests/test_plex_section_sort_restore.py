"""Tests for getSectionSort, getSectionGenre slots (Task 001) and
sort-on-cache-load behaviour (Task 007).

Covers:
  - getSectionSort returns the correct QML sort key for a stored API sort string
  - getSectionSort returns '' when the section has no stored sort
  - getSectionSort returns '' when the stored API sort string is not in _SORT_MAP_REVERSE
  - getSectionGenre returns the stored genre key for a section
  - getSectionGenre returns '' when the section has no stored genre
  - _SORT_MAP_REVERSE is the exact inverse of _SORT_MAP
  - selectLibrary applies persisted sort to cached movies before display
  - selectLibrary applies persisted sort to cached shows before display
  - selectLibrary does NOT sort cached data when no sort is persisted
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.plex_library import PlexLibrary
from backend.plex_models import PlexMovie, PlexShow


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


# ---------------------------------------------------------------------------
# selectLibrary — applies persisted sort to cached data (Task 007)
# ---------------------------------------------------------------------------


def _make_movie(title: str, added_at: int = 0) -> PlexMovie:
    return PlexMovie(
        rating_key="1",
        title=title,
        year=2020,
        summary="",
        content_rating="",
        audience_rating=0.0,
        duration_ms=0,
        studio="",
        tagline="",
        thumb_path="",
        art_path="",
        genres=[],
        directors=[],
        cast=[],
        added_at=added_at,
        poster_local="",
    )


def _make_show(title: str) -> PlexShow:
    return PlexShow(
        rating_key="1",
        title=title,
        year=2020,
        summary="",
        content_rating="",
        audience_rating=0.0,
        thumb_path="",
        art_path="",
        genres=[],
        cast=[],
        child_count=0,
        leaf_count=0,
        viewed_leaf_count=0,
        poster_local="",
    )


class TestSelectLibraryAppliesCachedSort:
    """selectLibrary must apply persisted sort to cached data before first display."""

    def _make_offline_lib(self, section_key: str, section_type: str) -> PlexLibrary:
        """Return a PlexLibrary with no server connection and the given library configured."""
        lib = _make_lib()
        lib._client = None  # offline — skip network fetch path
        lib._setup_complete = True
        lib._libraries_model.set_items([
            {"title": "Movies", "type": section_type, "key": section_key},
        ])
        # Suppress executor submissions (offline path hits sectionLoadFailed emit)
        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]
        return lib

    def test_movies_are_sorted_za_when_persisted_sort_is_za(self) -> None:
        """Cached movies are sorted Z-A when 'titleSort:desc' is persisted for the section."""
        lib = self._make_offline_lib("4", "movie")
        lib._section_sort["4"] = "titleSort:desc"

        unsorted = [_make_movie("Zorro"), _make_movie("Alpha"), _make_movie("Midway")]
        lib._load_movies_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        titles = [lib._movies_model._movies[i].title for i in range(len(lib._movies_model._movies))]
        assert titles == sorted([m.title for m in unsorted], reverse=True)

    def test_movies_are_sorted_az_when_persisted_sort_is_az(self) -> None:
        """Cached movies are sorted A-Z when 'titleSort:asc' is persisted for the section."""
        lib = self._make_offline_lib("4", "movie")
        lib._section_sort["4"] = "titleSort:asc"

        unsorted = [_make_movie("Zorro"), _make_movie("Alpha"), _make_movie("Midway")]
        lib._load_movies_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        titles = [lib._movies_model._movies[i].title for i in range(len(lib._movies_model._movies))]
        assert titles == sorted([m.title for m in unsorted])

    def test_movies_not_sorted_when_no_persisted_sort(self) -> None:
        """Cached movies are displayed in original cache order when no sort is persisted."""
        lib = self._make_offline_lib("4", "movie")
        # No entry in _section_sort for "4"

        unsorted = [_make_movie("Zorro"), _make_movie("Alpha"), _make_movie("Midway")]
        lib._load_movies_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        titles = [lib._movies_model._movies[i].title for i in range(len(lib._movies_model._movies))]
        assert titles == [m.title for m in unsorted]

    def test_shows_are_sorted_za_when_persisted_sort_is_za(self) -> None:
        """Cached shows are sorted Z-A when 'titleSort:desc' is persisted for the section."""
        lib = self._make_offline_lib("3", "show")
        lib._section_sort["3"] = "titleSort:desc"

        unsorted = [_make_show("Zorro"), _make_show("Alpha"), _make_show("Midway")]
        lib._load_shows_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("3")

        titles = [lib._shows_model._shows[i].title for i in range(len(lib._shows_model._shows))]
        assert titles == sorted([s.title for s in unsorted], reverse=True)

    def test_shows_are_sorted_az_when_persisted_sort_is_az(self) -> None:
        """Cached shows are sorted A-Z when 'titleSort:asc' is persisted for the section."""
        lib = self._make_offline_lib("3", "show")
        lib._section_sort["3"] = "titleSort:asc"

        unsorted = [_make_show("Zorro"), _make_show("Alpha"), _make_show("Midway")]
        lib._load_shows_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("3")

        titles = [lib._shows_model._shows[i].title for i in range(len(lib._shows_model._shows))]
        assert titles == sorted([s.title for s in unsorted])

    def test_shows_not_sorted_when_no_persisted_sort(self) -> None:
        """Cached shows are displayed in original cache order when no sort is persisted."""
        lib = self._make_offline_lib("3", "show")
        # No entry in _section_sort for "3"

        unsorted = [_make_show("Zorro"), _make_show("Alpha"), _make_show("Midway")]
        lib._load_shows_cache = lambda key: list(unsorted)  # type: ignore[method-assign]
        lib._resolve_cached_posters = lambda items: None  # type: ignore[method-assign]

        lib.selectLibrary("3")

        titles = [lib._shows_model._shows[i].title for i in range(len(lib._shows_model._shows))]
        assert titles == [s.title for s in unsorted]
