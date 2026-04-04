"""Tests for PlexClient — identity headers, timeline reporting, track persistence, retry logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.plex_client import PlexClient, PlexErrorType


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


class TestGetMetadataWithMarkers:
    """Verify get_metadata sends includeMarkers param when requested."""

    def test_get_metadata_with_markers_sends_param(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {
                "Metadata": [{"ratingKey": "123", "title": "Test"}]
            }
        })

        client.get_metadata("123", include_markers=True)

        client._get.assert_called_once_with(
            "/library/metadata/123", params={"includeMarkers": 1}
        )

    def test_get_metadata_without_markers_no_param(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        client._get = MagicMock(return_value={
            "MediaContainer": {
                "Metadata": [{"ratingKey": "123", "title": "Test"}]
            }
        })

        client.get_metadata("123")

        client._get.assert_called_once_with(
            "/library/metadata/123", params=None
        )


class TestGetMarkers:
    """Verify get_markers extracts intro and credits markers correctly."""

    def test_get_markers_extracts_intro(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        metadata = {
            "Marker": [
                {
                    "type": "intro",
                    "startTimeOffset": 5000,
                    "endTimeOffset": 90000,
                }
            ]
        }

        result = client.get_markers(metadata)

        assert result["intro_start_ms"] == 5000
        assert result["intro_end_ms"] == 90000
        assert result["credits_start_ms"] == 0

    def test_get_markers_extracts_credits(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        metadata = {
            "Marker": [
                {
                    "type": "credits",
                    "startTimeOffset": 3500000,
                    "endTimeOffset": 3600000,
                }
            ]
        }

        result = client.get_markers(metadata)

        assert result["intro_start_ms"] == 0
        assert result["intro_end_ms"] == 0
        assert result["credits_start_ms"] == 3500000

    def test_get_markers_returns_zeros_when_no_markers(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        metadata = {}

        result = client.get_markers(metadata)

        assert result == {"intro_start_ms": 0, "intro_end_ms": 0, "credits_start_ms": 0}

    def test_get_markers_handles_both_intro_and_credits(self) -> None:
        client = PlexClient("http://localhost:32400", "test-token")
        metadata = {
            "Marker": [
                {
                    "type": "intro",
                    "startTimeOffset": 1000,
                    "endTimeOffset": 60000,
                },
                {
                    "type": "credits",
                    "startTimeOffset": 3000000,
                    "endTimeOffset": 3600000,
                },
            ]
        }

        result = client.get_markers(metadata)

        assert result["intro_start_ms"] == 1000
        assert result["intro_end_ms"] == 60000
        assert result["credits_start_ms"] == 3000000


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
