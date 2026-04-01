"""Steam ACF/VDF file parser and game discovery.

Parses Steam's appmanifest_*.acf files (Valve Data Format) and discovers
installed games from the local Steam library.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from backend.steam_config import get_steam_dir
from backend.steam_models import SteamGame

logger = logging.getLogger(__name__)

# Default Steam library paths to search (in priority order)
_DEFAULT_SEARCH_PATHS: list[Path] = [
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps",  # Flatpak
    Path.home() / ".steam/steam/steamapps",                                          # native
    Path.home() / ".local/share/Steam/steamapps",                                    # native alt
]

# AppIDs and name patterns that identify non-game entries to skip
_SKIP_APPID = {"228980"}  # Steamworks Common Redistributables
_SKIP_NAME_CONTAINS = ("Steamworks", "Proton")
_SKIP_NAME_STARTSWITH = ("Steam Linux Runtime",)
_REQUIRED_STATE_FLAGS = "4"  # fully installed


# ---------------------------------------------------------------------------
# ACF/VDF parser
# ---------------------------------------------------------------------------


def parse_acf(filepath: Path) -> Optional[dict]:
    """Parse a single ACF file (Valve Data Format) into a Python dict.

    VDF format example::

        "AppState"
        {
            "appid"     "440"
            "name"      "Team Fortress 2"
            "depots"
            {
                "branches"
                {
                    "public"    "1"
                }
            }
        }

    Returns the top-level dict (e.g. ``{"AppState": {"appid": "440", ...}}``)
    or ``None`` if the file cannot be read or parsed.
    """
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("parse_acf: cannot read %s: %s", filepath, exc)
        return None

    tokens = _tokenize(text)
    if not tokens:
        return None

    try:
        result, _ = _parse_block(tokens, 0)
        return result
    except (IndexError, ValueError) as exc:
        logger.warning("parse_acf: failed to parse %s: %s", filepath, exc)
        return None


def _tokenize(text: str) -> list[str]:
    """Split VDF text into a flat list of quoted strings and braces."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
        elif ch == '"':
            # Quoted string — scan to closing quote, handling backslash escapes
            i += 1
            buf: list[str] = []
            while i < n:
                c = text[i]
                if c == '\\' and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            tokens.append("".join(buf))
        elif ch in "{}":
            tokens.append(ch)
            i += 1
        elif ch == '/':
            # C++ style line comment
            if i + 1 < n and text[i + 1] == '/':
                while i < n and text[i] != '\n':
                    i += 1
            else:
                i += 1
        else:
            i += 1
    return tokens


def _parse_block(tokens: list[str], pos: int) -> tuple[dict, int]:
    """Recursively parse a VDF block starting at *pos*.

    Expects the opening ``{`` to have already been consumed (or to be at the
    very start of the file for the top-level block).  Returns ``(dict, new_pos)``
    where *new_pos* is the index after the closing ``}``.
    """
    result: dict = {}
    n = len(tokens)
    while pos < n:
        token = tokens[pos]
        if token == "}":
            return result, pos + 1
        # token is a key
        key = token
        pos += 1
        if pos >= n:
            break
        next_token = tokens[pos]
        if next_token == "{":
            # Nested block
            pos += 1
            value, pos = _parse_block(tokens, pos)
            result[key] = value
        else:
            # Plain string value
            result[key] = next_token
            pos += 1
    return result, pos


# ---------------------------------------------------------------------------
# Artwork resolution
# ---------------------------------------------------------------------------


_STEAM_CDN_POSTER = "https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900_2x.jpg"
_OVERRIDE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")
_DOWNLOAD_TIMEOUT = 5  # seconds


def _resolve_artwork(steamapps_path: Path, app_id: str) -> str:
    """Return the best available poster image as a local file path.

    Resolution order:
    1. Custom override in artwork_custom/<app_id>.<ext>
    2. HTPC Station scraped cache in artwork_scraped/<app_id>.jpg
    3. Steam's own local cache (copied to scraped cache)
    4. Download from CDN (saved to scraped cache)
    5. Empty string if all else fails

    Never returns a URL — always a local path or empty string.
    """
    steam_dir = get_steam_dir()

    # 1. Check custom override first
    custom_dir = steam_dir / "artwork_custom"
    for ext in _OVERRIDE_EXTENSIONS:
        candidate = custom_dir / f"{app_id}.{ext}"
        if candidate.is_file():
            return str(candidate)

    # 2. Check HTPC Station scraped cache
    scraped_path = steam_dir / "artwork_scraped" / f"{app_id}.jpg"
    if scraped_path.is_file():
        return str(scraped_path)

    # 3. Check Steam's own local cache and copy to scraped cache
    steam_root = steamapps_path.parent  # e.g. ~/.local/share/Steam/
    steam_cache_dir = steam_root / "appcache" / "librarycache" / app_id
    for filename in ("library_600x900.jpg", "header.jpg"):
        candidate = steam_cache_dir / filename
        if candidate.is_file():
            try:
                shutil.copy2(candidate, scraped_path)
                return str(scraped_path)
            except OSError as exc:
                logger.warning(
                    "_resolve_artwork: failed to copy Steam cache for app_id=%s: %s",
                    app_id, exc,
                )
                return str(candidate)

    # 4. Download from CDN and save atomically to scraped cache
    url = _STEAM_CDN_POSTER.format(app_id=app_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "htpcstation/1.0"})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            scraped_dir = steam_dir / "artwork_scraped"
            tmp_fd, tmp_name = tempfile.mkstemp(dir=scraped_dir, suffix=".jpg.tmp")
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                os.replace(tmp_name, scraped_path)
            except OSError:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        logger.debug("_resolve_artwork: downloaded poster for app_id=%s -> %s", app_id, scraped_path)
        return str(scraped_path)
    except (urllib.error.URLError, OSError) as exc:
        logger.warning(
            "_resolve_artwork: failed to download poster for app_id=%s: %s", app_id, exc
        )
        return ""


# ---------------------------------------------------------------------------
# Game discovery
# ---------------------------------------------------------------------------


def discover_steam_games(
    search_paths: Optional[list[Path]] = None,
) -> list[SteamGame]:
    """Discover installed Steam games by scanning ACF manifest files.

    Args:
        search_paths: List of ``steamapps/`` directories to search.
            Defaults to the standard Flatpak and native Steam paths.

    Returns:
        A list of :class:`SteamGame` objects sorted by name (case-insensitive),
        with non-game entries (Proton, runtimes, redistributables, incomplete
        installs) filtered out.
    """
    if search_paths is None:
        search_paths = _DEFAULT_SEARCH_PATHS

    games: list[SteamGame] = []

    for steamapps_path in search_paths:
        if not steamapps_path.is_dir():
            continue

        for acf_file in sorted(steamapps_path.glob("appmanifest_*.acf")):
            game = _parse_manifest(acf_file, steamapps_path)
            if game is not None:
                games.append(game)

    # Sort by name, case-insensitive
    games.sort(key=lambda g: g.name.lower())
    return games


def _parse_manifest(acf_file: Path, steamapps_path: Path) -> Optional[SteamGame]:
    """Parse a single appmanifest ACF file and return a SteamGame, or None."""
    data = parse_acf(acf_file)
    if data is None:
        return None

    app_state = data.get("AppState")
    if not isinstance(app_state, dict):
        logger.debug("_parse_manifest: no AppState in %s", acf_file)
        return None

    app_id = app_state.get("appid", "")
    name = app_state.get("name", "")
    state_flags = app_state.get("StateFlags", "")

    # Filter: skip non-game entries
    if app_id in _SKIP_APPID:
        logger.debug("_parse_manifest: skipping appid %s (%s)", app_id, name)
        return None
    if any(pattern in name for pattern in _SKIP_NAME_CONTAINS):
        logger.debug("_parse_manifest: skipping '%s' (name contains filter)", name)
        return None
    if any(name.startswith(prefix) for prefix in _SKIP_NAME_STARTSWITH):
        logger.debug("_parse_manifest: skipping '%s' (name startswith filter)", name)
        return None
    if state_flags != _REQUIRED_STATE_FLAGS:
        logger.debug(
            "_parse_manifest: skipping '%s' (StateFlags=%s, expected 4)", name, state_flags
        )
        return None

    install_dir = app_state.get("installdir", "")
    last_played = int(app_state.get("LastPlayed", 0) or 0)
    size_on_disk = int(app_state.get("SizeOnDisk", 0) or 0)
    image_path = _resolve_artwork(steamapps_path, app_id)

    return SteamGame(
        app_id=app_id,
        name=name,
        install_dir=install_dir,
        last_played=last_played,
        size_on_disk=size_on_disk,
        image_path=image_path,
    )
