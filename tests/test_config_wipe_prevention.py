"""Tests for Task 005 — Config wipe prevention.

Covers:
  - BrowserLauncher: accepts button_layout kwarg and stores it as _button_layout
  - BrowserLauncher: default button_layout is "standard"
  - BrowserLauncher: set_button_layout updates _button_layout
  - BrowserLauncher._deploy_extension: uses self._button_layout (not a fresh Config())
  - Config.save: guard fires when in-memory token/server_id are blank but disk has them
  - Config.save: guard does NOT fire when in-memory token is set
  - Config.save: guard does NOT fire when disk file has no credentials
  - Config.save: guard does NOT fire when disk file does not exist
  - SettingsManager.setButtonLayout: calls browser_launcher.set_button_layout
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path):
    """Return a Config instance with CONFIG_FILE and CONFIG_DIR redirected to tmp_path."""
    from backend.config import Config

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config(), config_file


# ---------------------------------------------------------------------------
# BrowserLauncher — button_layout parameter
# ---------------------------------------------------------------------------


class TestBrowserLauncherButtonLayout:
    def test_default_button_layout_is_standard(self) -> None:
        """BrowserLauncher() with no args stores 'standard' as _button_layout."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        assert launcher._button_layout == "standard"

    def test_button_layout_kwarg_stored(self) -> None:
        """button_layout kwarg is stored as _button_layout."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher(button_layout="alternate")
        assert launcher._button_layout == "alternate"

    def test_set_button_layout_updates_stored_value(self) -> None:
        """set_button_layout() updates _button_layout."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        assert launcher._button_layout == "standard"
        launcher.set_button_layout("alternate")
        assert launcher._button_layout == "alternate"

    def test_set_button_layout_back_to_standard(self) -> None:
        """set_button_layout() can switch back to 'standard'."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher(button_layout="alternate")
        launcher.set_button_layout("standard")
        assert launcher._button_layout == "standard"

    def test_existing_call_site_without_kwarg_still_works(self) -> None:
        """BrowserLauncher(browser_command) without button_layout still works."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher("custom-browser")
        assert launcher._button_layout == "standard"
        assert launcher._browser_command == "custom-browser"


# ---------------------------------------------------------------------------
# BrowserLauncher._deploy_extension — uses self._button_layout, not Config()
# ---------------------------------------------------------------------------


class TestBrowserLauncherDeployExtensionUsesStoredLayout:
    def test_deploy_extension_passes_stored_button_layout_to_generate_mapping_js(
        self, tmp_path: Path
    ) -> None:
        """_deploy_extension calls generate_mapping_js with self._button_layout."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher(button_layout="alternate")
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"
        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        with patch("backend.browser_launcher.generate_mapping_js") as mock_gen, \
             patch("backend.browser_launcher.load_mapping", return_value={}):
            mock_gen.return_value = "// js"
            launcher._deploy_extension()

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        assert kwargs.get("button_layout") == "alternate"

    def test_deploy_extension_does_not_import_config(self, tmp_path: Path) -> None:
        """_deploy_extension must not construct a Config() instance."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher(button_layout="standard")
        src = tmp_path / "extension"
        src.mkdir()
        dst = tmp_path / "deployed"
        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        # If Config() were constructed inside _deploy_extension, it would try to
        # read/write the real config file.  We patch it to detect any call.
        with patch("backend.browser_launcher.generate_mapping_js", return_value="// js"), \
             patch("backend.browser_launcher.load_mapping", return_value={}):
            # Patch Config at the module level — if it's imported inside the method
            # it would appear as backend.config.Config
            with patch("backend.config.Config") as mock_config_cls:
                launcher._deploy_extension()
                mock_config_cls.assert_not_called()

    def test_deploy_extension_uses_standard_layout_by_default(
        self, tmp_path: Path
    ) -> None:
        """When button_layout is not set, 'standard' is passed to generate_mapping_js."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()  # default layout
        src = tmp_path / "extension"
        src.mkdir()
        dst = tmp_path / "deployed"
        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        with patch("backend.browser_launcher.generate_mapping_js") as mock_gen, \
             patch("backend.browser_launcher.load_mapping", return_value={}):
            mock_gen.return_value = "// js"
            launcher._deploy_extension()

        _, kwargs = mock_gen.call_args
        assert kwargs.get("button_layout") == "standard"


# ---------------------------------------------------------------------------
# Config.save — credential wipe guard
# ---------------------------------------------------------------------------


class TestConfigSaveGuard:
    def test_guard_fires_when_blank_token_but_disk_has_token(
        self, tmp_path: Path
    ) -> None:
        """save() refuses to write when in-memory token is blank but disk has one."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        # Disk has a token
        config_file.write_text(
            json.dumps({"plex": {"token": "real_token", "server_id": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            # Blank out the in-memory token (simulating the bug)
            config._plex_token = None
            config._plex_server_id = None
            original_mtime = config_file.stat().st_mtime
            config.save()

        # File must NOT have been overwritten
        assert config_file.stat().st_mtime == original_mtime

    def test_guard_fires_when_blank_server_id_but_disk_has_server_id(
        self, tmp_path: Path
    ) -> None:
        """save() refuses to write when in-memory server_id is blank but disk has one."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "", "server_id": "real_server_id"}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._plex_token = None
            config._plex_server_id = None
            original_mtime = config_file.stat().st_mtime
            config.save()

        assert config_file.stat().st_mtime == original_mtime

    def test_guard_does_not_fire_when_in_memory_token_is_set(
        self, tmp_path: Path
    ) -> None:
        """save() proceeds normally when in-memory token is set."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "real_token", "server_id": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            # Token is loaded from disk — save should proceed
            assert config._plex_token == "real_token"
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["token"] == "real_token"

    def test_guard_does_not_fire_when_disk_has_no_credentials(
        self, tmp_path: Path
    ) -> None:
        """save() proceeds normally when the disk file has no credentials."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._plex_token = None
            config._plex_server_id = None
            config.save()

        # File should have been written (no guard triggered)
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "plex" in saved

    def test_guard_does_not_fire_when_disk_file_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        """save() proceeds normally when the config file does not exist yet."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        # Do NOT create the file — simulate first-run

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            # Config.__init__ will call save() since file doesn't exist
            config = Config()

        assert config_file.exists()
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "plex" in saved

    def test_guard_logs_error_when_refusing_to_save(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """save() logs an error message when the guard fires."""
        import logging
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "real_token", "server_id": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._plex_token = None
            config._plex_server_id = None
            with caplog.at_level(logging.ERROR, logger="backend.config"):
                config.save()

        assert any("refusing to overwrite" in record.message for record in caplog.records)

    def test_guard_proceeds_when_existing_file_is_malformed(
        self, tmp_path: Path
    ) -> None:
        """save() proceeds when the existing file cannot be parsed (fail-safe)."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json", encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._plex_token = None
            config._plex_server_id = None
            config.save()

        # Should have written the file (guard couldn't read existing, so it proceeds)
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "plex" in saved


# ---------------------------------------------------------------------------
# SettingsManager.setButtonLayout — propagates to browser_launcher
# ---------------------------------------------------------------------------


class TestSettingsManagerSetButtonLayout:
    def _make_manager(self, tmp_path: Path, browser_launcher=None):
        from backend.settings_manager import SettingsManager
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        library = MagicMock()
        plex_library = MagicMock()
        manager = SettingsManager(
            config, library, plex_library, browser_launcher=browser_launcher
        )
        return manager, config

    def test_set_button_layout_calls_browser_launcher_set_button_layout(
        self, tmp_path: Path
    ) -> None:
        """setButtonLayout propagates the new layout to browser_launcher."""
        mock_launcher = MagicMock()
        manager, _ = self._make_manager(tmp_path, browser_launcher=mock_launcher)

        manager.setButtonLayout("alternate")

        mock_launcher.set_button_layout.assert_called_once_with("alternate")

    def test_set_button_layout_no_crash_when_browser_launcher_is_none(
        self, tmp_path: Path
    ) -> None:
        """setButtonLayout does not crash when browser_launcher is None."""
        manager, _ = self._make_manager(tmp_path, browser_launcher=None)
        # Should not raise
        manager.setButtonLayout("alternate")

    def test_set_button_layout_updates_config(self, tmp_path: Path) -> None:
        """setButtonLayout also updates the config (existing behaviour preserved)."""
        mock_launcher = MagicMock()
        manager, config = self._make_manager(tmp_path, browser_launcher=mock_launcher)

        manager.setButtonLayout("alternate")

        assert config.button_layout == "alternate"
