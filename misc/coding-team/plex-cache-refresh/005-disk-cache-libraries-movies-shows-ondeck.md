# Task 005 — Disk cache for libraries, on-deck, movies, and shows

## Context

The artists list already has a disk cache (`artists_cache_{section_key}.json`) that
loads instantly on app restart and is overwritten after each network fetch. The same
pattern needs to be applied to:

1. **Library list** — the list of Plex sections (Movies, TV Shows, etc.)
2. **On-deck items** — Continue Watching
3. **Movies** — per section key
4. **Shows** — per section key

Without these caches, Continue Watching / Movies / TV Shows only appear after the
user manually hits Refresh, because the in-memory models are empty on app restart.

## Reference implementation

Study the existing artists cache pattern carefully before writing anything:

- `_artists_cache_path()` — returns `poster_cache/artists_cache_{section_key}.json`
- `_save_artists_cache(artists)` — serializes list of PlexArtist to JSON (worker thread)
- `_load_artists_cache()` — deserializes JSON to list of PlexArtist (worker thread)
- `_worker_load_section()` — calls `_load_artists_cache()` first, emits cached data
  immediately, then fetches from network and overwrites
- `_on_artists_ready()` — calls `_save_artists_cache()` after updating the model

Follow this pattern exactly for each new cache.

## Objective

### Cache file paths (add as methods on PlexLibrary)

```python
def _libraries_cache_path(self) -> Path:
    cache_dir = CONFIG_DIR / "poster_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "libraries_cache.json"

def _ondeck_cache_path(self) -> Path:
    cache_dir = CONFIG_DIR / "poster_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "ondeck_cache.json"

def _movies_cache_path(self, section_key: str) -> Path:
    cache_dir = CONFIG_DIR / "poster_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"movies_cache_{section_key}.json"

def _shows_cache_path(self, section_key: str) -> Path:
    cache_dir = CONFIG_DIR / "poster_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"shows_cache_{section_key}.json"
```

### 1. Library list cache

**Fields to serialize** (from `client.get_libraries()` raw dict list — these are the
raw dicts passed to `_on_libraries_ready`, not parsed objects):
```json
[{"key": "1", "title": "Movies", "type": "movie"}, ...]
```
Read `_on_libraries_ready` and `_worker_refresh` to confirm the exact structure.

**Save:** in `_on_libraries_ready`, after `self._libraries_model.set_items(libraries)`:
```python
self._save_libraries_cache(libraries)
```

**Load:** in `_worker_refresh`, before `client.get_libraries()`:
```python
cached = self._load_libraries_cache()
if cached:
    self._librariesReady.emit(cached)
```

### 2. On-deck cache

**Fields to serialize** — the processed dicts from `_on_on_deck_ready` (after parsing,
not the raw API response), since `_on_on_deck_ready` does the parsing:
```json
[{"rating_key": "...", "title": "...", "type": "movie", "poster_local": "...",
  "grandparent_title": "...", "view_offset": 0, "duration": 0, "thumb_path": "..."}, ...]
```

**Save:** in `_on_on_deck_ready`, after `self._on_deck_model.set_items(items)`:
```python
self._save_ondeck_cache(items)
```

**Load:** in `_worker_refresh`, before `client.get_on_deck()`:
```python
cached = self._load_ondeck_cache()
if cached:
    self._onDeckReady.emit(cached)
```

Wait — `_on_on_deck_ready` expects raw API items and does its own parsing. For the
cache, save the **already-processed** `items` list (after the for loop in
`_on_on_deck_ready`). For loading, emit the processed dicts directly — but
`_onDeckReady` connects to `_on_on_deck_ready` which will try to re-parse them.

**Better approach:** add a separate `_onDeckCacheReady = Signal(list)` that connects
to a new `_on_on_deck_cache_ready` handler which calls `set_items()` directly with
the already-processed dicts (skipping the raw parsing step):

```python
_onDeckCacheReady = Signal(list)
# in __init__:
self._onDeckCacheReady.connect(self._on_on_deck_cache_ready,
                               Qt.ConnectionType.QueuedConnection)

def _on_on_deck_cache_ready(self, items: list) -> None:
    self._on_deck_model.set_items(items)
    self.onDeckModelChanged.emit()
```

In `_worker_refresh`:
```python
cached = self._load_ondeck_cache()
if cached:
    self._onDeckCacheReady.emit(cached)
```

### 3. Movies cache

**Fields to serialize** — PlexMovie fields needed by the model and UI:
```json
[{"rating_key": "...", "title": "...", "year": 0, "summary": "...",
  "content_rating": "...", "duration_ms": 0, "studio": "...",
  "thumb_path": "...", "genres": [], "view_count": 0, "view_offset": 0,
  "poster_local": "..."}, ...]
```

Read `PlexMovie` dataclass in `backend/plex_models.py` for the full field list.

**Save:** in `_on_movies_ready`, only on the first page (`self._movies_loaded == 0`
check, before the append path), after `self._movies_model.set_movies(movies)`:
```python
self._save_movies_cache(self._current_section_key, movies)
```

**Load:** in `_worker_load_section`, for `section_type == "movie"`, before the
network fetch — same pattern as artists:
```python
cached = self._load_movies_cache(section_key)
if cached:
    self._moviesReady.emit(cached, len(cached))
```

Reconstruct `PlexMovie` objects from the JSON dicts in `_load_movies_cache`.

### 4. Shows cache

Same pattern as movies. Fields from `PlexShow`:
```json
[{"rating_key": "...", "title": "...", "year": 0, "summary": "...",
  "content_rating": "...", "thumb_path": "...", "genres": [],
  "leaf_count": 0, "viewed_leaf_count": 0, "poster_local": "..."}, ...]
```

**Save:** in `_on_shows_ready`, first page only, after `set_shows()`:
```python
self._save_shows_cache(self._current_section_key, shows)
```

**Load:** in `_worker_load_section`, for `section_type == "show"`:
```python
cached = self._load_shows_cache(section_key)
if cached:
    self._showsReady.emit(cached, len(cached))
```

## Scope

- `backend/plex_library.py` only

## Non-goals

- Do not change any QML files.
- Do not cache paginated results beyond the first page — only the first page
  is cached (the `_movies_loaded == 0` guard ensures this).
- Do not cache sort/filter variants — only the default (unsorted) first-page
  result is cached. When the user applies a sort, the network fetch overwrites
  the cache with the sorted result.
- Do not add a cache TTL or invalidation — the network fetch always overwrites
  on Refresh. Stale data is acceptable; it will be replaced as soon as the
  network fetch completes.

## Caveats

- All save/load methods run on worker threads (`_executor`). Never call Qt
  methods from inside them — only emit private signals.
- `poster_local` paths in the cache may become stale if the poster cache is
  cleared. This is acceptable — the poster will just be missing until re-downloaded.
- The `_current_section_key` used for movies/shows cache path must be captured
  at the time of the save call, not read later (it may have changed if the user
  navigated to a different section).
- Add tests in `tests/test_plex_backend.py` following the existing artists cache
  test pattern.
