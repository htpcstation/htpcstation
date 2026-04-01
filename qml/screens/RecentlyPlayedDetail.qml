import QtQuick
import ".."
import "../components"

// Recently Played detail panel — simplified detail view for a recently played game.
//
// Shows: game name, source badge, poster image, and a launch button.
// For Steam entries, also shows rich metadata (developer, publisher, genre, etc.)
// fetched asynchronously via the Steam metadata pipeline.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "detail" view for the "recent" source.
//   A (Return)  → emit launch(source, appId, hostAddress, name)
//   B (Escape)  → emit back()
//   Left/Right  → emit navigatePrev() / navigateNext()
FocusScope {
    id: recentlyPlayedDetail

    // The dict from the recently played entries array.
    // Keys: name, source, imagePath, lastPlayed, appId, hostAddress
    property var gameData: ({})

    // Async metadata dict populated by steam.metadataChanged signal (Steam only).
    property var _metadata: ({})

    // Emitted when the user presses B / Escape to return to the grid.
    signal back()

    // Emitted when the user presses A / Return to launch the game.
    signal launch(string source, string appId, string hostAddress, string appName)

    // Emitted when the user presses Left/Right to navigate to prev/next game.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // ── Trigger metadata fetch when gameData changes ──────────────────────────
    onGameDataChanged: {
        recentlyPlayedDetail._metadata = ({})
        if (gameData.source === "steam" && gameData.appId && steam) {
            steam.fetchMetadata(gameData.appId)
        }
    }

    // ── Listen for metadataChanged to refresh displayed data ──────────────────
    Connections {
        target: steam
        function onMetadataChanged(appId, metadata) {
            if (appId === recentlyPlayedDetail.gameData.appId) {
                recentlyPlayedDetail._metadata = metadata
            }
        }
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

    // ── Helper: format rating as stars ────────────────────────────────────────
    // Input: float 0.0–1.0 → "★★★★☆" (5-star scale)
    // Returns "" for unrated games (rating <= 0) so the row is hidden.
    function _formatRating(rating) {
        if (rating === undefined || rating === null || rating === "") return ""
        if (rating <= 0) return ""
        var stars = Math.round(rating * 5)
        var filled = ""
        var empty = ""
        for (var i = 0; i < 5; i++) {
            if (i < stars) filled += "★"
            else empty += "☆"
        }
        return filled + empty
    }

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            var data = recentlyPlayedDetail.gameData
            recentlyPlayedDetail.launch(
                data.source || "",
                data.appId || "",
                data.hostAddress || "",
                data.name || ""
            )
        } else if (keys.isCancel(event)) {
            event.accepted = true
            recentlyPlayedDetail.back()
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            recentlyPlayedDetail.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            recentlyPlayedDetail.navigateNext()
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
            text: "◀  " + (recentlyPlayedDetail.gameData.name || "")
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
                         || !recentlyPlayedDetail.gameData.imagePath

                Text {
                    anchors.centerIn: parent
                    text: recentlyPlayedDetail.gameData.name || ""
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
                source: recentlyPlayedDetail.gameData.imagePath
                        ? (recentlyPlayedDetail.gameData.imagePath.startsWith("http")
                            ? recentlyPlayedDetail.gameData.imagePath
                            : "file://" + recentlyPlayedDetail.gameData.imagePath)
                        : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: status === Image.Ready && !!recentlyPlayedDetail.gameData.imagePath
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
                text: recentlyPlayedDetail.gameData.name || ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeTitle)
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            // ── Source badge ──────────────────────────────────────────────────
            Row {
                id: sourceBadgeRow

                anchors {
                    top: gameNameLabel.bottom
                    left: parent.left
                    topMargin: root.vpx(12)
                }
                spacing: root.vpx(8)

                Rectangle {
                    width: root.vpx(28)
                    height: root.vpx(28)
                    radius: root.vpx(4)
                    color: recentlyPlayedDetail.gameData.source === "steam"
                           ? "#1a9fff"
                           : "#ff8c00"

                    Text {
                        anchors.centerIn: parent
                        text: recentlyPlayedDetail.gameData.source === "steam" ? "S" : "M"
                        color: "#ffffff"
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(14)
                        font.bold: true
                    }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: recentlyPlayedDetail.gameData.source === "steam"
                          ? "Steam"
                          : "Moonlight"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                }
            }

            // ── Metadata fields ───────────────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: sourceBadgeRow.bottom
                    topMargin: root.vpx(16)
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(8)

                // ── Loading indicator (Steam only) ────────────────────────────
                Text {
                    visible: recentlyPlayedDetail.gameData.source === "steam"
                             && Object.keys(recentlyPlayedDetail._metadata).length === 0
                    text: "Loading..."
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.italic: true
                }

                // ── Rich metadata rows (Steam only) ───────────────────────────
                Repeater {
                    model: recentlyPlayedDetail.gameData.source === "steam"
                           ? [
                               {
                                   label: "Developer",
                                   value: recentlyPlayedDetail._metadata.developer || ""
                               },
                               {
                                   label: "Publisher",
                                   value: recentlyPlayedDetail._metadata.publisher || ""
                               },
                               {
                                   label: "Genre",
                                   value: recentlyPlayedDetail._metadata.genre || ""
                               },
                               {
                                   label: "Players",
                                   value: recentlyPlayedDetail._metadata.players || ""
                               },
                               {
                                   label: "Released",
                                   value: recentlyPlayedDetail._metadata.releaseDate || ""
                               },
                               {
                                   label: "Rating",
                                   value: recentlyPlayedDetail._formatRating(
                                              recentlyPlayedDetail._metadata.rating)
                               },
                           ]
                           : []

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

                Row {
                    spacing: root.vpx(8)

                    Text {
                        text: "Last Played:"
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(100)
                    }

                    Text {
                        text: recentlyPlayedDetail._formatLastPlayed(
                            recentlyPlayedDetail.gameData.lastPlayed
                        )
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                    }
                }
            }

            // ── Description (Steam only) ──────────────────────────────────────
            Text {
                id: descriptionText

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(8)
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                text: recentlyPlayedDetail._metadata.description || ""
                visible: (recentlyPlayedDetail._metadata.description || "") !== ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                wrapMode: Text.Wrap
                clip: true
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
                  ? "[◀▶] Prev/Next    [" + keys.acceptLabel + "] Launch    [" + keys.cancelLabel + "] Back"
                  : "[←→] Prev/Next    [Enter] Launch    [Esc] Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
