# Task 002 — Add Refresh button to WatchScreen and ListenScreen

## Context

After Task 001, `plex.refresh()` is no longer called automatically. The user
needs a way to manually update the content. A dedicated "Refresh" item is added
to the library list / menu list on each second-level screen.

## Objective

### WatchScreen.qml — add Refresh item to library list

The library list is driven by `watchScreen._libraryEntries` (a JS array built
from `plex.getLibraryList()`). The Refresh item is NOT part of this model —
it is a separate `Item` rendered below the `ListView`, inside `libraryListArea`.

1. Shrink `libraryList` bottom anchor to leave room:
   Change `bottom: parent.bottom` → `bottom: refreshItem.top`
   (keep existing `bottomMargin: root.vpx(32)` on the list, or reduce it).

2. Add a `refreshItem` below the list:
```qml
Item {
    id: refreshItem

    anchors {
        left: parent.left
        right: parent.right
        bottom: parent.bottom
        leftMargin: root.vpx(32)
        rightMargin: root.vpx(32)
        bottomMargin: root.vpx(16)
    }
    height: root.vpx(64)

    // Highlight background (matches library list delegate style)
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: refreshItem.activeFocus ? 1.0 : 0.0
        radius: root.vpx(Theme.focusRingRadius)
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
    }

    Text {
        anchors { left: parent.left; leftMargin: root.vpx(40); verticalCenter: parent.verticalCenter }
        text: watchScreen._refreshing ? "Refreshing..." : "↻  Refresh"
        color: watchScreen._refreshing ? Theme.colorTextDim : Theme.colorText
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeHeading)
    }

    FocusRing {}

    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            if (!watchScreen._refreshing) {
                watchScreen._refreshing = true
                watchScreen._availabilityKnown = false
                plex.refresh()
            }
        } else if (keys.isCancel(event)) {
            event.accepted = true
            watchScreen.back()
        } else if (event.key === Qt.Key_Up) {
            event.accepted = true
            libraryList.forceActiveFocus()
            libraryList.currentIndex = libraryList.count - 1
        }
    }
}
```

3. Add `property bool _refreshing: false` to `watchScreen`.

4. In the `Connections { target: plex }` block, set `_refreshing = false` when
   `onLibrariesModelChanged` fires (data has arrived).

5. Wire keyboard navigation: in `libraryList.Keys.onPressed`, when Down is
   pressed on the last item (`currentIndex === count - 1`), move focus to
   `refreshItem`. Add:
   ```qml
   } else if (event.key === Qt.Key_Down && currentIndex === count - 1) {
       event.accepted = true
       refreshItem.forceActiveFocus()
   }
   ```

6. Update `_routeFocus()`: when `currentView === "libraries"`, if
   `refreshItem.activeFocus` is true, leave it — don't steal focus back to
   `libraryList`.

### ListenScreen.qml — add Refresh item to menu list

The menu list model is a JS array built inline. Add a `"refresh"` action item
at the end of the model, after `"artists"`:

```qml
items.push({ label: listenScreen._refreshing ? "Refreshing..." : "↻  Refresh",
             action: "refresh" })
```

In `listenMenu.Keys.onPressed`, handle the new action:
```qml
} else if (item.menuAction === "refresh") {
    if (!listenScreen._refreshing) {
        listenScreen._refreshing = true
        listenScreen._loading = true
        plex.refresh()
        _trySelectMusicLibrary()
    }
}
```

Add `property bool _refreshing: false` to `listenScreen`.

In the `Connections { target: plex }` block, set `_refreshing = false` when
`onArtistsModelChanged` fires.

## Scope

- `qml/screens/WatchScreen.qml`
- `qml/screens/ListenScreen.qml`

## Non-goals

- Do not change `plex_library.py`.
- Do not add the lazy refresh toggle (Task 003).
- Do not change LiveTvScreen.
- The Refresh item does not need a hint in the statusBar — it is navigated to
  with D-pad and activated with Accept, same as any other list item.
