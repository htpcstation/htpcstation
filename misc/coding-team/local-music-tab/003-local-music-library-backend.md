# Task 003: LocalMusicLibrary Backend

## Context

We're building a Local Music tab that scans a user-configured directory for audio files, extracts metadata from ID3/Vorbis tags via `mutagen`, and exposes artist/album/track models to QML. This is the backend — no QML in this task.

The existing pattern to follow is `backend/plex_library.py` and `backend/library.py`:
- QAbstractListModel subclasses with roles exposed via `roleNames()`
- QObject orchestrator with Properties, Signals, and Slots
- ThreadPoolExecutor for async work, `QMetaObject.invokeMethod` with `QueuedConnection` to marshal results to the main thread
- Disk cache as JSON in `~/.config/htpcstation/local_music_cache/`

## Objective

Create `backend/local_music_library.py` with a `LocalMusicLibrary` QObject that:
1. Scans a configured directory recursively for audio files
2. Extracts metadata (artist, album, title, track number, year, duration, genre) using `mutagen`
3. Extracts embedded album art to a poster cache directory
4. Caches the full scan result to disk as JSON
5. Exposes QAbstractListModel-backed models for artists, albums, and tracks
6. Provides slots for QML to trigger scan, select artist, select album, sort artists, and get file URLs for playback

## Scope

### New file: `backend/local_music_library.py`

**Models (QAbstractListModel subclasses):**

1. `LocalArtistListModel` — roles: `title` (str), `genre` (str), `albumCount` (int), `imageLocal` (str, file:// URI to extracted art or "")
2. `LocalAlbumListModel` — roles: `title` (str), `artist` (str), `year` (int), `trackCount` (int), `posterLocal` (str, file:// URI), `folderPath` (str)
3. `LocalTrackListModel` — not needed as a persistent model; tracks are returned as JS arrays via signals (same pattern as Plex: `albumDetailReady` emits a dict with track arrays).

**QObject: `LocalMusicLibrary`**

Properties (with notify signals):
- `artistsModel` → LocalArtistListModel (read-only)
- `scanning` → bool (true while scan in progress)

Signals:
- `artistsModelChanged()`
- `scanningChanged()`
- `scanComplete()` — emitted when a full scan finishes (success or empty)
- `artistDetailReady(str artistName, "QVariant" data)` — `data` = `{"artist": {title, genre, albumCount, imageLocal}, "albums": [array of album header/entry dicts]}`. Use same dict structure as Plex: entries have `"type": "header"` or `"type": "album"` with fields `title`, `year`, `trackCount`, `posterLocal`, `folderPath`.
- `albumDetailReady(str folderPath, "QVariant" data)` — `data` = `{"album": {title, artist, year, trackCount, posterLocal, genre}, "tracks": [array of track dicts]}`. Track dict: `{"title", "index" (track number), "durationMs", "parentTitle" (album), "grandparentTitle" (artist), "streamUrl" (file:// URI), "ratingKey": "" (empty, for compat with shared now-playing)}`.
- `folderContentsReady(str folderPath, "QVariant" data)` — for filetree browsing. `data` = `{"folders": [{name, path, itemCount}], "tracks": [track dicts]}`.

Slots:
- `scan()` — trigger full directory scan (async). If already scanning, no-op. Reads the configured music directory from the Config object. On completion, caches to disk and updates the artists model.
- `fetchArtistDetail(str artistName)` — look up artist from cached data, emit `artistDetailReady`.
- `fetchAlbumDetail(str folderPath)` — look up album tracks from cached data, emit `albumDetailReady`.
- `sortArtists(str sortKey)` — sort the artists model in-place. Keys: `"az"` (A-Z), `"za"` (Z-A).
- `getTrackStreamUrl(str filePath) -> str` — return `"file://" + filePath` (or use `Path.as_uri()`). This is the local equivalent of `plex.getTrackStreamUrl()`.
- `browseFolder(str folderPath)` — list subfolders and audio files at the given path. Emit `folderContentsReady`. Used for filetree browsing. Validate that the path is under the configured music directory (security: don't allow traversal outside).
- `playFolder(str folderPath) -> QVariant` — return album-like data for a folder (track dicts for all audio files in it), so the caller can pass them to `homeScreen._playAlbum()`.

**Constructor:** `__init__(self, config: Config)`
- Store reference to config for reading music directory path
- Create `ThreadPoolExecutor(max_workers=2)`
- Create models
- Load cached data from disk if it exists (synchronous, fast JSON read)

**Scanning logic (`_worker_scan`):**
- Walk the music directory recursively
- For each audio file (extensions: `.mp3`, `.flac`, `.ogg`, `.opus`, `.m4a`, `.wma`, `.wav`, `.aac`, `.aif`, `.aiff`), use `mutagen.File(path, easy=True)` to extract tags
- Build an in-memory dict: `{artist_name: {albums: {album_title: {year, genre, tracks: [{title, track_num, duration_ms, file_path}], folder_path}}}}`
- Group by artist → album. Use `"Unknown Artist"` and `"Unknown Album"` for missing tags.
- Extract embedded art: for each album, check the first track for embedded art (APIC for ID3, METADATA_BLOCK_PICTURE for Vorbis/FLAC, `covr` for M4A). Save to `~/.config/htpcstation/local_music_cache/art/{sha256_of_folder_path}.jpg`. Use `mutagen.File(path)` (without `easy=True`) for art extraction since EasyID3 doesn't expose pictures.
- Marshal results to main thread via `QMetaObject.invokeMethod` with `QueuedConnection`.

**Cache:**
- Location: `~/.config/htpcstation/local_music_cache/library.json`
- Art cache: `~/.config/htpcstation/local_music_cache/art/`
- On scan complete, write the full library dict to `library.json`.
- On startup, if `library.json` exists, load it and populate models immediately (no scan needed until user triggers one).

### Dependency: `mutagen`

Add `mutagen` to `requirements.txt`.

### Config changes: `backend/config.py`

Add to Config class:
- `self.local_music_directory: Optional[Path] = None` (same pattern as `rom_directory`)
- `set_local_music_directory(self, path)` setter
- Serialize/deserialize in `save()`/`_load()` as `"local_music_directory"` key

## Non-goals
- No QML in this task
- No settings UI (Task 004)
- No HomeScreen registration (Task 006)
- No playlists
- No recently added
- No external album art fetching

## Constraints
- All worker→main-thread communication must use `QMetaObject.invokeMethod` with `QueuedConnection` (not `AutoConnection`). See resume-project.md "Plex cache fix — cross-thread signals" for why.
- Track dicts must include `"streamUrl"` (file:// URI) and `"ratingKey": ""` for compatibility with the shared now-playing view in HomeScreen.
- `browseFolder` must validate the requested path is under the configured music directory to prevent directory traversal.
- Use `mutagen.File(path, easy=True)` for tag reading (fast), `mutagen.File(path)` (without easy) only when extracting album art.
- Don't block the main thread during scan — all I/O on the executor.
