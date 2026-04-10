"""Tests for LocalMusicLibrary backend.

Covers:
  - Config: local_music_directory save/load/setter
  - LocalArtistListModel: roles, set_artists, titleAt
  - LocalAlbumListModel: roles, set_albums
  - LocalMusicLibrary: scan with real mutagen, cache persistence, fetchArtistDetail,
    fetchAlbumDetail, sortArtists, getTrackStreamUrl, browseFolder traversal check,
    playFolder
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, Qt

from backend.config import Config

# Patch cache dirs before importing the module under test
import backend.local_music_library as lml_module
from backend.local_music_library import (
    LocalAlbumListModel,
    LocalArtistListModel,
    LocalMusicLibrary,
    _make_track_dict,
    _read_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, music_dir: Path | None = None) -> Config:
    config_file = tmp_path / "config.json"
    data = {}
    if music_dir is not None:
        data["local_music_directory"] = str(music_dir)
    config_file.write_text(json.dumps(data), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


def _make_library(tmp_path: Path, config: Config) -> LocalMusicLibrary:
    """Create a LocalMusicLibrary with cache dirs redirected to tmp_path."""
    cache_dir = tmp_path / "local_music_cache"
    art_dir = cache_dir / "art"
    cache_file = cache_dir / "library.json"
    with patch.object(lml_module, "_CACHE_DIR", cache_dir), \
         patch.object(lml_module, "_ART_CACHE_DIR", art_dir), \
         patch.object(lml_module, "_CACHE_FILE", cache_file):
        return LocalMusicLibrary(config)


def _create_minimal_mp3(path: Path, title: str = "Test Song", artist: str = "Test Artist",
                         album: str = "Test Album", track_num: int = 1) -> None:
    """Create a minimal valid MP3 file with ID3v2 tags using mutagen."""
    # Create a minimal MP3 frame (silent, valid MPEG audio frame)
    # MPEG1 Layer3, 128kbps, 44100Hz, stereo
    # Frame header: 0xFFFB9004
    frame_header = b"\xff\xfb\x90\x04"
    # Pad to a full frame (417 bytes for 128kbps MPEG1 Layer3 at 44100Hz)
    frame = frame_header + b"\x00" * 413
    # Write a few frames to make it recognizable
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(frame * 3)

    # Now add ID3 tags with mutagen
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC, TCON
    try:
        tags = ID3(str(path))
    except Exception:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=[title]))
    tags.add(TPE1(encoding=3, text=[artist]))
    tags.add(TALB(encoding=3, text=[album]))
    tags.add(TRCK(encoding=3, text=[f"{track_num}"]))
    tags.add(TDRC(encoding=3, text=["2023"]))
    tags.add(TCON(encoding=3, text=["Rock"]))
    tags.save(str(path))


def _create_mp3_with_art(path: Path, title: str = "Art Song", artist: str = "Art Artist",
                          album: str = "Art Album") -> None:
    """Create a minimal MP3 with embedded APIC album art."""
    _create_minimal_mp3(path, title=title, artist=artist, album=album)
    from mutagen.id3 import ID3, APIC
    tags = ID3(str(path))
    # 1x1 JPEG placeholder
    jpeg_data = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\x9e\xa7("
        b"\xff\xd9"
    )
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpeg_data))
    tags.save(str(path))


def _process_events():
    """Process pending Qt events to deliver queued signals."""
    app = QCoreApplication.instance()
    if app:
        app.processEvents()


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfigLocalMusicDirectory:
    def test_default_is_none(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.local_music_directory is None

    def test_set_and_load(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("{}", encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_local_music_directory("/music/library")
            assert config.local_music_directory == Path("/music/library")

            # Reload and verify persistence
            config2 = Config()
            assert config2.local_music_directory == Path("/music/library")

    def test_save_includes_local_music_directory(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("{}", encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_local_music_directory("/home/user/Music")
            raw = json.loads(config_file.read_text(encoding="utf-8"))
            assert raw["local_music_directory"] == "/home/user/Music"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestLocalArtistListModel:
    def test_roles(self) -> None:
        model = LocalArtistListModel()
        names = model.roleNames()
        assert b"title" in names.values()
        assert b"genre" in names.values()
        assert b"albumCount" in names.values()
        assert b"imageLocal" in names.values()

    def test_set_artists_and_data(self) -> None:
        model = LocalArtistListModel()
        model.set_artists([
            {"title": "Artist A", "genre": "Rock", "albumCount": 3, "imageLocal": ""},
            {"title": "Artist B", "genre": "Jazz", "albumCount": 1, "imageLocal": "file:///art.jpg"},
        ])
        assert model.rowCount() == 2
        idx = model.index(0, 0)
        assert model.data(idx, LocalArtistListModel.TitleRole) == "Artist A"
        assert model.data(idx, LocalArtistListModel.GenreRole) == "Rock"
        assert model.data(idx, LocalArtistListModel.AlbumCountRole) == 3

        idx1 = model.index(1, 0)
        assert model.data(idx1, LocalArtistListModel.ImageLocalRole) == "file:///art.jpg"

    def test_titleAt(self) -> None:
        model = LocalArtistListModel()
        model.set_artists([{"title": "Solo", "genre": "", "albumCount": 1, "imageLocal": ""}])
        assert model.titleAt(0) == "Solo"
        assert model.titleAt(5) == ""


class TestLocalAlbumListModel:
    def test_roles(self) -> None:
        model = LocalAlbumListModel()
        names = model.roleNames()
        assert b"title" in names.values()
        assert b"artist" in names.values()
        assert b"year" in names.values()
        assert b"trackCount" in names.values()
        assert b"posterLocal" in names.values()
        assert b"folderPath" in names.values()

    def test_set_albums_and_data(self) -> None:
        model = LocalAlbumListModel()
        model.set_albums([{
            "title": "Album X",
            "artist": "Artist Y",
            "year": 2020,
            "trackCount": 10,
            "posterLocal": "",
            "folderPath": "/music/artist/album",
        }])
        assert model.rowCount() == 1
        idx = model.index(0, 0)
        assert model.data(idx, LocalAlbumListModel.TitleRole) == "Album X"
        assert model.data(idx, LocalAlbumListModel.YearRole) == 2020


# ---------------------------------------------------------------------------
# Tag reading tests
# ---------------------------------------------------------------------------


class TestReadTags:
    def test_read_mp3_tags(self, tmp_path: Path) -> None:
        mp3 = tmp_path / "test.mp3"
        _create_minimal_mp3(mp3, title="Hello", artist="World", album="Debut", track_num=3)
        tags = _read_tags(mp3)
        assert tags["title"] == "Hello"
        assert tags["artist"] == "World"
        assert tags["album"] == "Debut"
        assert tags["tracknumber"] == 3
        assert tags["year"] == 2023
        assert tags["genre"] == "Rock"

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        tags = _read_tags(tmp_path / "nope.mp3")
        assert tags == {} or tags.get("artist") is not None  # graceful failure


class TestMakeTrackDict:
    def test_includes_stream_url_and_rating_key(self, tmp_path: Path) -> None:
        mp3 = tmp_path / "song.mp3"
        mp3.write_bytes(b"\x00")  # dummy
        tags = {"title": "Song", "tracknumber": 1, "duration_ms": 3000,
                "album": "Alb", "artist": "Art"}
        d = _make_track_dict(mp3, tags)
        assert d["streamUrl"].startswith("file://")
        assert d["ratingKey"] == ""
        assert d["title"] == "Song"
        assert d["parentTitle"] == "Alb"
        assert d["grandparentTitle"] == "Art"


# ---------------------------------------------------------------------------
# LocalMusicLibrary integration tests
# ---------------------------------------------------------------------------


class TestLocalMusicLibraryScan:
    def test_scan_populates_artists(self, tmp_path: Path) -> None:
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        _create_minimal_mp3(music_dir / "song1.mp3", artist="Alpha", album="First", track_num=1)
        _create_minimal_mp3(music_dir / "song2.mp3", artist="Beta", album="Second", track_num=1)

        cache_dir = tmp_path / "cache"
        art_dir = cache_dir / "art"
        cache_file = cache_dir / "library.json"

        config = _make_config(tmp_path, music_dir=music_dir)

        with patch.object(lml_module, "_CACHE_DIR", cache_dir), \
             patch.object(lml_module, "_ART_CACHE_DIR", art_dir), \
             patch.object(lml_module, "_CACHE_FILE", cache_file):
            lib = LocalMusicLibrary(config)
            lib.scan()

            # Wait for async scan to finish
            import time
            for _ in range(50):
                _process_events()
                time.sleep(0.05)
                if not lib._scanning:
                    break

            assert not lib._scanning
            assert lib._artists_model.rowCount() == 2
            # Cache should be written
            assert cache_file.exists()

    def test_scan_noop_when_no_directory(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        lib.scan()
        assert not lib._scanning

    def test_cache_loads_on_startup(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "local_music_cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "library.json"
        cache_file.write_text(json.dumps({
            "Cached Artist": {
                "albums": {
                    "Cached Album": {
                        "year": 2021,
                        "genre": "Pop",
                        "tracks": [{"title": "Song", "track_num": 1, "duration_ms": 3000, "file_path": "/x.mp3"}],
                        "folder_path": "/music/cached",
                        "art_path": "",
                    }
                }
            }
        }), encoding="utf-8")

        config = _make_config(tmp_path)
        with patch.object(lml_module, "_CACHE_DIR", cache_dir), \
             patch.object(lml_module, "_ART_CACHE_DIR", cache_dir / "art"), \
             patch.object(lml_module, "_CACHE_FILE", cache_file):
            lib = LocalMusicLibrary(config)

        assert lib._artists_model.rowCount() == 1
        idx = lib._artists_model.index(0, 0)
        assert lib._artists_model.data(idx, LocalArtistListModel.TitleRole) == "Cached Artist"


class TestLocalMusicLibrarySlots:
    def _make_lib_with_data(self, tmp_path: Path) -> LocalMusicLibrary:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        lib._library_data = {
            "Artist A": {
                "albums": {
                    "Album 1": {
                        "year": 2020,
                        "genre": "Rock",
                        "tracks": [
                            {"title": "Track 1", "track_num": 1, "duration_ms": 3000, "file_path": "/music/a/t1.mp3"},
                            {"title": "Track 2", "track_num": 2, "duration_ms": 4000, "file_path": "/music/a/t2.mp3"},
                        ],
                        "folder_path": "/music/a",
                        "art_path": "",
                    }
                }
            },
            "Artist B": {
                "albums": {
                    "Album 2": {
                        "year": 2019,
                        "genre": "Jazz",
                        "tracks": [],
                        "folder_path": "/music/b",
                        "art_path": "",
                    }
                }
            },
        }
        lib._rebuild_artists_model()
        return lib

    def test_sort_artists_az(self, tmp_path: Path) -> None:
        lib = self._make_lib_with_data(tmp_path)
        lib.sortArtists("za")
        idx0 = lib._artists_model.index(0, 0)
        assert lib._artists_model.data(idx0, LocalArtistListModel.TitleRole) == "Artist B"
        lib.sortArtists("az")
        idx0 = lib._artists_model.index(0, 0)
        assert lib._artists_model.data(idx0, LocalArtistListModel.TitleRole) == "Artist A"

    def test_get_track_stream_url(self, tmp_path: Path) -> None:
        lib = self._make_lib_with_data(tmp_path)
        url = lib.getTrackStreamUrl("/music/test.mp3")
        assert url.startswith("file:///")
        assert "test.mp3" in url

    def test_fetch_artist_detail(self, tmp_path: Path) -> None:
        lib = self._make_lib_with_data(tmp_path)
        results = []
        lib.artistDetailReady.connect(lambda name, data: results.append((name, data)))
        lib.fetchArtistDetail("Artist A")

        import time
        for _ in range(50):
            _process_events()
            time.sleep(0.05)
            if results:
                break

        assert len(results) == 1
        name, data = results[0]
        assert name == "Artist A"
        assert data["artist"]["title"] == "Artist A"
        assert data["artist"]["albumCount"] == 1
        assert len(data["albums"]) == 2  # 1 header + 1 album
        assert data["albums"][0]["type"] == "header"
        assert data["albums"][1]["type"] == "album"
        assert data["albums"][1]["title"] == "Album 1"

    def test_fetch_album_detail(self, tmp_path: Path) -> None:
        lib = self._make_lib_with_data(tmp_path)
        results = []
        lib.albumDetailReady.connect(lambda path, data: results.append((path, data)))
        lib.fetchAlbumDetail("/music/a")

        import time
        for _ in range(50):
            _process_events()
            time.sleep(0.05)
            if results:
                break

        assert len(results) == 1
        path, data = results[0]
        assert path == "/music/a"
        assert data["album"]["title"] == "Album 1"
        assert data["album"]["artist"] == "Artist A"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["ratingKey"] == ""
        assert data["tracks"][0]["streamUrl"].startswith("file://")

    def test_browse_folder_traversal_blocked(self, tmp_path: Path) -> None:
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        config = _make_config(tmp_path, music_dir=music_dir)
        lib = _make_library(tmp_path, config)
        results = []
        lib.folderContentsReady.connect(lambda p, d: results.append((p, d)))
        # Try to browse outside music dir
        lib.browseFolder("/etc/passwd")
        _process_events()
        import time
        time.sleep(0.1)
        _process_events()
        # Should not have emitted any result
        assert len(results) == 0

    def test_browse_folder_valid(self, tmp_path: Path) -> None:
        music_dir = tmp_path / "music"
        subdir = music_dir / "artist"
        subdir.mkdir(parents=True)
        _create_minimal_mp3(subdir / "song.mp3")

        config = _make_config(tmp_path, music_dir=music_dir)
        lib = _make_library(tmp_path, config)
        results = []
        lib.folderContentsReady.connect(lambda p, d: results.append((p, d)))
        lib.browseFolder(str(music_dir))

        import time
        for _ in range(50):
            _process_events()
            time.sleep(0.05)
            if results:
                break

        assert len(results) == 1
        _, data = results[0]
        assert len(data["folders"]) == 1
        assert data["folders"][0]["name"] == "artist"
        assert data["folders"][0]["itemCount"] == 1

    def test_play_folder(self, tmp_path: Path) -> None:
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        _create_minimal_mp3(music_dir / "song.mp3", title="Play Me")

        config = _make_config(tmp_path, music_dir=music_dir)
        lib = _make_library(tmp_path, config)
        result = lib.playFolder(str(music_dir))
        assert len(result["tracks"]) == 1
        assert result["tracks"][0]["streamUrl"].startswith("file://")
        assert result["tracks"][0]["ratingKey"] == ""

    def test_play_folder_traversal_blocked(self, tmp_path: Path) -> None:
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        config = _make_config(tmp_path, music_dir=music_dir)
        lib = _make_library(tmp_path, config)
        result = lib.playFolder("/etc")
        assert result == {"tracks": []}


class TestAlbumArtExtraction:
    def test_extract_art_from_mp3(self, tmp_path: Path) -> None:
        from backend.local_music_library import _extract_album_art
        mp3 = tmp_path / "art_song.mp3"
        _create_mp3_with_art(mp3)

        art_cache = tmp_path / "art_cache"
        with patch.object(lml_module, "_ART_CACHE_DIR", art_cache):
            result = _extract_album_art(mp3, str(tmp_path))
        assert result != ""
        assert Path(result).exists()
        # Verify it wrote image data
        assert Path(result).stat().st_size > 0
