"""Tests for PlexClient — identity headers, timeline reporting, track persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.plex_client import PlexClient


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
