"""Plex library manager for HTPC Station.

Exposes Plex Media Server data to QML via models and slots.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

from PySide6.QtCore import (
    QAbstractListModel,
    QMetaObject,
    QModelIndex,
    QObject,
    Property,
    Q_ARG,
    Qt,
    Signal,
    Slot,
)

from backend.browser_launcher import BrowserLauncher
from backend.lrc_parser import parse_lrc, parse_plain
from backend.config import Config, CONFIG_DIR
from backend.mpv_launcher import LibMpvPlayer
from backend.plex_account import PlexAccount
from backend.plex_client import PlexClient, PlexErrorType
from backend.plex_timeline import PlexTimelineReporter
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

_PLEX_CACHE_DIR = CONFIG_DIR / "plex_cache"
_POSTER_CACHE_DIR = _PLEX_CACHE_DIR / "posters"
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

    def sort_movies(self, sort_key: str) -> None:
        """Sort the in-memory movie list by *sort_key* (an API sort string)."""
        key_func = {
            "titleSort:asc":       lambda m: (m.title or "").lower(),
            "titleSort:desc":      lambda m: (m.title or "").lower(),
            "addedAt:desc":        lambda m: m.added_at,
            "year:desc":           lambda m: m.year,
            "year:asc":            lambda m: m.year,
            "audienceRating:desc": lambda m: m.audience_rating,
        }.get(sort_key)
        if key_func is None:
            return
        reverse = sort_key.endswith(":desc")
        self.beginResetModel()
        self._movies.sort(key=key_func, reverse=reverse)
        self.endResetModel()

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

    def sort_shows(self, sort_key: str) -> None:
        """Sort the in-memory show list by *sort_key* (an API sort string)."""
        key_func = {
            "titleSort:asc":       lambda s: (s.title or "").lower(),
            "titleSort:desc":      lambda s: (s.title or "").lower(),
            "year:desc":           lambda s: s.year,
            "year:asc":            lambda s: s.year,
            "audienceRating:desc": lambda s: s.audience_rating,
        }.get(sort_key)
        if key_func is None:
            return
        reverse = sort_key.endswith(":desc")
        self.beginResetModel()
        self._shows.sort(key=key_func, reverse=reverse)
        self.endResetModel()

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
    myListChanged = Signal(bool)   # True = added, False = removed
    plexError = Signal(str)  # error type string: "auth", "not_found", "server", "network", "unknown"
    sectionLoadFailed = Signal()   # emitted when _worker_load_section network call fails
    mpvStarted = Signal()
    mpvFinished = Signal()
    mpvPlaybackReady = Signal()  # emitted when first frame is ready (wait_until_playing)
    markersReady = Signal(int)        # intro_end_ms (0 = no intro marker)
    mpvPositionChanged = Signal(int)  # current MPV position in ms (push-based)
    streamInfoReady = Signal(str, str, int)  # rating_key, url, view_offset_ms
    watchHistoryReady = Signal(list)
    lyricsReady = Signal(str, list)       # (rating_key, lines) — lines is list of {ms, text} dicts
    lyricsUnavailable = Signal(str)       # (rating_key) — no lyrics found or error
    movieReady    = Signal(str, "QVariant")   # (rating_key, movie_dict)
    showReady     = Signal(str, "QVariant")   # (rating_key, show_dict)
    seasonsReady  = Signal(str, "QVariant")   # (rating_key, seasons_list)
    episodesReady = Signal(str, "QVariant")   # (season_rating_key, episodes_list)
    artistPreviewReady = Signal(str, "QVariant")   # (rating_key, artist_preview_dict)
    artistDetailReady  = Signal(str, "QVariant")   # (artist_rating_key, {artist, albums})
    albumDetailReady   = Signal(str, "QVariant")   # (album_rating_key, {album, tracks})
    recentAlbumsReady  = Signal("QVariant")        # list of album dicts
    playlistsReady     = Signal("QVariant")        # list of playlist dicts
    playlistTracksReady = Signal(str, "QVariant")  # (rating_key, list of track dicts)
    posterUpdated      = Signal(str, str)           # (ratingKey, posterUrl) — lightweight poster update

    # Internal signals used to marshal results from worker threads to main thread
    _setupReady = Signal("QVariant")  # dict with setup results from worker thread
    _librariesReady = Signal(list, bool)  # (libraries, from_cache)
    _moviesReady = Signal(list, int)   # (movies, total_size)
    _showsReady = Signal(list, int)    # (shows, total_size)
    _onDeckReady = Signal(list)
    _onDeckCacheReady  = Signal(list)         # pre-processed on-deck items from disk cache
    _moviesCacheReady  = Signal(list, str)    # (PlexMovie list, section_key) from disk cache
    _showsCacheReady   = Signal(list, str)    # (PlexShow list, section_key) from disk cache
    _availabilityReady = Signal(bool)
    _posterReady = Signal(str, int, str)  # (model_type, row, file_url)
    _machineIdentifierReady = Signal(str)
    _artistsReady = Signal(list, int)  # (artists, total_size)
    _mpvLaunchReady = Signal(str, str, int, int, int, int)  # url, title, start_ms, duration_ms, part_id, intro_end_ms
    _mpvPositionMs = Signal(int)  # internal: marshal time-pos from mpv thread to main thread
    _streamInfoReady = Signal(str, str, int)  # rating_key, url, view_offset_ms
    _lyricsReady = Signal(str, list)      # (rating_key, lines)
    _lyricsUnavailable = Signal(str)      # (rating_key)
    _movieReady    = Signal(str, object)
    _showReady     = Signal(str, object)
    _seasonsReady  = Signal(str, object)
    _episodesReady = Signal(str, object)
    _artistPreviewReady = Signal(str, object)
    _artistDetailReady  = Signal(str, object)
    _albumDetailReady   = Signal(str, object)
    _recentAlbumsReady  = Signal(object)
    _playlistsReady     = Signal(object)
    _playlistTracksReady = Signal(str, object)

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
        self._section_sort: dict[str, str] = {}   # sort param per section key
        self._section_genre: dict[str, str] = {}  # genre filter per section key
        self._content_rating_filter: str = ""  # comma-separated allowed ratings for restricted users
        self._cached_content_rating_filter: str = ""  # cached alongside user token

        # Build models
        self._libraries_model = PlexLibraryListModel(self)
        self._movies_model = PlexMovieListModel(self)
        self._shows_model = PlexShowListModel(self)
        self._on_deck_model = PlexOnDeckModel(self)
        self._artists_model = PlexArtistListModel(self)
        self._my_list_model = PlexOnDeckModel(self)

        # Thread pool for network calls
        self._executor = ThreadPoolExecutor(max_workers=2)
        # Dedicated thread pool for poster downloads (higher concurrency for LAN fetching)
        self._poster_executor = ThreadPoolExecutor(max_workers=10)
        # Dedicated single-thread executor for disk-only cache loads — never
        # queued behind network work, starts immediately on app launch.
        self._cache_executor = ThreadPoolExecutor(max_workers=1)

        # Poster cache
        self._poster_cache = PosterCache(_POSTER_CACHE_DIR)

        # PlexAccount for server discovery and user switching
        self._account: Optional[PlexAccount] = None
        # Resolved server URL (set by _on_setup_ready after discovery)
        self._server_url: str = ""
        # Active token (user-specific or admin) used for deep-link URLs
        self._active_token: str = ""
        # Cache for user-switching to avoid redundant API calls on every refresh
        self._cached_user_id: Optional[int] = None
        self._cached_user_token: str = ""
        self._cached_user_title: str = ""

        # All known server connection URLs (populated by _resolve_server_url)
        self._all_server_urls: list[str] = []

        # Build Plex client if config is available
        self._client: Optional[PlexClient] = None
        self._event_listener: Optional["PlexEventListener"] = None

        # Connect internal signals (worker -> main thread)
        self._setupReady.connect(self._on_setup_ready,                   Qt.ConnectionType.QueuedConnection)
        self._librariesReady.connect(self._on_libraries_ready,           Qt.ConnectionType.QueuedConnection)
        self._moviesReady.connect(self._on_movies_ready,                 Qt.ConnectionType.QueuedConnection)
        self._showsReady.connect(self._on_shows_ready,                   Qt.ConnectionType.QueuedConnection)
        self._onDeckReady.connect(self._on_on_deck_ready,                Qt.ConnectionType.QueuedConnection)
        self._onDeckCacheReady.connect(self._on_on_deck_cache_ready,     Qt.ConnectionType.QueuedConnection)
        self._moviesCacheReady.connect(self._on_movies_cache_ready,      Qt.ConnectionType.QueuedConnection)
        self._showsCacheReady.connect(self._on_shows_cache_ready,        Qt.ConnectionType.QueuedConnection)
        self._availabilityReady.connect(self._on_availability_ready,     Qt.ConnectionType.QueuedConnection)
        self._posterReady.connect(self._on_poster_ready,                 Qt.ConnectionType.QueuedConnection)
        self._machineIdentifierReady.connect(self._on_machine_identifier_ready, Qt.ConnectionType.QueuedConnection)
        self._artistsReady.connect(self._on_artists_ready,               Qt.ConnectionType.QueuedConnection)
        self._mpvLaunchReady.connect(self._on_mpv_launch_ready, Qt.ConnectionType.QueuedConnection)
        self._streamInfoReady.connect(self._on_stream_info_ready, Qt.ConnectionType.QueuedConnection)
        self._mpvPositionMs.connect(self.mpvPositionChanged)
        self._lyricsReady.connect(self.lyricsReady)
        self._lyricsUnavailable.connect(self.lyricsUnavailable)
        self._movieReady.connect(lambda rk, d: self.movieReady.emit(rk, d))
        self._showReady.connect(lambda rk, d: self.showReady.emit(rk, d))
        self._seasonsReady.connect(lambda rk, d: self.seasonsReady.emit(rk, d))
        self._episodesReady.connect(lambda rk, d: self.episodesReady.emit(rk, d))
        self._artistPreviewReady.connect(self._on_artist_preview_ready,
                                        Qt.ConnectionType.QueuedConnection)
        self._artistDetailReady.connect(self._on_artist_detail_ready,
                                        Qt.ConnectionType.QueuedConnection)
        self._albumDetailReady.connect(self._on_album_detail_ready,
                                       Qt.ConnectionType.QueuedConnection)
        self._recentAlbumsReady.connect(self._on_recent_albums_ready,
                                        Qt.ConnectionType.QueuedConnection)
        self._playlistsReady.connect(self._on_playlists_ready,
                                     Qt.ConnectionType.QueuedConnection)
        self._playlistTracksReady.connect(self._on_playlist_tracks_ready,
                                          Qt.ConnectionType.QueuedConnection)

        # MPV launcher for direct stream playback
        self._mpv_launcher = LibMpvPlayer(parent=self)
        self._mpv_active = False  # True only while Plex VOD/Live TV owns the MPV instance
        self._mpv_launcher.processStarted.connect(self._on_mpv_process_started)
        self._mpv_launcher.processFinished.connect(self._on_mpv_process_finished)
        self._mpv_launcher.mpvPlaybackStarted.connect(self._on_mpv_playback_started)

        # Timeline reporter for Plex playback state
        self._timeline_reporter = PlexTimelineReporter(lambda: self._client)
        self._pending_play_rating_key: str = ""
        self._current_play_rating_key: str = ""
        self._current_play_duration_ms: int = 0
        self._current_play_part_id: int = 0
        self._pending_play_queue_item_id: int = 0
        self._current_play_queue_item_id: int = 0


        # Timeline reporter is driven via _on_mpv_process_finished (above)

        # One-time migration: move old cache files to new plex_cache/ layout
        self._migrate_cache_dirs()

        # Load My List from file and populate model
        items = self._load_my_list()
        self._rebuild_my_list_model(items)

        # Populate models from disk cache immediately (dedicated thread, no network I/O).
        # Uses _cache_executor so it is never queued behind network calls in _executor.
        self._cache_executor.submit(self._worker_load_all_caches)

        # Kick off server discovery + client setup on a worker thread.
        # _client remains None until _on_setup_ready fires — existing guards handle this.
        # refresh_after=False: __init__ only sets up the client; explicit refresh()
        # calls from QML trigger the data refresh.
        if self._config.plex_token:
            self._executor.submit(self._worker_setup, False)

    def set_wid(self, wid: int) -> None:
        """Pass the Qt native window handle to the MPV player.

        Must be called after the Qt window is shown (so winId() is valid).
        Registers property observers for push-based timeline position updates.
        """
        self._mpv_launcher.set_wid(wid)
        self._mpv_launcher.observe_time_pos(self._timeline_reporter.update_position)
        self._mpv_launcher.observe_pause(self._timeline_reporter.update_paused)

        def _on_time_pos(pos_seconds: float) -> None:
            if pos_seconds is not None:
                self._mpvPositionMs.emit(int(pos_seconds * 1000))

        self._mpv_launcher.observe_time_pos(_on_time_pos)

    def shutdown(self) -> None:
        """Shut down thread pools. Call before application exit."""
        self._stop_event_listener()
        self._timeline_reporter.stop()
        self._mpv_launcher.shutdown()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._poster_executor.shutdown(wait=False, cancel_futures=True)

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
    myListModel = Property(
        QObject,
        fget=lambda self: self._my_list_model,
        notify=myListChanged,
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
        my_list_count = len(self._my_list_model._items)
        if my_list_count:
            result.append({
                "title": "My List",
                "type": "mylist",
                "sectionKey": "_mylist",
                "count": my_list_count,
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
        token = self._config.plex_token
        if not token:
            self._client = None
            self._account = None
            self._server_url = ""
            self._on_availability_ready(False)
            return
        self._executor.submit(self._worker_setup, True)

    @Slot(str)
    def selectLibrary(self, section_key: str) -> None:
        """Load items for a library section identified by *section_key*."""
        # On-deck data is already loaded in onDeckModel from refresh().
        # There is no /library/sections/_ondeck/all endpoint — return early.
        if section_key == "_ondeck":
            self._current_section_key = section_key
            self._current_section_type = "ondeck"
            self._current_library = "Continue Watching"
            self.currentLibraryChanged.emit("Continue Watching")
            return

        # My List data is already loaded in myListModel from file.
        # There is no /library/sections/_mylist/all endpoint — return early.
        if section_key == "_mylist":
            self._current_section_key = section_key
            self._current_section_type = "mylist"
            self._current_library = "My List"
            self.currentLibraryChanged.emit("My List")
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

        # Cache-first: emit cached data immediately for instant display.
        # Skip if the model already has content (e.g. returning from a detail
        # view) — re-loading cache triggers set_movies/set_shows which resets
        # the GridView's contentY, causing scroll position jumps.
        if section_type == "movie" and len(self._movies_model._movies) == 0:
            cached = self._load_movies_cache(section_key)
            if cached:
                self._resolve_cached_posters(cached)
                self._on_movies_cache_ready(cached, section_key)
        elif section_type == "show" and len(self._shows_model._shows) == 0:
            cached = self._load_shows_cache(section_key)
            if cached:
                self._resolve_cached_posters(cached)
                self._on_shows_cache_ready(cached, section_key)
        elif section_type == "artist" and len(self._artists_model._artists) == 0:
            cached = self._load_artists_cache()
            if cached:
                self._resolve_cached_posters(cached)
                self._on_artists_ready(cached, len(cached))

        if self._client is None:
            # No server connection — show cached data only (loaded above).
            # Emit sectionLoadFailed so QML shows offline toast.
            self.sectionLoadFailed.emit()
            return

        client = self._client
        sort = self._section_sort.get(section_key, "")
        genre = self._section_genre.get(section_key, "")
        self._executor.submit(self._worker_load_section, client, section_key, section_type, sort, genre)

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
        sort = self._section_sort.get(section_key, "")
        genre = self._section_genre.get(section_key, "")
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
        if not self._current_section_key:
            return
        if self._current_section_key in ("_mylist", "_ondeck", "_livetv"):
            return
        api_sort = self._SORT_MAP.get(sort_key, "")
        self._section_sort[self._current_section_key] = api_sort
        self._save_sort_state()

        # Instant local sort for cached/in-memory data
        self._movies_model.sort_movies(api_sort)
        self.moviesModelChanged.emit()

        if self._client is None:
            return

        self._movies_total = 0
        self._movies_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        genre = self._section_genre.get(section_key, "")
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            api_sort, genre
        )

    @Slot(str)
    def filterByGenre(self, genre_key: str) -> None:
        """Re-fetch movies filtered by genre. Empty string clears the filter."""
        if self._client is None or not self._current_section_key:
            return
        if self._current_section_key in ("_mylist", "_ondeck", "_livetv"):
            return
        self._section_genre[self._current_section_key] = genre_key
        self._save_sort_state()
        self._movies_total = 0
        self._movies_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        sort = self._section_sort.get(section_key, "")
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
        sort = self._section_sort.get(section_key, "")
        genre = self._section_genre.get(section_key, "")
        self._executor.submit(
            self._worker_load_more_shows, client, section_key, start, sort, genre
        )

    @Slot(str)
    def sortShows(self, sort_key: str) -> None:
        """Re-fetch shows with the given sort.

        sort_key: 'az', 'za', 'recent', 'year_desc', 'year_asc', 'rating'
        """
        if not self._current_section_key:
            return
        if self._current_section_key in ("_mylist", "_ondeck", "_livetv"):
            return
        api_sort = self._SORT_MAP.get(sort_key, "")
        self._section_sort[self._current_section_key] = api_sort
        self._save_sort_state()

        # Instant local sort for cached/in-memory data
        self._shows_model.sort_shows(api_sort)
        self.showsModelChanged.emit()

        if self._client is None:
            return

        self._shows_total = 0
        self._shows_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        genre = self._section_genre.get(section_key, "")
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
        if self._current_section_key in ("_mylist", "_ondeck", "_livetv"):
            return
        self._section_genre[self._current_section_key] = genre_key
        self._save_sort_state()
        self._shows_total = 0
        self._shows_loaded = 0
        client = self._client
        section_key = self._current_section_key
        section_type = self._current_section_type
        sort = self._section_sort.get(section_key, "")
        self._executor.submit(
            self._worker_load_section, client, section_key, section_type,
            sort, genre_key
        )

    @Slot(result="QVariant")
    def getMovieGenres(self) -> list:
        """Return genres for the current movie library as [{key, title}, ...]."""
        if self._client is None or not self._current_section_key:
            return []
        if not self._available:
            return []
        return self._client.get_genres(self._current_section_key)

    @Slot(result="QVariant")
    def getShowGenres(self) -> list:
        """Return genres for the current show library as [{key, title}, ...]."""
        if self._client is None or not self._current_section_key:
            return []
        if not self._available:
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

    def _fetch_movie(self, client, poster_cache, rating_key: str) -> dict:
        """Worker-thread helper: fetch and parse movie metadata. Returns a dict."""
        data = client.get_metadata(rating_key)
        if not data:
            return {}
        movie = parse_movie(data)
        if movie.thumb_path and poster_cache:
            movie.poster_local = poster_cache.get_poster(client, movie.thumb_path)
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
            "viewCount": int(data.get("viewCount", 0) or 0),
        }

    def _fetch_show(self, client, poster_cache, rating_key: str) -> dict:
        """Worker-thread helper: fetch and parse show metadata. Returns a dict."""
        data = client.get_metadata(rating_key)
        if not data:
            return {}
        show = parse_show(data)
        if show.thumb_path and poster_cache:
            show.poster_local = poster_cache.get_poster(client, show.thumb_path)
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
            "viewCount": int(data.get("viewCount", 0) or 0),
        }

    def _fetch_seasons(self, client, rating_key: str) -> list:
        """Worker-thread helper: fetch and parse seasons list. Returns a list of dicts."""
        children = client.get_children(rating_key)
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

    def _fetch_episodes(self, client, season_rating_key: str) -> list:
        """Worker-thread helper: fetch and parse episodes list. Returns a list of dicts."""
        children = client.get_children(season_rating_key)
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
    def fetchMovie(self, rating_key: str) -> None:
        """Async: fetch movie details and emit movieReady(rating_key, movie_dict)."""
        if self._client is None:
            self._movieReady.emit(rating_key, {})
            return
        client = self._client
        poster_cache = self._poster_cache
        def _worker():
            result = self._fetch_movie(client, poster_cache, rating_key)
            self._movieReady.emit(rating_key, result)
        self._executor.submit(_worker)

    @Slot(str)
    def fetchShow(self, rating_key: str) -> None:
        """Async: fetch show details and emit showReady(rating_key, show_dict)."""
        if self._client is None:
            self._showReady.emit(rating_key, {})
            return
        client = self._client
        poster_cache = self._poster_cache
        def _worker():
            result = self._fetch_show(client, poster_cache, rating_key)
            self._showReady.emit(rating_key, result)
        self._executor.submit(_worker)

    @Slot(str)
    def fetchSeasons(self, rating_key: str) -> None:
        """Async: fetch seasons list and emit seasonsReady(rating_key, seasons_list)."""
        if self._client is None:
            self._seasonsReady.emit(rating_key, [])
            return
        client = self._client
        def _worker():
            result = self._fetch_seasons(client, rating_key)
            self._seasonsReady.emit(rating_key, result)
        self._executor.submit(_worker)

    @Slot(str)
    def fetchEpisodes(self, season_rating_key: str) -> None:
        """Async: fetch episodes list and emit episodesReady(season_rating_key, episodes_list)."""
        if self._client is None:
            self._episodesReady.emit(season_rating_key, [])
            return
        client = self._client
        def _worker():
            result = self._fetch_episodes(client, season_rating_key)
            self._episodesReady.emit(season_rating_key, result)
        self._executor.submit(_worker)

    @Slot(str, int)
    def fetchStreamInfo(self, rating_key: str, known_view_offset: int = 0) -> None:
        """Async version of getStreamInfo. Emits streamInfoReady when done.

        known_view_offset: if > 0, skip the server viewOffset and use this value directly.
        The url is still fetched from the server.
        """
        if self._client is None:
            self._streamInfoReady.emit(rating_key, "", 0)
            return
        client = self._client
        def _worker():
            url, server_offset = client.get_stream_url(rating_key)
            effective_offset = known_view_offset if known_view_offset > 0 else server_offset
            self._streamInfoReady.emit(rating_key, url, effective_offset)
        self._executor.submit(_worker)

    def _on_stream_info_ready(self, rating_key: str, url: str, view_offset_ms: int) -> None:
        """Called on main thread when async stream info fetch completes."""
        self.streamInfoReady.emit(rating_key, url, view_offset_ms)

    @Slot(int)
    def fetchWatchHistory(self, limit: int = 50) -> None:
        """Async version of getWatchHistory. Emits watchHistoryReady when done."""
        if self._client is None:
            self.watchHistoryReady.emit([])
            return
        client = self._client
        def _worker():
            raw = client.get_watch_history(limit=limit)
            result = []
            for item in raw:
                result.append({
                    "ratingKey": str(item.get("ratingKey", "")),
                    "title": item.get("title", ""),
                    "type": item.get("type", ""),
                    "viewedAt": int(item.get("viewedAt", 0) or 0),
                    "grandparentTitle": item.get("grandparentTitle", ""),
                    "thumb": item.get("thumb", ""),
                    "grandparentThumb": item.get("grandparentThumb", ""),
                    "duration": int(item.get("duration", 0) or 0),
                })
            self.watchHistoryReady.emit(result)
        self._executor.submit(_worker)

    @Slot(str, int)
    def playWithMpv(self, rating_key: str, start_ms: int = 0) -> None:
        """Fetch stream URL and launch MPV. Dispatches HTTP calls to thread pool."""
        if self._client is None:
            logger.warning("playWithMpv: no Plex client configured")
            return
        self._pending_play_rating_key = rating_key
        client = self._client
        def _worker():
            url, _ = client.get_stream_url(rating_key)
            if not url:
                self._mpvLaunchReady.emit("", "", 0, 0, 0, 0)
                return

            # Replace long-lived token with a short-lived transient token
            transient = client.get_transient_token()
            if transient and self._config is not None:
                main_token = self._config.plex_token or ""
                if main_token and main_token in url:
                    url = url.replace(main_token, transient)

            meta = client.get_metadata(rating_key, include_markers=True)
            title = meta.get("title", "")
            grandparent = meta.get("grandparentTitle", "")
            if grandparent:
                title = f"{grandparent} — {title}"
            duration_ms = int(meta.get("duration", 0) or 0)
            # Extract part_id and stream IDs for track persistence
            media = meta.get("Media", [])
            part_id = 0
            parts = []
            if media:
                parts = media[0].get("Part", [])
                if parts:
                    part_id = int(parts[0].get("id", 0) or 0)
            # Parse intro marker end time
            intro_end_ms = 0
            for marker in meta.get("Marker", []):
                if marker.get("type") == "intro":
                    intro_end_ms = int(marker.get("endTimeOffset", 0) or 0)
                    break
            # Register play queue with server (enables Plex Companion + Up Next)
            play_queue_item_id = 0
            machine_id = self._machine_identifier  # already cached from identity fetch
            if machine_id:
                pq_data = client.create_play_queue(rating_key, machine_id)
                container = pq_data.get("MediaContainer", {})
                # playQueueItemID is on the first item in the queue
                items = container.get("Metadata", [])
                if items:
                    play_queue_item_id = int(items[0].get("playQueueItemID", 0) or 0)
                logger.info("playWithMpv: playQueueItemID=%d", play_queue_item_id)
            self._pending_play_queue_item_id = play_queue_item_id
            logger.info("playWithMpv: launching MPV for '%s' start_ms=%d", title, start_ms)
            self._mpvLaunchReady.emit(url, title, start_ms, duration_ms, part_id, intro_end_ms)
        self._executor.submit(_worker)

    def _on_mpv_launch_ready(
        self,
        url: str,
        title: str,
        start_ms: int,
        duration_ms: int,
        part_id: int,
        intro_end_ms: int = 0,
    ) -> None:
        """Launch MPV on the main thread after worker fetched stream info."""
        if not url:
            logger.warning("playWithMpv: no stream URL — cannot launch")
            self.mpvFinished.emit()  # clear loading state in QML
            return
        self._current_play_rating_key = self._pending_play_rating_key
        self._current_play_duration_ms = duration_ms
        self._current_play_part_id = part_id
        self._current_play_queue_item_id = self._pending_play_queue_item_id
        self._mpv_active = True
        self._mpv_launcher.launch(url, title, start_ms)
        self.markersReady.emit(intro_end_ms)

    @Slot(str)
    def playWithMpvFromStart(self, rating_key: str) -> None:
        """Launch MPV from the beginning (no resume). Convenience slot for QML."""
        self.playWithMpv(rating_key, 0)

    @Slot()
    def stopMpv(self) -> None:
        """Stop MPV playback immediately. Safe to call when nothing is playing."""
        self._mpv_launcher.kill()

    @Slot(int)
    def seekMpv(self, position_ms: int) -> None:
        """Seek MPV to an absolute position in milliseconds."""
        if self._mpv_launcher._player is None:
            return
        try:
            self._mpv_launcher._player.seek(position_ms / 1000.0, "absolute")
        except Exception:  # noqa: BLE001
            pass

    @Slot(str)
    def markPlayed(self, rating_key: str) -> None:
        """Mark an item as watched. Dispatches to thread pool."""
        if self._client is None:
            return
        client = self._client
        self._executor.submit(client.mark_played, rating_key)

    @Slot(str)
    def markUnplayed(self, rating_key: str) -> None:
        """Mark an item as unwatched. Dispatches to thread pool."""
        if self._client is None:
            return
        client = self._client
        self._executor.submit(client.mark_unplayed, rating_key)

    @Slot(str, float)
    def rate(self, rating_key: str, rating: float) -> None:
        """Set a star rating (0.0–10.0) for a library item. 0.0 clears the rating.

        Fire-and-forget — dispatched to the worker thread pool.
        """
        if self._client is None or not rating_key:
            return
        client = self._client
        self._executor.submit(client.rate, rating_key, rating)

    def _on_mpv_started_for_timeline(self) -> None:
        """Start timeline reporting when MPV begins playing."""
        if not self._current_play_rating_key:
            return
        self._timeline_reporter.start(
            rating_key=self._current_play_rating_key,
            duration_ms=self._current_play_duration_ms,
            start_ms=0,  # MPV is already at the right position; observer will update
            play_queue_item_id=self._current_play_queue_item_id,
        )

    def _on_mpv_process_started(self) -> None:
        """Forward processStarted and start timeline only when Plex owns the MPV instance."""
        if not self._mpv_active:
            return
        self.mpvStarted.emit()
        self._on_mpv_started_for_timeline()

    def _on_mpv_process_finished(self, exit_code: int) -> None:
        """Forward processFinished only when Plex owns the MPV instance."""
        self._on_mpv_finished_for_timeline(exit_code)
        if not self._mpv_active:
            return
        self._mpv_active = False
        self.mpvFinished.emit()

    def _on_mpv_finished_for_timeline(self, exit_code: int) -> None:
        """Stop timeline reporting when MPV exits."""
        self._timeline_reporter.stop()

    def _on_mpv_playback_started(self) -> None:
        """Called on main thread when MPV first frame is ready."""
        if self._mpv_active:
            self.mpvPlaybackReady.emit()

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

    @Slot(str)
    def fetchArtistPreview(self, rating_key: str) -> None:
        """Async: fetch artist metadata only (no albums). Emits artistPreviewReady."""
        if self._client is None:
            return
        client = self._client
        poster_cache = self._poster_cache

        def _worker():
            data = client.get_metadata(rating_key)
            if not data:
                return
            artist = parse_artist(data)
            if artist.thumb_path and poster_cache:
                cached_path = poster_cache._cache_path(artist.thumb_path)
                if cached_path.exists():
                    artist.poster_local = cached_path.as_uri()
            self._artistPreviewReady.emit(rating_key, {
                "ratingKey": artist.rating_key,
                "title": artist.title,
                "summary": artist.summary,
                "genre": artist.genre,
                "posterLocal": artist.poster_local,
            })

        self._executor.submit(_worker)

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

    @Slot(str)
    def fetchArtistDetail(self, rating_key: str) -> None:
        """Async: fetch artist metadata + albums. Emits artistDetailReady."""
        if self._client is None:
            return
        client = self._client
        poster_cache = self._poster_cache
        def _worker():
            import re
            artist_dict = {}
            data = client.get_metadata(rating_key)
            if data:
                artist = parse_artist(data)
                if artist.thumb_path and poster_cache:
                    cached_path = poster_cache._cache_path(artist.thumb_path)
                    if cached_path.exists():
                        artist.poster_local = cached_path.as_uri()
                artist_dict = {
                    "ratingKey": artist.rating_key,
                    "title": artist.title,
                    "summary": artist.summary,
                    "genre": artist.genre,
                    "posterLocal": artist.poster_local,
                }
            # Reuse existing getArtistAlbums logic inline
            albums = []
            hubs = client.get_hubs(rating_key)
            for hub in hubs:
                hub_id = hub.get("hubIdentifier", "")
                if not (hub_id.startswith("artist.albums") or hub_id.startswith("hub.artist.albums")):
                    continue
                raw_title = hub.get("title", "")
                clean_title = re.sub(r'^\d+\s+', '', raw_title)
                if clean_title == "Album":
                    clean_title = "Albums"
                hub_albums = []
                for item in hub.get("Metadata", []):
                    album = parse_album(item)
                    if album.thumb_path and poster_cache:
                        cached_path = poster_cache._cache_path(album.thumb_path)
                        if cached_path.exists():
                            album.poster_local = cached_path.as_uri()
                    hub_albums.append({
                        "type": "album",
                        "ratingKey": album.rating_key,
                        "title": album.title,
                        "year": album.year,
                        "leafCount": album.leaf_count,
                        "posterLocal": album.poster_local,
                        "thumbPath": album.thumb_path,
                    })
                hub_albums.sort(key=lambda a: a["year"] or 0, reverse=True)
                albums.append({"type": "header", "title": clean_title})
                albums.extend(hub_albums)
            self._artistDetailReady.emit(rating_key, {"artist": artist_dict, "albums": albums})

            # Download uncached posters in parallel and re-emit progressively
            download_tasks: list[tuple[dict, str]] = []

            if data and artist_dict.get("posterLocal", "") == "" and poster_cache:
                artist = parse_artist(data)
                if artist.thumb_path:
                    download_tasks.append((artist_dict, artist.thumb_path))

            for album_entry in albums:
                if album_entry.get("type") != "album":
                    continue
                if album_entry.get("posterLocal", ""):
                    continue
                thumb_path = album_entry.get("thumbPath", "")
                if thumb_path:
                    download_tasks.append((album_entry, thumb_path))

            if download_tasks and poster_cache:
                future_to_entry: dict[Future, tuple[str, str]] = {}
                for entry_dict, thumb_path in download_tasks:
                    entry_rk = entry_dict.get("ratingKey", "")
                    future = self._poster_executor.submit(
                        poster_cache.get_poster, client, thumb_path
                    )
                    future_to_entry[future] = (entry_rk, thumb_path)

                for future in as_completed(future_to_entry):
                    entry_rk, _thumb = future_to_entry[future]
                    try:
                        local_url = future.result()
                        if local_url and entry_rk:
                            self.posterUpdated.emit(entry_rk, local_url)
                    except Exception:
                        pass  # Download failed — poster stays as placeholder

        self._executor.submit(_worker)

    @Slot(str)
    def fetchAlbumDetail(self, rating_key: str) -> None:
        """Async: fetch album metadata + tracks. Emits albumDetailReady."""
        if self._client is None:
            return
        client = self._client
        poster_cache = self._poster_cache
        def _worker():
            album_dict = {}
            thumb_path = ""
            data = client.get_metadata(rating_key)
            if data:
                album = parse_album(data)
                thumb_path = album.thumb_path
                if album.thumb_path and poster_cache:
                    cached_path = poster_cache._cache_path(album.thumb_path)
                    if cached_path.exists():
                        album.poster_local = cached_path.as_uri()
                album_dict = {
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
            tracks = []
            children = client.get_children(rating_key)
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
            self._albumDetailReady.emit(rating_key, {"album": album_dict, "tracks": tracks})

            # Download uncached album poster via lightweight signal
            if album_dict.get("posterLocal", "") == "" and thumb_path and poster_cache:
                local_url = poster_cache.get_poster(client, thumb_path)
                if local_url:
                    self.posterUpdated.emit(rating_key, local_url)

        self._executor.submit(_worker)

    @Slot(str)
    def fetchRecentAlbums(self, section_key: str) -> None:
        """Async: fetch recently added albums. Emits recentAlbumsReady."""
        if self._client is None:
            return
        client = self._client
        poster_cache = self._poster_cache
        def _worker():
            data = client._get(f"/library/sections/{section_key}/recentlyAdded")
            result = []
            if data:
                for item in data.get("MediaContainer", {}).get("Metadata", []):
                    if item.get("type") != "album":
                        continue
                    album = parse_album(item)
                    if album.thumb_path and poster_cache:
                        cached_path = poster_cache._cache_path(album.thumb_path)
                        if cached_path.exists():
                            album.poster_local = cached_path.as_uri()
                    result.append({
                        "ratingKey": album.rating_key,
                        "title": album.title,
                        "year": album.year,
                        "parentTitle": album.parent_title,
                        "posterLocal": album.poster_local,
                        "thumbPath": album.thumb_path,
                    })
            self._recentAlbumsReady.emit(result)

            # Download uncached posters in parallel and re-emit progressively
            download_tasks: list[tuple[dict, str]] = []
            for entry in result:
                if entry.get("posterLocal", ""):
                    continue
                thumb_path = entry.get("thumbPath", "")
                if thumb_path:
                    download_tasks.append((entry, thumb_path))

            if download_tasks and poster_cache:
                future_to_entry: dict[Future, tuple[str, str]] = {}
                for entry_dict, thumb_path in download_tasks:
                    entry_rk = entry_dict.get("ratingKey", "")
                    future = self._poster_executor.submit(
                        poster_cache.get_poster, client, thumb_path
                    )
                    future_to_entry[future] = (entry_rk, thumb_path)

                for future in as_completed(future_to_entry):
                    entry_rk, _thumb = future_to_entry[future]
                    try:
                        local_url = future.result()
                        if local_url and entry_rk:
                            self.posterUpdated.emit(entry_rk, local_url)
                    except Exception:
                        pass  # Download failed — poster stays as placeholder

        self._executor.submit(_worker)

    @Slot()
    def fetchPlaylists(self) -> None:
        """Async: fetch audio playlists. Emits playlistsReady."""
        if self._client is None:
            return
        client = self._client
        def _worker():
            # Reuse existing getPlaylists logic
            raw = client.get_playlists()
            result = []
            for p in raw:
                if p.get("playlistType") != "audio":
                    continue
                leaf_count = int(p.get("leafCount", 0) or 0)
                if leaf_count > PlexLibrary._MAX_PLAYLIST_TRACKS:
                    continue
                rk = str(p.get("ratingKey", ""))
                if p.get("smart") and rk:
                    probe = client.get_playlist_items(rk, limit=1)
                    if not probe:
                        continue
                result.append({
                    "ratingKey": rk,
                    "title": PlexLibrary._replace_emoji(p.get("title", "")),
                    "leafCount": leaf_count,
                    "duration": int(p.get("duration", 0) or 0),
                    "smart": bool(p.get("smart", False)),
                })
            self._playlistsReady.emit(result)
        self._executor.submit(_worker)

    @Slot(str)
    def fetchPlaylistTracks(self, rating_key: str) -> None:
        """Async: fetch tracks for a playlist. Emits playlistTracksReady."""
        if self._client is None:
            return
        client = self._client
        def _worker():
            raw = client.get_playlist_items(rating_key)
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
            self._playlistTracksReady.emit(rating_key, result)
        self._executor.submit(_worker)

    @Slot(str, result=str)
    def getTrackStreamUrl(self, media_key: str) -> str:
        """Return the authenticated stream URL for a track media part.

        Returns {server_url}{media_key}?X-Plex-Token={token}.
        This URL can be used directly as a MediaPlayer source in QML.
        """
        if self._client is None:
            return ""
        return self._client.get_authenticated_url(media_key)

    @Slot(str, str, str, str, int)
    def getLyrics(
        self,
        rating_key: str,
        track_title: str,
        artist_name: str,
        album_name: str,
        duration_ms: int,
    ) -> None:
        """Fetch lyrics for a track from LRCLIB asynchronously.

        Emits lyricsReady(rating_key, lines) on success, or
        lyricsUnavailable(rating_key) when no lyrics are found or an error occurs.

        QML usage:
            plex.getLyrics(track.ratingKey, track.title,
                           track.grandparentTitle, track.parentTitle, track.durationMs)
        """
        if duration_ms == 0:
            logger.debug("getLyrics: skipping zero-duration track %s", rating_key)
            self.lyricsUnavailable.emit(rating_key)
            return
        self._executor.submit(
            self._worker_fetch_lyrics,
            rating_key,
            track_title,
            artist_name,
            album_name,
            duration_ms,
        )

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
    # My List slots
    # ------------------------------------------------------------------

    @Slot(str, str, str, str, str)
    def toggleMyList(
        self,
        rating_key: str,
        title: str,
        type_: str,
        poster_local: str,
        grandparent_title: str,
    ) -> None:
        """Toggle an item in My List. Emits myListChanged(True) when added, (False) when removed."""
        items = self._load_my_list()
        existing = next((i for i, x in enumerate(items) if x["ratingKey"] == rating_key), -1)
        if existing >= 0:
            items.pop(existing)
            added = False
        else:
            items.append({
                "ratingKey": rating_key,
                "title": title,
                "type": type_,
                "posterLocal": poster_local,
                "grandparentTitle": grandparent_title,
            })
            added = True
        self._save_my_list(items)
        self._rebuild_my_list_model(items)
        self.myListChanged.emit(added)

    @Slot(str, result=bool)
    def isInMyList(self, rating_key: str) -> bool:
        """Return True if the item with the given rating_key is in My List."""
        return any(x["ratingKey"] == rating_key for x in self._load_my_list())

    @Slot(str, result=str)
    def getMyListItemType(self, rating_key: str) -> str:
        """Return the type ('movie', 'show', 'episode') of a My List item, or '' if not found."""
        items = self._load_my_list()
        for item in items:
            if item.get("ratingKey") == rating_key:
                return item.get("type", "")
        return ""

    # ------------------------------------------------------------------
    # Internal: error callback (called on worker thread)
    # ------------------------------------------------------------------

    def _on_plex_error(self, error_type) -> None:
        """Called on worker thread when a Plex API request fails."""
        # Use invokeMethod to ensure delivery on the main thread
        QMetaObject.invokeMethod(
            self,
            "_emit_plex_error",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, error_type.value),
        )
        if error_type == PlexErrorType.NETWORK and self._client is not None:
            if self._client.try_next_connection():
                logger.info("PlexLibrary: reconnected to server via fallback URL")

    @Slot(str)
    def _emit_plex_error(self, error_type: str) -> None:
        self.plexError.emit(error_type)

    # ------------------------------------------------------------------
    # Internal: worker thread functions
    # ------------------------------------------------------------------

    def _worker_refresh(self, client: PlexClient) -> None:
        """Worker: check availability, fetch libraries and on-deck."""
        # Emit cached data immediately so the UI is never blank during a slow
        # or failed network call. onLibrariesModelChanged will clear _refreshing.
        cached_libraries = self._load_libraries_cache()
        if cached_libraries:
            self._librariesReady.emit(cached_libraries, True)
        cached_ondeck = self._load_ondeck_cache()
        if cached_ondeck:
            self._onDeckCacheReady.emit(cached_ondeck)

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
                self._librariesReady.emit(libraries, False)
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

    def _worker_load_all_caches(self) -> None:
        """Worker: read only the libraries and on-deck caches from disk.

        Runs on _cache_executor thread. No network I/O — disk reads only.
        Movies and shows are loaded lazily in _worker_load_section when the
        user enters a specific library.
        """
        # Restore sort/genre state first so lazy fetches use the correct sort.
        state = self._load_state_cache()
        section_sort = state.get("section_sort", {})
        section_genre = state.get("section_genre", {})
        if section_sort:
            self._section_sort.update(section_sort)
        if section_genre:
            self._section_genre.update(section_genre)

        libraries = self._load_libraries_cache()
        if libraries:
            self._librariesReady.emit(libraries, True)

        ondeck = self._load_ondeck_cache()
        if ondeck:
            self._onDeckCacheReady.emit(ondeck)

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
            self.sectionLoadFailed.emit()
            return

        # get_library_items returns ([], 0) on soft failure (e.g. network error
        # after retries exhausted). Don't overwrite cached data with nothing.
        if not items and total == 0:
            self.sectionLoadFailed.emit()
            return

        if section_type == "movie":
            movies = [parse_movie(item) for item in items]
            if self._poster_cache is not None:
                for movie in movies:
                    if movie.thumb_path:
                        cached_path = self._poster_cache._cache_path(movie.thumb_path)
                        if cached_path.exists():
                            movie.poster_local = cached_path.as_uri()
            self._moviesReady.emit(movies, total)
        elif section_type == "show":
            shows = [parse_show(item) for item in items]
            if self._poster_cache is not None:
                for show in shows:
                    if show.thumb_path:
                        cached_path = self._poster_cache._cache_path(show.thumb_path)
                        if cached_path.exists():
                            show.poster_local = cached_path.as_uri()
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
            if not items and total == 0:
                self._loading_more = False
                self.sectionLoadFailed.emit()
                return
            movies = [parse_movie(item) for item in items]
            if self._poster_cache is not None:
                for movie in movies:
                    if movie.thumb_path:
                        cached_path = self._poster_cache._cache_path(movie.thumb_path)
                        if cached_path.exists():
                            movie.poster_local = cached_path.as_uri()
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
            if not items and total == 0:
                self._shows_loading_more = False
                self.sectionLoadFailed.emit()
                return
            shows = [parse_show(item) for item in items]
            if self._poster_cache is not None:
                for show in shows:
                    if show.thumb_path:
                        cached_path = self._poster_cache._cache_path(show.thumb_path)
                        if cached_path.exists():
                            show.poster_local = cached_path.as_uri()
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

    _LRCLIB_URL = "https://lrclib.net/api/get"
    _LRCLIB_USER_AGENT = "htpcstation/1.0 (https://github.com/tranxuanthang/lrcget)"

    def _worker_fetch_lyrics(
        self,
        rating_key: str,
        track_title: str,
        artist_name: str,
        album_name: str,
        duration_ms: int,
    ) -> None:
        """Worker: fetch lyrics from LRCLIB and emit the appropriate signal."""
        params = {
            "track_name": track_title,
            "artist_name": artist_name,
            "album_name": album_name,
            "duration": round(duration_ms / 1000),
        }
        headers = {"User-Agent": self._LRCLIB_USER_AGENT}
        try:
            response = requests.get(
                self._LRCLIB_URL,
                params=params,
                headers=headers,
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("getLyrics: network error for %s: %s", rating_key, exc)
            self._lyricsUnavailable.emit(rating_key)
            return

        if response.status_code == 404:
            self._lyricsUnavailable.emit(rating_key)
            return

        if response.status_code != 200:
            logger.warning(
                "getLyrics: unexpected HTTP %d for %s", response.status_code, rating_key
            )
            self._lyricsUnavailable.emit(rating_key)
            return

        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("getLyrics: failed to parse JSON for %s: %s", rating_key, exc)
            self._lyricsUnavailable.emit(rating_key)
            return

        if data.get("instrumental") is True:
            self._lyricsUnavailable.emit(rating_key)
            return

        synced = data.get("syncedLyrics") or ""
        if synced:
            lines = parse_lrc(synced)
            self._lyricsReady.emit(rating_key, lines)
            return

        plain = data.get("plainLyrics") or ""
        if plain:
            lines = parse_plain(plain)
            self._lyricsReady.emit(rating_key, lines)
            return

        self._lyricsUnavailable.emit(rating_key)

    # ------------------------------------------------------------------
    # Internal: main-thread result handlers
    # ------------------------------------------------------------------

    def _on_availability_ready(self, is_available: bool) -> None:
        self._available = is_available
        self.availableChanged.emit()

    def _on_machine_identifier_ready(self, machine_id: str) -> None:
        self._machine_identifier = machine_id
        logger.debug("PlexLibrary: cached machineIdentifier=%s", machine_id)

    def _on_libraries_ready(self, libraries: list, from_cache: bool = False) -> None:
        self._libraries_model.set_items(libraries)
        self.librariesModelChanged.emit()
        if not from_cache:
            self._save_libraries_cache(libraries)

    def _on_movies_ready(self, movies: list, total: int) -> None:
        self._loading_more = False
        if self._movies_loaded == 0:
            # First page — only replace if the model doesn't already have more
            # data (e.g. from cache). Avoids replacing a 500-item cached model
            # with a 50-item first page, which causes scroll/focus jumps.
            if len(movies) >= len(self._movies_model._movies):
                self._movies_model.set_movies(movies)
                self.moviesModelChanged.emit()
            self._save_state_cache("last_movie_section", self._current_section_key)
        else:
            # Subsequent pages — append
            self._movies_model.append_movies(movies)

        # Save every page — merge-by-key preserves existing entries.
        # Snapshot to dicts on main thread; disk I/O on _cache_executor.
        section_key = self._current_section_key
        movie_dicts = [self._movie_to_dict(m) for m in movies]
        self._cache_executor.submit(
            self._merge_and_write_movies_cache, section_key, movie_dicts
        )

        self._movies_total = total
        self._movies_loaded += len(movies)

        # Kick off poster downloads only for items not already cached
        client = self._client
        if client is not None:
            start_row = self._movies_loaded - len(movies)
            for i, movie in enumerate(movies):
                if movie.thumb_path and not movie.poster_local:
                    row = start_row + i
                    self._poster_executor.submit(
                        self._worker_fetch_poster, client, movie.thumb_path, "movie", row
                    )

    def _on_shows_ready(self, shows: list, total: int) -> None:
        self._shows_loading_more = False
        if self._shows_loaded == 0:
            # First page — only replace if the model doesn't already have more
            # data (e.g. from cache).
            if len(shows) >= len(self._shows_model._shows):
                self._shows_model.set_shows(shows)
                self.showsModelChanged.emit()
            self._save_state_cache("last_show_section", self._current_section_key)
        else:
            # Subsequent pages — append
            self._shows_model.append_shows(shows)

        # Save every page — merge-by-key preserves existing entries.
        # Snapshot to dicts on main thread; disk I/O on _cache_executor.
        section_key = self._current_section_key
        show_dicts = [self._show_to_dict(s) for s in shows]
        self._cache_executor.submit(
            self._merge_and_write_shows_cache, section_key, show_dicts
        )

        self._shows_total = total
        self._shows_loaded += len(shows)

        # Kick off poster downloads only for items not already cached
        client = self._client
        if client is not None:
            start_row = self._shows_loaded - len(shows)
            for i, show in enumerate(shows):
                if show.thumb_path and not show.poster_local:
                    row = start_row + i
                    self._poster_executor.submit(
                        self._worker_fetch_poster, client, show.thumb_path, "show", row
                    )

    def _on_artist_preview_ready(self, rating_key: str, data: object) -> None:
        self.artistPreviewReady.emit(rating_key, data)

    def _on_artist_detail_ready(self, rating_key: str, data: object) -> None:
        self.artistDetailReady.emit(rating_key, data)

    def _on_album_detail_ready(self, rating_key: str, data: object) -> None:
        self.albumDetailReady.emit(rating_key, data)

    def _on_recent_albums_ready(self, data: object) -> None:
        self.recentAlbumsReady.emit(data)

    def _on_playlists_ready(self, data: object) -> None:
        self.playlistsReady.emit(data)

    def _on_playlist_tracks_ready(self, rating_key: str, data: object) -> None:
        self.playlistTracksReady.emit(rating_key, data)

    def _on_artists_ready(self, artists: list, total: int) -> None:
        # Only replace if incoming data is at least as large as current model
        # (avoids replacing cached model with smaller network response).
        if len(artists) >= len(self._artists_model._artists):
            self._artists_model.set_artists(artists)
            self.artistsModelChanged.emit()

        # Save every page — merge-by-key preserves existing entries.
        # Snapshot to dicts on main thread; disk I/O on _cache_executor.
        artist_dicts = [self._artist_to_dict(a) for a in artists]
        self._cache_executor.submit(
            self._merge_and_write_artists_cache, artist_dicts
        )

        # Kick off poster downloads only for artists missing a local poster
        client = self._client
        if client is not None:
            for i, artist in enumerate(artists):
                if artist.thumb_path and not artist.poster_local:
                    self._poster_executor.submit(
                        self._worker_fetch_poster, client, artist.thumb_path, "artist", i
                    )

    def _on_on_deck_ready(self, raw_items: list) -> None:
        items = []
        for item in raw_items:
            item_type = item.get("type", "")
            thumb_path = item.get("thumb", "")
            # Pre-resolve cached poster
            poster_local = ""
            if thumb_path and self._poster_cache is not None:
                cached_path = self._poster_cache._cache_path(thumb_path)
                if cached_path.exists():
                    poster_local = cached_path.as_uri()
            items.append({
                "rating_key": str(item.get("ratingKey", "")),
                "title": item.get("title", ""),
                "type": item_type,
                "poster_local": poster_local,
                "grandparent_title": item.get("grandparentTitle", ""),
                "view_offset": int(item.get("viewOffset", 0) or 0),
                "duration": int(item.get("duration", 0) or 0),
                "thumb_path": thumb_path,
            })
        self._on_deck_model.set_items(items)
        self.onDeckModelChanged.emit()

        # Save processed items to disk cache for instant load on next launch
        self._save_ondeck_cache(items)

        # Download only missing posters
        client = self._client
        if client is not None:
            for i, item in enumerate(items):
                if item.get("thumb_path") and not item.get("poster_local"):
                    self._poster_executor.submit(
                        self._worker_fetch_poster, client, item["thumb_path"], "ondeck", i
                    )

    def _on_on_deck_cache_ready(self, items: list) -> None:
        """Main thread: populate on-deck model from disk cache."""
        self._on_deck_model.set_items(items)
        self.onDeckModelChanged.emit()

    def _on_movies_cache_ready(self, movies: list, section_key: str) -> None:
        """Main thread: populate movies model from disk cache."""
        self._movies_model.set_movies(movies)
        self._current_section_key  = section_key
        self._current_section_type = "movie"
        self.moviesModelChanged.emit()

    def _on_shows_cache_ready(self, shows: list, section_key: str) -> None:
        """Main thread: populate shows model from disk cache."""
        self._shows_model.set_shows(shows)
        if self._current_section_type != "movie":
            self._current_section_key  = section_key
            self._current_section_type = "show"
        self.showsModelChanged.emit()

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

    def _resolve_cached_posters(self, items: list) -> None:
        """Pre-resolve poster_local from disk cache for items missing it.

        Called on the main thread after loading items from cache. The SHA256
        hash + path construct and exists() checks are ~5ms for 500 items —
        acceptable for instant cache-first display.
        """
        if self._poster_cache is None:
            return
        for item in items:
            thumb = getattr(item, "thumb_path", "") or ""
            if thumb and not getattr(item, "poster_local", ""):
                cached_path = self._poster_cache._cache_path(thumb)
                if cached_path.exists():
                    item.poster_local = cached_path.as_uri()

    def _state_cache_path(self) -> Path:
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _PLEX_CACHE_DIR / "state.json"

    def _save_state_cache(self, key: str, value: str) -> None:
        """Update one key in state.json (worker thread safe — atomic read-modify-write)."""
        path = self._state_cache_path()
        try:
            state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            state = {}
        state[key] = value
        path.write_text(json.dumps(state), encoding="utf-8")

    def _save_sort_state(self) -> None:
        """Persist _section_sort and _section_genre to state.json."""
        path = self._state_cache_path()
        try:
            state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            state = {}
        state["section_sort"] = self._section_sort
        state["section_genre"] = self._section_genre
        path.write_text(json.dumps(state), encoding="utf-8")

    def _load_state_cache(self) -> dict:
        path = self._state_cache_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _migrate_cache_dirs(self) -> None:
        """One-time migration: move old cache files to new plex_cache/ layout."""
        import shutil

        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # poster_cache/ → plex_cache/posters/
        old_poster_dir = CONFIG_DIR / "poster_cache"
        new_poster_dir = _PLEX_CACHE_DIR / "posters"
        if old_poster_dir.exists() and not new_poster_dir.exists():
            shutil.move(str(old_poster_dir), str(new_poster_dir))
        elif old_poster_dir.exists() and new_poster_dir.exists():
            # Both exist — move individual files, skip conflicts
            for f in old_poster_dir.iterdir():
                dest = new_poster_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
            try:
                old_poster_dir.rmdir()  # remove if now empty
            except OSError:
                pass

        # plex_mylist.json → plex_cache/plex_mylist.json
        old_mylist = CONFIG_DIR / "plex_mylist.json"
        new_mylist = _PLEX_CACHE_DIR / "plex_mylist.json"
        if old_mylist.exists() and not new_mylist.exists():
            shutil.move(str(old_mylist), str(new_mylist))

        # livetv_cache/ → plex_cache/guide/
        old_guide_dir = CONFIG_DIR / "livetv_cache"
        new_guide_dir = _PLEX_CACHE_DIR / "guide"
        if old_guide_dir.exists() and not new_guide_dir.exists():
            shutil.move(str(old_guide_dir), str(new_guide_dir))
        elif old_guide_dir.exists() and new_guide_dir.exists():
            for f in old_guide_dir.iterdir():
                dest = new_guide_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
            try:
                old_guide_dir.rmdir()
            except OSError:
                pass

    def _load_my_list(self) -> list[dict]:
        """Load My List items from the JSON persistence file."""
        path = _PLEX_CACHE_DIR / "plex_mylist.json"
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_my_list(self, items: list[dict]) -> None:
        """Persist My List items to the JSON file."""
        path = _PLEX_CACHE_DIR / "plex_mylist.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(items, f, indent=2)
        except OSError as exc:
            logger.warning("_save_my_list: could not write %s: %s", path, exc)

    def _rebuild_my_list_model(self, items: list[dict]) -> None:
        """Convert the JSON list to the PlexOnDeckModel item shape and update the model."""
        model_items = [
            {
                "rating_key": item["ratingKey"],
                "title": item["title"],
                "type": item["type"],
                "poster_local": item.get("posterLocal", ""),
                "grandparent_title": item.get("grandparentTitle", ""),
                "view_offset": 0,
                "duration": 0,
            }
            for item in items
        ]
        self._my_list_model.set_items(model_items)

    def _artists_cache_path(self) -> Path:
        """Return the path to the artist list cache file, scoped by section key."""
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        section_key = self._current_section_key or "default"
        return _PLEX_CACHE_DIR / f"artists_cache_{section_key}.json"

    def _artist_to_dict(self, a) -> dict:
        """Snapshot a PlexArtist to a plain dict (no I/O, safe on main thread)."""
        return {
            "rating_key": a.rating_key,
            "title": a.title,
            "summary": a.summary,
            "thumb_path": a.thumb_path,
            "genre": a.genre,
            "poster_local": a.poster_local,
        }

    def _merge_and_write_artists_cache(self, artist_dicts: list) -> None:
        """Merge artist dicts into existing cache and write (runs on _cache_executor)."""
        try:
            path = self._artists_cache_path()
            existing = {}
            if path.exists():
                try:
                    for item in json.loads(path.read_text(encoding="utf-8")):
                        rk = item.get("rating_key", "")
                        if rk:
                            existing[rk] = item
                except Exception:
                    pass  # Corrupt cache — start fresh

            for d in artist_dicts:
                rk = d.get("rating_key", "")
                if rk:
                    existing[rk] = d

            path.write_text(json.dumps(list(existing.values())), encoding="utf-8")
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

    # ------------------------------------------------------------------
    # Disk cache helpers — libraries
    # ------------------------------------------------------------------

    def _libraries_cache_path(self) -> Path:
        """Return the path to the library list cache file."""
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _PLEX_CACHE_DIR / "libraries_cache.json"

    def _save_libraries_cache(self, libraries: list) -> None:
        """Serialize the library list to a JSON cache file (called from worker thread)."""
        try:
            path = self._libraries_cache_path()
            path.write_text(json.dumps(libraries), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save libraries cache", exc_info=True)

    def _load_libraries_cache(self) -> list | None:
        """Load the library list from the JSON cache file (called from worker thread).

        Returns a list of library dicts, or None if the cache is missing or corrupt.
        """
        path = self._libraries_cache_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to load libraries cache", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Disk cache helpers — on-deck
    # ------------------------------------------------------------------

    def _ondeck_cache_path(self) -> Path:
        """Return the path to the on-deck cache file."""
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _PLEX_CACHE_DIR / "ondeck_cache.json"

    def _save_ondeck_cache(self, items: list) -> None:
        """Serialize the processed on-deck items to a JSON cache file.

        Items must already be in the processed dict format (not raw API dicts).
        Called from the main thread (inside _on_on_deck_ready).
        """
        try:
            path = self._ondeck_cache_path()
            path.write_text(json.dumps(items), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save on-deck cache", exc_info=True)

    def _load_ondeck_cache(self) -> list | None:
        """Load the processed on-deck items from the JSON cache file (called from worker thread).

        Returns a list of processed item dicts, or None if the cache is missing or corrupt.
        """
        path = self._ondeck_cache_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to load on-deck cache", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Disk cache helpers — movies
    # ------------------------------------------------------------------

    def _movies_cache_path(self, section_key: str) -> Path:
        """Return the path to the movies cache file for the given section key."""
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _PLEX_CACHE_DIR / f"movies_cache_{section_key}.json"

    def _movie_to_dict(self, m) -> dict:
        """Snapshot a PlexMovie to a plain dict (no I/O, safe on main thread)."""
        return {
            "rating_key": m.rating_key,
            "title": m.title,
            "year": m.year,
            "summary": m.summary,
            "content_rating": m.content_rating,
            "audience_rating": m.audience_rating,
            "duration_ms": m.duration_ms,
            "studio": m.studio,
            "tagline": m.tagline,
            "thumb_path": m.thumb_path,
            "art_path": m.art_path,
            "genres": m.genres,
            "directors": m.directors,
            "cast": m.cast,
            "added_at": m.added_at,
            "view_offset": m.view_offset,
            "poster_local": m.poster_local,
        }

    def _merge_and_write_movies_cache(self, section_key: str, movie_dicts: list) -> None:
        """Merge movie dicts into existing cache and write (runs on _cache_executor)."""
        try:
            path = self._movies_cache_path(section_key)
            existing = {}
            if path.exists():
                try:
                    for item in json.loads(path.read_text(encoding="utf-8")):
                        rk = item.get("rating_key", "")
                        if rk:
                            existing[rk] = item
                except Exception:
                    pass  # Corrupt cache — start fresh

            for d in movie_dicts:
                rk = d.get("rating_key", "")
                if rk:
                    existing[rk] = d

            path.write_text(json.dumps(list(existing.values())), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save movies cache", exc_info=True)

    def _load_movies_cache(self, section_key: str) -> list | None:
        """Load the movie list from the JSON cache file (called from worker thread).

        Returns a list of PlexMovie objects, or None if the cache is missing or corrupt.
        """
        path = self._movies_cache_path(section_key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            movies = []
            for item in data:
                movies.append(PlexMovie(
                    rating_key=item.get("rating_key", ""),
                    title=item.get("title", ""),
                    year=item.get("year", 0),
                    summary=item.get("summary", ""),
                    content_rating=item.get("content_rating", ""),
                    audience_rating=item.get("audience_rating", 0.0),
                    duration_ms=item.get("duration_ms", 0),
                    studio=item.get("studio", ""),
                    tagline=item.get("tagline", ""),
                    thumb_path=item.get("thumb_path", ""),
                    art_path=item.get("art_path", ""),
                    genres=item.get("genres", []),
                    directors=item.get("directors", []),
                    cast=item.get("cast", []),
                    added_at=item.get("added_at", 0),
                    view_offset=item.get("view_offset", 0),
                    poster_local=item.get("poster_local", ""),
                ))
            return movies
        except Exception:
            logger.warning("Failed to load movies cache", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Disk cache helpers — shows
    # ------------------------------------------------------------------

    def _shows_cache_path(self, section_key: str) -> Path:
        """Return the path to the shows cache file for the given section key."""
        _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _PLEX_CACHE_DIR / f"shows_cache_{section_key}.json"

    def _show_to_dict(self, s) -> dict:
        """Snapshot a PlexShow to a plain dict (no I/O, safe on main thread)."""
        return {
            "rating_key": s.rating_key,
            "title": s.title,
            "year": s.year,
            "summary": s.summary,
            "content_rating": s.content_rating,
            "audience_rating": s.audience_rating,
            "thumb_path": s.thumb_path,
            "art_path": s.art_path,
            "genres": s.genres,
            "cast": s.cast,
            "child_count": s.child_count,
            "leaf_count": s.leaf_count,
            "viewed_leaf_count": s.viewed_leaf_count,
            "poster_local": s.poster_local,
        }

    def _merge_and_write_shows_cache(self, section_key: str, show_dicts: list) -> None:
        """Merge show dicts into existing cache and write (runs on _cache_executor)."""
        try:
            path = self._shows_cache_path(section_key)
            existing = {}
            if path.exists():
                try:
                    for item in json.loads(path.read_text(encoding="utf-8")):
                        rk = item.get("rating_key", "")
                        if rk:
                            existing[rk] = item
                except Exception:
                    pass  # Corrupt cache — start fresh

            for d in show_dicts:
                rk = d.get("rating_key", "")
                if rk:
                    existing[rk] = d

            path.write_text(json.dumps(list(existing.values())), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save shows cache", exc_info=True)

    def _load_shows_cache(self, section_key: str) -> list | None:
        """Load the show list from the JSON cache file (called from worker thread).

        Returns a list of PlexShow objects, or None if the cache is missing or corrupt.
        """
        path = self._shows_cache_path(section_key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            shows = []
            for item in data:
                shows.append(PlexShow(
                    rating_key=item.get("rating_key", ""),
                    title=item.get("title", ""),
                    year=item.get("year", 0),
                    summary=item.get("summary", ""),
                    content_rating=item.get("content_rating", ""),
                    audience_rating=item.get("audience_rating", 0.0),
                    thumb_path=item.get("thumb_path", ""),
                    art_path=item.get("art_path", ""),
                    genres=item.get("genres", []),
                    cast=item.get("cast", []),
                    child_count=item.get("child_count", 0),
                    leaf_count=item.get("leaf_count", 0),
                    viewed_leaf_count=item.get("viewed_leaf_count", 0),
                    poster_local=item.get("poster_local", ""),
                ))
            return shows
        except Exception:
            logger.warning("Failed to load shows cache", exc_info=True)
            return None

    def _resolve_server_url(self, account: PlexAccount) -> tuple[Optional[str], list[str]]:
        """Resolve the server URL from plex.tv resources API.

        Finds the server matching config.plex_server_id and picks the best
        connection URL using the priority: local > non-relay > relay, with
        HTTPS preferred within each tier.

        Returns (best_uri, all_uris) where best_uri is the chosen URL string
        (or None if not found) and all_uris is the prioritised list of all
        connection URIs.

        Safe to call from any thread — does not write to shared state.
        """
        server_id = self._config.plex_server_id
        if not server_id:
            return None, []

        resources = account.get_resources()
        server = next(
            (r for r in resources if r.get("clientIdentifier") == server_id),
            None,
        )
        if server is None:
            logger.warning(
                "PlexLibrary: server %s not found in resources", server_id
            )
            return None, []

        connections = server.get("connections", [])
        if not connections:
            logger.warning("PlexLibrary: server %s has no connections", server_id)
            return None, []

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
        all_urls = [c.get("uri", "") for c in sorted_conns if c.get("uri")]
        best = sorted_conns[0]
        uri = best.get("uri", "")
        logger.info("PlexLibrary: resolved server URL: %s (%d connections available)",
                    uri, len(all_urls))
        return (uri or None), all_urls

    def _probe_server_url(self, url: str, timeout: float = 3.0) -> bool:
        """Quick probe: is the server reachable at this URL?

        Uses a lightweight GET /identity with a short timeout.
        Returns True if the server responds with status < 400.
        """
        try:
            response = requests.get(f"{url}/identity", timeout=timeout)
            return response.status_code < 400
        except Exception:
            return False

    def _worker_setup(self, refresh_after: bool = False) -> None:
        """Worker thread: resolve server, probe, switch user. Emits _setupReady.

        All network I/O happens here. Does NOT write to any shared instance
        state — results are marshalled to the main thread via _setupReady.

        Args:
            refresh_after: if True, _on_setup_ready will also submit _worker_refresh
                to fetch library/on-deck data.  False for __init__ (setup only),
                True for explicit refresh() calls from QML.
        """
        token = self._config.plex_token
        server_id = self._config.plex_server_id

        if not server_id:
            self._setupReady.emit({
                "available": False,
                "account": PlexAccount(token) if token else None,
                "refresh_after": refresh_after,
            })
            return

        account = PlexAccount(token)
        server_url, all_urls = self._resolve_server_url(account)
        if server_url:
            # Cache the highest-priority (local) URL for offline startup.
            best_url = all_urls[0] if all_urls else server_url
            if best_url != self._config.plex_server_url:
                self._config.set_plex_server_url(best_url)

            # Probe the best URL; fall through to alternatives if unreachable
            if not self._probe_server_url(server_url):
                logger.info(
                    "PlexLibrary: primary URL %s unreachable, trying alternatives",
                    server_url,
                )
                for alt_url in all_urls:
                    if alt_url == server_url:
                        continue
                    if self._probe_server_url(alt_url):
                        logger.info("PlexLibrary: using alternative URL %s", alt_url)
                        server_url = alt_url
                        break
                else:
                    logger.warning("PlexLibrary: all server URLs unreachable")
        else:
            server_url = self._config.plex_server_url
            if server_url:
                logger.info(
                    "PlexLibrary: plex.tv unreachable, using cached server URL: %s", server_url
                )
                if not all_urls:
                    all_urls = [server_url]
            else:
                logger.info(
                    "PlexLibrary: could not resolve server URL and no cached URL available"
                )
                self._setupReady.emit({"available": False, "account": account, "refresh_after": refresh_after})
                return

        # If a user is selected, switch to get a user-specific token.
        # Read cached values — these are only written on the main thread in
        # _on_setup_ready, so reading them here is safe (stale-read at worst,
        # which just means an extra switch_user call).
        user_token = token
        user_id = self._config.plex_user_id
        user_title = ""
        content_rating_filter = ""
        cached_user_id = self._cached_user_id
        cached_user_token = self._cached_user_token
        cached_content_rating_filter = self._cached_content_rating_filter
        if user_id:
            if cached_user_id == user_id and cached_user_token:
                user_token = cached_user_token
                content_rating_filter = cached_content_rating_filter
                user_title = self._cached_user_title
                logger.debug("PlexLibrary: reusing cached token for user %s", user_id)
            else:
                switched_token = account.switch_user(user_id)
                if switched_token:
                    user_token = switched_token
                    home_users = account.get_home_users()
                    matched = next(
                        (u for u in home_users if u.get("id") == user_id), None
                    )
                    user_title = matched.get("title", "") if matched else ""
                    restriction = matched.get("restrictionProfile", "") if matched else ""
                    content_rating_filter = _RESTRICTION_RATINGS.get(restriction, "")
                    logger.info("PlexLibrary: switched to user %s", user_id)
                else:
                    logger.warning(
                        "PlexLibrary: failed to switch to user %s, using admin token", user_id
                    )

        self._setupReady.emit({
            "available": True,
            "server_url": server_url,
            "all_urls": all_urls,
            "account": account,
            "token": token,
            "user_token": user_token,
            "user_id": user_id,
            "user_title": user_title,
            "content_rating_filter": content_rating_filter,
            "refresh_after": refresh_after,
        })

    def _on_setup_ready(self, result: dict) -> None:
        """Main thread: apply setup results and start data refresh."""
        account = result.get("account")
        if account is not None:
            self._account = account

        if not result.get("available"):
            self._client = None
            self._server_url = ""
            self._on_availability_ready(False)
            return

        server_url = result["server_url"]
        all_urls = result["all_urls"]
        token = result["token"]
        user_token = result["user_token"]
        user_id = result.get("user_id")
        user_title = result.get("user_title", "")
        content_rating_filter = result.get("content_rating_filter", "")

        self._server_url = server_url
        self._all_server_urls = all_urls
        self._active_token = user_token
        self._content_rating_filter = content_rating_filter

        # Update user-switching cache
        if user_id and user_token != token:
            # A successful switch occurred (token changed)
            self._cached_user_id = user_id
            self._cached_user_token = user_token
            self._cached_user_title = user_title
            self._cached_content_rating_filter = content_rating_filter

        self._client = PlexClient(server_url, token, client_id=self._config.plex_client_id)
        self._client.set_error_callback(self._on_plex_error)
        fallbacks = [u for u in all_urls if u != server_url]
        self._client.set_fallback_urls(fallbacks)
        logger.info("PlexLibrary: client configured for %s", server_url)
        self._start_event_listener()

        # Submit data refresh only when requested (refresh() passes True,
        # __init__ passes False since QML triggers refresh explicitly).
        if result.get("refresh_after", True):
            self._executor.submit(self._worker_refresh, self._client)

    def _start_event_listener(self) -> None:
        """Start the SSE listener if a client is configured."""
        self._stop_event_listener()
        if self._client is None or not self._server_url:
            return
        from backend.plex_client import PlexEventListener
        self._event_listener = PlexEventListener(
            self._server_url,
            self._config.plex_token,
            self._on_library_event,
        )
        self._event_listener.start()

    def _stop_event_listener(self) -> None:
        if self._event_listener is not None:
            self._event_listener.stop()
            self._event_listener = None

    def _on_library_event(self) -> None:
        """Called from SSE thread when a library update event arrives."""
        logger.info("PlexLibrary: library event received — scheduling refresh")
        # Use executor so refresh() runs off the main thread (same as normal refresh).
        # Guard against RuntimeError if the executor is already shut down (app exit race).
        try:
            self._executor.submit(self._worker_refresh, self._client)
        except RuntimeError:
            pass

    def _ensure_account(self) -> PlexAccount | None:
        """Return a PlexAccount, creating one if needed.

        This allows getServerList/getHomeUsers to work even when _worker_setup
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
        self._stop_event_listener()
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
        # so the next _worker_setup() will re-switch and re-resolve the restriction profile
        self._cached_user_id = None
        self._cached_user_token = ""
        self._cached_user_title = ""
        self._cached_content_rating_filter = ""
        self._content_rating_filter = ""
        # Invalidate the current client
        self._stop_event_listener()
        self._client = None
        logger.info("PlexLibrary: user selection changed to %s", user_id)
