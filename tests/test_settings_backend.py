"""Tests for Task 025 — Settings Backend.

Covers:
  - Config: video_snap_autoplay and video_snap_delay_ms defaults
  - Config: ui section loaded from JSON
  - Config: ui section saved to JSON
  - Config: setters update fields and call save()
  - SettingsManager: Q_PROPERTY getters return correct values
  - SettingsManager: setters update config and emit signals
  - SettingsManager: getSystemsList returns discovered systems only
  - SettingsManager: testPlexConnection returns False when not configured
  - SettingsManager: testPlexConnection returns True on successful connection
  - SettingsManager: rescanLibrary calls library.rescan()
  - GameLibrary: rescan() re-scans the ROM directory
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.config import Config


# ---------------------------------------------------------------------------
# Config — video snap defaults
# ---------------------------------------------------------------------------


class TestConfigVideoSnapDefaults:
    def test_video_snap_autoplay_default_is_true(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.video_snap_autoplay is True

    def test_video_snap_delay_ms_default_is_1500(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.video_snap_delay_ms == 1500


# ---------------------------------------------------------------------------
# Config — ui section load/save
# ---------------------------------------------------------------------------


class TestConfigUiSection:
    def test_ui_section_loaded_from_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"ui": {"video_snap_autoplay": False, "video_snap_delay_ms": 3000}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.video_snap_autoplay is False
        assert config.video_snap_delay_ms == 3000

    def test_ui_section_saved_to_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.video_snap_autoplay = False
            config.video_snap_delay_ms = 2000
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "ui" in saved
        assert saved["ui"]["video_snap_autoplay"] is False
        assert saved["ui"]["video_snap_delay_ms"] == 2000

    def test_ui_section_missing_uses_defaults(self, tmp_path: Path) -> None:
        """Config without a ui section uses default values."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"retroarch": {}}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.video_snap_autoplay is True
        assert config.video_snap_delay_ms == 1500


# ---------------------------------------------------------------------------
# Config — setters
# ---------------------------------------------------------------------------


class TestConfigSetters:
    def _make_config(self, tmp_path: Path) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_set_plex_server_url_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_server_url("http://192.168.0.2:32400")

        assert config.plex_server_url == "http://192.168.0.2:32400"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["server_url"] == "http://192.168.0.2:32400"

    def test_set_plex_server_url_empty_string_sets_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"server_url": "http://server:32400", "token": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_server_url("")

        assert config.plex_server_url is None

    def test_set_plex_token_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_token("mytoken123")

        assert config.plex_token == "mytoken123"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["token"] == "mytoken123"

    def test_set_browser_command_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_browser_command("firefox")

        assert config.browser_command == "firefox"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["browser"]["command"] == "firefox"

    def test_set_retroarch_command_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_retroarch_command("retroarch")

        assert config.retroarch_command == "retroarch"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["command"] == "retroarch"

    def test_set_cores_directory_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_cores_directory(str(tmp_path))

        assert config.cores_directory == tmp_path
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["cores_directory"] == str(tmp_path)

    def test_set_system_core_updates_existing_system(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_system_core("snes", "snes9x_next_libretro.so")

        assert config.get_system("snes").core == "snes9x_next_libretro.so"

    def test_set_system_core_creates_new_system(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_system_core("custom_system", "custom_core.so")

        assert config.get_system("custom_system").core == "custom_core.so"

    def test_set_video_snap_autoplay_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_video_snap_autoplay(False)

        assert config.video_snap_autoplay is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["ui"]["video_snap_autoplay"] is False

    def test_set_video_snap_delay_ms_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_video_snap_delay_ms(3000)

        assert config.video_snap_delay_ms == 3000
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["ui"]["video_snap_delay_ms"] == 3000


# ---------------------------------------------------------------------------
# SettingsManager — property getters
# ---------------------------------------------------------------------------


class TestSettingsManagerProperties:
    def _make_manager(self, tmp_path: Path):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({
                "rom_directory": str(tmp_path),
                "retroarch": {"command": "retroarch", "cores_directory": str(tmp_path)},
                "plex": {"server_url": "http://server:32400", "token": "tok"},
                "browser": {"command": "firefox"},
                "ui": {"video_snap_autoplay": False, "video_snap_delay_ms": 2500},
            }),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        library = MagicMock()
        plex_library = MagicMock()
        return SettingsManager(config, library, plex_library)

    def test_rom_directory_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.romDirectory == str(tmp_path)

    def test_retroarch_command_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.retroarchCommand == "retroarch"

    def test_plex_server_url_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.plexServerUrl == "http://server:32400"

    def test_plex_token_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.plexToken == "tok"

    def test_browser_command_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.browserCommand == "firefox"

    def test_video_snap_autoplay_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.videoSnapAutoplay is False

    def test_video_snap_delay_ms_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.videoSnapDelayMs == 2500


# ---------------------------------------------------------------------------
# SettingsManager — setters emit signals
# ---------------------------------------------------------------------------


class TestSettingsManagerSetters:
    def _make_manager(self, tmp_path: Path):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        library = MagicMock()
        plex_library = MagicMock()
        return SettingsManager(config, library, plex_library), config

    def test_set_plex_server_url_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.plexServerUrlChanged.connect(lambda: emitted.append(True))

        manager.setPlexServerUrl("http://***REMOVED***:32400")

        assert config.plex_server_url == "http://***REMOVED***:32400"
        assert len(emitted) == 1

    def test_set_plex_token_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.plexTokenChanged.connect(lambda: emitted.append(True))

        manager.setPlexToken("newtoken")

        assert config.plex_token == "newtoken"
        assert len(emitted) == 1

    def test_set_browser_command_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.browserCommandChanged.connect(lambda: emitted.append(True))

        manager.setBrowserCommand("chromium")

        assert config.browser_command == "chromium"
        assert len(emitted) == 1

    def test_set_retroarch_command_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.retroarchCommandChanged.connect(lambda: emitted.append(True))

        manager.setRetroarchCommand("retroarch --verbose")

        assert config.retroarch_command == "retroarch --verbose"
        assert len(emitted) == 1

    def test_set_video_snap_autoplay_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.videoSnapAutoplayChanged.connect(lambda: emitted.append(True))

        manager.setVideoSnapAutoplay(False)

        assert config.video_snap_autoplay is False
        assert len(emitted) == 1

    def test_set_video_snap_delay_ms_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.videoSnapDelayMsChanged.connect(lambda: emitted.append(True))

        manager.setVideoSnapDelayMs(3000)

        assert config.video_snap_delay_ms == 3000
        assert len(emitted) == 1

    def test_set_rom_directory_rejects_nonexistent_path(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.romDirectoryChanged.connect(lambda: emitted.append(True))

        manager.setRomDirectory("/nonexistent/path/that/does/not/exist")

        # Should not update or emit
        assert config.rom_directory is None
        assert len(emitted) == 0

    def test_set_rom_directory_accepts_existing_path(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.romDirectoryChanged.connect(lambda: emitted.append(True))

        manager.setRomDirectory(str(tmp_path))

        assert config.rom_directory == tmp_path
        assert len(emitted) == 1

    def test_set_system_core_updates_config(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)

        manager.setSystemCore("snes", "snes9x_next_libretro.so")

        assert config.get_system("snes").core == "snes9x_next_libretro.so"


# ---------------------------------------------------------------------------
# SettingsManager — getSystemsList
# ---------------------------------------------------------------------------


class TestSettingsManagerGetSystemsList:
    def test_returns_only_discovered_systems(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        # Create two system directories
        (tmp_path / "snes").mkdir()
        (tmp_path / "nes").mkdir()
        # A file (not a directory) — should be ignored
        (tmp_path / "readme.txt").write_text("ignore me")

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"rom_directory": str(tmp_path)}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        manager = SettingsManager(config, MagicMock(), MagicMock())
        result = manager.getSystemsList()

        folder_names = [s["folderName"] for s in result]
        assert "snes" in folder_names
        assert "nes" in folder_names
        assert "readme.txt" not in folder_names

    def test_returns_empty_when_no_rom_directory(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        manager = SettingsManager(config, MagicMock(), MagicMock())
        result = manager.getSystemsList()

        assert result == []

    def test_result_contains_expected_keys(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        (tmp_path / "snes").mkdir()

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"rom_directory": str(tmp_path)}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        manager = SettingsManager(config, MagicMock(), MagicMock())
        result = manager.getSystemsList()

        assert len(result) == 1
        system = result[0]
        assert "folderName" in system
        assert "displayName" in system
        assert "core" in system
        assert system["folderName"] == "snes"
        assert system["displayName"] == "Super Nintendo"


# ---------------------------------------------------------------------------
# SettingsManager — testPlexConnection
# ---------------------------------------------------------------------------


class TestSettingsManagerTestPlexConnection:
    def test_returns_false_when_not_configured(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        manager = SettingsManager(config, MagicMock(), MagicMock())
        result = manager.testPlexConnection()

        assert result is False

    def test_returns_true_on_successful_connection(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"server_url": "http://server:32400", "token": "tok"}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {"machineIdentifier": "abc123"}

        manager = SettingsManager(config, MagicMock(), MagicMock())
        with patch("backend.settings_manager.PlexClient", return_value=mock_client):
            result = manager.testPlexConnection()

        assert result is True

    def test_returns_false_on_connection_failure(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"server_url": "http://server:32400", "token": "tok"}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {}  # no machineIdentifier

        manager = SettingsManager(config, MagicMock(), MagicMock())
        with patch("backend.settings_manager.PlexClient", return_value=mock_client):
            result = manager.testPlexConnection()

        assert result is False


# ---------------------------------------------------------------------------
# SettingsManager — rescanLibrary
# ---------------------------------------------------------------------------


class TestSettingsManagerRescanLibrary:
    def test_rescan_library_calls_library_rescan(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        library = MagicMock()
        manager = SettingsManager(config, library, MagicMock())
        manager.rescanLibrary()

        library.rescan.assert_called_once()


# ---------------------------------------------------------------------------
# GameLibrary — rescan slot
# ---------------------------------------------------------------------------


class TestGameLibraryRescan:
    def _write_gamelist(self, system_path: Path, xml_body: str) -> None:
        content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
        (system_path / "gamelist.xml").write_text(content, encoding="utf-8")

    def test_rescan_rebuilds_systems_model(self, tmp_path: Path) -> None:
        from backend.library import GameLibrary

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="Test System", core="core.so", extensions=[".rom"]
        )

        library = GameLibrary(config)
        # Initially no systems (no gamelist.xml files)
        initial_count = library.systemsModel.rowCount()

        # Add a system directory with a gamelist
        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        self._write_gamelist(
            system_dir,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )

        # Rescan should pick up the new system
        library.rescan()

        # After rescan, systems model should have more entries (collections + real)
        new_count = library.systemsModel.rowCount()
        assert new_count > initial_count
