"""Poster image cache for Plex Media Server artwork.

Downloads poster images from the Plex server and caches them locally.
Thread-safe — may be called from multiple worker threads.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 15  # seconds


class PosterCache:
    """Downloads and caches Plex poster images locally.

    Cache directory: ***REMOVED***.config/htpcstation/poster_cache/
    Filenames: SHA256 hash of the thumb_path + '.jpg'

    Thread-safe: a per-path lock prevents duplicate downloads when multiple
    threads request the same poster simultaneously.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Lock protecting the per-path download locks dict
        self._locks_lock = threading.Lock()
        self._path_locks: dict[str, threading.Lock] = {}

    def get_poster(self, plex_client: object, thumb_path: str) -> str:
        """Return a file:// URL to the cached poster.

        Downloads from the Plex server if not already cached.
        Returns an empty string if the download fails or thumb_path is empty.

        Args:
            plex_client: A PlexClient instance (typed as object to avoid circular import).
            thumb_path: Plex thumb path, e.g. '/library/metadata/126522/thumb/1771639193'.
        """
        if not thumb_path:
            return ""

        local_path = self._cache_path(thumb_path)

        # Fast path: already cached
        if local_path.exists():
            return local_path.as_uri()

        # Acquire a per-path lock to avoid duplicate downloads
        path_lock = self._get_path_lock(thumb_path)
        with path_lock:
            # Re-check after acquiring lock (another thread may have downloaded it)
            if local_path.exists():
                return local_path.as_uri()

            url = plex_client.get_poster_url(thumb_path)  # type: ignore[union-attr]
            try:
                with requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT) as response:
                    response.raise_for_status()
                    with open(local_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                logger.debug("Cached poster: %s -> %s", thumb_path, local_path)
                return local_path.as_uri()
            except requests.exceptions.ConnectionError as exc:
                logger.warning("Poster download connection error for %s: %s", thumb_path, exc)
            except requests.exceptions.Timeout:
                logger.warning("Poster download timed out for %s", thumb_path)
            except requests.exceptions.HTTPError as exc:
                logger.warning("Poster download HTTP error for %s: %s", thumb_path, exc)
            except OSError as exc:
                logger.warning("Poster write error for %s: %s", local_path, exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Poster download unexpected error for %s: %s", thumb_path, exc)

            # Clean up partial file on failure
            if local_path.exists():
                try:
                    local_path.unlink()
                except OSError:
                    pass

        return ""

    def _cache_path(self, thumb_path: str) -> Path:
        """Return the deterministic local cache path for a given thumb_path.

        Uses SHA256 hash of the thumb_path as the filename to avoid
        filesystem-unfriendly characters.
        """
        digest = hashlib.sha256(thumb_path.encode()).hexdigest()
        return self._cache_dir / f"{digest}.jpg"

    def _get_path_lock(self, thumb_path: str) -> threading.Lock:
        """Return (creating if needed) the per-path download lock."""
        with self._locks_lock:
            if thumb_path not in self._path_locks:
                self._path_locks[thumb_path] = threading.Lock()
            return self._path_locks[thumb_path]
