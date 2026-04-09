# Task 008 — Parallel progressive poster downloads in fetch workers

## Context

Task 007 added poster downloads after the initial emission in fetch workers
(`fetchArtistDetail`, `fetchAlbumDetail`, `fetchRecentAlbums`). Currently the
downloads are sequential in the worker thread — all posters download one by
one, then a single re-emission shows all album art at once. The user sees
nothing, then everything.

## Objective

Submit uncached poster downloads to `_poster_executor` (10 parallel workers)
and re-emit after each individual download completes. The user sees posters
appearing progressively as they download in parallel.

## Scope — `backend/plex_library.py` only

### `fetchArtistDetail()` — replace sequential download with parallel

Replace the sequential download loop (lines ~1754–1777):

```python
# REMOVE: sequential download + single re-emit
updated = False
if data and artist_dict.get("posterLocal", "") == "" and poster_cache:
    ...
for album_entry in albums:
    ...
if updated:
    self._artistDetailReady.emit(...)
```

Replace with parallel downloads using `concurrent.futures`:

```python
from concurrent.futures import as_completed, Future

# Collect poster download tasks
download_tasks: list[tuple[dict, str]] = []  # (entry_dict, thumb_path)

if data and artist_dict.get("posterLocal", "") == "" and poster_cache:
    artist = parse_artist(data)
    if artist.thumb_path:
        download_tasks.append((artist_dict, artist.thumb_path))

for album_entry in albums:
    if album_entry.get("type") != "album":
        continue
    if album_entry.get("posterLocal", ""):
        continue
    thumb_path = album_entry.get("thumbPath", "")
    if thumb_path:
        download_tasks.append((album_entry, thumb_path))

if download_tasks and poster_cache:
    # Submit all downloads to _poster_executor in parallel
    future_to_entry: dict[Future, tuple[dict, str]] = {}
    for entry_dict, thumb_path in download_tasks:
        future = self._poster_executor.submit(
            poster_cache.get_poster, client, thumb_path
        )
        future_to_entry[future] = (entry_dict, thumb_path)

    # As each download completes, update the entry and re-emit
    for future in as_completed(future_to_entry):
        entry_dict, thumb_path = future_to_entry[future]
        try:
            local_url = future.result()
            if local_url:
                # Determine the correct key — artist_dict uses "posterLocal",
                # album entries also use "posterLocal"
                entry_dict["posterLocal"] = local_url
                self._artistDetailReady.emit(
                    rating_key, {"artist": artist_dict, "albums": albums}
                )
        except Exception:
            pass  # Download failed — poster stays as placeholder
```

**Important:** `as_completed` blocks the current worker thread until all
futures complete, yielding each future as it finishes. This is correct — the
worker thread is from `_executor` (2 workers), while the poster downloads
run on `_poster_executor` (10 workers). The worker thread is just waiting
and re-emitting, not doing heavy work.

**`_poster_executor` has `max_workers=10`** — this is the parallelism limit.
Each download is ~20KB (400px poster). 10 concurrent downloads use negligible
RAM.

### `fetchAlbumDetail()` — same pattern

The album detail only downloads one poster (the album itself). This is already
a single download — parallel doesn't help. Keep the existing sequential
download-and-re-emit from Task 007. No changes needed here.

### `fetchRecentAlbums()` — same parallel pattern

Apply the same `as_completed` pattern as `fetchArtistDetail`. Recent albums
may have multiple uncached posters.

Find the `fetchRecentAlbums` function and replace its sequential download
loop with the parallel pattern.

## Non-goals / Later

- Do not change `_poster_executor` max_workers (already 10).
- Do not change any QML files.
- Do not change `fetchAlbumDetail` (single poster, parallel doesn't help).
- Do not change legacy sync @Slot methods.

## Constraints / Caveats

- `as_completed` is from `concurrent.futures` — already available (the module
  uses `ThreadPoolExecutor` from the same package). Check if it's imported;
  add if not.
- The `_executor` worker thread that runs `fetchArtistDetail._worker` blocks
  on `as_completed`. Since `_executor` has `max_workers=2`, one worker is
  occupied during poster downloads. This is acceptable — the other worker
  can still handle requests.
- Each `_artistDetailReady.emit` from the worker thread is delivered to QML
  via `QueuedConnection`. Multiple rapid emissions are queued on the main
  thread event loop and processed sequentially — no race condition.
- `poster_cache.get_poster()` is thread-safe (per-path lock prevents duplicate
  downloads of the same poster).
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
