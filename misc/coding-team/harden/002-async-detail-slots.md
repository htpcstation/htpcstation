# Task Brief 002 — Async getMovie / getShow / getSeasons / getEpisodes

## Context

`getMovie`, `getShow`, `getSeasons`, `getEpisodes` are synchronous `@Slot` methods on
`PlexLibrary` that make HTTP calls on the Qt main thread. On a remote Plex server this
freezes the UI for the duration of the request (typically 200ms–2s).

The existing async pattern in `plex_library.py` is: submit to `self._executor`, emit an
internal `_Signal` from the worker, connect that to a slot that emits the public signal.
See `fetchStreamInfo` / `_on_stream_info_ready` / `streamInfoReady` for the canonical example.

QML currently calls these slots synchronously and assigns the return value immediately:
```qml
watchScreen.selectedMovieData = plex.getMovie(ratingKey)   // WatchScreen.qml:645
showData = plex.getShow(showRatingKey)                      // PlexShowDetail.qml:67
seasons = plex.getSeasons(showRatingKey)                    // PlexShowDetail.qml:68
episodes = plex.getEpisodes(seasonRatingKey)                // PlexShowDetail.qml:78
```

## Objective

Convert all four slots to async. QML call sites updated to call async versions; results
delivered via signals handled in `Connections` blocks.

## Scope

**Modified files:**
- `backend/plex_library.py`
- `qml/screens/WatchScreen.qml`
- `qml/screens/PlexShowDetail.qml`

**New test file:** `tests/test_plex_library_async_detail.py`

---

## Python changes (`plex_library.py`)

### New public signals (add alongside existing signals)
```python
movieReady    = Signal(str, "QVariant")   # (rating_key, movie_dict)
showReady     = Signal(str, "QVariant")   # (rating_key, show_dict)
seasonsReady  = Signal(str, "QVariant")   # (rating_key, seasons_list)
episodesReady = Signal(str, "QVariant")   # (season_rating_key, episodes_list)
```

### New internal signals
```python
_movieReady    = Signal(str, object)
_showReady     = Signal(str, object)
_seasonsReady  = Signal(str, object)
_episodesReady = Signal(str, object)
```

Connect in `__init__` (alongside other internal signal connections):
```python
self._movieReady.connect(lambda rk, d: self.movieReady.emit(rk, d))
self._showReady.connect(lambda rk, d: self.showReady.emit(rk, d))
self._seasonsReady.connect(lambda rk, d: self.seasonsReady.emit(rk, d))
self._episodesReady.connect(lambda rk, d: self.episodesReady.emit(rk, d))
```

### Replace synchronous slots with async versions

Keep the existing synchronous implementations as private helpers
(`_fetch_movie`, `_fetch_show`, `_fetch_seasons`, `_fetch_episodes`) — the async slots
call these from the worker. This avoids duplicating the parsing logic.

```python
@Slot(str)
def fetchMovie(self, rating_key: str) -> None:
    if self._client is None:
        self._movieReady.emit(rating_key, {})
        return
    client = self._client
    poster_cache = self._poster_cache
    def _worker():
        result = self._fetch_movie(client, poster_cache, rating_key)
        self._movieReady.emit(rating_key, result)
    self._executor.submit(_worker)

# Same pattern for fetchShow, fetchSeasons, fetchEpisodes.
```

**Remove the old synchronous `getMovie`, `getShow`, `getSeasons`, `getEpisodes` slots.**
They are only called from QML (being replaced) and tests (being updated). No backend
code calls them.

### `_fetch_movie(client, poster_cache, rating_key) -> dict`

Extract the body of the current `getMovie` into this private helper. Same for the others.
These are called from worker threads — they must not touch Qt objects directly.
The old `getMovie` / `getShow` / `getSeasons` / `getEpisodes` slots are deleted after extraction.

---

## QML changes

### `WatchScreen.qml`

**Call sites** — replace `plex.getMovie(rk)` with `plex.fetchMovie(rk)`. The result
arrives via `plex.movieReady`. There are 4 call sites (lines ~645, ~683, ~686, ~695,
~698, ~813 — read the file to confirm exact lines).

Since `selectedMovieData` is set asynchronously, the detail view must handle the case
where it's empty while the fetch is in-flight. Add a `_movieLoading` bool property:
- Set `true` before calling `fetchMovie`, set `false` in `onMovieReady`
- `PlexMovieDetail` already guards on empty data — no QML change needed there

Add to the consolidated `Connections { target: plex }` block:
```qml
function onMovieReady(ratingKey, movieData) {
    if (ratingKey === watchScreen.selectedRatingKey) {
        watchScreen.selectedMovieData = movieData
        watchScreen._movieLoading = false
    }
}
```

**Important:** The `onMovieReady` guard must check `ratingKey === watchScreen.selectedRatingKey`
to discard stale responses (user navigated away before fetch completed).

### `PlexShowDetail.qml`

Read the file carefully before editing. The current pattern:
```qml
onShowRatingKeyChanged: {
    showData = plex.getShow(showRatingKey)
    seasons = plex.getSeasons(showRatingKey)
}
function _loadEpisodes(seasonRatingKey) {
    episodes = plex.getEpisodes(seasonRatingKey)
}
```

Replace with:
```qml
onShowRatingKeyChanged: {
    if (!showRatingKey) return
    showData = {}
    seasons = []
    plex.fetchShow(showRatingKey)
    plex.fetchSeasons(showRatingKey)
}
function _loadEpisodes(seasonRatingKey) {
    episodes = []
    plex.fetchEpisodes(seasonRatingKey)
}

Connections {
    target: plex
    function onShowReady(ratingKey, data) {
        if (ratingKey === showDetail.showRatingKey)
            showDetail.showData = data
    }
    function onSeasonsReady(ratingKey, data) {
        if (ratingKey === showDetail.showRatingKey)
            showDetail.seasons = data
    }
    function onEpisodesReady(ratingKey, data) {
        if (ratingKey === showDetail._selectedSeasonKey)
            showDetail.episodes = data
    }
}
```

`_selectedSeasonKey` is the rating key of the currently selected season — add it as a
property if it doesn't already exist. Read `PlexShowDetail.qml` to understand the current
season selection mechanism before adding it.

---

## Tests (`tests/test_plex_library_async_detail.py`)

Use the same mock/executor pattern as `tests/test_plex_library_lyrics.py`.

Cover:
- `fetchMovie` emits `movieReady` with correct rating_key and dict on success
- `fetchMovie` emits `movieReady` with empty dict when `_client` is None
- `fetchShow` emits `showReady` with correct rating_key and dict on success
- `fetchSeasons` emits `seasonsReady` with correct rating_key and list on success
- `fetchEpisodes` emits `episodesReady` with correct rating_key and list on success
- Stale response guard: `onMovieReady` only updates `selectedMovieData` when `ratingKey` matches (test in Python — the guard logic is in QML so just verify the signal carries the rating_key)
- Update `tests/test_plex_backend.py` — all existing `getMovie` / `getShow` / `getSeasons` / `getEpisodes` test classes must be updated to call `fetchMovie` / `fetchShow` / `fetchSeasons` / `fetchEpisodes` and capture results via signal instead of return value. Use the signal-capture pattern from `tests/test_plex_library_lyrics.py`.

## Constraints / Caveats

- `"QVariant"` in `Signal(str, "QVariant")` is required for PySide6 to accept both dict
  and list as the second argument from QML connections.
- Worker threads must not access `self._config`, `self._client`, or any Qt object directly
  after the initial capture — capture `client = self._client` before submitting.
- Read `PlexShowDetail.qml` fully before editing — the season/episode selection state
  is non-trivial.
- `tests/test_plex_backend.py` has ~30 test cases across the four slots — update all of them, do not leave any calling the old synchronous names.
