"""ScreenScraper.fr adapter for the HTPC Station retro scraper.

Queries the ScreenScraper.fr jeuInfos API to fetch metadata and media for
retro ROM files using MD5/CRC32 hash matching and filename fallback.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from backend.retro_scraper import AbstractScraperSource, RomHash, ScraperResult
from backend.scrapers._utils import download_file as _download_file_shared
from backend.scrapers._utils import scrub_url as _scrub_url_shared

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SS_API_URL = "https://www.screenscraper.fr/api2/jeuInfos.php"
_RATE_LIMIT_S = 1.2

REGION_PRIO = ["us", "wor", "eu", "ss", "uk", "jp"]
_LANG_PRIO = ["en"]

SS_PLATFORM_IDS: dict[str, int] = {
    # Nintendo
    "gb": 9, "gbc": 10, "gba": 12, "nes": 3, "snes": 4,
    "n64": 14, "n64dd": 122, "nds": 15, "n3ds": 17,
    "fds": 106, "satellaview": 107, "sufami": 108,
    "gamecube": 13, "wii": 16,
    "virtualboy": 11, "gameandwatch": 52, "supergrafx": 105,
    "sgb": 127, "gb2players": 9, "gbc2players": 10,
    # PC Engine
    "pce": 31, "pcengine": 31, "pcenginecd": 114,
    # Sega
    "megadrive": 1, "sega32x": 19, "segacd": 20,
    "mastersystem": 2, "gamegear": 21,
    "saturn": 22, "dreamcast": 23, "sg1000": 109,
    "naomi": 56, "naomi2": 230, "atomiswave": 53,
    # Sony
    "psx": 57, "ps2": 58, "ps3": 59, "psp": 61,
    # SNK
    "ngp": 25, "ngpc": 82,
    "neogeo": 142, "neogeocd": 70,
    # Atari
    "atari2600": 26, "atari7800": 41, "atari5200": 40,
    "atari800": 43, "atari8bit": 43,
    "atarilynx": 28, "lynx": 28,
    "atarist": 42, "jaguar": 27, "jaguarcd": 171,
    # WonderSwan
    "wonderswan": 45, "wonderswancolor": 46,
    "wswan": 45, "wswanc": 46,
    # Arcade
    "mame": 75, "fbneo": 75,
    # Commodore
    "c64": 66, "c128": 66,
    "amiga500": 64, "amiga1200": 111,
    "amigacd32": 130, "amigacdtv": 129,
    # MSX
    "msx1": 113, "msx2": 116, "msx2+": 117, "msxturbor": 118,
    # Other
    "intellivision": 115, "colecovision": 48,
    "vectrex": 102, "zxspectrum": 76,
    "pokemini": 211,
}

# Media slot → list of SS media type strings to try (in order)
_MEDIA_SLOTS: list[tuple[str, list[str]]] = [
    ("thumbnail_path", ["box-2D"]),
    ("marquee_path",   ["wheel-hd", "wheel", "wheel-steel"]),
    ("screenshot_path", ["ss", "sstitle"]),
    ("video_path",     ["video", "video-normalized"]),
]

# Media subdirectory per slot field
_MEDIA_SUBDIRS: dict[str, str] = {
    "thumbnail_path": "covers",
    "marquee_path":   "wheels",
    "screenshot_path": "screenshots",
    "video_path":     "videos",
}

_MEDIA_REGION_PRIO = ["us", "wor", "eu", "ss"]


# ---------------------------------------------------------------------------
# Credential scrubbing — re-exported from _utils for backwards compatibility
# ---------------------------------------------------------------------------

def _scrub_url(text: str) -> str:  # noqa: D401
    """Scrub credential values from *text*.  Delegates to ``_utils.scrub_url``."""
    return _scrub_url_shared(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick_by_region(items: list, key: str, region_prio: list) -> str:
    """Return ``item[key]`` for the first item matching any region in *region_prio*.

    Falls back to the first item's value if none match.  Returns ``""`` when
    *items* is empty.
    """
    if not items:
        return ""
    for region in region_prio:
        for item in items:
            if item.get("region") == region:
                return item.get(key, "")
    return items[0].get(key, "")


def _pick_by_lang(items: list, key: str, lang_prio: list) -> str:
    """Return ``item[key]`` for the first item matching any language in *lang_prio*.

    Falls back to the first item's value if none match.  Returns ``""`` when
    *items* is empty.
    """
    if not items:
        return ""
    for lang in lang_prio:
        for item in items:
            if item.get("langue") == lang:
                return item.get(key, "")
    return items[0].get(key, "")


def _best_media_url(medias: list, types: list[str]) -> Optional[tuple[str, str]]:
    """Find the best media entry matching any type in *types* (in order).

    Prefers regions in ``_MEDIA_REGION_PRIO`` order.  If a matching type has
    no preferred-region entry, falls back to the first entry of that type.

    Returns ``(url, format)`` or ``None`` if no match is found.
    """
    for media_type in types:
        candidates = [m for m in medias if m.get("type") == media_type]
        if not candidates:
            continue
        # Try preferred regions in order
        for region in _MEDIA_REGION_PRIO:
            for candidate in candidates:
                if candidate.get("region") == region:
                    return candidate.get("url", ""), candidate.get("format", "")
        # No preferred region — take any
        first = candidates[0]
        return first.get("url", ""), first.get("format", "")
    return None


def _download_file(session: requests.Session, url: str, dest_path: Path) -> bool:
    """Download *url* to *dest_path*.  Creates parent directories.

    Returns True on success, False on any exception (logged at WARNING).
    Delegates to the shared ``_utils.download_file`` helper.
    """
    return _download_file_shared(session, url, dest_path)


# ---------------------------------------------------------------------------
# ScreenScraperSource
# ---------------------------------------------------------------------------


class ScreenScraperSource(AbstractScraperSource):
    """Adapter for the ScreenScraper.fr jeuInfos API."""

    def __init__(
        self,
        devid: str,
        devpassword: str,
        username: str = "",
        password: str = "",
    ) -> None:
        self._devid = devid
        self._devpassword = devpassword
        self._username = username
        self._password = password
        self._session = requests.Session()
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "screenscraper"

    def is_configured(self) -> bool:
        """Return True if both devid and devpassword are non-empty."""
        return bool(self._devid and self._devpassword)

    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Query ScreenScraper for the given ROM and return a populated ScraperResult.

        Returns None when no match is found or on errors.
        """
        system_id = SS_PLATFORM_IDS.get(system_folder.lower())
        if system_id is None:
            logger.debug("[screenscraper] unknown platform: %s", system_folder)
            return None

        # Rate limiting
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)

        params: dict[str, str | int] = {
            "devid": self._devid,
            "devpassword": self._devpassword,
            "output": "json",
            "systemeid": system_id,
        }
        if self._username:
            params["ssid"] = self._username
        if self._password:
            params["sspassword"] = self._password
        if rom_hash.md5:
            params["md5"] = rom_hash.md5
        if rom_hash.crc32:
            params["crc"] = rom_hash.crc32
        params["romnom"] = rom_path.name

        try:
            resp = self._session.get(_SS_API_URL, params=params, timeout=(10, 30))
        except requests.RequestException as exc:
            logger.warning("[screenscraper] request error: %s", _scrub_url(str(exc)))
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code in (429, 430):
            logger.warning("[screenscraper] quota exhausted (HTTP %d)", resp.status_code)
            self._quota_exhausted = True
            return None
        if resp.status_code == 404:
            logger.debug("[screenscraper] no match for %s", rom_path.name)
            return None
        if not resp.ok:
            logger.warning("[screenscraper] unexpected status %d for %s", resp.status_code, rom_path.name)
            return None

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[screenscraper] JSON parse error: %s", exc)
            return None

        response = data.get("response", {})

        # Log quota
        ssuser = response.get("ssuser", {})
        req_today = ssuser.get("requeststoday", "?")
        max_req = ssuser.get("maxrequestsperday", "?")
        logger.debug("[screenscraper] quota: %s/%s", req_today, max_req)

        jeu = response.get("jeu")
        if not jeu:
            logger.debug("[screenscraper] no jeu in response for %s", rom_path.name)
            return None

        result = self._parse_jeu(jeu)
        self._fetch_media(jeu, result, rom_path, media_dir)
        return result

    def _parse_jeu(self, jeu: dict) -> ScraperResult:
        """Parse a ScreenScraper ``jeu`` dict into a ScraperResult."""
        result = ScraperResult()

        # name
        result.name = _pick_by_region(jeu.get("noms", []), "text", REGION_PRIO)

        # description
        result.description = _pick_by_lang(jeu.get("synopsis", []), "text", _LANG_PRIO)

        # developer
        result.developer = jeu.get("developpeur", {}).get("text", "")

        # publisher
        result.publisher = jeu.get("editeur", {}).get("text", "")

        # genre — first English genre name
        genres = jeu.get("genres", [])
        if genres:
            genre_noms = genres[0].get("noms", [])
            result.genre = _pick_by_lang(genre_noms, "text", _LANG_PRIO)

        # players
        result.players = jeu.get("joueurs", {}).get("text", "")

        # rating — SS scale 0–20, convert to 0.0–1.0
        try:
            result.rating = float(jeu.get("note", {}).get("text", "0") or "0") / 20.0
        except (ValueError, TypeError):
            result.rating = 0.0

        # release_date
        result.release_date = _pick_by_region(jeu.get("dates", []), "text", REGION_PRIO)

        return result

    def _fetch_media(
        self,
        jeu: dict,
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
    ) -> None:
        """Download media files from SS and populate media path fields on *result*."""
        medias = jeu.get("medias", [])
        stem = rom_path.stem

        for field_name, types in _MEDIA_SLOTS:
            url_fmt = _best_media_url(medias, types)
            if url_fmt is None:
                continue
            url, fmt = url_fmt
            if not url:
                continue
            subdir = _MEDIA_SUBDIRS[field_name]
            dest = media_dir / subdir / f"{stem}.{fmt}"
            if _download_file(self._session, url, dest):
                setattr(result, field_name, dest)

    def close(self) -> None:
        """No-op: keep session alive across games for connection reuse."""

    def __del__(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass
