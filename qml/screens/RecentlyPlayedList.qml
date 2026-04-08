import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Recently Played list view — split-panel browse view for recently played games.
//
// Shows a unified list of recently played Steam and Moonlight titles, each with
// a small source badge (colored dot + name). The left panel shows a poster
// preview and metadata for the currently highlighted entry.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "games" view (list mode) for the
//   "recent" source.
//   Up/Down navigate the list natively.
//   A (Return)  → emits gameSelected(index)
//   B (Escape)  → emits back()
//   Y (2)       → opens the view overlay panel
FocusScope {
    id: recentlyPlayedList

    // Emitted when the user presses B / Escape to return to the source list.
    signal back()

    // Emitted when the user presses A / Return on a game row.
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

    // ── Preview data for the left panel ──────────────────────────────────────
    // Cached entry dict for the currently highlighted item.
    property var _previewData: ({})

    // Update preview data when the current index changes.
    // Guards index bounds; sets _previewData from the entries array directly.
    function _updatePreview(index) {
        if (index < 0 || index >= recentlyPlayedList.entries.length) {
            _previewData = {}
            return
        }
        _previewData = recentlyPlayedList.entries[index] || {}
    }

    // Re-trigger preview when view becomes visible.
    onVisibleChanged: {
        if (visible) {
            _updatePreview(gameList.currentIndex)
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
            text: "◀  " + recentlyPlayedList.sourceName
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

            // ── Portrait poster image area (~70% of panel height) ─────────────
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
                height: Math.round(parent.height * 0.70)

                // Placeholder shown when there is no image or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready
                             || !recentlyPlayedList._previewData.imagePath

                    Text {
                        anchors.centerIn: parent
                        text: recentlyPlayedList._previewData.name || ""
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
                    source: recentlyPlayedList._previewData.imagePath
                            ? (recentlyPlayedList._previewData.imagePath.startsWith("http")
                                ? recentlyPlayedList._previewData.imagePath
                                : "file://" + recentlyPlayedList._previewData.imagePath)
                            : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.70)
                    visible: status === Image.Ready && !!recentlyPlayedList._previewData.imagePath
                }
            }

            // ── Source badge and last played info ─────────────────────────────
            Column {
                id: previewInfoColumn

                anchors {
                    top: posterArea.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(8)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                spacing: root.vpx(4)

                // Source badge row: colored dot + source name
                Row {
                    spacing: root.vpx(6)
                    visible: !!recentlyPlayedList._previewData.source

                    Rectangle {
                        width: root.vpx(10)
                        height: root.vpx(10)
                        radius: root.vpx(5)
                        anchors.verticalCenter: parent.verticalCenter
                        color: recentlyPlayedList._previewData.source === "steam"
                               ? Theme.colorBadgeSteam
                               : Theme.colorBadgeMoonlight
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: recentlyPlayedList._previewData.source === "steam"
                              ? "Steam"
                              : "Moonlight"
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    }
                }

                // Last played row
                Text {
                    text: "Last Played: " + recentlyPlayedList._formatLastPlayed(
                              recentlyPlayedList._previewData.lastPlayed)
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: !!recentlyPlayedList._previewData.name
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

            model: recentlyPlayedList.entries
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast

            // Update preview data when the current index changes.
            onCurrentIndexChanged: {
                recentlyPlayedList._updatePreview(currentIndex)
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    recentlyPlayedList.gameSelected(gameList.currentIndex)
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    recentlyPlayedList.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    viewOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, null,
                        function(i) { return "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    gameList.currentIndex = JumpHelper.jumpIndex(
                        gameList.count, gameList.currentIndex, null,
                        function(i) { return "" }, -1
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

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Source badge: small colored rectangle inline before the name
                Rectangle {
                    id: sourceDot

                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(12)
                        verticalCenter: parent.verticalCenter
                    }
                    width: root.vpx(8)
                    height: root.vpx(8)
                    radius: root.vpx(4)
                    color: modelData.source === "steam" ? Theme.colorBadgeSteam : Theme.colorBadgeMoonlight
                }

                // Game name
                Text {
                    anchors {
                        left: sourceDot.right
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(8)
                        rightMargin: root.vpx(12)
                    }
                    text: modelData.name || ""
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
            text: "No recently played games"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
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
            var vi = viewKeys.indexOf(recentlyPlayedList._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
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
                                var isActive = modelData.key === recentlyPlayedList._viewMode
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
                if (newView !== recentlyPlayedList._viewMode) {
                    // View mode is changing — hide overlay and return focus to the list
                    // so focus is not stranded when this component becomes invisible.
                    // PcGamesScreen.on_ViewModeChanged will re-route focus to the new view.
                    viewOverlay.visible = false
                    gameList.forceActiveFocus()
                    if (settings) settings.setPcGamesViewMode(newView)
                    recentlyPlayedList.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    viewOverlay.close()
                }
            }
        }
    }

    // Component.onCompleted: _viewMode is bound from parent; do not overwrite here.
}
