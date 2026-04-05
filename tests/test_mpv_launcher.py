"""Tests for LibMpvPlayer (Tasks 001 & 002 — libmpv migration).

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
  - _setup_keybinds() registers keybinds programmatically
  - Y button emits subtitlePickerRequested signal
  - mpvPlaybackStarted emitted after wait_until_playing
  - pause=False set before play() to ensure playback starts in play state
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_mpv_instance():
    """Return a MagicMock that looks like an mpv.MPV instance."""
    mock = MagicMock()
    # core_idle=True means idle (not playing); False means playing
    type(mock).core_idle = PropertyMock(return_value=True)
    # filename=None means no file loaded (not playing)
    type(mock).filename = PropertyMock(return_value=None)
    return mock


def _make_player_with_mock(mock_mpv_instance=None):
    """Create a LibMpvPlayer with a mocked mpv module.

    Returns (player, mock_mpv_instance).
    """
    from backend.mpv_launcher import LibMpvPlayer

    if mock_mpv_instance is None:
        mock_mpv_instance = _make_mock_mpv_instance()

    with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
         patch("backend.mpv_launcher.threading"):
        mock_mpv_module.MPV.return_value = mock_mpv_instance
        player = LibMpvPlayer()
        player.set_wid(123)

    return player, mock_mpv_instance


# ---------------------------------------------------------------------------
# TestLibMpvPlayerInit
# ---------------------------------------------------------------------------


class TestLibMpvPlayerInit:
    def test_creates_player_after_set_wid(self) -> None:
        """set_wid() creates the internal _player instance."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            assert player._player is None
            player.set_wid(123)

        assert player._player is not None

    def test_launch_before_set_wid_logs_error(self) -> None:
        """launch() without set_wid() logs an error and does not raise."""
        from backend.mpv_launcher import LibMpvPlayer

        player = LibMpvPlayer()
        # Should not raise; _player is None
        player.launch("http://example.com/stream.mkv")

    def test_no_input_conf_written(self, tmp_path: Path) -> None:
        """set_wid() does not write any input.conf file to disk."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        # No input.conf should be written anywhere in tmp_path
        conf_files = list(tmp_path.rglob("input.conf"))
        assert conf_files == []


# ---------------------------------------------------------------------------
# TestLibMpvPlayerLaunch
# ---------------------------------------------------------------------------


class TestLibMpvPlayerLaunch:
    def test_launch_calls_player_play(self) -> None:
        """launch() calls _player.play() with the given URL."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv", "Title", 0)

        mock_instance.play.assert_called_once_with("http://server/file.mkv")

    def test_launch_sets_title(self) -> None:
        """launch() sets player.title and player.force_media_title when title is non-empty."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv", "My Movie", 0)

        assert mock_instance.title == "My Movie"
        assert mock_instance.force_media_title == "My Movie"

    def test_launch_sets_start_position(self) -> None:
        """launch() sets player.start to HH:MM:SS for resume, 'none' for fresh play."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        start_values: list[str] = []

        def _capture_play(url):
            start_values.append(mock_instance.start)

        mock_instance.play.side_effect = _capture_play

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            # Resume play — start should be set to HH:MM:SS
            player.launch("http://server/file.mkv", "", 60_000)
            assert start_values == ["00:01:00"]
            start_values.clear()
            # Fresh play — start should be reset to "none"
            type(mock_instance).filename = PropertyMock(return_value=None)
            player.launch("http://server/file.mkv", "", 0)
            assert start_values == ["none"]

    def test_launch_sets_pause_false_before_play(self) -> None:
        """launch() sets player.pause = False before calling play() to prevent paused start."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        pause_at_play: list[bool] = []

        def _capture_play(url):
            pause_at_play.append(mock_instance.pause)

        mock_instance.play.side_effect = _capture_play

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch("http://server/file.mkv", "", 0)

        assert pause_at_play == [False]

    def test_launch_noop_when_running(self) -> None:
        """launch() does nothing when is_running() returns True."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # Simulate playing: filename is set (non-None/non-empty)
        type(mock_instance).filename = PropertyMock(return_value="file.mkv")

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
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
    def test_kill_sets_cancel_flag_and_dispatches_stop(self) -> None:
        """kill() sets _cancel_requested and dispatches player.stop() off-thread."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        started_targets: list = []

        class FakeThread:
            def __init__(self, target=None, daemon=None):
                started_targets.append(target)
            def start(self):
                # Actually call the target so stop() is invoked
                started_targets[-1]()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading") as mock_threading:
            mock_threading.Thread.side_effect = FakeThread
            mock_threading.Event.return_value = __import__("threading").Event()
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.kill()

        assert player._cancel_requested.is_set()
        mock_instance.stop.assert_called_once()

    def test_kill_noop_when_no_player(self) -> None:
        """kill() with _player=None does not raise."""
        from backend.mpv_launcher import LibMpvPlayer

        player = LibMpvPlayer()
        # _player is None — should not raise
        player.kill()


# ---------------------------------------------------------------------------
# TestLibMpvPlayerLiveTv
# ---------------------------------------------------------------------------


class TestLibMpvPlayerLiveTv:
    def test_live_tv_sets_reconnect_options(self) -> None:
        """launch_live_tv() sets stream-lavf-o with reconnect options."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        set_items: dict = {}

        mock_instance.__setitem__.side_effect = lambda key, value: set_items.update({key: value})

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.launch_live_tv("http://hdhomerun/stream", "Channel 7")

        assert "stream-lavf-o" in set_items
        assert "reconnect=1" in set_items["stream-lavf-o"]
        assert "reconnect_streamed=1" in set_items["stream-lavf-o"]

    def test_live_tv_sets_larger_demuxer(self) -> None:
        """launch_live_tv() sets demuxer-max-bytes to 128MiB."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        set_items: dict = {}

        mock_instance.__setitem__.side_effect = lambda key, value: set_items.update({key: value})

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
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
    def test_wayland_hwdec(self) -> None:
        """_hwdec_mode() returns 'vaapi-copy' on Wayland."""
        from backend.mpv_launcher import LibMpvPlayer

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}):
            assert LibMpvPlayer._hwdec_mode() == "vaapi-copy"

    def test_xorg_hwdec(self) -> None:
        """_hwdec_mode() returns 'vaapi' on Xorg."""
        from backend.mpv_launcher import LibMpvPlayer

        env = {"XDG_SESSION_TYPE": "x11"}
        with patch.dict(os.environ, env, clear=False):
            # Ensure WAYLAND_DISPLAY is not set
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert LibMpvPlayer._hwdec_mode() == "vaapi"

    def test_wayland_gpu_context(self) -> None:
        """_gpu_context() returns 'wayland' on Wayland."""
        from backend.mpv_launcher import LibMpvPlayer

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}):
            assert LibMpvPlayer._gpu_context() == "wayland"

    def test_xorg_gpu_context(self) -> None:
        """_gpu_context() returns 'x11' on Xorg."""
        from backend.mpv_launcher import LibMpvPlayer

        env = {"XDG_SESSION_TYPE": "x11"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert LibMpvPlayer._gpu_context() == "x11"


# ---------------------------------------------------------------------------
# TestKeybinds
# ---------------------------------------------------------------------------


class TestKeybinds:
    def test_setup_keybinds_called_after_set_wid(self) -> None:
        """set_wid() calls _setup_keybinds() which registers GAMEPAD_ACTION_DOWN."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # Track keybind calls
        keybind_calls: list[tuple] = []
        mock_instance.keybind.side_effect = lambda key, cmd: keybind_calls.append((key, cmd))

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        # Verify GAMEPAD_ACTION_DOWN → cycle pause was registered
        assert ("GAMEPAD_ACTION_DOWN", "cycle pause") in keybind_calls

    def test_setup_keybinds_registers_all_expected_binds(self) -> None:
        """_setup_keybinds() registers all expected gamepad keybinds."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        keybind_calls: list[tuple] = []
        mock_instance.keybind.side_effect = lambda key, cmd: keybind_calls.append((key, cmd))

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        keybind_keys = {k: cmd for k, cmd in keybind_calls}
        expected = {
            "GAMEPAD_ACTION_DOWN":    "cycle pause",
            "GAMEPAD_DPAD_LEFT":      "seek -10",
            "GAMEPAD_DPAD_RIGHT":     "seek 10",
            "GAMEPAD_DPAD_UP":        "add volume 5",
            "GAMEPAD_DPAD_DOWN":      "add volume -5",
            "GAMEPAD_LEFT_SHOULDER":  "cycle audio",
            "GAMEPAD_RIGHT_SHOULDER": "show-text ${track-list} 3000",
            "GAMEPAD_ACTION_LEFT":    "show-progress",
            "GAMEPAD_ACTION_UP":      "osd-msg cycle sub",
            "GAMEPAD_START":          "stop",
        }
        for key, cmd in expected.items():
            assert keybind_keys.get(key) == cmd, f"Keybind {key!r} expected {cmd!r}, got {keybind_keys.get(key)!r}"


# ---------------------------------------------------------------------------
# TestLoadingOverlay
# ---------------------------------------------------------------------------


class TestLoadingOverlay:
    def test_mpv_playback_started_emitted_after_wait_until_playing(self) -> None:
        """mpvPlaybackStarted is emitted after wait_until_playing() completes."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # wait_until_playing completes immediately (no-op)
        mock_instance.wait_until_playing.return_value = None

        emitted_signals: list[str] = []

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.QMetaObject") as mock_meta:
            mock_mpv_module.MPV.return_value = mock_instance

            player = LibMpvPlayer()
            player.set_wid(123)

            # Capture invokeMethod calls
            invoke_calls: list[str] = []
            mock_meta.invokeMethod.side_effect = lambda obj, method, *args, **kwargs: invoke_calls.append(method)

            # Simulate the _wait_and_signal thread running synchronously
            import threading as real_threading

            threads_started: list = []

            def fake_thread(target=None, daemon=None):
                t = MagicMock()
                t.start.side_effect = lambda: target()
                threads_started.append(t)
                return t

            with patch("backend.mpv_launcher.threading") as mock_threading:
                mock_threading.Thread.side_effect = fake_thread
                player.launch("http://example.com/stream.mkv")

        # Both _on_playback_started and _emit_started should be invoked
        assert "_on_playback_started" in invoke_calls
        assert "_emit_started" in invoke_calls

    def test_mpv_playback_started_not_emitted_on_timeout(self) -> None:
        """mpvPlaybackStarted is NOT emitted if wait_until_playing() raises (timeout)."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # Simulate timeout
        mock_instance.wait_until_playing.side_effect = Exception("timeout")

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.QMetaObject") as mock_meta:
            mock_mpv_module.MPV.return_value = mock_instance

            player = LibMpvPlayer()
            player.set_wid(123)

            invoke_calls: list[str] = []
            mock_meta.invokeMethod.side_effect = lambda obj, method, *args, **kwargs: invoke_calls.append(method)

            def fake_thread(target=None, daemon=None):
                t = MagicMock()
                t.start.side_effect = lambda: target()
                return t

            with patch("backend.mpv_launcher.threading") as mock_threading:
                mock_threading.Thread.side_effect = fake_thread
                player.launch("http://example.com/stream.mkv")

        # Neither signal should fire — stop/quit before playing means no started events
        assert "_on_playback_started" not in invoke_calls
        assert "_emit_started" not in invoke_calls

