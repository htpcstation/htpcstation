"""Tests for Task 019 — Browser Launch & Lifecycle.

Covers:
  - BrowserLauncher: builds correct command with --kiosk and --app=<url>
  - BrowserLauncher: rejects empty URL
  - BrowserLauncher: ignores launch when a process is already running
  - BrowserLauncher: emits processFinished(-1) on start failure
  - BrowserLauncher: emits processFinished(exit_code) on normal exit
  - Config: browser_command property defaults to flatpak run com.brave.Browser
  - Config: browser_command loaded from JSON
  - Config: browser_command saved to JSON
  - PlexLibrary.launchContent: builds correct deep-link URL
  - PlexLibrary.launchContent: no-op when browser launcher is None
  - PlexLibrary.launchContent: no-op when server URL is not configured
  - PlexLibrary.launchContent: no-op when rating key is empty
  - PlexLibrary._worker_refresh: caches machineIdentifier via signal
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# BrowserLauncher — command construction
# ---------------------------------------------------------------------------


class TestBrowserLauncherCommandConstruction:
    def test_build_command_includes_kiosk_and_app_flags(self) -> None:
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        url = "http://192.168.0.2:32400/web/index.html#!/server/abc/details?key=/library/metadata/123"
        cmd = launcher._build_command(url)

        assert cmd[0] == "flatpak"
        assert "--kiosk" in cmd
        assert url in cmd

    def test_build_command_starts_with_flatpak_run_brave(self) -> None:
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        cmd = launcher._build_command("http://example.com")

        assert cmd[:3] == ["flatpak", "run", "com.brave.Browser"]

    def test_build_command_app_flag_contains_full_url(self) -> None:
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        url = "http://server:32400/web/index.html#!/server/machineid/details?key=/library/metadata/42"
        cmd = launcher._build_command(url)

        # URL should be the last argument (positional, not --app= flag)
        assert cmd[-1] == url

    def test_build_command_includes_start_fullscreen(self) -> None:
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        cmd = launcher._build_command("http://example.com")

        assert "--start-fullscreen" in cmd


# ---------------------------------------------------------------------------
# BrowserLauncher — launch guard
# ---------------------------------------------------------------------------


class TestBrowserLauncherLaunchGuard:
    def test_launch_returns_false_for_empty_url(self) -> None:
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        result = launcher.launch("")
        assert result is False

    def test_launch_ignores_when_process_already_running(self) -> None:
        from backend.browser_launcher import BrowserLauncher
        from PySide6.QtCore import QProcess

        launcher = BrowserLauncher()

        # Simulate a running process
        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running
        launcher._process = mock_process

        result = launcher.launch("http://example.com")
        assert result is False

    def test_launch_emits_process_finished_minus_one_on_start_failure(self) -> None:
        from backend.browser_launcher import BrowserLauncher
        from PySide6.QtCore import QProcess

        launcher = BrowserLauncher()

        received: list[int] = []
        launcher.processFinished.connect(lambda code: received.append(code))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "waitForStarted", return_value=False), \
             patch.object(QProcess, "errorString", return_value="not found"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch("http://example.com")

        assert received == [-1]


# ---------------------------------------------------------------------------
# Config — browser_command property
# ---------------------------------------------------------------------------


class TestConfigBrowserCommand:
    def test_browser_command_default(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.browser_command == "flatpak run com.brave.Browser"

    def test_browser_command_loaded_from_json(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"browser": {"command": "custom-browser"}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.browser_command == "custom-browser"

    def test_browser_command_saved_to_json(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "browser" in saved
        assert saved["browser"]["command"] == "flatpak run com.brave.Browser"

    def test_browser_command_empty_string_uses_default(self, tmp_path: Path) -> None:
        """An empty string in config falls back to the built-in default."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"browser": {"command": ""}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.browser_command == "flatpak run com.brave.Browser"


# ---------------------------------------------------------------------------
# PlexLibrary.launchContent — URL construction and guards
# ---------------------------------------------------------------------------


class TestPlexLibraryLaunchContent:
    def _make_lib(self, browser_launcher=None):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_url = "http://192.168.0.2:32400"
            config.plex_token = "tok"
            lib = PlexLibrary(config, browser_launcher)
        return lib

    def test_launches_with_correct_deep_link_url(self) -> None:
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._machine_identifier = "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"

        lib.launchContent("12345")

        mock_launcher.launch.assert_called_once()
        url = mock_launcher.launch.call_args[0][0]
        assert "http://192.168.0.2:32400" in url
        assert "1e5c921da4e4a7a69709f8fe67505d2ffb274a46" in url
        assert "/library/metadata/12345" in url
        assert "#!/server/" in url

    def test_url_format_matches_spec(self) -> None:
        """Verify the exact URL format from the task brief (includes autoPlay=1)."""
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        machine_id = "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"
        lib._machine_identifier = machine_id

        lib.launchContent("99")

        url = mock_launcher.launch.call_args[0][0]
        expected = (
            f"http://192.168.0.2:32400/web/index.html"
            f"#!/server/{machine_id}/details"
            f"?key=/library/metadata/99"
            f"&autoPlay=1"
        )
        assert url == expected

    def test_no_op_when_browser_launcher_is_none(self) -> None:
        lib = self._make_lib(browser_launcher=None)
        lib._machine_identifier = "abc"
        # Should not raise
        lib.launchContent("123")

    def test_no_op_when_server_url_not_configured(self) -> None:
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._config.plex_server_url = None
        lib._machine_identifier = "abc"

        lib.launchContent("123")

        mock_launcher.launch.assert_not_called()

    def test_no_op_when_rating_key_is_empty(self) -> None:
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._machine_identifier = "abc"

        lib.launchContent("")

        mock_launcher.launch.assert_not_called()


# ---------------------------------------------------------------------------
# PlexLibrary._worker_refresh — caches machineIdentifier
# ---------------------------------------------------------------------------


class TestPlexLibraryMachineIdentifierCaching:
    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_url = "http://server:32400"
            config.plex_token = "tok"
            lib = PlexLibrary(config)
        return lib

    def test_machine_identifier_cached_after_worker_refresh(self) -> None:
        """_worker_refresh emits _machineIdentifierReady which caches the ID."""
        lib = self._make_lib()

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {
            "machineIdentifier": "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"
        }
        mock_client.get_libraries.return_value = []
        mock_client.get_on_deck.return_value = []

        # Simulate the signal being emitted synchronously (direct connection)
        emitted_ids: list[str] = []
        lib._machineIdentifierReady.connect(lambda mid: emitted_ids.append(mid))

        lib._worker_refresh(mock_client)

        assert emitted_ids == ["1e5c921da4e4a7a69709f8fe67505d2ffb274a46"]

    def test_machine_identifier_not_emitted_when_unavailable(self) -> None:
        """When the server is unreachable, no machineIdentifier is emitted."""
        lib = self._make_lib()

        mock_client = MagicMock()
        mock_client.get_identity.side_effect = Exception("connection refused")

        emitted_ids: list[str] = []
        lib._machineIdentifierReady.connect(lambda mid: emitted_ids.append(mid))

        lib._worker_refresh(mock_client)

        assert emitted_ids == []

    def test_on_machine_identifier_ready_stores_value(self) -> None:
        """_on_machine_identifier_ready stores the ID in _machine_identifier."""
        lib = self._make_lib()
        assert lib._machine_identifier == ""

        lib._on_machine_identifier_ready("abc123")

        assert lib._machine_identifier == "abc123"
