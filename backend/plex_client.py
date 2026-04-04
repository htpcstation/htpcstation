"""Plex Media Server API client.

A plain Python class (not a QObject) that wraps Plex HTTP API calls.
All methods are safe to call from worker threads.
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_RETRY_BACKOFF = [1.0, 3.0]  # seconds between retries


class PlexErrorType(enum.Enum):
    NONE = "none"
    AUTH = "auth"           # 401, 403
    NOT_FOUND = "not_found" # 404
    SERVER = "server"       # 500-599
    NETWORK = "network"     # ConnectionError, Timeout
    UNKNOWN = "unknown"     # anything else


def _get_device_name() -> str:
    import socket
    try:
        return socket.gethostname()
    except Exception:
        return "htpcstation"


class PlexClient:
    """HTTP client for the Plex Media Server API.

    All requests include the X-Plex-Token header and Accept: application/json.
    Connection errors are handled gracefully — methods return empty results and
    log a warning rather than raising.
    """

    def __init__(self, server_url: str, token: str, client_id: str = "") -> None:
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._client_id = client_id or "htpcstation"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Plex-Token": token,
                "Accept": "application/json",
                "X-Plex-Client-Identifier": self._client_id,
                "X-Plex-Product": "HTPC Station",
                "X-Plex-Version": "1.0.0",
                "X-Plex-Platform": "Linux",
                "X-Plex-Device": "PC",
                "X-Plex-Device-Name": _get_device_name(),
            }
        )
        self._last_error: PlexErrorType = PlexErrorType.NONE
        self._on_error: Optional[Callable[[PlexErrorType], None]] = None

        # Increase connection pool size to handle parallel EPG page fetches
        # (default is 10; Live TV fetches up to 10 pages concurrently).
        adapter = requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=12)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def set_error_callback(self, callback: Callable[[PlexErrorType], None]) -> None:
        """Register a callback invoked whenever a request fails.

        Called on the worker thread — callback must be thread-safe (e.g. emit a Qt signal).
        """
        self._on_error = callback

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

    def get_metadata(self, rating_key: str, include_markers: bool = False) -> dict:
        """GET /library/metadata/<ratingKey> — full metadata for one item."""
        params = {}
        if include_markers:
            params["includeMarkers"] = 1
        data = self._get(f"/library/metadata/{rating_key}", params=params or None)
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

    def get_hubs(self, rating_key: str) -> list[dict]:
        """GET /hubs/metadata/<ratingKey> — returns hub sections."""
        data = self._get(f"/hubs/metadata/{rating_key}?count=999")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        return container.get("Hub", [])

    def get_on_deck(self) -> list[dict]:
        """GET /hubs/home/continueWatching — continue watching items (cross-library).

        Returns the Metadata array. Falls back to empty list on error.
        Previously used /library/onDeck (legacy endpoint).
        """
        data = self._get("/hubs/home/continueWatching")
        if data is None:
            return []
        container = data.get("MediaContainer", {})
        # The hub endpoint wraps items in a Hub list; the first hub contains Metadata.
        hubs = container.get("Hub", [])
        if hubs:
            return hubs[0].get("Metadata", [])
        # Fallback: some server versions return Metadata directly
        return container.get("Metadata", [])

    def get_playlists(self) -> list[dict]:
        """GET /playlists — returns all playlists."""
        data = self._get("/playlists")
        if data is None:
            return []
        return data.get("MediaContainer", {}).get("Metadata", [])

    def get_playlist_items(self, rating_key: str, limit: int = 0) -> list[dict]:
        """GET /playlists/{ratingKey}/items — returns playlist tracks.

        If *limit* > 0, only fetch that many items (useful for probing
        whether a smart playlist actually returns tracks).
        """
        url = f"/playlists/{rating_key}/items"
        if limit > 0:
            url += f"?X-Plex-Container-Size={limit}"
        data = self._get(url)
        if data is None:
            return []
        return data.get("MediaContainer", {}).get("Metadata", [])

    def get_stream_url(self, rating_key: str) -> tuple[str, int]:
        """Return (direct_stream_url, view_offset_ms) for the first media part.

        view_offset_ms is 0 if no resume position is stored.
        Returns ("", 0) if the item has no media parts or the request fails.
        """
        data = self.get_metadata(rating_key)
        media = data.get("Media", [])
        if not media:
            return ("", 0)
        parts = media[0].get("Part", [])
        if not parts:
            return ("", 0)
        part_key = parts[0].get("key", "")
        if not part_key:
            return ("", 0)
        view_offset = int(data.get("viewOffset", 0) or 0)
        url = f"{self._server_url}{part_key}?X-Plex-Token={self._token}"
        return (url, view_offset)

    def get_poster_url(self, thumb_path: str) -> str:
        """Build full authenticated poster URL from a thumb path.

        Example thumb_path: '/library/metadata/126522/thumb/1771639193'
        Returns: http://<server>:32400<thumb_path>?X-Plex-Token=<token>
        """
        return f"{self._server_url}{thumb_path}?X-Plex-Token={self._token}"

    def report_timeline(
        self,
        rating_key: str,
        state: str,
        time_ms: int,
        duration_ms: int,
        session_id: str,
    ) -> None:
        """POST /:/timeline — playback heartbeat. Fire-and-forget; errors are ignored.

        state: 'playing' | 'paused' | 'stopped' | 'buffering'
        time_ms: current position in milliseconds
        duration_ms: total duration in milliseconds
        session_id: per-session UUID (stable for the lifetime of one playback)
        """
        try:
            self._session.get(
                f"{self._server_url}/:/timeline",
                params={
                    "ratingKey": rating_key,
                    "key": f"/library/metadata/{rating_key}",
                    "state": state,
                    "time": time_ms,
                    "duration": duration_ms,
                    "identifier": "com.plexapp.plugins.library",
                    "X-Plex-Session-Identifier": session_id,
                },
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            pass  # timeline reports are best-effort; never raise

    def persist_stream_selection(
        self,
        part_id: int,
        audio_stream_id: Optional[int] = None,
        subtitle_stream_id: Optional[int] = None,
    ) -> None:
        """PUT /library/parts/{partId} — persist audio/subtitle track selection.

        Writes the user's track choice to Plex metadata so it syncs to all
        other Plex clients and survives resume.

        audio_stream_id:    Plex stream ID for the audio track (from Media.Part.Stream[n].id)
        subtitle_stream_id: Plex stream ID for the subtitle track (0 = disabled)
        allParts=1 applies the selection to all media versions (1080p + 4K, etc.)
        """
        if not part_id:
            return
        params: dict = {"allParts": 1}
        if audio_stream_id is not None:
            params["audioStreamID"] = audio_stream_id
        if subtitle_stream_id is not None:
            params["subtitleStreamID"] = subtitle_stream_id
        try:
            url = f"{self._server_url}/library/parts/{part_id}"
            self._session.put(url, params=params, timeout=_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist_stream_selection failed for part %d: %s", part_id, exc)

    def mark_played(self, rating_key: str) -> None:
        """PUT /:/scrobble — mark item as watched.

        Sets viewCount and lastViewedAt on the server.
        identifier must be 'com.plexapp.plugins.library'.
        """
        try:
            self._session.get(
                f"{self._server_url}/:/scrobble",
                params={
                    "key": rating_key,
                    "identifier": "com.plexapp.plugins.library",
                },
                timeout=_TIMEOUT,
            )
        except Exception:  # noqa: BLE001
            logger.warning("mark_played failed for ratingKey=%s", rating_key)

    def mark_unplayed(self, rating_key: str) -> None:
        """PUT /:/unscrobble — mark item as unwatched.

        Clears viewCount and lastViewedAt on the server.
        """
        try:
            self._session.get(
                f"{self._server_url}/:/unscrobble",
                params={
                    "key": rating_key,
                    "identifier": "com.plexapp.plugins.library",
                },
                timeout=_TIMEOUT,
            )
        except Exception:  # noqa: BLE001
            logger.warning("mark_unplayed failed for ratingKey=%s", rating_key)

    def get_transient_token(self) -> str:
        """GET /security/token — returns a short-lived delegation token.

        Use this token in stream URLs passed to MPV instead of the long-lived
        user token. The long-lived token never appears in MPV logs or process args.
        Returns "" on failure (caller should fall back to the main token).
        """
        data = self._get("/security/token", params={"type": "delegation", "scope": "all"})
        if data is None:
            return ""
        return data.get("MediaContainer", {}).get("token", "")

    def get_markers(self, metadata: dict) -> dict:
        """Extract intro and credits marker timestamps from a metadata dict.

        Returns:
            {
                "intro_start_ms": int,   # 0 if no intro marker
                "intro_end_ms": int,     # 0 if no intro marker
                "credits_start_ms": int, # 0 if no credits marker
            }
        Marker timestamps from Plex are in milliseconds.
        Marker types: "intro", "credits", "commercial", "bookmark", "resume".
        """
        result = {"intro_start_ms": 0, "intro_end_ms": 0, "credits_start_ms": 0}
        markers = metadata.get("Marker", [])
        for marker in markers:
            marker_type = marker.get("type", "")
            start = int(marker.get("startTimeOffset", 0) or 0)
            end = int(marker.get("endTimeOffset", 0) or 0)
            if marker_type == "intro":
                result["intro_start_ms"] = start
                result["intro_end_ms"] = end
            elif marker_type == "credits":
                result["credits_start_ms"] = start
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Perform a GET request and return the parsed JSON, or None on error.

        Retries up to _MAX_RETRIES times for transient errors (429, 5xx, network).
        Permanent errors (401, 403, 404) are not retried.
        On any error, sets _last_error and calls _on_error callback if registered.
        Return type is unchanged — all callers continue to work without modification.
        """
        url = f"{self._server_url}{path}"
        last_exc = None

        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                delay = _RETRY_BACKOFF[attempt - 1]
                logger.info("Plex retry %d/%d for %s (waiting %.1fs)", attempt, _MAX_RETRIES, url, delay)
                time.sleep(delay)
            try:
                response = self._session.get(url, params=params, timeout=_TIMEOUT)

                # Check for Retry-After header on 429
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", _RETRY_BACKOFF[0]))
                    logger.warning("Plex rate limited for %s, retry after %.1fs", url, retry_after)
                    if attempt < _MAX_RETRIES:
                        time.sleep(min(retry_after, 30.0))
                        continue
                    self._set_error(PlexErrorType.SERVER)
                    return None

                response.raise_for_status()
                self._last_error = PlexErrorType.NONE
                return response.json()

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning("Plex HTTP error for %s: %s", url, exc)
                if status in (401, 403):
                    self._set_error(PlexErrorType.AUTH)
                    return None  # permanent — no retry
                if status == 404:
                    self._set_error(PlexErrorType.NOT_FOUND)
                    return None  # permanent — no retry
                if status in _TRANSIENT_STATUS_CODES:
                    last_exc = exc
                    continue  # retry
                self._set_error(PlexErrorType.SERVER)
                return None

            except requests.exceptions.ConnectionError as exc:
                logger.warning("Plex connection error for %s: %s", url, exc)
                last_exc = exc
                # retry

            except requests.exceptions.Timeout:
                logger.warning("Plex request timed out for %s", url)
                last_exc = Exception("timeout")
                # retry

            except Exception as exc:  # noqa: BLE001
                logger.warning("Plex unexpected error for %s: %s", url, exc)
                self._set_error(PlexErrorType.UNKNOWN)
                return None

        # All retries exhausted
        logger.warning("Plex request failed after %d retries for %s", _MAX_RETRIES, url)
        self._set_error(PlexErrorType.NETWORK)
        return None

    def _set_error(self, error_type: PlexErrorType) -> None:
        """Record the error type and invoke the callback if registered."""
        self._last_error = error_type
        if self._on_error is not None:
            try:
                self._on_error(error_type)
            except Exception:  # noqa: BLE001
                pass
