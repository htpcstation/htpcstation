"""Tests for playWithMpv transcode decision logic (Task 003).

Covers:
  - Direct mode: uses get_stream_url
  - Fixed resolution modes (480p/720p/1080p): uses get_transcode_url
  - Auto mode with hw-decodable codec: uses get_stream_url
  - Auto mode with non-hw-decodable codec: uses get_transcode_url at 1080p
  - Auto mode with empty/unknown codec: uses get_transcode_url at 1080p
  - HW codec detection triggered on first playback when cache is empty
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.config import Config


def _make_lib(
    transcode_mode: str = "auto",
    hw_decode_codecs: list[str] | None = None,
):
    """Return a PlexLibrary with mocked dependencies and explicit config values."""
    from backend.plex_library import PlexLibrary

    tmp_dir = Path(tempfile.mkdtemp())
    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount") as mock_pa_cls, \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"), \
         patch("backend.plex_library.CONFIG_DIR", tmp_dir):
        mock_pa = MagicMock()
        mock_pa.get_resources.return_value = [
            {
                "clientIdentifier": "server123",
                "name": "Test",
                "owned": True,
                "provides": "server",
                "connections": [
                    {"uri": "http://s:32400", "local": True, "relay": False, "protocol": "http"}
                ],
            }
        ]
        mock_pa.switch_user.return_value = None
        mock_pa_cls.return_value = mock_pa

        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        config.plex_transcode_mode = transcode_mode
        config.hw_decode_codecs = hw_decode_codecs if hw_decode_codecs is not None else []
        lib = PlexLibrary(config)
    return lib


def _setup_client(lib, stream_url="http://s:32400/parts/1/0/f.mkv?X-Plex-Token=tok"):
    """Attach a mock client to the library and return it."""
    mock_client = MagicMock()
    mock_client.get_stream_url.return_value = (stream_url, 0)
    mock_client.get_transcode_url.return_value = (
        "http://s:32400/video/:/transcode?X-Plex-Token=tok", 0
    )
    mock_client.get_metadata.return_value = {
        "title": "Movie", "grandparentTitle": "",
    }
    mock_client.get_transient_token.return_value = None
    mock_client.create_play_queue.return_value = {"MediaContainer": {}}
    lib._client = mock_client
    lib._machine_identifier = ""
    return mock_client


class TestPlaybackDecisionDirect:
    def test_direct_mode_uses_stream_url(self) -> None:
        lib = _make_lib(transcode_mode="direct", hw_decode_codecs=["h264"])
        client = _setup_client(lib)

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        client.get_stream_url.assert_called_once_with("123")
        client.get_transcode_url.assert_not_called()
        client.get_media_video_codec.assert_not_called()


class TestPlaybackDecisionFixedResolution:
    @pytest.mark.parametrize("mode", ["480p", "720p", "1080p"])
    def test_fixed_resolution_uses_transcode_url(self, mode: str) -> None:
        lib = _make_lib(transcode_mode=mode, hw_decode_codecs=["h264"])
        client = _setup_client(lib)

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        client.get_transcode_url.assert_called_once_with("123", mode)
        client.get_stream_url.assert_not_called()


class TestPlaybackDecisionAuto:
    def test_auto_hw_decodable_uses_direct(self) -> None:
        lib = _make_lib(transcode_mode="auto", hw_decode_codecs=["h264", "hevc"])
        client = _setup_client(lib)
        client.get_media_video_codec.return_value = "h264"

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        client.get_media_video_codec.assert_called_once_with("123")
        client.get_stream_url.assert_called_once_with("123")
        client.get_transcode_url.assert_not_called()

    def test_auto_not_hw_decodable_uses_transcode(self) -> None:
        lib = _make_lib(transcode_mode="auto", hw_decode_codecs=["h264"])
        client = _setup_client(lib)
        client.get_media_video_codec.return_value = "hevc"

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        client.get_transcode_url.assert_called_once_with("123", "1080p")
        client.get_stream_url.assert_not_called()

    def test_auto_empty_codec_uses_transcode(self) -> None:
        lib = _make_lib(transcode_mode="auto", hw_decode_codecs=["h264"])
        client = _setup_client(lib)
        client.get_media_video_codec.return_value = ""

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        client.get_transcode_url.assert_called_once_with("123", "1080p")

    def test_auto_empty_hw_codecs_uses_transcode(self) -> None:
        """When hw codec detection returns nothing, auto mode transcodes."""
        lib = _make_lib(transcode_mode="auto", hw_decode_codecs=[])
        client = _setup_client(lib)
        client.get_media_video_codec.return_value = "h264"

        with patch("backend.plex_library.detect_vaapi_codecs", return_value=[]):
            lib.playWithMpv("123", 0)
            lib._executor.shutdown(wait=True)

        # codec "h264" not in empty hw_codecs → transcode
        client.get_transcode_url.assert_called_once_with("123", "1080p")


class TestHwCodecDetection:
    def test_detection_triggered_when_cache_empty(self) -> None:
        lib = _make_lib(transcode_mode="direct", hw_decode_codecs=[])
        client = _setup_client(lib)

        with patch("backend.plex_library.detect_vaapi_codecs", return_value=["h264", "hevc"]) as mock_detect:
            lib.playWithMpv("123", 0)
            lib._executor.shutdown(wait=True)

        mock_detect.assert_called_once()
        lib._config.set_hw_decode_codecs.assert_called_once_with(["h264", "hevc"])

    def test_detection_skipped_when_cache_populated(self) -> None:
        lib = _make_lib(transcode_mode="direct", hw_decode_codecs=["h264"])
        client = _setup_client(lib)

        with patch("backend.plex_library.detect_vaapi_codecs") as mock_detect:
            lib.playWithMpv("123", 0)
            lib._executor.shutdown(wait=True)

        mock_detect.assert_not_called()
