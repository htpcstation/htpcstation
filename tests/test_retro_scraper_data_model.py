"""Tests for Task 001 — Data model + gamelist.xml extension.

Covers:
  - parse_gamelist populates thumbnail_path, marquee_path, screenshot_path
    from a gamelist.xml that contains those tags
  - parse_gamelist leaves them None when the tags are absent
  - parse_gamelist leaves them None when the file referenced does not exist
  - write_game_entry creates gamelist.xml when absent
  - write_game_entry appends a new entry when the ROM isn't in the file yet
  - write_game_entry updates in-place when the ROM is already present
  - write_game_entry never touches <image>, <playcount>, <gametime>,
    <lastplayed>, or <favorite>
  - write_game_entry skips empty/None fields
  - GameListModel exposes thumbnailPath, marqueePath, screenshotPath roles
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.gamelist import parse_gamelist, write_game_entry
from backend.models import Game


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(directory: Path, xml_body: str) -> None:
    """Write a minimal gamelist.xml to *directory*."""
    content = f"<gameList>{xml_body}</gameList>"
    (directory / "gamelist.xml").write_text(content, encoding="utf-8")


def _make_media_file(directory: Path, rel: str) -> Path:
    """Create a stub media file at *directory/rel* and return its absolute path."""
    p = directory / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"stub")
    return p


def _read_gamelist_xml(directory: Path) -> ET.Element:
    """Parse gamelist.xml in *directory* and return the root element."""
    return ET.parse(directory / "gamelist.xml").getroot()


def _game_elem(root: ET.Element, rel_path: str) -> ET.Element | None:
    """Return the first <game> element whose <path> matches *rel_path*, or None."""
    for elem in root.findall("game"):
        path_elem = elem.find("path")
        if path_elem is not None and (path_elem.text or "").strip() == rel_path:
            return elem
    return None


# ---------------------------------------------------------------------------
# parse_gamelist: new media fields
# ---------------------------------------------------------------------------


class TestParseGamelistNewFields:
    def test_all_three_fields_present_and_files_exist(self, tmp_path: Path) -> None:
        """thumbnail_path, marquee_path, screenshot_path are populated when files exist."""
        thumb = _make_media_file(tmp_path, "media/thumbnail.png")
        marquee = _make_media_file(tmp_path, "media/marquee.png")
        screenshot = _make_media_file(tmp_path, "media/screenshot.png")

        _write_gamelist(
            tmp_path,
            f"""
            <game>
                <path>./game.rom</path>
                <name>Test Game</name>
                <thumbnail>./media/thumbnail.png</thumbnail>
                <marquee>./media/marquee.png</marquee>
                <screenshot>./media/screenshot.png</screenshot>
            </game>
            """,
        )

        games = parse_gamelist(tmp_path)
        assert len(games) == 1
        assert games[0].thumbnail_path == thumb
        assert games[0].marquee_path == marquee
        assert games[0].screenshot_path == screenshot

    def test_fields_absent_from_xml_are_none(self, tmp_path: Path) -> None:
        """thumbnail_path, marquee_path, screenshot_path are None when tags are absent."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>No Media</name></game>",
        )
        games = parse_gamelist(tmp_path)
        assert len(games) == 1
        assert games[0].thumbnail_path is None
        assert games[0].marquee_path is None
        assert games[0].screenshot_path is None

    def test_fields_none_when_file_does_not_exist(self, tmp_path: Path) -> None:
        """thumbnail_path, marquee_path, screenshot_path are None when the referenced file is missing."""
        _write_gamelist(
            tmp_path,
            """
            <game>
                <path>./game.rom</path>
                <name>Missing Media</name>
                <thumbnail>./media/missing_thumb.png</thumbnail>
                <marquee>./media/missing_marquee.png</marquee>
                <screenshot>./media/missing_screenshot.png</screenshot>
            </game>
            """,
        )
        games = parse_gamelist(tmp_path)
        assert len(games) == 1
        assert games[0].thumbnail_path is None
        assert games[0].marquee_path is None
        assert games[0].screenshot_path is None

    def test_partial_fields(self, tmp_path: Path) -> None:
        """Only existing files are populated; missing ones stay None."""
        thumb = _make_media_file(tmp_path, "media/thumbnail.png")
        # marquee and screenshot files are intentionally NOT created

        _write_gamelist(
            tmp_path,
            """
            <game>
                <path>./game.rom</path>
                <name>Partial Media</name>
                <thumbnail>./media/thumbnail.png</thumbnail>
                <marquee>./media/missing_marquee.png</marquee>
            </game>
            """,
        )
        games = parse_gamelist(tmp_path)
        assert len(games) == 1
        assert games[0].thumbnail_path == thumb
        assert games[0].marquee_path is None
        assert games[0].screenshot_path is None


# ---------------------------------------------------------------------------
# write_game_entry: create / append / update
# ---------------------------------------------------------------------------


def _make_game(tmp_path: Path, rom_name: str = "game.rom", **kwargs) -> Game:
    """Return a minimal Game with the given overrides."""
    defaults = dict(
        path=tmp_path / rom_name,
        name="Test Game",
        description="",
        rating=0.0,
        release_date="",
        developer="",
        publisher="",
        genre="",
        players="",
    )
    defaults.update(kwargs)
    return Game(**defaults)


class TestWriteGameEntryCreate:
    def test_creates_gamelist_when_absent(self, tmp_path: Path) -> None:
        """write_game_entry creates gamelist.xml when the file does not exist."""
        game = _make_game(tmp_path, name="New Game")
        write_game_entry(tmp_path, game)

        assert (tmp_path / "gamelist.xml").exists()
        root = _read_gamelist_xml(tmp_path)
        assert root.tag == "gameList"
        assert _game_elem(root, "./game.rom") is not None

    def test_new_entry_has_correct_path(self, tmp_path: Path) -> None:
        """The created entry has the correct <path> value."""
        game = _make_game(tmp_path, name="New Game")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None

    def test_name_written(self, tmp_path: Path) -> None:
        """<name> is written correctly."""
        game = _make_game(tmp_path, name="My Game")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        name_elem = elem.find("name")
        assert name_elem is not None
        assert name_elem.text == "My Game"

    def test_string_fields_written(self, tmp_path: Path) -> None:
        """All non-empty string metadata fields are written."""
        game = _make_game(
            tmp_path,
            name="RPG",
            description="An adventure",
            release_date="19990527T000000",
            developer="Dev Inc",
            publisher="Pub Inc",
            genre="RPG",
            players="1",
        )
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None

        def _text(tag: str) -> str:
            child = elem.find(tag)
            return (child.text or "").strip() if child is not None else ""

        assert _text("name") == "RPG"
        assert _text("desc") == "An adventure"
        assert _text("releasedate") == "19990527T000000"
        assert _text("developer") == "Dev Inc"
        assert _text("publisher") == "Pub Inc"
        assert _text("genre") == "RPG"
        assert _text("players") == "1"

    def test_rating_formatted_to_two_decimal_places(self, tmp_path: Path) -> None:
        """Rating is written as a two-decimal float string."""
        game = _make_game(tmp_path, name="Rated", rating=0.75)
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        rating_elem = elem.find("rating")
        assert rating_elem is not None
        assert rating_elem.text == "0.75"

    def test_path_fields_written_as_relative(self, tmp_path: Path) -> None:
        """Media path fields are written as relative paths."""
        thumb = _make_media_file(tmp_path, "media/thumb.png")
        marquee = _make_media_file(tmp_path, "media/marquee.png")
        screenshot = _make_media_file(tmp_path, "media/screenshot.png")
        video = _make_media_file(tmp_path, "media/video.mp4")

        game = _make_game(
            tmp_path,
            name="Media Game",
            thumbnail_path=thumb,
            marquee_path=marquee,
            screenshot_path=screenshot,
            video_path=video,
        )
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None

        def _text(tag: str) -> str:
            child = elem.find(tag)
            return (child.text or "").strip() if child is not None else ""

        assert _text("thumbnail") == "./media/thumb.png"
        assert _text("marquee") == "./media/marquee.png"
        assert _text("screenshot") == "./media/screenshot.png"
        assert _text("video") == "./media/video.mp4"


class TestWriteGameEntryAppend:
    def test_appends_new_entry_to_existing_file(self, tmp_path: Path) -> None:
        """A new ROM is appended when the file exists but doesn't contain that entry."""
        _write_gamelist(
            tmp_path,
            "<game><path>./existing.rom</path><name>Existing</name></game>",
        )

        game = _make_game(tmp_path, rom_name="new.rom", name="New Game")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        game_elems = root.findall("game")
        assert len(game_elems) == 2
        assert _game_elem(root, "./existing.rom") is not None
        assert _game_elem(root, "./new.rom") is not None

    def test_existing_entry_not_touched(self, tmp_path: Path) -> None:
        """Existing entries are not modified when appending a new entry."""
        _write_gamelist(
            tmp_path,
            "<game><path>./existing.rom</path><name>Existing</name><playcount>5</playcount></game>",
        )

        game = _make_game(tmp_path, rom_name="new.rom", name="New Game")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        existing = _game_elem(root, "./existing.rom")
        assert existing is not None
        pc = existing.find("playcount")
        assert pc is not None and pc.text == "5"


class TestWriteGameEntryUpdateInPlace:
    def test_updates_existing_entry(self, tmp_path: Path) -> None:
        """When the ROM is already in gamelist.xml, the entry is updated in-place."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Old Name</name></game>",
        )

        game = _make_game(tmp_path, name="New Name")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        game_elems = root.findall("game")
        assert len(game_elems) == 1  # no duplicate added

        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        name_elem = elem.find("name")
        assert name_elem is not None
        assert name_elem.text == "New Name"

    def test_does_not_touch_stats_fields(self, tmp_path: Path) -> None:
        """write_game_entry never modifies <image>, <playcount>, <gametime>, <lastplayed>, <favorite>."""
        _write_gamelist(
            tmp_path,
            """
            <game>
                <path>./game.rom</path>
                <name>Stats Game</name>
                <image>./miximage.png</image>
                <playcount>10</playcount>
                <gametime>3600</gametime>
                <lastplayed>20240101T120000</lastplayed>
                <favorite>true</favorite>
            </game>
            """,
        )

        game = _make_game(tmp_path, name="Updated Name", description="New desc")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None

        def _text(tag: str) -> str:
            child = elem.find(tag)
            return (child.text or "").strip() if child is not None else ""

        # Stats fields untouched
        assert _text("image") == "./miximage.png"
        assert _text("playcount") == "10"
        assert _text("gametime") == "3600"
        assert _text("lastplayed") == "20240101T120000"
        assert _text("favorite") == "true"

        # Updated fields written
        assert _text("name") == "Updated Name"
        assert _text("desc") == "New desc"


class TestWriteGameEntryFieldSkipping:
    def test_empty_string_fields_not_written(self, tmp_path: Path) -> None:
        """Empty string fields are not written to the XML."""
        game = _make_game(tmp_path, name="Game", description="", developer="", genre="")
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        assert elem.find("desc") is None
        assert elem.find("developer") is None
        assert elem.find("genre") is None

    def test_zero_rating_not_written(self, tmp_path: Path) -> None:
        """Rating of 0.0 is not written."""
        game = _make_game(tmp_path, name="Game", rating=0.0)
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        assert elem.find("rating") is None

    def test_none_path_fields_not_written(self, tmp_path: Path) -> None:
        """None path fields are not written to the XML."""
        game = _make_game(
            tmp_path,
            name="Game",
            thumbnail_path=None,
            marquee_path=None,
            screenshot_path=None,
            video_path=None,
        )
        write_game_entry(tmp_path, game)

        root = _read_gamelist_xml(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        assert elem.find("thumbnail") is None
        assert elem.find("marquee") is None
        assert elem.find("screenshot") is None
        assert elem.find("video") is None


# ---------------------------------------------------------------------------
# GameListModel: new roles
# ---------------------------------------------------------------------------


class TestGameListModelNewRoles:
    """Verify that the three new roles exist and return correct values."""

    def _make_model(self, games: list[Game]):
        """Import GameListModel here so PySide6 is only needed if Qt is available."""
        try:
            from backend.library import GameListModel
            from PySide6.QtCore import QModelIndex
        except ImportError:
            pytest.skip("PySide6 not available")
        return GameListModel(games), QModelIndex

    def test_role_names_contain_new_fields(self, tmp_path: Path) -> None:
        """thumbnailPath, marqueePath, screenshotPath are in roleNames."""
        try:
            from backend.library import GameListModel
        except ImportError:
            pytest.skip("PySide6 not available")

        model = GameListModel([])
        names = model.roleNames()
        assert b"thumbnailPath" in names.values()
        assert b"marqueePath" in names.values()
        assert b"screenshotPath" in names.values()

    def test_role_ids_are_correct(self, tmp_path: Path) -> None:
        """ThumbnailPathRole=273, MarqueePathRole=274, ScreenshotPathRole=275."""
        try:
            from backend.library import GameListModel
            from PySide6.QtCore import Qt
        except ImportError:
            pytest.skip("PySide6 not available")

        assert GameListModel.ThumbnailPathRole == Qt.ItemDataRole.UserRole + 17
        assert GameListModel.MarqueePathRole == Qt.ItemDataRole.UserRole + 18
        assert GameListModel.ScreenshotPathRole == Qt.ItemDataRole.UserRole + 19

    def test_new_roles_return_url_when_path_set(self, tmp_path: Path) -> None:
        """data() returns a file:// URL string when the path is set."""
        try:
            from backend.library import GameListModel
            from PySide6.QtCore import QModelIndex, QUrl
        except ImportError:
            pytest.skip("PySide6 not available")

        thumb = _make_media_file(tmp_path, "thumb.png")
        marquee = _make_media_file(tmp_path, "marquee.png")
        screenshot = _make_media_file(tmp_path, "screenshot.png")

        game = Game(
            path=tmp_path / "game.rom",
            name="Game",
            thumbnail_path=thumb,
            marquee_path=marquee,
            screenshot_path=screenshot,
        )
        model = GameListModel([game])
        idx = model.index(0, 0)

        assert model.data(idx, model.ThumbnailPathRole) == QUrl.fromLocalFile(str(thumb)).toString()
        assert model.data(idx, model.MarqueePathRole) == QUrl.fromLocalFile(str(marquee)).toString()
        assert model.data(idx, model.ScreenshotPathRole) == QUrl.fromLocalFile(str(screenshot)).toString()

    def test_new_roles_return_none_when_path_not_set(self, tmp_path: Path) -> None:
        """data() returns None when the path fields are None."""
        try:
            from backend.library import GameListModel
        except ImportError:
            pytest.skip("PySide6 not available")

        game = Game(
            path=tmp_path / "game.rom",
            name="Game",
            thumbnail_path=None,
            marquee_path=None,
            screenshot_path=None,
        )
        model = GameListModel([game])
        idx = model.index(0, 0)

        assert model.data(idx, model.ThumbnailPathRole) is None
        assert model.data(idx, model.MarqueePathRole) is None
        assert model.data(idx, model.ScreenshotPathRole) is None
