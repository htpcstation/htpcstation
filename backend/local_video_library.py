"""Local video library backend for HTPC Station.

Scans user-configured video categories, exposes data to QML via
QAbstractListModel subclasses, and launches playback via LibMpvPlayer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

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

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "htpcstation"
_LOCAL_VIDEOS_CACHE_DIR = _CONFIG_DIR / "local_videos_cache"

# Per-category cache dirs (movies and tv_shows are the two default categories)
_MOVIES_CACHE_DIR   = _LOCAL_VIDEOS_CACHE_DIR / "movies"
_TV_SHOWS_CACHE_DIR = _LOCAL_VIDEOS_CACHE_DIR / "tv_shows"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Return a stable, filesystem-safe slug for a category name."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


class LocalVideoCache:
    """Read/write cache for a single video category.

    Handles library.json I/O, posterPath resolution, and field-level
    custom overrides. Instantiated once per category.
    """

    def __init__(self, cache_dir: Path, has_scraped_art: bool = True) -> None:
        """
        cache_dir       — e.g. _MOVIES_CACHE_DIR or a custom-category path
        has_scraped_art — False for custom categories (no artwork_scraped dir)
        """
        self._cache_dir = cache_dir
        self._custom_art_dir = cache_dir / "artwork_custom"
        self._scraped_art_dir = cache_dir / "artwork_scraped" if has_scraped_art else None
        self._library_file = cache_dir / "library.json"
        self._data: dict[str, dict] = {}  # key → raw JSON entry

    def ensure_dirs(self) -> None:
        """Create cache_dir, artwork_custom/, and artwork_scraped/ (if applicable)."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._custom_art_dir.mkdir(parents=True, exist_ok=True)
        if self._scraped_art_dir is not None:
            self._scraped_art_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        """Read library.json into self._data. No-op if file absent."""
        if not self._library_file.exists():
            return
        try:
            text = self._library_file.read_text(encoding="utf-8")
            parsed = json.loads(text)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("LocalVideoCache: failed to load %s: %s", self._library_file, exc)
            self._data = {}
            return
        if not isinstance(parsed, dict):
            logger.warning(
                "LocalVideoCache: %s contains %s instead of a JSON object; ignoring",
                self._library_file,
                type(parsed).__name__,
            )
            self._data = {}
            return
        self._data = parsed

    def save(self) -> None:
        """Write self._data to library.json as indented JSON."""
        self.ensure_dirs()
        try:
            self._library_file.write_text(
                json.dumps(self._data, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("LocalVideoCache: failed to save %s: %s", self._library_file, exc)

    def get_entry(self, key: str) -> dict | None:
        """Return a shallow copy of the entry for key, or None if absent."""
        entry = self._data.get(key)
        return dict(entry) if entry is not None else None

    def set_entry(self, key: str, data: dict) -> None:
        """Merge data into the existing entry, preserving the custom sub-dict."""
        existing = self._data.get(key, {})
        custom = existing.get("custom", {})
        self._data[key] = {**existing, **data, "custom": custom}
        self.save()

    def resolve_poster(self, key: str) -> str:
        """Return the best available poster path for key.

        Priority: artwork_custom file → poster_scraped field in JSON → "".
        """
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = self._custom_art_dir / f"{key}{ext}"
            if candidate.exists():
                return str(candidate)

        entry = self._data.get(key, {})
        scraped = entry.get("poster_scraped", "")
        if scraped and Path(scraped).exists():
            return scraped

        return ""

    def resolve_metadata(self, key: str) -> dict:
        """Return effective metadata for key: base fields merged with custom overrides."""
        entry = self._data.get(key, {})
        custom = entry.get("custom", {})
        base = {
            "title":       entry.get("title", ""),
            "year":        entry.get("year", 0),
            "description": entry.get("description", ""),
            "genres":      entry.get("genres", []),
            "rating":      entry.get("rating", ""),
            "tmdb_id":     entry.get("tmdb_id"),
        }
        return {**base, **custom}

    def is_tombstoned(self, key: str) -> bool:
        """Return True if the entry has tmdb_id explicitly set to None (lookup miss)."""
        entry = self._data.get(key)
        return entry is not None and entry.get("tmdb_id") is None and "tmdb_id" in entry

    def write_tombstone(self, key: str) -> None:
        """Write {"tmdb_id": null} for key, preserving any existing custom data."""
        existing = self._data.get(key, {})
        self._data[key] = {**existing, "tmdb_id": None}
        self.save()


def _movies_cache() -> LocalVideoCache:
    return LocalVideoCache(_MOVIES_CACHE_DIR, has_scraped_art=True)


def _tv_shows_cache() -> LocalVideoCache:
    return LocalVideoCache(_TV_SHOWS_CACHE_DIR, has_scraped_art=True)


def _custom_category_cache(name: str) -> LocalVideoCache:
    cache_dir = _LOCAL_VIDEOS_CACHE_DIR / _slugify(name)
    return LocalVideoCache(cache_dir, has_scraped_art=False)


# ---------------------------------------------------------------------------
# TMDb scraper helpers
# ---------------------------------------------------------------------------

_MOVIE_YEAR_RE = re.compile(r'^(.+?)\s*\((\d{4})\)\s*$')


def _parse_movie_title(stem: str) -> tuple[str, int | None]:
    """Split 'The Matrix (1999)' → ('The Matrix', 1999). No match → (stem, None)."""
    m = _MOVIE_YEAR_RE.match(stem)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return stem, None


class TmdbScraper:
    """Fetches movie/TV show metadata and posters from The Movie Database (TMDb).

    Pure Python — no Qt imports. Blocking HTTP only. Threading is handled by
    the caller (LocalVideoLibrary in Task 004).
    """

    SEARCH_BASE = "https://api.themoviedb.org/3"
    IMAGE_BASE  = "https://image.tmdb.org/t/p/w500"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "htpcstation/1.0"})

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search_movie(self, title: str, year: int | None) -> dict | None:
        """Search TMDb for a movie. Returns the best matching result dict or None."""
        params: dict = {
            "api_key": self._api_key,
            "query": title,
            "language": "en-US",
            "include_adult": "false",
        }
        if year is not None:
            params["year"] = year

        try:
            resp = self._session.get(
                f"{self.SEARCH_BASE}/search/movie",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except requests.RequestException as exc:
            logger.warning("TmdbScraper.search_movie failed for %r: %s", title, exc)
            return None

        if not results:
            return None

        if year is not None:
            year_str = str(year)
            for r in results:
                if r.get("release_date", "").startswith(year_str):
                    return r

        return results[0]

    def search_tv_show(self, name: str) -> dict | None:
        """Search TMDb for a TV show. Returns results[0] or None."""
        params: dict = {
            "api_key": self._api_key,
            "query": name,
            "language": "en-US",
        }
        try:
            resp = self._session.get(
                f"{self.SEARCH_BASE}/search/tv",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except requests.RequestException as exc:
            logger.warning("TmdbScraper.search_tv_show failed for %r: %s", name, exc)
            return None

        if not results:
            return None
        return results[0]

    def download_poster(self, tmdb_poster_path: str, dest: Path) -> bool:
        """Download a TMDb poster image to dest. Returns True on success."""
        stripped = tmdb_poster_path.lstrip("/")
        url = f"{self.IMAGE_BASE}/{stripped}"
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        except (requests.RequestException, OSError) as exc:
            logger.warning("TmdbScraper.download_poster failed for %r: %s", tmdb_poster_path, exc)
            return False

    # ------------------------------------------------------------------
    # Bulk scrape methods
    # ------------------------------------------------------------------

    def scrape_movies(
        self,
        items: list,
        cache: LocalVideoCache,
        on_progress: Callable | None = None,
    ) -> None:
        """Scrape TMDb metadata for a list of VideoFile items."""
        logger.info("scrape_movies: %d items to process", len(items))
        total = len(items)
        for done, item in enumerate(items, start=1):
            key = Path(item.path).stem
            logger.debug("scrape_movies: processing key=%r", key)

            if cache.is_tombstoned(key):
                logger.debug("scrape_movies: skipping tombstoned key=%r", key)
                if on_progress is not None:
                    on_progress(done, total)
                continue

            existing = cache.get_entry(key)
            if existing is not None and existing.get("tmdb_id") is not None:
                logger.debug("scrape_movies: skipping already-scraped key=%r", key)
                if on_progress is not None:
                    on_progress(done, total)
                continue

            title, year = _parse_movie_title(key)
            result = self.search_movie(title, year)
            logger.debug("scrape_movies: search title=%r year=%s → %s", title, year, result.get("id") if result else "no result")

            if result is None:
                cache.write_tombstone(key)
                logger.info("scrape_movies: no TMDb result for key=%r, writing tombstone", key)
                if on_progress is not None:
                    on_progress(done, total)
                time.sleep(0.26)
                continue

            entry: dict = {
                "title":          result.get("title", key),
                "year":           int(result["release_date"][:4]) if result.get("release_date") else 0,
                "description":    result.get("overview", ""),
                "genres":         [],
                "rating":         "",
                "tmdb_id":        result["id"],
                "poster_scraped": "",
            }

            if result.get("poster_path"):
                dest = cache._scraped_art_dir / f"{key}.jpg"
                if self.download_poster(result["poster_path"], dest):
                    entry["poster_scraped"] = str(dest)

            cache.set_entry(key, entry)
            logger.info("scrape_movies: saved key=%r tmdb_id=%s poster=%s", key, entry["tmdb_id"], bool(entry["poster_scraped"]))

            if on_progress is not None:
                on_progress(done, total)

            time.sleep(0.26)

    def scrape_tv_shows(
        self,
        shows: list,
        cache: LocalVideoCache,
        on_progress: Callable | None = None,
    ) -> None:
        """Scrape TMDb metadata for a list of Show items."""
        logger.info("scrape_tv_shows: %d shows to process", len(shows))
        total = len(shows)
        for done, show in enumerate(shows, start=1):
            key = show.name
            logger.debug("scrape_tv_shows: processing key=%r", key)

            if cache.is_tombstoned(key):
                if on_progress is not None:
                    on_progress(done, total)
                continue

            existing = cache.get_entry(key)
            if existing is not None and existing.get("tmdb_id") is not None:
                if on_progress is not None:
                    on_progress(done, total)
                continue

            result = self.search_tv_show(show.name)
            logger.debug("scrape_tv_shows: search name=%r → %s", show.name, result.get("id") if result else "no result")

            if result is None:
                cache.write_tombstone(key)
                logger.info("scrape_tv_shows: no TMDb result for key=%r, writing tombstone", key)
                if on_progress is not None:
                    on_progress(done, total)
                time.sleep(0.26)
                continue

            first_air = result.get("first_air_date", "")
            entry: dict = {
                "title":          result.get("name", key),
                "year":           int(first_air[:4]) if first_air else 0,
                "description":    result.get("overview", ""),
                "genres":         [],
                "rating":         "",
                "tmdb_id":        result["id"],
                "poster_scraped": "",
            }

            if result.get("poster_path"):
                dest = cache._scraped_art_dir / f"{key}.jpg"
                if self.download_poster(result["poster_path"], dest):
                    entry["poster_scraped"] = str(dest)

            cache.set_entry(key, entry)
            logger.info("scrape_tv_shows: saved key=%r tmdb_id=%s poster=%s", key, entry["tmdb_id"], bool(entry["poster_scraped"]))

            if on_progress is not None:
                on_progress(done, total)

            time.sleep(0.26)

    def close(self) -> None:
        """Close the underlying requests session."""
        self._session.close()


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
    year: int = 0       # populated by _enrich_from_cache automatically

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
# Cache enrichment helper
# ---------------------------------------------------------------------------


def _enrich_from_cache(items: list, cache: LocalVideoCache) -> None:
    """Mutate items in place, filling in poster/metadata from cache.

    Works for both VideoFile (has ``path``) and Show (has ``seasons``) via
    hasattr checks — no brittle isinstance coupling.
    """
    cache.load()  # reload from disk to pick up any scrapes done since last load
    logger.debug("_enrich_from_cache: %d items, cache=%s", len(items), cache._cache_dir)
    enriched = 0
    for item in items:
        # Determine cache key: Show uses folder name; VideoFile uses file stem
        if hasattr(item, "path") and not hasattr(item, "seasons"):
            key = Path(item.path).stem
        else:
            key = item.name

        poster = cache.resolve_poster(key)
        if poster:
            item.poster_path = poster

        meta = cache.resolve_metadata(key)
        if meta.get("tmdb_id") is not None or any(meta.get(f) for f in ("title", "description", "year")):
            enriched += 1
            logger.debug("  enriched key=%r tmdb_id=%s year=%s", key, meta.get("tmdb_id"), meta.get("year"))
        else:
            logger.debug("  no cache entry for key=%r", key)

        if meta.get("title") and hasattr(item, "title"):
            item.title = meta["title"]
        if meta.get("description"):
            item.description = meta["description"]
        if meta.get("year") and hasattr(item, "year"):
            item.year = meta["year"]
        genres = meta.get("genres", [])
        if genres and hasattr(item, "genre"):
            item.genre = ", ".join(genres)

    logger.info("_enrich_from_cache: %d/%d items enriched from %s", enriched, len(items), cache._cache_dir)


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

    Roles: title, path, posterPath, year, genre, description
    """

    TitleRole       = Qt.ItemDataRole.UserRole + 1
    PathRole        = Qt.ItemDataRole.UserRole + 2
    PosterPathRole  = Qt.ItemDataRole.UserRole + 3
    YearRole        = Qt.ItemDataRole.UserRole + 4
    GenreRole       = Qt.ItemDataRole.UserRole + 5
    DescriptionRole = Qt.ItemDataRole.UserRole + 6

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
        if role == self.YearRole:
            return item.year
        if role == self.GenreRole:
            return item.genre
        if role == self.DescriptionRole:
            return item.description
        if role == Qt.ItemDataRole.DisplayRole:
            return item.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole:       b"title",
            self.PathRole:        b"path",
            self.PosterPathRole:  b"posterPath",
            self.YearRole:        b"year",
            self.GenreRole:       b"genre",
            self.DescriptionRole: b"description",
        }


class ShowListModel(QAbstractListModel):
    """Exposes TV shows to QML.

    Roles: name, path, posterPath, seasonCount, episodeCount, year, description
    """

    NameRole        = Qt.ItemDataRole.UserRole + 1
    PathRole        = Qt.ItemDataRole.UserRole + 2
    PosterPathRole  = Qt.ItemDataRole.UserRole + 3
    SeasonCountRole = Qt.ItemDataRole.UserRole + 4
    EpisodeCountRole = Qt.ItemDataRole.UserRole + 5
    YearRole        = Qt.ItemDataRole.UserRole + 6
    DescriptionRole = Qt.ItemDataRole.UserRole + 7

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
        if role == self.YearRole:
            return item.year
        if role == self.DescriptionRole:
            return item.description
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole:        b"name",
            self.PathRole:        b"path",
            self.PosterPathRole:  b"posterPath",
            self.SeasonCountRole: b"seasonCount",
            self.EpisodeCountRole: b"episodeCount",
            self.YearRole:        b"year",
            self.DescriptionRole: b"description",
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
    scrapeProgressChanged = Signal(int, int)  # (done, total)
    scrapeFinished = Signal(str)              # category display name
    scrapeError = Signal(str)                 # error message

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
        self._scrape_thread: Optional[threading.Thread] = None

        # Empty models
        self._videos = VideoListModel(self)
        self._shows = ShowListModel(self)
        self._seasons = SeasonListModel(self)
        self._episodes = EpisodeListModel(self)

        self._current_category_index = -1

        # Sort/filter state (reset on each selectCategory call)
        self._video_sort: str = ""
        self._video_genre: str = ""
        self._show_sort: str = ""

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
        # Reset sort/filter state on each category switch
        self._video_sort = ""
        self._video_genre = ""
        self._show_sort = ""
        cat = cats[index]
        logger.debug("selectCategory: index=%d name=%r type=%r", index, cat.get("name"), cat.get("type"))
        if cat["type"] == "flat":
            items = _scan_flat(cat["paths"])
            cache = _movies_cache() if index == 0 else _custom_category_cache(cat["name"])
            _enrich_from_cache(items, cache)
            self._reset_model(self._videos, items)
            # Reset TV show models
            self._reset_model(self._shows, [])
            self._reset_model(self._seasons, [])
            self._reset_model(self._episodes, [])
            self.videosModelChanged.emit()
            logger.debug("selectCategory: model reset with %d items", len(items))
        else:
            shows = _scan_tv_shows(cat["paths"])
            cache = _tv_shows_cache() if index == 1 else _custom_category_cache(cat["name"])
            _enrich_from_cache(shows, cache)
            self._reset_model(self._shows, shows)
            # Reset flat/season/episode models
            self._reset_model(self._videos, [])
            self._reset_model(self._seasons, [])
            self._reset_model(self._episodes, [])
            self.showsModelChanged.emit()
            logger.debug("selectCategory: model reset with %d items", len(shows))
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
    # Sort / filter helpers
    # ------------------------------------------------------------------

    def _apply_videos_filter_sort(self) -> None:
        """Rebuild _display_items from _items, applying the current genre filter and sort."""
        items = self._videos._items
        # Genre filter
        if self._video_genre:
            items = [
                v for v in items
                if self._video_genre in [g.strip() for g in v.genre.split(",") if g.strip()]
            ]
        # Sort
        if self._video_sort == "az":
            items = sorted(items, key=lambda v: v.title.lower())
        elif self._video_sort == "za":
            items = sorted(items, key=lambda v: v.title.lower(), reverse=True)
        elif self._video_sort == "year_desc":
            items = sorted(items, key=lambda v: v.year, reverse=True)
        elif self._video_sort == "year_asc":
            items = sorted(items, key=lambda v: v.year)
        # Update display list only — _items remains the canonical unfiltered list
        self._videos.beginResetModel()
        self._videos._display_items = items
        self._videos.endResetModel()
        self.videosModelChanged.emit()

    def _apply_shows_sort(self) -> None:
        """Rebuild _display_items for shows, applying the current sort."""
        items = self._shows._items
        if self._show_sort == "az":
            items = sorted(items, key=lambda s: s.name.lower())
        elif self._show_sort == "za":
            items = sorted(items, key=lambda s: s.name.lower(), reverse=True)
        elif self._show_sort == "year_desc":
            items = sorted(items, key=lambda s: s.year, reverse=True)
        elif self._show_sort == "year_asc":
            items = sorted(items, key=lambda s: s.year)
        self._shows.beginResetModel()
        self._shows._display_items = items
        self._shows.endResetModel()
        self.showsModelChanged.emit()

    # ------------------------------------------------------------------
    # Sort / filter slots
    # ------------------------------------------------------------------

    @Slot(str)
    def sortVideos(self, sort_key: str) -> None:
        """Set the sort key for videos and refresh the display list."""
        self._video_sort = sort_key
        self._apply_videos_filter_sort()

    @Slot(str)
    def filterVideosByGenre(self, genre: str) -> None:
        """Set the genre filter for videos and refresh the display list."""
        self._video_genre = genre
        self._apply_videos_filter_sort()

    @Slot(str)
    def sortShows(self, sort_key: str) -> None:
        """Set the sort key for TV shows and refresh the display list."""
        self._show_sort = sort_key
        self._apply_shows_sort()

    @Slot(result="QVariantList")
    def getVideoGenres(self) -> list:
        """Return sorted unique genre strings from the current videos list."""
        genres: set[str] = set()
        for v in self._videos._items:
            for g in v.genre.split(","):
                g = g.strip()
                if g:
                    genres.add(g)
        return sorted(genres)

    # ------------------------------------------------------------------
    # Scrape slots
    # ------------------------------------------------------------------

    @Slot()
    def scrapeMovies(self) -> None:
        """Start a background TMDb scrape for the Movies category."""
        self._start_scrape("movies")

    @Slot()
    def scrapeTvShows(self) -> None:
        """Start a background TMDb scrape for the TV Shows category."""
        self._start_scrape("tv_shows")

    def _start_scrape(self, category_type: str) -> None:
        """Kick off a background scrape thread for movies or tv_shows."""
        api_key = self._config.tmdb_api_key
        if not api_key:
            self.scrapeError.emit("TMDb API key not configured. Set it in Settings → Videos.")
            return
        if self._scrape_thread and self._scrape_thread.is_alive():
            self.scrapeError.emit("A scrape is already in progress.")
            return

        cats = self._config.local_video_categories
        if category_type == "movies":
            cat = next(
                (c for c in cats if c.get("type") == "flat" and c.get("name") == "Movies"),
                None,
            )
            items = _scan_flat(cat["paths"]) if cat else []
            cache = _movies_cache()
            display_name = "Movies"
        else:
            cat = next(
                (c for c in cats if c.get("type") == "tv_shows" and c.get("name") == "TV Shows"),
                None,
            )
            items = _scan_tv_shows(cat["paths"]) if cat else []
            cache = _tv_shows_cache()
            display_name = "TV Shows"

        if not items:
            if cat is None:
                logger.warning(
                    "_start_scrape: no '%s' category found (type=%s) in local_video_categories — nothing to scrape",
                    "Movies" if category_type == "movies" else "TV Shows",
                    "flat" if category_type == "movies" else "tv_shows",
                )
            else:
                logger.warning("_start_scrape: category %r has no scannable items", cat.get("name"))

        logger.info("_start_scrape: category_type=%s items=%d cache=%s", category_type, len(items), cache._cache_dir)

        cache.ensure_dirs()
        cache.load()
        scraper = TmdbScraper(api_key)

        def _on_progress(done: int, total: int) -> None:
            QMetaObject.invokeMethod(
                self,
                "_emit_scrape_progress",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, done),
                Q_ARG(int, total),
            )

        def _run() -> None:
            try:
                if category_type == "movies":
                    scraper.scrape_movies(items, cache, _on_progress)
                else:
                    scraper.scrape_tv_shows(items, cache, _on_progress)
            except Exception as exc:  # noqa: BLE001
                logger.exception("TmdbScraper error: %s", exc)
                QMetaObject.invokeMethod(
                    self,
                    "_emit_scrape_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, f"Scrape failed: {exc}"),
                )
            finally:
                scraper.close()
                QMetaObject.invokeMethod(
                    self,
                    "_emit_scrape_finished",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, display_name),
                    Q_ARG(str, category_type),
                )

        self._scrape_thread = threading.Thread(target=_run, daemon=True)
        self._scrape_thread.start()

    @Slot(int, int)
    def _emit_scrape_progress(self, done: int, total: int) -> None:
        self.scrapeProgressChanged.emit(done, total)

    @Slot(str, str)
    def _emit_scrape_finished(self, display_name: str, category_type: str) -> None:
        logger.info("_emit_scrape_finished: display_name=%r category_type=%r", display_name, category_type)
        self.scrapeFinished.emit(display_name)
        # Reload the category that was just scraped.
        # Walk categories to find the matching one by type, then call selectCategory.
        cats = self._config.local_video_categories
        target_type = "flat" if category_type == "movies" else "tv_shows"
        for i, cat in enumerate(cats):
            if cat.get("type") == target_type:
                logger.info("_emit_scrape_finished: reloading category index=%d name=%r", i, cat.get("name"))
                self.selectCategory(i)
                break
        else:
            logger.warning("_emit_scrape_finished: no %r category found to reload", target_type)

    @Slot(str)
    def _emit_scrape_error(self, message: str) -> None:
        self.scrapeError.emit(message)

    # ------------------------------------------------------------------
    # set_wid pass-through
    # ------------------------------------------------------------------

    def set_wid(self, wid: int) -> None:
        """Pass the Qt native window handle to the MPV player.

        Must be called after the Qt window is shown (same as plex_library).
        """
        self._mpv.set_wid(wid)
