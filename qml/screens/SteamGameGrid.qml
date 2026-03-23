import QtQuick
import ".."
import "../components"

// Steam game grid — shows a scrollable grid of game tiles for the selected source.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits gameSelected(index).
//   B (Escape) → emits back() so PcGamesScreen can return to the source list.
//   Y (F2)     → opens the sort overlay panel.
FocusScope {
    id: steamGameGrid

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on a game cell.
    // index is the row in steam.gamesModel.
    signal gameSelected(int index)

    // Display name of the currently selected source (set by PcGamesScreen).
    property string sourceName: ""

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: "az"

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")     return "A-Z"
        if (_currentSort === "za")     return "Z-A"
        if (_currentSort === "recent") return "Recent"
        return "A-Z"
    }

    // ── Header bar ───────────────────────────────────────────────────────────
    Rectangle {
        id: headerBar

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "◀  " + steamGameGrid.sourceName
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // Y button hint
        Text {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.context2Label + "  Sort" : "F2  Sort"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Sort status bar ───────────────────────────────────────────────────────
    Rectangle {
        id: statusBar

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)
        visible: true

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "Sorted: " + steamGameGrid._sortLabel
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Game grid ────────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h)
    readonly property int _cellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    GridView {
        id: gameGrid

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: steam ? steam.gamesModel : null
        clip: true
        focus: true

        cellWidth: root.vpx(steamGameGrid._cellW + steamGameGrid._cellSpacing)
        cellHeight: root.vpx(steamGameGrid._cellH + steamGameGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortOverlay.open()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                steamGameGrid.gameSelected(gameGrid.currentIndex)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                steamGameGrid.back()
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

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(steamGameGrid._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && gameGrid.activeFocus ? 0.15 : 0.0

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
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
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(steamGameGrid._cellW)
                        sourceSize.height: root.vpx(steamGameGrid._cellH)
                        visible: status === Image.Ready && model.imageLocal !== ""
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

        function open() {
            if (!steam) return
            // Sync selection index to current state
            var sortKeys = ["az", "za", "recent"]
            var si = sortKeys.indexOf(steamGameGrid._currentSort)
            _sortIndex = si >= 0 ? si : 0
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
            color: "#000000"
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
            height: root.vpx(130)
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
                text: keys.useGamepadLabels ? keys.cancelLabel + " / " + keys.context2Label + "  Close" : "Esc / F2  Close"
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
                            var isFocused = sortOverlay._sortIndex === index
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
                                var isFocused = sortOverlay._sortIndex === index
                                return isFocused ? "#ffffff" : Theme.colorText
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

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortOverlay.close()

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortOverlay._sortIndex > 0)
                    sortOverlay._sortIndex -= 1

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortOverlay._sortIndex < sortCount - 1)
                    sortOverlay._sortIndex += 1

            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (!steam) return
                var sortKeys = ["az", "za", "recent"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                steamGameGrid._currentSort = newSort
                steam.sortGames(newSort)
                sortOverlay.close()
            }
        }
    }
}
