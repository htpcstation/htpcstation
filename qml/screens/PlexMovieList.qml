import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Plex movie list view — split-panel browse view for Plex movie libraries.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for a movie library
//   (list mode).
//   Up/Down navigate the list natively.
//   A (Return)  → emits movieSelected(ratingKey, index)
//   B (Escape)  → emits back()
//   Y (2)       → opens the sort/filter/view overlay panel
//
// Infinite scroll:
//   When the focused index approaches the end of the loaded list,
//   plex.loadMoreMovies() is called to fetch the next page.
FocusScope {
    id: movieListView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on a movie row.
    // ratingKey is the Plex ratingKey for the selected movie.
    signal movieSelected(string ratingKey, int index)

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

    // View mode ("grid" or "list") — set by WatchScreen; do not overwrite in onCompleted
    property string _viewMode: "grid"

    // Clear loading flag when the model is refreshed
    Connections {
        target: plex
        function onMoviesModelChanged() {
            movieListView._loading = false
        }
        function onSectionLoadFailed() {
            movieListView._loading = false
        }
        function onGenresReady(sectionKey, genres) {
            sortFilterOverlay._genres = genres
            sortFilterOverlay._genreIndex = 0
            if (movieListView._currentGenreKey !== "") {
                for (var i = 0; i < genres.length; i++) {
                    if (genres[i].key === movieListView._currentGenreKey) {
                        sortFilterOverlay._genreIndex = i + 1
                        break
                    }
                }
            }
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

    // ── Helper: format duration from milliseconds to "Xh Ym" ─────────────────
    function _formatDuration(ms) {
        var totalMin = Math.floor(ms / 60000)
        var h = Math.floor(totalMin / 60)
        var m = totalMin % 60
        return h > 0 ? h + "h " + m + "m" : m + "m"
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
            text: "◀  " + movieListView.systemName
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
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
                if (movieListView._currentSort !== "")
                    parts.push("Sort: " + movieListView._sortLabel)
                if (movieListView._currentGenreTitle !== "")
                    parts.push("Genre: " + movieListView._currentGenreTitle)
                return parts.length > 0 ? parts.join("  ·  ") : "Default order"
            }
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
                text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "1  My List"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context2Label + "  Sort / Filter" : "2  Sort / Filter"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Loading indicator — shown while a sort/filter re-fetch is in progress ─
    Text {
        anchors.centerIn: parent
        visible: movieListView._loading
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
                             || !movieList.currentItem.posterLocalValue

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
                    source: movieList.currentItem ? (movieList.currentItem.posterLocalValue || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: Math.round(leftPanel.width)
                    sourceSize.height: Math.round(leftPanel.height * 0.55)
                    visible: status === Image.Ready
                             && !!movieList.currentItem
                             && !!movieList.currentItem.posterLocalValue
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
                            label: "Score",
                            value: movieList.currentItem
                                   ? movieListView._formatRating(movieList.currentItem.audienceRatingValue)
                                   : ""
                        },
                        {
                            label: "Runtime",
                            value: movieList.currentItem && movieList.currentItem.durationValue > 0
                                   ? movieListView._formatDuration(movieList.currentItem.durationValue)
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
                interactive: false  // preview only — no scroll needed

                Text {
                    id: synopsisText

                    width: synopsisFlickable.width
                    text: movieList.currentItem ? (movieList.currentItem.summaryValue || "") : ""
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

            model: plex ? plex.moviesModel : null
            clip: true
            focus: true
            keyNavigationEnabled: true

            // Smooth highlight movement
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            // Infinite scroll + preview update
            onCurrentIndexChanged: {
                if (movieList.count > 0 && movieList.currentIndex > movieList.count - 10) {
                    plex.loadMoreMovies()
                }
            }

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = movieList.currentItem
                    if (item) {
                        movieListView.movieSelected(item.ratingKeyValue, movieList.currentIndex)
                    }
                } else if (keys.isContext1(event)) {
                    event.accepted = true
                    var item = movieList.currentItem
                    if (item) {
                        plex.toggleMyList(item.ratingKeyValue, item.titleValue, "movie",
                                          item.posterLocalValue, "")
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    movieListView.back()
                } else if (keys.isContext2(event)) {
                    event.accepted = true
                    sortFilterOverlay.open()
                } else if (keys.isPageDown(event)) {
                    event.accepted = true
                    var mdl = plex ? plex.moviesModel : null
                    movieList.currentIndex = JumpHelper.jumpIndex(
                        movieList.count, movieList.currentIndex, movieListView._currentSort,
                        function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                    )
                } else if (keys.isPageUp(event)) {
                    event.accepted = true
                    var mdl2 = plex ? plex.moviesModel : null
                    movieList.currentIndex = JumpHelper.jumpIndex(
                        movieList.count, movieList.currentIndex, movieListView._currentSort,
                        function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                    )
                }
            }

            // ── Movie row delegate ────────────────────────────────────────────
            delegate: FocusScope {
                id: rowRoot

                // Expose model data as properties so the left panel can read them
                // from movieList.currentItem.
                readonly property string ratingKeyValue: model.ratingKey || ""
                readonly property string titleValue: model.title || ""
                readonly property int yearValue: model.year || 0
                readonly property string posterLocalValue: model.posterLocal || ""
                readonly property real audienceRatingValue: model.audienceRating || 0.0
                readonly property int durationValue: model.duration || 0
                readonly property string summaryValue: model.summary || ""

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
            visible: !_loading && !plex.moviesLoading && movieList.count === 0
            text: "No movies found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Loading overlay ───────────────────────────────────────────────────────
    LoadingOverlay { loading: plex ? plex.moviesLoading : false }

    // ── Sort/Filter/View overlay ──────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Navigation:
    //   Up/Down moves between sections (sort=0, genre=1, view=2).
    //   Left/Right moves between options in the focused section.
    //   A (Return) applies all three settings together.
    //   B (Escape) or Y dismisses without changing.
    FocusScope {
        id: sortFilterOverlay

        anchors.fill: parent
        visible: false
        enabled: visible

        // 0 = sort row focused, 1 = genre list focused, 2 = view row focused
        property int _section: 0
        // Index within sort options
        property int _sortIndex: 0
        // Index within genre list (0 = "All")
        property int _genreIndex: 0
        // Index within view options (0=Grid, 1=List)
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
            var si = sortKeys.indexOf(movieListView._currentSort)
            _sortIndex = si >= 0 ? si : 0

            // Fetch genres asynchronously — onGenresReady populates _genres
            plex.fetchGenres()

            // Sync view selection
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
            // Height extends to include the view row
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
                        text: (movieListView._currentGenreKey === "" ? "✓ " : "") + "All"
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
                                var isActive = modelData.key === movieListView._currentGenreKey
                                return (isActive ? "✓ " : "") + modelData.title
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

                // Apply sort
                var newSort = sortFilterOverlay._sortOptions[sortFilterOverlay._sortIndex].key
                movieListView._currentSort = newSort
                movieListView._loading = true
                plex.sortMovies(newSort)
                if (settings) settings.setSortPlexMovies(newSort)

                // Apply genre filter
                if (sortFilterOverlay._genreIndex === 0) {
                    // "All" — clear filter
                    movieListView._currentGenreKey = ""
                    movieListView._currentGenreTitle = ""
                    plex.filterByGenre("")
                    if (settings) settings.setFilterPlexMovieGenre("")
                } else {
                    var gi = sortFilterOverlay._genreIndex - 1
                    var genre = sortFilterOverlay._genres[gi]
                    movieListView._currentGenreKey = genre.key
                    movieListView._currentGenreTitle = genre.title
                    plex.filterByGenre(genre.key)
                    if (settings) settings.setFilterPlexMovieGenre(genre.key)
                }

                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortFilterOverlay._viewIndex]
                if (newView !== movieListView._viewMode) {
                    // View mode is changing — hide overlay but don't grab focus locally.
                    // WatchScreen will route focus to the newly visible view.
                    sortFilterOverlay.visible = false
                    if (settings) settings.setWatchViewMode(newView)
                    movieListView.viewModeChanged(newView)
                } else {
                    // Same view mode — close normally (focus stays local).
                    sortFilterOverlay.close()
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) {
            var savedSort = settings.sortPlexMovies
            var savedGenre = settings.filterPlexMovieGenre
            if (savedSort) _currentSort = savedSort
            if (savedGenre) _currentGenreKey = savedGenre
            // Do NOT overwrite _viewMode — it is bound from WatchScreen.
        }
    }
}
