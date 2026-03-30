"""Gamelist XML reader/writer for Steam and Moonlight metadata.

Reads and writes EmulationStation-format gamelist.xml files stored at:
  - ~/.config/htpcstation/steam/gamelist.xml
  - ~/.config/htpcstation/moonlight/gamelist.xml

These files are the single source of truth for rich metadata (description,
developer, publisher, genre, players, release date, rating).  User edits are
preserved: ``write_game_metadata`` only overwrites non-empty fields.

Uses only stdlib xml.etree.ElementTree.  Intentionally independent of the
retro ``gamelist.py`` module.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class GameMetadata:
    """Rich metadata for a Steam or Moonlight game entry."""

    name: str = ""
    app_id: str = ""
    description: str = ""
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    players: str = ""
    release_date: str = ""
    rating: float = 0.0
    image_path: str = ""


# ---------------------------------------------------------------------------
# Internal helpers (mirrored from backend/gamelist.py — kept independent)
# ---------------------------------------------------------------------------


def _text(element: ET.Element, tag: str, default: str = "") -> str:
    """Return stripped text content of a child element, or *default* if absent/empty."""
    child = element.find(tag)
    if child is None:
        return default
    return (child.text or "").strip()


def _resolve_path(directory: Path, raw: str) -> Path:
    """Resolve a gamelist-relative path to an absolute path.

    Paths in gamelist.xml typically start with "./" — strip the exact prefix
    before joining.  Uses ``removeprefix`` (not ``lstrip``) so that paths like
    ``./...hidden`` are not corrupted.
    """
    relative = raw.removeprefix("./")
    return directory / relative


def _set_or_create_text(parent: ET.Element, tag: str, text: str) -> None:
    """Set the text of a child element, creating it if it does not exist."""
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_gamelist(directory: Path) -> dict[str, GameMetadata]:
    """Read ``gamelist.xml`` from *directory* and return a metadata dict.

    The dict is keyed by ``appid`` when present, otherwise by ``name``.
    Returns an empty dict if the file does not exist or is malformed.
    Logs warnings for parse errors; never raises.
    """
    gamelist_file = directory / "gamelist.xml"
    if not gamelist_file.exists():
        logger.debug("No gamelist.xml found in %s", directory)
        return {}

    try:
        tree = ET.parse(gamelist_file)
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", gamelist_file, exc)
        return {}

    root = tree.getroot()
    result: dict[str, GameMetadata] = {}

    for game_elem in root.findall("game"):
        try:
            metadata = _parse_game_element(game_elem, directory)
        except Exception as exc:  # noqa: BLE001
            name_hint = _text(game_elem, "name") or _text(game_elem, "appid") or "?"
            logger.warning(
                "Skipping game '%s' in %s due to parse error: %s",
                name_hint,
                gamelist_file,
                exc,
            )
            continue

        key = metadata.app_id if metadata.app_id else metadata.name
        if not key:
            logger.warning(
                "Skipping entry with no appid or name in %s", gamelist_file
            )
            continue
        result[key] = metadata

    return result


def write_game_metadata(directory: Path, key: str, metadata: GameMetadata) -> None:
    """Write or update a single ``<game>`` entry in ``gamelist.xml``.

    - If the file does not exist, creates it with a ``<gameList>`` root.
    - If a matching entry exists (by ``appid`` when ``metadata.app_id`` is
      non-empty, otherwise by ``name``), updates only the fields that are
      non-empty in *metadata* — user-edited fields are never clobbered.
    - If no matching entry exists, appends a new ``<game>`` element.

    Logs errors on I/O failure; never raises.
    """
    directory.mkdir(parents=True, exist_ok=True)
    gamelist_file = directory / "gamelist.xml"

    # Load or create the XML tree
    if gamelist_file.exists():
        try:
            tree = ET.parse(gamelist_file)
            root = tree.getroot()
        except ET.ParseError as exc:
            logger.warning(
                "write_game_metadata: failed to parse %s: %s — will overwrite",
                gamelist_file,
                exc,
            )
            root = ET.Element("gameList")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("gameList")
        tree = ET.ElementTree(root)

    # Locate an existing matching element
    target: ET.Element | None = _find_game_element(root, metadata)

    if target is None:
        # Create a new <game> element
        target = ET.SubElement(root, "game")

    # Write fields — only overwrite when the incoming value is non-empty
    _merge_field(target, "name", metadata.name)
    _merge_field(target, "appid", metadata.app_id)
    _merge_field(target, "desc", metadata.description)
    _merge_field(target, "developer", metadata.developer)
    _merge_field(target, "publisher", metadata.publisher)
    _merge_field(target, "genre", metadata.genre)
    _merge_field(target, "players", metadata.players)
    _merge_field(target, "releasedate", metadata.release_date)
    if metadata.rating != 0.0:
        _set_or_create_text(target, "rating", str(metadata.rating))
    _merge_field(target, "image", metadata.image_path)

    try:
        tree.write(gamelist_file, encoding="utf-8", xml_declaration=True)
        logger.debug(
            "write_game_metadata: wrote entry '%s' to %s", key, gamelist_file
        )
    except OSError as exc:
        logger.error(
            "write_game_metadata: failed to write %s: %s", gamelist_file, exc
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_game_element(elem: ET.Element, directory: Path) -> GameMetadata:
    """Parse a single ``<game>`` element into a :class:`GameMetadata` instance."""
    rating_str = _text(elem, "rating", "0.0")
    try:
        rating = float(rating_str) if rating_str else 0.0
    except ValueError:
        rating = 0.0

    image_raw = _text(elem, "image")
    image_path = ""
    if image_raw:
        image_path = str(_resolve_path(directory, image_raw))

    return GameMetadata(
        name=_text(elem, "name"),
        app_id=_text(elem, "appid"),
        description=_text(elem, "desc"),
        developer=_text(elem, "developer"),
        publisher=_text(elem, "publisher"),
        genre=_text(elem, "genre"),
        players=_text(elem, "players"),
        release_date=_text(elem, "releasedate"),
        rating=rating,
        image_path=image_path,
    )


def _find_game_element(
    root: ET.Element, metadata: GameMetadata
) -> ET.Element | None:
    """Find an existing ``<game>`` element matching *metadata*.

    Matches by ``<appid>`` when ``metadata.app_id`` is non-empty, otherwise
    by ``<name>``.
    """
    if metadata.app_id:
        for game_elem in root.findall("game"):
            if _text(game_elem, "appid") == metadata.app_id:
                return game_elem
    else:
        for game_elem in root.findall("game"):
            if _text(game_elem, "name") == metadata.name:
                return game_elem
    return None


def _merge_field(parent: ET.Element, tag: str, value: str) -> None:
    """Set *tag* text to *value* only when *value* is non-empty.

    If the element does not yet exist and *value* is non-empty, it is created.
    If *value* is empty, the existing element (if any) is left untouched.
    """
    if value:
        _set_or_create_text(parent, tag, value)
