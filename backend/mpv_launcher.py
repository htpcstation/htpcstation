"""MPV in-process player for HTPC Station.

Wraps python-mpv's MPV class for direct Plex stream playback.
Only one MPV instance is created; URLs are loaded via player.play().
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

import mpv

from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

logger = logging.getLogger(__name__)

# IPC socket path — kept for the input-ipc-server option (harmless, no longer polled).
MPV_IPC_SOCKET = "/tmp/htpcstation-mpv.sock"

_TRIGGER_DEBOUNCE = 0.5  # seconds — ignore L2/R2 repeats within this window


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
        mpvPlaybackStarted — emitted when first frame is ready (wait_until_playing).
        subtitlePickerRequested — emitted when Y button is pressed during playback.
    """

    processStarted = Signal()
    processFinished = Signal(int)
    mpvPlaybackStarted = Signal()
    subtitlePickerRequested = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._player: Optional[mpv.MPV] = None
        self._is_live_tv: bool = False

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

        # Register programmatic keybinds (replaces input.conf)
        self._setup_keybinds()

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
                self._player.wait_until_playing(timeout=30)
                QMetaObject.invokeMethod(
                    self,
                    "_on_playback_started",
                    Qt.ConnectionType.QueuedConnection,
                )
            except Exception:  # noqa: BLE001
                pass  # timeout or shutdown — processStarted already handles cleanup
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
                self._player.wait_until_playing(timeout=30)
                QMetaObject.invokeMethod(
                    self,
                    "_on_playback_started",
                    Qt.ConnectionType.QueuedConnection,
                )
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

    def observe_time_pos(self, callback: Callable[[float], None]) -> None:
        """Register a callback for time-pos changes. Called from mpv event thread."""
        if self._player is None:
            logger.warning("LibMpvPlayer.observe_time_pos: player not initialised — ignoring")
            return

        @self._player.property_observer("time-pos")
        def _handler(name, value):
            if isinstance(value, (int, float)) and value is not None:
                callback(float(value))

        self._time_pos_observer = _handler  # keep reference

    def observe_pause(self, callback: Callable[[bool], None]) -> None:
        """Register a callback for pause state changes. Called from mpv event thread."""
        if self._player is None:
            logger.warning("LibMpvPlayer.observe_pause: player not initialised — ignoring")
            return

        @self._player.property_observer("pause")
        def _handler(name, value):
            if value is not None:
                callback(bool(value))

        self._pause_observer = _handler  # keep reference

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

    @Slot()
    def _on_playback_started(self) -> None:
        self.mpvPlaybackStarted.emit()

    @Slot()
    def _request_subtitle_picker(self) -> None:
        self.subtitlePickerRequested.emit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_keybinds(self) -> None:
        """Register all gamepad keybinds programmatically.

        Replaces input.conf. Verified button names from mpv --input-test
        on 8BitDo Micro D-input (Bluetooth):
          GAMEPAD_ACTION_DOWN  = A (east, evdev 304) = wizard accept
          GAMEPAD_ACTION_RIGHT = B (south, evdev 305) = unbound
          GAMEPAD_ACTION_UP    = X (north, evdev 307)
          GAMEPAD_ACTION_LEFT  = Y (west, evdev 308)
          GAMEPAD_START        = Start (evdev 315)
        """
        binds = [
            ("GAMEPAD_ACTION_DOWN",    "cycle pause"),
            ("GAMEPAD_DPAD_LEFT",      "seek -10"),
            ("GAMEPAD_DPAD_RIGHT",     "seek 10"),
            ("GAMEPAD_DPAD_UP",        "add volume 5"),
            ("GAMEPAD_DPAD_DOWN",      "add volume -5"),
            ("GAMEPAD_LEFT_SHOULDER",  "cycle audio"),
            ("GAMEPAD_RIGHT_SHOULDER", "show-text ${track-list} 3000"),
            ("GAMEPAD_ACTION_UP",      "show-progress"),
            ("GAMEPAD_START",          "quit"),
            # GAMEPAD_ACTION_LEFT (Y) handled via Python callback — see subtitle picker
            # GAMEPAD_LEFT_TRIGGER / GAMEPAD_RIGHT_TRIGGER handled via key press handlers
        ]
        for key, cmd in binds:
            self._player.keybind(key, cmd)

        # Y button — emit signal to QML on main thread for subtitle picker
        @self._player.on_key_press("GAMEPAD_ACTION_LEFT")
        def _on_y_pressed():
            QMetaObject.invokeMethod(
                self, "_request_subtitle_picker", Qt.ConnectionType.QueuedConnection
            )

        # L2/R2 debounce — use on_key_press with debounce to avoid runaway seeks
        _last_l2_time = [0.0]
        _last_r2_time = [0.0]

        @self._player.on_key_press("GAMEPAD_LEFT_TRIGGER")
        def _on_l2():
            now = time.monotonic()
            if now - _last_l2_time[0] < _TRIGGER_DEBOUNCE:
                return
            _last_l2_time[0] = now
            self._player.seek(-30, "relative+keyframes")

        @self._player.on_key_press("GAMEPAD_RIGHT_TRIGGER")
        def _on_r2():
            now = time.monotonic()
            if now - _last_r2_time[0] < _TRIGGER_DEBOUNCE:
                return
            _last_r2_time[0] = now
            self._player.seek(30, "relative+keyframes")

        # Store references to prevent garbage collection
        self._keybind_callbacks = (_on_y_pressed, _on_l2, _on_r2)

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
