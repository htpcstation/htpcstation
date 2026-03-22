"""Moonlight CLI client — app enumeration and streaming launch.

Provides:
  - ``list_apps``: synchronous function to enumerate apps on a paired host.
  - ``MoonlightLauncher``: QObject that manages a streaming session via QProcess.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal

logger = logging.getLogger(__name__)

# Default Moonlight command (Flatpak installation)
_DEFAULT_MOONLIGHT_COMMAND = "flatpak run com.moonlight_stream.Moonlight"

# Timeout in seconds for the `list` subcommand
_LIST_TIMEOUT = 10


# ---------------------------------------------------------------------------
# App enumeration
# ---------------------------------------------------------------------------


def list_apps(
    host_address: str,
    moonlight_command: Optional[str] = None,
) -> list[str]:
    """Enumerate apps available on a paired Moonlight host.

    Runs ``<moonlight_command> list <host_address>`` synchronously and parses
    the output.  Stderr is ignored (SDL/Qt noise).

    Args:
        host_address: IP address or hostname of the paired host.
        moonlight_command: Full command string for the Moonlight CLI.
            Defaults to ``"flatpak run com.moonlight_stream.Moonlight"``.

    Returns:
        A list of app name strings.  Returns an empty list on any error
        (timeout, non-zero exit, subprocess exception).
    """
    if moonlight_command is None:
        moonlight_command = _DEFAULT_MOONLIGHT_COMMAND

    cmd = shlex.split(moonlight_command) + ["list", host_address]
    logger.debug("list_apps: running %s", cmd)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_LIST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "list_apps: timed out after %ds listing apps on %s",
            _LIST_TIMEOUT,
            host_address,
        )
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("list_apps: subprocess error listing apps on %s: %s", host_address, exc)
        return []

    if result.returncode != 0:
        logger.error(
            "list_apps: command exited with code %d for host %s",
            result.returncode,
            host_address,
        )
        return []

    stdout = result.stdout.decode(errors="replace")
    apps = [line.strip() for line in stdout.splitlines() if line.strip()]
    logger.debug("list_apps: found %d app(s) on %s", len(apps), host_address)
    return apps


# ---------------------------------------------------------------------------
# Streaming launcher
# ---------------------------------------------------------------------------


class MoonlightLauncher(QObject):
    """Launches Moonlight streaming sessions and monitors their lifecycle.

    Only one process may be active at a time.  If :meth:`launch` is called
    while a process is already running the request is silently ignored.

    Signals:
        processStarted() — emitted when the streaming process starts successfully.
        processFinished(exit_code, elapsed_seconds) — emitted when the
            streaming process exits.  ``exit_code`` is -1 when the process
            failed to start.
    """

    processStarted = Signal()          # emitted when streaming starts successfully
    processFinished = Signal(int, int)  # exit_code, elapsed_seconds

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._process: Optional[QProcess] = None
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch(
        self,
        host_address: str,
        app_name: str,
        moonlight_command: Optional[str] = None,
    ) -> None:
        """Launch a Moonlight streaming session for *app_name* on *host_address*.

        Returns immediately without blocking.  Outcome is reported via the
        ``processStarted`` and ``processFinished`` signals.

        Does nothing if a process is already running.

        Args:
            host_address: IP address or hostname of the paired host.
            app_name: Name of the app/game to stream.
            moonlight_command: Full command string for the Moonlight CLI.
                Defaults to ``"flatpak run com.moonlight_stream.Moonlight"``.
        """
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "MoonlightLauncher.launch: a process is already running — ignoring new launch request"
            )
            return

        if moonlight_command is None:
            moonlight_command = _DEFAULT_MOONLIGHT_COMMAND

        cmd = shlex.split(moonlight_command) + ["stream", host_address, app_name]
        self._start_process(cmd)

    def launch_gui(self, moonlight_command: Optional[str] = None) -> None:
        """Launch the Moonlight GUI (for pairing / host management).

        Starts Moonlight with no subcommand arguments so the GUI opens.
        Same QProcess lifecycle as :meth:`launch`.

        Args:
            moonlight_command: Full command string for the Moonlight CLI.
                Defaults to ``"flatpak run com.moonlight_stream.Moonlight"``.
        """
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "MoonlightLauncher.launch_gui: a process is already running — ignoring new launch request"
            )
            return

        if moonlight_command is None:
            moonlight_command = _DEFAULT_MOONLIGHT_COMMAND

        cmd = shlex.split(moonlight_command)
        self._start_process(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_process(self, cmd: list[str]) -> None:
        """Create and start a QProcess for *cmd*."""
        program = cmd[0]
        args = cmd[1:]

        logger.info("MoonlightLauncher: starting %s %s", program, " ".join(args))

        self._process = QProcess(self)
        # Connect signals before start() so no events are missed.
        self._process.started.connect(self._on_started)
        self._process.errorOccurred.connect(self._on_error_occurred)
        self._process.finished.connect(self._on_finished)

        self._start_time = time.monotonic()
        self._process.start(program, args)

    def _on_started(self) -> None:
        """Handle QProcess.started — process is confirmed running."""
        if self._process is not None:
            logger.info(
                "MoonlightLauncher: process started (pid=%s)", self._process.processId()
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
        logger.error(
            "MoonlightLauncher: failed to start '%s': %s", program, error_string
        )

        if self._process is not None:
            self._process.started.disconnect(self._on_started)
            self._process.errorOccurred.disconnect(self._on_error_occurred)
            self._process.finished.disconnect(self._on_finished)
            self._process = None

        self.processFinished.emit(-1, 0)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        logger.info(
            "MoonlightLauncher: process finished — exit_code=%d exit_status=%s elapsed=%ds",
            exit_code,
            exit_status,
            elapsed,
        )
        self._process = None
        self.processFinished.emit(exit_code, elapsed)
