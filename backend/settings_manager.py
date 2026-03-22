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
    Signal,
    Slot,
)

from backend.config import Config
from backend.library import GameLibrary
from backend.plex_account import PlexAccount

logger = logging.getLogger(__name__)


class SettingsManager(QObject):
    """Exposes application settings to QML.

    Constructor arguments:
        config       — the application :class:`Config` instance
        library      — the :class:`GameLibrary` instance (for rescan)
        plex_library — the :class:`PlexLibrary` instance (for connection test)
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
    videoSnapAutoplayChanged = Signal()
    videoSnapDelayMsChanged = Signal()

    def __init__(
        self,
        config: Config,
        library: GameLibrary,
        plex_library: object,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._library = library
        self._plex_library = plex_library

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

    def _get_video_snap_autoplay(self) -> bool:
        return self._config.video_snap_autoplay

    def _get_video_snap_delay_ms(self) -> int:
        return self._config.video_snap_delay_ms

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

    @Slot(str, str)
    def setSystemCore(self, folder_name: str, core: str) -> None:
        """Set the emulator core for a specific system."""
        self._config.set_system_core(folder_name, core)
        self.coresDirectoryChanged.emit()  # reuse signal to notify system core changes

    # ------------------------------------------------------------------
    # Slots — actions
    # ------------------------------------------------------------------

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
