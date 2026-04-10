"""Local music library backend for HTPC Station.

Scans a user-configured directory for audio files, extracts metadata via
mutagen, and exposes artist/album/track data to QML via QAbstractListModel
subclasses and a LocalMusicLibrary QObject orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import mutagen
import mutagen.flac
import mutagen.id3
import mutagen.mp4

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.config import Config

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "htpcstation"
_CACHE_DIR = _CONFIG_DIR / "local_music_cache"
_ART_CACHE_DIR = _CACHE_DIR / "art"
_CACHE_FILE = _CACHE_DIR / "library.json"

AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wma", ".wav", ".aac", ".aif", ".aiff",
})


# ---------------------------------------------------------------------------
# LocalArtistListModel
# ---------------------------------------------------------------------------


class LocalArtistListModel(QAbstractListModel):
    """Model for a list of local music artists.

    Roles: title, genre, albumCount, imageLocal
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    GenreRole = Qt.ItemDataRole.UserRole + 2
    AlbumCountRole = Qt.ItemDataRole.UserRole + 3
    ImageLocalRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._artists: list[dict] = []

    def set_artists(self, artists: list[dict]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._artists = artists
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._artists)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._artists)):
            return None
        artist = self._artists[index.row()]
        if role == self.TitleRole:
            return artist.get("title", "")
        if role == self.GenreRole:
            return artist.get("genre", "")
        if role == self.AlbumCountRole:
            return artist.get("albumCount", 0)
        if role == self.ImageLocalRole:
            return artist.get("imageLocal", "")
        if role == Qt.ItemDataRole.DisplayRole:
            return artist.get("title", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.GenreRole: b"genre",
            self.AlbumCountRole: b"albumCount",
            self.ImageLocalRole: b"imageLocal",
        }

    @Slot(int, result=str)
    def titleAt(self, index: int) -> str:
        """Return the title of the artist at *index*, or "" if out of range."""
        if 0 <= index < len(self._artists):
            return self._artists[index].get("title", "")
        return ""


# ---------------------------------------------------------------------------
# LocalAlbumListModel
# ---------------------------------------------------------------------------


class LocalAlbumListModel(QAbstractListModel):
    """Model for a list of local music albums.

    Roles: title, artist, year, trackCount, posterLocal, folderPath
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    ArtistRole = Qt.ItemDataRole.UserRole + 2
    YearRole = Qt.ItemDataRole.UserRole + 3
    TrackCountRole = Qt.ItemDataRole.UserRole + 4
    PosterLocalRole = Qt.ItemDataRole.UserRole + 5
    FolderPathRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._albums: list[dict] = []

    def set_albums(self, albums: list[dict]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._albums = albums
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._albums)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._albums)):
            return None
        album = self._albums[index.row()]
        if role == self.TitleRole:
            return album.get("title", "")
        if role == self.ArtistRole:
            return album.get("artist", "")
        if role == self.YearRole:
            return album.get("year", 0)
        if role == self.TrackCountRole:
            return album.get("trackCount", 0)
        if role == self.PosterLocalRole:
            return album.get("posterLocal", "")
        if role == self.FolderPathRole:
            return album.get("folderPath", "")
        if role == Qt.ItemDataRole.DisplayRole:
            return album.get("title", "")
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.ArtistRole: b"artist",
            self.YearRole: b"year",
            self.TrackCountRole: b"trackCount",
            self.PosterLocalRole: b"posterLocal",
            self.FolderPathRole: b"folderPath",
        }


# ---------------------------------------------------------------------------
# LocalMusicLibrary — main orchestrator
# ---------------------------------------------------------------------------


class LocalMusicLibrary(QObject):
    """Manages local music data and exposes it to QML.

    Scans a configured directory for audio files, extracts metadata,
    caches results to disk, and provides models and slots for QML.
    """

    # Public signals
    artistsModelChanged = Signal()
    scanningChanged = Signal()
    scanComplete = Signal()
    artistDetailReady = Signal(str, "QVariant")
    albumDetailReady = Signal(str, "QVariant")
    folderContentsReady = Signal(str, "QVariant")

    # Internal signals for worker→main thread marshalling
    _scanFinished = Signal(object)     # library_data dict
    _artistDetailResult = Signal(str, object)
    _albumDetailResult = Signal(str, object)
    _folderContentsResult = Signal(str, object)

    def __init__(self, config: Config, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._config = config
        self._scanning = False
        self._library_data: dict = {}  # {artist_name: {albums: {album_title: {...}}}}
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Models
        self._artists_model = LocalArtistListModel(self)

        # Connect internal signals
        self._scanFinished.connect(self._on_scan_finished, Qt.ConnectionType.QueuedConnection)
        self._artistDetailResult.connect(
            lambda name, data: self.artistDetailReady.emit(name, data),
            Qt.ConnectionType.QueuedConnection,
        )
        self._albumDetailResult.connect(
            lambda path, data: self.albumDetailReady.emit(path, data),
            Qt.ConnectionType.QueuedConnection,
        )
        self._folderContentsResult.connect(
            lambda path, data: self.folderContentsReady.emit(path, data),
            Qt.ConnectionType.QueuedConnection,
        )

        # Load cached data if available
        self._load_cache()

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    def _get_artists_model(self) -> LocalArtistListModel:
        return self._artists_model

    def _get_scanning(self) -> bool:
        return self._scanning

    artistsModel = Property(
        QObject,
        fget=_get_artists_model,
        notify=artistsModelChanged,
    )
    scanning = Property(
        bool,
        fget=_get_scanning,
        notify=scanningChanged,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def scan(self) -> None:
        """Trigger a full directory scan (async). No-op if already scanning."""
        if self._scanning:
            return
        music_dir = self._config.local_music_directory
        if music_dir is None:
            logger.info("LocalMusicLibrary.scan: no music directory configured")
            return
        music_dir = Path(music_dir)
        if not music_dir.is_dir():
            logger.warning("LocalMusicLibrary.scan: directory does not exist: %s", music_dir)
            return
        self._scanning = True
        self.scanningChanged.emit()
        self._executor.submit(self._worker_scan, music_dir)

    @Slot(str)
    def fetchArtistDetail(self, artist_name: str) -> None:
        """Look up artist from cached data, emit artistDetailReady."""
        self._executor.submit(self._worker_fetch_artist_detail, artist_name)

    @Slot(str)
    def fetchAlbumDetail(self, folder_path: str) -> None:
        """Look up album tracks from cached data, emit albumDetailReady."""
        self._executor.submit(self._worker_fetch_album_detail, folder_path)

    @Slot(str)
    def sortArtists(self, sort_key: str) -> None:
        """Sort the artists model in-place. Keys: 'az' (A-Z), 'za' (Z-A)."""
        artists = list(self._artists_model._artists)
        if sort_key == "az":
            artists.sort(key=lambda a: a.get("title", "").lower())
        elif sort_key == "za":
            artists.sort(key=lambda a: a.get("title", "").lower(), reverse=True)
        else:
            logger.warning("sortArtists: unknown sort_key '%s'", sort_key)
            return
        self._artists_model.set_artists(artists)

    @Slot(str, result=str)
    def getTrackStreamUrl(self, file_path: str) -> str:
        """Return a file:// URI for the given file path."""
        return Path(file_path).as_uri()

    @Slot(str)
    def browseFolder(self, folder_path: str) -> None:
        """List subfolders and audio files at the given path. Emit folderContentsReady.

        Validates that the path is under the configured music directory.
        """
        music_dir = self._config.local_music_directory
        if music_dir is None:
            return
        music_dir = Path(music_dir).resolve()
        target = Path(folder_path).resolve()
        # Security: prevent directory traversal
        try:
            target.relative_to(music_dir)
        except ValueError:
            logger.warning("browseFolder: path '%s' is outside music directory", folder_path)
            return
        self._executor.submit(self._worker_browse_folder, str(target))

    @Slot(str, result="QVariant")
    def playFolder(self, folder_path: str) -> object:
        """Return album-like data for a folder (track dicts for all audio files in it)."""
        music_dir = self._config.local_music_directory
        if music_dir is None:
            return {"tracks": []}
        music_dir_resolved = Path(music_dir).resolve()
        target = Path(folder_path).resolve()
        # Security: prevent directory traversal
        try:
            target.relative_to(music_dir_resolved)
        except ValueError:
            logger.warning("playFolder: path '%s' is outside music directory", folder_path)
            return {"tracks": []}
        if not target.is_dir():
            return {"tracks": []}
        tracks = []
        for child in sorted(target.iterdir()):
            if child.is_file() and child.suffix.lower() in AUDIO_EXTENSIONS:
                tags = _read_tags(child)
                tracks.append(_make_track_dict(child, tags))
        return {"tracks": tracks}

    # ------------------------------------------------------------------
    # Internal: main-thread handlers
    # ------------------------------------------------------------------

    def _on_scan_finished(self, library_data: object) -> None:
        """Handle scan completion on the main thread."""
        self._library_data = library_data
        self._rebuild_artists_model()
        self._scanning = False
        self.scanningChanged.emit()
        self.scanComplete.emit()
        logger.info(
            "LocalMusicLibrary: scan complete — %d artist(s)",
            len(self._library_data),
        )

    def _rebuild_artists_model(self) -> None:
        """Build the artists model from cached library data."""
        artists = []
        for artist_name, artist_data in self._library_data.items():
            albums = artist_data.get("albums", {})
            # Pick the first available art from any album
            image_local = ""
            genre = ""
            for album_data in albums.values():
                if not image_local and album_data.get("art_path"):
                    art = Path(album_data["art_path"])
                    if art.exists():
                        image_local = art.as_uri()
                if not genre and album_data.get("genre"):
                    genre = album_data["genre"]
            artists.append({
                "title": artist_name,
                "genre": genre,
                "albumCount": len(albums),
                "imageLocal": image_local,
            })
        artists.sort(key=lambda a: a["title"].lower())
        self._artists_model.set_artists(artists)
        self.artistsModelChanged.emit()

    # ------------------------------------------------------------------
    # Internal: cache
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        """Load library data from disk cache if available."""
        if not _CACHE_FILE.exists():
            return
        try:
            raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._library_data = raw
                self._rebuild_artists_model()
                logger.info("LocalMusicLibrary: loaded cache with %d artist(s)", len(raw))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("LocalMusicLibrary: failed to load cache: %s", exc)

    def _save_cache(self, library_data: dict) -> None:
        """Write library data to disk cache. Called from worker thread."""
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(json.dumps(library_data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("LocalMusicLibrary: failed to save cache: %s", exc)

    # ------------------------------------------------------------------
    # Internal: worker thread functions
    # ------------------------------------------------------------------

    def _worker_scan(self, music_dir: Path) -> None:
        """Scan music directory recursively. Runs on executor thread."""
        try:
            library_data: dict = {}  # {artist: {albums: {album: {year, genre, tracks, folder_path, art_path}}}}

            _ART_CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # Track which albums we've already extracted art for (by folder_path)
            art_extracted: dict[str, str] = {}

            for root, _dirs, files in os.walk(music_dir):
                root_path = Path(root)
                for filename in files:
                    file_path = root_path / filename
                    if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue

                    tags = _read_tags(file_path)
                    artist_name = tags.get("artist", "Unknown Artist")
                    album_title = tags.get("album", "Unknown Album")
                    track_title = tags.get("title", file_path.stem)
                    track_num = tags.get("tracknumber", 0)
                    year = tags.get("year", 0)
                    genre = tags.get("genre", "")
                    duration_ms = tags.get("duration_ms", 0)
                    codec_info = tags.get("codec_info", "")
                    folder_path = str(root_path)

                    # Ensure artist entry
                    if artist_name not in library_data:
                        library_data[artist_name] = {"albums": {}}

                    artist_albums = library_data[artist_name]["albums"]

                    # Ensure album entry
                    if album_title not in artist_albums:
                        artist_albums[album_title] = {
                            "year": year,
                            "genre": genre,
                            "tracks": [],
                            "folder_path": folder_path,
                            "art_path": "",
                        }

                    album_data = artist_albums[album_title]
                    album_data["tracks"].append({
                        "title": track_title,
                        "track_num": track_num,
                        "duration_ms": duration_ms,
                        "file_path": str(file_path),
                        "codec_info": codec_info,
                    })

                    # Extract album art (once per folder)
                    if folder_path not in art_extracted:
                        art_path = _extract_album_art(file_path, folder_path)
                        art_extracted[folder_path] = art_path
                        if art_path:
                            album_data["art_path"] = art_path

            # Sort tracks within each album by track number
            for artist_data in library_data.values():
                for album_data in artist_data["albums"].values():
                    album_data["tracks"].sort(key=lambda t: t["track_num"])

            # Save cache to disk
            self._save_cache(library_data)

            # Marshal result to main thread
            self._scanFinished.emit(library_data)
        except Exception:
            logger.exception("LocalMusicLibrary._worker_scan: unexpected error")
            self._scanFinished.emit({})

    def _worker_fetch_artist_detail(self, artist_name: str) -> None:
        """Build artist detail data from cache. Runs on executor thread."""
        artist_data = self._library_data.get(artist_name)
        if artist_data is None:
            self._artistDetailResult.emit(artist_name, {"artist": {}, "albums": []})
            return

        albums_dict = artist_data.get("albums", {})

        # Build artist info
        image_local = ""
        genre = ""
        for album_data in albums_dict.values():
            if not image_local and album_data.get("art_path"):
                art = Path(album_data["art_path"])
                if art.exists():
                    image_local = art.as_uri()
            if not genre and album_data.get("genre"):
                genre = album_data["genre"]

        artist_info = {
            "title": artist_name,
            "genre": genre,
            "albumCount": len(albums_dict),
            "imageLocal": image_local,
        }

        # Build albums list with headers (match Plex pattern)
        albums_list: list[dict] = []
        album_entries = []
        for album_title, album_data in albums_dict.items():
            poster_local = ""
            if album_data.get("art_path"):
                art = Path(album_data["art_path"])
                if art.exists():
                    poster_local = art.as_uri()
            album_entries.append({
                "type": "album",
                "title": album_title,
                "year": album_data.get("year", 0),
                "trackCount": len(album_data.get("tracks", [])),
                "posterLocal": poster_local,
                "folderPath": album_data.get("folder_path", ""),
            })
        album_entries.sort(key=lambda a: a["year"] or 0, reverse=True)
        if album_entries:
            albums_list.append({"type": "header", "title": "Albums"})
            albums_list.extend(album_entries)

        self._artistDetailResult.emit(artist_name, {"artist": artist_info, "albums": albums_list})

    def _worker_fetch_album_detail(self, folder_path: str) -> None:
        """Build album detail data from cache. Runs on executor thread."""
        # Find the album matching this folder_path
        album_info: dict = {}
        tracks: list[dict] = []

        for artist_name, artist_data in self._library_data.items():
            for album_title, album_data in artist_data.get("albums", {}).items():
                if album_data.get("folder_path") == folder_path:
                    poster_local = ""
                    if album_data.get("art_path"):
                        art = Path(album_data["art_path"])
                        if art.exists():
                            poster_local = art.as_uri()

                    album_info = {
                        "title": album_title,
                        "artist": artist_name,
                        "year": album_data.get("year", 0),
                        "trackCount": len(album_data.get("tracks", [])),
                        "posterLocal": poster_local,
                        "genre": album_data.get("genre", ""),
                        "source": "local",
                        "folderPath": folder_path,
                    }

                    for track in album_data.get("tracks", []):
                        file_path = track["file_path"]
                        codec = track.get("codec_info", "")
                        if not codec:
                            # Old cache without codec_info — derive from file on disk
                            codec = _codec_info_from_file(Path(file_path))
                        tracks.append({
                            "title": track["title"],
                            "index": track["track_num"],
                            "durationMs": track["duration_ms"],
                            "parentTitle": album_title,
                            "grandparentTitle": artist_name,
                            "streamUrl": Path(file_path).as_uri(),
                            "ratingKey": "",
                            "codecInfo": codec,
                        })
                    break
            if album_info:
                break

        self._albumDetailResult.emit(folder_path, {"album": album_info, "tracks": tracks})

    def _worker_browse_folder(self, folder_path: str) -> None:
        """List folder contents. Runs on executor thread."""
        target = Path(folder_path)
        folders: list[dict] = []
        tracks: list[dict] = []

        if not target.is_dir():
            self._folderContentsResult.emit(folder_path, {"folders": [], "tracks": []})
            return

        for child in sorted(target.iterdir()):
            if child.is_dir():
                # Count audio files in subfolder
                item_count = sum(
                    1 for f in child.iterdir()
                    if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
                )
                folders.append({
                    "name": child.name,
                    "path": str(child),
                    "itemCount": item_count,
                })
            elif child.is_file() and child.suffix.lower() in AUDIO_EXTENSIONS:
                tags = _read_tags(child)
                tracks.append(_make_track_dict(child, tags))

        self._folderContentsResult.emit(folder_path, {"folders": folders, "tracks": tracks})


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _read_tags(file_path: Path) -> dict:
    """Read metadata tags from an audio file using mutagen (easy mode).

    Returns a dict with keys: artist, album, title, tracknumber, year, genre, duration_ms.
    """
    result: dict = {}
    try:
        audio = mutagen.File(str(file_path), easy=True)
        if audio is None:
            return result
        result["artist"] = _first_tag(audio, "artist", "Unknown Artist")
        result["album"] = _first_tag(audio, "album", "Unknown Album")
        result["title"] = _first_tag(audio, "title", file_path.stem)
        result["genre"] = _first_tag(audio, "genre", "")

        # Track number: may be "3/12" format
        raw_track = _first_tag(audio, "tracknumber", "0")
        try:
            result["tracknumber"] = int(raw_track.split("/")[0])
        except (ValueError, IndexError):
            result["tracknumber"] = 0

        # Year: extract from date tag
        raw_date = _first_tag(audio, "date", "")
        try:
            result["year"] = int(raw_date[:4]) if len(raw_date) >= 4 else 0
        except ValueError:
            result["year"] = 0

        # Duration
        if audio.info and hasattr(audio.info, "length"):
            result["duration_ms"] = int(audio.info.length * 1000)
        else:
            result["duration_ms"] = 0

        # Codec info
        result["codec_info"] = _format_codec_info(audio, file_path)
    except Exception:
        logger.debug("_read_tags: failed to read tags from %s", file_path, exc_info=True)
    return result


def _codec_info_from_file(file_path: Path) -> str:
    """Read codec info from an audio file (used for cache entries missing the field)."""
    try:
        audio = mutagen.File(str(file_path), easy=True)
        if audio is None:
            return ""
        return _format_codec_info(audio, file_path)
    except Exception:
        return ""


def _format_codec_info(audio: object, file_path: Path) -> str:
    """Build a codec summary string like 'FLAC 44.1/16', 'MP3 256', 'OPUS 64'."""
    info = audio.info  # type: ignore[union-attr]
    if info is None:
        return ""

    # Codec name from file extension
    ext = file_path.suffix.lower().lstrip(".")
    codec_map = {
        "flac": "FLAC", "mp3": "MP3", "ogg": "OGG", "opus": "OPUS",
        "m4a": "AAC", "aac": "AAC", "wma": "WMA", "wav": "WAV",
        "aif": "AIFF", "aiff": "AIFF",
    }
    codec = codec_map.get(ext, ext.upper())

    # Lossless formats: show sample_rate / bits_per_sample
    sample_rate = getattr(info, "sample_rate", 0)
    bits = getattr(info, "bits_per_sample", 0)
    if codec in ("FLAC", "WAV", "AIFF") and sample_rate:
        sr = sample_rate / 1000  # e.g. 44100 -> 44.1
        sr_str = f"{sr:g}"  # drop trailing zeros
        if bits:
            return f"{codec} {sr_str}/{bits}"
        return f"{codec} {sr_str}"

    # Lossy formats: show bitrate in kbps
    bitrate = getattr(info, "bitrate", 0)
    if bitrate:
        kbps = round(bitrate / 1000)
        return f"{codec} {kbps}"

    return codec


def _first_tag(audio: object, key: str, default: str) -> str:
    """Extract the first value from an EasyID3/EasyMP4-like tag dict."""
    values = audio.get(key)  # type: ignore[union-attr]
    if values and isinstance(values, list) and len(values) > 0:
        return str(values[0])
    return default


def _extract_album_art(file_path: Path, folder_path: str) -> str:
    """Extract embedded album art from an audio file.

    Returns the path to the saved art file, or "" if no art found.
    Uses mutagen.File without easy=True to access picture data.
    """
    try:
        audio = mutagen.File(str(file_path))
        if audio is None:
            return ""

        image_data: bytes | None = None

        # ID3 (MP3, etc.) — APIC frames
        if hasattr(audio, "tags") and audio.tags is not None:
            if isinstance(audio.tags, mutagen.id3.ID3):
                for key in audio.tags:
                    if key.startswith("APIC"):
                        frame = audio.tags[key]
                        if hasattr(frame, "data") and frame.data:
                            image_data = frame.data
                            break

        # FLAC — pictures list
        if image_data is None and isinstance(audio, mutagen.flac.FLAC):
            if audio.pictures:
                image_data = audio.pictures[0].data

        # Vorbis comments (OGG/Opus) — METADATA_BLOCK_PICTURE
        if image_data is None and hasattr(audio, "tags") and audio.tags is not None:
            import base64
            pictures = audio.tags.get("metadata_block_picture") or audio.tags.get("METADATA_BLOCK_PICTURE")
            if pictures:
                try:
                    pic = mutagen.flac.Picture(base64.b64decode(pictures[0]))
                    if pic.data:
                        image_data = pic.data
                except Exception:
                    pass

        # M4A/MP4 — covr
        if image_data is None and isinstance(audio, mutagen.mp4.MP4):
            covr = audio.tags.get("covr") if audio.tags else None
            if covr and len(covr) > 0:
                image_data = bytes(covr[0])

        if image_data is None:
            return ""

        # Save to art cache
        folder_hash = hashlib.sha256(folder_path.encode("utf-8")).hexdigest()
        art_path = _ART_CACHE_DIR / f"{folder_hash}.jpg"
        _ART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        art_path.write_bytes(image_data)
        return str(art_path)
    except Exception:
        logger.debug("_extract_album_art: failed for %s", file_path, exc_info=True)
        return ""


def _make_track_dict(file_path: Path, tags: dict) -> dict:
    """Build a track dict suitable for QML consumption."""
    return {
        "title": tags.get("title", file_path.stem),
        "index": tags.get("tracknumber", 0),
        "durationMs": tags.get("duration_ms", 0),
        "parentTitle": tags.get("album", "Unknown Album"),
        "grandparentTitle": tags.get("artist", "Unknown Artist"),
        "streamUrl": file_path.as_uri(),
        "ratingKey": "",
        "codecInfo": tags.get("codec_info", ""),
    }
