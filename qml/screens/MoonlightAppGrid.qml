import QtQuick
import ".."
import "../components"

// Moonlight app grid — shows a scrollable grid of app tiles for the selected Moonlight host.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view for a Moonlight source.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits appSelected(index).
//   B (Escape) → emits back() so PcGamesScreen can return to the source list.
//   Y (F2)     → opens the sort overlay panel.
FocusScope {
    id: moonlightAppGrid

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on an app cell.
    // index is the row in moonlight.appsModel.
    signal appSelected(int index)

    // Display name of the currently selected source (set by PcGamesScreen).
    property string sourceName: ""

    // Whether the Moonlight host is offline (set by PcGamesScreen).
    // When true, the empty state shows "Host unavailable" instead of "No apps found".
    property bool hostOffline: false

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: "az"

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az") return "A-Z"
        if (_currentSort === "za") return "Z-A"
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
            text: "◀  " + moonlightAppGrid.sourceName
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
            text: "Sorted: " + moonlightAppGrid._sortLabel
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── App grid ─────────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h) matching Steam card size
    readonly property int _targetCellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    GridView {
        id: appGrid

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: moonlight ? moonlight.appsModel : null
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(moonlightAppGrid._targetCellW + moonlightAppGrid._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(moonlightAppGrid._targetCellW + moonlightAppGrid._cellSpacing)
        cellHeight: root.vpx(moonlightAppGrid._cellH + moonlightAppGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortOverlay.open()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                moonlightAppGrid.appSelected(appGrid.currentIndex)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                moonlightAppGrid.back()
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: appGrid.count === 0
            text: moonlightAppGrid.hostOffline
                  ? "Host unavailable — check that your streaming PC is powered on"
                  : "No apps found"
            color: moonlightAppGrid.hostOffline ? Theme.colorPrimary : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            width: parent.width - root.vpx(64)
        }

        // ── App tile delegate ────────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            width: appGrid.cellWidth
            height: appGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(moonlightAppGrid._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && appGrid.activeFocus ? 0.15 : 0.0

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

                    // Text-only placeholder shown when imagePath is empty or image not loaded
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.imagePath === ""

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
                        source: model.imagePath
                            ? (model.imagePath.startsWith("http") ? model.imagePath : "file://" + model.imagePath)
                            : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(moonlightAppGrid._targetCellW)
                        sourceSize.height: root.vpx(moonlightAppGrid._cellH)
                        visible: status === Image.Ready && model.imagePath !== ""
                    }
                }

                // ── App name label ───────────────────────────────────────────
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
                    visible: tileRoot.GridView.isCurrentItem && appGrid.activeFocus
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

        // Index within the sort options (0=A-Z, 1=Z-A)
        property int _sortIndex: 0

        function open() {
            if (!moonlight) return
            // Sync selection index to current state
            var sortKeys = ["az", "za"]
            var si = sortKeys.indexOf(moonlightAppGrid._currentSort)
            _sortIndex = si >= 0 ? si : 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            appGrid.forceActiveFocus()
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
                        { key: "az", label: "A-Z" },
                        { key: "za", label: "Z-A" }
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
                                var isActive = modelData.key === moonlightAppGrid._currentSort
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
            var sortCount = 2

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
                if (!moonlight) return
                var sortKeys = ["az", "za"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                moonlightAppGrid._currentSort = newSort
                moonlight.sortApps(newSort)
                sortOverlay.close()
            }
        }
    }
}
