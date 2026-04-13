"""EmuMovies adapter for the HTPC Station retro scraper.

Queries the EmuMovies API v2 for media assets (video snaps, screenshots,
box art, logos).  EmuMovies requires a paid subscription for API access.

IMPLEMENTATION NOTES / ASSUMPTIONS
-----------------------------------
Because the Swagger docs at https://api.emumovies.com/swagger/index.html
could not be verified at implementation time, the following decisions were
made based on the best-known API shape described in the Task Brief.  Items
most likely to need adjustment if the live API differs are marked (*).

  (*) Login endpoint:  POST /api/User/Login
      Response field:  "Token"

  (*) Media search endpoint: GET /api/v1/MediaSearch
      Query params:  SystemName, Title

  (*) Media response: JSON array of objects with "MediaType" and "URL" fields.
      If the API returns a wrapper object, adjust _parse_media_list() to
      unwrap it before iterating.

  (*) EM_SYSTEM_NAMES values should be verified against GET /api/v1/Systems.

All of the above are isolated to small, clearly labelled sections so that
adjustments require minimal changes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from backend.retro_scraper import AbstractScraperSource, RomHash, ScraperResult
from backend.scrapers._utils import download_file as _download_file
from backend.scrapers._utils import scrub_url as _scrub_url

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EM_BASE_URL = "https://api.emumovies.com"
_LOGIN_URL = f"{_EM_BASE_URL}/api/User/Login"        # (*) verify path
_MEDIA_SEARCH_URL = f"{_EM_BASE_URL}/api/v1/MediaSearch"  # (*) verify path
_RATE_LIMIT_S = 1.0

# ---------------------------------------------------------------------------
# System name mapping
# ---------------------------------------------------------------------------
# Maps HTPC Station system folder names to the string values accepted by the
# EmuMovies API's SystemName parameter.
#
# (*) ALL values here should be verified against GET /api/v1/Systems.
#     The strings below are approximate best-known values from the Task Brief.

EM_SYSTEM_NAMES: dict[str, str] = {
    "gb":            "Nintendo Game Boy",
    "gbc":           "Nintendo Game Boy Color",
    "gba":           "Nintendo Game Boy Advance",
    "nes":           "Nintendo Entertainment System",
    "snes":          "Super Nintendo Entertainment System",
    "n64":           "Nintendo 64",
    "nds":           "Nintendo DS",
    "gamecube":      "Nintendo GameCube",
    "wii":           "Nintendo Wii",
    "virtualboy":    "Nintendo Virtual Boy",
    "fds":           "Nintendo Famicom Disk System",
    "pce":           "NEC TurboGrafx-16",
    "megadrive":     "Sega Genesis",
    "sega32x":       "Sega 32X",
    "segacd":        "Sega CD",
    "mastersystem":  "Sega Master System",
    "gamegear":      "Sega Game Gear",
    "saturn":        "Sega Saturn",
    "dreamcast":     "Sega Dreamcast",
    "psx":           "Sony PlayStation",
    "ps2":           "Sony PlayStation 2",
    "psp":           "Sony PlayStation Portable",
    "ngp":           "SNK Neo Geo Pocket",
    "ngpc":          "SNK Neo Geo Pocket Color",
    "atari2600":     "Atari 2600",
    "atari7800":     "Atari 7800",
    "atari5200":     "Atari 5200",
    "atarilynx":     "Atari Lynx",
    "jaguar":        "Atari Jaguar",
    "wonderswan":    "Bandai WonderSwan",
    "wonderswancolor": "Bandai WonderSwan Color",
    "neogeo":        "SNK Neo Geo AES",
    "mame":          "MAME",
    "c64":           "Commodore 64",
    "amiga500":      "Commodore Amiga",
}

# ---------------------------------------------------------------------------
# Media type → ScraperResult field mapping
# ---------------------------------------------------------------------------
# (*) MediaType string values should be verified against the live API.
# Order matters: first match per field wins.

_MEDIA_SLOTS: list[tuple[str, list[str], str]] = [
    # (result_field, em_media_types_to_try, media_subdir)
    ("video_path",      ["Video", "VideoSnap"],          "videos"),
    ("screenshot_path", ["Screenshot", "InGame"],        "screenshots"),
    ("thumbnail_path",  ["BoxFront", "BoxArt"],          "covers"),
    ("marquee_path",    ["Logo", "ClearLogo", "Wheel"],  "wheels"),
]

# Extension fallbacks by media type when the URL has no recognisable extension.
_TYPE_DEFAULT_EXT: dict[str, str] = {
    "Video":      "mp4",
    "VideoSnap":  "mp4",
    "Screenshot": "jpg",
    "InGame":     "jpg",
    "BoxFront":   "jpg",
    "BoxArt":     "jpg",
    "Logo":       "png",
    "ClearLogo":  "png",
    "Wheel":      "png",
}


# ---------------------------------------------------------------------------
# EmuMoviesSource
# ---------------------------------------------------------------------------


class EmuMoviesSource(AbstractScraperSource):
    """Adapter for the EmuMovies API v2.

    Primarily contributes ``video_path`` and ``screenshot_path`` to the
    scraper result chain.  Metadata fields (name, description, etc.) are not
    populated because EmuMovies does not reliably provide them.
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._login_failed: bool = False
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "emumovies"

    def is_configured(self) -> bool:
        """Return True if both username and password are non-empty."""
        return bool(self._username and self._password)

    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Query EmuMovies for media assets for the given ROM.

        Returns a :class:`ScraperResult` with media path fields populated, or
        ``None`` if no match was found or if the adapter is not available.
        """
        if self._login_failed:
            return None

        system_name = EM_SYSTEM_NAMES.get(system_folder.lower())
        if system_name is None:
            logger.debug("[emumovies] unknown system folder: %s", system_folder)
            return None

        # Lazy login
        if self._token is None:
            if not self._login():
                return None

        title = canonical_name or rom_path.stem
        media_items = self._fetch_media_list(system_name, title)
        if media_items is None:
            return None

        result = ScraperResult()
        self._populate_media(media_items, result, rom_path, media_dir)
        return result

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _login(self) -> bool:
        """POST credentials to the EmuMovies login endpoint.

        Sets ``self._token`` on success.  On failure, sets
        ``self._login_failed`` and returns ``False``.

        (*) Endpoint path and response field name may need adjustment.
        """
        payload = {"Username": self._username, "Password": self._password}
        try:
            self._throttle()
            resp = self._session.post(
                _LOGIN_URL,
                json=payload,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning(
                "[emumovies] login request error: %s",
                _scrub_url(str(exc)),
            )
            self._login_failed = True
            return False
        finally:
            self._last_request_time = time.monotonic()

        if not resp.ok:
            logger.warning(
                "[emumovies] login failed with status %d", resp.status_code
            )
            self._login_failed = True
            return False

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[emumovies] login JSON parse error: %s", exc)
            self._login_failed = True
            return False

        if not isinstance(data, dict):
            logger.warning(
                "[emumovies] login: unexpected response type %s", type(data).__name__
            )
            self._login_failed = True
            return False

        # (*) The Token field name may differ — check Swagger docs.
        token = data.get("Token") or data.get("token") or data.get("access_token")
        if not token:
            logger.warning(
                "[emumovies] login response missing Token field: %s",
                list(data.keys()),
            )
            self._login_failed = True
            return False

        self._token = str(token)
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})
        logger.debug("[emumovies] login successful")
        return True

    # ------------------------------------------------------------------
    # Media search
    # ------------------------------------------------------------------

    def _fetch_media_list(
        self,
        system_name: str,
        title: str,
    ) -> Optional[list[dict]]:
        """GET media items for *system_name* / *title*.

        Returns a list of media item dicts (may be empty), or ``None`` on error.

        (*) Endpoint path and query parameter names may need adjustment based
            on the Swagger docs.
        """
        params = {
            "SystemName": system_name,  # (*) verify param name
            "Title": title,             # (*) verify param name
        }
        try:
            self._throttle()
            resp = self._session.get(
                _MEDIA_SEARCH_URL,
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning(
                "[emumovies] media search request error: %s",
                _scrub_url(str(exc)),
            )
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code == 429:
            logger.warning("[emumovies] quota exhausted")
            self._quota_exhausted = True
            return None
        if resp.status_code == 404:
            logger.debug("[emumovies] no match for system=%r title=%r", system_name, title)
            return None
        if not resp.ok:
            logger.warning(
                "[emumovies] unexpected status %d for system=%r title=%r",
                resp.status_code, system_name, title,
            )
            return None

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[emumovies] media search JSON parse error: %s", exc)
            return None

        return self._parse_media_list(data)

    def _parse_media_list(self, data: object) -> list[dict]:
        """Normalise the raw API response into a flat list of media item dicts.

        The EmuMovies API may return a plain array or a wrapper object. Both
        shapes are handled here.

        (*) Adjust if the live API uses a different envelope structure.
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try common envelope keys
            for key in ("results", "media", "items", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        logger.debug("[emumovies] unexpected media response shape: %r", type(data))
        return []

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    def _populate_media(
        self,
        media_items: list[dict],
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
    ) -> None:
        """Download media files and set path fields on *result*.

        (*) MediaType and URL field names in each item may need adjustment.
        """
        stem = rom_path.stem

        for field_name, em_types, subdir in _MEDIA_SLOTS:
            url, ext = self._pick_media(media_items, em_types)
            if not url:
                continue
            dest = media_dir / subdir / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                setattr(result, field_name, dest)

    def _pick_media(
        self,
        media_items: list[dict],
        em_types: list[str],
    ) -> tuple[str, str]:
        """Return ``(url, ext)`` for the first item matching any type in *em_types*.

        Returns ``("", "")`` when no match is found.

        (*) MediaType and URL key names may differ — adjust if needed.
        """
        for em_type in em_types:
            for item in media_items:
                # (*) field name may be "MediaType", "Type", or "mediaType"
                item_type = (
                    item.get("MediaType")
                    or item.get("Type")
                    or item.get("mediaType")
                    or ""
                )
                if item_type != em_type:
                    continue
                # (*) field name may be "URL", "Url", or "url"
                url = (
                    item.get("URL")
                    or item.get("Url")
                    or item.get("url")
                    or ""
                )
                if not url:
                    continue
                # Derive extension from URL path; fall back to type default.
                ext = Path(url.split("?")[0]).suffix.lstrip(".") or _TYPE_DEFAULT_EXT.get(em_type, "bin")
                return url, ext
        return "", ""

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep if needed to respect the 1-second rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op: keep session alive across games for connection reuse."""

    def __del__(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass
