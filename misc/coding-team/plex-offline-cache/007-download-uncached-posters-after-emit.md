# Task 007 — Download uncached posters after initial emit in fetch workers

## Context

Task 006 replaced `poster_cache.get_poster()` (downloads if not cached) with
`_cache_path().exists()` (disk-only pre-resolve) in `fetchArtistDetail`,
`fetchAlbumDetail`, and `fetchRecentAlbums`. This made initial display instant
but means posters that were never previously cached are never downloaded.
Album art doesn't appear on external connections where the disk cache is empty.

## Objective

After the initial fast emission with disk-cached posters, download uncached
posters in the same worker and re-emit the data with updated poster URLs.
The user sees data instantly (possibly without some album art), then the view
refreshes with full art once downloads complete.

## Scope — `backend/plex_library.py` only

### Pattern for each fetch worker

```python
# 1. Pre-resolve from disk cache (existing, fast)
# 2. Emit data immediately (existing)
# 3. NEW: Download uncached posters and re-emit if any were updated
```

### `fetchArtistDetail()` (~line 1646)

After the existing `_artistDetailReady.emit(...)`, add:

```python
    self._artistDetailReady.emit(rating_key, {"artist": artist_dict, "albums": albums})

    # Download uncached posters and re-emit if any were updated
    updated = False
    if data and artist_dict.get("posterLocal", "") == "" and poster_cache:
        artist = parse_artist(data)
        if artist.thumb_path:
            local_url = poster_cache.get_poster(client, artist.thumb_path)
            if local_url:
                artist_dict["posterLocal"] = local_url
                updated = True

    for album_entry in albums:
        if album_entry.get("type") != "album":
            continue
        if album_entry.get("posterLocal", ""):
            continue  # already resolved from disk cache
        # Need the thumb_path — but we only stored display fields in album_entry.
        # We need to find the original thumb_path.
```

**Problem:** The album dicts emitted to QML don't include `thumb_path` — they
only have `posterLocal`, `title`, `year`, etc. We need the `thumb_path` to
download the poster.

**Fix:** Track `thumb_path` alongside each album entry during the hub loop
so we can use it for the download pass. Simplest approach: include `thumbPath`
in the album dict (QML can ignore it).

```python
hub_albums.append({
    "type": "album",
    "ratingKey": album.rating_key,
    "title": album.title,
    "year": album.year,
    "leafCount": album.leaf_count,
    "posterLocal": album.poster_local,
    "thumbPath": album.thumb_path,  # NEW: for poster download pass
})
```

Then the download pass:

```python
for album_entry in albums:
    if album_entry.get("type") != "album":
        continue
    if album_entry.get("posterLocal", ""):
        continue
    thumb_path = album_entry.get("thumbPath", "")
    if thumb_path and poster_cache:
        local_url = poster_cache.get_poster(client, thumb_path)
        if local_url:
            album_entry["posterLocal"] = local_url
            updated = True

if updated:
    self._artistDetailReady.emit(rating_key, {"artist": artist_dict, "albums": albums})
```

Check that QML's `onArtistDetailReady` handler can receive the signal twice
without issues (it should just replace the data — verify in ListenScreen.qml).

### `fetchAlbumDetail()` (~line 1698)

Same pattern. After emitting, download the album poster if not cached:

```python
self._albumDetailReady.emit(rating_key, {"album": album_dict, "tracks": tracks})

# Download uncached album poster
if album_dict.get("posterLocal", "") == "" and poster_cache:
    thumb_path = # need to store it — similar to above
    if thumb_path:
        local_url = poster_cache.get_poster(client, thumb_path)
        if local_url:
            album_dict["posterLocal"] = local_url
            self._albumDetailReady.emit(rating_key, {"album": album_dict, "tracks": tracks})
```

Store `thumb_path` from `album.thumb_path` before building the dict.

### `fetchRecentAlbums()` (find it)

Same pattern — emit immediately, download uncached, re-emit if updated.

### Legacy `@Slot` methods

`getArtistAlbums`, `getAlbums`, `getRecentlyAddedAlbums` are synchronous
`@Slot` methods — they return data directly to QML. They cannot re-emit.
For these, the disk cache pre-resolve from Task 006 is sufficient. The poster
downloads from the async fetch workers will populate the cache for subsequent
calls. Do NOT add downloads back to the sync methods.

## Non-goals / Later

- Do not change any QML files.
- Do not change the disk cache pre-resolve from Task 006 — keep it for instant
  first emission.
- Do not change `_on_movies_ready` / `_on_shows_ready` poster download logic.

## Constraints / Caveats

- Double-emitting `_artistDetailReady` / `_albumDetailReady` is safe as long
  as QML simply replaces the data. Verify that the QML handlers in
  `ListenScreen.qml` don't have side effects on repeat calls (e.g. pushing
  to a navigation stack twice).
- `poster_cache.get_poster()` is thread-safe (per-path lock). Calling it from
  the executor worker is correct.
- The second emission only happens if at least one poster was actually
  downloaded. If all posters were already cached, no re-emission occurs.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
