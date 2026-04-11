import QtQuick
import ".."
import "../components"

// Local video show poster grid — shows a scrollable grid of show posters.
//
// Focus flow:
//   Gains focus when LocalVideosScreen switches to "shows" view (grid mode).
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits showSelected(index, showData).
//   B (Escape) → emits back() so LocalVideosScreen returns to categories.
//   Y (2)      → opens the sort/filter overlay panel.
FocusScope {
    id: showGridView

    // Emitted when the user presses B / Escape to return to the categories list.
    signal back()

    // Emitted when the user presses A / Return on a show cell.
    signal showSelected(int index, var showData)

    // Emitted when the user changes the view mode via the sort/filter overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected category (set by orchestrator).
    property string systemName: ""

    // View mode ("grid" or "list") — set by orchestrator; do not overwrite in onCompleted
    property string _viewMode: "grid"

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: ""

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")        return "A-Z"
        if (_currentSort === "za")        return "Z-A"
        if (_currentSort === "year_desc") return "Year (Newest)"
        if (_currentSort === "year_asc")  return "Year (Oldest)"
        return "Default"
    }

    // ── Cell dimensions (design-grid px, scaled via vpx) ─────────────────────
    readonly property int _targetCellW: 160
    readonly property int _cellH: 280
    readonly property int _cellSpacing: 12

    // ── Header bar + status bar ───────────────────────────────────────────────
    LibraryHeader {
        id: header
        title: showGridView.systemName
        statusText: showGridView._currentSort !== ""
            ? "Sort: " + showGridView._sortLabel
            : "Default order"
        rightText1: keys.useGamepadLabels ? keys.context2Label + "  Sort / Filter" : "2  Sort / Filter"
    }

    // ── Show grid ─────────────────────────────────────────────────────────────
    GridView {
        id: showGrid

        anchors {
            top: header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: localVideos ? localVideos.showsModel : null
        clip: true
        focus: true

        opacity: (localVideos && localVideos.categoryScanning) ? 0.3 : 1.0
        Behavior on opacity {
            NumberAnimation { duration: 200; easing.type: Easing.InOutQuad }
        }

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(showGridView._targetCellW + showGridView._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(showGridView._targetCellW + showGridView._cellSpacing)
        cellHeight: root.vpx(showGridView._cellH + showGridView._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortFilterOverlay.open()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var item = showGrid.currentItem
                if (item) {
                    showGridView.showSelected(showGrid.currentIndex, {
                        name:        item.itemName,
                        posterPath:  item.itemPosterPath,
                        year:        item.itemYear,
                        description: item.itemDescription,
                        seasonCount: item.itemSeasonCount
                    })
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                showGridView.back()
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: showGrid.count === 0 && (!localVideos || !localVideos.categoryScanning)
            text: "No shows found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Show tile delegate ────────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose fields so the key handler can read them.
            readonly property string itemName:        model.name        || ""
            readonly property string itemPosterPath:  model.posterPath  || ""
            readonly property int    itemYear:        model.year        || 0
            readonly property string itemDescription: model.description || ""
            readonly property int    itemSeasonCount: model.seasonCount || 0

            width: showGrid.cellWidth
            height: showGrid.cellHeight

            z: tileRoot.GridView.isCurrentItem && showGrid.activeFocus ? 1 : 0

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(showGridView._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                scale: tileRoot.GridView.isCurrentItem && showGrid.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                // Subtle highlight when focused
                GridCellHighlight {
                    active: tileRoot.GridView.isCurrentItem && showGrid.activeFocus
                }

                // ── Poster image area ─────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~75% of the card height
                    height: Math.round(parent.height * 0.75)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.posterPath === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.name || ""
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }
                    }

                    Image {
                        id: posterImage

                        anchors.fill: parent
                        source: model.posterPath || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        cache: true
                        sourceSize.width: root.vpx(showGridView._targetCellW)
                        sourceSize.height: Math.round(root.vpx(showGridView._cellH) * 0.75)
                        visible: status === Image.Ready && model.posterPath !== ""
                        clip: true
                    }
                }

                // ── Title label ───────────────────────────────────────────────
                Text {
                    id: titleText

                    anchors {
                        top: posterArea.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(4)
                    }
                    text: model.name || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Year label ────────────────────────────────────────────────
                Text {
                    id: yearText

                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.year > 0 ? "(" + model.year + ")" : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Season count label ────────────────────────────────────────
                Text {
                    anchors {
                        top: yearText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.seasonCount > 0 ? model.seasonCount + " seasons" : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && showGrid.activeFocus
                }
            }
        }
    }

    // ── Sort/Filter overlay ───────────────────────────────────────────────────
    //
    // Sections: 0 = sort, 1 = view (no genre section for shows)
    //
    // Loaded lazily: the FocusScope is not instantiated until the first time
    // the user opens the overlay. The Loader exposes open() and close()
    // so call sites in this file are unchanged.
    Loader {
        id: sortFilterOverlay
        anchors.fill: parent
        active: false

        // Open: initialise overlay state then activate the Loader.
        // forceActiveFocus() is called in onLoaded once the item exists.
        function open() {
            // Capture current state into properties that the Component reads
            // via the Loader's item after it is created.
            sortFilterOverlay._pendingSort = showGridView._currentSort
            sortFilterOverlay._pendingView = showGridView._viewMode
            active = true
        }

        // Close: deactivate (destroys the FocusScope) and restore grid focus.
        function close() {
            active = false
            showGrid.forceActiveFocus()
        }

        // Transient properties used to pass initial state into the component.
        property string _pendingSort: ""
        property string _pendingView: ""

        onLoaded: item.forceActiveFocus()

        sourceComponent: Component {
            FocusScope {
                id: overlay

                anchors.fill: parent
                // enabled mirrors existence: the item only exists while active,
                // so we do not need a separate enabled: visible guard.

                // 0 = sort row focused, 1 = view row focused
                property int _section: 0
                property int _sortIndex: 0
                property int _viewIndex: 0

                readonly property var _sortOptions: [
                    { key: "az",        label: "A-Z" },
                    { key: "za",        label: "Z-A" },
                    { key: "year_desc", label: "Year ↓" },
                    { key: "year_asc",  label: "Year ↑" }
                ]

                Component.onCompleted: {
                    // Initialise selection state from the pending values
                    // stored on the Loader before activation.
                    var sortKeys = ["az", "za", "year_desc", "year_asc"]
                    var si = sortKeys.indexOf(sortFilterOverlay._pendingSort)
                    _sortIndex = si >= 0 ? si : 0

                    var viewKeys = ["grid", "list"]
                    var vi = viewKeys.indexOf(sortFilterOverlay._pendingView)
                    _viewIndex = vi >= 0 ? vi : 0

                    _section = 0
                }

                // ── Backdrop ─────────────────────────────────────────────────
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorImagePlaceholder
                    opacity: 0.55
                }

                // ── Panel ─────────────────────────────────────────────────────
                Rectangle {
                    id: overlayPanel

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    height: viewOptionsRow.y + viewOptionsRow.height + root.vpx(16)
                    color: Theme.colorSecondary
                    opacity: 0.97

                    // ── Panel title ──────────────────────────────────────────
                    Text {
                        id: panelTitle
                        anchors {
                            top: parent.top
                            left: parent.left
                            leftMargin: root.vpx(16)
                            topMargin: root.vpx(10)
                        }
                        text: "Sort / Filter"
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    }

                    Text {
                        anchors {
                            top: parent.top
                            right: parent.right
                            rightMargin: root.vpx(16)
                            topMargin: root.vpx(14)
                        }
                        text: keys.useGamepadLabels ? keys.cancelLabel + " / " + keys.context2Label + "  Close" : "Esc / 2  Close"
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    }

                    // ── Divider ──────────────────────────────────────────────
                    Rectangle {
                        id: divider
                        anchors {
                            top: panelTitle.bottom
                            left: parent.left
                            right: parent.right
                            topMargin: root.vpx(8)
                        }
                        height: root.vpx(1)
                        color: Theme.colorTextDim
                        opacity: 0.3
                    }

                    // ── Sort section label ────────────────────────────────────
                    Text {
                        id: sortLabel
                        anchors {
                            top: divider.bottom
                            left: parent.left
                            leftMargin: root.vpx(16)
                            topMargin: root.vpx(8)
                        }
                        text: "Sort"
                        color: overlay._section === 0 ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    }

                    // ── Sort options row ──────────────────────────────────────
                    Row {
                        id: sortOptionsRow
                        anchors {
                            top: sortLabel.bottom
                            left: parent.left
                            leftMargin: root.vpx(16)
                            topMargin: root.vpx(4)
                        }
                        spacing: root.vpx(6)

                        Repeater {
                            model: overlay._sortOptions

                            delegate: Rectangle {
                                width: root.vpx(72)
                                height: root.vpx(32)
                                color: {
                                    var isFocused = overlay._section === 0
                                                 && overlay._sortIndex === index
                                    return isFocused ? Theme.colorPrimary : "transparent"
                                }
                                radius: root.vpx(Theme.focusRingRadius)

                                Behavior on color {
                                    ColorAnimation { duration: Theme.animDurationFast }
                                }

                                Text {
                                    anchors {
                                        left: parent.left
                                        leftMargin: root.vpx(6)
                                        verticalCenter: parent.verticalCenter
                                    }
                                    text: {
                                        var isActive = modelData.key === showGridView._currentSort
                                        return (isActive ? "✓ " : "") + modelData.label
                                    }
                                    color: {
                                        var isFocused = overlay._section === 0
                                                     && overlay._sortIndex === index
                                        return isFocused ? Theme.colorOverlayText : Theme.colorText
                                    }
                                    font.family: Theme.fontFamily
                                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                }
                            }
                        }
                    }

                    // ── View section label ────────────────────────────────────
                    Text {
                        id: viewLabel
                        anchors {
                            top: sortOptionsRow.bottom
                            left: parent.left
                            leftMargin: root.vpx(16)
                            topMargin: root.vpx(10)
                        }
                        text: "View"
                        color: overlay._section === 1 ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    }

                    // ── View options row ──────────────────────────────────────
                    Row {
                        id: viewOptionsRow
                        anchors {
                            top: viewLabel.bottom
                            left: parent.left
                            leftMargin: root.vpx(16)
                            topMargin: root.vpx(4)
                        }
                        spacing: root.vpx(8)

                        Repeater {
                            model: [
                                { key: "grid", label: "Grid" },
                                { key: "list", label: "List" }
                            ]

                            delegate: Rectangle {
                                width: root.vpx(80)
                                height: root.vpx(32)
                                color: overlay._section === 1
                                       && overlay._viewIndex === index
                                       ? Theme.colorPrimary
                                       : "transparent"
                                radius: root.vpx(Theme.focusRingRadius)

                                Behavior on color {
                                    ColorAnimation { duration: Theme.animDurationFast }
                                }

                                Text {
                                    anchors {
                                        left: parent.left
                                        leftMargin: root.vpx(6)
                                        verticalCenter: parent.verticalCenter
                                    }
                                    text: {
                                        var isActive = modelData.key === showGridView._viewMode
                                        return (isActive ? "✓ " : "") + modelData.label
                                    }
                                    color: overlay._section === 1
                                           && overlay._viewIndex === index
                                           ? Theme.colorOverlayText
                                           : Theme.colorText
                                    font.family: Theme.fontFamily
                                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                }
                            }
                        }
                    }
                }

                // ── Key handling ─────────────────────────────────────────────
                Keys.onPressed: (event) => {
                    var sortCount = overlay._sortOptions.length
                    var viewCount = 2

                    if (keys.isCancel(event) || keys.isContext2(event)) {
                        event.accepted = true
                        sortFilterOverlay.close()

                    } else if (event.key === Qt.Key_Up) {
                        event.accepted = true
                        if (overlay._section > 0)
                            overlay._section -= 1

                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (overlay._section < 1)
                            overlay._section += 1

                    } else if (event.key === Qt.Key_Left) {
                        event.accepted = true
                        if (overlay._section === 0) {
                            if (overlay._sortIndex > 0)
                                overlay._sortIndex -= 1
                        } else {
                            if (overlay._viewIndex > 0)
                                overlay._viewIndex -= 1
                        }

                    } else if (event.key === Qt.Key_Right) {
                        event.accepted = true
                        if (overlay._section === 0) {
                            if (overlay._sortIndex < sortCount - 1)
                                overlay._sortIndex += 1
                        } else {
                            if (overlay._viewIndex < viewCount - 1)
                                overlay._viewIndex += 1
                        }

                    } else if (keys.isAccept(event)) {
                        event.accepted = true

                        // Apply sort
                        var newSort = overlay._sortOptions[overlay._sortIndex].key
                        showGridView._currentSort = newSort
                        if (localVideos) localVideos.sortShows(newSort)

                        // Apply view mode
                        var viewKeys = ["grid", "list"]
                        var newView = viewKeys[overlay._viewIndex]
                        if (newView !== showGridView._viewMode) {
                            sortFilterOverlay.close()  // close() is fine here — viewModeChanged replaces the screen, superseding any focus restore
                            if (settings) settings.setLocalVideoViewMode(newView)
                            showGridView.viewModeChanged(newView)
                        } else {
                            sortFilterOverlay.close()
                        }
                    }
                }
            }
        }
    }
}
