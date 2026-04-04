"""MPV in-process player for HTPC Station.

Wraps python-mpv's MPV class for direct Plex stream playback.
Only one MPV instance is created; URLs are loaded via player.play().
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import mpv

from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

logger = logging.getLogger(__name__)

# IPC socket path for communicating with a running MPV instance.
# Kept for MpvIpc compatibility (task 3 will migrate this).
MPV_IPC_SOCKET = "/tmp/htpcstation-mpv.sock"

_INPUT_CONF_VERSION = "15"
_INPUT_CONF_CONTENT = """\
# HTPC Station MPV input config v15
# Verified with mpv --input-test (user confirmed, no SDL override needed):
#   A (east,  evdev 304) -> GAMEPAD_ACTION_DOWN   = wizard accept = pause
#   B (south, evdev 305) -> GAMEPAD_ACTION_RIGHT  (unbound)
#   X (north, evdev 307) -> GAMEPAD_ACTION_UP     = show-progress
#   Y (west,  evdev 308) -> GAMEPAD_ACTION_LEFT   (unbound)
#   Start (evdev 315)    -> GAMEPAD_START          = quit
# L2/R2 are unbound — analog axis fires continuously while held, unusable.

GAMEPAD_ACTION_DOWN     cycle pause
GAMEPAD_DPAD_LEFT       seek -10
GAMEPAD_DPAD_RIGHT      seek 10
GAMEPAD_DPAD_UP         add volume 5
GAMEPAD_DPAD_DOWN       add volume -5
GAMEPAD_LEFT_SHOULDER   cycle audio
GAMEPAD_RIGHT_SHOULDER  show-text ${track-list} 3000
GAMEPAD_ACTION_UP       show-progress
GAMEPAD_START           quit
"""

_INPUT_CONF_PATH = Path.home() / ".config" / "htpcstation" / "mpv" / "input.conf"


def _mpv_log(level: str, prefix: str, text: str) -> None:
    """Forward libmpv log messages to Python logging."""
    logger.debug("[mpv/%s] %s: %s", level, prefix, text.rstrip())


def _ms_to_hms(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS string for mpv --start."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class LibMpvPlayer(QObject):
    """Wraps python-mpv MPV instance for in-process video playback.

    Identical signal interface to the old MpvLauncher so callers need
    no changes beyond the class name.

    Signals:
        processStarted — emitted when MPV begins playing (first frame ready).
        processFinished(exit_code) — emitted when playback ends (always 0).
    """

    processStarted = Signal()
    processFinished = Signal(int)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._player: Optional[mpv.MPV] = None
        self._is_live_tv: bool = False
        self._ensure_input_conf()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_wid(self, wid: int) -> None:
        """Create the MPV instance bound to the given Qt native window handle.

        Must be called after the Qt window is shown (so winId() is valid).
        """
        if self._player is not None:
            logger.warning("LibMpvPlayer.set_wid: player already created — ignoring")
            return

        self._player = mpv.MPV(
            wid=str(wid),
            vo="gpu",
            hwdec=self._hwdec_mode(),
            hwdec_codecs="all",
            gpu_api="opengl",
            gpu_context=self._gpu_context(),
            vd_lavc_dr="yes",
            osc="no",
            fullscreen="yes",
            input_gamepad="yes",
            cache="yes",
            input_conf=str(_INPUT_CONF_PATH),
            log_handler=_mpv_log,
            loglevel="warn",
        )

        # Set persistent options
        self._player["input-ipc-server"] = MPV_IPC_SOCKET
        self._player["http-header-fields"] = (
            "X-Plex-Client-Identifier:htpcstation,X-Plex-Product:HTPC Station"
        )
        self._player["demuxer-max-bytes"] = "50MiB"

        # Register end-of-file event callback
        player = self._player

        @player.event_callback("end_file")
        def _on_end_file(event):  # noqa: ANN001
            if self._is_live_tv:
                # Reset live TV options after playback ends
                try:
                    self._player["demuxer-max-bytes"] = "50MiB"
                    self._player["stream-lavf-o"] = ""
                except Exception:  # noqa: BLE001
                    pass
                self._is_live_tv = False
            QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                Qt.ConnectionType.QueuedConnection,
            )

        logger.info("LibMpvPlayer: MPV instance created (wid=%d)", wid)

    def launch(self, url: str, title: str = "", start_ms: int = 0) -> None:
        """Load and play the given URL.

        start_ms: resume position in milliseconds (0 = start from beginning).
        Returns immediately. Does nothing if MPV is already playing.
        """
        if self._player is None:
            logger.error(
                "LibMpvPlayer.launch: player not initialised — call set_wid() first"
            )
            return

        if self.is_running():
            logger.warning(
                "LibMpvPlayer.launch: already playing — ignoring new launch request"
            )
            return

        if title:
            self._player.title = title
            self._player.force_media_title = title

        if start_ms > 0:
            self._player.start = _ms_to_hms(start_ms)

        self._player.play(url)

        # Wait for playback to start on a daemon thread, then signal main thread
        def _wait_and_signal() -> None:
            try:
                self._player.wait_until_playing()
            except Exception:  # noqa: BLE001
                pass
            QMetaObject.invokeMethod(
                self,
                "_emit_started",
                Qt.ConnectionType.QueuedConnection,
            )

        t = threading.Thread(target=_wait_and_signal, daemon=True)
        t.start()

    def launch_live_tv(self, url: str, title: str = "") -> None:
        """Load and play a Live TV (HDHomeRun MPEG-TS) stream.

        Uses reconnect options suitable for live streams.
        No HTTP auth headers — HDHomeRun streams are unauthenticated.
        Returns immediately. Does nothing if MPV is already playing.
        """
        if self._player is None:
            logger.error(
                "LibMpvPlayer.launch_live_tv: player not initialised — call set_wid() first"
            )
            return

        if self.is_running():
            logger.warning(
                "LibMpvPlayer.launch_live_tv: already playing — ignoring new launch request"
            )
            return

        # Override options for live TV
        self._player["demuxer-max-bytes"] = "128MiB"
        self._player["stream-lavf-o"] = (
            "reconnect=1,reconnect_streamed=1,reconnect_delay_max=5"
        )
        self._is_live_tv = True

        if title:
            self._player.title = title
            self._player.force_media_title = title

        self._player.play(url)

        def _wait_and_signal() -> None:
            try:
                self._player.wait_until_playing()
            except Exception:  # noqa: BLE001
                pass
            QMetaObject.invokeMethod(
                self,
                "_emit_started",
                Qt.ConnectionType.QueuedConnection,
            )

        t = threading.Thread(target=_wait_and_signal, daemon=True)
        t.start()

    def kill(self) -> None:
        """Stop playback."""
        if self._player is None:
            return
        logger.info("LibMpvPlayer: stopping playback")
        self._player.stop()

    def is_running(self) -> bool:
        """Return True if MPV is currently playing (not idle)."""
        if self._player is None:
            return False
        return self._player.core_idle is False

    def shutdown(self) -> None:
        """Terminate the MPV instance. Call on app exit."""
        if self._player is not None:
            try:
                self._player.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._player = None

    def __del__(self) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Slots (must be on main thread)
    # ------------------------------------------------------------------

    @Slot()
    def _emit_started(self) -> None:
        self.processStarted.emit()

    @Slot()
    def _emit_finished(self) -> None:
        self.processFinished.emit(0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gpu_context() -> str:
        """Return the correct MPV gpu-context for the current display server.

        On Wayland, use 'wayland'. On Xorg (or Xwayland), use 'x11'.
        Defaults to 'x11' if the session type cannot be determined.
        """
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session == "wayland" and os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        return "x11"

    @staticmethod
    def _hwdec_mode() -> str:
        """Return the appropriate hwdec mode for the current display server.

        On Wayland, VA-API decoded frames cannot be directly displayed via
        the Wayland EGL path without a copy — use 'vaapi-copy' which decodes
        with VA-API and copies to a regular GPU surface for display.
        On Xorg, 'vaapi' works directly.
        """
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session == "wayland" and os.environ.get("WAYLAND_DISPLAY"):
            return "vaapi-copy"
        return "vaapi"

    def _ensure_input_conf(self) -> None:
        """Write the default MPV input.conf, updating it if the version is outdated."""
        if _INPUT_CONF_PATH.exists():
            # Check version header — overwrite if outdated
            try:
                first_line = _INPUT_CONF_PATH.read_text(encoding="utf-8").split("\n")[0]
                if f"v{_INPUT_CONF_VERSION}" in first_line:
                    return  # up to date
            except OSError:
                pass
            # Outdated or unreadable — overwrite
            logger.info("LibMpvPlayer: updating input.conf to v%s", _INPUT_CONF_VERSION)
        try:
            _INPUT_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
            _INPUT_CONF_PATH.write_text(_INPUT_CONF_CONTENT, encoding="utf-8")
            logger.info("LibMpvPlayer: wrote input.conf at %s", _INPUT_CONF_PATH)
        except OSError as exc:
            logger.warning("LibMpvPlayer: failed to write input.conf: %s", exc)
