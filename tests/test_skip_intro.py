"""Tests for skip-intro feature (Task 001 — Auto Skip Intro).

Covers:
  - playWithMpv worker calls get_metadata with include_markers=True
  - _mpvLaunchReady emits 6 args when intro marker present (correct intro_end_ms)
  - _mpvLaunchReady emits intro_end_ms=0 when no intro marker
  - markersReady emitted with correct intro_end_ms from _on_mpv_launch_ready
  - markersReady emitted with 0 when no marker
  - seekMpv calls player.seek with correct seconds value (ms / 1000.0, "absolute")
  - seekMpv is a no-op when _player is None
  - Config.auto_skip_intro defaults to False
  - Config.set_auto_skip_intro(True) + save() + reload → True
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.plex_library import PlexLibrary
from backend.config import Config


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FAKE_SERVER_RESOURCES = [
    {
        "clientIdentifier": "server123",
        "name": "Test Server",
        "owned": True,
        "provides": "server",
        "connections": [
            {
                "uri": "http://server:32400",
                "local": True,
                "relay": False,
                "protocol": "http",
            }
        ],
    }
]


def _make_plex_account_mock():
    """Return a MagicMock PlexAccount class whose instances return fake resources."""
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


def _make_lib():
    """Create a PlexLibrary instance with mocked dependencies."""
    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        config.plex_transcode_mode = "direct"
        config.hw_decode_codecs = ["h264"]
        lib = PlexLibrary(config)
    return lib


def _make_config(tmp_path: Path) -> Config:
    """Return a Config instance with CONFIG_FILE and CONFIG_DIR redirected to tmp_path."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


# ---------------------------------------------------------------------------
# playWithMpv worker calls get_metadata with include_markers=True
# ---------------------------------------------------------------------------


class TestPlayWithMpvCallsGetMetadataWithMarkers:
    def test_get_metadata_called_with_include_markers_true(self) -> None:
        """playWithMpv worker must call get_metadata(rating_key, include_markers=True)."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/1/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Test Movie",
            "grandparentTitle": "",
            "duration": 5400000,
            "Media": [{"Part": [{"id": 1}]}],
            "Marker": [],
        }
        mock_client.get_transient_token.return_value = None
        mock_client.create_play_queue.return_value = {"MediaContainer": {"Metadata": []}}
        lib._client = mock_client
        lib._machine_identifier = ""

        lib.playWithMpv("42", 0)
        lib._executor.shutdown(wait=True)

        mock_client.get_metadata.assert_called_once_with("42", include_markers=True)


# ---------------------------------------------------------------------------
# _mpvLaunchReady emits 6 args when intro marker present
# ---------------------------------------------------------------------------


class TestMpvLaunchReadyWithIntroMarker:
    def test_emits_correct_intro_end_ms_when_marker_present(self) -> None:
        """_mpvLaunchReady must carry intro_end_ms from the intro marker."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/1/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Episode 1",
            "grandparentTitle": "My Show",
            "duration": 2700000,
            "Media": [{"Part": [{"id": 7}]}],
            "Marker": [
                {"type": "intro", "startTimeOffset": 5000, "endTimeOffset": 90000},
            ],
        }
        mock_client.get_transient_token.return_value = None
        mock_client.create_play_queue.return_value = {"MediaContainer": {"Metadata": []}}
        lib._client = mock_client
        lib._machine_identifier = ""

        received: list = []

        def _capture(url, title, start_ms, duration_ms, part_id, intro_end_ms):
            received.append((url, title, start_ms, duration_ms, part_id, intro_end_ms))

        lib._mpvLaunchReady.connect(_capture)

        lib.playWithMpv("99", 0)
        lib._executor.shutdown(wait=True)

        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        assert len(received) == 1
        _url, _title, _start_ms, _duration_ms, _part_id, intro_end_ms = received[0]
        assert intro_end_ms == 90000

    def test_emits_zero_intro_end_ms_when_no_marker(self) -> None:
        """_mpvLaunchReady must carry intro_end_ms=0 when no intro marker is present."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/2/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Movie Without Intro",
            "grandparentTitle": "",
            "duration": 7200000,
            "Media": [{"Part": [{"id": 3}]}],
            "Marker": [],
        }
        mock_client.get_transient_token.return_value = None
        mock_client.create_play_queue.return_value = {"MediaContainer": {"Metadata": []}}
        lib._client = mock_client
        lib._machine_identifier = ""

        received: list = []

        def _capture(url, title, start_ms, duration_ms, part_id, intro_end_ms):
            received.append((url, title, start_ms, duration_ms, part_id, intro_end_ms))

        lib._mpvLaunchReady.connect(_capture)

        lib.playWithMpv("55", 0)
        lib._executor.shutdown(wait=True)

        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        assert len(received) == 1
        _url, _title, _start_ms, _duration_ms, _part_id, intro_end_ms = received[0]
        assert intro_end_ms == 0

    def test_emits_zero_intro_end_ms_when_marker_list_absent(self) -> None:
        """_mpvLaunchReady must carry intro_end_ms=0 when Marker key is missing."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/3/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Old Movie",
            "grandparentTitle": "",
            "duration": 5400000,
            "Media": [{"Part": [{"id": 5}]}],
            # No "Marker" key at all
        }
        mock_client.get_transient_token.return_value = None
        mock_client.create_play_queue.return_value = {"MediaContainer": {"Metadata": []}}
        lib._client = mock_client
        lib._machine_identifier = ""

        received: list = []

        def _capture(url, title, start_ms, duration_ms, part_id, intro_end_ms):
            received.append((url, title, start_ms, duration_ms, part_id, intro_end_ms))

        lib._mpvLaunchReady.connect(_capture)

        lib.playWithMpv("77", 0)
        lib._executor.shutdown(wait=True)

        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        assert len(received) == 1
        _url, _title, _start_ms, _duration_ms, _part_id, intro_end_ms = received[0]
        assert intro_end_ms == 0


# ---------------------------------------------------------------------------
# markersReady emitted from _on_mpv_launch_ready
# ---------------------------------------------------------------------------


class TestMarkersReadySignal:
    def test_markers_ready_emitted_with_correct_intro_end_ms(self) -> None:
        """_on_mpv_launch_ready must emit markersReady(intro_end_ms) when intro present."""
        lib = _make_lib()
        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        received: list[int] = []
        lib.markersReady.connect(lambda ms: received.append(ms))

        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/1/0/file.mkv?X-Plex-Token=tok",
            "My Show — Episode 1",
            0,
            2700000,
            7,
            90000,
        )

        assert received == [90000]

    def test_markers_ready_emitted_with_zero_when_no_marker(self) -> None:
        """_on_mpv_launch_ready must emit markersReady(0) when no intro marker."""
        lib = _make_lib()
        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        received: list[int] = []
        lib.markersReady.connect(lambda ms: received.append(ms))

        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/2/0/file.mkv?X-Plex-Token=tok",
            "Movie Without Intro",
            0,
            7200000,
            3,
            0,
        )

        assert received == [0]

    def test_markers_ready_not_emitted_when_url_empty(self) -> None:
        """_on_mpv_launch_ready must NOT emit markersReady when URL is empty (no launch)."""
        lib = _make_lib()
        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        received: list[int] = []
        lib.markersReady.connect(lambda ms: received.append(ms))

        lib._on_mpv_launch_ready("", "", 0, 0, 0, 90000)

        assert received == []


# ---------------------------------------------------------------------------
# seekMpv slot
# ---------------------------------------------------------------------------


class TestSeekMpv:
    def test_seek_calls_player_seek_with_correct_seconds(self) -> None:
        """seekMpv(ms) must call player.seek(ms / 1000.0, 'absolute')."""
        lib = _make_lib()
        mock_player = MagicMock()
        lib._mpv_launcher._player = mock_player

        lib.seekMpv(90000)

        mock_player.seek.assert_called_once_with(90.0, "absolute")

    def test_seek_converts_ms_to_float_seconds(self) -> None:
        """seekMpv must pass a float (ms / 1000.0) to player.seek."""
        lib = _make_lib()
        mock_player = MagicMock()
        lib._mpv_launcher._player = mock_player

        lib.seekMpv(1500)

        mock_player.seek.assert_called_once_with(1.5, "absolute")

    def test_seek_noop_when_player_is_none(self) -> None:
        """seekMpv must be a no-op when _player is None."""
        lib = _make_lib()
        lib._mpv_launcher._player = None

        # Should not raise
        lib.seekMpv(90000)

    def test_seek_swallows_player_exception(self) -> None:
        """seekMpv must swallow exceptions raised by player.seek."""
        lib = _make_lib()
        mock_player = MagicMock()
        mock_player.seek.side_effect = RuntimeError("mpv error")
        lib._mpv_launcher._player = mock_player

        # Should not raise
        lib.seekMpv(90000)


# ---------------------------------------------------------------------------
# Config.auto_skip_intro
# ---------------------------------------------------------------------------


class TestConfigAutoSkipIntro:
    def test_defaults_to_false(self, tmp_path: Path) -> None:
        """Config.auto_skip_intro must default to False on a fresh config."""
        config = _make_config(tmp_path)
        assert config.auto_skip_intro is False

    def test_set_auto_skip_intro_true_persists(self, tmp_path: Path) -> None:
        """set_auto_skip_intro(True) + save() must persist True to disk."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_auto_skip_intro(True)

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["auto_skip_intro"] is True

    def test_set_auto_skip_intro_true_then_reload(self, tmp_path: Path) -> None:
        """set_auto_skip_intro(True) + save() + reload → auto_skip_intro is True."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_auto_skip_intro(True)

        # Reload from the same file
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()

        assert config2.auto_skip_intro is True

    def test_set_auto_skip_intro_false_persists(self, tmp_path: Path) -> None:
        """set_auto_skip_intro(False) must persist False to disk."""
        config_file = tmp_path / "config.json"
        # Start with True already saved
        config_file.write_text(
            json.dumps({"plex": {"auto_skip_intro": True}}), encoding="utf-8"
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            assert config.auto_skip_intro is True
            config.set_auto_skip_intro(False)

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["auto_skip_intro"] is False

    def test_set_auto_skip_intro_coerces_to_bool(self, tmp_path: Path) -> None:
        """set_auto_skip_intro must coerce the value to bool."""
        config = _make_config(tmp_path)
        # Truthy non-bool
        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config.set_auto_skip_intro(1)  # type: ignore[arg-type]
        assert config.auto_skip_intro is True
        assert isinstance(config.auto_skip_intro, bool)
