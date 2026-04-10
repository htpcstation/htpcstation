"""Settings manager for HTPC Station.

Exposes application settings to QML as a context property named ``settings``.
Wraps :class:`~backend.config.Config` with Q_PROPERTYs and Slots so QML can
read and write all configurable values without importing Python modules.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QObject,
    Property,
    QTimer,
    Signal,
    Slot,
)

from backend.config import Config, SYSTEM_COMPATIBLE_CORES
from backend.controller_mapping import ACTIONS, get_default_mapping, load_mapping, save_mapping
from backend.library import GameLibrary
from backend.plex_account import PlexAccount
import backend.retroarch_config as _ra_cfg

logger = logging.getLogger(__name__)

_OAUTH_POLL_INTERVAL_MS = 2000   # 2 seconds between polls
_OAUTH_MAX_POLLS = 60            # give up after 60 × 2 s = 120 s

_OAUTH_URL_TEMPLATE = (
    "https://app.plex.tv/auth#?clientID=htpcstation"
    "&code={code}"
    "&context[device][product]=HTPC%20Station"
    "&context[device][device]=PC"
    "&context[device][deviceName]=HTPC%20Station"
)


class SettingsManager(QObject):
    """Exposes application settings to QML.

    Constructor arguments:
        config           — the application :class:`Config` instance
        library          — the :class:`GameLibrary` instance (for rescan)
        plex_library     — the :class:`PlexLibrary` instance (for connection test)
        browser_launcher — the :class:`BrowserLauncher` instance (for OAuth)
    """

    # One signal per property so Q_PROPERTY NOTIFY works correctly.
    plexLoginStatus = Signal(str)
    romDirectoryChanged = Signal()
    retroarchCommandChanged = Signal()
    coresDirectoryChanged = Signal()
    plexServerUrlChanged = Signal()  # kept for backward compat with existing QML
    plexTokenChanged = Signal()
    plexServerIdChanged = Signal()
    plexServerNameChanged = Signal()
    plexUserIdChanged = Signal()
    plexUserTitleChanged = Signal()
    browserCommandChanged = Signal()
    moonlightCommandChanged = Signal()
    moonlightHostUuidChanged = Signal()
    musicLibraryKeyChanged = Signal()
    videoSnapAutoplayChanged = Signal()
    videoSnapDelayMsChanged = Signal()
    showNetworkIndicatorChanged = Signal()
    sortRetroGamesChanged = Signal()
    sortSteamGamesChanged = Signal()
    sortMoonlightAppsChanged = Signal()
    sortPlexMoviesChanged = Signal()
    sortPlexShowsChanged = Signal()
    sortPlexArtistsChanged = Signal()
    filterPlexMovieGenreChanged = Signal()
    filterPlexShowGenreChanged = Signal()
    retroGamesViewModeChanged = Signal()
    pcGamesViewModeChanged = Signal()
    moonlightViewModeChanged = Signal()
    watchViewModeChanged = Signal()
    listenViewModeChanged = Signal()
    showMoonlightTabChanged = Signal()
    tabVisibilityChanged = Signal()
    themeNameChanged = Signal()
    accentColorChanged = Signal()
    focusRingColorChanged = Signal()

    def __init__(
        self,
        config: Config,
        library: GameLibrary,
        plex_library: object,
        browser_launcher: object = None,
        moonlight_library: object = None,
        gamepad_manager: object = None,
        keys: object = None,
        app_dir: Path = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._library = library
        self._plex_library = plex_library
        self._browser_launcher = browser_launcher
        self._moonlight_library = moonlight_library
        self._gamepad_manager = gamepad_manager
        self._keys = keys
        self._app_dir: Path = app_dir if app_dir is not None else Path(__file__).parent.parent
        self._oauth_timer: Optional[QTimer] = None
        self._oauth_pin_id: Optional[int] = None
        self._oauth_poll_count: int = 0
        self._login_mode: str = "browser"  # "browser" or "pin"

    # ------------------------------------------------------------------
    # Property getters
    # ------------------------------------------------------------------

    def _get_rom_directory(self) -> str:
        return str(self._config.rom_directory) if self._config.rom_directory else ""

    def _get_retroarch_command(self) -> str:
        return self._config.retroarch_command

    def _get_cores_directory(self) -> str:
        return str(self._config.cores_directory)

    def _get_plex_server_url(self) -> str:
        # Kept for backward compat — returns empty string (server URL is now runtime-resolved)
        return ""

    def _get_plex_token(self) -> str:
        return self._config.plex_token or ""

    def _get_plex_server_id(self) -> str:
        return self._config.plex_server_id or ""

    def _get_plex_server_name(self) -> str:
        return self._config.plex_server_name

    def _get_plex_user_id(self) -> int:
        return self._config.plex_user_id or 0

    def _get_plex_user_title(self) -> str:
        return self._config.plex_user_title

    def _get_browser_command(self) -> str:
        return self._config.browser_command

    def _get_moonlight_command(self) -> str:
        return self._config.moonlight_command

    def _get_moonlight_host_uuid(self) -> str:
        return self._config.moonlight_host_uuid

    def _get_music_library_key(self) -> str:
        return self._config.music_library_key

    def _get_video_snap_autoplay(self) -> bool:
        return self._config.video_snap_autoplay

    def _get_video_snap_delay_ms(self) -> int:
        return self._config.video_snap_delay_ms

    def _get_show_network_indicator(self) -> bool:
        return self._config.show_network_indicator

    def _get_sort_retro_games(self) -> str:
        return self._config.sort_retro_games

    def _get_sort_steam_games(self) -> str:
        return self._config.sort_steam_games

    def _get_sort_moonlight_apps(self) -> str:
        return self._config.sort_moonlight_apps

    def _get_sort_plex_movies(self) -> str:
        return self._config.sort_plex_movies

    def _get_sort_plex_shows(self) -> str:
        return self._config.sort_plex_shows

    def _get_sort_plex_artists(self) -> str:
        return self._config.sort_plex_artists

    def _get_filter_plex_movie_genre(self) -> str:
        return self._config.filter_plex_movie_genre

    def _get_filter_plex_show_genre(self) -> str:
        return self._config.filter_plex_show_genre

    def _get_retro_games_view_mode(self) -> str:
        return self._config.retro_games_view_mode

    def _get_pc_games_view_mode(self) -> str:
        return self._config.pc_games_view_mode

    def _get_moonlight_view_mode(self) -> str:
        return self._config.moonlight_view_mode

    def _get_watch_view_mode(self) -> str:
        return self._config.watch_view_mode

    def _get_listen_view_mode(self) -> str:
        return self._config.listen_view_mode

    def _get_show_retro_games_tab(self) -> bool:
        return self._config.show_retro_games_tab

    def _get_show_pc_games_tab(self) -> bool:
        return self._config.show_pc_games_tab

    def _get_show_moonlight_tab(self) -> bool:
        return self._config.show_moonlight_tab

    def _get_show_watch_tab(self) -> bool:
        return self._config.show_watch_tab

    def _get_show_listen_tab(self) -> bool:
        return self._config.show_listen_tab

    def _get_theme_name(self) -> str:
        return self._config.theme_name

    def _get_accent_color(self) -> str:
        return self._config.accent_color

    def _get_focus_ring_color(self) -> str:
        return self._config.focus_ring_color

    def _get_theme_dir(self) -> str:
        return "file://" + str(self._app_dir / "themes" / self._config.theme_name) + "/"

    def _get_theme_available(self) -> bool:
        return (self._app_dir / "themes" / self._config.theme_name).is_dir()

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    romDirectory = Property(
        str,
        fget=_get_rom_directory,
        notify=romDirectoryChanged,
    )
    retroarchCommand = Property(
        str,
        fget=_get_retroarch_command,
        notify=retroarchCommandChanged,
    )
    coresDirectory = Property(
        str,
        fget=_get_cores_directory,
        notify=coresDirectoryChanged,
    )
    plexServerUrl = Property(
        str,
        fget=_get_plex_server_url,
        notify=plexServerUrlChanged,
    )
    plexToken = Property(
        str,
        fget=_get_plex_token,
        notify=plexTokenChanged,
    )
    plexServerId = Property(
        str,
        fget=_get_plex_server_id,
        notify=plexServerIdChanged,
    )
    plexServerName = Property(
        str,
        fget=_get_plex_server_name,
        notify=plexServerNameChanged,
    )
    plexUserId = Property(
        int,
        fget=_get_plex_user_id,
        notify=plexUserIdChanged,
    )
    plexUserTitle = Property(
        str,
        fget=_get_plex_user_title,
        notify=plexUserTitleChanged,
    )
    browserCommand = Property(
        str,
        fget=_get_browser_command,
        notify=browserCommandChanged,
    )
    moonlightCommand = Property(
        str,
        fget=_get_moonlight_command,
        notify=moonlightCommandChanged,
    )
    moonlightHostUuid = Property(
        str,
        fget=_get_moonlight_host_uuid,
        notify=moonlightHostUuidChanged,
    )
    musicLibraryKey = Property(
        str,
        fget=_get_music_library_key,
        notify=musicLibraryKeyChanged,
    )
    videoSnapAutoplay = Property(
        bool,
        fget=_get_video_snap_autoplay,
        notify=videoSnapAutoplayChanged,
    )
    videoSnapDelayMs = Property(
        int,
        fget=_get_video_snap_delay_ms,
        notify=videoSnapDelayMsChanged,
    )
    showNetworkIndicator = Property(
        bool,
        fget=_get_show_network_indicator,
        notify=showNetworkIndicatorChanged,
    )
    sortRetroGames = Property(
        str,
        fget=_get_sort_retro_games,
        notify=sortRetroGamesChanged,
    )
    sortSteamGames = Property(
        str,
        fget=_get_sort_steam_games,
        notify=sortSteamGamesChanged,
    )
    sortMoonlightApps = Property(
        str,
        fget=_get_sort_moonlight_apps,
        notify=sortMoonlightAppsChanged,
    )
    sortPlexMovies = Property(
        str,
        fget=_get_sort_plex_movies,
        notify=sortPlexMoviesChanged,
    )
    sortPlexShows = Property(
        str,
        fget=_get_sort_plex_shows,
        notify=sortPlexShowsChanged,
    )
    sortPlexArtists = Property(
        str,
        fget=_get_sort_plex_artists,
        notify=sortPlexArtistsChanged,
    )
    filterPlexMovieGenre = Property(
        str,
        fget=_get_filter_plex_movie_genre,
        notify=filterPlexMovieGenreChanged,
    )
    filterPlexShowGenre = Property(
        str,
        fget=_get_filter_plex_show_genre,
        notify=filterPlexShowGenreChanged,
    )
    retroGamesViewMode = Property(
        str,
        fget=_get_retro_games_view_mode,
        notify=retroGamesViewModeChanged,
    )
    pcGamesViewMode = Property(
        str,
        fget=_get_pc_games_view_mode,
        notify=pcGamesViewModeChanged,
    )
    moonlightViewMode = Property(
        str,
        fget=_get_moonlight_view_mode,
        notify=moonlightViewModeChanged,
    )
    watchViewMode = Property(
        str,
        fget=_get_watch_view_mode,
        notify=watchViewModeChanged,
    )
    listenViewMode = Property(
        str,
        fget=_get_listen_view_mode,
        notify=listenViewModeChanged,
    )
    showRetroGamesTab = Property(
        bool,
        fget=_get_show_retro_games_tab,
        notify=tabVisibilityChanged,
    )
    showPcGamesTab = Property(
        bool,
        fget=_get_show_pc_games_tab,
        notify=tabVisibilityChanged,
    )
    showMoonlightTab = Property(
        bool,
        fget=_get_show_moonlight_tab,
        notify=showMoonlightTabChanged,
    )
    showWatchTab = Property(
        bool,
        fget=_get_show_watch_tab,
        notify=tabVisibilityChanged,
    )
    showListenTab = Property(
        bool,
        fget=_get_show_listen_tab,
        notify=tabVisibilityChanged,
    )
    themeName = Property(
        str,
        fget=_get_theme_name,
        notify=themeNameChanged,
    )
    themeDir = Property(
        str,
        fget=_get_theme_dir,
        notify=themeNameChanged,
    )
    themeAvailable = Property(
        bool,
        fget=_get_theme_available,
        notify=themeNameChanged,
    )
    accentColor = Property(str, fget=_get_accent_color, notify=accentColorChanged)
    focusRingColor = Property(str, fget=_get_focus_ring_color, notify=focusRingColorChanged)

    # ------------------------------------------------------------------
    # Slots — setters
    # ------------------------------------------------------------------

    @Slot(str)
    def setRomDirectory(self, path: str) -> None:
        """Set the ROM directory. Validates that the path exists."""
        expanded = Path(path).expanduser()
        if not expanded.is_dir():
            logger.warning("setRomDirectory: path does not exist: %s", path)
            return
        self._config.set_rom_directory(expanded)
        self.romDirectoryChanged.emit()

    @Slot(str)
    def setRetroarchCommand(self, cmd: str) -> None:
        """Set the RetroArch launch command."""
        self._config.set_retroarch_command(cmd)
        self.retroarchCommandChanged.emit()

    @Slot(str)
    def setCoresDirectory(self, path: str) -> None:
        """Set the RetroArch cores directory."""
        self._config.set_cores_directory(path)
        self.coresDirectoryChanged.emit()

    @Slot(str)
    def setPlexServerUrl(self, url: str) -> None:
        """Deprecated: server URL is now resolved at runtime. This is a no-op."""
        # Server URL is no longer user-configured; use setPlexServerId instead.
        logger.debug("setPlexServerUrl called but server URL is now runtime-resolved")

    @Slot(str)
    def setPlexToken(self, token: str) -> None:
        """Set the Plex authentication token."""
        self._config.set_plex_token(token)
        self.plexTokenChanged.emit()

    @Slot(str, str)
    def setPlexServerId(self, server_id: str, server_name: str = "") -> None:
        """Set the Plex server machine identifier and cached display name."""
        self._config.set_plex_server_id(server_id, server_name)
        self.plexServerIdChanged.emit()
        self.plexServerNameChanged.emit()

    @Slot(int, str)
    def setPlexUserId(self, user_id: int, user_title: str = "") -> None:
        """Set the Plex home user ID and cached display name."""
        self._config.set_plex_user_id(user_id, user_title)
        self.plexUserIdChanged.emit()
        self.plexUserTitleChanged.emit()

    @Slot(str)
    def setBrowserCommand(self, cmd: str) -> None:
        """Set the browser launch command."""
        self._config.set_browser_command(cmd)
        self.browserCommandChanged.emit()

    @Slot(str)
    def setMoonlightCommand(self, cmd: str) -> None:
        """Set the Moonlight launch command."""
        self._config.set_moonlight_command(cmd)
        self.moonlightCommandChanged.emit()

    @Slot(str)
    def setMoonlightHostUuid(self, uuid: str) -> None:
        """Set the selected Moonlight host UUID and tell the library to re-select."""
        self._config.set_moonlight_host_uuid(uuid)
        self.moonlightHostUuidChanged.emit()
        if self._moonlight_library is not None:
            self._moonlight_library.setSelectedHost(uuid)

    @Slot(str)
    def setMusicLibraryKey(self, key: str) -> None:
        """Set the selected Plex music library section key."""
        self._config.set_music_library_key(key)
        self.musicLibraryKeyChanged.emit()

    @Slot(bool)
    def setVideoSnapAutoplay(self, enabled: bool) -> None:
        """Enable or disable video snap autoplay."""
        self._config.set_video_snap_autoplay(enabled)
        self.videoSnapAutoplayChanged.emit()

    @Slot(int)
    def setVideoSnapDelayMs(self, delay: int) -> None:
        """Set the video snap playback delay in milliseconds."""
        self._config.set_video_snap_delay_ms(delay)
        self.videoSnapDelayMsChanged.emit()

    @Slot(bool)
    def setShowNetworkIndicator(self, enabled: bool) -> None:
        """Enable or disable the network status indicator."""
        self._config.set_show_network_indicator(enabled)
        self.showNetworkIndicatorChanged.emit()

    @Slot(str)
    def setSortRetroGames(self, key: str) -> None:
        """Persist the sort preference for the retro games grid."""
        self._config.set_sort_retro_games(key)
        self.sortRetroGamesChanged.emit()

    @Slot(str)
    def setSortSteamGames(self, key: str) -> None:
        """Persist the sort preference for the Steam games grid."""
        self._config.set_sort_steam_games(key)
        self.sortSteamGamesChanged.emit()

    @Slot(str)
    def setSortMoonlightApps(self, key: str) -> None:
        """Persist the sort preference for the Moonlight apps grid."""
        self._config.set_sort_moonlight_apps(key)
        self.sortMoonlightAppsChanged.emit()

    @Slot(str)
    def setSortPlexMovies(self, key: str) -> None:
        """Persist the sort preference for the Plex movies grid."""
        self._config.set_sort_plex_movies(key)
        self.sortPlexMoviesChanged.emit()

    @Slot(str)
    def setSortPlexShows(self, key: str) -> None:
        """Persist the sort preference for the Plex shows grid."""
        self._config.set_sort_plex_shows(key)
        self.sortPlexShowsChanged.emit()

    @Slot(str)
    def setSortPlexArtists(self, key: str) -> None:
        """Persist the sort preference for the Plex artists grid."""
        self._config.set_sort_plex_artists(key)
        self.sortPlexArtistsChanged.emit()

    @Slot(str)
    def setFilterPlexMovieGenre(self, key: str) -> None:
        """Persist the genre filter for Plex movies."""
        self._config.set_filter_plex_movie_genre(key)
        self.filterPlexMovieGenreChanged.emit()

    @Slot(str)
    def setFilterPlexShowGenre(self, key: str) -> None:
        """Persist the genre filter for Plex shows."""
        self._config.set_filter_plex_show_genre(key)
        self.filterPlexShowGenreChanged.emit()

    @Slot(str)
    def setRetroGamesViewMode(self, mode: str) -> None:
        """Persist the view mode for the retro games screen ('grid' or 'list')."""
        self._config.set_retro_games_view_mode(mode)
        self.retroGamesViewModeChanged.emit()

    @Slot(str)
    def setPcGamesViewMode(self, mode: str) -> None:
        """Persist the view mode for the PC games screen ('grid' or 'list')."""
        self._config.set_pc_games_view_mode(mode)
        self.pcGamesViewModeChanged.emit()

    @Slot(str)
    def setMoonlightViewMode(self, mode: str) -> None:
        """Persist the view mode for the Moonlight screen ('grid' or 'list')."""
        self._config.set_moonlight_view_mode(mode)
        self.moonlightViewModeChanged.emit()

    @Slot(str)
    def setWatchViewMode(self, mode: str) -> None:
        """Persist the view mode for the Watch screen ('grid' or 'list')."""
        self._config.set_watch_view_mode(mode)
        self.watchViewModeChanged.emit()

    @Slot(str)
    def setListenViewMode(self, mode: str) -> None:
        """Persist the view mode for the Listen screen ('grid' or 'list')."""
        self._config.set_listen_view_mode(mode)
        self.listenViewModeChanged.emit()

    @Slot(bool)
    def setShowRetroGamesTab(self, enabled: bool) -> None:
        """Set the Retro Games tab visibility."""
        self._config.set_show_retro_games_tab(enabled)
        self.tabVisibilityChanged.emit()

    @Slot(bool)
    def setShowPcGamesTab(self, enabled: bool) -> None:
        """Set the PC Games tab visibility."""
        self._config.set_show_pc_games_tab(enabled)
        self.tabVisibilityChanged.emit()

    @Slot(bool)
    def setShowMoonlightTab(self, enabled: bool) -> None:
        """Set the Moonlight tab visibility."""
        self._config.set_show_moonlight_tab(enabled)
        self.showMoonlightTabChanged.emit()

    @Slot(bool)
    def setShowWatchTab(self, enabled: bool) -> None:
        """Set the Watch tab visibility."""
        self._config.set_show_watch_tab(enabled)
        self.tabVisibilityChanged.emit()

    @Slot(bool)
    def setShowListenTab(self, enabled: bool) -> None:
        """Set the Listen tab visibility."""
        self._config.set_show_listen_tab(enabled)
        self.tabVisibilityChanged.emit()

    @Slot(str)
    def setAccentColor(self, color: str) -> None:
        """Set the accent color."""
        self._config.set_accent_color(color)
        self.accentColorChanged.emit()

    @Slot(str)
    def setFocusRingColor(self, color: str) -> None:
        """Set the focus ring color."""
        self._config.set_focus_ring_color(color)
        self.focusRingColorChanged.emit()

    # -- Button layout ----------------------------------------------------

    buttonLayoutChanged = Signal()

    def _get_button_layout(self) -> str:
        return self._config.button_layout

    buttonLayout = Property(str, _get_button_layout,
                            notify=buttonLayoutChanged)

    # -- Plex player --------------------------------------------------

    plexPlayerChanged = Signal()

    def _get_plex_player(self) -> str:
        return self._config.plex_player

    plexPlayer = Property(str, fget=_get_plex_player, notify=plexPlayerChanged)

    @Slot(str)
    def setPlexPlayer(self, player: str) -> None:
        """Set the Plex player ('mpv' or 'browser')."""
        self._config.set_plex_player(player)
        self.plexPlayerChanged.emit()

    # -- Auto-skip intro ----------------------------------------------

    autoSkipIntroChanged = Signal()

    def _get_auto_skip_intro(self) -> bool:
        return self._config.auto_skip_intro

    autoSkipIntro = Property(bool, fget=_get_auto_skip_intro, notify=autoSkipIntroChanged)

    @Slot(bool)
    def setAutoSkipIntro(self, enabled: bool) -> None:
        """Set whether to automatically skip intro markers during Plex playback."""
        self._config.set_auto_skip_intro(enabled)
        self.autoSkipIntroChanged.emit()


    @Slot(str)
    def setButtonLayout(self, layout: str) -> None:
        """Set the button layout ('standard' or 'alternate')."""
        self._config.set_button_layout(layout)
        # Also update the Keys object so labels change immediately
        if self._keys is not None:
            self._keys.setButtonLayout(layout)
        # Keep BrowserLauncher in sync so the next extension deploy uses the new layout
        if self._browser_launcher is not None:
            self._browser_launcher.set_button_layout(layout)
        self.buttonLayoutChanged.emit()

    @Slot(str, str)
    def setSystemCore(self, folder_name: str, core: str) -> None:
        """Set the emulator core for a specific system."""
        self._config.set_system_core(folder_name, core)
        self.coresDirectoryChanged.emit()  # reuse signal to notify system core changes

    @Slot(str, result="QVariant")
    def getAvailableCores(self, folder_name: str) -> list:
        """Return installed cores compatible with the given system folder name.

        Returns cores from SYSTEM_COMPATIBLE_CORES[folder_name] that are
        actually installed in cores_directory, preserving recommendation order.

        Falls back to [current_core] if the system has no entry in the map
        and the current core is installed. Returns [] if nothing is installed.
        """
        cores_dir = self._config.cores_directory
        if not cores_dir.is_dir():
            return []
        installed = {p.name for p in cores_dir.glob("*.so")}

        compatible = SYSTEM_COMPATIBLE_CORES.get(folder_name)
        if compatible is not None:
            return [c for c in compatible if c in installed]

        # Fallback: return current core if installed
        sys_config = self._config.get_system(folder_name)
        if sys_config.core and sys_config.core in installed:
            return [sys_config.core]
        return []

    # ------------------------------------------------------------------
    # Slots — actions
    # ------------------------------------------------------------------

    @Slot()
    def openMoonlight(self) -> None:
        """Launch the Moonlight GUI so the user can pair hosts and configure settings."""
        if self._moonlight_library is None:
            logger.warning("openMoonlight: no moonlight_library — cannot launch Moonlight GUI")
            return
        self._moonlight_library.launchGui()

    @Slot(result="QVariant")
    def getHostsList(self) -> list:
        """Return a list of paired Moonlight hosts for the Settings host selector.

        Returns ``[{"id": uuid, "label": "hostname (ip)"}]``.
        Delegates to MoonlightLibrary.getPairedHosts().
        """
        if self._moonlight_library is None:
            return []
        return self._moonlight_library.getPairedHosts()

    @Slot(result="QVariant")
    def getSystemsList(self) -> list:
        """Return a list of dicts for all discovered systems.

        Only systems that exist in the current ROM directory are returned
        (i.e. systems discovered by the library scan, not all built-in defaults).

        Each dict has keys: folderName, displayName, core.
        """
        rom_dir = self._config.rom_directory
        if rom_dir is None:
            return []

        rom_dir = Path(rom_dir)
        if not rom_dir.is_dir():
            return []

        result = []
        for entry in sorted(rom_dir.iterdir()):
            if not entry.is_dir():
                continue
            folder_name = entry.name
            sys_config = self._config.get_system(folder_name)
            result.append(
                {
                    "folderName": folder_name,
                    "displayName": sys_config.display_name,
                    "core": sys_config.core,
                }
            )
        return result

    @Slot(result=bool)
    def testPlexConnection(self) -> bool:
        """Test the plex.tv token connection synchronously.

        Validates the plex.tv token by calling PlexAccount.test_connection().
        Returns True if the token is valid, False otherwise.
        Blocks briefly — acceptable for a settings screen.
        """
        token = self._config.plex_token
        if not token:
            logger.info("testPlexConnection: no token configured")
            return False

        try:
            account = PlexAccount(token)
            success = account.test_connection()
            if success:
                logger.info("testPlexConnection: plex.tv token is valid")
            else:
                logger.warning("testPlexConnection: plex.tv token validation failed")
            return success
        except Exception as exc:  # noqa: BLE001
            logger.warning("testPlexConnection: failed — %s", exc)
            return False

    @Slot()
    def rescanLibrary(self) -> None:
        """Trigger a library rescan."""
        logger.info("rescanLibrary: rescanning ROM directory")
        self._library.rescan()

    @Slot()
    def signInWithPlex(self) -> None:
        """Start the Plex PIN-based OAuth flow.

        1. Creates a PIN via the plex.tv API.
        2. Opens the OAuth URL in the browser.
        3. Polls every 2 seconds (up to 120 s) for the auth token.
        4. On success, stores the token and emits ``plexTokenChanged``.
        """
        result = PlexAccount.create_pin()
        if result is None:
            logger.error("signInWithPlex: failed to create PIN")
            return

        pin_id, code = result
        oauth_url = _OAUTH_URL_TEMPLATE.format(code=code)
        logger.info("signInWithPlex: opening OAuth URL (pin_id=%s)", pin_id)

        if self._browser_launcher is not None:
            self._browser_launcher.launch(oauth_url)
        else:
            logger.warning("signInWithPlex: no browser_launcher — cannot open OAuth URL")

        # Stop any previous polling timer before starting a new one.
        if self._oauth_timer is not None:
            self._oauth_timer.stop()

        self._oauth_pin_id = pin_id
        self._oauth_poll_count = 0
        self._login_mode = "browser"

        self._oauth_timer = QTimer(self)
        self._oauth_timer.setInterval(_OAUTH_POLL_INTERVAL_MS)
        self._oauth_timer.timeout.connect(self._poll_oauth_pin)
        self._oauth_timer.start()

    @Slot()
    def startPlexPinLogin(self) -> None:
        """Start the PIN-based in-app Plex login flow.

        1. Creates a PIN via PlexAccount.create_pin().
        2. Emits plexLoginStatus("waiting:<code>") where <code> is the 4-char PIN.
        3. Polls every 2 s (up to 120 s) for the auth token.
        4. On success: stores token, emits plexTokenChanged, emits plexLoginStatus("success").
        5. On timeout: emits plexLoginStatus("timeout").
        6. On PIN creation failure: emits plexLoginStatus("error").
        """
        result = PlexAccount.create_pin()
        if result is None:
            logger.error("startPlexPinLogin: failed to create PIN")
            self.plexLoginStatus.emit("error")
            return

        pin_id, code = result
        logger.info("startPlexPinLogin: PIN created (pin_id=%s)", pin_id)

        # Stop any previous polling timer before starting a new one.
        if self._oauth_timer is not None:
            self._oauth_timer.stop()

        self._oauth_pin_id = pin_id
        self._oauth_poll_count = 0
        self._login_mode = "pin"

        self._oauth_timer = QTimer(self)
        self._oauth_timer.setInterval(_OAUTH_POLL_INTERVAL_MS)
        self._oauth_timer.timeout.connect(self._poll_oauth_pin)
        self._oauth_timer.start()

        self.plexLoginStatus.emit(f"waiting:{code}")

    @Slot()
    def cancelPlexPinLogin(self) -> None:
        """Cancel an in-progress PIN login. Emits plexLoginStatus("cancelled")."""
        self._stop_oauth_timer()
        self.plexLoginStatus.emit("cancelled")

    def _poll_oauth_pin(self) -> None:
        """Timer callback — check whether the user has completed OAuth login."""
        self._oauth_poll_count += 1

        if self._oauth_poll_count > _OAUTH_MAX_POLLS:
            logger.warning("_poll_oauth_pin: timed out waiting for OAuth token")
            self._stop_oauth_timer()
            if self._login_mode == "pin":
                self.plexLoginStatus.emit("timeout")
            return

        token = PlexAccount.check_pin(self._oauth_pin_id)
        if token:
            logger.info("_poll_oauth_pin: received auth token")
            self._config.set_plex_token(token)
            self.plexTokenChanged.emit()
            if self._login_mode == "pin":
                self.plexLoginStatus.emit("success")
            self._stop_oauth_timer()

    def _stop_oauth_timer(self) -> None:
        """Stop and discard the OAuth polling timer."""
        if self._oauth_timer is not None:
            self._oauth_timer.stop()
            self._oauth_timer = None
        self._oauth_pin_id = None
        self._oauth_poll_count = 0

    # ------------------------------------------------------------------
    # Slots — controller mapping
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def getControllerActions(self) -> list:
        """Return the ACTIONS list for QML as a list of dicts.

        Each dict has keys: name, displayName, skippable.
        """
        return [
            {"name": name, "displayName": display_name, "skippable": skippable}
            for name, display_name, _qt_key, skippable in ACTIONS
        ]

    @Slot(result="QVariant")
    def getControllerActionEvdevCodes(self) -> dict:
        """Return a dict of action_name → evdev button code for the current mapping.

        Used by ControllerMappingDialog to detect Start+Select combo cancel.
        Only includes button-type entries with a valid code.
        """
        from backend.controller_mapping import load_mapping
        mapping = load_mapping()
        result: dict[str, int] = {}
        for action, entry in mapping.items():
            if not isinstance(entry, dict):
                continue
            evdev = entry.get("evdev")
            if isinstance(evdev, dict) and evdev.get("type") == "button" and isinstance(evdev.get("code"), int):
                result[action] = evdev["code"]
        return result

    @Slot("QVariant")
    def saveControllerMapping(self, mapping: object) -> None:
        """Save a controller mapping recorded by the QML dialog.

        ``mapping`` is a JS array of objects from QML:
        ``[{name, type, code, value}, ...]``

        Converts to the dual-record format expected by save_mapping() and reloads.
        The SDL half is resolved at save time using the SdlResolver singleton.
        """
        # QML passes JS arrays as QJSValue — convert to Python list
        from PySide6.QtQml import QJSValue
        if isinstance(mapping, QJSValue):
            mapping = mapping.toVariant()
        if not isinstance(mapping, list):
            logger.warning("saveControllerMapping: expected list, got %s", type(mapping))
            return

        from backend.sdl_resolver import resolver as _sdl_resolver

        mapping_dict: dict[str, dict] = {}
        for entry in mapping:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            ev_type = entry.get("type")
            code = entry.get("code")
            value = entry.get("value")
            if (
                isinstance(name, str)
                and ev_type in ("button", "axis")
                and isinstance(code, int)
                and isinstance(value, int)
            ):
                evdev_part = {"type": ev_type, "code": code, "value": value}
                # Resolve SDL half — value for axis is already ±1 from raw mode normalisation
                sdl_part = _sdl_resolver.resolve(ev_type, code, value)

                # Resolve co-firing (also) events
                also_raw = entry.get("also") or []
                also_evdev: list[dict] = []
                for ae in also_raw:
                    ae_type = ae.get("type")
                    ae_code = ae.get("code")
                    ae_value = ae.get("value")
                    if (
                        ae_type in ("button", "axis")
                        and isinstance(ae_code, int)
                        and isinstance(ae_value, int)
                    ):
                        ae_evdev = {"type": ae_type, "code": ae_code, "value": ae_value}
                        ae_sdl = _sdl_resolver.resolve(ae_type, ae_code, ae_value)
                        also_evdev.append({"evdev": ae_evdev, "sdl": ae_sdl})

                mapping_dict[name] = {
                    "evdev": evdev_part,
                    "sdl": sdl_part,
                    "also": also_evdev,
                }

        # _device key is no longer stored — SDL resolution is done at capture time
        save_mapping(mapping_dict)
        logger.info("saveControllerMapping: saved %d entries", len(mapping_dict))

        if self._gamepad_manager is not None:
            self._gamepad_manager.reloadMapping()  # type: ignore[union-attr]

    @Slot()
    def resetControllerMapping(self) -> None:
        """Reset the controller mapping to factory defaults and reload."""
        save_mapping(get_default_mapping())
        logger.info("resetControllerMapping: reset to defaults")

        if self._gamepad_manager is not None:
            self._gamepad_manager.reloadMapping()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Slots — RetroArch hotkey configuration
    # ------------------------------------------------------------------

    # Ordered hotkey rows for the UI (hotkey-function-centric model).
    _HOTKEY_ROWS: list[dict] = [
        {"hotkey_action": "save_state",          "label": "Save State"},
        {"hotkey_action": "load_state",          "label": "Load State"},
        {"hotkey_action": "fast_forward_toggle", "label": "Fast Forward (Toggle)"},
        {"hotkey_action": "fast_forward_hold",   "label": "Fast Forward (Hold)"},
        {"hotkey_action": "rewind",              "label": "Rewind"},
        {"hotkey_action": "menu_toggle",         "label": "Open Menu"},
        {"hotkey_action": "screenshot",          "label": "Screenshot"},
        {"hotkey_action": "show_fps",            "label": "Show FPS"},
        {"hotkey_action": "state_slot_increase", "label": "Next Save Slot"},
        {"hotkey_action": "state_slot_decrease", "label": "Previous Save Slot"},
        {"hotkey_action": "pause_toggle",        "label": "Pause Toggle"},
        {"hotkey_action": "exit_emulator",       "label": "Exit Emulator"},
    ]

    # Human-readable labels for evdev button codes (kept for modifier fallback display).
    _EVDEV_LABELS: dict[int, str] = {
        304: "B/South", 305: "A/East", 307: "X/North", 308: "Y/West",
        310: "L1", 311: "R1", 312: "L2", 313: "R2",
        314: "Select", 315: "Start", 316: "Home",
        317: "L3", 318: "R3",
    }

    # Face button labels with cardinal positions.
    # SDL always uses Xbox button names internally: A=East, B=South, X=West, Y=North.
    # This codebase defines two layouts:
    #   Standard:  A=East, B=South, X=North, Y=West  (Nintendo-style labelling)
    #   Alternate: A=South, B=East, X=West, Y=North  (Xbox-style labelling)
    #
    # The maps below translate SDL names → display label + cardinal for each layout.
    # Standard swaps X↔Y relative to SDL (SDL X=West→display Y=West, SDL Y=North→display X=North).
    # Alternate matches SDL names directly (SDL X=West, SDL Y=North).
    _FACE_LABELS_STANDARD: dict[str, str] = {
        "A": "A (East)",   # SDL A = East physical = display A in standard
        "B": "B (South)",  # SDL B = South physical = display B in standard
        "X": "Y (West)",   # SDL X = West physical = display Y in standard
        "Y": "X (North)",  # SDL Y = North physical = display X in standard
    }
    _FACE_LABELS_ALTERNATE: dict[str, str] = {
        "A": "B (East)",   # SDL A = East physical = display B in alternate
        "B": "A (South)",  # SDL B = South physical = display A in alternate
        "X": "X (West)",   # SDL X = West physical = display X in alternate
        "Y": "Y (North)",  # SDL Y = North physical = display Y in alternate
    }

    def _sdl_record_label(self, sdl_record: dict | None) -> str:
        """Return a human-readable label for an SDL record, honoring button_layout."""
        if sdl_record is None or not isinstance(sdl_record, dict):
            return ""
        sdl_type = sdl_record.get("type")
        if sdl_type == "button":
            # Label is stored in the record at capture time by resolver.resolve()
            label = sdl_record.get("label", "")
            if label:
                # Expand face button labels with cardinal position
                face_map = (
                    self._FACE_LABELS_ALTERNATE
                    if self._config.button_layout == "alternate"
                    else self._FACE_LABELS_STANDARD
                )
                return face_map.get(label, label)
            # Fallback for records stored before label was added
            from backend.sdl_resolver import resolver as _sdl_resolver
            idx = sdl_record.get("sdl_button", -1)
            return _sdl_resolver.button_label(idx)
        elif sdl_type == "axis":
            # Label is stored in the record at capture time by resolver.resolve()
            label = sdl_record.get("label", "")
            if label:
                return label
            # Fallback for records stored before label was added
            axis = sdl_record.get("sdl_axis", -1)
            direction = sdl_record.get("dir", 1)
            return f"Axis {axis} {'-' if direction < 0 else '+'}"
        elif sdl_type == "hat":
            direction = sdl_record.get("dir", "")
            _HAT_LABELS = {"up": "D-pad Up", "down": "D-pad Down",
                           "left": "D-pad Left", "right": "D-pad Right"}
            return _HAT_LABELS.get(direction, f"Hat {direction}")
        return ""

    @Slot(result=bool)
    def hasControllerMappingWithSdl(self) -> bool:
        """Return True if the saved controller mapping has at least one non-null SDL half.

        Used by RetroarchHotkeysScreen to warn the user if they haven't run the
        controller mapping wizard before assigning hotkeys.
        """
        from backend.controller_mapping import load_mapping
        mapping = load_mapping()
        return any(
            isinstance(entry, dict) and isinstance(entry.get("sdl"), dict)
            for entry in mapping.values()
        )

    @Slot(result="QVariant")
    def getRetroarchHotkeyConfig(self) -> dict:
        """Return current hotkey config for QML.

        Returns dict with:
          - modifier_evdev: int | None  (evdev code of modifier button)
          - modifier_sdl_record: dict | None  (SDL record for modifier)
          - modifier_label: str         (human-readable button name, e.g. "Home")
          - mapping: dict[str, dict|None]  (hotkey_action → SDL record)
          - hotkey_rows: list[dict]     (ordered list for UI rows)
          - cfg_path: str
          - rewind_enable: bool
          - rewind_buffer_size: int
          - rewind_granularity: int
        """
        modifier_evdev = self._config.hotkey_modifier_evdev
        modifier_sdl_record = self._config.hotkey_modifier_sdl

        # Derive modifier label: prefer SDL record label, fall back to evdev label
        if modifier_sdl_record is not None:
            modifier_label = self._sdl_record_label(modifier_sdl_record)
        elif modifier_evdev is not None:
            modifier_label = self._EVDEV_LABELS.get(modifier_evdev, f"Button {modifier_evdev}")
        else:
            modifier_label = ""

        # The mapping is always config.hotkey_mapping (empty dict = nothing assigned yet).
        mapping = dict(self._config.hotkey_mapping)

        # Build ordered hotkey_rows list for UI rows.
        hotkey_rows = []
        for row in self._HOTKEY_ROWS:
            action = row["hotkey_action"]
            sdl_record = mapping.get(action)
            hotkey_rows.append({
                "hotkey_action": action,
                "label": row["label"],
                "sdl_record": sdl_record,
                "button_label": self._sdl_record_label(sdl_record),
            })

        return {
            "modifier_evdev": modifier_evdev,
            "modifier_sdl_record": modifier_sdl_record,
            "modifier_label": modifier_label,
            "mapping": mapping,
            "hotkey_rows": hotkey_rows,
            "cfg_path": self._config.retroarch_cfg_path_str,
            "rewind_enable": self._config.rewind_enable,
            "rewind_buffer_size": self._config.rewind_buffer_size,
            "rewind_granularity": self._config.rewind_granularity,
        }

    @Slot(str, int)
    def setHotkeyAction(self, hotkey_action: str, sdl_index: int) -> None:
        """Set a single hotkey action to a SDL button index. Persists immediately."""
        mapping = dict(self._config.hotkey_mapping)
        mapping[hotkey_action] = sdl_index
        self._config.set_hotkey_mapping(mapping)
        logger.debug("setHotkeyAction: %s → SDL %d", hotkey_action, sdl_index)

    @Slot(int)
    def setHotkeyModifier(self, evdev_code: int) -> None:
        """Set the modifier button by evdev code. Resolves SDL record. Persists."""
        from backend.sdl_resolver import resolver as _sdl_resolver
        sdl_record = _sdl_resolver.resolve("button", evdev_code, 1)
        # Evict any hotkey action using the same SDL record
        if sdl_record is not None:
            mapping = dict(self._config.hotkey_mapping)
            changed = False
            for action, rec in mapping.items():
                if rec == sdl_record:
                    mapping[action] = None
                    changed = True
            if changed:
                self._config.set_hotkey_mapping(mapping)
        self._config.set_hotkey_modifier_evdev(evdev_code)
        self._config.set_hotkey_modifier_sdl(sdl_record)
        logger.debug("setHotkeyModifier: evdev %d → SDL %s", evdev_code, sdl_record)

    @Slot()
    def clearHotkeyModifier(self) -> None:
        """Clear the modifier button (set to None). Persists."""
        self._config.set_hotkey_modifier_evdev(None)
        self._config.set_hotkey_modifier_sdl(None)
        logger.debug("clearHotkeyModifier: modifier cleared")

    @Slot()
    def applyRetroarchHotkeys(self) -> None:
        """Write current hotkey config to retroarch.cfg.

        Calls retroarch_config.build_hotkey_cfg() then write_cfg().
        Also writes rewind settings. Logs success or error. Does not raise.
        """
        modifier_sdl_record = self._config.hotkey_modifier_sdl
        mapping = dict(self._config.hotkey_mapping)

        cfg_updates = _ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record)
        cfg_path = self._config.retroarch_cfg_path
        try:
            _ra_cfg.write_cfg(cfg_path, cfg_updates)
            logger.info("applyRetroarchHotkeys: wrote %d keys to %s", len(cfg_updates), cfg_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("applyRetroarchHotkeys: failed to write %s: %s", cfg_path, exc)
            return

        rewind_updates = {
            "rewind_enable": "true" if self._config.rewind_enable else "false",
            "rewind_buffer_size": str(self._config.rewind_buffer_size),
            "rewind_granularity": str(self._config.rewind_granularity),
        }
        try:
            _ra_cfg.write_cfg(cfg_path, rewind_updates)
            logger.info("applyRetroarchHotkeys: wrote rewind settings to %s", cfg_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("applyRetroarchHotkeys: failed to write rewind settings to %s: %s", cfg_path, exc)

    @Slot(result=str)
    def getRetroarchCfgPath(self) -> str:
        """Return the current retroarch.cfg path."""
        return self._config.retroarch_cfg_path_str

    @Slot(str)
    def setRetroarchCfgPath(self, path: str) -> None:
        """Set the retroarch.cfg path and persist."""
        self._config.set_retroarch_cfg_path(path)
        logger.debug("setRetroarchCfgPath: %s", path)

    @Slot(bool)
    def setRewindEnable(self, value: bool) -> None:
        """Enable or disable rewind in RetroArch."""
        self._config.set_rewind_enable(value)

    @Slot(int)
    def setRewindBufferSize(self, value: int) -> None:
        """Set the rewind buffer size in MB."""
        self._config.set_rewind_buffer_size(value)

    @Slot(int)
    def setRewindGranularity(self, value: int) -> None:
        """Set the rewind granularity in frames."""
        self._config.set_rewind_granularity(value)

    @Slot(str, int)
    def setHotkeyActionByEvdev(self, hotkey_action: str, evdev_code: int) -> None:
        """Set a hotkey action by evdev button code. Resolves SDL record internally."""
        from backend.sdl_resolver import resolver as _sdl_resolver
        sdl_record = _sdl_resolver.resolve("button", evdev_code, 1)
        self._store_hotkey_sdl(hotkey_action, sdl_record)
        logger.debug("setHotkeyActionByEvdev: %s → evdev %d → SDL %s", hotkey_action, evdev_code, sdl_record)

    @Slot(str, int, int)
    def setHotkeyActionByAxis(self, hotkey_action: str, evdev_code: int, value: int) -> None:
        """Set a hotkey action by evdev axis/hat event. Resolves SDL record internally."""
        from backend.sdl_resolver import resolver as _sdl_resolver
        sdl_record = _sdl_resolver.resolve("axis", evdev_code, value)
        self._store_hotkey_sdl(hotkey_action, sdl_record)
        logger.debug("setHotkeyActionByAxis: %s → evdev %d/%d → SDL %s", hotkey_action, evdev_code, value, sdl_record)

    def _store_hotkey_sdl(self, hotkey_action: str, sdl_record: dict | None) -> None:
        """Store an SDL record for a hotkey action, evicting conflicts."""
        mapping = dict(self._config.hotkey_mapping)
        # Evict any OTHER action using the same SDL record
        if sdl_record is not None:
            for action, rec in mapping.items():
                if action != hotkey_action and rec == sdl_record:
                    mapping[action] = None
        # Evict modifier if it uses the same SDL record
        if sdl_record is not None and self._config.hotkey_modifier_sdl == sdl_record:
            self._config.set_hotkey_modifier_evdev(None)
            self._config.set_hotkey_modifier_sdl(None)
        mapping[hotkey_action] = sdl_record
        self._config.set_hotkey_mapping(mapping)

    @Slot(str)
    def clearHotkeyAction(self, hotkey_action: str) -> None:
        """Clear a single hotkey action (set to None/nul)."""
        mapping = dict(self._config.hotkey_mapping)
        mapping[hotkey_action] = None
        self._config.set_hotkey_mapping(mapping)
        logger.debug("clearHotkeyAction: %s cleared", hotkey_action)
