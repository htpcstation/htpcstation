"""Tests for MPV stream URL and playback slots (Task 001 — MPV Player backend).

Covers:
  - PlexClient.get_stream_url: correct URL from metadata
  - PlexClient.get_stream_url: returns ("", 0) when no Media
  - PlexClient.get_stream_url: returns ("", 0) when no Part
  - PlexClient.get_stream_url: includes viewOffset
  - PlexLibrary.getStreamInfo: returns correct dict
  - PlexLibrary.getStreamInfo: returns {"url": "", "viewOffset": 0} when client None
  - PlexLibrary.playWithMpv: calls _mpv_launcher.launch with correct url/title/start_ms
  - PlexLibrary.playWithMpv: no-ops when client None
  - PlexLibrary.playWithMpv: no-ops when stream URL empty
  - PlexLibrary.playWithMpvFromStart: delegates to playWithMpv with start_ms=0
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
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
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


def _make_plex_client(server_url: str = "http://server:32400", token: str = "tok"):
    """Return a PlexClient with a mocked requests.Session."""
    from backend.plex_client import PlexClient

    with patch("backend.plex_client.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        client = PlexClient(server_url, token)
    return client, mock_session


def _make_lib():
    """Return a PlexLibrary with mocked dependencies."""
    import tempfile
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    tmp_dir = Path(tempfile.mkdtemp())
    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"), \
         patch("backend.plex_library.CONFIG_DIR", tmp_dir):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)
    return lib


# ---------------------------------------------------------------------------
# PlexClient.get_stream_url
# ---------------------------------------------------------------------------


class TestGetStreamUrl:
    def _make_metadata_response(self, part_key: str, view_offset: int = 0) -> dict:
        return {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "123",
                        "title": "Test Movie",
                        "Media": [
                            {
                                "Part": [
                                    {"key": part_key}
                                ]
                            }
                        ],
                        "viewOffset": view_offset,
                    }
                ]
            }
        }

    def test_returns_correct_url_and_zero_offset(self) -> None:
        """get_stream_url returns the correct direct stream URL with zero viewOffset."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = self._make_metadata_response(
                "/library/parts/456/0/file.mkv"
            )
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "mytoken")
            url, view_offset = client.get_stream_url("123")

        assert url == "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=mytoken"
        assert view_offset == 0

    def test_returns_view_offset_when_present(self) -> None:
        """get_stream_url returns the viewOffset from metadata."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = self._make_metadata_response(
                "/library/parts/456/0/file.mkv", view_offset=120000
            )
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "mytoken")
            url, view_offset = client.get_stream_url("123")

        assert url == "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=mytoken"
        assert view_offset == 120000

    def test_returns_empty_when_no_media(self) -> None:
        """get_stream_url returns ("", 0) when the item has no Media."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [
                        {"ratingKey": "123", "title": "Test", "Media": []}
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_stream_url("123")

        assert result == ("", 0)

    def test_returns_empty_when_no_part(self) -> None:
        """get_stream_url returns ("", 0) when Media has no Part."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "ratingKey": "123",
                            "title": "Test",
                            "Media": [{"Part": []}],
                        }
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_stream_url("123")

        assert result == ("", 0)

    def test_returns_empty_when_part_key_missing(self) -> None:
        """get_stream_url returns ("", 0) when the Part has no key."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "ratingKey": "123",
                            "title": "Test",
                            "Media": [{"Part": [{"key": ""}]}],
                        }
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_stream_url("123")

        assert result == ("", 0)

    def test_view_offset_none_treated_as_zero(self) -> None:
        """get_stream_url treats None viewOffset as 0."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "ratingKey": "123",
                            "title": "Test",
                            "Media": [{"Part": [{"key": "/library/parts/1/0/file.mkv"}]}],
                            "viewOffset": None,
                        }
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            url, view_offset = client.get_stream_url("123")

        assert view_offset == 0
        assert url != ""


# ---------------------------------------------------------------------------
# PlexLibrary.getStreamInfo
# ---------------------------------------------------------------------------


class TestGetStreamInfo:
    def test_returns_correct_dict(self) -> None:
        """getStreamInfo returns {"url": ..., "viewOffset": ...} from the client."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            90000,
        )
        lib._client = mock_client

        result = lib.getStreamInfo("123")

        assert result["url"] == "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok"
        assert result["viewOffset"] == 90000

    def test_returns_empty_dict_when_client_none(self) -> None:
        """getStreamInfo returns {"url": "", "viewOffset": 0} when no client."""
        lib = _make_lib()
        lib._client = None

        result = lib.getStreamInfo("123")

        assert result == {"url": "", "viewOffset": 0}

    def test_returns_empty_dict_when_no_stream_url(self) -> None:
        """getStreamInfo returns {"url": "", "viewOffset": 0} when client returns empty URL."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = ("", 0)
        lib._client = mock_client

        result = lib.getStreamInfo("999")

        assert result == {"url": "", "viewOffset": 0}


# ---------------------------------------------------------------------------
# PlexLibrary.playWithMpv
# ---------------------------------------------------------------------------


class TestPlayWithMpv:
    def test_calls_mpv_launcher_with_correct_args(self) -> None:
        """playWithMpv fetches stream URL and calls _mpv_launcher.launch correctly."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Test Movie",
            "grandparentTitle": "",
        }
        lib._client = mock_client

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)
        # Signal delivery requires an event loop; call handler directly
        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Test Movie",
            0,
        )

        mock_launcher.launch.assert_called_once_with(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Test Movie",
            0,
        )

    def test_title_includes_grandparent_when_present(self) -> None:
        """playWithMpv prefixes grandparentTitle to title for TV episodes."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/789/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {
            "title": "Pilot",
            "grandparentTitle": "My Show",
        }
        lib._client = mock_client

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpv("400", 0)
        lib._executor.shutdown(wait=True)
        # Signal delivery requires an event loop; call handler directly
        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/789/0/file.mkv?X-Plex-Token=tok",
            "My Show — Pilot",
            0,
        )

        mock_launcher.launch.assert_called_once_with(
            "http://server:32400/library/parts/789/0/file.mkv?X-Plex-Token=tok",
            "My Show — Pilot",
            0,
        )

    def test_passes_start_ms_to_launcher(self) -> None:
        """playWithMpv passes start_ms to _mpv_launcher.launch."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {"title": "Movie", "grandparentTitle": ""}
        lib._client = mock_client

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpv("123", 60000)
        lib._executor.shutdown(wait=True)
        # Signal delivery requires an event loop; call handler directly
        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Movie",
            60000,
        )

        mock_launcher.launch.assert_called_once_with(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Movie",
            60000,
        )

    def test_noop_when_client_none(self) -> None:
        """playWithMpv does nothing when no Plex client is configured."""
        lib = _make_lib()
        lib._client = None

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpv("123", 0)

        mock_launcher.launch.assert_not_called()

    def test_noop_when_stream_url_empty(self) -> None:
        """playWithMpv does nothing when the stream URL is empty."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = ("", 0)
        lib._client = mock_client

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpv("999", 0)
        lib._executor.shutdown(wait=True)
        # Worker emits _mpvLaunchReady("", "", 0); handler should not call launch
        lib._on_mpv_launch_ready("", "", 0)

        mock_launcher.launch.assert_not_called()


# ---------------------------------------------------------------------------
# PlexLibrary.playWithMpvFromStart
# ---------------------------------------------------------------------------


class TestPlayWithMpvFromStart:
    def test_delegates_to_play_with_mpv_with_zero_start(self) -> None:
        """playWithMpvFromStart calls playWithMpv with start_ms=0."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = (
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            0,
        )
        mock_client.get_metadata.return_value = {"title": "Movie", "grandparentTitle": ""}
        lib._client = mock_client

        mock_launcher = MagicMock()
        lib._mpv_launcher = mock_launcher

        lib.playWithMpvFromStart("123")
        lib._executor.shutdown(wait=True)
        # Signal delivery requires an event loop; call handler directly
        lib._on_mpv_launch_ready(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Movie",
            0,
        )

        mock_launcher.launch.assert_called_once_with(
            "http://server:32400/library/parts/456/0/file.mkv?X-Plex-Token=tok",
            "Movie",
            0,
        )
