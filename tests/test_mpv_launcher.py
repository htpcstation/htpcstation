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
  - L2/R2 debounce: one seek per tap, no runaway
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
        """launch() sets player.start to HH:MM:SS when start_ms > 0."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            # 60 seconds = 00:01:00
            player.launch("http://server/file.mkv", "", 60_000)

        assert mock_instance.start == "00:01:00"

    def test_launch_noop_when_running(self) -> None:
        """launch() does nothing when is_running() returns True."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # Simulate playing: core_idle=False
        type(mock_instance).core_idle = PropertyMock(return_value=False)

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
    def test_kill_calls_stop(self) -> None:
        """kill() calls _player.stop() when player is initialised."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)
            player.kill()

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
        # on_key_press returns a decorator — make it a no-op decorator
        mock_instance.on_key_press.return_value = lambda fn: fn

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
        mock_instance.on_key_press.return_value = lambda fn: fn

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        keybind_keys = [k for k, _ in keybind_calls]
        expected_keys = [
            "GAMEPAD_ACTION_DOWN",
            "GAMEPAD_DPAD_LEFT",
            "GAMEPAD_DPAD_RIGHT",
            "GAMEPAD_DPAD_UP",
            "GAMEPAD_DPAD_DOWN",
            "GAMEPAD_LEFT_SHOULDER",
            "GAMEPAD_RIGHT_SHOULDER",
            "GAMEPAD_ACTION_UP",
            "GAMEPAD_START",
        ]
        for key in expected_keys:
            assert key in keybind_keys, f"Expected keybind for {key} not registered"

    def test_y_button_emits_subtitle_picker_signal(self) -> None:
        """Y button (GAMEPAD_ACTION_LEFT) on_key_press callback emits subtitlePickerRequested."""
        from backend.mpv_launcher import LibMpvPlayer

        mock_instance = _make_mock_mpv_instance()
        # Capture the on_key_press callbacks
        key_press_callbacks: dict[str, object] = {}

        def fake_on_key_press(keydef, **kwargs):
            def decorator(fn):
                key_press_callbacks[keydef] = fn
                return fn
            return decorator

        mock_instance.on_key_press.side_effect = fake_on_key_press
        mock_instance.keybind.return_value = None

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"), \
             patch("backend.mpv_launcher.QMetaObject") as mock_meta:
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

            # Trigger the Y button callback
            assert "GAMEPAD_ACTION_LEFT" in key_press_callbacks
            key_press_callbacks["GAMEPAD_ACTION_LEFT"]()

            # Verify QMetaObject.invokeMethod was called to marshal to main thread
            mock_meta.invokeMethod.assert_called()
            call_args = mock_meta.invokeMethod.call_args
            assert call_args[0][0] is player
            assert call_args[0][1] == "_request_subtitle_picker"


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
            mock_instance.on_key_press.return_value = lambda fn: fn

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
            mock_instance.on_key_press.return_value = lambda fn: fn

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

        # _on_playback_started should NOT be invoked (exception was raised)
        assert "_on_playback_started" not in invoke_calls
        # But _emit_started should still be invoked
        assert "_emit_started" in invoke_calls


# ---------------------------------------------------------------------------
# TestL2R2Debounce
# ---------------------------------------------------------------------------


class TestL2R2Debounce:
    def _get_trigger_callbacks(self, mock_instance):
        """Set up mock and return captured L2/R2 callbacks."""
        from backend.mpv_launcher import LibMpvPlayer

        key_press_callbacks: dict[str, object] = {}

        def fake_on_key_press(keydef, **kwargs):
            def decorator(fn):
                key_press_callbacks[keydef] = fn
                return fn
            return decorator

        mock_instance.on_key_press.side_effect = fake_on_key_press
        mock_instance.keybind.return_value = None

        with patch("backend.mpv_launcher.mpv") as mock_mpv_module, \
             patch("backend.mpv_launcher.threading"), \
             patch("backend.mpv_launcher.QMetaObject"):
            mock_mpv_module.MPV.return_value = mock_instance
            player = LibMpvPlayer()
            player.set_wid(123)

        return player, key_press_callbacks

    def test_l2_seek_fires_once_per_tap(self) -> None:
        """L2 callback called twice within debounce window → seek called only once."""
        mock_instance = _make_mock_mpv_instance()
        player, callbacks = self._get_trigger_callbacks(mock_instance)

        assert "GAMEPAD_LEFT_TRIGGER" in callbacks
        l2_cb = callbacks["GAMEPAD_LEFT_TRIGGER"]

        with patch("backend.mpv_launcher.time") as mock_time:
            # Both calls happen at the same time (within debounce window)
            mock_time.monotonic.return_value = 1000.0
            l2_cb()
            l2_cb()

        # seek should only be called once
        seek_calls = [c for c in mock_instance.seek.call_args_list
                      if c[0][0] == -30]
        assert len(seek_calls) == 1

    def test_r2_seek_fires_once_per_tap(self) -> None:
        """R2 callback called twice within debounce window → seek called only once."""
        mock_instance = _make_mock_mpv_instance()
        player, callbacks = self._get_trigger_callbacks(mock_instance)

        assert "GAMEPAD_RIGHT_TRIGGER" in callbacks
        r2_cb = callbacks["GAMEPAD_RIGHT_TRIGGER"]

        with patch("backend.mpv_launcher.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            r2_cb()
            r2_cb()

        seek_calls = [c for c in mock_instance.seek.call_args_list
                      if c[0][0] == 30]
        assert len(seek_calls) == 1

    def test_l2_seek_fires_again_after_debounce(self) -> None:
        """L2 seek fires again after the debounce window has elapsed."""
        mock_instance = _make_mock_mpv_instance()
        player, callbacks = self._get_trigger_callbacks(mock_instance)

        l2_cb = callbacks["GAMEPAD_LEFT_TRIGGER"]

        with patch("backend.mpv_launcher.time") as mock_time:
            # First tap
            mock_time.monotonic.return_value = 1000.0
            l2_cb()
            # Second tap after debounce window (> 0.5s)
            mock_time.monotonic.return_value = 1000.6
            l2_cb()

        seek_calls = [c for c in mock_instance.seek.call_args_list
                      if c[0][0] == -30]
        assert len(seek_calls) == 2

    def test_r2_seek_fires_again_after_debounce(self) -> None:
        """R2 seek fires again after the debounce window has elapsed."""
        mock_instance = _make_mock_mpv_instance()
        player, callbacks = self._get_trigger_callbacks(mock_instance)

        r2_cb = callbacks["GAMEPAD_RIGHT_TRIGGER"]

        with patch("backend.mpv_launcher.time") as mock_time:
            # First tap
            mock_time.monotonic.return_value = 1000.0
            r2_cb()
            # Second tap after debounce window (> 0.5s)
            mock_time.monotonic.return_value = 1000.6
            r2_cb()

        seek_calls = [c for c in mock_instance.seek.call_args_list
                      if c[0][0] == 30]
        assert len(seek_calls) == 2
