"""Local video library backend for HTPC Station.

Scans user-configured video categories, exposes data to QML via
QAbstractListModel subclasses, and launches playback via LibMpvPlayer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.config import Config
from backend.mpv_launcher import LibMpvPlayer

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset({
    ".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv", ".webm",
    ".ts", ".m2ts", ".vob", ".ogv", ".mpg", ".mpeg", ".rm", ".rmvb",
    ".3gp", ".f4v", ".divx", ".mxf", ".asf",
})

_SEASON_RE = re.compile(
    r'(?:season|series|s)\s*[-_.]?\s*0*(\d+)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VideoFile:
    title: str          # filename stem (scraper will override later)
    path: str           # absolute path string
    poster_path: str = ""
    description: str = ""
    year: int = 0
    genre: str = ""
    rating: str = ""


@dataclass
class Episode:
    title: str          # filename stem
    path: str
    poster_path: str = ""
    description: str = ""


@dataclass
class Season:
    name: str           # "Season 1", "Unsorted", or raw folder name
    number: int         # parsed season number; -1 for unknown/unsorted
    episodes: list = field(default_factory=list)  # list[Episode]


@dataclass
class Show:
    name: str           # immediate subdirectory name
    path: str           # absolute path string
    poster_path: str = ""
    seasons: list = field(default_factory=list)   # list[Season]
    description: str = ""

    @property
    def season_count(self) -> int:
        return len(self.seasons)

    @property
    def episode_count(self) -> int:
        return sum(len(s.episodes) for s in self.seasons)


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------


def _scan_flat(paths: list[str]) -> list[VideoFile]:
    """Walk each path recursively, collect video files, sort by title."""
    results: list[VideoFile] = []
    for path_str in paths:
        p = Path(path_str)
        if not p.is_dir():
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                results.append(VideoFile(title=f.stem, path=str(f)))
    results.sort(key=lambda v: v.title.lower())
    return results


def _scan_tv_shows(paths: list[str]) -> list[Show]:
    """Scan each path for TV show directories."""
    shows: list[Show] = []
    for path_str in paths:
        root = Path(path_str)
        if not root.is_dir():
            continue
        for show_dir in sorted(root.iterdir()):
            if not show_dir.is_dir():
                continue
            show = _scan_single_show(show_dir)
            if show.episode_count > 0:
                shows.append(show)
    shows.sort(key=lambda s: s.name.lower())
    return shows


def _scan_single_show(show_dir: Path) -> Show:
    """Scan a single show directory and return a Show dataclass."""
    show = Show(name=show_dir.name, path=str(show_dir))

    # Collect direct video files → "Unsorted" season
    unsorted_episodes: list[Episode] = []
    named_seasons: list[Season] = []

    for child in show_dir.iterdir():
        if child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
            unsorted_episodes.append(Episode(title=child.stem, path=str(child)))
        elif child.is_dir():
            season = _scan_season_dir(child)
            if season is not None:
                named_seasons.append(season)

    # Sort seasons: numbered ascending, non-numeric named alphabetically, Unsorted last
    numbered = sorted(
        [s for s in named_seasons if s.number >= 0],
        key=lambda s: s.number,
    )
    non_numeric = sorted(
        [s for s in named_seasons if s.number < 0],
        key=lambda s: s.name.lower(),
    )

    seasons = numbered + non_numeric

    if unsorted_episodes:
        unsorted_episodes.sort(key=lambda e: e.title.lower())
        seasons.append(Season(name="Unsorted", number=-1, episodes=unsorted_episodes))

    show.seasons = seasons
    return show


def _scan_season_dir(season_dir: Path) -> Optional[Season]:
    """Scan a season directory. Returns None if no episodes found."""
    episodes: list[Episode] = []
    for f in sorted(season_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            episodes.append(Episode(title=f.stem, path=str(f)))

    if not episodes:
        return None

    episodes.sort(key=lambda e: e.title.lower())

    m = _SEASON_RE.search(season_dir.name)
    if m:
        num = int(m.group(1))
        return Season(name=f"Season {num}", number=num, episodes=episodes)
    else:
        return Season(name=season_dir.name, number=-1, episodes=episodes)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CategoryListModel(QAbstractListModel):
    """Exposes local_video_categories to QML.

    Roles: name, type, paths
    """

    NameRole = Qt.ItemDataRole.UserRole + 1
    TypeRole = Qt.ItemDataRole.UserRole + 2
    PathsRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._display_items: list[dict] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._display_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._display_items)):
            return None
        item = self._display_items[index.row()]
        if role == self.NameRole:
            return item.get("name", "")
        if role == self.TypeRole:
            return item.get("type", "flat")
        if role == self.PathsRole:
            return item.get("paths", [])
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("name", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.TypeRole: b"type",
            self.PathsRole: b"paths",
        }


class VideoListModel(QAbstractListModel):
    """Exposes flat video files to QML.

    Roles: title, path, posterPath
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    PosterPathRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[VideoFile] = []
        self._display_items: list[VideoFile] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._display_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._display_items)):
            return None
        item = self._display_items[index.row()]
        if role == self.TitleRole:
            return item.title
        if role == self.PathRole:
            return item.path
        if role == self.PosterPathRole:
            return item.poster_path
        if role == Qt.ItemDataRole.DisplayRole:
            return item.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.PathRole: b"path",
            self.PosterPathRole: b"posterPath",
        }


class ShowListModel(QAbstractListModel):
    """Exposes TV shows to QML.

    Roles: name, path, posterPath, seasonCount, episodeCount
    """

    NameRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    PosterPathRole = Qt.ItemDataRole.UserRole + 3
    SeasonCountRole = Qt.ItemDataRole.UserRole + 4
    EpisodeCountRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[Show] = []
        self._display_items: list[Show] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._display_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._display_items)):
            return None
        item = self._display_items[index.row()]
        if role == self.NameRole:
            return item.name
        if role == self.PathRole:
            return item.path
        if role == self.PosterPathRole:
            return item.poster_path
        if role == self.SeasonCountRole:
            return item.season_count
        if role == self.EpisodeCountRole:
            return item.episode_count
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.PathRole: b"path",
            self.PosterPathRole: b"posterPath",
            self.SeasonCountRole: b"seasonCount",
            self.EpisodeCountRole: b"episodeCount",
        }


class SeasonListModel(QAbstractListModel):
    """Exposes seasons of a TV show to QML.

    Roles: name, number, episodeCount
    """

    NameRole = Qt.ItemDataRole.UserRole + 1
    NumberRole = Qt.ItemDataRole.UserRole + 2
    EpisodeCountRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[Season] = []
        self._display_items: list[Season] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._display_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._display_items)):
            return None
        item = self._display_items[index.row()]
        if role == self.NameRole:
            return item.name
        if role == self.NumberRole:
            return item.number
        if role == self.EpisodeCountRole:
            return len(item.episodes)
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.NumberRole: b"number",
            self.EpisodeCountRole: b"episodeCount",
        }


class EpisodeListModel(QAbstractListModel):
    """Exposes episodes of a season to QML.

    Roles: title, path, posterPath
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    PosterPathRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[Episode] = []
        self._display_items: list[Episode] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._display_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._display_items)):
            return None
        item = self._display_items[index.row()]
        if role == self.TitleRole:
            return item.title
        if role == self.PathRole:
            return item.path
        if role == self.PosterPathRole:
            return item.poster_path
        if role == Qt.ItemDataRole.DisplayRole:
            return item.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.PathRole: b"path",
            self.PosterPathRole: b"posterPath",
        }


# ---------------------------------------------------------------------------
# LocalVideoLibrary — main orchestrator
# ---------------------------------------------------------------------------


class LocalVideoLibrary(QObject):
    """Manages local video data and exposes it to QML.

    Scans configured video categories (flat or TV show hierarchy) and provides
    models and slots for QML navigation and playback.
    """

    # Public signals
    categoriesModelChanged = Signal()
    videosModelChanged = Signal()
    showsModelChanged = Signal()
    seasonsModelChanged = Signal()
    episodesModelChanged = Signal()
    currentCategoryIndexChanged = Signal()
    playbackStarted = Signal()
    playbackFinished = Signal()

    def __init__(self, config: Config, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._config = config

        # Build categories model from config
        self._categories = CategoryListModel(self)
        cats = config.local_video_categories
        self._categories._items = list(cats)
        self._categories._display_items = list(cats)

        # MPV player
        self._mpv = LibMpvPlayer(parent=self)
        self._mpv.processStarted.connect(
            self.playbackStarted, Qt.ConnectionType.QueuedConnection
        )
        self._mpv.processFinished.connect(
            lambda _code: self.playbackFinished.emit(),
            Qt.ConnectionType.QueuedConnection,
        )
        self._mpv.processFinished.connect(
            self._clear_launching,
            Qt.ConnectionType.QueuedConnection,
        )

        self._is_launching = False

        # Empty models
        self._videos = VideoListModel(self)
        self._shows = ShowListModel(self)
        self._seasons = SeasonListModel(self)
        self._episodes = EpisodeListModel(self)

        self._current_category_index = -1

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _reset_model(model: QAbstractListModel, items: list) -> None:
        """Assign new items atomically inside a beginResetModel/endResetModel pair."""
        model.beginResetModel()
        model._items = items
        model._display_items = list(items)
        model.endResetModel()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def _get_categories_model(self) -> CategoryListModel:
        return self._categories

    def _get_videos_model(self) -> VideoListModel:
        return self._videos

    def _get_shows_model(self) -> ShowListModel:
        return self._shows

    def _get_seasons_model(self) -> SeasonListModel:
        return self._seasons

    def _get_episodes_model(self) -> EpisodeListModel:
        return self._episodes

    def _get_current_category_index(self) -> int:
        return self._current_category_index

    categoriesModel = Property(
        QObject,
        fget=_get_categories_model,
        notify=categoriesModelChanged,
    )
    videosModel = Property(
        QObject,
        fget=_get_videos_model,
        notify=videosModelChanged,
    )
    showsModel = Property(
        QObject,
        fget=_get_shows_model,
        notify=showsModelChanged,
    )
    seasonsModel = Property(
        QObject,
        fget=_get_seasons_model,
        notify=seasonsModelChanged,
    )
    episodesModel = Property(
        QObject,
        fget=_get_episodes_model,
        notify=episodesModelChanged,
    )
    currentCategoryIndex = Property(
        int,
        fget=_get_current_category_index,
        notify=currentCategoryIndexChanged,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(int)
    def selectCategory(self, index: int) -> None:
        """Select a category by index, scan it, and populate the appropriate model."""
        cats = self._config.local_video_categories
        if index < 0 or index >= len(cats):
            return
        self._current_category_index = index
        cat = cats[index]
        if cat["type"] == "flat":
            items = _scan_flat(cat["paths"])
            self._reset_model(self._videos, items)
            # Reset TV show models
            self._reset_model(self._shows, [])
            self._reset_model(self._seasons, [])
            self._reset_model(self._episodes, [])
            self.videosModelChanged.emit()
        else:
            shows = _scan_tv_shows(cat["paths"])
            self._reset_model(self._shows, shows)
            # Reset flat/season/episode models
            self._reset_model(self._videos, [])
            self._reset_model(self._seasons, [])
            self._reset_model(self._episodes, [])
            self.showsModelChanged.emit()
        self.currentCategoryIndexChanged.emit()

    @Slot(int)
    def selectShow(self, index: int) -> None:
        """Select a show by index and populate the seasons model."""
        shows = self._shows._display_items
        if index < 0 or index >= len(shows):
            return
        seasons = shows[index].seasons
        self._reset_model(self._seasons, seasons)
        self._reset_model(self._episodes, [])
        self.seasonsModelChanged.emit()
        self.episodesModelChanged.emit()

    @Slot(int)
    def selectSeason(self, index: int) -> None:
        """Select a season by index and populate the episodes model."""
        seasons = self._seasons._display_items
        if index < 0 or index >= len(seasons):
            return
        episodes = seasons[index].episodes
        self._reset_model(self._episodes, episodes)
        self.episodesModelChanged.emit()

    @Slot(str, int)
    def playVideo(self, path: str, start_ms: int = 0) -> None:
        """Launch playback of the given file path."""
        if self._is_launching:
            return
        self._is_launching = True
        self._mpv.launch(path, Path(path).stem, start_ms)

    @Slot()
    def _clear_launching(self) -> None:
        self._is_launching = False

    @Slot()
    def stopPlayback(self) -> None:
        """Stop current playback."""
        self._mpv.kill()

    @Slot(str, result=int)
    def getResumePosition(self, path: str) -> int:
        """Return resume position in ms. Stub — always returns 0."""
        return 0

    @Slot(int)
    def rescanCategory(self, index: int) -> None:
        """Re-run the scan for the given category index."""
        self.selectCategory(index)

    # ------------------------------------------------------------------
    # set_wid pass-through
    # ------------------------------------------------------------------

    def set_wid(self, wid: int) -> None:
        """Pass the Qt native window handle to the MPV player.

        Must be called after the Qt window is shown (same as plex_library).
        """
        self._mpv.set_wid(wid)
