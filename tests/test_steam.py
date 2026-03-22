"""Tests for Task 002 — Steam Backend.

Covers:
  - steam_models: SteamGame dataclass fields and defaults
  - steam_parser.parse_acf: valid ACF, nested blocks, malformed input
  - steam_parser.discover_steam_games: mock filesystem with ACF files
  - steam_parser: filtering non-games (Proton, runtimes, redistributables, StateFlags)
  - steam_parser: artwork resolution (local cache found, not found)
  - SteamGameListModel: roles, data, set_games
  - SteamSourceListModel: roles, data, set_sources
  - SteamLibrary: model population, sorting (az, za, recent), getGame, launchGame
  - SteamLibrary: selectSource, refresh
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QProcess

from backend.steam_models import SteamGame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_acf(path: Path, app_id: str, name: str, state_flags: str = "4",
               last_played: int = 0, size_on_disk: int = 0,
               install_dir: str = "") -> Path:
    """Write a minimal appmanifest ACF file to *path* (a steamapps directory)."""
    acf_file = path / f"appmanifest_{app_id}.acf"
    install_dir = install_dir or name.lower().replace(" ", "")
    content = (
        '"AppState"\n'
        '{\n'
        f'\t"appid"\t\t"{app_id}"\n'
        f'\t"name"\t\t"{name}"\n'
        f'\t"installdir"\t"{install_dir}"\n'
        f'\t"StateFlags"\t"{state_flags}"\n'
        f'\t"LastPlayed"\t"{last_played}"\n'
        f'\t"SizeOnDisk"\t"{size_on_disk}"\n'
        '}\n'
    )
    acf_file.write_text(content, encoding="utf-8")
    return acf_file


# ---------------------------------------------------------------------------
# SteamGame dataclass
# ---------------------------------------------------------------------------


class TestSteamGame:
    def test_all_fields_set(self) -> None:
        game = SteamGame(
            app_id="440",
            name="Team Fortress 2",
            install_dir="Team Fortress 2",
            last_played=1700000000,
            size_on_disk=25_000_000_000,
            image_path="/path/to/poster.jpg",
        )
        assert game.app_id == "440"
        assert game.name == "Team Fortress 2"
        assert game.install_dir == "Team Fortress 2"
        assert game.last_played == 1700000000
        assert game.size_on_disk == 25_000_000_000
        assert game.image_path == "/path/to/poster.jpg"

    def test_empty_image_path(self) -> None:
        game = SteamGame(
            app_id="1",
            name="Game",
            install_dir="game",
            last_played=0,
            size_on_disk=0,
            image_path="",
        )
        assert game.image_path == ""


# ---------------------------------------------------------------------------
# parse_acf — VDF parser
# ---------------------------------------------------------------------------


class TestParseAcf:
    def test_basic_key_value(self, tmp_path: Path) -> None:
        """parse_acf correctly parses a simple flat ACF file."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "appmanifest_440.acf"
        acf.write_text(
            '"AppState"\n'
            '{\n'
            '\t"appid"\t\t"440"\n'
            '\t"name"\t\t"Team Fortress 2"\n'
            '\t"StateFlags"\t"4"\n'
            '}\n',
            encoding="utf-8",
        )
        result = parse_acf(acf)
        assert result is not None
        assert "AppState" in result
        state = result["AppState"]
        assert state["appid"] == "440"
        assert state["name"] == "Team Fortress 2"
        assert state["StateFlags"] == "4"

    def test_nested_blocks(self, tmp_path: Path) -> None:
        """parse_acf handles nested VDF blocks."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "appmanifest_570.acf"
        acf.write_text(
            '"AppState"\n'
            '{\n'
            '\t"appid"\t\t"570"\n'
            '\t"name"\t\t"Dota 2"\n'
            '\t"depots"\n'
            '\t{\n'
            '\t\t"branches"\n'
            '\t\t{\n'
            '\t\t\t"public"\t"1"\n'
            '\t\t}\n'
            '\t}\n'
            '}\n',
            encoding="utf-8",
        )
        result = parse_acf(acf)
        assert result is not None
        state = result["AppState"]
        assert state["appid"] == "570"
        assert isinstance(state["depots"], dict)
        assert isinstance(state["depots"]["branches"], dict)
        assert state["depots"]["branches"]["public"] == "1"

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        """parse_acf returns None when the file does not exist."""
        from backend.steam_parser import parse_acf

        result = parse_acf(tmp_path / "nonexistent.acf")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        """parse_acf returns None for an empty file."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "empty.acf"
        acf.write_text("", encoding="utf-8")
        result = parse_acf(acf)
        assert result is None

    def test_handles_backslash_escape_in_string(self, tmp_path: Path) -> None:
        """parse_acf handles backslash-escaped characters inside quoted strings."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "appmanifest_1.acf"
        acf.write_text(
            '"AppState"\n'
            '{\n'
            '\t"name"\t\t"Game \\"Quoted\\" Name"\n'
            '\t"StateFlags"\t"4"\n'
            '}\n',
            encoding="utf-8",
        )
        result = parse_acf(acf)
        assert result is not None
        assert result["AppState"]["name"] == 'Game "Quoted" Name'

    def test_whitespace_and_tabs_ignored(self, tmp_path: Path) -> None:
        """parse_acf handles various whitespace between tokens."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "appmanifest_2.acf"
        acf.write_text(
            '"AppState"   \n'
            '   {   \n'
            '   "appid"   "999"   \n'
            '   }   \n',
            encoding="utf-8",
        )
        result = parse_acf(acf)
        assert result is not None
        assert result["AppState"]["appid"] == "999"

    def test_multiple_top_level_keys(self, tmp_path: Path) -> None:
        """parse_acf handles multiple top-level key-value pairs."""
        from backend.steam_parser import parse_acf

        acf = tmp_path / "appmanifest_3.acf"
        acf.write_text(
            '"AppState"\n'
            '{\n'
            '\t"appid"\t"100"\n'
            '\t"name"\t"My Game"\n'
            '\t"installdir"\t"mygame"\n'
            '}\n',
            encoding="utf-8",
        )
        result = parse_acf(acf)
        assert result is not None
        state = result["AppState"]
        assert state["appid"] == "100"
        assert state["name"] == "My Game"
        assert state["installdir"] == "mygame"


# ---------------------------------------------------------------------------
# discover_steam_games — game discovery
# ---------------------------------------------------------------------------


class TestDiscoverSteamGames:
    def test_discovers_games_from_path(self, tmp_path: Path) -> None:
        """discover_steam_games finds games in the given steamapps directory."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")
        _write_acf(steamapps, "570", "Dota 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 2
        names = {g.name for g in games}
        assert names == {"Team Fortress 2", "Dota 2"}

    def test_returns_empty_when_no_paths_exist(self, tmp_path: Path) -> None:
        """discover_steam_games returns [] when no search paths exist."""
        from backend.steam_parser import discover_steam_games

        games = discover_steam_games([tmp_path / "nonexistent"])
        assert games == []

    def test_sorted_by_name_case_insensitive(self, tmp_path: Path) -> None:
        """discover_steam_games returns games sorted A-Z (case-insensitive)."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "3", "Zelda")
        _write_acf(steamapps, "1", "asteroids")
        _write_acf(steamapps, "2", "Mario")

        games = discover_steam_games([steamapps])
        names = [g.name for g in games]
        assert names == ["asteroids", "Mario", "Zelda"]

    def test_skips_nonexistent_paths_silently(self, tmp_path: Path) -> None:
        """discover_steam_games skips paths that don't exist without error."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([
            tmp_path / "nonexistent",
            steamapps,
        ])
        assert len(games) == 1

    def test_deduplication_across_paths(self, tmp_path: Path) -> None:
        """Games found in multiple paths are all included (no dedup by design)."""
        from backend.steam_parser import discover_steam_games

        path1 = tmp_path / "steamapps1"
        path2 = tmp_path / "steamapps2"
        path1.mkdir()
        path2.mkdir()
        _write_acf(path1, "440", "Team Fortress 2")
        _write_acf(path2, "570", "Dota 2")

        games = discover_steam_games([path1, path2])
        assert len(games) == 2

    def test_game_fields_populated_correctly(self, tmp_path: Path) -> None:
        """discover_steam_games populates all SteamGame fields from ACF data."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(
            steamapps, "440", "Team Fortress 2",
            state_flags="4",
            last_played=1700000000,
            size_on_disk=25_000_000_000,
            install_dir="Team Fortress 2",
        )

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        game = games[0]
        assert game.app_id == "440"
        assert game.name == "Team Fortress 2"
        assert game.install_dir == "Team Fortress 2"
        assert game.last_played == 1700000000
        assert game.size_on_disk == 25_000_000_000


# ---------------------------------------------------------------------------
# discover_steam_games — filtering non-games
# ---------------------------------------------------------------------------


class TestFilterNonGames:
    def test_filters_steamworks_redistributables_by_appid(self, tmp_path: Path) -> None:
        """AppID 228980 (Steamworks Common Redistributables) is filtered out."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "228980", "Steamworks Common Redistributables")
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].app_id == "440"

    def test_filters_name_containing_steamworks(self, tmp_path: Path) -> None:
        """Entries with 'Steamworks' in the name are filtered out."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "1001", "Steamworks SDK Redist")
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].name == "Team Fortress 2"

    def test_filters_name_containing_proton(self, tmp_path: Path) -> None:
        """Entries with 'Proton' in the name are filtered out."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "1420170", "Proton 7.0")
        _write_acf(steamapps, "961940", "Proton Experimental")
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].name == "Team Fortress 2"

    def test_filters_steam_linux_runtime(self, tmp_path: Path) -> None:
        """Entries starting with 'Steam Linux Runtime' are filtered out."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "1070560", "Steam Linux Runtime")
        _write_acf(steamapps, "1391110", "Steam Linux Runtime 3.0 (sniper)")
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].name == "Team Fortress 2"

    def test_filters_non_fully_installed_state_flags(self, tmp_path: Path) -> None:
        """Entries with StateFlags != '4' are filtered out."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        # StateFlags 2 = update required, 1026 = downloading
        _write_acf(steamapps, "100", "Downloading Game", state_flags="1026")
        _write_acf(steamapps, "101", "Update Required Game", state_flags="2")
        _write_acf(steamapps, "440", "Team Fortress 2", state_flags="4")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].name == "Team Fortress 2"

    def test_all_filters_combined(self, tmp_path: Path) -> None:
        """All filter rules work together; only real installed games pass."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "228980", "Steamworks Common Redistributables")
        _write_acf(steamapps, "1420170", "Proton 7.0")
        _write_acf(steamapps, "1070560", "Steam Linux Runtime")
        _write_acf(steamapps, "999", "Partial Install", state_flags="1026")
        _write_acf(steamapps, "440", "Team Fortress 2")
        _write_acf(steamapps, "570", "Dota 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 2
        names = {g.name for g in games}
        assert names == {"Team Fortress 2", "Dota 2"}


# ---------------------------------------------------------------------------
# Artwork resolution
# ---------------------------------------------------------------------------


class TestArtworkResolution:
    def test_finds_library_600x900_jpg(self, tmp_path: Path) -> None:
        """Artwork resolution prefers library_600x900.jpg."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")

        # Create the expected artwork path
        cache_dir = tmp_path / "appcache" / "librarycache" / "440"
        cache_dir.mkdir(parents=True)
        poster = cache_dir / "library_600x900.jpg"
        poster.write_bytes(b"fake image data")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].image_path == str(poster)

    def test_falls_back_to_header_jpg(self, tmp_path: Path) -> None:
        """Artwork resolution falls back to header.jpg when 600x900 is absent."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")

        cache_dir = tmp_path / "appcache" / "librarycache" / "440"
        cache_dir.mkdir(parents=True)
        header = cache_dir / "header.jpg"
        header.write_bytes(b"fake header image")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].image_path == str(header)

    def test_prefers_600x900_over_header(self, tmp_path: Path) -> None:
        """library_600x900.jpg is preferred over header.jpg when both exist."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")

        cache_dir = tmp_path / "appcache" / "librarycache" / "440"
        cache_dir.mkdir(parents=True)
        poster = cache_dir / "library_600x900.jpg"
        poster.write_bytes(b"poster")
        header = cache_dir / "header.jpg"
        header.write_bytes(b"header")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert games[0].image_path == str(poster)

    def test_cdn_fallback_when_no_local_artwork(self, tmp_path: Path) -> None:
        """image_path falls back to Steam CDN URL when no local artwork exists."""
        from backend.steam_parser import discover_steam_games

        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        _write_acf(steamapps, "440", "Team Fortress 2")

        games = discover_steam_games([steamapps])
        assert len(games) == 1
        assert "cdn.cloudflare.steamstatic.com" in games[0].image_path
        assert "440" in games[0].image_path


# ---------------------------------------------------------------------------
# SteamGameListModel
# ---------------------------------------------------------------------------


class TestSteamGameListModel:
    def _make_game(self, app_id: str = "440", name: str = "Team Fortress 2") -> SteamGame:
        return SteamGame(
            app_id=app_id,
            name=name,
            install_dir=name.lower().replace(" ", ""),
            last_played=1700000000,
            size_on_disk=1_000_000,
            image_path="/path/to/poster.jpg",
        )

    def test_roles_and_data(self) -> None:
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        game = self._make_game("440", "Team Fortress 2")
        model.set_games([game])

        assert model.rowCount() == 1
        idx = model.index(0, 0)
        assert model.data(idx, SteamGameListModel.AppIdRole) == "440"
        assert model.data(idx, SteamGameListModel.NameRole) == "Team Fortress 2"
        assert model.data(idx, SteamGameListModel.ImageLocalRole) == "/path/to/poster.jpg"
        assert model.data(idx, SteamGameListModel.LastPlayedRole) == 1700000000
        assert model.data(idx, SteamGameListModel.SizeOnDiskRole) == 1_000_000

    def test_role_names(self) -> None:
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        names = model.roleNames()
        assert b"appId" in names.values()
        assert b"name" in names.values()
        assert b"imageLocal" in names.values()
        assert b"lastPlayed" in names.values()
        assert b"sizeOnDisk" in names.values()

    def test_invalid_index_returns_none(self) -> None:
        from backend.steam_library import SteamGameListModel
        from PySide6.QtCore import QModelIndex

        model = SteamGameListModel()
        assert model.data(QModelIndex(), SteamGameListModel.NameRole) is None

    def test_out_of_range_index_returns_none(self) -> None:
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        model.set_games([self._make_game()])
        idx = model.index(99, 0)
        assert model.data(idx, SteamGameListModel.NameRole) is None

    def test_display_role_returns_name(self) -> None:
        from backend.steam_library import SteamGameListModel
        from PySide6.QtCore import Qt

        model = SteamGameListModel()
        model.set_games([self._make_game("1", "My Game")])
        idx = model.index(0, 0)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "My Game"

    def test_set_games_replaces_contents(self) -> None:
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        model.set_games([self._make_game("1", "First")])
        assert model.rowCount() == 1

        model.set_games([self._make_game("2", "Second"), self._make_game("3", "Third")])
        assert model.rowCount() == 2

    def test_parent_valid_returns_zero(self) -> None:
        from backend.steam_library import SteamGameListModel

        model = SteamGameListModel()
        model.set_games([self._make_game()])
        # A valid parent index means it's a tree node — list models return 0
        parent = model.index(0, 0)
        assert model.rowCount(parent) == 0


# ---------------------------------------------------------------------------
# SteamSourceListModel
# ---------------------------------------------------------------------------


class TestSteamSourceListModel:
    def test_roles_and_data(self) -> None:
        from backend.steam_library import SteamSourceListModel

        model = SteamSourceListModel()
        model.set_sources([{"name": "Steam", "gameCount": 42, "source": "steam"}])

        assert model.rowCount() == 1
        idx = model.index(0, 0)
        assert model.data(idx, SteamSourceListModel.NameRole) == "Steam"
        assert model.data(idx, SteamSourceListModel.GameCountRole) == 42
        assert model.data(idx, SteamSourceListModel.SourceRole) == "steam"

    def test_role_names(self) -> None:
        from backend.steam_library import SteamSourceListModel

        model = SteamSourceListModel()
        names = model.roleNames()
        assert b"name" in names.values()
        assert b"gameCount" in names.values()
        assert b"source" in names.values()

    def test_invalid_index_returns_none(self) -> None:
        from backend.steam_library import SteamSourceListModel
        from PySide6.QtCore import QModelIndex

        model = SteamSourceListModel()
        assert model.data(QModelIndex(), SteamSourceListModel.NameRole) is None

    def test_display_role_returns_name(self) -> None:
        from backend.steam_library import SteamSourceListModel
        from PySide6.QtCore import Qt

        model = SteamSourceListModel()
        model.set_sources([{"name": "Steam", "gameCount": 5, "source": "steam"}])
        idx = model.index(0, 0)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "Steam"

    def test_loading_role_returns_false_by_default(self) -> None:
        """LoadingRole returns False when 'loading' key is absent."""
        from backend.steam_library import SteamSourceListModel

        model = SteamSourceListModel()
        model.set_sources([{"name": "Steam", "gameCount": 5, "source": "steam"}])
        idx = model.index(0, 0)
        assert model.data(idx, SteamSourceListModel.LoadingRole) is False

    def test_loading_role_returns_true_when_set(self) -> None:
        """LoadingRole returns True when 'loading' key is True."""
        from backend.steam_library import SteamSourceListModel

        model = SteamSourceListModel()
        model.set_sources([{
            "name": "Moonlight Games",
            "gameCount": 0,
            "source": "moonlight",
            "loading": True,
        }])
        idx = model.index(0, 0)
        assert model.data(idx, SteamSourceListModel.LoadingRole) is True

    def test_loading_role_in_role_names(self) -> None:
        """roleNames includes 'loading' key."""
        from backend.steam_library import SteamSourceListModel

        model = SteamSourceListModel()
        names = model.roleNames()
        assert b"loading" in names.values()


# ---------------------------------------------------------------------------
# SteamLibrary — model population and refresh
# ---------------------------------------------------------------------------


class TestSteamLibraryModelPopulation:
    def test_initial_state_with_no_games(self, tmp_path: Path) -> None:
        """SteamLibrary initialises with empty models when no games are found."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        assert lib._games_model.rowCount() == 0
        assert lib._sources_model.rowCount() == 1  # "Steam" source always present

    def test_sources_model_has_steam_entry(self, tmp_path: Path) -> None:
        """sourcesModel always contains a 'Steam' entry."""
        from backend.steam_library import SteamLibrary, SteamSourceListModel

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        assert lib._sources_model.rowCount() == 1
        idx = lib._sources_model.index(0, 0)
        assert lib._sources_model.data(idx, SteamSourceListModel.NameRole) == "Steam"
        assert lib._sources_model.data(idx, SteamSourceListModel.SourceRole) == "steam"

    def test_game_count_in_sources_model(self) -> None:
        """sourcesModel gameCount reflects the number of discovered games."""
        from backend.steam_library import SteamLibrary, SteamSourceListModel

        games = [
            SteamGame("1", "Game A", "gamea", 0, 0, ""),
            SteamGame("2", "Game B", "gameb", 0, 0, ""),
        ]
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            lib = SteamLibrary()

        idx = lib._sources_model.index(0, 0)
        assert lib._sources_model.data(idx, SteamSourceListModel.GameCountRole) == 2

    def test_games_model_populated_after_init(self) -> None:
        """gamesModel is populated with discovered games on construction."""
        from backend.steam_library import SteamLibrary

        games = [
            SteamGame("440", "Team Fortress 2", "tf2", 0, 0, ""),
            SteamGame("570", "Dota 2", "dota2", 0, 0, ""),
        ]
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            lib = SteamLibrary()

        assert lib._games_model.rowCount() == 2

    def test_refresh_rescans_and_rebuilds_models(self) -> None:
        """refresh() re-scans ACF files and rebuilds both models."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        assert lib._games_model.rowCount() == 0

        new_games = [SteamGame("440", "Team Fortress 2", "tf2", 0, 0, "")]
        with patch("backend.steam_library.discover_steam_games", return_value=new_games):
            lib.refresh()

        assert lib._games_model.rowCount() == 1

    def test_refresh_emits_signals(self) -> None:
        """refresh() emits sourcesModelChanged and gamesModelChanged."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        sources_signals: list[bool] = []
        games_signals: list[bool] = []
        lib.sourcesModelChanged.connect(lambda: sources_signals.append(True))
        lib.gamesModelChanged.connect(lambda: games_signals.append(True))

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib.refresh()

        assert len(sources_signals) >= 1
        assert len(games_signals) >= 1


# ---------------------------------------------------------------------------
# SteamLibrary — getGame
# ---------------------------------------------------------------------------


class TestSteamLibraryGetGame:
    def _make_lib_with_games(self, games: list[SteamGame]):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=games):
            return SteamLibrary()

    def test_get_game_returns_dict(self) -> None:
        """getGame returns a dict with all expected keys."""
        games = [SteamGame("440", "Team Fortress 2", "tf2", 1700000000, 25_000_000, "/img.jpg")]
        lib = self._make_lib_with_games(games)

        result = lib.getGame(0)
        assert result["appId"] == "440"
        assert result["name"] == "Team Fortress 2"
        assert result["installDir"] == "tf2"
        assert result["lastPlayed"] == 1700000000
        assert result["sizeOnDisk"] == 25_000_000
        assert result["imagePath"] == "/img.jpg"

    def test_get_game_out_of_range_returns_empty(self) -> None:
        """getGame returns {} for out-of-range index."""
        lib = self._make_lib_with_games([])
        assert lib.getGame(0) == {}
        assert lib.getGame(-1) == {}
        assert lib.getGame(99) == {}

    def test_get_game_reflects_current_sort_order(self) -> None:
        """getGame returns the game at the sorted position."""
        games = [
            SteamGame("1", "Zelda", "zelda", 0, 0, ""),
            SteamGame("2", "Asteroids", "asteroids", 0, 0, ""),
        ]
        lib = self._make_lib_with_games(games)
        # After init, games are sorted A-Z: Asteroids first, Zelda second
        assert lib.getGame(0)["name"] == "Asteroids"
        assert lib.getGame(1)["name"] == "Zelda"


# ---------------------------------------------------------------------------
# SteamLibrary — launchGame
# ---------------------------------------------------------------------------


class TestSteamLibraryLaunchGame:
    def test_launch_calls_xdg_open_with_steam_url(self) -> None:
        """launchGame calls QProcess.startDetached with the correct steam:// URL."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        with patch("backend.steam_library.QProcess.startDetached") as mock_start:
            lib.launchGame("440")
            mock_start.assert_called_once_with("xdg-open", ["steam://rungameid/440"])

    def test_launch_empty_appid_is_noop(self) -> None:
        """launchGame with empty appId does nothing."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        with patch("backend.steam_library.QProcess.startDetached") as mock_start:
            lib.launchGame("")
            mock_start.assert_not_called()

    def test_launch_uses_correct_appid(self) -> None:
        """launchGame uses the exact appId passed in the URL."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        with patch("backend.steam_library.QProcess.startDetached") as mock_start:
            lib.launchGame("570")
            mock_start.assert_called_once_with("xdg-open", ["steam://rungameid/570"])

    def test_launch_emits_game_running(self) -> None:
        """launchGame emits gameRunning signal."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        signals = []
        lib.gameRunning.connect(lambda: signals.append("running"))

        with patch("backend.steam_library.QProcess.startDetached"):
            lib.launchGame("440")

        assert "running" in signals

    def test_notify_game_stopped_emits_signal(self) -> None:
        """notifyGameStopped emits gameStopped when a game was running."""
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        signals = []
        lib.gameStopped.connect(lambda: signals.append("stopped"))

        # Not running — should not emit
        lib.notifyGameStopped()
        assert len(signals) == 0

        # Launch a game, then notify stopped
        with patch("backend.steam_library.QProcess.startDetached"):
            lib.launchGame("440")
        lib.notifyGameStopped()
        assert "stopped" in signals

        # Second call should not emit again (already stopped)
        signals.clear()
        lib.notifyGameStopped()
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# SteamLibrary — sortGames
# ---------------------------------------------------------------------------


class TestSteamLibrarySortGames:
    def _make_lib_with_games(self, games: list[SteamGame]):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=games):
            return SteamLibrary()

    def _make_games(self) -> list[SteamGame]:
        return [
            SteamGame("1", "Zelda", "zelda", 1000, 0, ""),
            SteamGame("2", "Asteroids", "asteroids", 3000, 0, ""),
            SteamGame("3", "Mario", "mario", 2000, 0, ""),
        ]

    def test_sort_az(self) -> None:
        """sortGames('az') sorts alphabetically ascending."""
        lib = self._make_lib_with_games(self._make_games())
        lib.sortGames("az")
        names = [lib._current_games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_za(self) -> None:
        """sortGames('za') sorts alphabetically descending."""
        lib = self._make_lib_with_games(self._make_games())
        lib.sortGames("za")
        names = [lib._current_games[i].name for i in range(3)]
        assert names == ["Zelda", "Mario", "Asteroids"]

    def test_sort_recent(self) -> None:
        """sortGames('recent') sorts by LastPlayed descending, unplayed at end."""
        games = [
            SteamGame("1", "Alpha", "alpha", 1000, 0, ""),
            SteamGame("2", "Beta", "beta", 0, 0, ""),   # never played
            SteamGame("3", "Gamma", "gamma", 3000, 0, ""),
        ]
        lib = self._make_lib_with_games(games)
        lib.sortGames("recent")
        names = [lib._current_games[i].name for i in range(3)]
        # Gamma (3000) first, Alpha (1000) second, Beta (0 = unplayed) last
        assert names == ["Gamma", "Alpha", "Beta"]

    def test_sort_unknown_key_falls_back_to_az(self) -> None:
        """sortGames with unknown key falls back to A-Z."""
        lib = self._make_lib_with_games(self._make_games())
        lib.sortGames("unknown")
        names = [lib._current_games[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_emits_games_model_changed(self) -> None:
        """sortGames emits gamesModelChanged."""
        lib = self._make_lib_with_games(self._make_games())
        signals: list[bool] = []
        lib.gamesModelChanged.connect(lambda: signals.append(True))
        lib.sortGames("za")
        assert len(signals) == 1

    def test_sort_updates_games_model(self) -> None:
        """sortGames updates the gamesModel so QML sees the new order."""
        from backend.steam_library import SteamGameListModel

        lib = self._make_lib_with_games(self._make_games())
        lib.sortGames("za")

        idx = lib._games_model.index(0, 0)
        assert lib._games_model.data(idx, SteamGameListModel.NameRole) == "Zelda"


# ---------------------------------------------------------------------------
# SteamLibrary — selectSource
# ---------------------------------------------------------------------------


class TestSteamLibrarySelectSource:
    def test_select_source_rebuilds_games_model(self) -> None:
        """selectSource('steam') rebuilds the games model."""
        from backend.steam_library import SteamLibrary

        games = [SteamGame("440", "Team Fortress 2", "tf2", 0, 0, "")]
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            lib = SteamLibrary()

        signals: list[bool] = []
        lib.gamesModelChanged.connect(lambda: signals.append(True))
        lib.selectSource("steam")

        assert lib._games_model.rowCount() == 1
        assert len(signals) == 1

    def test_select_source_preserves_current_sort(self) -> None:
        """selectSource re-applies the current sort."""
        from backend.steam_library import SteamLibrary, SteamGameListModel

        games = [
            SteamGame("1", "Zelda", "zelda", 0, 0, ""),
            SteamGame("2", "Asteroids", "asteroids", 0, 0, ""),
        ]
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            lib = SteamLibrary()

        lib.sortGames("za")
        lib.selectSource("steam")

        # After selectSource, sort is re-applied (za = Zelda first)
        idx = lib._games_model.index(0, 0)
        assert lib._games_model.data(idx, SteamGameListModel.NameRole) == "Zelda"


# ---------------------------------------------------------------------------
# SteamLibrary — properties exposed to QML
# ---------------------------------------------------------------------------


class TestSteamLibraryProperties:
    def test_sources_model_property(self) -> None:
        """sourcesModel property returns the SteamSourceListModel."""
        from backend.steam_library import SteamLibrary, SteamSourceListModel

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        assert isinstance(lib.sourcesModel, SteamSourceListModel)

    def test_games_model_property(self) -> None:
        """gamesModel property returns the SteamGameListModel."""
        from backend.steam_library import SteamLibrary, SteamGameListModel

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            lib = SteamLibrary()

        assert isinstance(lib.gamesModel, SteamGameListModel)
