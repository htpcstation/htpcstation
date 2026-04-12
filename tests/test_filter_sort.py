"""Tests for sort functionality in GameLibrary.

Covers:
  - GameLibrary.sortGames: az, za, genre, recent, unknown key
  - selectSystem resets sort state
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import Config
from backend.library import GameLibrary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(system_path: Path, xml_body: str) -> None:
    """Write a minimal gamelist.xml to *system_path*."""
    content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
    (system_path / "gamelist.xml").write_text(content, encoding="utf-8")


def _make_library(tmp_path: Path, systems_xml: dict[str, str]) -> GameLibrary:
    """Create a GameLibrary with one or more systems."""
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
# GameLibrary.sortGames
# ---------------------------------------------------------------------------


class TestSortGames:
    def _make_multi_game_library(self, tmp_path: Path) -> GameLibrary:
        xml = (
            "<game><path>./z.rom</path><name>Zelda</name>"
            "<genre>Action</genre><players>1</players></game>"
            "<game><path>./a.rom</path><name>Asteroids</name>"
            "<genre>Shooter</genre><players>2</players></game>"
            "<game><path>./m.rom</path><name>Mario</name>"
            "<genre>Action</genre><players>1-2</players></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        return library

    def test_sort_az(self, tmp_path: Path) -> None:
        """sortGames('az') sorts alphabetically ascending."""
        library = self._make_multi_game_library(tmp_path)
        library.sortGames("az")
        names = [library._games_model._games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_za(self, tmp_path: Path) -> None:
        """sortGames('za') sorts alphabetically descending."""
        library = self._make_multi_game_library(tmp_path)
        library.sortGames("za")
        names = [library._games_model._games[i].name for i in range(3)]
        assert names == ["Zelda", "Mario", "Asteroids"]

    def test_sort_genre_removed_falls_back_to_az(self, tmp_path: Path) -> None:
        """sortGames('genre') is no longer supported and falls back to A-Z."""
        library = self._make_multi_game_library(tmp_path)
        library.sortGames("genre")
        names = [library._games_model._games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_recent_played_before_unplayed(self, tmp_path: Path) -> None:
        """sortGames('recent') puts games with last_played before those without."""
        xml = (
            "<game><path>./a.rom</path><name>Alpha</name>"
            "<lastplayed>20260101T120000</lastplayed></game>"
            "<game><path>./b.rom</path><name>Beta</name></game>"
            "<game><path>./c.rom</path><name>Gamma</name>"
            "<lastplayed>20260315T090000</lastplayed></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        library.sortGames("recent")
        games = library._games_model._games
        names = [g.name for g in games]
        # Gamma (most recent) first, then Alpha, then Beta (no last_played)
        assert names == ["Gamma", "Alpha", "Beta"]

    def test_sort_recent_descending_by_last_played(self, tmp_path: Path) -> None:
        """sortGames('recent') sorts played games descending by last_played."""
        xml = (
            "<game><path>./a.rom</path><name>Alpha</name>"
            "<lastplayed>20260101T000000</lastplayed></game>"
            "<game><path>./b.rom</path><name>Beta</name>"
            "<lastplayed>20260315T000000</lastplayed></game>"
            "<game><path>./c.rom</path><name>Gamma</name>"
            "<lastplayed>20260201T000000</lastplayed></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        library.sortGames("recent")
        games = library._games_model._games
        names = [g.name for g in games]
        assert names == ["Beta", "Gamma", "Alpha"]

    def test_sort_recent_unplayed_at_end(self, tmp_path: Path) -> None:
        """sortGames('recent') puts all unplayed games at the end."""
        xml = (
            "<game><path>./a.rom</path><name>Alpha</name></game>"
            "<game><path>./b.rom</path><name>Beta</name></game>"
            "<game><path>./c.rom</path><name>Gamma</name>"
            "<lastplayed>20260101T000000</lastplayed></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        library.sortGames("recent")
        games = library._games_model._games
        # Gamma (played) first, then unplayed (Alpha, Beta in original order)
        assert games[0].name == "Gamma"
        assert games[1].name in {"Alpha", "Beta"}
        assert games[2].name in {"Alpha", "Beta"}

    def test_sort_unknown_key_falls_back_to_az(self, tmp_path: Path) -> None:
        """sortGames with an unknown key falls back to A-Z."""
        library = self._make_multi_game_library(tmp_path)
        library.sortGames("unknown_key")
        names = [library._games_model._games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_emits_games_model_changed(self, tmp_path: Path) -> None:
        """sortGames emits gamesModelChanged."""
        library = self._make_multi_game_library(tmp_path)
        signals_received: list[bool] = []
        library.gamesModelChanged.connect(lambda: signals_received.append(True))
        library.sortGames("za")
        assert len(signals_received) == 1

    def test_sort_updates_current_sort(self, tmp_path: Path) -> None:
        """sortGames updates _current_sort."""
        library = self._make_multi_game_library(tmp_path)
        library.sortGames("za")
        assert library._current_sort == "za"


# ---------------------------------------------------------------------------
# selectSystem resets sort state
# ---------------------------------------------------------------------------


class TestSelectSystemResetsState:
    def test_select_system_resets_sort_to_az(self, tmp_path: Path) -> None:
        """selectSystem resets _current_sort to 'az'."""
        xml = "<game><path>./a.rom</path><name>A</name></game>"
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        library.sortGames("za")
        assert library._current_sort == "za"

        library.selectSystem("snes")
        assert library._current_sort == "az"

    def test_select_system_applies_az_sort(self, tmp_path: Path) -> None:
        """selectSystem applies A-Z sort immediately (games not in parse order)."""
        # Games in reverse alphabetical order in XML
        xml = (
            "<game><path>./z.rom</path><name>Zelda</name></game>"
            "<game><path>./m.rom</path><name>Mario</name></game>"
            "<game><path>./a.rom</path><name>Asteroids</name></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        names = [library._games_model._games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_select_system_shows_all_games(self, tmp_path: Path) -> None:
        """After selectSystem, all games are shown."""
        xml = (
            "<game><path>./a.rom</path><name>A</name></game>"
            "<game><path>./b.rom</path><name>B</name></game>"
        )
        library = _make_library(tmp_path, {"snes": xml})
        library.selectSystem("snes")
        assert library._games_model.rowCount() == 2


# ---------------------------------------------------------------------------
# TestFavoritesOnTop
# ---------------------------------------------------------------------------


class TestFavoritesOnTop:
    """Tests for GameLibrary.setFavoritesOnTop."""

    # XML with three games: Asteroids (fav), Mario (not fav), Zelda (fav)
    _XML = (
        "<game><path>./z.rom</path><name>Zelda</name>"
        "<favorite>true</favorite></game>"
        "<game><path>./a.rom</path><name>Asteroids</name>"
        "<favorite>true</favorite></game>"
        "<game><path>./m.rom</path><name>Mario</name></game>"
    )

    def _make_fav_library(self, tmp_path: Path) -> GameLibrary:
        library = _make_library(tmp_path, {"snes": self._XML})
        library.selectSystem("snes")
        return library

    def test_favorites_on_top_true_az(self, tmp_path: Path) -> None:
        """setFavoritesOnTop(True) + sortGames('az'): favorites first, each partition A-Z."""
        library = self._make_fav_library(tmp_path)
        library.setFavoritesOnTop(True)
        library.sortGames("az")
        names = [g.name for g in library._games_model._games]
        # Favorites: Asteroids, Zelda (A-Z); non-favorites: Mario
        assert names == ["Asteroids", "Zelda", "Mario"]

    def test_favorites_on_top_false_az(self, tmp_path: Path) -> None:
        """setFavoritesOnTop(False) + sortGames('az'): purely alphabetical, no hoisting."""
        library = self._make_fav_library(tmp_path)
        library.setFavoritesOnTop(False)
        library.sortGames("az")
        names = [g.name for g in library._games_model._games]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_favorites_on_top_true_za(self, tmp_path: Path) -> None:
        """setFavoritesOnTop(True) + sortGames('za'): favorites first (Z-A), then non-favorites (Z-A)."""
        library = self._make_fav_library(tmp_path)
        library.setFavoritesOnTop(True)
        library.sortGames("za")
        names = [g.name for g in library._games_model._games]
        # Favorites: Zelda, Asteroids (Z-A); non-favorites: Mario
        assert names == ["Zelda", "Asteroids", "Mario"]

    def test_favorites_collection_not_reordered(self, tmp_path: Path) -> None:
        """setFavoritesOnTop(True) while current system is _favorites: no partition applied."""
        library = self._make_fav_library(tmp_path)
        library.setFavoritesOnTop(True)
        library.selectSystem("_favorites")
        # All games in _favorites are favorites; partition must not be applied
        # (i.e. the existing sort order from _build_collection_systems is preserved).
        names = [g.name for g in library._games_model._games]
        # _favorites is built alphabetically in _build_collection_systems
        assert names == ["Asteroids", "Zelda"]

    def test_set_favorites_on_top_emits_games_model_changed(self, tmp_path: Path) -> None:
        """setFavoritesOnTop emits gamesModelChanged."""
        library = self._make_fav_library(tmp_path)
        signals: list[bool] = []
        library.gamesModelChanged.connect(lambda: signals.append(True))
        library.setFavoritesOnTop(False)
        assert len(signals) == 1

    def test_set_favorites_on_top_emits_favorites_on_top_changed(self, tmp_path: Path) -> None:
        """setFavoritesOnTop emits favoritesOnTopChanged on change, not on same value."""
        library = self._make_fav_library(tmp_path)
        # Default is True; calling with True should be a no-op
        signals: list[bool] = []
        library.favoritesOnTopChanged.connect(lambda: signals.append(True))

        library.setFavoritesOnTop(True)   # same value — no emit, no re-sort
        assert len(signals) == 0

        sort_signals: list[bool] = []
        library.gamesModelChanged.connect(lambda: sort_signals.append(True))

        library.setFavoritesOnTop(True)   # still same value
        assert len(signals) == 0
        assert len(sort_signals) == 0

        library.setFavoritesOnTop(False)  # value changes — must emit
        assert len(signals) == 1
        assert len(sort_signals) == 1

        library.setFavoritesOnTop(False)  # same again — no emit
        assert len(signals) == 1
        assert len(sort_signals) == 1

    def test_favorites_on_top_toggle_true_false_true(self, tmp_path: Path) -> None:
        """Toggling True→False→True re-applies the partition correctly each time."""
        library = self._make_fav_library(tmp_path)
        library.sortGames("az")

        library.setFavoritesOnTop(True)
        names_on = [g.name for g in library._games_model._games]
        assert names_on[0] in {"Asteroids", "Zelda"}
        assert names_on[1] in {"Asteroids", "Zelda"}
        assert names_on[2] == "Mario"

        library.setFavoritesOnTop(False)
        names_off = [g.name for g in library._games_model._games]
        assert names_off == ["Asteroids", "Mario", "Zelda"]

        library.setFavoritesOnTop(True)
        names_on2 = [g.name for g in library._games_model._games]
        assert names_on2[0] in {"Asteroids", "Zelda"}
        assert names_on2[1] in {"Asteroids", "Zelda"}
        assert names_on2[2] == "Mario"
