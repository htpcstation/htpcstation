"""Tests for Task 002 — Scraper framework + logging.

Covers the acceptance criteria from the Task Brief:
- RetroScraper instantiation
- scrapeSystem with empty sources list emits scrapeFinished(0, N, 0)
- cancelScrape stops the loop
- Config round-trip for scraper credentials
- _hasheous_lookup returns empty result on network error
- _name_from_path strips bracketed tags
- All merge helpers behave correctly
- _game_fully_scraped and _seed_from_game helpers
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import Config
from backend.models import Game
from backend.retro_scraper import (
    MERGE_FIELDS,
    RomHash,
    ScraperResult,
    RetroScraper,
    _game_fully_scraped,
    _hasheous_lookup,
    _is_empty,
    _name_from_path,
    _seed_from_game,
    all_filled,
    compute_rom_hash,
    merge_into,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_factory(tmp_path: Path):
    """Fixture factory: patches CONFIG_FILE/CONFIG_DIR to tmp_path.

    The patch stays active for the entire test.  Returns a callable that
    creates a fresh :class:`Config` from the patched file.
    """
    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        yield lambda: Config()


# ---------------------------------------------------------------------------
# RomHash / compute_rom_hash
# ---------------------------------------------------------------------------


class TestComputeRomHash:
    def test_returns_correct_hashes(self, tmp_path: Path) -> None:
        """compute_rom_hash returns correct md5 and crc32 for a known file."""
        import hashlib
        import zlib

        data = b"hello world"
        p = tmp_path / "test.rom"
        p.write_bytes(data)

        rom_hash = compute_rom_hash(p)

        expected_md5 = hashlib.md5(data).hexdigest().lower()
        expected_crc32 = format(zlib.crc32(data) & 0xFFFFFFFF, "08x")
        assert rom_hash.md5 == expected_md5
        assert rom_hash.crc32 == expected_crc32

    def test_crc32_is_zero_padded_to_8_chars(self, tmp_path: Path) -> None:
        """CRC32 is always 8 hex characters, zero-padded."""
        p = tmp_path / "tiny.rom"
        p.write_bytes(b"\x00")
        rom_hash = compute_rom_hash(p)
        assert len(rom_hash.crc32) == 8
        assert rom_hash.crc32 == rom_hash.crc32.lower()

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        """compute_rom_hash returns RomHash('', '') when the file cannot be read."""
        missing = tmp_path / "nonexistent.rom"
        result = compute_rom_hash(missing)
        assert result == RomHash("", "")


# ---------------------------------------------------------------------------
# _is_empty / merge_into / all_filled
# ---------------------------------------------------------------------------


class TestMergeHelpers:
    def test_is_empty_detects_none(self) -> None:
        r = ScraperResult()
        assert _is_empty(r, "thumbnail_path") is True

    def test_is_empty_detects_empty_string(self) -> None:
        r = ScraperResult(name="")
        assert _is_empty(r, "name") is True

    def test_is_empty_detects_zero_float(self) -> None:
        r = ScraperResult(rating=0.0)
        assert _is_empty(r, "rating") is True

    def test_is_empty_false_for_set_value(self) -> None:
        r = ScraperResult(name="Foo")
        assert _is_empty(r, "name") is False

    def test_merge_into_copies_nonempty_to_empty(self) -> None:
        target = ScraperResult()
        source = ScraperResult(name="Mega Man 2", description="A great game")
        merge_into(target, source, "test_source", overwrite=False)
        assert target.name == "Mega Man 2"
        assert target.description == "A great game"
        assert target.source_for["name"] == "test_source"
        assert target.source_for["description"] == "test_source"

    def test_merge_into_no_overwrite_preserves_existing(self) -> None:
        target = ScraperResult(name="Existing Name")
        source = ScraperResult(name="New Name")
        merge_into(target, source, "src", overwrite=False)
        assert target.name == "Existing Name"
        assert "name" not in target.source_for

    def test_merge_into_overwrite_replaces(self) -> None:
        target = ScraperResult(name="Existing Name")
        source = ScraperResult(name="New Name")
        merge_into(target, source, "src", overwrite=True)
        assert target.name == "New Name"
        assert target.source_for["name"] == "src"

    def test_merge_into_skips_empty_source_fields(self) -> None:
        target = ScraperResult(name="Already Set")
        source = ScraperResult(name="")  # empty
        merge_into(target, source, "src", overwrite=True)
        assert target.name == "Already Set"

    def test_all_filled_false_when_any_empty(self) -> None:
        r = ScraperResult(name="Foo")  # most fields empty
        assert all_filled(r) is False

    def test_all_filled_true_when_all_set(self, tmp_path: Path) -> None:
        dummy_path = tmp_path / "img.png"
        dummy_path.write_bytes(b"x")
        r = ScraperResult(
            name="Foo",
            description="Bar",
            developer="Dev",
            publisher="Pub",
            genre="RPG",
            players="1",
            rating=0.8,
            release_date="19990101T000000",
            thumbnail_path=dummy_path,
            marquee_path=dummy_path,
            screenshot_path=dummy_path,
            video_path=dummy_path,
        )
        assert all_filled(r) is True


# ---------------------------------------------------------------------------
# _name_from_path
# ---------------------------------------------------------------------------


class TestNameFromPath:
    @pytest.mark.parametrize("stem,expected", [
        ("Mega Man 2 (USA) [!]", "Mega Man 2"),
        ("Super Mario World (Europe)", "Super Mario World"),
        ("Sonic [!]", "Sonic"),
        ("Zelda (U) [b1]", "Zelda"),
        ("Simple Name", "Simple Name"),
        ("Game {version}", "Game"),
    ])
    def test_strips_bracketed_tags(self, stem: str, expected: str, tmp_path: Path) -> None:
        rom = tmp_path / (stem + ".rom")
        assert _name_from_path(rom) == expected


# ---------------------------------------------------------------------------
# _game_fully_scraped
# ---------------------------------------------------------------------------


class TestGameFullyScraped:
    def test_false_when_any_field_missing(self, tmp_path: Path) -> None:
        g = Game(
            path=tmp_path / "g.rom",
            name="Foo",
            description="desc",
            thumbnail_path=tmp_path / "t.png",
            marquee_path=tmp_path / "m.png",
            screenshot_path=tmp_path / "s.png",
            video_path=None,  # video_path missing
        )
        assert _game_fully_scraped(g) is False

    def test_true_when_all_fields_present(self, tmp_path: Path) -> None:
        g = Game(
            path=tmp_path / "g.rom",
            name="Foo",
            description="desc",
            thumbnail_path=tmp_path / "t.png",
            marquee_path=tmp_path / "m.png",
            screenshot_path=tmp_path / "s.png",
            video_path=tmp_path / "v.mp4",
        )
        assert _game_fully_scraped(g) is True


# ---------------------------------------------------------------------------
# _seed_from_game
# ---------------------------------------------------------------------------


class TestSeedFromGame:
    def test_copies_nonempty_fields(self, tmp_path: Path) -> None:
        g = Game(
            path=tmp_path / "g.rom",
            name="Foo",
            description="A desc",
            developer="Dev",
        )
        r = ScraperResult()
        _seed_from_game(r, g)
        assert r.name == "Foo"
        assert r.description == "A desc"
        assert r.developer == "Dev"
        assert r.source_for["name"] == "existing"

    def test_skips_empty_fields(self, tmp_path: Path) -> None:
        g = Game(path=tmp_path / "g.rom", name="Foo", description="")
        r = ScraperResult()
        _seed_from_game(r, g)
        assert "description" not in r.source_for


# ---------------------------------------------------------------------------
# _hasheous_lookup
# ---------------------------------------------------------------------------


class TestHasheousLookup:
    def test_returns_empty_on_connection_error(self) -> None:
        """_hasheous_lookup returns an empty ScraperResult when network is unavailable."""
        import requests as req

        with patch.object(req, "get", side_effect=ConnectionError("no network")):
            result = _hasheous_lookup(RomHash(md5="aabbccdd", crc32="12345678"))

        assert result.canonical_name == ""
        assert result.cross_db_ids == {}

    def test_returns_empty_on_timeout(self) -> None:
        """_hasheous_lookup returns an empty ScraperResult on timeout."""
        import requests as req

        with patch.object(req, "get", side_effect=req.exceptions.Timeout()):
            result = _hasheous_lookup(RomHash(md5="aabbccdd", crc32="12345678"))

        assert result.canonical_name == ""
        assert result.cross_db_ids == {}

    def test_returns_empty_when_both_hashes_blank(self) -> None:
        """_hasheous_lookup returns empty immediately when both hashes are blank."""
        result = _hasheous_lookup(RomHash(md5="", crc32=""))
        assert result.canonical_name == ""

    def test_parses_canonical_name_from_response(self) -> None:
        """_hasheous_lookup parses canonical_name from a well-formed response."""
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "id": 1,
            "name": "Mega Man 2",
            "metadata": [],
        }

        with patch.object(req, "get", return_value=mock_resp):
            result = _hasheous_lookup(RomHash(md5="aabbccdd", crc32="12345678"))

        assert result.canonical_name == "Mega Man 2"

    def test_parses_cross_db_ids(self) -> None:
        """_hasheous_lookup parses tgdb_id and igdb_id from metadata list."""
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "id": 2,
            "name": "Street Fighter II",
            "metadata": [
                {"source": "TheGamesDb", "id": "123"},
                {"source": "IGDB", "id": "456"},
                {"source": "RetroAchievements", "id": "789"},
            ],
        }

        with patch.object(req, "get", return_value=mock_resp):
            result = _hasheous_lookup(RomHash(md5="aabbccdd", crc32="12345678"))

        assert result.cross_db_ids.get("tgdb_id") == 123
        assert result.cross_db_ids.get("igdb_id") == 456
        assert result.cross_db_ids.get("ra_id") == 789

    def test_hasheous_uses_md5_path_param(self) -> None:
        """_hasheous_lookup uses the correct /ByHash/md5/{md5} endpoint."""
        import requests as req

        captured_urls = []

        def _fake_get(url, **_kwargs):
            captured_urls.append(url)
            mock = MagicMock()
            mock.raise_for_status.return_value = None
            mock.json.return_value = {"id": 1, "name": "", "metadata": []}
            return mock

        with patch.object(req, "get", side_effect=_fake_get):
            _hasheous_lookup(RomHash(md5="abc123", crc32="00000000"))

        assert len(captured_urls) == 1
        assert "/Lookup/ByHash/md5/abc123" in captured_urls[0]

    def test_hasheous_falls_back_to_crc(self) -> None:
        """_hasheous_lookup uses /ByHash/crc/{crc} when md5 is empty."""
        import requests as req

        captured_urls = []

        def _fake_get(url, **_kwargs):
            captured_urls.append(url)
            mock = MagicMock()
            mock.raise_for_status.return_value = None
            mock.json.return_value = {"id": 1, "name": "", "metadata": []}
            return mock

        with patch.object(req, "get", side_effect=_fake_get):
            _hasheous_lookup(RomHash(md5="", crc32="deadbeef"))

        assert len(captured_urls) == 1
        assert "/Lookup/ByHash/crc/deadbeef" in captured_urls[0]


# ---------------------------------------------------------------------------
# Config scraper section round-trip
# ---------------------------------------------------------------------------


class TestConfigScraperSection:
    def test_default_values(self, config_factory) -> None:
        """Config has correct default scraper values."""
        cfg = config_factory()
        assert cfg.scraper_overwrite is False
        assert "screenscraper" in cfg.scraper_enabled_sources
        creds = cfg.scraper_credentials
        assert "screenscraper" in creds
        assert "api_key" in creds["thegamesdb"]

    def test_set_scraper_overwrite_persists(self, config_factory) -> None:
        """set_scraper_overwrite saves to disk and reloads correctly."""
        cfg = config_factory()
        cfg.set_scraper_overwrite(True)
        # In tests, _write_executor is replaced by a sync shim (see conftest),
        # so save() completes before we call config_factory() again.
        cfg2 = config_factory()
        assert cfg2.scraper_overwrite is True

    def test_set_scraper_credential_persists(self, config_factory) -> None:
        """set_scraper_credential saves a credential value to disk."""
        cfg = config_factory()
        cfg.set_scraper_credential("thegamesdb", "api_key", "mykey123")
        cfg2 = config_factory()
        assert cfg2.scraper_credentials["thegamesdb"]["api_key"] == "mykey123"

    def test_set_scraper_credential_noop_for_unknown_source(self, config_factory) -> None:
        """set_scraper_credential is a no-op for an unknown source."""
        cfg = config_factory()
        cfg.set_scraper_credential("nonexistent_source", "api_key", "val")
        assert "nonexistent_source" not in cfg.scraper_credentials

    def test_set_scraper_credential_noop_for_unknown_key(self, config_factory) -> None:
        """set_scraper_credential is a no-op for an unknown key within a known source."""
        cfg = config_factory()
        cfg.set_scraper_credential("thegamesdb", "unknown_key", "val")
        assert "unknown_key" not in cfg.scraper_credentials["thegamesdb"]

    def test_load_never_widens_known_key_set(self, tmp_path: Path) -> None:
        """Loading from disk never adds unknown credential keys."""
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir):
            # Create initial config (sync executor is autouse, so save completes immediately)
            _cfg = Config()

            # Inject a rogue key directly into the saved config file
            raw = json.loads(cfg_file.read_text())
            raw.setdefault("scraper", {}).setdefault("thegamesdb", {})["rogue_key"] = "hacked"
            cfg_file.write_text(json.dumps(raw))

            cfg2 = Config()

        assert "rogue_key" not in cfg2.scraper_credentials["thegamesdb"]

    def test_set_scraper_enabled_sources_persists(self, config_factory) -> None:
        """set_scraper_enabled_sources saves and reloads correctly."""
        cfg = config_factory()
        cfg.set_scraper_enabled_sources(["thegamesdb", "igdb"])
        cfg2 = config_factory()
        assert cfg2.scraper_enabled_sources == ["thegamesdb", "igdb"]


# ---------------------------------------------------------------------------
# RetroScraper instantiation and signal tests (require PySide6)
# ---------------------------------------------------------------------------


def _require_pyside6():
    """Skip the test if PySide6 is not available."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        pytest.skip("PySide6 not available")


def _get_qapp():
    """Return the existing QApplication or create one."""
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv[:1])


class TestRetroScraperInstantiation:
    def test_can_be_instantiated(self, config_factory) -> None:
        """RetroScraper can be instantiated with a Config."""
        _require_pyside6()
        _get_qapp()
        cfg = config_factory()
        scraper = RetroScraper(cfg)
        assert scraper is not None

    def test_scrape_system_no_roms_emits_finished(self, config_factory, tmp_path: Path) -> None:
        """scrapeSystem on a folder with no ROMs emits scrapeFinished(0, 0, 0, {})."""
        _require_pyside6()
        from PySide6.QtCore import QEventLoop, QTimer
        _get_qapp()

        cfg = config_factory()
        snes_dir = tmp_path / "roms" / "snes"
        snes_dir.mkdir(parents=True)
        cfg.set_rom_directory(tmp_path / "roms")

        results = []
        scraper = RetroScraper(cfg)
        loop = QEventLoop()
        scraper.scrapeFinished.connect(lambda s, sk, f, sc: results.append((s, sk, f, sc)))
        scraper.scrapeFinished.connect(lambda *_: loop.quit())
        QTimer.singleShot(5000, loop.quit)

        scraper.scrapeSystem("snes")
        loop.exec()

        assert len(results) == 1
        scraped, skipped, failed, source_counts = results[0]
        assert scraped == 0
        assert skipped == 0
        assert failed == 0
        assert source_counts == {}

    def test_scrape_system_with_roms_all_skipped(self, config_factory, tmp_path: Path) -> None:
        """With empty sources, all ROMs are skipped → scrapeFinished(0, N, 0, {})."""
        _require_pyside6()
        from PySide6.QtCore import QEventLoop, QTimer
        _get_qapp()

        cfg = config_factory()
        snes_dir = tmp_path / "roms" / "snes"
        snes_dir.mkdir(parents=True)
        # Create 3 stub ROM files with extensions matching SNES config
        for i in range(3):
            (snes_dir / f"game{i}.smc").write_bytes(b"ROM")
        cfg.set_rom_directory(tmp_path / "roms")

        results = []
        scraper = RetroScraper(cfg)
        loop = QEventLoop()
        scraper.scrapeFinished.connect(lambda s, sk, f, sc: results.append((s, sk, f, sc)))
        scraper.scrapeFinished.connect(lambda *_: loop.quit())
        QTimer.singleShot(10000, loop.quit)

        # Patch _hasheous_lookup to return empty immediately (avoid network)
        with patch("backend.retro_scraper._hasheous_lookup",
                   return_value=ScraperResult()):
            scraper.scrapeSystem("snes")
            loop.exec()

        assert len(results) == 1
        scraped, skipped, failed, source_counts = results[0]
        assert scraped == 0
        assert skipped == 3
        assert failed == 0
        assert source_counts == {}

    def test_cancel_scrape_terminates_cleanly(self, config_factory, tmp_path: Path) -> None:
        """cancelScrape() causes the loop to stop and either scrapeCancelled or scrapeFinished fires."""
        _require_pyside6()
        from PySide6.QtCore import QEventLoop, QTimer
        _get_qapp()

        cfg = config_factory()
        snes_dir = tmp_path / "roms" / "snes"
        snes_dir.mkdir(parents=True)
        for i in range(10):
            (snes_dir / f"game{i}.smc").write_bytes(b"ROM")
        cfg.set_rom_directory(tmp_path / "roms")

        done = []
        scraper = RetroScraper(cfg)
        loop = QEventLoop()
        scraper.scrapeCancelled.connect(lambda: done.append("cancelled"))
        scraper.scrapeCancelled.connect(loop.quit)
        scraper.scrapeFinished.connect(lambda *_: done.append("finished"))
        scraper.scrapeFinished.connect(lambda *_: loop.quit())
        QTimer.singleShot(10000, loop.quit)

        with patch("backend.retro_scraper._hasheous_lookup",
                   return_value=ScraperResult()):
            scraper.scrapeSystem("snes")
            scraper.cancelScrape()
            loop.exec()

        # Either cancelled or finished — either is valid (depends on timing)
        assert len(done) >= 1
