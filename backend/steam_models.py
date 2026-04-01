"""Data model for Steam games.

Plain Python dataclass — not a QObject. Populated by steam_parser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SteamGame:
    """Represents a single installed Steam game."""

    app_id: str       # Steam application ID, e.g. "440"
    name: str         # Display name, e.g. "Team Fortress 2"
    install_dir: str  # Installation directory name (relative to steamapps/common/)
    last_played: int  # Unix epoch seconds; 0 = never played
    size_on_disk: int # Bytes used on disk
    image_path: str   # Absolute path to poster image, or "" if not found
    favorite: bool = False  # Whether the game is marked as a favorite
