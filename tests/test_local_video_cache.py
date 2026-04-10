"""Tests for LocalVideoCache and related helpers.

Covers:
  - ensure_dirs() creates expected directory structure
  - load(): absent file, malformed JSON, round-trip
  - set_entry(): merging, custom preservation
  - resolve_poster(): priority ordering, missing-file fallback
  - resolve_metadata(): custom overrides, absent key defaults
  - is_tombstoned(): various states
  - write_tombstone(): preserves custom dict
  - _slugify(): transformations
  - _custom_category_cache(): uses slugified name for dir
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.local_video_library as _mod
from backend.local_video_library import (
    LocalVideoCache,
    _custom_category_cache,
    _movies_cache,
    _slugify,
    _tv_shows_cache,
)


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_lowercase(self) -> None:
        assert _slugify("MOVIES") == "movies"

    def test_spaces_become_underscores(self) -> None:
        assert _slugify("My Movies") == "my_movies"

    def test_punctuation_removed(self) -> None:
        assert _slugify("Sci-Fi & Fantasy!") == "sci_fi_fantasy"

    def test_leading_trailing_separators_stripped(self) -> None:
        assert _slugify("  hello  ") == "hello"

    def test_multiple_separators_collapse(self) -> None:
        assert _slugify("a---b") == "a_b"

    def test_numbers_preserved(self) -> None:
        assert _slugify("Top 10 Movies") == "top_10_movies"

    def test_already_valid(self) -> None:
        assert _slugify("movies") == "movies"


# ---------------------------------------------------------------------------
# LocalVideoCache: ensure_dirs
# ---------------------------------------------------------------------------


class TestEnsureDirs:
    def test_creates_cache_dir_and_artwork_custom(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        c = LocalVideoCache(cache_dir, has_scraped_art=False)
        c.ensure_dirs()
        assert cache_dir.is_dir()
        assert (cache_dir / "artwork_custom").is_dir()

    def test_creates_artwork_scraped_when_enabled(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        c = LocalVideoCache(cache_dir, has_scraped_art=True)
        c.ensure_dirs()
        assert (cache_dir / "artwork_scraped").is_dir()

    def test_no_artwork_scraped_for_custom_category(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "custom"
        c = LocalVideoCache(cache_dir, has_scraped_art=False)
        c.ensure_dirs()
        assert not (cache_dir / "artwork_scraped").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        c = LocalVideoCache(cache_dir, has_scraped_art=True)
        c.ensure_dirs()
        c.ensure_dirs()  # should not raise
        assert cache_dir.is_dir()


# ---------------------------------------------------------------------------
# LocalVideoCache: load
# ---------------------------------------------------------------------------


class TestLoad:
    def test_absent_file_leaves_data_empty(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        c.load()
        assert c._data == {}

    def test_malformed_json_no_exception_data_empty(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        (cache_dir / "library.json").write_text("{not valid json}", encoding="utf-8")
        c = LocalVideoCache(cache_dir)
        c.load()  # must not raise
        assert c._data == {}

    @pytest.mark.parametrize("payload", ["[]", "42", '"hello"', "null"])
    def test_non_dict_json_leaves_data_empty(self, tmp_path: Path, payload: str) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        (cache_dir / "library.json").write_text(payload, encoding="utf-8")
        c = LocalVideoCache(cache_dir)
        c.load()  # must not raise
        assert c._data == {}

    def test_load_round_trip(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        payload = {
            "Inception": {
                "title": "Inception",
                "year": 2010,
                "description": "Dream heist",
                "genres": ["Action", "Sci-Fi"],
                "rating": "8.8",
                "tmdb_id": 27205,
                "poster_scraped": "/path/to/poster.jpg",
                "custom": {"title": "Inception (Custom)"},
            }
        }
        (cache_dir / "library.json").write_text(json.dumps(payload), encoding="utf-8")
        c = LocalVideoCache(cache_dir)
        c.load()
        assert c._data == payload


# ---------------------------------------------------------------------------
# LocalVideoCache: save
# ---------------------------------------------------------------------------


class TestSave:
    def test_save_creates_dirs_and_writes_json(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        c = LocalVideoCache(cache_dir)
        c._data = {"key": {"title": "A Movie"}}
        c.save()
        assert (cache_dir / "library.json").exists()
        loaded = json.loads((cache_dir / "library.json").read_text(encoding="utf-8"))
        assert loaded == {"key": {"title": "A Movie"}}

    def test_save_is_indented(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        c = LocalVideoCache(cache_dir)
        c._data = {"k": {"v": 1}}
        c.save()
        raw = (cache_dir / "library.json").read_text(encoding="utf-8")
        assert "\n" in raw  # indented JSON has newlines


# ---------------------------------------------------------------------------
# LocalVideoCache: get_entry / set_entry
# ---------------------------------------------------------------------------


class TestGetEntry:
    def test_absent_key_returns_none(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        assert c.get_entry("missing") is None

    def test_returns_shallow_copy(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c._data = {"k": {"title": "T"}}
        result = c.get_entry("k")
        assert result == {"title": "T"}
        # Modifying the copy must not affect internal state
        result["title"] = "changed"
        assert c._data["k"]["title"] == "T"


class TestSetEntry:
    def test_merges_scraped_data(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c.set_entry("Inception", {"title": "Inception", "year": 2010})
        assert c._data["Inception"]["title"] == "Inception"
        assert c._data["Inception"]["year"] == 2010

    def test_custom_dict_preserved_on_merge(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c._data = {
            "Inception": {
                "title": "Inception",
                "year": 2010,
                "custom": {"title": "User Title"},
            }
        }
        # Scraper overwrites year but must not touch custom
        c.set_entry("Inception", {"title": "Inception", "year": 2010, "rating": "8.8"})
        assert c._data["Inception"]["custom"] == {"title": "User Title"}

    def test_new_entry_has_empty_custom(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c.set_entry("NewMovie", {"title": "New Movie"})
        assert c._data["NewMovie"]["custom"] == {}

    def test_set_entry_saves_to_disk(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c.set_entry("Film", {"title": "Film"})
        assert (cache_dir / "library.json").exists()
        loaded = json.loads((cache_dir / "library.json").read_text(encoding="utf-8"))
        assert "Film" in loaded


# ---------------------------------------------------------------------------
# LocalVideoCache: resolve_poster
# ---------------------------------------------------------------------------


class TestResolvePoster:
    def test_custom_artwork_wins_over_scraped(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        custom_dir = cache_dir / "artwork_custom"
        custom_dir.mkdir(parents=True)
        custom_file = custom_dir / "Inception.jpg"
        custom_file.write_bytes(b"")

        scraped_dir = cache_dir / "artwork_scraped"
        scraped_dir.mkdir()
        scraped_file = scraped_dir / "Inception.jpg"
        scraped_file.write_bytes(b"")

        c = LocalVideoCache(cache_dir)
        c._data = {"Inception": {"poster_scraped": str(scraped_file)}}
        result = c.resolve_poster("Inception")
        assert result == str(custom_file)

    def test_falls_back_to_poster_scraped_field(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        (cache_dir / "artwork_custom").mkdir(parents=True)

        scraped_dir = cache_dir / "artwork_scraped"
        scraped_dir.mkdir()
        scraped_file = scraped_dir / "Inception.jpg"
        scraped_file.write_bytes(b"")

        c = LocalVideoCache(cache_dir)
        c._data = {"Inception": {"poster_scraped": str(scraped_file)}}
        result = c.resolve_poster("Inception")
        assert result == str(scraped_file)

    def test_returns_empty_when_neither_present(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        (cache_dir / "artwork_custom").mkdir(parents=True)
        c = LocalVideoCache(cache_dir)
        assert c.resolve_poster("Inception") == ""

    def test_poster_scraped_nonexistent_on_disk_returns_empty(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        (cache_dir / "artwork_custom").mkdir(parents=True)
        c = LocalVideoCache(cache_dir)
        c._data = {"Inception": {"poster_scraped": "/does/not/exist.jpg"}}
        assert c.resolve_poster("Inception") == ""

    def test_custom_artwork_any_ext(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        custom_dir = cache_dir / "artwork_custom"
        custom_dir.mkdir(parents=True)
        custom_file = custom_dir / "Inception.png"
        custom_file.write_bytes(b"")
        c = LocalVideoCache(cache_dir)
        assert c.resolve_poster("Inception") == str(custom_file)


# ---------------------------------------------------------------------------
# LocalVideoCache: resolve_metadata
# ---------------------------------------------------------------------------


class TestResolveMetadata:
    def test_absent_key_returns_all_defaults(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        result = c.resolve_metadata("missing")
        assert result == {
            "title": "",
            "year": 0,
            "description": "",
            "genres": [],
            "rating": "",
            "tmdb_id": None,
        }

    def test_custom_overrides_base_fields(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        c._data = {
            "Inception": {
                "title": "Inception",
                "year": 2010,
                "description": "Original",
                "genres": ["Action"],
                "rating": "8.8",
                "tmdb_id": 27205,
                "custom": {"title": "Custom Title", "description": "User desc"},
            }
        }
        result = c.resolve_metadata("Inception")
        assert result["title"] == "Custom Title"
        assert result["description"] == "User desc"
        assert result["year"] == 2010  # not overridden
        assert result["tmdb_id"] == 27205

    def test_base_fields_returned_when_no_custom(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        c._data = {
            "Movie": {
                "title": "Movie",
                "year": 2000,
                "genres": ["Drama"],
                "rating": "7.0",
                "description": "Desc",
                "tmdb_id": 100,
            }
        }
        result = c.resolve_metadata("Movie")
        assert result["title"] == "Movie"
        assert result["genres"] == ["Drama"]


# ---------------------------------------------------------------------------
# LocalVideoCache: is_tombstoned / write_tombstone
# ---------------------------------------------------------------------------


class TestTombstone:
    def test_is_tombstoned_true_for_null_tmdb_id(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        c._data = {"Film": {"tmdb_id": None}}
        assert c.is_tombstoned("Film") is True

    def test_is_tombstoned_false_for_absent_key(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        assert c.is_tombstoned("missing") is False

    def test_is_tombstoned_false_for_set_tmdb_id(self, tmp_path: Path) -> None:
        c = LocalVideoCache(tmp_path / "movies")
        c._data = {"Film": {"tmdb_id": 12345}}
        assert c.is_tombstoned("Film") is False

    def test_write_tombstone_sets_tmdb_id_null(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c.write_tombstone("UnknownFilm")
        assert c._data["UnknownFilm"]["tmdb_id"] is None
        assert "tmdb_id" in c._data["UnknownFilm"]

    def test_write_tombstone_preserves_custom(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c._data = {"Film": {"custom": {"title": "Override"}}}
        c.write_tombstone("Film")
        assert c._data["Film"]["custom"] == {"title": "Override"}
        assert c._data["Film"]["tmdb_id"] is None

    def test_write_tombstone_saves_to_disk(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "movies"
        cache_dir.mkdir()
        c = LocalVideoCache(cache_dir)
        c.write_tombstone("Film")
        loaded = json.loads((cache_dir / "library.json").read_text(encoding="utf-8"))
        assert loaded["Film"]["tmdb_id"] is None


# ---------------------------------------------------------------------------
# Module-level cache factories
# ---------------------------------------------------------------------------


class TestCacheFactories:
    def test_movies_cache_uses_movies_cache_dir(self, tmp_path: Path, monkeypatch) -> None:
        movies_dir = tmp_path / "movies"
        monkeypatch.setattr(_mod, "_MOVIES_CACHE_DIR", movies_dir)
        cache = _movies_cache()
        assert cache._cache_dir == movies_dir
        assert cache._scraped_art_dir == movies_dir / "artwork_scraped"

    def test_tv_shows_cache_uses_tv_shows_cache_dir(self, tmp_path: Path, monkeypatch) -> None:
        tv_dir = tmp_path / "tv_shows"
        monkeypatch.setattr(_mod, "_TV_SHOWS_CACHE_DIR", tv_dir)
        cache = _tv_shows_cache()
        assert cache._cache_dir == tv_dir

    def test_custom_category_cache_uses_slugified_name(self, tmp_path: Path, monkeypatch) -> None:
        base_dir = tmp_path / "local_videos_cache"
        monkeypatch.setattr(_mod, "_LOCAL_VIDEOS_CACHE_DIR", base_dir)
        cache = _custom_category_cache("My Anime Collection!")
        assert cache._cache_dir == base_dir / "my_anime_collection"

    def test_custom_category_cache_has_no_scraped_art(self, tmp_path: Path, monkeypatch) -> None:
        base_dir = tmp_path / "local_videos_cache"
        monkeypatch.setattr(_mod, "_LOCAL_VIDEOS_CACHE_DIR", base_dir)
        cache = _custom_category_cache("Custom")
        assert cache._scraped_art_dir is None
