"""Browser process launcher for HTPC Station.

Manages launching and monitoring a browser process (Brave in kiosk mode)
via QProcess. Only one browser instance may be active at a time.
"""

from __future__ import annotations

import glob
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal

from backend.controller_mapping import generate_mapping_js, load_mapping

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
        # Extension directory ships with the project at <project_root>/extension/
        self._extension_dir = (Path(__file__).parent.parent / "extension").resolve()
        # Deployed copy of the extension inside the Brave flatpak data directory.
        # The flatpak sandbox cannot read arbitrary home directory paths, so the
        # extension must be copied here before launch.
        self._extension_deploy_dir = (
            Path.home() / ".var" / "app" / "com.brave.Browser"
            / "config" / "htpcstation-extension"
        )
        # Dedicated user data directory inside the flatpak sandbox.
        # This ensures HTPC Station's Brave instance is completely separate
        # from any personal browsing session — kiosk mode, extensions, and
        # command-line flags always apply, even if Brave is already running.
        self._user_data_dir = (
            Path.home() / ".var" / "app" / "com.brave.Browser"
            / "config" / "htpcstation-browser"
        )
        # Browser profile directory within our dedicated user data dir.
        # Session files are cleared before each launch to prevent tab
        # accumulation, but cookies/login persist.
        self._browser_profile_dir = (
            self._user_data_dir / "Default"
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
        # Ensure the Flatpak browser can access udev for gamepad enumeration.
        # The Web Gamepad API in Chromium-based browsers needs /run/udev to
        # discover game controllers.  Without this override, gamepads are
        # invisible to the browser inside the Flatpak sandbox.
        self._ensure_flatpak_gamepad_access()
        # Deploy the extension into the flatpak-accessible data directory.
        deployed = self._deploy_extension()
        # Ensure the user data directory exists.
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            *tokens,
            "--kiosk",
            "--start-fullscreen",
            "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={self._user_data_dir}",
        ]
        if deployed is not None:
            cmd.append(f"--load-extension={deployed}")
        cmd.append(url)
        return cmd

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

    def _ensure_flatpak_gamepad_access(self) -> None:
        """Grant the Flatpak browser access to /run/udev for gamepad support.

        Chromium-based browsers use udev to enumerate game controllers via the
        Web Gamepad API.  Inside a Flatpak sandbox, /run/udev is not accessible
        by default, making gamepads invisible to the browser.  This method
        applies a user-level Flatpak override to grant read-only access.

        The override is idempotent — it's safe to call on every launch.
        Only applies when the browser command starts with ``flatpak run``.
        """
        tokens = self._browser_command.split()
        if len(tokens) < 3 or tokens[0] != "flatpak" or tokens[1] != "run":
            return  # Not a Flatpak app — no override needed
        app_id = tokens[2]
        try:
            import subprocess
            subprocess.run(
                ["flatpak", "override", "--user", app_id, "--filesystem=/run/udev:ro"],
                capture_output=True,
                timeout=5,
            )
            logger.debug("BrowserLauncher: ensured Flatpak gamepad access for %s", app_id)
        except Exception as exc:
            logger.warning("BrowserLauncher: failed to set Flatpak override for gamepad: %s", exc)

    def _deploy_extension(self) -> Optional[Path]:
        """Copy the extension into the Brave flatpak data directory.

        The Brave flatpak sandbox cannot read arbitrary paths under the home
        directory, so the extension must be deployed to a path the sandbox can
        access (``~/.var/app/com.brave.Browser/``).

        Returns the deployed path on success, or ``None`` if the copy failed
        (e.g. the source directory does not exist).  When ``None`` is returned
        the caller should omit the ``--load-extension`` flag rather than
        crashing.
        """
        src = self._extension_dir
        dst = self._extension_deploy_dir
        if not src.exists():
            logger.warning(
                "BrowserLauncher: extension source directory not found: %s — "
                "omitting --load-extension flag",
                src,
            )
            return None
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            logger.debug("BrowserLauncher: extension deployed to %s", dst)
        except OSError as exc:
            logger.warning(
                "BrowserLauncher: failed to deploy extension from %s to %s: %s — "
                "omitting --load-extension flag",
                src,
                dst,
                exc,
            )
            return None

        # Generate the controller mapping JS file from the stored config.
        # This file is loaded by the extension before content.js so the
        # generated mapping is available as window.__htpcGeneratedMapping.
        try:
            mapping = load_mapping()
            # Read button layout from config to apply accept/cancel swap
            from backend.config import Config
            _cfg = Config()
            js_content = generate_mapping_js(mapping, button_layout=_cfg.button_layout)
            mapping_js_path = dst / "generated_mapping.js"
            mapping_js_path.write_text(js_content, encoding="utf-8")
            logger.debug("BrowserLauncher: generated mapping JS written to %s", mapping_js_path)
        except Exception as exc:
            logger.warning(
                "BrowserLauncher: failed to generate mapping JS: %s — "
                "extension will use hardcoded defaults",
                exc,
            )

        return dst

    def kill(self) -> None:
        """Terminate the browser process if it is running.

        Flatpak wraps the browser in a subprocess, so killing the QProcess
        (the ``flatpak run`` wrapper) may not stop the actual browser.
        We use ``flatpak kill`` for Flatpak apps, falling back to process
        group kill and then QProcess.kill().
        """
        if self._process is None or self._process.state() == QProcess.ProcessState.NotRunning:
            return

        logger.info("BrowserLauncher: killing browser")

        # For Flatpak apps, use `flatpak kill <app_id>` which reliably
        # terminates the sandboxed process and all its children.
        tokens = self._browser_command.split()
        if len(tokens) >= 3 and tokens[0] == "flatpak" and tokens[1] == "run":
            app_id = tokens[2]
            import subprocess
            try:
                subprocess.run(["flatpak", "kill", app_id], timeout=5)
                logger.info("BrowserLauncher: flatpak kill %s succeeded", app_id)
                return
            except Exception as exc:
                logger.warning("BrowserLauncher: flatpak kill failed: %s", exc)

        # Fallback for non-Flatpak browsers: kill the process
        self._process.kill()

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
