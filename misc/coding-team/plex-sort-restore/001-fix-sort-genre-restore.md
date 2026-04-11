# Task 001: Fix sort/genre label mismatch after app restart

## Context
Six Plex QML views (`PlexMovieGrid`, `PlexShowGrid`, `PlexMovieList`, `PlexShowList`, `PlexArtistGrid`, `PlexArtistList`) restore `_currentSort` in `Component.onCompleted` from a global settings key (`settings.sortPlexMovies` etc.). The backend stores sort per-section in `_section_sort[section_key]` (persisted to `state.json`). These two stores can diverge, causing the status bar sort label to show a stale/wrong value while the content is sorted correctly.

Secondary bug: `_currentGenreTitle` is never restored (only `_currentGenreKey` is). So the status bar genre label is always blank after restart even when a genre filter is active.

## Objective
Replace the global-settings-based restore with per-section backend queries. After this change, the sort label and genre label in the status bar always reflect the actual backend state for the selected section.

## Scope

### `backend/plex_library.py`

Add two slots (near the other sort methods around line 998):

```python
_SORT_MAP_REVERSE: dict[str, str] = {v: k for k, v in _SORT_MAP.items()}

@Slot(str, result=str)
def getSectionSort(self, section_key: str) -> str:
    """Return the QML sort key for the given section ('' = default order)."""
    api_sort = self._section_sort.get(section_key, "")
    return self._SORT_MAP_REVERSE.get(api_sort, "")

@Slot(str, result=str)
def getSectionGenre(self, section_key: str) -> str:
    """Return the stored genre key for the given section ('' = no filter)."""
    return self._section_genre.get(section_key, "")
```

### All six QML views

Apply the same changes to each of:
`PlexMovieGrid.qml`, `PlexShowGrid.qml`, `PlexMovieList.qml`, `PlexShowList.qml`, `PlexArtistGrid.qml`, `PlexArtistList.qml`

**1. Add `sectionKey` property:**
```qml
property string sectionKey: ""
```

**2. Add `onSectionKeyChanged` handler** (inside the root FocusScope, near the other properties):
```qml
onSectionKeyChanged: {
    if (!plex || !sectionKey) return
    _currentSort = plex.getSectionSort(sectionKey)
    // Genre: movie and show views only — artists have no genre filter
    if (typeof _currentGenreKey !== "undefined") {
        _currentGenreKey = plex.getSectionGenre(sectionKey)
        _currentGenreTitle = ""   // title resolved later in onGenresReady
    }
}
```

Since artists have no `_currentGenreKey` property, just skip the genre block there — use the simpler form:
```qml
onSectionKeyChanged: {
    if (!plex || !sectionKey) return
    _currentSort = plex.getSectionSort(sectionKey)
}
```

**3. `Component.onCompleted`: remove sort and genre restore.**
Remove the lines that read `settings.sortPlexMovies` / `settings.sortPlexShows` / `settings.sortPlexArtists` and set `_currentSort`. Remove lines that read `settings.filterPlexMovieGenre` / `settings.filterPlexShowGenre` and set `_currentGenreKey`. If `Component.onCompleted` becomes empty, remove it entirely.

**4. `Connections.onGenresReady` (movie and show views only): set `_currentGenreTitle`.**
In the existing `onGenresReady` handler, when a genre key match is found, also set `_currentGenreTitle`:
```qml
function onGenresReady(sectionKey, genres) {
    sortFilterOverlay._genres = genres
    sortFilterOverlay._genreIndex = 0
    if (movieGridView._currentGenreKey !== "") {   // (or showGridView, movieListView, etc.)
        for (var i = 0; i < genres.length; i++) {
            if (genres[i].key === movieGridView._currentGenreKey) {
                sortFilterOverlay._genreIndex = i + 1
                movieGridView._currentGenreTitle = genres[i].title   // ← ADD THIS LINE
                break
            }
        }
    }
}
```

### `qml/screens/WatchScreen.qml`

For each of the six views instantiated in WatchScreen, add:
```qml
sectionKey: watchScreen.selectedSectionKey
```

Look for PlexMovieGrid, PlexShowGrid, PlexMovieList, PlexShowList, PlexArtistGrid, PlexArtistList instantiations and add this property binding to each. (The first four are confirmed; verify where PlexArtistGrid/PlexArtistList are instantiated — they may be in a different screen like ListenScreen. Skip any that are not in WatchScreen.)

## Non-goals
- Do not remove `settings.setSortPlexMovies()` / `settings.setSortPlexShows()` call-sites (the write to settings is fine; only the read-back in Component.onCompleted is wrong)
- Do not change the `filterByGenre()` / `filterShowsByGenre()` backend calls
- Do not change sort overlay logic beyond the `onGenresReady` title fix
- Do not touch `PlexOnDeckGrid`, `PlexOnDeckList`, `MyList*` views

## Acceptance criteria
1. Set sort to Rating, quit, reopen → status bar shows "Sort: Rating" and content is sorted by rating
2. Set genre filter, quit, reopen → status bar shows the genre label correctly (not blank)
3. No regression: changing sort/genre within a session still works correctly
