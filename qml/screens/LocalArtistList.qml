import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Local music artist list view — split-panel browse view for local music artists.
//
// Focus flow:
//   Gains focus when LocalMusicScreen switches to "artists" view (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits artistSelected(artistName)
//   B (Escape)  → emits back()
//   Y (2)       → opens the sort overlay panel
FocusScope {
    id: localArtistList

    // Emitted when the user presses B / Escape to return to the menu.
    signal back()

    // Emitted when the user presses A / Return on an artist row.
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

    // ── Preview data for the left panel ──────────────────────────────────────
    // Cached artist dict for the currently highlighted item.
    property var _previewData: ({})

    // Last artist name for which we fetched preview data (avoids redundant calls).
    property string _lastPreviewName: ""

    // Update preview data when the current index changes.
    function _updatePreview() {
        var item = artistList.currentItem
        if (!item) {
            _previewData = {}
            _lastPreviewName = ""
            return
        }
        var name = item.artistName
        if (!name || name === _lastPreviewName) return
        _lastPreviewName = name
        // For local music, build preview from the delegate's model data directly.
        _previewData = {
            "title": name,
            "posterLocal": item.artistImageLocal || "",
            "genre": item.artistGenre || "",
        }
    }

    // Re-trigger preview when view becomes visible.
    onVisibleChanged: {
        if (visible) {
            _updatePreview()
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
            text: "◀  Artists"
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
            text: localArtistList._currentSort !== ""
                ? "Sorted: " + localArtistList._sortLabel
                : "Default order"
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
                             || !localArtistList._previewData.posterLocal

                    Text {
                        anchors.centerIn: parent
                        text: localArtistList._previewData.title || ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - root.vpx(16)
                    }
                }

                // Portrait poster image — imageLocal is already a valid URL
                Image {
                    id: posterImage

                    anchors.fill: parent
                    source: localArtistList._previewData.posterLocal || ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.60)
                    visible: status === Image.Ready && !!localArtistList._previewData.posterLocal
                }
            }

            // ── Genre label ───────────────────────────────────────────────────
            Text {
                id: genreText

                anchors {
                    top: posterArea.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.vpx(8)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                text: localArtistList._previewData.genre || ""
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
                visible: (localArtistList._previewData.genre || "") !== ""
            }
        }

        // ── Right panel: artist list (55% width) ──────────────────────────────
        ListView {
            id: artistList

            anchors {
                top: parent.top
                left: leftPanel.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(64)
                rightMargin: root.vpx(16)
            }

            model: localMusic ? localMusic.artistsModel : null
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
                localArtistList._updatePreview()
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = artistList.currentItem
                    if (item) {
                        localArtistList.artistSelected(item.artistName)
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    localArtistList.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    sortOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    var mdl = localMusic ? localMusic.artistsModel : null
                    artistList.currentIndex = JumpHelper.jumpIndex(
                        artistList.count, artistList.currentIndex, localArtistList._currentSort,
                        function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    var mdl2 = localMusic ? localMusic.artistsModel : null
                    artistList.currentIndex = JumpHelper.jumpIndex(
                        artistList.count, artistList.currentIndex, localArtistList._currentSort,
                        function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                    )
                }
            }

            // ── Artist row delegate ──────────────────────────────────────────
            delegate: Item {
                id: rowRoot

                // Expose model data so the key handler and preview can read it.
                readonly property string artistName: model.title || ""
                readonly property string artistImageLocal: model.imageLocal || ""
                readonly property string artistGenre: model.genre || ""

                width: artistList.width
                height: root.vpx(40)

                // Background highlight for the current item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: rowRoot.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: rowRoot.ListView.isCurrentItem && artistList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Artist name
                Text {
                    id: artistNameText
                    anchors {
                        left: parent.left
                        right: genreLabel.left
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(8)
                    }
                    text: model.title || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                }

                // Genre (right-aligned, dim)
                Text {
                    id: genreLabel
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        rightMargin: root.vpx(12)
                    }
                    text: model.genre || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }

                // Focus ring — visible when this row is current and list has focus
                FocusRing {
                    visible: rowRoot.ListView.isCurrentItem && artistList.activeFocus
                }
            }
        }

        // ── Empty state — prompt user to configure library path ────────────────
        Column {
            anchors.centerIn: parent
            visible: artistList.count === 0 && (!localMusic || !localMusic.scanning)
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
            var si = sortKeys.indexOf(localArtistList._currentSort)
            _sortIndex = si >= 0 ? si : 0

            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(localArtistList._viewMode)
            _viewIndex = vi >= 0 ? vi : 0

            _section = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            artistList.forceActiveFocus()
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
                                var isActive = modelData.key === localArtistList._currentSort
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
                                var isActive = modelData.key === localArtistList._viewMode
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
                localArtistList._currentSort = newSort
                if (localMusic) localMusic.sortArtists(newSort)
                if (settings) settings.setSortLocalMusicArtists(newSort)

                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortOverlay._viewIndex]
                if (newView !== localArtistList._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // LocalMusicScreen will route focus to the newly visible view.
                    sortOverlay.visible = false
                    if (settings) settings.setLocalMusicViewMode(newView)
                    localArtistList.viewModeChanged(newView)
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
