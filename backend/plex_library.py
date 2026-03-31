"""Plex library manager for HTPC Station.

Exposes Plex Media Server data to QML via models and slots.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.browser_launcher import BrowserLauncher
from backend.config import Config, CONFIG_DIR
from backend.plex_account import PlexAccount
from backend.plex_client import PlexClient
from backend.plex_models import (
    PlexArtist,
    PlexMovie,
    PlexShow,
    parse_album,
    parse_artist,
    parse_episode,
    parse_movie,
    parse_season,
    parse_show,
    parse_track,
)
from backend.poster_cache import PosterCache

logger = logging.getLogger(__name__)

_POSTER_CACHE_DIR = CONFIG_DIR / "poster_cache"
_PAGE_SIZE = 50

# Maps Plex restriction profile names to comma-separated allowed content ratings.
# Used to filter library items server-side for managed/restricted users.
_RESTRICTION_RATINGS: dict[str, str] = {
    "little_kid": "G,TV-Y,TV-Y7,TV-G,NR",
    "older_kid": "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR",
    "teen": "G,PG,PG-13,TV-Y,TV-Y7,TV-G,TV-PG,TV-14,NR",
}


# ---------------------------------------------------------------------------
# PlexLibraryListModel
# ---------------------------------------------------------------------------


class PlexLibraryListModel(QAbstractListModel):
    """Model for the list of Plex libraries (Movies, TV Shows).

    Roles: title, type, sectionKey
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    TypeRole = Qt.ItemDataRole.UserRole + 2
    SectionKeyRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []

    def set_items(self, items: list[dict]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.TitleRole:
            return item.get("title", "")
        if role == self.TypeRole:
            return item.get("type", "")
        if role == self.SectionKeyRole:
            return str(item.get("key", ""))
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("title", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.TypeRole: b"type",
            self.SectionKeyRole: b"sectionKey",
        }


# ---------------------------------------------------------------------------
# PlexMovieListModel
# ---------------------------------------------------------------------------


class PlexMovieListModel(QAbstractListModel):
    """Model for a paginated list of Plex movies.

    Roles: ratingKey, title, year, posterLocal, audienceRating, duration, summary
    """

    RatingKeyRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    YearRole = Qt.ItemDataRole.UserRole + 3
    PosterLocalRole = Qt.ItemDataRole.UserRole + 4
    AudienceRatingRole = Qt.ItemDataRole.UserRole + 5
    DurationRole = Qt.ItemDataRole.UserRole + 6
    SummaryRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._movies: list[PlexMovie] = []

    def set_movies(self, movies: list[PlexMovie]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._movies = movies
        self.endResetModel()

    def append_movies(self, movies: list[PlexMovie]) -> None:
        """Append movies to the model. Must be called on the main thread."""
        if not movies:
            return
        first = len(self._movies)
        last = first + len(movies) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._movies.extend(movies)
        self.endInsertRows()

    def notify_poster_changed(self, row: int) -> None:
        """Emit dataChanged for the poster role at *row*."""
        if 0 <= row < len(self._movies):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.PosterLocalRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._movies)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._movies)):
            return None
        movie = self._movies[index.row()]
        if role == self.RatingKeyRole:
            return movie.rating_key
        if role == self.TitleRole:
            return movie.title
        if role == self.YearRole:
            return movie.year
        if role == self.PosterLocalRole:
            return movie.poster_local
        if role == self.AudienceRatingRole:
            return movie.audience_rating
        if role == self.DurationRole:
            return movie.duration_ms
        if role == self.SummaryRole:
            return movie.summary
        if role == Qt.ItemDataRole.DisplayRole:
            return movie.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.RatingKeyRole: b"ratingKey",
            self.TitleRole: b"title",
            self.YearRole: b"year",
            self.PosterLocalRole: b"posterLocal",
            self.AudienceRatingRole: b"audienceRating",
            self.DurationRole: b"duration",
            self.SummaryRole: b"summary",
        }

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the title of the movie at *index*, or "" if out of range."""
        if 0 <= index < len(self._movies):
            return self._movies[index].title
        return ""


# ---------------------------------------------------------------------------
# PlexShowListModel
# ---------------------------------------------------------------------------


class PlexShowListModel(QAbstractListModel):
    """Model for a list of Plex TV shows.

    Roles: ratingKey, title, year, posterLocal, audienceRating,
           childCount, leafCount, viewedLeafCount
    """

    RatingKeyRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    YearRole = Qt.ItemDataRole.UserRole + 3
    PosterLocalRole = Qt.ItemDataRole.UserRole + 4
    AudienceRatingRole = Qt.ItemDataRole.UserRole + 5
    ChildCountRole = Qt.ItemDataRole.UserRole + 6
    LeafCountRole = Qt.ItemDataRole.UserRole + 7
    ViewedLeafCountRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._shows: list[PlexShow] = []

    def set_shows(self, shows: list[PlexShow]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._shows = shows
        self.endResetModel()

    def append_shows(self, shows: list[PlexShow]) -> None:
        """Append shows to the model. Must be called on the main thread."""
        if not shows:
            return
        first = len(self._shows)
        last = first + len(shows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._shows.extend(shows)
        self.endInsertRows()

    def notify_poster_changed(self, row: int) -> None:
        """Emit dataChanged for the poster role at *row*."""
        if 0 <= row < len(self._shows):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.PosterLocalRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._shows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._shows)):
            return None
        show = self._shows[index.row()]
        if role == self.RatingKeyRole:
            return show.rating_key
        if role == self.TitleRole:
            return show.title
        if role == self.YearRole:
            return show.year
        if role == self.PosterLocalRole:
            return show.poster_local
        if role == self.AudienceRatingRole:
            return show.audience_rating
        if role == self.ChildCountRole:
            return show.child_count
        if role == self.LeafCountRole:
            return show.leaf_count
        if role == self.ViewedLeafCountRole:
            return show.viewed_leaf_count
        if role == Qt.ItemDataRole.DisplayRole:
            return show.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.RatingKeyRole: b"ratingKey",
            self.TitleRole: b"title",
            self.YearRole: b"year",
            self.PosterLocalRole: b"posterLocal",
            self.AudienceRatingRole: b"audienceRating",
            self.ChildCountRole: b"childCount",
            self.LeafCountRole: b"leafCount",
            self.ViewedLeafCountRole: b"viewedLeafCount",
        }

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the title of the show at *index*, or "" if out of range."""
        if 0 <= index < len(self._shows):
            return self._shows[index].title
        return ""


# ---------------------------------------------------------------------------
# PlexOnDeckModel
# ---------------------------------------------------------------------------


class PlexOnDeckModel(QAbstractListModel):
    """Model for the on-deck (continue watching) list.

    Roles: ratingKey, title, type, posterLocal, grandparentTitle,
           viewOffset, duration
    """

    RatingKeyRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    TypeRole = Qt.ItemDataRole.UserRole + 3
    PosterLocalRole = Qt.ItemDataRole.UserRole + 4
    GrandparentTitleRole = Qt.ItemDataRole.UserRole + 5
    ViewOffsetRole = Qt.ItemDataRole.UserRole + 6
    DurationRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []

    def set_items(self, items: list[dict]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def notify_poster_changed(self, row: int) -> None:
        """Emit dataChanged for the poster role at *row*."""
        if 0 <= row < len(self._items):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.PosterLocalRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.RatingKeyRole:
            return item.get("rating_key", "")
        if role == self.TitleRole:
            return item.get("title", "")
        if role == self.TypeRole:
            return item.get("type", "")
        if role == self.PosterLocalRole:
            return item.get("poster_local", "")
        if role == self.GrandparentTitleRole:
            return item.get("grandparent_title", "")
        if role == self.ViewOffsetRole:
            return item.get("view_offset", 0)
        if role == self.DurationRole:
            return item.get("duration", 0)
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("title", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.RatingKeyRole: b"ratingKey",
            self.TitleRole: b"title",
            self.TypeRole: b"type",
            self.PosterLocalRole: b"posterLocal",
            self.GrandparentTitleRole: b"grandparentTitle",
            self.ViewOffsetRole: b"viewOffset",
            self.DurationRole: b"duration",
        }

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the title of the on-deck item at *index*, or "" if out of range."""
        if 0 <= index < len(self._items):
            return self._items[index].get("title", "")
        return ""


# ---------------------------------------------------------------------------
# PlexArtistListModel
# ---------------------------------------------------------------------------


class PlexArtistListModel(QAbstractListModel):
    """Model for a list of Plex music artists.

    Roles: ratingKey, title, genre, imageLocal
    """

    RatingKeyRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    GenreRole = Qt.ItemDataRole.UserRole + 3
    ImageLocalRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._artists: list[PlexArtist] = []

    def set_artists(self, artists: list[PlexArtist]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._artists = artists
        self.endResetModel()

    def notify_poster_changed(self, row: int) -> None:
        """Emit dataChanged for the image role at *row*."""
        if 0 <= row < len(self._artists):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.ImageLocalRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._artists)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._artists)):
            return None
        artist = self._artists[index.row()]
        if role == self.RatingKeyRole:
            return artist.rating_key
        if role == self.TitleRole:
            return artist.title
        if role == self.GenreRole:
            return artist.genre
        if role == self.ImageLocalRole:
            return artist.poster_local
        if role == Qt.ItemDataRole.DisplayRole:
            return artist.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.RatingKeyRole: b"ratingKey",
            self.TitleRole: b"title",
            self.GenreRole: b"genre",
            self.ImageLocalRole: b"imageLocal",
        }

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the title of the artist at *index*, or "" if out of range."""
        if 0 <= index < len(self._artists):
            return self._artists[index].title
        return ""


# ---------------------------------------------------------------------------
# PlexLibrary — main orchestrator
# ---------------------------------------------------------------------------


class PlexLibrary(QObject):
    """Manages Plex data and exposes it to QML.

    Exposed to QML as the ``plex`` context property.

    All network calls are dispatched to a ThreadPoolExecutor.
    Results are delivered back to the main thread via Qt signals.
    """

    availableChanged = Signal()
    librariesModelChanged = Signal()
    moviesModelChanged = Signal()
    showsModelChanged = Signal()
    onDeckModelChanged = Signal()
    artistsModelChanged = Signal()
    currentLibraryChanged = Signal(str)

    # Internal signals used to marshal results from worker threads to main thread
    _librariesReady = Signal(list)
    _moviesReady = Signal(list, int)   # (movies, total_size)
    _showsReady = Signal(list, int)    # (shows, total_size)
    _onDeckReady = Signal(list)
    _availabilityReady = Signal(bool)
    _posterReady = Signal(str, int, str)  # (model_type, row, file_url)
    _machineIdentifierReady = Signal(str)
    _artistsReady = Signal(list, int)  # (artists, total_size)

    def __init__(
        self,
        config: Config,
        browser_launcher: Optional[BrowserLauncher] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._config = config
        self._browser_launcher = browser_launcher
        self._available = False
        self._current_library = ""
        self._current_section_key = ""
        self._current_section_type = ""
        self._movies_total = 0
        self._movies_loaded = 0
        self._loading_more = False
        self._shows_total: int = 0
        self._shows_loaded: int = 0
        self._shows_loading_more: bool = False
        self._machine_identifier: str = ""
        self._current_sort: str = ""   # Plex API sort param for movies, e.g. 'titleSort:asc'
        self._current_genre: str = ""  # genre key for movies (integer as string)
        self._shows_sort: str = ""     # Plex API sort param for shows
        self._shows_genre: str = ""    # genre key for shows (integer as string)
        self._content_rating_filter: str = ""  # comma-separated allowed ratings for restricted users
        self._cached_content_rating_filter: str = ""  # cached alongside user token

        # Build models
        self._libraries_model = PlexLibraryListModel(self)
        self._movies_model = PlexMovieListModel(self)
        self._shows_model = PlexShowListModel(self)
        self._on_deck_model = PlexOnDeckModel(self)
        self._artists_model = PlexArtistListModel(self)

        # Thread pool for network calls
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Poster cache
        self._poster_cache = PosterCache(_POSTER_CACHE_DIR)

        # PlexAccount for server discovery and user switching
        self._account: Optional[PlexAccount] = None
        # Resolved server URL (set by _setup_client after discovery)
        self._server_url: str = ""
        # Active token (user-specific or admin) used for deep-link URLs
        self._active_token: str = ""
        # Cache for user-switching to avoid redundant API calls on every refresh
        self._cached_user_id: Optional[int] = None
        self._cached_user_token: str = ""
        self._cached_user_title: str = ""

        # Build Plex client if config is available
        self._client: Optional[PlexClient] = None
        self._setup_client()

        # Connect internal signals (worker -> main thread)
        self._librariesReady.connect(self._on_libraries_ready)
        self._moviesReady.connect(self._on_movies_ready)
        self._showsReady.connect(self._on_shows_ready)
        self._onDeckReady.connect(self._on_on_deck_ready)
        self._availabilityReady.connect(self._on_availability_ready)
        self._posterReady.connect(self._on_poster_ready)
        self._machineIdentifierReady.connect(self._on_machine_identifier_ready)
        self._artistsReady.connect(self._on_artists_ready)

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    @property
    def _available_prop(self) -> bool:
        return self._available

    @property
    def _libraries_model_prop(self) -> PlexLibraryListModel:
        return self._libraries_model

    @property
    def _movies_model_prop(self) -> PlexMovieListModel:
        return self._movies_model

    @property
    def _shows_model_prop(self) -> PlexShowListModel:
        return self._shows_model

    @property
    def _on_deck_model_prop(self) -> PlexOnDeckModel:
        return self._on_deck_model

    @property
    def _current_library_prop(self) -> str:
        return self._current_library

    available = Property(
        bool,
        fget=lambda self: self._available,
        notify=availableChanged,
    )
    librariesModel = Property(
        QObject,
        fget=lambda self: self._libraries_model,
        notify=librariesModelChanged,
    )
    moviesModel = Property(
        QObject,
        fget=lambda self: self._movies_model,
        notify=moviesModelChanged,
    )
    showsModel = Property(
        QObject,
        fget=lambda self: self._shows_model,
        notify=showsModelChanged,
    )
    onDeckModel = Property(
        QObject,
        fget=lambda self: self._on_deck_model,
        notify=onDeckModelChanged,
    )
    artistsModel = Property(
        QObject,
        fget=lambda self: self._artists_model,
        notify=artistsModelChanged,
    )
    currentLibrary = Property(
        str,
        fget=lambda self: self._current_library,
        notify=currentLibraryChanged,
    )
    serverUrl = Property(
        str,
        fget=lambda self: self._server_url,
        constant=True,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def getLibraryList(self) -> list:
        """Return library list as a list of dicts for QML consumption.

        Includes a "Continue Watching" entry when on-deck items are present,
        followed by one entry per Plex library (movie/show).
        """
        result = []
        on_deck_count = len(self._on_deck_model._items)
        if on_deck_count:
            result.append({
                "title": "Continue Watching",
                "type": "ondeck",
                "sectionKey": "_ondeck",
                "count": on_deck_count,
            })
        for lib in self._libraries_model._items:
            result.append({
                "title": lib.get("title", ""),
                "type": lib.get("type", ""),
                "sectionKey": str(lib.get("key", "")),
                "count": 0,
            })
        result.append({
            "title": "Live TV",
            "type": "livetv",
            "sectionKey": "_livetv",
            "count": 0,
        })
        return result

    @Slot(result="QVariant")
    def getMusicLibraries(self) -> list:
        """Return music (artist-type) libraries as [{id, label}] for the settings dropdown."""
        result = []
        for lib in self._libraries_model._items:
            if lib.get("type") == "artist":
                result.append({
                    "id": str(lib.get("key", "")),
                    "label": lib.get("title", ""),
                })
        return result

    @Slot()
    def refresh(self) -> None:
        """Re-fetch library list and on-deck, check server availability."""
        # Re-create client from config in case settings changed
        self._setup_client()
        if self._client is None:
            logger.info("PlexLibrary.refresh: no Plex client configured")
            self._on_availability_ready(False)
            return
        client = self._client
        self._executor.submit(self._worker_refresh, client)

    @Slot(str)
    def selectLibrary(self, section_key: str) -> None:
        """Load items for a library section identified by *section_key*."""
        if self._client is None:
            return

        # On-deck data is already loaded in onDeckModel from refresh().
        # There is no /library/sections/_ondeck/all endpoint — return early.
        if section_key == "_ondeck":
            self._current_section_key = section_key
            self._current_section_type = "ondeck"
            self._current_library = "Continue Watching"
            self.currentLibraryChanged.emit("Continue Watching")
            return

        # Find the library type from the libraries model
        section_type = ""
        section_title = ""
        for item in self._libraries_model._items:
            if str(item.get("key", "")) == section_key:
                section_type = item.get("type", "")
                section_title = item.get("title", "")
                break

        self._current_section_key = section_key
        self._current_section_type = section_type
        self._movies_total = 0
        self._movies_loaded = 0
        self._shows_total = 0
        self._shows_loaded = 0
        self._current_library = section_title
        self.currentLibraryChanged.emit(section_title)

        client = self._client
        self._executor.submit(self._worker_load_section, client, section_key, section_type)

    @Slot()
    def loadMoreMovies(self) -> None:
        """Load the next page of movies (pagination)."""
        if self._client is None:
            return
        if self._loading_more:
            return
        if self._movies_loaded >= self._movies_total and self._movies_total > 0:
            return
        self._loading_more = True
        client = self._client
        section_key = self._current_section_key
        start = self._movies_loaded
        sort = self._current_sort
        genre = self._current_genre
        self._executor.submit(
            self._worker_load_more_movies, client, section_key, start, sort, genre
        )

    # Sort key → Plex API sort param
    _SORT_MAP: dict[str, str] = {
        "az":        "titleSort:asc",
        "za":        "titleSort:desc",
        "recent":    "addedAt:desc",
        "year_desc": "year:desc",
        "year_asc":  "year:asc",
        "rating":    "audienceRating:desc",
    }

    @Slot(str)
    def sortMovies(self, sort_key: str) -> None:
        """Re-fetch movies with the given sort.

        sort_key: 'az', 'za', 'recent', 'year_desc', 'year_asc', 'rating'
        """
        if self._client is None or not self._current_section_key:
            return
        api_sort = self._SORT_MAP.get(sort_key, "")
        self._current_sort = api_sort
        self._movies_total = 0
        self._movies_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        genre = self._current_genre
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            api_sort, genre
        )

    @Slot(str)
    def filterByGenre(self, genre_key: str) -> None:
        """Re-fetch movies filtered by genre. Empty string clears the filter."""
        if self._client is None or not self._current_section_key:
            return
        self._current_genre = genre_key
        self._movies_total = 0
        self._movies_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        sort = self._current_sort
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            sort, genre_key
        )

    @Slot()
    def loadMoreShows(self) -> None:
        """Load the next page of shows (pagination)."""
        if self._client is None:
            return
        if self._shows_loading_more:
            return
        if self._shows_loaded >= self._shows_total and self._shows_total > 0:
            return
        self._shows_loading_more = True
        client = self._client
        section_key = self._current_section_key
        start = self._shows_loaded
        sort = self._shows_sort
        genre = self._shows_genre
        self._executor.submit(
            self._worker_load_more_shows, client, section_key, start, sort, genre
        )

    @Slot(str)
    def sortShows(self, sort_key: str) -> None:
        """Re-fetch shows with the given sort.

        sort_key: 'az', 'za', 'recent', 'year_desc', 'year_asc', 'rating'
        """
        if self._client is None or not self._current_section_key:
            return
        api_sort = self._SORT_MAP.get(sort_key, "")
        self._shows_sort = api_sort
        self._shows_total = 0
        self._shows_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        genre = self._shows_genre
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            api_sort, genre
        )

    @Slot(str)
    def sortArtists(self, sort_key: str) -> None:
        """Re-fetch artists with the given sort.

        sort_key: 'az', 'za', 'recent', 'year_desc', 'year_asc', 'rating'
        """
        if self._client is None or not self._current_section_key:
            return
        api_sort = self._SORT_MAP.get(sort_key, "")
        client = self._client
        section_key = self._current_section_key
        self._executor.submit(
            self._worker_load_section, client, section_key, "artist", api_sort
        )

    @Slot(str)
    def filterShowsByGenre(self, genre_key: str) -> None:
        """Re-fetch shows filtered by genre. Empty string clears the filter."""
        if self._client is None or not self._current_section_key:
            return
        self._shows_genre = genre_key
        self._shows_total = 0
        self._shows_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        sort = self._shows_sort
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            sort, genre_key
        )

    @Slot(result="QVariant")
    def getMovieGenres(self) -> list:
        """Return genres for the current movie library as [{key, title}, ...]."""
        if self._client is None or not self._current_section_key:
            return []
        return self._client.get_genres(self._current_section_key)

    @Slot(result="QVariant")
    def getShowGenres(self) -> list:
        """Return genres for the current show library as [{key, title}, ...]."""
        if self._client is None or not self._current_section_key:
            return []
        return self._client.get_genres(self._current_section_key)

    @Slot(int, result=str)
    def getMovieRatingKeyAt(self, index: int) -> str:
        """Return the ratingKey of the movie at the given index, or empty string."""
        if 0 <= index < len(self._movies_model._movies):
            return self._movies_model._movies[index].rating_key
        return ""

    @Slot(result=int)
    def moviesCount(self) -> int:
        """Return the number of movies currently loaded in the model."""
        return len(self._movies_model._movies)

    @Slot(str, result="QVariant")
    def getMovie(self, rating_key: str) -> dict:
        """Return full movie details as a dict (synchronous, blocks briefly)."""
        if self._client is None:
            return {}
        data = self._client.get_metadata(rating_key)
        if not data:
            return {}
        movie = parse_movie(data)
        if movie.thumb_path and self._poster_cache:
            movie.poster_local = self._poster_cache.get_poster(
                self._client, movie.thumb_path
            )
        return {
            "ratingKey": movie.rating_key,
            "title": movie.title,
            "year": movie.year,
            "summary": movie.summary,
            "contentRating": movie.content_rating,
            "audienceRating": movie.audience_rating,
            "duration": movie.duration_ms,
            "studio": movie.studio,
            "tagline": movie.tagline,
            "genres": movie.genres,
            "directors": movie.directors,
            "cast": movie.cast,
            "posterLocal": movie.poster_local,
        }

    @Slot(str, result="QVariant")
    def getShow(self, rating_key: str) -> dict:
        """Return full show details as a dict (synchronous, blocks briefly)."""
        if self._client is None:
            return {}
        data = self._client.get_metadata(rating_key)
        if not data:
            return {}
        show = parse_show(data)
        if show.thumb_path and self._poster_cache:
            show.poster_local = self._poster_cache.get_poster(
                self._client, show.thumb_path
            )
        return {
            "ratingKey": show.rating_key,
            "title": show.title,
            "year": show.year,
            "summary": show.summary,
            "contentRating": show.content_rating,
            "audienceRating": show.audience_rating,
            "childCount": show.child_count,
            "leafCount": show.leaf_count,
            "viewedLeafCount": show.viewed_leaf_count,
            "genres": show.genres,
            "cast": show.cast,
            "posterLocal": show.poster_local,
        }

    @Slot(str, result="QVariant")
    def getSeasons(self, rating_key: str) -> list:
        """Return seasons list as a list of dicts (synchronous, blocks briefly)."""
        if self._client is None:
            return []
        children = self._client.get_children(rating_key)
        seasons = []
        for item in children:
            if item.get("type") == "season":
                season = parse_season(item)
                seasons.append({
                    "ratingKey": season.rating_key,
                    "title": season.title,
                    "index": season.index,
                    "leafCount": season.leaf_count,
                    "viewedLeafCount": season.viewed_leaf_count,
                    "parentRatingKey": season.parent_rating_key,
                })
        return seasons

    @Slot(str, result="QVariant")
    def getEpisodes(self, season_rating_key: str) -> list:
        """Return episodes list as a list of dicts (synchronous, blocks briefly)."""
        if self._client is None:
            return []
        children = self._client.get_children(season_rating_key)
        episodes = []
        for item in children:
            if item.get("type") == "episode":
                episode = parse_episode(item)
                episodes.append({
                    "ratingKey": episode.rating_key,
                    "title": episode.title,
                    "index": episode.index,
                    "parentIndex": episode.parent_index,
                    "summary": episode.summary,
                    "duration": episode.duration_ms,
                    "viewOffset": episode.view_offset,
                    "viewed": episode.viewed,
                    "grandparentTitle": episode.grandparent_title,
                    "posterLocal": episode.poster_local,
                })
        return episodes

    @Slot(str, result="QVariant")
    def getArtist(self, rating_key: str) -> dict:
        """Return full artist details as a dict (synchronous, blocks briefly)."""
        if self._client is None:
            return {}
        data = self._client.get_metadata(rating_key)
        if not data:
            return {}
        artist = parse_artist(data)
        if artist.thumb_path and self._poster_cache:
            artist.poster_local = self._poster_cache.get_poster(
                self._client, artist.thumb_path
            )
        return {
            "ratingKey": artist.rating_key,
            "title": artist.title,
            "summary": artist.summary,
            "genre": artist.genre,
            "posterLocal": artist.poster_local,
        }

    @Slot(str, result="QVariant")
    def getAlbum(self, rating_key: str) -> dict:
        """Return album metadata as a dict (synchronous, blocks briefly)."""
        if self._client is None:
            return {}
        data = self._client.get_metadata(rating_key)
        if not data:
            return {}
        album = parse_album(data)
        if album.thumb_path and self._poster_cache:
            album.poster_local = self._poster_cache.get_poster(
                self._client, album.thumb_path
            )
        return {
            "ratingKey": album.rating_key,
            "title": album.title,
            "year": album.year,
            "leafCount": album.leaf_count,
            "parentTitle": album.parent_title,
            "posterLocal": album.poster_local,
            "summary": album.summary,
            "studio": album.studio,
            "genre": album.genre,
            "rating": album.rating,
        }

    @Slot(str, result="QVariant")
    def getArtistAlbums(self, artist_rating_key: str) -> list:
        """Return all album categories for an artist as a grouped list.

        Returns a list of dicts, each representing either a section header
        or an album entry:

        Headers:  {"type": "header", "title": "Albums"}
        Albums:   {"type": "album", "ratingKey": ..., "title": ..., "year": ...,
                   "leafCount": ..., "posterLocal": ...}

        Albums within each category are sorted by year descending (newest first).
        """
        import re

        if self._client is None:
            return []
        hubs = self._client.get_hubs(artist_rating_key)
        result = []
        for hub in hubs:
            hub_id = hub.get("hubIdentifier", "")
            if not (hub_id.startswith("artist.albums") or hub_id.startswith("hub.artist.albums")):
                continue
            # Clean up the hub title: strip leading count prefix
            raw_title = hub.get("title", "")
            clean_title = re.sub(r'^\d+\s+', '', raw_title)
            # Normalize "Album" -> "Albums" for consistency
            if clean_title == "Album":
                clean_title = "Albums"
            # Parse and sort albums within this category
            albums = []
            for item in hub.get("Metadata", []):
                album = parse_album(item)
                if album.thumb_path and self._poster_cache:
                    album.poster_local = self._poster_cache.get_poster(
                        self._client, album.thumb_path
                    )
                albums.append({
                    "type": "album",
                    "ratingKey": album.rating_key,
                    "title": album.title,
                    "year": album.year,
                    "leafCount": album.leaf_count,
                    "posterLocal": album.poster_local,
                })
            # Sort albums by year descending (newest first)
            albums.sort(key=lambda a: a["year"] or 0, reverse=True)
            # Emit header then albums
            result.append({"type": "header", "title": clean_title})
            result.extend(albums)
        return result

    @Slot(str, result="QVariant")
    def getAlbums(self, artist_rating_key: str) -> list:
        """Return albums list as a list of dicts (synchronous, blocks briefly)."""
        if self._client is None:
            return []
        children = self._client.get_children(artist_rating_key)
        albums = []
        for item in children:
            if item.get("type") == "album":
                album = parse_album(item)
                if album.thumb_path and self._poster_cache:
                    album.poster_local = self._poster_cache.get_poster(
                        self._client, album.thumb_path
                    )
                albums.append({
                    "ratingKey": album.rating_key,
                    "title": album.title,
                    "year": album.year,
                    "leafCount": album.leaf_count,
                    "parentRatingKey": album.parent_rating_key,
                    "posterLocal": album.poster_local,
                })
        return albums

    # Maximum track count for playlists.  Playlists larger than this are
    # hidden to avoid freezing the UI with a synchronous fetch of tens of
    # thousands of tracks.
    _MAX_PLAYLIST_TRACKS = 1000

    # Emoji → text replacements for playlist titles.  The app font may not
    # render all emoji; these common ones are replaced with text equivalents.
    _EMOJI_REPLACEMENTS = {
        "\u2764\ufe0f": "\u2665",   # ❤️  → ♥
        "\u2764": "\u2665",          # ❤   → ♥
        "\U0001f49c": "\u2665",      # 💜  → ♥
        "\U0001f499": "\u2665",      # 💙  → ♥
        "\U0001f49a": "\u2665",      # 💚  → ♥
        "\U0001f3b5": "\u266b",      # 🎵  → ♫
        "\U0001f3b6": "\u266b",      # 🎶  → ♫
        "\u2b50": "\u2605",          # ⭐  → ★
        "\U0001f525": "*",           # 🔥  → *
    }

    @classmethod
    def _replace_emoji(cls, text: str) -> str:
        for emoji, replacement in cls._EMOJI_REPLACEMENTS.items():
            text = text.replace(emoji, replacement)
        return text

    @Slot(result="QVariant")
    def getPlaylists(self) -> list:
        """Return audio playlists as a list of dicts.

        Filters out non-audio playlists, playlists with more than
        _MAX_PLAYLIST_TRACKS tracks (to avoid UI freezes), and smart
        playlists that return zero items from the API.
        """
        if self._client is None:
            return []
        raw = self._client.get_playlists()
        result = []
        for p in raw:
            if p.get("playlistType") != "audio":
                continue
            leaf_count = int(p.get("leafCount", 0) or 0)
            if leaf_count > self._MAX_PLAYLIST_TRACKS:
                continue
            # Smart playlists may report a leafCount but return 0 items
            # from the API.  Probe with a single-item fetch to check.
            rk = str(p.get("ratingKey", ""))
            if p.get("smart") and rk:
                probe = self._client.get_playlist_items(rk, limit=1)
                if not probe:
                    continue
            result.append({
                "ratingKey": rk,
                "title": self._replace_emoji(p.get("title", "")),
                "leafCount": leaf_count,
                "duration": int(p.get("duration", 0) or 0),
                "smart": bool(p.get("smart", False)),
            })
        return result

    @Slot(str, result="QVariant")
    def getPlaylistTracks(self, rating_key: str) -> list:
        """Return tracks for a playlist as a list of dicts."""
        if self._client is None:
            return []
        raw = self._client.get_playlist_items(rating_key)
        result = []
        for item in raw:
            track = parse_track(item)
            result.append({
                "ratingKey": track.rating_key,
                "title": track.title,
                "index": track.index,
                "durationMs": track.duration_ms,
                "parentTitle": track.parent_title,
                "grandparentTitle": track.grandparent_title,
                "mediaKey": track.media_key,
            })
        return result

    @Slot(str, result="QVariant")
    def getRecentlyAddedAlbums(self, section_key: str) -> list:
        """Return recently added albums for a music library section."""
        if self._client is None:
            return []
        data = self._client._get(f"/library/sections/{section_key}/recentlyAdded")
        if data is None:
            return []
        items = data.get("MediaContainer", {}).get("Metadata", [])
        result = []
        for item in items:
            if item.get("type") != "album":
                continue
            album = parse_album(item)
            if album.thumb_path and self._poster_cache:
                album.poster_local = self._poster_cache.get_poster(
                    self._client, album.thumb_path
                )
            result.append({
                "ratingKey": album.rating_key,
                "title": album.title,
                "year": album.year,
                "parentTitle": album.parent_title,
                "posterLocal": album.poster_local,
            })
        return result

    @Slot(str, result="QVariant")
    def getTracks(self, album_rating_key: str) -> list:
        """Return tracks list as a list of dicts (synchronous, blocks briefly)."""
        if self._client is None:
            return []
        children = self._client.get_children(album_rating_key)
        tracks = []
        for item in children:
            if item.get("type") == "track":
                track = parse_track(item)
                tracks.append({
                    "ratingKey": track.rating_key,
                    "title": track.title,
                    "index": track.index,
                    "durationMs": track.duration_ms,
                    "parentTitle": track.parent_title,
                    "grandparentTitle": track.grandparent_title,
                    "mediaKey": track.media_key,
                })
        return tracks

    @Slot(str, result=str)
    def getTrackStreamUrl(self, media_key: str) -> str:
        """Return the authenticated stream URL for a track media part.

        Returns {server_url}{media_key}?X-Plex-Token={token}.
        This URL can be used directly as a MediaPlayer source in QML.
        """
        if self._client is None:
            return ""
        return self._client.get_poster_url(media_key)

    @Slot()
    def launchLiveTv(self) -> None:
        """Launch Plex Web in kiosk browser at the Live TV guide.

        Builds a deep-link URL using the active token, then delegates to the
        browser launcher.  The URL format places the token before the hash
        fragment so Plex Web picks it up correctly.
        """
        if self._browser_launcher is None:
            logger.warning("PlexLibrary.launchLiveTv: no browser launcher configured")
            return
        if not self._active_token:
            logger.warning("PlexLibrary.launchLiveTv: no active token — ignoring")
            return

        url = (
            f"https://app.plex.tv/desktop"
            f"?X-Plex-Token={self._active_token}"
            f"#!/live-tv"
        )
        user_title = self._cached_user_title
        if user_title:
            url += f"&htpc_user={quote(user_title)}"
        logger.info("PlexLibrary.launchLiveTv: launching %s", url)
        self._browser_launcher.launch(url)

    @Slot(str)
    def launchContent(self, rating_key: str) -> None:
        """Launch Plex Web in kiosk browser for the given content.

        Builds a deep-link URL using the cached machine identifier and the
        server URL from config, then delegates to the browser launcher.
        """
        if self._browser_launcher is None:
            logger.warning("PlexLibrary.launchContent: no browser launcher configured")
            return
        if not self._server_url:
            logger.warning("PlexLibrary.launchContent: no Plex server URL configured")
            return
        if not rating_key:
            logger.warning("PlexLibrary.launchContent: empty rating key — ignoring")
            return

        machine_id = self._machine_identifier

        url = (
            f"https://app.plex.tv/desktop"
            f"?X-Plex-Token={self._active_token}"
            f"#!/server/{machine_id}/details"
            f"?key=/library/metadata/{rating_key}"
            f"&autoPlay=1"
        )
        user_title = self._cached_user_title
        if user_title:
            url += f"&htpc_user={quote(user_title)}"
        logger.info("PlexLibrary.launchContent: launching %s", url)
        self._browser_launcher.launch(url)

    # ------------------------------------------------------------------
    # Internal: worker thread functions
    # ------------------------------------------------------------------

    def _worker_refresh(self, client: PlexClient) -> None:
        """Worker: check availability, fetch libraries and on-deck."""
        try:
            identity = client.get_identity()
            machine_id = identity.get("machineIdentifier", "")
            is_available = bool(machine_id)
        except Exception:  # noqa: BLE001
            machine_id = ""
            is_available = False

        self._availabilityReady.emit(is_available)
        if machine_id:
            self._machineIdentifierReady.emit(machine_id)

        if is_available:
            try:
                libraries = client.get_libraries()
                self._librariesReady.emit(libraries)
            except Exception as exc:  # noqa: BLE001
                logger.warning("PlexLibrary: failed to fetch libraries: %s", exc)

            # On-deck (Continue Watching) is only available for the admin user.
            # Managed/restricted users' tokens get 401 from the server, so we
            # can't fetch their on-deck data.  Skip for restricted users.
            if not self._content_rating_filter:
                try:
                    on_deck_raw = client.get_on_deck()
                    self._onDeckReady.emit(on_deck_raw)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("PlexLibrary: failed to fetch on-deck: %s", exc)
            else:
                # Clear any stale on-deck data from the previous user
                self._onDeckReady.emit([])

    def _worker_load_section(
        self,
        client: PlexClient,
        section_key: str,
        section_type: str,
        sort: str = "",
        genre: str = "",
    ) -> None:
        """Worker: load all items for a library section."""
        if section_type == "artist":
            # Try loading from cache first for instant display
            cached = self._load_artists_cache()
            if cached:
                self._artistsReady.emit(cached, len(cached))

            # Load all artists at once — most music libraries have <500 artists
            page_size = 9999
        else:
            page_size = _PAGE_SIZE

        try:
            items, total = client.get_library_items(
                section_key, 0, page_size, sort=sort, genre=genre,
                content_rating=self._content_rating_filter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexLibrary: failed to load section %s: %s", section_key, exc)
            return

        if section_type == "movie":
            movies = [parse_movie(item) for item in items]
            self._moviesReady.emit(movies, total)
        elif section_type == "show":
            shows = [parse_show(item) for item in items]
            self._showsReady.emit(shows, total)
        elif section_type == "artist":
            artists = [parse_artist(item) for item in items]
            # Pre-resolve cached posters on the worker thread so the main
            # thread doesn't queue hundreds of poster-fetch tasks for
            # already-cached images.
            if self._poster_cache is not None:
                for artist in artists:
                    if artist.thumb_path:
                        cached_path = self._poster_cache._cache_path(artist.thumb_path)
                        if cached_path.exists():
                            artist.poster_local = cached_path.as_uri()
            self._artistsReady.emit(artists, total)

    def _worker_load_more_movies(
        self,
        client: PlexClient,
        section_key: str,
        start: int,
        sort: str = "",
        genre: str = "",
    ) -> None:
        """Worker: load the next page of movies."""
        try:
            items, total = client.get_library_items(
                section_key, start, _PAGE_SIZE, sort=sort, genre=genre,
                content_rating=self._content_rating_filter,
            )
            movies = [parse_movie(item) for item in items]
            self._moviesReady.emit(movies, total)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexLibrary: failed to load more movies: %s", exc)
            self._loading_more = False

    def _worker_load_more_shows(
        self,
        client: PlexClient,
        section_key: str,
        start: int,
        sort: str = "",
        genre: str = "",
    ) -> None:
        """Worker: load the next page of shows."""
        try:
            items, total = client.get_library_items(
                section_key, start, _PAGE_SIZE, sort=sort, genre=genre,
                content_rating=self._content_rating_filter,
            )
            shows = [parse_show(item) for item in items]
            self._showsReady.emit(shows, total)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexLibrary: failed to load more shows: %s", exc)
            self._shows_loading_more = False

    def _worker_fetch_poster(
        self,
        client: PlexClient,
        thumb_path: str,
        model_type: str,
        row: int,
    ) -> None:
        """Worker: download a poster and emit posterReady when done."""
        local_url = self._poster_cache.get_poster(client, thumb_path)
        if local_url:
            self._posterReady.emit(model_type, row, local_url)

    # ------------------------------------------------------------------
    # Internal: main-thread result handlers
    # ------------------------------------------------------------------

    def _on_availability_ready(self, is_available: bool) -> None:
        self._available = is_available
        self.availableChanged.emit()

    def _on_machine_identifier_ready(self, machine_id: str) -> None:
        self._machine_identifier = machine_id
        logger.debug("PlexLibrary: cached machineIdentifier=%s", machine_id)

    def _on_libraries_ready(self, libraries: list) -> None:
        self._libraries_model.set_items(libraries)
        self.librariesModelChanged.emit()

    def _on_movies_ready(self, movies: list, total: int) -> None:
        self._loading_more = False
        if self._movies_loaded == 0:
            # First page — replace model
            self._movies_model.set_movies(movies)
            self.moviesModelChanged.emit()
        else:
            # Subsequent pages — append
            self._movies_model.append_movies(movies)

        self._movies_total = total
        self._movies_loaded += len(movies)

        # Kick off poster downloads for new items
        client = self._client
        if client is not None:
            start_row = self._movies_loaded - len(movies)
            for i, movie in enumerate(movies):
                if movie.thumb_path:
                    row = start_row + i
                    self._executor.submit(
                        self._worker_fetch_poster, client, movie.thumb_path, "movie", row
                    )

    def _on_shows_ready(self, shows: list, total: int) -> None:
        self._shows_loading_more = False
        if self._shows_loaded == 0:
            # First page — replace model
            self._shows_model.set_shows(shows)
            self.showsModelChanged.emit()
        else:
            # Subsequent pages — append
            self._shows_model.append_shows(shows)

        self._shows_total = total
        self._shows_loaded += len(shows)

        # Kick off poster downloads for new items
        client = self._client
        if client is not None:
            start_row = self._shows_loaded - len(shows)
            for i, show in enumerate(shows):
                if show.thumb_path:
                    row = start_row + i
                    self._executor.submit(
                        self._worker_fetch_poster, client, show.thumb_path, "show", row
                    )

    def _on_artists_ready(self, artists: list, total: int) -> None:
        self._artists_model.set_artists(artists)
        self.artistsModelChanged.emit()

        # Save to cache for instant load on next launch
        self._save_artists_cache(artists)

        # Kick off poster downloads only for artists missing a local poster
        client = self._client
        if client is not None:
            for i, artist in enumerate(artists):
                if artist.thumb_path and not artist.poster_local:
                    self._executor.submit(
                        self._worker_fetch_poster, client, artist.thumb_path, "artist", i
                    )

    def _on_on_deck_ready(self, raw_items: list) -> None:
        items = []
        for item in raw_items:
            item_type = item.get("type", "")
            items.append({
                "rating_key": str(item.get("ratingKey", "")),
                "title": item.get("title", ""),
                "type": item_type,
                "poster_local": "",
                "grandparent_title": item.get("grandparentTitle", ""),
                "view_offset": int(item.get("viewOffset", 0) or 0),
                "duration": int(item.get("duration", 0) or 0),
                "thumb_path": item.get("thumb", ""),
            })
        self._on_deck_model.set_items(items)
        self.onDeckModelChanged.emit()

        # Kick off poster downloads
        client = self._client
        if client is not None:
            for i, item in enumerate(items):
                if item.get("thumb_path"):
                    self._executor.submit(
                        self._worker_fetch_poster, client, item["thumb_path"], "ondeck", i
                    )

    def _on_poster_ready(self, model_type: str, row: int, file_url: str) -> None:
        """Update the poster_local field in the appropriate model."""
        if model_type == "movie":
            if 0 <= row < len(self._movies_model._movies):
                self._movies_model._movies[row].poster_local = file_url
                self._movies_model.notify_poster_changed(row)
        elif model_type == "show":
            if 0 <= row < len(self._shows_model._shows):
                self._shows_model._shows[row].poster_local = file_url
                self._shows_model.notify_poster_changed(row)
        elif model_type == "ondeck":
            if 0 <= row < len(self._on_deck_model._items):
                self._on_deck_model._items[row]["poster_local"] = file_url
                self._on_deck_model.notify_poster_changed(row)
        elif model_type == "artist":
            if 0 <= row < len(self._artists_model._artists):
                self._artists_model._artists[row].poster_local = file_url
                self._artists_model.notify_poster_changed(row)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _artists_cache_path(self) -> Path:
        """Return the path to the artist list cache file, scoped by section key."""
        cache_dir = Path.home() / ".config" / "htpcstation" / "poster_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        section_key = self._current_section_key or "default"
        return cache_dir / f"artists_cache_{section_key}.json"

    def _save_artists_cache(self, artists: list) -> None:
        """Serialize the artist list to a JSON cache file (called from worker thread)."""
        try:
            data = []
            for a in artists:
                data.append({
                    "rating_key": a.rating_key,
                    "title": a.title,
                    "summary": a.summary,
                    "thumb_path": a.thumb_path,
                    "genre": a.genre,
                    "poster_local": a.poster_local,
                })
            path = self._artists_cache_path()
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save artists cache", exc_info=True)

    def _load_artists_cache(self) -> list | None:
        """Load the artist list from the JSON cache file (called from worker thread).

        Returns a list of PlexArtist objects, or None if the cache is missing or corrupt.
        """
        path = self._artists_cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            artists = []
            for item in data:
                artists.append(PlexArtist(
                    rating_key=item.get("rating_key", ""),
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    thumb_path=item.get("thumb_path", ""),
                    genre=item.get("genre", ""),
                    poster_local=item.get("poster_local", ""),
                ))
            return artists
        except Exception:
            logger.warning("Failed to load artists cache", exc_info=True)
            return None

    def _resolve_server_url(self) -> Optional[str]:
        """Resolve the server URL from plex.tv resources API.

        Finds the server matching config.plex_server_id and picks the best
        connection URL using the priority: local > non-relay > relay, with
        HTTPS preferred within each tier.

        Returns the URI string, or None if not found.
        """
        if self._account is None or not self._config.plex_server_id:
            return None

        resources = self._account.get_resources()
        server = next(
            (r for r in resources if r.get("clientIdentifier") == self._config.plex_server_id),
            None,
        )
        if server is None:
            logger.warning(
                "PlexLibrary: server %s not found in resources", self._config.plex_server_id
            )
            return None

        connections = server.get("connections", [])
        if not connections:
            logger.warning("PlexLibrary: server %s has no connections", self._config.plex_server_id)
            return None

        # Sort connections by priority: local first, then non-relay, then relay.
        # Within each tier, prefer direct IP connections over plex.direct URLs
        # (which may have stale/wrong IPs), then prefer HTTPS over HTTP.
        def _conn_priority(conn: dict) -> tuple:
            is_local = bool(conn.get("local", False))
            is_relay = bool(conn.get("relay", False))
            is_https = conn.get("protocol", "") == "https"
            is_plex_direct = "plex.direct" in conn.get("uri", "")
            # Lower tuple = higher priority
            tier = 0 if is_local else (2 if is_relay else 1)
            # Within a tier, prefer non-plex.direct (direct IP) over plex.direct
            plex_direct_pref = 1 if is_plex_direct else 0
            https_pref = 0 if is_https else 1
            return (tier, plex_direct_pref, https_pref)

        sorted_conns = sorted(connections, key=_conn_priority)
        best = sorted_conns[0]
        uri = best.get("uri", "")
        logger.info("PlexLibrary: resolved server URL: %s", uri)
        return uri or None

    def _setup_client(self) -> None:
        """Create the PlexClient using PlexAccount server discovery."""
        token = self._config.plex_token
        if not token:
            self._client = None
            self._account = None
            self._server_url = ""
            logger.info("PlexLibrary: no Plex token configured")
            return

        if not self._config.plex_server_id:
            self._client = None
            self._account = PlexAccount(token)
            self._server_url = ""
            logger.info("PlexLibrary: no Plex server selected")
            return

        self._account = PlexAccount(token)
        server_url = self._resolve_server_url()
        if not server_url:
            self._client = None
            self._server_url = ""
            logger.info("PlexLibrary: could not resolve server URL")
            return

        # If a user is selected, switch to get a user-specific token.
        # Cache the result to avoid hammering the API on every refresh().
        user_token = token
        user_id = self._config.plex_user_id
        if user_id:
            if self._cached_user_id == user_id and self._cached_user_token:
                # Reuse the cached token and restriction filter
                user_token = self._cached_user_token
                self._content_rating_filter = self._cached_content_rating_filter
                logger.debug("PlexLibrary: reusing cached token for user %s", user_id)
            else:
                switched_token = self._account.switch_user(user_id)
                if switched_token:
                    user_token = switched_token
                    self._cached_user_id = user_id
                    self._cached_user_token = switched_token
                    # Look up and cache the user's display title and restriction profile
                    home_users = self._account.get_home_users()
                    matched = next(
                        (u for u in home_users if u.get("id") == user_id), None
                    )
                    self._cached_user_title = matched.get("title", "") if matched else ""
                    restriction = matched.get("restrictionProfile", "") if matched else ""
                    self._content_rating_filter = _RESTRICTION_RATINGS.get(restriction, "")
                    self._cached_content_rating_filter = self._content_rating_filter
                    logger.info("PlexLibrary: switched to user %s", user_id)
                else:
                    logger.warning(
                        "PlexLibrary: failed to switch to user %s, using admin token", user_id
                    )

        self._server_url = server_url
        # The user-specific token is for browser deep links only (so Plex Web
        # applies the correct user profile and content restrictions).
        # The PlexClient uses the admin token for server API calls because
        # managed/restricted users don't have direct server access.
        self._active_token = user_token
        self._client = PlexClient(server_url, token)
        logger.info("PlexLibrary: client configured for %s", server_url)

    def _ensure_account(self) -> PlexAccount | None:
        """Return a PlexAccount, creating one if needed.

        This allows getServerList/getHomeUsers to work even when _setup_client
        failed (e.g. wrong server selected, server unreachable).
        """
        if self._account is not None:
            return self._account
        token = self._config.plex_token
        if not token:
            return None
        self._account = PlexAccount(token)
        return self._account

    @Slot(result="QVariant")
    def getServerList(self) -> list:
        """Return list of available Plex servers from plex.tv resources API.

        Returns list of {"id": clientIdentifier, "name": name, "owned": owned}.
        """
        account = self._ensure_account()
        if account is None:
            return []
        resources = account.get_resources()
        return [
            {
                "id": r.get("clientIdentifier", ""),
                "name": r.get("name", ""),
                "owned": bool(r.get("owned", False)),
            }
            for r in resources
        ]

    @Slot(result="QVariant")
    def getHomeUsers(self) -> list:
        """Return list of home users from plex.tv API.

        Returns list of {"id": id, "title": title, "admin": admin, "restricted": restricted}.
        """
        account = self._ensure_account()
        if account is None:
            return []
        users = account.get_home_users()
        return [
            {
                "id": u.get("id", 0),
                "title": u.get("title", ""),
                "admin": bool(u.get("admin", False)),
                "restricted": bool(u.get("restricted", False)),
            }
            for u in users
        ]

    @Slot(str)
    def selectServer(self, server_id: str) -> None:
        """Select a Plex server by its machine identifier.

        Only saves the selection — does not reconnect immediately.
        The next refresh() (e.g. when navigating to the Watch tab) will
        pick up the new server.
        """
        self._config.set_plex_server_id(server_id)
        # Invalidate the current client so the next refresh() reconnects
        self._client = None
        self._server_url = ""
        self._active_token = ""
        logger.info("PlexLibrary: server selection changed to %s", server_id)

    @Slot(int)
    def selectUser(self, user_id: int) -> None:
        """Select a Plex home user by ID.

        Only saves the selection — does not reconnect immediately.
        The next refresh() (e.g. when navigating to the Watch tab) will
        pick up the new user.
        """
        self._config.set_plex_user_id(user_id)
        # Clear the cached user token, title, and content rating filter
        # so the next _setup_client() will re-switch and re-resolve the restriction profile
        self._cached_user_id = None
        self._cached_user_token = ""
        self._cached_user_title = ""
        self._cached_content_rating_filter = ""
        self._content_rating_filter = ""
        # Invalidate the current client
        self._client = None
        logger.info("PlexLibrary: user selection changed to %s", user_id)
