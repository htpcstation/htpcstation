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
# Helpers shared across SettingsManager tests
# ---------------------------------------------------------------------------


def _make_settings_manager(tmp_path: Path, plex_token: str = ""):
    """Create a SettingsManager with a real Config and mock dependencies."""
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    data = {}
    if plex_token:
        data["plex"] = {"token": plex_token}
    config_file.write_text(json.dumps(data), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    browser_launcher = MagicMock()
    manager = SettingsManager(config, library, plex_library, browser_launcher)
    return manager, config, browser_launcher


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

    def test_set_plex_server_id_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_server_id("machine-abc123")

        assert config.plex_server_id == "machine-abc123"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["server_id"] == "machine-abc123"

    def test_set_plex_server_id_empty_string_sets_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"server_id": "machine-abc", "token": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_server_id("")

        assert config.plex_server_id is None

    def test_set_plex_user_id_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_user_id(42)

        assert config.plex_user_id == 42
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["user_id"] == 42

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
                "plex": {"token": "tok", "server_id": "machine-abc", "user_id": 5},
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

    def test_plex_server_url_property_returns_empty(self, tmp_path: Path) -> None:
        """plexServerUrl is now always empty (server URL is runtime-resolved)."""
        manager = self._make_manager(tmp_path)
        assert manager.plexServerUrl == ""

    def test_plex_server_id_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.plexServerId == "machine-abc"

    def test_plex_user_id_property(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.plexUserId == 5

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

        # Prevent save() from writing to the real config file after the patch
        # exits.  Setter tests only verify in-memory state and signal emissions;
        # file persistence is already covered by TestConfigSetters.
        config.save = MagicMock()

        library = MagicMock()
        plex_library = MagicMock()
        return SettingsManager(config, library, plex_library), config

    def test_set_plex_server_url_is_noop(self, tmp_path: Path) -> None:
        """setPlexServerUrl is now a no-op (server URL is runtime-resolved)."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.plexServerUrlChanged.connect(lambda: emitted.append(True))

        manager.setPlexServerUrl("http://***REMOVED***:32400")

        # No signal emitted, no config change
        assert len(emitted) == 0

    def test_set_plex_server_id_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.plexServerIdChanged.connect(lambda: emitted.append(True))

        manager.setPlexServerId("machine-xyz")

        assert config.plex_server_id == "machine-xyz"
        assert len(emitted) == 1

    def test_set_plex_user_id_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.plexUserIdChanged.connect(lambda: emitted.append(True))

        manager.setPlexUserId(7)

        assert config.plex_user_id == 7
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
            json.dumps({"plex": {"token": "tok"}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        mock_account = MagicMock()
        mock_account.test_connection.return_value = True

        manager = SettingsManager(config, MagicMock(), MagicMock())
        with patch("backend.settings_manager.PlexAccount", return_value=mock_account):
            result = manager.testPlexConnection()

        assert result is True

    def test_returns_false_on_connection_failure(self, tmp_path: Path) -> None:
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "tok"}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        mock_account = MagicMock()
        mock_account.test_connection.return_value = False

        manager = SettingsManager(config, MagicMock(), MagicMock())
        with patch("backend.settings_manager.PlexAccount", return_value=mock_account):
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


# ---------------------------------------------------------------------------
# SettingsManager — signInWithPlex
# ---------------------------------------------------------------------------


class TestSettingsManagerSignInWithPlex:
    def test_sign_in_calls_create_pin(self, tmp_path: Path) -> None:
        """signInWithPlex calls PlexAccount.create_pin."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=None) as mock_create_pin:
            manager.signInWithPlex()

        mock_create_pin.assert_called_once()

    def test_sign_in_opens_browser_with_oauth_url(self, tmp_path: Path) -> None:
        """signInWithPlex opens the OAuth URL in the browser."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(42, "mycode")):
            with patch("backend.settings_manager.QTimer"):
                manager.signInWithPlex()

        browser_launcher.launch.assert_called_once()
        url_arg = browser_launcher.launch.call_args[0][0]
        assert "mycode" in url_arg
        assert "app.plex.tv/auth" in url_arg
        assert "htpcstation" in url_arg

    def test_sign_in_does_nothing_when_create_pin_fails(self, tmp_path: Path) -> None:
        """signInWithPlex returns early if create_pin returns None."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        with patch("backend.settings_manager.PlexAccount.create_pin", return_value=None):
            manager.signInWithPlex()

        browser_launcher.launch.assert_not_called()

    def test_sign_in_starts_polling_timer(self, tmp_path: Path) -> None:
        """signInWithPlex creates a QTimer for polling."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(99, "code99")):
            manager.signInWithPlex()

        # Timer should be created after signInWithPlex
        assert manager._oauth_timer is not None
        manager._oauth_timer.stop()  # clean up

    def test_poll_stores_token_and_emits_signal_on_success(self, tmp_path: Path) -> None:
        """_poll_oauth_pin stores the token and emits plexTokenChanged when token arrives."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        emitted = []
        manager.plexTokenChanged.connect(lambda: emitted.append(True))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "code1")):
            manager.signInWithPlex()

        # Simulate a successful poll
        with patch("backend.settings_manager.PlexAccount.check_pin",
                   return_value="received_token"):
            manager._poll_oauth_pin()

        assert config.plex_token == "received_token"
        assert len(emitted) == 1
        # Timer should be stopped after success
        assert manager._oauth_timer is None

    def test_poll_stops_after_max_polls(self, tmp_path: Path) -> None:
        """_poll_oauth_pin gives up after _OAUTH_MAX_POLLS polls."""
        from backend.settings_manager import _OAUTH_MAX_POLLS

        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "code1")):
            manager.signInWithPlex()

        # Simulate polls returning None (not yet authenticated)
        with patch("backend.settings_manager.PlexAccount.check_pin", return_value=None):
            # Exhaust all polls
            for _ in range(_OAUTH_MAX_POLLS + 1):
                manager._poll_oauth_pin()

        # Timer should be stopped after timeout
        assert manager._oauth_timer is None

    def test_poll_does_not_store_token_when_none(self, tmp_path: Path) -> None:
        """_poll_oauth_pin does not store a token when check_pin returns None."""
        manager, config, browser_launcher = _make_settings_manager(tmp_path)

        emitted = []
        manager.plexTokenChanged.connect(lambda: emitted.append(True))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "code1")):
            manager.signInWithPlex()

        with patch("backend.settings_manager.PlexAccount.check_pin", return_value=None):
            manager._poll_oauth_pin()

        assert config.plex_token is None
        assert len(emitted) == 0
        # Timer should still be running
        assert manager._oauth_timer is not None
        manager._oauth_timer.stop()  # clean up

    def test_sign_in_without_browser_launcher_does_not_crash(self, tmp_path: Path) -> None:
        """signInWithPlex works even if browser_launcher is None."""
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
        config.save = MagicMock()

        manager = SettingsManager(config, MagicMock(), MagicMock(), browser_launcher=None)

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "code1")):
            manager.signInWithPlex()  # should not raise

        assert manager._oauth_timer is not None
        manager._oauth_timer.stop()  # clean up
