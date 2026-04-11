import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Steam game grid — shows a scrollable grid of game tiles for the selected source.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits gameSelected(index).
//   B (Escape) → emits back() so PcGamesScreen can return to the source list.
//   Y (2)      → opens the sort overlay panel.
FocusScope {
    id: steamGameGrid

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on a game cell.
    // index is the row in steam.gamesModel.
    signal gameSelected(int index)

    // Emitted when the user changes the view mode via the sort overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected source (set by PcGamesScreen).
    property string sourceName: ""

    // ── View mode (set by PcGamesScreen; "grid" or "list") ────────────────────
    property string _viewMode: "grid"

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: "az"

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")     return "A-Z"
        if (_currentSort === "za")     return "Z-A"
        if (_currentSort === "recent") return "Recent"
        return "A-Z"
    }

    // ── Header bar + status bar ───────────────────────────────────────────────
    LibraryHeader {
        id: header
        title: steamGameGrid.sourceName
        statusText: "Sorted: " + steamGameGrid._sortLabel
        rightText1: keys.useGamepadLabels ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
        rightText2: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "1  Favorite"
        rightText3: keys.useGamepadLabels ? keys.context2Label + "  Sort" : "2  Sort"
    }

    // ── Game grid ────────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h)
    readonly property int _targetCellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    GridView {
        id: gameGrid

        anchors {
            top: header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: steam ? steam.gamesModel : null
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(steamGameGrid._targetCellW + steamGameGrid._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(steamGameGrid._targetCellW + steamGameGrid._cellSpacing)
        cellHeight: root.vpx(steamGameGrid._cellH + steamGameGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortOverlay.open()
            } else if (keys.isContext1(event)) {
                event.accepted = true
                if (steam) steam.toggleFavorite(gameGrid.currentIndex)
            } else if (keys.isAccept(event)) {
                event.accepted = true
                steamGameGrid.gameSelected(gameGrid.currentIndex)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                steamGameGrid.back()
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                var mdl = steam ? steam.gamesModel : null
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, steamGameGrid._currentSort,
                    function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                )
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                var mdl2 = steam ? steam.gamesModel : null
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, steamGameGrid._currentSort,
                    function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                )
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: gameGrid.count === 0
            text: "No games found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Game tile delegate ───────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            width: gameGrid.cellWidth
            height: gameGrid.cellHeight

            z: tileRoot.GridView.isCurrentItem && gameGrid.activeFocus ? 1 : 0

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(steamGameGrid._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                scale: tileRoot.GridView.isCurrentItem && gameGrid.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                // Subtle highlight when focused
                GridCellHighlight {
                    active: tileRoot.GridView.isCurrentItem && gameGrid.activeFocus
                }

                // ── Poster image area ────────────────────────────────────────
                Item {
                    id: imageArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Image area takes ~80% of the card height (portrait poster)
                    height: Math.round(parent.height * 0.80)

                    // Text-only placeholder shown when imageLocal is empty or image not loaded
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.imageLocal === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.name
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            maximumLineCount: 4
                            elide: Text.ElideRight
                        }
                    }

                    Image {
                        id: posterImage

                        anchors.fill: parent
                        source: model.imageLocal
                            ? (model.imageLocal.startsWith("http") ? model.imageLocal : "file://" + model.imageLocal)
                            : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(steamGameGrid._targetCellW)
                        sourceSize.height: root.vpx(steamGameGrid._cellH)
                        visible: status === Image.Ready && model.imageLocal !== ""
                    }

                    // ── Favorite star indicator ──────────────────────────────
                    Text {
                        anchors {
                            top: parent.top
                            right: parent.right
                            topMargin: root.vpx(4)
                            rightMargin: root.vpx(4)
                        }
                        text: "★"
                        color: Theme.colorPrimary
                        font.pixelSize: root.vpx(14)
                        visible: model.favorite === true
                    }
                }

                // ── Game name label ──────────────────────────────────────────
                Text {
                    anchors {
                        top: imageArea.bottom
                        left: parent.left
                        right: parent.right
                        bottom: parent.bottom
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(4)
                        bottomMargin: root.vpx(4)
                    }
                    text: model.name
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: Text.AlignHCenter
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && gameGrid.activeFocus
                }
            }
        }
    }

    // ── Sort overlay ──────────────────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Navigation: Left/Right moves between sort options.
    //             A (Return) applies the selection.
    //             B (Escape) or Y dismisses without changing.
    FocusScope {
        id: sortOverlay

        anchors.fill: parent
        visible: false
        enabled: visible

        // Index within the sort options (0=A-Z, 1=Z-A, 2=Recent)
        property int _sortIndex: 0

        // Index within the view options (0=Grid, 1=List)
        property int _viewIndex: 0

        // Currently focused row: 0=sort row, 1=view row
        property int _focusRow: 0

        function open() {
            if (!steam) return
            // Sync selection indices to current state
            var sortKeys = ["az", "za", "recent"]
            var si = sortKeys.indexOf(steamGameGrid._currentSort)
            _sortIndex = si >= 0 ? si : 0
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(steamGameGrid._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
            _focusRow = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            gameGrid.forceActiveFocus()
        }

        // ── Backdrop ─────────────────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: Theme.colorImagePlaceholder
            opacity: 0.55
        }

        // ── Panel ─────────────────────────────────────────────────────────────
        Rectangle {
            id: overlayPanel

            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
            }
            height: root.vpx(190)
            color: Theme.colorSecondary
            opacity: 0.97

            // ── Panel title ──────────────────────────────────────────────────
            Text {
                id: panelTitle
                anchors {
                    top: parent.top
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(10)
                }
                text: "Sort"
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

            // ── Divider ──────────────────────────────────────────────────────
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

            // ── Sort options row ──────────────────────────────────────────────
            Row {
                id: sortOptionsRow
                anchors {
                    top: divider.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(10)
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { key: "az",     label: "A-Z" },
                        { key: "za",     label: "Z-A" },
                        { key: "recent", label: "Recent" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(80)
                        height: root.vpx(36)
                        color: {
                            var isFocused = sortOverlay._focusRow === 0 && sortOverlay._sortIndex === index
                            return isFocused ? Theme.colorPrimary : "transparent"
                        }
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(8)
                                verticalCenter: parent.verticalCenter
                            }
                            text: {
                                var isActive = modelData.key === steamGameGrid._currentSort
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortOverlay._focusRow === 0 && sortOverlay._sortIndex === index
                                return isFocused ? Theme.colorOverlayText : Theme.colorText
                            }
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }

            // ── View label ───────────────────────────────────────────────────
            Text {
                id: viewLabel
                anchors {
                    top: sortOptionsRow.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(6)
                }
                text: "View"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
            }

            // ── View options row ──────────────────────────────────────────────
            Row {
                id: viewOptionsRow
                anchors {
                    top: viewLabel.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(6)
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { key: "grid", label: "Grid" },
                        { key: "list", label: "List" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(80)
                        height: root.vpx(36)
                        color: {
                            var isFocused = sortOverlay._focusRow === 1 && sortOverlay._viewIndex === index
                            return isFocused ? Theme.colorPrimary : "transparent"
                        }
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(8)
                                verticalCenter: parent.verticalCenter
                            }
                            text: {
                                var isActive = modelData.key === steamGameGrid._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortOverlay._focusRow === 1 && sortOverlay._viewIndex === index
                                return isFocused ? Theme.colorOverlayText : Theme.colorText
                            }
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }
        }

        // ── Key handling ─────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            var sortCount = 3
            var viewCount = 2

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortOverlay.close()

            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (sortOverlay._focusRow > 0)
                    sortOverlay._focusRow -= 1

            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (sortOverlay._focusRow < 1)
                    sortOverlay._focusRow += 1

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortOverlay._focusRow === 0) {
                    if (sortOverlay._sortIndex > 0)
                        sortOverlay._sortIndex -= 1
                } else {
                    if (sortOverlay._viewIndex > 0)
                        sortOverlay._viewIndex -= 1
                }

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortOverlay._focusRow === 0) {
                    if (sortOverlay._sortIndex < sortCount - 1)
                        sortOverlay._sortIndex += 1
                } else {
                    if (sortOverlay._viewIndex < viewCount - 1)
                        sortOverlay._viewIndex += 1
                }

            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (!steam) return
                // Apply sort
                var sortKeys = ["az", "za", "recent"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                steamGameGrid._currentSort = newSort
                steam.sortGames(newSort)
                if (settings) settings.setSortSteamGames(newSort)
                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== steamGameGrid._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // PcGamesScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (settings) settings.setPcGamesViewMode(newView)
                    steamGameGrid.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortOverlay.close()
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) {
            var saved = settings.sortSteamGames
            if (saved) {
                _currentSort = saved
                if (steam) steam.sortGames(saved)
            }
        }
    }
}
