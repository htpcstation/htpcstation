"""Tests for Task 001 — Plex music backend.

Covers:
  - parse_artist: full and minimal data
  - parse_album: full and minimal data
  - parse_track: full data including Media[0].Part[0].key extraction
  - parse_track: missing Media → empty media_key
  - get_libraries: now includes artist-type libraries
  - PlexLibrary.getArtist: returns correct dict
  - PlexLibrary.getAlbums: returns list of album dicts, filters non-album children
  - PlexLibrary.getTracks: returns list of track dicts with media_key
  - PlexLibrary.getTrackStreamUrl: returns correct URL with token
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


class TestGetArtist:
    def test_returns_artist_dict_with_expected_keys(self) -> None:
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

        result = lib.getArtist("500")

        assert result["ratingKey"] == "500"
        assert result["title"] == "The Beatles"
        assert result["summary"] == "Legendary band."
        assert result["genre"] == "Rock, Pop"
        assert "posterLocal" in result

    def test_returns_empty_dict_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None
        result = lib.getArtist("500")
        assert result == {}

    def test_returns_empty_dict_when_metadata_not_found(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {}
        lib._client = mock_client
        result = lib.getArtist("999")
        assert result == {}

    def test_poster_local_populated_when_thumb_path_present(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "500",
            "title": "Artist",
            "thumb": "/library/metadata/500/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster_cache/artist.jpg"
        lib._poster_cache = mock_cache

        result = lib.getArtist("500")

        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/500/thumb/1"
        )
        assert result["posterLocal"] == "file:///tmp/poster_cache/artist.jpg"

    def test_poster_local_empty_when_no_thumb_path(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "501",
            "title": "No Thumb Artist",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        lib._poster_cache = mock_cache

        result = lib.getArtist("501")

        mock_cache.get_poster.assert_not_called()
        assert result["posterLocal"] == ""


# ---------------------------------------------------------------------------
# PlexLibrary.getAlbums
# ---------------------------------------------------------------------------


class TestGetAlbums:
    def test_returns_album_list(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "album",
                "ratingKey": "600",
                "title": "Abbey Road",
                "year": 1969,
                "leafCount": 17,
                "parentRatingKey": "500",
                "parentTitle": "The Beatles",
            },
            {
                "type": "album",
                "ratingKey": "601",
                "title": "Let It Be",
                "year": 1970,
                "leafCount": 12,
                "parentRatingKey": "500",
                "parentTitle": "The Beatles",
            },
        ]
        lib._client = mock_client

        result = lib.getAlbums("500")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "600"
        assert result[0]["title"] == "Abbey Road"
        assert result[0]["year"] == 1969
        assert result[0]["leafCount"] == 17
        assert result[0]["parentRatingKey"] == "500"
        assert "posterLocal" in result[0]
        assert result[1]["ratingKey"] == "601"
        assert result[1]["title"] == "Let It Be"

    def test_filters_out_non_album_children(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "album", "ratingKey": "600", "title": "Abbey Road"},
            {"type": "track", "ratingKey": "700", "title": "Some Track"},
            {"type": "artist", "ratingKey": "500", "title": "The Beatles"},
        ]
        lib._client = mock_client

        result = lib.getAlbums("500")

        assert len(result) == 1
        assert result[0]["ratingKey"] == "600"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None
        result = lib.getAlbums("500")
        assert result == []

    def test_returns_empty_list_when_no_children(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = []
        lib._client = mock_client
        result = lib.getAlbums("500")
        assert result == []

    def test_poster_local_populated_when_thumb_path_present(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "album",
                "ratingKey": "600",
                "title": "Abbey Road",
                "thumb": "/library/metadata/600/thumb/1",
            },
        ]
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster_cache/album.jpg"
        lib._poster_cache = mock_cache

        result = lib.getAlbums("500")

        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/600/thumb/1"
        )
        assert result[0]["posterLocal"] == "file:///tmp/poster_cache/album.jpg"


# ---------------------------------------------------------------------------
# PlexLibrary.getTracks
# ---------------------------------------------------------------------------


class TestGetTracks:
    def test_returns_track_list_with_media_key(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "track",
                "ratingKey": "700",
                "title": "Come Together",
                "index": 1,
                "duration": 259000,
                "parentTitle": "Abbey Road",
                "grandparentTitle": "The Beatles",
                "Media": [
                    {"Part": [{"key": "/library/parts/12345/file.flac"}]}
                ],
            },
            {
                "type": "track",
                "ratingKey": "701",
                "title": "Something",
                "index": 2,
                "duration": 182000,
                "parentTitle": "Abbey Road",
                "grandparentTitle": "The Beatles",
                "Media": [
                    {"Part": [{"key": "/library/parts/12346/file.flac"}]}
                ],
            },
        ]
        lib._client = mock_client

        result = lib.getTracks("600")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "700"
        assert result[0]["title"] == "Come Together"
        assert result[0]["index"] == 1
        assert result[0]["durationMs"] == 259000
        assert result[0]["parentTitle"] == "Abbey Road"
        assert result[0]["grandparentTitle"] == "The Beatles"
        assert result[0]["mediaKey"] == "/library/parts/12345/file.flac"
        assert result[1]["ratingKey"] == "701"
        assert result[1]["mediaKey"] == "/library/parts/12346/file.flac"

    def test_filters_out_non_track_children(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "track",
                "ratingKey": "700",
                "title": "Come Together",
                "Media": [{"Part": [{"key": "/library/parts/12345/file.flac"}]}],
            },
            {"type": "album", "ratingKey": "600", "title": "Abbey Road"},
        ]
        lib._client = mock_client

        result = lib.getTracks("600")

        assert len(result) == 1
        assert result[0]["ratingKey"] == "700"

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None
        result = lib.getTracks("600")
        assert result == []

    def test_returns_empty_list_when_no_children(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = []
        lib._client = mock_client
        result = lib.getTracks("600")
        assert result == []

    def test_track_with_missing_media_has_empty_media_key(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {
                "type": "track",
                "ratingKey": "702",
                "title": "Track Without Media",
            },
        ]
        lib._client = mock_client

        result = lib.getTracks("600")

        assert len(result) == 1
        assert result[0]["mediaKey"] == ""

    def test_all_expected_keys_present(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_children.return_value = [
            {"type": "track", "ratingKey": "700", "title": "Track"},
        ]
        lib._client = mock_client

        result = lib.getTracks("600")

        assert len(result) == 1
        track = result[0]
        assert "ratingKey" in track
        assert "title" in track
        assert "index" in track
        assert "durationMs" in track
        assert "parentTitle" in track
        assert "grandparentTitle" in track
        assert "mediaKey" in track


# ---------------------------------------------------------------------------
# PlexLibrary.getTrackStreamUrl
# ---------------------------------------------------------------------------


class TestGetTrackStreamUrl:
    def test_returns_correct_url_with_token(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_poster_url.return_value = (
            "http://server:32400/library/parts/12345/file.flac?X-Plex-Token=mytoken"
        )
        lib._client = mock_client

        result = lib.getTrackStreamUrl("/library/parts/12345/file.flac")

        mock_client.get_poster_url.assert_called_once_with(
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
