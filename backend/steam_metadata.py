"""Steam Store API metadata fetcher.

Fetches rich metadata for a single Steam app from the Steam Store API.
Pure function — no QObject dependency.

Public API:
    fetch_steam_metadata(app_id: str) -> GameMetadata | None
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from backend.metadata_gamelist import GameMetadata

logger = logging.getLogger(__name__)

_STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails/?appids={app_id}"
_REQUEST_TIMEOUT = 5  # seconds
_USER_AGENT = "htpcstation/1.0"

# Player category descriptions to look for (by description string, not ID)
_PLAYER_CATEGORIES = {
    "Single-player",
    "Multi-player",
    "Co-op",
    "Online Co-op",
    "Online PvP",
    "Local Co-op",
    "Local PvP",
}


def fetch_steam_metadata(app_id: str) -> Optional[GameMetadata]:
    """Fetch metadata for a single Steam app from the Steam Store API.

    Calls ``https://store.steampowered.com/api/appdetails/?appids={app_id}``,
    parses the JSON response, and returns a :class:`GameMetadata` instance.

    Returns ``None`` on any error (network, parse, API failure).
    Logs warnings on failure.

    Args:
        app_id: The Steam application ID as a string (e.g. "440").

    Returns:
        A populated :class:`GameMetadata` instance, or ``None`` on failure.
    """
    url = _STEAM_APPDETAILS_URL.format(app_id=app_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        logger.warning("fetch_steam_metadata: network error for app_id=%s: %s", app_id, exc)
        return None
    except OSError as exc:
        logger.warning("fetch_steam_metadata: OS error for app_id=%s: %s", app_id, exc)
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("fetch_steam_metadata: JSON parse error for app_id=%s: %s", app_id, exc)
        return None

    # The API returns { "<app_id>": { "success": bool, "data": {...} } }
    app_entry = payload.get(str(app_id))
    if not app_entry:
        logger.warning(
            "fetch_steam_metadata: no entry for app_id=%s in response", app_id
        )
        return None

    if not app_entry.get("success", False):
        logger.warning(
            "fetch_steam_metadata: API returned success=false for app_id=%s", app_id
        )
        return None

    data = app_entry.get("data", {})
    if not data:
        logger.warning(
            "fetch_steam_metadata: empty data object for app_id=%s", app_id
        )
        return None

    try:
        return _parse_app_data(app_id, data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "fetch_steam_metadata: failed to parse data for app_id=%s: %s", app_id, exc
        )
        return None


def _parse_app_data(app_id: str, data: dict) -> GameMetadata:
    """Parse the ``data`` object from the Steam Store API response.

    Args:
        app_id: The Steam application ID (used as-is for ``GameMetadata.app_id``).
        data: The ``data`` dict from the API response.

    Returns:
        A populated :class:`GameMetadata` instance.
    """
    name = data.get("name", "")

    description = data.get("short_description", "")

    # developers: list of strings → join with ", "
    developers = data.get("developers", [])
    developer = ", ".join(developers) if developers else ""

    # publishers: list of strings → join with ", "
    publishers = data.get("publishers", [])
    publisher = ", ".join(publishers) if publishers else ""

    # genres: list of {"id": ..., "description": ...} → join descriptions with ", "
    genres = data.get("genres", [])
    genre = ", ".join(g.get("description", "") for g in genres if g.get("description"))

    # categories: list of {"id": ..., "description": ...}
    # Look for known player category descriptions
    categories = data.get("categories", [])
    matched_players = [
        c.get("description", "")
        for c in categories
        if c.get("description", "") in _PLAYER_CATEGORIES
    ]
    players = ", ".join(matched_players)

    # release_date: {"coming_soon": bool, "date": "Oct 10, 2007"}
    release_date_obj = data.get("release_date", {})
    release_date = release_date_obj.get("date", "") if release_date_obj else ""

    # metacritic: {"score": 96, "url": "..."} → divide by 100 for 0.0-1.0 scale
    metacritic = data.get("metacritic")
    if metacritic and isinstance(metacritic.get("score"), (int, float)):
        rating = metacritic["score"] / 100.0
    else:
        rating = 0.0

    return GameMetadata(
        name=name,
        app_id=app_id,
        description=description,
        developer=developer,
        publisher=publisher,
        genre=genre,
        players=players,
        release_date=release_date,
        rating=rating,
        image_path="",  # artwork is handled by the existing system
    )
