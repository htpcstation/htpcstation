import QtQuick
import QtMultimedia
import ".."
import "../components"

// Game detail panel — shows full metadata for a selected game.
//
// Focus flow:
//   Gains focus when RetroGamesScreen switches to "detail" view.
//   A (Return)  → emit launch()
//   X (1)       → emit toggleFavorite()
//   B (Escape)  → emit back()
//   Up/Down     → scroll description if it overflows
FocusScope {
    id: gameDetailView

    // The dict returned by library.getGame(index). Set by RetroGamesScreen.
    property var gameData: ({})

    // Emitted when the user presses B / Escape to return to the game grid.
    signal back()

    // Emitted when the user presses A / Return to launch the game.
    signal launch()

    // Emitted when the user presses X / 1 to toggle the favorite flag.
    signal toggleFavorite()

    // Emitted when the user presses Left/Right to navigate to prev/next game.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // ── Video playback lifecycle ──────────────────────────────────────────────
    // Start/stop video when gameData changes or the view is shown/hidden.
    onGameDataChanged: {
        mediaPlayer.stop()
        if (gameDetailView.gameData.videoPath && settings.videoSnapAutoplay) {
            // Small delay to let source load before playing
            playTimer.restart()
        }
    }

    onVisibleChanged: {
        if (!visible) {
            mediaPlayer.stop()
        } else if (gameDetailView.gameData.videoPath && settings.videoSnapAutoplay) {
            playTimer.restart()
        }
    }

    // Delay play() slightly so the source has time to load
    Timer {
        id: playTimer
        interval: settings ? settings.videoSnapDelayMs : 1000
        repeat: false
        onTriggered: mediaPlayer.play()
    }

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            gameDetailView.launch()
        } else if (keys.isCancel(event)) {
            event.accepted = true
            gameDetailView.back()
        } else if (keys.isContext1(event)) {
            // X button (context1 / 1)
            event.accepted = true
            gameDetailView.toggleFavorite()
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            gameDetailView.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            gameDetailView.navigateNext()
        } else if (event.key === Qt.Key_Up) {
            event.accepted = true
            descriptionFlickable.contentY = Math.max(
                0,
                descriptionFlickable.contentY - root.vpx(40)
            )
        } else if (event.key === Qt.Key_Down) {
            event.accepted = true
            var maxY = Math.max(0, descriptionFlickable.contentHeight - descriptionFlickable.height)
            descriptionFlickable.contentY = Math.min(maxY, descriptionFlickable.contentY + root.vpx(40))
        }
    }

    // ── Helper: format release date ───────────────────────────────────────────
    // Input: "19990527T000000" → output: "1999" (year only for v1)
    function _formatYear(raw) {
        if (!raw || raw.length < 4) return ""
        return raw.substring(0, 4)
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
            text: "◀  " + (gameDetailView.gameData.name || "")
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

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Row {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
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

        // ── Left column: video snap or screenshot ─────────────────────────────
        Item {
            id: screenshotArea

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            // Media area takes ~40% of the content width
            width: Math.round(parent.width * 0.40)

            // Placeholder shown when there is no image/video or while loading
            Rectangle {
                anchors.fill: parent
                color: Qt.darker(Theme.colorSecondary, 1.4)
                radius: root.vpx(Theme.focusRingRadius)
                visible: mediaPlayer.playbackState !== MediaPlayer.PlayingState
                         && (screenshotImage.status !== Image.Ready || !gameDetailView.gameData.imagePath)

                Text {
                    anchors.centerIn: parent
                    text: gameDetailView.gameData.name || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width - root.vpx(16)
                }
            }

            // MediaPlayer drives the video — no visual output itself
            MediaPlayer {
                id: mediaPlayer
                source: gameDetailView.gameData.videoPath || ""
                videoOutput: videoOutput
                audioOutput: AudioOutput { volume: 0 }
                loops: MediaPlayer.Infinite
            }

            // VideoOutput renders the decoded frames
            VideoOutput {
                id: videoOutput
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
                visible: mediaPlayer.playbackState === MediaPlayer.PlayingState
            }

            // Screenshot fallback — shown when no video is playing
            Image {
                id: screenshotImage

                anchors.fill: parent
                source: gameDetailView.gameData.imagePath || ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: true
                visible: mediaPlayer.playbackState !== MediaPlayer.PlayingState
                         && status === Image.Ready && !!gameDetailView.gameData.imagePath
            }
        }

        // ── Right column: metadata + description ──────────────────────────────
        Item {
            id: rightColumn

            anchors {
                top: parent.top
                left: screenshotArea.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(24)
            }

            // ── Metadata fields (anchored to top) ─────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { label: "Developer", value: gameDetailView.gameData.developer || "" },
                        { label: "Publisher", value: gameDetailView.gameData.publisher || "" },
                        { label: "Genre",     value: gameDetailView.gameData.genre || "" },
                        { label: "Players",   value: gameDetailView.gameData.players || "" },
                        { label: "Released",  value: gameDetailView._formatYear(gameDetailView.gameData.releaseDate) },
                        { label: "Rating",    value: gameDetailView._formatRating(gameDetailView.gameData.rating) },
                    ]

                    Row {
                        spacing: root.vpx(8)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(90)
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
            }

            // ── Description (scrollable) — fills remaining space ──────────────
            Flickable {
                id: descriptionFlickable

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(8)
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                clip: true
                contentWidth: width
                contentHeight: descriptionText.implicitHeight
                interactive: false  // D-pad scrolls via Keys.onPressed above

                Text {
                    id: descriptionText

                    width: descriptionFlickable.width
                    text: gameDetailView.gameData.description || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                }
            }
        }
    }

    // ── Favorite toast notification ───────────────────────────────────────────
    // Shows "★ Added to Favorites" or "Removed from Favorites" for 2 seconds.
    // Does NOT take focus.
    Rectangle {
        id: favoriteToast

        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(64)
        }
        width: toastText.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        color: Theme.colorOverlay
        radius: root.vpx(8)
        opacity: 0.0
        visible: opacity > 0

        Text {
            id: toastText
            anchors.centerIn: parent
            color: Theme.colorOverlayText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }

        Behavior on opacity {
            NumberAnimation { duration: 200 }
        }

        Timer {
            id: toastTimer
            interval: 2000
            repeat: false
            onTriggered: favoriteToast.opacity = 0.0
        }
    }

    // Public function called by RetroGamesScreen when library.favoriteToggled fires.
    function showFavoriteToast(isFavorite) {
        toastText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
        favoriteToast.opacity = 1.0
        toastTimer.restart()
    }
}
