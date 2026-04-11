# Task 002: QML spinner and view transition state management

## Context
With `selectCategory()` now async, QML must:
1. Show a spinner overlay while the category is scanning
2. Store the category type (flat vs tv_shows) so the view knows which grid/list to show
3. Transition views when the scan *starts* (not after `selectCategory` returns)

## Objective
Update `LocalVideosScreen.qml` to display loading feedback and manage view transitions for async category scanning.

## Scope

### File: `qml/screens/LocalVideosScreen.qml`

**Add state properties** (after line 40, alongside existing properties):
```qml
property string _selectedCategoryType: ""  // "flat" or "tv_shows"
```

**Remove inline view transitions** from the `Keys.onPressed` handler (lines 141–158):
- Delete: `localVideosScreen.currentView = "videos"` (line 149)
- Delete: `localVideosScreen.currentView = "shows"` (line 151)

**Add view transition logic** — new `Connections` block after `Component.onCompleted` (around line 81):
```qml
Connections {
    target: localVideos
    enabled: localVideos !== null

    function onCategoryScanningChanged() {
        if (localVideos.categoryScanning && localVideosScreen._selectedCategoryType !== "") {
            // Transition view as soon as scan starts (before data arrives)
            if (localVideosScreen._selectedCategoryType === "flat")
                localVideosScreen.currentView = "videos"
            else
                localVideosScreen.currentView = "shows"
        }
    }
}
```

**Update `Keys.onPressed` handler** (lines 142–158) to store category type:
- After `localVideosScreen._selectedCategoryIndex = currentIndex`, add:
  ```qml
  localVideosScreen._selectedCategoryType = currentItem.categoryType
  ```
- After `localVideos.selectCategory(currentIndex)`, remove the inline view transitions (they move to the Connections block)

**Update `MouseArea.onDoubleClicked` handler** (lines 202–219) similarly:
- Add `localVideosScreen._selectedCategoryType = model.type` after setting the index
- Remove inline `currentView = "videos"` / `currentView = "shows"` (the Connections block handles it)

**Add spinner overlay** — new `Rectangle` at the end of the file (before the closing `}` of LocalVideosScreen):
```qml
// ── Loading overlay ───────────────────────────────────────────────────────────
Rectangle {
    anchors.fill: parent
    color: Theme.colorBackground
    opacity: 0.95
    visible: localVideos ? localVideos.categoryScanning : false
    z: 100

    Column {
        anchors.centerIn: parent
        spacing: root.vpx(16)

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Loading..."
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Scanning videos..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }
}
```

## Non-goals
- Do not add per-item progress indicators
- Do not change the navTarget navigation logic (lines 46–76) — it's already independent
- Do not change the grid/list component loading properties (they're optional with the overlay)
- Do not change the _routeFocus() method

## Acceptance criteria
1. View transitions happen when scanning starts (via Connections callback), not inline
2. Spinner overlay is visible while `localVideos.categoryScanning` is true
3. Spinner disappears when scan completes (categoryScanning goes false → videosModelChanged/showsModelChanged fires)
4. Grid/list populates after spinner disappears
5. Category type is stored before the async call so the Connections block knows which view to show
6. No regressions in keyboard/mouse navigation

## Constraints
- Must guard `localVideos` access (it can be null during initialization)
- The overlay must have higher z-index than the grid/list so it covers them
- The Connections block must only act when `_selectedCategoryType` is set (not empty string)
