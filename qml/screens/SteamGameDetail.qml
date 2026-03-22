import QtQuick
import ".."
import "../components"

// Steam game detail panel — shows metadata for a selected Steam game.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "detail" view.
//   A (Return)  → emit launch(appId)
//   B (Escape)  → emit back()
//   Left/Right  → emit navigatePrev() / navigateNext()
FocusScope {
    id: steamGameDetail

    // The dict returned by steam.getGame(index). Set by PcGamesScreen.
    property var gameData: ({})

    // Emitted when the user presses B / Escape to return to the game grid.
    signal back()

    // Emitted when the user presses A / Return to launch the game.
    signal launch(string appId)

    // Emitted when the user presses Left/Right to navigate to prev/next game.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // ── Helper: format size on disk ───────────────────────────────────────────
    // Input: bytes (int) → "X.X GB" or "X MB"
    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "Unknown"
        var gb = bytes / (1024 * 1024 * 1024)
        if (gb >= 1.0) {
            return gb.toFixed(1) + " GB"
        }
        var mb = bytes / (1024 * 1024)
        return Math.round(mb) + " MB"
    }

    // ── Helper: format last played timestamp ──────────────────────────────────
    // Input: Unix timestamp (int) → "YYYY-MM-DD" or "Never"
    function _formatLastPlayed(timestamp) {
        if (!timestamp || timestamp <= 0) return "Never"
        var d = new Date(timestamp * 1000)
        var year = d.getFullYear()
        var month = String(d.getMonth() + 1).padStart(2, "0")
        var day = String(d.getDate()).padStart(2, "0")
        return year + "-" + month + "-" + day
    }

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            var appId = steamGameDetail.gameData.appId || ""
            steamGameDetail.launch(appId)
        } else if (keys.isCancel(event)) {
            event.accepted = true
            steamGameDetail.back()
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            steamGameDetail.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            steamGameDetail.navigateNext()
        }
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
            text: "◀  " + (steamGameDetail.gameData.name || "")
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            elide: Text.ElideRight
            width: parent.width - root.vpx(32)
        }
    }

    // ── Main content area ─────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
            margins: root.vpx(24)
        }

        // ── Left column: poster image ─────────────────────────────────────────
        Item {
            id: posterArea

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            // Poster area takes ~30% of the content width (portrait aspect)
            width: Math.round(parent.width * 0.30)

            // Placeholder shown when there is no image or while loading
            Rectangle {
                anchors.fill: parent
                color: Qt.darker(Theme.colorSecondary, 1.4)
                radius: root.vpx(Theme.focusRingRadius)
                visible: posterImage.status !== Image.Ready
                         || !steamGameDetail.gameData.imagePath

                Text {
                    anchors.centerIn: parent
                    text: steamGameDetail.gameData.name || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width - root.vpx(16)
                }
            }

            Image {
                id: posterImage

                anchors.fill: parent
                source: steamGameDetail.gameData.imagePath
                        ? (steamGameDetail.gameData.imagePath.startsWith("http")
                            ? steamGameDetail.gameData.imagePath
                            : "file://" + steamGameDetail.gameData.imagePath)
                        : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: status === Image.Ready && !!steamGameDetail.gameData.imagePath
            }
        }

        // ── Right column: metadata ────────────────────────────────────────────
        Item {
            id: rightColumn

            anchors {
                top: parent.top
                left: posterArea.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(24)
            }

            // ── Game name (large) ─────────────────────────────────────────────
            Text {
                id: gameNameLabel

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                }
                text: steamGameDetail.gameData.name || ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeTitle)
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            // ── Metadata fields ───────────────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: gameNameLabel.bottom
                    topMargin: root.vpx(16)
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        {
                            label: "Install Dir",
                            value: steamGameDetail.gameData.installDir || ""
                        },
                        {
                            label: "Size",
                            value: steamGameDetail._formatSize(steamGameDetail.gameData.sizeOnDisk)
                        },
                        {
                            label: "Last Played",
                            value: steamGameDetail._formatLastPlayed(steamGameDetail.gameData.lastPlayed)
                        },
                    ]

                    Row {
                        spacing: root.vpx(8)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(100)
                        }

                        Text {
                            text: modelData.value
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }
        }
    }

    // ── Action hints bar ──────────────────────────────────────────────────────
    Rectangle {
        id: actionBar

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        height: root.vpx(48)
        color: Theme.colorSecondary

        Text {
            anchors.centerIn: parent
            text: keys.useGamepadLabels
                  ? "[◀▶] Prev/Next    [A] Launch    [B] Back"
                  : "[←→] Prev/Next    [Enter] Launch    [Esc] Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
