"""Plex playback timeline reporter.

Sends POST /:/timeline heartbeats to the Plex server while MPV is playing.
Required for watch state, resume position, and "Now Playing" on other clients.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Optional

from PySide6.QtCore import QObject, QThread, Slot

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 10  # seconds between timeline reports
_IDENTIFIER = "com.plexapp.plugins.library"


class _TimelineWorker(QObject):
    """QObject worker that runs the heartbeat loop on a QThread."""

    def __init__(self, reporter: "PlexTimelineReporter") -> None:
        super().__init__()
        self._reporter = reporter

    @Slot()
    def start(self) -> None:
        """Heartbeat loop — runs on the QThread. Called via QThread.started signal."""
        self._reporter._send_report("playing")
        while not self._reporter._stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
            with self._reporter._lock:
                state = "paused" if self._reporter._paused else "playing"
            self._reporter._send_report(state)


class PlexTimelineReporter:
    """Sends /:/timeline heartbeats to Plex while MPV is playing.

    Position is updated via push-based property observers (observe_time_pos /
    observe_pause on LibMpvPlayer) rather than polled via IPC.

    Usage:
        reporter = PlexTimelineReporter(client)
        reporter.start(rating_key, duration_ms, start_ms)   # on MPV launch
        reporter.update_position(30.5)                       # called by time-pos observer
        reporter.update_paused(True)                         # called by pause observer
        reporter.stop()                                      # on MPV exit
    """

    def __init__(self, client_factory) -> None:
        """
        client_factory: callable that returns the current PlexClient or None.
        Using a factory (not a direct reference) so we always get the live client
        even if it changes between sessions.
        """
        self._client_factory = client_factory
        self._thread: Optional[QThread] = None
        self._worker: Optional[_TimelineWorker] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Current session state
        self._rating_key: str = ""
        self._duration_ms: int = 0
        self._session_id: str = ""
        self._paused: bool = False
        self._position_ms: int = 0  # updated by observer

    def start(
        self,
        rating_key: str,
        duration_ms: int,
        start_ms: int = 0,
        play_queue_item_id: int = 0,
    ) -> None:
        """Begin reporting for a new playback session.

        rating_key:  Plex ratingKey of the item being played.
        duration_ms: Total duration of the item in milliseconds.
        start_ms:    Resume offset in milliseconds (0 = from beginning).
                     Used to seed the initial position before the first observer callback.
        play_queue_item_id: Plex playQueueItemID for Companion/Up Next support.
        """
        self.stop()  # stop any previous session

        with self._lock:
            self._rating_key = rating_key
            self._duration_ms = duration_ms
            self._session_id = str(uuid.uuid4())
            self._paused = False
            self._position_ms = start_ms  # seed with resume position
            self._play_queue_item_id: int = play_queue_item_id

        self._stop_event.clear()
        self._thread = QThread()
        self._thread.setObjectName("plex-timeline")
        self._worker = _TimelineWorker(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._thread.start()
        logger.info(
            "PlexTimelineReporter: started for ratingKey=%s session=%s",
            rating_key, self._session_id,
        )

    def update_position(self, pos_seconds: float) -> None:
        """Update the current playback position. Called by the time-pos observer."""
        with self._lock:
            self._position_ms = int(pos_seconds * 1000)

    def update_paused(self, paused: bool) -> None:
        """Update pause state and trigger an immediate report. Called by the pause observer."""
        with self._lock:
            self._paused = paused
        self._report_now()

    def set_paused(self, paused: bool) -> None:
        """Update pause state. Alias for update_paused for backward compatibility."""
        self.update_paused(paused)

    def stop(self) -> None:
        """Stop reporting and send a final 'stopped' report."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._send_report("stopped")
        logger.info("PlexTimelineReporter: stopped for ratingKey=%s", self._rating_key)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Heartbeat loop — kept for test compatibility; production code uses _TimelineWorker."""
        self._send_report("playing")
        while not self._stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
            with self._lock:
                state = "paused" if self._paused else "playing"
            self._send_report(state)

    def _current_position_ms(self) -> int:
        """Return current playback position in milliseconds.

        Returns the last position pushed by the time-pos observer.
        """
        with self._lock:
            return self._position_ms

    def _report_now(self) -> None:
        """Send an immediate report (used on pause/resume)."""
        with self._lock:
            state = "paused" if self._paused else "playing"
        self._send_report(state)

    def _send_report(self, state: str) -> None:
        """POST /:/timeline — fire and forget."""
        client = self._client_factory()
        if client is None:
            return
        with self._lock:
            rating_key = self._rating_key
            duration_ms = self._duration_ms
            session_id = self._session_id

        if not rating_key:
            return

        position_ms = self._current_position_ms()

        try:
            client.report_timeline(
                rating_key=rating_key,
                state=state,
                time_ms=position_ms,
                duration_ms=duration_ms,
                session_id=session_id,
                play_queue_item_id=self._play_queue_item_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("PlexTimelineReporter: report failed: %s", exc)
