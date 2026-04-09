"""Tests for Task 001 — Plex music backend.

Covers:
  - parse_artist: full and minimal data
  - parse_album: full and minimal data
  - parse_track: full data including Media[0].Part[0].key extraction
  - parse_track: missing Media → empty media_key
  - get_libraries: now includes artist-type libraries
  - PlexLibrary.getArtist: returns correct dict
  - PlexLibrary.getAlbum: returns album dict with summary/studio/genre/rating fields
  - PlexLibrary.getAlbums: returns list of album dicts, filters non-album children
  - PlexLibrary.getTracks: returns list of track dicts with media_key
  - PlexLibrary.getTrackStreamUrl: returns correct URL with token
  - PlexClient.get_hubs: returns Hub array from API response
  - PlexLibrary.getArtistAlbums: returns grouped list with headers and albums
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
# PlexLibrary.getAlbum
# ---------------------------------------------------------------------------


class TestGetAlbum:
    def test_returns_album_dict_with_all_expected_keys(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "600",
            "title": "Abbey Road",
            "year": 1969,
            "thumb": "/library/metadata/600/thumb/1",
            "leafCount": 17,
            "parentTitle": "The Beatles",
            "summary": "Classic album.",
            "studio": "Apple Records",
            "Genre": [{"tag": "Rock"}, {"tag": "Pop"}],
            "rating": 9.0,
        }
        lib._client = mock_client

        result = lib.getAlbum("600")

        assert result["ratingKey"] == "600"
        assert result["title"] == "Abbey Road"
        assert result["year"] == 1969
        assert result["leafCount"] == 17
        assert result["parentTitle"] == "The Beatles"
        assert result["summary"] == "Classic album."
        assert result["studio"] == "Apple Records"
        assert result["genre"] == "Rock, Pop"
        assert abs(result["rating"] - 0.9) < 1e-9
        assert "posterLocal" in result

    def test_returns_empty_dict_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None
        result = lib.getAlbum("600")
        assert result == {}

    def test_returns_empty_dict_when_metadata_not_found(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {}
        lib._client = mock_client
        result = lib.getAlbum("999")
        assert result == {}

    def test_poster_local_populated_when_thumb_path_present(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "600",
            "title": "Abbey Road",
            "thumb": "/library/metadata/600/thumb/1",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        mock_cache.get_poster.return_value = "file:///tmp/poster_cache/album.jpg"
        lib._poster_cache = mock_cache

        result = lib.getAlbum("600")

        mock_cache.get_poster.assert_called_once_with(
            mock_client, "/library/metadata/600/thumb/1"
        )
        assert result["posterLocal"] == "file:///tmp/poster_cache/album.jpg"

    def test_poster_local_empty_when_no_thumb_path(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "601",
            "title": "No Thumb Album",
        }
        lib._client = mock_client

        mock_cache = MagicMock()
        lib._poster_cache = mock_cache

        result = lib.getAlbum("601")

        mock_cache.get_poster.assert_not_called()
        assert result["posterLocal"] == ""

    def test_genre_empty_when_no_genres(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "602",
            "title": "Album Without Genre",
        }
        lib._client = mock_client

        result = lib.getAlbum("602")

        assert result["genre"] == ""

    def test_rating_zero_when_not_rated(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_metadata.return_value = {
            "ratingKey": "603",
            "title": "Unrated Album",
        }
        lib._client = mock_client

        result = lib.getAlbum("603")

        assert result["rating"] == 0.0


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

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.as_uri.return_value = "file:///tmp/poster_cache/album.jpg"
        mock_cache = MagicMock()
        mock_cache._cache_path.return_value = mock_path
        lib._poster_cache = mock_cache

        result = lib.getAlbums("500")

        mock_cache._cache_path.assert_called_once_with(
            "/library/metadata/600/thumb/1"
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
# PlexLibrary.getArtistAlbums
# ---------------------------------------------------------------------------


def _make_hub_response(hubs: list) -> list:
    """Helper to build a hub list as returned by get_hubs()."""
    return hubs


class TestGetArtistAlbums:
    def _make_hub(
        self,
        hub_id: str,
        title: str,
        metadata: list | None = None,
    ) -> dict:
        return {
            "hubIdentifier": hub_id,
            "title": title,
            "type": "album",
            "Metadata": metadata or [],
        }

    def _make_album_item(
        self,
        rating_key: str,
        title: str,
        year: int = 0,
        leaf_count: int = 0,
        thumb: str = "",
    ) -> dict:
        return {
            "type": "album",
            "ratingKey": rating_key,
            "title": title,
            "year": year,
            "leafCount": leaf_count,
            "thumb": thumb,
        }

    def test_returns_grouped_list_with_headers_and_albums(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "3 Albums", [
                self._make_album_item("600", "Abbey Road", 1969, 17),
                self._make_album_item("601", "Let It Be", 1970, 12),
                self._make_album_item("602", "Help!", 1965, 14),
            ]),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        # Should have 1 header + 3 albums = 4 entries
        assert len(result) == 4
        assert result[0]["type"] == "header"
        assert result[0]["title"] == "Albums"
        assert result[1]["type"] == "album"
        assert result[2]["type"] == "album"
        assert result[3]["type"] == "album"

    def test_filters_to_album_type_hubs_only(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "2 Albums", [
                self._make_album_item("600", "Abbey Road", 1969),
                self._make_album_item("601", "Let It Be", 1970),
            ]),
            # Non-album hubs should be ignored
            {
                "hubIdentifier": "hub.artist.similar",
                "title": "Similar Artists",
                "type": "artist",
                "Metadata": [{"ratingKey": "999", "title": "Similar Artist"}],
            },
            {
                "hubIdentifier": "hub.artist.popularTracks",
                "title": "Popular Tracks",
                "type": "track",
                "Metadata": [],
            },
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        # Only the albums hub should be included
        assert len(result) == 3  # 1 header + 2 albums
        types = [e["type"] for e in result]
        assert types == ["header", "album", "album"]

    def test_sorts_albums_within_category_by_year_descending(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "3 Albums", [
                self._make_album_item("600", "Abbey Road", 1969),
                self._make_album_item("601", "Let It Be", 1970),
                self._make_album_item("602", "Help!", 1965),
            ]),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        albums = [e for e in result if e["type"] == "album"]
        years = [a["year"] for a in albums]
        assert years == sorted(years, reverse=True)
        assert years == [1970, 1969, 1965]

    def test_strips_count_prefix_from_hub_titles(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "5 Albums", []),
            self._make_hub("hub.artist.albums.singles", "Singles & EPs", []),
            self._make_hub("hub.artist.albums.demo", "1 Album", []),
            self._make_hub("hub.artist.albums.compilation", "Compilations", []),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        headers = [e for e in result if e["type"] == "header"]
        titles = [h["title"] for h in headers]
        assert "Albums" in titles
        assert "Singles & EPs" in titles
        assert "Albums" in titles  # "1 Album" -> "Albums"
        assert "Compilations" in titles
        # Ensure no count prefix remains
        for title in titles:
            assert not title[0].isdigit(), f"Title '{title}' still has count prefix"

    def test_returns_empty_list_when_no_hubs_found(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = []
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        assert result == []

    def test_returns_empty_list_when_no_client(self) -> None:
        lib = _make_lib()
        lib._client = None

        result = lib.getArtistAlbums("500")

        assert result == []

    def test_multiple_hub_categories_preserve_order(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "2 Albums", [
                self._make_album_item("600", "Album A", 2020),
            ]),
            self._make_hub("hub.artist.albums.singles", "Singles & EPs", [
                self._make_album_item("700", "Single X", 2021),
            ]),
            self._make_hub("hub.artist.albums.compilation", "Compilations", [
                self._make_album_item("800", "Comp Z", 2019),
            ]),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        # Should be: header Albums, album A, header Singles & EPs, single X, header Compilations, comp Z
        assert len(result) == 6
        assert result[0] == {"type": "header", "title": "Albums"}
        assert result[1]["title"] == "Album A"
        assert result[2] == {"type": "header", "title": "Singles & EPs"}
        assert result[3]["title"] == "Single X"
        assert result[4] == {"type": "header", "title": "Compilations"}
        assert result[5]["title"] == "Comp Z"

    def test_album_entries_have_expected_keys(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "1 Album", [
                self._make_album_item("600", "Abbey Road", 1969, 17),
            ]),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        album = next(e for e in result if e["type"] == "album")
        assert "ratingKey" in album
        assert "title" in album
        assert "year" in album
        assert "leafCount" in album
        assert "posterLocal" in album
        assert album["ratingKey"] == "600"
        assert album["title"] == "Abbey Road"
        assert album["year"] == 1969
        assert album["leafCount"] == 17

    def test_poster_local_populated_when_thumb_present(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "1 Album", [
                self._make_album_item("600", "Abbey Road", 1969, 17, "/thumb/600"),
            ]),
        ]
        lib._client = mock_client

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.as_uri.return_value = "file:///tmp/poster_cache/album.jpg"
        mock_cache = MagicMock()
        mock_cache._cache_path.return_value = mock_path
        lib._poster_cache = mock_cache

        result = lib.getArtistAlbums("500")

        album = next(e for e in result if e["type"] == "album")
        mock_cache._cache_path.assert_called_once_with("/thumb/600")
        assert album["posterLocal"] == "file:///tmp/poster_cache/album.jpg"

    def test_hub_with_no_metadata_emits_only_header(self) -> None:
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_hubs.return_value = [
            self._make_hub("hub.artist.albums", "Albums", []),
        ]
        lib._client = mock_client

        result = lib.getArtistAlbums("500")

        assert len(result) == 1
        assert result[0]["type"] == "header"
        assert result[0]["title"] == "Albums"


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
# PlexLibrary.getRecentlyAddedAlbums — Task 011
# ---------------------------------------------------------------------------


class TestGetRecentlyAddedAlbums:
    def test_returns_album_dicts_with_correct_fields(self) -> None:
        """getRecentlyAddedAlbums returns album dicts with ratingKey, title, year, parentTitle, posterLocal."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "type": "album",
                        "ratingKey": "600",
                        "title": "Abbey Road",
                        "year": 1969,
                        "parentTitle": "The Beatles",
                        "thumb": "/library/metadata/600/thumb/1",
                    },
                    {
                        "type": "album",
                        "ratingKey": "601",
                        "title": "Let It Be",
                        "year": 1970,
                        "parentTitle": "The Beatles",
                        "thumb": "",
                    },
                ]
            }
        }
        lib._client = mock_client

        result = lib.getRecentlyAddedAlbums("3")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "600"
        assert result[0]["title"] == "Abbey Road"
        assert result[0]["year"] == 1969
        assert result[0]["parentTitle"] == "The Beatles"
        assert "posterLocal" in result[0]
        assert result[1]["ratingKey"] == "601"
        assert result[1]["title"] == "Let It Be"

    def test_filters_non_album_items(self) -> None:
        """getRecentlyAddedAlbums skips items whose type is not 'album'."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "type": "album",
                        "ratingKey": "600",
                        "title": "Abbey Road",
                        "year": 1969,
                        "parentTitle": "The Beatles",
                    },
                    {
                        "type": "track",
                        "ratingKey": "700",
                        "title": "Come Together",
                    },
                    {
                        "type": "artist",
                        "ratingKey": "500",
                        "title": "The Beatles",
                    },
                ]
            }
        }
        lib._client = mock_client

        result = lib.getRecentlyAddedAlbums("3")

        assert len(result) == 1
        assert result[0]["ratingKey"] == "600"

    def test_returns_empty_list_when_no_client(self) -> None:
        """getRecentlyAddedAlbums returns [] when no Plex client is configured."""
        lib = _make_lib()
        lib._client = None

        result = lib.getRecentlyAddedAlbums("3")

        assert result == []

    def test_returns_empty_list_when_api_returns_none(self) -> None:
        """getRecentlyAddedAlbums returns [] when the API call returns None."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = None
        lib._client = mock_client

        result = lib.getRecentlyAddedAlbums("3")

        assert result == []

    def test_returns_empty_list_when_metadata_missing(self) -> None:
        """getRecentlyAddedAlbums returns [] when MediaContainer has no Metadata key."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {"MediaContainer": {}}
        lib._client = mock_client

        result = lib.getRecentlyAddedAlbums("3")

        assert result == []

    def test_poster_local_populated_when_thumb_present(self) -> None:
        """getRecentlyAddedAlbums resolves poster via disk cache pre-resolve."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "type": "album",
                        "ratingKey": "600",
                        "title": "Abbey Road",
                        "thumb": "/library/metadata/600/thumb/1",
                    },
                ]
            }
        }
        lib._client = mock_client

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.as_uri.return_value = "file:///tmp/poster_cache/album.jpg"
        mock_cache = MagicMock()
        mock_cache._cache_path.return_value = mock_path
        lib._poster_cache = mock_cache

        result = lib.getRecentlyAddedAlbums("3")

        mock_cache._cache_path.assert_called_once_with(
            "/library/metadata/600/thumb/1"
        )
        assert result[0]["posterLocal"] == "file:///tmp/poster_cache/album.jpg"

    def test_calls_correct_api_endpoint(self) -> None:
        """getRecentlyAddedAlbums calls /library/sections/{key}/recentlyAdded."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client._get.return_value = {"MediaContainer": {"Metadata": []}}
        lib._client = mock_client

        lib.getRecentlyAddedAlbums("42")

        mock_client._get.assert_called_once_with("/library/sections/42/recentlyAdded")


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


# ---------------------------------------------------------------------------
# PlexLibrary.getPlaylists — Task 012
# ---------------------------------------------------------------------------


class TestGetPlaylists:
    def test_filters_to_audio_only_playlists(self) -> None:
        """getPlaylists returns only playlists with playlistType == 'audio'."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {"ratingKey": "1", "title": "My Music", "playlistType": "audio", "leafCount": 10, "duration": 3600000, "smart": False},
            {"ratingKey": "2", "title": "My Videos", "playlistType": "video", "leafCount": 5, "duration": 0, "smart": False},
            {"ratingKey": "3", "title": "Smart Music", "playlistType": "audio", "leafCount": 20, "duration": 7200000, "smart": True},
        ]
        lib._client = mock_client

        result = lib.getPlaylists()

        assert len(result) == 2
        assert all(p["ratingKey"] in ("1", "3") for p in result)

    def test_returns_correct_fields(self) -> None:
        """getPlaylists returns dicts with ratingKey, title, leafCount, duration, smart."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {"ratingKey": "42", "title": "Chill Vibes", "playlistType": "audio",
             "leafCount": 15, "duration": 5400000, "smart": False},
        ]
        lib._client = mock_client

        result = lib.getPlaylists()

        assert len(result) == 1
        pl = result[0]
        assert pl["ratingKey"] == "42"
        assert pl["title"] == "Chill Vibes"
        assert pl["leafCount"] == 15
        assert pl["duration"] == 5400000
        assert pl["smart"] is False

    def test_returns_empty_list_when_no_client(self) -> None:
        """getPlaylists returns [] when no Plex client is configured."""
        lib = _make_lib()
        lib._client = None

        result = lib.getPlaylists()

        assert result == []

    def test_returns_empty_list_when_no_audio_playlists(self) -> None:
        """getPlaylists returns [] when there are no audio playlists."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {"ratingKey": "1", "title": "Videos", "playlistType": "video", "leafCount": 3, "duration": 0},
        ]
        lib._client = mock_client

        result = lib.getPlaylists()

        assert result == []

    def test_handles_none_duration_and_leaf_count(self) -> None:
        """getPlaylists coerces None duration and leafCount to 0."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlists.return_value = [
            {"ratingKey": "1", "title": "Playlist", "playlistType": "audio",
             "leafCount": None, "duration": None, "smart": False},
        ]
        lib._client = mock_client

        result = lib.getPlaylists()

        assert result[0]["leafCount"] == 0
        assert result[0]["duration"] == 0


# ---------------------------------------------------------------------------
# PlexLibrary.getPlaylistTracks — Task 012
# ---------------------------------------------------------------------------


class TestGetPlaylistTracks:
    def test_returns_track_dicts_with_correct_fields(self) -> None:
        """getPlaylistTracks returns track dicts with all expected fields."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = [
            {
                "ratingKey": "700",
                "title": "Come Together",
                "index": 1,
                "duration": 259000,
                "parentTitle": "Abbey Road",
                "grandparentTitle": "The Beatles",
                "Media": [{"Part": [{"key": "/library/parts/12345/file.flac"}]}],
            },
            {
                "ratingKey": "800",
                "title": "Bohemian Rhapsody",
                "index": 1,
                "duration": 354000,
                "parentTitle": "A Night at the Opera",
                "grandparentTitle": "Queen",
                "Media": [{"Part": [{"key": "/library/parts/99999/file.flac"}]}],
            },
        ]
        lib._client = mock_client

        result = lib.getPlaylistTracks("42")

        assert len(result) == 2
        assert result[0]["ratingKey"] == "700"
        assert result[0]["title"] == "Come Together"
        assert result[0]["index"] == 1
        assert result[0]["durationMs"] == 259000
        assert result[0]["parentTitle"] == "Abbey Road"
        assert result[0]["grandparentTitle"] == "The Beatles"
        assert result[0]["mediaKey"] == "/library/parts/12345/file.flac"
        assert result[1]["ratingKey"] == "800"
        assert result[1]["grandparentTitle"] == "Queen"

    def test_returns_empty_list_when_no_client(self) -> None:
        """getPlaylistTracks returns [] when no Plex client is configured."""
        lib = _make_lib()
        lib._client = None

        result = lib.getPlaylistTracks("42")

        assert result == []

    def test_returns_empty_list_on_api_error(self) -> None:
        """getPlaylistTracks returns [] when the API returns an empty list."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = []
        lib._client = mock_client

        result = lib.getPlaylistTracks("42")

        assert result == []

    def test_all_expected_keys_present(self) -> None:
        """getPlaylistTracks track dicts have all required keys."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = [
            {"ratingKey": "700", "title": "Track"},
        ]
        lib._client = mock_client

        result = lib.getPlaylistTracks("42")

        assert len(result) == 1
        track = result[0]
        assert "ratingKey" in track
        assert "title" in track
        assert "index" in track
        assert "durationMs" in track
        assert "parentTitle" in track
        assert "grandparentTitle" in track
        assert "mediaKey" in track

    def test_calls_correct_rating_key(self) -> None:
        """getPlaylistTracks passes the rating_key to get_playlist_items."""
        lib = _make_lib()
        mock_client = MagicMock()
        mock_client.get_playlist_items.return_value = []
        lib._client = mock_client

        lib.getPlaylistTracks("99")

        mock_client.get_playlist_items.assert_called_once_with("99")


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
