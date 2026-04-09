# Task 005 — Offline sort + fix genre fetch main-thread block

## Context

When offline, pressing "2" to open the sort/filter overlay lags for several
seconds (main thread blocked), then changing the sort does nothing.

**Root cause 1 — genre fetch blocks main thread:** `getMovieGenres()` and
`getShowGenres()` are `@Slot` methods that call `self._client.get_genres()`
synchronously on the main thread. When the server is unreachable, `_get()`
retries 3 times with 1s + 3s backoff ≈ 4s of UI freeze.

**Root cause 2 — sort bails when client exists but server is down:**
`sortMovies()` / `sortShows()` submit `_worker_load_section` to the executor.
The worker calls `get_library_items` which fails with `([], 0)` →
`sectionLoadFailed`. The cached model is preserved (our guard from Task 003)
but the sort was never applied — the network response was supposed to contain
sorted data, but it returned nothing.

## Objective

1. Sort works offline by sorting the in-memory model locally (Python sort).
2. Genre fetch never blocks the main thread.

## Part A — Local sort when server is unreachable

When `_worker_load_section` gets an empty response (the `([], 0)` guard),
the sort was requested but never applied. The fix: sort the in-memory model
locally when the network fetch fails, or better, always sort locally first
(instant feedback) and let the network backfill refresh with server-sorted data.

### Approach: sort in-memory model in `sortMovies` / `sortShows`

Add Python-side sort to the model classes and call it before submitting the
network fetch. This gives instant sort feedback regardless of network state.

In `PlexMovieListModel`, add:

```python
def sort_movies(self, sort_key: str) -> None:
    """Sort the in-memory movie list. Called on the main thread."""
    key_func = {
        "titleSort:asc":   lambda m: (m.title or "").lower(),
        "titleSort:desc":  lambda m: (m.title or "").lower(),
        "addedAt:desc":    lambda m: m.added_at,
        "year:desc":       lambda m: m.year,
        "year:asc":        lambda m: m.year,
        "audienceRating:desc": lambda m: m.audience_rating,
    }.get(sort_key)
    if key_func is None:
        return
    reverse = sort_key.endswith(":desc")
    self.beginResetModel()
    self._movies.sort(key=key_func, reverse=reverse)
    self.endResetModel()
```

Check `_SORT_MAP` in `PlexLibrary` for the exact sort key strings. Mirror the
same keys.

Add the equivalent `sort_shows` to `PlexShowListModel`.

In `sortMovies()` — after saving the sort state and before submitting to the
executor — call:

```python
api_sort = self._SORT_MAP.get(sort_key, "")
# ... existing state save ...

# Instant local sort for cached/in-memory data
self._movies_model.sort_movies(api_sort)
self.moviesModelChanged.emit()

if self._client is None:
    return

# Network backfill with server-sorted data
self._executor.submit(...)
```

Same for `sortShows()`.

### Genre filter

Genre filtering is harder to do locally (would need to parse genre data from
each item). For now, when `_client is None`, `filterByGenre` / `filterShowsByGenre`
should sort the current model (ignoring the genre filter) and return. Genre
filtering requires network — this is acceptable. The sort overlay can still
show sort options; genre options just won't appear when offline.

## Part B — Fix `getMovieGenres` / `getShowGenres` main-thread block

These are called from QML to populate the genre dropdown in the sort overlay.
They call `self._client.get_genres()` synchronously on the main thread.

### Fix: return empty immediately when server is unavailable

```python
@Slot(result="QVariant")
def getMovieGenres(self) -> list:
    if self._client is None or not self._current_section_key:
        return []
    if not self._available:
        return []
    return self._client.get_genres(self._current_section_key)
```

Same for `getShowGenres()`. The `_available` flag is set by `_on_availability_ready`
— it's `False` when the server identity check failed. This prevents the
blocking retry loop when the server is known to be unavailable.

**Note:** There are 13 other `@Slot` methods that call `self._client.*`
synchronously on the main thread (see audit list below). These should also
check `_available` to avoid blocking. However, most of them are rarely called
when offline. For this task, fix only `getMovieGenres` and `getShowGenres`
(the ones causing the reported lag). The others can be addressed in a
follow-up if they cause similar issues.

**Audit of synchronous main-thread client calls (for reference):**
- `getStreamInfo` — only called when launching playback (not offline)
- `getWatchHistory` — not used in offline context
- `getArtist`, `getAlbum`, `getArtistAlbums`, `getAlbums` — legacy sync
  versions replaced by `fetchArtistDetail` / `fetchAlbumDetail` async workers
- `getPlaylists`, `getPlaylistTracks` — legacy sync versions
- `getTracks` — called from ListenScreen
- `getRecentlyAddedAlbums` — called from ListenScreen
- `getTrackStreamUrl` — only called when playing a track (not offline)

## Non-goals / Later

- Do not make `filterByGenre` / `filterShowsByGenre` work offline with local
  filtering — genre filtering requires knowing genre membership which is in
  the full metadata, not the cached model.
- Do not convert all 13 synchronous `@Slot` methods to async — that's a
  larger refactor. Only fix the two that cause the reported lag.
- Do not change any QML files.

## Constraints / Caveats

- `PlexMovie` has `title`, `year`, `added_at`, `audience_rating` fields.
  `PlexShow` has `title`, `year`, `added_at`, `audience_rating`.
  Check exact field names in `plex_models.py`.
- `beginResetModel()` / `endResetModel()` temporarily makes QML see count=0.
  This is fine for a sort — the model is immediately repopulated.
- `_SORT_MAP` translates user-facing sort keys to API sort strings. The
  local sort must use the same API sort strings as keys.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
