import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Recently Played grid — shows a unified scrollable grid of recently played
// Steam and Moonlight titles, each with a small source badge.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view for the "recent" source.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits gameSelected(index).
//   B (Escape) → emits back() so PcGamesScreen can return to the source list.
//
// Model: JS array of dicts from steam.getRecentlyPlayed()
//   { name, source, imagePath, lastPlayed, appId, hostAddress }
FocusScope {
    id: recentlyPlayedGrid

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on a game cell.
    // index is the position in the JS array model.
    signal gameSelected(int index)

    // Emitted when the user changes the view mode via the view overlay.
    signal viewModeChanged(string mode)

    // JS array model — set by PcGamesScreen when this source is selected.
    property var entries: []

    // Display name shown in the header bar (e.g. "Recently Played" or "PC Favorites").
    property string sourceName: "Recently Played"

    // ── View mode (set by PcGamesScreen; "grid" or "list") ────────────────────
    property string _viewMode: "grid"

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
            text: "◀  " + recentlyPlayedGrid.sourceName
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
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

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "Sorted: Most Recent"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Row {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(16)

            Text {
                text: keys.useGamepadLabels ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context2Label + "  View" : "2  View"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Game grid ────────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h) matching Steam/Moonlight
    readonly property int _targetCellW: 160
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

        model: recentlyPlayedGrid.entries
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(recentlyPlayedGrid._targetCellW + recentlyPlayedGrid._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(recentlyPlayedGrid._targetCellW + recentlyPlayedGrid._cellSpacing)
        cellHeight: root.vpx(recentlyPlayedGrid._cellH + recentlyPlayedGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                viewOverlay.open()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                recentlyPlayedGrid.gameSelected(gameGrid.currentIndex)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                recentlyPlayedGrid.back()
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, null,
                    function(i) { return "" }, 1
                )
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                gameGrid.currentIndex = JumpHelper.jumpIndex(
                    gameGrid.count, gameGrid.currentIndex, null,
                    function(i) { return "" }, -1
                )
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: gameGrid.count === 0
            text: "No recently played games"
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
                    margins: root.vpx(recentlyPlayedGrid._cellSpacing / 2)
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

                    // Text-only placeholder shown when imagePath is empty or image not loaded
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || !modelData.imagePath

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: modelData.name || ""
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
                        source: modelData.imagePath
                            ? (modelData.imagePath.startsWith("http")
                                ? modelData.imagePath
                                : "file://" + modelData.imagePath)
                            : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(recentlyPlayedGrid._targetCellW)
                        sourceSize.height: root.vpx(recentlyPlayedGrid._cellH)
                        visible: status === Image.Ready && !!modelData.imagePath
                    }

                    // ── Source badge ─────────────────────────────────────────
                    // Small colored rectangle in the top-left corner of the image area.
                    // "S" = Steam (blue), "M" = Moonlight (orange)
                    Rectangle {
                        id: sourceBadge

                        anchors {
                            top: parent.top
                            left: parent.left
                            topMargin: root.vpx(4)
                            leftMargin: root.vpx(4)
                        }
                        width: root.vpx(20)
                        height: root.vpx(20)
                        radius: root.vpx(3)
                        color: modelData.source === "steam" ? Theme.colorBadgeSteam : Theme.colorBadgeMoonlight
                        opacity: 0.92

                        Text {
                            anchors.centerIn: parent
                            text: modelData.source === "steam" ? "S" : "M"
                            color: Theme.colorOverlayText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(11)
                            font.bold: true
                        }
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
                    text: modelData.name || ""
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

    // ── View overlay ──────────────────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Only has a View row (no sort — sorting is fixed to "Most Recent").
    // Navigation: Left/Right moves between view options.
    //             A (Return) applies the selection.
    //             B (Escape) or Y dismisses without changing.
    FocusScope {
        id: viewOverlay

        anchors.fill: parent
        visible: false
        enabled: visible

        // Index within the view options (0=Grid, 1=List)
        property int _viewIndex: 0

        function open() {
            // Sync selection index to current state
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(recentlyPlayedGrid._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
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
                text: "View"
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
                text: keys.useGamepadLabels
                      ? keys.cancelLabel + " / " + keys.context2Label + "  Close"
                      : "Esc / 2  Close"
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

            // ── View options row ──────────────────────────────────────────────
            Row {
                id: viewOptionsRow
                anchors {
                    top: divider.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(10)
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
                        color: viewOverlay._viewIndex === index
                               ? Theme.colorPrimary
                               : "transparent"
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
                                var isActive = modelData.key === recentlyPlayedGrid._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: viewOverlay._viewIndex === index
                                   ? Theme.colorOverlayText
                                   : Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }
        }

        // ── Key handling ─────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            var viewCount = 2

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                viewOverlay.close()

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (viewOverlay._viewIndex > 0)
                    viewOverlay._viewIndex -= 1

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (viewOverlay._viewIndex < viewCount - 1)
                    viewOverlay._viewIndex += 1

            } else if (keys.isAccept(event)) {
                event.accepted = true
                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[viewOverlay._viewIndex]
                if (newView !== recentlyPlayedGrid._viewMode) {
                    // View mode is changing — hide overlay and return focus to the grid
                    // so focus is not stranded when this component becomes invisible.
                    // PcGamesScreen.on_ViewModeChanged will re-route focus to the new view.
                    viewOverlay.visible = false
                    gameGrid.forceActiveFocus()
                    if (settings) settings.setPcGamesViewMode(newView)
                    recentlyPlayedGrid.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    viewOverlay.close()
                }
            }
        }
    }
}
