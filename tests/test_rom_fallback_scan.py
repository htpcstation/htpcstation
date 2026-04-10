"""Tests for filesystem fallback scan when gamelist.xml is missing.

Covers:
  1. Folder with no gamelist.xml + known system -> games populated from matching files
  2. Folder with no gamelist.xml + unknown system (no extensions) -> system skipped
  3. Folder with gamelist.xml -> gamelist.xml used (not filesystem scan)
  4. Title cleaning: parentheses, brackets, and combinations stripped correctly
  5. Extension matching is case-insensitive
  6. Non-matching extensions are ignored
  7. Files are sorted alphabetically by cleaned name
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import Config
from backend.library import GameLibrary, _clean_rom_title, _scan_rom_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(system_path: Path, xml_body: str) -> None:
    """Write a minimal gamelist.xml to *system_path*."""
    content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
    (system_path / "gamelist.xml").write_text(content, encoding="utf-8")


def _make_config_mock(
    rom_dir: Path,
    *,
    known_systems: dict[str, tuple[str, list[str]]] | None = None,
) -> MagicMock:
    """Build a Config mock.

    *known_systems* maps folder_name -> (display_name, extensions).
    Folders not in *known_systems* return an unknown system config with
    empty extensions.
    """
    if known_systems is None:
        known_systems = {}

    config = MagicMock(spec=Config)
    config.rom_directory = rom_dir

    def _get_system(folder_name: str) -> MagicMock:
        if folder_name in known_systems:
            display, exts = known_systems[folder_name]
            return MagicMock(display_name=display, core="core.so", extensions=exts)
        return MagicMock(display_name=folder_name, core="", extensions=[])

    config.get_system.side_effect = _get_system
    return config


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------


class TestCleanRomTitle:
    def test_strips_parentheses(self):
        assert _clean_rom_title("Super Mario Bros (USA).nes") == "Super Mario Bros"

    def test_strips_brackets(self):
        assert _clean_rom_title("Zelda [Europe].gba") == "Zelda"

    def test_strips_mixed(self):
        assert _clean_rom_title("Zelda [Europe] (Rev 1).gba") == "Zelda"

    def test_plain_name(self):
        assert _clean_rom_title("Castlevania.sfc") == "Castlevania"

    def test_multiple_parenthesized_groups(self):
        assert _clean_rom_title("Game (USA) (Rev 2).nes") == "Game"

    def test_whitespace_only_after_strip(self):
        # Edge case: everything is in brackets
        assert _clean_rom_title("(USA) [v1.0].nes") == ""


# ---------------------------------------------------------------------------
# _scan_rom_files (unit-level)
# ---------------------------------------------------------------------------


class TestScanRomFiles:
    def test_matches_extensions(self, tmp_path: Path):
        (tmp_path / "game.gba").touch()
        (tmp_path / "readme.txt").touch()
        games = _scan_rom_files(tmp_path, "gba", [".gba"])
        assert len(games) == 1
        assert games[0].name == "game"
        assert games[0].system_folder == "gba"

    def test_case_insensitive_extensions(self, tmp_path: Path):
        (tmp_path / "Game.GBA").touch()
        games = _scan_rom_files(tmp_path, "gba", [".gba"])
        assert len(games) == 1
        assert games[0].name == "Game"

    def test_non_matching_extensions_ignored(self, tmp_path: Path):
        (tmp_path / "music.mp3").touch()
        (tmp_path / "notes.txt").touch()
        games = _scan_rom_files(tmp_path, "gba", [".gba"])
        assert games == []

    def test_sorted_by_cleaned_name(self, tmp_path: Path):
        (tmp_path / "Zelda (USA).gba").touch()
        (tmp_path / "Advance Wars.gba").touch()
        (tmp_path / "Mario (EU).gba").touch()
        games = _scan_rom_files(tmp_path, "gba", [".gba"])
        names = [g.name for g in games]
        assert names == ["Advance Wars", "Mario", "Zelda"]

    def test_skips_directories(self, tmp_path: Path):
        (tmp_path / "subdir.gba").mkdir()
        (tmp_path / "real.gba").touch()
        games = _scan_rom_files(tmp_path, "gba", [".gba"])
        assert len(games) == 1
        assert games[0].name == "real"

    def test_multiple_extensions(self, tmp_path: Path):
        (tmp_path / "game1.smc").touch()
        (tmp_path / "game2.sfc").touch()
        games = _scan_rom_files(tmp_path, "snes", [".smc", ".sfc"])
        assert len(games) == 2


# ---------------------------------------------------------------------------
# Integration: _scan with filesystem fallback
# ---------------------------------------------------------------------------


class TestScanFallbackIntegration:
    def test_known_system_no_gamelist_populates_from_files(self, tmp_path: Path):
        """Folder with no gamelist.xml + known system -> games from matching files."""
        gba_dir = tmp_path / "gba"
        gba_dir.mkdir()
        (gba_dir / "Super Mario (USA).gba").touch()
        (gba_dir / "Zelda.gba").touch()

        config = _make_config_mock(
            tmp_path,
            known_systems={"gba": ("Game Boy Advance", [".gba"])},
        )
        lib = GameLibrary(config)

        # Find the gba system (skip collection systems)
        real = [s for s in lib._systems if not s.folder_name.startswith("_")]
        assert len(real) == 1
        assert real[0].folder_name == "gba"
        assert real[0].game_count == 2
        names = [g.name for g in real[0].games]
        assert names == ["Super Mario", "Zelda"]

    def test_unknown_system_no_gamelist_is_skipped(self, tmp_path: Path):
        """Folder with no gamelist.xml + unknown system -> system skipped."""
        unknown_dir = tmp_path / "unknown_sys"
        unknown_dir.mkdir()
        (unknown_dir / "something.rom").touch()

        config = _make_config_mock(tmp_path)  # no known systems
        lib = GameLibrary(config)

        real = [s for s in lib._systems if not s.folder_name.startswith("_")]
        assert len(real) == 0

    def test_gamelist_takes_precedence(self, tmp_path: Path):
        """Folder with gamelist.xml -> gamelist.xml used, not filesystem scan."""
        gba_dir = tmp_path / "gba"
        gba_dir.mkdir()
        # ROM file on disk
        (gba_dir / "SomeRom.gba").touch()
        # gamelist.xml with a different game name
        _write_gamelist(
            gba_dir,
            '<game><path>./SomeRom.gba</path><name>From Gamelist</name></game>',
        )

        config = _make_config_mock(
            tmp_path,
            known_systems={"gba": ("Game Boy Advance", [".gba"])},
        )
        lib = GameLibrary(config)

        real = [s for s in lib._systems if not s.folder_name.startswith("_")]
        assert len(real) == 1
        assert real[0].games[0].name == "From Gamelist"
