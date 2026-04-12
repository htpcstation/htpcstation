"""Game library manager for HTPC Station.

Scans the ROM directory, parses gamelists, and exposes the data to QML via
QAbstractListModel subclasses.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from backend.config import Config
from backend.gamelist import parse_gamelist, write_game_stats
from backend.launcher import Launcher
from backend.models import Game, System

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filesystem fallback helpers
# ---------------------------------------------------------------------------


def _clean_rom_title(filename: str) -> str:
    """Derive a display title from a ROM filename.

    Strips the extension, removes anything in parentheses or brackets
    (including the delimiters themselves), and trims whitespace.
    """
    name = Path(filename).stem
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    return name.strip()


def _scan_rom_files(
    system_path: Path,
    folder_name: str,
    extensions: list[str],
) -> list[Game]:
    """Scan *system_path* for ROM files matching *extensions*.

    Returns a list of :class:`Game` objects with cleaned filenames as titles,
    sorted case-insensitively by name.  Only top-level files are considered
    (no recursive descent).
    """
    ext_lower = {ext.lower() for ext in extensions}
    games: list[Game] = []
    for child in sorted(system_path.iterdir()):
        if not child.is_file():
            continue
        if child.suffix.lower() not in ext_lower:
            continue
        games.append(
            Game(
                path=child.resolve(),
                name=_clean_rom_title(child.name),
                system_folder=folder_name,
            )
        )
    games.sort(key=lambda g: g.name.lower())
    return games


# ---------------------------------------------------------------------------
# SystemListModel
# ---------------------------------------------------------------------------


class SystemListModel(QAbstractListModel):
    """QAbstractListModel wrapping a list of :class:`System` objects.

    Roles:
        displayName  — human-readable system name (e.g. "Neo Geo Pocket Color")
        folderName   — directory name (e.g. "ngpc")
        gameCount    — number of games in the system
    """

    # Custom role IDs start at Qt.UserRole (256) + 1 = 257
    DisplayNameRole = Qt.ItemDataRole.UserRole + 1   # 257
    FolderNameRole = Qt.ItemDataRole.UserRole + 2    # 258
    GameCountRole = Qt.ItemDataRole.UserRole + 3     # 259

    def __init__(self, systems: list[System], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._systems = systems

    # ------------------------------------------------------------------
    # QAbstractListModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._systems)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._systems)):
            return None
        system = self._systems[index.row()]
        if role == self.DisplayNameRole:
            return system.display_name
        if role == self.FolderNameRole:
            return system.folder_name
        if role == self.GameCountRole:
            return system.game_count
        if role == Qt.ItemDataRole.DisplayRole:
            return system.display_name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.DisplayNameRole: b"displayName",
            self.FolderNameRole: b"folderName",
            self.GameCountRole: b"gameCount",
        }


# ---------------------------------------------------------------------------
# GameListModel
# ---------------------------------------------------------------------------


class GameListModel(QAbstractListModel):
    """QAbstractListModel wrapping a list of :class:`Game` objects.

    Roles:
        name         — game title
        description  — long description
        imagePath    — file:// URL string for QML Image source (empty if no image)
        videoPath    — file:// URL string to video file (empty if absent)
        rating       — float 0.0–1.0
        releaseDate  — raw date string e.g. "19990527T000000"
        developer    — developer name
        publisher    — publisher name
        genre        — genre string
        players      — players string e.g. "1", "2", "1-2"
        favorite     — bool
        playCount    — int
        lastPlayed   — raw date string
        gameTime     — int (seconds)
        romPath      — absolute path string to ROM file
        systemFolder — system folder name e.g. "ngpc"
    """

    NameRole = Qt.ItemDataRole.UserRole + 1          # 257
    DescriptionRole = Qt.ItemDataRole.UserRole + 2   # 258
    ImagePathRole = Qt.ItemDataRole.UserRole + 3     # 259
    VideoPathRole = Qt.ItemDataRole.UserRole + 4     # 260
    RatingRole = Qt.ItemDataRole.UserRole + 5        # 261
    ReleaseDateRole = Qt.ItemDataRole.UserRole + 6   # 262
    DeveloperRole = Qt.ItemDataRole.UserRole + 7     # 263
    PublisherRole = Qt.ItemDataRole.UserRole + 8     # 264
    GenreRole = Qt.ItemDataRole.UserRole + 9         # 265
    PlayersRole = Qt.ItemDataRole.UserRole + 10      # 266
    FavoriteRole = Qt.ItemDataRole.UserRole + 11     # 267
    PlayCountRole = Qt.ItemDataRole.UserRole + 12    # 268
    LastPlayedRole = Qt.ItemDataRole.UserRole + 13   # 269
    GameTimeRole = Qt.ItemDataRole.UserRole + 14     # 270
    RomPathRole = Qt.ItemDataRole.UserRole + 15      # 271
    SystemFolderRole = Qt.ItemDataRole.UserRole + 16 # 272

    def __init__(self, games: list[Game], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._games = games

    # ------------------------------------------------------------------
    # QAbstractListModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._games)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._games)):
            return None
        game = self._games[index.row()]

        if role == self.NameRole:
            return game.name
        if role == self.DescriptionRole:
            return game.description
        if role == self.ImagePathRole:
            if game.image_path is not None:
                return QUrl.fromLocalFile(str(game.image_path)).toString()
            return ""
        if role == self.VideoPathRole:
            if game.video_path is not None:
                return QUrl.fromLocalFile(str(game.video_path)).toString()
            return ""
        if role == self.RatingRole:
            return game.rating
        if role == self.ReleaseDateRole:
            return game.release_date
        if role == self.DeveloperRole:
            return game.developer
        if role == self.PublisherRole:
            return game.publisher
        if role == self.GenreRole:
            return game.genre
        if role == self.PlayersRole:
            return game.players
        if role == self.FavoriteRole:
            return game.favorite
        if role == self.PlayCountRole:
            return game.play_count
        if role == self.LastPlayedRole:
            return game.last_played
        if role == self.GameTimeRole:
            return game.game_time
        if role == self.RomPathRole:
            return str(game.path)
        if role == self.SystemFolderRole:
            return game.system_folder
        if role == Qt.ItemDataRole.DisplayRole:
            return game.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.DescriptionRole: b"description",
            self.ImagePathRole: b"imagePath",
            self.VideoPathRole: b"videoPath",
            self.RatingRole: b"rating",
            self.ReleaseDateRole: b"releaseDate",
            self.DeveloperRole: b"developer",
            self.PublisherRole: b"publisher",
            self.GenreRole: b"genre",
            self.PlayersRole: b"players",
            self.FavoriteRole: b"favorite",
            self.PlayCountRole: b"playCount",
            self.LastPlayedRole: b"lastPlayed",
            self.GameTimeRole: b"gameTime",
            self.RomPathRole: b"romPath",
            self.SystemFolderRole: b"systemFolder",
        }

    def notify_game_changed(self, row: int) -> None:
        """Emit dataChanged for the game at *row* so QML bindings update."""
        if 0 <= row < len(self._games):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, list(self.roleNames().keys()))

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the name of the game at *index*, or "" if out of range."""
        if 0 <= index < len(self._games):
            return self._games[index].name
        return ""


# ---------------------------------------------------------------------------
# GameLibrary — main orchestrator
# ---------------------------------------------------------------------------


class GameLibrary(QObject):
    """Manages the game library and exposes it to QML.

    On construction, scans ``config.rom_directory`` for system folders that
    contain a ``gamelist.xml``, parses them, and builds the QML models.

    QML properties:
        systemsModel  — :class:`SystemListModel` of all discovered systems
        gamesModel    — :class:`GameListModel` for the currently selected system
        currentSystem — folder name of the currently selected system (str)

    QML slots:
        selectSystem(folderName)  — switch the active games model
        getGame(index)            — return a dict of all fields for one game
        launchGame(index)         — launch the game at the given index
        toggleFavorite(index)     — toggle favorite and persist to gamelist.xml
    """

    systemsModelChanged = Signal()
    gamesModelChanged = Signal()
    currentSystemChanged = Signal(str)
    favoriteToggled = Signal(bool)  # emitted after toggleFavorite; arg is new favorite state
    favoriteSorted = Signal(int)    # emitted after toggleFavorite re-sort; arg is new index of the game
    favoritesOnTopChanged = Signal()

    def __init__(
        self,
        config: Config,
        launcher: Optional[Launcher] = None,
        parent: Optional[QObject] = None,
        recently_played=None,
    ) -> None:
        super().__init__(parent)

        self._config = config
        self._launcher = launcher
        self._recently_played = recently_played
        self._systems: list[System] = []
        self._systems_by_folder: dict[str, System] = {}
        self._current_system: str = ""

        # Track the game that is currently being played so we can update stats
        # when the process finishes.
        self._active_game: Optional[Game] = None
        self._active_game_index: int = -1
        self._active_games_model: Optional[GameListModel] = None

        # Sort state — reset when selectSystem is called
        self._current_games_unfiltered: list[Game] = []
        self._current_sort: str = "az"
        self._favorites_on_top: bool = True

        # Build empty models first so properties are always valid
        self._systems_model = SystemListModel(self._systems, self)
        self._games_model = GameListModel([], self)

        if self._launcher is not None:
            self._launcher.processFinished.connect(self._on_process_finished)

        self._scan()

    # ------------------------------------------------------------------
    # Q_PROPERTYs (exposed to QML)
    # ------------------------------------------------------------------

    @property
    def systems_model(self) -> SystemListModel:
        return self._systems_model

    @property
    def games_model(self) -> GameListModel:
        return self._games_model

    @property
    def current_system(self) -> str:
        return self._current_system

    # PySide6 Q_PROPERTY declarations
    systemsModel = Property(
        QObject,
        fget=lambda self: self._systems_model,
        notify=systemsModelChanged,
    )
    gamesModel = Property(
        QObject,
        fget=lambda self: self._games_model,
        notify=gamesModelChanged,
    )
    currentSystem = Property(
        str,
        fget=lambda self: self._current_system,
        notify=currentSystemChanged,
    )
    favoritesOnTop = Property(
        bool,
        fget=lambda self: self._favorites_on_top,
        notify=favoritesOnTopChanged,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def selectSystem(self, folder_name: str) -> None:
        """Switch the active games model to the system identified by *folder_name*.

        When *folder_name* starts with ``_`` (a virtual collection), the
        collection data is rebuilt first so it reflects the latest favorites
        and play history.

        Resets sort to "az".
        """
        if folder_name.startswith("_"):
            self._rebuild_collections()

        system = self._systems_by_folder.get(folder_name)
        if system is None:
            logger.warning("selectSystem: unknown system '%s'", folder_name)
            return

        # Reset sort state for the new system
        self._current_games_unfiltered = list(system.games)
        self._current_sort = "az"
        self._current_system = folder_name
        self._apply_sort_filter()
        self.currentSystemChanged.emit(folder_name)

    @Slot(str)
    def sortGames(self, sort_key: str) -> None:
        """Sort the current games model.

        sort_key: 'az' (A-Z), 'za' (Z-A),
                  'recent' (by last_played descending, games with no last_played go last).

        Rebuilds the GameListModel with the sorted game list and emits gamesModelChanged.
        """
        self._current_sort = sort_key
        self._apply_sort_filter()

    @Slot(bool)
    def setFavoritesOnTop(self, val: bool) -> None:
        """Set whether favorites are pinned to the top of the games list.

        Re-applies sort/filter immediately.  This is a sticky preference and is
        NOT reset by selectSystem.
        """
        if val == self._favorites_on_top:
            return
        self._favorites_on_top = val
        self._apply_sort_filter()
        self.favoritesOnTopChanged.emit()

    @Slot(int, result="QVariant")
    def getGame(self, index: int) -> dict:
        """Return a dict of all fields for the game at *index* in the current games model.

        Returns an empty dict if the index is out of range.
        """
        games = self._games_model._games
        if not (0 <= index < len(games)):
            return {}
        game = games[index]
        return {
            "name": game.name,
            "description": game.description,
            "imagePath": (
                QUrl.fromLocalFile(str(game.image_path)).toString()
                if game.image_path is not None
                else ""
            ),
            "videoPath": (
                QUrl.fromLocalFile(str(game.video_path)).toString()
                if game.video_path is not None
                else ""
            ),
            "rating": game.rating,
            "releaseDate": game.release_date,
            "developer": game.developer,
            "publisher": game.publisher,
            "genre": game.genre,
            "players": game.players,
            "favorite": game.favorite,
            "playCount": game.play_count,
            "lastPlayed": game.last_played,
            "gameTime": game.game_time,
            "romPath": str(game.path),
            "systemFolder": game.system_folder,
        }

    @Slot(int)
    def launchGame(self, index: int) -> None:
        """Launch the game at *index* in the current games model.

        Does nothing if the index is out of range or no launcher is configured.
        """
        if self._launcher is None:
            logger.warning("launchGame: no launcher configured")
            return

        games = self._games_model._games
        if not (0 <= index < len(games)):
            logger.warning("launchGame: index %d out of range (model has %d games)", index, len(games))
            return

        game = games[index]
        command = self._config.get_launch_command(game.system_folder, game.path)
        logger.info("launchGame: launching '%s' — %s", game.name, command)

        if self._recently_played:
            artwork = ("file://" + str(game.image_path)) if game.image_path else ""
            system = self._systems_by_folder.get(game.system_folder)
            system_display_name = system.display_name if system is not None else game.system_folder
            self._recently_played.record(
                "retro",
                game.name,
                artwork,
                {
                    "rom_path": str(game.path),
                    "system_folder": game.system_folder,
                    "system_display_name": system_display_name,
                },
            )

        # Set active game optimistically before the async launch.  If the
        # process fails to start, _on_process_finished(-1, 0) will be called
        # and will clear these fields (game is None guard handles that).
        self._active_game = game
        self._active_game_index = index
        self._active_games_model = self._games_model
        self._launcher.launch(command)

    @Slot()
    def rescan(self) -> None:
        """Re-scan the ROM directory and rebuild all models."""
        self._scan()

    @Slot()
    def clearRecentlyPlayed(self) -> None:
        """Reset play_count and last_played for all games in all real systems.

        Iterates over every real system (non-collection) and resets play_count
        to 0 and last_played to "" for any game that has play history, then
        persists the change to gamelist.xml.  Rebuilds collections afterwards
        so the UI reflects the cleared state.
        """
        real_systems = [s for s in self._systems if not s.folder_name.startswith("_")]
        for system in real_systems:
            for game in system.games:
                if game.play_count > 0 or game.last_played:
                    game.play_count = 0
                    game.last_played = ""
                    write_game_stats(system.path, game)
        self._rebuild_collections()
        logger.info("clearRecentlyPlayed: cleared play history for all retro games")

    @Slot(int)
    def toggleFavorite(self, index: int) -> None:
        """Toggle the favorite status of the game at *index* and persist to gamelist.xml."""
        games = self._games_model._games
        if not (0 <= index < len(games)):
            logger.warning("toggleFavorite: index %d out of range", index)
            return

        game = games[index]
        game.favorite = not game.favorite
        logger.info(
            "toggleFavorite: '%s' favorite=%s", game.name, game.favorite
        )

        # Notify QML that this row changed
        self._games_model.notify_game_changed(index)

        # Emit signal so QML can show a toast notification
        self.favoriteToggled.emit(game.favorite)

        # Re-sort the current model so the game immediately moves to/from the
        # top of the list when _favorites_on_top is enabled.
        self._apply_sort_filter()

        # Tell QML where the game landed after the re-sort so focus can be restored.
        new_index = next(
            (i for i, g in enumerate(self._games_model._games) if g is game), -1
        )
        if new_index >= 0:
            self.favoriteSorted.emit(new_index)

        # Persist to gamelist.xml
        system = self._systems_by_folder.get(game.system_folder)
        if system is not None:
            write_game_stats(system.path, game)
        else:
            logger.warning(
                "toggleFavorite: system '%s' not found — cannot write gamelist.xml",
                game.system_folder,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_sort_filter(self) -> None:
        """Rebuild the games model applying the current sort.

        Uses ``_current_games_unfiltered`` as the source, sorts the result,
        and replaces ``_games_model``.
        """
        games = list(self._current_games_unfiltered)

        # Apply sort
        sort_key = self._current_sort
        if sort_key == "az":
            games.sort(key=lambda g: g.name.lower())
        elif sort_key == "za":
            games.sort(key=lambda g: g.name.lower(), reverse=True)
        elif sort_key == "recent":
            # Played games sorted descending by last_played, unplayed at end
            played = sorted([g for g in games if g.last_played], key=lambda g: g.last_played, reverse=True)
            unplayed = [g for g in games if not g.last_played]
            games = played + unplayed
        else:
            logger.warning("_apply_sort_filter: unknown sort_key '%s'", sort_key)
            games.sort(key=lambda g: g.name.lower())

        # Partition favorites to the top (unless already in the _favorites collection)
        if self._favorites_on_top and self._current_system != "_favorites":
            favs = [g for g in games if g.favorite]
            non_favs = [g for g in games if not g.favorite]
            games = favs + non_favs

        self._games_model = GameListModel(games, self)
        self.gamesModelChanged.emit()

    def _on_process_finished(self, exit_code: int, elapsed_seconds: int) -> None:
        """Handle emulator process exit — update play stats and write back to gamelist.xml."""
        game = self._active_game
        if game is None:
            return

        index = self._active_game_index
        launch_model = self._active_games_model
        self._active_game = None
        self._active_game_index = -1
        self._active_games_model = None

        if exit_code == -1:
            # Process failed to start — clear tracking state but don't update stats.
            logger.warning("_on_process_finished: process failed to start for '%s'", game.name)
            return

        # Update in-memory stats
        game.play_count += 1
        game.game_time += elapsed_seconds
        game.last_played = datetime.now().strftime("%Y%m%dT%H%M%S")

        logger.info(
            "_on_process_finished: '%s' play_count=%d game_time=%ds last_played=%s",
            game.name,
            game.play_count,
            game.game_time,
            game.last_played,
        )

        # Notify QML only if the user hasn't navigated to a different system
        # since the game was launched (i.e. the games model hasn't been replaced).
        if launch_model is self._games_model:
            self._games_model.notify_game_changed(index)
        else:
            logger.debug(
                "_on_process_finished: games model replaced since launch of '%s' — skipping notify",
                game.name,
            )

        # Persist to gamelist.xml
        system = self._systems_by_folder.get(game.system_folder)
        if system is not None:
            write_game_stats(system.path, game)
        else:
            logger.warning(
                "_on_process_finished: system '%s' not found — cannot write gamelist.xml",
                game.system_folder,
            )

    def _build_collection_systems(self, real_systems: list[System]) -> list[System]:
        """Build the three virtual collection System objects from *real_systems*.

        Returns a list of three System objects (Favorites, Last Played, All Games)
        that aggregate games across all real systems.  These are prepended to the
        full systems list so they appear at the top of the UI.
        """
        all_games = [g for s in real_systems for g in s.games]

        favorites_games = sorted(
            [g for g in all_games if g.favorite],
            key=lambda g: g.name.lower(),
        )
        last_played_games = sorted(
            [g for g in all_games if g.last_played],
            key=lambda g: g.last_played,
            reverse=True,
        )[:50]
        all_games_sorted = sorted(all_games, key=lambda g: g.name.lower())

        # Collections use a sentinel Path so System.path is always a Path object.
        _sentinel = Path(".")

        favorites = System(
            folder_name="_favorites",
            display_name="Favorites",
            path=_sentinel,
            games=favorites_games,
            game_count=len(favorites_games),
        )
        last_played = System(
            folder_name="_lastplayed",
            display_name="Last Played",
            path=_sentinel,
            games=last_played_games,
            game_count=len(last_played_games),
        )
        all_games_system = System(
            folder_name="_allgames",
            display_name="All Games",
            path=_sentinel,
            games=all_games_sorted,
            game_count=len(all_games_sorted),
        )

        return [favorites, last_played, all_games_system]

    def _rebuild_collections(self) -> None:
        """Regenerate the three collection System objects from current game data.

        Called in :meth:`selectSystem` whenever a collection folder (prefixed
        with ``_``) is selected, so the data is always fresh after a favorite
        toggle or a game play.
        """
        real_systems = [s for s in self._systems if not s.folder_name.startswith("_")]
        new_collections = self._build_collection_systems(real_systems)

        # Replace the collection entries at the front of self._systems in-place.
        # The real systems remain unchanged.
        collection_count = sum(1 for s in self._systems if s.folder_name.startswith("_"))
        self._systems = new_collections + self._systems[collection_count:]

        # Rebuild the folder lookup so selectSystem can find the updated objects.
        self._systems_by_folder = {s.folder_name: s for s in self._systems}

        # Rebuild the SystemListModel so QML picks up the updated collection game counts.
        self._systems_model = SystemListModel(self._systems, self)
        self.systemsModelChanged.emit()

        logger.debug("_rebuild_collections: rebuilt %d collection(s)", len(new_collections))

    def _scan(self) -> None:
        """Scan the ROM directory and build the systems list."""
        rom_dir = self._config.rom_directory
        if rom_dir is None:
            logger.info("GameLibrary: no ROM directory configured — library is empty")
            return

        rom_dir = Path(rom_dir)
        if not rom_dir.is_dir():
            logger.warning("GameLibrary: ROM directory does not exist: %s", rom_dir)
            return

        real_systems: list[System] = []
        for entry in sorted(rom_dir.iterdir()):
            if not entry.is_dir():
                continue

            gamelist_file = entry / "gamelist.xml"
            folder_name = entry.name
            sys_config = self._config.get_system(folder_name)

            if gamelist_file.exists():
                games = parse_gamelist(entry)
            elif sys_config.extensions:
                games = _scan_rom_files(entry, folder_name, sys_config.extensions)
            else:
                continue

            system = System(
                folder_name=folder_name,
                display_name=sys_config.display_name,
                path=entry,
                games=games,
                game_count=len(games),
            )
            real_systems.append(system)
            logger.debug(
                "Loaded system '%s' (%s) with %d games",
                folder_name,
                sys_config.display_name,
                len(games),
            )

        collections = self._build_collection_systems(real_systems)
        self._systems = collections + real_systems
        self._systems_by_folder = {s.folder_name: s for s in self._systems}

        # Replace the model in-place so any existing QML bindings update
        self._systems_model = SystemListModel(self._systems, self)
        self.systemsModelChanged.emit()

        logger.info(
            "GameLibrary: loaded %d real system(s) + %d collection(s) from %s",
            len(real_systems),
            len(collections),
            rom_dir,
        )
