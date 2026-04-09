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

            mock_session.headers.update.assert_called_once()
            call_headers = mock_session.headers.update.call_args[0][0]
            assert call_headers["X-Plex-Token"] == "tok123"
            assert call_headers["Accept"] == "application/json"
            assert call_headers["X-Plex-Client-Identifier"] == "htpcstation"
            assert call_headers["X-Plex-Product"] == "HTPC Station"

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
            # get_poster_url now routes through /photo/:/transcode for server-side resizing
            assert "/photo/:/transcode" in url
            assert "width=400" in url
            assert "X-Plex-Token=mytoken" in url


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

    def test_filters_to_movie_show_and_artist(self) -> None:
        """get_libraries now includes movie, show, and artist types."""
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Movies", "type": "movie", "key": "1"},
            {"title": "TV Shows", "type": "show", "key": "2"},
            {"title": "Music", "type": "artist", "key": "3"},
            {"title": "Audiobooks", "type": "artist", "key": "4"},
            {"title": "Photos", "type": "photo", "key": "5"},
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

        assert len(libs) == 4
        types = {lib["type"] for lib in libs}
        assert types == {"movie", "show", "artist"}

    def test_empty_libraries_when_all_filtered(self) -> None:
        """Unsupported library types (e.g. photo) are still filtered out."""
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Photos", "type": "photo", "key": "1"},
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
    @patch("backend.plex_client.time.sleep")
    def test_connection_error_returns_empty(self, mock_sleep) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            result = client.get_identity()

        assert result == {}

    @patch("backend.plex_client.time.sleep")
    def test_timeout_returns_empty(self, mock_sleep) -> None:
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

    @patch("backend.plex_client.time.sleep")
    def test_connection_error_returns_empty_libraries(self, mock_sleep) -> None:
        import requests as req
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            libs = client.get_libraries()

        assert libs == []

    @patch("backend.plex_client.time.sleep")
    def test_connection_error_returns_empty_items(self, mock_sleep) -> None:
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
# PlexClient — get_on_deck (continueWatching)
# ---------------------------------------------------------------------------


class TestPlexClientGetOnDeck:
    def test_calls_continue_watching_endpoint(self) -> None:
        """get_on_deck() should call /hubs/home/continueWatching."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Hub": [
                        {
                            "Metadata": [
                                {"ratingKey": "1", "title": "Episode 1"},
                                {"ratingKey": "2", "title": "Episode 2"},
                            ]
                        }
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_on_deck()

            call_url = mock_session.get.call_args[0][0]
            assert "/hubs/home/continueWatching" in call_url
            assert len(result) == 2
            assert result[0]["title"] == "Episode 1"

    def test_fallback_metadata_at_container_level(self) -> None:
        """When Hub is absent, fall back to Metadata at the container level."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Metadata": [
                        {"ratingKey": "3", "title": "Episode 3"},
                    ]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_on_deck()

            assert len(result) == 1
            assert result[0]["title"] == "Episode 3"

    @patch("backend.plex_client.time.sleep")
    def test_returns_empty_list_on_none_response(self, mock_sleep) -> None:
        """get_on_deck() returns [] when _get returns None (error)."""
        from backend.plex_client import PlexClient
        import requests as req

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            result = client.get_on_deck()

            assert result == []

    def test_returns_empty_list_when_hub_has_no_metadata(self) -> None:
        """When Hub exists but has no Metadata key, returns []."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {
                    "Hub": [{}]
                }
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_on_deck()

            assert result == []


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
        import tempfile
        from pathlib import Path
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        tmp_dir = Path(tempfile.mkdtemp())
        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"), \
             patch("backend.plex_library.CONFIG_DIR", tmp_dir):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_empty_when_no_data(self) -> None:
        """With no libraries and no on-deck, only the Live TV entry is returned."""
        lib = self._make_lib()
        result = lib.getLibraryList()
        # Live TV is always appended
        assert len(result) == 1
        assert result[0]["title"] == "Live TV"
        assert result[0]["type"] == "livetv"

    def test_libraries_only_no_ondeck(self) -> None:
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
            {"title": "TV Shows", "type": "show", "key": "3"},
        ])
        result = lib.getLibraryList()
        # Movies, TV Shows, then Live TV
        assert len(result) == 3
        assert result[0]["title"] == "Movies"
        assert result[0]["type"] == "movie"
        assert result[0]["sectionKey"] == "4"
        assert result[1]["title"] == "TV Shows"
        assert result[1]["sectionKey"] == "3"
        assert result[2]["title"] == "Live TV"
        assert result[2]["type"] == "livetv"

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
        # Continue Watching, Movies, then Live TV
        assert len(result) == 3
        assert result[0]["title"] == "Continue Watching"
        assert result[0]["type"] == "ondeck"
        assert result[0]["sectionKey"] == "_ondeck"
        assert result[0]["count"] == 1
        assert result[1]["title"] == "Movies"
        assert result[2]["title"] == "Live TV"

    def test_ondeck_not_prepended_when_empty(self) -> None:
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])
        result = lib.getLibraryList()
        # Movies, then Live TV
        assert len(result) == 2
        assert result[0]["title"] == "Movies"
        assert result[1]["title"] == "Live TV"

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
# PlexLibrary.fetchShow — Task 018 (updated to async in harden/002)
# ---------------------------------------------------------------------------


def _run_fetch_worker(lib, method_name, *args):
    """Submit a fetch* call and run the captured worker synchronously."""
    submitted = []

    def fake_submit(fn, *a, **kw):
        submitted.append(fn)

    lib._executor.submit = fake_submit  # type: ignore[method-assign]
    getattr(lib, method_name)(*args)
    for fn in submitted:
        fn()


class TestGetShow:
    """fetchShow() emits showReady with show metadata for QML consumption."""

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

        received = []
        lib.showReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchShow", "200")

        assert len(received) == 1
        _, result = received[0]
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

        received = []
        lib.showReady.connect(lambda rk, d: received.append((rk, d)))
        lib.fetchShow("200")

        assert len(received) == 1
        _, result = received[0]
        assert result == {}

    def test_returns_empty_dict_when_metadata_not_found(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = None
        lib._client = mock_client

        received = []
        lib.showReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchShow", "999")

        assert len(received) == 1
        _, result = received[0]
        assert result == {}


# ---------------------------------------------------------------------------
# PlexLibrary.fetchSeasons — Task 018 (updated to async in harden/002)
# ---------------------------------------------------------------------------


class TestGetSeasons:
    """fetchSeasons() emits seasonsReady with a list of season dicts for QML consumption."""

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

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchSeasons", "200")

        assert len(received) == 1
        _, result = received[0]
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

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchSeasons", "200")

        _, result = received[0]
        assert len(result) == 1
        assert result[0]["ratingKey"] == "300"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))
        lib.fetchSeasons("200")

        assert len(received) == 1
        _, result = received[0]
        assert result == []

    def test_returns_empty_list_when_no_children(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = []
        lib._client = mock_client

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchSeasons", "200")

        _, result = received[0]
        assert result == []


# ---------------------------------------------------------------------------
# PlexLibrary.fetchEpisodes — Task 018 (updated to async in harden/002)
# ---------------------------------------------------------------------------


class TestGetEpisodes:
    """fetchEpisodes() emits episodesReady with a list of episode dicts for QML consumption."""

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

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchEpisodes", "300")

        assert len(received) == 1
        _, result = received[0]
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

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker(lib, "fetchEpisodes", "300")

        _, result = received[0]
        assert len(result) == 1
        assert result[0]["ratingKey"] == "400"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append((rk, d)))
        lib.fetchEpisodes("300")

        assert len(received) == 1
        _, result = received[0]
        assert result == []

    def test_watched_indicator_fields_present(self) -> None:
        """All episode dicts must have 'viewed' and 'viewOffset' for QML watched indicators."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "episode", "ratingKey": "400", "title": "Ep"},
        ]
        lib._client = mock_client

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchEpisodes", "300")

        assert len(received) == 1
        result = received[0]
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
# PlexLibrary.fetchMovie — poster caching (Task 023, updated to async in harden/002)
# ---------------------------------------------------------------------------


class TestGetMoviePosterCaching:
    """fetchMovie() must populate posterLocal via the poster cache."""

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
        """posterLocal in the emitted dict reflects the cached file URL."""
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

        received = []
        lib.movieReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchMovie", "123")

        result = received[0]
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

        received = []
        lib.movieReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchMovie", "124")

        result = received[0]
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

        received = []
        lib.movieReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchMovie", "125")

        result = received[0]
        assert result["posterLocal"] == ""


# ---------------------------------------------------------------------------
# PlexLibrary.fetchShow — poster caching (Task 023, updated to async in harden/002)
# ---------------------------------------------------------------------------


class TestGetShowPosterCaching:
    """fetchShow() must populate posterLocal via the poster cache."""

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
        """posterLocal in the emitted dict reflects the cached file URL."""
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

        received = []
        lib.showReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchShow", "200")

        result = received[0]
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

        received = []
        lib.showReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchShow", "201")

        result = received[0]
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

        received = []
        lib.showReady.connect(lambda rk, d: received.append(d))
        _run_fetch_worker(lib, "fetchShow", "202")

        result = received[0]
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

    @patch("backend.plex_client.time.sleep")
    def test_returns_empty_on_connection_error(self, mock_sleep) -> None:
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

        assert lib._section_sort.get(lib._current_section_key, "") == "titleSort:asc"
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

        assert lib._section_sort.get(lib._current_section_key, "") == "titleSort:desc"

    def test_sort_recent_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("recent")

        assert lib._section_sort.get(lib._current_section_key, "") == "addedAt:desc"

    def test_sort_year_desc_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("year_desc")

        assert lib._section_sort.get(lib._current_section_key, "") == "year:desc"

    def test_sort_rating_maps_to_correct_api_param(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "4"
        lib._current_section_type = "movie"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortMovies("rating")

        assert lib._section_sort.get(lib._current_section_key, "") == "audienceRating:desc"

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

        assert lib._section_genre.get(lib._current_section_key, "") == "42"

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
        lib._section_genre[lib._current_section_key] = "42"

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterByGenre("")

        assert lib._section_genre.get(lib._current_section_key, "") == ""

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
    """selectLibrary preserves _current_sort and _current_genre (sort persists across library switches)."""

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

    def test_select_library_preserves_sort_when_same_section(self) -> None:
        """selectLibrary preserves sort/genre when re-entering the same section."""
        lib = self._make_lib()
        lib._current_section_key = "4"   # already in this section
        lib._section_sort[lib._current_section_key] = "titleSort:asc"
        lib._section_genre[lib._current_section_key] = "42"
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        assert lib._section_sort.get(lib._current_section_key, "") == "titleSort:asc"
        assert lib._section_genre.get(lib._current_section_key, "") == "42"

    def test_select_library_resets_sort_when_switching_section(self) -> None:
        """selectLibrary resets sort/genre when switching to a different section."""
        lib = self._make_lib()
        lib._current_section_key = "3"   # was in a different section
        lib._section_sort[lib._current_section_key] = "titleSort:asc"
        lib._section_genre[lib._current_section_key] = "42"
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
        ])

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.selectLibrary("4")

        assert lib._section_sort.get(lib._current_section_key, "") == ""
        assert lib._section_genre.get(lib._current_section_key, "") == ""

    def test_select_library_ondeck_does_not_reset_sort(self) -> None:
        """selectLibrary('_ondeck') must not affect other sections' sort/filter state."""
        lib = self._make_lib()
        lib._section_sort["4"] = "titleSort:asc"
        lib._section_genre["4"] = "42"

        lib.selectLibrary("_ondeck")

        # _ondeck early-returns — other sections' sort/filter must be untouched
        assert lib._section_sort.get("4", "") == "titleSort:asc"
        assert lib._section_genre.get("4", "") == "42"


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
        lib._section_sort[lib._current_section_key] = "addedAt:desc"
        lib._section_genre[lib._current_section_key] = "7"

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


# ---------------------------------------------------------------------------
# PlexShowListModel.append_shows (Task 001 — show pagination)
# ---------------------------------------------------------------------------


class TestAppendShows:
    """append_shows adds items to the model without resetting it."""

    def _make_show(self, rating_key: str = "1", title: str = "Test Show") -> "PlexShow":
        from backend.plex_models import PlexShow
        return PlexShow(
            rating_key=rating_key,
            title=title,
            year=2019,
            audience_rating=9.0,
            child_count=3,
            leaf_count=30,
            viewed_leaf_count=10,
        )

    def test_append_shows_adds_to_existing(self) -> None:
        from backend.plex_library import PlexShowListModel

        model = PlexShowListModel()
        model.set_shows([self._make_show("1", "First")])
        model.append_shows([self._make_show("2", "Second")])

        assert model.rowCount() == 2
        idx = model.index(1, 0)
        assert model.data(idx, PlexShowListModel.TitleRole) == "Second"

    def test_append_shows_noop_on_empty_list(self) -> None:
        from backend.plex_library import PlexShowListModel

        model = PlexShowListModel()
        model.set_shows([self._make_show("1", "First")])
        model.append_shows([])

        assert model.rowCount() == 1

    def test_append_shows_emits_rows_inserted(self) -> None:
        from backend.plex_library import PlexShowListModel

        model = PlexShowListModel()
        model.set_shows([self._make_show("1", "First")])

        inserted: list = []
        model.rowsInserted.connect(lambda parent, first, last: inserted.append((first, last)))

        model.append_shows([self._make_show("2", "Second"), self._make_show("3", "Third")])

        assert len(inserted) == 1
        assert inserted[0] == (1, 2)  # rows 1 and 2 inserted


# ---------------------------------------------------------------------------
# PlexLibrary._showsReady signal carries total count (Task 001)
# ---------------------------------------------------------------------------


class TestShowsReadySignalCarriesTotalCount:
    """_showsReady signal must carry (list, int) — the total count."""

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

    def test_on_shows_ready_sets_total(self) -> None:
        """_on_shows_ready stores the total count from the signal."""
        from backend.plex_models import PlexShow

        lib = self._make_lib()
        lib._client = None  # prevent poster fetch attempts

        show = PlexShow(rating_key="1", title="Test Show", year=2020)
        lib._on_shows_ready([show], 150)

        assert lib._shows_total == 150
        assert lib._shows_loaded == 1

    def test_on_shows_ready_first_page_replaces_model(self) -> None:
        """First call (_shows_loaded == 0) replaces the model."""
        from backend.plex_models import PlexShow

        lib = self._make_lib()
        lib._client = None
        lib._shows_loaded = 0

        shows = [PlexShow(rating_key=str(i), title=f"Show {i}", year=2020) for i in range(3)]
        lib._on_shows_ready(shows, 100)

        assert lib._shows_model.rowCount() == 3
        assert lib._shows_loaded == 3
        assert lib._shows_total == 100

    def test_on_shows_ready_subsequent_page_appends(self) -> None:
        """Subsequent calls (_shows_loaded > 0) append to the model."""
        from backend.plex_models import PlexShow

        lib = self._make_lib()
        lib._client = None

        # Simulate first page already loaded
        first_page = [PlexShow(rating_key=str(i), title=f"Show {i}", year=2020) for i in range(3)]
        lib._shows_model.set_shows(first_page)
        lib._shows_loaded = 3
        lib._shows_total = 6

        # Load second page
        second_page = [PlexShow(rating_key=str(i + 3), title=f"Show {i + 3}", year=2020) for i in range(3)]
        lib._on_shows_ready(second_page, 6)

        assert lib._shows_model.rowCount() == 6
        assert lib._shows_loaded == 6

    def test_on_shows_ready_clears_loading_more_flag(self) -> None:
        """_shows_loading_more is reset to False when _on_shows_ready is called."""
        from backend.plex_models import PlexShow

        lib = self._make_lib()
        lib._client = None
        lib._shows_loading_more = True
        lib._shows_loaded = 0

        show = PlexShow(rating_key="1", title="Test", year=2020)
        lib._on_shows_ready([show], 1)

        assert lib._shows_loading_more is False


# ---------------------------------------------------------------------------
# PlexLibrary.loadMoreShows — guards and pagination (Task 001)
# ---------------------------------------------------------------------------


class TestLoadMoreShowsGuard:
    """loadMoreShows guards prevent duplicate submissions."""

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

    def test_loading_more_flag_prevents_duplicate_submission(self) -> None:
        """Second call to loadMoreShows while _shows_loading_more is True is a no-op."""
        lib = self._make_lib()
        lib._shows_total = 100
        lib._shows_loaded = 50
        lib._current_section_key = "3"

        submit_calls: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

        # First call — should submit
        lib.loadMoreShows()
        assert lib._shows_loading_more is True
        assert len(submit_calls) == 1

        # Second call while flag is set — should be a no-op
        lib.loadMoreShows()
        assert len(submit_calls) == 1  # still only one submission

    def test_no_submission_when_all_loaded(self) -> None:
        """loadMoreShows is a no-op when all shows are already loaded."""
        lib = self._make_lib()
        lib._shows_total = 50
        lib._shows_loaded = 50
        lib._current_section_key = "3"

        submit_calls: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

        lib.loadMoreShows()

        assert len(submit_calls) == 0

    def test_no_submission_when_no_client(self) -> None:
        """loadMoreShows is a no-op when _client is None."""
        lib = self._make_lib()
        lib._client = None
        lib._shows_total = 100
        lib._shows_loaded = 50
        lib._current_section_key = "3"

        submit_calls: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submit_calls.append(fn)  # type: ignore[method-assign]

        lib.loadMoreShows()

        assert len(submit_calls) == 0

    def test_submits_with_correct_offset(self) -> None:
        """loadMoreShows passes the current _shows_loaded as the start offset."""
        lib = self._make_lib()
        lib._shows_total = 200
        lib._shows_loaded = 50
        lib._current_section_key = "3"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.loadMoreShows()

        assert len(submitted) == 1
        fn, args = submitted[0]
        # args: (client, section_key, start, sort, genre)
        assert 50 in args  # start offset

    def test_loading_more_flag_cleared_after_shows_ready(self) -> None:
        """_shows_loading_more is reset to False when _on_shows_ready is called."""
        from backend.plex_models import PlexShow

        lib = self._make_lib()
        lib._shows_loading_more = True
        lib._shows_loaded = 0
        lib._client = None  # prevent poster fetch attempts

        show = PlexShow(rating_key="1", title="Test", year=2020)
        lib._on_shows_ready([show], 1)

        assert lib._shows_loading_more is False


# ---------------------------------------------------------------------------
# PlexLibrary._worker_load_more_shows — failure resets flag (Task 001)
# ---------------------------------------------------------------------------


class TestLoadMoreShowsFailureResetsFlag:
    """_shows_loading_more must be reset to False when _worker_load_more_shows fails."""

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

        lib._shows_loading_more = True

        mock_client = MagicMock()
        mock_client.get_library_items.side_effect = RuntimeError("network error")

        # Run the worker directly (synchronously) to test the failure path.
        lib._worker_load_more_shows(mock_client, "3", 0)

        assert lib._shows_loading_more is False


# ---------------------------------------------------------------------------
# PlexLibrary.sortShows (Task 001)
# ---------------------------------------------------------------------------


class TestSortShows:
    """sortShows re-fetches shows with the correct Plex API sort param."""

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
        lib._current_section_key = "3"
        lib._current_section_type = "show"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.sortShows("az")

        assert lib._section_sort.get(lib._current_section_key, "") == "titleSort:asc"
        assert len(submitted) == 1
        assert "titleSort:asc" in submitted[0][1]

    def test_sort_resets_show_pagination(self) -> None:
        """sortShows resets _shows_loaded and _shows_total."""
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._shows_loaded = 100
        lib._shows_total = 500

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.sortShows("az")

        assert lib._shows_loaded == 0
        assert lib._shows_total == 0

    def test_sort_does_not_reset_movie_pagination(self) -> None:
        """sortShows must not affect movie pagination state."""
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._movies_loaded = 50
        lib._movies_total = 200

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.sortShows("az")

        assert lib._movies_loaded == 50
        assert lib._movies_total == 200

    def test_sort_noop_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        lib._current_section_key = "3"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.sortShows("az")

        assert len(submitted) == 0

    def test_sort_noop_when_no_section_key(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = ""

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.sortShows("az")

        assert len(submitted) == 0

    def test_sort_shows_does_not_affect_movies_section(self) -> None:
        """sortShows only updates the current section's sort, not other sections."""
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._section_sort["4"] = "addedAt:desc"  # movies section sort should be untouched

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.sortShows("rating")

        assert lib._section_sort.get("3", "") == "audienceRating:desc"
        assert lib._section_sort.get("4", "") == "addedAt:desc"  # movies section unchanged


# ---------------------------------------------------------------------------
# PlexLibrary.filterShowsByGenre (Task 001)
# ---------------------------------------------------------------------------


class TestFilterShowsByGenre:
    """filterShowsByGenre re-fetches shows filtered by genre."""

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

    def test_filter_sets_shows_genre(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterShowsByGenre("42")

        assert lib._section_genre.get(lib._current_section_key, "") == "42"

    def test_filter_passes_genre_to_worker(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.filterShowsByGenre("42")

        assert len(submitted) == 1
        assert "42" in submitted[0][1]

    def test_filter_empty_string_clears_genre(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._section_genre[lib._current_section_key] = "42"

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterShowsByGenre("")

        assert lib._section_genre.get(lib._current_section_key, "") == ""

    def test_filter_resets_show_pagination(self) -> None:
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._shows_loaded = 50
        lib._shows_total = 200

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterShowsByGenre("7")

        assert lib._shows_loaded == 0
        assert lib._shows_total == 0

    def test_filter_does_not_reset_movie_pagination(self) -> None:
        """filterShowsByGenre must not affect movie pagination state."""
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._movies_loaded = 50
        lib._movies_total = 200

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterShowsByGenre("7")

        assert lib._movies_loaded == 50
        assert lib._movies_total == 200

    def test_filter_noop_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None
        lib._current_section_key = "3"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.filterShowsByGenre("42")

        assert len(submitted) == 0

    def test_filter_shows_does_not_affect_movies_section(self) -> None:
        """filterShowsByGenre only updates the current section's genre, not other sections."""
        lib = self._make_lib()
        lib._current_section_key = "3"
        lib._current_section_type = "show"
        lib._section_genre["4"] = "99"  # movies section genre should be untouched

        lib._executor.submit = lambda fn, *args, **kwargs: None  # type: ignore[method-assign]

        lib.filterShowsByGenre("42")

        assert lib._section_genre.get("3", "") == "42"
        assert lib._section_genre.get("4", "") == "99"  # movies section unchanged


# ---------------------------------------------------------------------------
# PlexLibrary.loadMoreShows — passes sort/filter to worker (Task 001)
# ---------------------------------------------------------------------------


class TestLoadMoreShowsPassesSortFilter:
    """loadMoreShows passes current shows sort/filter to the worker."""

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
        lib._shows_total = 200
        lib._shows_loaded = 50
        lib._current_section_key = "3"
        lib._section_sort[lib._current_section_key] = "addedAt:desc"
        lib._section_genre[lib._current_section_key] = "7"

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.loadMoreShows()

        assert len(submitted) == 1
        fn, args = submitted[0]
        # args: (client, section_key, start, sort, genre)
        assert "addedAt:desc" in args
        assert "7" in args


# ---------------------------------------------------------------------------
# PlexLibrary._worker_load_section — emits total for shows (Task 001)
# ---------------------------------------------------------------------------


class TestWorkerLoadSectionShowsTotal:
    """_worker_load_section emits total count for shows via _showsReady."""

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

    def test_shows_ready_receives_total_from_worker(self) -> None:
        """_worker_load_section emits (shows, total) for show sections."""
        lib = self._make_lib()

        received: list = []
        lib._showsReady.connect(lambda shows, total: received.append((shows, total)))

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = (
            [{"ratingKey": "1", "title": "Show 1", "type": "show"}],
            75,
        )

        lib._worker_load_section(mock_client, "3", "show")

        assert len(received) == 1
        shows, total = received[0]
        assert total == 75
        assert len(shows) == 1

    def test_content_rating_filter_passed_to_load_more_shows(self) -> None:
        """_worker_load_more_shows passes content_rating_filter to client.get_library_items."""
        lib = self._make_lib()
        lib._content_rating_filter = "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        lib._worker_load_more_shows(mock_client, "3", 0)

        mock_client.get_library_items.assert_called_once()
        call_kwargs = mock_client.get_library_items.call_args[1]
        assert call_kwargs.get("content_rating") == "G,PG,TV-Y,TV-Y7,TV-G,TV-PG,NR"


# ---------------------------------------------------------------------------
# PlexLibrary.launchLiveTv — Task 001 (Live TV entry)
# ---------------------------------------------------------------------------


class TestLaunchLiveTv:
    """launchLiveTv() builds the correct URL and delegates to the browser launcher."""

    def _make_lib(self, browser_launcher=None):
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
            lib = PlexLibrary(config, browser_launcher=browser_launcher)
        return lib

    def test_launches_correct_url_with_token(self) -> None:
        """launchLiveTv builds URL with token before the hash fragment."""
        mock_launcher = MagicMock()
        lib = self._make_lib(browser_launcher=mock_launcher)
        lib._active_token = "mytoken123"

        lib.launchLiveTv()

        mock_launcher.launch.assert_called_once()
        url = mock_launcher.launch.call_args[0][0]
        assert url == "https://app.plex.tv/desktop?X-Plex-Token=mytoken123#!/live-tv"

    def test_includes_htpc_user_when_user_selected(self) -> None:
        """launchLiveTv appends htpc_user after the hash fragment when a user is set."""
        mock_launcher = MagicMock()
        lib = self._make_lib(browser_launcher=mock_launcher)
        lib._active_token = "mytoken123"
        lib._cached_user_title = "Kids"

        lib.launchLiveTv()

        mock_launcher.launch.assert_called_once()
        url = mock_launcher.launch.call_args[0][0]
        assert url == "https://app.plex.tv/desktop?X-Plex-Token=mytoken123#!/live-tv&htpc_user=Kids"

    def test_htpc_user_is_url_encoded(self) -> None:
        """htpc_user value is URL-encoded when it contains special characters."""
        mock_launcher = MagicMock()
        lib = self._make_lib(browser_launcher=mock_launcher)
        lib._active_token = "tok"
        lib._cached_user_title = "My User"

        lib.launchLiveTv()

        url = mock_launcher.launch.call_args[0][0]
        assert "htpc_user=My%20User" in url

    def test_no_htpc_user_when_no_user_selected(self) -> None:
        """launchLiveTv does not append htpc_user when no user is selected."""
        mock_launcher = MagicMock()
        lib = self._make_lib(browser_launcher=mock_launcher)
        lib._active_token = "tok"
        lib._cached_user_title = ""

        lib.launchLiveTv()

        url = mock_launcher.launch.call_args[0][0]
        assert "htpc_user" not in url

    def test_guard_no_browser_launcher(self) -> None:
        """launchLiveTv returns early when no browser launcher is configured."""
        lib = self._make_lib(browser_launcher=None)
        lib._active_token = "tok"

        # Should not raise
        lib.launchLiveTv()

    def test_guard_no_active_token(self) -> None:
        """launchLiveTv returns early when there is no active token."""
        mock_launcher = MagicMock()
        lib = self._make_lib(browser_launcher=mock_launcher)
        lib._active_token = ""

        lib.launchLiveTv()

        mock_launcher.launch.assert_not_called()


# ---------------------------------------------------------------------------
# PlexLibrary.getLibraryList — Live TV entry (Task 001)
# ---------------------------------------------------------------------------


class TestGetLibraryListLiveTv:
    """getLibraryList() always includes a 'Live TV' entry before My List."""

    def _make_lib(self):
        import tempfile
        from pathlib import Path
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        tmp_dir = Path(tempfile.mkdtemp())
        with patch("backend.plex_library.PlexClient"), \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"), \
             patch("backend.plex_library.CONFIG_DIR", tmp_dir):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_live_tv_entry_always_present(self) -> None:
        """getLibraryList always includes a 'Live TV' entry."""
        lib = self._make_lib()
        result = lib.getLibraryList()

        # With no My List items, Live TV is the last entry
        live_tv = next(e for e in result if e["title"] == "Live TV")
        assert live_tv["title"] == "Live TV"
        assert live_tv["type"] == "livetv"
        assert live_tv["sectionKey"] == "_livetv"
        assert live_tv["count"] == 0

    def test_live_tv_entry_appears_after_libraries(self) -> None:
        """Live TV entry appears after all library sections (before My List)."""
        lib = self._make_lib()
        lib._libraries_model.set_items([
            {"title": "Movies", "type": "movie", "key": "4"},
            {"title": "TV Shows", "type": "show", "key": "3"},
        ])

        result = lib.getLibraryList()

        # Movies and TV Shows come first, Live TV appears after them
        assert result[0]["title"] == "Movies"
        assert result[1]["title"] == "TV Shows"
        live_tv = next(e for e in result if e["title"] == "Live TV")
        assert live_tv is not None

    def test_live_tv_entry_appears_after_ondeck_and_libraries(self) -> None:
        """Live TV entry appears after Continue Watching and library sections."""
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

        assert result[0]["title"] == "Continue Watching"
        assert result[1]["title"] == "Movies"
        live_tv = next(e for e in result if e["title"] == "Live TV")
        assert live_tv["type"] == "livetv"

    def test_live_tv_entry_present_even_with_no_libraries(self) -> None:
        """Live TV entry is present even when no library sections are loaded."""
        lib = self._make_lib()
        # No libraries, no on-deck
        result = lib.getLibraryList()

        assert len(result) == 1
        assert result[0]["title"] == "Live TV"
        assert result[0]["type"] == "livetv"


# ---------------------------------------------------------------------------
# PlexLibrary — error callback registration and plexError signal (Task 002)
# ---------------------------------------------------------------------------


class TestPlexLibraryErrorCallback:
    """Verify PlexLibrary registers the error callback and emits plexError."""

    def _make_lib(self):
        from backend.plex_library import PlexLibrary
        from backend.config import Config

        with patch("backend.plex_library.PlexClient") as mock_client_cls, \
             patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)
        return lib

    def test_plex_library_registers_error_callback(self) -> None:
        """After _setup_client(), verify client._on_error is not None."""
        lib = self._make_lib()
        if lib._client is not None:
            assert lib._client._on_error is not None

    def test_plex_error_signal_emitted(self) -> None:
        """Mock client to call _on_plex_error(PlexErrorType.AUTH); verify plexError emitted with 'auth'.

        _on_plex_error now uses QMetaObject.invokeMethod with QueuedConnection to
        ensure cross-thread delivery, so we must process Qt events before checking.
        """
        from backend.plex_client import PlexErrorType
        from PySide6.QtCore import QCoreApplication

        lib = self._make_lib()

        received: list[str] = []
        lib.plexError.connect(lambda err: received.append(err))

        lib._on_plex_error(PlexErrorType.AUTH)
        QCoreApplication.processEvents()

        assert received == ["auth"]


# ---------------------------------------------------------------------------
# PlexLibrary.getWatchHistory — Task 005 (playback history)
# ---------------------------------------------------------------------------


class TestGetWatchHistorySlot:
    """getWatchHistory() returns a list of dicts with expected keys."""

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

    def test_get_watch_history_slot_returns_list(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_watch_history.return_value = [
            {
                "ratingKey": "123",
                "title": "Test Movie",
                "type": "movie",
                "viewedAt": 1700000000,
                "grandparentTitle": "",
                "thumb": "/library/metadata/123/thumb/1",
                "grandparentThumb": "",
                "duration": 7200000,
            },
            {
                "ratingKey": "456",
                "title": "Pilot",
                "type": "episode",
                "viewedAt": 1700000100,
                "grandparentTitle": "Test Show",
                "thumb": "/library/metadata/456/thumb/1",
                "grandparentThumb": "/library/metadata/200/thumb/1",
                "duration": 2700000,
            },
        ]
        lib._client = mock_client

        result = lib.getWatchHistory(50)

        assert len(result) == 2
        assert result[0]["ratingKey"] == "123"
        assert result[0]["title"] == "Test Movie"
        assert result[0]["type"] == "movie"
        assert result[0]["viewedAt"] == 1700000000
        assert result[0]["grandparentTitle"] == ""
        assert result[0]["thumb"] == "/library/metadata/123/thumb/1"
        assert result[0]["grandparentThumb"] == ""
        assert result[0]["duration"] == 7200000
        assert result[1]["ratingKey"] == "456"
        assert result[1]["grandparentTitle"] == "Test Show"

    def test_get_watch_history_slot_returns_empty_without_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        result = lib.getWatchHistory(50)

        assert result == []


# ---------------------------------------------------------------------------
# PlexLibrary._setup_client — passes fallback URLs (Task 006)
# ---------------------------------------------------------------------------


class TestSetupClientPassesFallbackUrls:
    """_setup_client passes all known server URLs as fallbacks to PlexClient."""

    def test_setup_client_passes_fallback_urls(self) -> None:
        """After _setup_client, client._fallback_urls is set from _all_server_urls."""
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
                    {"uri": "https://external.example.com:32400", "local": False, "relay": False, "protocol": "https"},
                    {"uri": "https://relay.plex.tv/server", "local": False, "relay": True, "protocol": "https"},
                ],
            }
        ]
        mock_account.switch_user.return_value = None

        mock_account_cls = MagicMock()
        mock_account_cls.return_value = mock_account

        with patch("backend.plex_library.PlexAccount", mock_account_cls), \
             patch("backend.config.CONFIG_FILE"), \
             patch("backend.config.CONFIG_DIR"):
            config = MagicMock(spec=Config)
            config.plex_server_id = "server123"
            config.plex_token = "tok"
            config.plex_user_id = None
            lib = PlexLibrary(config)

        # The primary URL is the best connection (local direct IP)
        assert lib._server_url == "http://192.168.0.2:32400"
        # _all_server_urls should contain all connection URIs
        assert len(lib._all_server_urls) == 3
        # The client's fallback list should exclude the primary URL
        assert lib._client is not None
        assert "http://192.168.0.2:32400" not in lib._client._fallback_urls
        assert len(lib._client._fallback_urls) == 2


# ---------------------------------------------------------------------------
# PlexLibrary._on_plex_error — triggers reconnect on NETWORK (Task 006)
# ---------------------------------------------------------------------------


class TestOnPlexErrorTriggersReconnect:
    """_on_plex_error calls try_next_connection on NETWORK errors."""

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

    def test_on_plex_error_triggers_reconnect_on_network(self) -> None:
        """_on_plex_error calls try_next_connection when error is NETWORK."""
        from backend.plex_client import PlexErrorType

        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.try_next_connection.return_value = True
        lib._client = mock_client

        lib._on_plex_error(PlexErrorType.NETWORK)

        mock_client.try_next_connection.assert_called_once()

    def test_on_plex_error_does_not_reconnect_on_auth(self) -> None:
        """_on_plex_error does NOT call try_next_connection for AUTH errors."""
        from backend.plex_client import PlexErrorType

        lib = self._make_lib()
        mock_client = MagicMock()
        lib._client = mock_client

        lib._on_plex_error(PlexErrorType.AUTH)

        mock_client.try_next_connection.assert_not_called()

    def test_on_plex_error_does_not_reconnect_when_no_client(self) -> None:
        """_on_plex_error does NOT call try_next_connection when _client is None."""
        from backend.plex_client import PlexErrorType

        lib = self._make_lib()
        lib._client = None

        # Should not raise
        lib._on_plex_error(PlexErrorType.NETWORK)


# ---------------------------------------------------------------------------
# PlexLibrary — SSE event listener integration (Task 007)
# ---------------------------------------------------------------------------


class TestEventListenerIntegration:
    """Integration tests for PlexLibrary SSE event listener lifecycle."""

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

    def test_start_event_listener_called_after_setup_client(self) -> None:
        """After _setup_client succeeds, _event_listener is not None."""
        lib = self._make_lib()
        # _setup_client was called during __init__ and succeeded (server123 is in fake resources)
        assert lib._event_listener is not None

    def test_stop_event_listener_called_on_shutdown(self) -> None:
        """shutdown() stops the event listener."""
        lib = self._make_lib()

        # Verify listener is set
        assert lib._event_listener is not None

        # Patch the listener's stop method to track calls
        mock_listener = MagicMock()
        lib._event_listener = mock_listener

        lib.shutdown()

        mock_listener.stop.assert_called_once()
        # After shutdown, _event_listener should be None
        assert lib._event_listener is None

    def test_on_library_event_submits_worker_refresh(self) -> None:
        """_on_library_event() submits _worker_refresh to the executor."""
        lib = self._make_lib()

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib._on_library_event()

        assert len(submitted) == 1
        fn, args = submitted[0]
        # Bound methods create new objects each time; compare by __func__ instead
        assert fn.__func__ is lib._worker_refresh.__func__

    def test_event_listener_stopped_on_select_server(self) -> None:
        """selectServer() stops the event listener before invalidating the client."""
        lib = self._make_lib()

        mock_listener = MagicMock()
        lib._event_listener = mock_listener

        lib.selectServer("new-server-id")

        mock_listener.stop.assert_called_once()
        assert lib._event_listener is None

    def test_event_listener_stopped_on_select_user(self) -> None:
        """selectUser() stops the event listener before invalidating the client."""
        lib = self._make_lib()

        mock_listener = MagicMock()
        lib._event_listener = mock_listener

        lib.selectUser(99)

        mock_listener.stop.assert_called_once()
        assert lib._event_listener is None

    def test_no_event_listener_when_no_client(self) -> None:
        """_start_event_listener does nothing when _client is None."""
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

        assert lib._event_listener is None


# ---------------------------------------------------------------------------
# PlexLibrary.rate — Task 008
# ---------------------------------------------------------------------------


class TestRateSlot:
    """rate() slot dispatches to executor and is a no-op when _client is None."""

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

    def test_rate_slot_dispatches_to_executor(self) -> None:
        """rate() submits client.rate to the executor with correct args."""
        lib = self._make_lib()
        mock_client = MagicMock()
        lib._client = mock_client

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append((fn, args))  # type: ignore[method-assign]

        lib.rate("123", 7.0)

        assert len(submitted) == 1
        fn, args = submitted[0]
        assert fn == mock_client.rate
        assert args == ("123", 7.0)

    def test_rate_slot_no_op_without_client(self) -> None:
        """rate() is a no-op when _client is None — no error raised."""
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        # Should not raise
        lib.rate("123", 7.0)

        assert len(submitted) == 0


# ---------------------------------------------------------------------------
# PlexLibrary.fetchArtistDetail — Task 004 (async listen screen)
# ---------------------------------------------------------------------------


def _run_fetch_worker_with_events(lib, method_name, *args):
    """Submit a fetch* call, run the captured worker synchronously, then flush Qt events.

    The new async slots (fetchArtistDetail, fetchAlbumDetail, etc.) use
    QueuedConnection for the private→public signal chain, so we must call
    processEvents() after the worker runs to deliver the queued signal.
    """
    from PySide6.QtCore import QCoreApplication
    submitted = []

    def fake_submit(fn, *a, **kw):
        submitted.append(fn)

    lib._executor.submit = fake_submit  # type: ignore[method-assign]
    getattr(lib, method_name)(*args)
    for fn in submitted:
        fn()
    QCoreApplication.processEvents()


class TestFetchArtistDetail:
    """fetchArtistDetail() emits artistDetailReady with artist metadata and albums."""

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

    def test_emits_artist_detail_ready_with_artist_and_albums(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "100",
            "title": "Test Artist",
            "summary": "A great artist.",
            "Genre": [{"tag": "Rock"}],
        }
        mock_client.get_hubs.return_value = [
            {
                "hubIdentifier": "artist.albums",
                "title": "Albums",
                "Metadata": [
                    {
                        "ratingKey": "200",
                        "title": "Album One",
                        "year": 2020,
                        "leafCount": 10,
                        "type": "album",
                    }
                ],
            }
        ]
        lib._client = mock_client

        received = []
        lib.artistDetailReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistDetail", "100")

        assert len(received) == 1
        rk, data = received[0]
        assert rk == "100"
        assert data["artist"]["ratingKey"] == "100"
        assert data["artist"]["title"] == "Test Artist"
        assert data["artist"]["summary"] == "A great artist."
        assert len(data["albums"]) == 2  # header + 1 album
        assert data["albums"][0]["type"] == "header"
        assert data["albums"][1]["type"] == "album"
        assert data["albums"][1]["ratingKey"] == "200"

    def test_no_op_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.fetchArtistDetail("100")

        assert len(submitted) == 0

    def test_emits_empty_artist_when_metadata_not_found(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = None
        mock_client.get_hubs.return_value = []
        lib._client = mock_client

        received = []
        lib.artistDetailReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistDetail", "999")

        assert len(received) == 1
        rk, data = received[0]
        assert rk == "999"
        assert data["artist"] == {}
        assert data["albums"] == []

    def test_albums_sorted_by_year_descending(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {"ratingKey": "100", "title": "Artist"}
        mock_client.get_hubs.return_value = [
            {
                "hubIdentifier": "artist.albums",
                "title": "Albums",
                "Metadata": [
                    {"ratingKey": "201", "title": "Old Album", "year": 2010, "leafCount": 5, "type": "album"},
                    {"ratingKey": "202", "title": "New Album", "year": 2022, "leafCount": 8, "type": "album"},
                ],
            }
        ]
        lib._client = mock_client

        received = []
        lib.artistDetailReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistDetail", "100")

        _, data = received[0]
        albums = [a for a in data["albums"] if a["type"] == "album"]
        assert albums[0]["year"] == 2022
        assert albums[1]["year"] == 2010


# ---------------------------------------------------------------------------
# PlexLibrary.fetchAlbumDetail — Task 004 (async listen screen)
# ---------------------------------------------------------------------------


class TestFetchAlbumDetail:
    """fetchAlbumDetail() emits albumDetailReady with album metadata and tracks."""

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

    def test_emits_album_detail_ready_with_album_and_tracks(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "200",
            "title": "Test Album",
            "year": 2021,
            "leafCount": 2,
            "parentTitle": "Test Artist",
            "summary": "A great album.",
            "studio": "Test Label",
            "Genre": [{"tag": "Rock"}],
            "userRating": 8.0,
        }
        mock_client.get_children.return_value = [
            {
                "type": "track",
                "ratingKey": "300",
                "title": "Track One",
                "index": 1,
                "duration": 240000,
                "parentTitle": "Test Album",
                "grandparentTitle": "Test Artist",
                "Media": [{"Part": [{"key": "/library/parts/300/file.mp3"}]}],
            },
            {
                "type": "track",
                "ratingKey": "301",
                "title": "Track Two",
                "index": 2,
                "duration": 200000,
                "parentTitle": "Test Album",
                "grandparentTitle": "Test Artist",
                "Media": [{"Part": [{"key": "/library/parts/301/file.mp3"}]}],
            },
        ]
        lib._client = mock_client

        received = []
        lib.albumDetailReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchAlbumDetail", "200")

        assert len(received) == 1
        rk, data = received[0]
        assert rk == "200"
        assert data["album"]["ratingKey"] == "200"
        assert data["album"]["title"] == "Test Album"
        assert data["album"]["year"] == 2021
        assert data["album"]["parentTitle"] == "Test Artist"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["ratingKey"] == "300"
        assert data["tracks"][0]["title"] == "Track One"
        assert data["tracks"][1]["ratingKey"] == "301"

    def test_no_op_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.fetchAlbumDetail("200")

        assert len(submitted) == 0

    def test_filters_out_non_track_children(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {"ratingKey": "200", "title": "Album"}
        mock_client.get_children.return_value = [
            {"type": "track", "ratingKey": "300", "title": "Track One", "index": 1},
            {"type": "album", "ratingKey": "999", "title": "Not a track"},
        ]
        lib._client = mock_client

        received = []
        lib.albumDetailReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchAlbumDetail", "200")

        _, data = received[0]
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["ratingKey"] == "300"


# ---------------------------------------------------------------------------
# PlexLibrary.fetchRecentAlbums — Task 004 (async listen screen)
# ---------------------------------------------------------------------------


class TestFetchRecentAlbums:
    """fetchRecentAlbums() emits recentAlbumsReady with a list of album dicts."""

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

    def test_emits_recent_albums_ready(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "type": "album",
                        "ratingKey": "200",
                        "title": "Recent Album",
                        "year": 2023,
                        "parentTitle": "Some Artist",
                    }
                ]
            }
        }
        lib._client = mock_client

        received = []
        lib.recentAlbumsReady.connect(lambda d: received.append(d))
        _run_fetch_worker_with_events(lib, "fetchRecentAlbums", "3")

        assert len(received) == 1
        albums = received[0]
        assert len(albums) == 1
        assert albums[0]["ratingKey"] == "200"
        assert albums[0]["title"] == "Recent Album"
        assert albums[0]["year"] == 2023
        assert albums[0]["parentTitle"] == "Some Artist"

    def test_no_op_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.fetchRecentAlbums("3")

        assert len(submitted) == 0

    def test_filters_out_non_album_items(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"type": "album", "ratingKey": "200", "title": "Album"},
                    {"type": "track", "ratingKey": "300", "title": "Track"},
                ]
            }
        }
        lib._client = mock_client

        received = []
        lib.recentAlbumsReady.connect(lambda d: received.append(d))
        _run_fetch_worker_with_events(lib, "fetchRecentAlbums", "3")

        albums = received[0]
        assert len(albums) == 1
        assert albums[0]["ratingKey"] == "200"

    def test_emits_empty_list_when_no_data(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = None
        lib._client = mock_client

        received = []
        lib.recentAlbumsReady.connect(lambda d: received.append(d))
        _run_fetch_worker_with_events(lib, "fetchRecentAlbums", "3")

        assert len(received) == 1
        assert received[0] == []


# ---------------------------------------------------------------------------
# PlexLibrary.fetchPlaylists — Task 004 (async listen screen)
# ---------------------------------------------------------------------------


class TestFetchPlaylists:
    """fetchPlaylists() emits playlistsReady with a list of audio playlist dicts."""

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

    def test_emits_playlists_ready_with_audio_playlists(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {
                "ratingKey": "500",
                "title": "My Playlist",
                "playlistType": "audio",
                "leafCount": 10,
                "duration": 3600000,
                "smart": False,
            }
        ]
        lib._client = mock_client

        received = []
        lib.playlistsReady.connect(lambda d: received.append(d))
        _run_fetch_worker_with_events(lib, "fetchPlaylists")

        assert len(received) == 1
        playlists = received[0]
        assert len(playlists) == 1
        assert playlists[0]["ratingKey"] == "500"
        assert playlists[0]["title"] == "My Playlist"
        assert playlists[0]["leafCount"] == 10

    def test_no_op_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.fetchPlaylists()

        assert len(submitted) == 0

    def test_filters_out_non_audio_playlists(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {"ratingKey": "500", "title": "Audio PL", "playlistType": "audio", "leafCount": 5, "duration": 0, "smart": False},
            {"ratingKey": "501", "title": "Video PL", "playlistType": "video", "leafCount": 3, "duration": 0, "smart": False},
        ]
        lib._client = mock_client

        received = []
        lib.playlistsReady.connect(lambda d: received.append(d))
        _run_fetch_worker_with_events(lib, "fetchPlaylists")

        playlists = received[0]
        assert len(playlists) == 1
        assert playlists[0]["ratingKey"] == "500"


# ---------------------------------------------------------------------------
# PlexLibrary.fetchPlaylistTracks — Task 004 (async listen screen)
# ---------------------------------------------------------------------------


class TestFetchPlaylistTracks:
    """fetchPlaylistTracks() emits playlistTracksReady with a list of track dicts."""

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

    def test_emits_playlist_tracks_ready(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = [
            {
                "type": "track",
                "ratingKey": "300",
                "title": "Track One",
                "index": 1,
                "duration": 240000,
                "parentTitle": "Album",
                "grandparentTitle": "Artist",
                "Media": [{"Part": [{"key": "/library/parts/300/file.mp3"}]}],
            }
        ]
        lib._client = mock_client

        received = []
        lib.playlistTracksReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchPlaylistTracks", "500")

        assert len(received) == 1
        rk, tracks = received[0]
        assert rk == "500"
        assert len(tracks) == 1
        assert tracks[0]["ratingKey"] == "300"
        assert tracks[0]["title"] == "Track One"
        assert tracks[0]["durationMs"] == 240000
        assert tracks[0]["parentTitle"] == "Album"
        assert tracks[0]["grandparentTitle"] == "Artist"

    def test_no_op_when_no_client(self) -> None:
        lib = self._make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *args, **kwargs: submitted.append(fn)  # type: ignore[method-assign]

        lib.fetchPlaylistTracks("500")

        assert len(submitted) == 0

    def test_emits_empty_list_when_no_items(self) -> None:
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = []
        lib._client = mock_client

        received = []
        lib.playlistTracksReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchPlaylistTracks", "500")

        assert len(received) == 1
        rk, tracks = received[0]
        assert rk == "500"
        assert tracks == []

    def test_rating_key_passed_through_signal(self) -> None:
        """The rating_key in the signal matches the one passed to fetchPlaylistTracks."""
        lib = self._make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = []
        lib._client = mock_client

        received_keys = []
        lib.playlistTracksReady.connect(lambda rk, d: received_keys.append(rk))
        _run_fetch_worker_with_events(lib, "fetchPlaylistTracks", "my-playlist-key")

        assert received_keys == ["my-playlist-key"]


# ---------------------------------------------------------------------------
# Task 005 — Disk cache: libraries, on-deck, movies, shows
# ---------------------------------------------------------------------------


def _make_lib_with_tmp(tmp_path):
    """Create a PlexLibrary with CONFIG_DIR patched to tmp_path."""
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR"), \
         patch("backend.plex_library.CONFIG_DIR", tmp_path):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)
    return lib


class TestLibrariesDiskCache:
    """_save_libraries_cache / _load_libraries_cache round-trip."""

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        libraries = [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
        ]
        with patch("backend.plex_library.CONFIG_DIR", tmp_path):
            lib._save_libraries_cache(libraries)
            loaded = lib._load_libraries_cache()

        assert loaded == libraries

    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            result = lib._load_libraries_cache()
        assert result is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "libraries_cache.json").write_text("not valid json", encoding="utf-8")
        with patch("backend.plex_library._PLEX_CACHE_DIR", cache_dir):
            result = lib._load_libraries_cache()
        assert result is None

    def test_on_libraries_ready_saves_cache(self, tmp_path: Path) -> None:
        """_on_libraries_ready calls _save_libraries_cache after updating the model."""
        lib = _make_lib_with_tmp(tmp_path)
        libraries = [{"key": "1", "title": "Movies", "type": "movie"}]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_libraries_ready(libraries)
            loaded = lib._load_libraries_cache()

        assert loaded == libraries
        assert lib._libraries_model.rowCount() == 1

    def test_cache_path_is_correct(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            path = lib._libraries_cache_path()
        assert path.name == "libraries_cache.json"
        assert path.parent.name == "plex_cache"


class TestOnDeckDiskCache:
    """_save_ondeck_cache / _load_ondeck_cache round-trip."""

    def _make_ondeck_items(self):
        return [
            {
                "rating_key": "100",
                "title": "Episode 1",
                "type": "episode",
                "poster_local": "file:///tmp/poster.jpg",
                "grandparent_title": "My Show",
                "view_offset": 60000,
                "duration": 2700000,
                "thumb_path": "/library/metadata/100/thumb/1",
            }
        ]

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        items = self._make_ondeck_items()
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_ondeck_cache(items)
            loaded = lib._load_ondeck_cache()
        assert loaded == items

    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            result = lib._load_ondeck_cache()
        assert result is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "ondeck_cache.json").write_text("{bad json", encoding="utf-8")
        with patch("backend.plex_library._PLEX_CACHE_DIR", cache_dir):
            result = lib._load_ondeck_cache()
        assert result is None

    def test_on_on_deck_ready_saves_cache(self, tmp_path: Path) -> None:
        """_on_on_deck_ready saves processed items to disk cache."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None  # prevent poster fetch attempts
        raw_items = [
            {
                "ratingKey": "100",
                "title": "Episode 1",
                "type": "episode",
                "thumb": "/library/metadata/100/thumb/1",
                "grandparentTitle": "My Show",
                "viewOffset": 60000,
                "duration": 2700000,
            }
        ]
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_on_deck_ready(raw_items)
            loaded = lib._load_ondeck_cache()

        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["rating_key"] == "100"
        assert loaded[0]["title"] == "Episode 1"
        assert loaded[0]["type"] == "episode"
        assert loaded[0]["grandparent_title"] == "My Show"
        assert loaded[0]["view_offset"] == 60000
        assert loaded[0]["duration"] == 2700000

    def test_cache_path_is_correct(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            path = lib._ondeck_cache_path()
        assert path.name == "ondeck_cache.json"
        assert path.parent.name == "plex_cache"

    def test_on_ondeck_cache_ready_sets_ondeck_model(self, tmp_path: Path) -> None:
        """_on_on_deck_cache_ready populates the on-deck model from startup cache data."""
        lib = _make_lib_with_tmp(tmp_path)
        items = self._make_ondeck_items()
        lib._on_on_deck_cache_ready(items)
        assert lib._on_deck_model.rowCount() == 1
        from backend.plex_library import PlexOnDeckModel
        idx = lib._on_deck_model.index(0, 0)
        assert lib._on_deck_model.data(idx, PlexOnDeckModel.TitleRole) == "Episode 1"


class TestMoviesDiskCache:
    """_save_movies_cache / _load_movies_cache round-trip."""

    def _make_movie(self, rating_key="1", title="Test Movie"):
        from backend.plex_models import PlexMovie
        return PlexMovie(
            rating_key=rating_key,
            title=title,
            year=2020,
            summary="A test movie.",
            content_rating="PG-13",
            audience_rating=8.5,
            duration_ms=7200000,
            studio="Test Studio",
            tagline="A tagline",
            thumb_path="/library/metadata/1/thumb/1",
            art_path="/library/metadata/1/art/1",
            genres=["Action", "Comedy"],
            directors=["Director A"],
            cast=["Actor A", "Actor B"],
            added_at=1700000000,
            view_offset=0,
            poster_local="file:///tmp/poster.jpg",
        )

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Movie One"), self._make_movie("2", "Movie Two")]
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_movies_cache("4", movies)
            loaded = lib._load_movies_cache("4")

        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0].rating_key == "1"
        assert loaded[0].title == "Movie One"
        assert loaded[0].year == 2020
        assert loaded[0].summary == "A test movie."
        assert loaded[0].content_rating == "PG-13"
        assert loaded[0].audience_rating == 8.5
        assert loaded[0].duration_ms == 7200000
        assert loaded[0].studio == "Test Studio"
        assert loaded[0].tagline == "A tagline"
        assert loaded[0].thumb_path == "/library/metadata/1/thumb/1"
        assert loaded[0].art_path == "/library/metadata/1/art/1"
        assert loaded[0].genres == ["Action", "Comedy"]
        assert loaded[0].directors == ["Director A"]
        assert loaded[0].cast == ["Actor A", "Actor B"]
        assert loaded[0].added_at == 1700000000
        assert loaded[0].view_offset == 0
        assert loaded[0].poster_local == "file:///tmp/poster.jpg"
        assert loaded[1].rating_key == "2"
        assert loaded[1].title == "Movie Two"

    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            result = lib._load_movies_cache("4")
        assert result is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "movies_cache_4.json").write_text("not json", encoding="utf-8")
        with patch("backend.plex_library._PLEX_CACHE_DIR", cache_dir):
            result = lib._load_movies_cache("4")
        assert result is None

    def test_cache_is_section_key_scoped(self, tmp_path: Path) -> None:
        """Movies caches for different section keys are independent."""
        lib = _make_lib_with_tmp(tmp_path)
        movies_4 = [self._make_movie("1", "Movie A")]
        movies_5 = [self._make_movie("2", "Movie B")]
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_movies_cache("4", movies_4)
            lib._save_movies_cache("5", movies_5)
            loaded_4 = lib._load_movies_cache("4")
            loaded_5 = lib._load_movies_cache("5")

        assert loaded_4[0].title == "Movie A"
        assert loaded_5[0].title == "Movie B"

    def test_cache_path_includes_section_key(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            path = lib._movies_cache_path("42")
        assert path.name == "movies_cache_42.json"

    def test_on_movies_ready_saves_cache_on_first_page(self, tmp_path: Path) -> None:
        """_on_movies_ready saves cache only on the first page (_movies_loaded == 0)."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None  # prevent poster fetch attempts
        lib._movies_loaded = 0
        lib._current_section_key = "4"
        movies = [self._make_movie("1", "Movie One")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_movies_ready(movies, 1)
            loaded = lib._load_movies_cache("4")

        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].title == "Movie One"

    def test_on_movies_ready_does_not_save_cache_on_subsequent_pages(self, tmp_path: Path) -> None:
        """_on_movies_ready does NOT save cache on subsequent pages."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None
        lib._movies_loaded = 50  # simulate second page
        lib._current_section_key = "4"
        movies = [self._make_movie("51", "Movie 51")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_movies_ready(movies, 100)
            loaded = lib._load_movies_cache("4")

        # Cache should not exist (no first-page save happened)
        assert loaded is None

    def test_on_all_caches_ready_replaces_movies_model(self, tmp_path: Path) -> None:
        """_on_movies_cache_ready populates the movies model from startup cache data."""
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Cached Movie")]
        lib._movies_loaded = 0

        lib._on_movies_cache_ready(movies, "4")

        assert lib._movies_model.rowCount() == 1
        from backend.plex_library import PlexMovieListModel
        idx = lib._movies_model.index(0, 0)
        assert lib._movies_model.data(idx, PlexMovieListModel.TitleRole) == "Cached Movie"
        # Pagination counters must NOT be affected by cache load
        assert lib._movies_loaded == 0

    def test_worker_load_section_does_not_emit_cache(self, tmp_path: Path) -> None:
        """_worker_load_section no longer emits cache — startup cache handles that."""
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Cached Movie")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_movies_cache("4", movies)

        network_signals: list = []
        lib._moviesReady.connect(lambda m, t: network_signals.append(m))

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._worker_load_section(mock_client, "4", "movie")

        # Only the network signal fires (with empty result), no cache signal
        assert len(network_signals) == 1
        assert network_signals[0] == []


class TestShowsDiskCache:
    """_save_shows_cache / _load_shows_cache round-trip."""

    def _make_show(self, rating_key="1", title="Test Show"):
        from backend.plex_models import PlexShow
        return PlexShow(
            rating_key=rating_key,
            title=title,
            year=2019,
            summary="A test show.",
            content_rating="TV-MA",
            audience_rating=9.0,
            thumb_path="/library/metadata/1/thumb/1",
            art_path="/library/metadata/1/art/1",
            genres=["Drama", "Sci-Fi"],
            cast=["Actor A"],
            child_count=3,
            leaf_count=30,
            viewed_leaf_count=15,
            poster_local="file:///tmp/show_poster.jpg",
        )

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        shows = [self._make_show("1", "Show One"), self._make_show("2", "Show Two")]
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_shows_cache("3", shows)
            loaded = lib._load_shows_cache("3")

        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0].rating_key == "1"
        assert loaded[0].title == "Show One"
        assert loaded[0].year == 2019
        assert loaded[0].summary == "A test show."
        assert loaded[0].content_rating == "TV-MA"
        assert loaded[0].audience_rating == 9.0
        assert loaded[0].thumb_path == "/library/metadata/1/thumb/1"
        assert loaded[0].art_path == "/library/metadata/1/art/1"
        assert loaded[0].genres == ["Drama", "Sci-Fi"]
        assert loaded[0].cast == ["Actor A"]
        assert loaded[0].child_count == 3
        assert loaded[0].leaf_count == 30
        assert loaded[0].viewed_leaf_count == 15
        assert loaded[0].poster_local == "file:///tmp/show_poster.jpg"
        assert loaded[1].rating_key == "2"
        assert loaded[1].title == "Show Two"

    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            result = lib._load_shows_cache("3")
        assert result is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "shows_cache_3.json").write_text("not json", encoding="utf-8")
        with patch("backend.plex_library._PLEX_CACHE_DIR", cache_dir):
            result = lib._load_shows_cache("3")
        assert result is None

    def test_cache_is_section_key_scoped(self, tmp_path: Path) -> None:
        """Shows caches for different section keys are independent."""
        lib = _make_lib_with_tmp(tmp_path)
        shows_3 = [self._make_show("1", "Show A")]
        shows_6 = [self._make_show("2", "Show B")]
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_shows_cache("3", shows_3)
            lib._save_shows_cache("6", shows_6)
            loaded_3 = lib._load_shows_cache("3")
            loaded_6 = lib._load_shows_cache("6")

        assert loaded_3[0].title == "Show A"
        assert loaded_6[0].title == "Show B"

    def test_cache_path_includes_section_key(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            path = lib._shows_cache_path("99")
        assert path.name == "shows_cache_99.json"

    def test_on_shows_ready_saves_cache_on_first_page(self, tmp_path: Path) -> None:
        """_on_shows_ready saves cache only on the first page (_shows_loaded == 0)."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None
        lib._shows_loaded = 0
        lib._current_section_key = "3"
        shows = [self._make_show("1", "Show One")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_shows_ready(shows, 1)
            loaded = lib._load_shows_cache("3")

        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].title == "Show One"

    def test_on_shows_ready_does_not_save_cache_on_subsequent_pages(self, tmp_path: Path) -> None:
        """_on_shows_ready does NOT save cache on subsequent pages."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None
        lib._shows_loaded = 50  # simulate second page
        lib._current_section_key = "3"
        shows = [self._make_show("51", "Show 51")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_shows_ready(shows, 100)
            loaded = lib._load_shows_cache("3")

        assert loaded is None

    def test_on_all_caches_ready_replaces_shows_model(self, tmp_path: Path) -> None:
        """_on_shows_cache_ready populates the shows model from startup cache data."""
        lib = _make_lib_with_tmp(tmp_path)
        shows = [self._make_show("1", "Cached Show")]
        lib._shows_loaded = 0

        lib._on_shows_cache_ready(shows, "3")

        assert lib._shows_model.rowCount() == 1
        from backend.plex_library import PlexShowListModel
        idx = lib._shows_model.index(0, 0)
        assert lib._shows_model.data(idx, PlexShowListModel.TitleRole) == "Cached Show"
        # Pagination counters must NOT be affected by cache load
        assert lib._shows_loaded == 0

    def test_worker_load_section_does_not_emit_cache(self, tmp_path: Path) -> None:
        """_worker_load_section no longer emits cache — startup cache handles that."""
        lib = _make_lib_with_tmp(tmp_path)
        shows = [self._make_show("1", "Cached Show")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_shows_cache("3", shows)

        network_signals: list = []
        lib._showsReady.connect(lambda s, t: network_signals.append(s))

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = ([], 0)

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._worker_load_section(mock_client, "3", "show")

        # Only the network signal fires (with empty result), no cache signal
        assert len(network_signals) == 1
        assert network_signals[0] == []


class TestWorkerRefreshLibrariesCache:
    """_worker_refresh pre-emits cached data then emits network data."""

    def _make_lib(self, tmp_path):
        return _make_lib_with_tmp(tmp_path)

    def test_worker_refresh_emits_cache_then_network_libraries(self, tmp_path: Path) -> None:
        """_worker_refresh pre-emits cached libraries, then emits network libraries."""
        lib = self._make_lib(tmp_path)
        libraries = [{"key": "1", "title": "Movies", "type": "movie"}]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_libraries_cache(libraries)

        emitted: list = []
        lib._librariesReady.connect(lambda libs: emitted.append(libs))

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {"machineIdentifier": "abc123"}
        mock_client.get_libraries.return_value = [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
        ]
        mock_client.get_on_deck.return_value = []

        lib._worker_refresh(mock_client)

        # Two emits: first from cache, then from network
        assert len(emitted) == 2
        assert len(emitted[0]) == 1     # cache data (1 library)
        assert len(emitted[1]) == 2     # network data (2 libraries)

    def test_worker_refresh_skips_cache_emit_when_no_cache(self, tmp_path: Path) -> None:
        """When no libraries cache exists, _worker_refresh only emits network data."""
        lib = self._make_lib(tmp_path)

        emitted: list = []
        lib._librariesReady.connect(lambda libs: emitted.append(libs))

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {"machineIdentifier": "abc123"}
        mock_client.get_libraries.return_value = [
            {"key": "1", "title": "Movies", "type": "movie"},
        ]
        mock_client.get_on_deck.return_value = []

        lib._worker_refresh(mock_client)

        assert len(emitted) == 1  # only network data (no cache to pre-emit)


class TestWorkerRefreshOnDeckCache:
    """_worker_refresh no longer pre-emits on-deck cache (startup cache handles that)."""

    def _make_lib(self, tmp_path):
        return _make_lib_with_tmp(tmp_path)

    def test_worker_refresh_does_not_emit_ondeck_cache(self, tmp_path: Path) -> None:
        """_worker_refresh no longer emits cached on-deck — startup cache handles that."""
        lib = self._make_lib(tmp_path)
        cached_items = [
            {
                "rating_key": "100",
                "title": "Episode 1",
                "type": "episode",
                "poster_local": "",
                "grandparent_title": "My Show",
                "view_offset": 0,
                "duration": 2700000,
                "thumb_path": "/thumb/100",
            }
        ]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_ondeck_cache(cached_items)

        ondeck_emitted: list = []
        lib._onDeckReady.connect(lambda items: ondeck_emitted.append(items))

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {"machineIdentifier": "abc123"}
        mock_client.get_libraries.return_value = []
        mock_client.get_on_deck.return_value = []

        lib._worker_refresh(mock_client)

        # _onDeckReady fires once with network result (empty list)
        assert len(ondeck_emitted) == 1
        assert ondeck_emitted[0] == []

    def test_worker_refresh_skips_ondeck_for_restricted_users(self, tmp_path: Path) -> None:
        """On-deck is not fetched for restricted users (content_rating_filter set)."""
        lib = self._make_lib(tmp_path)
        lib._content_rating_filter = "G,PG"  # restricted user

        ondeck_emitted: list = []
        lib._onDeckReady.connect(lambda items: ondeck_emitted.append(items))

        mock_client = MagicMock()
        mock_client.get_identity.return_value = {"machineIdentifier": "abc123"}
        mock_client.get_libraries.return_value = []

        lib._worker_refresh(mock_client)

        # Restricted users get an empty on-deck emit (to clear stale data)
        assert len(ondeck_emitted) == 1
        assert ondeck_emitted[0] == []


# ---------------------------------------------------------------------------
# Task 006 — Startup cache: _worker_load_all_caches + state cache
# ---------------------------------------------------------------------------


class TestStateCacheHelpers:
    """_save_state_cache / _load_state_cache round-trip."""

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_state_cache("last_movie_section", "4")
            lib._save_state_cache("last_show_section", "3")
            state = lib._load_state_cache()

        assert state["last_movie_section"] == "4"
        assert state["last_show_section"] == "3"

    def test_load_returns_empty_dict_when_no_file(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            state = lib._load_state_cache()
        assert state == {}

    def test_load_returns_empty_dict_on_corrupt_json(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "state.json").write_text("not json", encoding="utf-8")
        with patch("backend.plex_library._PLEX_CACHE_DIR", cache_dir):
            state = lib._load_state_cache()
        assert state == {}

    def test_save_updates_existing_key(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_state_cache("last_movie_section", "4")
            lib._save_state_cache("last_movie_section", "7")
            state = lib._load_state_cache()
        assert state["last_movie_section"] == "7"

    def test_save_preserves_other_keys(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_state_cache("last_movie_section", "4")
            lib._save_state_cache("last_show_section", "3")
            # Update only movie section
            lib._save_state_cache("last_movie_section", "9")
            state = lib._load_state_cache()
        assert state["last_movie_section"] == "9"
        assert state["last_show_section"] == "3"

    def test_on_movies_ready_saves_state(self, tmp_path: Path) -> None:
        """_on_movies_ready saves last_movie_section to state.json on first page."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None
        lib._movies_loaded = 0
        lib._current_section_key = "4"
        from backend.plex_models import PlexMovie
        movies = [PlexMovie(rating_key="1", title="Movie")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_movies_ready(movies, 1)
            state = lib._load_state_cache()

        assert state.get("last_movie_section") == "4"

    def test_on_shows_ready_saves_state(self, tmp_path: Path) -> None:
        """_on_shows_ready saves last_show_section to state.json on first page."""
        lib = _make_lib_with_tmp(tmp_path)
        lib._client = None
        lib._shows_loaded = 0
        lib._current_section_key = "3"
        from backend.plex_models import PlexShow
        shows = [PlexShow(rating_key="1", title="Show")]

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._on_shows_ready(shows, 1)
            state = lib._load_state_cache()

        assert state.get("last_show_section") == "3"


class _RemovedWorkerLoadAllCaches:
    """Removed — _allCachesReady signal no longer exists."""

    def _make_movie(self, rating_key="1", title="Movie"):
        from backend.plex_models import PlexMovie
        return PlexMovie(rating_key=rating_key, title=title, year=2020)

    def _make_show(self, rating_key="1", title="Show"):
        from backend.plex_models import PlexShow
        return PlexShow(rating_key=rating_key, title=title, year=2019)

    def test_emits_all_caches_ready_with_empty_when_no_files(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        emitted: list = []
        lib._allCachesReady.connect(lambda d: emitted.append(d))

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._worker_load_all_caches()

        assert len(emitted) == 1
        assert emitted[0]["libraries"] == []
        assert emitted[0]["ondeck"] == []
        assert emitted[0]["movies"] == []
        assert emitted[0]["shows"] == []

    def test_emits_libraries_from_cache(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        libraries = [{"key": "1", "title": "Movies", "type": "movie"}]

        emitted: list = []
        lib._allCachesReady.connect(lambda d: emitted.append(d))

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_libraries_cache(libraries)
            lib._worker_load_all_caches()

        assert emitted[0]["libraries"] == libraries

    def test_emits_movies_from_cache_when_state_has_section(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Cached Movie")]

        emitted: list = []
        lib._allCachesReady.connect(lambda d: emitted.append(d))

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_movies_cache("4", movies)
            lib._save_state_cache("last_movie_section", "4")
            lib._worker_load_all_caches()

        assert len(emitted[0]["movies"]) == 1
        assert emitted[0]["movies"][0].title == "Cached Movie"
        assert emitted[0]["movie_section"] == "4"

    def test_emits_shows_from_cache_when_state_has_section(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        shows = [self._make_show("1", "Cached Show")]

        emitted: list = []
        lib._allCachesReady.connect(lambda d: emitted.append(d))

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_shows_cache("3", shows)
            lib._save_state_cache("last_show_section", "3")
            lib._worker_load_all_caches()

        assert len(emitted[0]["shows"]) == 1
        assert emitted[0]["shows"][0].title == "Cached Show"
        assert emitted[0]["show_section"] == "3"

    def test_skips_movies_when_no_state_section(self, tmp_path: Path) -> None:
        """If state has no last_movie_section, movies cache is not loaded."""
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Movie")]

        emitted: list = []
        lib._allCachesReady.connect(lambda d: emitted.append(d))

        with patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"):
            lib._save_movies_cache("4", movies)
            # No state file — no last_movie_section
            lib._worker_load_all_caches()

        assert emitted[0]["movies"] == []


class _RemovedOnAllCachesReady:
    """Removed — _on_all_caches_ready no longer exists."""

    def _make_movie(self, rating_key="1", title="Movie"):
        from backend.plex_models import PlexMovie
        return PlexMovie(rating_key=rating_key, title=title, year=2020)

    def _make_show(self, rating_key="1", title="Show"):
        from backend.plex_models import PlexShow
        return PlexShow(rating_key=rating_key, title=title, year=2019)

    def test_populates_libraries_model(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        libraries = [{"key": "1", "title": "Movies", "type": "movie"}]
        signals: list = []
        lib.librariesModelChanged.connect(lambda: signals.append(True))

        lib._on_all_caches_ready({
            "libraries": libraries, "ondeck": [], "movies": [], "shows": [],
            "movie_section": "", "show_section": "",
        })

        assert lib._libraries_model.rowCount() == 1
        assert len(signals) == 1

    def test_populates_ondeck_model(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        ondeck = [{"rating_key": "1", "title": "Ep 1", "type": "episode",
                   "poster_local": "", "grandparent_title": "Show",
                   "view_offset": 0, "duration": 1000, "thumb_path": ""}]
        signals: list = []
        lib.onDeckModelChanged.connect(lambda: signals.append(True))

        lib._on_all_caches_ready({
            "libraries": [], "ondeck": ondeck, "movies": [], "shows": [],
            "movie_section": "", "show_section": "",
        })

        assert lib._on_deck_model.rowCount() == 1
        assert len(signals) == 1

    def test_populates_movies_model_and_sets_section(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Movie")]
        signals: list = []
        lib.moviesModelChanged.connect(lambda: signals.append(True))

        lib._on_all_caches_ready({
            "libraries": [], "ondeck": [], "movies": movies, "shows": [],
            "movie_section": "4", "show_section": "",
        })

        assert lib._movies_model.rowCount() == 1
        assert lib._current_section_key == "4"
        assert lib._current_section_type == "movie"
        assert len(signals) == 1

    def test_populates_shows_model_and_sets_section(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        shows = [self._make_show("1", "Show")]
        signals: list = []
        lib.showsModelChanged.connect(lambda: signals.append(True))

        lib._on_all_caches_ready({
            "libraries": [], "ondeck": [], "movies": [], "shows": shows,
            "movie_section": "", "show_section": "3",
        })

        assert lib._shows_model.rowCount() == 1
        assert lib._current_section_key == "3"
        assert lib._current_section_type == "show"
        assert len(signals) == 1

    def test_movies_section_takes_priority_over_shows(self, tmp_path: Path) -> None:
        """When both movies and shows are cached, movie_section wins for current_section_key."""
        lib = _make_lib_with_tmp(tmp_path)
        movies = [self._make_movie("1", "Movie")]
        shows = [self._make_show("2", "Show")]

        lib._on_all_caches_ready({
            "libraries": [], "ondeck": [], "movies": movies, "shows": shows,
            "movie_section": "4", "show_section": "3",
        })

        # movies set section first; shows should not overwrite
        assert lib._current_section_key == "4"
        assert lib._current_section_type == "movie"

    def test_no_signals_emitted_for_empty_data(self, tmp_path: Path) -> None:
        lib = _make_lib_with_tmp(tmp_path)
        lib_signals: list = []
        lib.librariesModelChanged.connect(lambda: lib_signals.append(True))
        movie_signals: list = []
        lib.moviesModelChanged.connect(lambda: movie_signals.append(True))

        lib._on_all_caches_ready({
            "libraries": [], "ondeck": [], "movies": [], "shows": [],
            "movie_section": "", "show_section": "",
        })

        assert len(lib_signals) == 0
        assert len(movie_signals) == 0
