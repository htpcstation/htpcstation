"""HTPC Station — entry point."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Suppress harmless VAAPI hardware decoding errors in ffmpeg logs.
# The system falls back to software decoding automatically.
os.environ.setdefault("LIBVA_MESSAGING_LEVEL", "0")

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QFontDatabase, QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine

from backend.browser_launcher import BrowserLauncher
from backend.config import Config
from backend.gamepad import GamepadManager
from backend.keys import Keys
from backend.launcher import Launcher
from backend.library import GameLibrary
from backend.moonlight_library import MoonlightLibrary
from backend.network_monitor import NetworkMonitor
from backend.plex_library import PlexLibrary
from backend.settings_manager import SettingsManager
from backend.steam_library import SteamLibrary

QML_DIR = Path(__file__).parent / "qml"
ASSETS_DIR = Path(__file__).parent / "assets"


def main() -> None:
    config = Config()  # loads/creates ***REMOVED***.config/htpcstation/config.json

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

    # Emulator process launcher
    launcher = Launcher()

    # Game library — exposed to QML as `library`
    library = GameLibrary(config, launcher)
    engine.rootContext().setContextProperty("library", library)

    # Browser launcher for Plex Web kiosk mode
    browser_launcher = BrowserLauncher(config.browser_command)

    # Plex library — exposed to QML as `plex`
    plex_library = PlexLibrary(config, browser_launcher)
    engine.rootContext().setContextProperty("plex", plex_library)

    # Steam library — exposed to QML as `steam`
    steam = SteamLibrary()
    engine.rootContext().setContextProperty("steam", steam)

    # Moonlight library — exposed to QML as `moonlight`
    moonlight = MoonlightLibrary(
        moonlight_command=config.moonlight_command,
        host_uuid=config.moonlight_host_uuid,
    )
    engine.rootContext().setContextProperty("moonlight", moonlight)

    # Give SteamLibrary a reference to MoonlightLibrary so it can dispatch
    # Moonlight launches from the "Recently Played" source.
    steam.setMoonlightLibrary(moonlight)

    # Settings manager — exposed to QML as `settings`
    settings_manager = SettingsManager(config, library, plex_library, browser_launcher, moonlight_library=moonlight)
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

    # Hide the window when an external process launches, restore when it exits
    def _hide_window():
        window.hide()

    def _show_window(*_args):
        window.showFullScreen()
        window.raise_()
        window.requestActivate()

    launcher.processStarted.connect(_hide_window)
    launcher.processFinished.connect(_show_window)
    browser_launcher.processStarted.connect(_hide_window)
    browser_launcher.processFinished.connect(_show_window)
    # Steam launches are fire-and-forget — we don't hide or minimize the
    # window.  The game takes focus and HTPC Station sits behind it.  When
    # the game exits, the window manager returns focus to HTPC Station
    # automatically.  No performance cost: Qt stops rendering when obscured.

    # Moonlight streaming: hide the window while streaming, restore when done
    moonlight.processStarted.connect(_hide_window)
    moonlight.processFinished.connect(_show_window)

    # When Moonlight host discovery completes, update the Steam source list
    # and inject recently played Moonlight data.
    def _on_moonlight_hosts_changed() -> None:
        if not moonlight._paired_hosts:
            steam.setMoonlightSources([])
            steam.setMoonlightRecentlyPlayed([])
            return
        app_count = len(moonlight._all_apps)
        is_loading = moonlight.loading
        # After Phase 2 completes (loading=False), check whether the host is online.
        # During loading, offline is False so the "Loading..." indicator takes precedence.
        is_offline = (not is_loading) and (not moonlight.hostOnline) and bool(moonlight._paired_hosts)
        steam.setMoonlightSources([{
            "name": "Moonlight Games",
            "gameCount": app_count,
            "source": "moonlight",
            "loading": is_loading,
            "offline": is_offline,
        }])

        # Build recently played list from Moonlight apps that have been played.
        # Normalize ISO 8601 timestamps to Unix epoch ints for unified sorting.
        recent_items = []
        for app in moonlight._all_apps:
            if not app.last_played:
                continue
            try:
                dt = datetime.fromisoformat(app.last_played)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                last_played_epoch = int(dt.timestamp())
            except (ValueError, OSError):
                continue
            # Find the host address for this app
            host = next(
                (h for h in moonlight._paired_hosts if h.uuid == app.host_uuid),
                None,
            )
            host_address = host.address if host else ""
            recent_items.append({
                "name": app.name,
                "source": "moonlight",
                "imagePath": app.image_path,
                "lastPlayed": last_played_epoch,
                "appId": "",
                "hostAddress": host_address,
            })
        steam.setMoonlightRecentlyPlayed(recent_items)

    moonlight.hostsChanged.connect(_on_moonlight_hosts_changed)
    moonlight.loadingChanged.connect(_on_moonlight_hosts_changed)

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
            return False

    kb_detector = _KeyboardDetector(app)
    app.installEventFilter(kb_detector)

    # Gamepad manager — inject events into the root QML window
    gamepad_manager = GamepadManager(app)
    gamepad_manager.window = window
    gamepad_manager.keys = keys
    gamepad_manager.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
