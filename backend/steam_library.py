"""Steam library manager for HTPC Station.

Exposes Steam game data to QML via models and slots.
Game discovery is synchronous (ACF files are small local reads).
Metadata fetching is asynchronous (HTTP calls via ThreadPoolExecutor).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QProcess,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.metadata_gamelist import read_gamelist, write_game_metadata
from backend.moonlight_play_history import clear_history
from backend.steam_config import get_steam_dir
from backend.steam_metadata import fetch_steam_metadata
from backend.steam_models import SteamGame
from backend.steam_parser import discover_steam_games

if TYPE_CHECKING:
    from backend.moonlight_library import MoonlightLibrary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SteamGameListModel
# ---------------------------------------------------------------------------


class SteamGameListModel(QAbstractListModel):
    """QAbstractListModel wrapping a list of :class:`SteamGame` objects.

    Roles: appId, name, imageLocal, lastPlayed, sizeOnDisk
    """

    AppIdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    ImageLocalRole = Qt.ItemDataRole.UserRole + 3
    LastPlayedRole = Qt.ItemDataRole.UserRole + 4
    SizeOnDiskRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._games: list[SteamGame] = []

    def set_games(self, games: list[SteamGame]) -> None:
        """Replace the model contents."""
        self.beginResetModel()
        self._games = games
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._games)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._games)):
            return None
        game = self._games[index.row()]
        if role == self.AppIdRole:
            return game.app_id
        if role == self.NameRole:
            return game.name
        if role == self.ImageLocalRole:
            return game.image_path
        if role == self.LastPlayedRole:
            return game.last_played
        if role == self.SizeOnDiskRole:
            return game.size_on_disk
        if role == Qt.ItemDataRole.DisplayRole:
            return game.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.AppIdRole: b"appId",
            self.NameRole: b"name",
            self.ImageLocalRole: b"imageLocal",
            self.LastPlayedRole: b"lastPlayed",
            self.SizeOnDiskRole: b"sizeOnDisk",
        }


# ---------------------------------------------------------------------------
# SteamSourceListModel
# ---------------------------------------------------------------------------


class SteamSourceListModel(QAbstractListModel):
    """QAbstractListModel for the source/system list in the PC Games screen.

    Initially contains a single "Steam" entry.  Extensible for GOG/Epic later.

    Roles: name, gameCount, source
    """

    NameRole = Qt.ItemDataRole.UserRole + 1
    GameCountRole = Qt.ItemDataRole.UserRole + 2
    SourceRole = Qt.ItemDataRole.UserRole + 3
    LoadingRole = Qt.ItemDataRole.UserRole + 4
    OfflineRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._sources: list[dict] = []

    def set_sources(self, sources: list[dict]) -> None:
        """Replace the model contents."""
        self.beginResetModel()
        self._sources = sources
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._sources)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._sources)):
            return None
        source = self._sources[index.row()]
        if role == self.NameRole:
            return source.get("name", "")
        if role == self.GameCountRole:
            return source.get("gameCount", 0)
        if role == self.SourceRole:
            return source.get("source", "")
        if role == self.LoadingRole:
            return source.get("loading", False)
        if role == self.OfflineRole:
            return source.get("offline", False)
        if role == Qt.ItemDataRole.DisplayRole:
            return source.get("name", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.GameCountRole: b"gameCount",
            self.SourceRole: b"source",
            self.LoadingRole: b"loading",
            self.OfflineRole: b"offline",
        }


# ---------------------------------------------------------------------------
# SteamLibrary — main orchestrator
# ---------------------------------------------------------------------------


class SteamLibrary(QObject):
    """Manages Steam game data and exposes it to QML.

    Exposed to QML as the ``steam`` context property.

    QML properties:
        sourcesModel — :class:`SteamSourceListModel` (system/source list)
        gamesModel   — :class:`SteamGameListModel` (game grid)

    QML slots:
        refresh()                       — re-scan ACF files, rebuild models
        getGame(index)                  — return game details dict for the detail view
        launchGame(appId)               — launch via xdg-open steam://rungameid/{appId}
        selectSource(source)            — select which source to display
        sortGames(sortKey)              — sort the games model (az, za, recent)
        setMoonlightRecentlyPlayed(items) — inject Moonlight recently played data
        getRecentlyPlayed()             — return unified recently played list
        launchRecentGame(source, appId, hostAddress, appName) — dispatch launch
    """

    sourcesModelChanged = Signal()
    gamesModelChanged = Signal()
    gameRunning = Signal()
    gameStopped = Signal()

    # Public signal: emitted when metadata is available for a game.
    # QML connects to this to update the detail view.
    # Signature: (appId: str, metadata: QVariant dict)
    metadataChanged = Signal(str, "QVariant")

    # Internal signal: marshals metadata fetch results from worker thread to main thread.
    # Signature: (appId: str, metadata: object — GameMetadata dict or None)
    _metadataReady = Signal(str, object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._game_running = False

        # All discovered games (unfiltered by source, unsorted beyond initial)
        self._all_games: list[SteamGame] = []
        # Games currently shown in gamesModel (may be a sorted/filtered subset)
        self._current_games: list[SteamGame] = []
        self._current_source: str = "steam"
        self._current_sort: str = "az"

        # Recently played: Moonlight items injected by main.py
        self._moonlight_recent: list[dict] = []

        # Moonlight sources injected by setMoonlightSources
        self._moonlight_sources: list[dict] = []

        # Reference to MoonlightLibrary for dispatching Moonlight launches
        self._moonlight_library: Optional["MoonlightLibrary"] = None

        # Metadata cache: keyed by app_id, populated from gamelist.xml during refresh()
        self._metadata_cache: dict = {}

        self._sources_model = SteamSourceListModel(self)
        self._games_model = SteamGameListModel(self)

        # Thread pool for metadata HTTP fetches (sequential — one detail view at a time)
        self._executor = ThreadPoolExecutor(max_workers=1)

        # Connect internal signal (worker thread → main thread)
        self._metadataReady.connect(self._on_metadata_ready)

        # Perform initial scan
        self.refresh()

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    sourcesModel = Property(
        QObject,
        fget=lambda self: self._sources_model,
        notify=sourcesModelChanged,
    )
    gamesModel = Property(
        QObject,
        fget=lambda self: self._games_model,
        notify=gamesModelChanged,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Re-scan ACF files and rebuild both models.

        Also reloads the metadata cache from gamelist.xml so that getGame()
        can return rich metadata without a network call.
        """
        self._all_games = discover_steam_games()
        logger.info("SteamLibrary.refresh: found %d games", len(self._all_games))

        # Load metadata cache from gamelist.xml
        try:
            self._metadata_cache = read_gamelist(get_steam_dir())
        except Exception as exc:  # noqa: BLE001
            logger.warning("SteamLibrary.refresh: failed to load metadata cache: %s", exc)
            self._metadata_cache = {}

        # Rebuild sources model with updated game count
        self._rebuild_sources_model()

        # Rebuild games model with current sort applied
        self._current_games = list(self._all_games)
        self._apply_sort()

    @Slot(int, result="QVariant")
    def getGame(self, index: int) -> dict:
        """Return a dict of all fields for the game at *index*.

        Merges any cached metadata from gamelist.xml into the returned dict.
        Returns an empty dict if the index is out of range.
        """
        if not (0 <= index < len(self._current_games)):
            return {}
        game = self._current_games[index]
        result = {
            "appId": game.app_id,
            "name": game.name,
            "installDir": game.install_dir,
            "lastPlayed": game.last_played,
            "sizeOnDisk": game.size_on_disk,
            "imagePath": game.image_path,
        }

        # Merge cached metadata if available
        cached = self._metadata_cache.get(game.app_id)
        if cached is not None:
            result["description"] = cached.description
            result["developer"] = cached.developer
            result["publisher"] = cached.publisher
            result["genre"] = cached.genre
            result["players"] = cached.players
            result["releaseDate"] = cached.release_date
            result["rating"] = cached.rating

        return result

    @Slot(str)
    def launchGame(self, app_id: str) -> None:
        """Launch a Steam game via xdg-open (fire-and-forget).

        Emits gameRunning so main.py can hide the window.  The window is
        restored when the application regains focus (gamepad Start button,
        Alt+Tab, or game exit) — see main.py for the applicationStateChanged
        handler.
        """
        if not app_id:
            logger.warning("SteamLibrary.launchGame: empty appId — ignoring")
            return
        url = f"steam://rungameid/{app_id}"
        logger.info("SteamLibrary.launchGame: launching %s", url)
        self._game_running = True
        self.gameRunning.emit()
        QProcess.startDetached("xdg-open", [url])

    def notifyGameStopped(self) -> None:
        """Called by main.py when the application regains focus after a Steam launch."""
        if self._game_running:
            self._game_running = False
            self.gameStopped.emit()

    @Slot(str)
    def fetchMetadata(self, app_id: str) -> None:
        """Fetch rich metadata for the game with *app_id*.

        1. Checks gamelist.xml first — if the entry has a non-empty description,
           emits ``metadataChanged`` immediately (cache hit, no API call).
        2. Otherwise, dispatches a background fetch via the thread pool.
           The worker writes the result to gamelist.xml and emits
           ``_metadataReady``, which is handled on the main thread by
           ``_on_metadata_ready``.

        Args:
            app_id: The Steam application ID as a string (e.g. "440").
        """
        if not app_id:
            logger.warning("SteamLibrary.fetchMetadata: empty app_id — ignoring")
            return

        # Check cache first
        cached = self._metadata_cache.get(app_id)
        if cached is not None and cached.description.strip():
            logger.debug(
                "SteamLibrary.fetchMetadata: cache hit for app_id=%s", app_id
            )
            self.metadataChanged.emit(app_id, _metadata_to_dict(cached))
            return

        # No cache — fetch from API on background thread
        logger.debug(
            "SteamLibrary.fetchMetadata: dispatching background fetch for app_id=%s",
            app_id,
        )
        self._executor.submit(self._worker_fetch_metadata, app_id)

    @Slot("QVariant")
    def setMoonlightSources(self, sources: list) -> None:
        """Inject Moonlight host entries into the source list.

        Accepts a list of ``{"name": ..., "gameCount": ..., "source": "moonlight:<uuid>"}``
        dicts.  Rebuilds the full sources model (Recently Played + Steam + Moonlight)
        and emits ``sourcesModelChanged``.

        Called by ``main.py`` whenever ``MoonlightLibrary.hostsChanged`` fires.
        When *sources* is empty, only the Steam entry is shown.
        """
        self._moonlight_sources = list(sources)
        self._rebuild_sources_model()

    @Slot("QVariant")
    def setMoonlightRecentlyPlayed(self, items: list) -> None:
        """Inject Moonlight recently played items.

        Accepts a list of dicts with keys: name, imagePath, lastPlayed (Unix epoch int),
        hostAddress.  Called by ``main.py`` after Moonlight refresh completes.
        Rebuilds the sources model to update the "Recently Played" count.
        """
        self._moonlight_recent = list(items)
        self._rebuild_sources_model()

    def setMoonlightLibrary(self, moonlight: "MoonlightLibrary") -> None:
        """Store a reference to MoonlightLibrary for dispatching Moonlight launches.

        Called by ``main.py`` after both libraries are constructed.
        """
        self._moonlight_library = moonlight

    @Slot(result="QVariant")
    def getRecentlyPlayed(self) -> list:
        """Return a unified list of recently played games from Steam and Moonlight.

        Returns a list of dicts sorted by lastPlayed descending, limited to 20 entries:
        ``{"name", "source", "imagePath", "lastPlayed", "appId", "hostAddress"}``
        """
        items: list[dict] = []

        # Steam: games with last_played > 0
        for game in self._all_games:
            if game.last_played > 0:
                items.append({
                    "name": game.name,
                    "source": "steam",
                    "imagePath": game.image_path,
                    "lastPlayed": game.last_played,
                    "appId": game.app_id,
                    "hostAddress": "",
                })

        # Moonlight: items injected by main.py
        items.extend(self._moonlight_recent)

        # Sort by lastPlayed descending and limit to 20
        items.sort(key=lambda x: x.get("lastPlayed", 0), reverse=True)
        return items[:20]

    @Slot(str, str, str, str)
    def launchRecentGame(
        self,
        source: str,
        app_id: str,
        host_address: str,
        app_name: str,
    ) -> None:
        """Dispatch a launch to the correct launcher based on *source*.

        For Steam: calls ``launchGame(appId)``.
        For Moonlight: calls ``MoonlightLibrary.launchApp(hostAddress, appName)``.
        """
        if source == "steam":
            self.launchGame(app_id)
        elif source == "moonlight":
            if self._moonlight_library is not None:
                self._moonlight_library.launchApp(host_address, app_name)
            else:
                logger.warning(
                    "SteamLibrary.launchRecentGame: no MoonlightLibrary set — "
                    "cannot launch Moonlight app '%s'",
                    app_name,
                )
        else:
            logger.warning(
                "SteamLibrary.launchRecentGame: unknown source '%s' — ignoring",
                source,
            )

    @Slot()
    def clearRecentlyPlayed(self) -> None:
        """Clear Moonlight play history.

        Steam play history is managed by Steam itself and cannot be modified.
        Only Moonlight history (stored in play_history.json) is cleared.
        Rebuilds the sources model so the "Recently Played" entry disappears.
        """
        clear_history()
        self._moonlight_recent = []
        self._rebuild_sources_model()
        logger.info("SteamLibrary.clearRecentlyPlayed: cleared Moonlight play history")

    @Slot(str)
    def selectSource(self, source: str) -> None:
        """Select which source to display.

        Currently only "steam" is supported.  Rebuilds gamesModel.
        """
        self._current_source = source
        # Future: filter self._all_games by source when GOG/Epic are added.
        # For now, all games are from Steam.
        self._current_games = list(self._all_games)
        self._apply_sort()

    @Slot(str)
    def sortGames(self, sort_key: str) -> None:
        """Sort the games model.

        sort_key: 'az' (A-Z), 'za' (Z-A), 'recent' (by LastPlayed descending).
        """
        self._current_sort = sort_key
        self._apply_sort()

    # ------------------------------------------------------------------
    # Internal: worker thread function (metadata fetch)
    # ------------------------------------------------------------------

    def _worker_fetch_metadata(self, app_id: str) -> None:
        """Worker: fetch metadata from Steam Store API and write to gamelist.xml.

        Runs on the thread pool.  Emits ``_metadataReady`` with the result
        (a dict or None) so the main thread can update the UI.
        """
        result = fetch_steam_metadata(app_id)
        if result is not None:
            try:
                write_game_metadata(get_steam_dir(), app_id, result)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SteamLibrary._worker_fetch_metadata: failed to write metadata "
                    "for app_id=%s: %s",
                    app_id,
                    exc,
                )
        result_dict = _metadata_to_dict(result) if result is not None else None
        self._metadataReady.emit(app_id, result_dict)

    # ------------------------------------------------------------------
    # Internal: main-thread result handler
    # ------------------------------------------------------------------

    def _on_metadata_ready(self, app_id: str, metadata: object) -> None:
        """Handle metadata fetch result on the main thread.

        Connected to ``_metadataReady`` in ``__init__``.  Updates the in-memory
        cache and emits ``metadataChanged`` so QML can update the detail view.

        Args:
            app_id: The Steam application ID.
            metadata: A dict with camelCase keys (from ``_metadata_to_dict``),
                      or ``None`` if the fetch failed.
        """
        if metadata is not None:
            # Update the in-memory cache so subsequent getGame() calls are fast.
            # Re-read from disk to get the freshly written entry.
            try:
                self._metadata_cache = read_gamelist(get_steam_dir())
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SteamLibrary._on_metadata_ready: failed to reload metadata cache: %s",
                    exc,
                )
            self.metadataChanged.emit(app_id, metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_sources_model(self) -> None:
        """Rebuild the sources model from current state and emit sourcesModelChanged.

        Order: "Recently Played" (if any) → "Steam" → Moonlight sources.
        """
        sources: list[dict] = []

        # "Recently Played" entry — only shown when there are recently played games
        recent_count = self._count_recently_played()
        if recent_count > 0:
            sources.append({
                "name": "Recently Played",
                "gameCount": recent_count,
                "source": "recent",
            })

        # Steam entry
        sources.append({
            "name": "Steam",
            "gameCount": len(self._all_games),
            "source": "steam",
        })

        # Moonlight entries
        sources.extend(self._moonlight_sources)

        self._sources_model.set_sources(sources)
        self.sourcesModelChanged.emit()

    def _count_recently_played(self) -> int:
        """Return the total number of recently played games (Steam + Moonlight), capped at 20."""
        steam_played = [g for g in self._all_games if g.last_played > 0]
        combined = steam_played + self._moonlight_recent
        return min(len(combined), 20)

    def _apply_sort(self) -> None:
        """Sort ``_current_games`` and push the result to ``_games_model``."""
        games = list(self._current_games)

        if self._current_sort == "az":
            games.sort(key=lambda g: g.name.lower())
        elif self._current_sort == "za":
            games.sort(key=lambda g: g.name.lower(), reverse=True)
        elif self._current_sort == "recent":
            played = sorted(
                [g for g in games if g.last_played],
                key=lambda g: g.last_played,
                reverse=True,
            )
            unplayed = [g for g in games if not g.last_played]
            games = played + unplayed
        else:
            logger.warning("SteamLibrary._apply_sort: unknown sort_key '%s'", self._current_sort)
            games.sort(key=lambda g: g.name.lower())

        self._current_games = games
        self._games_model.set_games(games)
        self.gamesModelChanged.emit()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _metadata_to_dict(metadata: object) -> dict:
    """Convert a :class:`GameMetadata` instance to a camelCase dict for QML.

    Keys: ``name``, ``appId``, ``description``, ``developer``, ``publisher``,
    ``genre``, ``players``, ``releaseDate``, ``rating``.

    Args:
        metadata: A :class:`~backend.metadata_gamelist.GameMetadata` instance.

    Returns:
        A dict with camelCase keys suitable for QML consumption.
    """
    return {
        "name": metadata.name,
        "appId": metadata.app_id,
        "description": metadata.description,
        "developer": metadata.developer,
        "publisher": metadata.publisher,
        "genre": metadata.genre,
        "players": metadata.players,
        "releaseDate": metadata.release_date,
        "rating": metadata.rating,
    }
