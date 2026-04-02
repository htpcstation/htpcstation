"""Tests for MpvLauncher (Task 001 — MPV Player backend).

Covers:
  - launch() starts QProcess with correct program and args
  - launch() while already running is a no-op
  - kill() terminates the process
  - is_running() returns correct state
  - _ensure_input_conf() creates the file when absent
  - _ensure_input_conf() overwrites when version header is outdated
  - _ensure_input_conf() does not overwrite when version is current
  - _build_args() includes new hardware acceleration and IPC args
  - _build_live_tv_args() includes new hardware acceleration and IPC args
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
        assert any(a.startswith("--hwdec=vaapi") for a in args)  # vaapi or vaapi-copy
        assert "--vo=gpu" in args
        assert any(a.startswith("--gpu-context=") for a in args)  # x11 or wayland
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

    def test_overwrites_outdated_version(self, tmp_path: Path) -> None:
        """_ensure_input_conf() overwrites an existing file with an outdated version header."""
        from backend.mpv_launcher import MpvLauncher, _INPUT_CONF_VERSION
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        input_conf_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a file with an old version header (v1)
        old_content = "# HTPC Station MPV input config v1\nq quit\n"
        input_conf_path.write_text(old_content, encoding="utf-8")

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            MpvLauncher()

        # File should have been overwritten with the current version
        content = input_conf_path.read_text(encoding="utf-8")
        assert f"v{_INPUT_CONF_VERSION}" in content
        assert content != old_content

    def test_does_not_overwrite_current_version(self, tmp_path: Path) -> None:
        """_ensure_input_conf() does not overwrite a file with the current version header."""
        from backend.mpv_launcher import MpvLauncher, _INPUT_CONF_VERSION
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        input_conf_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a file with the current version header but custom content
        current_content = f"# HTPC Station MPV input config v{_INPUT_CONF_VERSION}\nq quit\n"
        input_conf_path.write_text(current_content, encoding="utf-8")

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            MpvLauncher()

        # File should still contain the custom content (not overwritten)
        assert input_conf_path.read_text(encoding="utf-8") == current_content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """_ensure_input_conf() creates parent directories as needed."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "deep" / "nested" / "mpv" / "input.conf"
        assert not input_conf_path.parent.exists()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        assert input_conf_path.exists()


# ---------------------------------------------------------------------------
# _build_args() — new hardware acceleration and IPC args
# ---------------------------------------------------------------------------


class TestBuildArgs:
    def test_build_args_includes_hwdec_codecs_all(self, tmp_path: Path) -> None:
        """_build_args() includes --hwdec-codecs=all."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_args("http://server/file.mkv", "")
        assert "--hwdec-codecs=all" in args

    def test_build_args_includes_gpu_api_opengl(self, tmp_path: Path) -> None:
        """_build_args() includes --gpu-api=opengl."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_args("http://server/file.mkv", "")
        assert "--gpu-api=opengl" in args

    def test_build_args_includes_vd_lavc_dr(self, tmp_path: Path) -> None:
        """_build_args() includes --vd-lavc-dr=yes."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_args("http://server/file.mkv", "")
        assert "--vd-lavc-dr=yes" in args

    def test_build_args_includes_osc_no(self, tmp_path: Path) -> None:
        """_build_args() includes --osc=no."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_args("http://server/file.mkv", "")
        assert "--osc=no" in args

    def test_build_args_includes_ipc_server(self, tmp_path: Path) -> None:
        """_build_args() includes --input-ipc-server with the correct socket path."""
        from backend.mpv_launcher import MpvLauncher, MPV_IPC_SOCKET
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_args("http://server/file.mkv", "")
        assert f"--input-ipc-server={MPV_IPC_SOCKET}" in args


# ---------------------------------------------------------------------------
# _build_live_tv_args() — new hardware acceleration and IPC args
# ---------------------------------------------------------------------------


class TestBuildLiveTvArgs:
    def test_build_live_tv_args_includes_hwdec_codecs_all(self, tmp_path: Path) -> None:
        """_build_live_tv_args() includes --hwdec-codecs=all."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_live_tv_args("http://server/stream")
        assert "--hwdec-codecs=all" in args

    def test_build_live_tv_args_includes_gpu_api_opengl(self, tmp_path: Path) -> None:
        """_build_live_tv_args() includes --gpu-api=opengl."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_live_tv_args("http://server/stream")
        assert "--gpu-api=opengl" in args

    def test_build_live_tv_args_includes_vd_lavc_dr(self, tmp_path: Path) -> None:
        """_build_live_tv_args() includes --vd-lavc-dr=yes."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_live_tv_args("http://server/stream")
        assert "--vd-lavc-dr=yes" in args

    def test_build_live_tv_args_includes_osc_no(self, tmp_path: Path) -> None:
        """_build_live_tv_args() includes --osc=no."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_live_tv_args("http://server/stream")
        assert "--osc=no" in args

    def test_build_live_tv_args_includes_ipc_server(self, tmp_path: Path) -> None:
        """_build_live_tv_args() includes --input-ipc-server with the correct socket path."""
        from backend.mpv_launcher import MpvLauncher, MPV_IPC_SOCKET
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()

        args = launcher._build_live_tv_args("http://server/stream")
        assert f"--input-ipc-server={MPV_IPC_SOCKET}" in args
