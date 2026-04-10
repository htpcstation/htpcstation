"""HTPC Station — entry point."""

import locale
import os
import sys
from pathlib import Path

# libmpv requires LC_NUMERIC=C. This MUST be set before any other import
# that transitively loads libmpv (including `import mpv` in mpv_launcher.py).
# Qt also resets the locale, so we set it here first and again after PySide6.
locale.setlocale(locale.LC_NUMERIC, "C")

os.environ.setdefault("LIBVA_MESSAGING_LEVEL", "0")

import re
import threading

_STDERR_NOISE = re.compile(
    r"Failed to open VDPAU backend|"
    r"No sample format supported|"
    r"Input #\d|"
    r"^\s*Metadata:|"
    r"^\s*major_brand|^\s*minor_version|^\s*compatible_brands|^\s*encoder\s|"
    r"^\s*Duration:|"
    r"^\s*Stream #|"
    r"^\s*handler_name|^\s*vendor_id|"
    r"\[h264 @|"
    r"qt\.multimedia|"
    r"No gamepads found|"
    r"Failed setup for format vaapi"
)

def _start_stderr_filter():
    """Redirect fd 2 to a pipe; filter out noisy C library messages."""
    real_stderr_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)
    sys.stderr = os.fdopen(real_stderr_fd, "w", closefd=False)

    def _filter_thread():
        with os.fdopen(read_fd, "r", errors="replace") as pipe:
            for line in pipe:
                if not _STDERR_NOISE.search(line):
                    sys.__stderr__.write(line)
                    sys.__stderr__.flush()

    t = threading.Thread(target=_filter_thread, daemon=True)
    t.start()

if "--debug" not in sys.argv:
    _start_stderr_filter()

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QFontDatabase, QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine

# Qt resets LC_NUMERIC on import — restore it for libmpv.
locale.setlocale(locale.LC_NUMERIC, "C")

from backend.browser_launcher import BrowserLauncher
from backend.config import Config
from backend.gamepad import GamepadManager
from backend.keys import Keys
from backend.launcher import Launcher
from backend.library import GameLibrary
from backend.live_tv_library import LiveTvLibrary
from backend.local_music_library import LocalMusicLibrary
from backend.local_video_library import LocalVideoLibrary
from backend.moonlight_library import MoonlightLibrary
from backend.network_monitor import NetworkMonitor
from backend.plex_library import PlexLibrary
from backend.recently_played import RecentlyPlayedManager
from backend.settings_manager import SettingsManager
from backend.steam_library import SteamLibrary

APP_DIR = Path(__file__).parent
QML_DIR = APP_DIR / "qml"
ASSETS_DIR = APP_DIR / "assets"


def main() -> None:
    import argparse
    import logging

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", action="store_true")
    args, remaining = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining   # strip --debug before Qt sees it

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.ERROR,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = Config()  # loads/creates ~/.config/htpcstation/config.json

    app = QGuiApplication(sys.argv)
    app.setApplicationName("htpcstation")
    app.setOrganizationName("htpcstation")

    # Load bundled emoji font so glyphs like 🎮 render without system font deps
    emoji_font = ASSETS_DIR / "fonts" / "NotoEmoji-Regular.ttf"
    if emoji_font.exists():
        QFontDatabase.addApplicationFont(str(emoji_font))

    engine = QQmlApplicationEngine()

    # Semantic key abstraction — exposed to QML as `keys`
    keys = Keys()
    engine.rootContext().setContextProperty("keys", keys)

    # Recently-played history — exposed to QML as `recentlyPlayed`
    recently_played = RecentlyPlayedManager(config)
    engine.rootContext().setContextProperty("recentlyPlayed", recently_played)

    # Emulator process launcher
    launcher = Launcher()

    # Game library — exposed to QML as `library`
    library = GameLibrary(config, launcher, recently_played=recently_played)
    engine.rootContext().setContextProperty("library", library)

    # Browser launcher for Plex Web kiosk mode
    browser_launcher = BrowserLauncher(config.browser_command, button_layout=config.button_layout)

    # Plex library — exposed to QML as `plex`
    plex_library = PlexLibrary(config, browser_launcher, recently_played=recently_played)
    engine.rootContext().setContextProperty("plex", plex_library)

    # Live TV library — exposed to QML as `liveTV`
    live_tv = LiveTvLibrary(
        plex_client_factory=lambda: plex_library._client,
        mpv_launcher=plex_library._mpv_launcher,
    )
    engine.rootContext().setContextProperty("liveTV", live_tv)
    app.aboutToQuit.connect(live_tv.shutdown)
    app.aboutToQuit.connect(plex_library.shutdown)

    # Local music library — exposed to QML as `localMusic`
    local_music = LocalMusicLibrary(config)
    engine.rootContext().setContextProperty("localMusic", local_music)

    # Local video library — exposed to QML as `localVideos`
    local_videos = LocalVideoLibrary(config)
    engine.rootContext().setContextProperty("localVideos", local_videos)

    # Steam library — exposed to QML as `steam`
    steam = SteamLibrary(recently_played=recently_played)
    engine.rootContext().setContextProperty("steam", steam)

    # Moonlight library — exposed to QML as `moonlight`
    moonlight = MoonlightLibrary(
        moonlight_command=config.moonlight_command,
        host_uuid=config.moonlight_host_uuid,
        recently_played=recently_played,
    )
    engine.rootContext().setContextProperty("moonlight", moonlight)

    # Gamepad manager — created early so it can be passed to SettingsManager
    gamepad_manager = GamepadManager(app)

    # Settings manager — exposed to QML as `settings`
    settings_manager = SettingsManager(
        config, library, plex_library, browser_launcher,
        moonlight_library=moonlight, gamepad_manager=gamepad_manager,
        keys=keys, app_dir=APP_DIR,
    )
    # Initialize button layout from config
    keys.setButtonLayout(config.button_layout)
    engine.rootContext().setContextProperty("settings", settings_manager)

    # Network monitor — exposed to QML as `networkMonitor`
    network_monitor = NetworkMonitor()
    engine.rootContext().setContextProperty("networkMonitor", network_monitor)

    # Allow QML files to import siblings and the Theme singleton via `import "."`
    engine.addImportPath(str(QML_DIR))

    engine.load(QML_DIR / "main.qml")

    if not engine.rootObjects():
        sys.exit(1)

    # Get the root window for focus/visibility management
    window = engine.rootObjects()[0]

    # Show the window before passing wid so winId() is valid
    window.showFullScreen()

    # Pass the Qt native window handle to the MPV player (libmpv renders inside it)
    plex_library.set_wid(int(window.winId()))
    local_videos.set_wid(int(window.winId()))

    # Hide the window when an external process launches, restore when it exits
    def _hide_window():
        window.hide()

    def _show_window(*_args):
        window.showFullScreen()
        window.raise_()
        window.requestActivate()

    def _show_window_after_mpv(*_args):
        """Restore the Qt window after MPV closes.

        On GNOME/Wayland with fullscreen=yes, MPV takes over the compositor
        surface. When the WM closes it (Alt+F4), the underlying Qt surface is
        also destroyed. We must force Qt to recreate the surface by hiding the
        window first, then showing it fullscreen again after a short delay to
        give Mutter time to process the surface destruction.
        """
        window.hide()
        QTimer.singleShot(150, lambda: (
            window.showFullScreen(),
            window.raise_(),
            window.requestActivate(),
        ))

    launcher.processStarted.connect(_hide_window)
    launcher.processFinished.connect(_show_window)
    launcher.processStarted.connect(lambda: gamepad_manager.setExternalAppActive(True))
    launcher.processFinished.connect(lambda *_: gamepad_manager.setExternalAppActive(False))
    browser_launcher.processStarted.connect(_hide_window)
    browser_launcher.processFinished.connect(_show_window)
    browser_launcher.processStarted.connect(lambda: gamepad_manager.setExternalAppActive(True))
    browser_launcher.processFinished.connect(lambda *_: gamepad_manager.setExternalAppActive(False))
    # Steam launches are fire-and-forget — we don't hide or minimize the
    # window.  The game takes focus and HTPC Station sits behind it.  When
    # the game exits, the window manager returns focus to HTPC Station
    # automatically.  No performance cost: Qt stops rendering when obscured.

    # Moonlight streaming: hide the window while streaming, restore when done
    moonlight.processStarted.connect(_hide_window)
    moonlight.processFinished.connect(_show_window)
    moonlight.processStarted.connect(lambda: gamepad_manager.setExternalAppActive(True))
    moonlight.processFinished.connect(lambda *_: gamepad_manager.setExternalAppActive(False))

    # MPV (libmpv, embedded): no hide/show on start — MPV renders inside the Qt
    # window. On playback end, raise and re-activate the window so the HTPC
    # Station UI regains focus (the MPV surface goes blank when playback stops).
    # Suppress Qt gamepad key injection while an external app is active — MPV,
    # emulators, browser kiosk, and Moonlight all handle the gamepad directly;
    # injecting the same events into Qt causes double-handling.
    plex_library.mpvStarted.connect(lambda: gamepad_manager.setExternalAppActive(True))
    plex_library.mpvFinished.connect(lambda: gamepad_manager.setExternalAppActive(False))
    plex_library.mpvFinished.connect(_show_window_after_mpv)
    local_videos.playbackStarted.connect(lambda: gamepad_manager.setExternalAppActive(True))
    local_videos.playbackFinished.connect(lambda: gamepad_manager.setExternalAppActive(False))
    local_videos.playbackFinished.connect(_show_window_after_mpv)

    # Start+Select combo: kill the browser process (equivalent to Alt+F4).
    # The browser extension can't close kiosk windows via window.close(),
    # so we handle it at the evdev level by terminating the QProcess.
    def _on_start_select_combo():
        browser_launcher.kill()

    gamepad_manager.startSelectCombo.connect(_on_start_select_combo)

    # Detect real keyboard input to switch hint labels.
    # Gamepad input is tracked by GamepadManager calling keys.setGamepadInput().
    class _KeyboardDetector(QObject):
        def eventFilter(self, obj: QObject, event: QEvent) -> bool:
            if isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
                # Only switch to keyboard mode if this is NOT a gamepad-injected event.
                # Gamepad-injected events call setGamepadInput() before sendEvent(),
                # so if useGamepadLabels was just set to True, this event is from gamepad.
                # Real keyboard events arrive without that preceding call.
                # We detect real keyboard by checking spontaneous() — native events are
                # spontaneous, injected events via sendEvent() are not.
                if event.spontaneous():
                    keys.setKeyboardInput()
            # Intercept Alt+F4 / WM close events on the main window while MPV is
            # active. MPV renders into the Qt window surface — a WM close event
            # would kill the entire app. Instead, stop MPV and let HTPC Station
            # continue running.
            if (event.type() == QEvent.Type.Close
                    and obj is window
                    and plex_library._mpv_launcher.is_running()):
                event.ignore()
                plex_library.stopMpv()
                return True
            return False

    kb_detector = _KeyboardDetector(app)
    app.installEventFilter(kb_detector)
    window.installEventFilter(kb_detector)

    # Gamepad manager — inject events into the root QML window and expose to QML
    gamepad_manager.window = window
    gamepad_manager.keys = keys
    engine.rootContext().setContextProperty("gamepadManager", gamepad_manager)
    gamepad_manager.start()



    sys.exit(app.exec())


if __name__ == "__main__":
    main()
