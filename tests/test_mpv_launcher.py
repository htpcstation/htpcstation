"""Tests for MpvLauncher (Task 001 — MPV Player backend).

Covers:
  - launch() starts QProcess with correct program and args
  - launch() while already running is a no-op
  - kill() terminates the process
  - is_running() returns correct state
  - _ensure_input_conf() creates the file when absent
  - _ensure_input_conf() does not overwrite when present
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_launcher(tmp_path: Path):
    """Create an MpvLauncher with a patched input.conf path."""
    from backend.mpv_launcher import MpvLauncher
    import backend.mpv_launcher as mpv_mod

    input_conf_path = tmp_path / "mpv" / "input.conf"
    with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
        launcher = MpvLauncher()
    return launcher, input_conf_path


# ---------------------------------------------------------------------------
# launch() — starts QProcess with correct program and args
# ---------------------------------------------------------------------------


class TestMpvLauncherLaunch:
    def test_launch_starts_qprocess_with_mpv(self, tmp_path: Path) -> None:
        """launch() starts /usr/bin/mpv with the expected arguments."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server:32400/library/parts/123/0/file.mkv?X-Plex-Token=tok")

        mock_process.start.assert_called_once()
        program, args = mock_process.start.call_args[0]
        assert program == "/usr/bin/mpv"
        assert "--fullscreen" in args
        assert "--no-terminal" in args
        assert "--hwdec=vaapi" in args
        assert "--vo=gpu" in args
        assert "--gpu-context=x11" in args
        assert "--cache=yes" in args
        assert "--demuxer-max-bytes=50MiB" in args
        assert any("X-Plex-Client-Identifier:htpcstation" in a for a in args)
        assert "http://server:32400/library/parts/123/0/file.mkv?X-Plex-Token=tok" in args

    def test_launch_includes_title_args_when_title_given(self, tmp_path: Path) -> None:
        """launch() includes --title and --force-media-title when title is provided."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv", title="My Movie")

        _, args = mock_process.start.call_args[0]
        assert "--title=My Movie" in args
        assert "--force-media-title=My Movie" in args

    def test_launch_omits_title_args_when_no_title(self, tmp_path: Path) -> None:
        """launch() omits --title and --force-media-title when title is empty."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv")

        _, args = mock_process.start.call_args[0]
        assert not any(a.startswith("--title=") for a in args)
        assert not any(a.startswith("--force-media-title=") for a in args)

    def test_launch_includes_start_arg_when_start_ms_positive(self, tmp_path: Path) -> None:
        """launch() includes --start=HH:MM:SS when start_ms > 0."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            # 90 minutes + 5 seconds = 5_405_000 ms
            launcher.launch("http://server/file.mkv", start_ms=5_405_000)

        _, args = mock_process.start.call_args[0]
        assert "--start=01:30:05" in args

    def test_launch_omits_start_arg_when_start_ms_zero(self, tmp_path: Path) -> None:
        """launch() omits --start when start_ms is 0."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv", start_ms=0)

        _, args = mock_process.start.call_args[0]
        assert not any(a.startswith("--start=") for a in args)

    def test_launch_includes_input_conf_arg(self, tmp_path: Path) -> None:
        """launch() includes --input-conf pointing to the configured path."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv")

        _, args = mock_process.start.call_args[0]
        assert any(f"--input-conf={input_conf_path}" in a for a in args)


# ---------------------------------------------------------------------------
# launch() — no-op when already running
# ---------------------------------------------------------------------------


class TestMpvLauncherNoOpWhenRunning:
    def test_second_launch_ignored_when_already_running(self, tmp_path: Path) -> None:
        """launch() while MPV is already running is a no-op."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        # First call: not running; after start, simulate running
        mock_process.state.side_effect = [
            QProcess.ProcessState.NotRunning,  # check before first launch
            QProcess.ProcessState.Running,     # check before second launch
        ]

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv")
            launcher.launch("http://server/other.mkv")

        # start() should only have been called once
        assert mock_process.start.call_count == 1


# ---------------------------------------------------------------------------
# kill()
# ---------------------------------------------------------------------------


class TestMpvLauncherKill:
    def test_kill_calls_process_kill(self, tmp_path: Path) -> None:
        """kill() calls QProcess.kill() when MPV is running."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.side_effect = [
            QProcess.ProcessState.NotRunning,  # before launch
            QProcess.ProcessState.Running,     # before kill
        ]

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch("http://server/file.mkv")
            launcher.kill()

        mock_process.kill.assert_called_once()

    def test_kill_noop_when_not_running(self, tmp_path: Path) -> None:
        """kill() does nothing when MPV is not running."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()
            # No process started — kill should be a no-op
            launcher.kill()  # should not raise


# ---------------------------------------------------------------------------
# is_running()
# ---------------------------------------------------------------------------


class TestMpvLauncherIsRunning:
    def test_is_running_false_initially(self, tmp_path: Path) -> None:
        """is_running() returns False before any launch."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        assert launcher.is_running() is False

    def test_is_running_true_when_process_running(self, tmp_path: Path) -> None:
        """is_running() returns True when the QProcess is in Running state."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            # Manually inject the mock process to simulate running state
            launcher._process = mock_process

        assert launcher.is_running() is True

    def test_is_running_false_when_process_not_running(self, tmp_path: Path) -> None:
        """is_running() returns False when the QProcess is in NotRunning state."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()
            launcher._process = mock_process

        assert launcher.is_running() is False


# ---------------------------------------------------------------------------
# _ensure_input_conf()
# ---------------------------------------------------------------------------


class TestEnsureInputConf:
    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        """_ensure_input_conf() creates the input.conf when it does not exist."""
        from backend.mpv_launcher import MpvLauncher, _INPUT_CONF_CONTENT
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        assert not input_conf_path.exists()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        assert input_conf_path.exists()
        content = input_conf_path.read_text(encoding="utf-8")
        assert "GAMEPAD_ACTION_A" in content
        assert "cycle pause" in content

    def test_does_not_overwrite_existing_file(self, tmp_path: Path) -> None:
        """_ensure_input_conf() does not overwrite an existing input.conf."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        input_conf_path.parent.mkdir(parents=True, exist_ok=True)
        custom_content = "# My custom config\nq quit\n"
        input_conf_path.write_text(custom_content, encoding="utf-8")

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        # File should still contain the custom content
        assert input_conf_path.read_text(encoding="utf-8") == custom_content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """_ensure_input_conf() creates parent directories as needed."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "deep" / "nested" / "mpv" / "input.conf"
        assert not input_conf_path.parent.exists()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        assert input_conf_path.exists()
