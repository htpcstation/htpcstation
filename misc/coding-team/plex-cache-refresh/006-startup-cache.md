# Task 006 — Startup cache: populate Plex models from disk at __init__

## Context

The previous cache implementation (Task 005) put cache loads inside
`_worker_refresh()` and `_worker_load_section()`. These only run when the user
triggers a refresh or navigates into a library — not at startup. So models are
still empty on cold boot.

The correct pattern (matching GameLibrary / gamelist.xml) is:
- Read all cache files **synchronously in `__init__`** before any network call
- Models are populated immediately — QML sees data on first render
- Refresh overwrites the cache files after a successful network fetch

## Constraint

**No synchronous calls on the main thread.** All disk reads must happen on a
worker thread. The main thread only handles signal emissions.

## Objective

### 1. New cache directory

Change all cache paths from `CONFIG_DIR / "poster_cache"` to a dedicated
`CONFIG_DIR / "plex_cache"` directory. This separates metadata JSON from
poster image files.

Define at module level (near `_POSTER_CACHE_DIR`):
```python
_PLEX_CACHE_DIR = CONFIG_DIR / "plex_cache"
```

Update all four `_*_cache_path()` methods to use `_PLEX_CACHE_DIR`.

### 2. Submit async cache load in `__init__`

After the existing model initializations, submit a single worker job:

```python
self._executor.submit(self._worker_load_all_caches)
```

Add a private signal to carry all cache data in one shot:
```python
_allCachesReady = Signal(object)   # dict with keys: libraries, ondeck, movies, shows
```

Wire it in `__init__`:
```python
self._allCachesReady.connect(self._on_all_caches_ready,
                             Qt.ConnectionType.QueuedConnection)
```

### 3. Worker: read all cache files from disk

```python
def _worker_load_all_caches(self) -> None:
    """Worker: read all Plex metadata caches from disk.

    Runs on _executor thread. No network I/O — disk reads only.
    Emits _allCachesReady with a dict of all cached data.
    """
    state = self._load_state_cache()

    libraries = self._load_libraries_cache()
    ondeck    = self._load_ondeck_cache()

    movies = None
    last_movie_section = state.get("last_movie_section", "")
    if last_movie_section:
        movies = self._load_movies_cache(last_movie_section)

    shows = None
    last_show_section = state.get("last_show_section", "")
    if last_show_section:
        shows = self._load_shows_cache(last_show_section)

    self._allCachesReady.emit({
        "libraries": libraries or [],
        "ondeck":    ondeck    or [],
        "movies":    movies    or [],
        "shows":     shows     or [],
        "movie_section": last_movie_section,
        "show_section":  last_show_section,
    })
```

### 4. Main-thread handler: populate models and emit signals

```python
def _on_all_caches_ready(self, data: object) -> None:
    """Main thread: populate models from disk cache data."""
    libraries = data.get("libraries", [])
    if libraries:
        self._libraries_model.set_items(libraries)
        self.librariesModelChanged.emit()

    ondeck = data.get("ondeck", [])
    if ondeck:
        self._on_deck_model.set_items(ondeck)
        self.onDeckModelChanged.emit()

    movies = data.get("movies", [])
    if movies:
        self._movies_model.set_movies(movies)
        self._current_section_key  = data.get("movie_section", "")
        self._current_section_type = "movie"
        self.moviesModelChanged.emit()

    shows = data.get("shows", [])
    if shows:
        self._shows_model.set_shows(shows)
        if not movies:   # don't overwrite if movies already set section
            self._current_section_key  = data.get("show_section", "")
            self._current_section_type = "show"
        self.showsModelChanged.emit()
```

### 5. State file: track last-used section keys

Add `_state_cache_path()`, `_save_state_cache()`, `_load_state_cache()`:

```python
def _state_cache_path(self) -> Path:
    _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _PLEX_CACHE_DIR / "state.json"

def _save_state_cache(self, key: str, value: str) -> None:
    """Update one key in state.json (worker thread safe — atomic read-modify-write)."""
    path = self._state_cache_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}
    state[key] = value
    path.write_text(json.dumps(state), encoding="utf-8")

def _load_state_cache(self) -> dict:
    path = self._state_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

In `_on_movies_ready()`, after `_save_movies_cache()`:
```python
self._save_state_cache("last_movie_section", self._current_section_key)
```

In `_on_shows_ready()`, after `_save_shows_cache()`:
```python
self._save_state_cache("last_show_section", self._current_section_key)
```

Note: `_save_state_cache` is called from the main thread (inside `_on_movies_ready`
which is a main-thread handler). This is a fast local disk write — acceptable.
If it becomes a concern, move it to a worker.

### 6. Remove cache loads from workers

In `_worker_refresh()`, remove the libraries and ondeck cache loads (they are
now handled by `_worker_load_all_caches` at startup).

In `_worker_load_section()`, remove the movies and shows cache loads.

Remove `_moviesCacheReady`, `_showsCacheReady`, `_onDeckCacheReady` signals
and their handlers and `__init__` connections — no longer needed.

### 8. WatchScreen.qml — remove the empty-state refresh guard

In `onActiveFocusChanged`, remove:
```qml
if (_libraryEntries.length === 0 && !_refreshed) {
    _refreshed = true
    _availabilityKnown = false
    plex.refresh()
}
```

This was the last automatic `plex.refresh()` call. With startup cache loading,
`_libraryEntries` will be non-empty on first focus (populated from cache in
`Component.onCompleted`). The only remaining trigger for `plex.refresh()` is
the manual Refresh button.

Also remove the `_refreshed` property — it is no longer used.

## Scope

- `backend/plex_library.py` — primary changes
- `qml/screens/WatchScreen.qml` — remove empty-state refresh guard + `_refreshed`

## Non-goals

- Do not change ListenScreen — it has its own `_initialized` guard which is fine.
- Do not change LiveTvScreen.
- Do not change the poster cache directory or poster download logic.
- Do not add a cache TTL.

## Acceptance criteria

- On cold boot (no prior Refresh), if cache files exist, movies/shows/on-deck/
  libraries appear immediately without any user action or network call.
- On first ever launch (no cache files), the screen shows empty state until the
  user hits Refresh.
- After a Refresh, cache files are written and subsequent cold boots show data
  immediately.
