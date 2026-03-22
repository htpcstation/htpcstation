"""Moonlight artwork cache and Steam Store lookup helper.

Resolves artwork for Moonlight games by:
1. Checking for user-provided images in a local cache directory
2. Falling back to Steam CDN posters by searching the Steam Store API
3. Downloading and caching the poster image locally for offline reuse

Cache directory: ***REMOVED***.config/htpcstation/moonlight_artwork/
Metadata index:  moonlight_artwork_index.json

Public API:
    slugify_app_name(app_name) -> str
    get_artwork_path(app_name) -> Optional[Path]
    refresh_artwork(app_name) -> Optional[Path]
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STEAM_SEARCH_URL = (
    "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=US"
)
_STEAM_POSTER_URL = (
    "https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900_2x.jpg"
)
_DOWNLOAD_TIMEOUT = 5  # seconds
_METADATA_FILENAME = "moonlight_artwork_index.json"
_OVERRIDE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")

# ---------------------------------------------------------------------------
# Cache directory helper (monkeypatchable in tests)
# ---------------------------------------------------------------------------


def _get_artwork_dir() -> Path:
    """Return the artwork cache directory, creating it if needed.

    Also creates the ``custom/`` subdirectory so users can discover it.

    Respects XDG_CONFIG_HOME.  Monkeypatch this function in tests to redirect
    all I/O to a temporary directory.
    """
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    artwork_dir = config_home / "htpcstation" / "moonlight_artwork"
    artwork_dir.mkdir(parents=True, exist_ok=True)
    custom_dir = artwork_dir / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    return artwork_dir


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


def slugify_app_name(app_name: str) -> str:
    """Convert *app_name* to a filesystem-safe slug.

    - Lowercase
    - Replace non-alphanumeric characters with hyphens
    - Collapse multiple hyphens
    - Strip leading/trailing hyphens
    - Fallback to ``app`` + short hash if the result is empty
    """
    slug = app_name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    if not slug:
        short_hash = hashlib.md5(app_name.encode()).hexdigest()[:8]  # noqa: S324
        slug = f"app{short_hash}"
    return slug


# ---------------------------------------------------------------------------
# Metadata index helpers
# ---------------------------------------------------------------------------


def _metadata_path(artwork_dir: Path) -> Path:
    return artwork_dir / _METADATA_FILENAME


def _load_metadata(artwork_dir: Path) -> dict:
    """Load the metadata index from disk.  Returns an empty dict on any error."""
    path = _metadata_path(artwork_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("moonlight_artwork: failed to load metadata index: %s", exc)
        return {}


def _save_metadata(artwork_dir: Path, metadata: dict) -> None:
    """Atomically write *metadata* to the index file."""
    path = _metadata_path(artwork_dir)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=artwork_dir, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        os.replace(tmp_name, path)
    except OSError as exc:
        logger.warning("moonlight_artwork: failed to save metadata index: %s", exc)
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Manual override detection
# ---------------------------------------------------------------------------


def _find_override(artwork_dir: Path, slug: str) -> Optional[Path]:
    """Return the first file matching ``custom/<slug>.<ext>`` for known image extensions.

    Only looks in the ``custom/`` subdirectory of *artwork_dir*.  Files in the
    main directory are never treated as overrides — they are auto-downloaded
    cache files managed by the app.

    Returns ``None`` if no override file is found.
    """
    custom_dir = artwork_dir / "custom"
    for ext in _OVERRIDE_EXTENSIONS:
        candidate = custom_dir / f"{slug}.{ext}"
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Steam Store helpers
# ---------------------------------------------------------------------------


def _steam_search(app_name: str) -> Optional[int]:
    """Search the Steam Store for *app_name* and return the first result's app ID.

    Returns ``None`` if no results are found or the request fails.
    """
    term = urllib.parse.quote(app_name)
    url = _STEAM_SEARCH_URL.format(term=term)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "htpcstation/1.0"})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("moonlight_artwork: Steam search failed for '%s': %s", app_name, exc)
        return None

    items = data.get("items", [])
    if not items:
        return None
    return int(items[0]["id"])


def _ext_from_content_type(content_type: str) -> str:
    """Derive a file extension from an HTTP Content-Type header value.

    Defaults to ``jpg`` for unknown or JPEG types.
    """
    ct = content_type.lower().split(";")[0].strip()
    mapping = {
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
    }
    return mapping.get(ct, "jpg")


def _download_poster(app_id: int, dest_path: Path) -> Optional[Path]:
    """Download the Steam CDN poster for *app_id* and save it to *dest_path*.

    The caller is responsible for choosing the destination path (including
    extension).  Returns *dest_path* on success, ``None`` on failure.
    """
    url = _STEAM_POSTER_URL.format(app_id=app_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "htpcstation/1.0"})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            ext = _ext_from_content_type(content_type)
            # Honour the actual content type extension
            actual_dest = dest_path.with_suffix(f".{ext}")
            # Write atomically: temp file → rename
            tmp_fd, tmp_name = tempfile.mkstemp(dir=dest_path.parent, suffix=f".{ext}.tmp")
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                os.replace(tmp_name, actual_dest)
            except OSError:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        logger.debug("moonlight_artwork: downloaded poster for app_id=%d -> %s", app_id, actual_dest)
        return actual_dest
    except (urllib.error.URLError, OSError) as exc:
        logger.warning(
            "moonlight_artwork: failed to download poster for app_id=%d: %s", app_id, exc
        )
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_artwork_path(app_name: str) -> Optional[Path]:
    """Return a local file path for the artwork if available, else ``None``.

    Checks for manual overrides first, then consults the metadata index.
    Does **not** perform any network requests.
    """
    artwork_dir = _get_artwork_dir()
    slug = slugify_app_name(app_name)

    # 1. Manual override: any custom/<slug>.<ext> file always takes priority.
    #    Files in custom/ are unambiguously user-provided — no metadata check needed.
    override = _find_override(artwork_dir, slug)
    if override is not None:
        metadata = _load_metadata(artwork_dir)
        entry = metadata.get(slug, {})
        if entry.get("source") != "manual" or entry.get("filename") != override.name:
            entry.update(
                {
                    "app_name": app_name,
                    "slug": slug,
                    "steam_app_id": entry.get("steam_app_id"),
                    "source": "manual",
                    "filename": override.name,
                    "updated_at": _now_utc(),
                }
            )
            metadata[slug] = entry
            _save_metadata(artwork_dir, metadata)
        return override

    # 2. Cached metadata + file
    metadata = _load_metadata(artwork_dir)
    entry = metadata.get(slug)
    if entry and entry.get("filename"):
        cached_file = artwork_dir / entry["filename"]
        if cached_file.exists():
            return cached_file

    return None


def refresh_artwork(app_name: str) -> Optional[Path]:
    """Ensure artwork exists locally (download if needed) and return the path.

    Lookup flow:
    1. Check custom/<slug>.<ext> — if found, return it (source="manual")
    2. Check metadata index + cached file in main dir — if found, return it
    3. Search Steam Store → download poster to main dir → cache
    4. If Steam fails → record ``source="none"`` in metadata, return ``None``
    """
    artwork_dir = _get_artwork_dir()
    slug = slugify_app_name(app_name)

    # 1. Manual override: any custom/<slug>.<ext> file always takes priority.
    #    Files in custom/ are unambiguously user-provided — no metadata check needed.
    override = _find_override(artwork_dir, slug)
    if override is not None:
        metadata = _load_metadata(artwork_dir)
        entry = metadata.get(slug, {})
        if entry.get("source") != "manual" or entry.get("filename") != override.name:
            entry.update(
                {
                    "app_name": app_name,
                    "slug": slug,
                    "steam_app_id": entry.get("steam_app_id"),
                    "source": "manual",
                    "filename": override.name,
                    "updated_at": _now_utc(),
                }
            )
            metadata[slug] = entry
            _save_metadata(artwork_dir, metadata)
        return override

    # 2. Cached metadata + file
    metadata = _load_metadata(artwork_dir)
    entry = metadata.get(slug)
    if entry and entry.get("filename"):
        cached_file = artwork_dir / entry["filename"]
        if cached_file.exists():
            return cached_file

    # 3. Steam Store search + download
    app_id = _steam_search(app_name)
    if app_id is not None:
        dest_stem = artwork_dir / slug  # extension determined by content-type
        downloaded = _download_poster(app_id, dest_stem.with_suffix(".jpg"))
        if downloaded is not None:
            entry = {
                "app_name": app_name,
                "slug": slug,
                "steam_app_id": app_id,
                "source": "steam",
                "filename": downloaded.name,
                "updated_at": _now_utc(),
            }
            metadata[slug] = entry
            _save_metadata(artwork_dir, metadata)
            return downloaded

    # 4. No results or download failed
    entry = {
        "app_name": app_name,
        "slug": slug,
        "steam_app_id": None,
        "source": "none",
        "filename": None,
        "updated_at": _now_utc(),
    }
    metadata[slug] = entry
    _save_metadata(artwork_dir, metadata)
    return None
