import QtQuick
import ".."
import "../components"

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

    // JS array model — set by PcGamesScreen when this source is selected.
    property var entries: []

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
            text: "◀  Recently Played"
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
    }

    // ── Game grid ────────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h) matching Steam/Moonlight
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

        model: recentlyPlayedGrid.entries
        clip: true
        focus: true

        cellWidth: root.vpx(recentlyPlayedGrid._cellW + recentlyPlayedGrid._cellSpacing)
        cellHeight: root.vpx(recentlyPlayedGrid._cellH + recentlyPlayedGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                recentlyPlayedGrid.gameSelected(gameGrid.currentIndex)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                recentlyPlayedGrid.back()
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
                        sourceSize.width: root.vpx(recentlyPlayedGrid._cellW)
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
                        color: modelData.source === "steam" ? "#1a9fff" : "#ff8c00"
                        opacity: 0.92

                        Text {
                            anchors.centerIn: parent
                            text: modelData.source === "steam" ? "S" : "M"
                            color: "#ffffff"
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
}
