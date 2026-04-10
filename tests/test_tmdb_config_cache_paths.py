"""Tests for Task 001 — Config + cache paths for local video scraping.

Covers:
  - Config._tmdb_api_key defaults to "".
  - Config.set_tmdb_api_key persists via save() and strips whitespace.
  - Config round-trip: tmdb.api_key is written by save() and restored by _load().
  - Missing tmdb key in JSON keeps default "".
  - SettingsManager.tmdbApiKey property returns value from config.
  - SettingsManager.setTmdbApiKey delegates to config and emits tmdbApiKeyChanged.
  - local_video_library module-level cache path constants exist and are Path instances.
  - Cache path constants are nested correctly under the config dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, content: dict | None = None) -> Config:
    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path
    if content is not None:
        cfg_file.write_text(json.dumps(content), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        return Config()


def _reload(cfg_file: Path, cfg_dir: Path) -> Config:
    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        return Config()


def _make_manager(tmp_path: Path):
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    manager = SettingsManager(config, library, plex_library)
    return manager, config


# ---------------------------------------------------------------------------
# Config: tmdb_api_key
# ---------------------------------------------------------------------------


class TestTmdbApiKeyConfig:
    def test_default_is_empty_string(self, tmp_path: Path) -> None:
        """tmdb_api_key defaults to '' when no config file exists."""
        cfg = _make_config(tmp_path)
        assert cfg.tmdb_api_key == ""

    def test_missing_tmdb_section_keeps_default(self, tmp_path: Path) -> None:
        """Loading a config without a 'tmdb' key keeps the default empty string."""
        cfg = _make_config(tmp_path, {})
        assert cfg.tmdb_api_key == ""

    def test_set_tmdb_api_key_calls_save(self, tmp_path: Path) -> None:
        """set_tmdb_api_key stores the value and calls save()."""
        cfg = _make_config(tmp_path, {})
        cfg.save = MagicMock()
        cfg.set_tmdb_api_key("abc123")
        assert cfg.tmdb_api_key == "abc123"
        cfg.save.assert_called_once()

    def test_set_tmdb_api_key_strips_whitespace(self, tmp_path: Path) -> None:
        """set_tmdb_api_key strips leading/trailing whitespace."""
        cfg = _make_config(tmp_path, {})
        cfg.save = MagicMock()
        cfg.set_tmdb_api_key("  mykey  ")
        assert cfg.tmdb_api_key == "mykey"

    def test_round_trip(self, tmp_path: Path) -> None:
        """tmdb.api_key is written by save() and correctly restored by _load()."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_tmdb_api_key("test-api-key-xyz")

        # Now reload from the written file.
        cfg2 = _reload(cfg_file, cfg_dir)
        assert cfg2.tmdb_api_key == "test-api-key-xyz"

    def test_round_trip_empty_string(self, tmp_path: Path) -> None:
        """An empty tmdb.api_key round-trips as '' (not None or missing)."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_tmdb_api_key("")

        cfg2 = _reload(cfg_file, cfg_dir)
        assert cfg2.tmdb_api_key == ""

    def test_saved_json_contains_tmdb_section(self, tmp_path: Path) -> None:
        """save() writes a 'tmdb' key with 'api_key' in the JSON output."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_tmdb_api_key("mykey")

        raw = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "tmdb" in raw
        assert raw["tmdb"]["api_key"] == "mykey"

    def test_load_strips_whitespace_in_stored_value(self, tmp_path: Path) -> None:
        """_load() strips whitespace from a stored api_key value."""
        content = {"tmdb": {"api_key": "  padded  "}}
        cfg = _make_config(tmp_path, content)
        assert cfg.tmdb_api_key == "padded"


# ---------------------------------------------------------------------------
# SettingsManager: tmdbApiKey property and setTmdbApiKey slot
# ---------------------------------------------------------------------------


class TestSettingsManagerTmdbApiKey:
    def test_property_returns_config_value(self, tmp_path: Path) -> None:
        """tmdbApiKey property returns the value from the underlying config."""
        manager, config = _make_manager(tmp_path)
        config._tmdb_api_key = "prop-test-key"
        assert manager.tmdbApiKey == "prop-test-key"

    def test_set_slot_delegates_to_config(self, tmp_path: Path) -> None:
        """setTmdbApiKey calls config.set_tmdb_api_key with the given key."""
        manager, config = _make_manager(tmp_path)
        config.set_tmdb_api_key = MagicMock()
        manager.setTmdbApiKey("slot-key")
        config.set_tmdb_api_key.assert_called_once_with("slot-key")

    def test_set_slot_emits_signal(self, tmp_path: Path) -> None:
        """setTmdbApiKey emits tmdbApiKeyChanged after persisting."""
        manager, config = _make_manager(tmp_path)
        config.set_tmdb_api_key = MagicMock()

        emitted: list[None] = []
        manager.tmdbApiKeyChanged.connect(lambda: emitted.append(None))
        manager.setTmdbApiKey("emit-test")
        assert len(emitted) == 1


# ---------------------------------------------------------------------------
# local_video_library: module-level cache path constants
# ---------------------------------------------------------------------------


class TestLocalVideoCachePathConstants:
    def test_constants_exist(self) -> None:
        """_LOCAL_VIDEOS_CACHE_DIR, _MOVIES_CACHE_DIR, _TV_SHOWS_CACHE_DIR must exist."""
        from backend.local_video_library import (
            _LOCAL_VIDEOS_CACHE_DIR,
            _MOVIES_CACHE_DIR,
            _TV_SHOWS_CACHE_DIR,
        )
        assert _LOCAL_VIDEOS_CACHE_DIR is not None
        assert _MOVIES_CACHE_DIR is not None
        assert _TV_SHOWS_CACHE_DIR is not None

    def test_constants_are_path_instances(self) -> None:
        """All cache path constants must be pathlib.Path instances."""
        from backend.local_video_library import (
            _LOCAL_VIDEOS_CACHE_DIR,
            _MOVIES_CACHE_DIR,
            _TV_SHOWS_CACHE_DIR,
        )
        assert isinstance(_LOCAL_VIDEOS_CACHE_DIR, Path)
        assert isinstance(_MOVIES_CACHE_DIR, Path)
        assert isinstance(_TV_SHOWS_CACHE_DIR, Path)

    def test_movies_cache_dir_under_local_videos_cache(self) -> None:
        """_MOVIES_CACHE_DIR must be a subdirectory of _LOCAL_VIDEOS_CACHE_DIR."""
        from backend.local_video_library import (
            _LOCAL_VIDEOS_CACHE_DIR,
            _MOVIES_CACHE_DIR,
        )
        assert _MOVIES_CACHE_DIR.parent == _LOCAL_VIDEOS_CACHE_DIR

    def test_tv_shows_cache_dir_under_local_videos_cache(self) -> None:
        """_TV_SHOWS_CACHE_DIR must be a subdirectory of _LOCAL_VIDEOS_CACHE_DIR."""
        from backend.local_video_library import (
            _LOCAL_VIDEOS_CACHE_DIR,
            _TV_SHOWS_CACHE_DIR,
        )
        assert _TV_SHOWS_CACHE_DIR.parent == _LOCAL_VIDEOS_CACHE_DIR

    def test_local_videos_cache_under_config_dir(self) -> None:
        """_LOCAL_VIDEOS_CACHE_DIR must be a subdirectory of the htpcstation config dir."""
        from backend.local_video_library import _LOCAL_VIDEOS_CACHE_DIR
        assert _LOCAL_VIDEOS_CACHE_DIR.parent.name == "htpcstation"

    def test_movies_dir_name(self) -> None:
        """_MOVIES_CACHE_DIR must be named 'movies'."""
        from backend.local_video_library import _MOVIES_CACHE_DIR
        assert _MOVIES_CACHE_DIR.name == "movies"

    def test_tv_shows_dir_name(self) -> None:
        """_TV_SHOWS_CACHE_DIR must be named 'tv_shows'."""
        from backend.local_video_library import _TV_SHOWS_CACHE_DIR
        assert _TV_SHOWS_CACHE_DIR.name == "tv_shows"
