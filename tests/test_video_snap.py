"""Tests for Task 021 — Video Snap Playback.

Covers:
  - getGame() returns a file:// URL for videoPath when a video exists
  - getGame() returns an empty string for videoPath when no video exists
  - GameListModel VideoPathRole returns a file:// URL when a video exists
  - GameListModel VideoPathRole returns an empty string when no video exists
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import Config
from backend.library import GameLibrary, GameListModel
from backend.models import Game


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
# getGame() — videoPath field
# ---------------------------------------------------------------------------


class TestGetGameVideoPath:
    def test_video_path_returns_file_url_when_video_exists(self, tmp_path: Path) -> None:
        """getGame() returns a file:// URL for videoPath when the video file exists."""
        system_dir = tmp_path / "ngpc"
        system_dir.mkdir()
        video_file = system_dir / "videos" / "game.mp4"
        video_file.parent.mkdir(parents=True)
        video_file.touch()

        _write_gamelist(
            system_dir,
            "<game>"
            "<path>./game.rom</path>"
            "<name>Test Game</name>"
            "<video>./videos/game.mp4</video>"
            "</game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="Neo Geo Pocket Color", core="core.so", extensions=[".rom"]
        )
        library = GameLibrary(config)
        library.selectSystem("ngpc")

        game_dict = library.getGame(0)
        assert game_dict["videoPath"].startswith("file://"), (
            f"Expected file:// URL, got: {game_dict['videoPath']!r}"
        )
        assert "game.mp4" in game_dict["videoPath"]

    def test_video_path_returns_empty_string_when_no_video(self, tmp_path: Path) -> None:
        """getGame() returns an empty string for videoPath when no video is set."""
        library = _make_library(
            tmp_path,
            {
                "snes": "<game><path>./game.rom</path><name>No Video Game</name></game>",
            },
        )
        library.selectSystem("snes")

        game_dict = library.getGame(0)
        assert game_dict["videoPath"] == ""

    def test_video_path_not_file_url_raw_path(self, tmp_path: Path) -> None:
        """videoPath must NOT be a raw filesystem path (no file:// prefix would be wrong)."""
        system_dir = tmp_path / "ngpc"
        system_dir.mkdir()
        video_file = system_dir / "videos" / "game.mp4"
        video_file.parent.mkdir(parents=True)
        video_file.touch()

        _write_gamelist(
            system_dir,
            "<game>"
            "<path>./game.rom</path>"
            "<name>Test Game</name>"
            "<video>./videos/game.mp4</video>"
            "</game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="Neo Geo Pocket Color", core="core.so", extensions=[".rom"]
        )
        library = GameLibrary(config)
        library.selectSystem("ngpc")

        game_dict = library.getGame(0)
        # Must not be a bare path like "/home/..."
        assert not game_dict["videoPath"].startswith("/"), (
            f"videoPath should be a file:// URL, not a bare path: {game_dict['videoPath']!r}"
        )


# ---------------------------------------------------------------------------
# GameListModel — VideoPathRole
# ---------------------------------------------------------------------------


class TestGameListModelVideoPathRole:
    def test_video_path_role_returns_file_url(self, tmp_path: Path) -> None:
        """VideoPathRole returns a file:// URL when game has a video_path."""
        video_file = tmp_path / "game.mp4"
        video_file.touch()

        game = Game(
            path=tmp_path / "game.rom",
            name="Test Game",
            video_path=video_file,
        )
        model = GameListModel([game])
        idx = model.index(0, 0)
        value = model.data(idx, GameListModel.VideoPathRole)

        assert isinstance(value, str)
        assert value.startswith("file://"), f"Expected file:// URL, got: {value!r}"
        assert "game.mp4" in value

    def test_video_path_role_returns_empty_string_when_none(self) -> None:
        """VideoPathRole returns an empty string when game.video_path is None."""
        game = Game(
            path=Path("/roms/game.rom"),
            name="No Video Game",
            video_path=None,
        )
        model = GameListModel([game])
        idx = model.index(0, 0)
        value = model.data(idx, GameListModel.VideoPathRole)

        assert value == ""
