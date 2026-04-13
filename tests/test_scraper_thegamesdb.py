"""Tests for Task 005 — TheGamesDB adapter.

Acceptance criteria from the Task Brief:
- TheGamesDBSource("").is_configured() returns False
- With mocked responses, returns ScraperResult with correct metadata and media paths
- Date conversion: "1989-01-01" → "19890101T000000"
- HTTP 429 → returns None
- HTTP 404 → returns None
- Network error → returns None
- Platform ID miss → search() returns None with DEBUG log
- Rate limit enforced (monkeypatched time.sleep)
- API key must not appear in log output
- All existing tests still pass
- No real network calls
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from backend.retro_scraper import RomHash, ScraperResult
from backend.scrapers.thegamesdb import TheGamesDBSource, TGDB_PLATFORM_IDS
from backend.scrapers._utils import iso_date_to_gamelist


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CANNED_GAMES_RESPONSE = {
    "data": {
        "games": [
            {
                "id": 1234,
                "game_title": "Mega Man 2",
                "overview": "A great platformer",
                "players": 1,
                "release_date": "1989-01-01",
                "developers": [21],
                "publishers": [22],
                "genres": [15],
                "rating": "E",
                "platform": 7,
            }
        ]
    },
    "include": {
        "publishers": {"data": {"22": {"name": "Capcom"}}},
        "developers": {"data": {"21": {"name": "Capcom"}}},
        "genres": {"data": {"15": {"genre": "Platform"}}},
    },
}

_CANNED_IMAGES_RESPONSE = {
    "data": {
        "images": {
            "1234": [
                {"type": "boxart", "side": "front", "filename": "boxart/front/1234-1.jpg"},
                {"type": "clearlogo", "filename": "clearlogo/1234-1.png"},
                {"type": "screenshot", "filename": "screenshots/1234-1.jpg"},
            ]
        }
    },
    "base_url": {
        "original": "https://cdn.thegamesdb.net/images/original/",
    },
}


def _make_source(api_key: str = "testkey") -> TheGamesDBSource:
    return TheGamesDBSource(api_key=api_key)


def _mock_response(status_code: int, json_data: object = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no body")
    return resp


def _search_with_mocks(
    source: TheGamesDBSource,
    search_resp: MagicMock,
    images_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    system_folder: str = "nes",
) -> ScraperResult | None:
    """Run source.search() with both HTTP calls mocked."""
    responses = [search_resp, images_resp]
    with patch.object(source._session, "get", side_effect=responses):
        return source.search(
            rom_path=rom_path,
            system_folder=system_folder,
            rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=media_dir,
        )


# ---------------------------------------------------------------------------
# iso_date_to_gamelist utility
# ---------------------------------------------------------------------------


class TestIsoDateToGamelist:
    def test_converts_valid_date(self) -> None:
        assert iso_date_to_gamelist("1989-01-01") == "19890101T000000"

    def test_converts_padded_parts(self) -> None:
        assert iso_date_to_gamelist("2005-07-04") == "20050704T000000"

    def test_returns_empty_on_bad_format(self) -> None:
        # Only 2 parts — not a valid YYYY-MM-DD
        assert iso_date_to_gamelist("not-a") == ""

    def test_returns_empty_on_empty_string(self) -> None:
        assert iso_date_to_gamelist("") == ""

    def test_returns_empty_on_missing_parts(self) -> None:
        assert iso_date_to_gamelist("1989-01") == ""


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_empty(self) -> None:
        assert TheGamesDBSource("").is_configured() is False

    def test_true_when_key_set(self) -> None:
        assert TheGamesDBSource("abc123").is_configured() is True


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


class TestName:
    def test_name_is_thegamesdb(self) -> None:
        assert _make_source().name == "thegamesdb"


# ---------------------------------------------------------------------------
# Platform mapping
# ---------------------------------------------------------------------------


class TestPlatformMapping:
    def test_known_platforms_mapped(self) -> None:
        for folder in ("nes", "snes", "gb", "gba", "gbc", "n64", "megadrive", "psx"):
            assert folder in TGDB_PLATFORM_IDS, f"{folder!r} missing from TGDB_PLATFORM_IDS"

    def test_megadrive_has_two_ids(self) -> None:
        # Sega Genesis and Mega Drive are separate TGDB platform IDs
        assert len(TGDB_PLATFORM_IDS["megadrive"]) >= 2

    def test_returns_none_for_unknown_platform(self, tmp_path: Path) -> None:
        src = _make_source()
        result = src.search(
            rom_path=tmp_path / "game.rom",
            system_folder="unknownplatform_xyz",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None

    def test_unknown_platform_logs_debug(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = _make_source()
        with caplog.at_level(logging.DEBUG, logger="scraper"):
            src.search(
                rom_path=tmp_path / "game.rom",
                system_folder="unknownplatform_xyz",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert any("unknown platform" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


class TestSearchHttpErrors:
    def test_returns_none_on_429(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(429)
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_returns_none_on_404(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(404)
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_returns_none_on_other_non_2xx(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(500)
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_returns_none_on_network_error(self, tmp_path: Path) -> None:
        src = _make_source()
        with patch.object(
            src._session, "get", side_effect=requests.ConnectionError("no net")
        ):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_returns_none_on_empty_games_list(self, tmp_path: Path) -> None:
        src = _make_source()
        body = {"data": {"games": []}, "include": {}}
        resp = _mock_response(200, body)
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_returns_none_on_json_error(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.ok = True
        resp.json.side_effect = ValueError("bad json")
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None


# ---------------------------------------------------------------------------
# API key scrubbing
# ---------------------------------------------------------------------------


class TestApiKeyScrubbing:
    def test_api_key_absent_from_logs_on_network_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret_key = "super_secret_api_key"
        src = TheGamesDBSource(api_key=secret_key)

        exc_msg = f"HTTPSConnectionPool: failed apikey={secret_key}&name=test"
        with caplog.at_level(logging.WARNING, logger="scraper"):
            with patch.object(
                src._session, "get", side_effect=requests.ConnectionError(exc_msg)
            ):
                src.search(
                    rom_path=tmp_path / "mm2.nes",
                    system_folder="nes",
                    rom_hash=RomHash(md5="aa", crc32="bb"),
                    canonical_name="Mega Man 2",
                    cross_db_ids={},
                    media_dir=tmp_path / "media",
                )

        combined = " ".join(caplog.messages)
        assert secret_key not in combined


# ---------------------------------------------------------------------------
# Successful metadata parsing
# ---------------------------------------------------------------------------


class TestSearchSuccess:
    def test_returns_scraperresult_with_metadata(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)

        with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, images_resp,
                tmp_path / "Mega Man 2 (USA).nes", tmp_path / "media",
            )

        assert result is not None
        assert result.name == "Mega Man 2"
        assert result.description == "A great platformer"
        assert result.developer == "Capcom"
        assert result.publisher == "Capcom"
        assert result.genre == "Platform"
        assert result.players == "1"
        assert result.release_date == "19890101T000000"
        # Rating left empty (ESRB string not convertible)
        assert result.rating == 0.0

    def test_multiple_games_uses_first(self, tmp_path: Path) -> None:
        body = dict(_CANNED_GAMES_RESPONSE)
        body["data"] = {
            "games": [
                {
                    "id": 1234,
                    "game_title": "First Game",
                    "overview": "",
                    "players": None,
                    "release_date": None,
                    "developers": [],
                    "publishers": [],
                    "genres": [],
                    "rating": None,
                    "platform": 7,
                },
                {
                    "id": 5678,
                    "game_title": "Second Game",
                    "overview": "",
                    "players": None,
                    "release_date": None,
                    "developers": [],
                    "publishers": [],
                    "genres": [],
                    "rating": None,
                    "platform": 7,
                },
            ]
        }
        src = _make_source()
        search_resp = _mock_response(200, body)
        images_resp = _mock_response(200, {"data": {"images": {}}, "base_url": {"original": ""}})

        with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, images_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.name == "First Game"

    def test_media_paths_populated_on_successful_download(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        with patch("backend.scrapers.thegamesdb._download_file", side_effect=fake_download):
            result = _search_with_mocks(
                src, search_resp, images_resp,
                tmp_path / "Mega Man 2 (USA).nes", media_dir,
            )

        assert result is not None
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).jpg"
        assert result.marquee_path == media_dir / "wheels" / "Mega Man 2 (USA).png"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).jpg"
        assert result.video_path is None  # TGDB has no video

    def test_media_paths_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)

        with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, images_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.thumbnail_path is None
        assert result.marquee_path is None
        assert result.screenshot_path is None


# ---------------------------------------------------------------------------
# Lookup by TGDB ID (cross_db_ids)
# ---------------------------------------------------------------------------


class TestSearchByTgdbId:
    def test_uses_by_game_id_endpoint_when_tgdb_id_present(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)

        calls_made = []

        def mock_get(url, **kwargs):
            calls_made.append(url)
            if "ByGameID" in url:
                return search_resp
            return images_resp

        with patch.object(src._session, "get", side_effect=mock_get):
            with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
                result = src.search(
                    rom_path=tmp_path / "mm2.nes",
                    system_folder="nes",
                    rom_hash=RomHash(md5="aa", crc32="bb"),
                    canonical_name="Mega Man 2",
                    cross_db_ids={"tgdb_id": 1234},
                    media_dir=tmp_path / "media",
                )

        assert result is not None
        assert any("ByGameID" in c for c in calls_made)

    def test_uses_by_game_name_when_no_tgdb_id(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)

        calls_made = []

        def mock_get(url, **kwargs):
            calls_made.append(url)
            if "ByGameName" in url:
                return search_resp
            return images_resp

        with patch.object(src._session, "get", side_effect=mock_get):
            with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
                result = src.search(
                    rom_path=tmp_path / "mm2.nes",
                    system_folder="nes",
                    rom_hash=RomHash(md5="aa", crc32="bb"),
                    canonical_name="Mega Man 2",
                    cross_db_ids={},
                    media_dir=tmp_path / "media",
                )

        assert result is not None
        assert any("ByGameName" in c for c in calls_made)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_sleep_called_when_too_fast(self, tmp_path: Path) -> None:
        src = _make_source()
        # Pretend last request was just now
        src._last_request_time = time.monotonic()

        search_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        images_resp = _mock_response(200, _CANNED_IMAGES_RESPONSE)

        sleep_calls = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("backend.scrapers.thegamesdb.time.sleep", side_effect=fake_sleep):
            with patch.object(src._session, "get", side_effect=[search_resp, images_resp]):
                with patch("backend.scrapers.thegamesdb._download_file", return_value=False):
                    src.search(
                        rom_path=tmp_path / "mm2.nes",
                        system_folder="nes",
                        rom_hash=RomHash(md5="aa", crc32="bb"),
                        canonical_name="Mega Man 2",
                        cross_db_ids={},
                        media_dir=tmp_path / "media",
                    )

        # At least one sleep call should have been made
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
    def test_build_sources_includes_thegamesdb_when_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_tgdb_build_sources__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        assert "thegamesdb" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        tgdb_sources = [s for s in sources if s.name == "thegamesdb"]
        assert len(tgdb_sources) == 1

    def test_build_sources_excludes_thegamesdb_when_not_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_tgdb_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        tgdb_sources = [s for s in sources if s.name == "thegamesdb"]
        assert len(tgdb_sources) == 0
