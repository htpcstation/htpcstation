import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Plex on-deck (Continue Watching) list view — split-panel browse view for
// in-progress movies and episodes.
//
// Key differences from movie/show list views:
//   - No sort/filter — on-deck ordering is fixed by Plex.
//   - Mixed types: items can be movies OR episodes.
//   - Progress bar per item (viewOffset / duration).
//   - Signal is itemSelected(ratingKey), not movieSelected/showSelected.
//   - No infinite scroll — typically <20 items.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for the ondeck
//   library (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits itemSelected(ratingKey)
//   B (Escape)  → emits back()
//   Y (F2)      → opens the view overlay panel
FocusScope {
    id: onDeckListView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on an item row.
    // ratingKey is the Plex ratingKey for the selected item.
    signal itemSelected(string ratingKey)

    // Emitted when the user changes the view mode via the view overlay.
    signal viewModeChanged(string mode)

    // View mode (set by WatchScreen; "grid" or "list").
    property string _viewMode: "grid"

    // Title shown in the header bar. Defaults to "Continue Watching" for the
    // on-deck view; set to "Watchlist" (or any other string) when reused for
    // other sources.
    property string sourceTitle: "Continue Watching"

    // Model to display. Defaults to plex.onDeckModel; override to use a
    // different PlexOnDeckModel instance (e.g. plex.watchlistModel).
    property var model: plex ? plex.onDeckModel : null

    // Guard flag — when true, the next onActiveFocusChanged will NOT reset
    // currentIndex to 0.  Used by WatchScreen to restore focus after the
    // resume dialog is cancelled.
    property bool _suppressIndexReset: false

    // Expose the current item's viewOffset so WatchScreen can pass it to
    // _playContent without changing the itemSelected signal signature.
    readonly property int currentViewOffset: onDeckList.currentItem ? (onDeckList.currentItem.viewOffsetValue || 0) : 0
    property int currentIndex: 0
    onCurrentIndexChanged: {
        if (onDeckList.currentIndex !== currentIndex)
            onDeckList.currentIndex = currentIndex
    }

    // ── Helper: format watch progress ─────────────────────────────────────────
    // Returns "X%" string when duration > 0, otherwise "".
    function _formatProgress(viewOffset, duration) {
        if (!duration || duration <= 0) return ""
        var pct = Math.round(Math.min(100, (viewOffset / duration) * 100))
        return pct + "%"
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
            text: "◀  " + onDeckListView.sourceTitle
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

    }

    // ── Status bar ────────────────────────────────────────────────────────────
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
            text: "Sorted: Continue Watching"
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
                text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "F1  My List"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context2Label + "  View" : "F2  View"
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

        // ── Left panel: poster + progress preview (45% width) ─────────────────
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
                height: Math.round(parent.height * 0.60)

                // Placeholder shown when there is no poster or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready
                             || !onDeckList.currentItem
                             || !onDeckList.currentItem.posterLocalValue

                    Text {
                        anchors.centerIn: parent
                        text: {
                            if (!onDeckList.currentItem) return ""
                            if (onDeckList.currentItem.itemType === "episode")
                                return onDeckList.currentItem.grandparentTitleValue || onDeckList.currentItem.titleValue || ""
                            return onDeckList.currentItem.titleValue || ""
                        }
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - root.vpx(16)
                    }
                }

                // Portrait poster image
                Image {
                    id: posterImage

                    anchors.fill: parent
                    source: (onDeckList.currentItem && onDeckList.currentItem.posterLocalValue)
                            ? onDeckList.currentItem.posterLocalValue
                            : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.60)
                    visible: status === Image.Ready
                             && !!onDeckList.currentItem
                             && !!onDeckList.currentItem.posterLocalValue
                }
            }

            // ── Type indicator + progress info ────────────────────────────────
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

                // Type indicator: show name for episodes, "Movie" for movies
                Text {
                    width: parent.width
                    text: {
                        if (!onDeckList.currentItem) return ""
                        if (onDeckList.currentItem.itemType === "episode")
                            return onDeckList.currentItem.grandparentTitleValue || ""
                        return "Movie"
                    }
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    visible: !!onDeckList.currentItem
                }

                // Progress bar track + fill
                Item {
                    id: previewProgressBar

                    width: parent.width
                    height: root.vpx(4)
                    visible: !!onDeckList.currentItem
                             && onDeckList.currentItem.durationValue > 0

                    // Track (background)
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorOverlayMid
                    }

                    // Fill (progress)
                    Rectangle {
                        anchors {
                            left: parent.left
                            top: parent.top
                            bottom: parent.bottom
                        }
                        width: {
                            if (!onDeckList.currentItem) return 0
                            var dur = onDeckList.currentItem.durationValue
                            if (dur <= 0) return 0
                            var pct = Math.min(1.0, onDeckList.currentItem.viewOffsetValue / dur)
                            return parent.width * pct
                        }
                        color: Theme.colorPrimary
                    }
                }

                // Progress text: "X% watched"
                Text {
                    width: parent.width
                    text: {
                        if (!onDeckList.currentItem) return ""
                        var s = onDeckListView._formatProgress(
                            onDeckList.currentItem.viewOffsetValue,
                            onDeckList.currentItem.durationValue)
                        return s ? s + " watched" : ""
                    }
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: !!onDeckList.currentItem
                             && onDeckList.currentItem.durationValue > 0
                }
            }
        }

        // ── Right panel: on-deck list (55% width) ─────────────────────────────
        ListView {
            id: onDeckList

            anchors {
                top: parent.top
                left: leftPanel.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(64)
                rightMargin: root.vpx(16)
            }

            model: onDeckListView.model
            clip: true
            focus: true
            keyNavigationEnabled: true

            onCurrentIndexChanged: onDeckListView.currentIndex = currentIndex

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast

            // Reset to first item whenever this list gains focus (unless suppressed).
            onActiveFocusChanged: {
                if (activeFocus) {
                    if (!onDeckListView._suppressIndexReset && count > 0) currentIndex = 0
                    onDeckListView._suppressIndexReset = false
                }
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = onDeckList.currentItem
                    if (item) {
                        onDeckListView.itemSelected(item.ratingKeyValue)
                    }
                } else if (keys.isContext1(event)) {
                    event.accepted = true
                    var item = onDeckList.currentItem
                    if (item) {
                        plex.toggleMyList(item.ratingKeyValue, item.titleValue, item.itemType,
                                          item.posterLocalValue, item.grandparentTitleValue)
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    onDeckListView.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    viewOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    onDeckList.currentIndex = JumpHelper.jumpIndex(
                        onDeckList.count, onDeckList.currentIndex, null,
                        function(i) { return "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    onDeckList.currentIndex = JumpHelper.jumpIndex(
                        onDeckList.count, onDeckList.currentIndex, null,
                        function(i) { return "" }, -1
                    )
                }
            }

            // ── On-deck row delegate ─────────────────────────────────────────
            delegate: FocusScope {
                id: rowRoot

                // Expose model values so the left panel and key handler can read them.
                readonly property string ratingKeyValue: model.ratingKey
                readonly property string titleValue: model.title
                readonly property string itemType: model.type
                readonly property string posterLocalValue: model.posterLocal
                readonly property string grandparentTitleValue: model.grandparentTitle
                readonly property int viewOffsetValue: model.viewOffset
                readonly property int durationValue: model.duration

                width: onDeckList.width
                // Slightly taller than standard 40px to fit two lines for episodes
                height: root.vpx(44)

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

                // ── Title area ───────────────────────────────────────────────
                // For movies: title only (vertically centered).
                // For episodes: show name on first line, episode title on second.
                Item {
                    id: titleArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                        bottom: rowProgressBar.top
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(12)
                    }

                    // Movie: single title line, vertically centered
                    Text {
                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                        }
                        visible: rowRoot.itemType !== "episode"
                        text: rowRoot.titleValue
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                    }

                    // Episode: show name (first line)
                    Text {
                        id: showNameText

                        anchors {
                            top: parent.top
                            left: parent.left
                            right: parent.right
                            topMargin: root.vpx(2)
                        }
                        visible: rowRoot.itemType === "episode"
                        text: rowRoot.grandparentTitleValue
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                    }

                    // Episode: episode title (second line)
                    Text {
                        anchors {
                            top: showNameText.bottom
                            left: parent.left
                            right: parent.right
                        }
                        visible: rowRoot.itemType === "episode"
                        text: rowRoot.titleValue
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        elide: Text.ElideRight
                    }
                }

                // ── Small progress bar at the bottom of each row ─────────────
                Item {
                    id: rowProgressBar

                    anchors {
                        left: parent.left
                        right: parent.right
                        bottom: parent.bottom
                    }
                    height: root.vpx(2)
                    visible: rowRoot.durationValue > 0

                    // Track (background)
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorOverlayMid
                    }

                    // Fill (progress)
                    Rectangle {
                        anchors {
                            left: parent.left
                            top: parent.top
                            bottom: parent.bottom
                        }
                        width: {
                            var dur = rowRoot.durationValue
                            if (dur <= 0) return 0
                            var pct = Math.min(1.0, rowRoot.viewOffsetValue / dur)
                            return parent.width * pct
                        }
                        color: Theme.colorPrimary
                    }
                }

                // Focus ring — visible when this row is current and list has focus
                FocusRing {
                    visible: rowRoot.ListView.isCurrentItem && onDeckList.activeFocus
                }
            }
        }

        // ── Empty state (centered in full content area) ───────────────────────
        Text {
            anchors.centerIn: parent
            visible: onDeckList.count === 0
            text: "Nothing to continue watching"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── View overlay ──────────────────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Only has a View row (no sort — ordering is fixed by Plex).
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
            var vi = viewKeys.indexOf(onDeckListView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            onDeckList.forceActiveFocus()
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
                      : "Esc / F2  Close"
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
                                var isActive = modelData.key === onDeckListView._viewMode
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
                if (newView !== onDeckListView._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // WatchScreen will route focus to the newly visible view.
                    viewOverlay.visible = false
                    if (settings) settings.setWatchViewMode(newView)
                    onDeckListView.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    viewOverlay.close()
                }
            }
        }
    }

    // Component.onCompleted: _viewMode is bound from WatchScreen; do not overwrite here.
}
