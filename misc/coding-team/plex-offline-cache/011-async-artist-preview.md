# Task 011 — Async artist preview in PlexArtistList

## Context

`PlexArtistList.qml` calls `plex.getArtist(ratingKey)` synchronously on
every D-pad press in the artist list view (`_updatePreview()`). This makes a
`GET /library/metadata/{ratingKey}` network request that blocks the main
thread for 100ms–1s+ per navigation step. Fast scrolling through artists
causes repeated freezes.

## Objective

Replace the synchronous `getArtist()` call in `_updatePreview()` with an
async pattern. Navigation must be instant; the preview updates when the
data arrives.

## Approach

Use the existing `fetchArtistDetail()` async worker + `artistDetailReady`
signal. But `fetchArtistDetail` fetches full albums too — overkill for a
preview. Add a lightweight async preview fetch instead.

### Option A: Lightweight `fetchArtistPreview` (preferred)

Add a new `fetchArtistPreview(rating_key)` method to `PlexLibrary` that
fetches only the artist metadata (no albums, no hubs). Emits a new
`artistPreviewReady(ratingKey, data)` signal.

```python
artistPreviewReady = Signal(str, "QVariant")  # (rating_key, artist_dict)

@Slot(str)
def fetchArtistPreview(self, rating_key: str) -> None:
    """Async: fetch artist metadata only (no albums). Emits artistPreviewReady."""
    if self._client is None:
        return
    client = self._client
    poster_cache = self._poster_cache
    def _worker():
        data = client.get_metadata(rating_key)
        if not data:
            return
        artist = parse_artist(data)
        if artist.thumb_path and poster_cache:
            cached_path = poster_cache._cache_path(artist.thumb_path)
            if cached_path.exists():
                artist.poster_local = cached_path.as_uri()
        self._artistPreviewReady.emit(rating_key, {
            "ratingKey": artist.rating_key,
            "title": artist.title,
            "summary": artist.summary,
            "genre": artist.genre,
            "posterLocal": artist.poster_local,
        })
    self._executor.submit(_worker)
```

Add `_artistPreviewReady` as an internal signal connected with QueuedConnection,
or emit `artistPreviewReady` directly (it's a public signal emitted from a
worker thread — check if QML connections handle cross-thread delivery; if not,
use the trampoline pattern).

### QML changes in `PlexArtistList.qml`

Replace:
```qml
function _updatePreview() {
    var item = artistList.currentItem
    if (!item) { ... return }
    var rk = item.artistRatingKey
    if (!rk || rk === _lastPreviewKey) return
    _lastPreviewKey = rk
    if (plex) {
        _previewData = plex.getArtist(rk)  // BLOCKING
    }
}
```

With:
```qml
function _updatePreview() {
    var item = artistList.currentItem
    if (!item) { ... return }
    var rk = item.artistRatingKey
    if (!rk || rk === _lastPreviewKey) return
    _lastPreviewKey = rk
    _previewData = {}  // clear immediately for visual feedback
    if (plex) plex.fetchArtistPreview(rk)  // NON-BLOCKING
}

// In Connections { target: plex }:
function onArtistPreviewReady(ratingKey, data) {
    if (ratingKey === plexArtistList._lastPreviewKey) {
        plexArtistList._previewData = data
    }
}
```

The `ratingKey === _lastPreviewKey` guard ensures that only the most recent
preview request updates the display (handles fast scrolling where multiple
requests are in-flight).

### Option B: Debounce (simpler, less ideal)

Add a 200ms debounce timer in QML before calling the sync `getArtist()`.
This reduces the number of blocking calls during fast scrolling but still
blocks on each debounce fire.

**Prefer Option A** — it eliminates all main-thread blocking.

## Non-goals / Later

- Do not remove `getArtist()` yet — verify it has no other callers first.
  If `PlexArtistList._updatePreview()` is the only caller, it can be removed
  in a follow-up.
- Do not change `fetchArtistDetail()` — it's used for the full detail view.
- Do not change `PlexArtistGrid.qml` — the grid view doesn't have a preview
  panel and doesn't call `getArtist()`.

## Constraints / Caveats

- Fast scrolling may queue many `fetchArtistPreview` calls on the executor.
  Only 2 workers — older requests will queue. The `ratingKey` guard in QML
  ensures stale results are discarded.
- The preview poster uses disk cache pre-resolve (no download). If the poster
  isn't cached, the preview shows without art. The poster will be cached when
  the user visits the full artist detail.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
