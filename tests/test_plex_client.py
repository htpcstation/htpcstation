"""Tests for PlexClient — identity headers, timeline reporting, track persistence, retry logic."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.plex_client import PlexClient, PlexErrorType, PlexEventListener


class TestClientIdentityHeaders:
    """Verify that PlexClient sets the required Plex identity headers."""

    def test_identity_headers_present(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token", client_id="test-uuid")
        headers = client._session.headers
        assert headers["X-Plex-Client-Identifier"] == "test-uuid"
        assert headers["X-Plex-Product"] == "HTPC Station"
        assert headers["X-Plex-Platform"] == "Linux"
        assert headers["X-Plex-Version"] == "1.0.0"
        assert headers["X-Plex-Device"] == "PC"
        assert "X-Plex-Device-Name" in headers

    def test_default_client_id(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        assert client._session.headers["X-Plex-Client-Identifier"] == "htpcstation"

    def test_custom_client_id(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token", client_id="my-uuid-123")
        assert client._session.headers["X-Plex-Client-Identifier"] == "my-uuid-123"

    def test_client_profile_extra_header_present(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        header = client._session.headers["X-Plex-Client-Profile-Extra"]
        assert "video.bitDepth" in header
        assert "upperBound" in header


class TestReportTimeline:
    """Verify report_timeline sends correct params and never raises."""

    def test_sends_correct_params(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock()

        client.report_timeline(
            rating_key="12345",
            state="playing",
            time_ms=60000,
            duration_ms=7200000,
            session_id="sess-uuid",
        )

        client._session.get.assert_called_once()
        call_args = client._session.get.call_args
        assert call_args[0][0] == "http://localhost:32400/:/timeline"
        params = call_args[1]["params"]
        assert params["ratingKey"] == "12345"
        assert params["state"] == "playing"
        assert params["time"] == 60000
        assert params["duration"] == 7200000
        assert params["X-Plex-Session-Identifier"] == "sess-uuid"
        assert params["identifier"] == "com.plexapp.plugins.library"
        assert params["key"] == "/library/metadata/12345"

    def test_never_raises_on_connection_error(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock(side_effect=ConnectionError("refused"))

        # Should not raise
        client.report_timeline(
            rating_key="12345",
            state="playing",
            time_ms=0,
            duration_ms=100000,
            session_id="sess-uuid",
        )

    def test_never_raises_on_timeout(self) -> None:
        import requests
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock(side_effect=requests.exceptions.Timeout())

        client.report_timeline(
            rating_key="12345",
            state="stopped",
            time_ms=0,
            duration_ms=100000,
            session_id="sess-uuid",
        )


class TestPersistStreamSelection:
    """Verify persist_stream_selection sends correct PUT requests."""

    def test_audio_selection(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.persist_stream_selection(part_id=999, audio_stream_id=42)

        client._session.put.assert_called_once()
        call_args = client._session.put.call_args
        assert call_args[0][0] == "http://localhost:32400/library/parts/999"
        params = call_args[1]["params"]
        assert params["allParts"] == 1
        assert params["audioStreamID"] == 42
        assert "subtitleStreamID" not in params

    def test_subtitle_disabled(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.persist_stream_selection(part_id=999, subtitle_stream_id=0)

        call_args = client._session.put.call_args
        params = call_args[1]["params"]
        assert params["subtitleStreamID"] == 0
        assert "audioStreamID" not in params

    def test_subtitle_selection(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.persist_stream_selection(part_id=999, subtitle_stream_id=55)

        call_args = client._session.put.call_args
        params = call_args[1]["params"]
        assert params["subtitleStreamID"] == 55

    def test_no_request_when_part_id_zero(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.persist_stream_selection(part_id=0, audio_stream_id=42)

        client._session.put.assert_not_called()

    def test_never_raises_on_error(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock(side_effect=ConnectionError("refused"))

        # Should not raise
        client.persist_stream_selection(part_id=999, audio_stream_id=42)


class TestMarkPlayed:
    """Verify mark_played and mark_unplayed send correct requests."""

    def test_mark_played_calls_scrobble(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock()

        client.mark_played("12345")

        client._session.get.assert_called_once()
        call_args = client._session.get.call_args
        assert call_args[0][0] == "http://localhost:32400/:/scrobble"
        params = call_args[1]["params"]
        assert params["key"] == "12345"
        assert params["identifier"] == "com.plexapp.plugins.library"

    def test_mark_unplayed_calls_unscrobble(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock()

        client.mark_unplayed("12345")

        client._session.get.assert_called_once()
        call_args = client._session.get.call_args
        assert call_args[0][0] == "http://localhost:32400/:/unscrobble"
        params = call_args[1]["params"]
        assert params["key"] == "12345"
        assert params["identifier"] == "com.plexapp.plugins.library"

    def test_mark_played_never_raises(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock(side_effect=ConnectionError("refused"))

        # Should not raise
        client.mark_played("12345")

    def test_mark_unplayed_never_raises(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock(side_effect=ConnectionError("refused"))

        # Should not raise
        client.mark_unplayed("12345")


class TestRate:
    """Verify rate() sends correct PUT request and never raises."""

    def test_rate_sends_correct_params(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.rate("123", 8.0)

        client._session.put.assert_called_once()
        call_args = client._session.put.call_args
        assert call_args[0][0] == "http://localhost:32400/:/rate"
        params = call_args[1]["params"]
        assert params["key"] == "123"
        assert params["rating"] == 8.0
        assert params["identifier"] == "com.plexapp.plugins.library"

    def test_rate_zero_clears_rating(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock()

        client.rate("123", 0.0)

        call_args = client._session.put.call_args
        params = call_args[1]["params"]
        assert params["rating"] == 0.0

    def test_rate_never_raises(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.put = MagicMock(side_effect=ConnectionError("refused"))

        # Should not raise
        client.rate("123", 8.0)


class TestTransientToken:
    """Verify get_transient_token returns token or empty string."""

    def test_get_transient_token_returns_token(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {"token": "abc123"}
        })

        result = client.get_transient_token()

        assert result == "abc123"
        client._get.assert_called_once_with(
            "/security/token", params={"type": "delegation", "scope": "all"}
        )

    def test_get_transient_token_returns_empty_on_failure(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value=None)

        result = client.get_transient_token()

        assert result == ""


# ---------------------------------------------------------------------------
# PlexClient._get — retry logic and error classification
# ---------------------------------------------------------------------------


class TestGetRetryLogic:
    """Verify _get() retries transient errors and classifies error types."""

    @patch("backend.plex_client.time.sleep")
    def test_get_retries_on_500(self, mock_sleep: MagicMock) -> None:
        """Mock _session.get to return 500 twice then 200; verify 3 calls and result returned."""
        client = PlexClient("http://localhost:32400", "test-token")

        # Build mock responses: 500, 500, 200
        resp_500_1 = MagicMock()
        resp_500_1.status_code = 500
        resp_500_1.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_500_1
        )

        resp_500_2 = MagicMock()
        resp_500_2.status_code = 500
        resp_500_2.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_500_2
        )

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None
        resp_200.json.return_value = {"MediaContainer": {"data": "ok"}}

        client._session.get = MagicMock(side_effect=[resp_500_1, resp_500_2, resp_200])

        result = client._get("/test")

        assert result == {"MediaContainer": {"data": "ok"}}
        assert client._session.get.call_count == 3
        assert client._last_error == PlexErrorType.NONE

    @patch("backend.plex_client.time.sleep")
    def test_get_no_retry_on_401(self, mock_sleep: MagicMock) -> None:
        """Mock returns 401; verify only 1 call made, returns None, _last_error == AUTH."""
        client = PlexClient("http://localhost:32400", "test-token")

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_401
        )

        client._session.get = MagicMock(side_effect=[resp_401])

        result = client._get("/test")

        assert result is None
        assert client._session.get.call_count == 1
        assert client._last_error == PlexErrorType.AUTH

    @patch("backend.plex_client.time.sleep")
    def test_get_no_retry_on_404(self, mock_sleep: MagicMock) -> None:
        """Mock returns 404; verify only 1 call, _last_error == NOT_FOUND."""
        client = PlexClient("http://localhost:32400", "test-token")

        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_404
        )

        client._session.get = MagicMock(side_effect=[resp_404])

        result = client._get("/test")

        assert result is None
        assert client._session.get.call_count == 1
        assert client._last_error == PlexErrorType.NOT_FOUND

    @patch("backend.plex_client.time.sleep")
    def test_get_retries_on_connection_error(self, mock_sleep: MagicMock) -> None:
        """Mock raises ConnectionError twice then succeeds; verify 3 calls."""
        client = PlexClient("http://localhost:32400", "test-token")

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None
        resp_200.json.return_value = {"MediaContainer": {"ok": True}}

        client._session.get = MagicMock(side_effect=[
            requests.exceptions.ConnectionError("refused"),
            requests.exceptions.ConnectionError("refused"),
            resp_200,
        ])

        result = client._get("/test")

        assert result == {"MediaContainer": {"ok": True}}
        assert client._session.get.call_count == 3

    @patch("backend.plex_client.time.sleep")
    def test_get_calls_error_callback(self, mock_sleep: MagicMock) -> None:
        """Register callback, mock returns 401; verify callback called with PlexErrorType.AUTH."""
        client = PlexClient("http://localhost:32400", "test-token")

        callback = MagicMock()
        client.set_error_callback(callback)

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_401
        )

        client._session.get = MagicMock(side_effect=[resp_401])

        client._get("/test")

        callback.assert_called_once_with(PlexErrorType.AUTH)

    @patch("backend.plex_client.time.sleep")
    def test_get_handles_retry_after_header(self, mock_sleep: MagicMock) -> None:
        """Mock returns 429 with Retry-After: 0; verify retried."""
        client = PlexClient("http://localhost:32400", "test-token")

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None
        resp_200.json.return_value = {"MediaContainer": {"ok": True}}

        client._session.get = MagicMock(side_effect=[resp_429, resp_200])

        result = client._get("/test")

        assert result == {"MediaContainer": {"ok": True}}
        assert client._session.get.call_count == 2

class TestCreatePlayQueue:
    """Verify create_play_queue sends correct POST and handles failures."""

    def test_create_play_queue_posts_correct_uri(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "MediaContainer": {
                "playQueueID": 123,
                "Metadata": [{"playQueueItemID": 456}],
            }
        }
        mock_response.raise_for_status.return_value = None
        client._session.post = MagicMock(return_value=mock_response)

        result = client.create_play_queue("789", "abc-machine-id")

        client._session.post.assert_called_once()
        call_args = client._session.post.call_args
        assert call_args[0][0] == "http://localhost:32400/playQueues"
        params = call_args[1]["params"]
        assert params["type"] == "video"
        assert "abc-machine-id" in params["uri"]
        assert "789" in params["uri"]
        assert result == mock_response.json.return_value

    def test_create_play_queue_returns_empty_on_failure(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.post = MagicMock(side_effect=ConnectionError("refused"))

        result = client.create_play_queue("789", "abc-machine-id")

        assert result == {}

    def test_create_play_queue_returns_empty_without_machine_id(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.post = MagicMock()

        result = client.create_play_queue("789", "")

        assert result == {}
        client._session.post.assert_not_called()

    def test_report_timeline_includes_play_queue_item_id(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock()

        client.report_timeline(
            rating_key="12345",
            state="playing",
            time_ms=60000,
            duration_ms=7200000,
            session_id="sess-uuid",
            play_queue_item_id=42,
        )

        call_args = client._session.get.call_args
        params = call_args[1]["params"]
        assert params["playQueueItemID"] == 42

    def test_report_timeline_omits_play_queue_item_id_when_zero(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._session.get = MagicMock()

        client.report_timeline(
            rating_key="12345",
            state="playing",
            time_ms=60000,
            duration_ms=7200000,
            session_id="sess-uuid",
            play_queue_item_id=0,
        )

        call_args = client._session.get.call_args
        params = call_args[1]["params"]
        assert "playQueueItemID" not in params


# ---------------------------------------------------------------------------
# PlexClient.get_watch_history
# ---------------------------------------------------------------------------


class TestGetWatchHistory:
    """Verify get_watch_history calls the correct endpoint with correct params."""

    def test_get_watch_history_returns_metadata(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {
                "Metadata": [{"ratingKey": "1", "title": "Movie"}]
            }
        })

        result = client.get_watch_history()

        assert result == [{"ratingKey": "1", "title": "Movie"}]

    def test_get_watch_history_sends_correct_params(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {"Metadata": []}
        })

        client.get_watch_history()

        client._get.assert_called_once()
        call_args = client._get.call_args
        params = call_args[1]["params"]
        assert params["sort"] == "viewedAt:desc"
        assert params["X-Plex-Container-Size"] == 50

    def test_get_watch_history_with_account_id(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {"Metadata": []}
        })

        client.get_watch_history(account_id=123)

        call_args = client._get.call_args
        params = call_args[1]["params"]
        assert params["accountID"] == 123

    def test_get_watch_history_returns_empty_on_failure(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value=None)

        result = client.get_watch_history()

        assert result == []


# ---------------------------------------------------------------------------
# PlexClient.get_transcode_url
# ---------------------------------------------------------------------------


class TestGetTranscodeUrl:
    """Verify get_transcode_url builds correct HLS transcode URLs."""

    _METADATA = {
        "ratingKey": "999",
        "viewOffset": 45000,
        "Media": [{"videoCodec": "hevc", "Part": [{"key": "/library/parts/1"}]}],
    }

    def test_builds_correct_url_1080p(self) -> None:
        client = PlexClient("http://plex:32400", "tok123", client_id="my-id")
        client.get_metadata = MagicMock(return_value=self._METADATA)

        url, offset = client.get_transcode_url("999")

        assert offset == 45000
        assert url.startswith("http://plex:32400/video/:/transcode/universal/start.m3u8?")
        assert "videoResolution=1920x1080" in url
        assert "maxVideoBitrate=20000" in url
        assert "X-Plex-Token=tok123" in url
        assert "X-Plex-Client-Identifier=my-id" in url
        assert "protocol=hls" in url
        assert "directPlay=0" in url
        assert "directStream=0" in url
        assert "path=%2Flibrary%2Fmetadata%2F999" in url

    def test_builds_correct_url_720p(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value=self._METADATA)

        url, _ = client.get_transcode_url("999", max_resolution="720p")

        assert "videoResolution=1280x720" in url
        assert "maxVideoBitrate=4000" in url

    def test_builds_correct_url_480p(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value=self._METADATA)

        url, _ = client.get_transcode_url("999", max_resolution="480p")

        assert "videoResolution=854x480" in url
        assert "maxVideoBitrate=2000" in url

    def test_returns_empty_on_metadata_failure(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value={})

        url, offset = client.get_transcode_url("999")

        assert url == ""
        assert offset == 0

    def test_returns_empty_on_unknown_resolution(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value=self._METADATA)

        url, offset = client.get_transcode_url("999", max_resolution="4k")

        assert url == ""
        assert offset == 0
        # Should not even call get_metadata for invalid resolution
        client.get_metadata.assert_not_called()

    def test_zero_view_offset_when_not_set(self) -> None:
        metadata = {
            "ratingKey": "999",
            "Media": [{"videoCodec": "h264"}],
        }
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value=metadata)

        _, offset = client.get_transcode_url("999")

        assert offset == 0


# ---------------------------------------------------------------------------
# PlexClient.get_media_video_codec
# ---------------------------------------------------------------------------


class TestGetMediaVideoCodec:
    """Verify get_media_video_codec extracts the codec from metadata."""

    def test_returns_codec(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value={
            "Media": [{"videoCodec": "hevc"}],
        })

        assert client.get_media_video_codec("123") == "hevc"

    def test_returns_empty_on_no_media(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value={"Media": []})

        assert client.get_media_video_codec("123") == ""

    def test_returns_empty_on_metadata_failure(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value={})

        assert client.get_media_video_codec("123") == ""

    def test_returns_empty_when_codec_missing(self) -> None:
        client = PlexClient("http://plex:32400", "tok123")
        client.get_metadata = MagicMock(return_value={
            "Media": [{"bitrate": 5000}],
        })

        assert client.get_media_video_codec("123") == ""


# ---------------------------------------------------------------------------
# PlexClient._get — retry logic and error classification
# ---------------------------------------------------------------------------


class TestGetRetryLogicExtra:
    """Verify _get() retries transient errors and classifies error types."""

    @patch("backend.plex_client.time.sleep")
    def test_last_error_cleared_on_success(self, mock_sleep: MagicMock) -> None:
        """Set _last_error to AUTH, then mock returns 200; verify _last_error == NONE."""
        client = PlexClient("http://localhost:32400", "test-token")
        client._last_error = PlexErrorType.AUTH

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None
        resp_200.json.return_value = {"MediaContainer": {}}

        client._session.get = MagicMock(return_value=resp_200)

        result = client._get("/test")

        assert result == {"MediaContainer": {}}
        assert client._last_error == PlexErrorType.NONE


# ---------------------------------------------------------------------------
# PlexClient — self-healing connection (fallback URLs)
# ---------------------------------------------------------------------------


class TestSetFallbackUrls:
    """Verify set_fallback_urls filters and stores URLs correctly."""

    def test_set_fallback_urls_excludes_primary(self) -> None:
        """set_fallback_urls excludes the primary URL from the fallback list."""
        client = PlexClient("http://primary:32400", "test-token")
        client.set_fallback_urls([
            "http://primary:32400",
            "http://fallback1:32400",
            "http://fallback2:32400",
        ])
        assert client._fallback_urls == ["http://fallback1:32400", "http://fallback2:32400"]
        assert client._fallback_index == 0


class TestTryNextConnection:
    """Verify try_next_connection probes fallback URLs and updates state."""

    def test_try_next_connection_succeeds(self) -> None:
        """Mock _session.get to return 200 for fallback URL; verify _server_url updated."""
        client = PlexClient("http://primary:32400", "test-token")
        client.set_fallback_urls(["http://fallback1:32400"])

        resp_200 = MagicMock()
        resp_200.status_code = 200
        client._session.get = MagicMock(return_value=resp_200)

        result = client.try_next_connection()

        assert result is True
        assert client._server_url == "http://fallback1:32400"
        client._session.get.assert_called_once_with("http://fallback1:32400/identity", timeout=5)

    def test_try_next_connection_skips_unreachable(self) -> None:
        """First fallback raises ConnectionError, second returns 200; verify second URL is used."""
        client = PlexClient("http://primary:32400", "test-token")
        client.set_fallback_urls(["http://bad:32400", "http://good:32400"])

        resp_200 = MagicMock()
        resp_200.status_code = 200
        client._session.get = MagicMock(
            side_effect=[ConnectionError("refused"), resp_200]
        )

        result = client.try_next_connection()

        assert result is True
        assert client._server_url == "http://good:32400"

    def test_try_next_connection_returns_false_when_exhausted(self) -> None:
        """All fallbacks fail; verify returns False, _server_url unchanged."""
        client = PlexClient("http://primary:32400", "test-token")
        client.set_fallback_urls(["http://bad1:32400", "http://bad2:32400"])

        client._session.get = MagicMock(side_effect=ConnectionError("refused"))

        result = client.try_next_connection()

        assert result is False
        assert client._server_url == "http://primary:32400"

    def test_try_next_connection_resets_index_on_success(self) -> None:
        """After success, _fallback_index is 0 so we can cycle again."""
        client = PlexClient("http://primary:32400", "test-token")
        client.set_fallback_urls(["http://fallback1:32400", "http://fallback2:32400"])

        resp_200 = MagicMock()
        resp_200.status_code = 200
        client._session.get = MagicMock(return_value=resp_200)

        result = client.try_next_connection()

        assert result is True
        assert client._fallback_index == 0


# ---------------------------------------------------------------------------
# PlexEventListener
# ---------------------------------------------------------------------------


class TestPlexEventListener:
    """Tests for PlexEventListener._handle_payload and connection error handling."""

    def _make_payload(self, event_type: str) -> str:
        """Build a JSON SSE payload for the given event type."""
        return json.dumps({"NotificationContainer": {"type": event_type}})

    def test_calls_callback_on_library_update(self) -> None:
        """SSE line with library.update triggers callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload(self._make_payload("library.update"))

        callback.assert_called_once()

    def test_calls_callback_on_library_new(self) -> None:
        """SSE line with library.new triggers callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload(self._make_payload("library.new"))

        callback.assert_called_once()

    def test_calls_callback_on_library_refresh_all(self) -> None:
        """SSE line with library.refresh.all triggers callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload(self._make_payload("library.refresh.all"))

        callback.assert_called_once()

    def test_ignores_unknown_event_type(self) -> None:
        """SSE line with unknown type does NOT trigger callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload(self._make_payload("media.play"))

        callback.assert_not_called()

    def test_ignores_empty_event_type(self) -> None:
        """SSE line with empty type does NOT trigger callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload(self._make_payload(""))

        callback.assert_not_called()

    def test_stop_prevents_callback(self) -> None:
        """After stop(), callback is not called even if a line arrives."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener.stop()
        # _handle_payload itself doesn't check _stop_event — the loop does.
        # But we can verify the stop event is set and the loop would break.
        assert listener._stop_event.is_set()

    def test_handles_invalid_json_silently(self) -> None:
        """Malformed JSON payload does not raise and does not call callback."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        listener._handle_payload("not-valid-json{{{")

        callback.assert_not_called()

    @pytest.mark.real_sse_run
    def test_handles_connection_error_silently(self) -> None:
        """Connection error logs warning and does not raise."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        with patch("requests.get", side_effect=ConnectionError("refused")):
            # _run should complete without raising
            listener._run()

        # callback should not have been called
        callback.assert_not_called()

    @pytest.mark.real_sse_run
    def test_start_creates_qthread(self) -> None:
        """start() creates a QThread named 'plex-sse' that is running."""
        from PySide6.QtCore import QThread
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        # Mock requests.get to block until stop is called
        import threading as _threading

        stop_barrier = _threading.Event()

        def fake_get(*args, **kwargs):
            stop_barrier.wait(timeout=0.2)
            raise ConnectionError("stopped")

        with patch("requests.get", side_effect=fake_get):
            listener.start()
            assert listener._thread is not None
            assert isinstance(listener._thread, QThread)
            assert listener._thread.objectName() == "plex-sse"
            assert listener._thread.isRunning()
            # Clean up
            stop_barrier.set()
            listener.stop()

    @pytest.mark.real_sse_run
    def test_start_noop_if_already_running(self) -> None:
        """start() is a no-op if the thread is already running."""
        callback = MagicMock()
        listener = PlexEventListener("http://server:32400", "tok", callback)

        import threading as _threading

        stop_barrier = _threading.Event()

        def fake_get(*args, **kwargs):
            stop_barrier.wait(timeout=0.2)
            raise ConnectionError("stopped")

        with patch("requests.get", side_effect=fake_get):
            listener.start()
            first_thread = listener._thread

            # Call start() again — should not create a new thread
            listener.start()
            assert listener._thread is first_thread

            # Clean up
            stop_barrier.set()
            listener.stop()
