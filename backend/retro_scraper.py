"""Retro ROM scraper orchestrator for HTPC Station.

Provides the thread model, signal contract, per-field merge logic,
config schema integration, Hasheous pre-pass, hash computation, and
logging infrastructure.  Actual scraper adapters are added in later tasks;
``_sources`` is empty here so the loop runs but produces zero results.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from PySide6.QtCore import (
    QMetaObject,
    QObject,
    QThread,
    Q_ARG,
    Qt,
    Signal,
    Slot,
)

from backend.config import Config
from backend.gamelist import parse_gamelist, write_game_entry
from backend.models import Game

# ---------------------------------------------------------------------------
# Module-level logger — file handler added lazily in RetroScraper.__init__
# ---------------------------------------------------------------------------

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RomHash:
    """MD5 and CRC32 hashes of a ROM file."""

    md5: str    # lowercase hex
    crc32: str  # lowercase hex, zero-padded to 8 chars


@dataclass
class ScraperResult:
    """Accumulated metadata from one or more scraper sources."""

    # Identification hints (set by Hasheous pre-pass; used by chain sources)
    canonical_name: str = ""
    cross_db_ids: dict = field(default_factory=dict)  # e.g. {"tgdb_id": 123, "igdb_id": 456}

    # Scraped metadata (any source can fill these)
    name: str = ""
    description: str = ""
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    players: str = ""
    rating: float = 0.0
    release_date: str = ""        # raw string, e.g. "19990527T000000"

    # Scraped media paths (set after download; absolute Path)
    thumbnail_path: Optional[Path] = None    # cover / boxart front
    marquee_path: Optional[Path] = None      # wheel / clear logo
    screenshot_path: Optional[Path] = None   # gameplay screenshot
    video_path: Optional[Path] = None        # video snap

    # Per-field attribution (for logging: field_name → source_name)
    source_for: dict = field(default_factory=dict)


# Fields eligible for merge / completeness checks (order is significant for logs)
MERGE_FIELDS = (
    "name", "description", "developer", "publisher", "genre",
    "players", "rating", "release_date",
    "thumbnail_path", "marquee_path", "screenshot_path", "video_path",
)

# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _is_empty(result: ScraperResult, field_name: str) -> bool:
    """Return True if *field_name* on *result* is None, ``""``, or ``0.0``."""
    val = getattr(result, field_name)
    return val is None or val == "" or val == 0.0


def merge_into(
    target: ScraperResult,
    source: ScraperResult,
    source_name: str,
    overwrite: bool,
) -> None:
    """Merge non-empty fields from *source* into *target*.

    For each field in ``MERGE_FIELDS``: if *source* has a non-empty value AND
    (*overwrite* is True OR *target* field is currently empty), copy the value
    and record ``target.source_for[field] = source_name``.
    """
    for f in MERGE_FIELDS:
        if _is_empty(source, f):
            continue
        if overwrite or _is_empty(target, f):
            setattr(target, f, getattr(source, f))
            target.source_for[f] = source_name


def all_filled(result: ScraperResult) -> bool:
    """Return True when every field in ``MERGE_FIELDS`` is non-empty."""
    return all(not _is_empty(result, f) for f in MERGE_FIELDS)


# ---------------------------------------------------------------------------
# AbstractScraperSource
# ---------------------------------------------------------------------------


class AbstractScraperSource(ABC):
    """Base class for all scraper adapters."""

    # Non-abstract — adapters set this True when quota is exhausted.
    _quota_exhausted: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this source (e.g. ``"screenscraper"``)."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this source has enough credentials to make requests."""
        ...

    @abstractmethod
    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Search for the game and download media.

        Returns a :class:`ScraperResult` with whatever fields this source
        could fill, or ``None`` if no match was found.

        *media_dir* is the system's media root
        (``{rom_dir}/{system}/media/``).  Each source is responsible for
        downloading into the correct subdirectory:

        - ``media_dir / "covers"   / stem + ext``
        - ``media_dir / "wheels"   / stem + ext``
        - ``media_dir / "screenshots" / stem + ext``
        - ``media_dir / "videos"   / stem + ext``
        """
        ...

    def close(self) -> None:
        """Release HTTP sessions or other resources.  Called after each game."""


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def compute_rom_hash(path: Path) -> RomHash:
    """Read *path* in 64 KB chunks and return its MD5 + CRC32 hashes.

    Returns ``RomHash("", "")`` on :exc:`OSError` (logs a warning).
    """
    _CHUNK = 65536
    md5_obj = hashlib.md5()
    crc_val = 0
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(_CHUNK)
                if not chunk:
                    break
                md5_obj.update(chunk)
                crc_val = zlib.crc32(chunk, crc_val)
    except OSError as exc:
        logger.warning("compute_rom_hash: could not read %s: %s", path, exc)
        return RomHash("", "")

    md5_hex = md5_obj.hexdigest().lower()
    # CRC32 from Python's zlib is already unsigned (>= 0) but mask to be safe
    crc_hex = format(crc_val & 0xFFFFFFFF, "08x")
    return RomHash(md5=md5_hex, crc32=crc_hex)


# ---------------------------------------------------------------------------
# Hasheous pre-pass
# ---------------------------------------------------------------------------

_HASHEOUS_BASE = "https://hasheous.org/api/v1"


def _hasheous_lookup(rom_hash: RomHash) -> ScraperResult:
    """Query Hasheous for canonical name and cross-DB IDs.

    Best-effort: returns an empty :class:`ScraperResult` on any error.

    Uses MD5 when available, falls back to CRC32.
    """
    result = ScraperResult()
    try:
        if rom_hash.md5:
            url = f"{_HASHEOUS_BASE}/Lookup/ByHash/md5/{rom_hash.md5}"
        elif rom_hash.crc32:
            url = f"{_HASHEOUS_BASE}/Lookup/ByHash/crc/{rom_hash.crc32}"
        else:
            return result

        resp = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=(5, 10),
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            logger.debug("_hasheous_lookup: unexpected response type: %r", type(data))
            return result

        result.canonical_name = data.get("name", "")

        for entry in data.get("metadata", []):
            source = entry.get("source", "")
            id_val = entry.get("id", "")
            if not id_val:
                continue
            if source == "TheGamesDb":
                try:
                    result.cross_db_ids["tgdb_id"] = int(id_val)
                except (ValueError, TypeError):
                    pass
            elif source == "IGDB":
                try:
                    result.cross_db_ids["igdb_id"] = int(id_val)
                except (ValueError, TypeError):
                    pass
            elif source == "RetroAchievements":
                try:
                    result.cross_db_ids["ra_id"] = int(id_val)
                except (ValueError, TypeError):
                    pass

    except Exception as exc:  # noqa: BLE001
        logger.debug("_hasheous_lookup: error for hash %s: %s", rom_hash.md5 or rom_hash.crc32, exc)

    return result


# ---------------------------------------------------------------------------
# ROM discovery and name helpers
# ---------------------------------------------------------------------------


def _discover_roms(system_path: Path, config: Config, folder_name: str) -> list[Path]:
    """Return ROM files in *system_path* matching configured extensions.

    Does not recurse.  Returns ``[]`` if the extensions list is empty or the
    directory does not exist.
    """
    sc = config.get_system(folder_name)
    if not sc.extensions:
        return []
    if not system_path.is_dir():
        return []
    exts = frozenset(ext.lower() for ext in sc.extensions)
    return sorted(
        p for p in system_path.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    )


def _name_from_path(rom_path: Path) -> str:
    """Return *rom_path.stem* with bracketed tags stripped.

    Example: ``"Mega Man 2 (USA) [!]"`` → ``"Mega Man 2"``.
    """
    stem = rom_path.stem
    cleaned = re.sub(r'\s*[\(\[{][^\)\]}\n]*[\)\]}\n]', '', stem)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Game helpers
# ---------------------------------------------------------------------------


def _find_game(rom_path: Path, games: list[Game]) -> Optional[Game]:
    """Return the :class:`Game` whose path matches *rom_path*, or ``None``."""
    for g in games:
        if g.path == rom_path:
            return g
    return None


def _find_or_create_game(
    rom_path: Path,
    games: list[Game],
    folder_name: str,
) -> Game:
    """Return an existing :class:`Game` for *rom_path* or create a new one."""
    existing = _find_game(rom_path, games)
    if existing is not None:
        return existing
    return Game(path=rom_path, name=rom_path.stem, system_folder=folder_name)


def _game_fully_scraped(game: Game) -> bool:
    """Return True when all primary metadata + media fields are non-empty."""
    return all([
        game.name,
        game.description,
        game.thumbnail_path,
        game.marquee_path,
        game.screenshot_path,
        game.video_path,
    ])


def _seed_from_game(result: ScraperResult, game: Game) -> None:
    """Pre-fill *result* from an existing :class:`Game` so that
    ``overwrite=False`` merge skips already-filled fields.

    Maps Game fields to ScraperResult fields and marks them as ``"existing"``.
    """
    mapping = {
        "name": "name",
        "description": "description",
        "developer": "developer",
        "publisher": "publisher",
        "genre": "genre",
        "players": "players",
        "rating": "rating",
        "release_date": "release_date",
        "thumbnail_path": "thumbnail_path",
        "marquee_path": "marquee_path",
        "screenshot_path": "screenshot_path",
        "video_path": "video_path",
    }
    for game_field, result_field in mapping.items():
        val = getattr(game, game_field)
        # Only seed non-empty values
        if val is None or val == "" or val == 0.0:
            continue
        setattr(result, result_field, val)
        result.source_for[result_field] = "existing"


def _apply_result(game: Game, result: ScraperResult, config: Config) -> None:
    """Copy all non-empty fields from *result* onto *game*.

    Also sets *game.image_path* from the configured preview source
    (cover thumbnail or screenshot) when *game.image_path* is not already set,
    so that existing miximages are never overwritten.
    """
    mapping = {
        "name": "name",
        "description": "description",
        "developer": "developer",
        "publisher": "publisher",
        "genre": "genre",
        "players": "players",
        "rating": "rating",
        "release_date": "release_date",
        "thumbnail_path": "thumbnail_path",
        "marquee_path": "marquee_path",
        "screenshot_path": "screenshot_path",
        "video_path": "video_path",
    }
    for result_field, game_field in mapping.items():
        val = getattr(result, result_field)
        if val is None or val == "" or val == 0.0:
            continue
        setattr(game, game_field, val)

    # Set preview image only if not already set (preserves user-generated miximages)
    if not game.image_path:
        preview = config.scraper_preview_image
        if preview == "screenshot" and result.screenshot_path:
            game.image_path = result.screenshot_path
        elif result.thumbnail_path:
            game.image_path = result.thumbnail_path


# ---------------------------------------------------------------------------
# Scrape one ROM
# ---------------------------------------------------------------------------


def _scrape_one(
    rom_path: Path,
    folder_name: str,
    system_path: Path,
    games: list[Game],
    config: Config,
    sources: list[AbstractScraperSource],
    overwrite: bool,
) -> Optional[ScraperResult]:
    """Run the Hasheous pre-pass and source chain for one ROM.

    Returns the merged :class:`ScraperResult`, or ``None`` if the ROM was
    skipped (already fully scraped and *overwrite* is False).
    """
    existing = _find_game(rom_path, games)

    # Skip when all fields are already filled and we're not overwriting
    if not overwrite and existing and _game_fully_scraped(existing):
        logger.debug("_scrape_one: skipping fully-scraped ROM: %s", rom_path.name)
        return None

    rom_hash = compute_rom_hash(rom_path)
    logger.debug("_scrape_one: hash md5=%s crc32=%s", rom_hash.md5, rom_hash.crc32)

    # Hasheous pre-pass
    pre = _hasheous_lookup(rom_hash)
    canonical_name = pre.canonical_name or _name_from_path(rom_path)
    logger.debug(
        "_scrape_one: canonical_name=%r (hasheous=%s)",
        canonical_name,
        bool(pre.canonical_name),
    )

    merged = ScraperResult(
        canonical_name=canonical_name,
        cross_db_ids=pre.cross_db_ids,
    )
    # Seed from existing gamelist data so overwrite=False skips already-filled fields
    if existing:
        _seed_from_game(merged, existing)

    media_dir = system_path / "media"

    for source in sources:
        if not source.is_configured():
            continue
        if source._quota_exhausted:
            logger.debug("_scrape_one: [%s] quota exhausted, skipping", source.name)
            continue
        if all_filled(merged) and not overwrite:
            break
        logger.debug("_scrape_one: [%s] querying", source.name)
        try:
            partial = source.search(
                rom_path, folder_name, rom_hash,
                canonical_name, pre.cross_db_ids, media_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("_scrape_one: [%s] error: %s", source.name, exc)
            continue
        finally:
            source.close()

        if partial is None:
            logger.debug("_scrape_one: [%s] no match", source.name)
            continue

        merge_into(merged, partial, source.name, overwrite)
        filled_by = [f for f in MERGE_FIELDS if merged.source_for.get(f) == source.name]
        logger.debug("_scrape_one: [%s] filled: %s", source.name, filled_by)

    # Log per-ROM attribution summary
    attribution = {f: merged.source_for.get(f, "\u2014") for f in MERGE_FIELDS}
    logger.info("  %s \u2192 %s", rom_path.name, attribution)

    # If no source filled any MERGE_FIELDS (e.g. empty source list or all missed),
    # treat as a skip so callers don't write empty entries into the gamelist.
    newly_filled = {f for f in MERGE_FIELDS if merged.source_for.get(f) not in (None, "existing")}
    if not newly_filled:
        logger.debug("_scrape_one: no new metadata for %s — skipping", rom_path.name)
        return None

    return merged


# ---------------------------------------------------------------------------
# Scrape thread
# ---------------------------------------------------------------------------


class _ScrapeThread(QThread):
    """QThread subclass that runs the retro scrape loop in its run() override.

    Uses ``QMetaObject.invokeMethod`` with ``QueuedConnection`` to marshal
    signals back to the owning :class:`RetroScraper` on the main thread.
    """

    def __init__(
        self,
        owner: "RetroScraper",
        config: Config,
        sources: list[AbstractScraperSource],
        systems: list[tuple[str, Path]],
        cancel_flag: threading.Event,
        overwrite: bool,
    ) -> None:
        super().__init__()
        self._owner = owner
        self._config = config
        self._sources = sources
        self._systems = systems
        self._cancel_flag = cancel_flag
        self._overwrite = overwrite

    def run(self) -> None:  # noqa: C901
        """Run the scrape loop on the worker thread."""
        self._scrape_loop()

    def _scrape_loop(self) -> None:  # noqa: C901
        scraped = skipped = failed = 0
        source_counts: dict[str, int] = {}

        for folder_name, system_path in self._systems:
            if self._cancel_flag.is_set():
                self._invoke("_emit_scrape_cancelled")
                return

            games = parse_gamelist(system_path)
            all_rom_paths = _discover_roms(system_path, self._config, folder_name)
            total = len(all_rom_paths)

            for i, rom_path in enumerate(all_rom_paths):
                if self._cancel_flag.is_set():
                    self._invoke("_emit_scrape_cancelled")
                    return

                QMetaObject.invokeMethod(
                    self._owner,
                    "_emit_scrape_progress",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(int, i),
                    Q_ARG(int, total),
                    Q_ARG(str, rom_path.stem),
                )

                try:
                    result = _scrape_one(
                        rom_path, folder_name, system_path,
                        games, self._config, self._sources, self._overwrite,
                    )
                    if result is None:
                        skipped += 1
                    else:
                        game = _find_or_create_game(rom_path, games, folder_name)
                        _apply_result(game, result, self._config)
                        write_game_entry(system_path, game)
                        scraped += 1
                        # Credit every source that filled at least one field
                        for src in set(result.source_for.values()):
                            if src != "existing":
                                source_counts[src] = source_counts.get(src, 0) + 1
                except Exception:  # noqa: BLE001
                    logger.exception("_scrape_loop: unhandled error for %s", rom_path)
                    failed += 1

        QMetaObject.invokeMethod(
            self._owner,
            "_emit_scrape_finished",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, scraped),
            Q_ARG(int, skipped),
            Q_ARG(int, failed),
            Q_ARG('QVariantMap', source_counts),
        )

    def _invoke(self, slot: str) -> None:
        """Invoke a no-argument slot on the owner via QueuedConnection."""
        QMetaObject.invokeMethod(
            self._owner,
            slot,
            Qt.ConnectionType.QueuedConnection,
        )


# ---------------------------------------------------------------------------
# RetroScraper QObject
# ---------------------------------------------------------------------------

#: Virtual folder names that should never be scraped
_VIRTUAL_SYSTEMS = frozenset({"_favorites", "_lastplayed", "_allgames"})


class RetroScraper(QObject):
    """Orchestrates ROM metadata scraping for all configured retro systems.

    Signals are always emitted on the main thread via
    ``QMetaObject.invokeMethod``.
    """

    scrapeProgress = Signal(int, int, str)          # (done, total, current_game_name)
    scrapeFinished = Signal(int, int, int, 'QVariantMap')  # (scraped, skipped, failed, source_counts)
    scrapeError = Signal(str)                       # fatal error message
    scrapeCancelled = Signal()

    def __init__(self, config: Config, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._sources: list[AbstractScraperSource] = []
        self._scrape_thread: Optional[_ScrapeThread] = None
        self._cancel_flag = threading.Event()

        # Set up the scraper file logger (add at most one FileHandler)
        _setup_scraper_logger()

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot(str)
    def scrapeSystem(self, folder_name: str) -> None:
        """Scrape all ROMs in one system.  No-op if a scrape is already running."""
        if self._config.rom_directory is None:
            self.scrapeError.emit("ROM directory is not configured.")
            return
        system_path = self._config.rom_directory / folder_name
        self._start_scrape([(folder_name, system_path)])

    @Slot()
    def scrapeAll(self) -> None:
        """Scrape all real systems (skips virtual _favorites/_lastplayed/_allgames)."""
        if self._config.rom_directory is None:
            self.scrapeError.emit("ROM directory is not configured.")
            return
        rom_dir = self._config.rom_directory
        systems: list[tuple[str, Path]] = []
        if rom_dir.is_dir():
            for entry in sorted(rom_dir.iterdir()):
                if entry.is_dir() and entry.name not in _VIRTUAL_SYSTEMS:
                    systems.append((entry.name, entry))
        self._start_scrape(systems)

    @Slot()
    def cancelScrape(self) -> None:
        """Signal the running scrape to stop after the current game finishes."""
        self._cancel_flag.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_sources(self) -> list[AbstractScraperSource]:
        """Instantiate configured scraper sources from current credentials."""
        # Lazy import to avoid circular dependency:
        # screenscraper.py imports AbstractScraperSource etc. from retro_scraper.py
        from backend.scrapers.screenscraper import ScreenScraperSource  # noqa: PLC0415

        sources: list[AbstractScraperSource] = []
        enabled = self._config.scraper_enabled_sources
        creds = self._config.scraper_credentials

        if "screenscraper" in enabled:
            ss = creds.get("screenscraper", {})
            src = ScreenScraperSource(
                devid=ss.get("devid", ""),
                devpassword=ss.get("devpassword", ""),
                username=ss.get("username", ""),
                password=ss.get("password", ""),
            )
            sources.append(src)

        if "emumovies" in enabled:
            from backend.scrapers.emumovies import EmuMoviesSource  # noqa: PLC0415
            em = creds.get("emumovies", {})
            sources.append(EmuMoviesSource(
                username=em.get("username", ""),
                password=em.get("password", ""),
            ))

        if "thegamesdb" in enabled:
            from backend.scrapers.thegamesdb import TheGamesDBSource  # noqa: PLC0415
            tgdb = creds.get("thegamesdb", {})
            sources.append(TheGamesDBSource(api_key=tgdb.get("api_key", "")))

        if "mobygames" in enabled:
            from backend.scrapers.mobygames import MobyGamesSource  # noqa: PLC0415
            mg = creds.get("mobygames", {})
            sources.append(MobyGamesSource(api_key=mg.get("api_key", "")))

        if "igdb" in enabled:
            from backend.scrapers.igdb import IGDBSource  # noqa: PLC0415
            ig = creds.get("igdb", {})
            sources.append(IGDBSource(
                client_id=ig.get("client_id", ""),
                client_secret=ig.get("client_secret", ""),
            ))

        if "retroachievements" in enabled:
            from backend.scrapers.retroachievements import RetroAchievementsSource  # noqa: PLC0415
            ra = creds.get("retroachievements", {})
            sources.append(RetroAchievementsSource(
                username=ra.get("username", ""),
                api_key=ra.get("api_key", ""),
            ))

        return sources

    def _start_scrape(self, systems: list[tuple[str, Path]]) -> None:
        """Validate, guard against concurrent scrapes, and start the thread."""
        _setup_scraper_logger()
        # Truncate the log file at the start of each scrape session so each run
        # starts fresh rather than appending to prior sessions.
        _scraper_logger = logging.getLogger("scraper")
        for handler in _scraper_logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.stream.seek(0)
                handler.stream.truncate()
                break

        self._sources = self._build_sources()
        configured_sources = [s for s in self._sources if s.is_configured()]

        if self._scrape_thread is not None and self._scrape_thread.isRunning():
            self.scrapeError.emit("A scrape is already in progress.")
            return

        self._cancel_flag.clear()
        overwrite = self._config.scraper_overwrite
        thread = _ScrapeThread(
            self, self._config, configured_sources, systems,
            self._cancel_flag, overwrite,
        )
        self._scrape_thread = thread
        thread.start()

    # ------------------------------------------------------------------
    # Slots invoked from worker thread via QMetaObject.invokeMethod
    # ------------------------------------------------------------------

    @Slot(int, int, str)
    def _emit_scrape_progress(self, done: int, total: int, name: str) -> None:
        self.scrapeProgress.emit(done, total, name)

    @Slot(int, int, int, 'QVariantMap')
    def _emit_scrape_finished(self, scraped: int, skipped: int, failed: int, source_counts: dict) -> None:
        logger.info(
            "_emit_scrape_finished: scraped=%d skipped=%d failed=%d sources=%s",
            scraped, skipped, failed, source_counts,
        )
        self.scrapeFinished.emit(scraped, skipped, failed, source_counts)

    @Slot(str)
    def _emit_scrape_error(self, message: str) -> None:
        self.scrapeError.emit(message)

    @Slot()
    def _emit_scrape_cancelled(self) -> None:
        self.scrapeCancelled.emit()


# ---------------------------------------------------------------------------
# Logger setup helper
# ---------------------------------------------------------------------------


def _setup_scraper_logger() -> None:
    """Add a FileHandler to the ``scraper`` logger (at most once)."""
    scraper_logger = logging.getLogger("scraper")
    if not any(isinstance(h, logging.FileHandler) for h in scraper_logger.handlers):
        log_dir = Path.home() / ".config" / "htpcstation"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(
            log_dir / "scraper.log",
            mode="a",
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        scraper_logger.addHandler(handler)
