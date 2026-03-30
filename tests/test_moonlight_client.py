"""Tests for Task 002 — Moonlight Client (App Enumeration + Launch).

Covers:
  - list_apps: successful output with multiple apps
  - list_apps: empty output (no apps)
  - list_apps: host unpaired (non-zero exit code)
  - list_apps: timeout
  - list_apps: subprocess exception (e.g. command not found)
  - list_apps: custom moonlight_command
  - list_apps: stderr noise is ignored
  - MoonlightLauncher.launch: successful launch emits processStarted
  - MoonlightLauncher.launch: process finish emits processFinished with exit code and elapsed time
  - MoonlightLauncher.launch: failed to start emits processFinished(-1, 0)
  - MoonlightLauncher.launch: ignores launch while process already running
  - MoonlightLauncher.launch_gui: starts the correct command
  - MoonlightLauncher: command string splitting works correctly
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QProcess

from backend.moonlight_client import MoonlightLauncher, list_apps
from tests.local_overrides import get_override

LOCAL_IP = get_override("moonlight_local_ip", "192.168.50.5")
ALT_IP = get_override("moonlight_alt_ip", "10.0.0.1")


# ---------------------------------------------------------------------------
# TestListApps
# ---------------------------------------------------------------------------


class TestListApps:
    def _make_result(
        self,
        stdout: bytes = b"",
        returncode: int = 0,
    ) -> subprocess.CompletedProcess:
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.stdout = stdout
        result.returncode = returncode
        return result

    def test_successful_output_multiple_apps(self) -> None:
        """list_apps returns a list of app names from stdout."""
        output = b"Cyberpunk 2077\nRed Dead Redemption 2\nThe Witcher 3\n"
        with patch("subprocess.run", return_value=self._make_result(stdout=output)):
            apps = list_apps(LOCAL_IP)

        assert apps == ["Cyberpunk 2077", "Red Dead Redemption 2", "The Witcher 3"]

    def test_empty_output_returns_empty_list(self) -> None:
        """list_apps returns [] when stdout is empty."""
        with patch("subprocess.run", return_value=self._make_result(stdout=b"")):
            apps = list_apps(LOCAL_IP)

        assert apps == []

    def test_host_unpaired_nonzero_exit_returns_empty_list(self) -> None:
        """list_apps returns [] when the command exits with a non-zero code."""
        output = b"Computer DESKTOP-ABC has not been paired.\n"
        with patch(
            "subprocess.run",
            return_value=self._make_result(stdout=output, returncode=1),
        ):
            apps = list_apps(LOCAL_IP)

        assert apps == []

    def test_timeout_returns_empty_list(self) -> None:
        """list_apps returns [] when the subprocess times out."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=10)):
            apps = list_apps(LOCAL_IP)

        assert apps == []

    def test_subprocess_exception_returns_empty_list(self) -> None:
        """list_apps returns [] when subprocess raises an exception (e.g. command not found)."""
        with patch("subprocess.run", side_effect=FileNotFoundError("flatpak not found")):
            apps = list_apps(LOCAL_IP)

        assert apps == []

    def test_custom_moonlight_command(self) -> None:
        """list_apps uses the custom moonlight_command when provided."""
        output = b"Desktop\n"
        with patch("subprocess.run", return_value=self._make_result(stdout=output)) as mock_run:
            apps = list_apps(LOCAL_IP, moonlight_command="/usr/bin/moonlight")

        assert apps == ["Desktop"]
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/usr/bin/moonlight"
        assert "list" in call_args
        assert LOCAL_IP in call_args

    def test_stderr_noise_is_ignored(self) -> None:
        """list_apps passes stderr=DEVNULL so SDL/Qt noise is discarded."""
        output = b"Game A\nGame B\n"
        with patch("subprocess.run", return_value=self._make_result(stdout=output)) as mock_run:
            apps = list_apps(LOCAL_IP)

        assert apps == ["Game A", "Game B"]
        _, kwargs = mock_run.call_args
        assert kwargs.get("stderr") == subprocess.DEVNULL

    def test_default_command_is_flatpak(self) -> None:
        """list_apps uses the Flatpak command by default."""
        with patch("subprocess.run", return_value=self._make_result()) as mock_run:
            list_apps(LOCAL_IP)

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "flatpak"
        assert "com.moonlight_stream.Moonlight" in call_args

    def test_whitespace_lines_are_filtered(self) -> None:
        """list_apps strips and filters blank lines from stdout."""
        output = b"\nGame A\n  \nGame B\n\n"
        with patch("subprocess.run", return_value=self._make_result(stdout=output)):
            apps = list_apps(LOCAL_IP)

        assert apps == ["Game A", "Game B"]

    def test_command_includes_list_subcommand_and_host(self) -> None:
        """list_apps builds the command with 'list' and the host address."""
        with patch("subprocess.run", return_value=self._make_result()) as mock_run:
            list_apps(ALT_IP)

        call_args = mock_run.call_args[0][0]
        assert "list" in call_args
        assert ALT_IP in call_args

    def test_command_split_uses_shlex(self) -> None:
        """list_apps uses shlex.split to handle commands with spaces correctly."""
        custom_cmd = "flatpak run com.moonlight_stream.Moonlight"
        with patch("subprocess.run", return_value=self._make_result()) as mock_run:
            list_apps(LOCAL_IP, moonlight_command=custom_cmd)

        call_args = mock_run.call_args[0][0]
        # shlex.split should produce individual tokens, not one big string
        assert call_args == ["flatpak", "run", "com.moonlight_stream.Moonlight", "list", LOCAL_IP]


# ---------------------------------------------------------------------------
# TestMoonlightLauncher
# ---------------------------------------------------------------------------


class TestMoonlightLauncher:
    def test_successful_launch_emits_process_started(self) -> None:
        """launch() emits processStarted when the process starts."""
        launcher = MoonlightLauncher()

        received: list[bool] = []
        launcher.processStarted.connect(lambda: received.append(True))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            launcher._on_started()

        assert received == [True]

    def test_process_finish_emits_process_finished_with_exit_code_and_elapsed(self) -> None:
        """_on_finished emits processFinished with exit code and elapsed time."""
        launcher = MoonlightLauncher()

        received: list[tuple] = []
        launcher.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            launcher._on_finished(0, QProcess.ExitStatus.NormalExit)

        assert len(received) == 1
        exit_code, elapsed = received[0]
        assert exit_code == 0
        assert isinstance(elapsed, int)
        assert elapsed >= 0

    def test_failed_to_start_emits_process_finished_minus_one(self) -> None:
        """_on_error_occurred(FailedToStart) emits processFinished(-1, 0) and clears _process."""
        launcher = MoonlightLauncher()

        received: list[tuple] = []
        launcher.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            assert launcher._process is not None
            launcher._on_error_occurred(QProcess.ProcessError.FailedToStart)

        assert received == [(-1, 0)]
        assert launcher._process is None

    def test_non_failed_to_start_error_is_ignored(self) -> None:
        """_on_error_occurred for non-FailedToStart errors does not emit processFinished."""
        launcher = MoonlightLauncher()

        received: list[tuple] = []
        launcher.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            launcher._on_error_occurred(QProcess.ProcessError.Crashed)

        assert received == []

    def test_ignores_launch_while_process_already_running(self) -> None:
        """launch() is a no-op when a process is already running."""
        launcher = MoonlightLauncher()

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running
        launcher._process = mock_process

        # Should not create a new process
        launcher.launch(LOCAL_IP, "Cyberpunk 2077")

        # _process should still be the original mock
        assert launcher._process is mock_process

    def test_launch_gui_starts_correct_command(self) -> None:
        """launch_gui starts Moonlight with no subcommand args."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start") as mock_start, \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch_gui()

        mock_start.assert_called_once()
        program, args = mock_start.call_args[0]
        assert program == "flatpak"
        # No "stream" or "list" subcommand — just the base command args
        assert "stream" not in args
        assert "list" not in args

    def test_launch_gui_with_custom_command(self) -> None:
        """launch_gui uses the custom moonlight_command when provided."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start") as mock_start, \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch_gui(moonlight_command="/usr/bin/moonlight")

        mock_start.assert_called_once()
        program, args = mock_start.call_args[0]
        assert program == "/usr/bin/moonlight"
        assert args == []

    def test_launch_gui_ignores_when_process_already_running(self) -> None:
        """launch_gui is a no-op when a process is already running."""
        launcher = MoonlightLauncher()

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running
        launcher._process = mock_process

        launcher.launch_gui()

        assert launcher._process is mock_process

    def test_command_string_splitting_with_spaces(self) -> None:
        """launch() correctly splits a moonlight_command string with spaces."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start") as mock_start, \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(
                LOCAL_IP,
                "My Game",
                moonlight_command="flatpak run com.moonlight_stream.Moonlight",
            )

        mock_start.assert_called_once()
        program, args = mock_start.call_args[0]
        assert program == "flatpak"
        assert args == ["run", "com.moonlight_stream.Moonlight", "stream", LOCAL_IP, "My Game"]

    def test_launch_builds_stream_command(self) -> None:
        """launch() builds the correct stream command with host and app name."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start") as mock_start, \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(ALT_IP, "Desktop")

        mock_start.assert_called_once()
        program, args = mock_start.call_args[0]
        assert "stream" in args
        assert ALT_IP in args
        assert "Desktop" in args

    def test_process_cleared_after_finish(self) -> None:
        """_process is set to None after the process finishes."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            assert launcher._process is not None
            launcher._on_finished(0, QProcess.ExitStatus.NormalExit)

        assert launcher._process is None

    def test_on_started_emits_process_started(self) -> None:
        """_on_started emits processStarted signal."""
        launcher = MoonlightLauncher()

        received: list[bool] = []
        launcher.processStarted.connect(lambda: received.append(True))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(LOCAL_IP, "Cyberpunk 2077")
            launcher._on_started()

        assert received == [True]

    def test_launch_returns_none(self) -> None:
        """launch() returns None — it is a void async operation."""
        launcher = MoonlightLauncher()

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            result = launcher.launch(LOCAL_IP, "Cyberpunk 2077")

        assert result is None
