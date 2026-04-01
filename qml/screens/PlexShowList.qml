import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Plex TV show list view — split-panel browse view for Plex TV shows.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for a show library
//   (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits showSelected(ratingKey)
//   B (Escape)  → emits back()
//   Y (F2)      → opens the sort/filter/view overlay panel
FocusScope {
    id: showListView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on a show row.
    // ratingKey is the Plex ratingKey for the selected show.
    signal showSelected(string ratingKey)

    // Emitted when the user changes the view mode via the sort/filter overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected library (set by WatchScreen).
    property string systemName: ""

    // ── Sort/filter state (mirrors backend state for display) ──────────────────
    property string _currentSort: ""
    property string _currentGenreKey: ""
    property string _currentGenreTitle: ""

    // True while a sort/filter re-fetch is in progress
    property bool _loading: false

    // ── View mode (set by WatchScreen; "grid" or "list") ──────────────────────
    property string _viewMode: "grid"

    // Clear loading flag when the model is refreshed
    Connections {
        target: plex
        function onShowsModelChanged() {
            showListView._loading = false
        }
    }

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")        return "A-Z"
        if (_currentSort === "za")        return "Z-A"
        if (_currentSort === "recent")    return "Recently Added"
        if (_currentSort === "year_desc") return "Year (Newest)"
        if (_currentSort === "year_asc")  return "Year (Oldest)"
        if (_currentSort === "rating")    return "Rating"
        return "Default"
    }

    // ── Helper: format audience rating as "X.X/10" ───────────────────────────
    function _formatRating(rating) {
        if (!rating || rating <= 0) return ""
        return rating.toFixed(1) + "/10"
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
            text: "◀  " + showListView.systemName
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // Y button hint
        Text {
            id: sortHint
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.context2Label + "  Sort / Filter" : "F2  Sort / Filter"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        // X button hint — My List
        Text {
            id: myListHint
            anchors {
                right: sortHint.left
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

    // ── Sort/filter status bar ────────────────────────────────────────────────
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
            text: {
                var parts = []
                if (showListView._currentSort !== "")
                    parts.push("Sort: " + showListView._sortLabel)
                if (showListView._currentGenreTitle !== "")
                    parts.push("Genre: " + showListView._currentGenreTitle)
                return parts.length > 0 ? parts.join("  ·  ") : "Default order"
            }
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Loading indicator ─────────────────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        visible: showListView._loading
        text: "Loading..."
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeHeading)
        z: 1
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

            // ── Portrait poster image area (~65% of panel height) ─────────────
            // More space since there is no synopsis to display.
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
                // Poster area takes ~65% of the left panel height (portrait aspect)
                height: Math.round(parent.height * 0.65)

                // Placeholder shown when there is no poster or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready
                             || !showList.currentItem
                             || showList.currentItem.posterLocalValue === ""

                    Text {
                        anchors.centerIn: parent
                        text: showList.currentItem ? (showList.currentItem.titleValue || "") : ""
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
                    source: showList.currentItem ? (showList.currentItem.posterLocalValue || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.65)
                    visible: status === Image.Ready
                             && showList.currentItem
                             && showList.currentItem.posterLocalValue !== ""
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
                            label: "Year",
                            value: (showList.currentItem && showList.currentItem.yearValue > 0)
                                   ? String(showList.currentItem.yearValue) : ""
                        },
                        {
                            label: "Score",
                            value: showList.currentItem
                                   ? showListView._formatRating(showList.currentItem.audienceRatingValue)
                                   : ""
                        },
                        {
                            label: "Seasons",
                            value: (showList.currentItem && showList.currentItem.childCountValue > 0)
                                   ? String(showList.currentItem.childCountValue) : ""
                        },
                        {
                            label: "Episodes",
                            value: (showList.currentItem && showList.currentItem.leafCountValue > 0)
                                   ? (showList.currentItem.viewedLeafCountValue + "/"
                                      + showList.currentItem.leafCountValue + " watched")
                                   : ""
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
        }

        // ── Right panel: show list (55% width) ────────────────────────────────
        ListView {
            id: showList

            anchors {
                top: parent.top
                left: leftPanel.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(64)
                rightMargin: root.vpx(16)
            }

            model: plex ? plex.showsModel : null
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast

            // ── Infinite scroll ──────────────────────────────────────────────
            onCurrentIndexChanged: {
                var threshold = showList.count - 8
                if (showList.count > 0 && showList.currentIndex >= threshold) {
                    plex.loadMoreShows()
                }
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = showList.currentItem
                    if (item) {
                        showListView.showSelected(item.ratingKeyValue)
                    }
                } else if (keys.isContext1(event)) {
                    event.accepted = true
                    var item = showList.currentItem
                    if (item) {
                        plex.toggleMyList(item.ratingKeyValue, item.titleValue, "show",
                                          item.posterLocalValue, "")
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    showListView.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    sortFilterOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    var mdl = plex ? plex.showsModel : null
                    showList.currentIndex = JumpHelper.jumpIndex(
                        showList.count, showList.currentIndex, showListView._currentSort,
                        function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    var mdl2 = plex ? plex.showsModel : null
                    showList.currentIndex = JumpHelper.jumpIndex(
                        showList.count, showList.currentIndex, showListView._currentSort,
                        function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                    )
                }
            }

            // ── Show row delegate ────────────────────────────────────────────
            delegate: FocusScope {
                id: rowRoot

                // Expose model values so the left panel and key handler can read them.
                readonly property string ratingKeyValue: model.ratingKey
                readonly property string titleValue: model.title || ""
                readonly property int yearValue: model.year || 0
                readonly property string posterLocalValue: model.posterLocal || ""
                readonly property real audienceRatingValue: model.audienceRating || 0
                readonly property int childCountValue: model.childCount || 0
                readonly property int leafCountValue: model.leafCount || 0
                readonly property int viewedLeafCountValue: model.viewedLeafCount || 0

                width: showList.width
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

                // Show title + year (left-aligned)
                Text {
                    id: titleLabel

                    anchors {
                        left: parent.left
                        right: progressLabel.left
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(8)
                    }
                    text: {
                        var t = model.title || ""
                        var y = model.year || 0
                        return y > 0 ? t + " (" + y + ")" : t
                    }
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                }

                // Episode progress (right-aligned): "8/12"
                Text {
                    id: progressLabel

                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        rightMargin: root.vpx(12)
                    }
                    text: model.leafCount > 0
                          ? model.viewedLeafCount + "/" + model.leafCount
                          : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }

                // Focus ring — visible when this row is current and list has focus
                FocusRing {
                    visible: rowRoot.ListView.isCurrentItem && showList.activeFocus
                }
            }
        }

        // ── Empty state (centered in full content area) ───────────────────────
        // Shown when the list has no items and not loading.
        Text {
            anchors.centerIn: parent
            visible: showList.count === 0 && !showListView._loading
            text: "No shows found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Sort/Filter/View overlay ──────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Navigation:
    //   Left/Right moves between options in the focused section.
    //   Up/Down moves between sections (Sort → Genre → View).
    //   A (Return) applies the selection.
    //   B (Escape) or Y dismisses without changing.
    FocusScope {
        id: sortFilterOverlay

        anchors.fill: parent
        visible: false
        enabled: visible

        // 0 = sort row, 1 = genre list, 2 = view row
        property int _section: 0
        // Index within sort options
        property int _sortIndex: 0
        // Index within genre list (0 = "All")
        property int _genreIndex: 0
        // Index within view options (0 = Grid, 1 = List)
        property int _viewIndex: 0
        // Genres loaded from backend
        property var _genres: []

        readonly property var _sortOptions: [
            { key: "az",        label: "A-Z" },
            { key: "za",        label: "Z-A" },
            { key: "recent",    label: "Recent" },
            { key: "year_desc", label: "Year ↓" },
            { key: "year_asc",  label: "Year ↑" },
            { key: "rating",    label: "Rating" }
        ]

        function open() {
            // Sync sort selection to current state
            var sortKeys = ["az", "za", "recent", "year_desc", "year_asc", "rating"]
            var si = sortKeys.indexOf(showListView._currentSort)
            _sortIndex = si >= 0 ? si : 0

            // Load genres
            _genres = plex.getShowGenres()

            // Sync genre selection
            _genreIndex = 0
            if (showListView._currentGenreKey !== "") {
                for (var i = 0; i < _genres.length; i++) {
                    if (_genres[i].key === showListView._currentGenreKey) {
                        _genreIndex = i + 1  // +1 for "All" at index 0
                        break
                    }
                }
            }

            // Sync view selection
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(showListView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0

            _section = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            showList.forceActiveFocus()
        }

        // ── Backdrop ─────────────────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: "#000000"
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
            // Height: title + sort row + genre flow + view row + padding
            // Use implicit height from content so wrapped genres don't clip
            height: viewRow.y + viewRow.height + root.vpx(16)
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
                text: "Sort / Filter"
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
                text: keys.useGamepadLabels ? keys.cancelLabel + " / " + keys.context2Label + "  Close" : "Esc / F2  Close"
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
                id: sortLabel
                anchors {
                    top: divider.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(8)
                }
                text: "Sort"
                color: sortFilterOverlay._section === 0 ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            // ── Sort options row ──────────────────────────────────────────────
            Row {
                id: sortOptionsRow
                anchors {
                    top: sortLabel.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(4)
                }
                spacing: root.vpx(6)

                Repeater {
                    model: sortFilterOverlay._sortOptions

                    delegate: Rectangle {
                        width: root.vpx(72)
                        height: root.vpx(32)
                        color: {
                            var isFocused = sortFilterOverlay._section === 0
                                         && sortFilterOverlay._sortIndex === index
                            return isFocused ? Theme.colorPrimary : "transparent"
                        }
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(6)
                                verticalCenter: parent.verticalCenter
                            }
                            text: {
                                var isActive = modelData.key === showListView._currentSort
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 0
                                             && sortFilterOverlay._sortIndex === index
                                return isFocused ? "#ffffff" : Theme.colorText
                            }
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        }
                    }
                }
            }

            // ── Genre section label ───────────────────────────────────────────
            Text {
                id: genreLabel
                anchors {
                    top: sortOptionsRow.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(10)
                }
                text: "Genre"
                color: sortFilterOverlay._section === 1 ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            // ── Genre list (wrapping flow) ────────────────────────────────────
            Flow {
                id: genreRow
                anchors {
                    top: genreLabel.bottom
                    left: parent.left
                    right: parent.right
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                    topMargin: root.vpx(4)
                }
                spacing: root.vpx(6)

                // "All" option
                Rectangle {
                    width: root.vpx(60)
                    height: root.vpx(28)
                    color: {
                        var isFocused = sortFilterOverlay._section === 1
                                     && sortFilterOverlay._genreIndex === 0
                        return isFocused ? Theme.colorPrimary : "transparent"
                    }
                    radius: root.vpx(Theme.focusRingRadius)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }

                    Text {
                        anchors {
                            left: parent.left
                            leftMargin: root.vpx(6)
                            verticalCenter: parent.verticalCenter
                        }
                        text: (showListView._currentGenreKey === "" ? "✓ " : "") + "All"
                        color: {
                            var isFocused = sortFilterOverlay._section === 1
                                         && sortFilterOverlay._genreIndex === 0
                            return isFocused ? "#ffffff" : Theme.colorText
                        }
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    }
                }

                Repeater {
                    model: sortFilterOverlay._genres

                    delegate: Rectangle {
                        width: root.vpx(90)
                        height: root.vpx(28)
                        color: {
                            var isFocused = sortFilterOverlay._section === 1
                                         && sortFilterOverlay._genreIndex === (index + 1)
                            return isFocused ? Theme.colorPrimary : "transparent"
                        }
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(6)
                                verticalCenter: parent.verticalCenter
                            }
                            text: {
                                var isActive = modelData.key === showListView._currentGenreKey
                                return (isActive ? "✓ " : "") + modelData.title
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 1
                                             && sortFilterOverlay._genreIndex === (index + 1)
                                return isFocused ? "#ffffff" : Theme.colorText
                            }
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            elide: Text.ElideRight
                            width: parent.width - root.vpx(12)
                        }
                    }
                }
            }

            // ── View section label ────────────────────────────────────────────
            Text {
                id: viewLabel
                anchors {
                    top: genreRow.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(10)
                }
                text: "View"
                color: sortFilterOverlay._section === 2 ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            // ── View options row ──────────────────────────────────────────────
            Row {
                id: viewRow
                anchors {
                    top: viewLabel.bottom
                    left: parent.left
                    leftMargin: root.vpx(16)
                    topMargin: root.vpx(4)
                }
                spacing: root.vpx(6)

                Repeater {
                    model: [
                        { key: "grid", label: "Grid" },
                        { key: "list", label: "List" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(72)
                        height: root.vpx(32)
                        color: {
                            var isFocused = sortFilterOverlay._section === 2
                                         && sortFilterOverlay._viewIndex === index
                            return isFocused ? Theme.colorPrimary : "transparent"
                        }
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(6)
                                verticalCenter: parent.verticalCenter
                            }
                            text: {
                                var isActive = modelData.key === showListView._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 2
                                             && sortFilterOverlay._viewIndex === index
                                return isFocused ? "#ffffff" : Theme.colorText
                            }
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        }
                    }
                }
            }
        }

        // ── Key handling ─────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            var sortCount = sortFilterOverlay._sortOptions.length
            // +1 for "All"
            var genreCount = sortFilterOverlay._genres.length + 1
            var viewCount = 2

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortFilterOverlay.close()

            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (sortFilterOverlay._section > 0)
                    sortFilterOverlay._section -= 1

            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (sortFilterOverlay._section < 2)
                    sortFilterOverlay._section += 1

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortFilterOverlay._section === 0) {
                    if (sortFilterOverlay._sortIndex > 0)
                        sortFilterOverlay._sortIndex -= 1
                } else if (sortFilterOverlay._section === 1) {
                    if (sortFilterOverlay._genreIndex > 0)
                        sortFilterOverlay._genreIndex -= 1
                } else {
                    if (sortFilterOverlay._viewIndex > 0)
                        sortFilterOverlay._viewIndex -= 1
                }

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortFilterOverlay._section === 0) {
                    if (sortFilterOverlay._sortIndex < sortCount - 1)
                        sortFilterOverlay._sortIndex += 1
                } else if (sortFilterOverlay._section === 1) {
                    if (sortFilterOverlay._genreIndex < genreCount - 1)
                        sortFilterOverlay._genreIndex += 1
                } else {
                    if (sortFilterOverlay._viewIndex < viewCount - 1)
                        sortFilterOverlay._viewIndex += 1
                }

            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (sortFilterOverlay._section === 0) {
                    // Apply sort — dismiss overlay so user sees list with loading indicator
                    var newSort = sortFilterOverlay._sortOptions[sortFilterOverlay._sortIndex].key
                    showListView._currentSort = newSort
                    showListView._loading = true
                    sortFilterOverlay.close()
                    plex.sortShows(newSort)
                    if (settings) settings.setSortPlexShows(newSort)
                } else if (sortFilterOverlay._section === 1) {
                    // Apply genre filter
                    sortFilterOverlay.close()
                    if (sortFilterOverlay._genreIndex === 0) {
                        // "All" — clear filter
                        showListView._currentGenreKey = ""
                        showListView._currentGenreTitle = ""
                        showListView._loading = true
                        plex.filterShowsByGenre("")
                        if (settings) settings.setFilterPlexShowGenre("")
                    } else {
                        var gi = sortFilterOverlay._genreIndex - 1
                        var genre = sortFilterOverlay._genres[gi]
                        showListView._currentGenreKey = genre.key
                        showListView._currentGenreTitle = genre.title
                        showListView._loading = true
                        plex.filterShowsByGenre(genre.key)
                        if (settings) settings.setFilterPlexShowGenre(genre.key)
                    }
                } else {
                    // Apply view mode
                    var viewKeys = ["grid", "list"]
                    var newView = viewKeys[sortFilterOverlay._viewIndex]
                    if (newView !== showListView._viewMode) {
                        // View mode is changing — hide overlay but don't grab focus locally.
                        // WatchScreen will route focus to the newly visible view.
                        sortFilterOverlay.visible = false
                        if (settings) settings.setWatchViewMode(newView)
                        showListView.viewModeChanged(newView)
                    } else {
                        // Same view mode — close normally (focus stays local).
                        sortFilterOverlay.close()
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) {
            var savedSort = settings.sortPlexShows
            var savedGenre = settings.filterPlexShowGenre
            if (savedSort) {
                _currentSort = savedSort
                _loading = true
                plex.sortShows(savedSort)
            }
            if (savedGenre) {
                _currentGenreKey = savedGenre
                _loading = true
                plex.filterShowsByGenre(savedGenre)
            }
            // Do NOT overwrite _viewMode — it is set by WatchScreen.
        }
    }
}
