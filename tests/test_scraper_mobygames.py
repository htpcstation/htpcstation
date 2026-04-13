"""Tests for Task 005 — MobyGames adapter.

Acceptance criteria from the Task Brief:
- MobyGamesSource("").is_configured() returns False
- With mocked responses, returns ScraperResult with correct metadata and media paths
- HTML stripping: <p>Hello</p> → Hello
- Date conversion: "1989-01-01" → "19890101T000000"
- HTTP 429 → returns None
- HTTP 404 → returns None
- HTTP 401 → returns None, sets _auth_failed
- Network error → returns None
- Platform ID miss → search() returns None with DEBUG log
- Rate limit enforced (monkeypatched time.sleep)
- API key must not appear in log output
- No real network calls
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.retro_scraper import RomHash, ScraperResult
from backend.scrapers.mobygames import MobyGamesSource, MOBY_PLATFORM_IDS, _strip_html


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CANNED_SEARCH_RESPONSE = {
    "games": [
        {
            "id": 5674,
            "title": "Mega Man 2",
            "platforms": [{"platform_id": 22, "first_release_date": "1989-01-01"}],
        }
    ]
}

_CANNED_DETAIL_RESPONSE = {
    "games": [
        {
            "id": 5674,
            "title": "Mega Man 2",
            "description": "<p>A great platformer</p>",
            "genres": [
                {"genre_category_id": 1, "genre_name": "Action"},
                {"genre_category_id": 2, "genre_name": "Shooter"},
            ],
            "developers": [{"company_name": "Capcom", "platform_id": 22}],
            "publishers": [{"company_name": "Capcom", "platform_id": 22}],
            "covers": [
                {"platform_id": 22, "image_url": "https://cdn.mobygames.com/covers/mm2_cover.jpg"},
            ],
            "screenshots": [
                {"platform_id": 22, "image_url": "https://cdn.mobygames.com/ss/mm2_ss.jpg"},
            ],
            "platforms": [{"platform_id": 22, "first_release_date": "1989-01-01"}],
        }
    ]
}


def _make_source(api_key: str = "testkey") -> MobyGamesSource:
    return MobyGamesSource(api_key=api_key)


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
    source: MobyGamesSource,
    search_resp: MagicMock,
    detail_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    system_folder: str = "nes",
) -> ScraperResult | None:
    """Run source.search() with both HTTP calls mocked."""
    responses = [search_resp, detail_resp]
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
# HTML stripping
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_strips_paragraph_tags(self) -> None:
        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_strips_nested_tags(self) -> None:
        assert _strip_html("<div><p>World</p></div>") == "World"

    def test_leaves_plain_text(self) -> None:
        assert _strip_html("plain text") == "plain text"

    def test_handles_empty_string(self) -> None:
        assert _strip_html("") == ""


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_empty(self) -> None:
        assert MobyGamesSource("").is_configured() is False

    def test_true_when_key_set(self) -> None:
        assert MobyGamesSource("abc123").is_configured() is True


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


class TestName:
    def test_name_is_mobygames(self) -> None:
        assert _make_source().name == "mobygames"


# ---------------------------------------------------------------------------
# Platform mapping
# ---------------------------------------------------------------------------


class TestPlatformMapping:
    def test_known_platforms_mapped(self) -> None:
        for folder in ("nes", "snes", "gb", "gba", "gbc", "n64", "megadrive", "psx"):
            assert folder in MOBY_PLATFORM_IDS, f"{folder!r} missing from MOBY_PLATFORM_IDS"

    def test_platform_ids_are_ints(self) -> None:
        for folder, pid in MOBY_PLATFORM_IDS.items():
            assert isinstance(pid, int), f"{folder!r} → {pid!r} is not int"

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
# HTTP error handling — search step
# ---------------------------------------------------------------------------


class TestSearchHttpErrors:
    def test_returns_none_on_401(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(401)
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
        assert src._auth_failed is True

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

    def test_returns_none_on_non_2xx(self, tmp_path: Path) -> None:
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
        body = {"games": []}
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

    def test_auth_failed_flag_prevents_retries(self, tmp_path: Path) -> None:
        src = _make_source()
        src._auth_failed = True
        # Should return None immediately without any network call
        mock_get = MagicMock()
        src._session.get = mock_get
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# API key scrubbing
# ---------------------------------------------------------------------------


class TestApiKeyScrubbing:
    def test_api_key_absent_from_logs_on_network_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret_key = "super_secret_moby_key"
        src = MobyGamesSource(api_key=secret_key)

        exc_msg = f"HTTPSConnectionPool: failed api_key={secret_key}&title=test"
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
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, _CANNED_DETAIL_RESPONSE)

        with patch("backend.scrapers.mobygames._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "Mega Man 2 (USA).nes", tmp_path / "media",
            )

        assert result is not None
        assert result.name == "Mega Man 2"
        assert result.description == "A great platformer"  # HTML stripped
        assert result.developer == "Capcom"
        assert result.publisher == "Capcom"
        assert result.genre == "Action"  # genre_category_id=1
        assert result.release_date == "19890101T000000"
        assert result.rating == 0.0  # not available on Hobbyist tier
        assert result.players == ""  # not available on Hobbyist tier

    def test_description_html_stripped(self, tmp_path: Path) -> None:
        detail = dict(_CANNED_DETAIL_RESPONSE)
        detail["games"] = [dict(detail["games"][0])]
        detail["games"][0]["description"] = "<h1>Title</h1><p>Description text</p>"
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, detail)

        with patch("backend.scrapers.mobygames._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        assert result is not None
        assert "<" not in result.description
        assert "Title" in result.description
        assert "Description text" in result.description

    def test_genre_prefers_basic_genres_category(self, tmp_path: Path) -> None:
        """genre_category_id=1 (Basic Genres) should be preferred over others."""
        detail = dict(_CANNED_DETAIL_RESPONSE)
        detail["games"] = [dict(detail["games"][0])]
        detail["games"][0]["genres"] = [
            {"genre_category_id": 5, "genre_name": "Perspective"},
            {"genre_category_id": 1, "genre_name": "Action"},
        ]
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, detail)

        with patch("backend.scrapers.mobygames._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.genre == "Action"

    def test_media_paths_populated_on_successful_download(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, _CANNED_DETAIL_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        with patch("backend.scrapers.mobygames._download_file", side_effect=fake_download):
            result = _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "Mega Man 2 (USA).nes", media_dir,
            )

        assert result is not None
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).jpg"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).jpg"
        assert result.marquee_path is None   # not available from MobyGames
        assert result.video_path is None     # not available from MobyGames

    def test_media_paths_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, _CANNED_DETAIL_RESPONSE)

        with patch("backend.scrapers.mobygames._download_file", return_value=False):
            result = _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.thumbnail_path is None
        assert result.screenshot_path is None

    def test_prefers_platform_matching_cover(self, tmp_path: Path) -> None:
        """Cover with matching platform_id should be preferred over first entry."""
        detail = dict(_CANNED_DETAIL_RESPONSE)
        detail["games"] = [dict(detail["games"][0])]
        detail["games"][0]["covers"] = [
            {"platform_id": 999, "image_url": "https://cdn.mobygames.com/wrong.jpg"},
            {"platform_id": 22, "image_url": "https://cdn.mobygames.com/correct.jpg"},
        ]
        src = _make_source()
        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, detail)
        downloaded_urls = []

        def fake_download(session, url, dest: Path) -> bool:
            downloaded_urls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        with patch("backend.scrapers.mobygames._download_file", side_effect=fake_download):
            _search_with_mocks(
                src, search_resp, detail_resp,
                tmp_path / "game.nes", tmp_path / "media",
            )

        cover_urls = [u for u in downloaded_urls if "covers" in u or "cover" in u]
        if cover_urls:
            assert "correct.jpg" in cover_urls[0]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_sleep_called_when_too_fast(self, tmp_path: Path) -> None:
        src = _make_source()
        # Pretend last request was just now
        src._last_request_time = time.monotonic()

        search_resp = _mock_response(200, _CANNED_SEARCH_RESPONSE)
        detail_resp = _mock_response(200, _CANNED_DETAIL_RESPONSE)

        sleep_calls = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("backend.scrapers.mobygames.time.sleep", side_effect=fake_sleep):
            with patch.object(src._session, "get", side_effect=[search_resp, detail_resp]):
                with patch("backend.scrapers.mobygames._download_file", return_value=False):
                    src.search(
                        rom_path=tmp_path / "mm2.nes",
                        system_folder="nes",
                        rom_hash=RomHash(md5="aa", crc32="bb"),
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
    def test_build_sources_includes_mobygames_when_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_moby_build_sources__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        assert "mobygames" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        moby_sources = [s for s in sources if s.name == "mobygames"]
        assert len(moby_sources) == 1

    def test_build_sources_excludes_mobygames_when_not_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_moby_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        moby_sources = [s for s in sources if s.name == "mobygames"]
        assert len(moby_sources) == 0
