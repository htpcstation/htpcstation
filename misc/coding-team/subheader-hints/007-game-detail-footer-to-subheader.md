# Task 007 — GameDetailView: replace footer actionBar with sub-header statusBar

## Context

`GameDetailView.qml` currently has a footer `actionBar` (48px Rectangle anchored to
`parent.bottom`) showing all button hints. All other third-level screens now use a
28px `statusBar` sub-header below `headerBar` for hints. This screen should match.

## Objective

### 1. Remove `actionBar`

Delete the entire `actionBar` Rectangle block (id: `actionBar`, ~lines 311–331).

### 2. Add `statusBar` sub-header

Add a `statusBar` Rectangle immediately after `headerBar`, identical in structure to
the other screens:

```qml
Rectangle {
    id: statusBar

    anchors {
        top: headerBar.bottom
        left: parent.left
        right: parent.right
    }
    height: root.vpx(28)
    color: Qt.darker(Theme.colorSecondary, 1.3)

    Row {
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        spacing: root.vpx(16)

        Text {
            text: keys.useGamepadLabels ? "[ ◀▶ ]  Prev/Next" : "[ ←→ ]  Prev/Next"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Text {
            text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "F1  Favorite"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
```

Hints shown: Prev/Next and Favorite only.
- Launch (Accept) and Back (Cancel) are excluded — universally understood.

### 3. Fix `contentArea` anchor

Change:
```qml
bottom: actionBar.top
```
To:
```qml
bottom: parent.bottom
```

### 4. Fix `favoriteToast` anchor

The toast is currently anchored `bottom: actionBar.top`. Change to:
```qml
bottom: parent.bottom
bottomMargin: root.vpx(64)
```

## Scope

- `qml/screens/GameDetailView.qml` only.

## Non-goals / Later

- Do not touch `RetroGamesScreen.qml` or any other file.
- Do not change the `favoriteToast` Rectangle itself — only its anchor.
- Do not change key bindings.
