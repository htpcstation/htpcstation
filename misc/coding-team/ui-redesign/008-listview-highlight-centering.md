# Task 008 — ListView/GridView highlight centering

> Full spec in `misc/coding-team/ui-redesign/task-sheet.md`.
> Test command: `python3 -m pytest tests/ -q`

## The problem

No ListView or GridView has `preferredHighlightBegin` / `preferredHighlightEnd`
set. The focused item skates to the top/bottom edge before the list scrolls —
the focus indicator moves, not the content.

## The fix

Add to every ListView and GridView:

```qml
highlightRangeMode:      ListView.ApplyRange
preferredHighlightBegin: height * 0.35
preferredHighlightEnd:   height * 0.65
```

**Why `ApplyRange` not `StrictlyEnforceRange`:**
`ApplyRange` keeps the focused item in the center third when possible but
allows it to be at the edge when the list is too short to scroll.
`StrictlyEnforceRange` would prevent focus from reaching the first/last
items in short lists.

**Why `height * 0.35` / `height * 0.65`:**
`preferredHighlightBegin/End` are in pixels. Using a fraction of `height`
makes them scale with the list size automatically.

## Complete list of ListViews/GridViews to update

For each, add the three properties alongside the existing
`highlightMoveDuration: Theme.animDurationFast` line.

### `qml/screens/WatchScreen.qml`
- `libraryList` (ListView)

### `qml/screens/RetroGamesScreen.qml`
- `systemList` (ListView)

### `qml/screens/GameGridView.qml`
- `gameGrid` (GridView)

### `qml/screens/GameListView.qml`
- `gameListView` (ListView)

### `qml/screens/ListenScreen.qml`
- `listenMenu` (ListView)
- `recentlyAddedList` (ListView) — or equivalent id
- `playlistList` (ListView) — or equivalent id
- `albumList` (ListView) — or equivalent id
- `trackList` (ListView) — or equivalent id
- `playlistTrackList` (ListView) — or equivalent id

### `qml/screens/PlexMovieGrid.qml`
- movie GridView

### `qml/screens/PlexMovieList.qml`
- movie ListView

### `qml/screens/PlexShowGrid.qml`
- show GridView

### `qml/screens/PlexShowList.qml`
- show ListView

### `qml/screens/PlexOnDeckGrid.qml`
- on-deck GridView

### `qml/screens/PlexOnDeckList.qml`
- on-deck ListView

### `qml/screens/PlexArtistGrid.qml`
- artist GridView

### `qml/screens/PlexArtistList.qml`
- artist ListView (and any inner album/track ListViews)

### `qml/screens/MoonlightAppGrid.qml`
- app GridView

### `qml/screens/MoonlightAppList.qml`
- app ListView

### `qml/screens/MoonlightScreen.qml`
- host ListView

### `qml/screens/SteamGameGrid.qml`
- game GridView

### `qml/screens/SteamGameList.qml`
- game ListView

### `qml/screens/RecentlyPlayedGrid.qml`
- GridView

### `qml/screens/RecentlyPlayedList.qml`
- ListView

### `qml/screens/PcGamesScreen.qml`
- system ListView

### `qml/screens/SettingsScreen.qml`
- settings ListView

### `qml/screens/LiveTvScreen.qml`
- channel ListView

## Items to SKIP

- `PlexShowDetail.qml` — the episode list has custom scroll/focus logic;
  check before touching. If it has a simple ListView with no custom
  highlight logic, apply. If it has `currentIndex` management that would
  conflict, skip.
- Any ListView inside a detail view that is very short (< 5 items) and
  never scrolls — applying `ApplyRange` to these is harmless but pointless.
  Apply anyway for consistency.

## Constraints / Caveats

- `preferredHighlightBegin` and `preferredHighlightEnd` are **pixel values**,
  not fractions. `height * 0.35` evaluates to a pixel value at runtime.
- For `GridView`, the same properties apply and refer to the vertical scroll
  axis (assuming vertical grids, which all current grids are).
- Do not change `highlightMoveDuration` — it is already set correctly.
- No Python files change in this task.
- All tests must pass.
