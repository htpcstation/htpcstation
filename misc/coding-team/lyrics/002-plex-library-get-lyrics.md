# Task Brief 002 — PlexLibrary: getLyrics slot + lyricsReady / lyricsUnavailable signals

## Context

`backend/lrc_parser.py` (Task 001) is already implemented and provides `parse_lrc(text)` and `parse_plain(text)`.

`PlexLibrary` in `backend/plex_library.py` is a `QObject` with a `ThreadPoolExecutor` at `self._executor` (max_workers=2). All async work follows the pattern: `@Slot` method submits to `self._executor`, worker emits an internal `_Signal`, which is connected to a slot that emits the public signal. See any existing `_worker_*` method for the pattern.

The track dict shape (from `getTracks` / `getPlaylistTracks`) is:
```python
{
    "ratingKey": str,
    "title": str,
    "index": int,
    "durationMs": int,
    "parentTitle": str,       # album name
    "grandparentTitle": str,  # artist name
    "mediaKey": str,
}
```

## Objective

Add lyrics fetching to `PlexLibrary` via LRCLIB (`https://lrclib.net/api/get`).

## Scope

**Modified file:** `backend/plex_library.py`
**New test file:** `tests/test_plex_library_lyrics.py`

## Changes to plex_library.py

### New public signals (add alongside existing signals ~line 477)
```python
lyricsReady = Signal(str, list)       # (rating_key, lines) — lines is list of {ms, text} dicts
lyricsUnavailable = Signal(str)       # (rating_key) — no lyrics found or error
```

### New internal signal
```python
_lyricsReady = Signal(str, list)      # (rating_key, lines)
_lyricsUnavailable = Signal(str)      # (rating_key)
```

Connect in `__init__` (alongside other internal signal connections):
```python
self._lyricsReady.connect(self.lyricsReady)
self._lyricsUnavailable.connect(self.lyricsUnavailable)
```

### New public slot
```python
@Slot(str, str, str, int)
def getLyrics(self, rating_key: str, track_title: str, artist_name: str, album_name: str, duration_ms: int) -> None:
```

Wait — the slot signature must match what QML can call. Use a single dict approach via `QVariant`, or individual args. Use individual args — QML will call:
```qml
plex.getLyrics(track.ratingKey, track.title, track.grandparentTitle, track.parentTitle, track.durationMs)
```

Slot decorator: `@Slot(str, str, str, str, int)`

Submits `_worker_fetch_lyrics(rating_key, track_title, artist_name, album_name, duration_ms)` to `self._executor`.

### Worker function `_worker_fetch_lyrics`

```python
def _worker_fetch_lyrics(self, rating_key, track_title, artist_name, album_name, duration_ms):
```

- `GET https://lrclib.net/api/get` with params:
  - `track_name=track_title`
  - `artist_name=artist_name`
  - `album_name=album_name`
  - `duration=round(duration_ms / 1000)`
- User-Agent: `htpcstation/1.0 (https://github.com/tranxuanthang/lrcget)` — LRCLIB asks clients to identify themselves
- Timeout: 10s
- Use `requests` (already imported)
- On HTTP 200:
  - If `instrumental == True` → emit `_lyricsUnavailable(rating_key)`
  - Else if `syncedLyrics` is non-empty → `parse_lrc(syncedLyrics)` → emit `_lyricsReady(rating_key, lines)`
  - Else if `plainLyrics` is non-empty → `parse_plain(plainLyrics)` → emit `_lyricsReady(rating_key, lines)`
  - Else → emit `_lyricsUnavailable(rating_key)`
- On HTTP 404 → emit `_lyricsUnavailable(rating_key)`
- On any other error (network, timeout, non-200/404 status) → emit `_lyricsUnavailable(rating_key)` and log a warning
- Import `parse_lrc` and `parse_plain` from `backend.lrc_parser` at the top of the file

## Test file: tests/test_plex_library_lyrics.py

Use `unittest.mock.patch` to mock `requests.get`. Do **not** instantiate a real `PlexLibrary` — use a minimal stub or mock the executor to run synchronously (see existing test patterns in `tests/test_plex_library_*.py` for how other tests handle this).

Tests must cover:
- 200 with `syncedLyrics` → `lyricsReady` emitted with parsed LRC lines
- 200 with `plainLyrics` only → `lyricsReady` emitted with parsed plain lines
- 200 with `instrumental: true` → `lyricsUnavailable` emitted
- 200 with neither lyrics field → `lyricsUnavailable` emitted
- 404 → `lyricsUnavailable` emitted
- Network error (`requests.exceptions.ConnectionError`) → `lyricsUnavailable` emitted
- Correct params sent to LRCLIB: `track_name`, `artist_name`, `album_name`, `duration` (rounded seconds)
- Correct User-Agent header sent

## Non-goals
- No caching
- No retry logic (single attempt only — LRCLIB is fast and non-critical)
- Do not modify `getTracks` or `getPlaylistTracks`
