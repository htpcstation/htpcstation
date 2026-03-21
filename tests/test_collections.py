"""Tests for Task 011 — Collections.

Covers:
  - Collections appear at the top of the systems list after scan
  - Collection folder names are prefixed with '_'
  - Favorites collection: only favorited games, sorted by name
  - Last Played collection: only games with last_played, sorted descending, limit 50
  - All Games collection: all games sorted by name
  - selectSystem for a collection rebuilds it (reflects latest favorite/play state)
  - No ROM directory: no collections added (library is empty)
  - Collections are not included in real_systems when rebuilding
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import Config
from backend.library import GameLibrary
from backend.models import Game, System


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(system_path: Path, xml_body: str) -> None:
    """Write a minimal gamelist.xml to *system_path*."""
    content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
    (system_path / "gamelist.xml").write_text(content, encoding="utf-8")


def _make_library(tmp_path: Path, systems_xml: dict[str, str]) -> GameLibrary:
    """Create a GameLibrary with one or more systems.

    *systems_xml* maps folder_name -> XML body for gamelist.xml.
    """
    for folder_name, xml_body in systems_xml.items():
        system_dir = tmp_path / folder_name
        system_dir.mkdir(exist_ok=True)
        _write_gamelist(system_dir, xml_body)

    config = MagicMock(spec=Config)
    config.rom_directory = tmp_path
    config.get_system.return_value = MagicMock(
        display_name="Test System", core="core.so", extensions=[".rom"]
    )
    return GameLibrary(config)


# ---------------------------------------------------------------------------
# Collections appear at the top of the systems list
# ---------------------------------------------------------------------------


class TestCollectionsInSystemsList:
    def test_three_collections_prepended(self, tmp_path: Path) -> None:
        """After scan, the first three systems are the three virtual collections."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        systems = library._systems
        assert len(systems) == 4  # 3 collections + 1 real system

        folder_names = [s.folder_name for s in systems]
        assert folder_names[:3] == ["_favorites", "_lastplayed", "_allgames"]

    def test_collection_folder_names_start_with_underscore(self, tmp_path: Path) -> None:
        """All collection folder names start with '_'."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        collections = [s for s in library._systems if s.folder_name.startswith("_")]
        assert len(collections) == 3

    def test_real_systems_follow_collections(self, tmp_path: Path) -> None:
        """Real systems appear after the three collections."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
                "nes": "<game><path>./game2.rom</path><name>B Game</name></game>",
            },
        )
        systems = library._systems
        real = [s for s in systems if not s.folder_name.startswith("_")]
        assert len(real) == 2
        # Real systems come after the 3 collections
        assert systems.index(real[0]) >= 3

    def test_no_rom_directory_no_collections(self) -> None:
        """When no ROM directory is configured, the library is empty (no collections)."""
        config = MagicMock(spec=Config)
        config.rom_directory = None
        library = GameLibrary(config)
        assert library._systems == []

    def test_display_names_have_emoji_prefix(self, tmp_path: Path) -> None:
        """Collection display names include the expected emoji prefixes."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        by_folder = library._systems_by_folder
        assert by_folder["_favorites"].display_name == "Favorites"
        assert by_folder["_lastplayed"].display_name == "Last Played"
        assert by_folder["_allgames"].display_name == "All Games"


# ---------------------------------------------------------------------------
# Favorites collection
# ---------------------------------------------------------------------------


class TestFavoritesCollection:
    def test_only_favorited_games(self, tmp_path: Path) -> None:
        """Favorites collection contains only games with favorite=True."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./fav.rom</path><name>Fav Game</name>"
                    "<favorite>true</favorite></game>"
                    "<game><path>./nonfav.rom</path><name>Non Fav</name></game>"
                ),
            },
        )
        fav_system = library._systems_by_folder["_favorites"]
        assert fav_system.game_count == 1
        assert fav_system.games[0].name == "Fav Game"

    def test_sorted_alphabetically(self, tmp_path: Path) -> None:
        """Favorites are sorted alphabetically by name (case-insensitive)."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./z.rom</path><name>Zelda</name>"
                    "<favorite>true</favorite></game>"
                    "<game><path>./a.rom</path><name>Asteroids</name>"
                    "<favorite>true</favorite></game>"
                    "<game><path>./m.rom</path><name>Mario</name>"
                    "<favorite>true</favorite></game>"
                ),
            },
        )
        fav_system = library._systems_by_folder["_favorites"]
        names = [g.name for g in fav_system.games]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_empty_when_no_favorites(self, tmp_path: Path) -> None:
        """Favorites collection is empty when no games are favorited."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        fav_system = library._systems_by_folder["_favorites"]
        assert fav_system.game_count == 0
        assert fav_system.games == []

    def test_aggregates_across_systems(self, tmp_path: Path) -> None:
        """Favorites are collected from all real systems."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./a.rom</path><name>SNES Fav</name>"
                    "<favorite>true</favorite></game>"
                ),
                "nes": (
                    "<game><path>./b.rom</path><name>NES Fav</name>"
                    "<favorite>true</favorite></game>"
                ),
            },
        )
        fav_system = library._systems_by_folder["_favorites"]
        assert fav_system.game_count == 2
        names = {g.name for g in fav_system.games}
        assert names == {"SNES Fav", "NES Fav"}


# ---------------------------------------------------------------------------
# Last Played collection
# ---------------------------------------------------------------------------


class TestLastPlayedCollection:
    def test_only_games_with_last_played(self, tmp_path: Path) -> None:
        """Last Played collection contains only games with a non-empty last_played."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./played.rom</path><name>Played</name>"
                    "<lastplayed>20260101T120000</lastplayed></game>"
                    "<game><path>./unplayed.rom</path><name>Unplayed</name></game>"
                ),
            },
        )
        lp_system = library._systems_by_folder["_lastplayed"]
        assert lp_system.game_count == 1
        assert lp_system.games[0].name == "Played"

    def test_sorted_descending_by_last_played(self, tmp_path: Path) -> None:
        """Last Played games are sorted most-recent first."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./old.rom</path><name>Old Game</name>"
                    "<lastplayed>20240101T000000</lastplayed></game>"
                    "<game><path>./new.rom</path><name>New Game</name>"
                    "<lastplayed>20260101T000000</lastplayed></game>"
                    "<game><path>./mid.rom</path><name>Mid Game</name>"
                    "<lastplayed>20250101T000000</lastplayed></game>"
                ),
            },
        )
        lp_system = library._systems_by_folder["_lastplayed"]
        names = [g.name for g in lp_system.games]
        assert names == ["New Game", "Mid Game", "Old Game"]

    def test_limited_to_50(self, tmp_path: Path) -> None:
        """Last Played collection is capped at 50 entries."""
        # Create 60 games with last_played timestamps
        games_xml = "".join(
            f"<game><path>./{i:03d}.rom</path><name>Game {i:03d}</name>"
            f"<lastplayed>2026{i:02d}01T000000</lastplayed></game>"
            for i in range(1, 61)
        )
        library = _make_library(tmp_path, {"snes": games_xml})
        lp_system = library._systems_by_folder["_lastplayed"]
        assert lp_system.game_count == 50
        assert len(lp_system.games) == 50

    def test_empty_when_no_games_played(self, tmp_path: Path) -> None:
        """Last Played collection is empty when no games have been played."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        lp_system = library._systems_by_folder["_lastplayed"]
        assert lp_system.game_count == 0


# ---------------------------------------------------------------------------
# All Games collection
# ---------------------------------------------------------------------------


class TestAllGamesCollection:
    def test_contains_all_games(self, tmp_path: Path) -> None:
        """All Games collection contains every game from every system."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./a.rom</path><name>SNES Game</name></game>",
                "nes": "<game><path>./b.rom</path><name>NES Game</name></game>",
            },
        )
        all_system = library._systems_by_folder["_allgames"]
        assert all_system.game_count == 2
        names = {g.name for g in all_system.games}
        assert names == {"SNES Game", "NES Game"}

    def test_sorted_alphabetically(self, tmp_path: Path) -> None:
        """All Games are sorted alphabetically by name (case-insensitive)."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./z.rom</path><name>Zelda</name></game>"
                    "<game><path>./a.rom</path><name>Asteroids</name></game>"
                ),
                "nes": "<game><path>./m.rom</path><name>Mario</name></game>",
            },
        )
        all_system = library._systems_by_folder["_allgames"]
        names = [g.name for g in all_system.games]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_game_count_matches_total(self, tmp_path: Path) -> None:
        """game_count on All Games equals the total number of games."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./a.rom</path><name>A</name></game>"
                    "<game><path>./b.rom</path><name>B</name></game>"
                ),
                "nes": "<game><path>./c.rom</path><name>C</name></game>",
            },
        )
        all_system = library._systems_by_folder["_allgames"]
        assert all_system.game_count == 3


# ---------------------------------------------------------------------------
# selectSystem rebuilds collections
# ---------------------------------------------------------------------------


class TestSelectSystemRebuildsCollections:
    def test_favorites_updated_after_toggle(self, tmp_path: Path) -> None:
        """After toggling a favorite, selecting _favorites shows the updated list."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>Test Game</name></game>",
            },
        )

        # Initially no favorites
        library.selectSystem("_favorites")
        assert library._games_model.rowCount() == 0

        # Toggle the game as favorite via the real system
        library.selectSystem("snes")
        library.toggleFavorite(0)

        # Now select favorites — should rebuild and show the game
        library.selectSystem("_favorites")
        assert library._games_model.rowCount() == 1
        assert library._games_model._games[0].name == "Test Game"

    def test_last_played_updated_after_play(self, tmp_path: Path) -> None:
        """After a game is played, selecting _lastplayed shows the updated list."""
        from datetime import datetime

        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>Test Game</name></game>",
            },
        )

        # Initially no last-played games
        library.selectSystem("_lastplayed")
        assert library._games_model.rowCount() == 0

        # Simulate a game being played by updating last_played directly
        library.selectSystem("snes")
        game = library._games_model._games[0]
        game.last_played = datetime.now().strftime("%Y%m%dT%H%M%S")

        # Now select last played — should rebuild and show the game
        library.selectSystem("_lastplayed")
        assert library._games_model.rowCount() == 1

    def test_allgames_accessible_via_select_system(self, tmp_path: Path) -> None:
        """selectSystem('_allgames') populates gamesModel with all games."""
        library = _make_library(
            tmp_path,
            {
                "snes": (
                    "<game><path>./a.rom</path><name>A</name></game>"
                    "<game><path>./b.rom</path><name>B</name></game>"
                ),
            },
        )
        library.selectSystem("_allgames")
        assert library._games_model.rowCount() == 2

    def test_rebuild_does_not_duplicate_collections(self, tmp_path: Path) -> None:
        """Calling selectSystem on a collection multiple times does not duplicate collections."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>A Game</name></game>",
            },
        )
        initial_count = len(library._systems)

        library.selectSystem("_favorites")
        library.selectSystem("_favorites")
        library.selectSystem("_allgames")

        assert len(library._systems) == initial_count
