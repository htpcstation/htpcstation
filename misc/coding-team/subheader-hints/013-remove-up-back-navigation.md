# Task 013 — Remove Up-arrow back navigation from all screens

## Context

The old UI had a launcher row at the top. Pressing Up on the first item in a list
would "escape" back to the launcher. The launcher no longer exists in the current
layout — `back()` now exits the tab entirely. This makes Up on the first item
unexpectedly exit the screen.

## Objective

Remove all `Key_Up → back()` patterns from the following files. In each case,
simply delete the `else if` block (or the OR clause) that triggers `back()` on Up.
Do NOT change any other key handling.

### 1. `RetroGamesScreen.qml`
Remove:
```qml
if (event.key === Qt.Key_Up && currentIndex === 0) {
    event.accepted = true
    retroGamesScreen.back()
} else if ...
```
Change to just start with `if (keys.isAccept(event)) {` (the next branch).

### 2. `PcGamesScreen.qml`
Same pattern — remove `Key_Up && currentIndex === 0 → pcGamesScreen.back()`.

### 3. `MoonlightScreen.qml`
Same pattern — remove `Key_Up && currentIndex === 0 → moonlightScreen.back()`.

### 4. `WatchScreen.qml`
Same pattern — remove `Key_Up && currentIndex === 0 → watchScreen.back()`.

### 5. `ListenScreen.qml`
Remove:
```qml
} else if (event.key === Qt.Key_Up && listenMenu.currentIndex === 0) {
    event.accepted = true
    listenScreen.back()
}
```

### 6. `LiveTvScreen.qml`
The condition is an OR:
```qml
if (keys.isCancel(event) || (event.key === Qt.Key_Up && currentIndex === 0)) {
```
Change to:
```qml
if (keys.isCancel(event)) {
```

### 7. `PlexArtistGrid.qml`
Remove:
```qml
} else if (event.key === Qt.Key_Up && artistGrid.currentIndex < artistGrid._columns) {
    event.accepted = true
    plexArtistGrid.back()
}
```

## Scope

- `qml/screens/RetroGamesScreen.qml`
- `qml/screens/PcGamesScreen.qml`
- `qml/screens/MoonlightScreen.qml`
- `qml/screens/WatchScreen.qml`
- `qml/screens/ListenScreen.qml`
- `qml/screens/LiveTvScreen.qml`
- `qml/screens/PlexArtistGrid.qml`

## Non-goals

- Do NOT touch any other `Key_Up` handlers (sort overlay navigation, settings list
  navigation, resume dialog, etc.) — those are all correct.
- Do NOT change any other key bindings.
- Do NOT change any other files.
