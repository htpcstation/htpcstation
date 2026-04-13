"""Tests for Task 004 — EmuMovies adapter.

Acceptance criteria from the Task Brief:
- EmuMoviesSource("", "").is_configured() returns False
- With mocked login and mocked media search, search() returns a ScraperResult
  with video_path and screenshot_path set.
- Login failure (non-2xx on login endpoint) → search() returns None and does
  not retry within the same run (_login_failed flag).
- _login_failed flag prevents repeated login attempts.
- Password not present in any log output when a ConnectionError is raised.
- _utils.py is used by both screenscraper.py and emumovies.py.
- All mocks — no real network calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from backend.retro_scraper import RomHash, ScraperResult
from backend.scrapers.emumovies import EmuMoviesSource, EM_SYSTEM_NAMES
from backend.scrapers._utils import scrub_url


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_CANNED_TOKEN_RESPONSE = {"Token": "fake-jwt-token"}

_CANNED_MEDIA_RESPONSE = [
    {"MediaType": "Video",      "URL": "https://cdn.emumovies.com/nes/mm2.mp4"},
    {"MediaType": "Screenshot", "URL": "https://cdn.emumovies.com/nes/mm2.jpg"},
    {"MediaType": "BoxFront",   "URL": "https://cdn.emumovies.com/nes/mm2_box.jpg"},
    {"MediaType": "Logo",       "URL": "https://cdn.emumovies.com/nes/mm2_logo.png"},
]


def _make_source(username: str = "testuser", password: str = "testpw") -> EmuMoviesSource:
    return EmuMoviesSource(username=username, password=password)


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
    source: EmuMoviesSource,
    login_resp: MagicMock,
    search_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    system_folder: str = "nes",
) -> ScraperResult | None:
    """Run source.search() with both the login and media-search calls mocked."""
    # post → login, get → media search
    source._session.post = MagicMock(return_value=login_resp)
    source._session.get = MagicMock(return_value=search_resp)
    return source.search(
        rom_path=rom_path,
        system_folder=system_folder,
        rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
        canonical_name="Mega Man 2",
        cross_db_ids={},
        media_dir=media_dir,
    )


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_both_empty(self) -> None:
        assert EmuMoviesSource("", "").is_configured() is False

    def test_false_when_username_empty(self) -> None:
        assert EmuMoviesSource("", "pw").is_configured() is False

    def test_false_when_password_empty(self) -> None:
        assert EmuMoviesSource("user", "").is_configured() is False

    def test_true_when_both_set(self) -> None:
        assert EmuMoviesSource("user", "pw").is_configured() is True


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


class TestName:
    def test_name_is_emumovies(self) -> None:
        assert _make_source().name == "emumovies"


# ---------------------------------------------------------------------------
# Unknown system folder
# ---------------------------------------------------------------------------


class TestUnknownSystem:
    def test_returns_none_for_unknown_system_folder(self, tmp_path: Path) -> None:
        src = _make_source()
        result = src.search(
            rom_path=tmp_path / "game.rom",
            system_folder="unknownsystem_xyz",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Game",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        # No login attempt should have been made
        assert src._token is None


# ---------------------------------------------------------------------------
# Login failure handling
# ---------------------------------------------------------------------------


class TestLoginFailure:
    def test_login_non_2xx_returns_none(self, tmp_path: Path) -> None:
        src = _make_source()
        login_resp = _mock_response(401)
        src._session.post = MagicMock(return_value=login_resp)
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        assert src._login_failed is True

    def test_login_missing_token_sets_flag(self, tmp_path: Path) -> None:
        src = _make_source()
        login_resp = _mock_response(200, {"status": "ok"})  # no Token key
        src._session.post = MagicMock(return_value=login_resp)
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        assert src._login_failed is True

    def test_login_failure_does_not_retry_on_subsequent_search(self, tmp_path: Path) -> None:
        """After login fails, _login_failed prevents another login attempt."""
        src = _make_source()
        login_resp = _mock_response(403)
        mock_post = MagicMock(return_value=login_resp)
        src._session.post = mock_post

        # First search — triggers login attempt
        src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        first_call_count = mock_post.call_count

        # Second search — must NOT attempt login again
        src.search(
            rom_path=tmp_path / "sonic.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="cc", crc32="dd"),
            canonical_name="Sonic",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert mock_post.call_count == first_call_count  # no new login call

    def test_login_network_error_sets_flag(self, tmp_path: Path) -> None:
        src = _make_source()
        src._session.post = MagicMock(
            side_effect=requests.ConnectionError("login network error")
        )
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        assert src._login_failed is True

    def test_login_json_array_response_sets_flag(self, tmp_path: Path) -> None:
        """Login endpoint returning a JSON array must not raise AttributeError.

        Regression guard: data.get() on a list would raise AttributeError before
        the isinstance(data, dict) guard was added.
        """
        src = _make_source()
        login_resp = _mock_response(200, [])  # valid JSON but a list, not a dict
        src._session.post = MagicMock(return_value=login_resp)
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None
        assert src._login_failed is True


# ---------------------------------------------------------------------------
# Successful search — media populated
# ---------------------------------------------------------------------------


class TestSearchSuccess:
    def test_returns_scraperresult_with_media_paths(self, tmp_path: Path) -> None:
        src = _make_source()
        login_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        search_resp = _mock_response(200, _CANNED_MEDIA_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        with patch("backend.scrapers.emumovies._download_file", side_effect=fake_download):
            result = _do_search(
                src, login_resp, search_resp,
                tmp_path / "Mega Man 2 (USA).nes", media_dir,
            )

        assert result is not None
        assert result.video_path == media_dir / "videos" / "Mega Man 2 (USA).mp4"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).jpg"
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).jpg"
        assert result.marquee_path == media_dir / "wheels" / "Mega Man 2 (USA).png"

    def test_metadata_fields_not_populated(self, tmp_path: Path) -> None:
        """EmuMovies does not populate metadata — name/description must remain empty."""
        src = _make_source()
        login_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        search_resp = _mock_response(200, _CANNED_MEDIA_RESPONSE)

        with patch("backend.scrapers.emumovies._download_file", return_value=False):
            result = _do_search(
                src, login_resp, search_resp,
                tmp_path / "mm2.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.name == ""
        assert result.description == ""
        assert result.developer == ""

    def test_media_paths_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        login_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        search_resp = _mock_response(200, _CANNED_MEDIA_RESPONSE)

        with patch("backend.scrapers.emumovies._download_file", return_value=False):
            result = _do_search(
                src, login_resp, search_resp,
                tmp_path / "mm2.nes", tmp_path / "media",
            )

        assert result is not None
        assert result.video_path is None
        assert result.screenshot_path is None
        assert result.thumbnail_path is None
        assert result.marquee_path is None

    def test_token_stored_and_header_set(self, tmp_path: Path) -> None:
        src = _make_source()
        login_resp = _mock_response(200, {"Token": "my-token-value"})
        search_resp = _mock_response(200, [])

        src._session.post = MagicMock(return_value=login_resp)
        src._session.get = MagicMock(return_value=search_resp)
        src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )

        assert src._token == "my-token-value"
        assert src._session.headers.get("Authorization") == "Bearer my-token-value"


# ---------------------------------------------------------------------------
# Media search HTTP error handling
# ---------------------------------------------------------------------------


class TestSearchHttpErrors:
    def _with_token(self, src: EmuMoviesSource) -> None:
        """Pre-set a valid token so login is skipped."""
        src._token = "pre-set-token"
        src._session.headers.update({"Authorization": "Bearer pre-set-token"})

    def test_returns_none_on_404(self, tmp_path: Path) -> None:
        src = _make_source()
        self._with_token(src)
        src._session.get = MagicMock(return_value=_mock_response(404))
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
        self._with_token(src)
        src._session.get = MagicMock(return_value=_mock_response(500))
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
        self._with_token(src)
        src._session.get = MagicMock(
            side_effect=requests.ConnectionError("no network")
        )
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None

    def test_empty_media_list_returns_scraperresult_with_no_media(self, tmp_path: Path) -> None:
        """An empty response is valid — returns a ScraperResult with no media set."""
        src = _make_source()
        self._with_token(src)
        src._session.get = MagicMock(return_value=_mock_response(200, []))
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is not None
        assert result.video_path is None
        assert result.screenshot_path is None


# ---------------------------------------------------------------------------
# Password scrubbing in logs
# ---------------------------------------------------------------------------


class TestPasswordScrubbing:
    def test_password_absent_from_logs_on_login_connection_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "super_secret_pw"
        src = EmuMoviesSource(username="user", password=secret)

        # Simulate a ConnectionError that embeds the password in its message
        exc_msg = f"HTTPSConnectionPool: Login failed password={secret}&other=x"
        src._session.post = MagicMock(
            side_effect=requests.ConnectionError(exc_msg)
        )

        with caplog.at_level(logging.WARNING, logger="scraper"):
            src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        combined = " ".join(caplog.messages)
        assert secret not in combined

    def test_password_absent_from_logs_on_search_connection_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "super_secret_pw"
        src = EmuMoviesSource(username="user", password=secret)
        src._token = "token"
        src._session.headers.update({"Authorization": "Bearer token"})

        exc_msg = f"HTTPSConnectionPool: request failed password={secret}&x=y"
        src._session.get = MagicMock(
            side_effect=requests.ConnectionError(exc_msg)
        )

        with caplog.at_level(logging.WARNING, logger="scraper"):
            src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        combined = " ".join(caplog.messages)
        assert secret not in combined


# ---------------------------------------------------------------------------
# _parse_media_list — envelope handling
# ---------------------------------------------------------------------------


class TestParseMediaList:
    def test_plain_list(self) -> None:
        src = _make_source()
        items = [{"MediaType": "Video", "URL": "http://x.com/v.mp4"}]
        assert src._parse_media_list(items) == items

    def test_results_envelope(self) -> None:
        src = _make_source()
        inner = [{"MediaType": "Video", "URL": "http://x.com/v.mp4"}]
        data = {"results": inner}
        assert src._parse_media_list(data) == inner

    def test_data_envelope(self) -> None:
        src = _make_source()
        inner = [{"MediaType": "Screenshot", "URL": "http://x.com/s.jpg"}]
        data = {"data": inner}
        assert src._parse_media_list(data) == inner

    def test_unknown_shape_returns_empty(self) -> None:
        src = _make_source()
        assert src._parse_media_list("unexpected string") == []


# ---------------------------------------------------------------------------
# _pick_media — type fallbacks and URL extension
# ---------------------------------------------------------------------------


class TestPickMedia:
    def test_returns_empty_when_no_match(self) -> None:
        src = _make_source()
        url, ext = src._pick_media([], ["Video"])
        assert url == ""
        assert ext == ""

    def test_picks_first_matching_type(self) -> None:
        src = _make_source()
        items = [
            {"MediaType": "VideoSnap", "URL": "http://x.com/snap.mp4"},
            {"MediaType": "Video",     "URL": "http://x.com/full.mp4"},
        ]
        url, ext = src._pick_media(items, ["Video", "VideoSnap"])
        assert url == "http://x.com/full.mp4"
        assert ext == "mp4"

    def test_falls_back_to_second_type(self) -> None:
        src = _make_source()
        items = [{"MediaType": "VideoSnap", "URL": "http://x.com/snap.mp4"}]
        url, ext = src._pick_media(items, ["Video", "VideoSnap"])
        assert url == "http://x.com/snap.mp4"

    def test_extension_from_url(self) -> None:
        src = _make_source()
        items = [{"MediaType": "Screenshot", "URL": "http://x.com/img.png"}]
        _, ext = src._pick_media(items, ["Screenshot"])
        assert ext == "png"

    def test_default_extension_when_url_has_none(self) -> None:
        src = _make_source()
        items = [{"MediaType": "Logo", "URL": "http://x.com/logo"}]
        _, ext = src._pick_media(items, ["Logo"])
        assert ext == "png"  # default for Logo

    def test_url_with_query_string_ignored_for_extension(self) -> None:
        src = _make_source()
        items = [{"MediaType": "Video", "URL": "http://x.com/video.mp4?token=abc"}]
        _, ext = src._pick_media(items, ["Video"])
        assert ext == "mp4"

    def test_alternate_field_names_type(self) -> None:
        """Adapter should also accept 'Type' as the media type field."""
        src = _make_source()
        items = [{"Type": "Screenshot", "URL": "http://x.com/ss.jpg"}]
        url, ext = src._pick_media(items, ["Screenshot"])
        assert url == "http://x.com/ss.jpg"

    def test_alternate_field_names_url(self) -> None:
        """Adapter should also accept lowercase 'url' field."""
        src = _make_source()
        items = [{"MediaType": "BoxFront", "url": "http://x.com/box.jpg"}]
        url, _ = src._pick_media(items, ["BoxFront"])
        assert url == "http://x.com/box.jpg"


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
# _utils.scrub_url — shared by both adapters
# ---------------------------------------------------------------------------


class TestScrubUrl:
    def test_scrubs_password_param(self) -> None:
        url = "https://api.example.com?password=mysecret&other=x"
        result = scrub_url(url)
        assert "mysecret" not in result
        assert "password=***" in result

    def test_scrubs_token_param(self) -> None:
        url = "https://api.example.com?token=abc123&x=y"
        result = scrub_url(url)
        assert "abc123" not in result
        assert "token=***" in result

    def test_scrubs_devpassword_and_sspassword(self) -> None:
        url = "https://x.com?devpassword=devpw123&sspassword=sspw456&ok=1"
        result = scrub_url(url)
        assert "devpw123" not in result
        assert "sspw456" not in result
        assert "devpassword=***" in result
        assert "sspassword=***" in result

    def test_leaves_non_credential_params(self) -> None:
        url = "https://x.com?SystemName=NES&Title=Mega+Man"
        assert scrub_url(url) == url

    def test_imported_by_both_adapters(self) -> None:
        """Verify _utils.scrub_url is the same function used in both adapters."""
        from backend.scrapers import screenscraper
        from backend.scrapers import emumovies
        # Both modules should ultimately use the same implementation
        # (screenscraper wraps it; emumovies imports it directly)
        assert screenscraper._scrub_url("password=x") == scrub_url("password=x")
        assert emumovies._scrub_url("password=x") == scrub_url("password=x")


# ---------------------------------------------------------------------------
# RetroScraper._build_sources integration
# ---------------------------------------------------------------------------


class TestBuildSourcesIntegration:
    def test_build_sources_includes_emumovies_when_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_emumovies_build_sources__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        # emumovies should be in enabled sources by default
        assert "emumovies" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        em_sources = [s for s in sources if s.name == "emumovies"]
        assert len(em_sources) == 1

    def test_build_sources_excludes_emumovies_when_not_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_emumovies_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        em_sources = [s for s in sources if s.name == "emumovies"]
        assert len(em_sources) == 0
