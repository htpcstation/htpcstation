"""Tests for gamelist.py parser bug fixes (Task 006a).

Covers:
  - Fix 1: _resolve_path uses removeprefix("./") not lstrip("./")
  - Fix 2: Games with missing/empty <path> are skipped with a warning
"""

from __future__ import annotations

import logging
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.gamelist import _resolve_path, parse_gamelist


# ---------------------------------------------------------------------------
# Fix 1: removeprefix vs lstrip
# ---------------------------------------------------------------------------

class TestResolvePath:
    def test_normal_relative_path(self, tmp_path: Path) -> None:
        """Standard './game.rom' path is resolved correctly."""
        result = _resolve_path(tmp_path, "./game.rom")
        assert result == tmp_path / "game.rom"

    def test_dotfile_path_not_corrupted(self, tmp_path: Path) -> None:
        """Paths like './...hidden.rom' must NOT have leading dots stripped.

        lstrip("./") would remove all leading '.' and '/' chars, corrupting
        '...hidden.rom' → 'hidden.rom'.  removeprefix("./") only removes the
        exact two-character prefix.
        """
        result = _resolve_path(tmp_path, "./...hidden.rom")
        assert result == tmp_path / "...hidden.rom"

    def test_path_without_prefix(self, tmp_path: Path) -> None:
        """Paths that don't start with './' are passed through unchanged."""
        result = _resolve_path(tmp_path, "subdir/game.rom")
        assert result == tmp_path / "subdir/game.rom"

    def test_nested_relative_path(self, tmp_path: Path) -> None:
        """Nested paths like './media/images/cover.png' resolve correctly."""
        result = _resolve_path(tmp_path, "./media/images/cover.png")
        assert result == tmp_path / "media/images/cover.png"


# ---------------------------------------------------------------------------
# Fix 2: skip games with missing/empty <path>
# ---------------------------------------------------------------------------

def _write_gamelist(tmp_path: Path, xml_body: str) -> Path:
    """Write a minimal gamelist.xml to *tmp_path* and return the directory."""
    content = f"<gameList>{xml_body}</gameList>"
    (tmp_path / "gamelist.xml").write_text(content, encoding="utf-8")
    return tmp_path


class TestMissingPath:
    def test_empty_path_tag_is_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A <game> with an empty <path> tag is skipped and a warning is logged."""
        _write_gamelist(
            tmp_path,
            textwrap.dedent("""\
                <game>
                    <path></path>
                    <name>Bad Game</name>
                </game>
                <game>
                    <path>./good.rom</path>
                    <name>Good Game</name>
                </game>
            """),
        )
        with caplog.at_level(logging.WARNING, logger="backend.gamelist"):
            games = parse_gamelist(tmp_path)

        assert len(games) == 1
        assert games[0].name == "Good Game"
        assert any("Bad Game" in record.message for record in caplog.records)

    def test_missing_path_tag_is_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A <game> with no <path> element at all is skipped and a warning is logged."""
        _write_gamelist(
            tmp_path,
            textwrap.dedent("""\
                <game>
                    <name>No Path Game</name>
                </game>
                <game>
                    <path>./good.rom</path>
                    <name>Good Game</name>
                </game>
            """),
        )
        with caplog.at_level(logging.WARNING, logger="backend.gamelist"):
            games = parse_gamelist(tmp_path)

        assert len(games) == 1
        assert games[0].name == "Good Game"
        assert any("No Path Game" in record.message for record in caplog.records)

    def test_valid_game_is_not_skipped(self, tmp_path: Path) -> None:
        """A <game> with a valid <path> is parsed normally."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>My Game</name></game>",
        )
        games = parse_gamelist(tmp_path)
        assert len(games) == 1
        assert games[0].name == "My Game"
        assert games[0].path == tmp_path / "game.rom"
