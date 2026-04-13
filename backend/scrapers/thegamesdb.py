"""TheGamesDB adapter for the HTPC Station retro scraper.

Queries the TheGamesDB v1 API to fetch metadata and media for retro ROM files
using canonical name search with optional platform filter, or by TGDB game ID
when available from the Hasheous pre-pass.
"""

from __future__ import annotations

import logging
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

_TGDB_BASE = "https://api.thegamesdb.net/v1"
_RATE_LIMIT_S = 0.5

# ---------------------------------------------------------------------------
# Platform ID mapping
# Built from /home/thwonp/opencode/skyscraper/tgdb_platforms.json
# Key = HTPC Station system folder; Value = list of TGDB platform IDs
# ---------------------------------------------------------------------------

TGDB_PLATFORM_IDS: dict[str, list[int]] = {
    # Nintendo handhelds
    "gb": [4],          # Nintendo Game Boy
    "gbc": [41],        # Nintendo Game Boy Color
    "gba": [5],         # Nintendo Game Boy Advance
    "nds": [8],         # Nintendo DS
    "n3ds": [4912],     # Nintendo 3DS
    "virtualboy": [4918],  # Nintendo Virtual Boy
    "pokemini": [4957], # Nintendo Pokémon Mini
    # Nintendo consoles
    "nes": [7],         # Nintendo Entertainment System (NES)
    "fds": [4936],      # Famicom Disk System
    "snes": [6],        # Super Nintendo (SNES)
    "n64": [3],         # Nintendo 64
    "gamecube": [2],    # Nintendo GameCube
    "wii": [9],         # Nintendo Wii
    # Sega handhelds
    "gamegear": [20],   # Sega Game Gear
    # Sega consoles
    "mastersystem": [35],  # Sega Master System
    "megadrive": [18, 36], # Sega Genesis / Mega Drive (two IDs)
    "sega32x": [33],    # Sega 32X
    "segacd": [21],     # Sega CD
    "saturn": [17],     # Sega Saturn
    "dreamcast": [16],  # Sega Dreamcast
    "sg1000": [4949],   # SEGA SG-1000
    # Sony
    "psx": [10],        # Sony PlayStation
    "ps2": [11],        # Sony PlayStation 2
    "ps3": [12],        # Sony PlayStation 3
    "psp": [13],        # Sony PlayStation Portable
    # SNK
    "ngp": [4922],      # Neo Geo Pocket
    "ngpc": [4923],     # Neo Geo Pocket Color
    "neogeo": [24],     # Neo Geo
    "neogeocd": [4956], # Neo Geo CD
    # Atari
    "atari2600": [22],  # Atari 2600
    "atari5200": [26],  # Atari 5200
    "atari7800": [27],  # Atari 7800
    "atari800": [4943], # Atari 800
    "atarilynx": [4924], # Atari Lynx
    "lynx": [4924],
    "atarist": [4937],  # Atari ST
    "jaguar": [28],     # Atari Jaguar
    "jaguarcd": [29],   # Atari Jaguar CD
    # NEC
    "pce": [34],        # TurboGrafx-16 / PC Engine
    "pcengine": [34],
    "pcenginecd": [4955],  # TurboGrafx CD
    # WonderSwan
    "wonderswan": [4925],  # WonderSwan
    "wonderswancolor": [4926],  # WonderSwan Color
    "wswan": [4925],
    "wswanc": [4926],
    # Arcade
    "mame": [23],       # Arcade
    "fbneo": [23],
    # Commodore / Amiga
    "c64": [40],        # Commodore 64
    "amiga500": [4911], # Amiga
    "amiga1200": [4911],
    "amigacd32": [4947],  # Amiga CD32
    # MSX
    "msx1": [4929],     # MSX
    "msx2": [4929],
    # Other
    "intellivision": [32],   # Intellivision
    "colecovision": [31],    # ColecoVision
    "vectrex": [4939],       # Vectrex
    "zxspectrum": [4913],    # ZX Spectrum
}


# ---------------------------------------------------------------------------
# TheGamesDBSource
# ---------------------------------------------------------------------------


class TheGamesDBSource(AbstractScraperSource):
    """Adapter for the TheGamesDB v1 API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._session = requests.Session()
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "thegamesdb"

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
        """Query TheGamesDB for the given ROM and return a populated ScraperResult.

        Prefers lookup by TGDB game ID when available in cross_db_ids.
        Falls back to name search with platform filter.

        Returns None when no match is found or on errors.
        """
        platform_ids = TGDB_PLATFORM_IDS.get(system_folder.lower())
        if platform_ids is None:
            logger.debug("[thegamesdb] unknown platform: %s", system_folder)
            return None

        self._throttle()

        tgdb_id = cross_db_ids.get("tgdb_id")
        if tgdb_id:
            game_data, include = self._fetch_by_id(tgdb_id)
        else:
            game_data, include = self._fetch_by_name(canonical_name, platform_ids)

        if game_data is None:
            return None

        result = self._parse_game(game_data, include)
        self._fetch_media(game_data.get("id"), result, rom_path, media_dir)
        return result

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def _fetch_by_id(self, tgdb_id: int) -> tuple[Optional[dict], dict]:
        """GET /v1/Games/ByGameID for a known TGDB game ID."""
        params = {
            "apikey": self._api_key,
            "id": tgdb_id,
            "fields": "players,publishers,genres,overview,last_updated,rating,platform",
        }
        try:
            resp = self._session.get(
                f"{_TGDB_BASE}/Games/ByGameID",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[thegamesdb] request error: %s", _scrub_url(str(exc)))
            return None, {}
        finally:
            self._last_request_time = time.monotonic()

        return self._handle_response(resp)

    def _fetch_by_name(
        self,
        canonical_name: str,
        platform_ids: list[int],
    ) -> tuple[Optional[dict], dict]:
        """GET /v1/Games/ByGameName for a name search."""
        params: dict[str, object] = {
            "apikey": self._api_key,
            "name": canonical_name,
            "fields": "players,publishers,genres,overview,last_updated,rating,platform",
            "filter[platform]": ",".join(str(pid) for pid in platform_ids),
        }
        try:
            resp = self._session.get(
                f"{_TGDB_BASE}/Games/ByGameName",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[thegamesdb] request error: %s", _scrub_url(str(exc)))
            return None, {}
        finally:
            self._last_request_time = time.monotonic()

        return self._handle_response(resp)

    def _handle_response(
        self, resp: requests.Response
    ) -> tuple[Optional[dict], dict]:
        """Parse HTTP response and return (game_dict, include_dict) or (None, {})."""
        if resp.status_code == 429:
            logger.warning("[thegamesdb] quota exhausted")
            self._quota_exhausted = True
            return None, {}
        if resp.status_code == 404:
            logger.debug("[thegamesdb] no match")
            return None, {}
        if not resp.ok:
            logger.warning("[thegamesdb] unexpected status %d", resp.status_code)
            return None, {}

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[thegamesdb] JSON parse error: %s", exc)
            return None, {}

        games = data.get("data", {}).get("games") or []
        if not games:
            logger.debug("[thegamesdb] empty games list in response")
            return None, {}

        if len(games) > 1:
            logger.debug("[thegamesdb] multiple games returned (%d), using first", len(games))

        include = data.get("include", {})
        return games[0], include

    # ------------------------------------------------------------------
    # Metadata parsing
    # ------------------------------------------------------------------

    def _parse_game(self, game: dict, include: dict) -> ScraperResult:
        """Parse a TGDB game dict into a ScraperResult."""
        result = ScraperResult()

        result.name = game.get("game_title", "")
        result.description = game.get("overview", "") or ""

        # Developer — resolve first developer ID
        dev_ids = game.get("developers") or []
        if dev_ids:
            dev_data = include.get("developers", {}).get("data", {})
            dev_info = dev_data.get(str(dev_ids[0]), {})
            result.developer = dev_info.get("name", "")

        # Publisher — resolve first publisher ID
        pub_ids = game.get("publishers") or []
        if pub_ids:
            pub_data = include.get("publishers", {}).get("data", {})
            pub_info = pub_data.get(str(pub_ids[0]), {})
            result.publisher = pub_info.get("name", "")

        # Genre — resolve first genre ID
        genre_ids = game.get("genres") or []
        if genre_ids:
            genre_data = include.get("genres", {}).get("data", {})
            genre_info = genre_data.get(str(genre_ids[0]), {})
            result.genre = genre_info.get("genre", "")

        # Players
        players = game.get("players")
        if players is not None:
            result.players = str(players)

        # Release date: "YYYY-MM-DD" → "YYYYMMDDTHHMMSS"
        release_date_raw = game.get("release_date", "") or ""
        if release_date_raw:
            result.release_date = iso_date_to_gamelist(release_date_raw)

        # Rating: TGDB provides ESRB strings (e.g. "E"), not 0-1 float — leave empty
        # result.rating remains 0.0

        return result

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def _fetch_media(
        self,
        game_id: Optional[int],
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
    ) -> None:
        """Fetch image URLs for game_id and download them."""
        if not game_id:
            return

        self._throttle()

        params = {
            "apikey": self._api_key,
            "games_id": game_id,
        }
        try:
            resp = self._session.get(
                f"{_TGDB_BASE}/Games/Images",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[thegamesdb] images request error: %s", _scrub_url(str(exc)))
            return
        finally:
            self._last_request_time = time.monotonic()

        if not resp.ok:
            logger.warning("[thegamesdb] images status %d for game_id=%s", resp.status_code, game_id)
            return

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[thegamesdb] images JSON parse error: %s", exc)
            return

        base_url = data.get("base_url", {}).get("original", "")
        images = data.get("data", {}).get("images", {}).get(str(game_id), [])
        if not images:
            return

        stem = rom_path.stem

        # thumbnail_path ← boxart front
        cover_url = self._find_image(images, image_type="boxart", side="front")
        if cover_url:
            url = base_url + cover_url["filename"]
            ext = Path(cover_url["filename"]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "covers" / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                result.thumbnail_path = dest

        # marquee_path ← clearlogo
        logo_url = self._find_image(images, image_type="clearlogo")
        if logo_url:
            url = base_url + logo_url["filename"]
            ext = Path(logo_url["filename"]).suffix.lstrip(".") or "png"
            dest = media_dir / "wheels" / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                result.marquee_path = dest

        # screenshot_path ← screenshot
        ss_url = self._find_image(images, image_type="screenshot")
        if ss_url:
            url = base_url + ss_url["filename"]
            ext = Path(ss_url["filename"]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "screenshots" / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                result.screenshot_path = dest

        # video_path — not available from TGDB

    def _find_image(
        self,
        images: list[dict],
        image_type: str,
        side: Optional[str] = None,
    ) -> Optional[dict]:
        """Return the first image entry matching type (and optionally side)."""
        for img in images:
            if img.get("type") != image_type:
                continue
            if side is not None and img.get("side") != side:
                continue
            return img
        return None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep if needed to respect the 2 req/s rate limit."""
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
