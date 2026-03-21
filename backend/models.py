"""Data models for HTPC Station game library.

Plain Python dataclasses — not QObjects.  The QML-facing list models in
``library.py`` wrap these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Game:
    """Represents a single game entry parsed from a gamelist.xml."""

    path: Path                          # absolute path to ROM file
    name: str
    description: str = ""
    image_path: Optional[Path] = None  # absolute path to screenshot (None if absent/missing)
    video_path: Optional[Path] = None  # absolute path to video (stored, not used yet)
    rating: float = 0.0
    release_date: str = ""             # raw string from XML, e.g. "19990527T000000"
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    players: str = ""
    favorite: bool = False
    play_count: int = 0
    last_played: str = ""              # raw string from XML
    game_time: int = 0                 # seconds
    system_folder: str = ""            # e.g. "ngpc" — which system this game belongs to


@dataclass
class System:
    """Represents a discovered system folder with its parsed games."""

    folder_name: str        # e.g. "ngpc"
    display_name: str       # e.g. "Neo Geo Pocket Color" (from config)
    path: Path              # absolute path to system folder
    games: list[Game] = field(default_factory=list)
    game_count: int = 0     # len(games), stored for convenience
