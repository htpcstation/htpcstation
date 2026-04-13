"""Tests for Task 003 — ScreenScraper.fr adapter.

Covers the acceptance criteria from the Task Brief:
- ScreenScraperSource("", "").is_configured() returns False
- search() with valid mocked response returns a fully-populated ScraperResult
- HTTP 429 → returns None
- HTTP 404 → returns None
- Network error → returns None
- JSON parse error → returns None
- Missing "jeu" key → returns None
- _pick_by_region / _pick_by_lang priority and fallback behaviour
- Unknown platform folder → search() returns None (DEBUG log)
- No real network calls (all requests mocked)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from backend.scrapers.screenscraper import (
    ScreenScraperSource,
    _pick_by_region,
    _pick_by_lang,
    _best_media_url,
    _scrub_url,
    REGION_PRIO,
)
from backend.retro_scraper import RomHash, ScraperResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_CANNED_JEU = {
    "noms": [
        {"region": "jp", "text": "Rockman 2"},
        {"region": "us", "text": "Mega Man 2"},
        {"region": "eu", "text": "Mega Man 2"},
    ],
    "synopsis": [
        {"langue": "fr", "text": "Un super jeu"},
        {"langue": "en", "text": "A great platformer"},
    ],
    "developpeur": {"text": "Capcom"},
    "editeur": {"text": "Capcom"},
    "genres": [
        {
            "noms": [
                {"langue": "fr", "text": "Plate-forme"},
                {"langue": "en", "text": "Platform"},
            ]
        }
    ],
    "joueurs": {"text": "1"},
    "note": {"text": "18"},
    "dates": [
        {"region": "jp", "text": "19881224T000000"},
        {"region": "us", "text": "19890101T000000"},
    ],
    "medias": [
        {
            "type": "box-2D",
            "region": "us",
            "url": "https://media.screenscraper.fr/covers/nes/megaman2_us.jpg",
            "format": "jpg",
        },
        {
            "type": "wheel-hd",
            "region": "us",
            "url": "https://media.screenscraper.fr/wheels/nes/megaman2_hd.png",
            "format": "png",
        },
        {
            "type": "ss",
            "region": "us",
            "url": "https://media.screenscraper.fr/screenshots/nes/megaman2.jpg",
            "format": "jpg",
        },
        {
            "type": "video",
            "region": "us",
            "url": "https://media.screenscraper.fr/videos/nes/megaman2.mp4",
            "format": "mp4",
        },
    ],
}

_CANNED_RESPONSE = {
    "response": {
        "ssuser": {"requeststoday": 42, "maxrequestsperday": 20000},
        "jeu": _CANNED_JEU,
    }
}


def _make_source(devid: str = "testdev", devpassword: str = "testpw") -> ScreenScraperSource:
    return ScreenScraperSource(devid=devid, devpassword=devpassword)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = (200 <= status_code < 300)
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no body")
    return resp


def _search_with_mock(
    source: ScreenScraperSource,
    mock_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    system_folder: str = "nes",
) -> ScraperResult | None:
    """Run source.search() with the HTTP session patched to return *mock_resp*."""
    with patch.object(source._session, "get", return_value=mock_resp):
        return source.search(
            rom_path=rom_path,
            system_folder=system_folder,
            rom_hash=RomHash(md5="aabbccddaabbccdd", crc32="12345678"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=media_dir,
        )


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_both_empty(self) -> None:
        assert ScreenScraperSource("", "").is_configured() is False

    def test_false_when_devid_empty(self) -> None:
        assert ScreenScraperSource("", "pw").is_configured() is False

    def test_false_when_devpassword_empty(self) -> None:
        assert ScreenScraperSource("id", "").is_configured() is False

    def test_true_when_both_set(self) -> None:
        assert ScreenScraperSource("id", "pw").is_configured() is True


# ---------------------------------------------------------------------------
# _pick_by_region
# ---------------------------------------------------------------------------


class TestPickByRegion:
    def test_returns_highest_priority_match(self) -> None:
        items = [
            {"region": "jp", "text": "JP text"},
            {"region": "us", "text": "US text"},
            {"region": "eu", "text": "EU text"},
        ]
        assert _pick_by_region(items, "text", REGION_PRIO) == "US text"

    def test_falls_back_to_first_when_no_match(self) -> None:
        items = [{"region": "kr", "text": "Korean text"}]
        assert _pick_by_region(items, "text", REGION_PRIO) == "Korean text"

    def test_returns_empty_string_for_empty_list(self) -> None:
        assert _pick_by_region([], "text", REGION_PRIO) == ""

    def test_respects_order_of_region_prio(self) -> None:
        items = [
            {"region": "eu", "text": "EU"},
            {"region": "wor", "text": "WOR"},
        ]
        # "wor" comes before "eu" in REGION_PRIO
        assert _pick_by_region(items, "text", REGION_PRIO) == "WOR"


# ---------------------------------------------------------------------------
# _pick_by_lang
# ---------------------------------------------------------------------------


class TestPickByLang:
    def test_returns_english_when_available(self) -> None:
        items = [
            {"langue": "fr", "text": "Français"},
            {"langue": "en", "text": "English"},
        ]
        assert _pick_by_lang(items, "text", ["en"]) == "English"

    def test_falls_back_to_first_when_no_match(self) -> None:
        items = [{"langue": "de", "text": "Deutsch"}]
        assert _pick_by_lang(items, "text", ["en"]) == "Deutsch"

    def test_returns_empty_for_empty_list(self) -> None:
        assert _pick_by_lang([], "text", ["en"]) == ""


# ---------------------------------------------------------------------------
# _best_media_url
# ---------------------------------------------------------------------------


class TestBestMediaUrl:
    def test_returns_none_when_no_match(self) -> None:
        assert _best_media_url([], ["box-2D"]) is None

    def test_returns_preferred_region(self) -> None:
        medias = [
            {"type": "box-2D", "region": "jp", "url": "jp.jpg", "format": "jpg"},
            {"type": "box-2D", "region": "us", "url": "us.jpg", "format": "jpg"},
        ]
        url, fmt = _best_media_url(medias, ["box-2D"])
        assert url == "us.jpg"

    def test_falls_back_to_any_region_when_no_pref(self) -> None:
        medias = [
            {"type": "box-2D", "region": "kr", "url": "kr.jpg", "format": "jpg"},
        ]
        url, fmt = _best_media_url(medias, ["box-2D"])
        assert url == "kr.jpg"

    def test_tries_types_in_order(self) -> None:
        medias = [
            {"type": "wheel", "region": "us", "url": "wheel.png", "format": "png"},
        ]
        # wheel-hd not present; should fall through to wheel
        url, fmt = _best_media_url(medias, ["wheel-hd", "wheel"])
        assert url == "wheel.png"


# ---------------------------------------------------------------------------
# search() — HTTP error handling
# ---------------------------------------------------------------------------


class TestSearchHttpErrors:
    def test_returns_none_on_429(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(429)
        result = _search_with_mock(src, resp, tmp_path / "mm2.nes", tmp_path / "media")
        assert result is None

    def test_returns_none_on_404(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(404)
        result = _search_with_mock(src, resp, tmp_path / "mm2.nes", tmp_path / "media")
        assert result is None

    def test_returns_none_on_other_non_2xx(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(500)
        result = _search_with_mock(src, resp, tmp_path / "mm2.nes", tmp_path / "media")
        assert result is None

    def test_returns_none_on_network_error(self, tmp_path: Path) -> None:
        src = _make_source()
        with patch.object(src._session, "get", side_effect=requests.ConnectionError("no net")):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aabb", crc32="1234"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None

    def test_network_error_log_does_not_contain_devpassword(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Credentials must not appear verbatim in log output on network error."""
        secret_password = "super_secret_devpw"
        src = ScreenScraperSource(devid="mydevid", devpassword=secret_password)

        # Simulate a ConnectionError whose string representation embeds the full
        # request URL (which requests normally includes).
        fake_url = (
            f"https://www.screenscraper.fr/api2/jeuInfos.php"
            f"?devid=mydevid&devpassword={secret_password}&output=json"
        )
        exc = requests.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: {fake_url}")

        import logging as _logging
        with caplog.at_level(_logging.WARNING, logger="scraper"):
            with patch.object(src._session, "get", side_effect=exc):
                src.search(
                    rom_path=tmp_path / "mm2.nes",
                    system_folder="nes",
                    rom_hash=RomHash(md5="aabb", crc32="1234"),
                    canonical_name="Mega Man 2",
                    cross_db_ids={},
                    media_dir=tmp_path / "media",
                )

        combined = " ".join(caplog.messages)
        assert secret_password not in combined

    def test_returns_none_on_json_error(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.ok = True
        resp.json.side_effect = ValueError("bad json")
        result = _search_with_mock(src, resp, tmp_path / "mm2.nes", tmp_path / "media")
        assert result is None

    def test_returns_none_when_jeu_absent(self, tmp_path: Path) -> None:
        src = _make_source()
        body = {"response": {"ssuser": {}, "jeu": None}}
        resp = _mock_response(200, body)
        result = _search_with_mock(src, resp, tmp_path / "mm2.nes", tmp_path / "media")
        assert result is None

    def test_returns_none_for_unknown_platform(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(200, _CANNED_RESPONSE)
        with patch.object(src._session, "get", return_value=resp):
            result = src.search(
                rom_path=tmp_path / "game.rom",
                system_folder="unknownplatform_xyz",
                rom_hash=RomHash(md5="aabb", crc32="1234"),
                canonical_name="Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )
        assert result is None


# ---------------------------------------------------------------------------
# search() — successful metadata parsing
# ---------------------------------------------------------------------------


class TestSearchSuccess:
    def test_returns_scraperresult_with_metadata(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(200, _CANNED_RESPONSE)

        # Stub out media downloads so we don't actually hit the network
        with patch("backend.scrapers.screenscraper._download_file", return_value=False):
            result = _search_with_mock(src, resp, tmp_path / "Mega Man 2 (USA).nes", tmp_path / "media")

        assert result is not None
        assert result.name == "Mega Man 2"
        assert result.description == "A great platformer"
        assert result.developer == "Capcom"
        assert result.publisher == "Capcom"
        assert result.genre == "Platform"
        assert result.players == "1"
        assert abs(result.rating - 18 / 20.0) < 1e-9
        assert result.release_date == "19890101T000000"

    def test_rating_zero_on_missing_note(self, tmp_path: Path) -> None:
        jeu = dict(_CANNED_JEU)
        jeu.pop("note", None)
        body = {"response": {"ssuser": {}, "jeu": jeu}}
        src = _make_source()
        resp = _mock_response(200, body)
        with patch("backend.scrapers.screenscraper._download_file", return_value=False):
            result = _search_with_mock(src, resp, tmp_path / "game.nes", tmp_path / "media")
        assert result is not None
        assert result.rating == 0.0

    def test_rating_zero_on_invalid_note_text(self, tmp_path: Path) -> None:
        jeu = dict(_CANNED_JEU)
        jeu["note"] = {"text": "N/A"}
        body = {"response": {"ssuser": {}, "jeu": jeu}}
        src = _make_source()
        resp = _mock_response(200, body)
        with patch("backend.scrapers.screenscraper._download_file", return_value=False):
            result = _search_with_mock(src, resp, tmp_path / "game.nes", tmp_path / "media")
        assert result is not None
        assert result.rating == 0.0

    def test_media_paths_populated_on_successful_download(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(200, _CANNED_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest_path: Path) -> bool:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"fake")
            return True

        with patch("backend.scrapers.screenscraper._download_file", side_effect=fake_download):
            result = _search_with_mock(
                src, resp,
                tmp_path / "Mega Man 2 (USA).nes",
                media_dir,
            )

        assert result is not None
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).jpg"
        assert result.marquee_path == media_dir / "wheels" / "Mega Man 2 (USA).png"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).jpg"
        assert result.video_path == media_dir / "videos" / "Mega Man 2 (USA).mp4"

    def test_media_path_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        resp = _mock_response(200, _CANNED_RESPONSE)
        media_dir = tmp_path / "media"

        with patch("backend.scrapers.screenscraper._download_file", return_value=False):
            result = _search_with_mock(src, resp, tmp_path / "game.nes", media_dir)

        assert result is not None
        assert result.thumbnail_path is None
        assert result.marquee_path is None
        assert result.screenshot_path is None
        assert result.video_path is None


# ---------------------------------------------------------------------------
# close() and __del__
# ---------------------------------------------------------------------------


class TestCloseAndDel:
    def test_close_is_noop(self) -> None:
        """close() must not raise and must not close the session."""
        src = _make_source()
        original_session = src._session
        src.close()
        # Session should still be the same object (not replaced)
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
    def test_build_sources_returns_screenscraper(self) -> None:
        """_build_sources() instantiates ScreenScraperSource when enabled."""
        import json
        from unittest.mock import patch as upatch

        from backend.config import Config
        from backend.retro_scraper import RetroScraper
        from backend.scrapers.screenscraper import ScreenScraperSource

        cfg_file = Path("/tmp/__htpc_test_build_sources_config__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        # screenscraper should be in enabled sources by default
        assert "screenscraper" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        ss_sources = [s for s in sources if isinstance(s, ScreenScraperSource)]
        assert len(ss_sources) == 1

    def test_build_sources_excludes_screenscraper_when_not_enabled(self) -> None:
        """_build_sources() skips ScreenScraperSource when not in enabled list."""
        import json
        from unittest.mock import patch as upatch

        from backend.config import Config
        from backend.retro_scraper import RetroScraper
        from backend.scrapers.screenscraper import ScreenScraperSource

        cfg_file = Path("/tmp/__htpc_test_build_sources_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        ss_sources = [s for s in sources if isinstance(s, ScreenScraperSource)]
        assert len(ss_sources) == 0
