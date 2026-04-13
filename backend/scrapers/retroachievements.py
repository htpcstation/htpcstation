"""RetroAchievements adapter for the HTPC Station retro scraper.

Resolves ROM MD5 hashes against the RetroAchievements database to retrieve
game metadata and box art / in-game screenshots.

Auth: username + API key sent as query parameters on every request.
Images are served from a public CDN (no auth required).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
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

# RA passes the API key as a single-letter query param "y=<key>".  The shared
# scrub_url helper won't catch it (too short / too generic), so we apply a
# local pattern before logging any error message that may embed a URL.
_RA_KEY_SCRUB = re.compile(r"\by=([^&\s)\"]+)")

_RA_API_BASE = "https://retroachievements.org/API"
_RA_MEDIA_BASE = "https://media.retroachievements.org"
_RATE_LIMIT_S = 1.0


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------


def _parse_ra_date(released: str) -> str:
    """Best-effort conversion of RetroAchievements "Released" field.

    Tries several format strings and returns a gamelist-compatible
    ``"YYYYMMDDTHHMMSS"`` string, or ``""`` on failure.

    Supported input formats (examples):
    - ``"January 1989"``  → ``"19890101T000000"``
    - ``"1989-01-01"``    → ``"19890101T000000"``
    - ``"1989"``          → ``"19890101T000000"``
    """
    if not released:
        return ""

    # Try "%B %Y" — e.g. "January 1989"
    try:
        dt = datetime.strptime(released.strip(), "%B %Y")
        return dt.strftime("%Y%m%d") + "T000000"
    except ValueError:
        pass

    # Try "%Y-%m-%d" — e.g. "1989-01-01"
    try:
        dt = datetime.strptime(released.strip(), "%Y-%m-%d")
        return dt.strftime("%Y%m%d") + "T000000"
    except ValueError:
        pass

    # Try "%Y" — e.g. "1989"
    try:
        dt = datetime.strptime(released.strip(), "%Y")
        return dt.strftime("%Y") + "0101T000000"
    except ValueError:
        pass

    return ""


# ---------------------------------------------------------------------------
# RetroAchievementsSource
# ---------------------------------------------------------------------------


class RetroAchievementsSource(AbstractScraperSource):
    """Adapter for the RetroAchievements API.

    Uses MD5 hash to look up game metadata.  Contributes name, developer,
    publisher, genre, release_date, thumbnail_path, and screenshot_path.
    """

    def __init__(self, username: str, api_key: str) -> None:
        self._username = username
        self._api_key = api_key
        self._session = requests.Session()
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "retroachievements"

    def is_configured(self) -> bool:
        """Return True if both username and api_key are non-empty."""
        return bool(self._username and self._api_key)

    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Resolve ROM MD5 hash against RetroAchievements and return metadata."""
        if not rom_hash.md5:
            logger.debug("[retroachievements] no MD5 hash available for %s", rom_path.name)
            return None

        data = self._lookup_by_md5(rom_hash.md5)
        if data is None:
            return None

        game_id = data.get("ID")
        if not game_id:
            logger.debug(
                "[retroachievements] no game ID in response for MD5 %s", rom_hash.md5
            )
            return None

        result = ScraperResult()
        self._map_metadata(data, result)
        self._download_media(data, result, rom_path, media_dir)
        return result

    # ------------------------------------------------------------------
    # API request
    # ------------------------------------------------------------------

    def _lookup_by_md5(self, md5: str) -> Optional[dict]:
        """GET /API_GetGameInfoByMD5.php for *md5*.

        Returns the response dict on success, or None on error / no match.
        """
        params = {
            "z": self._username,
            "y": self._api_key,
            "m": md5,
        }
        try:
            self._throttle()
            resp = self._session.get(
                f"{_RA_API_BASE}/API_GetGameInfoByMD5.php",
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            scrubbed = _RA_KEY_SCRUB.sub(r"y=***", _scrub_url(str(exc)))
            logger.warning("[retroachievements] request error: %s", scrubbed)
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code == 429:
            logger.warning("[retroachievements] quota exhausted")
            self._quota_exhausted = True
            return None
        if not resp.ok:
            logger.warning(
                "[retroachievements] unexpected status %d for MD5 %s",
                resp.status_code, md5,
            )
            return None

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[retroachievements] JSON parse error: %s", exc)
            return None

        if not isinstance(data, dict):
            logger.debug("[retroachievements] unexpected response type: %r", type(data))
            return None

        return data

    # ------------------------------------------------------------------
    # Metadata mapping
    # ------------------------------------------------------------------

    def _map_metadata(self, data: dict, result: ScraperResult) -> None:
        """Populate *result* from the RA game info dict."""
        result.name = data.get("Title") or ""
        result.developer = data.get("Developer") or ""
        result.publisher = data.get("Publisher") or ""
        result.genre = data.get("Genre") or ""

        released = data.get("Released") or ""
        result.release_date = _parse_ra_date(released)

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    def _download_media(
        self,
        data: dict,
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
    ) -> None:
        """Download box art and in-game screenshot from the RA media CDN."""
        stem = rom_path.stem

        # thumbnail ← ImageBoxArt
        box_art = data.get("ImageBoxArt") or ""
        if box_art:
            url = _RA_MEDIA_BASE + box_art
            ext = Path(box_art.split("?")[0]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "covers" / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                result.thumbnail_path = dest

        # screenshot ← ImageIngame
        ingame = data.get("ImageIngame") or ""
        if ingame:
            url = _RA_MEDIA_BASE + ingame
            ext = Path(ingame.split("?")[0]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "screenshots" / f"{stem}.{ext}"
            if _download_file(self._session, url, dest):
                result.screenshot_path = dest

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep if needed to respect the rate limit."""
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
