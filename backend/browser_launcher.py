"""Browser process launcher for HTPC Station.

Manages launching and monitoring a browser process (Brave in kiosk mode)
via QProcess. Only one browser instance may be active at a time.
"""

from __future__ import annotations

import glob
import logging
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal

logger = logging.getLogger(__name__)


class BrowserLauncher(QObject):
    """Launches browser in kiosk mode and monitors lifecycle.

    Only one browser process may be active at a time.  If :meth:`launch` is
    called while a browser is already running the request is silently ignored.

    Signals:
        processFinished(exit_code) — emitted when the browser process exits.
            ``exit_code`` is -1 when the process failed to start.
    """

    processStarted = Signal()     # emitted when browser starts successfully
    processFinished = Signal(int)  # exit_code

    def __init__(self, browser_command: str = "flatpak run com.brave.Browser", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._browser_command = browser_command
        self._process: Optional[QProcess] = None
        self._start_time: float = 0.0
        # Brave flatpak default profile — session files are cleared before
        # each launch to prevent tab accumulation, but cookies/login persist.
        self._browser_profile_dir = (
            Path.home() / ".var" / "app" / "com.brave.Browser"
            / "config" / "BraveSoftware" / "Brave-Browser" / "Default"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch(self, url: str) -> None:
        """Launch browser in kiosk mode at the given URL.

        The browser command is split into tokens; ``--kiosk`` and the URL are
        appended automatically.

        Returns immediately without blocking.  Outcome is reported via the
        ``processStarted`` and ``processFinished`` signals.

        Does nothing if a browser is already running or the URL is empty.
        """
        if not url:
            logger.error("BrowserLauncher.launch: empty URL — ignoring")
            return

        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "BrowserLauncher.launch: a browser is already running — ignoring new launch request"
            )
            return

        command = self._build_command(url)
        program = command[0]
        args = command[1:]

        logger.info("BrowserLauncher: starting %s %s", program, " ".join(args))

        self._process = QProcess(self)
        # Connect signals before start() so no events are missed.
        self._process.started.connect(self._on_started)
        self._process.errorOccurred.connect(self._on_error_occurred)
        self._process.finished.connect(self._on_finished)

        self._start_time = time.monotonic()
        self._process.start(program, args)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(self, url: str) -> list[str]:
        """Build the argv list for the browser process."""
        tokens = self._browser_command.split()
        # Clear session restore files to prevent tab accumulation,
        # but keep the profile (cookies, Plex login, etc.)
        self._clear_session_state()
        return [*tokens, "--kiosk", "--start-fullscreen", url]

    def _clear_session_state(self) -> None:
        """Remove Chromium session restore files from the browser profile.

        This prevents tabs from accumulating across launches while
        preserving cookies, local storage, and other persistent data
        (e.g. Plex login).
        """
        profile = self._browser_profile_dir
        if not profile.exists():
            return

        # Sessions/ directory contains Session_* and Tabs_* files
        sessions_dir = profile / "Sessions"
        if sessions_dir.exists():
            import shutil
            try:
                shutil.rmtree(sessions_dir)
                logger.debug("BrowserLauncher: removed Sessions dir")
            except OSError as e:
                logger.warning("BrowserLauncher: failed to remove Sessions: %s", e)

        # Session Storage/ directory (LevelDB)
        session_storage = profile / "Session Storage"
        if session_storage.exists():
            import shutil
            try:
                shutil.rmtree(session_storage)
                logger.debug("BrowserLauncher: removed Session Storage dir")
            except OSError as e:
                logger.warning("BrowserLauncher: failed to remove Session Storage: %s", e)

    def _on_started(self) -> None:
        """Handle QProcess.started — browser process is confirmed running."""
        if self._process is not None:
            logger.info(
                "BrowserLauncher: browser started (pid=%s)", self._process.processId()
            )
        self.processStarted.emit()

    def _on_error_occurred(self, error: QProcess.ProcessError) -> None:
        """Handle QProcess.errorOccurred — only act on FailedToStart."""
        if error != QProcess.ProcessError.FailedToStart:
            # Crashed/Timedout/WriteError/ReadError happen after the process is
            # running; they are already covered by the finished signal.
            return

        program = self._process.program() if self._process is not None else "<unknown>"
        error_string = self._process.errorString() if self._process is not None else ""
        logger.error("BrowserLauncher: failed to start '%s': %s", program, error_string)

        if self._process is not None:
            self._process.started.disconnect(self._on_started)
            self._process.errorOccurred.disconnect(self._on_error_occurred)
            self._process.finished.disconnect(self._on_finished)
            self._process = None

        self.processFinished.emit(-1)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        logger.info(
            "BrowserLauncher: browser finished — exit_code=%d exit_status=%s elapsed=%ds",
            exit_code,
            exit_status,
            elapsed,
        )
        self._process = None
        self.processFinished.emit(exit_code)
