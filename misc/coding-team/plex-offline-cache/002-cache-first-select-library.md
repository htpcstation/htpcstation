# Task 002 — Cache-first selectLibrary

## Context

`selectLibrary()` currently submits `_worker_load_section()` to the thread
pool executor, which loads cache then fetches from the network. The cache
emission happens on a background thread, so there's a delay before the UI
sees data — and if `_client is None` (offline, no cached server URL),
`selectLibrary()` returns immediately without loading anything.

The disk cache already contains movies, shows, and artists from previous
sessions. This data should display instantly on every library entry,
regardless of network state. The network fetch then backfills any gaps.

## Objective

Make `selectLibrary()` always load from disk cache first and emit
immediately (on the main thread), then submit the network fetch as a
background backfill if `_client` is available. Cache miss = skip straight
to network fetch (current behavior).

## Scope — one file: `backend/plex_library.py`

### 1. `selectLibrary()` — emit cache before network fetch

After setting `_current_section_key`, `_current_section_type`, etc.
(lines 851–858), and before submitting to the executor (line 863), load
and emit cached data directly on the main thread:

```python
# Cache-first: emit cached data immediately for instant display.
# Network fetch (below) will backfill if client is available.
if section_type == "movie":
    cached = self._load_movies_cache(section_key)
    if cached:
        self._on_movies_cache_ready(cached, section_key)
elif section_type == "show":
    cached = self._load_shows_cache(section_key)
    if cached:
        self._on_shows_cache_ready(cached, section_key)
elif section_type == "artist":
    cached = self._load_artists_cache()
    if cached:
        self._on_artists_ready(cached, len(cached))
```

Note: calling `_on_movies_cache_ready()` etc. directly (not via signal
emission) is correct here because we're already on the main thread. This
populates the model and emits `moviesModelChanged` synchronously so QML
sees data before the frame renders.

### 2. `selectLibrary()` — handle `_client is None` gracefully

Change the guard at line 821 from:
```python
if self._client is None:
    return
```
to:
```python
if self._client is None:
    # No server connection — show cached data only (loaded above).
    return
```

Move the cache-first block (step 1) ABOVE this guard so cache is always
loaded regardless of client state. The executor submission stays below
the guard (it needs the client).

### 3. `_worker_load_section()` — remove cache loading

Since cache is now loaded synchronously in `selectLibrary()`, remove the
cache-loading blocks from `_worker_load_section()` (lines 2095–2112):

```python
# REMOVE these blocks:
if section_type == "artist":
    cached = self._load_artists_cache()
    if cached:
        self._artistsReady.emit(cached, len(cached))
elif section_type == "movie":
    cached = self._load_movies_cache(section_key)
    if cached:
        self._moviesCacheReady.emit(cached, section_key)
elif section_type == "show":
    cached = self._load_shows_cache(section_key)
    if cached:
        self._showsCacheReady.emit(cached, section_key)
```

Replace with just the `page_size` assignment:
```python
if section_type == "artist":
    page_size = 9999
else:
    page_size = _PAGE_SIZE
```

The network fetch and cache-save logic that follows remains unchanged.

### 4. ListenScreen music sub-views

`ListenScreen` has additional lazy-loaded views (Recently Added, Playlists)
that call `plex.fetchRecentlyAdded()` and `plex.fetchPlaylists()`. These
also need cache-first treatment, but only if they have disk caches. Check
whether these are cached:
- If they ARE cached: add cache-first loading in their fetch methods
  (same pattern as step 1).
- If they are NOT cached: leave them as-is — they'll show "Loading..." only
  for these sub-views, which is acceptable for now. Note this as a follow-up.

## Non-goals / Later

- Do not change the cache file format or location.
- Do not add new caches for data that isn't already cached.
- Do not change any QML files — the existing `onMoviesModelChanged`,
  `onShowsModelChanged`, `onArtistsModelChanged` handlers already clear
  `_loading` correctly.
- Do not change `_worker_refresh()` — it already pre-emits cached
  libraries/on-deck (Task 012 fix).

## Constraints / Caveats

- `_load_movies_cache()`, `_load_shows_cache()`, `_load_artists_cache()`
  do disk I/O. On the main thread this is a blocking read. These caches
  are local JSON files — typical read time is <10ms. This is acceptable
  for instant display. If profiling shows a problem, the reads can be
  moved to `_worker_load_all_caches()` later.
- The network backfill will overwrite the cached model data when it
  completes. This is the desired behavior — fresh data replaces stale
  cache seamlessly.
- `_on_movies_cache_ready` and `_on_shows_cache_ready` both call
  `moviesModelChanged.emit()` / `showsModelChanged.emit()`. These will
  fire twice when the network backfill completes (once from cache, once
  from network). QML handles this correctly — it just re-reads the model.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
