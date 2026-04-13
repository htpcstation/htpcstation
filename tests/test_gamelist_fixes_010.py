"""Tests for Task 010 — Gamelist fixes: XML indentation, preview image, completion report.

Covers:
  - Fix 1: write_game_entry / write_game_stats produce indented XML
  - Fix 2: _apply_result sets image_path from cover (default) or screenshot
  - Fix 2: _apply_result does not overwrite an existing image_path (miximage)
  - Fix 2: write_game_entry writes <image> tag when game.image_path is set
  - Fix 2: write_game_entry does not overwrite an existing <image> in XML
  - Fix 2: Config.scraper_preview_image round-trip
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.gamelist import write_game_entry, write_game_stats
from backend.models import Game
from backend.retro_scraper import ScraperResult, _apply_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_game(tmp_path: Path, rom_name: str = "game.rom", **kwargs) -> Game:
    defaults = dict(path=tmp_path / rom_name, name="Test Game")
    defaults.update(kwargs)
    return Game(**defaults)


def _make_media(tmp_path: Path, rel: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"stub")
    return p


def _read_root(tmp_path: Path) -> ET.Element:
    return ET.parse(tmp_path / "gamelist.xml").getroot()


def _game_elem(root: ET.Element, rel: str) -> ET.Element | None:
    for e in root.findall("game"):
        pe = e.find("path")
        if pe is not None and (pe.text or "").strip() == rel:
            return e
    return None


def _raw_xml(tmp_path: Path) -> str:
    return (tmp_path / "gamelist.xml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1 — XML indentation
# ---------------------------------------------------------------------------


class TestXmlIndentation:
    def test_write_game_entry_produces_indented_xml(self, tmp_path: Path) -> None:
        """write_game_entry must write indented XML (newlines between elements)."""
        game = _make_game(tmp_path, name="Mega Man 2")
        write_game_entry(tmp_path, game)
        raw = _raw_xml(tmp_path)
        # Indented output contains newlines and leading spaces inside the elements
        assert "\n" in raw
        assert "  " in raw  # 2-space indent

    def test_write_game_stats_produces_indented_xml(self, tmp_path: Path) -> None:
        """write_game_stats must also produce indented XML."""
        # Create a gamelist.xml with one entry first
        game = _make_game(tmp_path, name="Sonic", play_count=0, game_time=0, last_played="", favorite=False)
        write_game_entry(tmp_path, game)
        # Now update stats
        game.play_count = 3
        game.game_time = 120
        write_game_stats(tmp_path, game)
        raw = _raw_xml(tmp_path)
        assert "\n" in raw
        assert "  " in raw


# ---------------------------------------------------------------------------
# Fix 2 — Preview image: _apply_result
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, preview_image: str = "cover"):
    """Return a Config with scraper_preview_image set to *preview_image*."""
    from backend.config import Config

    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        cfg = Config()

    cfg._scraper_preview_image = preview_image
    return cfg


class TestApplyResultPreviewImage:
    def test_defaults_to_cover_thumbnail(self, tmp_path: Path) -> None:
        """With preview_image='cover', image_path is set to thumbnail_path."""
        thumb = _make_media(tmp_path, "media/covers/game.png")
        game = _make_game(tmp_path)
        result = ScraperResult(name="Foo", thumbnail_path=thumb)
        config = _make_config(tmp_path, preview_image="cover")
        _apply_result(game, result, config)
        assert game.image_path == thumb

    def test_screenshot_mode_uses_screenshot(self, tmp_path: Path) -> None:
        """With preview_image='screenshot', image_path is set to screenshot_path."""
        thumb = _make_media(tmp_path, "media/covers/game.png")
        ss = _make_media(tmp_path, "media/screenshots/game.png")
        game = _make_game(tmp_path)
        result = ScraperResult(name="Foo", thumbnail_path=thumb, screenshot_path=ss)
        config = _make_config(tmp_path, preview_image="screenshot")
        _apply_result(game, result, config)
        assert game.image_path == ss

    def test_screenshot_mode_falls_back_to_cover_when_no_screenshot(self, tmp_path: Path) -> None:
        """With preview_image='screenshot' but no screenshot, falls back to thumbnail."""
        thumb = _make_media(tmp_path, "media/covers/game.png")
        game = _make_game(tmp_path)
        result = ScraperResult(name="Foo", thumbnail_path=thumb, screenshot_path=None)
        config = _make_config(tmp_path, preview_image="screenshot")
        _apply_result(game, result, config)
        assert game.image_path == thumb

    def test_does_not_overwrite_existing_image_path(self, tmp_path: Path) -> None:
        """image_path is not changed when the game already has one (miximage)."""
        miximage = _make_media(tmp_path, "media/miximages/game.png")
        thumb = _make_media(tmp_path, "media/covers/game.png")
        game = _make_game(tmp_path, image_path=miximage)
        result = ScraperResult(name="Foo", thumbnail_path=thumb)
        config = _make_config(tmp_path, preview_image="cover")
        _apply_result(game, result, config)
        assert game.image_path == miximage  # unchanged

    def test_no_image_path_set_when_no_thumbnail_or_screenshot(self, tmp_path: Path) -> None:
        """image_path stays None when neither thumbnail nor screenshot is available."""
        game = _make_game(tmp_path)
        result = ScraperResult(name="Foo")
        config = _make_config(tmp_path, preview_image="cover")
        _apply_result(game, result, config)
        assert game.image_path is None


# ---------------------------------------------------------------------------
# Fix 2 — Preview image: write_game_entry writes <image> tag
# ---------------------------------------------------------------------------


class TestWriteGameEntryImageTag:
    def test_writes_image_tag_when_image_path_set(self, tmp_path: Path) -> None:
        """write_game_entry writes <image> when game.image_path is set."""
        img = _make_media(tmp_path, "media/covers/game.png")
        game = _make_game(tmp_path, image_path=img)
        write_game_entry(tmp_path, game)

        root = _read_root(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        img_elem = elem.find("image")
        assert img_elem is not None
        assert img_elem.text == "./media/covers/game.png"

    def test_no_image_tag_when_image_path_is_none(self, tmp_path: Path) -> None:
        """write_game_entry does not write <image> when game.image_path is None."""
        game = _make_game(tmp_path, image_path=None)
        write_game_entry(tmp_path, game)

        root = _read_root(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        assert elem.find("image") is None

    def test_does_not_overwrite_existing_image_tag(self, tmp_path: Path) -> None:
        """write_game_entry does not overwrite an existing <image> element in the XML."""
        # Pre-populate gamelist.xml with a miximage
        miximage_rel = "./media/miximages/game.png"
        (tmp_path / "gamelist.xml").write_text(
            f"<gameList>"
            f"<game><path>./game.rom</path><name>Old</name>"
            f"<image>{miximage_rel}</image>"
            f"</game></gameList>",
            encoding="utf-8",
        )
        # Scraper sets a new thumbnail as image_path
        thumb = _make_media(tmp_path, "media/covers/game.png")
        game = _make_game(tmp_path, name="New Name", image_path=thumb)
        write_game_entry(tmp_path, game)

        root = _read_root(tmp_path)
        elem = _game_elem(root, "./game.rom")
        assert elem is not None
        img_elem = elem.find("image")
        assert img_elem is not None
        # Original miximage path preserved
        assert img_elem.text == miximage_rel


# ---------------------------------------------------------------------------
# Fix 2 — Config.scraper_preview_image round-trip
# ---------------------------------------------------------------------------


class TestConfigScraperPreviewImage:
    def _make_config(self, tmp_path: Path):
        from backend.config import Config

        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            return Config(), cfg_file, cfg_dir

    def test_default_is_cover(self, tmp_path: Path) -> None:
        from backend.config import Config

        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()

        assert cfg.scraper_preview_image == "cover"

    def test_set_and_reload_screenshot(self, tmp_path: Path) -> None:
        from backend.config import Config

        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_scraper_preview_image("screenshot")
            cfg2 = Config()

        assert cfg2.scraper_preview_image == "screenshot"

    def test_invalid_value_ignored(self, tmp_path: Path) -> None:
        from backend.config import Config

        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            cfg = Config()
            cfg.set_scraper_preview_image("miximage")  # invalid

        assert cfg.scraper_preview_image == "cover"  # unchanged default
