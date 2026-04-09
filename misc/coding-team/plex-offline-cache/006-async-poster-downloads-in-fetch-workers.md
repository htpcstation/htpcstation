# Task 006 — Async poster downloads in fetch workers

## Context

`fetchArtistDetail()` downloads album poster images sequentially inside the
worker function via `poster_cache.get_poster(client, thumb_path)`. Each
uncached poster takes 1–5 seconds over a remote connection. An artist with
10 albums blocks the worker for 10–50 seconds before emitting the result.

The same pattern exists in `fetchAlbumDetail()` (artist poster download) and
`fetchRecentAlbums()` (album posters in recently added).

Additionally, three legacy `@Slot` methods (`getArtistAlbums`, `getAlbums`,
`getRecentlyAddedAlbums`) download posters synchronously on the main thread
inside loops — these are even worse (block UI completely).

## Objective

Worker functions emit data immediately with pre-resolved local poster paths
(from disk cache). Poster downloads for uncached images are kicked off
separately via `_poster_executor`, and the model is updated when each
download completes — same pattern used by `_on_movies_ready`.

## Part A — `fetchArtistDetail()` (~line 1646)

### Current flow (slow)
```python
for item in hub.get("Metadata", []):
    album = parse_album(item)
    if album.thumb_path and poster_cache:
        album.poster_local = poster_cache.get_poster(client, album.thumb_path)  # BLOCKS
    hub_albums.append({...})
self._artistDetailReady.emit(...)
```

### New flow (fast)
```python
for item in hub.get("Metadata", []):
    album = parse_album(item)
    # Pre-resolve from disk cache only (no download)
    if album.thumb_path and poster_cache:
        cached_path = poster_cache._cache_path(album.thumb_path)
        if cached_path.exists():
            album.poster_local = cached_path.as_uri()
    hub_albums.append({...})
self._artistDetailReady.emit(...)

# Kick off async poster downloads for uncached images
for item in hub.get("Metadata", []):
    album = parse_album(item)
    if album.thumb_path and poster_cache:
        cached_path = poster_cache._cache_path(album.thumb_path)
        if not cached_path.exists():
            self._poster_executor.submit(
                self._worker_fetch_poster, client, album.thumb_path, "artist_detail", 0
            )
```

Wait — `_worker_fetch_poster` emits `_posterReady(model_type, row, file_url)`.
But the artist detail albums are a one-shot list sent to QML, not a persistent
model with row indices. The poster download would update the model row, but
there's no persistent model to update.

**Revised approach:** For `fetchArtistDetail`, pre-resolve from disk cache
only. Don't kick off async downloads — the artist detail view is transient
(rebuilt on every entry). If the poster isn't cached, show a placeholder.
The poster will be cached when the user next visits the main artist grid
(which does download posters via `_poster_executor`).

Actually, the simpler and more correct fix: pre-resolve from disk cache (fast),
then download only the artist poster (one image, not N albums). Album posters
in the hub list are the same images as the album grid — they'll already be
cached from the main artist list view.

**Simplest correct fix for fetchArtistDetail:**
1. Pre-resolve artist poster from disk cache (no download)
2. Pre-resolve album posters from disk cache (no download)
3. Emit immediately
4. If the artist poster is not cached, submit ONE poster download to
   `_poster_executor` for the artist image only

```python
def _worker():
    import re
    artist_dict = {}
    data = client.get_metadata(rating_key)
    if data:
        artist = parse_artist(data)
        # Pre-resolve from disk cache only
        if artist.thumb_path and poster_cache:
            cached_path = poster_cache._cache_path(artist.thumb_path)
            if cached_path.exists():
                artist.poster_local = cached_path.as_uri()
        artist_dict = {
            "ratingKey": artist.rating_key,
            "title": artist.title,
            "summary": artist.summary,
            "genre": artist.genre,
            "posterLocal": artist.poster_local,
        }

    albums = []
    hubs = client.get_hubs(rating_key)
    for hub in hubs:
        # ... existing hub filtering ...
        hub_albums = []
        for item in hub.get("Metadata", []):
            album = parse_album(item)
            # Pre-resolve from disk cache only (no download)
            if album.thumb_path and poster_cache:
                cached_path = poster_cache._cache_path(album.thumb_path)
                if cached_path.exists():
                    album.poster_local = cached_path.as_uri()
            hub_albums.append({...})
        # ... existing sort + header ...

    self._artistDetailReady.emit(rating_key, {"artist": artist_dict, "albums": albums})
```

## Part B — `fetchAlbumDetail()` (~line 1698)

Same pattern — the album poster download (`poster_cache.get_poster`) blocks.
Replace with disk cache pre-resolve only:

```python
if album.thumb_path and poster_cache:
    cached_path = poster_cache._cache_path(album.thumb_path)
    if cached_path.exists():
        album.poster_local = cached_path.as_uri()
```

## Part C — `fetchRecentAlbums()` (find it)

Search for `fetchRecentAlbums` or similar. If it has the same pattern, apply
the same fix: pre-resolve from disk cache, don't download in the loop.

## Part D — Legacy `@Slot` methods with synchronous poster downloads

These three methods download posters synchronously on the main thread:
- `getArtistAlbums()` (~line 1491)
- `getAlbums()` (~line 1543)
- `getRecentlyAddedAlbums()` (~line 1822)

Apply the same fix: replace `poster_cache.get_poster()` with disk cache
pre-resolve (`_cache_path().exists()`). These are legacy sync methods that
may still be called from QML — they must not block.

## Non-goals / Later

- Do not convert the legacy sync `@Slot` methods to async workers — that's a
  larger refactor.
- Do not add a poster update mechanism for the artist detail view (it's
  transient and rebuilt on every entry).

## Constraints / Caveats

- `poster_cache._cache_path(thumb_path)` returns a `Path` object. Call
  `.exists()` to check, `.as_uri()` to get the file:// URL. This is the same
  pattern used in `_worker_load_section` for movies/shows/artists.
- Pre-resolving from disk cache means the poster must have been downloaded
  previously (e.g. from the main library grid). If not, the album/artist
  shows a placeholder. This is acceptable — the poster downloads happen when
  the user browses the main grid, and subsequent visits to detail views will
  have cached posters.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
