import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Steam game list view — split-panel browse view for Steam games.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits gameSelected(index)
//   B (Escape)  → emits back()
//   Y (2)       → opens the sort overlay panel
FocusScope {
    id: steamGameList

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on a game row.
    // index is the row in steam.gamesModel.
    signal gameSelected(int index)

    // Emitted when the user changes the view mode via the sort overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected source (set by PcGamesScreen).
    property string sourceName: ""

    // ── Sort state (mirrors backend state for display) ─────────────────────────
    property string _currentSort: "az"

    // ── View mode (set by PcGamesScreen; "grid" or "list") ────────────────────
    property string _viewMode: "grid"

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")     return "A-Z"
        if (_currentSort === "za")     return "Z-A"
        if (_currentSort === "recent") return "Recent"
        return "A-Z"
    }

    // ── Preview data for the left panel ──────────────────────────────────────
    // Cached game dict for the currently highlighted item (from steam.getGame).
    property var _previewData: ({})

    // Async metadata dict populated by steam.metadataChanged signal.
    property var _previewMetadata: ({})

    // Update preview data when the current index changes.
    // Null-guards steam and model; resets async metadata; triggers fetch.
    function _updatePreview(index) {
        if (!steam) {
            _previewData = {}
            _previewMetadata = {}
            return
        }
        if (index < 0 || index >= gameList.count) {
            _previewData = {}
            _previewMetadata = {}
            return
        }
        _previewData = steam.getGame(index)
        _previewMetadata = {}
        if (_previewData.appId) {
            steam.fetchMetadata(_previewData.appId)
        }
    }

    // ── Listen for metadataChanged to refresh the left panel ─────────────────
    Connections {
        target: steam
        function onMetadataChanged(appId, metadata) {
            if (appId === steamGameList._previewData.appId) {
                steamGameList._previewMetadata = metadata
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

    // Re-trigger preview when view becomes visible.
    onVisibleChanged: {
        if (visible) {
            _updatePreview(gameList.currentIndex)
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
            text: "◀  " + steamGameList.sourceName
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
        visible: true

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "Sorted: " + steamGameList._sortLabel
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
                text: keys.useGamepadLabels ? keys.context1Label + "  Favorite" : "1  Favorite"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context2Label + "  Sort" : "2  Sort"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Split content area ────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        // ── Left panel: preview area (45% width) ──────────────────────────────
        Item {
            id: leftPanel

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            width: Math.round(parent.width * 0.45)

            // ── Portrait poster image area (~60% of panel height) ─────────────
            Item {
                id: posterArea

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(16)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                // Poster area takes ~60% of the left panel height (portrait aspect)
                height: Math.round(parent.height * 0.60)

                // Placeholder shown when there is no image or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready
                             || !steamGameList._previewData.imagePath

                    Text {
                        anchors.centerIn: parent
                        text: steamGameList._previewData.name || ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - root.vpx(16)
                    }
                }

                // Portrait poster image — prepend "file://" for local paths
                Image {
                    id: posterImage

                    anchors.fill: parent
                    source: steamGameList._previewData.imagePath
                            ? (steamGameList._previewData.imagePath.startsWith("http")
                                ? steamGameList._previewData.imagePath
                                : "file://" + steamGameList._previewData.imagePath)
                            : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.60)
                    visible: status === Image.Ready && !!steamGameList._previewData.imagePath
                }
            }

            // ── Compact metadata column ───────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: posterArea.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(8)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                spacing: root.vpx(4)

                Repeater {
                    model: [
                        {
                            label: "Developer",
                            value: steamGameList._previewMetadata.developer
                                   || steamGameList._previewData.developer || ""
                        },
                        {
                            label: "Genre",
                            value: steamGameList._previewMetadata.genre
                                   || steamGameList._previewData.genre || ""
                        },
                        {
                            label: "Rating",
                            value: steamGameList._formatRating(
                                       steamGameList._previewMetadata.rating !== undefined
                                       ? steamGameList._previewMetadata.rating
                                       : steamGameList._previewData.rating)
                        },
                        {
                            label: "Last Played",
                            value: steamGameList._formatLastPlayed(
                                       steamGameList._previewData.lastPlayed)
                        }
                    ]

                    Row {
                        spacing: root.vpx(6)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            width: root.vpx(72)
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
                interactive: false  // preview only — no scroll needed

                Text {
                    id: descriptionText

                    width: descriptionFlickable.width
                    text: steamGameList._previewMetadata.description
                          || steamGameList._previewData.description || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.Wrap
                }
            }
        }

        // ── Right panel: game list (55% width) ────────────────────────────────
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

            model: steam ? steam.gamesModel : null
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast

            // Update preview data when the current index changes.
            onCurrentIndexChanged: {
                steamGameList._updatePreview(currentIndex)
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    steamGameList.gameSelected(gameList.currentIndex)
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    steamGameList.back()
                } else if (keys.isContext1(event)) {
                    event.accepted = true
                    if (steam) steam.toggleFavorite(gameList.currentIndex)
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    sortOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    var mdl = steam ? steam.gamesModel : null
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, steamGameList._currentSort,
                        function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    var mdl2 = steam ? steam.gamesModel : null
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, steamGameList._currentSort,
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

                // Game name
                Text {
                    anchors {
                        left: parent.left
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(12)
                    }
                    text: model.name
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
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
            if (!steam) return
            // Sync selection indices to current state
            var sortKeys = ["az", "za", "recent"]
            var si = sortKeys.indexOf(steamGameList._currentSort)
            _sortIndex = si >= 0 ? si : 0
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(steamGameList._viewMode)
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
                text: keys.useGamepadLabels ? keys.cancelLabel + " / " + keys.context2Label + "  Close" : "Esc / 2  Close"
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
                                var isActive = modelData.key === steamGameList._currentSort
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
                                var isActive = modelData.key === steamGameList._viewMode
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

            if (keys.isCancel(event) || keys.isContext2(event)) {
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

            } else if (keys.isAccept(event)) {
                event.accepted = true
                // Apply sort
                var sortKeys = ["az", "za", "recent"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                steamGameList._currentSort = newSort
                if (steam) steam.sortGames(newSort)
                if (settings) settings.setSortSteamGames(newSort)
                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== steamGameList._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // PcGamesScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (settings) settings.setPcGamesViewMode(newView)
                    steamGameList.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortOverlay.close()
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) {
            var saved = settings.sortSteamGames
            if (saved) {
                _currentSort = saved
                if (steam) steam.sortGames(saved)
            }
            // _viewMode is bound from PcGamesScreen; do not overwrite here.
        }
    }
}
