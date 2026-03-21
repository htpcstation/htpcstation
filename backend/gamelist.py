"""gamelist.xml parser for HTPC Station.

Parses the EmulationStation gamelist.xml format into a list of Game dataclass
instances.  All file I/O uses pathlib.Path.  Uses only stdlib xml.etree.ElementTree.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from backend.models import Game

logger = logging.getLogger(__name__)


def _text(element: ET.Element, tag: str, default: str = "") -> str:
    """Return stripped text content of a child element, or *default* if absent/empty."""
    child = element.find(tag)
    if child is None:
        return default
    return (child.text or "").strip()


def _resolve_path(system_path: Path, raw: str) -> Path:
    """Resolve a gamelist-relative path (e.g. ``./screenshots/foo.png``) to absolute."""
    # Paths in gamelist.xml start with "./" — strip the leading "./" before joining.
    # Use removeprefix (not lstrip) so only the exact prefix "./" is removed, not
    # individual '.' and '/' characters which would corrupt paths like ./...hidden.rom
    relative = raw.removeprefix("./")
    return system_path / relative


def parse_gamelist(system_path: Path) -> list[Game]:
    """Parse ``gamelist.xml`` in *system_path* and return a list of :class:`Game`.

    Returns an empty list if the file does not exist or is malformed.
    Individual game entries that fail to parse are skipped with a warning.
    """
    gamelist_file = system_path / "gamelist.xml"
    if not gamelist_file.exists():
        logger.debug("No gamelist.xml found in %s", system_path)
        return []

    try:
        tree = ET.parse(gamelist_file)
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", gamelist_file, exc)
        return []

    root = tree.getroot()
    folder_name = system_path.name
    games: list[Game] = []

    for game_elem in root.findall("game"):
        try:
            game = _parse_game_element(game_elem, system_path, folder_name)
        except Exception as exc:  # noqa: BLE001
            name_hint = _text(game_elem, "name") or _text(game_elem, "path") or "?"
            logger.warning(
                "Skipping game '%s' in %s due to parse error: %s",
                name_hint,
                gamelist_file,
                exc,
            )
            continue
        games.append(game)

    return games


def _parse_game_element(
    elem: ET.Element,
    system_path: Path,
    folder_name: str,
) -> Game:
    """Parse a single ``<game>`` element into a :class:`Game` instance."""

    # --- ROM path -----------------------------------------------------------
    path_raw = _text(elem, "path")
    if not path_raw:
        name_hint = _text(elem, "name") or "?"
        raise ValueError(f"Game '{name_hint}' has a missing or empty <path> tag")
    rom_path = _resolve_path(system_path, path_raw)

    # --- Image path ---------------------------------------------------------
    image_raw = _text(elem, "image")
    image_path: Path | None = None
    if image_raw:
        candidate = _resolve_path(system_path, image_raw)
        if candidate.exists():
            image_path = candidate

    # --- Video path ---------------------------------------------------------
    video_raw = _text(elem, "video")
    video_path: Path | None = None
    if video_raw:
        video_path = _resolve_path(system_path, video_raw)

    # --- Numeric fields -----------------------------------------------------
    rating_str = _text(elem, "rating", "0.0")
    try:
        rating = float(rating_str) if rating_str else 0.0
    except ValueError:
        rating = 0.0

    playcount_str = _text(elem, "playcount", "0")
    try:
        play_count = int(playcount_str) if playcount_str else 0
    except ValueError:
        play_count = 0

    gametime_str = _text(elem, "gametime", "0")
    try:
        game_time = int(gametime_str) if gametime_str else 0
    except ValueError:
        game_time = 0

    # --- Favorite -----------------------------------------------------------
    favorite_str = _text(elem, "favorite", "").lower()
    favorite = favorite_str == "true"

    return Game(
        path=rom_path,
        name=_text(elem, "name"),
        description=_text(elem, "desc"),
        image_path=image_path,
        video_path=video_path,
        rating=rating,
        release_date=_text(elem, "releasedate"),
        developer=_text(elem, "developer"),
        publisher=_text(elem, "publisher"),
        genre=_text(elem, "genre"),
        players=_text(elem, "players"),
        favorite=favorite,
        play_count=play_count,
        last_played=_text(elem, "lastplayed"),
        game_time=game_time,
        system_folder=folder_name,
    )


def _set_or_create_text(parent: ET.Element, tag: str, text: str) -> None:
    """Set the text of a child element, creating it if it does not exist."""
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = text


def write_game_stats(system_path: Path, game: Game) -> None:
    """Update lastplayed, playcount, gametime, and favorite for a single game in gamelist.xml.

    Finds the matching ``<game>`` element by its ``<path>`` value and updates
    the stats fields in-place, then writes the file back.

    If the gamelist.xml does not exist or cannot be parsed, logs a warning and
    returns without raising.
    """
    gamelist_file = system_path / "gamelist.xml"
    if not gamelist_file.exists():
        logger.warning("write_game_stats: gamelist.xml not found in %s", system_path)
        return

    try:
        tree = ET.parse(gamelist_file)
    except ET.ParseError as exc:
        logger.warning("write_game_stats: failed to parse %s: %s", gamelist_file, exc)
        return

    root = tree.getroot()

    # Build the relative path string as stored in gamelist.xml (e.g. "./game.rom")
    try:
        rel = "./" + game.path.relative_to(system_path).as_posix()
    except ValueError:
        # game.path is not relative to system_path — fall back to absolute path
        rel = str(game.path)

    # Find the matching <game> element
    target: ET.Element | None = None
    for game_elem in root.findall("game"):
        if _text(game_elem, "path") == rel:
            target = game_elem
            break

    if target is None:
        logger.warning(
            "write_game_stats: no <game> with <path>=%s found in %s",
            rel,
            gamelist_file,
        )
        return

    # lastplayed — format: YYYYMMDDTHHMMSS
    last_played_str = game.last_played
    if not last_played_str:
        last_played_str = datetime.now().strftime("%Y%m%dT%H%M%S")
    _set_or_create_text(target, "lastplayed", last_played_str)

    # playcount
    _set_or_create_text(target, "playcount", str(game.play_count))

    # gametime
    _set_or_create_text(target, "gametime", str(game.game_time))

    # favorite — present and "true" when favorite, removed when not
    fav_elem = target.find("favorite")
    if game.favorite:
        if fav_elem is None:
            fav_elem = ET.SubElement(target, "favorite")
        fav_elem.text = "true"
    else:
        if fav_elem is not None:
            target.remove(fav_elem)

    try:
        tree.write(gamelist_file, encoding="utf-8", xml_declaration=True)
        logger.debug("write_game_stats: wrote stats for '%s' to %s", game.name, gamelist_file)
    except OSError as exc:
        logger.error("write_game_stats: failed to write %s: %s", gamelist_file, exc)
