"""Tests for Task 002 (harden) — async fetchMovie / fetchShow / fetchSeasons / fetchEpisodes.

Covers:
  - fetchMovie emits movieReady with correct rating_key and dict on success
  - fetchMovie emits movieReady with empty dict when _client is None
  - fetchShow emits showReady with correct rating_key and dict on success
  - fetchSeasons emits seasonsReady with correct rating_key and list on success
  - fetchEpisodes emits episodesReady with correct rating_key and list on success
  - Signal carries the rating_key (stale-response guard relies on this in QML)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.plex_library import PlexLibrary


# ---------------------------------------------------------------------------
# Shared helpers
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
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


def _make_lib():
    """Create a PlexLibrary instance with mocked dependencies."""
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


def _run_worker(lib, method_name, *args):
    """Call a fetch* method synchronously by intercepting executor.submit."""
    submitted = []

    def fake_submit(fn, *a, **kw):
        submitted.append(fn)

    lib._executor.submit = fake_submit  # type: ignore[method-assign]
    getattr(lib, method_name)(*args)
    # Run the captured worker synchronously
    for fn in submitted:
        fn()


# ---------------------------------------------------------------------------
# fetchMovie
# ---------------------------------------------------------------------------


class TestFetchMovie:
    def test_emits_movie_ready_with_correct_rating_key_and_dict(self) -> None:
        """fetchMovie emits movieReady with the rating_key and a populated dict."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "123",
            "title": "Test Movie",
            "year": 2020,
            "summary": "A test movie.",
            "contentRating": "PG-13",
            "audienceRating": 8.5,
            "duration": 7200000,
            "studio": "Test Studio",
            "tagline": "A tagline",
            "Genre": [{"tag": "Action"}],
            "Director": [{"tag": "Director A"}],
            "Role": [{"tag": "Actor A"}],
        }
        lib._client = mock_client

        received = []
        lib.movieReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchMovie", "123")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "123"
        assert d["ratingKey"] == "123"
        assert d["title"] == "Test Movie"
        assert d["year"] == 2020
        assert d["summary"] == "A test movie."
        assert d["contentRating"] == "PG-13"
        assert d["audienceRating"] == 8.5
        assert d["genres"] == ["Action"]
        assert d["directors"] == ["Director A"]
        assert d["cast"] == ["Actor A"]

    def test_emits_movie_ready_with_empty_dict_when_client_is_none(self) -> None:
        """fetchMovie emits movieReady({}) immediately when _client is None."""
        lib = _make_lib()
        lib._client = None

        received = []
        lib.movieReady.connect(lambda rk, d: received.append((rk, d)))

        # No executor needed — emits synchronously
        lib.fetchMovie("999")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "999"
        assert d == {}

    def test_emits_movie_ready_with_empty_dict_when_metadata_not_found(self) -> None:
        """fetchMovie emits movieReady({}) when get_metadata returns None."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = None
        lib._client = mock_client

        received = []
        lib.movieReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchMovie", "404")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "404"
        assert d == {}

    def test_rating_key_carried_in_signal_for_stale_guard(self) -> None:
        """movieReady always carries the rating_key so QML can discard stale responses."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {"ratingKey": "42", "title": "Movie"}
        lib._client = mock_client

        received_keys = []
        lib.movieReady.connect(lambda rk, d: received_keys.append(rk))

        _run_worker(lib, "fetchMovie", "42")

        assert received_keys == ["42"]

    def test_poster_local_populated_via_cache(self) -> None:
        """fetchMovie populates posterLocal via the poster cache."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "123",
            "title": "Movie",
            "thumb": "/library/metadata/123/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster.jpg"
        lib._poster_cache = mock_cache

        received = []
        lib.movieReady.connect(lambda rk, d: received.append(d))

        _run_worker(lib, "fetchMovie", "123")

        assert received[0]["posterLocal"] == "file:///tmp/poster.jpg"
        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/123/thumb/1"
        )


# ---------------------------------------------------------------------------
# fetchShow
# ---------------------------------------------------------------------------


class TestFetchShow:
    def test_emits_show_ready_with_correct_rating_key_and_dict(self) -> None:
        """fetchShow emits showReady with the rating_key and a populated dict."""
        lib = _make_lib()
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

        _run_worker(lib, "fetchShow", "200")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "200"
        assert d["ratingKey"] == "200"
        assert d["title"] == "Test Show"
        assert d["year"] == 2018
        assert d["childCount"] == 3
        assert d["leafCount"] == 30
        assert d["viewedLeafCount"] == 15
        assert d["genres"] == ["Drama", "Sci-Fi"]
        assert d["cast"] == ["Actor A", "Actor B"]

    def test_emits_show_ready_with_empty_dict_when_client_is_none(self) -> None:
        """fetchShow emits showReady({}) immediately when _client is None."""
        lib = _make_lib()
        lib._client = None

        received = []
        lib.showReady.connect(lambda rk, d: received.append((rk, d)))

        lib.fetchShow("200")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "200"
        assert d == {}

    def test_emits_show_ready_with_empty_dict_when_metadata_not_found(self) -> None:
        """fetchShow emits showReady({}) when get_metadata returns None."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = None
        lib._client = mock_client

        received = []
        lib.showReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchShow", "404")

        assert len(received) == 1
        rk, d = received[0]
        assert rk == "404"
        assert d == {}


# ---------------------------------------------------------------------------
# fetchSeasons
# ---------------------------------------------------------------------------


class TestFetchSeasons:
    def test_emits_seasons_ready_with_correct_rating_key_and_list(self) -> None:
        """fetchSeasons emits seasonsReady with the rating_key and a populated list."""
        lib = _make_lib()
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
                "leafCount": 10,
                "viewedLeafCount": 0,
                "parentRatingKey": "200",
            },
        ]
        lib._client = mock_client

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchSeasons", "200")

        assert len(received) == 1
        rk, seasons = received[0]
        assert rk == "200"
        assert len(seasons) == 2
        assert seasons[0]["ratingKey"] == "300"
        assert seasons[0]["title"] == "Season 1"
        assert seasons[0]["index"] == 1
        assert seasons[0]["leafCount"] == 8
        assert seasons[0]["viewedLeafCount"] == 5
        assert seasons[0]["parentRatingKey"] == "200"
        assert seasons[1]["ratingKey"] == "301"

    def test_emits_seasons_ready_with_empty_list_when_client_is_none(self) -> None:
        """fetchSeasons emits seasonsReady([]) immediately when _client is None."""
        lib = _make_lib()
        lib._client = None

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))

        lib.fetchSeasons("200")

        assert len(received) == 1
        rk, seasons = received[0]
        assert rk == "200"
        assert seasons == []

    def test_filters_out_non_season_items(self) -> None:
        """fetchSeasons only includes items with type == 'season'."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "season", "ratingKey": "300", "title": "Season 1", "index": 1},
            {"type": "episode", "ratingKey": "400", "title": "Pilot"},
        ]
        lib._client = mock_client

        received = []
        lib.seasonsReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchSeasons", "200")

        _, seasons = received[0]
        assert len(seasons) == 1
        assert seasons[0]["ratingKey"] == "300"


# ---------------------------------------------------------------------------
# fetchEpisodes
# ---------------------------------------------------------------------------


class TestFetchEpisodes:
    def test_emits_episodes_ready_with_correct_rating_key_and_list(self) -> None:
        """fetchEpisodes emits episodesReady with the season_rating_key and a populated list."""
        lib = _make_lib()
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

        _run_worker(lib, "fetchEpisodes", "300")

        assert len(received) == 1
        rk, episodes = received[0]
        assert rk == "300"
        assert len(episodes) == 2
        assert episodes[0]["ratingKey"] == "400"
        assert episodes[0]["title"] == "Pilot"
        assert episodes[0]["index"] == 1
        assert episodes[0]["parentIndex"] == 1
        assert episodes[0]["duration"] == 2700000
        assert episodes[0]["viewOffset"] == 0
        assert episodes[0]["viewed"] is True
        assert episodes[0]["grandparentTitle"] == "Test Show"
        assert episodes[1]["ratingKey"] == "401"
        assert episodes[1]["viewOffset"] == 60000
        assert episodes[1]["viewed"] is False

    def test_emits_episodes_ready_with_empty_list_when_client_is_none(self) -> None:
        """fetchEpisodes emits episodesReady([]) immediately when _client is None."""
        lib = _make_lib()
        lib._client = None

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append((rk, d)))

        lib.fetchEpisodes("300")

        assert len(received) == 1
        rk, episodes = received[0]
        assert rk == "300"
        assert episodes == []

    def test_filters_out_non_episode_items(self) -> None:
        """fetchEpisodes only includes items with type == 'episode'."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "episode", "ratingKey": "400", "title": "Pilot", "index": 1},
            {"type": "season", "ratingKey": "300", "title": "Season 1"},
        ]
        lib._client = mock_client

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append((rk, d)))

        _run_worker(lib, "fetchEpisodes", "300")

        _, episodes = received[0]
        assert len(episodes) == 1
        assert episodes[0]["ratingKey"] == "400"

    def test_viewed_and_view_offset_fields_present(self) -> None:
        """All episode dicts must have 'viewed' and 'viewOffset' for QML watched indicators."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "episode", "ratingKey": "400", "title": "Ep"},
        ]
        lib._client = mock_client

        received = []
        lib.episodesReady.connect(lambda rk, d: received.append(d))

        _run_worker(lib, "fetchEpisodes", "300")

        assert len(received) == 1
        assert "viewed" in received[0][0]
        assert "viewOffset" in received[0][0]

    def test_season_rating_key_carried_in_signal_for_stale_guard(self) -> None:
        """episodesReady always carries the season_rating_key so QML can discard stale responses."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = []
        lib._client = mock_client

        received_keys = []
        lib.episodesReady.connect(lambda rk, d: received_keys.append(rk))

        _run_worker(lib, "fetchEpisodes", "300")

        assert received_keys == ["300"]
