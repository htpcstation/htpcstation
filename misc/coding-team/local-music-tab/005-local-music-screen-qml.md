# Task 005: LocalMusicScreen QML + HomeScreen Tab Registration

## Context

The backend (`LocalMusicLibrary`) and settings are done. This task creates the QML screen and registers it as a HomeScreen tab. The screen mirrors ListenScreen's structure but uses `localMusic` instead of `plex` for data, and adds a filetree browser view.

Reference: `qml/screens/ListenScreen.qml` — the primary pattern to follow.

## Objective

Create `qml/screens/LocalMusicScreen.qml` with the same navigation model as ListenScreen (menu → artists → artist detail → album detail), plus a filetree browser. Register it in HomeScreen's tab array.

## Scope

### New file: `qml/screens/LocalMusicScreen.qml`

**Structure — FocusScope with views:**
- `"menu"` — main menu: Now Playing (conditional), Artists, Browse Folders, Scan Library
- `"artists"` — artist grid/list (reuse PlexArtistGrid/PlexArtistList patterns but with localMusic model)
- `"detail"` — artist detail with album list
- `"album"` — album detail with track list + Play All
- `"folders"` — filetree browser (new view, not in ListenScreen)

**Key differences from ListenScreen:**
1. **Data source:** `localMusic` context property instead of `plex`. Different signal names and slots.
2. **No library selection:** No `_trySelectMusicLibrary()` — local music has a single directory.
3. **No playlists, no recently added** (out of scope per plan).
4. **Filetree browser** replaces playlists/recently added as an alternative navigation mode.
5. **Scan instead of Refresh:** Menu has "Scan Library" (calls `localMusic.scan()`) instead of "Refresh".
6. **Artist model:** `localMusic.artistsModel` (LocalArtistListModel) has `title`, `genre`, `albumCount`, `imageLocal` roles — same as PlexArtistListModel.

**Connections block (target: localMusic):**
- `onArtistsModelChanged()` — set `_loading = false`, `_scanning = false`
- `onScanComplete()` — set `_scanning = false`
- `onArtistDetailReady(artistName, data)` — populate `_artistData` and `_albums` (keyed by artistName, not ratingKey)
- `onAlbumDetailReady(folderPath, data)` — populate `_albumData` and `_tracks`
- `onFolderContentsReady(folderPath, data)` — populate `_folderData` for filetree view

**Properties:**
```
signal back()
enabled: focus
property string currentView: "menu"
property string _viewMode: "grid"  // loaded from settings.localMusicViewMode
property bool _loading: true
property bool _scanning: false
property bool _initialized: false
property string _selectedArtistName: ""
property var _artistData: ({})
property var _albums: []
property string _selectedAlbumFolder: ""
property var _albumData: ({})
property var _tracks: []
property string _albumReturnView: "detail"
property var _folderData: ({})      // {folders: [], tracks: []}
property string _currentFolder: ""  // current filetree path
property var _folderHistory: []     // stack for filetree back navigation
property string _toastText: ""
```

**Menu view:** Same pattern as ListenScreen's `listenMenu` ListView:
- "Now Playing" (conditional, calls `homeScreen._showNowPlaying()`)
- "Artists" (goes to "artists" view)
- "Browse Folders" (goes to "folders" view, calls `localMusic.browseFolder(musicDir)`)
- "Scan Library" / "Scanning..." (calls `localMusic.scan()`)

**Artists view:**
- Cannot literally reuse `PlexArtistGrid.qml` because it hardcodes `plex.artistsModel` and `plex.sortArtists()`. Two options:
  - **Option A (recommended):** Create `LocalArtistGrid.qml` and `LocalArtistList.qml` that are copies of the Plex versions with `plex` → `localMusic` substitutions and sort calls pointing to `localMusic.sortArtists()` / `settings.setSortLocalMusicArtists()`.
  - **Option B:** Parameterize the existing Plex components. This would be cleaner long-term but is a bigger refactor touching tested code.
  - **Go with Option A** — duplicate and adapt. Keep the components identical in structure but pointing to the local music backend.

**Artist detail view:** Same as ListenScreen's detail view — header bar with "◀ Artist Name", album list (ListView with header/album delegate pattern). Selecting an album calls `localMusic.fetchAlbumDetail(album.folderPath)`.

**Album detail view:** Same as ListenScreen — header bar with "◀ Album Name", Play All button at top, track ListView. Selecting a track or Play All calls `homeScreen._playAlbum(tracks, albumData, startIndex)`.
- Track dicts from the backend already have `streamUrl` populated with `file://` URIs, so HomeScreen's source-agnostic playback handles them.
- Lyrics: call `plex.getLyrics()` if plex is available (LRCLIB is accessed through plex). If plex is not available, lyrics just won't be fetched — the now-playing view handles missing lyrics gracefully.

**Filetree browser view ("folders"):**
- Header bar: "◀ Folder Name" (or "◀ Browse Folders" at root)
- ListView of folders (navigate into) and audio files (play)
- Pressing A on a folder: push current path to `_folderHistory`, call `localMusic.browseFolder(folder.path)`, update `_currentFolder`
- Pressing B: pop `_folderHistory`. If empty, return to menu.
- Pressing A on a track: build a track array from `_folderData.tracks` and call `homeScreen._playAlbum(tracks, folderAlbumData, index)` where `folderAlbumData` is a synthetic album dict from the folder.
- Pressing Y on a folder: call `localMusic.playFolder(folder.path)` to get track dicts, then `homeScreen._playAlbum(...)` to play the whole folder.

**Focus routing (`_routeFocus`):**
```
menu → localMusicMenu.forceActiveFocus()
artists → grid or list based on _viewMode
detail → albumList.forceActiveFocus()
album → trackList, with _playAllFocused = true
folders → folderList.forceActiveFocus()
```

**Sort overlay in artist grid/list:**
- Sort options: "az" (A-Z), "za" (Z-A) — calls `localMusic.sortArtists(key)` and `settings.setSortLocalMusicArtists(key)`
- View mode toggle: "grid" / "list" — calls `settings.setLocalMusicViewMode(mode)`

**Initialization (onActiveFocusChanged):**
- On first focus: set `_initialized = true`, load cached data. If `localMusic.artistsModel` has items (from cache loaded at startup), set `_loading = false`. Otherwise show loading state.

### New files: `qml/screens/LocalArtistGrid.qml` and `qml/screens/LocalArtistList.qml`

Copies of `PlexArtistGrid.qml` and `PlexArtistList.qml` with these substitutions:
- `plex.artistsModel` → `localMusic ? localMusic.artistsModel : null`
- `plex.sortArtists(sortKey)` → `localMusic.sortArtists(sortKey)`
- `settings.sortPlexArtists` → `settings.sortLocalMusicArtists`
- `settings.setSortPlexArtists(key)` → `settings.setSortLocalMusicArtists(key)`
- `settings.listenViewMode` → `settings.localMusicViewMode` (if bound externally, keep the same external binding pattern)
- `settings.setListenViewMode(mode)` → `settings.setLocalMusicViewMode(mode)`
- Keep all else identical (grid layout, list layout, sort overlay, focus, key handling, theme usage).

### HomeScreen.qml — Tab registration

Add the Local Music tab to `_allTabs` array, **before Settings but after Plex Music**:
```javascript
{ name: "Music", source: "LocalMusicScreen.qml", setting: "showLocalMusicTab", slug: "localmusic" },
```

### Lyrics integration

In `_playTrackAtIndex` in HomeScreen.qml, lyrics are fetched via `plex.getLyrics()` only when `plex && track.ratingKey` is truthy. Local music tracks have `ratingKey: ""`, so lyrics won't be fetched via that path. 

To get LRCLIB lyrics for local music, add a condition: if `track.ratingKey` is empty but `track.grandparentTitle` (artist) and `track.title` are present, still call `plex.getLyrics("", track.title, track.grandparentTitle, track.parentTitle, track.durationMs)` — LRCLIB lookup uses title/artist/album/duration, not ratingKey. The ratingKey is only used as a correlation key for the response signal; use a synthetic key like `"local_" + track.title` or just pass empty string (the now-playing view doesn't filter by ratingKey for display).

Actually, check how `plex.getLyrics` uses the ratingKey — if it's only for signal correlation, passing empty is fine. If it guards against fetching, we may need to adjust. Read `plex_library.py`'s `getLyrics` method to determine.

## Non-goals
- Don't refactor PlexArtistGrid/PlexArtistList into parameterized shared components
- Don't add playlist support
- Don't add recently added
- Don't wire up main.py (Task 006)

## Constraints
- **Never use `id: root`** in any QML component
- **Guard all context property bindings:** `localMusic ? localMusic.artistsModel : null`
- **Only ONE `Component.onCompleted` per scope**
- **`Loader` recreates on every tab switch** — load data in `Component.onCompleted`
- All `homeScreen._playAlbum()` calls work because local track dicts have `streamUrl` populated
- The `localMusic` context property won't exist yet in main.py (Task 006 wires it). The QML will load but all guards will return null — that's fine, the screen just shows empty state.
