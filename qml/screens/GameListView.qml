import QtQuick
import QtMultimedia
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper
import HTPCBackend 1.0

// Game list view — split-panel browse view for retro games.
//
// Focus flow:
//   Gains focus when RetroGamesScreen switches to "games" view (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits gameSelected(index)
//   B (Escape)  → emits back()
//   Y (2)       → opens the sort overlay panel
//   X (1)       → toggles favorite on the current game
FocusScope {
    id: gameListView

    // Emitted when the user presses B / Escape to return to the system list.
    signal back()

    // Emitted when the user presses A / Return on a game row.
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

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")     return "A-Z"
        if (_currentSort === "za")     return "Z-A"
        if (_currentSort === "recent") return "Recent"
        return "A-Z"
    }

    // ── Preview data for the left panel ──────────────────────────────────────
    // Cached game dict for the currently highlighted item.
    property var _previewData: ({})

    // Update preview data when the current index changes.
    // Guard against -1 and empty model.
    function _updatePreview(index) {
        if (!library || !library.gamesModel) {
            _previewData = {}
            return
        }
        if (index < 0 || index >= gameList.count) {
            _previewData = {}
            return
        }
        _previewData = library.getGame(index)
    }

    // ── Helper: format release date ───────────────────────────────────────────
    // Input: "19990527T000000" → output: "1999" (year only)
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

    // ── Video playback lifecycle ──────────────────────────────────────────────
    // Delay play() slightly so the source has time to load.
    Timer {
        id: playTimer
        interval: Settings ? Settings.videoSnapDelayMs : 1000
        repeat: false
        onTriggered: mediaPlayer.play()
    }

    // Stop video when the view is hidden to avoid background audio/CPU.
    onVisibleChanged: {
        if (!visible) {
            mediaPlayer.stop()
            playTimer.stop()
        } else {
            // Re-trigger preview for the current item when view becomes visible.
            _updatePreview(gameList.currentIndex)
            if (_previewData.videoPath && Settings && Settings.videoSnapAutoplay) {
                playTimer.restart()
            }
        }
    }

    // ── Header bar + status bar ───────────────────────────────────────────────
    LibraryHeader {
        id: header
        title: gameListView.systemName
        statusText: "Sorted: " + gameListView._sortLabel
        rightText1: KeyHandler.useGamepadLabels ? KeyHandler.pageUpLabel + "/" + KeyHandler.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
        rightText2: KeyHandler.useGamepadLabels ? KeyHandler.context1Label + "  Favorite" : "1  Favorite"
        rightText3: KeyHandler.useGamepadLabels ? KeyHandler.context2Label + "  Sort" : "2  Sort"
    }

    // ── Split content area ────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        // ── Left panel: preview area (40% width) ──────────────────────────────
        Item {
            id: leftPanel

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            width: Math.round(parent.width * 0.45)

            // ── Media area ────────────────────────────────────────────────────
            Item {
                id: mediaArea

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(16)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                // Media area takes ~55% of the left panel height
                height: Math.round(parent.height * 0.55)

                // Placeholder shown when there is no image/video or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: mediaPlayer.playbackState !== MediaPlayer.PlayingState
                             && (previewImage.status !== Image.Ready || !gameListView._previewData.imagePath)

                    Text {
                        anchors.centerIn: parent
                        text: gameListView._previewData.name || ""
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
                    source: gameListView._previewData.videoPath || ""
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
                    id: previewImage

                    anchors.fill: parent
                    source: gameListView._previewData.imagePath || ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.65)
                    visible: mediaPlayer.playbackState !== MediaPlayer.PlayingState
                             && status === Image.Ready && !!gameListView._previewData.imagePath
                }
            }

            // ── Compact metadata column ───────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: mediaArea.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(8)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                spacing: root.vpx(4)

                Repeater {
                    model: [
                        { label: "Genre",    value: gameListView._previewData.genre || "" },
                        { label: "Players",  value: gameListView._previewData.players || "" },
                        { label: "Rating",   value: gameListView._formatRating(gameListView._previewData.rating) },
                        { label: "Released", value: gameListView._formatYear(gameListView._previewData.releaseDate) }
                    ]

                    Row {
                        spacing: root.vpx(6)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            width: root.vpx(60)
                        }

                        Text {
                            text: modelData.value
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        }
                    }
                }
            }

            // ── Description (scrollable) ──────────────────────────────────────
            Flickable {
                id: descriptionFlickable

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(8)
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                    bottomMargin: root.vpx(8)
                }
                clip: true
                contentWidth: width
                contentHeight: descriptionText.implicitHeight
                interactive: false  // scrolling not needed — preview only

                Text {
                    id: descriptionText

                    width: descriptionFlickable.width
                    text: gameListView._previewData.description || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.Wrap
                }
            }
        }

        // ── Right panel: game list (60% width) ────────────────────────────────
        ListView {
            id: gameList

            anchors {
                top: parent.top
                left: leftPanel.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(64)
                rightMargin: root.vpx(16)
            }

            model: library ? library.gamesModel : null
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            // Update preview data when the current index changes.
            onCurrentIndexChanged: {
                mediaPlayer.stop()
                playTimer.stop()
                gameListView._updatePreview(currentIndex)
                if (gameListView._previewData.videoPath && Settings && Settings.videoSnapAutoplay) {
                    playTimer.restart()
                }
            }

            Keys.onPressed: (event) => {
                if (KeyHandler.isAccept(event)) {
                    event.accepted = true
                    gameListView.gameSelected(gameList.currentIndex)
                } else if (KeyHandler.isCancel(event)) {
                    event.accepted = true
                    gameListView.back()
                } else if (KeyHandler.isContext2(event)) {
                    event.accepted = true
                    sortOverlay.open()
                } else if (KeyHandler.isContext1(event)) {
                    event.accepted = true
                    if (library) library.toggleFavorite(gameList.currentIndex)
                } else if (KeyHandler.isPageDown(event)) {
                    event.accepted = true
                    var mdl = library ? library.gamesModel : null
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, gameListView._currentSort,
                        function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                    )
                } else if (KeyHandler.isPageUp(event)) {
                    event.accepted = true
                    var mdl2 = library ? library.gamesModel : null
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, gameListView._currentSort,
                        function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                    )
                }
            }

            // ── Game row delegate ────────────────────────────────────────────
            delegate: FocusScope {
                id: rowRoot

                width: gameList.width
                height: root.vpx(40)

                // Background highlight for the current item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: rowRoot.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: rowRoot.ListView.isCurrentItem && gameList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Favorite indicator + game name
                Row {
                    anchors {
                        left: parent.left
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(12)
                    }
                    spacing: 0

                    // Favorite star prefix
                    Text {
                        text: "★ "
                        color: Theme.colorPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        visible: model.favorite === true
                    }

                    // Game name
                    Text {
                        text: model.name
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        width: parent.width - (model.favorite === true ? root.vpx(20) : 0)
                    }
                }

                // Focus ring — visible when this row is current and list has focus
                FocusRing {
                    visible: rowRoot.ListView.isCurrentItem && gameList.activeFocus
                }
            }
        }

        // ── Empty state (centered in full content area) ───────────────────────
        // Shown when the list has no items (covers both panels).
        Text {
            anchors.centerIn: parent
            visible: gameList.count === 0
            text: "No games found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
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

        // Currently focused row: 0=sort row, 1=view row
        property int _focusRow: 0

        function open() {
            // Sync selection indices to current state
            var sortKeys = ["az", "za", "recent"]
            var si = sortKeys.indexOf(gameListView._currentSort)
            _sortIndex = si >= 0 ? si : 0
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(gameListView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
            _focusRow = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            gameList.forceActiveFocus()
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
                                var isActive = modelData.key === gameListView._currentSort
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
                                var isActive = modelData.key === gameListView._viewMode
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

            } else if (KeyHandler.isAccept(event)) {
                event.accepted = true
                // Apply sort
                var sortKeys = ["az", "za", "recent"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                gameListView._currentSort = newSort
                library.sortGames(newSort)
                if (Settings) Settings.setSortRetroGames(newSort)
                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== gameListView._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // RetroGamesScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (Settings) Settings.setRetroGamesViewMode(newView)
                    gameListView.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortOverlay.close()
                }
            }
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
        }
    }
}
