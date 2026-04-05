"""Tests for Task 002 — PlexLibrary getLyrics slot.

Covers:
  - 200 with syncedLyrics → lyricsReady emitted with parsed LRC lines
  - 200 with plainLyrics only → lyricsReady emitted with parsed plain lines
  - 200 with instrumental: true → lyricsUnavailable emitted
  - 200 with neither lyrics field → lyricsUnavailable emitted
  - 404 → lyricsUnavailable emitted
  - Network error (requests.exceptions.ConnectionError) → lyricsUnavailable emitted
  - Correct params sent to LRCLIB: track_name, artist_name, album_name, duration (rounded seconds)
  - Correct User-Agent header sent
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests as req

from backend.plex_library import PlexLibrary


# ---------------------------------------------------------------------------
# Test helpers
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
    from backend.config import Config

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)
    return lib


def _call_worker_directly(lib, rating_key, track_title, artist_name, album_name, duration_ms):
    """Call _worker_fetch_lyrics synchronously (bypasses executor)."""
    lib._worker_fetch_lyrics(rating_key, track_title, artist_name, album_name, duration_ms)


def _make_mock_response(status_code, json_data=None):
    """Build a mock requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json.return_value = json_data
    return mock_resp


# ---------------------------------------------------------------------------
# 200 with syncedLyrics → lyricsReady
# ---------------------------------------------------------------------------


class TestGetLyricsSyncedLyrics:
    def test_synced_lyrics_emits_lyrics_ready(self) -> None:
        """200 with syncedLyrics → lyricsReady emitted with parsed LRC lines."""
        lib = _make_lib()

        synced = "[00:01.00] Hello\n[00:02.00] World"
        mock_resp = _make_mock_response(200, {
            "syncedLyrics": synced,
            "plainLyrics": None,
            "instrumental": False,
        })

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append((rk, lines)))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "42", "Hello", "Artist", "Album", 180000)

        assert len(received_ready) == 1
        rk, lines = received_ready[0]
        assert rk == "42"
        assert len(lines) == 2
        assert lines[0] == {"ms": 1000, "text": "Hello"}
        assert lines[1] == {"ms": 2000, "text": "World"}

    def test_synced_lyrics_preferred_over_plain(self) -> None:
        """When both syncedLyrics and plainLyrics are present, synced takes priority."""
        lib = _make_lib()

        synced = "[00:01.00] Synced line"
        mock_resp = _make_mock_response(200, {
            "syncedLyrics": synced,
            "plainLyrics": "Plain line",
            "instrumental": False,
        })

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append((rk, lines)))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "42", "Track", "Artist", "Album", 60000)

        assert len(received_ready) == 1
        _, lines = received_ready[0]
        # Should be LRC-parsed (has ms > -1)
        assert all(line["ms"] >= 0 for line in lines)

    def test_synced_lyrics_lines_sorted_by_ms(self) -> None:
        """Parsed LRC lines are sorted ascending by ms."""
        lib = _make_lib()

        synced = "[00:03.00] Third\n[00:01.00] First\n[00:02.00] Second"
        mock_resp = _make_mock_response(200, {
            "syncedLyrics": synced,
            "plainLyrics": None,
            "instrumental": False,
        })

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append((rk, lines)))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "42", "Track", "Artist", "Album", 60000)

        _, lines = received_ready[0]
        ms_values = [line["ms"] for line in lines]
        assert ms_values == sorted(ms_values)


# ---------------------------------------------------------------------------
# 200 with plainLyrics only → lyricsReady
# ---------------------------------------------------------------------------


class TestGetLyricsPlainLyrics:
    def test_plain_lyrics_emits_lyrics_ready(self) -> None:
        """200 with plainLyrics only → lyricsReady emitted with parsed plain lines."""
        lib = _make_lib()

        plain = "Line one\nLine two\nLine three"
        mock_resp = _make_mock_response(200, {
            "syncedLyrics": None,
            "plainLyrics": plain,
            "instrumental": False,
        })

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append((rk, lines)))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "99", "Track", "Artist", "Album", 120000)

        assert len(received_ready) == 1
        rk, lines = received_ready[0]
        assert rk == "99"
        assert len(lines) == 3
        assert all(line["ms"] == -1 for line in lines)
        assert lines[0]["text"] == "Line one"
        assert lines[1]["text"] == "Line two"
        assert lines[2]["text"] == "Line three"

    def test_plain_lyrics_empty_synced_string_falls_through(self) -> None:
        """Empty string syncedLyrics falls through to plainLyrics."""
        lib = _make_lib()

        mock_resp = _make_mock_response(200, {
            "syncedLyrics": "",
            "plainLyrics": "Only plain",
            "instrumental": False,
        })

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append((rk, lines)))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "55", "Track", "Artist", "Album", 60000)

        assert len(received_ready) == 1
        _, lines = received_ready[0]
        assert lines[0]["ms"] == -1
        assert lines[0]["text"] == "Only plain"


# ---------------------------------------------------------------------------
# 200 with instrumental: true → lyricsUnavailable
# ---------------------------------------------------------------------------


class TestGetLyricsInstrumental:
    def test_instrumental_emits_lyrics_unavailable(self) -> None:
        """200 with instrumental: true → lyricsUnavailable emitted."""
        lib = _make_lib()

        mock_resp = _make_mock_response(200, {
            "syncedLyrics": "[00:01.00] Some text",
            "plainLyrics": "Some text",
            "instrumental": True,
        })

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append(rk))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "77", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["77"]
        assert received_ready == []


# ---------------------------------------------------------------------------
# 200 with neither lyrics field → lyricsUnavailable
# ---------------------------------------------------------------------------


class TestGetLyricsNeitherField:
    def test_no_lyrics_fields_emits_unavailable(self) -> None:
        """200 with neither syncedLyrics nor plainLyrics → lyricsUnavailable."""
        lib = _make_lib()

        mock_resp = _make_mock_response(200, {
            "syncedLyrics": None,
            "plainLyrics": None,
            "instrumental": False,
        })

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "88", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["88"]

    def test_empty_string_lyrics_fields_emits_unavailable(self) -> None:
        """200 with empty string syncedLyrics and plainLyrics → lyricsUnavailable."""
        lib = _make_lib()

        mock_resp = _make_mock_response(200, {
            "syncedLyrics": "",
            "plainLyrics": "",
            "instrumental": False,
        })

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "89", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["89"]


# ---------------------------------------------------------------------------
# 404 → lyricsUnavailable
# ---------------------------------------------------------------------------


class TestGetLyrics404:
    def test_404_emits_lyrics_unavailable(self) -> None:
        """HTTP 404 → lyricsUnavailable emitted."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append(rk))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "11", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["11"]
        assert received_ready == []


# ---------------------------------------------------------------------------
# Network error → lyricsUnavailable
# ---------------------------------------------------------------------------


class TestGetLyricsNetworkError:
    def test_connection_error_emits_lyrics_unavailable(self) -> None:
        """requests.exceptions.ConnectionError → lyricsUnavailable emitted."""
        lib = _make_lib()

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append(rk))

        with patch(
            "backend.plex_library.requests.get",
            side_effect=req.exceptions.ConnectionError("refused"),
        ):
            _call_worker_directly(lib, "22", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["22"]
        assert received_ready == []

    def test_timeout_error_emits_lyrics_unavailable(self) -> None:
        """requests.exceptions.Timeout → lyricsUnavailable emitted."""
        lib = _make_lib()

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        with patch(
            "backend.plex_library.requests.get",
            side_effect=req.exceptions.Timeout("timed out"),
        ):
            _call_worker_directly(lib, "33", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["33"]

    def test_non_200_non_404_emits_lyrics_unavailable(self) -> None:
        """Non-200/404 HTTP status → lyricsUnavailable emitted."""
        lib = _make_lib()

        mock_resp = _make_mock_response(500)

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        with patch("backend.plex_library.requests.get", return_value=mock_resp):
            _call_worker_directly(lib, "44", "Track", "Artist", "Album", 60000)

        assert received_unavailable == ["44"]


# ---------------------------------------------------------------------------
# Correct params sent to LRCLIB
# ---------------------------------------------------------------------------


class TestGetLyricsRequestParams:
    def test_correct_params_sent(self) -> None:
        """Correct query params are sent: track_name, artist_name, album_name, duration."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        with patch("backend.plex_library.requests.get", return_value=mock_resp) as mock_get:
            _call_worker_directly(
                lib,
                "42",
                "Come Together",
                "The Beatles",
                "Abbey Road",
                259000,
            )

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        # Access via keyword argument
        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["track_name"] == "Come Together"
        assert params["artist_name"] == "The Beatles"
        assert params["album_name"] == "Abbey Road"
        assert params["duration"] == 259  # round(259000 / 1000)

    def test_duration_rounded_to_seconds(self) -> None:
        """duration param is round(duration_ms / 1000)."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        with patch("backend.plex_library.requests.get", return_value=mock_resp) as mock_get:
            _call_worker_directly(lib, "1", "T", "A", "B", 259499)

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["duration"] == round(259499 / 1000)

    def test_correct_url_called(self) -> None:
        """requests.get is called with the LRCLIB API URL."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        with patch("backend.plex_library.requests.get", return_value=mock_resp) as mock_get:
            _call_worker_directly(lib, "1", "T", "A", "B", 60000)

        url = mock_get.call_args.args[0] if mock_get.call_args.args else mock_get.call_args[0][0]
        assert url == "https://lrclib.net/api/get"


# ---------------------------------------------------------------------------
# Correct User-Agent header sent
# ---------------------------------------------------------------------------


class TestGetLyricsUserAgent:
    def test_correct_user_agent_sent(self) -> None:
        """Correct User-Agent header is sent to LRCLIB."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        with patch("backend.plex_library.requests.get", return_value=mock_resp) as mock_get:
            _call_worker_directly(lib, "1", "T", "A", "B", 60000)

        headers = mock_get.call_args.kwargs.get("headers") or mock_get.call_args[1].get("headers")
        assert headers["User-Agent"] == "htpcstation/1.0 (https://github.com/tranxuanthang/lrcget)"

    def test_timeout_is_10_seconds(self) -> None:
        """requests.get is called with timeout=10."""
        lib = _make_lib()

        mock_resp = _make_mock_response(404)

        with patch("backend.plex_library.requests.get", return_value=mock_resp) as mock_get:
            _call_worker_directly(lib, "1", "T", "A", "B", 60000)

        timeout = mock_get.call_args.kwargs.get("timeout") or mock_get.call_args[1].get("timeout")
        assert timeout == 10


# ---------------------------------------------------------------------------
# Zero-duration guard — getLyrics slot
# ---------------------------------------------------------------------------


class TestGetLyricsZeroDuration:
    def test_zero_duration_emits_lyrics_unavailable(self) -> None:
        """getLyrics with duration_ms=0 emits lyricsUnavailable without touching the executor."""
        lib = _make_lib()

        received_unavailable = []
        lib.lyricsUnavailable.connect(lambda rk: received_unavailable.append(rk))

        received_ready = []
        lib.lyricsReady.connect(lambda rk, lines: received_ready.append(rk))

        with patch("backend.plex_library.requests.get") as mock_get:
            lib.getLyrics("42", "Track", "Artist", "Album", 0)

        assert received_unavailable == ["42"]
        assert received_ready == []
        mock_get.assert_not_called()

    def test_zero_duration_does_not_submit_to_executor(self) -> None:
        """getLyrics with duration_ms=0 does not submit a task to the executor."""
        lib = _make_lib()

        with patch.object(lib._executor, "submit") as mock_submit:
            lib.getLyrics("99", "Track", "Artist", "Album", 0)

        mock_submit.assert_not_called()

    def test_nonzero_duration_proceeds_normally(self) -> None:
        """getLyrics with duration_ms > 0 still submits to the executor (no false guard)."""
        lib = _make_lib()

        with patch.object(lib._executor, "submit") as mock_submit:
            lib.getLyrics("7", "Track", "Artist", "Album", 180000)

        mock_submit.assert_called_once()
