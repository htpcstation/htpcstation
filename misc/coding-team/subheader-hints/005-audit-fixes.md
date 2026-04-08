# Task 005 — Audit fixes: GameListView missing hint + GameDetailView key binding bug

## Context

A full audit of all third-level screens found two issues:

1. **`GameListView.qml`** — `isContext1` (X / F1) toggles a favorite on the current game,
   but there is no hint for it in the `statusBar` Row. The other list/grid screens that have
   a Favorite action (SteamGameList, SteamGameGrid, MoonlightAppList, MoonlightAppGrid) all
   show the hint correctly.

2. **`GameDetailView.qml`** — The Favorite action is bound to the raw `Qt.Key_F1` instead of
   `keys.isContext1(event)`. This means it works on keyboard but silently fails on a gamepad
   (the X button does not emit `Qt.Key_F1`). All other screens that have a Favorite action
   use `keys.isContext1(event)` correctly.

## Objective

### Fix 1 — `GameListView.qml`

Add a Favorite hint to the `statusBar` Row, between the Scroll hint and the Sort hint:

```qml
Text {
    text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "F1  Favorite"
    color: Theme.colorTextDim
    font.family: Theme.fontFamily
    font.pixelSize: root.vpx(Theme.fontSizeSmall)
}
```

The Row order must be: Scroll → **Favorite** → Sort  
(matching the pattern in SteamGameList, MoonlightAppList, etc.)

### Fix 2 — `GameDetailView.qml`

In the `Keys.onPressed` handler, find the branch that checks `Qt.Key_F1` and replace it
with `keys.isContext1(event)`. The action body stays identical — only the condition changes.

Before:
```qml
} else if (event.key === Qt.Key_F1) {
```

After:
```qml
} else if (keys.isContext1(event)) {
```

## Scope

- `qml/screens/GameListView.qml`
- `qml/screens/GameDetailView.qml`

## Non-goals / Later

- Do not change any other files.
- Do not add scroll-description hints to any detail view.
- Do not change the actionBar text in `GameDetailView.qml` — it already displays
  `keys.context1Label` correctly for the Favorite label.
