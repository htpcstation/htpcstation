# Task 007 — Focus scale animation

> Full spec in `misc/coding-team/ui-redesign/task-sheet.md`.
> Test command: `python3 -m pytest tests/ -q`
> Tokens added in Task 006: `Theme.focusScale = 1.05`, `Theme.focusScaleDuration = 120`

## The clipping constraint

Nearly every ListView/GridView has `clip: true`. Scaling the delegate
**root** FocusScope would clip the overflow at the original bounds.

**Rule:** Apply `scale` + `Behavior` to the **inner visual item** (the card
`Rectangle`, poster `Image`, or equivalent visual container) — NOT the
delegate root FocusScope. The delegate root stays at its original size;
only the rendered content scales up.

For the `FocusRing` component: it `anchors.fill: parent` (the delegate
root), so it does NOT scale with the inner item. That is correct — the
focus ring should stay at the cell boundary, not grow with the card.
No changes to `FocusRing.qml` are needed.

## Pattern to apply

For every focusable item, find the primary visual container (the
`Rectangle` or `Image` that fills the delegate) and add:

```qml
scale: parent.activeFocus ? Theme.focusScale : 1.0
Behavior on scale {
    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
}
```

Where `parent` is the delegate FocusScope that has `activeFocus`.

For grid delegates that are tightly packed, also add to the delegate root:
```qml
z: activeFocus ? 1 : 0
```
This ensures the scaled card renders above its neighbours.

## Scope — files and items to update

### `qml/screens/HomeScreen.qml` — tab buttons
The `buttonItem` FocusScope contains a `Rectangle` fallback and a focus
`Rectangle` border. Apply scale to the outer `FocusScope` directly here
(the home screen is NOT inside a clipped ListView):
```qml
// On buttonItem FocusScope:
scale: activeFocus ? Theme.focusScale : 1.0
Behavior on scale {
    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
}
```

### `qml/screens/WatchScreen.qml` — library list delegate
The delegate `FocusScope` (`delegateRoot`) contains a highlight `Rectangle`.
Apply scale to the highlight `Rectangle` (the visual card):
```qml
scale: delegateRoot.ListView.isCurrentItem && libraryList.activeFocus
    ? Theme.focusScale : 1.0
Behavior on scale { NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic } }
```
Add `z: delegateRoot.ListView.isCurrentItem ? 1 : 0` to `delegateRoot`.

### `qml/screens/RetroGamesScreen.qml` — system list delegate
Same pattern as WatchScreen delegate.

### `qml/screens/GameGridView.qml` — game grid delegate
Apply scale to the inner card `Rectangle`. Add `z` to delegate root.

### `qml/screens/GameListView.qml` — game list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/ListenScreen.qml` — menu + all list/grid delegates
Multiple ListViews: `listenMenu`, `recentlyAddedList`, `playlistList`,
`albumList`, `trackList`, `playlistTrackList`. Apply scale to the inner
highlight/card `Rectangle` in each delegate.

### `qml/screens/PlexMovieGrid.qml` — movie grid delegate
Apply scale to the poster `Rectangle`/`Image` container. Add `z` to root.

### `qml/screens/PlexMovieList.qml` — movie list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/PlexShowGrid.qml` — show grid delegate
Same as PlexMovieGrid.

### `qml/screens/PlexShowList.qml` — show list delegate
Same as PlexMovieList.

### `qml/screens/PlexOnDeckGrid.qml` — on-deck grid delegate
Apply scale to the card container. Add `z` to root.

### `qml/screens/PlexOnDeckList.qml` — on-deck list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/PlexArtistGrid.qml` — artist grid delegate
Apply scale to the card container. Add `z` to root.

### `qml/screens/PlexArtistList.qml` — artist list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/MoonlightAppGrid.qml` — app grid delegate
Apply scale to the card container. Add `z` to root.

### `qml/screens/MoonlightAppList.qml` — app list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/MoonlightScreen.qml` — host list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/SteamGameGrid.qml` — game grid delegate
Apply scale to the card container. Add `z` to root.

### `qml/screens/SteamGameList.qml` — game list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/RecentlyPlayedGrid.qml` — grid delegate
Apply scale to the card container. Add `z` to root.

### `qml/screens/RecentlyPlayedList.qml` — list delegate
Apply scale to the inner highlight `Rectangle`.

### `qml/screens/PcGamesScreen.qml` — system list delegate
Apply scale to the inner highlight `Rectangle`.

## Items to SKIP (do not apply scale)

- `SettingsScreen.qml` — settings rows are functional, not content cards.
  Scale animation would feel wrong here.
- `LiveTvScreen.qml` — dense EPG grid; scale would cause significant overlap.
- `PlexShowDetail.qml` — episode list rows; functional list, not content cards.
- `PlexMovieDetail.qml`, `SteamGameDetail.qml`, `MoonlightAppDetail.qml`,
  `RecentlyPlayedDetail.qml` — detail view action buttons are small; skip.
- `ControllerMappingDialog.qml`, `ModifierCaptureDialog.qml` — dialogs.
- `SystemCoresScreen.qml`, `RetroarchHotkeysScreen.qml` — settings screens.

## Constraints / Caveats

- Scale is applied to the **inner visual item**, never the delegate root
  FocusScope, to avoid clipping artifacts.
- `z: activeFocus ? 1 : 0` on the delegate root is required for grid views
  where cards are tightly packed — without it, the scaled card is obscured
  by its neighbours' normal z-order.
- Use `Theme.focusScale` and `Theme.focusScaleDuration` — do not hardcode
  values.
- `Easing.OutCubic` gives a fast-start, slow-finish feel that reads as
  snappy at 10 feet.
- Do not change `FocusRing.qml` — it stays at the delegate root boundary.
- All tests must pass. No Python files change in this task.
