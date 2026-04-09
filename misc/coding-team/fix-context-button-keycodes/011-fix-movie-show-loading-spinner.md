# Task 011 — Remove redundant sort/filter network calls from Component.onCompleted

## Root cause

`PlexMovieGrid.qml`, `PlexMovieList.qml`, `PlexShowGrid.qml`, and
`PlexShowList.qml` all have a `Component.onCompleted` block that:

1. Sets `_loading = true`
2. Calls `plex.sortMovies(savedSort)` / `plex.sortShows(savedSort)` /
   `plex.filterByGenre(savedGenre)` / `plex.filterShowsByGenre(savedGenre)`

These calls are silently dropped because `plex._current_section_key` is `""`
at the time the component loads — `selectLibrary()` has not been called yet.
Both `sortMovies` and `filterByGenre` guard with
`if not self._current_section_key: return` and do nothing.

Result: `_loading` is set to `true` and never cleared (because
`onMoviesModelChanged` / `onShowsModelChanged` never fires), so the
"Loading..." spinner shows indefinitely on slow connections.

The calls are also redundant: `selectLibrary()` already reads
`_section_sort[section_key]` and `_section_genre[section_key]` (restored
from `state.json` at startup) and passes them to `_worker_load_section`.
The saved sort/genre is applied automatically — no extra call needed.

## Objective

Remove the broken network calls and `_loading = true` assignments from
`Component.onCompleted` in all four files. Keep only the local display
state assignments (`_currentSort`, `_currentGenreKey`) so the sort/genre
label in the UI header is correct immediately.

## Scope — four QML files only

### `qml/screens/PlexMovieGrid.qml` (lines 861–876)

```qml
// Before
Component.onCompleted: {
    if (settings) {
        var savedSort = settings.sortPlexMovies
        var savedGenre = settings.filterPlexMovieGenre
        if (savedSort) {
            _currentSort = savedSort
            _loading = true
            plex.sortMovies(savedSort)
        }
        if (savedGenre) {
            _currentGenreKey = savedGenre
            _loading = true
            plex.filterByGenre(savedGenre)
        }
    }
}

// After
Component.onCompleted: {
    if (settings) {
        var savedSort = settings.sortPlexMovies
        var savedGenre = settings.filterPlexMovieGenre
        if (savedSort) _currentSort = savedSort
        if (savedGenre) _currentGenreKey = savedGenre
    }
}
```

### `qml/screens/PlexMovieList.qml` (lines 940–956)

Same pattern — same fix. Remove `_loading = true`, `plex.sortMovies()`,
`plex.filterByGenre()`. Keep `_currentSort = savedSort` and
`_currentGenreKey = savedGenre`.

### `qml/screens/PlexShowGrid.qml` (lines 877–892)

Same pattern — same fix. Remove `_loading = true`, `plex.sortShows()`,
`plex.filterShowsByGenre()`. Keep `_currentSort = savedSort` and
`_currentGenreKey = savedGenre`.

### `qml/screens/PlexShowList.qml` (lines 931–947)

Same pattern — same fix. Remove `_loading = true`, `plex.sortShows()`,
`plex.filterShowsByGenre()`. Keep `_currentSort = savedSort` and
`_currentGenreKey = savedGenre`.

## Non-goals / Later

- Do not change any Python files.
- Do not change any other QML files.
- Do not change the `_loading` flag logic elsewhere in these files
  (sort/filter overlay still sets `_loading = true` correctly when the
  user explicitly changes sort — that path is fine).

## Constraints / Caveats

- The `_currentGenreTitle` assignment (if present) should also be kept
  if it exists in the original — check each file.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
