# Task 004 — Make ListenScreen view transitions non-blocking

## Context

`ListenScreen.qml` currently makes synchronous blocking calls on every view
transition in `onCurrentViewChanged`:

| View | Blocking call(s) |
|---|---|
| `"detail"` | `plex.getArtist(key)` + `plex.getArtistAlbums(key)` |
| `"album"` | `plex.getAlbum(key)` + `plex.getTracks(key)` |
| `"recentlyadded"` | `plex.getRecentlyAddedAlbums(sectionKey)` |
| `"playlists"` | `plex.getPlaylists()` |
| `"playlistdetail"` | `plex.getPlaylistTracks(key)` |

Each of these hits the network on the main thread, freezing the UI for the
duration of the HTTP request.

The fix: add async versions of these calls to `plex_library.py` that submit
to `_executor` and emit signals when done. QML handles the signals in a
`Connections` block instead of reading return values directly.

---

## Objective

### 1. `backend/plex_library.py`

#### New public signals (add alongside existing signals ~line 486):

```python
artistDetailReady  = Signal(str, "QVariant")   # (artist_rating_key, {artist, albums})
albumDetailReady   = Signal(str, "QVariant")   # (album_rating_key, {album, tracks})
recentAlbumsReady  = Signal("QVariant")        # list of album dicts
playlistsReady     = Signal("QVariant")        # list of playlist dicts
playlistTracksReady = Signal(str, "QVariant")  # (rating_key, list of track dicts)
```

#### New private signals (add alongside existing private signals ~line 492):

```python
_artistDetailReady  = Signal(str, object)
_albumDetailReady   = Signal(str, object)
_recentAlbumsReady  = Signal(object)
_playlistsReady     = Signal(object)
_playlistTracksReady = Signal(str, object)
```

#### New async slot methods (add after `getPlaylistTracks`, ~line 1578):

```python
@Slot(str)
def fetchArtistDetail(self, rating_key: str) -> None:
    """Async: fetch artist metadata + albums. Emits artistDetailReady."""
    if self._client is None:
        return
    client = self._client
    poster_cache = self._poster_cache
    def _worker():
        artist_dict = {}
        data = client.get_metadata(rating_key)
        if data:
            artist = parse_artist(data)
            if artist.thumb_path and poster_cache:
                artist.poster_local = poster_cache.get_poster(client, artist.thumb_path)
            artist_dict = {
                "ratingKey": artist.rating_key,
                "title": artist.title,
                "summary": artist.summary,
                "genre": artist.genre,
                "posterLocal": artist.poster_local,
            }
        # Reuse existing getArtistAlbums logic inline
        albums = []
        import re
        hubs = client.get_hubs(rating_key)
        for hub in hubs:
            hub_id = hub.get("hubIdentifier", "")
            if not (hub_id.startswith("artist.albums") or hub_id.startswith("hub.artist.albums")):
                continue
            raw_title = hub.get("title", "")
            clean_title = re.sub(r'^\d+\s+', '', raw_title)
            if clean_title == "Album":
                clean_title = "Albums"
            hub_albums = []
            for item in hub.get("Metadata", []):
                album = parse_album(item)
                if album.thumb_path and poster_cache:
                    album.poster_local = poster_cache.get_poster(client, album.thumb_path)
                hub_albums.append({
                    "type": "album",
                    "ratingKey": album.rating_key,
                    "title": album.title,
                    "year": album.year,
                    "leafCount": album.leaf_count,
                    "posterLocal": album.poster_local,
                })
            hub_albums.sort(key=lambda a: a["year"] or 0, reverse=True)
            albums.append({"type": "header", "title": clean_title})
            albums.extend(hub_albums)
        self._artistDetailReady.emit(rating_key, {"artist": artist_dict, "albums": albums})
    self._executor.submit(_worker)

@Slot(str)
def fetchAlbumDetail(self, rating_key: str) -> None:
    """Async: fetch album metadata + tracks. Emits albumDetailReady."""
    if self._client is None:
        return
    client = self._client
    poster_cache = self._poster_cache
    def _worker():
        album_dict = {}
        data = client.get_metadata(rating_key)
        if data:
            album = parse_album(data)
            if album.thumb_path and poster_cache:
                album.poster_local = poster_cache.get_poster(client, album.thumb_path)
            album_dict = {
                "ratingKey": album.rating_key,
                "title": album.title,
                "year": album.year,
                "leafCount": album.leaf_count,
                "parentTitle": album.parent_title,
                "posterLocal": album.poster_local,
                "summary": album.summary,
                "studio": album.studio,
                "genre": album.genre,
                "rating": album.rating,
            }
        tracks = []
        children = client.get_children(rating_key)
        for item in children:
            if item.get("type") == "track":
                track = parse_track(item)
                tracks.append({
                    "ratingKey": track.rating_key,
                    "title": track.title,
                    "index": track.index,
                    "durationMs": track.duration_ms,
                    "parentTitle": track.parent_title,
                    "grandparentTitle": track.grandparent_title,
                    "mediaKey": track.media_key,
                })
        self._albumDetailReady.emit(rating_key, {"album": album_dict, "tracks": tracks})
    self._executor.submit(_worker)

@Slot(str)
def fetchRecentAlbums(self, section_key: str) -> None:
    """Async: fetch recently added albums. Emits recentAlbumsReady."""
    if self._client is None:
        return
    client = self._client
    poster_cache = self._poster_cache
    def _worker():
        data = client._get(f"/library/sections/{section_key}/recentlyAdded")
        result = []
        if data:
            for item in data.get("MediaContainer", {}).get("Metadata", []):
                if item.get("type") != "album":
                    continue
                album = parse_album(item)
                if album.thumb_path and poster_cache:
                    album.poster_local = poster_cache.get_poster(client, album.thumb_path)
                result.append({
                    "ratingKey": album.rating_key,
                    "title": album.title,
                    "year": album.year,
                    "parentTitle": album.parent_title,
                    "posterLocal": album.poster_local,
                })
        self._recentAlbumsReady.emit(result)
    self._executor.submit(_worker)

@Slot()
def fetchPlaylists(self) -> None:
    """Async: fetch audio playlists. Emits playlistsReady."""
    if self._client is None:
        return
    client = self._client
    def _worker():
        # Reuse existing getPlaylists logic
        raw = client.get_playlists()
        result = []
        for p in raw:
            if p.get("playlistType") != "audio":
                continue
            leaf_count = int(p.get("leafCount", 0) or 0)
            if leaf_count > PlexLibrary._MAX_PLAYLIST_TRACKS:
                continue
            rk = str(p.get("ratingKey", ""))
            if p.get("smart") and rk:
                probe = client.get_playlist_items(rk, limit=1)
                if not probe:
                    continue
            result.append({
                "ratingKey": rk,
                "title": PlexLibrary._replace_emoji(p.get("title", "")),
                "leafCount": leaf_count,
                "duration": int(p.get("duration", 0) or 0),
                "smart": bool(p.get("smart", False)),
            })
        self._playlistsReady.emit(result)
    self._executor.submit(_worker)

@Slot(str)
def fetchPlaylistTracks(self, rating_key: str) -> None:
    """Async: fetch tracks for a playlist. Emits playlistTracksReady."""
    if self._client is None:
        return
    client = self._client
    def _worker():
        raw = client.get_playlist_items(rating_key)
        result = []
        for item in raw:
            track = parse_track(item)
            result.append({
                "ratingKey": track.rating_key,
                "title": track.title,
                "index": track.index,
                "durationMs": track.duration_ms,
                "parentTitle": track.parent_title,
                "grandparentTitle": track.grandparent_title,
                "mediaKey": track.media_key,
            })
        self._playlistTracksReady.emit(rating_key, result)
    self._executor.submit(_worker)
```

#### Wire private → public signals in `__init__` (follow the pattern of
`_artistsReady` → `_on_artists_ready` at ~line 560):

```python
self._artistDetailReady.connect(self._on_artist_detail_ready,
                                Qt.ConnectionType.QueuedConnection)
self._albumDetailReady.connect(self._on_album_detail_ready,
                               Qt.ConnectionType.QueuedConnection)
self._recentAlbumsReady.connect(self._on_recent_albums_ready,
                                Qt.ConnectionType.QueuedConnection)
self._playlistsReady.connect(self._on_playlists_ready,
                             Qt.ConnectionType.QueuedConnection)
self._playlistTracksReady.connect(self._on_playlist_tracks_ready,
                                  Qt.ConnectionType.QueuedConnection)
```

#### Add handler methods (on the main thread, emit public signals):

```python
def _on_artist_detail_ready(self, rating_key: str, data: object) -> None:
    self.artistDetailReady.emit(rating_key, data)

def _on_album_detail_ready(self, rating_key: str, data: object) -> None:
    self.albumDetailReady.emit(rating_key, data)

def _on_recent_albums_ready(self, data: object) -> None:
    self.recentAlbumsReady.emit(data)

def _on_playlists_ready(self, data: object) -> None:
    self.playlistsReady.emit(data)

def _on_playlist_tracks_ready(self, rating_key: str, data: object) -> None:
    self.playlistTracksReady.emit(rating_key, data)
```

---

### 2. `qml/screens/ListenScreen.qml`

#### Add loading state properties:

```qml
property bool _detailLoading: false
property bool _albumLoading: false
property bool _recentLoading: false
property bool _playlistsLoading: false
property bool _playlistTracksLoading: false
```

#### Replace synchronous calls in `onCurrentViewChanged`:

Remove all synchronous assignments. Replace with async fetch calls:

```qml
onCurrentViewChanged: {
    // Lazy refresh (existing, keep)
    if ((currentView === "artists" || currentView === "recentlyadded") ...) { ... }

    if (currentView !== "nowplaying") _previousView = currentView

    if (currentView === "detail" && _selectedArtistKey) {
        _detailLoading = true
        _artistData = {}
        _albums = []
        plex.fetchArtistDetail(_selectedArtistKey)
    } else if (currentView === "recentlyadded" && _musicSectionKey) {
        _recentLoading = true
        _recentAlbums = []
        plex.fetchRecentAlbums(_musicSectionKey)
    } else if (currentView === "album" && _selectedAlbumKey) {
        _albumLoading = true
        _albumData = {}
        _tracks = []
        plex.fetchAlbumDetail(_selectedAlbumKey)
    } else if (currentView === "playlists") {
        _playlistsLoading = true
        _playlists = []
        plex.fetchPlaylists()
    } else if (currentView === "playlistdetail" && _selectedPlaylist.ratingKey) {
        _playlistTracksLoading = true
        _playlistTracks = []
        plex.fetchPlaylistTracks(_selectedPlaylist.ratingKey)
    }
    _routeFocus()
}
```

#### Add signal handlers in the `Connections { target: plex }` block:

```qml
function onArtistDetailReady(ratingKey, data) {
    if (ratingKey !== listenScreen._selectedArtistKey) return
    listenScreen._artistData = data.artist
    listenScreen._albums = data.albums
    listenScreen._detailLoading = false
    // Set initial focus to first non-header entry
    var firstAlbum = 0
    for (var i = 0; i < listenScreen._albums.length; i++) {
        if (listenScreen._albums[i].type !== "header") { firstAlbum = i; break }
    }
    albumList.currentIndex = firstAlbum
}

function onAlbumDetailReady(ratingKey, data) {
    if (ratingKey !== listenScreen._selectedAlbumKey) return
    listenScreen._albumData = data.album
    listenScreen._tracks = data.tracks
    listenScreen._albumLoading = false
    trackList.currentIndex = 0
}

function onRecentAlbumsReady(albums) {
    listenScreen._recentAlbums = albums
    listenScreen._recentLoading = false
    recentAlbumsList.currentIndex = 0
}

function onPlaylistsReady(playlists) {
    listenScreen._playlists = playlists
    listenScreen._playlistsLoading = false
    playlistsList.currentIndex = 0
}

function onPlaylistTracksReady(ratingKey, tracks) {
    if (ratingKey !== listenScreen._selectedPlaylist.ratingKey) return
    listenScreen._playlistTracks = tracks
    listenScreen._playlistTracksLoading = false
    playlistTrackList.currentIndex = 0
}
```

#### Add loading indicators

For each view that now loads asynchronously, show a "Loading..." text while
the fetch is in-flight. Find the existing loading indicator pattern in the
artists view (`loading: listenScreen._loading`) and apply the same approach
to the detail, album, recentlyadded, playlists, and playlistdetail views.

The simplest approach: add a `Text { text: "Loading..."; visible: <loadingFlag> }`
overlay inside each view's root Item, centered, using `Theme.colorTextDim` and
`Theme.fontSizeHeading`. Read the existing views to find the right place.

---

## Scope

- `backend/plex_library.py`
- `qml/screens/ListenScreen.qml`

## Non-goals

- Do not change the synchronous `getArtist`, `getAlbum`, `getTracks`,
  `getPlaylists`, `getPlaylistTracks`, `getRecentlyAddedAlbums` methods —
  leave them in place (they may be used elsewhere or in tests).
- Do not change WatchScreen, LiveTvScreen, or any other file.
- Add tests for the new async slots in `tests/test_plex_backend.py` following
  the existing async test pattern (mock `_executor.submit`, verify the worker
  function calls the right client methods and emits the right signal).

## Caveats

- All worker functions run on `_executor` threads. Never call Qt UI methods
  from inside `_worker()`. Only emit the private `_*Ready` signal.
- The private signals use `Qt.ConnectionType.QueuedConnection` to marshal
  results back to the main thread before emitting the public signal.
- The `ratingKey` guard in QML signal handlers (`if ratingKey !== _selected...`)
  prevents stale responses from a previous navigation from overwriting current data.
