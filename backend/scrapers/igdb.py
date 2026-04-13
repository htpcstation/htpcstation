"""IGDB adapter for the HTPC Station retro scraper.

Queries the Twitch/IGDB API v4 for game metadata and media.
IGDB is particularly strong for later-gen systems (PS1, PS2, N64, PSP).

Auth: Twitch OAuth client-credentials flow.  Token is obtained once per
scrape run and reused for all requests.  On 401 the _login_failed flag is set
and all subsequent calls within the same run return None without retrying.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
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

_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
_RATE_LIMIT_S = 1.1  # IGDB enforces 4 req/sec; 1.1 s is conservative

# APICalypse fields requested from IGDB
_IGDB_FIELDS = (
    "name,summary,involved_companies.company.name,involved_companies.developer,"
    "involved_companies.publisher,genres.name,game_modes.slug,"
    "first_release_date,cover.url,screenshots.url,artworks.url,"
    "release_dates.date,release_dates.platform,rating,platforms.name,platforms.id"
)

# ---------------------------------------------------------------------------
# game_modes.slug → players string
# ---------------------------------------------------------------------------

_GAME_MODE_PLAYERS: dict[str, str] = {
    "single-player": "1",
    "multiplayer": "2",
    "co-operative": "2",
}

# ---------------------------------------------------------------------------
# IGDB platform IDs
# Maps HTPC Station system folder names → list of IGDB platform IDs
# ---------------------------------------------------------------------------

IGDB_PLATFORM_IDS: dict[str, list[int]] = {
    "gb": [33],         # Game Boy
    "gbc": [22],        # Game Boy Color
    "gba": [24],        # Game Boy Advance
    "nes": [18],        # NES
    "snes": [19],       # SNES
    "n64": [4],         # Nintendo 64
    "nds": [20],        # Nintendo DS
    "gamecube": [21],   # GameCube
    "wii": [5],         # Wii
    "virtualboy": [87],
    "pce": [128],       # PC Engine/TurboGrafx-16
    "megadrive": [29],  # Sega Mega Drive/Genesis
    "mastersystem": [64],
    "gamegear": [35],
    "sega32x": [30],
    "saturn": [32],
    "dreamcast": [23],
    "psx": [7],         # PlayStation
    "ps2": [8],
    "ps3": [9],
    "psp": [38],
    "ngpc": [119],
    "atari2600": [59],
    "atari7800": [60],
    "atarilynx": [61],
    "jaguar": [62],
    "wonderswan": [57],
    "wonderswancolor": [58],
    "neogeo": [80],
    "mame": [52],       # Arcade
    "fbneo": [52],
    "c64": [15],
    "amiga500": [16],
    "zxspectrum": [26],
}


# ---------------------------------------------------------------------------
# URL helper
# ---------------------------------------------------------------------------


def _igdb_image_url(raw_url: str, size: str) -> str:
    """Normalise an IGDB image URL and substitute *size* token.

    IGDB returns protocol-relative URLs like ``//images.igdb.com/…/t_thumb/x.jpg``.
    This helper adds ``https:`` and replaces the size token with *size*.
    """
    if raw_url.startswith("//"):
        url = "https:" + raw_url
    else:
        url = raw_url
    return re.sub(r"/t_[^/]+/", f"/t_{size}/", url)


# ---------------------------------------------------------------------------
# IGDBSource
# ---------------------------------------------------------------------------


class IGDBSource(AbstractScraperSource):
    """Adapter for the Twitch/IGDB API v4.

    Contributes name, description, developer, publisher, genre, players,
    release_date, rating, thumbnail_path, and screenshot_path.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = requests.Session()
        self._access_token: Optional[str] = None
        self._login_failed: bool = False
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "igdb"

    def is_configured(self) -> bool:
        """Return True if both client_id and client_secret are non-empty."""
        return bool(self._client_id and self._client_secret)

    def search(
        self,
        rom_path: Path,
        system_folder: str,
        rom_hash: RomHash,
        canonical_name: str,
        cross_db_ids: dict,
        media_dir: Path,
    ) -> Optional[ScraperResult]:
        """Query IGDB for metadata and media for the given ROM."""
        if self._login_failed:
            return None

        # Lazy token acquisition
        if self._access_token is None:
            if not self._authenticate():
                return None

        igdb_id = cross_db_ids.get("igdb_id")
        game = self._fetch_game(
            canonical_name=canonical_name or rom_path.stem,
            igdb_id=igdb_id,
            system_folder=system_folder.lower(),
        )
        if game is None:
            return None

        result = ScraperResult()
        self._map_metadata(game, result)
        self._download_media(game, result, rom_path, media_dir)
        return result

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> bool:
        """Obtain a Twitch OAuth token via client-credentials flow.

        Sets ``self._access_token`` on success.  On failure sets
        ``self._login_failed`` and returns False.
        """
        params = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }
        try:
            self._throttle()
            resp = self._session.post(
                _TWITCH_TOKEN_URL,
                params=params,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning(
                "[igdb] token request error: %s",
                _scrub_url(str(exc)),
            )
            self._login_failed = True
            return False
        finally:
            self._last_request_time = time.monotonic()

        if not resp.ok:
            logger.warning("[igdb] token request failed with status %d", resp.status_code)
            self._login_failed = True
            return False

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[igdb] token JSON parse error: %s", exc)
            self._login_failed = True
            return False

        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            logger.warning("[igdb] token response missing access_token: %r", type(data))
            self._login_failed = True
            return False

        self._access_token = str(token)
        self._session.headers.update({
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._access_token}",
        })
        logger.debug("[igdb] authenticated successfully")
        return True

    # ------------------------------------------------------------------
    # Game fetch
    # ------------------------------------------------------------------

    def _fetch_game(
        self,
        canonical_name: str,
        igdb_id: Optional[int],
        system_folder: str,
    ) -> Optional[dict]:
        """POST an APICalypse query to IGDB and return the best matching game dict."""
        if igdb_id is not None:
            body = (
                f"fields {_IGDB_FIELDS};"
                f"where id = {igdb_id};"
                "limit 1;"
            )
        else:
            # Name-based search — request top 5; we'll filter/pick below
            safe_name = canonical_name.replace('"', '\\"')
            body = (
                f'fields {_IGDB_FIELDS};'
                "where version_parent = null;"
                f'search "{safe_name}";'
                "limit 5;"
            )

        try:
            self._throttle()
            resp = self._session.post(
                _IGDB_GAMES_URL,
                data=body,
                headers={"Content-Type": "text/plain"},
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            logger.warning("[igdb] game search request error: %s", _scrub_url(str(exc)))
            return None
        finally:
            self._last_request_time = time.monotonic()

        if resp.status_code == 401:
            logger.warning("[igdb] received 401 — marking auth as failed")
            self._login_failed = True
            return None

        if resp.status_code == 429:
            logger.warning("[igdb] quota exhausted")
            self._quota_exhausted = True
            return None

        if not resp.ok:
            logger.warning("[igdb] game search status %d", resp.status_code)
            return None

        try:
            results = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[igdb] game search JSON parse error: %s", exc)
            return None

        if not isinstance(results, list) or not results:
            logger.debug("[igdb] no results for %r", canonical_name)
            return None

        if igdb_id is not None:
            return results[0]

        # Platform filtering for name-based searches
        platform_ids = IGDB_PLATFORM_IDS.get(system_folder)
        if platform_ids:
            filtered = [
                g for g in results
                if any(
                    p.get("id") in platform_ids
                    for p in (g.get("platforms") or [])
                )
            ]
            if filtered:
                return filtered[0]
            # Fall back to first result if no platform match
            logger.debug(
                "[igdb] no platform-filtered result for system=%r; using first result",
                system_folder,
            )

        return results[0]

    # ------------------------------------------------------------------
    # Metadata mapping
    # ------------------------------------------------------------------

    def _map_metadata(self, game: dict, result: ScraperResult) -> None:
        """Populate *result* metadata fields from *game* dict."""
        result.name = game.get("name") or ""
        result.description = game.get("summary") or ""

        # developer / publisher from involved_companies
        for entry in game.get("involved_companies") or []:
            company_name = (entry.get("company") or {}).get("name") or ""
            if entry.get("developer") and not result.developer:
                result.developer = company_name
            if entry.get("publisher") and not result.publisher:
                result.publisher = company_name

        # genre
        genres = game.get("genres") or []
        if genres:
            result.genre = genres[0].get("name") or ""

        # players from first game_mode slug
        modes = game.get("game_modes") or []
        if modes:
            slug = modes[0].get("slug") or ""
            result.players = _GAME_MODE_PLAYERS.get(slug, "")

        # release_date from Unix timestamp
        ts = game.get("first_release_date")
        if ts is not None:
            try:
                result.release_date = datetime.fromtimestamp(
                    int(ts), tz=timezone.utc
                ).strftime("%Y%m%dT%H%M%S")
            except (ValueError, OSError, OverflowError):
                pass

        # rating: IGDB is 0–100; normalise to 0.0–1.0
        raw_rating = game.get("rating")
        if raw_rating is not None:
            try:
                result.rating = float(raw_rating) / 100.0
            except (TypeError, ValueError):
                pass

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    def _download_media(
        self,
        game: dict,
        result: ScraperResult,
        rom_path: Path,
        media_dir: Path,
    ) -> None:
        """Download cover and screenshot images from IGDB CDN."""
        stem = rom_path.stem

        # thumbnail (cover)
        cover = game.get("cover") or {}
        cover_url_raw = cover.get("url") or ""
        if cover_url_raw:
            cover_url = _igdb_image_url(cover_url_raw, "cover_big")
            ext = Path(cover_url.split("?")[0]).suffix.lstrip(".") or "jpg"
            dest = media_dir / "covers" / f"{stem}.{ext}"
            if _download_file(self._session, cover_url, dest):
                result.thumbnail_path = dest

        # screenshot
        screenshots = game.get("screenshots") or []
        if screenshots:
            ss_url_raw = screenshots[0].get("url") or ""
            if ss_url_raw:
                ss_url = _igdb_image_url(ss_url_raw, "screenshot_big")
                ext = Path(ss_url.split("?")[0]).suffix.lstrip(".") or "jpg"
                dest = media_dir / "screenshots" / f"{stem}.{ext}"
                if _download_file(self._session, ss_url, dest):
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
