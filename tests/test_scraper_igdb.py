"""Tests for Task 006 — IGDB adapter.

Acceptance criteria from the Task Brief:
- IGDBSource("", "").is_configured() returns False
- With mocked Twitch token response + mocked IGDB game search,
  search() returns ScraperResult with name, description, developer,
  rating, cover, and screenshot populated.
- _login_failed flag prevents retry after 401.
- Unix timestamp converted correctly to gamelist date string.
- _igdb_image_url replaces URL prefix and size token correctly.
- All existing tests still pass.
- No real network calls.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.retro_scraper import RomHash, ScraperResult
from backend.scrapers.igdb import IGDBSource, IGDB_PLATFORM_IDS, _igdb_image_url


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_CANNED_TOKEN_RESPONSE = {
    "access_token": "fake-igdb-token",
    "expires_in": 5183944,
    "token_type": "Bearer",
}

_CANNED_GAME = {
    "id": 1234,
    "name": "Mega Man 2",
    "summary": "A classic NES platformer",
    "involved_companies": [
        {
            "developer": True,
            "publisher": False,
            "company": {"name": "Capcom"},
        },
        {
            "developer": False,
            "publisher": True,
            "company": {"name": "Capcom"},
        },
    ],
    "genres": [{"name": "Platform"}],
    "game_modes": [{"slug": "single-player"}],
    "first_release_date": 599616000,  # 1989-01-01T00:00:00 UTC
    "rating": 85.0,
    "platforms": [{"id": 18, "name": "NES"}],
    "cover": {"url": "//images.igdb.com/igdb/image/upload/t_thumb/abc123.jpg"},
    "screenshots": [
        {"url": "//images.igdb.com/igdb/image/upload/t_thumb/ss456.jpg"}
    ],
}

_CANNED_GAMES_RESPONSE = [_CANNED_GAME]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(client_id: str = "test_id", client_secret: str = "test_secret") -> IGDBSource:
    return IGDBSource(client_id=client_id, client_secret=client_secret)


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
    source: IGDBSource,
    token_resp: MagicMock,
    games_resp: MagicMock,
    rom_path: Path,
    media_dir: Path,
    system_folder: str = "nes",
    cross_db_ids: dict | None = None,
) -> ScraperResult | None:
    """Run source.search() with token POST and games POST mocked."""
    source._session.post = MagicMock(side_effect=[token_resp, games_resp])
    with patch("backend.scrapers.igdb._download_file", return_value=False):
        return source.search(
            rom_path=rom_path,
            system_folder=system_folder,
            rom_hash=RomHash(md5="aabbccdd", crc32="12345678"),
            canonical_name="Mega Man 2",
            cross_db_ids=cross_db_ids or {},
            media_dir=media_dir,
        )


# ---------------------------------------------------------------------------
# _igdb_image_url helper
# ---------------------------------------------------------------------------


class TestIgdbImageUrl:
    def test_adds_https_to_protocol_relative_url(self) -> None:
        raw = "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
        result = _igdb_image_url(raw, "cover_big")
        assert result.startswith("https://images.igdb.com/")

    def test_replaces_size_token(self) -> None:
        raw = "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
        result = _igdb_image_url(raw, "cover_big")
        assert "/t_cover_big/" in result
        assert "/t_thumb/" not in result

    def test_replaces_screenshot_size(self) -> None:
        raw = "//images.igdb.com/igdb/image/upload/t_thumb/ss.jpg"
        result = _igdb_image_url(raw, "screenshot_big")
        assert "/t_screenshot_big/" in result

    def test_leaves_https_url_as_is(self) -> None:
        raw = "https://images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
        result = _igdb_image_url(raw, "cover_big")
        assert result.startswith("https://")
        assert "/t_cover_big/" in result

    def test_empty_string_returns_empty(self) -> None:
        result = _igdb_image_url("", "cover_big")
        assert result == ""


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_both_empty(self) -> None:
        assert IGDBSource("", "").is_configured() is False

    def test_false_when_client_id_empty(self) -> None:
        assert IGDBSource("", "secret").is_configured() is False

    def test_false_when_client_secret_empty(self) -> None:
        assert IGDBSource("id", "").is_configured() is False

    def test_true_when_both_set(self) -> None:
        assert IGDBSource("id", "secret").is_configured() is True


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


class TestName:
    def test_name_is_igdb(self) -> None:
        assert _make_source().name == "igdb"


# ---------------------------------------------------------------------------
# Successful search
# ---------------------------------------------------------------------------


class TestSearchSuccess:
    def test_returns_scraperresult_with_metadata(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "Mega Man 2 (USA).nes", tmp_path / "media",
        )

        assert result is not None
        assert result.name == "Mega Man 2"
        assert result.description == "A classic NES platformer"
        assert result.developer == "Capcom"
        assert result.publisher == "Capcom"
        assert result.genre == "Platform"
        assert result.players == "1"
        assert result.release_date == "19890101T000000"
        assert abs(result.rating - 0.85) < 1e-6

    def test_unix_timestamp_converted_correctly(self, tmp_path: Path) -> None:
        """Unix timestamp 0 → 1970-01-01T000000."""
        game = dict(_CANNED_GAME)
        game["first_release_date"] = 0
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, [game])

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "test.nes", tmp_path / "media",
        )

        assert result is not None
        assert result.release_date == "19700101T000000"

    def test_rating_normalised_from_100_scale(self, tmp_path: Path) -> None:
        """IGDB rating 100 → 1.0, rating 50 → 0.5."""
        game = dict(_CANNED_GAME)
        game["rating"] = 50.0
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, [game])

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "test.nes", tmp_path / "media",
        )

        assert result is not None
        assert abs(result.rating - 0.5) < 1e-6

    def test_multiplayer_game_mode_maps_to_2(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["game_modes"] = [{"slug": "multiplayer"}]
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, [game])

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "test.nes", tmp_path / "media",
        )

        assert result is not None
        assert result.players == "2"

    def test_cooperative_game_mode_maps_to_2(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["game_modes"] = [{"slug": "co-operative"}]
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, [game])

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "test.nes", tmp_path / "media",
        )

        assert result is not None
        assert result.players == "2"

    def test_unknown_game_mode_leaves_players_empty(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["game_modes"] = [{"slug": "battle-royale"}]
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, [game])

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "test.nes", tmp_path / "media",
        )

        assert result is not None
        assert result.players == ""

    def test_media_paths_populated_on_successful_download(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        media_dir = tmp_path / "media"

        def fake_download(session, url, dest: Path) -> bool:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        src._session.post = MagicMock(side_effect=[token_resp, games_resp])
        with patch("backend.scrapers.igdb._download_file", side_effect=fake_download):
            result = src.search(
                rom_path=tmp_path / "Mega Man 2 (USA).nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=media_dir,
            )

        assert result is not None
        assert result.thumbnail_path == media_dir / "covers" / "Mega Man 2 (USA).jpg"
        assert result.screenshot_path == media_dir / "screenshots" / "Mega Man 2 (USA).jpg"
        assert result.marquee_path is None   # not available from IGDB
        assert result.video_path is None     # not available from IGDB

    def test_media_paths_none_when_download_fails(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)

        result = _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "mm2.nes", tmp_path / "media",
        )

        assert result is not None
        assert result.thumbnail_path is None
        assert result.screenshot_path is None


# ---------------------------------------------------------------------------
# Token acquisition
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_token_stored_after_successful_auth(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(200, {"access_token": "my-token", "expires_in": 999})
        games_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)

        _search_with_mocks(
            src, token_resp, games_resp,
            tmp_path / "mm2.nes", tmp_path / "media",
        )

        assert src._access_token == "my-token"
        assert src._session.headers.get("Authorization") == "Bearer my-token"
        assert src._session.headers.get("Client-ID") == "test_id"

    def test_auth_failure_sets_login_failed(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(400)
        src._session.post = MagicMock(return_value=token_resp)

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

    def test_auth_missing_access_token_sets_login_failed(self, tmp_path: Path) -> None:
        src = _make_source()
        token_resp = _mock_response(200, {"status": "ok"})  # no access_token key
        src._session.post = MagicMock(return_value=token_resp)

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

    def test_auth_network_error_sets_login_failed(self, tmp_path: Path) -> None:
        src = _make_source()
        src._session.post = MagicMock(
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
        assert src._login_failed is True

    def test_login_failed_flag_prevents_retry(self, tmp_path: Path) -> None:
        """After login fails, _login_failed prevents another token request."""
        src = _make_source()
        src._session.post = MagicMock(
            return_value=_mock_response(401)
        )

        # First search triggers auth attempt
        src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        first_call_count = src._session.post.call_count

        # Second search must NOT attempt another token request
        src.search(
            rom_path=tmp_path / "sonic.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="cc", crc32="dd"),
            canonical_name="Sonic",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert src._session.post.call_count == first_call_count


# ---------------------------------------------------------------------------
# 401 during game search sets _login_failed
# ---------------------------------------------------------------------------


class TestGameSearch401:
    def test_401_on_game_search_sets_login_failed(self, tmp_path: Path) -> None:
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        src._session.post = MagicMock(return_value=_mock_response(401))

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
# HTTP error handling
# ---------------------------------------------------------------------------


class TestGameSearchErrors:
    def _with_token(self, src: IGDBSource) -> None:
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })

    def test_returns_none_on_500(self, tmp_path: Path) -> None:
        src = _make_source()
        self._with_token(src)
        src._session.post = MagicMock(return_value=_mock_response(500))
        result = src.search(
            rom_path=tmp_path / "mm2.nes",
            system_folder="nes",
            rom_hash=RomHash(md5="aa", crc32="bb"),
            canonical_name="Mega Man 2",
            cross_db_ids={},
            media_dir=tmp_path / "media",
        )
        assert result is None

    def test_returns_none_on_empty_results(self, tmp_path: Path) -> None:
        src = _make_source()
        self._with_token(src)
        src._session.post = MagicMock(return_value=_mock_response(200, []))
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
        src._session.post = MagicMock(
            side_effect=requests.ConnectionError("no net")
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

    def test_returns_none_on_json_error(self, tmp_path: Path) -> None:
        src = _make_source()
        self._with_token(src)
        bad_resp = MagicMock(spec=requests.Response)
        bad_resp.status_code = 200
        bad_resp.ok = True
        bad_resp.json.side_effect = ValueError("bad json")
        src._session.post = MagicMock(return_value=bad_resp)

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
# Platform filtering
# ---------------------------------------------------------------------------


class TestPlatformFiltering:
    def test_known_platforms_present_in_map(self) -> None:
        for folder in ("nes", "snes", "gb", "gba", "n64", "psx", "ps2", "psp"):
            assert folder in IGDB_PLATFORM_IDS, f"{folder!r} missing from IGDB_PLATFORM_IDS"

    def test_platform_filter_picks_matching_game(self, tmp_path: Path) -> None:
        """When multiple results, picks the one whose platforms include the system ID."""
        nes_game = dict(_CANNED_GAME)
        nes_game["platforms"] = [{"id": 18, "name": "NES"}]

        ps2_game = dict(_CANNED_GAME)
        ps2_game["name"] = "PS2 Version"
        ps2_game["platforms"] = [{"id": 8, "name": "PS2"}]

        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        # Return PS2 game first, NES game second — NES search should pick NES game
        src._session.post = MagicMock(
            return_value=_mock_response(200, [ps2_game, nes_game])
        )

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert result is not None
        assert result.name == "Mega Man 2"  # the NES game, not PS2 Version

    def test_unknown_platform_uses_first_result(self, tmp_path: Path) -> None:
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        src._session.post = MagicMock(
            return_value=_mock_response(200, _CANNED_GAMES_RESPONSE)
        )

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            result = src.search(
                rom_path=tmp_path / "game.bin",
                system_folder="unknownplatform_xyz",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Some Game",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert result is not None
        assert result.name == "Mega Man 2"


# ---------------------------------------------------------------------------
# Lookup by IGDB ID
# ---------------------------------------------------------------------------


class TestLookupByIgdbId:
    def test_uses_id_query_when_igdb_id_present(self, tmp_path: Path) -> None:
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })

        bodies_sent: list[str] = []

        def capture_post(url, data=None, **kwargs):
            if data:
                bodies_sent.append(data)
            return _mock_response(200, _CANNED_GAMES_RESPONSE)

        src._session.post = MagicMock(side_effect=capture_post)

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={"igdb_id": 1234},
                media_dir=tmp_path / "media",
            )

        assert any("where id = 1234" in b for b in bodies_sent)

    def test_uses_search_query_when_no_igdb_id(self, tmp_path: Path) -> None:
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })

        bodies_sent: list[str] = []

        def capture_post(url, data=None, **kwargs):
            if data:
                bodies_sent.append(data)
            return _mock_response(200, _CANNED_GAMES_RESPONSE)

        src._session.post = MagicMock(side_effect=capture_post)

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert any('search "Mega Man 2"' in b for b in bodies_sent)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_sleep_called_when_requests_too_fast(self, tmp_path: Path) -> None:
        src = _make_source()
        src._last_request_time = time.monotonic()

        token_resp = _mock_response(200, _CANNED_TOKEN_RESPONSE)
        games_resp = _mock_response(200, _CANNED_GAMES_RESPONSE)
        src._session.post = MagicMock(side_effect=[token_resp, games_resp])

        sleep_calls: list[float] = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("backend.scrapers.igdb.time.sleep", side_effect=fake_sleep):
            with patch("backend.scrapers.igdb._download_file", return_value=False):
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
# Credential scrubbing
# ---------------------------------------------------------------------------


class TestCredentialScrubbing:
    def test_client_secret_absent_from_logs_on_auth_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "super_secret_client_secret"
        src = IGDBSource(client_id="myid", client_secret=secret)

        exc_msg = f"ConnectionError: client_secret={secret}&grant_type=client_credentials"
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


# ---------------------------------------------------------------------------
# Partial game data (missing optional fields)
# ---------------------------------------------------------------------------


class TestPartialGameData:
    def test_missing_involved_companies_leaves_empty(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["involved_companies"] = None
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        src._session.post = MagicMock(return_value=_mock_response(200, [game]))

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert result is not None
        assert result.developer == ""
        assert result.publisher == ""

    def test_missing_cover_leaves_thumbnail_none(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["cover"] = None
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        src._session.post = MagicMock(return_value=_mock_response(200, [game]))

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert result is not None
        assert result.thumbnail_path is None

    def test_missing_first_release_date_leaves_empty(self, tmp_path: Path) -> None:
        game = dict(_CANNED_GAME)
        game["first_release_date"] = None
        src = _make_source()
        src._access_token = "pre-set"
        src._session.headers.update({
            "Client-ID": "test_id",
            "Authorization": "Bearer pre-set",
        })
        src._session.post = MagicMock(return_value=_mock_response(200, [game]))

        with patch("backend.scrapers.igdb._download_file", return_value=False):
            result = src.search(
                rom_path=tmp_path / "mm2.nes",
                system_folder="nes",
                rom_hash=RomHash(md5="aa", crc32="bb"),
                canonical_name="Mega Man 2",
                cross_db_ids={},
                media_dir=tmp_path / "media",
            )

        assert result is not None
        assert result.release_date == ""


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
    def test_build_sources_includes_igdb_when_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_igdb_build_sources__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()

        assert "igdb" in cfg.scraper_enabled_sources

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        igdb_sources = [s for s in sources if s.name == "igdb"]
        assert len(igdb_sources) == 1

    def test_build_sources_excludes_igdb_when_not_enabled(self) -> None:
        import json
        from unittest.mock import patch as upatch
        from backend.config import Config
        from backend.retro_scraper import RetroScraper

        cfg_file = Path("/tmp/__htpc_test_igdb_disabled__.json")
        cfg_file.write_text(json.dumps({}), encoding="utf-8")

        import backend.config as _cfg_mod
        with upatch.object(_cfg_mod, "CONFIG_FILE", cfg_file), \
             upatch.object(_cfg_mod, "CONFIG_DIR", Path("/tmp")):
            cfg = Config()
            cfg.set_scraper_enabled_sources([])

        scraper = RetroScraper(cfg)
        sources = scraper._build_sources()
        igdb_sources = [s for s in sources if s.name == "igdb"]
        assert len(igdb_sources) == 0
