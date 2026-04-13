"""MobyGames adapter for the HTPC Station retro scraper.

Queries the MobyGames v2 API to fetch metadata and media for retro ROM files.
MobyGames is particularly strong on description quality and developer/publisher
data.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests

from backend.retro_scraper import AbstractScraperSource, RomHash, ScraperResult
from backend.scrapers._utils import download_file as _download_file
from backend.scrapers._utils import iso_date_to_gamelist
from backend.scrapers._utils import scrub_url as _scrub_url

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOBY_BASE = "https://api.mobygames.com/v2"
_RATE_LIMIT_S = 5.0

# ---------------------------------------------------------------------------
# Platform ID mapping
# Built from /home/thwonp/opencode/skyscraper/mobygames_platforms.json
# Key = HTPC Station system folder; Value = MobyGames platform ID (int)
# ---------------------------------------------------------------------------

MOBY_PLATFORM_IDS: dict[str, int] = {
    # Nintendo handhelds
    "gb": 10,           # Game Boy
    "gbc": 11,          # Game Boy Color
    "gba": 12,          # Game Boy Advance
    "nds": 44,          # Nintendo DS
    "n3ds": 101,        # Nintendo 3DS
    "virtualboy": 38,   # Virtual Boy
    "pokemini": 152,    # Pokémon Mini
    # Nintendo consoles
    "nes": 22,          # NES
    "snes": 15,         # SNES
    "n64": 9,           # Nintendo 64
    "gamecube": 14,     # GameCube
    "wii": 82,          # Wii
    # Sega handhelds
    "gamegear": 25,     # Game Gear
    # Sega consoles
    "mastersystem": 26, # SEGA Master System
    "megadrive": 16,    # Genesis (MobyGames uses "Genesis" for the combined platform)
    "sega32x": 21,      # SEGA 32X
    "segacd": 20,       # SEGA CD
    "saturn": 23,       # SEGA Saturn
    "dreamcast": 8,     # Dreamcast
    "sg1000": 114,      # SG-1000
    # Sony
    "psx": 6,           # PlayStation
    "ps2": 7,           # PlayStation 2
    "ps3": 81,          # PlayStation 3
    "psp": 46,          # PSP
    # SNK
    "ngp": 52,          # Neo Geo Pocket
    "ngpc": 53,         # Neo Geo Pocket Color
    "neogeo": 36,       # Neo Geo
    "neogeocd": 54,     # Neo Geo CD
    # Atari
    "atari2600": 28,    # Atari 2600
    "atari5200": 33,    # Atari 5200
    "atari7800": 34,    # Atari 7800
    "atari800": 39,     # Atari 8-bit
    "atarilynx": 18,    # Lynx
    "lynx": 18,
    "atarist": 24,      # Atari ST
    "jaguar": 17,       # Jaguar
    # NEC
    "pce": 40,          # TurboGrafx-16
    "pcengine": 40,
    "pcenginecd": 45,   # TurboGrafx CD
    # WonderSwan
    "wonderswan": 48,   # WonderSwan
    "wonderswancolor": 49,  # WonderSwan Color
    "wswan": 48,
    "wswanc": 49,
    # Arcade
    "mame": 143,        # Arcade
    "fbneo": 143,
    # Commodore / Amiga
    "c64": 27,          # Commodore 64
    "amiga500": 19,     # Amiga
    "amiga1200": 19,
    "amigacd32": 56,    # Amiga CD32
    # MSX
    "msx1": 57,         # MSX
    "msx2": 57,
    # Other
    "intellivision": 30,   # Intellivision
    "colecovision": 29,    # ColecoVision
    "vectrex": 37,         # Vectrex
    "zxspectrum": 41,      # ZX Spectrum
}

# HTML tag stripping pattern
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from *text*."""
    return _HTML_TAG_RE.sub("", text)


# ---------------------------------------------------------------------------
# MobyGamesSource
# ---------------------------------------------------------------------------


class MobyGamesSource(AbstractScraperSource):
    """Adapter for the MobyGames v2 API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._session = requests.Session()
        self._last_request_time: float = 0.0
        self._auth_failed: bool = False

    @property
    def name(self) -> str:
        return "mobygames"

    def is_configured(self) -> bool:
        """Return True if api_key is non-empty."""
        return bool(self._api_key)

    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Query MobyGames for the given ROM and return a populated ScraperResult.

        Returns None when no match is found or on errors.
        """
        if self._auth_failed:
            return None

        platform_id = MOBY_PLATFORM_IDS.get(system_folder.lower())
        if platform_id is None:
            logger.debug("[mobygames] unknown platform: %s", system_folder)
            return None

        self._throttle()

        # Step 1: search for game ID
        game_id = self._search_game_id(canonical_name, platform_id)
        if game_id is None:
            return None

        self._throttle()

        # Step 2: fetch full detail
        game_detail = self._fetch_game_detail(game_id)
        if game_detail is None:
            return None

        result = self._parse_game(game_detail, platform_id)
        self._fetch_media(game_detail, result, rom_path, media_dir, platform_id)
        return result

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def _search_game_id(
        self,
        canonical_name: str,
        platform_id: int,
    ) -> Optional[int]:
        """GET /v2/games to find the best-matching game ID."""
        params: dict[str, object] = {
            "api_key": self._api_key,
            "title": canonical_name,
            "platform": platform_id,
            "fuzzy": "true",
            "include": "platforms,release_date",
        }
        try:
            resp = self._session.get(
                f"{_MOBY_BASE}/games",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[mobygames] request error: %s", _scrub_url(str(exc)))
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code == 401:
            logger.warning("[mobygames] invalid API key")
            self._auth_failed = True
            return None
        if resp.status_code == 429:
            logger.warning("[mobygames] quota exhausted")
            self._quota_exhausted = True
            return None
        if resp.status_code == 404:
            logger.debug("[mobygames] no match for %r", canonical_name)
            return None
        if not resp.ok:
            logger.warning("[mobygames] unexpected status %d", resp.status_code)
            return None

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[mobygames] JSON parse error: %s", exc)
            return None

        games = data.get("games") or []
        if not games:
            logger.debug("[mobygames] empty games list for %r", canonical_name)
            return None

        return games[0].get("id")

    def _fetch_game_detail(self, game_id: int) -> Optional[dict]:
        """GET /v2/games with id= to fetch full game detail."""
        params = {
            "api_key": self._api_key,
            "id": game_id,
            "include": "covers,description,developers,genres,publishers,screenshots,title",
        }
        try:
            resp = self._session.get(
                f"{_MOBY_BASE}/games",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[mobygames] request error: %s", _scrub_url(str(exc)))
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code == 401:
            logger.warning("[mobygames] invalid API key")
            self._auth_failed = True
            return None
        if resp.status_code == 429:
            logger.warning("[mobygames] quota exhausted")
            self._quota_exhausted = True
            return None
        if resp.status_code == 404:
            logger.debug("[mobygames] no detail for game_id=%s", game_id)
            return None
        if not resp.ok:
            logger.warning("[mobygames] unexpected status %d for game_id=%s", resp.status_code, game_id)
            return None

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[mobygames] JSON parse error: %s", exc)
            return None

        games = data.get("games") or []
        if not games:
            return None
        return games[0]

    # ------------------------------------------------------------------
    # Metadata parsing
    # ------------------------------------------------------------------

    def _parse_game(self, game: dict, platform_id: int) -> ScraperResult:
        """Parse a MobyGames game detail dict into a ScraperResult."""
        result = ScraperResult()

        result.name = game.get("title", "") or ""

        # Description — strip HTML tags
        raw_desc = game.get("description", "") or ""
        result.description = _strip_html(raw_desc)

        # Developer — prefer match for target platform_id
        devs = game.get("developers") or []
        result.developer = self._pick_company(devs, platform_id)

        # Publisher — prefer match for target platform_id
        pubs = game.get("publishers") or []
        result.publisher = self._pick_company(pubs, platform_id)

        # Genre — first genre where genre_category_id is 1 (Basic Genres) or 4 (Genres)
        genres = game.get("genres") or []
        for genre in genres:
            cat_id = genre.get("genre_category_id")
            if cat_id in (1, 4):
                result.genre = genre.get("genre_name", "")
                break
        if not result.genre and genres:
            result.genre = genres[0].get("genre_name", "")

        # Players — not reliably available on Hobbyist tier; leave empty

        # Release date — from platforms list, prefer platform_id match
        platforms = game.get("platforms") or []
        release_date_raw = self._pick_release_date(platforms, platform_id)
        if release_date_raw:
            result.release_date = iso_date_to_gamelist(release_date_raw)

        # Rating — not available; leave empty (result.rating stays 0.0)

        return result

    def _pick_company(self, companies: list[dict], platform_id: int) -> str:
        """Return company_name, preferring an entry matching platform_id."""
        if not companies:
            return ""
        for company in companies:
            if company.get("platform_id") == platform_id:
                return company.get("company_name", "")
        return companies[0].get("company_name", "")

    def _pick_release_date(self, platforms: list[dict], platform_id: int) -> str:
        """Return first_release_date, preferring an entry matching platform_id."""
        if not platforms:
            return ""
        for plat in platforms:
            if plat.get("platform_id") == platform_id:
                return plat.get("first_release_date", "") or ""
        return platforms[0].get("first_release_date", "") or ""

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def _fetch_media(
        self,
        game: dict,
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
        platform_id: int,
    ) -> None:
        """Download media files and populate media path fields on result."""
        stem = rom_path.stem

        # thumbnail_path ← covers[0].image_url (prefer platform_id match)
        covers = game.get("covers") or []
        cover_url = self._pick_media_url(covers, platform_id, "image_url")
        if cover_url:
            ext = Path(cover_url.split("?")[0]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "covers" / f"{stem}.{ext}"
            if _download_file(self._session, cover_url, dest):
                result.thumbnail_path = dest

        # screenshot_path ← screenshots[0].image_url
        screenshots = game.get("screenshots") or []
        ss_url = self._pick_media_url(screenshots, platform_id, "image_url")
        if ss_url:
            ext = Path(ss_url.split("?")[0]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "screenshots" / f"{stem}.{ext}"
            if _download_file(self._session, ss_url, dest):
                result.screenshot_path = dest

        # marquee_path — not available from MobyGames
        # video_path — not available from MobyGames

    def _pick_media_url(
        self,
        items: list[dict],
        platform_id: int,
        url_key: str,
    ) -> str:
        """Return url_key value, preferring an item with matching platform_id."""
        if not items:
            return ""
        for item in items:
            if item.get("platform_id") == platform_id:
                return item.get(url_key, "") or ""
        return items[0].get(url_key, "") or ""

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep if needed to respect the 1 req/5s safe rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op."""

    def __del__(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass
