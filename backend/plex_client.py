"""Plex Media Server API client.

A plain Python class (not a QObject) that wraps Plex HTTP API calls.
All methods are safe to call from worker threads.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds


class PlexClient:
    """HTTP client for the Plex Media Server API.

    All requests include the X-Plex-Token header and Accept: application/json.
    Connection errors are handled gracefully — methods return empty results and
    log a warning rather than raising.
    """

    def __init__(self, server_url: str, token: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Plex-Token": token,
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_identity(self) -> dict:
        """GET /identity — returns server identity including machineIdentifier."""
        data = self._get("/identity")
        if data is None:
            return {}
        return data.get("MediaContainer", {})

    def get_libraries(self) -> list[dict]:
        """GET /library/sections — returns library list.

        Filters to type='movie' and type='show' only.
        """
        data = self._get("/library/sections")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        directories = container.get("Directory", [])
        return [
            d for d in directories
            if isinstance(d, dict) and d.get("type") in ("movie", "show", "artist")
        ]

    def get_library_items(
        self,
        section_key: str,
        start: int = 0,
        size: int = 50,
        sort: str = "",
        genre: str = "",
        content_rating: str = "",
    ) -> tuple[list[dict], int]:
        """GET /library/sections/<key>/all — paginated.

        Returns (items, totalSize).
        Uses X-Plex-Container-Start and X-Plex-Container-Size query params.
        Optional sort (e.g. 'titleSort:asc'), genre (genre key ID), and
        content_rating (comma-separated MPAA/TV ratings) params.
        """
        params: dict = {
            "X-Plex-Container-Start": start,
            "X-Plex-Container-Size": size,
        }
        if sort:
            params["sort"] = sort
        if genre:
            params["genre"] = genre
        if content_rating:
            params["contentRating"] = content_rating
        data = self._get(f"/library/sections/{section_key}/all", params=params)
        if data is None:
            return [], 0
        container = data.get("MediaContainer", {})
        total = int(container.get("totalSize", container.get("size", 0)))
        items = container.get("Metadata", [])
        return items, total

    def get_genres(self, section_key: str) -> list[dict]:
        """GET /library/sections/<key>/genre — returns list of {key, title}."""
        data = self._get(f"/library/sections/{section_key}/genre")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        directories = container.get("Directory", [])
        return [
            {"key": str(d.get("key", "")), "title": d.get("title", "")}
            for d in directories
            if isinstance(d, dict)
        ]

    def get_metadata(self, rating_key: str) -> dict:
        """GET /library/metadata/<ratingKey> — full metadata for one item."""
        data = self._get(f"/library/metadata/{rating_key}")
        if data is None:
            return {}
        container = data.get("MediaContainer", {})
        metadata_list = container.get("Metadata", [])
        if metadata_list:
            return metadata_list[0]
        return {}

    def get_children(self, rating_key: str) -> list[dict]:
        """GET /library/metadata/<ratingKey>/children.

        Returns seasons of a show, or episodes of a season.
        """
        data = self._get(f"/library/metadata/{rating_key}/children")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        return container.get("Metadata", [])

    def get_on_deck(self) -> list[dict]:
        """GET /library/onDeck — continue watching items."""
        data = self._get("/library/onDeck")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        return container.get("Metadata", [])

    def get_poster_url(self, thumb_path: str) -> str:
        """Build full authenticated poster URL from a thumb path.

        Example thumb_path: '/library/metadata/126522/thumb/1771639193'
        Returns: http://<server>:32400<thumb_path>?X-Plex-Token=<token>
        """
        return f"{self._server_url}{thumb_path}?X-Plex-Token={self._token}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Perform a GET request and return the parsed JSON, or None on error."""
        url = f"{self._server_url}{path}"
        try:
            response = self._session.get(url, params=params, timeout=_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Plex connection error for %s: %s", url, exc)
        except requests.exceptions.Timeout:
            logger.warning("Plex request timed out for %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.warning("Plex HTTP error for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plex unexpected error for %s: %s", url, exc)
        return None
