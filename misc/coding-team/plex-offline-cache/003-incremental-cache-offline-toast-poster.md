# Task 003 — Incremental cache save + offline toast + poster pre-resolve

## Context

Three related issues with the current Plex offline cache:

1. **Partial cache:** `_save_movies_cache` / `_save_shows_cache` only save the
   first page (~50 items). Subsequent pages are never cached. A library of 500
   movies has only ~50 in cache.

2. **No offline toast:** When `_client is None`, `selectLibrary()` returns after
   loading cache but never emits `sectionLoadFailed`, so QML shows no
   "Network unavailable" toast.

3. **Unnecessary poster fetch submissions:** The cache-first path in
   `selectLibrary()` loads from JSON where `poster_local` may be stale/empty
   (poster was downloaded after cache was written). Pre-resolving poster paths
   from disk when loading from cache eliminates unnecessary `_poster_executor`
   submissions.

---

## Part A — Incremental merge-by-key cache save

### Approach

Replace the current "save first page, overwrite entire file" with a
merge-by-`rating_key` strategy. Each save:

1. Loads the existing cache from disk (if any)
2. Builds a `{rating_key: entry_dict}` lookup from the existing data
3. Updates/inserts entries from the new items
4. Writes the merged result back

This means:
- Cache grows incrementally as each page loads
- Items not in the current page are preserved (no data loss from partial loads)
- A full 500-item cache is never overwritten by a 50-item partial load

### Threading model

The merge read-modify-write is pure disk I/O + dict operations — no Qt objects
touched. It must NOT run on the main thread. Offload to `_cache_executor`
(dedicated single-thread pool already used for cache ops at startup). Single
thread = no concurrent writes to the same file = no locks needed.

The call site on the main thread snapshots data to plain dicts (cheap attribute
reads, no I/O), then submits the disk work to the executor:

```python
# Main thread: snapshot to dicts (fast, no I/O)
movie_dicts = [self._movie_to_dict(m) for m in movies]
# Executor: merge + write (disk I/O)
self._cache_executor.submit(
    self._merge_and_write_movies_cache, section_key, movie_dicts
)
```

This keeps the main thread work minimal and all I/O off it.

### Changes to `_save_movies_cache` area (~line 2707)

Split into two functions:

```python
def _movie_to_dict(self, m) -> dict:
    """Snapshot a PlexMovie to a plain dict (no I/O, safe on main thread)."""
    return {
        "rating_key": m.rating_key,
        "title": m.title,
        "year": m.year,
        "summary": m.summary,
        "content_rating": m.content_rating,
        "audience_rating": m.audience_rating,
        "duration_ms": m.duration_ms,
        "studio": m.studio,
        "tagline": m.tagline,
        "thumb_path": m.thumb_path,
        "art_path": m.art_path,
        "genres": m.genres,
        "directors": m.directors,
        "cast": m.cast,
        "added_at": m.added_at,
        "view_offset": m.view_offset,
        "poster_local": m.poster_local,
    }

def _merge_and_write_movies_cache(self, section_key: str, movie_dicts: list[dict]) -> None:
    """Merge movie dicts into existing cache and write (runs on _cache_executor)."""
    try:
        path = self._movies_cache_path(section_key)
        existing = {}
        if path.exists():
            try:
                for item in json.loads(path.read_text(encoding="utf-8")):
                    rk = item.get("rating_key", "")
                    if rk:
                        existing[rk] = item
            except Exception:
                pass  # Corrupt cache — start fresh

        for d in movie_dicts:
            rk = d.get("rating_key", "")
            if rk:
                existing[rk] = d

        path.write_text(json.dumps(list(existing.values())), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save movies cache", exc_info=True)
```

Remove the old `_save_movies_cache` method — it is fully replaced by the
two new methods above.

### Same pattern for shows

Add `_show_to_dict` and `_merge_and_write_shows_cache`. Check the show
serialization fields in the existing `_save_shows_cache` and mirror them.
Remove the old `_save_shows_cache`.

### Same pattern for artists

Find the artist cache save function (`_save_artists_cache`). Add
`_artist_to_dict` and `_merge_and_write_artists_cache`. Remove the old save.

### Call save on every page, not just page 1

In `_on_movies_ready` (~line 2307):

```python
def _on_movies_ready(self, movies: list, total: int) -> None:
    self._loading_more = False
    if self._movies_loaded == 0:
        self._movies_model.set_movies(movies)
        self.moviesModelChanged.emit()
        self._save_state_cache("last_movie_section", self._current_section_key)
    else:
        self._movies_model.append_movies(movies)

    # Save every page — merge-by-key preserves existing entries.
    # Snapshot to dicts on main thread; disk I/O on _cache_executor.
    section_key = self._current_section_key
    movie_dicts = [self._movie_to_dict(m) for m in movies]
    self._cache_executor.submit(
        self._merge_and_write_movies_cache, section_key, movie_dicts
    )

    self._movies_total = total
    self._movies_loaded += len(movies)
    # ... poster downloads unchanged
```

Same change for `_on_shows_ready` and `_on_artists_ready` (artists).

---

## Part B — Emit `sectionLoadFailed` when `_client is None`

In `selectLibrary()`, after loading cache and before returning for
`_client is None`, emit the signal so QML shows the offline toast:

```python
if self._client is None:
    # No server connection — show cached data only (loaded above).
    # Emit sectionLoadFailed so QML shows offline toast.
    self.sectionLoadFailed.emit()
    return
```

---

## Part C — Pre-resolve poster paths when loading from cache

When `selectLibrary()` loads items from cache, `poster_local` may be stale
(poster was downloaded after the cache was written). Pre-resolve from the
poster cache directory so the network backfill's `not movie.poster_local`
guard correctly skips already-cached posters.

Add a helper:

```python
def _resolve_cached_posters(self, items: list) -> None:
    """Pre-resolve poster_local from disk cache for items missing it."""
    if self._poster_cache is None:
        return
    for item in items:
        thumb = getattr(item, "thumb_path", "") or ""
        if thumb and not getattr(item, "poster_local", ""):
            cached_path = self._poster_cache._cache_path(thumb)
            if cached_path.exists():
                item.poster_local = cached_path.as_uri()
```

In `selectLibrary()`, call `_resolve_cached_posters` after loading from
cache and before calling the `_on_*_ready` slot:

```python
if section_type == "movie":
    cached = self._load_movies_cache(section_key)
    if cached:
        self._resolve_cached_posters(cached)
        self._on_movies_cache_ready(cached, section_key)
elif section_type == "show":
    cached = self._load_shows_cache(section_key)
    if cached:
        self._resolve_cached_posters(cached)
        self._on_shows_cache_ready(cached, section_key)
elif section_type == "artist":
    cached = self._load_artists_cache()
    if cached:
        self._resolve_cached_posters(cached)
        self._on_artists_ready(cached, len(cached))
```

Note: `_resolve_cached_posters` does `_cache_path()` (SHA256 hash + path
construct) and `exists()` checks. For 500 items this is ~5ms — acceptable
on the main thread for instant display. The alternative (offloading to a
thread) would defeat the purpose of cache-first synchronous display.

---

## Non-goals / Later

- Do not add caches for `fetchRecentlyAdded` or `fetchPlaylists` — separate task.
- Do not change the poster download logic in `_on_movies_ready` / `_on_shows_ready`
  — the existing `not movie.poster_local` guard is correct; pre-resolving in
  Part C ensures it works for cache-loaded items too.
- Do not change `_worker_load_all_caches` or `_worker_refresh`.
- Do not change any QML files.
- Cache pruning (removing entries deleted from the server) is a future concern —
  stale entries are harmless in offline mode.

## Constraints / Caveats

- `rating_key` is the Plex-assigned unique identifier. Stable across sessions,
  never changes for a given media item.
- `_cache_executor` is a single-thread `ThreadPoolExecutor`. Submitting merges
  to it serializes all cache writes — no concurrent access to the same file.
- The dict snapshot (`_movie_to_dict`) reads dataclass attributes on the main
  thread. `PlexMovie` fields are only written during model replacement (not
  mutated in-place after construction), so there is no race with the executor.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
