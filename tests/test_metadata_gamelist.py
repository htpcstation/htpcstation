"""Tests for backend/metadata_gamelist.py.

Covers:
  - read_gamelist: well-formed file with Steam (appid) and Moonlight (no appid) entries
  - read_gamelist: missing file → empty dict
  - read_gamelist: malformed XML → empty dict + warning logged
  - write_game_metadata: new entry to non-existent file → creates file
  - write_game_metadata: new entry to existing file → appends without clobbering
  - write_game_metadata: update existing entry — only non-empty fields overwritten
  - Matching by appid when present, by name when absent
  - Image path resolution (relative → absolute)
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from backend.metadata_gamelist import GameMetadata, read_gamelist, write_game_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_xml(directory: Path, content: str) -> None:
    """Write *content* as gamelist.xml inside *directory*."""
    (directory / "gamelist.xml").write_text(content, encoding="utf-8")


WELL_FORMED_XML = textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <gameList>
      <game>
        <name>Counter-Strike 2</name>
        <appid>730</appid>
        <desc>The most-played FPS on the planet.</desc>
        <developer>Valve</developer>
        <publisher>Valve</publisher>
        <genre>Action, FPS</genre>
        <players>1-64</players>
        <releasedate>20230927T000000</releasedate>
        <rating>0.8</rating>
        <image>./artwork_custom/730.jpg</image>
      </game>
      <game>
        <name>Moonlight App</name>
        <desc>A Moonlight-streamed game without an appid.</desc>
        <developer>NVIDIA</developer>
        <publisher>NVIDIA</publisher>
        <genre>Streaming</genre>
        <players>1</players>
        <releasedate>20200101T000000</releasedate>
        <rating>0.9</rating>
      </game>
    </gameList>
""")


# ---------------------------------------------------------------------------
# read_gamelist
# ---------------------------------------------------------------------------


class TestReadGamelist:
    def test_well_formed_steam_entry(self, tmp_path: Path) -> None:
        """Steam entry (with appid) is keyed by appid and fields are populated."""
        _write_xml(tmp_path, WELL_FORMED_XML)
        result = read_gamelist(tmp_path)

        assert "730" in result
        entry = result["730"]
        assert entry.name == "Counter-Strike 2"
        assert entry.app_id == "730"
        assert entry.description == "The most-played FPS on the planet."
        assert entry.developer == "Valve"
        assert entry.publisher == "Valve"
        assert entry.genre == "Action, FPS"
        assert entry.players == "1-64"
        assert entry.release_date == "20230927T000000"
        assert entry.rating == pytest.approx(0.8)

    def test_well_formed_moonlight_entry(self, tmp_path: Path) -> None:
        """Moonlight entry (no appid) is keyed by name."""
        _write_xml(tmp_path, WELL_FORMED_XML)
        result = read_gamelist(tmp_path)

        assert "Moonlight App" in result
        entry = result["Moonlight App"]
        assert entry.app_id == ""
        assert entry.name == "Moonlight App"
        assert entry.developer == "NVIDIA"

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Missing gamelist.xml returns an empty dict without raising."""
        result = read_gamelist(tmp_path)
        assert result == {}

    def test_malformed_xml_returns_empty_dict_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed XML returns empty dict and logs a warning."""
        _write_xml(tmp_path, "<gameList><game><name>Broken</name></gameList")
        with caplog.at_level(logging.WARNING, logger="backend.metadata_gamelist"):
            result = read_gamelist(tmp_path)

        assert result == {}
        assert any("Failed to parse" in r.message for r in caplog.records)

    def test_image_path_resolved_to_absolute(self, tmp_path: Path) -> None:
        """<image> relative path is resolved to an absolute path string."""
        _write_xml(tmp_path, WELL_FORMED_XML)
        result = read_gamelist(tmp_path)

        entry = result["730"]
        expected = str(tmp_path / "artwork_custom" / "730.jpg")
        assert entry.image_path == expected

    def test_missing_image_tag_gives_empty_string(self, tmp_path: Path) -> None:
        """Entry without <image> tag has image_path == ''."""
        _write_xml(tmp_path, WELL_FORMED_XML)
        result = read_gamelist(tmp_path)

        entry = result["Moonlight App"]
        assert entry.image_path == ""

    def test_all_text_fields_default_to_empty_string(self, tmp_path: Path) -> None:
        """An entry with only <name> has all other string fields as empty string."""
        _write_xml(tmp_path, "<gameList><game><name>Minimal</name></game></gameList>")
        result = read_gamelist(tmp_path)

        entry = result["Minimal"]
        assert entry.description == ""
        assert entry.developer == ""
        assert entry.publisher == ""
        assert entry.genre == ""
        assert entry.players == ""
        assert entry.release_date == ""
        assert entry.image_path == ""
        assert entry.rating == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# write_game_metadata
# ---------------------------------------------------------------------------


class TestWriteGameMetadata:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        """Writing to a non-existent directory/file creates the gamelist.xml."""
        new_dir = tmp_path / "steam"
        metadata = GameMetadata(name="Portal 2", app_id="620", description="Puzzle game")
        write_game_metadata(new_dir, "620", metadata)

        gamelist_file = new_dir / "gamelist.xml"
        assert gamelist_file.exists()

        result = read_gamelist(new_dir)
        assert "620" in result
        assert result["620"].name == "Portal 2"
        assert result["620"].description == "Puzzle game"

    def test_appends_new_entry_to_existing_file(self, tmp_path: Path) -> None:
        """A new entry is appended without touching existing entries."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        new_meta = GameMetadata(name="Half-Life 2", app_id="220", developer="Valve")
        write_game_metadata(tmp_path, "220", new_meta)

        result = read_gamelist(tmp_path)
        assert "730" in result, "Existing CS2 entry must still be present"
        assert "Moonlight App" in result, "Existing Moonlight entry must still be present"
        assert "220" in result
        assert result["220"].name == "Half-Life 2"

    def test_update_only_non_empty_fields(self, tmp_path: Path) -> None:
        """Updating an entry only overwrites fields that are non-empty in the new metadata."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        # Update CS2 with only a new description; developer/publisher should be preserved
        update = GameMetadata(
            app_id="730",
            name="Counter-Strike 2",
            description="Updated description",
        )
        write_game_metadata(tmp_path, "730", update)

        result = read_gamelist(tmp_path)
        entry = result["730"]
        assert entry.description == "Updated description"
        assert entry.developer == "Valve", "User-edited developer must not be clobbered"
        assert entry.publisher == "Valve", "User-edited publisher must not be clobbered"
        assert entry.genre == "Action, FPS", "User-edited genre must not be clobbered"

    def test_match_by_appid_when_present(self, tmp_path: Path) -> None:
        """When metadata.app_id is set, matching uses <appid>, not <name>."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        # Provide a different name but same appid — should update the existing entry
        update = GameMetadata(app_id="730", name="CS2 Renamed", description="New desc")
        write_game_metadata(tmp_path, "730", update)

        result = read_gamelist(tmp_path)
        # Should still be keyed by appid "730"
        assert "730" in result
        assert result["730"].description == "New desc"
        # Only one entry for appid 730 should exist
        assert len([v for v in result.values() if v.app_id == "730"]) == 1

    def test_match_by_name_when_no_appid(self, tmp_path: Path) -> None:
        """When metadata.app_id is empty, matching uses <name>."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        update = GameMetadata(name="Moonlight App", description="Updated Moonlight desc")
        write_game_metadata(tmp_path, "Moonlight App", update)

        result = read_gamelist(tmp_path)
        assert "Moonlight App" in result
        assert result["Moonlight App"].description == "Updated Moonlight desc"
        assert result["Moonlight App"].developer == "NVIDIA", "Developer must be preserved"

    def test_no_duplicate_entries_on_update(self, tmp_path: Path) -> None:
        """Updating an existing entry must not create a duplicate."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        update = GameMetadata(app_id="730", name="Counter-Strike 2", genre="FPS")
        write_game_metadata(tmp_path, "730", update)

        result = read_gamelist(tmp_path)
        # Total entries should still be 2 (CS2 + Moonlight App)
        assert len(result) == 2

    def test_write_image_path(self, tmp_path: Path) -> None:
        """image_path is written to <image> when non-empty."""
        metadata = GameMetadata(
            name="Portal", app_id="400", image_path="./artwork_custom/400.jpg"
        )
        write_game_metadata(tmp_path, "400", metadata)

        result = read_gamelist(tmp_path)
        entry = result["400"]
        expected = str(tmp_path / "artwork_custom" / "400.jpg")
        assert entry.image_path == expected

    def test_rating_zero_not_overwritten(self, tmp_path: Path) -> None:
        """A rating of 0.0 in the update does not overwrite an existing non-zero rating."""
        _write_xml(tmp_path, WELL_FORMED_XML)

        # CS2 has rating 0.8; update with rating=0.0 (default) should not change it
        update = GameMetadata(app_id="730", name="Counter-Strike 2", description="New")
        write_game_metadata(tmp_path, "730", update)

        result = read_gamelist(tmp_path)
        assert result["730"].rating == pytest.approx(0.8)
