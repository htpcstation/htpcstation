"""Tests for Task 001 (plex-mylist) — Plex My List backend.

Covers:
  - toggleMyList: add item, remove item, toggle twice returns to empty, persists to file
  - isInMyList: returns True when present, False when absent
  - _rebuild_my_list_model: correct model shape, correct item count
  - getLibraryList: My List entry present when model non-empty, absent when empty, positioned last
  - selectLibrary("_mylist"): sets correct state, no network calls
  - Load on init: model populated from existing file at startup
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_FAKE_SERVER_RESOURCES = [
    {
        "clientIdentifier": "server123",
        "name": "Test Server",
        "owned": True,
        "provides": "server",
        "connections": [
            {
                "uri": "http://server:32400",
                "local": True,
                "relay": False,
                "protocol": "http",
            }
        ],
    }
]


def _make_plex_account_mock():
    """Return a MagicMock PlexAccount class whose instances return fake resources."""
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


def _make_lib(tmp_path: Path, browser_launcher=None):
    """Create a PlexLibrary with CONFIG_DIR redirected to tmp_path.

    Uses monkeypatching at import time so _load_my_list / _save_my_list
    never touch the real ~/.config/htpcstation directory.
    """
    import backend.plex_library as plex_lib_module
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    # Redirect CONFIG_DIR in plex_library before instantiation
    plex_lib_module.CONFIG_DIR = tmp_path

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config, browser_launcher=browser_launcher)

    return lib


@pytest.fixture(autouse=True)
def _restore_config_dir():
    """Restore backend.plex_library.CONFIG_DIR after each test."""
    import backend.plex_library as m
    original = m.CONFIG_DIR
    yield
    m.CONFIG_DIR = original


# ---------------------------------------------------------------------------
# toggleMyList
# ---------------------------------------------------------------------------


class TestToggleMyList:
    """toggleMyList adds/removes items and persists to file."""

    def test_add_item(self, tmp_path: Path) -> None:
        """toggleMyList adds an item when it is not already in the list."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "/path/to/poster.jpg", "")

        items = lib._load_my_list()
        assert len(items) == 1
        assert items[0]["ratingKey"] == "123"
        assert items[0]["title"] == "Dune"
        assert items[0]["type"] == "movie"
        assert items[0]["posterLocal"] == "/path/to/poster.jpg"
        assert items[0]["grandparentTitle"] == ""

    def test_remove_item(self, tmp_path: Path) -> None:
        """toggleMyList removes an item when it is already in the list."""
        lib = _make_lib(tmp_path)
        # Add first
        lib.toggleMyList("123", "Dune", "movie", "", "")
        assert len(lib._load_my_list()) == 1

        # Remove
        lib.toggleMyList("123", "Dune", "movie", "", "")
        assert len(lib._load_my_list()) == 0

    def test_toggle_twice_returns_to_empty(self, tmp_path: Path) -> None:
        """Toggling the same item twice results in an empty list."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("abc", "The Bear", "show", "", "")
        lib.toggleMyList("abc", "The Bear", "show", "", "")

        items = lib._load_my_list()
        assert items == []

    def test_persists_to_file(self, tmp_path: Path) -> None:
        """toggleMyList writes the updated list to the JSON file."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("999", "Oppenheimer", "movie", "/poster.jpg", "")

        mylist_file = tmp_path / "plex_mylist.json"
        assert mylist_file.exists()
        data = json.loads(mylist_file.read_text())
        assert len(data) == 1
        assert data[0]["ratingKey"] == "999"
        assert data[0]["title"] == "Oppenheimer"

    def test_emits_true_when_added(self, tmp_path: Path) -> None:
        """myListChanged is emitted with True when an item is added."""
        lib = _make_lib(tmp_path)
        emitted: list[bool] = []
        lib.myListChanged.connect(lambda added: emitted.append(added))

        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert emitted == [True]

    def test_emits_false_when_removed(self, tmp_path: Path) -> None:
        """myListChanged is emitted with False when an item is removed."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")

        emitted: list[bool] = []
        lib.myListChanged.connect(lambda added: emitted.append(added))

        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert emitted == [False]

    def test_updates_model_after_add(self, tmp_path: Path) -> None:
        """toggleMyList updates _my_list_model after adding an item."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert lib._my_list_model.rowCount() == 1

    def test_updates_model_after_remove(self, tmp_path: Path) -> None:
        """toggleMyList updates _my_list_model after removing an item."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")
        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert lib._my_list_model.rowCount() == 0

    def test_multiple_items_preserved(self, tmp_path: Path) -> None:
        """Adding multiple items keeps all of them in the list."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("1", "Movie A", "movie", "", "")
        lib.toggleMyList("2", "Movie B", "movie", "", "")
        lib.toggleMyList("3", "Show C", "show", "", "")

        items = lib._load_my_list()
        assert len(items) == 3
        keys = [i["ratingKey"] for i in items]
        assert "1" in keys
        assert "2" in keys
        assert "3" in keys

    def test_remove_only_matching_item(self, tmp_path: Path) -> None:
        """Removing one item does not affect other items in the list."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("1", "Movie A", "movie", "", "")
        lib.toggleMyList("2", "Movie B", "movie", "", "")

        # Remove only item "1"
        lib.toggleMyList("1", "Movie A", "movie", "", "")

        items = lib._load_my_list()
        assert len(items) == 1
        assert items[0]["ratingKey"] == "2"

    def test_episode_with_grandparent_title(self, tmp_path: Path) -> None:
        """toggleMyList stores grandparentTitle for episodes."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("ep1", "Pilot", "episode", "", "My Show")

        items = lib._load_my_list()
        assert items[0]["grandparentTitle"] == "My Show"


# ---------------------------------------------------------------------------
# isInMyList
# ---------------------------------------------------------------------------


class TestIsInMyList:
    """isInMyList returns True when present, False when absent."""

    def test_returns_true_when_present(self, tmp_path: Path) -> None:
        """isInMyList returns True for an item that has been added."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert lib.isInMyList("123") is True

    def test_returns_false_when_absent(self, tmp_path: Path) -> None:
        """isInMyList returns False for an item that has not been added."""
        lib = _make_lib(tmp_path)
        assert lib.isInMyList("999") is False

    def test_returns_false_after_removal(self, tmp_path: Path) -> None:
        """isInMyList returns False after an item has been removed."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")
        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert lib.isInMyList("123") is False

    def test_returns_false_for_empty_list(self, tmp_path: Path) -> None:
        """isInMyList returns False when the list is empty."""
        lib = _make_lib(tmp_path)
        assert lib.isInMyList("any-key") is False

    def test_does_not_match_partial_key(self, tmp_path: Path) -> None:
        """isInMyList does not match a partial ratingKey."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("12345", "Dune", "movie", "", "")

        assert lib.isInMyList("123") is False


# ---------------------------------------------------------------------------
# getMyListItemType
# ---------------------------------------------------------------------------


class TestGetMyListItemType:
    """getMyListItemType returns the type of a My List item by ratingKey."""

    def test_returns_movie_type(self, tmp_path: Path) -> None:
        """Returns 'movie' for a movie item."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("123", "Dune", "movie", "", "")

        assert lib.getMyListItemType("123") == "movie"

    def test_returns_show_type(self, tmp_path: Path) -> None:
        """Returns 'show' for a show item."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("456", "The Bear", "show", "", "")

        assert lib.getMyListItemType("456") == "show"

    def test_returns_episode_type(self, tmp_path: Path) -> None:
        """Returns 'episode' for an episode item."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("789", "Pilot", "episode", "", "The Bear")

        assert lib.getMyListItemType("789") == "episode"

    def test_returns_empty_for_unknown_key(self, tmp_path: Path) -> None:
        """Returns '' for a ratingKey not in My List."""
        lib = _make_lib(tmp_path)

        assert lib.getMyListItemType("nonexistent") == ""

    def test_returns_empty_for_empty_list(self, tmp_path: Path) -> None:
        """Returns '' when My List is empty."""
        lib = _make_lib(tmp_path)

        assert lib.getMyListItemType("any") == ""


# ---------------------------------------------------------------------------
# _rebuild_my_list_model
# ---------------------------------------------------------------------------


class TestRebuildMyListModel:
    """_rebuild_my_list_model produces the correct model shape and item count."""

    def test_correct_item_count(self, tmp_path: Path) -> None:
        """_rebuild_my_list_model sets the correct number of items in the model."""
        lib = _make_lib(tmp_path)
        items = [
            {"ratingKey": "1", "title": "Movie A", "type": "movie",
             "posterLocal": "", "grandparentTitle": ""},
            {"ratingKey": "2", "title": "Show B", "type": "show",
             "posterLocal": "", "grandparentTitle": ""},
        ]

        lib._rebuild_my_list_model(items)

        assert lib._my_list_model.rowCount() == 2

    def test_correct_model_shape(self, tmp_path: Path) -> None:
        """_rebuild_my_list_model maps JSON fields to the PlexOnDeckModel shape."""
        from backend.plex_library import PlexOnDeckModel

        lib = _make_lib(tmp_path)
        items = [
            {
                "ratingKey": "42",
                "title": "Dune",
                "type": "movie",
                "posterLocal": "/path/to/poster.jpg",
                "grandparentTitle": "",
            }
        ]

        lib._rebuild_my_list_model(items)

        idx = lib._my_list_model.index(0, 0)
        assert lib._my_list_model.data(idx, PlexOnDeckModel.RatingKeyRole) == "42"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.TitleRole) == "Dune"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.TypeRole) == "movie"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.PosterLocalRole) == "/path/to/poster.jpg"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.GrandparentTitleRole) == ""
        assert lib._my_list_model.data(idx, PlexOnDeckModel.ViewOffsetRole) == 0
        assert lib._my_list_model.data(idx, PlexOnDeckModel.DurationRole) == 0

    def test_episode_grandparent_title(self, tmp_path: Path) -> None:
        """_rebuild_my_list_model maps grandparentTitle for episodes."""
        from backend.plex_library import PlexOnDeckModel

        lib = _make_lib(tmp_path)
        items = [
            {
                "ratingKey": "ep1",
                "title": "Pilot",
                "type": "episode",
                "posterLocal": "",
                "grandparentTitle": "My Show",
            }
        ]

        lib._rebuild_my_list_model(items)

        idx = lib._my_list_model.index(0, 0)
        assert lib._my_list_model.data(idx, PlexOnDeckModel.GrandparentTitleRole) == "My Show"

    def test_empty_list_clears_model(self, tmp_path: Path) -> None:
        """_rebuild_my_list_model with an empty list clears the model."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("1", "Movie", "movie", "", "")
        assert lib._my_list_model.rowCount() == 1

        lib._rebuild_my_list_model([])

        assert lib._my_list_model.rowCount() == 0

    def test_missing_optional_fields_use_defaults(self, tmp_path: Path) -> None:
        """_rebuild_my_list_model handles missing posterLocal and grandparentTitle."""
        from backend.plex_library import PlexOnDeckModel

        lib = _make_lib(tmp_path)
        items = [
            {"ratingKey": "1", "title": "Movie", "type": "movie"}
        ]

        lib._rebuild_my_list_model(items)

        idx = lib._my_list_model.index(0, 0)
        assert lib._my_list_model.data(idx, PlexOnDeckModel.PosterLocalRole) == ""
        assert lib._my_list_model.data(idx, PlexOnDeckModel.GrandparentTitleRole) == ""


# ---------------------------------------------------------------------------
# getLibraryList — My List entry
# ---------------------------------------------------------------------------


class TestGetLibraryListMyList:
    """getLibraryList() includes a 'My List' entry when the model is non-empty."""

    def test_mylist_entry_present_when_model_non_empty(self, tmp_path: Path) -> None:
        """My List entry appears when _my_list_model has items."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("1", "Dune", "movie", "", "")

        result = lib.getLibraryList()

        titles = [entry["title"] for entry in result]
        assert "My List" in titles

        mylist_entry = next(e for e in result if e["title"] == "My List")
        assert mylist_entry["type"] == "mylist"
        assert mylist_entry["sectionKey"] == "_mylist"
        assert mylist_entry["count"] == 1

    def test_mylist_entry_absent_when_model_empty(self, tmp_path: Path) -> None:
        """My List entry is absent when _my_list_model has no items."""
        lib = _make_lib(tmp_path)
        # _my_list_model is empty by default
        result = lib.getLibraryList()

        titles = [entry["title"] for entry in result]
        assert "My List" not in titles

    def test_mylist_positioned_last(self, tmp_path: Path) -> None:
        """My List appears after Live TV (at the end of the list)."""
        lib = _make_lib(tmp_path)
        lib._on_deck_model.set_items([
            {"rating_key": "1", "title": "Ep 1", "type": "episode",
             "poster_local": "", "grandparent_title": "Show",
             "view_offset": 0, "duration": 1000, "thumb_path": ""},
        ])
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])
        lib.toggleMyList("abc", "Dune", "movie", "", "")

        result = lib.getLibraryList()

        titles = [entry["title"] for entry in result]
        livetv_idx = titles.index("Live TV")
        mylist_idx = titles.index("My List")

        assert mylist_idx > livetv_idx, "My List should appear after Live TV"
        assert mylist_idx == len(result) - 1, "My List should be the last entry"

    def test_mylist_count_reflects_model_size(self, tmp_path: Path) -> None:
        """My List count matches the number of items in the model."""
        lib = _make_lib(tmp_path)
        for i in range(3):
            lib.toggleMyList(str(i), f"Item {i}", "movie", "", "")

        result = lib.getLibraryList()

        mylist_entry = next(e for e in result if e["title"] == "My List")
        assert mylist_entry["count"] == 3

    def test_mylist_absent_after_all_items_removed(self, tmp_path: Path) -> None:
        """My List entry disappears when all items are removed."""
        lib = _make_lib(tmp_path)
        lib.toggleMyList("1", "Dune", "movie", "", "")
        lib.toggleMyList("1", "Dune", "movie", "", "")  # remove

        result = lib.getLibraryList()

        titles = [entry["title"] for entry in result]
        assert "My List" not in titles


# ---------------------------------------------------------------------------
# selectLibrary("_mylist")
# ---------------------------------------------------------------------------


class TestSelectLibraryMyList:
    """selectLibrary('_mylist') sets state without making network calls."""

    def test_sets_current_section_type_to_mylist(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') sets _current_section_type = 'mylist'."""
        lib = _make_lib(tmp_path)
        lib.selectLibrary("_mylist")

        assert lib._current_section_type == "mylist"

    def test_sets_current_section_key(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') sets _current_section_key = '_mylist'."""
        lib = _make_lib(tmp_path)
        lib.selectLibrary("_mylist")

        assert lib._current_section_key == "_mylist"

    def test_sets_current_library_to_my_list(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') sets _current_library = 'My List'."""
        lib = _make_lib(tmp_path)
        lib.selectLibrary("_mylist")

        assert lib._current_library == "My List"

    def test_emits_current_library_changed(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') emits currentLibraryChanged with 'My List'."""
        lib = _make_lib(tmp_path)
        emitted: list[str] = []
        lib.currentLibraryChanged.connect(lambda title: emitted.append(title))

        lib.selectLibrary("_mylist")

        assert emitted == ["My List"]

    def test_does_not_submit_worker(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') must not submit a network worker."""
        lib = _make_lib(tmp_path)
        submit_calls: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

        lib.selectLibrary("_mylist")

        assert len(submit_calls) == 0, "No worker should be submitted for _mylist"

    def test_does_not_reset_movies_state(self, tmp_path: Path) -> None:
        """selectLibrary('_mylist') must not reset _movies_loaded/_movies_total."""
        lib = _make_lib(tmp_path)
        lib._movies_loaded = 50
        lib._movies_total = 200

        lib.selectLibrary("_mylist")

        assert lib._movies_loaded == 50
        assert lib._movies_total == 200


# ---------------------------------------------------------------------------
# Load on init
# ---------------------------------------------------------------------------


class TestLoadOnInit:
    """Model is populated from existing file at startup."""

    def test_model_populated_from_existing_file(self, tmp_path: Path) -> None:
        """PlexLibrary loads My List from file during __init__."""
        mylist_file = tmp_path / "plex_mylist.json"
        mylist_file.write_text(
            json.dumps([
                {
                    "ratingKey": "42",
                    "title": "Dune",
                    "type": "movie",
                    "posterLocal": "/path/to/poster.jpg",
                    "grandparentTitle": "",
                },
                {
                    "ratingKey": "99",
                    "title": "The Bear",
                    "type": "show",
                    "posterLocal": "",
                    "grandparentTitle": "",
                },
            ]),
            encoding="utf-8",
        )

        lib = _make_lib(tmp_path)
        assert lib._my_list_model.rowCount() == 2

    def test_model_empty_when_no_file(self, tmp_path: Path) -> None:
        """PlexLibrary starts with an empty My List when no file exists."""
        lib = _make_lib(tmp_path)
        assert lib._my_list_model.rowCount() == 0

    def test_model_empty_when_file_is_corrupt(self, tmp_path: Path) -> None:
        """PlexLibrary starts with an empty My List when the file is corrupt JSON."""
        mylist_file = tmp_path / "plex_mylist.json"
        mylist_file.write_text("not valid json", encoding="utf-8")

        lib = _make_lib(tmp_path)
        assert lib._my_list_model.rowCount() == 0

    def test_model_items_have_correct_data(self, tmp_path: Path) -> None:
        """Items loaded from file have the correct data in the model."""
        from backend.plex_library import PlexOnDeckModel

        mylist_file = tmp_path / "plex_mylist.json"
        mylist_file.write_text(
            json.dumps([
                {
                    "ratingKey": "42",
                    "title": "Dune",
                    "type": "movie",
                    "posterLocal": "/path/to/poster.jpg",
                    "grandparentTitle": "",
                }
            ]),
            encoding="utf-8",
        )

        lib = _make_lib(tmp_path)
        idx = lib._my_list_model.index(0, 0)
        assert lib._my_list_model.data(idx, PlexOnDeckModel.RatingKeyRole) == "42"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.TitleRole) == "Dune"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.TypeRole) == "movie"
        assert lib._my_list_model.data(idx, PlexOnDeckModel.PosterLocalRole) == "/path/to/poster.jpg"
