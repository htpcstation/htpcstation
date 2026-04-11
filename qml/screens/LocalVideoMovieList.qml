import QtQuick
import ".."
import "../components"

// Local video movie list view — split-panel browse view for local movie libraries.
//
// Focus flow:
//   Gains focus when LocalVideosScreen switches to "videos" view (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits movieSelected(index, movieData)
//   B (Escape)  → emits back()
//   Y (2)       → opens the sort/filter/view overlay panel
FocusScope {
    id: movieListView

    // Emitted when the user presses B / Escape to return to the categories list.
    signal back()

    // Emitted when the user presses A / Return on a movie row.
    signal movieSelected(int index, var movieData)

    // Emitted when the user changes the view mode via the sort/filter overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected category (set by orchestrator).
    property string systemName: ""

    // ── Sort/filter state (mirrors backend state for display) ──────────────────
    property string _currentSort: ""
    property string _currentGenre: ""

    // View mode ("grid" or "list") — set by orchestrator; do not overwrite in onCompleted
    property string _viewMode: "list"

    // Human-readable sort label for the status bar
    readonly property string _sortLabel: {
        if (_currentSort === "az")        return "A-Z"
        if (_currentSort === "za")        return "Z-A"
        if (_currentSort === "year_desc") return "Year (Newest)"
        if (_currentSort === "year_asc")  return "Year (Oldest)"
        return "Default"
    }

    // ── Header bar + status bar ───────────────────────────────────────────────
    LibraryHeader {
        id: header
        title: movieListView.systemName
        statusText: {
            var parts = []
            if (movieListView._currentSort !== "")
                parts.push("Sort: " + movieListView._sortLabel)
            if (movieListView._currentGenre !== "")
                parts.push("Genre: " + movieListView._currentGenre)
            return parts.length > 0 ? parts.join("  ·  ") : "Default order"
        }
        rightText1: keys.useGamepadLabels ? keys.context2Label + "  Sort / Filter" : "2  Sort / Filter"
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

        opacity: (localVideos && localVideos.categoryScanning) ? 0.3 : 1.0
        Behavior on opacity {
            NumberAnimation { duration: 200; easing.type: Easing.InOutQuad }
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

            // ── Portrait poster image area (~55% of panel height) ─────────────
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
                height: Math.round(parent.height * 0.55)

                // Placeholder shown when there is no poster or while loading
                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready
                             || !movieList.currentItem
                             || !movieList.currentItem.posterPathValue

                    Text {
                        anchors.centerIn: parent
                        text: movieList.currentItem ? (movieList.currentItem.titleValue || "") : ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - root.vpx(16)
                    }
                }

                Image {
                    id: posterImage

                    anchors.fill: parent
                    source: movieList.currentItem ? (movieList.currentItem.posterPathValue || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.55)
                    visible: status === Image.Ready
                             && !!movieList.currentItem
                             && !!movieList.currentItem.posterPathValue
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
                            value: movieList.currentItem && movieList.currentItem.yearValue > 0
                                   ? String(movieList.currentItem.yearValue)
                                   : ""
                        },
                        {
                            label: "Genre",
                            value: movieList.currentItem
                                   ? (movieList.currentItem.genreValue || "")
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

            // ── Synopsis (scrollable) ─────────────────────────────────────────
            Flickable {
                id: synopsisFlickable

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
                contentHeight: synopsisText.implicitHeight
                interactive: false  // preview only

                Text {
                    id: synopsisText

                    width: synopsisFlickable.width
                    text: movieList.currentItem ? (movieList.currentItem.descriptionValue || "") : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.Wrap
                }
            }
        }

        // ── Right panel: movie list (55% width) ───────────────────────────────
        ListView {
            id: movieList

            anchors {
                top: parent.top
                left: leftPanel.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(64)
                rightMargin: root.vpx(16)
            }

            model: localVideos ? localVideos.videosModel : null
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = movieList.currentItem
                    if (item) {
                        movieListView.movieSelected(movieList.currentIndex, {
                            path:        item.pathValue,
                            title:       item.titleValue,
                            year:        item.yearValue,
                            genre:       item.genreValue,
                            description: item.descriptionValue,
                            posterPath:  item.posterPathValue
                        })
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    movieListView.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    sortFilterOverlay.open()
                }
            }

            // ── Movie row delegate ────────────────────────────────────────────
            delegate: FocusScope {
                id: rowRoot

                // Expose model data so the left panel can read them from movieList.currentItem.
                readonly property string pathValue:        model.path        || ""
                readonly property string titleValue:       model.title       || ""
                readonly property int    yearValue:        model.year        || 0
                readonly property string genreValue:       model.genre       || ""
                readonly property string descriptionValue: model.description || ""
                readonly property string posterPathValue:  model.posterPath  || ""

                width: movieList.width
                height: root.vpx(40)

                // Background highlight for the current item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: rowRoot.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: rowRoot.ListView.isCurrentItem && movieList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Title + year
                Text {
                    anchors {
                        left: parent.left
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(12)
                        rightMargin: root.vpx(12)
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

                // Focus ring — visible when this row is current and list has focus
                FocusRing {
                    visible: rowRoot.ListView.isCurrentItem && movieList.activeFocus
                }
            }
        }

        // ── Empty state (centered in full content area) ───────────────────────
        Text {
            anchors.centerIn: parent
            visible: movieList.count === 0 && (!localVideos || !localVideos.categoryScanning)
            text: "No videos found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Sort/Filter/View overlay ──────────────────────────────────────────────
    //
    // Sections: 0 = sort, 1 = genre, 2 = view
    FocusScope {
        id: sortFilterOverlay

        anchors.fill: parent
        visible: false
        enabled: visible

        // 0 = sort row focused, 1 = genre list focused, 2 = view row focused
        property int _section: 0
        property int _sortIndex: 0
        property int _genreIndex: 0
        property int _viewIndex: 0
        property var _genres: []

        readonly property var _sortOptions: [
            { key: "az",        label: "A-Z" },
            { key: "za",        label: "Z-A" },
            { key: "year_desc", label: "Year ↓" },
            { key: "year_asc",  label: "Year ↑" }
        ]

        function open() {
            var sortKeys = ["az", "za", "year_desc", "year_asc"]
            var si = sortKeys.indexOf(movieListView._currentSort)
            _sortIndex = si >= 0 ? si : 0

            _genres = localVideos ? localVideos.getVideoGenres() : []

            _genreIndex = 0
            if (movieListView._currentGenre !== "") {
                for (var i = 0; i < _genres.length; i++) {
                    if (_genres[i] === movieListView._currentGenre) {
                        _genreIndex = i + 1
                        break
                    }
                }
            }

            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(movieListView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0

            _section = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            movieList.forceActiveFocus()
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
            height: viewOptionsRow.y + viewOptionsRow.height + root.vpx(16)
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
                                var isActive = modelData.key === movieListView._currentSort
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 0
                                             && sortFilterOverlay._sortIndex === index
                                return isFocused ? Theme.colorOverlayText : Theme.colorText
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
                        text: (movieListView._currentGenre === "" ? "✓ " : "") + "All"
                        color: {
                            var isFocused = sortFilterOverlay._section === 1
                                         && sortFilterOverlay._genreIndex === 0
                            return isFocused ? Theme.colorOverlayText : Theme.colorText
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
                                var isActive = modelData === movieListView._currentGenre
                                return (isActive ? "✓ " : "") + modelData
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 1
                                             && sortFilterOverlay._genreIndex === (index + 1)
                                return isFocused ? Theme.colorOverlayText : Theme.colorText
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
                id: viewOptionsRow
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
                                var isActive = modelData.key === movieListView._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: {
                                var isFocused = sortFilterOverlay._section === 2
                                             && sortFilterOverlay._viewIndex === index
                                return isFocused ? Theme.colorOverlayText : Theme.colorText
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
            var genreCount = sortFilterOverlay._genres.length + 1
            var viewCount = 2

            if (keys.isCancel(event) || keys.isContext2(event)) {
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

                // Apply sort
                var newSort = sortFilterOverlay._sortOptions[sortFilterOverlay._sortIndex].key
                movieListView._currentSort = newSort
                if (localVideos) localVideos.sortVideos(newSort)

                // Apply genre
                if (sortFilterOverlay._genreIndex === 0) {
                    movieListView._currentGenre = ""
                    if (localVideos) localVideos.filterVideosByGenre("")
                } else {
                    var genre = sortFilterOverlay._genres[sortFilterOverlay._genreIndex - 1]
                    movieListView._currentGenre = genre
                    if (localVideos) localVideos.filterVideosByGenre(genre)
                }

                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortFilterOverlay._viewIndex]
                if (newView !== movieListView._viewMode) {
                    sortFilterOverlay.visible = false
                    if (settings) settings.setLocalVideoViewMode(newView)
                    movieListView.viewModeChanged(newView)
                } else {
                    sortFilterOverlay.close()
                }
            }
        }
    }
}
