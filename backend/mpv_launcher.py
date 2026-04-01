"""MPV process launcher for HTPC Station.

Manages launching and monitoring an MPV process for direct Plex stream playback
via QProcess. Only one MPV instance may be active at a time.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal

logger = logging.getLogger(__name__)

_INPUT_CONF_CONTENT = """\
# HTPC Station MPV gamepad input config
# Standard Linux gamepad button names (evdev/SDL)

GAMEPAD_ACTION_A        cycle pause
GAMEPAD_ACTION_B        quit
GAMEPAD_LEFT            seek -10
GAMEPAD_RIGHT           seek 10
GAMEPAD_UP              add volume 5
GAMEPAD_DOWN            add volume -5
GAMEPAD_LEFT_TRIGGER    add chapter -1
GAMEPAD_RIGHT_TRIGGER   add chapter 1
GAMEPAD_LEFT_SHOULDER   cycle audio
GAMEPAD_RIGHT_SHOULDER  cycle sub
GAMEPAD_X               cycle sub-visibility
GAMEPAD_Y               show-progress
GAMEPAD_START           quit
"""

_INPUT_CONF_PATH = Path.home() / ".config" / "htpcstation" / "mpv" / "input.conf"


class MpvLauncher(QObject):
    """Launches MPV for direct Plex stream playback and monitors lifecycle.

    Only one MPV process may be active at a time.  If :meth:`launch` is
    called while MPV is already running the request is silently ignored.

    Signals:
        processStarted — emitted when MPV starts successfully.
        processFinished(exit_code) — emitted when MPV exits.
            ``exit_code`` is -1 when the process failed to start.
    """

    processStarted = Signal()
    processFinished = Signal(int)  # exit_code; -1 = failed to start

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._process: Optional[QProcess] = None
        self._start_time: float = 0.0
        self._ensure_input_conf()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch(self, url: str, title: str = "", start_ms: int = 0) -> None:
        """Launch MPV with the given stream URL.

        start_ms: resume position in milliseconds (0 = start from beginning).
        Returns immediately. Does nothing if MPV is already running.
        """
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "MpvLauncher.launch: MPV is already running — ignoring new launch request"
            )
            return

        args = self._build_args(url, title, start_ms)
        program = "/usr/bin/mpv"

        logger.info("MpvLauncher: starting %s %s", program, " ".join(args))

        self._process = QProcess(self)
        self._process.started.connect(self._on_started)
        self._process.errorOccurred.connect(self._on_error_occurred)
        self._process.finished.connect(self._on_finished)

        self._start_time = time.monotonic()
        self._process.start(program, args)

    def launch_live_tv(self, url: str, title: str = "") -> None:
        """Launch MPV for a Live TV (HDHomeRun MPEG-TS) stream.

        Uses reconnect options suitable for live streams.
        No HTTP auth headers — HDHomeRun streams are unauthenticated.
        Returns immediately. Does nothing if MPV is already running.
        """
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            logger.warning(
                "MpvLauncher.launch_live_tv: MPV is already running — ignoring new launch request"
            )
            return

        args = self._build_live_tv_args(url, title)
        program = "/usr/bin/mpv"

        logger.info("MpvLauncher: starting live TV %s %s", program, " ".join(args))

        self._process = QProcess(self)
        self._process.started.connect(self._on_started)
        self._process.errorOccurred.connect(self._on_error_occurred)
        self._process.finished.connect(self._on_finished)

        self._start_time = time.monotonic()
        self._process.start(program, args)

    def kill(self) -> None:
        """Terminate MPV if running."""
        if self._process is None or self._process.state() == QProcess.ProcessState.NotRunning:
            return
        logger.info("MpvLauncher: killing MPV")
        self._process.kill()

    def is_running(self) -> bool:
        """Return True if MPV is currently running."""
        return (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_live_tv_args(self, url: str, title: str = "") -> list[str]:
        """Build the argv list for a Live TV MPV process.

        Uses reconnect options for MPEG-TS streams.
        No --http-header-fields (HDHomeRun streams need no auth).
        No --start (live streams always start from the live edge).
        """
        args = [
            "--fullscreen",
            "--no-terminal",
            f"--input-conf={_INPUT_CONF_PATH}",
            "--hwdec=vaapi",
            "--vo=gpu",
            "--gpu-context=x11",
            "--cache=yes",
            "--demuxer-max-bytes=128MiB",
            "--stream-lavf-o=reconnect=1,reconnect_streamed=1,reconnect_delay_max=5",
        ]
        if title:
            args.append(f"--title={title}")
            args.append(f"--force-media-title={title}")
        args.append(url)
        return args

    def _build_args(self, url: str, title: str, start_ms: int = 0) -> list[str]:
        """Build the argv list for the MPV process."""
        args = [
            "--fullscreen",
            "--no-terminal",
            f"--input-conf={_INPUT_CONF_PATH}",
            "--hwdec=vaapi",
            "--vo=gpu",
            "--gpu-context=x11",
            "--cache=yes",
            "--demuxer-max-bytes=50MiB",
            "--http-header-fields=X-Plex-Client-Identifier:htpcstation,X-Plex-Product:HTPC Station",
        ]
        if title:
            args.append(f"--title={title}")
            args.append(f"--force-media-title={title}")
        if start_ms > 0:
            total_seconds = start_ms // 1000
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            args.append(f"--start={hours:02d}:{minutes:02d}:{seconds:02d}")
        args.append(url)
        return args

    def _ensure_input_conf(self) -> None:
        """Write the default MPV input.conf if it does not already exist.

        Never overwrites an existing file — the user may have customised it.
        """
        if _INPUT_CONF_PATH.exists():
            return
        try:
            _INPUT_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
            _INPUT_CONF_PATH.write_text(_INPUT_CONF_CONTENT, encoding="utf-8")
            logger.info("MpvLauncher: created default input.conf at %s", _INPUT_CONF_PATH)
        except OSError as exc:
            logger.warning("MpvLauncher: failed to create input.conf: %s", exc)

    def _on_started(self) -> None:
        """Handle QProcess.started — MPV process is confirmed running."""
        if self._process is not None:
            logger.info(
                "MpvLauncher: MPV started (pid=%s)", self._process.processId()
            )
        self.processStarted.emit()

    def _on_error_occurred(self, error: QProcess.ProcessError) -> None:
        """Handle QProcess.errorOccurred — only act on FailedToStart."""
        if error != QProcess.ProcessError.FailedToStart:
            return

        program = self._process.program() if self._process is not None else "<unknown>"
        error_string = self._process.errorString() if self._process is not None else ""
        logger.error("MpvLauncher: failed to start '%s': %s", program, error_string)

        if self._process is not None:
            self._process.started.disconnect(self._on_started)
            self._process.errorOccurred.disconnect(self._on_error_occurred)
            self._process.finished.disconnect(self._on_finished)
            self._process = None

        self.processFinished.emit(-1)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        logger.info(
            "MpvLauncher: MPV finished — exit_code=%d exit_status=%s elapsed=%ds",
            exit_code,
            exit_status,
            elapsed,
        )
        self._process = None
        self.processFinished.emit(exit_code)
