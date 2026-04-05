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
from tests.local_overrides import get_override

LOCAL_IP = get_override("moonlight_local_ip", "192.168.50.5")
PLEX_SERVER_URL = get_override("plex_server_url", f"http://{LOCAL_IP}:32400")

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

        manager.setPlexServerUrl(PLEX_SERVER_URL)

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


# ---------------------------------------------------------------------------
# Config — moonlight section
# ---------------------------------------------------------------------------


class TestConfigMoonlightSection:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_moonlight_command_default(self, tmp_path: Path) -> None:
        """Config.moonlight_command returns the built-in default."""
        config = self._make_config(tmp_path)
        assert config.moonlight_command == "flatpak run com.moonlight_stream.Moonlight"

    def test_set_moonlight_command_persists(self, tmp_path: Path) -> None:
        """set_moonlight_command updates the property and saves to disk."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_moonlight_command("moonlight-qt")

        assert config.moonlight_command == "moonlight-qt"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["moonlight"]["command"] == "moonlight-qt"

    def test_load_reads_moonlight_section(self, tmp_path: Path) -> None:
        """Config._load() reads the moonlight section from disk."""
        config = self._make_config(
            tmp_path,
            {"moonlight": {"command": "moonlight-qt"}},
        )
        assert config.moonlight_command == "moonlight-qt"

    def test_moonlight_section_missing_uses_default(self, tmp_path: Path) -> None:
        """Config without a moonlight section uses the default command."""
        config = self._make_config(tmp_path, {"retroarch": {}})
        assert config.moonlight_command == "flatpak run com.moonlight_stream.Moonlight"

    def test_save_includes_moonlight_section(self, tmp_path: Path) -> None:
        """Config.save() writes the moonlight section to disk."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "moonlight" in saved
        assert saved["moonlight"]["command"] == "flatpak run com.moonlight_stream.Moonlight"


# ---------------------------------------------------------------------------
# SettingsManager — moonlight settings
# ---------------------------------------------------------------------------


class TestSettingsManagerMoonlightSettings:
    def _make_manager_with_moonlight(self, tmp_path: Path, moonlight_library=None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        library = MagicMock()
        plex_library = MagicMock()
        manager = SettingsManager(
            config, library, plex_library, moonlight_library=moonlight_library
        )
        return manager, config

    def test_moonlight_command_property_returns_default(self, tmp_path: Path) -> None:
        """moonlightCommand property returns the default command."""
        manager, _ = self._make_manager_with_moonlight(tmp_path)
        assert manager.moonlightCommand == "flatpak run com.moonlight_stream.Moonlight"

    def test_set_moonlight_command_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        """setMoonlightCommand updates config and emits moonlightCommandChanged."""
        manager, config = self._make_manager_with_moonlight(tmp_path)
        emitted = []
        manager.moonlightCommandChanged.connect(lambda: emitted.append(True))

        manager.setMoonlightCommand("moonlight-qt")

        assert config.moonlight_command == "moonlight-qt"
        assert len(emitted) == 1

    def test_open_moonlight_calls_launch_gui(self, tmp_path: Path) -> None:
        """openMoonlight calls moonlight_library.launchGui()."""
        moonlight_library = MagicMock()
        manager, _ = self._make_manager_with_moonlight(tmp_path, moonlight_library=moonlight_library)

        manager.openMoonlight()

        moonlight_library.launchGui.assert_called_once()

    def test_open_moonlight_without_library_does_not_crash(self, tmp_path: Path) -> None:
        """openMoonlight is a no-op when moonlight_library is None."""
        manager, _ = self._make_manager_with_moonlight(tmp_path, moonlight_library=None)

        manager.openMoonlight()  # should not raise

    def test_moonlight_library_defaults_to_none(self, tmp_path: Path) -> None:
        """SettingsManager can be constructed without moonlight_library (backward compat)."""
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        # Existing call signature without moonlight_library — must not break
        manager = SettingsManager(config, MagicMock(), MagicMock())
        assert manager._moonlight_library is None


# ---------------------------------------------------------------------------
# Config — moonlight_host_uuid
# ---------------------------------------------------------------------------


class TestConfigMoonlightHostUuid:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_moonlight_host_uuid_default_is_empty(self, tmp_path: Path) -> None:
        """Config.moonlight_host_uuid defaults to empty string."""
        config = self._make_config(tmp_path)
        assert config.moonlight_host_uuid == ""

    def test_set_moonlight_host_uuid_persists(self, tmp_path: Path) -> None:
        """set_moonlight_host_uuid updates the property and saves to disk."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_moonlight_host_uuid("uuid-abc123")

        assert config.moonlight_host_uuid == "uuid-abc123"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["moonlight"]["host_uuid"] == "uuid-abc123"

    def test_load_reads_host_uuid_from_moonlight_section(self, tmp_path: Path) -> None:
        """Config._load() reads host_uuid from the moonlight section."""
        config = self._make_config(
            tmp_path,
            {"moonlight": {"command": "moonlight-qt", "host_uuid": "uuid-xyz"}},
        )
        assert config.moonlight_host_uuid == "uuid-xyz"

    def test_host_uuid_missing_from_moonlight_section_uses_empty(self, tmp_path: Path) -> None:
        """Config without host_uuid in moonlight section defaults to empty string."""
        config = self._make_config(
            tmp_path,
            {"moonlight": {"command": "moonlight-qt"}},
        )
        assert config.moonlight_host_uuid == ""

    def test_save_includes_host_uuid_in_moonlight_section(self, tmp_path: Path) -> None:
        """Config.save() writes host_uuid to the moonlight section."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._moonlight_host_uuid = "uuid-save-test"
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["moonlight"]["host_uuid"] == "uuid-save-test"


# ---------------------------------------------------------------------------
# SettingsManager — moonlightHostUuid property and setMoonlightHostUuid slot
# ---------------------------------------------------------------------------


class TestSettingsManagerMoonlightHostUuid:
    def _make_manager(self, tmp_path: Path, moonlight_library=None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        library = MagicMock()
        plex_library = MagicMock()
        manager = SettingsManager(
            config, library, plex_library, moonlight_library=moonlight_library
        )
        return manager, config

    def test_moonlight_host_uuid_property_default_empty(self, tmp_path: Path) -> None:
        """moonlightHostUuid property returns empty string by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.moonlightHostUuid == ""

    def test_moonlight_host_uuid_property_reflects_config(self, tmp_path: Path) -> None:
        """moonlightHostUuid property reflects the config value."""
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"moonlight": {"host_uuid": "uuid-from-config"}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        manager = SettingsManager(config, MagicMock(), MagicMock())
        assert manager.moonlightHostUuid == "uuid-from-config"

    def test_set_moonlight_host_uuid_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        """setMoonlightHostUuid updates config and emits moonlightHostUuidChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.moonlightHostUuidChanged.connect(lambda: emitted.append(True))

        manager.setMoonlightHostUuid("uuid-new")

        assert config.moonlight_host_uuid == "uuid-new"
        assert len(emitted) == 1

    def test_set_moonlight_host_uuid_calls_set_selected_host(self, tmp_path: Path) -> None:
        """setMoonlightHostUuid calls moonlight_library.setSelectedHost."""
        moonlight_library = MagicMock()
        manager, _ = self._make_manager(tmp_path, moonlight_library=moonlight_library)

        manager.setMoonlightHostUuid("uuid-new")

        moonlight_library.setSelectedHost.assert_called_once_with("uuid-new")

    def test_set_moonlight_host_uuid_without_library_does_not_crash(self, tmp_path: Path) -> None:
        """setMoonlightHostUuid is safe when moonlight_library is None."""
        manager, config = self._make_manager(tmp_path, moonlight_library=None)

        manager.setMoonlightHostUuid("uuid-new")  # should not raise

        assert config.moonlight_host_uuid == "uuid-new"


# ---------------------------------------------------------------------------
# SettingsManager — getHostsList
# ---------------------------------------------------------------------------


class TestSettingsManagerGetHostsList:
    def _make_manager(self, tmp_path: Path, moonlight_library=None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        library = MagicMock()
        plex_library = MagicMock()
        manager = SettingsManager(
            config, library, plex_library, moonlight_library=moonlight_library
        )
        return manager

    def test_get_hosts_list_returns_empty_when_no_library(self, tmp_path: Path) -> None:
        """getHostsList returns [] when moonlight_library is None."""
        manager = self._make_manager(tmp_path, moonlight_library=None)
        assert manager.getHostsList() == []

    def test_get_hosts_list_delegates_to_library(self, tmp_path: Path) -> None:
        """getHostsList delegates to moonlight_library.getPairedHosts()."""
        moonlight_library = MagicMock()
        moonlight_library.getPairedHosts.return_value = [
            {"id": "uuid-1", "label": "DESKTOP-PC (192.168.0.10)"},
        ]
        manager = self._make_manager(tmp_path, moonlight_library=moonlight_library)

        result = manager.getHostsList()

        moonlight_library.getPairedHosts.assert_called_once()
        assert len(result) == 1
        assert result[0]["id"] == "uuid-1"
        assert result[0]["label"] == "DESKTOP-PC (192.168.0.10)"

    def test_get_hosts_list_returns_correct_format(self, tmp_path: Path) -> None:
        """getHostsList returns list with id and label keys."""
        moonlight_library = MagicMock()
        moonlight_library.getPairedHosts.return_value = [
            {"id": "uuid-1", "label": "PC1 (10.0.0.1)"},
            {"id": "uuid-2", "label": "PC2 (10.0.0.2)"},
        ]
        manager = self._make_manager(tmp_path, moonlight_library=moonlight_library)

        result = manager.getHostsList()

        assert len(result) == 2
        for item in result:
            assert "id" in item
            assert "label" in item


# ---------------------------------------------------------------------------
# Config — show_network_indicator
# ---------------------------------------------------------------------------


class TestConfigShowNetworkIndicator:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_show_network_indicator_default_is_true(self, tmp_path: Path) -> None:
        """Config.show_network_indicator defaults to True."""
        config = self._make_config(tmp_path)
        assert config.show_network_indicator is True

    def test_show_network_indicator_loaded_from_json(self, tmp_path: Path) -> None:
        """Config._load() reads show_network_indicator from the ui section."""
        config = self._make_config(
            tmp_path,
            {"ui": {"show_network_indicator": False}},
        )
        assert config.show_network_indicator is False

    def test_show_network_indicator_saved_to_json(self, tmp_path: Path) -> None:
        """Config.save() writes show_network_indicator to the ui section."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.show_network_indicator = False
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["ui"]["show_network_indicator"] is False

    def test_set_show_network_indicator_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_network_indicator updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_network_indicator(False)

        assert config.show_network_indicator is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["ui"]["show_network_indicator"] is False

    def test_ui_section_missing_uses_default(self, tmp_path: Path) -> None:
        """Config without show_network_indicator in ui section uses default True."""
        config = self._make_config(tmp_path, {"ui": {"video_snap_autoplay": True}})
        assert config.show_network_indicator is True


# ---------------------------------------------------------------------------
# SettingsManager — showNetworkIndicator property and setShowNetworkIndicator slot
# ---------------------------------------------------------------------------


class TestSettingsManagerShowNetworkIndicator:
    def _make_manager(self, tmp_path: Path):
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

    def test_show_network_indicator_property_default_true(self, tmp_path: Path) -> None:
        """showNetworkIndicator property returns True by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.showNetworkIndicator is True

    def test_set_show_network_indicator_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowNetworkIndicator updates config and emits showNetworkIndicatorChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted: list[bool] = []
        manager.showNetworkIndicatorChanged.connect(lambda: emitted.append(True))

        manager.setShowNetworkIndicator(False)

        assert config.show_network_indicator is False
        assert len(emitted) == 1

    def test_set_show_network_indicator_to_true_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowNetworkIndicator(True) also emits the signal."""
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"ui": {"show_network_indicator": False}}),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        assert manager.showNetworkIndicator is False

        emitted: list[bool] = []
        manager.showNetworkIndicatorChanged.connect(lambda: emitted.append(True))

        manager.setShowNetworkIndicator(True)

        assert config.show_network_indicator is True
        assert len(emitted) == 1

    def test_show_network_indicator_config_round_trip(self, tmp_path: Path) -> None:
        """show_network_indicator survives a save/load round-trip."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_network_indicator(False)

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.show_network_indicator is False


# ---------------------------------------------------------------------------
# SettingsManager — controller mapping slots
# ---------------------------------------------------------------------------


def _make_settings_manager_with_gamepad(tmp_path: Path, gamepad_manager=None):
    """Create a SettingsManager with a real Config and optional mock gamepad_manager."""
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    manager = SettingsManager(
        config, library, plex_library, gamepad_manager=gamepad_manager
    )
    return manager


class TestSettingsManagerGetControllerActions:
    def test_returns_list_of_dicts(self, tmp_path: Path) -> None:
        """getControllerActions returns a list of dicts."""
        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_returns_14_actions(self, tmp_path: Path) -> None:
        """getControllerActions returns exactly 14 actions (matching ACTIONS list)."""
        from backend.controller_mapping import ACTIONS

        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        assert len(result) == len(ACTIONS)

    def test_each_entry_has_required_keys(self, tmp_path: Path) -> None:
        """Each action dict has name, displayName, and skippable keys."""
        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        for entry in result:
            assert "name" in entry
            assert "displayName" in entry
            assert "skippable" in entry

    def test_first_action_is_dpad_up(self, tmp_path: Path) -> None:
        """First action is dpad_up with displayName 'D-pad Up'."""
        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        assert result[0]["name"] == "dpad_up"
        assert result[0]["displayName"] == "D-pad Up"
        assert result[0]["skippable"] is False

    def test_skippable_actions_are_marked(self, tmp_path: Path) -> None:
        """Skippable actions (shoulders, triggers) have skippable=True."""
        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        skippable_names = {e["name"] for e in result if e["skippable"]}
        assert "left_shoulder" in skippable_names
        assert "right_shoulder" in skippable_names
        assert "left_trigger" in skippable_names
        assert "right_trigger" in skippable_names

    def test_non_skippable_actions_are_marked(self, tmp_path: Path) -> None:
        """Core navigation actions have skippable=False."""
        manager = _make_settings_manager_with_gamepad(tmp_path)
        result = manager.getControllerActions()
        non_skippable = {e["name"] for e in result if not e["skippable"]}
        assert "dpad_up" in non_skippable
        assert "accept" in non_skippable
        assert "cancel" in non_skippable


class TestSettingsManagerSaveControllerMapping:
    def test_saves_valid_mapping_to_disk(self, tmp_path: Path) -> None:
        """saveControllerMapping writes the mapping to disk."""
        from backend.controller_mapping import load_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        manager = _make_settings_manager_with_gamepad(tmp_path)

        mapping = [
            {"name": "dpad_up", "type": "axis", "code": 17, "value": -1},
            {"name": "accept", "type": "button", "code": 305, "value": 1},
        ]

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.saveControllerMapping(mapping)
            result = load_mapping()

        assert result["dpad_up"]["code"] == 17
        assert result["accept"]["code"] == 305

    def test_calls_reload_mapping_on_gamepad_manager(self, tmp_path: Path) -> None:
        """saveControllerMapping calls gamepad_manager.reloadMapping() after saving."""
        mapping_file = tmp_path / "controller_mapping.json"
        mock_gamepad = MagicMock()
        manager = _make_settings_manager_with_gamepad(tmp_path, gamepad_manager=mock_gamepad)

        mapping = [
            {"name": "dpad_up", "type": "axis", "code": 17, "value": -1},
        ]

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.saveControllerMapping(mapping)

        mock_gamepad.reloadMapping.assert_called_once()

    def test_does_not_crash_without_gamepad_manager(self, tmp_path: Path) -> None:
        """saveControllerMapping is safe when gamepad_manager is None."""
        mapping_file = tmp_path / "controller_mapping.json"
        manager = _make_settings_manager_with_gamepad(tmp_path, gamepad_manager=None)

        mapping = [
            {"name": "dpad_up", "type": "axis", "code": 17, "value": -1},
        ]

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.saveControllerMapping(mapping)  # should not raise

    def test_ignores_invalid_entries(self, tmp_path: Path) -> None:
        """saveControllerMapping skips entries with invalid structure."""
        from backend.controller_mapping import load_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        manager = _make_settings_manager_with_gamepad(tmp_path)

        mapping = [
            {"name": "dpad_up", "type": "axis", "code": 17, "value": -1},
            {"name": "bad_entry", "type": "unknown", "code": 99, "value": 1},  # bad type
            {"name": "also_bad"},  # missing fields
            "not a dict",  # not a dict at all
        ]

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.saveControllerMapping(mapping)
            result = load_mapping()

        # Only the valid entry should be saved
        assert result["dpad_up"]["code"] == 17

    def test_rejects_non_list_input(self, tmp_path: Path) -> None:
        """saveControllerMapping logs a warning and returns early for non-list input."""
        manager = _make_settings_manager_with_gamepad(tmp_path)

        # Should not raise
        manager.saveControllerMapping("not a list")  # type: ignore[arg-type]
        manager.saveControllerMapping(None)  # type: ignore[arg-type]
        manager.saveControllerMapping(42)  # type: ignore[arg-type]


class TestSettingsManagerResetControllerMapping:
    def test_resets_to_defaults_on_disk(self, tmp_path: Path) -> None:
        """resetControllerMapping writes the default mapping to disk."""
        from backend.controller_mapping import DEFAULT_MAPPING, load_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        # Write a custom mapping first
        import json as _json
        custom = {k: dict(v) for k, v in DEFAULT_MAPPING.items()}
        custom["accept"]["code"] = 9999
        mapping_file.write_text(_json.dumps(custom), encoding="utf-8")

        manager = _make_settings_manager_with_gamepad(tmp_path)

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.resetControllerMapping()
            result = load_mapping()

        assert result["accept"]["code"] == DEFAULT_MAPPING["accept"]["code"]

    def test_calls_reload_mapping_on_gamepad_manager(self, tmp_path: Path) -> None:
        """resetControllerMapping calls gamepad_manager.reloadMapping() after saving."""
        mapping_file = tmp_path / "controller_mapping.json"
        mock_gamepad = MagicMock()
        manager = _make_settings_manager_with_gamepad(tmp_path, gamepad_manager=mock_gamepad)

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.resetControllerMapping()

        mock_gamepad.reloadMapping.assert_called_once()

    def test_does_not_crash_without_gamepad_manager(self, tmp_path: Path) -> None:
        """resetControllerMapping is safe when gamepad_manager is None."""
        mapping_file = tmp_path / "controller_mapping.json"
        manager = _make_settings_manager_with_gamepad(tmp_path, gamepad_manager=None)

        with patch("backend.controller_mapping.get_mapping_path", return_value=mapping_file):
            manager.resetControllerMapping()  # should not raise

    def test_gamepad_manager_kwarg_defaults_to_none(self, tmp_path: Path) -> None:
        """SettingsManager can be constructed without gamepad_manager (backward compat)."""
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        # Existing call signature without gamepad_manager — must not break
        manager = SettingsManager(config, MagicMock(), MagicMock())
        assert manager._gamepad_manager is None


# ---------------------------------------------------------------------------
# Config — sort_preferences section
# ---------------------------------------------------------------------------


class TestConfigSortPreferences:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_sort_retro_games_default_is_az(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.sort_retro_games == "az"

    def test_sort_steam_games_default_is_az(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.sort_steam_games == "az"

    def test_sort_moonlight_apps_default_is_az(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.sort_moonlight_apps == "az"

    def test_sort_plex_movies_default_is_empty(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.sort_plex_movies == ""

    def test_sort_plex_shows_default_is_empty(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.sort_plex_shows == ""

    def test_filter_plex_movie_genre_default_is_empty(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.filter_plex_movie_genre == ""

    def test_filter_plex_show_genre_default_is_empty(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        assert config.filter_plex_show_genre == ""

    def test_sort_preferences_loaded_from_json(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, {
            "sort_preferences": {
                "retro_games": "za",
                "steam_games": "recent",
                "moonlight_apps": "za",
                "plex_movies": "rating",
                "plex_shows": "year_desc",
                "plex_movie_genre": "28",
                "plex_show_genre": "10759",
            }
        })
        assert config.sort_retro_games == "za"
        assert config.sort_steam_games == "recent"
        assert config.sort_moonlight_apps == "za"
        assert config.sort_plex_movies == "rating"
        assert config.sort_plex_shows == "year_desc"
        assert config.filter_plex_movie_genre == "28"
        assert config.filter_plex_show_genre == "10759"

    def test_sort_preferences_saved_to_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_sort_retro_games("za")
            config.set_sort_steam_games("recent")
            config.set_sort_moonlight_apps("za")
            config.set_sort_plex_movies("rating")
            config.set_sort_plex_shows("year_desc")
            config.set_filter_plex_movie_genre("28")
            config.set_filter_plex_show_genre("10759")

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "sort_preferences" in saved
        sp = saved["sort_preferences"]
        assert sp["retro_games"] == "za"
        assert sp["steam_games"] == "recent"
        assert sp["moonlight_apps"] == "za"
        assert sp["plex_movies"] == "rating"
        assert sp["plex_shows"] == "year_desc"
        assert sp["plex_movie_genre"] == "28"
        assert sp["plex_show_genre"] == "10759"

    def test_sort_preferences_missing_section_uses_defaults(self, tmp_path: Path) -> None:
        """Config without sort_preferences section uses defaults."""
        config = self._make_config(tmp_path, {"ui": {}})
        assert config.sort_retro_games == "az"
        assert config.sort_plex_movies == ""
        assert config.filter_plex_movie_genre == ""

    def test_sort_preferences_round_trip(self, tmp_path: Path) -> None:
        """Sort preferences survive a save/load round-trip."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_sort_retro_games("recent")
            config.set_filter_plex_movie_genre("28")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.sort_retro_games == "recent"
        assert config2.filter_plex_movie_genre == "28"


# ---------------------------------------------------------------------------
# SettingsManager — sort preference properties and slots
# ---------------------------------------------------------------------------


class TestSettingsManagerSortPreferences:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_sort_retro_games_property_default(self, tmp_path: Path) -> None:
        manager, _ = self._make_manager(tmp_path)
        assert manager.sortRetroGames == "az"

    def test_sort_plex_movies_property_default(self, tmp_path: Path) -> None:
        manager, _ = self._make_manager(tmp_path)
        assert manager.sortPlexMovies == ""

    def test_filter_plex_movie_genre_property_default(self, tmp_path: Path) -> None:
        manager, _ = self._make_manager(tmp_path)
        assert manager.filterPlexMovieGenre == ""

    def test_sort_retro_games_property_reflects_config(self, tmp_path: Path) -> None:
        manager, _ = self._make_manager(tmp_path, {
            "sort_preferences": {"retro_games": "recent"}
        })
        assert manager.sortRetroGames == "recent"

    def test_set_sort_retro_games_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortRetroGamesChanged.connect(lambda: emitted.append(True))

        manager.setSortRetroGames("za")

        assert config.sort_retro_games == "za"
        assert len(emitted) == 1

    def test_set_sort_steam_games_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortSteamGamesChanged.connect(lambda: emitted.append(True))

        manager.setSortSteamGames("recent")

        assert config.sort_steam_games == "recent"
        assert len(emitted) == 1

    def test_set_sort_moonlight_apps_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortMoonlightAppsChanged.connect(lambda: emitted.append(True))

        manager.setSortMoonlightApps("za")

        assert config.sort_moonlight_apps == "za"
        assert len(emitted) == 1

    def test_set_sort_plex_movies_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortPlexMoviesChanged.connect(lambda: emitted.append(True))

        manager.setSortPlexMovies("rating")

        assert config.sort_plex_movies == "rating"
        assert len(emitted) == 1

    def test_set_sort_plex_shows_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortPlexShowsChanged.connect(lambda: emitted.append(True))

        manager.setSortPlexShows("year_desc")

        assert config.sort_plex_shows == "year_desc"
        assert len(emitted) == 1

    def test_set_filter_plex_movie_genre_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.filterPlexMovieGenreChanged.connect(lambda: emitted.append(True))

        manager.setFilterPlexMovieGenre("28")

        assert config.filter_plex_movie_genre == "28"
        assert len(emitted) == 1

    def test_set_filter_plex_show_genre_updates_config_and_emits_signal(self, tmp_path: Path) -> None:
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.filterPlexShowGenreChanged.connect(lambda: emitted.append(True))

        manager.setFilterPlexShowGenre("10759")

        assert config.filter_plex_show_genre == "10759"
        assert len(emitted) == 1

    def test_set_filter_plex_movie_genre_empty_clears_filter(self, tmp_path: Path) -> None:
        """Setting genre to empty string clears the filter."""
        manager, config = self._make_manager(tmp_path, {
            "sort_preferences": {"plex_movie_genre": "28"}
        })

        manager.setFilterPlexMovieGenre("")

        assert config.filter_plex_movie_genre == ""


# ---------------------------------------------------------------------------
# Config — tab visibility settings
# ---------------------------------------------------------------------------


class TestConfigTabVisibility:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_all_tab_visibility_defaults_are_true(self, tmp_path: Path) -> None:
        """All tab visibility settings default to True."""
        config = self._make_config(tmp_path)
        assert config.show_retro_games_tab is True
        assert config.show_pc_games_tab is True
        assert config.show_watch_tab is True
        assert config.show_listen_tab is True

    def test_tabs_section_loaded_from_json(self, tmp_path: Path) -> None:
        """Config._load() reads tab visibility from the tabs section."""
        config = self._make_config(tmp_path, {
            "tabs": {
                "show_retro_games": False,
                "show_pc_games": False,
                "show_watch": False,
                "show_listen": False,
            }
        })
        assert config.show_retro_games_tab is False
        assert config.show_pc_games_tab is False
        assert config.show_watch_tab is False
        assert config.show_listen_tab is False

    def test_tabs_section_partial_load_uses_defaults_for_missing(self, tmp_path: Path) -> None:
        """Missing keys in tabs section fall back to True."""
        config = self._make_config(tmp_path, {
            "tabs": {"show_retro_games": False}
        })
        assert config.show_retro_games_tab is False
        assert config.show_pc_games_tab is True
        assert config.show_watch_tab is True
        assert config.show_listen_tab is True

    def test_tabs_section_missing_uses_defaults(self, tmp_path: Path) -> None:
        """Config without a tabs section uses all-True defaults."""
        config = self._make_config(tmp_path, {"ui": {}})
        assert config.show_retro_games_tab is True
        assert config.show_pc_games_tab is True

    def test_tabs_section_saved_to_json(self, tmp_path: Path) -> None:
        """Config.save() writes the tabs section to disk."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._show_retro_games_tab = False
            config._show_pc_games_tab = True
            config._show_watch_tab = False
            config._show_listen_tab = True
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "tabs" in saved
        assert saved["tabs"]["show_retro_games"] is False
        assert saved["tabs"]["show_pc_games"] is True
        assert saved["tabs"]["show_watch"] is False
        assert saved["tabs"]["show_listen"] is True

    def test_set_show_retro_games_tab_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_retro_games_tab updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_retro_games_tab(False)

        assert config.show_retro_games_tab is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_retro_games"] is False

    def test_set_show_pc_games_tab_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_pc_games_tab updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_pc_games_tab(False)

        assert config.show_pc_games_tab is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_pc_games"] is False

    def test_set_show_watch_tab_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_watch_tab updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_watch_tab(False)

        assert config.show_watch_tab is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_watch"] is False

    def test_set_show_listen_tab_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_listen_tab updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_listen_tab(False)

        assert config.show_listen_tab is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_listen"] is False

    def test_tab_visibility_round_trip(self, tmp_path: Path) -> None:
        """Tab visibility settings survive a save/load round-trip."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_retro_games_tab(False)
            config.set_show_listen_tab(False)

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.show_retro_games_tab is False
        assert config2.show_pc_games_tab is True
        assert config2.show_watch_tab is True
        assert config2.show_listen_tab is False


# ---------------------------------------------------------------------------
# SettingsManager — tab visibility properties and slots
# ---------------------------------------------------------------------------


class TestSettingsManagerTabVisibility:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_all_tab_visibility_properties_default_true(self, tmp_path: Path) -> None:
        """All tab visibility properties return True by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.showRetroGamesTab is True
        assert manager.showPcGamesTab is True
        assert manager.showWatchTab is True
        assert manager.showListenTab is True

    def test_tab_visibility_properties_reflect_config(self, tmp_path: Path) -> None:
        """Tab visibility properties reflect values loaded from config."""
        manager, _ = self._make_manager(tmp_path, {
            "tabs": {
                "show_retro_games": False,
                "show_pc_games": True,
                "show_watch": False,
                "show_listen": True,
            }
        })
        assert manager.showRetroGamesTab is False
        assert manager.showPcGamesTab is True
        assert manager.showWatchTab is False
        assert manager.showListenTab is True

    def test_set_show_retro_games_tab_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowRetroGamesTab updates config and emits tabVisibilityChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowRetroGamesTab(False)

        assert config.show_retro_games_tab is False
        assert len(emitted) == 1

    def test_set_show_pc_games_tab_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowPcGamesTab updates config and emits tabVisibilityChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowPcGamesTab(False)

        assert config.show_pc_games_tab is False
        assert len(emitted) == 1

    def test_set_show_watch_tab_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowWatchTab updates config and emits tabVisibilityChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowWatchTab(False)

        assert config.show_watch_tab is False
        assert len(emitted) == 1

    def test_set_show_listen_tab_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowListenTab updates config and emits tabVisibilityChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowListenTab(False)

        assert config.show_listen_tab is False
        assert len(emitted) == 1

    def test_all_setters_emit_same_tab_visibility_changed_signal(
        self, tmp_path: Path
    ) -> None:
        """All four tab setters emit the shared tabVisibilityChanged signal."""
        manager, _ = self._make_manager(tmp_path)
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowRetroGamesTab(False)
        manager.setShowPcGamesTab(False)
        manager.setShowWatchTab(False)
        manager.setShowListenTab(False)

        assert len(emitted) == 4

    def test_re_enabling_tab_emits_signal(self, tmp_path: Path) -> None:
        """Re-enabling a hidden tab also emits tabVisibilityChanged."""
        manager, config = self._make_manager(tmp_path, {
            "tabs": {"show_retro_games": False}
        })
        emitted = []
        manager.tabVisibilityChanged.connect(lambda: emitted.append(True))

        manager.setShowRetroGamesTab(True)

        assert config.show_retro_games_tab is True
        assert len(emitted) == 1


# ---------------------------------------------------------------------------
# Config — retro_games_view_mode
# ---------------------------------------------------------------------------


class TestConfigRetroGamesViewMode:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_retro_games_view_mode_default_is_grid(self, tmp_path: Path) -> None:
        """A fresh Config() has retro_games_view_mode == 'grid'."""
        config = self._make_config(tmp_path)
        assert config.retro_games_view_mode == "grid"

    def test_set_retro_games_view_mode_to_list(self, tmp_path: Path) -> None:
        """set_retro_games_view_mode('list') → retro_games_view_mode == 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_retro_games_view_mode("list")

        assert config.retro_games_view_mode == "list"

    def test_set_retro_games_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """set_retro_games_view_mode('invalid') falls back to 'grid'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_retro_games_view_mode("invalid")

        assert config.retro_games_view_mode == "grid"

    def test_retro_games_view_mode_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'list', save, reload from same file → reads back 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_retro_games_view_mode("list")

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.retro_games_view_mode == "list"

    def test_load_validation_bogus_value_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with 'retro_games_view_mode': 'bogus' in ui section loads as 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"retro_games_view_mode": "bogus"}},
        )
        assert config.retro_games_view_mode == "grid"

    def test_missing_retro_games_view_mode_key_defaults_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no retro_games_view_mode key defaults to 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"video_snap_autoplay": True}},
        )
        assert config.retro_games_view_mode == "grid"


# ---------------------------------------------------------------------------
# SettingsManager — retroGamesViewMode property and setRetroGamesViewMode slot
# ---------------------------------------------------------------------------


class TestSettingsManagerRetroGamesViewMode:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_retro_games_view_mode_property_default_is_grid(
        self, tmp_path: Path
    ) -> None:
        """retroGamesViewMode returns 'grid' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.retroGamesViewMode == "grid"

    def test_set_retro_games_view_mode_to_list(self, tmp_path: Path) -> None:
        """setRetroGamesViewMode('list') → retroGamesViewMode returns 'list'."""
        manager, config = self._make_manager(tmp_path)

        manager.setRetroGamesViewMode("list")

        assert manager.retroGamesViewMode == "list"

    def test_set_retro_games_view_mode_emits_signal(self, tmp_path: Path) -> None:
        """setRetroGamesViewMode('list') emits retroGamesViewModeChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.retroGamesViewModeChanged.connect(lambda: emitted.append(True))

        manager.setRetroGamesViewMode("list")

        assert len(emitted) == 1

    def test_set_retro_games_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """setRetroGamesViewMode('invalid') → retroGamesViewMode returns 'grid'."""
        manager, config = self._make_manager(tmp_path)

        manager.setRetroGamesViewMode("invalid")

        assert manager.retroGamesViewMode == "grid"


# ---------------------------------------------------------------------------
# Config — pc_games_view_mode
# ---------------------------------------------------------------------------


class TestConfigPcGamesViewMode:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_pc_games_view_mode_default_is_grid(self, tmp_path: Path) -> None:
        """A fresh Config() has pc_games_view_mode == 'grid'."""
        config = self._make_config(tmp_path)
        assert config.pc_games_view_mode == "grid"

    def test_set_pc_games_view_mode_to_list(self, tmp_path: Path) -> None:
        """set_pc_games_view_mode('list') → pc_games_view_mode == 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_pc_games_view_mode("list")

        assert config.pc_games_view_mode == "list"

    def test_set_pc_games_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """set_pc_games_view_mode('invalid') falls back to 'grid'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_pc_games_view_mode("invalid")

        assert config.pc_games_view_mode == "grid"

    def test_pc_games_view_mode_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'list', save, reload from same file → reads back 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_pc_games_view_mode("list")

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.pc_games_view_mode == "list"

    def test_load_validation_bogus_value_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with 'pc_games_view_mode': 'bogus' in ui section loads as 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"pc_games_view_mode": "bogus"}},
        )
        assert config.pc_games_view_mode == "grid"

    def test_missing_pc_games_view_mode_key_defaults_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no pc_games_view_mode key defaults to 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"video_snap_autoplay": True}},
        )
        assert config.pc_games_view_mode == "grid"


# ---------------------------------------------------------------------------
# SettingsManager — pcGamesViewMode property and setPcGamesViewMode slot
# ---------------------------------------------------------------------------


class TestSettingsManagerPcGamesViewMode:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_pc_games_view_mode_property_default_is_grid(
        self, tmp_path: Path
    ) -> None:
        """pcGamesViewMode returns 'grid' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.pcGamesViewMode == "grid"

    def test_set_pc_games_view_mode_to_list(self, tmp_path: Path) -> None:
        """setPcGamesViewMode('list') → pcGamesViewMode returns 'list'."""
        manager, config = self._make_manager(tmp_path)

        manager.setPcGamesViewMode("list")

        assert manager.pcGamesViewMode == "list"

    def test_set_pc_games_view_mode_emits_signal(self, tmp_path: Path) -> None:
        """setPcGamesViewMode('list') emits pcGamesViewModeChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.pcGamesViewModeChanged.connect(lambda: emitted.append(True))

        manager.setPcGamesViewMode("list")

        assert len(emitted) == 1

    def test_set_pc_games_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """setPcGamesViewMode('invalid') → pcGamesViewMode returns 'grid'."""
        manager, config = self._make_manager(tmp_path)

        manager.setPcGamesViewMode("invalid")

        assert manager.pcGamesViewMode == "grid"


# ---------------------------------------------------------------------------
# Config — watch_view_mode
# ---------------------------------------------------------------------------


class TestConfigWatchViewMode:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_watch_view_mode_default_is_grid(self, tmp_path: Path) -> None:
        """A fresh Config() has watch_view_mode == 'grid'."""
        config = self._make_config(tmp_path)
        assert config.watch_view_mode == "grid"

    def test_set_watch_view_mode_to_list(self, tmp_path: Path) -> None:
        """set_watch_view_mode('list') → watch_view_mode == 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_watch_view_mode("list")

        assert config.watch_view_mode == "list"

    def test_set_watch_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """set_watch_view_mode('invalid') falls back to 'grid'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_watch_view_mode("invalid")

        assert config.watch_view_mode == "grid"

    def test_watch_view_mode_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'list', save, reload from same file → reads back 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_watch_view_mode("list")

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.watch_view_mode == "list"

    def test_load_validation_bogus_value_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with 'watch_view_mode': 'bogus' in ui section loads as 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"watch_view_mode": "bogus"}},
        )
        assert config.watch_view_mode == "grid"

    def test_missing_watch_view_mode_key_defaults_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no watch_view_mode key defaults to 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"video_snap_autoplay": True}},
        )
        assert config.watch_view_mode == "grid"


# ---------------------------------------------------------------------------
# SettingsManager — watchViewMode property and setWatchViewMode slot
# ---------------------------------------------------------------------------


class TestSettingsManagerWatchViewMode:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_watch_view_mode_property_default_is_grid(
        self, tmp_path: Path
    ) -> None:
        """watchViewMode returns 'grid' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.watchViewMode == "grid"

    def test_set_watch_view_mode_to_list(self, tmp_path: Path) -> None:
        """setWatchViewMode('list') → watchViewMode returns 'list'."""
        manager, config = self._make_manager(tmp_path)

        manager.setWatchViewMode("list")

        assert manager.watchViewMode == "list"

    def test_set_watch_view_mode_emits_signal(self, tmp_path: Path) -> None:
        """setWatchViewMode('list') emits watchViewModeChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.watchViewModeChanged.connect(lambda: emitted.append(True))

        manager.setWatchViewMode("list")

        assert len(emitted) == 1

    def test_set_watch_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """setWatchViewMode('invalid') → watchViewMode returns 'grid'."""
        manager, config = self._make_manager(tmp_path)

        manager.setWatchViewMode("invalid")

        assert manager.watchViewMode == "grid"


# ---------------------------------------------------------------------------
# Config — listen_view_mode
# ---------------------------------------------------------------------------


class TestConfigListenViewMode:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_listen_view_mode_default_is_grid(self, tmp_path: Path) -> None:
        """A fresh Config() has listen_view_mode == 'grid'."""
        config = self._make_config(tmp_path)
        assert config.listen_view_mode == "grid"

    def test_set_listen_view_mode_to_list(self, tmp_path: Path) -> None:
        """set_listen_view_mode('list') → listen_view_mode == 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_listen_view_mode("list")

        assert config.listen_view_mode == "list"

    def test_set_listen_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """set_listen_view_mode('invalid') falls back to 'grid'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_listen_view_mode("invalid")

        assert config.listen_view_mode == "grid"

    def test_listen_view_mode_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'list', save, reload from same file → reads back 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_listen_view_mode("list")

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.listen_view_mode == "list"

    def test_load_validation_bogus_value_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with 'listen_view_mode': 'bogus' in ui section loads as 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"listen_view_mode": "bogus"}},
        )
        assert config.listen_view_mode == "grid"

    def test_missing_listen_view_mode_key_defaults_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no listen_view_mode key defaults to 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"video_snap_autoplay": True}},
        )
        assert config.listen_view_mode == "grid"


# ---------------------------------------------------------------------------
# SettingsManager — listenViewMode property and setListenViewMode slot
# ---------------------------------------------------------------------------


class TestSettingsManagerListenViewMode:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_listen_view_mode_property_default_is_grid(
        self, tmp_path: Path
    ) -> None:
        """listenViewMode returns 'grid' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.listenViewMode == "grid"

    def test_set_listen_view_mode_to_list(self, tmp_path: Path) -> None:
        """setListenViewMode('list') → listenViewMode returns 'list'."""
        manager, config = self._make_manager(tmp_path)

        manager.setListenViewMode("list")

        assert manager.listenViewMode == "list"

    def test_set_listen_view_mode_emits_signal(self, tmp_path: Path) -> None:
        """setListenViewMode('list') emits listenViewModeChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.listenViewModeChanged.connect(lambda: emitted.append(True))

        manager.setListenViewMode("list")

        assert len(emitted) == 1

    def test_set_listen_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """setListenViewMode('invalid') → listenViewMode returns 'grid'."""
        manager, config = self._make_manager(tmp_path)

        manager.setListenViewMode("invalid")

        assert manager.listenViewMode == "grid"


# ---------------------------------------------------------------------------
# Config — sort_plex_artists
# ---------------------------------------------------------------------------


class TestConfigSortPlexArtists:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_sort_plex_artists_default_is_empty(self, tmp_path: Path) -> None:
        """A fresh Config() has sort_plex_artists == ''."""
        config = self._make_config(tmp_path)
        assert config.sort_plex_artists == ""

    def test_set_sort_plex_artists_to_az(self, tmp_path: Path) -> None:
        """set_sort_plex_artists('az') → sort_plex_artists == 'az'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_sort_plex_artists("az")

        assert config.sort_plex_artists == "az"

    def test_sort_plex_artists_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'az', save, reload from same file → reads back 'az'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_sort_plex_artists("az")

        # Reload from disk
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.sort_plex_artists == "az"

    def test_missing_sort_plex_artists_key_defaults_to_empty(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no plex_artists key in sort_preferences defaults to ''."""
        config = self._make_config(
            tmp_path,
            {"sort_preferences": {"plex_movies": "rating"}},
        )
        assert config.sort_plex_artists == ""


# ---------------------------------------------------------------------------
# SettingsManager — sortPlexArtists property and setSortPlexArtists slot
# ---------------------------------------------------------------------------


class TestSettingsManagerSortPlexArtists:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_sort_plex_artists_property_default_is_empty(
        self, tmp_path: Path
    ) -> None:
        """sortPlexArtists returns '' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.sortPlexArtists == ""

    def test_set_sort_plex_artists_to_az(self, tmp_path: Path) -> None:
        """setSortPlexArtists('az') → sortPlexArtists returns 'az'."""
        manager, config = self._make_manager(tmp_path)

        manager.setSortPlexArtists("az")

        assert config.sort_plex_artists == "az"

    def test_set_sort_plex_artists_emits_signal(self, tmp_path: Path) -> None:
        """setSortPlexArtists('az') emits sortPlexArtistsChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.sortPlexArtistsChanged.connect(lambda: emitted.append(True))

        manager.setSortPlexArtists("az")

        assert len(emitted) == 1


# ---------------------------------------------------------------------------
# Config — show_moonlight_tab
# ---------------------------------------------------------------------------


class TestConfigShowMoonlightTab:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_show_moonlight_tab_default_is_true(self, tmp_path: Path) -> None:
        """Config.show_moonlight_tab defaults to True."""
        config = self._make_config(tmp_path)
        assert config.show_moonlight_tab is True

    def test_show_moonlight_tab_loaded_from_json(self, tmp_path: Path) -> None:
        """Config._load() reads show_moonlight from the tabs section."""
        config = self._make_config(
            tmp_path,
            {"tabs": {"show_moonlight": False}},
        )
        assert config.show_moonlight_tab is False

    def test_show_moonlight_tab_saved_to_json(self, tmp_path: Path) -> None:
        """Config.save() writes show_moonlight to the tabs section."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._show_moonlight_tab = False
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_moonlight"] is False

    def test_set_show_moonlight_tab_updates_and_saves(self, tmp_path: Path) -> None:
        """set_show_moonlight_tab updates the property and persists."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_moonlight_tab(False)

        assert config.show_moonlight_tab is False
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["tabs"]["show_moonlight"] is False

    def test_show_moonlight_tab_round_trip(self, tmp_path: Path) -> None:
        """show_moonlight_tab survives a save/load round-trip."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_moonlight_tab(False)

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.show_moonlight_tab is False


# ---------------------------------------------------------------------------
# SettingsManager — showMoonlightTab property and setShowMoonlightTab slot
# ---------------------------------------------------------------------------


class TestShowMoonlightTab:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_show_moonlight_tab_property_default_true(self, tmp_path: Path) -> None:
        """showMoonlightTab property returns True by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.showMoonlightTab is True

    def test_show_moonlight_tab_property_reflects_config(self, tmp_path: Path) -> None:
        """showMoonlightTab property reflects the config value."""
        manager, _ = self._make_manager(tmp_path, {"tabs": {"show_moonlight": False}})
        assert manager.showMoonlightTab is False

    def test_set_show_moonlight_tab_updates_config_and_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowMoonlightTab updates config and emits showMoonlightTabChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted: list[bool] = []
        manager.showMoonlightTabChanged.connect(lambda: emitted.append(True))

        manager.setShowMoonlightTab(False)

        assert config.show_moonlight_tab is False
        assert len(emitted) == 1

    def test_set_show_moonlight_tab_to_true_emits_signal(
        self, tmp_path: Path
    ) -> None:
        """setShowMoonlightTab(True) also emits the signal."""
        manager, config = self._make_manager(tmp_path, {"tabs": {"show_moonlight": False}})
        emitted: list[bool] = []
        manager.showMoonlightTabChanged.connect(lambda: emitted.append(True))

        manager.setShowMoonlightTab(True)

        assert config.show_moonlight_tab is True
        assert len(emitted) == 1

    def test_show_moonlight_tab_config_round_trip(self, tmp_path: Path) -> None:
        """show_moonlight_tab survives a save/load round-trip via SettingsManager."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_show_moonlight_tab(False)

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.show_moonlight_tab is False


# ---------------------------------------------------------------------------
# Config — moonlight_view_mode
# ---------------------------------------------------------------------------


class TestConfigMoonlightViewMode:
    def _make_config(self, tmp_path: Path, data: dict | None = None) -> Config:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config()

    def test_moonlight_view_mode_default_is_grid(self, tmp_path: Path) -> None:
        """A fresh Config() has moonlight_view_mode == 'grid'."""
        config = self._make_config(tmp_path)
        assert config.moonlight_view_mode == "grid"

    def test_set_moonlight_view_mode_to_list(self, tmp_path: Path) -> None:
        """set_moonlight_view_mode('list') → moonlight_view_mode == 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_moonlight_view_mode("list")

        assert config.moonlight_view_mode == "list"

    def test_set_moonlight_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """set_moonlight_view_mode('invalid') falls back to 'grid'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_moonlight_view_mode("invalid")

        assert config.moonlight_view_mode == "grid"

    def test_moonlight_view_mode_persistence_round_trip(self, tmp_path: Path) -> None:
        """Set to 'list', save, reload from same file → reads back 'list'."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_moonlight_view_mode("list")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.moonlight_view_mode == "list"

    def test_load_validation_bogus_value_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with 'moonlight_view_mode': 'bogus' in ui section loads as 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"moonlight_view_mode": "bogus"}},
        )
        assert config.moonlight_view_mode == "grid"

    def test_missing_moonlight_view_mode_key_defaults_to_grid(
        self, tmp_path: Path
    ) -> None:
        """Config JSON with no moonlight_view_mode key defaults to 'grid'."""
        config = self._make_config(
            tmp_path,
            {"ui": {"video_snap_autoplay": True}},
        )
        assert config.moonlight_view_mode == "grid"


# ---------------------------------------------------------------------------
# SettingsManager — moonlightViewMode property and setMoonlightViewMode slot
# ---------------------------------------------------------------------------


class TestMoonlightViewMode:
    def _make_manager(self, tmp_path: Path, data: dict | None = None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager, config

    def test_moonlight_view_mode_property_default_is_grid(
        self, tmp_path: Path
    ) -> None:
        """moonlightViewMode returns 'grid' by default."""
        manager, _ = self._make_manager(tmp_path)
        assert manager.moonlightViewMode == "grid"

    def test_set_moonlight_view_mode_to_list(self, tmp_path: Path) -> None:
        """setMoonlightViewMode('list') → moonlightViewMode returns 'list'."""
        manager, config = self._make_manager(tmp_path)

        manager.setMoonlightViewMode("list")

        assert manager.moonlightViewMode == "list"

    def test_set_moonlight_view_mode_emits_signal(self, tmp_path: Path) -> None:
        """setMoonlightViewMode('list') emits moonlightViewModeChanged."""
        manager, config = self._make_manager(tmp_path)
        emitted = []
        manager.moonlightViewModeChanged.connect(lambda: emitted.append(True))

        manager.setMoonlightViewMode("list")

        assert len(emitted) == 1

    def test_set_moonlight_view_mode_invalid_falls_back_to_grid(
        self, tmp_path: Path
    ) -> None:
        """setMoonlightViewMode('invalid') → moonlightViewMode returns 'grid'."""
        manager, config = self._make_manager(tmp_path)

        manager.setMoonlightViewMode("invalid")

        assert manager.moonlightViewMode == "grid"

    def test_set_moonlight_view_mode_persists(self, tmp_path: Path) -> None:
        """setMoonlightViewMode persists the value via config."""
        manager, config = self._make_manager(tmp_path)

        manager.setMoonlightViewMode("list")

        assert config.moonlight_view_mode == "list"


# ---------------------------------------------------------------------------
# SettingsManager — getAvailableCores
# ---------------------------------------------------------------------------


class TestGetAvailableCores:
    def _make_manager(self, tmp_path: Path, cores_dir=None):
        from backend.settings_manager import SettingsManager

        config_file = tmp_path / "config.json"
        data: dict = {}
        if cores_dir is not None:
            data["retroarch"] = {"cores_directory": str(cores_dir)}
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())
        return manager

    def test_returns_empty_when_directory_does_not_exist(self, tmp_path: Path) -> None:
        """getAvailableCores returns [] when cores_directory does not exist."""
        nonexistent = tmp_path / "no_such_dir"
        manager = self._make_manager(tmp_path, cores_dir=nonexistent)

        result = manager.getAvailableCores("gb")

        assert result == []

    def test_returns_empty_when_directory_has_no_so_files(self, tmp_path: Path) -> None:
        """getAvailableCores returns [] when cores_directory exists but has no .so files."""
        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        (cores_dir / "readme.txt").write_text("not a core")
        (cores_dir / "core.so.zip").write_text("not a core")
        (cores_dir / "core.info").write_text("not a core")
        manager = self._make_manager(tmp_path, cores_dir=cores_dir)

        result = manager.getAvailableCores("gb")

        assert result == []

    def test_returns_only_compatible_cores(self, tmp_path: Path) -> None:
        """getAvailableCores returns only cores compatible with the given system."""
        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        # Two compatible cores for "gb" + one incompatible (snes9x)
        (cores_dir / "gambatte_libretro.so").write_text("")
        (cores_dir / "mgba_libretro.so").write_text("")
        (cores_dir / "snes9x_libretro.so").write_text("")
        manager = self._make_manager(tmp_path, cores_dir=cores_dir)

        result = manager.getAvailableCores("gb")

        assert "gambatte_libretro.so" in result
        assert "mgba_libretro.so" in result
        assert "snes9x_libretro.so" not in result
        assert len(result) == 2

    def test_preserves_recommendation_order(self, tmp_path: Path) -> None:
        """getAvailableCores preserves the recommendation order from SYSTEM_COMPATIBLE_CORES."""
        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        # Install in reverse order — result should still follow recommendation order
        (cores_dir / "snes9x_libretro.so").write_text("")
        (cores_dir / "bsnes_libretro.so").write_text("")
        manager = self._make_manager(tmp_path, cores_dir=cores_dir)

        result = manager.getAvailableCores("snes")

        # snes9x is recommended first for "snes"
        assert result[0] == "snes9x_libretro.so"
        assert result[1] == "bsnes_libretro.so"

    def test_fallback_for_unknown_system(self, tmp_path: Path) -> None:
        """getAvailableCores returns [current_core] for a system not in SYSTEM_COMPATIBLE_CORES."""
        from backend.settings_manager import SettingsManager

        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        (cores_dir / "custom_core_libretro.so").write_text("")

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({
                "retroarch": {"cores_directory": str(cores_dir)},
                "systems": {
                    "myunknownsystem": {
                        "display_name": "My Unknown System",
                        "core": "custom_core_libretro.so",
                        "extensions": [".bin"],
                    }
                },
            }),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())

        result = manager.getAvailableCores("myunknownsystem")

        assert result == ["custom_core_libretro.so"]

    def test_fallback_returns_empty_when_core_not_installed(self, tmp_path: Path) -> None:
        """getAvailableCores returns [] for unknown system when current core is not installed."""
        from backend.settings_manager import SettingsManager

        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        # Core is NOT present in the directory

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({
                "retroarch": {"cores_directory": str(cores_dir)},
                "systems": {
                    "myunknownsystem": {
                        "display_name": "My Unknown System",
                        "core": "missing_core_libretro.so",
                        "extensions": [".bin"],
                    }
                },
            }),
            encoding="utf-8",
        )
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        manager = SettingsManager(config, MagicMock(), MagicMock())

        result = manager.getAvailableCores("myunknownsystem")

        assert result == []

    def test_excludes_non_so_files(self, tmp_path: Path) -> None:
        """getAvailableCores only returns .so files, not .so.zip or .info files."""
        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        (cores_dir / "snes9x_libretro.so").write_text("")
        (cores_dir / "snes9x_libretro.so.zip").write_text("")
        (cores_dir / "snes9x_libretro.info").write_text("")
        manager = self._make_manager(tmp_path, cores_dir=cores_dir)

        result = manager.getAvailableCores("snes")

        assert result == ["snes9x_libretro.so"]

    def test_returns_filenames_not_full_paths(self, tmp_path: Path) -> None:
        """getAvailableCores returns bare filenames, not full paths."""
        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        (cores_dir / "gambatte_libretro.so").write_text("")
        manager = self._make_manager(tmp_path, cores_dir=cores_dir)

        result = manager.getAvailableCores("gb")

        assert len(result) == 1
        assert result[0] == "gambatte_libretro.so"
        assert "/" not in result[0]
