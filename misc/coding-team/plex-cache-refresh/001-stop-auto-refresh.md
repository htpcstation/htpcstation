# Task 001 — Stop automatic plex.refresh() on screen load

## Context

`WatchScreen` calls `plex.refresh()` in `Component.onCompleted` and in
`onActiveFocusChanged`. `ListenScreen` calls `plex.refresh()` in
`onActiveFocusChanged`. Both calls happen before the user has done anything,
introducing visible network lag on every cold load.

The in-memory models already act as a cache — if they are populated from a
previous session (or a manual Refresh), the UI should show that data immediately
without hitting the network.

## Objective

### WatchScreen.qml

1. Remove `plex.refresh()` from `Component.onCompleted` (lines ~1029–1033).
   Keep the `settings.watchViewMode` read. Remove the `_refreshed = true` and
   `_availabilityKnown = false` lines from this block too.

2. In `onActiveFocusChanged`, replace the current guard:
   ```qml
   if (!_refreshed || _libraryEntries.length === 0) {
       _refreshed = true
       _availabilityKnown = false
       plex.refresh()
   }
   ```
   With a silent empty-state guard — only fetch if models are completely empty
   (first ever launch with no data):
   ```qml
   if (_libraryEntries.length === 0 && !_refreshed) {
       _refreshed = true
       _availabilityKnown = false
       plex.refresh()
   }
   ```
   This means: on first launch with no data, trigger one silent fetch. On all
   subsequent visits (data already in models), do nothing.

### ListenScreen.qml

1. In `onActiveFocusChanged`, remove `plex.refresh()` from the `!_initialized`
   block. Keep `_trySelectMusicLibrary()` — it calls `plex.selectLibrary()` which
   is needed to populate the artists model.

2. Add an empty-state guard for the artists model: if `_initialized` is already
   true but the artists model is empty (plex was unavailable on first load), allow
   a retry. Check `plex.artistsModel` count or use the existing `_noLibrary` flag.
   Specifically: if `_initialized && _noLibrary && !_loading`, call
   `_trySelectMusicLibrary()` again on focus.

## Scope

- `qml/screens/WatchScreen.qml`
- `qml/screens/ListenScreen.qml`

## Non-goals

- Do not change LiveTvScreen.
- Do not change `plex_library.py`.
- Do not add the Refresh button yet (Task 002).
- Do not add the lazy refresh toggle yet (Task 003).

## Acceptance criteria

- Navigating to Plex Media or Plex Music with data already in models makes
  zero network calls.
- On first launch (empty models), one silent fetch is triggered automatically.
