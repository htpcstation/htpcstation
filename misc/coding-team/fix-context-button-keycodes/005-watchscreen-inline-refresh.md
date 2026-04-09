# Task 005 — Move WatchScreen Refresh into the library ListView as the last row

## Context

`WatchScreen.qml` currently has:
- `libraryList` (ListView) with `bottomMargin: root.vpx(96)` to reserve space
  for a separate Refresh item below it.
- A standalone `refreshItem` (Item) anchored to `bottom: parent.bottom` of
  `libraryListArea`, outside the list.
- Manual focus wiring: Down on last list item → `refreshItem.forceActiveFocus()`;
  Up on refreshItem → `libraryList.forceActiveFocus()` at last index.
- A guard in `_routeFocus()`: `if (refreshItem.activeFocus) return`.

The music screen (`ListenScreen.qml`) uses the simpler pattern: Refresh is
just the last entry in the ListView model array
`{ label: "↻  Refresh", action: "refresh" }`. No separate item, no reserved
margin, no manual focus wiring.

## Objective

Make WatchScreen's Refresh row work exactly like ListenScreen's: it is the
last delegate in `libraryList`, scrolls with the list, and is reached by
normal ListView D-pad navigation.

## Scope — what to change in `WatchScreen.qml`

### 1. `_libraryEntries` model — add a sentinel at the end

`_getVideoLibraries()` builds the array from `plex.getLibraryList()`. Append
a sentinel entry after the filtered results:

```js
function _getVideoLibraries() {
    var all = plex.getLibraryList()
    var filtered = []
    for (var i = 0; i < all.length; i++) {
        if (all[i].type !== "artist") filtered.push(all[i])
    }
    filtered.push({ title: watchScreen._refreshing ? "Refreshing..." : "↻  Refresh",
                    type: "refresh", sectionKey: "", count: 0 })
    return filtered
}
```

Because `_refreshing` is a property, the model array must be rebuilt when it
changes. Add:

```qml
on_RefreshingChanged: _libraryEntries = _getVideoLibraries()
```

### 2. Delegate — handle the refresh sentinel

In the existing delegate, the library title `Text` already reads
`modelData.title` and the count `Text` reads `modelData.count`. The highlight
`Rectangle` and `FocusRing` already work for any row. No structural delegate
changes are needed.

The only addition: in the `Keys.onPressed` accept handler inside the delegate
(or in `libraryList.Keys.onPressed`), check for `type === "refresh"` and
trigger the refresh instead of navigating to content.

The current `Keys.onPressed` on `libraryList` handles Accept by reading
`currentItem.entryType`. Add a branch:

```qml
if (currentItem.entryType === "refresh") {
    event.accepted = true
    if (!watchScreen._refreshing) {
        watchScreen._refreshing = true
        watchScreen._availabilityKnown = false
        plex.refresh()
    }
}
```

Also expose `entryType` from the delegate's `modelData.type` — it already
does this via `readonly property string entryType: modelData.type`, so the
refresh type flows through automatically.

The `MouseArea.onDoubleClicked` handler also reads `modelData.type` — add a
guard so double-clicking the refresh row triggers refresh, not navigation:

```qml
} else if (modelData.type === "refresh") {
    if (!watchScreen._refreshing) {
        watchScreen._refreshing = true
        watchScreen._availabilityKnown = false
        plex.refresh()
    }
}
```

### 3. Remove the standalone `refreshItem`

Delete the entire `Item { id: refreshItem ... }` block (lines 681–730).

### 4. Remove the `bottomMargin` reservation on `libraryList`

Change:
```qml
// Leave room for the Refresh item (64px height + 16px bottom margin + 16px gap)
bottomMargin: root.vpx(96)
```
to:
```qml
bottomMargin: root.vpx(16)
```
(standard bottom padding, same as topMargin).

### 5. Remove the `refreshItem.activeFocus` guard in `_routeFocus()`

Delete:
```qml
// Don't steal focus from the Refresh item when it is already focused.
if (refreshItem.activeFocus) return
```

### 6. Remove the Up/Down manual focus wiring in `libraryList.Keys.onPressed`

Delete:
```qml
} else if (event.key === Qt.Key_Down && currentIndex === count - 1) {
    event.accepted = true
    refreshItem.forceActiveFocus()
}
```

And remove the entire `Keys.onPressed` block on `refreshItem` (already gone
with step 3).

### 7. Style the refresh row to match ListenScreen

The refresh row should be visually distinct from library entries — use
`Theme.colorTextDim` for the title text when `type === "refresh"`, matching
the dimmed style used when refreshing. The existing delegate title Text uses:

```qml
color: modelData.type === "ondeck" ? Theme.colorPrimary : Theme.colorText
```

Extend this:
```qml
color: modelData.type === "refresh"
    ? Theme.colorTextDim
    : (modelData.type === "ondeck" ? Theme.colorPrimary : Theme.colorText)
```

Also suppress the count text for the refresh row (count is already 0, so the
existing `modelData.count > 0 ? modelData.count : ""` guard already hides it
— no change needed).

Also suppress the `▸` indentation indicator for the refresh row:
```qml
opacity: modelData.type === "refresh" ? 0.0 : 0.5
```

## Non-goals / Later

- Do not change any other screen or file.
- Do not change the refresh logic itself (`plex.refresh()`, `_refreshing`,
  `_availabilityKnown`).
- Do not add animations or separators.

## Constraints / Caveats

- `_libraryEntries` is a JS array property. Mutating it in-place does not
  trigger QML bindings — always reassign: `_libraryEntries = _getVideoLibraries()`.
- The sentinel's `title` must be reactive to `_refreshing`. Since JS arrays
  are not reactive, the `on_RefreshingChanged` handler (step 1) handles this
  by rebuilding the array.
- `libraryList.onModelChanged` resets `currentIndex = 0` — this fires on
  every `_refreshing` toggle. That is acceptable (the list is short and the
  user just triggered a refresh).
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
