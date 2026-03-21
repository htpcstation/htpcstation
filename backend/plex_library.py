"""Plex library manager for HTPC Station.

Exposes Plex Media Server data to QML via models and slots.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
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

from backend.browser_launcher import BrowserLauncher
from backend.config import Config, CONFIG_DIR
from backend.plex_client import PlexClient
from backend.plex_models import (
    PlexMovie,
    PlexShow,
    parse_episode,
    parse_movie,
    parse_season,
    parse_show,
)
from backend.poster_cache import PosterCache

logger = logging.getLogger(__name__)

_POSTER_CACHE_DIR = CONFIG_DIR / "poster_cache"
_PAGE_SIZE = 50


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
    currentLibraryChanged = Signal(str)

    # Internal signals used to marshal results from worker threads to main thread
    _librariesReady = Signal(list)
    _moviesReady = Signal(list, int)   # (movies, total_size)
    _showsReady = Signal(list)
    _onDeckReady = Signal(list)
    _availabilityReady = Signal(bool)
    _posterReady = Signal(str, int, str)  # (model_type, row, file_url)
    _machineIdentifierReady = Signal(str)

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
        self._machine_identifier: str = ""
        self._current_sort: str = ""   # Plex API sort param, e.g. 'titleSort:asc'
        self._current_genre: str = ""  # genre key (integer as string)

        # Build models
        self._libraries_model = PlexLibraryListModel(self)
        self._movies_model = PlexMovieListModel(self)
        self._shows_model = PlexShowListModel(self)
        self._on_deck_model = PlexOnDeckModel(self)

        # Thread pool for network calls
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Poster cache
        self._poster_cache = PosterCache(_POSTER_CACHE_DIR)

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
    currentLibrary = Property(
        str,
        fget=lambda self: self._current_library,
        notify=currentLibraryChanged,
    )
    serverUrl = Property(
        str,
        fget=lambda self: self._config.plex_server_url or "",
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
        self._current_library = section_title
        self._current_sort = ""
        self._current_genre = ""
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

    @Slot(str)
    def launchContent(self, rating_key: str) -> None:
        """Launch Plex Web in kiosk browser for the given content.

        Builds a deep-link URL using the cached machine identifier and the
        server URL from config, then delegates to the browser launcher.
        """
        if self._browser_launcher is None:
            logger.warning("PlexLibrary.launchContent: no browser launcher configured")
            return
        if not self._config.plex_server_url:
            logger.warning("PlexLibrary.launchContent: no Plex server URL configured")
            return
        if not rating_key:
            logger.warning("PlexLibrary.launchContent: empty rating key — ignoring")
            return

        machine_id = self._machine_identifier
        server_url = self._config.plex_server_url

        url = (
            f"{server_url}/web/index.html"
            f"#!/server/{machine_id}/details"
            f"?key=/library/metadata/{rating_key}"
            f"&autoPlay=1"
        )
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

            try:
                on_deck_raw = client.get_on_deck()
                self._onDeckReady.emit(on_deck_raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("PlexLibrary: failed to fetch on-deck: %s", exc)

    def _worker_load_section(
        self,
        client: PlexClient,
        section_key: str,
        section_type: str,
        sort: str = "",
        genre: str = "",
    ) -> None:
        """Worker: load all items for a library section."""
        try:
            items, total = client.get_library_items(
                section_key, 0, _PAGE_SIZE, sort=sort, genre=genre
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexLibrary: failed to load section %s: %s", section_key, exc)
            return

        if section_type == "movie":
            movies = [parse_movie(item) for item in items]
            self._moviesReady.emit(movies, total)
        elif section_type == "show":
            shows = [parse_show(item) for item in items]
            self._showsReady.emit(shows)

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
                section_key, start, _PAGE_SIZE, sort=sort, genre=genre
            )
            movies = [parse_movie(item) for item in items]
            self._moviesReady.emit(movies, total)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexLibrary: failed to load more movies: %s", exc)
            self._loading_more = False

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

    def _on_shows_ready(self, shows: list) -> None:
        self._shows_model.set_shows(shows)
        self.showsModelChanged.emit()

        # Kick off poster downloads
        client = self._client
        if client is not None:
            for i, show in enumerate(shows):
                if show.thumb_path:
                    self._executor.submit(
                        self._worker_fetch_poster, client, show.thumb_path, "show", i
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_client(self) -> None:
        """Create the PlexClient from config if server URL and token are set."""
        server_url = self._config.plex_server_url
        token = self._config.plex_token
        if server_url and token:
            self._client = PlexClient(server_url, token)
            logger.info("PlexLibrary: client configured for %s", server_url)
        else:
            logger.info("PlexLibrary: no Plex server configured")
