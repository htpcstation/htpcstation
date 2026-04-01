"""Tests for PC Games Favorites — Task 001 (backend).

Covers:
  - GameMetadata: favorite field default and parsing
  - metadata_gamelist: read/write favorite field (round-trip)
  - SteamGame: favorite field default
  - MoonlightApp: favorite field default
  - SteamGameListModel: FavoriteRole
  - MoonlightAppListModel: FavoriteRole
  - SteamLibrary.toggleFavorite: flip, persist, signal, sources rebuild
  - SteamLibrary.getFavorites: returns favorited games sorted A-Z
  - SteamLibrary.selectSource("favorites"): filters to favorited games
  - SteamLibrary._rebuild_sources_model: "PC Favorites" entry appears/disappears
  - SteamLibrary.setMoonlightFavoriteCount: updates PC Favorites count
  - MoonlightLibrary.toggleFavorite: flip, persist, signal, hostsChanged
  - MoonlightLibrary.favoriteCount property
  - Persistence round-trip: toggle → read back from gamelist.xml
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication

from backend.metadata_gamelist import GameMetadata, read_gamelist, write_game_metadata
from backend.moonlight_models import MoonlightApp
from backend.steam_models import SteamGame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_steam_game(
    app_id: str = "440",
    name: str = "Team Fortress 2",
    favorite: bool = False,
) -> SteamGame:
    return SteamGame(
        app_id=app_id,
        name=name,
        install_dir=name.lower().replace(" ", ""),
        last_played=0,
        size_on_disk=0,
        image_path="",
        favorite=favorite,
    )


def _make_moonlight_app(
    name: str = "Desktop",
    host_uuid: str = "uuid-1",
    favorite: bool = False,
) -> MoonlightApp:
    return MoonlightApp(name=name, host_uuid=host_uuid, favorite=favorite)


def _make_steam_lib(games: list[SteamGame], steam_dir: Path | None = None):
    """Create a SteamLibrary with the given games, optionally redirecting steam dir."""
    from backend.steam_library import SteamLibrary

    if steam_dir is not None:
        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.get_steam_dir", return_value=steam_dir), \
             patch("backend.steam_library.read_gamelist", return_value={}):
            return SteamLibrary()
    else:
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            return SteamLibrary()


# ---------------------------------------------------------------------------
# GameMetadata — favorite field
# ---------------------------------------------------------------------------


class TestGameMetadataFavoriteField:
    def test_default_is_false(self) -> None:
        """GameMetadata.favorite defaults to False."""
        meta = GameMetadata()
        assert meta.favorite is False

    def test_can_be_set_to_true(self) -> None:
        """GameMetadata.favorite can be set to True."""
        meta = GameMetadata(name="Game", favorite=True)
        assert meta.favorite is True


# ---------------------------------------------------------------------------
# metadata_gamelist — favorite field read/write
# ---------------------------------------------------------------------------


class TestMetadataGamelistFavorite:
    def test_read_favorite_true(self, tmp_path: Path) -> None:
        """<favorite>true</favorite> is parsed as True."""
        xml = textwrap.dedent("""\
            <?xml version='1.0' encoding='utf-8'?>
            <gameList>
              <game>
                <name>Portal 2</name>
                <appid>620</appid>
                <favorite>true</favorite>
              </game>
            </gameList>
        """)
        (tmp_path / "gamelist.xml").write_text(xml, encoding="utf-8")
        result = read_gamelist(tmp_path)
        assert result["620"].favorite is True

    def test_read_favorite_false(self, tmp_path: Path) -> None:
        """<favorite>false</favorite> is parsed as False."""
        xml = textwrap.dedent("""\
            <?xml version='1.0' encoding='utf-8'?>
            <gameList>
              <game>
                <name>Portal 2</name>
                <appid>620</appid>
                <favorite>false</favorite>
              </game>
            </gameList>
        """)
        (tmp_path / "gamelist.xml").write_text(xml, encoding="utf-8")
        result = read_gamelist(tmp_path)
        assert result["620"].favorite is False

    def test_read_favorite_missing_defaults_to_false(self, tmp_path: Path) -> None:
        """Missing <favorite> element defaults to False."""
        xml = textwrap.dedent("""\
            <?xml version='1.0' encoding='utf-8'?>
            <gameList>
              <game>
                <name>Portal 2</name>
                <appid>620</appid>
              </game>
            </gameList>
        """)
        (tmp_path / "gamelist.xml").write_text(xml, encoding="utf-8")
        result = read_gamelist(tmp_path)
        assert result["620"].favorite is False

    def test_write_favorite_true(self, tmp_path: Path) -> None:
        """Writing favorite=True persists <favorite>true</favorite>."""
        meta = GameMetadata(name="Portal 2", app_id="620", favorite=True)
        write_game_metadata(tmp_path, "620", meta)

        result = read_gamelist(tmp_path)
        assert result["620"].favorite is True

    def test_write_favorite_false(self, tmp_path: Path) -> None:
        """Writing favorite=False persists <favorite>false</favorite>."""
        meta = GameMetadata(name="Portal 2", app_id="620", favorite=False)
        write_game_metadata(tmp_path, "620", meta)

        result = read_gamelist(tmp_path)
        assert result["620"].favorite is False

    def test_toggle_off_persists(self, tmp_path: Path) -> None:
        """Toggling favorite from True to False persists correctly (not clobbered)."""
        # Write True first
        meta = GameMetadata(name="Portal 2", app_id="620", favorite=True)
        write_game_metadata(tmp_path, "620", meta)

        # Now write False
        meta.favorite = False
        write_game_metadata(tmp_path, "620", meta)

        result = read_gamelist(tmp_path)
        assert result["620"].favorite is False

    def test_favorite_written_even_when_false(self, tmp_path: Path) -> None:
        """<favorite> element is always written, even when False."""
        meta = GameMetadata(name="Portal 2", app_id="620", favorite=False)
        write_game_metadata(tmp_path, "620", meta)

        xml_content = (tmp_path / "gamelist.xml").read_text(encoding="utf-8")
        assert "<favorite>false</favorite>" in xml_content

    def test_round_trip_toggle(self, tmp_path: Path) -> None:
        """Full round-trip: write True, read back True; write False, read back False."""
        meta = GameMetadata(name="Game", app_id="1")

        meta.favorite = True
        write_game_metadata(tmp_path, "1", meta)
        assert read_gamelist(tmp_path)["1"].favorite is True

        meta.favorite = False
        write_game_metadata(tmp_path, "1", meta)
        assert read_gamelist(tmp_path)["1"].favorite is False


# ---------------------------------------------------------------------------
# SteamGame — favorite field
# ---------------------------------------------------------------------------


class TestSteamGameFavoriteField:
    def test_default_is_false(self) -> None:
        """SteamGame.favorite defaults to False."""
        game = SteamGame(
            app_id="440",
            name="TF2",
            install_dir="tf2",
            last_played=0,
            size_on_disk=0,
            image_path="",
        )
        assert game.favorite is False

    def test_can_be_set_to_true(self) -> None:
        """SteamGame.favorite can be set to True."""
        game = _make_steam_game(favorite=True)
        assert game.favorite is True


# ---------------------------------------------------------------------------
# MoonlightApp — favorite field
# ---------------------------------------------------------------------------


class TestMoonlightAppFavoriteField:
    def test_default_is_false(self) -> None:
        """MoonlightApp.favorite defaults to False."""
        app = MoonlightApp(name="Desktop", host_uuid="uuid-1")
        assert app.favorite is False

    def test_can_be_set_to_true(self) -> None:
        """MoonlightApp.favorite can be set to True."""
        app = _make_moonlight_app(favorite=True)
        assert app.favorite is True


# ---------------------------------------------------------------------------
# SteamGameListModel — FavoriteRole
# ---------------------------------------------------------------------------


class TestSteamGameListModelFavoriteRole:
    def test_favorite_role_returns_false_by_default(self) -> None:
        """FavoriteRole returns False for a game with favorite=False."""
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        model.set_games([_make_steam_game(favorite=False)])
        idx = model.index(0, 0)
        assert model.data(idx, SteamGameListModel.FavoriteRole) is False

    def test_favorite_role_returns_true_when_set(self) -> None:
        """FavoriteRole returns True for a game with favorite=True."""
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        model.set_games([_make_steam_game(favorite=True)])
        idx = model.index(0, 0)
        assert model.data(idx, SteamGameListModel.FavoriteRole) is True

    def test_favorite_role_in_role_names(self) -> None:
        """roleNames includes 'favorite' key."""
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        names = model.roleNames()
        assert b"favorite" in names.values()


# ---------------------------------------------------------------------------
# MoonlightAppListModel — FavoriteRole
# ---------------------------------------------------------------------------


class TestMoonlightAppListModelFavoriteRole:
    def test_favorite_role_returns_false_by_default(self) -> None:
        """FavoriteRole returns False for an app with favorite=False."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_moonlight_app(favorite=False)])
        idx = model.index(0, 0)
        assert model.data(idx, MoonlightAppListModel.FavoriteRole) is False

    def test_favorite_role_returns_true_when_set(self) -> None:
        """FavoriteRole returns True for an app with favorite=True."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_moonlight_app(favorite=True)])
        idx = model.index(0, 0)
        assert model.data(idx, MoonlightAppListModel.FavoriteRole) is True

    def test_favorite_role_in_role_names(self) -> None:
        """roleNames includes 'favorite' key."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        names = model.roleNames()
        assert b"favorite" in names.values()


# ---------------------------------------------------------------------------
# SteamLibrary — toggleFavorite
# ---------------------------------------------------------------------------


class TestSteamLibraryToggleFavorite:
    def _make_lib(self, games: list[SteamGame], steam_dir: Path | None = None):
        from backend.steam_library import SteamLibrary

        if steam_dir is not None:
            with patch("backend.steam_library.discover_steam_games", return_value=games), \
                 patch("backend.steam_library.get_steam_dir", return_value=steam_dir), \
                 patch("backend.steam_library.read_gamelist", return_value={}):
                return SteamLibrary()
        else:
            with patch("backend.steam_library.discover_steam_games", return_value=games):
                return SteamLibrary()

    def test_toggle_flips_favorite_to_true(self, tmp_path: Path) -> None:
        """toggleFavorite flips favorite from False to True."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._current_games[0].favorite is True

    def test_toggle_flips_favorite_to_false(self, tmp_path: Path) -> None:
        """toggleFavorite flips favorite from True to False."""
        games = [_make_steam_game("440", "TF2", favorite=True)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._current_games[0].favorite is False

    def test_toggle_updates_all_games(self, tmp_path: Path) -> None:
        """toggleFavorite also updates the matching game in _all_games."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._all_games[0].favorite is True

    def test_toggle_emits_favorite_toggled_signal(self, tmp_path: Path) -> None:
        """toggleFavorite emits favoriteToggled with the new value."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        received: list[bool] = []
        lib.favoriteToggled.connect(lambda v: received.append(v))

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert received == [True]

    def test_toggle_emits_false_when_unfavoriting(self, tmp_path: Path) -> None:
        """toggleFavorite emits False when unfavoriting."""
        games = [_make_steam_game("440", "TF2", favorite=True)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        received: list[bool] = []
        lib.favoriteToggled.connect(lambda v: received.append(v))

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert received == [False]

    def test_toggle_rebuilds_sources_model(self, tmp_path: Path) -> None:
        """toggleFavorite rebuilds the sources model (PC Favorites count updates)."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        signals: list[bool] = []
        lib.sourcesModelChanged.connect(lambda: signals.append(True))

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert len(signals) >= 1

    def test_toggle_out_of_range_is_noop(self, tmp_path: Path) -> None:
        """toggleFavorite with out-of-range index does nothing."""
        games = [_make_steam_game("440", "TF2")]
        lib = self._make_lib(games, steam_dir=tmp_path)

        received: list[bool] = []
        lib.favoriteToggled.connect(lambda v: received.append(v))

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(99)

        assert received == []
        assert lib._current_games[0].favorite is False

    def test_toggle_persists_to_gamelist_xml(self, tmp_path: Path) -> None:
        """toggleFavorite writes the new favorite value to gamelist.xml."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        result = read_gamelist(tmp_path)
        assert result["440"].favorite is True

    def test_toggle_round_trip_persistence(self, tmp_path: Path) -> None:
        """Toggle on then off — gamelist.xml reflects False after second toggle."""
        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games, steam_dir=tmp_path)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)  # → True
            lib.toggleFavorite(0)  # → False

        result = read_gamelist(tmp_path)
        assert result["440"].favorite is False


# ---------------------------------------------------------------------------
# SteamLibrary — getFavorites
# ---------------------------------------------------------------------------


class TestSteamLibraryGetFavorites:
    def _make_lib(self, games: list[SteamGame]):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.read_gamelist", return_value={}):
            return SteamLibrary()

    def test_returns_empty_when_no_favorites(self) -> None:
        """getFavorites returns [] when no games are favorited."""
        games = [
            _make_steam_game("1", "Alpha", favorite=False),
            _make_steam_game("2", "Beta", favorite=False),
        ]
        lib = self._make_lib(games)
        assert lib.getFavorites() == []

    def test_returns_only_favorited_games(self) -> None:
        """getFavorites returns only games with favorite=True."""
        games = [
            _make_steam_game("1", "Alpha", favorite=True),
            _make_steam_game("2", "Beta", favorite=False),
            _make_steam_game("3", "Gamma", favorite=True),
        ]
        lib = self._make_lib(games)
        result = lib.getFavorites()
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"Alpha", "Gamma"}

    def test_returns_sorted_az(self) -> None:
        """getFavorites returns games sorted A-Z."""
        games = [
            _make_steam_game("1", "Zelda", favorite=True),
            _make_steam_game("2", "Asteroids", favorite=True),
            _make_steam_game("3", "Mario", favorite=True),
        ]
        lib = self._make_lib(games)
        result = lib.getFavorites()
        names = [r["name"] for r in result]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_result_has_expected_keys(self) -> None:
        """getFavorites result dicts have the expected keys."""
        games = [_make_steam_game("440", "TF2", favorite=True)]
        lib = self._make_lib(games)
        result = lib.getFavorites()
        assert len(result) == 1
        entry = result[0]
        assert entry["appId"] == "440"
        assert entry["name"] == "TF2"
        assert entry["source"] == "steam"
        assert entry["hostAddress"] == ""
        assert "installDir" in entry
        assert "lastPlayed" in entry
        assert "sizeOnDisk" in entry
        assert "imagePath" in entry
        assert entry["favorite"] is True


# ---------------------------------------------------------------------------
# SteamLibrary — selectSource("favorites")
# ---------------------------------------------------------------------------


class TestSteamLibrarySelectSourceFavorites:
    def _make_lib(self, games: list[SteamGame]):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.read_gamelist", return_value={}):
            return SteamLibrary()

    def test_select_favorites_shows_only_favorited_games(self) -> None:
        """selectSource('favorites') filters _current_games to favorited games."""
        games = [
            _make_steam_game("1", "Alpha", favorite=True),
            _make_steam_game("2", "Beta", favorite=False),
            _make_steam_game("3", "Gamma", favorite=True),
        ]
        lib = self._make_lib(games)
        lib.selectSource("favorites")

        assert lib._games_model.rowCount() == 2
        names = {lib._current_games[i].name for i in range(2)}
        assert names == {"Alpha", "Gamma"}

    def test_select_favorites_empty_when_none_favorited(self) -> None:
        """selectSource('favorites') shows empty model when no games are favorited."""
        games = [
            _make_steam_game("1", "Alpha", favorite=False),
            _make_steam_game("2", "Beta", favorite=False),
        ]
        lib = self._make_lib(games)
        lib.selectSource("favorites")

        assert lib._games_model.rowCount() == 0

    def test_select_steam_after_favorites_shows_all(self) -> None:
        """selectSource('steam') after 'favorites' restores all games."""
        games = [
            _make_steam_game("1", "Alpha", favorite=True),
            _make_steam_game("2", "Beta", favorite=False),
        ]
        lib = self._make_lib(games)
        lib.selectSource("favorites")
        lib.selectSource("steam")

        assert lib._games_model.rowCount() == 2


# ---------------------------------------------------------------------------
# SteamLibrary — PC Favorites source entry
# ---------------------------------------------------------------------------


class TestSteamLibraryPCFavoritesSource:
    def _make_lib(self, games: list[SteamGame]):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.read_gamelist", return_value={}):
            return SteamLibrary()

    def test_pc_favorites_not_shown_when_no_favorites(self) -> None:
        """'PC Favorites' source entry is absent when no games are favorited."""
        games = [
            _make_steam_game("1", "Alpha", favorite=False),
        ]
        lib = self._make_lib(games)

        sources = [lib._sources_model.data(lib._sources_model.index(i, 0), 0x0101)
                   for i in range(lib._sources_model.rowCount())]
        # Check by iterating source names
        source_names = []
        from backend.steam_library import SteamSourceListModel
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )
        assert "PC Favorites" not in source_names

    def test_pc_favorites_shown_when_steam_game_favorited(self, tmp_path: Path) -> None:
        """'PC Favorites' source entry appears when a Steam game is favorited."""
        from backend.steam_library import SteamSourceListModel

        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        source_names = []
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )
        assert "PC Favorites" in source_names

    def test_pc_favorites_count_reflects_steam_favorites(self, tmp_path: Path) -> None:
        """'PC Favorites' gameCount reflects the number of favorited Steam games."""
        from backend.steam_library import SteamSourceListModel

        games = [
            _make_steam_game("1", "Alpha", favorite=False),
            _make_steam_game("2", "Beta", favorite=False),
        ]
        lib = self._make_lib(games)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)  # Alpha → favorite

        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            name = lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            if name == "PC Favorites":
                count = lib._sources_model.data(idx, SteamSourceListModel.GameCountRole)
                assert count == 1
                break
        else:
            pytest.fail("PC Favorites entry not found in sources model")

    def test_pc_favorites_disappears_when_unfavorited(self, tmp_path: Path) -> None:
        """'PC Favorites' source entry disappears when all games are unfavorited."""
        from backend.steam_library import SteamSourceListModel

        games = [_make_steam_game("440", "TF2", favorite=False)]
        lib = self._make_lib(games)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)  # → True
            lib.toggleFavorite(0)  # → False

        source_names = []
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )
        assert "PC Favorites" not in source_names

    def test_pc_favorites_position_after_recently_played(self, tmp_path: Path) -> None:
        """'PC Favorites' appears after 'Recently Played' and before 'Steam'."""
        from backend.steam_library import SteamSourceListModel

        # Beta has last_played > 0 so "Recently Played" will appear
        games = [
            _make_steam_game("1", "Alpha", favorite=False),
            SteamGame(
                app_id="2", name="Beta", install_dir="beta",
                last_played=1700000000, size_on_disk=0, image_path="", favorite=False,
            ),
        ]
        lib = self._make_lib(games)

        with patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib.toggleFavorite(0)  # Alpha → favorite

        source_names = []
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )

        assert "Recently Played" in source_names
        assert "PC Favorites" in source_names
        assert "Steam" in source_names

        rp_idx = source_names.index("Recently Played")
        fav_idx = source_names.index("PC Favorites")
        steam_idx = source_names.index("Steam")
        assert rp_idx < fav_idx < steam_idx


# ---------------------------------------------------------------------------
# SteamLibrary — setMoonlightFavoriteCount
# ---------------------------------------------------------------------------


class TestSteamLibrarySetMoonlightFavoriteCount:
    def _make_lib(self, games: list[SteamGame] | None = None):
        from backend.steam_library import SteamLibrary

        games = games or []
        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.read_gamelist", return_value={}):
            return SteamLibrary()

    def test_moonlight_favorites_included_in_pc_favorites_count(self) -> None:
        """setMoonlightFavoriteCount adds to the PC Favorites count."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_lib([_make_steam_game("1", "Alpha", favorite=True)])
        lib.setMoonlightFavoriteCount(3)

        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            name = lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            if name == "PC Favorites":
                count = lib._sources_model.data(idx, SteamSourceListModel.GameCountRole)
                assert count == 4  # 1 Steam + 3 Moonlight
                break
        else:
            pytest.fail("PC Favorites entry not found")

    def test_moonlight_favorites_alone_shows_pc_favorites(self) -> None:
        """PC Favorites appears when only Moonlight games are favorited."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_lib([_make_steam_game("1", "Alpha", favorite=False)])
        lib.setMoonlightFavoriteCount(2)

        source_names = []
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )
        assert "PC Favorites" in source_names

    def test_moonlight_favorites_zero_no_pc_favorites_when_no_steam(self) -> None:
        """PC Favorites absent when both Steam and Moonlight favorites are 0."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_lib([_make_steam_game("1", "Alpha", favorite=False)])
        lib.setMoonlightFavoriteCount(0)

        source_names = []
        for i in range(lib._sources_model.rowCount()):
            idx = lib._sources_model.index(i, 0)
            source_names.append(
                lib._sources_model.data(idx, SteamSourceListModel.NameRole)
            )
        assert "PC Favorites" not in source_names

    def test_set_moonlight_favorite_count_emits_sources_model_changed(self) -> None:
        """setMoonlightFavoriteCount emits sourcesModelChanged."""
        lib = self._make_lib()

        signals: list[bool] = []
        lib.sourcesModelChanged.connect(lambda: signals.append(True))
        lib.setMoonlightFavoriteCount(1)

        assert len(signals) >= 1


# ---------------------------------------------------------------------------
# MoonlightLibrary — toggleFavorite
# ---------------------------------------------------------------------------


class TestMoonlightLibraryToggleFavorite:
    def _make_lib_with_apps(self, apps: list[MoonlightApp]):
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = list(apps)
        lib._current_apps = list(apps)
        lib._apps_model.set_apps(apps)
        return lib

    def test_toggle_flips_favorite_to_true(self, tmp_path: Path) -> None:
        """toggleFavorite flips favorite from False to True."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._current_apps[0].favorite is True

    def test_toggle_flips_favorite_to_false(self, tmp_path: Path) -> None:
        """toggleFavorite flips favorite from True to False."""
        apps = [_make_moonlight_app("Desktop", favorite=True)]
        lib = self._make_lib_with_apps(apps)

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._current_apps[0].favorite is False

    def test_toggle_updates_all_apps(self, tmp_path: Path) -> None:
        """toggleFavorite also updates the matching app in _all_apps."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib._all_apps[0].favorite is True

    def test_toggle_emits_favorite_toggled_signal(self, tmp_path: Path) -> None:
        """toggleFavorite emits favoriteToggled with the new value."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        received: list[bool] = []
        lib.favoriteToggled.connect(lambda v: received.append(v))

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert received == [True]

    def test_toggle_emits_hosts_changed(self, tmp_path: Path) -> None:
        """toggleFavorite emits hostsChanged so main.py can update PC Favorites count."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        signals: list[bool] = []
        lib.hostsChanged.connect(lambda: signals.append(True))

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert len(signals) >= 1

    def test_toggle_out_of_range_is_noop(self, tmp_path: Path) -> None:
        """toggleFavorite with out-of-range index does nothing."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        received: list[bool] = []
        lib.favoriteToggled.connect(lambda v: received.append(v))

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(99)

        assert received == []
        assert lib._current_apps[0].favorite is False

    def test_toggle_persists_to_gamelist_xml(self, tmp_path: Path) -> None:
        """toggleFavorite writes the new favorite value to gamelist.xml."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        result = read_gamelist(tmp_path)
        assert result["Desktop"].favorite is True

    def test_toggle_round_trip_persistence(self, tmp_path: Path) -> None:
        """Toggle on then off — gamelist.xml reflects False after second toggle."""
        apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib = self._make_lib_with_apps(apps)

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)  # → True
            lib.toggleFavorite(0)  # → False

        result = read_gamelist(tmp_path)
        assert result["Desktop"].favorite is False


# ---------------------------------------------------------------------------
# MoonlightLibrary — favoriteCount property
# ---------------------------------------------------------------------------


class TestMoonlightLibraryFavoriteCount:
    def test_favorite_count_zero_when_no_apps(self) -> None:
        """favoriteCount is 0 when there are no apps."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert lib.favoriteCount == 0

    def test_favorite_count_zero_when_no_favorites(self) -> None:
        """favoriteCount is 0 when no apps are favorited."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [
            _make_moonlight_app("Desktop", favorite=False),
            _make_moonlight_app("Steam", favorite=False),
        ]
        assert lib.favoriteCount == 0

    def test_favorite_count_reflects_favorited_apps(self) -> None:
        """favoriteCount returns the number of favorited apps."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [
            _make_moonlight_app("Desktop", favorite=True),
            _make_moonlight_app("Steam", favorite=False),
            _make_moonlight_app("Cyberpunk", favorite=True),
        ]
        assert lib.favoriteCount == 2

    def test_favorite_count_updates_after_toggle(self, tmp_path: Path) -> None:
        """favoriteCount updates after toggleFavorite is called."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [_make_moonlight_app("Desktop", favorite=False)]
        lib._current_apps = list(lib._all_apps)

        assert lib.favoriteCount == 0

        with patch("backend.moonlight_library.get_moonlight_dir", return_value=tmp_path):
            lib.toggleFavorite(0)

        assert lib.favoriteCount == 1


# ---------------------------------------------------------------------------
# SteamLibrary — refresh populates favorite from cache
# ---------------------------------------------------------------------------


class TestSteamLibraryRefreshPopulatesFavorite:
    def test_refresh_populates_favorite_from_cache(self, tmp_path: Path) -> None:
        """refresh() populates game.favorite from the metadata cache."""
        from backend.steam_library import SteamLibrary
        from backend.metadata_gamelist import GameMetadata

        # Pre-populate gamelist.xml with a favorited game
        meta = GameMetadata(name="TF2", app_id="440", favorite=True)
        write_game_metadata(tmp_path, "440", meta)

        games = [_make_steam_game("440", "TF2", favorite=False)]

        with patch("backend.steam_library.discover_steam_games", return_value=games), \
             patch("backend.steam_library.get_steam_dir", return_value=tmp_path):
            lib = SteamLibrary()

        assert lib._all_games[0].favorite is True
