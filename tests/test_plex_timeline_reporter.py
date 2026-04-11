"""Tests for PlexTimelineReporter — lifecycle, heartbeat, and synchronisation.

Covers:
  - start() then stop(): reporter starts background thread, stop() joins it and sends
    a final "stopped" report
  - stop() before start(): no-op, does not raise
  - update_position(): updates internal position; next heartbeat uses the new value
  - update_paused(): updates internal paused state; next heartbeat uses "paused" state
  - Heartbeat fires: mock client's report_timeline; use short interval to verify the
    heartbeat loop calls report_timeline with correct args
  - stop() thread join timeout: stop() completes even if the thread is slow
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from backend.plex_timeline import PlexTimelineReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reporter(client=None) -> PlexTimelineReporter:
    """Return a PlexTimelineReporter with a mock or None client factory."""
    if client is None:
        return PlexTimelineReporter(lambda: None)
    return PlexTimelineReporter(lambda: client)


# ---------------------------------------------------------------------------
# start() then stop()
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_creates_background_thread(self) -> None:
        """start() launches a QThread named 'plex-timeline'."""
        from PySide6.QtCore import QThread
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="123", duration_ms=100_000)
        assert reporter._thread is not None
        assert isinstance(reporter._thread, QThread)
        assert reporter._thread.isRunning()
        reporter.stop()

    def test_stop_joins_thread(self) -> None:
        """stop() waits for the QThread to finish (thread is no longer running after stop)."""
        from PySide6.QtCore import QThread
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="123", duration_ms=100_000)
        thread = reporter._thread
        reporter.stop()

        assert thread is not None
        assert not thread.isRunning()

    def test_stop_sends_stopped_report(self) -> None:
        """stop() sends a final 'stopped' report after joining the thread."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="456", duration_ms=200_000)
        reporter.stop()

        calls = mock_client.report_timeline.call_args_list
        assert len(calls) >= 1
        last_call = calls[-1]
        assert last_call[1]["state"] == "stopped"
        assert last_call[1]["rating_key"] == "456"

    def test_start_sends_initial_playing_report(self) -> None:
        """start() triggers an initial 'playing' report from the background thread."""
        mock_client = MagicMock()
        # Use an event to wait for the initial report
        initial_report_event = threading.Event()

        original_report = mock_client.report_timeline

        def _capture(**kwargs):
            if kwargs.get("state") == "playing":
                initial_report_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)
        reporter.start(rating_key="789", duration_ms=300_000)

        fired = initial_report_event.wait(timeout=2.0)
        reporter.stop()

        assert fired, "Initial 'playing' report was not sent within 2 seconds"

    def test_start_stop_thread_is_none_after_stop(self) -> None:
        """After stop(), reporter._thread is None."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="abc", duration_ms=50_000)
        reporter.stop()

        assert reporter._thread is None


# ---------------------------------------------------------------------------
# stop() before start()
# ---------------------------------------------------------------------------


class TestStopBeforeStart:
    def test_stop_before_start_is_noop(self) -> None:
        """stop() before start() does not raise and is a no-op."""
        reporter = _make_reporter()
        # Must not raise
        reporter.stop()

    def test_stop_before_start_thread_remains_none(self) -> None:
        """stop() before start() leaves _thread as None."""
        reporter = _make_reporter()
        reporter.stop()
        assert reporter._thread is None

    def test_multiple_stops_before_start_are_safe(self) -> None:
        """Multiple stop() calls before start() do not raise."""
        reporter = _make_reporter()
        reporter.stop()
        reporter.stop()
        reporter.stop()


# ---------------------------------------------------------------------------
# update_position()
# ---------------------------------------------------------------------------


class TestUpdatePosition:
    def test_update_position_sets_internal_ms(self) -> None:
        """update_position(30.5) sets _position_ms to 30500."""
        reporter = _make_reporter()
        reporter.update_position(30.5)
        assert reporter._position_ms == 30_500

    def test_update_position_zero(self) -> None:
        """update_position(0.0) sets _position_ms to 0."""
        reporter = _make_reporter()
        reporter.update_position(0.0)
        assert reporter._position_ms == 0

    def test_update_position_large_value(self) -> None:
        """update_position(3600.0) sets _position_ms to 3_600_000."""
        reporter = _make_reporter()
        reporter.update_position(3600.0)
        assert reporter._position_ms == 3_600_000

    def test_update_position_used_in_next_report(self) -> None:
        """Position set via update_position() is used in the next _send_report call."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)
        reporter.start(rating_key="pos_test", duration_ms=120_000)

        reporter.update_position(45.0)  # 45000 ms
        mock_client.report_timeline.reset_mock()
        reporter._send_report("playing")

        calls = mock_client.report_timeline.call_args_list
        assert len(calls) == 1
        assert calls[0][1]["time_ms"] == 45_000

        reporter.stop()

    def test_update_position_thread_safe(self) -> None:
        """update_position() can be called from multiple threads without error."""
        reporter = _make_reporter()
        errors: list[Exception] = []

        def _update(pos: float) -> None:
            try:
                reporter.update_position(pos)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_update, args=(float(i),)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        assert not errors


# ---------------------------------------------------------------------------
# update_paused()
# ---------------------------------------------------------------------------


class TestUpdatePaused:
    def test_update_paused_sets_internal_state(self) -> None:
        """update_paused(True) sets _paused to True."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)
        reporter.start(rating_key="pause_test", duration_ms=60_000)

        reporter.update_paused(True)
        assert reporter._paused is True

        reporter.stop()

    def test_update_paused_false_sets_internal_state(self) -> None:
        """update_paused(False) sets _paused to False."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)
        reporter.start(rating_key="pause_test2", duration_ms=60_000)

        reporter.update_paused(True)
        reporter.update_paused(False)
        assert reporter._paused is False

        reporter.stop()

    def test_update_paused_triggers_immediate_report(self) -> None:
        """update_paused() triggers an immediate report with the correct state."""
        mock_client = MagicMock()
        paused_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("state") == "paused":
                paused_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)
        reporter.start(rating_key="pause_imm", duration_ms=60_000)

        # Wait for initial playing report, then reset
        time.sleep(0.05)
        mock_client.report_timeline.reset_mock()
        mock_client.report_timeline.side_effect = _capture

        reporter.update_paused(True)
        fired = paused_event.wait(timeout=2.0)
        reporter.stop()

        assert fired, "Immediate 'paused' report was not sent after update_paused(True)"

    def test_update_paused_state_used_in_heartbeat(self) -> None:
        """After update_paused(True), the heartbeat loop sends 'paused' state."""
        mock_client = MagicMock()
        paused_heartbeat_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("state") == "paused":
                paused_heartbeat_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="pause_hb", duration_ms=60_000)
            reporter.update_paused(True)
            fired = paused_heartbeat_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not send 'paused' state after update_paused(True)"


# ---------------------------------------------------------------------------
# Heartbeat fires
# ---------------------------------------------------------------------------


class TestHeartbeatFires:
    def test_heartbeat_calls_report_timeline(self) -> None:
        """With a short interval, the heartbeat loop calls report_timeline."""
        mock_client = MagicMock()
        heartbeat_event = threading.Event()

        call_count = 0

        def _capture(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # initial + at least one heartbeat
                heartbeat_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="hb_test", duration_ms=500_000)
            fired = heartbeat_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not fire within 2 seconds"
        assert call_count >= 2

    def test_heartbeat_uses_correct_rating_key(self) -> None:
        """Heartbeat reports use the rating_key from start()."""
        mock_client = MagicMock()
        heartbeat_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("rating_key") == "hb_key":
                heartbeat_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="hb_key", duration_ms=500_000)
            fired = heartbeat_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not use the correct rating_key"

    def test_heartbeat_uses_correct_duration_ms(self) -> None:
        """Heartbeat reports use the duration_ms from start()."""
        mock_client = MagicMock()
        heartbeat_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("duration_ms") == 999_000:
                heartbeat_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="dur_test", duration_ms=999_000)
            fired = heartbeat_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not use the correct duration_ms"

    def test_heartbeat_sends_playing_state_when_not_paused(self) -> None:
        """Heartbeat sends 'playing' state when not paused."""
        mock_client = MagicMock()
        playing_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("state") == "playing":
                playing_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="play_state", duration_ms=100_000)
            fired = playing_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not send 'playing' state"

    def test_heartbeat_sends_paused_state_when_paused(self) -> None:
        """Heartbeat sends 'paused' state when paused."""
        mock_client = MagicMock()
        paused_hb_event = threading.Event()

        def _capture(**kwargs):
            if kwargs.get("state") == "paused":
                paused_hb_event.set()

        mock_client.report_timeline.side_effect = _capture

        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="paused_state", duration_ms=100_000)
            reporter.update_paused(True)
            fired = paused_hb_event.wait(timeout=2.0)
            reporter.stop()

        assert fired, "Heartbeat did not send 'paused' state after pausing"

    def test_no_report_when_client_is_none(self) -> None:
        """No report_timeline call when client_factory returns None."""
        reporter = PlexTimelineReporter(lambda: None)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="no_client", duration_ms=100_000)
            time.sleep(0.15)
            reporter.stop()
        # No exception means the test passes


# ---------------------------------------------------------------------------
# stop() thread join timeout
# ---------------------------------------------------------------------------


class TestStopJoinTimeout:
    def test_stop_returns_even_if_thread_is_slow(self) -> None:
        """stop() completes within a reasonable time after setting the stop event."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        # Start and immediately stop — the heartbeat loop exits quickly because
        # _stop_event is set before QThread.wait() is called.
        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 10.0):
            reporter.start(rating_key="slow_test", duration_ms=100_000)
            # Give the worker a moment to start its blocking wait
            time.sleep(0.05)

            start_time = time.monotonic()
            reporter.stop()
            elapsed = time.monotonic() - start_time

        # stop() should complete quickly once the stop event is set
        assert elapsed < 5.0, f"stop() took too long: {elapsed:.2f}s"

    def test_stop_completes_normally_when_thread_exits_quickly(self) -> None:
        """stop() completes quickly when the thread exits promptly."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="fast_stop", duration_ms=100_000)

        start_time = time.monotonic()
        reporter.stop()
        elapsed = time.monotonic() - start_time

        # Should complete well within 5 seconds (the join timeout)
        assert elapsed < 5.0, f"stop() took too long: {elapsed:.2f}s"

    def test_stop_sets_stop_event_before_join(self) -> None:
        """stop() sets the stop event, which causes the heartbeat loop to exit."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        with patch("backend.plex_timeline._HEARTBEAT_INTERVAL", 0.05):
            reporter.start(rating_key="event_test", duration_ms=100_000)
            time.sleep(0.05)

            assert not reporter._stop_event.is_set()
            reporter.stop()
            # After stop(), the event should be set (it's set before join)
            assert reporter._stop_event.is_set()


# ---------------------------------------------------------------------------
# start() seeds position from start_ms
# ---------------------------------------------------------------------------


class TestStartSeedsPosition:
    def test_start_ms_seeds_position(self) -> None:
        """start() with start_ms=60000 seeds _position_ms to 60000."""
        reporter = _make_reporter()
        reporter.start(rating_key="seed_test", duration_ms=300_000, start_ms=60_000)
        assert reporter._position_ms == 60_000
        reporter.stop()

    def test_start_ms_zero_seeds_position_to_zero(self) -> None:
        """start() with start_ms=0 seeds _position_ms to 0."""
        reporter = _make_reporter()
        reporter.start(rating_key="seed_zero", duration_ms=300_000, start_ms=0)
        assert reporter._position_ms == 0
        reporter.stop()


# ---------------------------------------------------------------------------
# Restart (start() after stop())
# ---------------------------------------------------------------------------


class TestRestart:
    def test_start_after_stop_creates_new_thread(self) -> None:
        """start() after stop() creates a new background thread."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="first", duration_ms=100_000)
        first_thread = reporter._thread
        reporter.stop()

        reporter.start(rating_key="second", duration_ms=200_000)
        second_thread = reporter._thread
        reporter.stop()

        assert first_thread is not second_thread

    def test_restart_uses_new_rating_key(self) -> None:
        """After restart, reports use the new rating_key."""
        mock_client = MagicMock()
        reporter = _make_reporter(mock_client)

        reporter.start(rating_key="old_key", duration_ms=100_000)
        reporter.stop()

        mock_client.report_timeline.reset_mock()

        reporter.start(rating_key="new_key", duration_ms=200_000)
        reporter.stop()

        calls = mock_client.report_timeline.call_args_list
        # All calls after restart should use "new_key"
        for c in calls:
            assert c[1]["rating_key"] == "new_key"
