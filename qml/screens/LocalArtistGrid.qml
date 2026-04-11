import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Local music artist poster grid — shows a scrollable grid of artist posters.
//
// Focus flow:
//   Gains focus when LocalMusicScreen switches to "artists" view (grid mode).
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits artistSelected(artistName).
//   B (Escape) → emits back() so LocalMusicScreen can return to the menu.
//   Y (2)      → opens the sort/view overlay panel.
FocusScope {
    id: localArtistGrid

    // Emitted when the user presses B / Escape to return to the menu.
    signal back()

    // Emitted when the user presses A / Return on an artist cell.
    signal artistSelected(string artistName)

    // Emitted when the user changes the view mode via the sort overlay.
    signal viewModeChanged(string mode)

    // Sort/view state
    property string _currentSort: ""
    property string _viewMode: "grid"

    // Loading state (bound from LocalMusicScreen)
    property bool loading: false

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az") return "A-Z"
        if (_currentSort === "za") return "Z-A"
        return "Default"
    }

    // ── Cell dimensions (design-grid px, scaled via vpx) ─────────────────────
    readonly property int _targetCellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    // ── Header bar + status bar ───────────────────────────────────────────────
    LibraryHeader {
        id: header
        title: "Artists"
        statusText: localArtistGrid._currentSort !== ""
            ? "Sorted: " + localArtistGrid._sortLabel
            : "Default order"
        rightText1: keys.useGamepadLabels ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll" : "PgUp/PgDn  Scroll"
        rightText2: keys.useGamepadLabels ? keys.context2Label + "  Sort" : "2  Sort"
    }

    // ── Artist grid ───────────────────────────────────────────────────────────
    GridView {
        id: artistGrid

        anchors {
            top: header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: localMusic ? localMusic.artistsModel : null
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(localArtistGrid._targetCellW + localArtistGrid._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(localArtistGrid._targetCellW + localArtistGrid._cellSpacing)
        cellHeight: root.vpx(localArtistGrid._cellH + localArtistGrid._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortOverlay.open()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var item = artistGrid.currentItem
                if (item) {
                    localArtistGrid.artistSelected(item.artistName)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localArtistGrid.back()
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                var mdl = localMusic ? localMusic.artistsModel : null
                artistGrid.currentIndex = JumpHelper.jumpIndex(
                    artistGrid.count, artistGrid.currentIndex, localArtistGrid._currentSort,
                    function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                )
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                var mdl2 = localMusic ? localMusic.artistsModel : null
                artistGrid.currentIndex = JumpHelper.jumpIndex(
                    artistGrid.count, artistGrid.currentIndex, localArtistGrid._currentSort,
                    function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                )
            }
        }

        // ── Empty state — prompt user to configure library path ─────────────
        Column {
            anchors.centerIn: parent
            visible: artistGrid.count === 0 && (!localMusic || !localMusic.scanning)
            spacing: root.vpx(12)

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "No music found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Set your Music Directory in Settings → Paths, then Scan Library from the menu"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                opacity: 0.7
            }
        }

        // ── Artist tile delegate ─────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose artist name so the key handler can read it.
            readonly property string artistName: model.title || ""

            width: artistGrid.cellWidth
            height: artistGrid.cellHeight

            z: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus ? 1 : 0

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(localArtistGrid._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                scale: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                // Subtle highlight when focused
                GridCellHighlight {
                    active: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus
                }

                // ── Poster image area ────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~80% of the card height
                    height: Math.round(parent.height * 0.80)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.imageLocal === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.title || ""
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
                        source: model.imageLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        cache: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(localArtistGrid._targetCellW)
                        sourceSize.height: Math.round(root.vpx(localArtistGrid._cellH) * 0.80)
                        visible: status === Image.Ready && model.imageLocal !== ""
                        clip: true
                    }
                }

                // ── Artist name label ────────────────────────────────────────
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
                    text: model.title || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Genre subtitle ───────────────────────────────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.genre || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus
                }
            }
        }
    }

    // ── Sort+View overlay ─────────────────────────────────────────────────────
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

        // 0 = sort section, 1 = view section
        property int _section: 0
        // Index within sort options (0=A-Z, 1=Z-A)
        property int _sortIndex: 0
        // Index within view options (0=Grid, 1=List)
        property int _viewIndex: 0

        function open() {
            // Sync selection to current state
            var sortKeys = ["az", "za"]
            var si = sortKeys.indexOf(localArtistGrid._currentSort)
            _sortIndex = si >= 0 ? si : 0

            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(localArtistGrid._viewMode)
            _viewIndex = vi >= 0 ? vi : 0

            _section = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            artistGrid.forceActiveFocus()
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

            // ── Sort section label ────────────────────────────────────────────
            Text {
                id: sortSectionLabel
                anchors {
                    top: divider.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(8)
                }
                text: "Sort"
                color: sortOverlay._section === 0 ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            // ── Sort options row ──────────────────────────────────────────────
            Row {
                id: sortOptionsRow
                anchors {
                    top: sortSectionLabel.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(4)
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { key: "az", label: "A-Z" },
                        { key: "za", label: "Z-A" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(80)
                        height: root.vpx(36)
                        color: sortOverlay._section === 0 && sortOverlay._sortIndex === index
                            ? Theme.colorPrimary : "transparent"
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
                                var isActive = modelData.key === localArtistGrid._currentSort
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: sortOverlay._section === 0 && sortOverlay._sortIndex === index
                                ? Theme.colorOverlayText : Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }

            // ── View section label ────────────────────────────────────────────
            Text {
                id: viewSectionLabel
                anchors {
                    top: sortOptionsRow.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(6)
                }
                text: "View"
                color: sortOverlay._section === 1 ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            // ── View options row ──────────────────────────────────────────────
            Row {
                id: viewOptionsRow
                anchors {
                    top: viewSectionLabel.bottom
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
                        color: sortOverlay._section === 1 && sortOverlay._viewIndex === index
                            ? Theme.colorPrimary : "transparent"
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
                                var isActive = modelData.key === localArtistGrid._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: sortOverlay._section === 1 && sortOverlay._viewIndex === index
                                ? Theme.colorOverlayText : Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }
        }

        // ── Key handling ─────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            var sortCount = 2
            var viewCount = 2

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortOverlay.close()

            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (sortOverlay._section > 0)
                    sortOverlay._section -= 1

            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (sortOverlay._section < 1)
                    sortOverlay._section += 1

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortOverlay._section === 0) {
                    if (sortOverlay._sortIndex > 0)
                        sortOverlay._sortIndex -= 1
                } else {
                    if (sortOverlay._viewIndex > 0)
                        sortOverlay._viewIndex -= 1
                }

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortOverlay._section === 0) {
                    if (sortOverlay._sortIndex < sortCount - 1)
                        sortOverlay._sortIndex += 1
                } else {
                    if (sortOverlay._viewIndex < viewCount - 1)
                        sortOverlay._viewIndex += 1
                }

            } else if (keys.isAccept(event)) {
                event.accepted = true

                // Apply sort
                var sortKeys = ["az", "za"]
                var newSort = sortKeys[sortOverlay._sortIndex]
                localArtistGrid._currentSort = newSort
                if (localMusic) localMusic.sortArtists(newSort)
                if (settings) settings.setSortLocalMusicArtists(newSort)

                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== localArtistGrid._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // LocalMusicScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (settings) settings.setLocalMusicViewMode(newView)
                    localArtistGrid.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortOverlay.close()
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) {
            var savedSort = settings.sortLocalMusicArtists
            if (savedSort) {
                _currentSort = savedSort
                if (localMusic) localMusic.sortArtists(savedSort)
            }
            // _viewMode is bound from LocalMusicScreen; do not overwrite here.
        }
    }
}
