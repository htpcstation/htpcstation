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

    // Async metadata dict populated by steam.metadataChanged signal.
    property var _metadata: ({})

    // Emitted when the user presses B / Escape to return to the game grid.
    signal back()

    // Emitted when the user presses A / Return to launch the game.
    signal launch(string appId)

    // Emitted when the user presses Left/Right to navigate to prev/next game.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // ── Trigger metadata fetch when gameData changes ──────────────────────────
    onGameDataChanged: {
        steamGameDetail._metadata = ({})
        if (gameData.appId && steam) {
            steam.fetchMetadata(gameData.appId)
        }
    }

    // ── Listen for metadataChanged to refresh displayed data ──────────────────
    Connections {
        target: steam
        function onMetadataChanged(appId, metadata) {
            if (appId === steamGameDetail.gameData.appId) {
                steamGameDetail._metadata = metadata
            }
        }
    }

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
            var appId = steamGameDetail.gameData.appId || ""
            steamGameDetail.launch(appId)
        } else if (keys.isCancel(event)) {
            event.accepted = true
            steamGameDetail.back()
        } else if (keys.isContext1(event)) {
            event.accepted = true
            if (steam) steam.toggleFavorite(pcGamesScreen.selectedGameIndex)
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            steamGameDetail.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            steamGameDetail.navigateNext()
        }
    }

    // ── Listen for favoriteToggled to show toast ──────────────────────────────
    Connections {
        target: steam
        function onFavoriteToggled(isFavorite) {
            if (steamGameDetail.activeFocus || steamGameDetail.focus) {
                steamDetailToastText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
                steamDetailToast.opacity = 1.0
                steamDetailToastTimer.restart()
            }
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

    // ── Status bar (sub-header) ───────────────────────────────────────────────
    Rectangle {
        id: statusBar
        anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Row {
            anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            spacing: root.vpx(16)

            Text {
                text: keys.useGamepadLabels ? "[ ◀▶ ]  Prev/Next" : "[ ←→ ]  Prev/Next"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "1  Favorite"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Main content area ─────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
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

            // ── Favorite status label ─────────────────────────────────────────
            Text {
                id: favoriteLabel

                anchors {
                    top: gameNameLabel.bottom
                    left: parent.left
                    topMargin: root.vpx(6)
                }
                text: steamGameDetail.gameData.favorite ? "★ Favorited" : "☆ Add to Favorites"
                color: steamGameDetail.gameData.favorite ? Theme.colorPrimary : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
            }

            // ── Metadata fields ───────────────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: favoriteLabel.bottom
                    topMargin: root.vpx(10)
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(8)

                // ── Loading indicator ─────────────────────────────────────────
                Text {
                    visible: Object.keys(steamGameDetail._metadata).length === 0
                             && !(steamGameDetail.gameData.description)
                             && !(steamGameDetail.gameData.developer)
                             && !(steamGameDetail.gameData.publisher)
                             && !(steamGameDetail.gameData.genre)
                             && !(steamGameDetail.gameData.players)
                             && !(steamGameDetail.gameData.releaseDate)
                    text: "Loading..."
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.italic: true
                }

                Repeater {
                    model: [
                        {
                            label: "Developer",
                            value: steamGameDetail._metadata.developer
                                   || steamGameDetail.gameData.developer || ""
                        },
                        {
                            label: "Publisher",
                            value: steamGameDetail._metadata.publisher
                                   || steamGameDetail.gameData.publisher || ""
                        },
                        {
                            label: "Genre",
                            value: steamGameDetail._metadata.genre
                                   || steamGameDetail.gameData.genre || ""
                        },
                        {
                            label: "Players",
                            value: steamGameDetail._metadata.players
                                   || steamGameDetail.gameData.players || ""
                        },
                        {
                            label: "Released",
                            value: steamGameDetail._metadata.releaseDate
                                   || steamGameDetail.gameData.releaseDate || ""
                        },
                        {
                            label: "Rating",
                            value: steamGameDetail._formatRating(
                                       steamGameDetail._metadata.rating !== undefined
                                       ? steamGameDetail._metadata.rating
                                       : steamGameDetail.gameData.rating)
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

                // ── Separator ─────────────────────────────────────────────────
                Rectangle {
                    width: metadataColumn.width
                    height: root.vpx(1)
                    color: Theme.colorTextDim
                    opacity: 0.3
                }

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

            // ── Description ───────────────────────────────────────────────────
            Text {
                id: descriptionText

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(8)
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                text: steamGameDetail._metadata.description
                      || steamGameDetail.gameData.description || ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                wrapMode: Text.Wrap
                elide: Text.ElideRight
                clip: true
            }
        }
    }

    // ── Favorite toast notification ───────────────────────────────────────────
    // Shows "★ Added to Favorites" or "Removed from Favorites" for 2 seconds.
    // Does NOT take focus.
    Rectangle {
        id: steamDetailToast

        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(64)
        }
        width: steamDetailToastText.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        color: Theme.colorOverlay
        radius: root.vpx(8)
        opacity: 0.0
        visible: opacity > 0

        Text {
            id: steamDetailToastText
            anchors.centerIn: parent
            color: Theme.colorOverlayText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }

        Behavior on opacity {
            NumberAnimation { duration: 200 }
        }

        Timer {
            id: steamDetailToastTimer
            interval: 2000
            repeat: false
            onTriggered: steamDetailToast.opacity = 0.0
        }
    }
}
