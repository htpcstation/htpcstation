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

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 10  # seconds between timeline reports
_IDENTIFIER = "com.plexapp.plugins.library"


class PlexTimelineReporter:
    """Sends /:/timeline heartbeats to Plex while MPV is playing.

    Usage:
        reporter = PlexTimelineReporter(client)
        reporter.start(rating_key, duration_ms, start_ms)   # on MPV launch
        reporter.set_paused(True)                            # on pause
        reporter.set_paused(False)                           # on resume
        reporter.stop()                                      # on MPV exit
    """

    def __init__(self, client_factory) -> None:
        """
        client_factory: callable that returns the current PlexClient or None.
        Using a factory (not a direct reference) so we always get the live client
        even if it changes between sessions.
        """
        self._client_factory = client_factory
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Current session state
        self._rating_key: str = ""
        self._duration_ms: int = 0
        self._session_id: str = ""
        self._paused: bool = False
        self._mpv_ipc = None  # set in start()

    def start(
        self,
        rating_key: str,
        duration_ms: int,
        start_ms: int = 0,
        mpv_ipc=None,
    ) -> None:
        """Begin reporting for a new playback session.

        rating_key:  Plex ratingKey of the item being played.
        duration_ms: Total duration of the item in milliseconds.
        start_ms:    Resume offset in milliseconds (0 = from beginning).
        mpv_ipc:     MpvIpc instance for reading current position. If None,
                     position is estimated from elapsed time.
        """
        self.stop()  # stop any previous session

        with self._lock:
            self._rating_key = rating_key
            self._duration_ms = duration_ms
            self._session_id = str(uuid.uuid4())
            self._paused = False
            self._mpv_ipc = mpv_ipc
            self._start_ms = start_ms
            self._start_wall = time.monotonic()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="plex-timeline", daemon=True
        )
        self._thread.start()
        logger.info(
            "PlexTimelineReporter: started for ratingKey=%s session=%s",
            rating_key, self._session_id,
        )

    def set_paused(self, paused: bool) -> None:
        """Update pause state. Triggers an immediate report."""
        with self._lock:
            self._paused = paused
        self._report_now()

    def stop(self) -> None:
        """Stop reporting and send a final 'stopped' report."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        self._send_report("stopped")
        logger.info("PlexTimelineReporter: stopped for ratingKey=%s", self._rating_key)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Heartbeat loop — runs on the reporter thread."""
        # Send initial 'playing' report immediately
        self._send_report("playing")
        while not self._stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
            with self._lock:
                state = "paused" if self._paused else "playing"
            self._send_report(state)

    def _current_position_ms(self) -> int:
        """Return current playback position in milliseconds.

        Reads from MPV IPC if available; falls back to wall-clock estimate.
        """
        if self._mpv_ipc is not None:
            try:
                pos = self._mpv_ipc.command("get_property", "time-pos")
                if isinstance(pos, (int, float)) and pos >= 0:
                    return int(pos * 1000)
            except Exception:  # noqa: BLE001
                pass
        # Fallback: estimate from elapsed wall time
        with self._lock:
            elapsed = time.monotonic() - self._start_wall
            if self._paused:
                return self._start_ms
            return min(self._start_ms + int(elapsed * 1000), self._duration_ms)

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
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("PlexTimelineReporter: report failed: %s", exc)
