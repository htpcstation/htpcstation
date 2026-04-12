import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper
import HTPCBackend 1.0

// Game grid view — shows a scrollable grid of game tiles for the selected system.
//
// Focus flow:
//   Gains focus when RetroGamesScreen switches to "games" view.
//   Arrow Keys navigate the grid natively.
//   A (Return) on a cell → emits gameSelected(index) (task 009 will connect to it).
//   B (Escape) → emits back() so RetroGamesScreen can return to the system list.
//   Y (2)      → opens the sort overlay panel.
FocusScope {
    id: gameGridView

    // Emitted when the user presses B / Escape to return to the system list.
    signal back()

    // Emitted when the user presses A / Return on a game cell.
    // index is the row in library.gamesModel.
    signal gameSelected(int index)

    // Emitted when the user changes the view mode via the sort overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected system (set by RetroGamesScreen).
    property string systemName: ""

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: "az"

    // ── View mode (set by RetroGamesScreen; "grid" or "list") ─────────────────
    property string _viewMode: "grid"

    // ── Favorites on top ──────────────────────────────────────────────────────
    property bool _favoritesOnTop: true

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
        title: gameGridView.systemName
        statusText: "Sorted: " + gameGridView._sortLabel
        rightText1: KeyHandler.useGamepadLabels ? KeyHandler.pageUpLabel + "/" + KeyHandler.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
        rightText2: KeyHandler.useGamepadLabels ? KeyHandler.context1Label + "  Favorite" : "1  Favorite"
        rightText3: KeyHandler.useGamepadLabels ? KeyHandler.context2Label + "  Sort" : "2  Sort"
    }

    // ── Game grid ────────────────────────────────────────────────────────────
    // Target cell dimensions (design-grid px, scaled via vpx).
    // Actual cellWidth is computed dynamically to fill the grid evenly.
    readonly property int _targetCellW: 200
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

        model: library ? library.gamesModel : null
        clip: true
        focus: true

        // Compute columns from available width and target cell size, then
        // distribute the full width evenly so there is no dead space.
        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(gameGridView._targetCellW + gameGridView._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(gameGridView._targetCellW + gameGridView._cellSpacing)
        cellHeight: root.vpx(gameGridView._cellH + gameGridView._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        Keys.onPressed: (event) => {
            if (KeyHandler.isContext2(event)) {
                event.accepted = true
                sortOverlay.open()
            } else if (KeyHandler.isContext1(event)) {
                event.accepted = true
                if (library) library.toggleFavorite(gameGrid.currentIndex)
            } else if (KeyHandler.isAccept(event)) {
                event.accepted = true
                gameGridView.gameSelected(gameGrid.currentIndex)
            } else if (KeyHandler.isCancel(event)) {
                event.accepted = true
                gameGridView.back()
            } else if (KeyHandler.isPageDown(event)) {
                event.accepted = true
                var mdl = library ? library.gamesModel : null
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, gameGridView._currentSort,
                    function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                )
            } else if (KeyHandler.isPageUp(event)) {
                event.accepted = true
                var mdl2 = library ? library.gamesModel : null
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, gameGridView._currentSort,
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
                    margins: root.vpx(gameGridView._cellSpacing / 2)
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

                // ── Screenshot image ─────────────────────────────────────────
                Item {
                    id: imageArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Image area takes ~75% of the card height
                    height: Math.round(parent.height * 0.75)

                    // Placeholder shown when there is no image or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: gameImage.status !== Image.Ready || model.imagePath === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.name
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
                        id: gameImage

                        anchors.fill: parent
                        source: model.imagePath
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(gameGridView._targetCellW)
                        sourceSize.height: Math.round(root.vpx(gameGridView._cellH) * 0.75)
                        visible: status === Image.Ready && model.imagePath !== ""
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
    // Navigation: Up/Down switches between sort row and view row.
    //             Left/Right moves between options in the focused row.
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

        // Index within the favorites-on-top options (0=On, 1=Off)
        property int _favOnTopIndex: 0

        // Currently focused row: 0=sort row, 1=view row, 2=favorites row
        property int _focusRow: 0

        function open() {
            // Sync selection indices to current state
            var sortKeys = ["az", "za", "recent"]
            var si = sortKeys.indexOf(gameGridView._currentSort)
            _sortIndex = si >= 0 ? si : 0
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(gameGridView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
            _favOnTopIndex = gameGridView._favoritesOnTop ? 0 : 1
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
            height: root.vpx(250)
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
                text: KeyHandler.useGamepadLabels ? KeyHandler.cancelLabel + " / " + KeyHandler.context2Label + "  Close" : "Esc / 2  Close"
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
                                var isActive = modelData.key === gameGridView._currentSort
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
                                var isActive = modelData.key === gameGridView._viewMode
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

            // ── Favorites label ───────────────────────────────────────────────
            Text {
                id: favoritesLabel
                anchors {
                    top: viewOptionsRow.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(6)
                }
                text: "Favorites on top"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
            }

            // ── Favorites options row ─────────────────────────────────────────
            Row {
                id: favoritesOptionsRow
                anchors {
                    top: favoritesLabel.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(6)
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { key: "on",  label: "On" },
                        { key: "off", label: "Off" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(80)
                        height: root.vpx(36)
                        color: {
                            var isFocused = sortOverlay._focusRow === 2 && sortOverlay._favOnTopIndex === index
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
                                var isActive = modelData.key === (gameGridView._favoritesOnTop ? "on" : "off")
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortOverlay._focusRow === 2 && sortOverlay._favOnTopIndex === index
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

            if (KeyHandler.isCancel(event) || KeyHandler.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortOverlay.close()

            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (sortOverlay._focusRow > 0)
                    sortOverlay._focusRow -= 1

            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (sortOverlay._focusRow < 2)
                    sortOverlay._focusRow += 1

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortOverlay._focusRow === 0) {
                    if (sortOverlay._sortIndex > 0)
                        sortOverlay._sortIndex -= 1
                } else if (sortOverlay._focusRow === 1) {
                    if (sortOverlay._viewIndex > 0)
                        sortOverlay._viewIndex -= 1
                } else {
                    if (sortOverlay._favOnTopIndex > 0)
                        sortOverlay._favOnTopIndex -= 1
                }

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortOverlay._focusRow === 0) {
                    if (sortOverlay._sortIndex < sortCount - 1)
                        sortOverlay._sortIndex += 1
                } else if (sortOverlay._focusRow === 1) {
                    if (sortOverlay._viewIndex < viewCount - 1)
                        sortOverlay._viewIndex += 1
                } else {
                    if (sortOverlay._favOnTopIndex < 1)
                        sortOverlay._favOnTopIndex += 1
                }

            } else if (KeyHandler.isAccept(event)) {
                event.accepted = true
                // Apply sort
                var sortKeys = ["az", "za", "recent"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                gameGridView._currentSort = newSort
                library.sortGames(newSort)
                if (Settings) Settings.setSortRetroGames(newSort)
                // Apply favorites on top
                var newFavOnTop = sortOverlay._favOnTopIndex === 0
                gameGridView._favoritesOnTop = newFavOnTop
                library.setFavoritesOnTop(newFavOnTop)
                if (Settings) Settings.setRetroGamesFavoritesOnTop(newFavOnTop)
                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== gameGridView._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // RetroGamesScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (Settings) Settings.setRetroGamesViewMode(newView)
                    gameGridView.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortOverlay.close()
                }
            }
        }
    }

    // Restore focus to the game's new position after a favorite toggle re-sorts the list.
    // highlightMoveDuration is zeroed so the view snaps without a visible scroll animation.
    Connections {
        target: library
        function onFavoriteSorted(newIndex) {
            gameGrid.highlightMoveDuration = 0
            gameGrid.currentIndex = newIndex
            Qt.callLater(function() { gameGrid.highlightMoveDuration = Theme.animDurationFast })
        }
    }

    Component.onCompleted: {
        if (Settings) {
            var saved = Settings.sortRetroGames
            if (saved) {
                _currentSort = saved
                library.sortGames(saved)
            }
            // _viewMode is bound from RetroGamesScreen; do not overwrite here.
            _favoritesOnTop = Settings.retroGamesFavoritesOnTop
            library.setFavoritesOnTop(_favoritesOnTop)
        }
    }
}
