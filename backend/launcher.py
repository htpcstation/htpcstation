"""Emulator process launcher for HTPC Station.

Manages launching and monitoring external emulator processes via QProcess.
Only one process may be active at a time.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal

logger = logging.getLogger(__name__)


class Launcher(QObject):
    """Launches emulator processes and monitors their lifecycle.

    Only one process may be active at a time.  If :meth:`launch` is called
    while a process is already running the request is silently ignored.

    Signals:
        processStarted() — emitted when the emulator process starts successfully.
        processFinished(exit_code, elapsed_seconds) — emitted when the
            launched process exits.  ``exit_code`` is -1 when the process
            failed to start.
    """

    processStarted = Signal()                # emitted when emulator starts successfully
    processFinished = Signal(int, int)  # exit_code, elapsed_seconds

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._process: Optional[QProcess] = None
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch(self, command: list[str]) -> None:
        """Launch a process with the given argv list.

        Returns immediately without blocking.  Outcome is reported via the
        ``processStarted`` and ``processFinished`` signals.

        Does nothing if a process is already running or the command list is
        empty.
        """
        if not command:
            logger.error("Launcher.launch: empty command — ignoring")
            return

        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "Launcher.launch: a process is already running — ignoring new launch request"
            )
            return

        program = command[0]
        args = command[1:]

        logger.info("Launcher: starting %s %s", program, " ".join(args))

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

    def _on_started(self) -> None:
        """Handle QProcess.started — process is confirmed running."""
        if self._process is not None:
            logger.info("Launcher: process started (pid=%s)", self._process.processId())
        self.processStarted.emit()

    def _on_error_occurred(self, error: QProcess.ProcessError) -> None:
        """Handle QProcess.errorOccurred — only act on FailedToStart."""
        if error != QProcess.ProcessError.FailedToStart:
            # Crashed/Timedout/WriteError/ReadError happen after the process is
            # running; they are already covered by the finished signal.
            return

        program = self._process.program() if self._process is not None else "<unknown>"
        error_string = self._process.errorString() if self._process is not None else ""
        logger.error("Launcher: failed to start '%s': %s", program, error_string)

        if self._process is not None:
            self._process.started.disconnect(self._on_started)
            self._process.errorOccurred.disconnect(self._on_error_occurred)
            self._process.finished.disconnect(self._on_finished)
            self._process = None

        self.processFinished.emit(-1, 0)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        logger.info(
            "Launcher: process finished — exit_code=%d exit_status=%s elapsed=%ds",
            exit_code,
            exit_status,
            elapsed,
        )
        self._process = None
        self.processFinished.emit(exit_code, elapsed)
