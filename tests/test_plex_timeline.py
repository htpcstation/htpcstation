"""Tests for PlexTimelineReporter — heartbeat lifecycle and error handling."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

from backend.plex_timeline import PlexTimelineReporter, _HEARTBEAT_INTERVAL


def _make_signaling_mock(n: int = 1) -> tuple[MagicMock, threading.Event]:
    """Return a mock and an Event that is set after n calls to report_timeline."""
    event = threading.Event()
    call_count = [0]

    def _side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] >= n:
            event.set()

    mock_client = MagicMock()
    mock_client.report_timeline.side_effect = _side_effect
    return mock_client, event


class TestTimelineReporterStart:
    """Verify that starting the reporter sends an initial 'playing' report."""

    def test_start_sends_playing_report(self) -> None:
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="123", duration_ms=100000, start_ms=0)
        # Wait until the initial report fires (up to 2s, normally <50ms)
        assert report_event.wait(timeout=2), "Initial report never sent"
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
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="456", duration_ms=200000)
        assert report_event.wait(timeout=2), "Initial report never sent"
        reporter.stop()

        calls = mock_client.report_timeline.call_args_list
        # Last call should be 'stopped'
        assert calls[-1][1]["state"] == "stopped"


class TestTimelineReporterPause:
    """Verify that set_paused sends a 'paused' report."""

    def test_set_paused_sends_paused_report(self) -> None:
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="789", duration_ms=300000)
        assert report_event.wait(timeout=2), "Initial report never sent"

        # Now track whether a paused state appears
        paused_event = threading.Event()
        original_side_effect = mock_client.report_timeline.side_effect

        def _check_paused(*args, **kwargs):
            if kwargs.get("state") == "paused" or (args and args[0] == "paused"):
                paused_event.set()

        mock_client.report_timeline.side_effect = _check_paused
        reporter.set_paused(True)
        assert paused_event.wait(timeout=2), "Paused report never sent"
        reporter.stop()

        states = [c[1]["state"] for c in mock_client.report_timeline.call_args_list]
        assert "paused" in states


class TestTimelineReporterHeartbeat:
    """Verify that the heartbeat fires at the configured interval."""

    def test_heartbeat_fires_at_interval(self) -> None:
        # Wait for 4 calls: initial + 2-3 heartbeats + stop handled separately
        mock_client, report_event = _make_signaling_mock(n=4)
        reporter = PlexTimelineReporter(lambda: mock_client)

        # Use a short interval for testing by patching the module constant
        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.1):
            reporter.start(rating_key="111", duration_ms=500000)
            # Wait up to 2s for 4 reports at 0.1s interval
            assert report_event.wait(timeout=2), "Not enough heartbeats fired"
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
        # Give a brief moment for thread to start; no report to wait on since client is None
        time.sleep(0.05)
        reporter.stop()
        # If we get here without exception, the test passes


class TestTimelineReporterPlayQueueItemId:
    """Verify that play_queue_item_id is passed through to report_timeline."""

    def test_start_passes_play_queue_item_id_to_report(self) -> None:
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)

        reporter.start(rating_key="123", duration_ms=100000, play_queue_item_id=42)
        assert report_event.wait(timeout=2), "Initial report never sent"
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
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)
        reporter.start(rating_key="abc", duration_ms=60000)
        assert report_event.wait(timeout=2), "Initial report never sent"
        mock_client.report_timeline.reset_mock()

        paused_event = threading.Event()

        def _check_paused(*args, **kwargs):
            if kwargs.get("state") == "paused":
                paused_event.set()

        mock_client.report_timeline.side_effect = _check_paused
        reporter.update_paused(True)
        assert paused_event.wait(timeout=2), "Paused report never sent"
        reporter.stop()

        # At least one call should have state='paused'
        states = [c[1]["state"] for c in mock_client.report_timeline.call_args_list]
        assert "paused" in states

    def test_position_used_in_report(self) -> None:
        """Position set via update_position is used in the next report."""
        mock_client, report_event = _make_signaling_mock(n=1)
        reporter = PlexTimelineReporter(lambda: mock_client)
        reporter.start(rating_key="xyz", duration_ms=120000)
        assert report_event.wait(timeout=2), "Initial report never sent"

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
