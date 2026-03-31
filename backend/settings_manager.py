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

from backend.config import Config
from backend.controller_mapping import ACTIONS, get_default_mapping, save_mapping
from backend.library import GameLibrary
from backend.plex_account import PlexAccount

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
    romDirectoryChanged = Signal()
    retroarchCommandChanged = Signal()
    coresDirectoryChanged = Signal()
    plexServerUrlChanged = Signal()  # kept for backward compat with existing QML
    plexTokenChanged = Signal()
    plexServerIdChanged = Signal()
    plexUserIdChanged = Signal()
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
    watchViewModeChanged = Signal()
    listenViewModeChanged = Signal()
    tabVisibilityChanged = Signal()

    def __init__(
        self,
        config: Config,
        library: GameLibrary,
        plex_library: object,
        browser_launcher: object = None,
        moonlight_library: object = None,
        gamepad_manager: object = None,
        keys: object = None,
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
        self._oauth_timer: Optional[QTimer] = None
        self._oauth_pin_id: Optional[int] = None
        self._oauth_poll_count: int = 0

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

    def _get_plex_user_id(self) -> int:
        return self._config.plex_user_id or 0

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

    def _get_watch_view_mode(self) -> str:
        return self._config.watch_view_mode

    def _get_listen_view_mode(self) -> str:
        return self._config.listen_view_mode

    def _get_show_retro_games_tab(self) -> bool:
        return self._config.show_retro_games_tab

    def _get_show_pc_games_tab(self) -> bool:
        return self._config.show_pc_games_tab

    def _get_show_watch_tab(self) -> bool:
        return self._config.show_watch_tab

    def _get_show_listen_tab(self) -> bool:
        return self._config.show_listen_tab

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
    plexUserId = Property(
        int,
        fget=_get_plex_user_id,
        notify=plexUserIdChanged,
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

    @Slot(str)
    def setPlexServerId(self, server_id: str) -> None:
        """Set the Plex server machine identifier."""
        self._config.set_plex_server_id(server_id)
        self.plexServerIdChanged.emit()

    @Slot(int)
    def setPlexUserId(self, user_id: int) -> None:
        """Set the Plex home user ID."""
        self._config.set_plex_user_id(user_id)
        self.plexUserIdChanged.emit()

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
    def setShowWatchTab(self, enabled: bool) -> None:
        """Set the Watch tab visibility."""
        self._config.set_show_watch_tab(enabled)
        self.tabVisibilityChanged.emit()

    @Slot(bool)
    def setShowListenTab(self, enabled: bool) -> None:
        """Set the Listen tab visibility."""
        self._config.set_show_listen_tab(enabled)
        self.tabVisibilityChanged.emit()

    # -- Button layout ----------------------------------------------------

    buttonLayoutChanged = Signal()

    def _get_button_layout(self) -> str:
        return self._config.button_layout

    buttonLayout = Property(str, _get_button_layout,
                            notify=buttonLayoutChanged)

    @Slot(str)
    def setButtonLayout(self, layout: str) -> None:
        """Set the button layout ('standard' or 'alternate')."""
        self._config.set_button_layout(layout)
        # Also update the Keys object so labels change immediately
        if self._keys is not None:
            self._keys.setButtonLayout(layout)
        self.buttonLayoutChanged.emit()

    @Slot(str, str)
    def setSystemCore(self, folder_name: str, core: str) -> None:
        """Set the emulator core for a specific system."""
        self._config.set_system_core(folder_name, core)
        self.coresDirectoryChanged.emit()  # reuse signal to notify system core changes

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

        self._oauth_timer = QTimer(self)
        self._oauth_timer.setInterval(_OAUTH_POLL_INTERVAL_MS)
        self._oauth_timer.timeout.connect(self._poll_oauth_pin)
        self._oauth_timer.start()

    def _poll_oauth_pin(self) -> None:
        """Timer callback — check whether the user has completed OAuth login."""
        self._oauth_poll_count += 1

        if self._oauth_poll_count > _OAUTH_MAX_POLLS:
            logger.warning("signInWithPlex: timed out waiting for OAuth token")
            self._stop_oauth_timer()
            return

        token = PlexAccount.check_pin(self._oauth_pin_id)
        if token:
            logger.info("signInWithPlex: received auth token")
            self._config.set_plex_token(token)
            self.plexTokenChanged.emit()
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

    @Slot("QVariant")
    def saveControllerMapping(self, mapping: object) -> None:
        """Save a controller mapping recorded by the QML dialog.

        ``mapping`` is a JS array of objects from QML:
        ``[{name, type, code, value}, ...]``

        Converts to the dict format expected by save_mapping() and reloads.
        Also records the current device capabilities as ``_device`` so the
        browser extension can auto-generate its button/axis mapping.
        """
        # QML passes JS arrays as QJSValue — convert to Python list
        from PySide6.QtQml import QJSValue
        if isinstance(mapping, QJSValue):
            mapping = mapping.toVariant()
        if not isinstance(mapping, list):
            logger.warning("saveControllerMapping: expected list, got %s", type(mapping))
            return

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
                mapping_dict[name] = {"type": ev_type, "code": code, "value": value}

        # Record device capabilities so the browser extension can auto-generate
        # its Web Gamepad API mapping at deploy time.
        if self._gamepad_manager is not None:
            caps = self._gamepad_manager.getDeviceCapabilities()  # type: ignore[union-attr]
            if isinstance(caps, dict) and caps:
                mapping_dict["_device"] = caps

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
