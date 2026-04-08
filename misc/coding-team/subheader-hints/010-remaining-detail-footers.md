# Task 010 — Remove footer actionBar from SteamGameDetail, MoonlightAppDetail, RecentlyPlayedDetail

## Context

Three detail screens still have a footer `actionBar` (48px Rectangle anchored to
`parent.bottom`). All other detail screens were converted in Tasks 007 and 008.
Use `GameDetailView.qml` as the reference for the finished pattern.

## Objective

Apply the same transformation to all three screens:
1. Remove the `actionBar` Rectangle entirely.
2. Add a `statusBar` Rectangle (28px) immediately after `headerBar`.
3. Fix `contentArea` bottom anchor: `actionBar.top` → `parent.bottom`.
4. Fix toast anchor: `bottom: actionBar.top` → `bottom: parent.bottom`, `bottomMargin: root.vpx(64)`.

---

## SteamGameDetail.qml

### statusBar hints

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
            text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "1  Favorite"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
```

### Anchor fixes
- `contentArea`: `top: headerBar.bottom` → `top: statusBar.bottom`, `bottom: actionBar.top` → `bottom: parent.bottom`
- `steamDetailToast`: `bottom: actionBar.top` → `bottom: parent.bottom`, `bottomMargin: root.vpx(64)`

---

## MoonlightAppDetail.qml

### statusBar hints

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
            text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "1  Favorite"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
```

### Anchor fixes
- `contentArea`: `top: headerBar.bottom` → `top: statusBar.bottom`, `bottom: actionBar.top` → `bottom: parent.bottom`
- `moonlightDetailToast`: `bottom: actionBar.top` → `bottom: parent.bottom`, `bottomMargin: root.vpx(64)`

---

## RecentlyPlayedDetail.qml

Read the file first. Apply the same pattern. Hints: `[ ◀▶ ] Prev/Next` only (no
context1 action exists in this screen). No toast to reanchor.

---

## Scope

- `qml/screens/SteamGameDetail.qml`
- `qml/screens/MoonlightAppDetail.qml`
- `qml/screens/RecentlyPlayedDetail.qml`

## Non-goals

- Do not change key bindings.
- Do not change any other files.
