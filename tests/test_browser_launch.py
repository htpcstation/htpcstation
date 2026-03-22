"""Tests for Task 019 — Browser Launch & Lifecycle.

Covers:
  - BrowserLauncher: builds correct command with --kiosk and --app=<url>
  - BrowserLauncher: rejects empty URL
  - BrowserLauncher: ignores launch when a process is already running
  - BrowserLauncher: emits processFinished(-1) on start failure
  - BrowserLauncher: emits processFinished(exit_code) on normal exit
  - BrowserLauncher: deploys extension to flatpak data dir before launch
  - BrowserLauncher: omits --load-extension when source dir is missing
  - BrowserLauncher: omits --load-extension when copy fails
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

    def test_build_command_includes_load_extension_flag(self, tmp_path: Path) -> None:
        """--load-extension points to the deployed path, not the source path."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        dst = tmp_path / "deployed"
        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        cmd = launcher._build_command("http://example.com")

        load_ext_flags = [tok for tok in cmd if tok.startswith("--load-extension=")]
        assert len(load_ext_flags) == 1
        ext_path = load_ext_flags[0].split("=", 1)[1]
        # Must point to the deployed dir, not the source dir
        assert ext_path == str(dst)
        assert ext_path != str(src)

    def test_build_command_load_extension_before_url(self, tmp_path: Path) -> None:
        """--load-extension must appear before the URL argument."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        launcher._extension_dir = src
        launcher._extension_deploy_dir = tmp_path / "deployed"

        url = "http://example.com"
        cmd = launcher._build_command(url)

        url_idx = cmd.index(url)
        load_ext_idx = next(
            i for i, tok in enumerate(cmd) if tok.startswith("--load-extension=")
        )
        assert load_ext_idx < url_idx


# ---------------------------------------------------------------------------
# BrowserLauncher — extension deployment
# ---------------------------------------------------------------------------


class TestBrowserLauncherExtensionDeploy:
    def test_deploy_extension_copies_to_flatpak_data_dir(self, tmp_path: Path) -> None:
        """_deploy_extension copies source to _extension_deploy_dir and returns it."""
        from backend.browser_launcher import BrowserLauncher
        import shutil

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        result = launcher._deploy_extension()

        assert result == dst
        assert (dst / "manifest.json").exists()

    def test_deploy_extension_overwrites_previous_copy(self, tmp_path: Path) -> None:
        """dirs_exist_ok=True means a second deploy overwrites the first."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text('{"version":"1"}', encoding="utf-8")
        dst = tmp_path / "deployed"
        dst.mkdir()
        (dst / "old_file.txt").write_text("stale", encoding="utf-8")

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        result = launcher._deploy_extension()

        assert result == dst
        assert (dst / "manifest.json").read_text(encoding="utf-8") == '{"version":"1"}'

    def test_deploy_extension_returns_none_when_source_missing(self, tmp_path: Path) -> None:
        """Returns None (and logs a warning) when the source dir does not exist."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        launcher._extension_dir = tmp_path / "nonexistent"
        launcher._extension_deploy_dir = tmp_path / "deployed"

        result = launcher._deploy_extension()

        assert result is None
        assert not (tmp_path / "deployed").exists()

    def test_deploy_extension_returns_none_on_oserror(self, tmp_path: Path) -> None:
        """Returns None (and logs a warning) when shutil.copytree raises OSError."""
        from backend.browser_launcher import BrowserLauncher
        import shutil

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        launcher._extension_dir = src
        launcher._extension_deploy_dir = tmp_path / "deployed"

        with patch.object(shutil, "copytree", side_effect=OSError("permission denied")):
            result = launcher._deploy_extension()

        assert result is None

    def test_build_command_omits_load_extension_when_source_missing(self, tmp_path: Path) -> None:
        """When source dir is absent, --load-extension is not in the command."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        launcher._extension_dir = tmp_path / "nonexistent"
        launcher._extension_deploy_dir = tmp_path / "deployed"

        cmd = launcher._build_command("http://example.com")

        assert not any(tok.startswith("--load-extension=") for tok in cmd)
        assert "http://example.com" in cmd

    def test_build_command_uses_deployed_path_not_source_path(self, tmp_path: Path) -> None:
        """The --load-extension flag uses the deployed dir, not the source dir."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        cmd = launcher._build_command("http://example.com")

        load_ext_flags = [tok for tok in cmd if tok.startswith("--load-extension=")]
        assert len(load_ext_flags) == 1
        assert load_ext_flags[0] == f"--load-extension={dst}"


# ---------------------------------------------------------------------------
# BrowserLauncher — launch guard
# ---------------------------------------------------------------------------


class TestBrowserLauncherLaunchGuard:
    def test_launch_returns_none_for_empty_url(self) -> None:
        """launch() returns None (not False) for an empty URL — it's now void."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        result = launcher.launch("")
        assert result is None

    def test_launch_ignores_when_process_already_running(self) -> None:
        from backend.browser_launcher import BrowserLauncher
        from PySide6.QtCore import QProcess

        launcher = BrowserLauncher()

        # Simulate a running process
        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running
        launcher._process = mock_process

        result = launcher.launch("http://example.com")
        assert result is None

    def test_launch_emits_process_finished_minus_one_on_start_failure(self) -> None:
        """processFinished(-1) is emitted when errorOccurred(FailedToStart) fires."""
        from backend.browser_launcher import BrowserLauncher
        from PySide6.QtCore import QProcess

        launcher = BrowserLauncher()

        received: list[int] = []
        launcher.processFinished.connect(lambda code: received.append(code))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch("http://example.com")
            # Simulate the FailedToStart error signal firing asynchronously
            assert launcher._process is not None
            launcher._on_error_occurred(QProcess.ProcessError.FailedToStart)

        assert received == [-1]

    def test_non_failed_to_start_error_does_not_emit_process_finished(self) -> None:
        """errorOccurred for non-FailedToStart errors is ignored (handled by finished)."""
        from backend.browser_launcher import BrowserLauncher
        from PySide6.QtCore import QProcess

        launcher = BrowserLauncher()

        received: list[int] = []
        launcher.processFinished.connect(lambda code: received.append(code))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch("http://example.com")
            # Simulate a Crashed error — should be ignored
            launcher._on_error_occurred(QProcess.ProcessError.Crashed)

        assert received == []


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
    def _make_lib(self, browser_launcher=None, server_url: str = "http://192.168.0.2:32400"):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config, browser_launcher)
        # Set the resolved server URL directly (simulates successful _setup_client)
        lib._server_url = server_url
        return lib

    def test_launches_with_correct_deep_link_url(self) -> None:
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._machine_identifier = "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"

        lib.launchContent("12345")

        mock_launcher.launch.assert_called_once()
        url = mock_launcher.launch.call_args[0][0]
        assert url.startswith("https://app.plex.tv/desktop?X-Plex-Token=")
        assert "1e5c921da4e4a7a69709f8fe67505d2ffb274a46" in url
        assert "/library/metadata/12345" in url

    def test_url_format_matches_spec(self) -> None:
        """Verify the exact URL format: token in query string before hash fragment."""
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        machine_id = "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"
        lib._machine_identifier = machine_id
        lib._active_token = "tok"
        # No user title cached — htpc_user should be absent
        lib._cached_user_title = ""

        lib.launchContent("99")

        url = mock_launcher.launch.call_args[0][0]
        expected = (
            f"https://app.plex.tv/desktop"
            f"?X-Plex-Token=tok"
            f"#!/server/{machine_id}/details"
            f"?key=/library/metadata/99"
            f"&autoPlay=1"
        )
        assert url == expected

    def test_url_includes_htpc_user_when_user_title_cached(self) -> None:
        """When _cached_user_title is set, htpc_user is appended to the URL."""
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        machine_id = "1e5c921da4e4a7a69709f8fe67505d2ffb274a46"
        lib._machine_identifier = machine_id
        lib._active_token = "tok"
        lib._cached_user_title = "thwonp"

        lib.launchContent("99")

        url = mock_launcher.launch.call_args[0][0]
        expected = (
            f"https://app.plex.tv/desktop"
            f"?X-Plex-Token=tok"
            f"#!/server/{machine_id}/details"
            f"?key=/library/metadata/99"
            f"&autoPlay=1"
            f"&htpc_user=thwonp"
        )
        assert url == expected

    def test_url_htpc_user_is_url_encoded(self) -> None:
        """User titles with special characters are URL-encoded in htpc_user."""
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._machine_identifier = "abc"
        lib._active_token = "tok"
        lib._cached_user_title = "Eric Toland"

        lib.launchContent("42")

        url = mock_launcher.launch.call_args[0][0]
        assert "htpc_user=Eric%20Toland" in url

    def test_url_no_htpc_user_when_title_empty(self) -> None:
        """When _cached_user_title is empty, htpc_user is not appended."""
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher)
        lib._machine_identifier = "abc"
        lib._active_token = "tok"
        lib._cached_user_title = ""

        lib.launchContent("42")

        url = mock_launcher.launch.call_args[0][0]
        assert "htpc_user" not in url

    def test_no_op_when_browser_launcher_is_none(self) -> None:
        lib = self._make_lib(browser_launcher=None)
        lib._machine_identifier = "abc"
        # Should not raise
        lib.launchContent("123")

    def test_no_op_when_server_url_not_configured(self) -> None:
        mock_launcher = MagicMock()
        lib = self._make_lib(mock_launcher, server_url="")
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

        mock_account_cls = MagicMock()
        mock_account_cls.return_value.get_resources.return_value = [
            {
                "clientIdentifier": "server123",
                "name": "Test Server",
                "owned": True,
                "connections": [
                    {"uri": "http://server:32400", "local": True, "relay": False, "protocol": "http"}
                ],
            }
        ]
        mock_account_cls.return_value.switch_user.return_value = None

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
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
