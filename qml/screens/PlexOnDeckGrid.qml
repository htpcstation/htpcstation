import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Plex on-deck (Continue Watching) grid — shows a scrollable grid of in-progress items.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for the ondeck library.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits itemSelected(ratingKey).
//   B (Escape) → emits back() so WatchScreen can return to the library list.
//
// No sort/filter overlay — on-deck is a fixed list ordered by Plex.
FocusScope {
    id: onDeckGridView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on an item cell.
    // ratingKey is the Plex ratingKey for the selected item.
    signal itemSelected(string ratingKey)

    // Emitted when the user changes the view mode via the view overlay.
    signal viewModeChanged(string mode)

    // View mode ("grid" or "list") — set by WatchScreen; do not overwrite in onCompleted
    property string _viewMode: "grid"

    // Title shown in the header bar. Defaults to "Continue Watching" for the
    // on-deck view; set to "Watchlist" (or any other string) when reused for
    // other sources.
    property string sourceTitle: "Continue Watching"

    // Model to display. Defaults to plex.onDeckModel; override to use a
    // different PlexOnDeckModel instance (e.g. plex.watchlistModel).
    property var model: plex ? plex.onDeckModel : null

    // Reset to the first item whenever this grid gains focus so the
    // top-left (most recently watched) item is always highlighted on entry.
    onActiveFocusChanged: {
        if (activeFocus) {
            if (onDeckGrid.count > 0) {
                onDeckGrid.currentIndex = 0
            }
            onDeckGrid.forceActiveFocus()
        }
    }

    // ── Cell dimensions (same as PlexMovieGrid for visual consistency) ────────
    readonly property int _targetCellW: 160
    readonly property int _cellH: 280
    readonly property int _cellSpacing: 12

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
            text: "◀  " + onDeckGridView.sourceTitle
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // Y button hint — opens the view toggle overlay
        Text {
            id: viewHint
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.context2Label + "  View" : "F2  View"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        // X button hint — My List
        Text {
            id: myListHint
            anchors {
                right: viewHint.left
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "F1  My List"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        // Quick scroll hint
        Text {
            id: scrollHint
            anchors {
                right: myListHint.left
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── On-deck grid ──────────────────────────────────────────────────────────
    GridView {
        id: onDeckGrid

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: onDeckGridView.model
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(onDeckGridView._targetCellW + onDeckGridView._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(onDeckGridView._targetCellW + onDeckGridView._cellSpacing)
        cellHeight: root.vpx(onDeckGridView._cellH + onDeckGridView._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                viewOverlay.open()
            } else if (keys.isContext1(event)) {
                event.accepted = true
                var item = onDeckGrid.currentItem
                if (item) {
                    plex.toggleMyList(item.itemRatingKey, item.itemTitle, item.itemType,
                                      item.itemPosterLocal, item.itemGrandparentTitle)
                }
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var item = onDeckGrid.currentItem
                if (item) {
                    onDeckGridView.itemSelected(item.itemRatingKey)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                onDeckGridView.back()
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                onDeckGrid.currentIndex = JumpHelper.jumpIndex(
                    onDeckGrid.count, onDeckGrid.currentIndex, null,
                    function(i) { return "" }, 1
                )
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                onDeckGrid.currentIndex = JumpHelper.jumpIndex(
                    onDeckGrid.count, onDeckGrid.currentIndex, null,
                    function(i) { return "" }, -1
                )
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: onDeckGrid.count === 0
            text: "Nothing in progress"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── On-deck tile delegate ─────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose ratingKey so the key handler can read it.
            readonly property string itemRatingKey: model.ratingKey
            // Expose additional fields for My List toggle
            readonly property string itemTitle: model.title || ""
            readonly property string itemType: model.type || ""
            readonly property string itemPosterLocal: model.posterLocal || ""
            readonly property string itemGrandparentTitle: model.grandparentTitle || ""

            // Cache My List status at creation time (isInMyList reads from disk)
            property bool _inMyList: false
            Component.onCompleted: {
                if (plex) _inMyList = plex.isInMyList(model.ratingKey)
            }

            width: onDeckGrid.cellWidth
            height: onDeckGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(onDeckGridView._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && onDeckGrid.activeFocus ? 0.15 : 0.0

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // ── Poster image area ─────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~75% of the card height (portrait 2:3 ratio)
                    height: Math.round(parent.height * 0.75)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.posterLocal === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.type === "episode"
                                  ? (model.grandparentTitle || model.title || "")
                                  : (model.title || "")
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }
                    }

                    Image {
                        id: posterImage

                        anchors.fill: parent
                        source: model.posterLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(onDeckGridView._targetCellW)
                        sourceSize.height: Math.round(root.vpx(onDeckGridView._cellH) * 0.75)
                        visible: status === Image.Ready && model.posterLocal !== ""
                        clip: true
                    }

                    // ── Progress bar ──────────────────────────────────────────
                    // Shown at the bottom of the poster area
                    Item {
                        id: progressBarArea

                        anchors {
                            left: parent.left
                            right: parent.right
                            bottom: parent.bottom
                        }
                        height: root.vpx(4)
                        visible: model.duration > 0

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
                                var pct = model.duration > 0
                                          ? Math.min(1.0, model.viewOffset / model.duration)
                                          : 0.0
                                return parent.width * pct
                            }
                            color: Theme.colorPrimary
                        }
                    }
                }

                // ── Title label ───────────────────────────────────────────────
                // For episodes: show name on first line, episode title on second.
                // For movies: just the title.
                Text {
                    id: titleText

                    anchors {
                        top: posterArea.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(4)
                    }
                    text: model.type === "episode"
                          ? (model.grandparentTitle || "")
                          : (model.title || "")
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Episode title (second line, episodes only) ─────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.type === "episode" ? (model.title || "") : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    visible: model.type === "episode"
                }

                // ── My List star indicator ───────────────────────────────────
                Text {
                    anchors {
                        top: parent.top
                        right: parent.right
                        topMargin: root.vpx(4)
                        rightMargin: root.vpx(4)
                    }
                    text: "★"
                    color: Theme.colorPrimary
                    font.pixelSize: root.vpx(14)
                    visible: tileRoot._inMyList
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && onDeckGrid.activeFocus
                }
            }
        }
    }

    // ── View overlay ──────────────────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Only has a View row (no sort — on-deck ordering is fixed by Plex).
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
            var vi = viewKeys.indexOf(onDeckGridView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            onDeckGrid.forceActiveFocus()
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
                                var isActive = modelData.key === onDeckGridView._viewMode
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
                if (newView !== onDeckGridView._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // WatchScreen will route focus to the newly visible view.
                    viewOverlay.visible = false
                    if (settings) settings.setWatchViewMode(newView)
                    onDeckGridView.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    viewOverlay.close()
                }
            }
        }
    }
}
