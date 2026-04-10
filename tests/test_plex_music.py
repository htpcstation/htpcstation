"""Tests for Plex music backend.

Covers:
  - parse_artist: full and minimal data
  - parse_album: full and minimal data
  - parse_track: full data including Media[0].Part[0].key extraction
  - parse_track: missing Media → empty media_key
  - get_libraries: now includes artist-type libraries
  - PlexLibrary.fetchArtistPreview: async artist metadata fetch
  - PlexLibrary.fetchArtistDetail: async artist + albums fetch
  - PlexLibrary.fetchAlbumDetail: async album + tracks fetch
  - PlexLibrary.fetchRecentAlbums: async recently added albums
  - PlexClient.get_hubs: returns Hub array from API response
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.plex_models import (
    PlexAlbum,
    PlexArtist,
    PlexTrack,
    parse_album,
    parse_artist,
    parse_track,
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


def _make_lib():
    """Create a PlexLibrary instance with mocked dependencies."""
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


# ---------------------------------------------------------------------------
# parse_artist
# ---------------------------------------------------------------------------


class TestParseArtist:
    def test_full_data(self) -> None:
        data = {
            "ratingKey": "500",
            "title": "The Beatles",
            "summary": "Legendary band.",
            "thumb": "/library/metadata/500/thumb/1",
            "Genre": [{"tag": "Rock"}, {"tag": "Pop"}],
        }
        artist = parse_artist(data)
        assert artist.rating_key == "500"
        assert artist.title == "The Beatles"
        assert artist.summary == "Legendary band."
        assert artist.thumb_path == "/library/metadata/500/thumb/1"
        assert artist.genre == "Rock, Pop"
        assert artist.poster_local == ""

    def test_minimal_data(self) -> None:
        data = {"ratingKey": "501", "title": "Unknown Artist"}
        artist = parse_artist(data)
        assert artist.rating_key == "501"
        assert artist.title == "Unknown Artist"
        assert artist.summary == ""
        assert artist.thumb_path == ""
        assert artist.genre == ""
        assert artist.poster_local == ""

    def test_no_genres(self) -> None:
        data = {"ratingKey": "502", "title": "Artist", "Genre": []}
        artist = parse_artist(data)
        assert artist.genre == ""

    def test_single_genre(self) -> None:
        data = {"ratingKey": "503", "title": "Artist", "Genre": [{"tag": "Jazz"}]}
        artist = parse_artist(data)
        assert artist.genre == "Jazz"

    def test_genre_without_tag_skipped(self) -> None:
        data = {
            "ratingKey": "504",
            "title": "Artist",
            "Genre": [{"tag": "Rock"}, {"notag": "ignored"}],
        }
        artist = parse_artist(data)
        assert artist.genre == "Rock"

    def test_rating_key_coerced_to_string(self) -> None:
        data = {"ratingKey": 505, "title": "Artist"}
        artist = parse_artist(data)
        assert isinstance(artist.rating_key, str)
        assert artist.rating_key == "505"


# ---------------------------------------------------------------------------
# parse_album
# ---------------------------------------------------------------------------


class TestParseAlbum:
    def test_full_data(self) -> None:
        data = {
            "ratingKey": "600",
            "title": "Abbey Road",
            "year": 1969,
            "thumb": "/library/metadata/600/thumb/1",
            "leafCount": 17,
            "parentRatingKey": "500",
            "parentTitle": "The Beatles",
        }
        album = parse_album(data)
        assert album.rating_key == "600"
        assert album.title == "Abbey Road"
        assert album.year == 1969
        assert album.thumb_path == "/library/metadata/600/thumb/1"
        assert album.leaf_count == 17
        assert album.parent_rating_key == "500"
        assert album.parent_title == "The Beatles"
        assert album.poster_local == ""

    def test_minimal_data(self) -> None:
        data = {"ratingKey": "601", "title": "Unknown Album"}
        album = parse_album(data)
        assert album.rating_key == "601"
        assert album.title == "Unknown Album"
        assert album.year == 0
        assert album.thumb_path == ""
        assert album.leaf_count == 0
        assert album.parent_rating_key == ""
        assert album.parent_title == ""
        assert album.poster_local == ""

    def test_none_year_handled(self) -> None:
        data = {"ratingKey": "602", "title": "Album", "year": None}
        album = parse_album(data)
        assert album.year == 0

    def test_none_leaf_count_handled(self) -> None:
        data = {"ratingKey": "603", "title": "Album", "leafCount": None}
        album = parse_album(data)
        assert album.leaf_count == 0

    def test_rating_key_coerced_to_string(self) -> None:
        data = {"ratingKey": 604, "title": "Album"}
        album = parse_album(data)
        assert isinstance(album.rating_key, str)
        assert album.rating_key == "604"

    def test_parent_rating_key_coerced_to_string(self) -> None:
        data = {"ratingKey": "605", "title": "Album", "parentRatingKey": 500}
        album = parse_album(data)
        assert isinstance(album.parent_rating_key, str)
        assert album.parent_rating_key == "500"

    def test_summary_parsed(self) -> None:
        data = {"ratingKey": "606", "title": "Album", "summary": "A great album."}
        album = parse_album(data)
        assert album.summary == "A great album."

    def test_summary_defaults_to_empty(self) -> None:
        data = {"ratingKey": "607", "title": "Album"}
        album = parse_album(data)
        assert album.summary == ""

    def test_studio_parsed(self) -> None:
        data = {"ratingKey": "608", "title": "Album", "studio": "Apple Records"}
        album = parse_album(data)
        assert album.studio == "Apple Records"

    def test_studio_defaults_to_empty(self) -> None:
        data = {"ratingKey": "609", "title": "Album"}
        album = parse_album(data)
        assert album.studio == ""

    def test_genre_parsed_from_genre_list(self) -> None:
        data = {
            "ratingKey": "610",
            "title": "Album",
            "Genre": [{"tag": "Rock"}, {"tag": "Pop"}],
        }
        album = parse_album(data)
        assert album.genre == "Rock, Pop"

    def test_genre_defaults_to_empty_when_no_genre_key(self) -> None:
        data = {"ratingKey": "611", "title": "Album"}
        album = parse_album(data)
        assert album.genre == ""

    def test_genre_handles_none_genre_key(self) -> None:
        data = {"ratingKey": "612", "title": "Album", "Genre": None}
        album = parse_album(data)
        assert album.genre == ""

    def test_genre_skips_entries_without_tag(self) -> None:
        data = {
            "ratingKey": "613",
            "title": "Album",
            "Genre": [{"tag": "Rock"}, {"notag": "ignored"}, {"tag": "Jazz"}],
        }
        album = parse_album(data)
        assert album.genre == "Rock, Jazz"

    def test_rating_normalized_from_plex_0_10_scale(self) -> None:
        data = {"ratingKey": "614", "title": "Album", "rating": 8.5}
        album = parse_album(data)
        assert abs(album.rating - 0.85) < 1e-9

    def test_rating_defaults_to_zero(self) -> None:
        data = {"ratingKey": "615", "title": "Album"}
        album = parse_album(data)
        assert album.rating == 0.0

    def test_rating_handles_none(self) -> None:
        data = {"ratingKey": "616", "title": "Album", "rating": None}
        album = parse_album(data)
        assert album.rating == 0.0

    def test_rating_handles_zero(self) -> None:
        data = {"ratingKey": "617", "title": "Album", "rating": 0}
        album = parse_album(data)
        assert album.rating == 0.0


# ---------------------------------------------------------------------------
# parse_track
# ---------------------------------------------------------------------------


class TestParseTrack:
    def test_full_data_with_media_key(self) -> None:
        data = {
            "ratingKey": "700",
            "title": "Come Together",
            "index": 1,
            "duration": 259000,
            "parentTitle": "Abbey Road",
            "grandparentTitle": "The Beatles",
            "Media": [
                {
                    "Part": [
                        {"key": "/library/parts/12345/file.flac"}
                    ]
                }
            ],
        }
        track = parse_track(data)
        assert track.rating_key == "700"
        assert track.title == "Come Together"
        assert track.index == 1
        assert track.duration_ms == 259000
        assert track.parent_title == "Abbey Road"
        assert track.grandparent_title == "The Beatles"
        assert track.media_key == "/library/parts/12345/file.flac"

    def test_missing_media_gives_empty_media_key(self) -> None:
        data = {
            "ratingKey": "701",
            "title": "Track Without Media",
        }
        track = parse_track(data)
        assert track.media_key == ""

    def test_empty_media_list_gives_empty_media_key(self) -> None:
        data = {
            "ratingKey": "702",
            "title": "Track",
            "Media": [],
        }
        track = parse_track(data)
        assert track.media_key == ""

    def test_empty_parts_list_gives_empty_media_key(self) -> None:
        data = {
            "ratingKey": "703",
            "title": "Track",
            "Media": [{"Part": []}],
        }
        track = parse_track(data)
        assert track.media_key == ""

    def test_minimal_data(self) -> None:
        data = {"ratingKey": "704", "title": "Minimal Track"}
        track = parse_track(data)
        assert track.rating_key == "704"
        assert track.title == "Minimal Track"
        assert track.index == 0
        assert track.duration_ms == 0
        assert track.parent_title == ""
        assert track.grandparent_title == ""
        assert track.media_key == ""

    def test_none_duration_handled(self) -> None:
        data = {"ratingKey": "705", "title": "Track", "duration": None}
        track = parse_track(data)
        assert track.duration_ms == 0

    def test_none_index_handled(self) -> None:
        data = {"ratingKey": "706", "title": "Track", "index": None}
        track = parse_track(data)
        assert track.index == 0

    def test_rating_key_coerced_to_string(self) -> None:
        data = {"ratingKey": 707, "title": "Track"}
        track = parse_track(data)
        assert isinstance(track.rating_key, str)
        assert track.rating_key == "707"


# ---------------------------------------------------------------------------
# PlexClient.get_libraries — includes artist type
# ---------------------------------------------------------------------------


class TestGetLibrariesIncludesArtist:
    def test_artist_libraries_included(self) -> None:
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Movies", "type": "movie", "key": "1"},
            {"title": "TV Shows", "type": "show", "key": "2"},
            {"title": "Music", "type": "artist", "key": "3"},
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

        assert len(libs) == 3
        types = {lib["type"] for lib in libs}
        assert "artist" in types
        assert "movie" in types
        assert "show" in types

    def test_artist_library_not_filtered_out(self) -> None:
        from backend.plex_client import PlexClient

        directories = [
            {"title": "Music", "type": "artist", "key": "3"},
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

        assert len(libs) == 1
        assert libs[0]["type"] == "artist"
        assert libs[0]["title"] == "Music"


# ---------------------------------------------------------------------------
# PlexLibrary.getArtist
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PlexLibrary.fetchArtistPreview
# ---------------------------------------------------------------------------


def _run_fetch_worker_with_events(lib, method_name, *args):
    """Submit a fetch* call, run the captured worker synchronously, then flush Qt events."""
    from PySide6.QtCore import QCoreApplication

    submitted = []

    def fake_submit(fn, *a, **kw):
        submitted.append(fn)

    lib._executor.submit = fake_submit  # type: ignore[method-assign]
    getattr(lib, method_name)(*args)
    for fn in submitted:
        fn()
    QCoreApplication.processEvents()


class TestFetchArtistPreview:
    def test_emits_artist_preview_ready_with_correct_data(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "500",
            "title": "The Beatles",
            "summary": "Legendary band.",
            "thumb": "/library/metadata/500/thumb/1",
            "Genre": [{"tag": "Rock"}, {"tag": "Pop"}],
        }
        lib._client = mock_client

        received = []
        lib.artistPreviewReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistPreview", "500")

        assert len(received) == 1
        rk, data = received[0]
        assert rk == "500"
        assert data["ratingKey"] == "500"
        assert data["title"] == "The Beatles"
        assert data["summary"] == "Legendary band."
        assert data["genre"] == "Rock, Pop"
        assert "posterLocal" in data

    def test_no_op_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None

        submitted: list = []
        lib._executor.submit = lambda fn, *a, **kw: submitted.append(fn)  # type: ignore[method-assign]
        lib.fetchArtistPreview("500")

        assert len(submitted) == 0

    def test_no_emit_when_metadata_not_found(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {}
        lib._client = mock_client

        received = []
        lib.artistPreviewReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistPreview", "999")

        assert len(received) == 0

    def test_uses_disk_cache_pre_resolve_not_get_poster(self, tmp_path) -> None:
        """Poster resolution uses _cache_path().exists(), not get_poster()."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "500",
            "title": "Artist",
            "thumb": "/library/metadata/500/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        cached_path = MagicMock()
        cached_path.exists.return_value = True
        cached_path.as_uri.return_value = "file:///tmp/poster_cache/artist.jpg"
        mock_cache._cache_path.return_value = cached_path
        lib._poster_cache = mock_cache

        received = []
        lib.artistPreviewReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistPreview", "500")

        assert len(received) == 1
        assert received[0][1]["posterLocal"] == "file:///tmp/poster_cache/artist.jpg"
        mock_cache._cache_path.assert_called_once_with("/library/metadata/500/thumb/1")
        # get_poster must NOT be called — preview uses disk pre-resolve only
        mock_cache.get_poster.assert_not_called()

    def test_poster_local_empty_when_not_cached(self) -> None:
        """When the poster is not in the disk cache, posterLocal stays empty."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "500",
            "title": "Artist",
            "thumb": "/library/metadata/500/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        cached_path = MagicMock()
        cached_path.exists.return_value = False
        mock_cache._cache_path.return_value = cached_path
        lib._poster_cache = mock_cache

        received = []
        lib.artistPreviewReady.connect(lambda rk, d: received.append((rk, d)))
        _run_fetch_worker_with_events(lib, "fetchArtistPreview", "500")

        assert len(received) == 1
        assert received[0][1]["posterLocal"] == ""


# ---------------------------------------------------------------------------
# PlexLibrary.getTrackStreamUrl
# ---------------------------------------------------------------------------


class TestGetTrackStreamUrl:
    def test_returns_correct_url_with_token(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_authenticated_url.return_value = (
            "http://server:32400/library/parts/12345/file.flac?X-Plex-Token=mytoken"
        )
        lib._client = mock_client

        result = lib.getTrackStreamUrl("/library/parts/12345/file.flac")

        mock_client.get_authenticated_url.assert_called_once_with(
            "/library/parts/12345/file.flac"
        )
        assert result == "http://server:32400/library/parts/12345/file.flac?X-Plex-Token=mytoken"

    def test_returns_empty_string_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None
        result = lib.getTrackStreamUrl("/library/parts/12345/file.flac")
        assert result == ""

    def test_url_format_includes_token(self) -> None:
        """Verify the URL format: {server_url}{media_key}?X-Plex-Token={token}."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session"):
            client = PlexClient("http://server:32400", "mytoken")

        lib = _make_lib()
        lib._client = client

        result = lib.getTrackStreamUrl("/library/parts/12345/file.flac")

        assert result == "http://server:32400/library/parts/12345/file.flac?X-Plex-Token=mytoken"


# ---------------------------------------------------------------------------
# PlexArtistListModel
# ---------------------------------------------------------------------------


class TestPlexArtistListModel:
    def _make_artist(
        self,
        rating_key: str = "500",
        title: str = "Test Artist",
        genre: str = "Rock",
    ) -> PlexArtist:
        return PlexArtist(
            rating_key=rating_key,
            title=title,
            genre=genre,
            thumb_path="/thumb/500",
        )

    def test_roles_and_data(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        artist = self._make_artist("42", "My Artist", "Jazz")
        model.set_artists([artist])

        idx = model.index(0, 0)
        assert model.data(idx, PlexArtistListModel.RatingKeyRole) == "42"
        assert model.data(idx, PlexArtistListModel.TitleRole) == "My Artist"
        assert model.data(idx, PlexArtistListModel.GenreRole) == "Jazz"
        assert model.data(idx, PlexArtistListModel.ImageLocalRole) == ""

    def test_image_local_role_returns_updated_value(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        artist = self._make_artist()
        model.set_artists([artist])

        artist.poster_local = "file:///tmp/artist.jpg"
        idx = model.index(0, 0)
        assert model.data(idx, PlexArtistListModel.ImageLocalRole) == "file:///tmp/artist.jpg"

    def test_notify_poster_changed_emits_data_changed(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        model.set_artists([self._make_artist()])

        received = []
        model.dataChanged.connect(lambda tl, br, roles: received.append(roles))

        model.notify_poster_changed(0)

        assert len(received) == 1
        assert PlexArtistListModel.ImageLocalRole in received[0]

    def test_role_names(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        names = model.roleNames()
        assert b"ratingKey" in names.values()
        assert b"title" in names.values()
        assert b"genre" in names.values()
        assert b"imageLocal" in names.values()

    def test_row_count(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        assert model.rowCount() == 0

        model.set_artists([self._make_artist("1"), self._make_artist("2")])
        assert model.rowCount() == 2

    def test_invalid_index_returns_none(self) -> None:
        from backend.plex_library import PlexArtistListModel
        from PySide6.QtCore import QModelIndex

        model = PlexArtistListModel()
        assert model.data(QModelIndex(), PlexArtistListModel.TitleRole) is None

    def test_set_artists_replaces_model(self) -> None:
        from backend.plex_library import PlexArtistListModel

        model = PlexArtistListModel()
        model.set_artists([self._make_artist("1", "First")])
        model.set_artists([self._make_artist("2", "Second"), self._make_artist("3", "Third")])

        assert model.rowCount() == 2
        idx = model.index(0, 0)
        assert model.data(idx, PlexArtistListModel.TitleRole) == "Second"


# ---------------------------------------------------------------------------
# PlexLibrary.artistsModel property
# ---------------------------------------------------------------------------


class TestArtistsModelProperty:
    def test_artists_model_property_exposed(self) -> None:
        """artistsModel property returns the PlexArtistListModel instance."""
        from backend.plex_library import PlexLibrary, PlexArtistListModel

        lib = _make_lib()
        assert lib.artistsModel is lib._artists_model
        assert isinstance(lib.artistsModel, PlexArtistListModel)


# ---------------------------------------------------------------------------
# PlexLibrary.getMusicLibraries
# ---------------------------------------------------------------------------


class TestGetMusicLibraries:
    def test_returns_only_artist_type_libraries(self) -> None:
        """getMusicLibraries returns only libraries with type == 'artist'."""
        lib = _make_lib()
        lib._libraries_model._items = [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
            {"key": "3", "title": "Music", "type": "artist"},
            {"key": "4", "title": "Audiobooks", "type": "artist"},
        ]

        result = lib.getMusicLibraries()

        assert len(result) == 2
        ids = [r["id"] for r in result]
        labels = [r["label"] for r in result]
        assert "3" in ids
        assert "4" in ids
        assert "Music" in labels
        assert "Audiobooks" in labels

    def test_returns_empty_list_when_no_artist_libraries(self) -> None:
        """getMusicLibraries returns [] when no artist-type libraries exist."""
        lib = _make_lib()
        lib._libraries_model._items = [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "2", "title": "TV Shows", "type": "show"},
        ]

        result = lib.getMusicLibraries()

        assert result == []

    def test_returns_empty_list_when_libraries_not_loaded(self) -> None:
        """getMusicLibraries returns [] when the libraries model is empty."""
        lib = _make_lib()
        lib._libraries_model._items = []

        result = lib.getMusicLibraries()

        assert result == []

    def test_result_has_id_and_label_keys(self) -> None:
        """getMusicLibraries entries have 'id' and 'label' keys."""
        lib = _make_lib()
        lib._libraries_model._items = [
            {"key": "5", "title": "My Music", "type": "artist"},
        ]

        result = lib.getMusicLibraries()

        assert len(result) == 1
        assert "id" in result[0]
        assert "label" in result[0]
        assert result[0]["id"] == "5"
        assert result[0]["label"] == "My Music"

    def test_id_is_string_even_when_key_is_int(self) -> None:
        """getMusicLibraries coerces the key to a string for the 'id' field."""
        lib = _make_lib()
        lib._libraries_model._items = [
            {"key": 7, "title": "Music", "type": "artist"},
        ]

        result = lib.getMusicLibraries()

        assert result[0]["id"] == "7"
        assert isinstance(result[0]["id"], str)


# ---------------------------------------------------------------------------
# Config — music_library_key round-trip
# ---------------------------------------------------------------------------


class TestConfigMusicLibraryKey:
    def _make_config(self, tmp_path, data=None):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data or {}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            return Config(), config_file

    def test_music_library_key_default_is_empty(self, tmp_path) -> None:
        """Config.music_library_key defaults to empty string."""
        config, _ = self._make_config(tmp_path)
        assert config.music_library_key == ""

    def test_set_music_library_key_persists(self, tmp_path) -> None:
        """set_music_library_key updates the property and saves to disk."""
        import json
        from pathlib import Path
        from unittest.mock import patch
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_music_library_key("42")

        assert config.music_library_key == "42"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["music_library_key"] == "42"

    def test_load_reads_music_library_key_from_plex_section(self, tmp_path) -> None:
        """Config._load() reads music_library_key from the plex section."""
        config, _ = self._make_config(
            tmp_path,
            {"plex": {"music_library_key": "99"}},
        )
        assert config.music_library_key == "99"

    def test_music_library_key_missing_from_plex_section_uses_empty(self, tmp_path) -> None:
        """Config without music_library_key in plex section defaults to empty string."""
        config, _ = self._make_config(
            tmp_path,
            {"plex": {"token": "tok"}},
        )
        assert config.music_library_key == ""

    def test_save_includes_music_library_key_in_plex_section(self, tmp_path) -> None:
        """Config.save() writes music_library_key to the plex section."""
        import json
        from pathlib import Path
        from unittest.mock import patch
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config._music_library_key = "77"
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["music_library_key"] == "77"


# ---------------------------------------------------------------------------
# PlexClient.get_hubs
# ---------------------------------------------------------------------------


class TestGetHubs:
    def test_returns_hub_array_from_api_response(self) -> None:
        from backend.plex_client import PlexClient

        hubs = [
            {"hubIdentifier": "hub.artist.albums", "title": "3 Albums", "type": "album"},
            {"hubIdentifier": "hub.artist.albums.singles", "title": "Singles & EPs", "type": "album"},
        ]

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"Hub": hubs}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_hubs("500")

        assert result == hubs
        assert len(result) == 2
        assert result[0]["hubIdentifier"] == "hub.artist.albums"

    def test_returns_empty_list_on_error(self) -> None:
        from backend.plex_client import PlexClient
        import requests as req

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            result = client.get_hubs("500")

        assert result == []

    def test_returns_empty_list_when_no_hub_key(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_hubs("500")

        assert result == []

    def test_calls_correct_endpoint(self) -> None:
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {"Hub": []}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            client.get_hubs("42")

        call_url = mock_session.get.call_args[0][0]
        assert call_url == "http://server:32400/hubs/metadata/42?count=999"


# ---------------------------------------------------------------------------
# Artist list cache — Task 007
# ---------------------------------------------------------------------------


def _make_artists(n: int = 2) -> list:
    """Return a list of n PlexArtist objects for testing."""
    return [
        PlexArtist(
            rating_key=str(i),
            title=f"Artist {i}",
            summary=f"Summary {i}",
            thumb_path=f"/thumb/{i}",
            genre="Rock",
            poster_local=f"file:///cache/{i}.jpg",
        )
        for i in range(n)
    ]


class TestSaveArtistsCache:
    def test_writes_valid_json_with_correct_fields(self, tmp_path) -> None:
        """_merge_and_write_artists_cache writes a JSON file with all expected fields."""
        import json as _json

        lib = _make_lib()
        lib._current_section_key = "3"

        # _PLEX_CACHE_DIR is already redirected to tmp_path / "plex_cache"
        # by the isolate_plex_cache autouse fixture in conftest.py
        artists = _make_artists(2)
        artist_dicts = [lib._artist_to_dict(a) for a in artists]
        lib._merge_and_write_artists_cache(artist_dicts)

        cache_path = tmp_path / "plex_cache" / "artists_cache_3.json"
        assert cache_path.exists()

        data = _json.loads(cache_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["rating_key"] == "0"
        assert data[0]["title"] == "Artist 0"
        assert data[0]["summary"] == "Summary 0"
        assert data[0]["thumb_path"] == "/thumb/0"
        assert data[0]["genre"] == "Rock"
        assert data[0]["poster_local"] == "file:///cache/0.jpg"

    def test_writes_empty_list_for_no_artists(self, tmp_path) -> None:
        """_merge_and_write_artists_cache writes an empty JSON array when given no artists."""
        import json as _json

        lib = _make_lib()
        lib._current_section_key = "3"

        lib._merge_and_write_artists_cache([])

        cache_path = tmp_path / "plex_cache" / "artists_cache_3.json"
        data = _json.loads(cache_path.read_text(encoding="utf-8"))
        assert data == []

    def test_does_not_raise_on_write_error(self, tmp_path, monkeypatch) -> None:
        """_merge_and_write_artists_cache silently swallows write errors."""
        lib = _make_lib()
        lib._current_section_key = "3"

        # Point _PLEX_CACHE_DIR to a path that cannot be written
        # (the "plex_cache" entry is a file, not a dir, so mkdir will fail)
        blocker_parent = tmp_path / "blocker_parent"
        blocker_parent.mkdir()
        blocker = blocker_parent / "plex_cache"
        blocker.write_text("not a dir")

        monkeypatch.setattr("backend.plex_library._PLEX_CACHE_DIR", blocker)

        # Should not raise
        artists = _make_artists(1)
        lib._merge_and_write_artists_cache([lib._artist_to_dict(a) for a in artists])


class TestLoadArtistsCache:
    def test_returns_plex_artist_list_from_valid_cache(self, tmp_path) -> None:
        """_load_artists_cache deserializes a valid JSON file into PlexArtist objects."""
        import json as _json

        lib = _make_lib()
        lib._current_section_key = "3"

        # _PLEX_CACHE_DIR is already redirected to tmp_path / "plex_cache"
        # by the isolate_plex_cache autouse fixture in conftest.py
        cache_dir = tmp_path / "plex_cache"
        cache_path = cache_dir / "artists_cache_3.json"
        cache_path.write_text(
            _json.dumps([
                {
                    "rating_key": "42",
                    "title": "The Beatles",
                    "summary": "Legendary.",
                    "thumb_path": "/thumb/42",
                    "genre": "Rock",
                    "poster_local": "file:///cache/42.jpg",
                }
            ]),
            encoding="utf-8",
        )

        result = lib._load_artists_cache()

        assert result is not None
        assert len(result) == 1
        artist = result[0]
        assert isinstance(artist, PlexArtist)
        assert artist.rating_key == "42"
        assert artist.title == "The Beatles"
        assert artist.summary == "Legendary."
        assert artist.thumb_path == "/thumb/42"
        assert artist.genre == "Rock"
        assert artist.poster_local == "file:///cache/42.jpg"

    def test_returns_none_for_missing_file(self, tmp_path) -> None:
        """_load_artists_cache returns None when the cache file does not exist."""
        lib = _make_lib()
        lib._current_section_key = "3"

        # _PLEX_CACHE_DIR points to tmp_path / "plex_cache" (no cache file written)
        result = lib._load_artists_cache()

        assert result is None

    def test_returns_none_for_corrupt_json(self, tmp_path) -> None:
        """_load_artists_cache returns None when the cache file contains invalid JSON."""
        lib = _make_lib()
        lib._current_section_key = "3"

        cache_dir = tmp_path / "plex_cache"
        cache_path = cache_dir / "artists_cache_3.json"
        cache_path.write_text("not valid json {{{{", encoding="utf-8")

        result = lib._load_artists_cache()

        assert result is None

    def test_missing_fields_use_defaults(self, tmp_path) -> None:
        """_load_artists_cache uses empty-string defaults for missing JSON fields."""
        import json as _json

        lib = _make_lib()
        lib._current_section_key = "3"

        cache_dir = tmp_path / "plex_cache"
        cache_path = cache_dir / "artists_cache_3.json"
        # Only rating_key and title present
        cache_path.write_text(
            _json.dumps([{"rating_key": "1", "title": "Minimal"}]),
            encoding="utf-8",
        )

        result = lib._load_artists_cache()

        assert result is not None
        assert len(result) == 1
        artist = result[0]
        assert artist.rating_key == "1"
        assert artist.title == "Minimal"
        assert artist.summary == ""
        assert artist.thumb_path == ""
        assert artist.genre == ""
        assert artist.poster_local == ""


# ---------------------------------------------------------------------------
# PlexClient.get_playlists — Task 012
# ---------------------------------------------------------------------------


class TestGetPlaylists:
    def test_returns_playlist_list_from_api(self) -> None:
        """get_playlists returns the Metadata list from the /playlists endpoint."""
        from backend.plex_client import PlexClient

        playlists = [
            {"ratingKey": "1", "title": "My Playlist", "playlistType": "audio", "leafCount": 10, "duration": 3600000},
            {"ratingKey": "2", "title": "Video Playlist", "playlistType": "video", "leafCount": 5, "duration": 0},
        ]

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "MediaContainer": {"Metadata": playlists}
            }
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_playlists()

        assert result == playlists
        assert len(result) == 2

    def test_returns_empty_list_on_error(self) -> None:
        """get_playlists returns [] on connection error."""
        from backend.plex_client import PlexClient
        import requests as req

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

            client = PlexClient("http://server:32400", "tok")
            result = client.get_playlists()

        assert result == []

    def test_returns_empty_list_when_no_metadata_key(self) -> None:
        """get_playlists returns [] when MediaContainer has no Metadata key."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            result = client.get_playlists()

        assert result == []

    def test_calls_correct_endpoint(self) -> None:
        """get_playlists calls /playlists."""
        from backend.plex_client import PlexClient

        with patch("backend.plex_client.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"MediaContainer": {"Metadata": []}}
            mock_session.get.return_value = mock_response

            client = PlexClient("http://server:32400", "tok")
            client.get_playlists()

        call_url = mock_session.get.call_args[0][0]
        assert call_url == "http://server:32400/playlists"


class TestWorkerLoadSectionArtistCache:
    """Tests for the cache-aware _worker_load_section behaviour for artist sections."""

    def _make_lib_with_section(self, section_key: str = "3"):
        lib = _make_lib()
        lib._current_section_key = section_key
        # Inject a real music library entry so selectLibrary can find it
        lib._libraries_model._items = [
            {"key": section_key, "title": "Music", "type": "artist"},
        ]
        return lib

    def _fake_api_artists(self):
        return [
            {
                "ratingKey": "10",
                "title": "Fresh Artist",
                "summary": "",
                "thumb": "",
                "Genre": [],
            }
        ]

    def test_emits_artistsReady_once_from_network_when_cache_exists(self, tmp_path) -> None:
        """Cache is now loaded in selectLibrary(), not _worker_load_section().

        Even when a cache file exists, _worker_load_section emits _artistsReady
        exactly once — only from the network result.
        """
        import json as _json

        lib = self._make_lib_with_section("3")

        # Write a cache file under tmp_path / "plex_cache" (which is _PLEX_CACHE_DIR,
        # already redirected by the isolate_plex_cache autouse fixture in conftest.py)
        cache_dir = tmp_path / "plex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / "artists_cache_3.json"
        cache_path.write_text(
            _json.dumps([
                {"rating_key": "99", "title": "Cached Artist", "summary": "",
                 "thumb_path": "", "genre": "", "poster_local": ""},
            ]),
            encoding="utf-8",
        )

        # Mock the API to return one fresh artist
        mock_client = MagicMock()
        mock_client.get_library_items.return_value = (self._fake_api_artists(), 1)
        lib._client = mock_client

        emitted: list[list] = []
        lib._artistsReady.connect(lambda artists, total: emitted.append(list(artists)))

        lib._worker_load_section(mock_client, "3", "artist")

        # Only the network emission fires — cache is now loaded in selectLibrary()
        assert len(emitted) == 1, f"Expected 1 emission, got {len(emitted)}"
        assert emitted[0][0].title == "Fresh Artist"

    def test_emits_artistsReady_once_when_no_cache(self, tmp_path) -> None:
        """When no cache file exists, _artistsReady is emitted only once (from API)."""
        lib = self._make_lib_with_section("3")

        mock_client = MagicMock()
        mock_client.get_library_items.return_value = (self._fake_api_artists(), 1)
        lib._client = mock_client

        emitted: list[list] = []
        lib._artistsReady.connect(lambda artists, total: emitted.append(list(artists)))

        # _PLEX_CACHE_DIR is already redirected to tmp_path / "plex_cache" (empty)
        # by the isolate_plex_cache autouse fixture in conftest.py
        lib._worker_load_section(mock_client, "3", "artist")

        assert len(emitted) == 1, f"Expected 1 emission, got {len(emitted)}"
        assert emitted[0][0].title == "Fresh Artist"


# ---------------------------------------------------------------------------
# _on_artists_ready — model reset guard
# ---------------------------------------------------------------------------


class TestOnArtistsReadyGuard:
    def test_on_artists_ready_skips_when_same_count(self) -> None:
        """When incoming artist count equals model count, set_artists is NOT called."""
        lib = _make_lib()
        lib._client = None  # prevent poster fetch attempts

        # Pre-populate the model with 3 artists
        existing = _make_artists(3)
        lib._artists_model.set_artists(existing)

        # Call _on_artists_ready with the same count
        incoming = _make_artists(3)
        with patch.object(lib._artists_model, "set_artists") as mock_set:
            lib._on_artists_ready(incoming, 3)
            mock_set.assert_not_called()
