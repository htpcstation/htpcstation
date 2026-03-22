"""Tests for Task 015 — Plex Backend.

Covers:
  - PlexClient: correct URL construction, header injection, response parsing
  - PlexClient: graceful error handling (connection error, timeout, HTTP error)
  - PlexClient: library filtering (only movie/show types)
  - PlexClient: pagination parameters
  - plex_models: parse_movie, parse_show, parse_season, parse_episode
  - plex_models: genre/director/cast extraction, cast limited to 5
  - PosterCache: returns file:// URL for cached file
  - PosterCache: downloads and caches on first access
  - PosterCache: returns empty string on download failure
  - PosterCache: thread-safe (no duplicate downloads)
  - Config: plex_server_id, plex_user_id, and plex_token properties
  - Config: plex section loaded from JSON
  - Config: plex section saved to JSON
  - Config: backward compat with old server_url field
  - PlexLibraryListModel: roles and data
  - PlexMovieListModel: roles, data, append, poster update
  - PlexShowListModel: roles, data, poster update
  - PlexOnDeckModel: roles and data
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.plex_models import (
    PlexEpisode,
    PlexMovie,
    PlexSeason,
    PlexShow,
    parse_episode,
    parse_movie,
    parse_season,
    parse_show,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_FAKE_SERVER_RESOURCES = [
    {
        "clientIdentifier": "server123",
        "name": "Test Server",
        "owned": True,
        "provides": "server",
        "connections": [
            {
                "uri": "http://server:32400",
                "local": True,
                "relay": False,
                "protocol": "http",
            }
        ],
    }
]


def _make_plex_account_mock():
    """Return a MagicMock PlexAccount class whose instances return fake resources."""
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


# ---------------------------------------------------------------------------
# plex_models — parse_movie
# ---------------------------------------------------------------------------


class TestParseMovie:
    def test_basic_fields(self) -> None:
        data = {
            "ratingKey": "123",
            "title": "Test Movie",
            "year": 2020,
            "summary": "A test movie.",
            "contentRating": "PG-13",
            "audienceRating": 8.5,
            "duration": 7200000,
            "studio": "Test Studio",
            "tagline": "A tagline",
            "thumb": "/library/metadata/123/thumb/1",
            "art": "/library/metadata/123/art/1",
            "addedAt": 1700000000,
            "viewOffset": 60000,
        }
        movie = parse_movie(data)
        assert movie.rating_key == "123"
        assert movie.title == "Test Movie"
        assert movie.year == 2020
        assert movie.summary == "A test movie."
        assert movie.content_rating == "PG-13"
        assert movie.audience_rating == 8.5
        assert movie.duration_ms == 7200000
        assert movie.studio == "Test Studio"
        assert movie.tagline == "A tagline"
        assert movie.thumb_path == "/library/metadata/123/thumb/1"
        assert movie.art_path == "/library/metadata/123/art/1"
        assert movie.added_at == 1700000000
        assert movie.view_offset == 60000

    def test_genres_extracted(self) -> None:
        data = {
            "ratingKey": "1",
            "title": "Movie",
            "Genre": [{"tag": "Action"}, {"tag": "Comedy"}],
        }
        movie = parse_movie(data)
        assert movie.genres == ["Action", "Comedy"]

    def test_directors_extracted(self) -> None:
        data = {
            "ratingKey": "1",
            "title": "Movie",
            "Director": [{"tag": "Director A"}, {"tag": "Director B"}],
        }
        movie = parse_movie(data)
        assert movie.directors == ["Director A", "Director B"]

    def test_cast_limited_to_5(self) -> None:
        data = {
            "ratingKey": "1",
            "title": "Movie",
            "Role": [{"tag": f"Actor {i}"} for i in range(10)],
        }
        movie = parse_movie(data)
        assert len(movie.cast) == 5
        assert movie.cast == ["Actor 0", "Actor 1", "Actor 2", "Actor 3", "Actor 4"]

    def test_missing_optional_fields_use_defaults(self) -> None:
        data = {"ratingKey": "1", "title": "Minimal Movie"}
        movie = parse_movie(data)
        assert movie.year == 0
        assert movie.summary == ""
        assert movie.genres == []
        assert movie.directors == []
        assert movie.cast == []
        assert movie.poster_local == ""

    def test_none_values_handled(self) -> None:
        """None values in numeric fields should not raise."""
        data = {
            "ratingKey": "1",
            "title": "Movie",
            "year": None,
            "audienceRating": None,
            "duration": None,
            "addedAt": None,
            "viewOffset": None,
        }
        movie = parse_movie(data)
        assert movie.year == 0
        assert movie.audience_rating == 0.0
        assert movie.duration_ms == 0


# ---------------------------------------------------------------------------
# plex_models — parse_show
# ---------------------------------------------------------------------------


class TestParseShow:
    def test_basic_fields(self) -> None:
        data = {
            "ratingKey": "200",
            "title": "Test Show",
            "year": 2018,
            "summary": "A test show.",
            "contentRating": "TV-MA",
            "audienceRating": 9.0,
            "thumb": "/library/metadata/200/thumb/1",
            "art": "/library/metadata/200/art/1",
            "childCount": 3,
            "leafCount": 30,
            "viewedLeafCount": 15,
        }
        show = parse_show(data)
        assert show.rating_key == "200"
        assert show.title == "Test Show"
        assert show.year == 2018
        assert show.child_count == 3
        assert show.leaf_count == 30
        assert show.viewed_leaf_count == 15

    def test_cast_limited_to_5(self) -> None:
        data = {
            "ratingKey": "1",
            "title": "Show",
            "Role": [{"tag": f"Actor {i}"} for i in range(8)],
        }
        show = parse_show(data)
        assert len(show.cast) == 5


# ---------------------------------------------------------------------------
# plex_models — parse_season
# ---------------------------------------------------------------------------


class TestParseSeason:
    def test_basic_fields(self) -> None:
        data = {
            "ratingKey": "300",
            "title": "Season 1",
            "index": 1,
            "thumb": "/library/metadata/300/thumb/1",
            "leafCount": 10,
            "viewedLeafCount": 5,
            "parentRatingKey": "200",
        }
        season = parse_season(data)
        assert season.rating_key == "300"
        assert season.title == "Season 1"
        assert season.index == 1
        assert season.leaf_count == 10
        assert season.viewed_leaf_count == 5
        assert season.parent_rating_key == "200"


# ---------------------------------------------------------------------------
# plex_models — parse_episode
# ---------------------------------------------------------------------------


class TestParseEpisode:
    def test_basic_fields(self) -> None:
        data = {
            "ratingKey": "400",
            "title": "Pilot",
            "index": 1,
            "parentIndex": 1,
            "summary": "The first episode.",
            "thumb": "/library/metadata/400/thumb/1",
            "duration": 2700000,
            "viewOffset": 0,
            "viewCount": 1,
            "grandparentTitle": "Test Show",
        }
        episode = parse_episode(data)
        assert episode.rating_key == "400"
        assert episode.title == "Pilot"
        assert episode.index == 1
        assert episode.parent_index == 1
        assert episode.duration_ms == 2700000
        assert episode.grandparent_title == "Test Show"

    def test_viewed_when_view_count_positive_and_no_offset(self) -> None:
        data = {
            "ratingKey": "1",
            "title": "Ep",
            "viewCount": 1,
            "viewOffset": 0,
        }
        episode = parse_episode(data)
        assert episode.viewed is True

    def test_not_viewed_when_has_offset(self) -> None:
        """Episode with a viewOffset is in-progress, not fully viewed."""
        data = {
            "ratingKey": "1",
            "title": "Ep",
            "viewCount": 1,
            "viewOffset": 60000,
        }
        episode = parse_episode(data)
        assert episode.viewed is False

    def test_not_viewed_when_no_view_count(self) -> None:
        data = {"ratingKey": "1", "title": "Ep"}
        episode = parse_episode(data)
        assert episode.viewed is False


# ---------------------------------------------------------------------------
# PlexClient — URL construction and headers
# ---------------------------------------------------------------------------


class TestPlexClientUrlAndHeaders:
    def test_get_identity_calls_correct_url(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"machineIdentifier": "abc123"}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://192.168.0.2:32400", "mytoken")
            result = client.get_identity()

            mock_session.get.assert_called_once()
            call_url = mock_session.get.call_args[0][0]
            assert call_url == "http://192.168.0.2:32400/identity"
            assert result.get("machineIdentifier") == "abc123"

    def test_headers_set_on_session(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            PlexClient("http://server:32400", "tok123")

            mock_session.headers.update.assert_called_once_with(
                {"X-Plex-Token": "tok123", "Accept": "application/json"}
            )

    def test_trailing_slash_stripped_from_server_url(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400/", "tok")
            client.get_identity()

            call_url = mock_session.get.call_args[0][0]
            assert call_url == "http://server:32400/identity"

    def test_get_poster_url_builds_authenticated_url(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session"):
            client = PlexClient("http://server:32400", "mytoken")
            url = client.get_poster_url("/library/metadata/123/thumb/456")
            assert url == "http://server:32400/library/metadata/123/thumb/456?X-Plex-Token=mytoken"


# ---------------------------------------------------------------------------
# PlexClient — library filtering
# ---------------------------------------------------------------------------


class TestPlexClientLibraryFiltering:
    def _make_client_with_libraries(self, directories: list[dict]):
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"Directory": directories}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            # Patch the session on the already-created client
            client._session = mock_session
            return client

    def test_filters_to_movie_and_show_only(self) -> None:
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Movies", "type": "movie", "key": "1"},
            {"title": "TV Shows", "type": "show", "key": "2"},
            {"title": "Music", "type": "artist", "key": "3"},
            {"title": "Audiobooks", "type": "artist", "key": "4"},
        ]

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"Directory": directories}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            libs = client.get_libraries()

        assert len(libs) == 2
        types = {lib["type"] for lib in libs}
        assert types == {"movie", "show"}

    def test_empty_libraries_when_all_filtered(self) -> None:
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Music", "type": "artist", "key": "1"},
        ]

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"Directory": directories}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            libs = client.get_libraries()

        assert libs == []


# ---------------------------------------------------------------------------
# PlexClient — pagination
# ---------------------------------------------------------------------------


class TestPlexClientPagination:
    def test_pagination_params_sent(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [],
                    "totalSize": 100,
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            items, total = client.get_library_items("4", start=50, size=25)

            call_kwargs = mock_session.get.call_args[1]
            params = call_kwargs.get("params", {})
            assert params["X-Plex-Container-Start"] == 50
            assert params["X-Plex-Container-Size"] == 25
            assert total == 100

    def test_returns_empty_on_missing_metadata(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            items, total = client.get_library_items("4")

        assert items == []
        assert total == 0


# ---------------------------------------------------------------------------
# PlexClient — error handling
# ---------------------------------------------------------------------------


class TestPlexClientErrorHandling:
    def test_connection_error_returns_empty(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            result = client.get_identity()

        assert result == {}

    def test_timeout_returns_empty(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.Timeout()

            client = PlexClient("http://server:32400", "tok")
            result = client.get_identity()

        assert result == {}

    def test_http_error_returns_empty(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("401")
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_identity()

        assert result == {}

    def test_connection_error_returns_empty_libraries(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            libs = client.get_libraries()

        assert libs == []

    def test_connection_error_returns_empty_items(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            items, total = client.get_library_items("4")

        assert items == []
        assert total == 0


# ---------------------------------------------------------------------------
# PosterCache
# ---------------------------------------------------------------------------


class TestPosterCache:
    def test_returns_file_url_for_cached_file(self, tmp_path: Path) -> None:
        from backend.poster_cache import PosterCache
        import hashlib

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/123/thumb/456"
        digest = hashlib.sha256(thumb_path.encode()).hexdigest()
        cached_file = tmp_path / f"{digest}.jpg"
        cached_file.write_bytes(b"fake image data")

        mock_client = MagicMock()
        result = cache.get_poster(mock_client, thumb_path)

        assert result == cached_file.as_uri()
        mock_client.get_poster_url.assert_not_called()

    def test_downloads_and_caches_on_first_access(self, tmp_path: Path) -> None:
        import requests as req
        from backend.poster_cache import PosterCache
        import hashlib

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/123/thumb/456"
        digest = hashlib.sha256(thumb_path.encode()).hexdigest()
        expected_path = tmp_path / f"{digest}.jpg"

        mock_client = MagicMock()
        mock_client.get_poster_url.return_value = "http://server/thumb?token=abc"

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"fake", b"image"]
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("backend.poster_cache.requests.get", return_value=mock_response):
            result = cache.get_poster(mock_client, thumb_path)

        assert result == expected_path.as_uri()
        assert expected_path.exists()

    def test_returns_empty_string_on_download_failure(self, tmp_path: Path) -> None:
        import requests as req
        from backend.poster_cache import PosterCache

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/123/thumb/456"

        mock_client = MagicMock()
        mock_client.get_poster_url.return_value = "http://server/thumb"

        with patch("backend.poster_cache.requests.get") as mock_get:
            mock_get.side_effect = req.exceptions.ConnectionError("refused")
            result = cache.get_poster(mock_client, thumb_path)

        assert result == ""

    def test_returns_empty_string_for_empty_thumb_path(self, tmp_path: Path) -> None:
        from backend.poster_cache import PosterCache

        cache = PosterCache(tmp_path)
        mock_client = MagicMock()
        result = cache.get_poster(mock_client, "")
        assert result == ""
        mock_client.get_poster_url.assert_not_called()

    def test_cache_path_is_deterministic(self, tmp_path: Path) -> None:
        from backend.poster_cache import PosterCache
        import hashlib

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/999/thumb/111"
        path1 = cache._cache_path(thumb_path)
        path2 = cache._cache_path(thumb_path)
        assert path1 == path2

        digest = hashlib.sha256(thumb_path.encode()).hexdigest()
        assert path1 == tmp_path / f"{digest}.jpg"

    def test_no_duplicate_download_under_concurrent_access(self, tmp_path: Path) -> None:
        """Two threads requesting the same poster should only download once.

        The per-path lock in PosterCache ensures that when two threads race to
        download the same poster, only one actually performs the download.
        """
        import requests as req
        from backend.poster_cache import PosterCache

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/123/thumb/456"
        download_count = [0]
        lock = threading.Lock()

        mock_client = MagicMock()
        mock_client.get_poster_url.return_value = "http://server/thumb"

        def fake_download(url, stream, timeout):
            with lock:
                download_count[0] += 1
            mock_response = MagicMock()
            mock_response.iter_content.return_value = [b"data"]
            mock_response.raise_for_status = MagicMock()
            return mock_response

        results = []
        results_lock = threading.Lock()

        with patch("backend.poster_cache.requests.get", side_effect=fake_download):
            def fetch():
                r = cache.get_poster(mock_client, thumb_path)
                with results_lock:
                    results.append(r)

            t1 = threading.Thread(target=fetch)
            t2 = threading.Thread(target=fetch)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        # Both should return a valid URL
        assert len(results) == 2
        assert all(r != "" for r in results)
        # Only one download should have occurred (second thread sees cached file)
        assert download_count[0] == 1


# ---------------------------------------------------------------------------
# Config — plex properties
# ---------------------------------------------------------------------------


class TestConfigPlexProperties:
    def test_plex_token_loaded_from_json(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "tok123", "server_id": "abc123", "user_id": 42}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.plex_token == "tok123"
        assert config.plex_server_id == "abc123"
        assert config.plex_user_id == 42

    def test_plex_defaults_to_none_when_not_in_config(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.plex_token is None
        assert config.plex_server_id is None
        assert config.plex_user_id is None

    def test_plex_empty_string_treated_as_none(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "", "server_id": "", "user_id": 0}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        assert config.plex_token is None
        assert config.plex_server_id is None
        assert config.plex_user_id is None

    def test_plex_section_saved_to_json(self, tmp_path: Path) -> None:
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"token": "abc", "server_id": "srv1", "user_id": 7}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert "plex" in saved
        assert saved["plex"]["token"] == "abc"
        assert saved["plex"]["server_id"] == "srv1"
        assert saved["plex"]["user_id"] == 7

    def test_old_config_with_server_url_does_not_crash(self, tmp_path: Path) -> None:
        """Backward compat: old config files with server_url field load without error."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"plex": {"server_url": "http://192.168.0.2:32400", "token": "tok"}}),
            encoding="utf-8",
        )

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        # Old server_url is ignored; token is still loaded
        assert config.plex_token == "tok"
        assert config.plex_server_id is None

    def test_plex_server_id_and_user_id_persistence(self, tmp_path: Path) -> None:
        """set_plex_server_id and set_plex_user_id persist to config file."""
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_server_id("machine-abc")
            config.set_plex_user_id(99)

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["server_id"] == "machine-abc"
        assert saved["plex"]["user_id"] == 99


# ---------------------------------------------------------------------------
# PlexLibraryListModel
# ---------------------------------------------------------------------------


class TestPlexLibraryListModel:
    def test_roles_and_data(self) -> None:
        from backend.plex_library import PlexLibraryListModel
        from PySide6.QtCore import QModelIndex, Qt

        model = PlexLibraryListModel()
        model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
            {"title": "TV Shows", "type": "show", "key": "3"},
        ])

        assert model.rowCount() == 2

        idx = model.index(0, 0)
        assert model.data(idx, PlexLibraryListModel.TitleRole) == "Movies"
        assert model.data(idx, PlexLibraryListModel.TypeRole) == "movie"
        assert model.data(idx, PlexLibraryListModel.SectionKeyRole) == "4"

        idx2 = model.index(1, 0)
        assert model.data(idx2, PlexLibraryListModel.TitleRole) == "TV Shows"

    def test_role_names(self) -> None:
        from backend.plex_library import PlexLibraryListModel

        model = PlexLibraryListModel()
        names = model.roleNames()
        assert b"title" in names.values()
        assert b"type" in names.values()
        assert b"sectionKey" in names.values()

    def test_invalid_index_returns_none(self) -> None:
        from backend.plex_library import PlexLibraryListModel
        from PySide6.QtCore import QModelIndex

        model = PlexLibraryListModel()
        assert model.data(QModelIndex(), PlexLibraryListModel.TitleRole) is None


# ---------------------------------------------------------------------------
# PlexMovieListModel
# ---------------------------------------------------------------------------


class TestPlexMovieListModel:
    def _make_movie(self, rating_key: str = "1", title: str = "Test Movie") -> PlexMovie:
        return PlexMovie(
            rating_key=rating_key,
            title=title,
            year=2020,
            audience_rating=8.0,
            duration_ms=7200000,
            summary="A movie.",
            thumb_path="/thumb/1",
        )

    def test_roles_and_data(self) -> None:
        from backend.plex_library import PlexMovieListModel

        model = PlexMovieListModel()
        movie = self._make_movie("42", "My Movie")
        model.set_movies([movie])

        idx = model.index(0, 0)
        assert model.data(idx, PlexMovieListModel.RatingKeyRole) == "42"
        assert model.data(idx, PlexMovieListModel.TitleRole) == "My Movie"
        assert model.data(idx, PlexMovieListModel.YearRole) == 2020
        assert model.data(idx, PlexMovieListModel.AudienceRatingRole) == 8.0
        assert model.data(idx, PlexMovieListModel.DurationRole) == 7200000
        assert model.data(idx, PlexMovieListModel.SummaryRole) == "A movie."

    def test_append_movies(self) -> None:
        from backend.plex_library import PlexMovieListModel

        model = PlexMovieListModel()
        model.set_movies([self._make_movie("1", "First")])
        model.append_movies([self._make_movie("2", "Second")])

        assert model.rowCount() == 2
        idx = model.index(1, 0)
        assert model.data(idx, PlexMovieListModel.TitleRole) == "Second"

    def test_notify_poster_changed_emits_data_changed(self) -> None:
        from backend.plex_library import PlexMovieListModel

        model = PlexMovieListModel()
        model.set_movies([self._make_movie()])

        received = []
        model.dataChanged.connect(lambda tl, br, roles: received.append(roles))

        model.notify_poster_changed(0)

        assert len(received) == 1
        assert PlexMovieListModel.PosterLocalRole in received[0]

    def test_poster_local_role_returns_updated_value(self) -> None:
        from backend.plex_library import PlexMovieListModel

        model = PlexMovieListModel()
        movie = self._make_movie()
        model.set_movies([movie])

        movie.poster_local = "file:///tmp/poster.jpg"
        idx = model.index(0, 0)
        assert model.data(idx, PlexMovieListModel.PosterLocalRole) == "file:///tmp/poster.jpg"


# ---------------------------------------------------------------------------
# PlexShowListModel
# ---------------------------------------------------------------------------


class TestPlexShowListModel:
    def _make_show(self, rating_key: str = "1", title: str = "Test Show") -> PlexShow:
        return PlexShow(
            rating_key=rating_key,
            title=title,
            year=2019,
            audience_rating=9.0,
            child_count=3,
            leaf_count=30,
            viewed_leaf_count=10,
        )

    def test_roles_and_data(self) -> None:
        from backend.plex_library import PlexShowListModel

        model = PlexShowListModel()
        show = self._make_show("99", "My Show")
        model.set_shows([show])

        idx = model.index(0, 0)
        assert model.data(idx, PlexShowListModel.RatingKeyRole) == "99"
        assert model.data(idx, PlexShowListModel.TitleRole) == "My Show"
        assert model.data(idx, PlexShowListModel.YearRole) == 2019
        assert model.data(idx, PlexShowListModel.ChildCountRole) == 3
        assert model.data(idx, PlexShowListModel.LeafCountRole) == 30
        assert model.data(idx, PlexShowListModel.ViewedLeafCountRole) == 10

    def test_notify_poster_changed(self) -> None:
        from backend.plex_library import PlexShowListModel

        model = PlexShowListModel()
        model.set_shows([self._make_show()])

        received = []
        model.dataChanged.connect(lambda tl, br, roles: received.append(roles))
        model.notify_poster_changed(0)

        assert len(received) == 1
        assert PlexShowListModel.PosterLocalRole in received[0]


# ---------------------------------------------------------------------------
# PlexOnDeckModel
# ---------------------------------------------------------------------------


class TestPlexOnDeckModel:
    def _make_item(self) -> dict:
        return {
            "rating_key": "500",
            "title": "Episode 1",
            "type": "episode",
            "poster_local": "",
            "grandparent_title": "My Show",
            "view_offset": 120000,
            "duration": 2700000,
            "thumb_path": "/thumb/500",
        }

    def test_roles_and_data(self) -> None:
        from backend.plex_library import PlexOnDeckModel

        model = PlexOnDeckModel()
        model.set_items([self._make_item()])

        idx = model.index(0, 0)
        assert model.data(idx, PlexOnDeckModel.RatingKeyRole) == "500"
        assert model.data(idx, PlexOnDeckModel.TitleRole) == "Episode 1"
        assert model.data(idx, PlexOnDeckModel.TypeRole) == "episode"
        assert model.data(idx, PlexOnDeckModel.GrandparentTitleRole) == "My Show"
        assert model.data(idx, PlexOnDeckModel.ViewOffsetRole) == 120000
        assert model.data(idx, PlexOnDeckModel.DurationRole) == 2700000

    def test_notify_poster_changed(self) -> None:
        from backend.plex_library import PlexOnDeckModel

        model = PlexOnDeckModel()
        model.set_items([self._make_item()])

        received = []
        model.dataChanged.connect(lambda tl, br, roles: received.append(roles))
        model.notify_poster_changed(0)

        assert len(received) == 1
        assert PlexOnDeckModel.PosterLocalRole in received[0]


# ---------------------------------------------------------------------------
# PlexLibrary — loadMoreMovies duplicate guard
# ---------------------------------------------------------------------------


class TestLoadMoreMoviesGuard:
    """Verify that concurrent calls to loadMoreMovies do not submit duplicate
    worker tasks while a load is already in flight."""

    def test_loading_more_flag_prevents_duplicate_submission(self) -> None:
        """Second call to loadMoreMovies while _loading_more is True is a no-op."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from unittest.mock import patch, MagicMock

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None

            lib = PlexLibrary(config)
            # Simulate state: one page already loaded, more available
            lib._movies_total = 100
            lib._movies_loaded = 50
            lib._current_section_key = "4"

            submit_calls: list = []
            lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

            # First call — should submit
            lib.loadMoreMovies()
            assert lib._loading_more is True
            assert len(submit_calls) == 1

            # Second call while flag is set — should be a no-op
            lib.loadMoreMovies()
            assert len(submit_calls) == 1  # still only one submission

    def test_loading_more_flag_cleared_after_movies_ready(self) -> None:
        """_loading_more is reset to False when _on_movies_ready is called."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from unittest.mock import patch, MagicMock
        from backend.plex_models import PlexMovie

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None

            lib = PlexLibrary(config)
            lib._loading_more = True
            lib._movies_loaded = 0
            lib._client = None  # prevent poster fetch attempts

            movie = PlexMovie(rating_key="1", title="Test", year=2020)
            lib._on_movies_ready([movie], 1)

            assert lib._loading_more is False


# ---------------------------------------------------------------------------
# PosterCache — response closed via context manager
# ---------------------------------------------------------------------------


class TestPosterCacheResponseClose:
    def test_response_context_manager_exit_called(self, tmp_path: Path) -> None:
        """Verify that the response's __exit__ is called (context manager used)."""
        from backend.poster_cache import PosterCache

        cache = PosterCache(tmp_path)
        thumb_path = "/library/metadata/999/thumb/1"

        mock_client = MagicMock()
        mock_client.get_poster_url.return_value = "http://server/thumb"

        exit_called = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                exit_called.append(True)
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=8192):
                return [b"data"]

        with patch("backend.poster_cache.requests.get", return_value=FakeResponse()):
            cache.get_poster(mock_client, thumb_path)

        assert exit_called, "__exit__ was never called — response was not closed"


# ---------------------------------------------------------------------------
# PlexLibrary.getLibraryList — Fix 1 (016a)
# ---------------------------------------------------------------------------


class TestGetLibraryList:
    """getLibraryList() returns a JS-friendly list of dicts for QML."""

    def _make_lib(self, **kwargs):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_empty_when_no_data(self) -> None:
        lib = self._make_lib()
        result = lib.getLibraryList()
        assert result == []

    def test_libraries_only_no_ondeck(self) -> None:
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
            {"title": "TV Shows", "type": "show", "key": "3"},
        ])
        result = lib.getLibraryList()
        assert len(result) == 2
        assert result[0]["title"] == "Movies"
        assert result[0]["type"] == "movie"
        assert result[0]["sectionKey"] == "4"
        assert result[1]["title"] == "TV Shows"
        assert result[1]["sectionKey"] == "3"

    def test_ondeck_prepended_when_items_present(self) -> None:
        lib = self._make_lib()
        lib._on_deck_model.set_items([
            {"rating_key": "1", "title": "Ep 1", "type": "episode",
             "poster_local": "", "grandparent_title": "Show",
             "view_offset": 0, "duration": 1000, "thumb_path": ""},
        ])
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])
        result = lib.getLibraryList()
        assert len(result) == 2
        assert result[0]["title"] == "Continue Watching"
        assert result[0]["type"] == "ondeck"
        assert result[0]["sectionKey"] == "_ondeck"
        assert result[0]["count"] == 1
        assert result[1]["title"] == "Movies"

    def test_ondeck_not_prepended_when_empty(self) -> None:
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])
        result = lib.getLibraryList()
        assert len(result) == 1
        assert result[0]["title"] == "Movies"

    def test_section_key_is_string(self) -> None:
        """sectionKey must be a string even when the raw key is an int."""
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": 4},
        ])
        result = lib.getLibraryList()
        assert isinstance(result[0]["sectionKey"], str)
        assert result[0]["sectionKey"] == "4"


# ---------------------------------------------------------------------------
# PlexLibrary.serverUrl — Fix 6 (016a)
# ---------------------------------------------------------------------------


class TestServerUrlProperty:
    def test_server_url_exposed(self) -> None:
        """serverUrl returns the resolved URL after _setup_client succeeds."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {"uri": "http://192.168.0.2:32400", "local": True, "relay": False, "protocol": "http"},
                ],
            }
        ]

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", return_value=mock_account), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)

        assert lib.serverUrl == "http://192.168.0.2:32400"

    def test_server_url_empty_when_not_configured(self) -> None:
        """serverUrl is empty when no token is configured."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = None
            config.plex_token = None
            config.plex_user_id = None
            lib = PlexLibrary(config)

        assert lib.serverUrl == ""


# ---------------------------------------------------------------------------
# PlexLibrary._worker_load_more_movies — Fix 5 (016a)
# ---------------------------------------------------------------------------


class TestLoadMoreMoviesFailureResetsFlag:
    """_loading_more must be reset to False when _worker_load_more_movies fails."""

    def test_loading_more_reset_on_exception(self) -> None:
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)

        lib._loading_more = True

        mock_client = MagicMock()
        mock_client.get_library_items.side_effect = RuntimeError("network error")

        # Run the worker directly (synchronously) to test the failure path.
        lib._worker_load_more_movies(mock_client, "4", 0)

        assert lib._loading_more is False


# ---------------------------------------------------------------------------
# PlexLibrary.getShow — Task 018
# ---------------------------------------------------------------------------


class TestGetShow:
    """getShow() returns a dict with show metadata for QML consumption."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_returns_show_dict_with_expected_keys(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "200",
            "title": "Test Show",
            "year": 2018,
            "summary": "A great show.",
            "contentRating": "TV-MA",
            "audienceRating": 9.0,
            "childCount": 3,
            "leafCount": 30,
            "viewedLeafCount": 15,
            "Genre": [{"tag": "Drama"}, {"tag": "Sci-Fi"}],
            "Role": [{"tag": "Actor A"}, {"tag": "Actor B"}],
        }
        lib._client = mock_client

        result = lib.getShow("200")

        assert result["ratingKey"] == "200"
        assert result["title"] == "Test Show"
        assert result["year"] == 2018
        assert result["summary"] == "A great show."
        assert result["contentRating"] == "TV-MA"
        assert result["audienceRating"] == 9.0
        assert result["childCount"] == 3
        assert result["leafCount"] == 30
        assert result["viewedLeafCount"] == 15
        assert result["genres"] == ["Drama", "Sci-Fi"]
        assert result["cast"] == ["Actor A", "Actor B"]

    def test_returns_empty_dict_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        result = lib.getShow("200")
        assert result == {}

    def test_returns_empty_dict_when_metadata_not_found(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = None
        lib._client = mock_client
        result = lib.getShow("999")
        assert result == {}


# ---------------------------------------------------------------------------
# PlexLibrary.getSeasons — Task 018
# ---------------------------------------------------------------------------


class TestGetSeasons:
    """getSeasons() returns a list of season dicts for QML consumption."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_returns_season_list(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "season",
                "ratingKey": "300",
                "title": "Season 1",
                "index": 1,
                "leafCount": 8,
                "viewedLeafCount": 5,
                "parentRatingKey": "200",
            },
            {
                "type": "season",
                "ratingKey": "301",
                "title": "Season 2",
                "index": 2,
                "leafCount": 8,
                "viewedLeafCount": 0,
                "parentRatingKey": "200",
            },
        ]
        lib._client = mock_client

        result = lib.getSeasons("200")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "300"
        assert result[0]["title"] == "Season 1"
        assert result[0]["index"] == 1
        assert result[0]["leafCount"] == 8
        assert result[0]["viewedLeafCount"] == 5
        assert result[0]["parentRatingKey"] == "200"
        assert result[1]["ratingKey"] == "301"
        assert result[1]["index"] == 2

    def test_filters_out_non_season_items(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "season", "ratingKey": "300", "title": "Season 1", "index": 1},
            {"type": "episode", "ratingKey": "400", "title": "Pilot"},
        ]
        lib._client = mock_client

        result = lib.getSeasons("200")

        assert len(result) == 1
        assert result[0]["ratingKey"] == "300"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        result = lib.getSeasons("200")
        assert result == []

    def test_returns_empty_list_when_no_children(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = []
        lib._client = mock_client
        result = lib.getSeasons("200")
        assert result == []


# ---------------------------------------------------------------------------
# PlexLibrary.getEpisodes — Task 018
# ---------------------------------------------------------------------------


class TestGetEpisodes:
    """getEpisodes() returns a list of episode dicts for QML consumption."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_returns_episode_list(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "episode",
                "ratingKey": "400",
                "title": "Pilot",
                "index": 1,
                "parentIndex": 1,
                "summary": "The first episode.",
                "duration": 2700000,
                "viewOffset": 0,
                "viewCount": 1,
                "grandparentTitle": "Test Show",
            },
            {
                "type": "episode",
                "ratingKey": "401",
                "title": "The Signal",
                "index": 2,
                "parentIndex": 1,
                "summary": "Second episode.",
                "duration": 2520000,
                "viewOffset": 60000,
                "viewCount": 0,
                "grandparentTitle": "Test Show",
            },
        ]
        lib._client = mock_client

        result = lib.getEpisodes("300")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "400"
        assert result[0]["title"] == "Pilot"
        assert result[0]["index"] == 1
        assert result[0]["parentIndex"] == 1
        assert result[0]["duration"] == 2700000
        assert result[0]["viewOffset"] == 0
        assert result[0]["viewed"] is True
        assert result[0]["grandparentTitle"] == "Test Show"

        # In-progress episode
        assert result[1]["ratingKey"] == "401"
        assert result[1]["viewOffset"] == 60000
        assert result[1]["viewed"] is False

    def test_filters_out_non_episode_items(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "episode", "ratingKey": "400", "title": "Pilot", "index": 1},
            {"type": "season", "ratingKey": "300", "title": "Season 1"},
        ]
        lib._client = mock_client

        result = lib.getEpisodes("300")

        assert len(result) == 1
        assert result[0]["ratingKey"] == "400"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        result = lib.getEpisodes("300")
        assert result == []

    def test_watched_indicator_fields_present(self) -> None:
        """All episode dicts must have 'viewed' and 'viewOffset' for QML watched indicators."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "episode", "ratingKey": "400", "title": "Ep"},
        ]
        lib._client = mock_client

        result = lib.getEpisodes("300")

        assert len(result) == 1
        assert "viewed" in result[0]
        assert "viewOffset" in result[0]


# ---------------------------------------------------------------------------
# PlexLibrary.selectLibrary — _ondeck early return (Fix 1, Task 020)
# ---------------------------------------------------------------------------


class TestSelectLibraryOnDeckGuard:
    """selectLibrary('_ondeck') must not submit a worker to fetch library items."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_ondeck_does_not_submit_worker(self) -> None:
        """Calling selectLibrary('_ondeck') must not submit a network worker."""
        lib = self._make_lib()

        submit_calls: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

        lib.selectLibrary("_ondeck")

        assert len(submit_calls) == 0, "No worker should be submitted for _ondeck"

    def test_ondeck_sets_current_library_to_continue_watching(self) -> None:
        """selectLibrary('_ondeck') sets currentLibrary to 'Continue Watching'."""
        lib = self._make_lib()

        emitted: list[str] = []
        lib.currentLibraryChanged.connect(lambda title: emitted.append(title))

        lib.selectLibrary("_ondeck")

        assert lib._current_section_key == "_ondeck"
        assert lib._current_section_type == "ondeck"
        assert lib._current_library == "Continue Watching"
        assert emitted == ["Continue Watching"]

    def test_ondeck_does_not_reset_movies_state(self) -> None:
        """selectLibrary('_ondeck') must not reset _movies_loaded/_movies_total."""
        lib = self._make_lib()
        lib._movies_loaded = 50
        lib._movies_total = 200

        lib.selectLibrary("_ondeck")

        # State should be unchanged — the movies library is still intact
        assert lib._movies_loaded == 50
        assert lib._movies_total == 200


# ---------------------------------------------------------------------------
# PlexLibrary.getMovie — poster caching (Task 023)
# ---------------------------------------------------------------------------


class TestGetMoviePosterCaching:
    """getMovie() must populate posterLocal via the poster cache."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_poster_local_populated_when_thumb_path_present(self) -> None:
        """posterLocal in the returned dict reflects the cached file URL."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "123",
            "title": "Test Movie",
            "thumb": "/library/metadata/123/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster_cache/abc.jpg"
        lib._poster_cache = mock_cache

        result = lib.getMovie("123")

        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/123/thumb/1"
        )
        assert result["posterLocal"] == "file:///tmp/poster_cache/abc.jpg"

    def test_poster_local_empty_when_no_thumb_path(self) -> None:
        """posterLocal stays empty when the item has no thumb_path."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "124",
            "title": "No Thumb Movie",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        lib._poster_cache = mock_cache

        result = lib.getMovie("124")

        mock_cache.get_poster.assert_not_called()
        assert result["posterLocal"] == ""

    def test_poster_cache_not_called_when_cache_is_none(self) -> None:
        """No error and posterLocal is empty when _poster_cache is None."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "125",
            "title": "Movie",
            "thumb": "/library/metadata/125/thumb/1",
        }
        lib._client = mock_client
        lib._poster_cache = None

        result = lib.getMovie("125")

        assert result["posterLocal"] == ""


# ---------------------------------------------------------------------------
# PlexLibrary.getShow — poster caching (Task 023)
# ---------------------------------------------------------------------------


class TestGetShowPosterCaching:
    """getShow() must populate posterLocal via the poster cache."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_poster_local_populated_when_thumb_path_present(self) -> None:
        """posterLocal in the returned dict reflects the cached file URL."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "200",
            "title": "Test Show",
            "thumb": "/library/metadata/200/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster_cache/def.jpg"
        lib._poster_cache = mock_cache

        result = lib.getShow("200")

        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/200/thumb/1"
        )
        assert result["posterLocal"] == "file:///tmp/poster_cache/def.jpg"

    def test_poster_local_empty_when_no_thumb_path(self) -> None:
        """posterLocal stays empty when the show has no thumb_path."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "201",
            "title": "No Thumb Show",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        lib._poster_cache = mock_cache

        result = lib.getShow("201")

        mock_cache.get_poster.assert_not_called()
        assert result["posterLocal"] == ""

    def test_poster_cache_not_called_when_cache_is_none(self) -> None:
        """No error and posterLocal is empty when _poster_cache is None."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "202",
            "title": "Show",
            "thumb": "/library/metadata/202/thumb/1",
        }
        lib._client = mock_client
        lib._poster_cache = None

        result = lib.getShow("202")

        assert result["posterLocal"] == ""


# ---------------------------------------------------------------------------
# PlexClient.get_library_items — sort and genre params (Task 022)
# ---------------------------------------------------------------------------


class TestPlexClientSortAndGenreParams:
    """get_library_items passes sort and genre query params to the API."""

    def _make_client_with_session(self, response_data: dict):
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = response_data
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            client._session = mock_session
        return client, mock_session

    def test_sort_param_sent_when_provided(self) -> None:
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", sort="titleSort:asc")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("sort") == "titleSort:asc"

    def test_genre_param_sent_when_provided(self) -> None:
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", genre="42")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("genre") == "42"

    def test_sort_and_genre_both_sent(self) -> None:
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", sort="addedAt:desc", genre="7")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("sort") == "addedAt:desc"
        assert params.get("genre") == "7"

    def test_sort_not_sent_when_empty(self) -> None:
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", sort="")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert "sort" not in params

    def test_genre_not_sent_when_empty(self) -> None:
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", genre="")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert "genre" not in params


# ---------------------------------------------------------------------------
# PlexClient.get_genres (Task 022)
# ---------------------------------------------------------------------------


class TestPlexClientGetGenres:
    """get_genres returns a list of {key, title} dicts."""

    def test_returns_genre_list(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Directory": [
                        {"key": "1", "title": "Action"},
                        {"key": "2", "title": "Comedy"},
                        {"key": "3", "title": "Drama"},
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            genres = client.get_genres("4")

        assert len(genres) == 3
        assert genres[0] == {"key": "1", "title": "Action"}
        assert genres[1] == {"key": "2", "title": "Comedy"}
        assert genres[2] == {"key": "3", "title": "Drama"}

    def test_calls_correct_endpoint(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {"Directory": []}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            client.get_genres("4")

        call_url = mock_session.get.call_args[0][0]
        assert call_url == "http://server:32400/library/sections/4/genre"

    def test_returns_empty_on_connection_error(self) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            genres = client.get_genres("4")

        assert genres == []

    def test_key_converted_to_string(self) -> None:
        """Genre keys from the API should be returned as strings."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Directory": [
                        {"key": 42, "title": "Action"},  # integer key
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            genres = client.get_genres("4")

        assert genres[0]["key"] == "42"
        assert isinstance(genres[0]["key"], str)


# ---------------------------------------------------------------------------
# PlexLibrary.sortMovies (Task 022)
# ---------------------------------------------------------------------------


class TestSortMovies:
    """sortMovies re-fetches with the correct Plex API sort param."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_sort_az_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("az")

        assert lib._current_sort == "titleSort:asc"
        assert len(submitted) == 1
        # sort param passed to worker
        assert "titleSort:asc" in submitted[0][1]

    def test_sort_za_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("za")

        assert lib._current_sort == "titleSort:desc"

    def test_sort_recent_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("recent")

        assert lib._current_sort == "addedAt:desc"

    def test_sort_year_desc_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("year_desc")

        assert lib._current_sort == "year:desc"

    def test_sort_rating_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("rating")

        assert lib._current_sort == "audienceRating:desc"

    def test_sort_resets_pagination(self) -> None:
        """sortMovies resets _movies_loaded and _movies_total."""
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"
        lib._movies_loaded = 100
        lib._movies_total = 500

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.sortMovies("az")

        assert lib._movies_loaded == 0
        assert lib._movies_total == 0

    def test_sort_noop_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        lib._current_section_key = "4"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.sortMovies("az")

        assert len(submitted) == 0

    def test_sort_noop_when_no_section_key(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = ""

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.sortMovies("az")

        assert len(submitted) == 0


# ---------------------------------------------------------------------------
# PlexLibrary.filterByGenre (Task 022)
# ---------------------------------------------------------------------------


class TestFilterByGenre:
    """filterByGenre re-fetches with the correct genre key."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_filter_sets_current_genre(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterByGenre("42")

        assert lib._current_genre == "42"

    def test_filter_passes_genre_to_worker(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.filterByGenre("42")

        assert len(submitted) == 1
        assert "42" in submitted[0][1]

    def test_filter_empty_string_clears_genre(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"
        lib._current_genre = "42"

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterByGenre("")

        assert lib._current_genre == ""

    def test_filter_resets_pagination(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"
        lib._movies_loaded = 50
        lib._movies_total = 200

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterByGenre("7")

        assert lib._movies_loaded == 0
        assert lib._movies_total == 0

    def test_filter_noop_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        lib._current_section_key = "4"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.filterByGenre("42")

        assert len(submitted) == 0


# ---------------------------------------------------------------------------
# PlexLibrary.getMovieGenres / getShowGenres (Task 022)
# ---------------------------------------------------------------------------


class TestGetGenres:
    """getMovieGenres and getShowGenres delegate to the Plex client."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_get_movie_genres_calls_client(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        mock_client = MagicMock()
        mock_client.get_genres.return_value = [
            {"key": "1", "title": "Action"},
            {"key": "2", "title": "Comedy"},
        ]
        lib._client = mock_client

        result = lib.getMovieGenres()

        mock_client.get_genres.assert_called_once_with("4")
        assert len(result) == 2
        assert result[0]["title"] == "Action"

    def test_get_show_genres_calls_client(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "3"
        mock_client = MagicMock()
        mock_client.get_genres.return_value = [
            {"key": "5", "title": "Drama"},
        ]
        lib._client = mock_client

        result = lib.getShowGenres()

        mock_client.get_genres.assert_called_once_with("3")
        assert result[0]["title"] == "Drama"

    def test_get_movie_genres_returns_empty_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        lib._current_section_key = "4"

        result = lib.getMovieGenres()

        assert result == []

    def test_get_movie_genres_returns_empty_when_no_section_key(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = ""

        result = lib.getMovieGenres()

        assert result == []


# ---------------------------------------------------------------------------
# PlexLibrary.selectLibrary — resets sort/filter (Task 022)
# ---------------------------------------------------------------------------


class TestSelectLibraryResetsSortFilter:
    """selectLibrary resets _current_sort and _current_genre."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_select_library_resets_sort(self) -> None:
        lib = self._make_lib()
        lib._current_sort = "titleSort:asc"
        lib._current_genre = "42"
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        assert lib._current_sort == ""
        assert lib._current_genre == ""

    def test_select_library_ondeck_does_not_reset_sort(self) -> None:
        """selectLibrary('_ondeck') must not reset sort/filter state."""
        lib = self._make_lib()
        lib._current_sort = "titleSort:asc"
        lib._current_genre = "42"

        lib.selectLibrary("_ondeck")

        # _ondeck early-returns before resetting sort/filter
        assert lib._current_sort == "titleSort:asc"
        assert lib._current_genre == "42"


# ---------------------------------------------------------------------------
# PlexLibrary.loadMoreMovies — passes sort/filter to worker (Task 022)
# ---------------------------------------------------------------------------


class TestLoadMoreMoviesPassesSortFilter:
    """loadMoreMovies passes current sort/filter to the worker."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_sort_and_genre_passed_to_worker(self) -> None:
        lib = self._make_lib()
        lib._movies_total = 200
        lib._movies_loaded = 50
        lib._current_section_key = "4"
        lib._current_sort = "addedAt:desc"
        lib._current_genre = "7"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.loadMoreMovies()

        assert len(submitted) == 1
        fn, args = submitted[0]
        # args: (client, section_key, start, sort, genre)
        assert "addedAt:desc" in args
        assert "7" in args


# ---------------------------------------------------------------------------
# PlexLibrary._resolve_server_url — connection selection logic (Task 002)
# ---------------------------------------------------------------------------


class TestResolveServerUrl:
    """_resolve_server_url picks the best connection URL from plex.tv resources."""

    def _make_lib_with_account(self, resources):
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = resources

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_prefers_local_connection(self) -> None:
        """Local connections are preferred over non-local."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {"uri": "https://relay.plex.tv/server", "local": False, "relay": True, "protocol": "https"},
                    {"uri": "http://192.168.0.2:32400", "local": True, "relay": False, "protocol": "http"},
                    {"uri": "https://external.example.com:32400", "local": False, "relay": False, "protocol": "https"},
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == "http://192.168.0.2:32400"

    def test_prefers_https_within_local(self) -> None:
        """Among local connections, HTTPS is preferred over HTTP."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {"uri": "http://192.168.0.2:32400", "local": True, "relay": False, "protocol": "http"},
                    {"uri": "https://192.168.0.2:32443", "local": True, "relay": False, "protocol": "https"},
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == "https://192.168.0.2:32443"

    def test_falls_back_to_non_relay_when_no_local(self) -> None:
        """Non-relay external connections are preferred over relay."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {"uri": "https://relay.plex.tv/server", "local": False, "relay": True, "protocol": "https"},
                    {"uri": "https://external.example.com:32400", "local": False, "relay": False, "protocol": "https"},
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == "https://external.example.com:32400"

    def test_falls_back_to_relay_as_last_resort(self) -> None:
        """Relay connections are used when no better option exists."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {"uri": "https://relay.plex.tv/server", "local": False, "relay": True, "protocol": "https"},
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == "https://relay.plex.tv/server"

    def test_returns_empty_when_server_not_found(self) -> None:
        """Returns empty string when the configured server ID is not in resources."""
        resources = [
            {
                "clientIdentifier": "other-server",
                "name": "Other Server",
                "owned": True,
                "connections": [
                    {"uri": "http://other:32400", "local": True, "relay": False, "protocol": "http"},
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == ""

    def test_returns_empty_when_no_connections(self) -> None:
        """Returns empty string when the server has no connections."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == ""

    def test_prefers_direct_ip_over_plex_direct_within_local(self) -> None:
        """Within local connections, direct IP URLs are preferred over plex.direct URLs."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {
                        "uri": "https://192-168-0-3.abc123.plex.direct:32400",
                        "local": True,
                        "relay": False,
                        "protocol": "https",
                    },
                    {
                        "uri": "http://192.168.0.2:32400",
                        "local": True,
                        "relay": False,
                        "protocol": "http",
                    },
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        # The plain HTTP direct IP connection should be preferred over the
        # plex.direct HTTPS URL, even though HTTPS normally ranks higher.
        assert lib._server_url == "http://192.168.0.2:32400"

    def test_plex_direct_https_preferred_over_plex_direct_http_within_local(self) -> None:
        """Among plex.direct connections, HTTPS is still preferred over HTTP."""
        resources = [
            {
                "clientIdentifier": "server123",
                "name": "My Server",
                "owned": True,
                "connections": [
                    {
                        "uri": "http://192-168-0-2.abc123.plex.direct:32400",
                        "local": True,
                        "relay": False,
                        "protocol": "http",
                    },
                    {
                        "uri": "https://192-168-0-2.abc123.plex.direct:32400",
                        "local": True,
                        "relay": False,
                        "protocol": "https",
                    },
                ],
            }
        ]
        lib = self._make_lib_with_account(resources)
        assert lib._server_url == "https://192-168-0-2.abc123.plex.direct:32400"


# ---------------------------------------------------------------------------
# PlexLibrary._setup_client — user switching (Task 002)
# ---------------------------------------------------------------------------


class TestSetupClientUserSwitching:
    """_setup_client calls switch_user when plex_user_id is set."""

    def test_switch_user_called_when_user_id_set(self) -> None:
        """When plex_user_id is set, switch_user is called and user token is used."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = "user-specific-token"

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        mock_client_cls = MagicMock()

        with patch("backend.plex_library.PlexClient", mock_client_cls), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

        mock_account.switch_user.assert_called_once_with(42)
        # PlexClient uses the admin token for server API calls (managed users
        # don't have direct server access).  The user-specific token is stored
        # in _active_token for browser deep links only.
        mock_client_cls.assert_called_once()
        call_args = mock_client_cls.call_args
        assert call_args[0][1] == "admin-token"
        assert lib._active_token == "user-specific-token"

    def test_admin_token_used_when_switch_user_fails(self) -> None:
        """When switch_user returns None, the admin token is used as fallback."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = None  # switch failed

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        mock_client_cls = MagicMock()

        with patch("backend.plex_library.PlexClient", mock_client_cls), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

        # PlexClient should be created with the admin token as fallback
        mock_client_cls.assert_called_once()
        call_args = mock_client_cls.call_args
        assert call_args[0][1] == "admin-token"

    def test_no_client_when_no_token(self) -> None:
        """No client is created when no token is configured."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = None
            config.plex_token = None
            config.plex_user_id = None
            lib = PlexLibrary(config)

        assert lib._client is None
        assert lib._server_url == ""

    def test_no_client_when_no_server_id(self) -> None:
        """No client is created when no server ID is configured."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount"), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = None
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)

        assert lib._client is None
        assert lib._server_url == ""


# ---------------------------------------------------------------------------
# PlexLibrary._setup_client — user token caching (Bug 2)
# ---------------------------------------------------------------------------


class TestSetupClientTokenCaching:
    """_setup_client caches the user token to avoid redundant switch_user calls."""

    def _make_lib_with_user(self, user_id=42):
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = "user-specific-token"

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        mock_client_cls = MagicMock()

        with patch("backend.plex_library.PlexClient", mock_client_cls), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = user_id
            lib = PlexLibrary(config)

        return lib, mock_account, mock_client_cls

    def test_switch_user_called_only_once_on_repeated_setup(self) -> None:
        """Calling _setup_client() multiple times with the same user_id only calls
        switch_user() once — subsequent calls reuse the cached token."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = "user-specific-token"

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

            # switch_user was called once during __init__
            assert mock_account.switch_user.call_count == 1

            # Call _setup_client() again (simulating refresh())
            lib._setup_client()
            lib._setup_client()

            # switch_user should still only have been called once
            assert mock_account.switch_user.call_count == 1

    def test_cached_token_stored_after_first_switch(self) -> None:
        """After a successful switch_user, the token is cached."""
        lib, mock_account, _ = self._make_lib_with_user(42)

        assert lib._cached_user_id == 42
        assert lib._cached_user_token == "user-specific-token"

    def test_select_user_clears_cache(self) -> None:
        """selectUser() clears the cached token so the next _setup_client() re-switches."""
        lib, mock_account, _ = self._make_lib_with_user(42)

        # Cache is populated after init
        assert lib._cached_user_id == 42
        assert lib._cached_user_token == "user-specific-token"

        # selectUser clears the cache
        with patch.object(lib, "_setup_client"), patch.object(lib, "refresh"):
            lib.selectUser(99)

        assert lib._cached_user_id is None
        assert lib._cached_user_token == ""

    def test_switch_user_called_again_after_cache_cleared(self) -> None:
        """After selectUser() clears the cache, the next _setup_client() calls switch_user()."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = "user-specific-token"

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

            # switch_user called once during init
            assert mock_account.switch_user.call_count == 1

            # Clear cache (as selectUser would do) and call _setup_client() again
            lib._cached_user_id = None
            lib._cached_user_token = ""
            lib._setup_client()

            # switch_user should have been called again
            assert mock_account.switch_user.call_count == 2

    def test_cache_not_populated_when_switch_fails(self) -> None:
        """If switch_user returns None, the cache is not populated."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = None  # switch fails

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

        # Cache should not be populated when switch fails
        assert lib._cached_user_id is None
        assert lib._cached_user_token == ""


# ---------------------------------------------------------------------------
# PlexLibrary.getServerList / getHomeUsers (Task 002)
# ---------------------------------------------------------------------------


class TestGetServerListAndHomeUsers:
    """getServerList and getHomeUsers delegate to PlexAccount."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_get_server_list_returns_formatted_list(self) -> None:
        lib = self._make_lib()
        mock_account = MagicMock()
        mock_account.get_resources.return_value = [
            {"clientIdentifier": "srv1", "name": "Home Server", "owned": True},
            {"clientIdentifier": "srv2", "name": "Friend's Server", "owned": False},
        ]
        lib._account = mock_account

        result = lib.getServerList()

        assert len(result) == 2
        assert result[0] == {"id": "srv1", "name": "Home Server", "owned": True}
        assert result[1] == {"id": "srv2", "name": "Friend's Server", "owned": False}

    def test_get_server_list_returns_empty_when_no_account(self) -> None:
        lib = self._make_lib()
        lib._account = None

        result = lib.getServerList()

        assert result == []

    def test_get_home_users_returns_formatted_list(self) -> None:
        lib = self._make_lib()
        mock_account = MagicMock()
        mock_account.get_home_users.return_value = [
            {"id": 1, "title": "Admin", "admin": True, "restricted": False},
            {"id": 2, "title": "Kid", "admin": False, "restricted": True},
        ]
        lib._account = mock_account

        result = lib.getHomeUsers()

        assert len(result) == 2
        assert result[0] == {"id": 1, "title": "Admin", "admin": True, "restricted": False}
        assert result[1] == {"id": 2, "title": "Kid", "admin": False, "restricted": True}

    def test_get_home_users_returns_empty_when_no_account(self) -> None:
        lib = self._make_lib()
        lib._account = None

        result = lib.getHomeUsers()

        assert result == []


# ---------------------------------------------------------------------------
# PlexLibrary.selectServer / selectUser (Task 002)
# ---------------------------------------------------------------------------


class TestSelectServerAndUser:
    """selectServer and selectUser update config and trigger reconnect."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_select_server_updates_config(self) -> None:
        lib = self._make_lib()
        lib._executor.submit = lambda fn, *args, **kwargs: None  # suppress network calls

        with patch.object(lib, "_setup_client"), \
             patch.object(lib, "refresh"):
            lib.selectServer("new-server-id")

        lib._config.set_plex_server_id.assert_called_once_with("new-server-id")

    def test_select_server_invalidates_client(self) -> None:
        lib = self._make_lib()
        lib._client = MagicMock()
        lib._server_url = "http://old-server"
        lib._active_token = "old-token"

        lib.selectServer("new-server-id")

        assert lib._client is None
        assert lib._server_url == ""
        assert lib._active_token == ""

    def test_select_user_updates_config(self) -> None:
        lib = self._make_lib()

        lib.selectUser(7)

        lib._config.set_plex_user_id.assert_called_once_with(7)

    def test_select_user_invalidates_client_and_cache(self) -> None:
        lib = self._make_lib()
        lib._client = MagicMock()
        lib._cached_user_id = 5
        lib._cached_user_token = "old-token"

        lib.selectUser(7)

        assert lib._client is None
        assert lib._cached_user_id is None
        assert lib._cached_user_token == ""


# ---------------------------------------------------------------------------
# PlexClient.get_library_items — content_rating parameter (Task 003)
# ---------------------------------------------------------------------------


class TestPlexClientContentRatingParam:
    """get_library_items passes contentRating query param when content_rating is set."""

    def _make_client_with_session(self, response_data: dict):
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = response_data
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            client._session = mock_session
        return client, mock_session

    def test_content_rating_param_sent_when_provided(self) -> None:
        """contentRating query param is included when content_rating is non-empty."""
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", content_rating="G,PG,TV-Y,TV-G,NR")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("contentRating") == "G,PG,TV-Y,TV-G,NR"

    def test_content_rating_not_sent_when_empty(self) -> None:
        """contentRating query param is omitted when content_rating is empty string."""
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4", content_rating="")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert "contentRating" not in params

    def test_content_rating_not_sent_by_default(self) -> None:
        """contentRating is not sent when content_rating parameter is omitted."""
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items("4")

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert "contentRating" not in params

    def test_content_rating_combined_with_sort_and_genre(self) -> None:
        """content_rating works alongside sort and genre params."""
        client, mock_session = self._make_client_with_session(
            {"MediaContainer": {"Metadata": [], "totalSize": 0}}
        )
        client.get_library_items(
            "4", sort="titleSort:asc", genre="7",
            content_rating="G,PG,TV-Y,TV-G,NR"
        )

        call_kwargs = mock_session.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("sort") == "titleSort:asc"
        assert params.get("genre") == "7"
        assert params.get("contentRating") == "G,PG,TV-Y,TV-G,NR"


# ---------------------------------------------------------------------------
# _RESTRICTION_RATINGS mapping (Task 003)
# ---------------------------------------------------------------------------


class TestRestrictionRatingsMapping:
    """_RESTRICTION_RATINGS maps profile names to correct comma-separated ratings."""

    def test_little_kid_profile_ratings(self) -> None:
        from backend.plex_library import _RESTRICTION_RATINGS

        ratings = _RESTRICTION_RATINGS["little_kid"]
        assert "G" in ratings.split(",")
        assert "TV-Y" in ratings.split(",")
        assert "TV-Y7" in ratings.split(",")
        assert "TV-G" in ratings.split(",")
        assert "NR" in ratings.split(",")
        # Should NOT include PG or higher
        assert "PG" not in ratings.split(",")
        assert "PG-13" not in ratings.split(",")

    def test_older_kid_profile_ratings(self) -> None:
        from backend.plex_library import _RESTRICTION_RATINGS

        ratings = _RESTRICTION_RATINGS["older_kid"]
        assert "G" in ratings.split(",")
        assert "PG" in ratings.split(",")
        assert "TV-Y" in ratings.split(",")
        assert "TV-Y7" in ratings.split(",")
        assert "TV-G" in ratings.split(",")
        assert "TV-PG" in ratings.split(",")
        assert "NR" in ratings.split(",")
        # Should NOT include PG-13 or higher
        assert "PG-13" not in ratings.split(",")
        assert "TV-14" not in ratings.split(",")

    def test_teen_profile_ratings(self) -> None:
        from backend.plex_library import _RESTRICTION_RATINGS

        ratings = _RESTRICTION_RATINGS["teen"]
        assert "G" in ratings.split(",")
        assert "PG" in ratings.split(",")
        assert "PG-13" in ratings.split(",")
        assert "TV-Y" in ratings.split(",")
        assert "TV-Y7" in ratings.split(",")
        assert "TV-G" in ratings.split(",")
        assert "TV-PG" in ratings.split(",")
        assert "TV-14" in ratings.split(",")
        assert "NR" in ratings.split(",")
        # Should NOT include R or TV-MA
        assert "R" not in ratings.split(",")
        assert "TV-MA" not in ratings.split(",")

    def test_unknown_profile_returns_empty_string(self) -> None:
        """An unrecognized restriction profile results in no filter (empty string)."""
        from backend.plex_library import _RESTRICTION_RATINGS

        assert _RESTRICTION_RATINGS.get("unknown_profile", "") == ""
        assert _RESTRICTION_RATINGS.get("", "") == ""


# ---------------------------------------------------------------------------
# PlexLibrary._setup_client — restriction profile stored (Task 003)
# ---------------------------------------------------------------------------


class TestSetupClientRestrictionProfile:
    """_setup_client stores the content_rating_filter from the user's restrictionProfile."""

    def _make_lib_with_restricted_user(self, restriction_profile: str):
        from backend.plex_library import PlexLibrary
        from backend.config import Config
        from backend.plex_account import PlexAccount

        mock_account = MagicMock(spec=PlexAccount)
        mock_account.get_resources.return_value = _FAKE_SERVER_RESOURCES
        mock_account.switch_user.return_value = "user-specific-token"
        mock_account.get_home_users.return_value = [
            {
                "id": 42,
                "title": "Kids",
                "admin": False,
                "restricted": True,
                "protected": False,
                "thumb": "",
                "restrictionProfile": restriction_profile,
            }
        ]

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "admin-token"
            config.plex_user_id = 42
            lib = PlexLibrary(config)

        return lib

    def test_older_kid_profile_sets_content_rating_filter(self) -> None:
        """older_kid restriction profile sets the correct content rating filter."""
        lib = self._make_lib_with_restricted_user("older_kid")

        assert lib._content_rating_filter == "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"

    def test_little_kid_profile_sets_content_rating_filter(self) -> None:
        """little_kid restriction profile sets the correct content rating filter."""
        lib = self._make_lib_with_restricted_user("little_kid")

        assert lib._content_rating_filter == "G,TV-Y,TV-Y7,TV-G,NR"

    def test_teen_profile_sets_content_rating_filter(self) -> None:
        """teen restriction profile sets the correct content rating filter."""
        lib = self._make_lib_with_restricted_user("teen")

        assert lib._content_rating_filter == "G,PG,PG-13,TV-Y,TV-Y7,TV-G,TV-PG,TV-14,NR"

    def test_no_restriction_profile_leaves_filter_empty(self) -> None:
        """Empty restriction profile (admin/unrestricted user) leaves filter empty."""
        lib = self._make_lib_with_restricted_user("")

        assert lib._content_rating_filter == ""

    def test_unknown_restriction_profile_leaves_filter_empty(self) -> None:
        """Unrecognized restriction profile leaves filter empty (no filter applied)."""
        lib = self._make_lib_with_restricted_user("custom_profile")

        assert lib._content_rating_filter == ""

    def test_content_rating_filter_initialized_to_empty(self) -> None:
        """_content_rating_filter is initialized to empty string in __init__."""
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)

        assert lib._content_rating_filter == ""

    def test_select_user_clears_content_rating_filter(self) -> None:
        """selectUser() clears _content_rating_filter so next setup re-resolves it."""
        lib = self._make_lib_with_restricted_user("older_kid")

        # Filter should be set after init with restricted user
        assert lib._content_rating_filter != ""

        # selectUser clears the filter
        lib.selectUser(99)

        assert lib._content_rating_filter == ""


# ---------------------------------------------------------------------------
# PlexLibrary._worker_load_section — passes content_rating filter (Task 003)
# ---------------------------------------------------------------------------


class TestWorkerLoadSectionContentRating:
    """_worker_load_section passes _content_rating_filter to get_library_items."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_content_rating_filter_passed_to_get_library_items(self) -> None:
        """_worker_load_section passes content_rating_filter to client.get_library_items."""
        lib = self._make_lib()
        lib._content_rating_filter = "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        lib._worker_load_section(mock_client, "4", "movie")

        mock_client.get_library_items.assert_called_once()
        call_kwargs = mock_client.get_library_items.call_args[1]
        assert call_kwargs.get("content_rating") == "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"

    def test_empty_content_rating_filter_passed_when_no_restriction(self) -> None:
        """When no restriction is set, empty string is passed as content_rating."""
        lib = self._make_lib()
        lib._content_rating_filter = ""

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        lib._worker_load_section(mock_client, "4", "movie")

        call_kwargs = mock_client.get_library_items.call_args[1]
        assert call_kwargs.get("content_rating") == ""

    def test_content_rating_filter_passed_to_load_more_movies(self) -> None:
        """_worker_load_more_movies passes content_rating_filter to client.get_library_items."""
        lib = self._make_lib()
        lib._content_rating_filter = "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        lib._worker_load_more_movies(mock_client, "4", 0)

        mock_client.get_library_items.assert_called_once()
        call_kwargs = mock_client.get_library_items.call_args[1]
        assert call_kwargs.get("content_rating") == "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"
