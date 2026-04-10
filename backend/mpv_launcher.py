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

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._player: Optional[mpv.MPV] = None
        self._dead_player: Optional[mpv.MPV] = None  # held for cleanup after shutdown
        self._is_live_tv: bool = False
        self._cancel_requested = threading.Event()
        self._wid: Optional[int] = None  # stored so we can recreate after shutdown

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_wid(self, wid: int) -> None:
        """Create the MPV instance bound to the given Qt native window handle.

        Must be called after the Qt window is shown (so winId() is valid).
        Safe to call again after a shutdown — recreates the player with the same wid.
        """
        self._wid = wid
        if self._player is not None:
            logger.warning("LibMpvPlayer.set_wid: player already created — ignoring")
            return

        # libmpv requires LC_NUMERIC=C. Qt resets the locale; restore it here
        # immediately before creating the MPV instance.
        import locale as _locale
        _locale.setlocale(_locale.LC_NUMERIC, "C")

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

            input_default_bindings=True,
            input_vo_keyboard=True,
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
            # Explicitly stop to clear player.filename — libmpv keeps the last
            # filename set after end_file, which causes is_running() to return
            # True and block subsequent launch() calls. This is a no-op if
            # already stopped (e.g. user pressed Stop keybind).
            try:
                self._player.stop()
                # Release the video output surface so the Wayland toplevel
                # created by fullscreen=yes is destroyed. Without this, the
                # surface lingers as a zombie after the WM closes it (Alt+F4).
                self._player["vid"] = "no"
            except Exception:  # noqa: BLE001
                pass
            QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                Qt.ConnectionType.QueuedConnection,
            )

        # Register programmatic keybinds (replaces input.conf)
        self._setup_keybinds()

        # When the WM sends a close event (e.g. Alt+F4), libmpv calls quit and
        # fires SHUTDOWN, destroying the core. Detect this and schedule a
        # recreation of the player on the main thread so subsequent launches work.
        @player.event_callback("shutdown")
        def _on_shutdown(_event):  # noqa: ANN001
            logger.info("LibMpvPlayer: core shutdown detected — scheduling recreation")
            # Stash the dead player so _recreate_player can terminate() it on
            # the main thread, which cleans up the zombie Wayland surface.
            self._dead_player = self._player
            self._player = None
            QMetaObject.invokeMethod(
                self,
                "_recreate_player",
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
                "LibMpvPlayer.launch: player reports running — force-stopping before new launch"
            )
            self._player.stop()
            # Brief yield to let the stop command propagate through the mpv event loop
            # before we call play() with the new URL.
            time.sleep(0.05)

        if title:
            self._player.title = title
            self._player.force_media_title = title

        # Set start position. "none" clears any previous resume position.
        # Do NOT use "" or "0" — both cause errors or a seek+pause on some streams.
        self._player.start = _ms_to_hms(start_ms) if start_ms > 0 else "none"

        # Ensure playback starts in play state (not paused).
        # MPV can retain a paused state from a previous session or the
        # pause=yes default; force it off before loading the new file.
        self._player.pause = False

        self._cancel_requested.clear()
        self._player.play(url)

        # Wait for playback to start on a daemon thread, then signal main thread
        def _wait_and_signal() -> None:
            try:
                self._player.wait_until_playing(timeout=30)
            except Exception:  # noqa: BLE001
                # Timed out or stopped before first frame — clear the loading overlay.
                if self.is_running():
                    QMetaObject.invokeMethod(
                        self,
                        "_emit_finished",
                        Qt.ConnectionType.QueuedConnection,
                    )
                return
            # If cancel was requested while we were waiting, stop without
            # revealing video — the player will fire end_file which emits
            # processFinished to clean up the loading state.
            if self._cancel_requested.is_set():
                self._player.stop()
                return
            QMetaObject.invokeMethod(
                self,
                "_on_playback_started",
                Qt.ConnectionType.QueuedConnection,
            )
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
                "LibMpvPlayer.launch_live_tv: player reports running — force-stopping before new launch"
            )
            self._player.stop()
            time.sleep(0.05)

        # Override options for live TV
        self._player["demuxer-max-bytes"] = "128MiB"
        self._player["stream-lavf-o"] = (
            "reconnect=1,reconnect_streamed=1,reconnect_delay_max=5"
        )
        self._is_live_tv = True

        if title:
            self._player.title = title
            self._player.force_media_title = title

        # Ensure playback starts in play state.
        self._player.pause = False

        self._cancel_requested.clear()
        self._player["vid"] = "no"
        self._player.play(url)

        def _wait_and_signal() -> None:
            try:
                self._player.wait_until_playing(timeout=30)
            except Exception:  # noqa: BLE001
                self._player["vid"] = "auto"
                return  # stopped before playing — do not emit started signals
            if self._cancel_requested.is_set():
                self._player.stop()
                return
            self._player["vid"] = "auto"
            QMetaObject.invokeMethod(
                self,
                "_on_playback_started",
                Qt.ConnectionType.QueuedConnection,
            )
            QMetaObject.invokeMethod(
                self,
                "_emit_started",
                Qt.ConnectionType.QueuedConnection,
            )

        t = threading.Thread(target=_wait_and_signal, daemon=True)
        t.start()

    def kill(self) -> None:
        """Stop playback.

        Sets the cancel flag immediately (so _wait_and_signal won't emit
        playback-started) then dispatches the actual stop off the main thread
        to avoid blocking Qt while MPV processes the command.
        """
        if self._player is None:
            return
        logger.info("LibMpvPlayer: stopping playback")
        self._cancel_requested.set()
        player = self._player
        t = threading.Thread(target=player.stop, daemon=True)
        t.start()

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
        """Return True if MPV has a file loaded (playing or paused)."""
        if self._player is None:
            return False
        try:
            return bool(self._player.filename)
        except Exception:  # noqa: BLE001
            return False

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
    def _recreate_player(self) -> None:
        """Recreate the libmpv core after a shutdown (e.g. Alt+F4 WM close).

        Called on the main thread via QueuedConnection from the shutdown callback.
        Terminates the dead player first to clean up the zombie Wayland surface.
        """
        if self._wid is None:
            logger.warning("LibMpvPlayer._recreate_player: no wid stored — cannot recreate")
            return
        if self._player is not None:
            logger.warning("LibMpvPlayer._recreate_player: player already exists — skipping")
            return
        # Terminate the dead core on the main thread (safe — not the event thread).
        # This calls _mpv_terminate_destroy which releases the Wayland surface,
        # removing the zombie from the compositor's window list.
        if self._dead_player is not None:
            try:
                self._dead_player.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._dead_player = None
        logger.info("LibMpvPlayer._recreate_player: recreating MPV core with wid=%d", self._wid)
        self.set_wid(self._wid)

    @Slot()
    def _emit_started(self) -> None:
        self.processStarted.emit()

    @Slot()
    def _emit_finished(self) -> None:
        self.processFinished.emit(0)

    @Slot()
    def _on_playback_started(self) -> None:
        self.mpvPlaybackStarted.emit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_keybinds(self) -> None:
        """Register all gamepad keybinds programmatically.

        Verified with mpv --input-test on 8BitDo Micro D-input (Bluetooth):
          GAMEPAD_ACTION_DOWN  = A (east,  evdev 304) = wizard accept = pause
          GAMEPAD_ACTION_RIGHT = B (south, evdev 305) = unbound
          GAMEPAD_ACTION_LEFT  = X (north, evdev 307) = show-progress
          GAMEPAD_ACTION_UP    = Y (west,  evdev 308) = cycle sub (MPV native)
          GAMEPAD_START        = Start (evdev 315)    = stop
        """
        binds = [
            ("GAMEPAD_ACTION_DOWN",    "cycle pause"),
            ("GAMEPAD_DPAD_LEFT",      "seek -10"),
            ("GAMEPAD_DPAD_RIGHT",     "seek 10"),
            ("GAMEPAD_DPAD_UP",        "add volume 5"),
            ("GAMEPAD_DPAD_DOWN",      "add volume -5"),
            ("GAMEPAD_LEFT_SHOULDER",  "cycle audio"),
            ("GAMEPAD_RIGHT_SHOULDER", "show-text ${track-list} 3000"),
            ("GAMEPAD_ACTION_LEFT",    "show-progress"),
            ("GAMEPAD_ACTION_UP",      "osd-msg cycle sub"),
            ("GAMEPAD_START",          "stop"),
            # Override default quit bindings — use stop (keeps core alive) not quit
            ("q",                      "stop"),
            ("Q",                      "stop"),
            ("ESC",                    "stop"),
        ]
        for key, cmd in binds:
            self._player.keybind(key, cmd)



    @staticmethod
    def _gpu_context() -> str:
        """Return the correct MPV gpu-context for the current display server.

        Uses 'auto' to let mpv select the best available context (EGL, GLX,
        Wayland, etc.) for the running display server and GPU drivers.
        """
        return "auto"

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
