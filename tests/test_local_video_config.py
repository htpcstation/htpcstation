"""Tests for Task 001 — Config: local_videos categories.

Covers:
  - Config defaults for _local_video_categories and _show_local_videos_tab.
  - Round-trip: save() / _load() persists categories and tab visibility.
  - add/remove/update_local_video_category mutators persist correctly.
  - Missing local_videos key in JSON keeps defaults (Movies + TV Shows).
  - Malformed category entries are skipped without raising.
  - SettingsManager properties and slots delegate to Config and emit signals.
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


def _make_config(tmp_path: Path, content: str | None = None) -> Config:
    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path
    if content is not None:
        cfg_file.write_text(content, encoding="utf-8")
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
# Config defaults
# ---------------------------------------------------------------------------


class TestLocalVideoConfigDefaults:
    def test_default_categories_present(self, tmp_path: Path) -> None:
        """Config() ships with Movies and TV Shows categories by default."""
        cfg = _make_config(tmp_path)
        cats = cfg.local_video_categories
        names = [c["name"] for c in cats]
        assert "Movies" in names
        assert "TV Shows" in names

    def test_default_categories_count(self, tmp_path: Path) -> None:
        """Config() ships with exactly 2 default categories."""
        cfg = _make_config(tmp_path)
        assert len(cfg.local_video_categories) == 2

    def test_default_movies_type(self, tmp_path: Path) -> None:
        """Default Movies category has type='flat'."""
        cfg = _make_config(tmp_path)
        movies = next(c for c in cfg.local_video_categories if c["name"] == "Movies")
        assert movies["type"] == "flat"
        assert movies["paths"] == []

    def test_default_tv_shows_type(self, tmp_path: Path) -> None:
        """Default TV Shows category has type='tv_shows'."""
        cfg = _make_config(tmp_path)
        tv = next(c for c in cfg.local_video_categories if c["name"] == "TV Shows")
        assert tv["type"] == "tv_shows"
        assert tv["paths"] == []

    def test_default_show_local_videos_tab(self, tmp_path: Path) -> None:
        """show_local_videos_tab defaults to True."""
        cfg = _make_config(tmp_path)
        assert cfg.show_local_videos_tab is True


# ---------------------------------------------------------------------------
# Round-trip: save() / _load()
# ---------------------------------------------------------------------------


class TestLocalVideoConfigRoundTrip:
    def test_show_local_videos_tab_roundtrip(self, tmp_path: Path) -> None:
        """set_show_local_videos_tab(False) persists across save/load."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_show_local_videos_tab(False)

        reloaded = _reload(cfg_file, cfg_dir)
        assert reloaded.show_local_videos_tab is False

    def test_categories_roundtrip(self, tmp_path: Path) -> None:
        """Categories written by save() are reloaded correctly."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.add_local_video_category("Anime", ["/media/anime"], "flat")

        reloaded = _reload(cfg_file, cfg_dir)
        names = [c["name"] for c in reloaded.local_video_categories]
        assert "Anime" in names

    def test_saved_json_has_local_videos_key(self, tmp_path: Path) -> None:
        """save() writes a top-level 'local_videos' key with 'categories'."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.save()

        data = json.loads(cfg_file.read_text())
        assert "local_videos" in data
        assert "categories" in data["local_videos"]

    def test_saved_json_tabs_has_show_local_videos(self, tmp_path: Path) -> None:
        """save() writes 'show_local_videos' under the 'tabs' key."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.save()

        data = json.loads(cfg_file.read_text())
        assert "show_local_videos" in data["tabs"]

    def test_shallow_copy_on_read(self, tmp_path: Path) -> None:
        """local_video_categories returns a copy — mutating it does not affect internal state."""
        cfg = _make_config(tmp_path)
        copy = cfg.local_video_categories
        copy.append({"name": "Bogus", "paths": [], "type": "flat"})
        assert len(cfg.local_video_categories) == 2


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------


class TestLocalVideoConfigMutators:
    def test_add_category(self, tmp_path: Path) -> None:
        """add_local_video_category appends a new entry."""
        cfg = _make_config(tmp_path)
        cfg.add_local_video_category("Anime", ["/media/anime"], "flat")
        assert len(cfg.local_video_categories) == 3

    def test_add_category_fields(self, tmp_path: Path) -> None:
        """add_local_video_category stores name, paths, and type correctly."""
        cfg = _make_config(tmp_path)
        cfg.add_local_video_category("Docs", ["/media/docs"], "flat")
        added = cfg.local_video_categories[-1]
        assert added["name"] == "Docs"
        assert added["paths"] == ["/media/docs"]
        assert added["type"] == "flat"

    def test_remove_category(self, tmp_path: Path) -> None:
        """remove_local_video_category removes by index."""
        cfg = _make_config(tmp_path)
        cfg.remove_local_video_category(0)
        assert len(cfg.local_video_categories) == 1

    def test_update_category(self, tmp_path: Path) -> None:
        """update_local_video_category replaces entry at index."""
        cfg = _make_config(tmp_path)
        cfg.update_local_video_category(0, "Films", ["/media/films"], "flat")
        updated = cfg.local_video_categories[0]
        assert updated["name"] == "Films"
        assert updated["paths"] == ["/media/films"]
        assert updated["type"] == "flat"

    def test_add_then_remove_persists(self, tmp_path: Path) -> None:
        """Adding then removing a category round-trips to 2 entries."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.add_local_video_category("Temp", [], "flat")
            cfg.remove_local_video_category(2)

        reloaded = _reload(cfg_file, cfg_dir)
        assert len(reloaded.local_video_categories) == 2


# ---------------------------------------------------------------------------
# _load() edge cases
# ---------------------------------------------------------------------------


class TestLocalVideoConfigLoad:
    def test_missing_local_videos_key_keeps_defaults(self, tmp_path: Path) -> None:
        """If local_videos key is absent in JSON, defaults are kept intact."""
        cfg = _make_config(tmp_path, content=json.dumps({}))
        cats = cfg.local_video_categories
        assert len(cats) == 2
        assert cats[0]["name"] == "Movies"
        assert cats[1]["name"] == "TV Shows"

    def test_malformed_entry_missing_name_skipped(self, tmp_path: Path) -> None:
        """An entry without 'name' is skipped without raising."""
        data = {
            "local_videos": {
                "categories": [
                    {"paths": ["/foo"], "type": "flat"},
                    {"name": "Good", "paths": [], "type": "flat"},
                ]
            }
        }
        cfg = _make_config(tmp_path, content=json.dumps(data))
        cats = cfg.local_video_categories
        assert len(cats) == 1
        assert cats[0]["name"] == "Good"

    def test_malformed_entry_bad_type_skipped(self, tmp_path: Path) -> None:
        """An entry with an invalid type value is skipped."""
        data = {
            "local_videos": {
                "categories": [
                    {"name": "Bad", "paths": [], "type": "unknown"},
                    {"name": "Good", "paths": [], "type": "tv_shows"},
                ]
            }
        }
        cfg = _make_config(tmp_path, content=json.dumps(data))
        cats = cfg.local_video_categories
        assert len(cats) == 1
        assert cats[0]["name"] == "Good"

    def test_malformed_entry_non_string_in_paths_skipped(self, tmp_path: Path) -> None:
        """An entry with non-string items in paths list is skipped."""
        data = {
            "local_videos": {
                "categories": [
                    {"name": "Bad", "paths": [1, 2], "type": "flat"},
                    {"name": "Good", "paths": ["/foo"], "type": "flat"},
                ]
            }
        }
        cfg = _make_config(tmp_path, content=json.dumps(data))
        cats = cfg.local_video_categories
        assert len(cats) == 1
        assert cats[0]["name"] == "Good"

    def test_malformed_entry_not_a_dict_skipped(self, tmp_path: Path) -> None:
        """A non-dict entry in the categories list is skipped."""
        data = {
            "local_videos": {
                "categories": [
                    "not a dict",
                    {"name": "Good", "paths": [], "type": "flat"},
                ]
            }
        }
        cfg = _make_config(tmp_path, content=json.dumps(data))
        cats = cfg.local_video_categories
        assert len(cats) == 1
        assert cats[0]["name"] == "Good"

    def test_tabs_show_local_videos_loaded(self, tmp_path: Path) -> None:
        """tabs.show_local_videos is loaded from JSON."""
        data = {"tabs": {"show_local_videos": False}}
        cfg = _make_config(tmp_path, content=json.dumps(data))
        assert cfg.show_local_videos_tab is False


# ---------------------------------------------------------------------------
# SettingsManager
# ---------------------------------------------------------------------------


class TestSettingsManagerLocalVideos:
    def test_show_local_videos_tab_property(self, tmp_path: Path) -> None:
        """showLocalVideosTab property returns config value."""
        manager, config = _make_manager(tmp_path)
        config._show_local_videos_tab = False
        assert manager.showLocalVideosTab is False

    def test_local_video_categories_property(self, tmp_path: Path) -> None:
        """localVideoCategories property returns the categories list."""
        manager, config = _make_manager(tmp_path)
        categories = manager.localVideoCategories
        assert isinstance(categories, list)
        assert len(categories) == 2

    def test_set_show_local_videos_tab_emits_signal(self, tmp_path: Path) -> None:
        """setShowLocalVideosTab emits tabVisibilityChanged."""
        manager, config = _make_manager(tmp_path)
        emitted: list = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowLocalVideosTab(False)

        assert len(emitted) == 1
        config.save.assert_called()

    def test_add_local_video_category_emits_signal(self, tmp_path: Path) -> None:
        """addLocalVideoCategory emits localVideoCategoriesChanged."""
        manager, config = _make_manager(tmp_path)
        emitted: list = []
        manager.localVideoCategoriesChanged.connect(lambda: emitted.append(True))

        manager.addLocalVideoCategory("Docs", [], "flat")

        assert len(emitted) == 1
        config.save.assert_called()

    def test_remove_local_video_category_emits_signal(self, tmp_path: Path) -> None:
        """removeLocalVideoCategory emits localVideoCategoriesChanged."""
        manager, config = _make_manager(tmp_path)
        emitted: list = []
        manager.localVideoCategoriesChanged.connect(lambda: emitted.append(True))

        manager.removeLocalVideoCategory(0)

        assert len(emitted) == 1
        config.save.assert_called()

    def test_update_local_video_category_emits_signal(self, tmp_path: Path) -> None:
        """updateLocalVideoCategory emits localVideoCategoriesChanged."""
        manager, config = _make_manager(tmp_path)
        emitted: list = []
        manager.localVideoCategoriesChanged.connect(lambda: emitted.append(True))

        manager.updateLocalVideoCategory(0, "Films", ["/media/films"], "flat")

        assert len(emitted) == 1
        config.save.assert_called()

    def test_add_category_paths_coerced_to_str(self, tmp_path: Path) -> None:
        """addLocalVideoCategory converts paths items to str."""
        manager, config = _make_manager(tmp_path)
        # Bypass the mock.save to allow real category modification
        config.save = lambda: None

        manager.addLocalVideoCategory("Test", ["/foo"], "flat")
        cats = config.local_video_categories
        added = next(c for c in cats if c["name"] == "Test")
        assert all(isinstance(p, str) for p in added["paths"])


# ---------------------------------------------------------------------------
# Local video view mode — Config and SettingsManager
# ---------------------------------------------------------------------------


class TestLocalVideoViewModeConfig:
    def test_default_is_grid(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        assert cfg.local_video_view_mode == "grid"

    def test_set_list_persists(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_local_video_view_mode("list")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            reloaded = Config()
        assert reloaded.local_video_view_mode == "list"

    def test_invalid_value_coerces_to_grid(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        cfg.save = lambda: None
        cfg.set_local_video_view_mode("invalid")
        assert cfg.local_video_view_mode == "grid"

    def test_save_includes_local_video_view_mode(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_local_video_view_mode("list")

        data = json.loads(cfg_file.read_text())
        assert data["ui"]["local_video_view_mode"] == "list"


class TestLocalVideoViewModeSettingsManager:
    def test_property_returns_config_value(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager
        manager, config = _make_manager(tmp_path)
        config._local_video_view_mode = "list"
        assert manager.localVideoViewMode == "list"

    def test_set_local_video_view_mode_calls_config_and_emits(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager
        manager, config = _make_manager(tmp_path)

        emitted: list = []
        manager.localVideoViewModeChanged.connect(lambda: emitted.append(True))

        manager.setLocalVideoViewMode("list")

        assert len(emitted) == 1
        config.save.assert_called()
