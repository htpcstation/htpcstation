"""Tests for Task 001 — Theme Config Backend.

Covers:
  - Config.theme_name defaults to "default" with no config file.
  - Config.theme_name loads correctly from a config file.
  - Config.theme_name falls back to "default" for blank or missing values.
  - Config.set_theme_name validates and persists.
  - Config.save() includes theme_name in the "ui" dict.
  - SettingsManager.themeName returns the raw theme name.
  - SettingsManager.themeDir returns a file:// URL ending with "/" and containing the correct path.
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
    """Create a Config instance backed by tmp_path."""
    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path

    if content is not None:
        cfg_file.write_text(content, encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        return Config()


def _save_and_reload(cfg: Config, tmp_path: Path) -> Config:
    """Save cfg then load a fresh Config from the same file."""
    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        cfg.save()
        return Config()


def _make_manager(tmp_path: Path, app_dir: Path | None = None):
    """Create a SettingsManager with a real Config and mock dependencies."""
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    manager = SettingsManager(config, library, plex_library, app_dir=app_dir)
    return manager, config


# ---------------------------------------------------------------------------
# Config.theme_name — defaults
# ---------------------------------------------------------------------------


class TestConfigThemeNameDefaults:
    def test_default_theme_name_no_file(self, tmp_path: Path) -> None:
        """Config() with no existing config file has theme_name == 'default'."""
        cfg = _make_config(tmp_path)
        assert cfg.theme_name == "default"

    def test_default_theme_name_empty_file(self, tmp_path: Path) -> None:
        """Config() with an empty config file has theme_name == 'default'."""
        cfg = _make_config(tmp_path, content="{}")
        assert cfg.theme_name == "default"

    def test_default_theme_name_missing_ui_section(self, tmp_path: Path) -> None:
        """Config() with no 'ui' section has theme_name == 'default'."""
        cfg = _make_config(tmp_path, content=json.dumps({"plex": {}}))
        assert cfg.theme_name == "default"

    def test_default_theme_name_missing_key(self, tmp_path: Path) -> None:
        """Config() with 'ui' section but no 'theme_name' key has theme_name == 'default'."""
        content = json.dumps({"ui": {"button_layout": "standard"}})
        cfg = _make_config(tmp_path, content=content)
        assert cfg.theme_name == "default"


# ---------------------------------------------------------------------------
# Config.theme_name — loading from file
# ---------------------------------------------------------------------------


class TestConfigThemeNameLoad:
    def test_loads_theme_name_from_file(self, tmp_path: Path) -> None:
        """Config() loading a config with 'ui': {'theme_name': 'mytheme'} has theme_name == 'mytheme'."""
        content = json.dumps({"ui": {"theme_name": "mytheme"}})
        cfg = _make_config(tmp_path, content=content)
        assert cfg.theme_name == "mytheme"

    def test_blank_theme_name_falls_back_to_default(self, tmp_path: Path) -> None:
        """Config() loading a config with blank theme_name falls back to 'default'."""
        content = json.dumps({"ui": {"theme_name": ""}})
        cfg = _make_config(tmp_path, content=content)
        assert cfg.theme_name == "default"

    def test_whitespace_only_theme_name_falls_back_to_default(self, tmp_path: Path) -> None:
        """Config() loading a config with whitespace-only theme_name falls back to 'default'."""
        content = json.dumps({"ui": {"theme_name": "   "}})
        cfg = _make_config(tmp_path, content=content)
        assert cfg.theme_name == "default"

    def test_theme_name_is_stripped(self, tmp_path: Path) -> None:
        """Config() strips whitespace from theme_name when loading."""
        content = json.dumps({"ui": {"theme_name": "  mytheme  "}})
        cfg = _make_config(tmp_path, content=content)
        assert cfg.theme_name == "mytheme"


# ---------------------------------------------------------------------------
# Config.set_theme_name — validation and persistence
# ---------------------------------------------------------------------------


class TestConfigSetThemeName:
    def test_set_theme_name_valid(self, tmp_path: Path) -> None:
        """set_theme_name() with a valid name updates theme_name."""
        cfg = _make_config(tmp_path)
        cfg.set_theme_name("dark")
        assert cfg.theme_name == "dark"

    def test_set_theme_name_empty_string_ignored(self, tmp_path: Path) -> None:
        """set_theme_name() with an empty string leaves theme_name unchanged."""
        cfg = _make_config(tmp_path)
        cfg.set_theme_name("dark")
        cfg.set_theme_name("")
        assert cfg.theme_name == "dark"

    def test_set_theme_name_whitespace_only_ignored(self, tmp_path: Path) -> None:
        """set_theme_name() with whitespace-only string leaves theme_name unchanged."""
        cfg = _make_config(tmp_path)
        cfg.set_theme_name("dark")
        cfg.set_theme_name("   ")
        assert cfg.theme_name == "dark"

    def test_set_theme_name_persists(self, tmp_path: Path) -> None:
        """set_theme_name() persists the value so it survives a reload."""
        cfg = _make_config(tmp_path)
        cfg.set_theme_name("retro")
        cfg2 = _save_and_reload(cfg, tmp_path)
        assert cfg2.theme_name == "retro"


# ---------------------------------------------------------------------------
# Config.save() — theme_name in "ui" dict
# ---------------------------------------------------------------------------


class TestConfigSaveThemeName:
    def test_save_includes_theme_name_in_ui(self, tmp_path: Path) -> None:
        """save() writes theme_name into the 'ui' section of the JSON file."""
        cfg = _make_config(tmp_path)
        cfg.set_theme_name("neon")
        cfg_file = tmp_path / "config.json"

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            cfg.save()

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data["ui"]["theme_name"] == "neon"

    def test_save_default_theme_name(self, tmp_path: Path) -> None:
        """save() writes 'default' as theme_name when no theme has been set."""
        cfg = _make_config(tmp_path)
        cfg_file = tmp_path / "config.json"

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            cfg.save()

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data["ui"]["theme_name"] == "default"


# ---------------------------------------------------------------------------
# SettingsManager.themeName and themeDir
# ---------------------------------------------------------------------------


class TestSettingsManagerThemeProperties:
    def test_theme_name_returns_config_value(self, tmp_path: Path) -> None:
        """SettingsManager.themeName returns the raw theme name from Config."""
        manager, config = _make_manager(tmp_path)
        # Default is "default"
        assert manager.themeName == "default"

    def test_theme_name_reflects_config_change(self, tmp_path: Path) -> None:
        """SettingsManager.themeName reflects changes made to Config.theme_name."""
        manager, config = _make_manager(tmp_path)
        config._theme_name = "dark"
        assert manager.themeName == "dark"

    def test_theme_dir_ends_with_slash(self, tmp_path: Path) -> None:
        """SettingsManager.themeDir ends with '/' for QML path concatenation."""
        app_dir = tmp_path / "app"
        manager, _ = _make_manager(tmp_path, app_dir=app_dir)
        assert manager.themeDir.endswith("/")

    def test_theme_dir_starts_with_file_scheme(self, tmp_path: Path) -> None:
        """SettingsManager.themeDir starts with 'file://'."""
        app_dir = tmp_path / "app"
        manager, _ = _make_manager(tmp_path, app_dir=app_dir)
        assert manager.themeDir.startswith("file://")

    def test_theme_dir_contains_correct_path(self, tmp_path: Path) -> None:
        """SettingsManager.themeDir contains the correct absolute path."""
        app_dir = tmp_path / "app"
        manager, config = _make_manager(tmp_path, app_dir=app_dir)
        config._theme_name = "default"
        expected = "file://" + str(app_dir / "themes" / "default") + "/"
        assert manager.themeDir == expected

    def test_theme_dir_uses_current_theme_name(self, tmp_path: Path) -> None:
        """SettingsManager.themeDir uses the current theme_name from Config."""
        app_dir = tmp_path / "app"
        manager, config = _make_manager(tmp_path, app_dir=app_dir)
        config._theme_name = "neon"
        expected = "file://" + str(app_dir / "themes" / "neon") + "/"
        assert manager.themeDir == expected

    def test_theme_dir_default_app_dir_fallback(self, tmp_path: Path) -> None:
        """SettingsManager without app_dir uses a sensible fallback (parent of settings_manager.py)."""
        manager, _ = _make_manager(tmp_path, app_dir=None)
        # Should not raise and should produce a valid file:// URL ending with /
        assert manager.themeDir.startswith("file://")
        assert manager.themeDir.endswith("/")
