"""Tests for PlexTimelineReporter — heartbeat lifecycle and error handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest

from backend.plex_timeline import PlexTimelineReporter, _HEARTBEAT_INTERVAL


class TestTimelineReporterStart:
    """Verify that starting the reporter sends an initial 'playing' report."""

    def test_start_sends_playing_report(self) -> None:
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="123", duration_ms=100000, start_ms=0)
        # Give the thread a moment to send the initial report
        time.sleep(0.3)
        reporter.stop()

        # The initial report should be 'playing', the final should be 'stopped'
        calls = mock_client.report_timeline.call_args_list
        assert len(calls) >= 1
        # First call should be 'playing'
        assert calls[0][1]["state"] == "playing"
        assert calls[0][1]["rating_key"] == "123"
        assert calls[0][1]["duration_ms"] == 100000


class TestTimelineReporterStop:
    """Verify that stopping the reporter sends a 'stopped' report."""

    def test_stop_sends_stopped_report(self) -> None:
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="456", duration_ms=200000)
        time.sleep(0.3)
        reporter.stop()

        calls = mock_client.report_timeline.call_args_list
        # Last call should be 'stopped'
        assert calls[-1][1]["state"] == "stopped"


class TestTimelineReporterPause:
    """Verify that set_paused sends a 'paused' report."""

    def test_set_paused_sends_paused_report(self) -> None:
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="789", duration_ms=300000)
        time.sleep(0.3)
        reporter.set_paused(True)
        time.sleep(0.1)
        reporter.stop()

        states = [c[1]["state"] for c in mock_client.report_timeline.call_args_list]
        assert "paused" in states


class TestTimelineReporterHeartbeat:
    """Verify that the heartbeat fires at the configured interval."""

    def test_heartbeat_fires_at_interval(self) -> None:
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)

        # Use a short interval for testing by patching the module constant
        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.2):
            reporter.start(rating_key="111", duration_ms=500000)
            time.sleep(0.8)
            reporter.stop()

        # Should have initial report + at least 2 heartbeats + stopped
        calls = mock_client.report_timeline.call_args_list
        assert len(calls) >= 4  # initial + 2-3 heartbeats + stopped


class TestTimelineReporterNoClient:
    """Verify no exception when client_factory returns None."""

    def test_no_report_when_no_client(self) -> None:
        reporter = PlexTimelineReporter(lambda: None)

        # Should not raise
        reporter.start(rating_key="999", duration_ms=100000)
        time.sleep(0.3)
        reporter.stop()
        # If we get here without exception, the test passes


class TestTimelineReporterPlayQueueItemId:
    """Verify that play_queue_item_id is passed through to report_timeline."""

    def test_start_passes_play_queue_item_id_to_report(self) -> None:
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="123", duration_ms=100000, play_queue_item_id=42)
        time.sleep(0.3)
        reporter.stop()

        # At least one call should have play_queue_item_id=42
        calls = mock_client.report_timeline.call_args_list
        assert len(calls) >= 1
        for c in calls:
            assert c[1]["play_queue_item_id"] == 42


class TestTimelineReporterStopIdempotent:
    """Verify that calling stop() when not started is safe."""

    def test_stop_when_not_started(self) -> None:
        reporter = PlexTimelineReporter(lambda: None)
        # Should not raise
        reporter.stop()


class TestPlexTimelineReporterPush:
    """Tests for the push-based position/pause update interface."""

    def test_update_position_updates_internal_state(self) -> None:
        """update_position(30.5) sets _position_ms to 30500."""
        reporter = PlexTimelineReporter(lambda: None)
        reporter.update_position(30.5)
        assert reporter._position_ms == 30500

    def test_update_paused_triggers_report(self) -> None:
        """update_paused(True) triggers an immediate report."""
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)
        reporter.start(rating_key="abc", duration_ms=60000)
        time.sleep(0.1)
        mock_client.report_timeline.reset_mock()

        reporter.update_paused(True)
        time.sleep(0.1)
        reporter.stop()

        # At least one call should have state='paused'
        states = [c[1]["state"] for c in mock_client.report_timeline.call_args_list]
        assert "paused" in states

    def test_position_used_in_report(self) -> None:
        """Position set via update_position is used in the next report."""
        mock_client = MagicMock()
        reporter = PlexTimelineReporter(lambda: mock_client)
        reporter.start(rating_key="xyz", duration_ms=120000)
        time.sleep(0.1)

        reporter.update_position(5.0)  # 5000 ms
        mock_client.report_timeline.reset_mock()
        reporter._send_report("playing")

        calls = mock_client.report_timeline.call_args_list
        assert len(calls) == 1
        assert calls[0][1]["time_ms"] == 5000
        reporter.stop()

    def test_start_seeds_position_from_start_ms(self) -> None:
        """start() with start_ms=60000 seeds _position_ms to 60000."""
        reporter = PlexTimelineReporter(lambda: None)
        reporter.start(rating_key="def", duration_ms=300000, start_ms=60000)
        assert reporter._position_ms == 60000
        reporter.stop()
