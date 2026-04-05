# Task Brief 002 — Watch Screen Header Fade

## Context

`WatchScreen.qml` has a left-side library list (`id: libraryListArea`) and a right-side
content area. When the user navigates from the library list into a content grid or list,
the header/library area should fade to 30% opacity to give visual focus to the content.
It should restore to full opacity when focus returns to the library list.

Content grids/lists: `movieGrid`, `movieList`, `showGrid`, `showList`, `onDeckGrid`,
`onDeckList`, `myListGridView`, `myListListView`.

The fade should NOT apply in the detail view (`currentView === "detail"`).

## Objective

Add a `_contentFocused` bool to `WatchScreen` and bind `libraryListArea` opacity to it
with a 160ms animation.

## Scope

**Modified file:** `qml/screens/WatchScreen.qml` only.

---

## Changes

### New property
```qml
property bool _contentFocused: false
```

### `libraryListArea` opacity
```qml
opacity: watchScreen._contentFocused ? 0.3 : 1.0
Behavior on opacity { NumberAnimation { duration: 160 } }
```

### Set `_contentFocused`

Each content grid/list already has `onActiveFocusChanged` or is managed by `_routeFocus`.
The cleanest approach: update `_routeFocus()` to set `_contentFocused` based on where
focus is going:

```qml
function _routeFocus() {
    if (_resumeDialogVisible) { resumeDialog.forceActiveFocus(); return }
    if (_loadingOverlayVisible) { loadingOverlay.forceActiveFocus(); return }

    if (currentView === "libraries") {
        _contentFocused = false
        libraryList.forceActiveFocus()
    } else if (currentView === "content") {
        _contentFocused = true
        // ... existing content routing ...
    } else if (currentView === "detail") {
        _contentFocused = false   // don't fade in detail view
        // ... existing detail routing ...
    }
}
```

Also clear `_contentFocused` in `onActiveFocusChanged` when `WatchScreen` first gains
focus (before `_routeFocus` runs):
```qml
onActiveFocusChanged: {
    if (activeFocus) {
        _contentFocused = false   // reset; _routeFocus will set correctly
        // ... existing refresh logic ...
        _routeFocus()
    }
}
```

## Constraints / Caveats

- Read `_routeFocus()` fully before editing — it has modal overlay guards at the top
  that must be preserved.
- `libraryListArea` is the correct id to fade — it contains both the header label and
  the `libraryList` ListView. Confirm by reading the QML before editing.
- Do not add `_contentFocused` changes anywhere except `_routeFocus()` and
  `onActiveFocusChanged` — other paths (e.g. `onCurrentViewChanged`) already call
  `_routeFocus()` so they get it for free.
- No new tests needed — purely visual QML change.
