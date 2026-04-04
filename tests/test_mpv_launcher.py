"""Tests for LibMpvPlayer (Task 001 — libmpv migration: core player + lifecycle).

Covers:
  - Player creation after set_wid()
  - launch() before set_wid() logs error and does not raise
  - launch() calls player.play() with the URL
  - launch() sets title on the player
  - launch() sets start position from start_ms
  - launch() is a no-op when already running
  - kill() calls player.stop()
  - kill() with no player does not raise
  - launch_live_tv() sets reconnect stream options
  - launch_live_tv() sets larger demuxer-max-bytes
  - _hwdec_mode() returns vaapi-copy on Wayland, vaapi on Xorg
  - _gpu_context() returns wayland on Wayland, x11 on Xorg
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_player(tmp_path: Path, mock_mpv_cls=None):
    """Create a LibMpvPlayer with a patched input.conf path.

    If mock_mpv_cls is provided it is used as the mpv.MPV replacement.
    Returns (player, mock_mpv_instance_or_None).
    """
    import backend.mpv_launcher as mpv_mod
    from backend.mpv_launcher import LibMpvPlayer

    input_conf_path = tmp_path / "mpv" / "input.conf"

    if mock_mpv_cls is not None:
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module:
            mock_mpv_module.MPV.return_value = mock_mpv_cls
            player = LibMpvPlayer()
        return player, mock_mpv_cls
    else:
        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            player = LibMpvPlayer()
        return player, None


def _make_mock_mpv_instance():
    """Return a MagicMock that looks like an mpv.MPV instance."""
    mock = MagicMock()
    # core_idle=True means idle (not playing); False means playing
    type(mock).core_idle = PropertyMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# TestLibMpvPlayerInit
# ---------------------------------------------------------------------------


class TestLibMpvPlayerInit:
    def test_creates_player_after_set_wid(self, tmp_path: Path) -> None:
        """set_wid() creates the internal _player instance."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module:
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            assert player._player is None
            player.set_wid(123)

        assert player._player is not None

    def test_launch_before_set_wid_logs_error(self, tmp_path: Path) -> None:
        """launch() without set_wid() logs an error and does not raise."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            player = LibMpvPlayer()

        # Should not raise; _player is None
        player.launch("http://example.com/stream.mkv")


# ---------------------------------------------------------------------------
# TestLibMpvPlayerLaunch
# ---------------------------------------------------------------------------


class TestLibMpvPlayerLaunch:
    def _make_running_player(self, tmp_path: Path):
        """Helper: create a LibMpvPlayer with set_wid() already called."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        return player, mock_instance

    def test_launch_calls_player_play(self, tmp_path: Path) -> None:
        """launch() calls _player.play() with the given URL."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv", "Title", 0)

        mock_instance.play.assert_called_once_with("http://server/file.mkv")

    def test_launch_sets_title(self, tmp_path: Path) -> None:
        """launch() sets player.title and player.force_media_title when title is non-empty."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv", "My Movie", 0)

        assert mock_instance.title == "My Movie"
        assert mock_instance.force_media_title == "My Movie"

    def test_launch_sets_start_position(self, tmp_path: Path) -> None:
        """launch() sets player.start to HH:MM:SS when start_ms > 0."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            # 60 seconds = 00:01:00
            player.launch("http://server/file.mkv", "", 60_000)

        assert mock_instance.start == "00:01:00"

    def test_launch_noop_when_running(self, tmp_path: Path) -> None:
        """launch() does nothing when is_running() returns True."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()
        # Simulate playing: core_idle=False
        type(mock_instance).core_idle = PropertyMock(return_value=False)

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv")

        mock_instance.play.assert_not_called()


# ---------------------------------------------------------------------------
# TestLibMpvPlayerKill
# ---------------------------------------------------------------------------


class TestLibMpvPlayerKill:
    def test_kill_calls_stop(self, tmp_path: Path) -> None:
        """kill() calls _player.stop() when player is initialised."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.kill()

        mock_instance.stop.assert_called_once()

    def test_kill_noop_when_no_player(self, tmp_path: Path) -> None:
        """kill() with _player=None does not raise."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            player = LibMpvPlayer()

        # _player is None — should not raise
        player.kill()


# ---------------------------------------------------------------------------
# TestLibMpvPlayerLiveTv
# ---------------------------------------------------------------------------


class TestLibMpvPlayerLiveTv:
    def test_live_tv_sets_reconnect_options(self, tmp_path: Path) -> None:
        """launch_live_tv() sets stream-lavf-o with reconnect options."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()
        set_items: dict = {}

        mock_instance.__setitem__.side_effect = lambda key, value: set_items.update({key: value})

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch_live_tv("http://hdhomerun/stream", "Channel 7")

        assert "stream-lavf-o" in set_items
        assert "reconnect=1" in set_items["stream-lavf-o"]
        assert "reconnect_streamed=1" in set_items["stream-lavf-o"]

    def test_live_tv_sets_larger_demuxer(self, tmp_path: Path) -> None:
        """launch_live_tv() sets demuxer-max-bytes to 128MiB."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        mock_instance = _make_mock_mpv_instance()
        set_items: dict = {}

        mock_instance.__setitem__.side_effect = lambda key, value: set_items.update({key: value})

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch_live_tv("http://hdhomerun/stream")

        assert set_items.get("demuxer-max-bytes") == "128MiB"


# ---------------------------------------------------------------------------
# TestHwdecAndGpuContext
# ---------------------------------------------------------------------------


class TestHwdecAndGpuContext:
    def test_wayland_hwdec(self, tmp_path: Path) -> None:
        """_hwdec_mode() returns 'vaapi-copy' on Wayland."""
        from backend.mpv_launcher import LibMpvPlayer

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}):
            assert LibMpvPlayer._hwdec_mode() == "vaapi-copy"

    def test_xorg_hwdec(self, tmp_path: Path) -> None:
        """_hwdec_mode() returns 'vaapi' on Xorg."""
        from backend.mpv_launcher import LibMpvPlayer

        env = {"XDG_SESSION_TYPE": "x11"}
        with patch.dict(os.environ, env, clear=False):
            # Ensure WAYLAND_DISPLAY is not set
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert LibMpvPlayer._hwdec_mode() == "vaapi"

    def test_wayland_gpu_context(self, tmp_path: Path) -> None:
        """_gpu_context() returns 'wayland' on Wayland."""
        from backend.mpv_launcher import LibMpvPlayer

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}):
            assert LibMpvPlayer._gpu_context() == "wayland"

    def test_xorg_gpu_context(self, tmp_path: Path) -> None:
        """_gpu_context() returns 'x11' on Xorg."""
        from backend.mpv_launcher import LibMpvPlayer

        env = {"XDG_SESSION_TYPE": "x11"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert LibMpvPlayer._gpu_context() == "x11"


# ---------------------------------------------------------------------------
# TestEnsureInputConf (kept from old tests — still relevant)
# ---------------------------------------------------------------------------


class TestEnsureInputConf:
    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        """_ensure_input_conf() creates the input.conf when it does not exist."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "mpv" / "input.conf"
        assert not input_conf_path.exists()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            LibMpvPlayer()

        assert input_conf_path.exists()
        content = input_conf_path.read_text(encoding="utf-8")
        assert "GAMEPAD_ACTION_RIGHT" in content
        assert "cycle pause" in content

    def test_overwrites_outdated_version(self, tmp_path: Path) -> None:
        """_ensure_input_conf() overwrites an existing file with an outdated version header."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer, _INPUT_CONF_VERSION

        input_conf_path = tmp_path / "mpv" / "input.conf"
        input_conf_path.parent.mkdir(parents=True, exist_ok=True)
        old_content = "# HTPC Station MPV input config v1\nq quit\n"
        input_conf_path.write_text(old_content, encoding="utf-8")

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            LibMpvPlayer()

        content = input_conf_path.read_text(encoding="utf-8")
        assert f"v{_INPUT_CONF_VERSION}" in content
        assert content != old_content

    def test_does_not_overwrite_current_version(self, tmp_path: Path) -> None:
        """_ensure_input_conf() does not overwrite a file with the current version header."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer, _INPUT_CONF_VERSION

        input_conf_path = tmp_path / "mpv" / "input.conf"
        input_conf_path.parent.mkdir(parents=True, exist_ok=True)
        current_content = f"# HTPC Station MPV input config v{_INPUT_CONF_VERSION}\nq quit\n"
        input_conf_path.write_text(current_content, encoding="utf-8")

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            LibMpvPlayer()

        assert input_conf_path.read_text(encoding="utf-8") == current_content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """_ensure_input_conf() creates parent directories as needed."""
        import backend.mpv_launcher as mpv_mod
        from backend.mpv_launcher import LibMpvPlayer

        input_conf_path = tmp_path / "deep" / "nested" / "mpv" / "input.conf"
        assert not input_conf_path.parent.exists()

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            LibMpvPlayer()

        assert input_conf_path.exists()
