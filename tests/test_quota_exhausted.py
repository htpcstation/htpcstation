"""Tests for Task 009 — Quota-exhausted flag for scraper sources.

Acceptance criteria:
- After a source returns 429/430, it is not called again for any subsequent
  game in the run.
- ScreenScraper 430 is logged as "quota exhausted (HTTP 430)".
- _quota_exhausted = True on a source → _scrape_one() skips it with a DEBUG log.
- One test per adapter that emits 429, plus one for ScreenScraper 430.
- All existing tests still pass.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from backend.retro_scraper import (
    AbstractScraperSource,
    RomHash,
    ScraperResult,
    _scrape_one,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _make_rom(tmp_path: Path, name: str = "game.smc") -> Path:
    p = tmp_path / name
    p.write_bytes(b"ROM")
    return p


def _make_config(tmp_path: Path):
    """Return a minimal Config-like mock with snes extension configured."""
    from unittest.mock import MagicMock
    from backend.config import Config
    import json

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


# ---------------------------------------------------------------------------
# _scrape_one: quota-exhausted flag causes source to be skipped
# ---------------------------------------------------------------------------


class TestScrapeOneSkipsQuotaExhausted:
    """_scrape_one() skips any source whose _quota_exhausted flag is True."""

    def _make_fake_source(self, name: str = "fake") -> AbstractScraperSource:
        """Create a minimal concrete AbstractScraperSource."""
        class FakeSource(AbstractScraperSource):
            def __init__(self, src_name: str) -> None:
                self._name = src_name

            @property
            def name(self) -> str:
                return self._name

            def is_configured(self) -> bool:
                return True

            def search(self, *args, **kwargs):
                return None

        src = FakeSource(name)
        src.search = MagicMock(return_value=None)
        return src

    def test_quota_exhausted_source_is_skipped(self, tmp_path: Path) -> None:
        """A source with _quota_exhausted=True is not called by _scrape_one."""
        source = self._make_fake_source("fake_source")
        source._quota_exhausted = True

        rom = _make_rom(tmp_path)

        with patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom,
                folder_name="snes",
                system_path=tmp_path,
                games=[],
                config=MagicMock(),
                sources=[source],
                overwrite=False,
            )

        source.search.assert_not_called()

    def test_quota_exhausted_debug_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a quota-exhausted source is skipped, a DEBUG log is emitted."""
        source = self._make_fake_source("slow_source")
        source._quota_exhausted = True

        rom = _make_rom(tmp_path)

        with caplog.at_level(logging.DEBUG, logger="scraper"), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom,
                folder_name="snes",
                system_path=tmp_path,
                games=[],
                config=MagicMock(),
                sources=[source],
                overwrite=False,
            )

        assert any(
            "quota exhausted" in r.message and "slow_source" in r.message
            for r in caplog.records
            if r.levelno == logging.DEBUG
        )

    def test_not_exhausted_source_is_called(self, tmp_path: Path) -> None:
        """A source with _quota_exhausted=False (default) is still called normally."""
        source = self._make_fake_source("active_source")

        rom = _make_rom(tmp_path)

        with patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom,
                folder_name="snes",
                system_path=tmp_path,
                games=[],
                config=MagicMock(),
                sources=[source],
                overwrite=False,
            )

        source.search.assert_called_once()


# ---------------------------------------------------------------------------
# ScreenScraper: 429 and 430 set _quota_exhausted
# ---------------------------------------------------------------------------


class TestScreenScraperQuota:
    def _make_source(self):
        from backend.scrapers.screenscraper import ScreenScraperSource
        return ScreenScraperSource(devid="d", devpassword="p")

    def _call_search(self, source, tmp_path: Path, status_code: int) -> None:
        resp = _mock_response(status_code)
        rom = _make_rom(tmp_path)
        with patch.object(source._session, "get", return_value=resp):
            result = source.search(
                rom_path=rom,
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        return result

    def test_429_sets_quota_exhausted(self, tmp_path: Path) -> None:
        source = self._make_source()
        result = self._call_search(source, tmp_path, 429)
        assert result is None
        assert source._quota_exhausted is True

    def test_430_sets_quota_exhausted(self, tmp_path: Path) -> None:
        """HTTP 430 (ScreenScraper daily quota) sets _quota_exhausted and returns None."""
        source = self._make_source()
        result = self._call_search(source, tmp_path, 430)
        assert result is None
        assert source._quota_exhausted is True

    def test_430_logged_as_quota_exhausted(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """HTTP 430 is logged as 'quota exhausted (HTTP 430)', not as unexpected status."""
        source = self._make_source()
        with caplog.at_level(logging.WARNING, logger="scraper"):
            self._call_search(source, tmp_path, 430)

        msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("quota exhausted" in m and "430" in m for m in msgs)
        assert not any("unexpected status" in m for m in msgs)

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "get", side_effect=fake_get), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        # Session.get should have been called once only (for game 1)
        assert call_count == 1


# ---------------------------------------------------------------------------
# TheGamesDB: 429 sets _quota_exhausted
# ---------------------------------------------------------------------------


class TestTheGamesDBQuota:
    def _make_source(self):
        from backend.scrapers.thegamesdb import TheGamesDBSource
        return TheGamesDBSource(api_key="testkey")

    def test_429_sets_quota_exhausted(self, tmp_path: Path) -> None:
        source = self._make_source()
        resp = _mock_response(429)
        with patch.object(source._session, "get", return_value=resp):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "get", side_effect=fake_get), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        assert call_count == 1


# ---------------------------------------------------------------------------
# MobyGames: 429 sets _quota_exhausted (both internal methods)
# ---------------------------------------------------------------------------


class TestMobyGamesQuota:
    def _make_source(self):
        from backend.scrapers.mobygames import MobyGamesSource
        return MobyGamesSource(api_key="testkey")

    def test_429_on_search_sets_quota_exhausted(self, tmp_path: Path) -> None:
        """429 on the search-game-id request sets _quota_exhausted."""
        source = self._make_source()
        resp = _mock_response(429)
        with patch.object(source._session, "get", return_value=resp):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_429_on_detail_sets_quota_exhausted(self, tmp_path: Path) -> None:
        """429 on the fetch-detail request also sets _quota_exhausted."""
        source = self._make_source()

        resp_search = _mock_response(200, {"games": [{"id": 42}]})
        resp_detail_429 = _mock_response(429)

        responses = iter([resp_search, resp_detail_429])
        with patch.object(source._session, "get", side_effect=lambda *a, **kw: next(responses)):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "get", side_effect=fake_get), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        assert call_count == 1


# ---------------------------------------------------------------------------
# IGDB: 429 sets _quota_exhausted
# ---------------------------------------------------------------------------


class TestIGDBQuota:
    def _make_source(self):
        from backend.scrapers.igdb import IGDBSource
        src = IGDBSource(client_id="cid", client_secret="csec")
        # Pre-fill token so we bypass auth
        src._access_token = "fake-token"
        src._session.headers.update({
            "Client-ID": "cid",
            "Authorization": "Bearer fake-token",
        })
        return src

    def test_429_sets_quota_exhausted(self, tmp_path: Path) -> None:
        source = self._make_source()
        resp = _mock_response(429)
        with patch.object(source._session, "post", return_value=resp):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "post", side_effect=fake_post), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        assert call_count == 1


# ---------------------------------------------------------------------------
# EmuMovies: 429 sets _quota_exhausted
# ---------------------------------------------------------------------------


class TestEmuMoviesQuota:
    def _make_source(self):
        from backend.scrapers.emumovies import EmuMoviesSource
        src = EmuMoviesSource(username="user", password="pass")
        # Pre-fill token to bypass login
        src._token = "fake-token"
        src._session.headers.update({"Authorization": "Bearer fake-token"})
        return src

    def test_429_sets_quota_exhausted(self, tmp_path: Path) -> None:
        source = self._make_source()
        resp = _mock_response(429)
        with patch.object(source._session, "get", return_value=resp):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "get", side_effect=fake_get), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("", "")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        assert call_count == 1


# ---------------------------------------------------------------------------
# RetroAchievements: 429 sets _quota_exhausted
# ---------------------------------------------------------------------------


class TestRetroAchievementsQuota:
    def _make_source(self):
        from backend.scrapers.retroachievements import RetroAchievementsSource
        return RetroAchievementsSource(username="user", api_key="key123")

    def test_429_sets_quota_exhausted(self, tmp_path: Path) -> None:
        source = self._make_source()
        resp = _mock_response(429)
        with patch.object(source._session, "get", return_value=resp):
            result = source.search(
                rom_path=_make_rom(tmp_path),
                system_folder="snes",
                rom_hash=RomHash("abc123", "00000001"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None
        assert source._quota_exhausted is True

    def test_quota_exhausted_skips_second_game(self, tmp_path: Path) -> None:
        """After 429 on game 1, search() is not called for game 2."""
        source = self._make_source()

        rom1 = _make_rom(tmp_path, "game1.smc")
        rom2 = _make_rom(tmp_path, "game2.smc")

        resp_429 = _mock_response(429)
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp_429

        with patch.object(source._session, "get", side_effect=fake_get), \
             patch("backend.retro_scraper.compute_rom_hash", return_value=RomHash("abc123", "00000001")), \
             patch("backend.retro_scraper._hasheous_lookup", return_value=ScraperResult()):
            _scrape_one(
                rom_path=rom1, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )
            assert source._quota_exhausted is True

            _scrape_one(
                rom_path=rom2, folder_name="snes", system_path=tmp_path,
                games=[], config=MagicMock(), sources=[source], overwrite=False,
            )

        assert call_count == 1
