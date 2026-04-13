"""Tests for Task 006 — RetroAchievements adapter.

Acceptance criteria from the Task Brief:
- RetroAchievementsSource("", "").is_configured() returns False
- With mocked MD5 hash response, search() returns ScraperResult with
  name, developer, publisher, genre, cover, screenshot.
- Empty md5 → returns None immediately.
- Date parsing covers "January 1989", "1989-01-01", "1989" formats.
- All existing tests still pass.
- No real network calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.retro_scraper import RomHash, ScraperResult
from backend.scrapers.retroachievements import (
    RetroAchievementsSource,
    _parse_ra_date,
)


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_CANNED_GAME_RESPONSE = {
    "ID": 1234,
    "Title": "Mega Man 2",
    "ConsoleID": 7,
    "ConsoleName": "NES",
    "ImageIcon": "/Images/001234.png",
    "ImageTitle": "/Images/title/001234.png",
    "ImageIngame": "/Images/ingame/001234.png",
    "ImageBoxArt": "/Images/boxartcache/001234.png",
    "Developer": "Capcom",
    "Publisher": "Capcom",
    "Genre": "Platform",
    "Released": "January 1989",
    "ForumTopicID": 1,
    "Flags": None,
    "NumAchievements": 40,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    username: str = "testuser", api_key: str = "testapikey"
) -> RetroAchievementsSource:
    return RetroAchievementsSource(username=username, api_key=api_key)


def _mock_response(status_code: int, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no body")
    return resp


def _do_search(
    source: RetroAchievementsSource,
    api_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    md5: str = "aabbccdd",
) -> ScraperResult | None:
    source._session.get = MagicMock(return_value=api_resp)
    with patch("backend.scrapers.retroachievements._download_file", return_value=False):
        return source.search(
            rom_path=rom_path,
            system_folder="nes",
            rom_hash=RomHash(md5=md5, crc32="12345678"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=media_dir,
        )


# ---------------------------------------------------------------------------
# _parse_ra_date
# ---------------------------------------------------------------------------


class TestParseRaDate:
    def test_month_year_format(self) -> None:
        assert _parse_ra_date("January 1989") == "19890101T000000"

    def test_month_year_other_month(self) -> None:
        assert _parse_ra_date("July 2005") == "20050701T000000"

    def test_iso_date_format(self) -> None:
        assert _parse_ra_date("1989-01-01") == "19890101T000000"

    def test_year_only_format(self) -> None:
        result = _parse_ra_date("1989")
        assert result == "19890101T000000"

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_ra_date("") == ""

    def test_unknown_format_returns_empty(self) -> None:
        assert _parse_ra_date("Spring 1989") == ""

    def test_strips_whitespace(self) -> None:
        assert _parse_ra_date("  1989  ") == "19890101T000000"


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_both_empty(self) -> None:
        assert RetroAchievementsSource("", "").is_configured() is False

    def test_false_when_username_empty(self) -> None:
        assert RetroAchievementsSource("", "key").is_configured() is False

    def test_false_when_api_key_empty(self) -> None:
        assert RetroAchievementsSource("user", "").is_configured() is False

    def test_true_when_both_set(self) -> None:
        assert RetroAchievementsSource("user", "key").is_configured() is True


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


class TestName:
    def test_name_is_retroachievements(self) -> None:
        assert _make_source().name == "retroachievements"


# ---------------------------------------------------------------------------
# Empty MD5 → immediate None
# ---------------------------------------------------------------------------


class TestEmptyMd5:
    def test_returns_none_when_md5_empty(self, tmp_path: Path) -> None:
        src = _make_source()
        mock_get = MagicMock()
        src._session.get = mock_get

        result = src.search(
            rom_path=tmp_path / "game.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="", crc32="12345678"),
            canonical_name="Some Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )

        assert result is None
        mock_get.assert_not_called()

    def test_empty_md5_logs_debug(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = _make_source()
        src._session.get = MagicMock()

        with caplog.at_level(logging.DEBUG, logger="scraper"):
            src.search(
                rom_path=tmp_path / "game.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="", crc32="12345678"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert any("no MD5" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Successful search
# ---------------------------------------------------------------------------


class TestSearchSuccess:
    def test_returns_scraperresult_with_metadata(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)

        result = _do_search(src, api_resp, tmp_path / "Mega Man 2 (USA).nes", tmp_path / "media")

        assert result is not None
        assert result.name == "Mega Man 2"
        assert result.developer == "Capcom"
        assert result.publisher == "Capcom"
        assert result.genre == "Platform"
        assert result.release_date == "19890101T000000"

    def test_description_is_empty(self, tmp_path: Path) -> None:
        """RA does not provide description."""
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)

        result = _do_search(src, api_resp, tmp_path / "mm2.nes", tmp_path / "media")

        assert result is not None
        assert result.description == ""

    def test_players_is_empty(self, tmp_path: Path) -> None:
        """RA does not provide players count."""
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)

        result = _do_search(src, api_resp, tmp_path / "mm2.nes", tmp_path / "media")

        assert result is not None
        assert result.players == ""

    def test_rating_is_zero(self, tmp_path: Path) -> None:
        """RA does not provide rating."""
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)

        result = _do_search(src, api_resp, tmp_path / "mm2.nes", tmp_path / "media")

        assert result is not None
        assert result.rating == 0.0

    def test_media_paths_populated_on_successful_download(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        src._session.get = MagicMock(return_value=api_resp)
        with patch(
            "backend.scrapers.retroachievements._download_file",
            side_effect=fake_download,
        ):
            result = src.search(
                rom_path=tmp_path / "Mega Man 2 (USA).nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=media_dir,
            )

        assert result is not None
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).png"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).png"
        assert result.marquee_path is None
        assert result.video_path is None

    def test_media_paths_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)

        result = _do_search(src, api_resp, tmp_path / "mm2.nes", tmp_path / "media")

        assert result is not None
        assert result.thumbnail_path is None
        assert result.screenshot_path is None

    def test_media_url_constructed_correctly(self, tmp_path: Path) -> None:
        """Verify the media base URL is prepended to image paths."""
        src = _make_source()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)
        media_dir = tmp_path / "media"

        download_calls: list[str] = []

        def capture_download(session, url, dest: Path) -> bool:
            download_calls.append(url)
            return False

        src._session.get = MagicMock(return_value=api_resp)
        with patch(
            "backend.scrapers.retroachievements._download_file",
            side_effect=capture_download,
        ):
            src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=media_dir,
            )

        assert any("https://media.retroachievements.org/Images/boxartcache" in u for u in download_calls)
        assert any("https://media.retroachievements.org/Images/ingame" in u for u in download_calls)


# ---------------------------------------------------------------------------
# No game ID in response → None
# ---------------------------------------------------------------------------


class TestNoGameId:
    def test_returns_none_when_id_missing(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(200, {"Title": "Some Game"})  # no ID key

        result = _do_search(src, api_resp, tmp_path / "game.nes", tmp_path / "media")

        assert result is None

    def test_returns_none_when_id_is_zero(self, tmp_path: Path) -> None:
        data = dict(_CANNED_GAME_RESPONSE)
        data["ID"] = 0
        src = _make_source()
        api_resp = _mock_response(200, data)

        result = _do_search(src, api_resp, tmp_path / "game.nes", tmp_path / "media")

        assert result is None

    def test_returns_none_when_id_is_none(self, tmp_path: Path) -> None:
        data = dict(_CANNED_GAME_RESPONSE)
        data["ID"] = None
        src = _make_source()
        api_resp = _mock_response(200, data)

        result = _do_search(src, api_resp, tmp_path / "game.nes", tmp_path / "media")

        assert result is None


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


class TestHttpErrors:
    def test_returns_none_on_non_2xx(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(500)

        result = _do_search(src, api_resp, tmp_path / "game.nes", tmp_path / "media")

        assert result is None

    def test_returns_none_on_404(self, tmp_path: Path) -> None:
        src = _make_source()
        api_resp = _mock_response(404)

        result = _do_search(src, api_resp, tmp_path / "game.nes", tmp_path / "media")

        assert result is None

    def test_returns_none_on_network_error(self, tmp_path: Path) -> None:
        src = _make_source()
        src._session.get = MagicMock(
            side_effect=requests.ConnectionError("no network")
        )

        result = src.search(
            rom_path=tmp_path / "game.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
            canonical_name="Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )

        assert result is None

    def test_returns_none_on_json_error(self, tmp_path: Path) -> None:
        src = _make_source()
        bad_resp = MagicMock(spec=requests.Response)
        bad_resp.status_code = 200
        bad_resp.ok = True
        bad_resp.json.side_effect = ValueError("bad json")
        src._session.get = MagicMock(return_value=bad_resp)

        result = src.search(
            rom_path=tmp_path / "game.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
            canonical_name="Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )

        assert result is None

    def test_returns_none_on_list_response(self, tmp_path: Path) -> None:
        """Unexpected list response should not raise AttributeError."""
        src = _make_source()
        api_resp = _mock_response(200, [])
        src._session.get = MagicMock(return_value=api_resp)

        result = src.search(
            rom_path=tmp_path / "game.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
            canonical_name="Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )

        assert result is None


# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------


class TestCredentialScrubbing:
    def test_api_key_absent_from_logs_on_network_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "super_secret_api_key"
        src = RetroAchievementsSource(username="user", api_key=secret)

        exc_msg = f"ConnectionError: y={secret}&m=abc123"
        src._session.get = MagicMock(
            side_effect=requests.ConnectionError(exc_msg)
        )

        with caplog.at_level(logging.WARNING, logger="scraper"):
            src.search(
                rom_path=tmp_path / "game.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
                canonical_name="Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        combined = " ".join(caplog.messages)
        assert secret not in combined


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_sleep_called_when_requests_too_fast(self, tmp_path: Path) -> None:
        import time
        src = _make_source()
        src._last_request_time = time.monotonic()
        api_resp = _mock_response(200, _CANNED_GAME_RESPONSE)
        src._session.get = MagicMock(return_value=api_resp)

        sleep_calls: list[float] = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("backend.scrapers.retroachievements.time.sleep", side_effect=fake_sleep):
            with patch(
                "backend.scrapers.retroachievements._download_file", return_value=False
            ):
                src.search(
                    rom_path=tmp_path / "mm2.nes",
                    system_folder="nes",
                    rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
                    canonical_name="Mega Man 2",
                    cross_db_ids={},
                    media_dir=tmp_path / "media",
                )

        assert len(sleep_calls) > 0
        assert all(s > 0 for s in sleep_calls)


# ---------------------------------------------------------------------------
# close() and __del__
# ---------------------------------------------------------------------------


class TestCloseAndDel:
    def test_close_is_noop(self) -> None:
        src = _make_source()
        original_session = src._session
        src.close()
        assert src._session is original_session

    def test_del_closes_session(self) -> None:
        src = _make_source()
        mock_session = MagicMock()
        src._session = mock_session
        src.__del__()
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# RetroScraper._build_sources integration
# ---------------------------------------------------------------------------


class TestBuildSourcesIntegration:
    def test_build_sources_includes_ra_when_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_ra_build_sources__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        assert "retroachievements" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        ra_sources = [s for s in sources if s.name == "retroachievements"]
        assert len(ra_sources) == 1

    def test_build_sources_excludes_ra_when_not_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_ra_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        ra_sources = [s for s in sources if s.name == "retroachievements"]
        assert len(ra_sources) == 0
