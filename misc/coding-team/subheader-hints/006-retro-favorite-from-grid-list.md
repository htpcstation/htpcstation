# Task 006 — Favorite retro games from grid and list views

## Context

`library.toggleFavorite(index)` works and emits `library.favoriteToggled(isFavorite)`.

**Working reference:** `PcGamesScreen.qml` — the toast lives in the parent screen
(`PcGamesScreen`), not in the child grid/list views. `steam.favoriteToggled` fires and
`PcGamesScreen` handles it directly with a self-contained toast Rectangle + Timer.

**Current state of retro games:**
- `GameListView` has the `isContext1` key binding and calls `library.toggleFavorite()` ✅
- `GameGridView` has NO `isContext1` key binding and NO Favorite hint ❌
- `RetroGamesScreen`'s `Connections` block routes `onFavoriteToggled` only to
  `gameDetailView.showFavoriteToast()` — so the toast never fires from grid or list view ❌

## Objective

### 1. `GameGridView.qml` — add Favorite key binding and hint

In the `gameGrid` `Keys.onPressed` block, add an `isContext1` branch after `isContext2`:

```qml
} else if (keys.isContext1(event)) {
    event.accepted = true
    if (library) library.toggleFavorite(gameGrid.currentIndex)
}
```

Add a Favorite hint to the `statusBar` Row between Scroll and Sort:

```qml
Text {
    text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "F1  Favorite"
    color: Theme.colorTextDim
    font.family: Theme.fontFamily
    font.pixelSize: root.vpx(Theme.fontSizeSmall)
}
```

Row order: Scroll → **Favorite** → Sort.

### 2. `RetroGamesScreen.qml` — add toast + fix routing

Add a toast Rectangle to `RetroGamesScreen`, identical in structure to the one in
`PcGamesScreen.qml` (lines ~488–523). Place it after the `GameDetailView` block,
before the `Connections` block. Use `z: 100` so it renders above all child views.

Then replace the existing `Connections` block:

```qml
// BEFORE:
Connections {
    target: library
    function onFavoriteToggled(isFavorite) {
        gameDetailView.showFavoriteToast(isFavorite)
    }
}

// AFTER:
Connections {
    target: library
    function onFavoriteToggled(isFavorite) {
        toastBarText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
        toastBar.opacity = 1.0
        toastBarTimer.restart()
    }
}
```

The toast fires for all views (grid, list, detail) — no routing by `currentView` needed.
`GameDetailView.showFavoriteToast()` can be left in place; it just won't be called anymore.

## Scope

- `qml/screens/GameGridView.qml`
- `qml/screens/RetroGamesScreen.qml`

`GameListView.qml` — do NOT touch. The key binding already works; the toast fix in
`RetroGamesScreen` will make it work end-to-end without any changes to the list view.

## Non-goals / Later

- Do not change `GameDetailView.qml`.
- Do not touch any other screen.
- Do not remove `GameDetailView.showFavoriteToast()` — leave it in place.
