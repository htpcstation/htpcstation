"""Tests for Task 002 — Steam metadata fetcher.

Covers:
  - fetch_steam_metadata: successful API response → correct GameMetadata fields
  - fetch_steam_metadata: API returns success=false → returns None
  - fetch_steam_metadata: network error → returns None
  - fetch_steam_metadata: missing optional fields (no metacritic, no categories) → graceful defaults
  - SteamLibrary.fetchMetadata: cached metadata in gamelist.xml → emits immediately, no API call
  - SteamLibrary.fetchMetadata: no cache → triggers API call and writes back to gamelist.xml
"""

from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.metadata_gamelist import GameMetadata, read_gamelist, write_game_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_response(app_id: str, data: dict, success: bool = True) -> bytes:
    """Build a minimal Steam Store API JSON response."""
    payload = {
        app_id: {
            "success": success,
            "data": data,
        }
    }
    return json.dumps(payload).encode("utf-8")


def _make_full_data() -> dict:
    """Return a realistic Steam Store API ``data`` object."""
    return {
        "name": "Half-Life 2",
        "short_description": "Set between the events of Half-Life and Half-Life 2.",
        "developers": ["Valve"],
        "publishers": ["Valve"],
        "genres": [
            {"id": "1", "description": "Action"},
            {"id": "25", "description": "Adventure"},
        ],
        "categories": [
            {"id": "2", "description": "Single-player"},
            {"id": "22", "description": "Steam Achievements"},
            {"id": "28", "description": "Full controller support"},
        ],
        "release_date": {"coming_soon": False, "date": "Nov 16, 2004"},
        "metacritic": {"score": 96, "url": "https://www.metacritic.com/game/half-life-2/"},
    }


def _make_urlopen_mock(response_bytes: bytes) -> MagicMock:
    """Return a mock suitable for use as ``urllib.request.urlopen`` context manager."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# fetch_steam_metadata — successful response
# ---------------------------------------------------------------------------


class TestFetchSteamMetadataSuccess:
    def test_name_field(self) -> None:
        """name is populated from data.name."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.name == "Half-Life 2"

    def test_app_id_field(self) -> None:
        """app_id is the input app_id string."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.app_id == "220"

    def test_description_field(self) -> None:
        """description is populated from data.short_description."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.description == "Set between the events of Half-Life and Half-Life 2."

    def test_developer_field_joined(self) -> None:
        """developer is developers list joined with ', '."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["developers"] = ["Valve", "Hidden Path Entertainment"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.developer == "Valve, Hidden Path Entertainment"

    def test_publisher_field_joined(self) -> None:
        """publisher is publishers list joined with ', '."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["publishers"] = ["Valve", "EA"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.publisher == "Valve, EA"

    def test_genre_field_joined(self) -> None:
        """genre is genres[*].description joined with ', '."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.genre == "Action, Adventure"

    def test_players_field_filters_known_categories(self) -> None:
        """players includes only known player category descriptions."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        # categories includes "Single-player" (known) and "Steam Achievements" (unknown)
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.players == "Single-player"

    def test_players_field_multiple_categories(self) -> None:
        """players joins multiple matched categories with ', '."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["categories"] = [
            {"id": "2", "description": "Single-player"},
            {"id": "1", "description": "Multi-player"},
            {"id": "9", "description": "Co-op"},
            {"id": "22", "description": "Steam Achievements"},  # not a player category
        ]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        # All three known categories should be present
        assert "Single-player" in result.players
        assert "Multi-player" in result.players
        assert "Co-op" in result.players
        # Unknown category should not be present
        assert "Steam Achievements" not in result.players

    def test_release_date_field(self) -> None:
        """release_date is populated from data.release_date.date."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.release_date == "Nov 16, 2004"

    def test_rating_from_metacritic(self) -> None:
        """rating is metacritic.score / 100."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["metacritic"] = {"score": 96}
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.rating == pytest.approx(0.96)

    def test_image_path_is_empty(self) -> None:
        """image_path is always empty — artwork is handled by the existing system."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.image_path == ""

    def test_returns_game_metadata_instance(self) -> None:
        """fetch_steam_metadata returns a GameMetadata instance on success."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert isinstance(result, GameMetadata)

    def test_uses_correct_url(self) -> None:
        """fetch_steam_metadata calls the correct Steam Store API URL."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("440", data))
        captured_requests = []

        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fetch_steam_metadata("440")

        assert len(captured_requests) == 1
        assert "440" in captured_requests[0].full_url
        assert "store.steampowered.com" in captured_requests[0].full_url

    def test_uses_correct_user_agent(self) -> None:
        """fetch_steam_metadata sends User-Agent: htpcstation/1.0."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        mock_resp = _make_urlopen_mock(_make_api_response("440", data))
        captured_requests = []

        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fetch_steam_metadata("440")

        assert len(captured_requests) == 1
        assert captured_requests[0].get_header("User-agent") == "htpcstation/1.0"


# ---------------------------------------------------------------------------
# fetch_steam_metadata — error cases
# ---------------------------------------------------------------------------


class TestFetchSteamMetadataErrors:
    def test_api_success_false_returns_none(self) -> None:
        """Returns None when the API returns success=false."""
        from backend.steam_metadata import fetch_steam_metadata

        mock_resp = _make_urlopen_mock(_make_api_response("99999", {}, success=False))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("99999")

        assert result is None

    def test_network_error_returns_none(self) -> None:
        """Returns None on URLError (network failure)."""
        from backend.steam_metadata import fetch_steam_metadata

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = fetch_steam_metadata("440")

        assert result is None

    def test_os_error_returns_none(self) -> None:
        """Returns None on OSError."""
        from backend.steam_metadata import fetch_steam_metadata

        with patch(
            "urllib.request.urlopen",
            side_effect=OSError("socket error"),
        ):
            result = fetch_steam_metadata("440")

        assert result is None

    def test_json_decode_error_returns_none(self) -> None:
        """Returns None when the response is not valid JSON."""
        from backend.steam_metadata import fetch_steam_metadata

        mock_resp = _make_urlopen_mock(b"not valid json {{{")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("440")

        assert result is None

    def test_missing_app_id_in_response_returns_none(self) -> None:
        """Returns None when the app_id key is absent from the response."""
        from backend.steam_metadata import fetch_steam_metadata

        # Response has a different app_id key
        payload = {"999": {"success": True, "data": _make_full_data()}}
        mock_resp = _make_urlopen_mock(json.dumps(payload).encode())
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("440")

        assert result is None

    def test_network_error_logs_warning(self, caplog) -> None:
        """A warning is logged on network error."""
        import logging
        from backend.steam_metadata import fetch_steam_metadata

        with caplog.at_level(logging.WARNING, logger="backend.steam_metadata"):
            with patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("timeout"),
            ):
                fetch_steam_metadata("440")

        assert any("440" in r.message for r in caplog.records)

    def test_api_failure_logs_warning(self, caplog) -> None:
        """A warning is logged when the API returns success=false."""
        import logging
        from backend.steam_metadata import fetch_steam_metadata

        mock_resp = _make_urlopen_mock(_make_api_response("440", {}, success=False))
        with caplog.at_level(logging.WARNING, logger="backend.steam_metadata"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                fetch_steam_metadata("440")

        assert any("440" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# fetch_steam_metadata — missing optional fields
# ---------------------------------------------------------------------------


class TestFetchSteamMetadataMissingFields:
    def test_no_metacritic_rating_defaults_to_zero(self) -> None:
        """rating defaults to 0.0 when metacritic is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["metacritic"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.rating == pytest.approx(0.0)

    def test_no_categories_players_is_empty(self) -> None:
        """players is empty string when categories is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["categories"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.players == ""

    def test_no_genres_genre_is_empty(self) -> None:
        """genre is empty string when genres is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["genres"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.genre == ""

    def test_no_developers_developer_is_empty(self) -> None:
        """developer is empty string when developers is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["developers"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.developer == ""

    def test_no_publishers_publisher_is_empty(self) -> None:
        """publisher is empty string when publishers is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["publishers"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.publisher == ""

    def test_no_release_date_is_empty(self) -> None:
        """release_date is empty string when release_date is absent."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        del data["release_date"]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.release_date == ""

    def test_empty_categories_list_players_is_empty(self) -> None:
        """players is empty string when categories list is empty."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["categories"] = []
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.players == ""

    def test_categories_with_no_known_player_types_players_is_empty(self) -> None:
        """players is empty when no categories match known player types."""
        from backend.steam_metadata import fetch_steam_metadata

        data = _make_full_data()
        data["categories"] = [
            {"id": "22", "description": "Steam Achievements"},
            {"id": "28", "description": "Full controller support"},
        ]
        mock_resp = _make_urlopen_mock(_make_api_response("220", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("220")

        assert result is not None
        assert result.players == ""

    def test_all_optional_fields_missing_returns_metadata(self) -> None:
        """fetch_steam_metadata returns a GameMetadata even with minimal data."""
        from backend.steam_metadata import fetch_steam_metadata

        data = {"name": "Minimal Game"}
        mock_resp = _make_urlopen_mock(_make_api_response("1", data))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_steam_metadata("1")

        assert result is not None
        assert result.name == "Minimal Game"
        assert result.app_id == "1"
        assert result.description == ""
        assert result.developer == ""
        assert result.publisher == ""
        assert result.genre == ""
        assert result.players == ""
        assert result.release_date == ""
        assert result.rating == pytest.approx(0.0)
        assert result.image_path == ""


# ---------------------------------------------------------------------------
# SteamLibrary.fetchMetadata — cache hit
# ---------------------------------------------------------------------------


class TestFetchMetadataCacheHit:
    def _make_lib(self, tmp_path: Path):
        """Create a SteamLibrary with get_steam_dir redirected to tmp_path."""
        from backend.steam_library import SteamLibrary

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_metadata.fetch_steam_metadata") as mock_fetch,
        ):
            lib = SteamLibrary()
        return lib

    def test_cached_metadata_emits_immediately(self, tmp_path: Path) -> None:
        """fetchMetadata emits metadataChanged immediately when cache has description."""
        from backend.steam_library import SteamLibrary

        # Write a gamelist.xml with a description for app 440
        metadata = GameMetadata(
            name="Team Fortress 2",
            app_id="440",
            description="A team-based multiplayer shooter.",
            developer="Valve",
            publisher="Valve",
            genre="Action",
            players="Multi-player",
            release_date="Oct 10, 2007",
            rating=0.92,
        )
        write_game_metadata(tmp_path, "440", metadata)

        emitted: list[tuple] = []

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
        ):
            lib = SteamLibrary()
            lib.metadataChanged.connect(lambda app_id, meta: emitted.append((app_id, meta)))

            with patch("backend.steam_metadata.fetch_steam_metadata") as mock_fetch:
                lib.fetchMetadata("440")
                # API should NOT be called
                mock_fetch.assert_not_called()

        assert len(emitted) == 1
        assert emitted[0][0] == "440"
        meta_dict = emitted[0][1]
        assert meta_dict["name"] == "Team Fortress 2"
        assert meta_dict["description"] == "A team-based multiplayer shooter."
        assert meta_dict["developer"] == "Valve"
        assert meta_dict["releaseDate"] == "Oct 10, 2007"
        assert meta_dict["rating"] == pytest.approx(0.92)

    def test_cached_metadata_dict_has_camel_case_keys(self, tmp_path: Path) -> None:
        """The emitted metadata dict uses camelCase keys for QML."""
        from backend.steam_library import SteamLibrary

        metadata = GameMetadata(
            name="Portal",
            app_id="400",
            description="A puzzle game.",
            release_date="Oct 9, 2007",
        )
        write_game_metadata(tmp_path, "400", metadata)

        emitted: list[dict] = []

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
        ):
            lib = SteamLibrary()
            lib.metadataChanged.connect(lambda app_id, meta: emitted.append(meta))

            with patch("backend.steam_metadata.fetch_steam_metadata"):
                lib.fetchMetadata("400")

        assert len(emitted) == 1
        meta = emitted[0]
        assert "appId" in meta
        assert "releaseDate" in meta
        assert "app_id" not in meta
        assert "release_date" not in meta

    def test_empty_description_triggers_api_call(self, tmp_path: Path) -> None:
        """fetchMetadata triggers an API call when cached entry has empty description."""
        from backend.steam_library import SteamLibrary

        # Write a gamelist.xml entry with NO description
        metadata = GameMetadata(name="Portal", app_id="400", description="")
        write_game_metadata(tmp_path, "400", metadata)

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata") as mock_fetch,
        ):
            mock_fetch.return_value = None  # fetch fails — that's fine for this test
            lib = SteamLibrary()
            lib.fetchMetadata("400")
            # Give the worker thread a moment to run
            time.sleep(0.3)
            mock_fetch.assert_called_once_with("400")

    def test_no_cache_entry_triggers_api_call(self, tmp_path: Path) -> None:
        """fetchMetadata triggers an API call when there is no cache entry at all."""
        from backend.steam_library import SteamLibrary

        # No gamelist.xml written — cache is empty
        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata") as mock_fetch,
        ):
            mock_fetch.return_value = None
            lib = SteamLibrary()
            lib.fetchMetadata("440")
            time.sleep(0.3)
            mock_fetch.assert_called_once_with("440")


# ---------------------------------------------------------------------------
# SteamLibrary.fetchMetadata — API call and write-back
# ---------------------------------------------------------------------------


class TestFetchMetadataApiCall:
    def test_successful_fetch_writes_to_gamelist(self, tmp_path: Path) -> None:
        """fetchMetadata writes fetched metadata to gamelist.xml."""
        from backend.steam_library import SteamLibrary
        from PySide6.QtCore import QCoreApplication

        fetched_metadata = GameMetadata(
            name="Half-Life 2",
            app_id="220",
            description="Set between the events of Half-Life and Half-Life 2.",
            developer="Valve",
            publisher="Valve",
            genre="Action",
            players="Single-player",
            release_date="Nov 16, 2004",
            rating=0.96,
        )

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata", return_value=fetched_metadata),
        ):
            lib = SteamLibrary()
            lib.fetchMetadata("220")
            # Wait for the worker thread to complete
            time.sleep(0.5)
            # Process pending Qt events so signals are delivered
            QCoreApplication.processEvents()

        # Verify gamelist.xml was written
        result = read_gamelist(tmp_path)
        assert "220" in result
        assert result["220"].name == "Half-Life 2"
        assert result["220"].description == "Set between the events of Half-Life and Half-Life 2."
        assert result["220"].developer == "Valve"

    def test_successful_fetch_emits_metadata_changed(self, tmp_path: Path) -> None:
        """fetchMetadata emits metadataChanged after a successful API fetch."""
        from backend.steam_library import SteamLibrary
        from PySide6.QtCore import QCoreApplication

        fetched_metadata = GameMetadata(
            name="Half-Life 2",
            app_id="220",
            description="A great game.",
            developer="Valve",
            publisher="Valve",
        )

        emitted: list[tuple] = []

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata", return_value=fetched_metadata),
        ):
            lib = SteamLibrary()
            lib.metadataChanged.connect(lambda app_id, meta: emitted.append((app_id, meta)))
            lib.fetchMetadata("220")
            time.sleep(0.5)
            QCoreApplication.processEvents()

        assert len(emitted) == 1
        assert emitted[0][0] == "220"
        assert emitted[0][1]["name"] == "Half-Life 2"

    def test_failed_fetch_does_not_emit_metadata_changed(self, tmp_path: Path) -> None:
        """fetchMetadata does not emit metadataChanged when the API fetch fails."""
        from backend.steam_library import SteamLibrary
        from PySide6.QtCore import QCoreApplication

        emitted: list[tuple] = []

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata", return_value=None),
        ):
            lib = SteamLibrary()
            lib.metadataChanged.connect(lambda app_id, meta: emitted.append((app_id, meta)))
            lib.fetchMetadata("440")
            time.sleep(0.5)
            QCoreApplication.processEvents()

        assert len(emitted) == 0

    def test_empty_app_id_is_noop(self, tmp_path: Path) -> None:
        """fetchMetadata with empty app_id does nothing."""
        from backend.steam_library import SteamLibrary

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
            patch("backend.steam_library.fetch_steam_metadata") as mock_fetch,
        ):
            mock_fetch.return_value = None
            lib = SteamLibrary()
            lib.fetchMetadata("")
            time.sleep(0.1)
            mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# SteamLibrary.getGame — metadata merge
# ---------------------------------------------------------------------------


class TestGetGameMetadataMerge:
    def test_get_game_includes_merged_metadata(self, tmp_path: Path) -> None:
        """getGame returns a dict with metadata fields merged from gamelist.xml."""
        from backend.steam_library import SteamLibrary
        from backend.steam_models import SteamGame

        # Seed gamelist.xml with metadata for app 220
        metadata = GameMetadata(
            name="Half-Life 2",
            app_id="220",
            description="Set between the events of Half-Life and Half-Life 2.",
            developer="Valve",
            publisher="Valve",
            genre="Action",
            players="Single-player",
            release_date="Nov 16, 2004",
            rating=0.96,
        )
        write_game_metadata(tmp_path, "220", metadata)

        game = SteamGame(
            app_id="220",
            name="Half-Life 2",
            install_dir="Half-Life 2",
            last_played=0,
            size_on_disk=0,
            image_path="",
        )

        with (
            patch("backend.steam_library.discover_steam_games", return_value=[game]),
            patch("backend.steam_library.get_steam_dir", return_value=tmp_path),
        ):
            lib = SteamLibrary()
            # refresh() is called in __init__; call again to ensure cache is loaded
            lib.refresh()
            result = lib.getGame(0)

        assert result["description"] == "Set between the events of Half-Life and Half-Life 2."
        assert result["developer"] == "Valve"
        assert result["publisher"] == "Valve"
        assert result["genre"] == "Action"
        assert result["players"] == "Single-player"
        assert result["releaseDate"] == "Nov 16, 2004"
        assert result["rating"] == pytest.approx(0.96)
