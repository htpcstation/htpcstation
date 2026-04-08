# Task 008 — PlexMovieDetail + PlexShowDetail: replace footer actionBar with sub-header statusBar

## Context

Both Plex detail screens have a footer `actionBar` (48px Rectangle anchored to `parent.bottom`).
All other third-level screens now use a 28px `statusBar` sub-header below `headerBar`.
`GameDetailView.qml` was already converted in Task 007 — use it as the reference.

## Objective

Apply the same transformation to both screens:
1. Remove the `actionBar` Rectangle.
2. Add a `statusBar` Rectangle (28px) immediately after `headerBar`.
3. Fix the `contentArea` / `mainFlickable` bottom anchor from `actionBar.top` → `parent.bottom`.

---

## PlexMovieDetail.qml

### statusBar hints (right-aligned Row)

Non-obvious actions only — Accept and Cancel are excluded:

```qml
Rectangle {
    id: statusBar
    anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
    height: root.vpx(28)
    color: Qt.darker(Theme.colorSecondary, 1.3)

    Row {
        anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
        spacing: root.vpx(16)

        Text {
            text: keys.useGamepadLabels ? "[ ◀▶ ]  Prev/Next" : "[ ←→ ]  Prev/Next"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Text {
            text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "F1  My List"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Text {
            text: {
                var watchLabel = movieDetailView._viewCount > 0 ? "Mark Unwatched" : "Mark Watched"
                return keys.useGamepadLabels
                    ? keys.context2Label + "  " + watchLabel
                    : "F2  " + watchLabel
            }
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
```

### Anchor fix

`contentArea` bottom: `actionBar.top` → `parent.bottom`

---

## PlexShowDetail.qml

### statusBar hints (right-aligned Row)

```qml
Rectangle {
    id: statusBar
    anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
    height: root.vpx(28)
    color: Qt.darker(Theme.colorSecondary, 1.3)

    Row {
        anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
        spacing: root.vpx(16)

        Text {
            text: keys.useGamepadLabels ? "[ ◀▶ ]  Season" : "[ ←→ ]  Season"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Text {
            text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "F1  My List"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Text {
            text: {
                var watchLabel = showDetailView._viewCount > 0 ? "Mark Unwatched" : "Mark Watched"
                return keys.useGamepadLabels
                    ? keys.context2Label + "  " + watchLabel
                    : "F2  " + watchLabel
            }
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
```

### Anchor fix

`mainFlickable` bottom: `actionBar.top` → `parent.bottom`

---

## Scope

- `qml/screens/PlexMovieDetail.qml`
- `qml/screens/PlexShowDetail.qml`

## Non-goals / Later

- Do not touch any other file.
- Do not change key bindings.
- Do not change any other layout or content.
