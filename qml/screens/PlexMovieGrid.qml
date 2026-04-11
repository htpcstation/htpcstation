import QtQuick
import ".."
import "../components"
import "../helpers/JumpHelper.js" as JumpHelper

// Plex movie poster grid — shows a scrollable grid of movie posters.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for a movie library.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits movieSelected(ratingKey).
//   B (Escape) → emits back() so WatchScreen can return to the library list.
//   Y (2)      → opens the sort/filter overlay panel.
//
// Infinite scroll:
//   When the focused index approaches the end of the loaded list,
//   plex.loadMoreMovies() is called to fetch the next page.
FocusScope {
    id: movieGridView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on a movie cell.
    // ratingKey is the Plex ratingKey for the selected movie.
    signal movieSelected(string ratingKey, int index)

    // Emitted when the user changes the view mode via the sort/filter overlay.
    signal viewModeChanged(string mode)

    // Display name of the currently selected library (set by WatchScreen).
    property string systemName: ""

    // Section key for per-section sort/genre restore (set by WatchScreen).
    property string sectionKey: ""

    // View mode ("grid" or "list") — set by WatchScreen; do not overwrite in onCompleted
    property string _viewMode: "grid"

    // ── Sort/filter state (mirrors backend state for display) ──────────────────
    property string _currentSort: ""
    property string _currentGenreKey: ""
    property string _currentGenreTitle: ""

    onSectionKeyChanged: {
        if (!plex || !sectionKey) return
        _currentSort = plex.getSectionSort(sectionKey)
        _currentGenreKey = plex.getSectionGenre(sectionKey)
        _currentGenreTitle = ""   // title resolved later in onGenresReady
    }

    // True while a sort/filter re-fetch is in progress
    property bool _loading: false

    // Clear loading flag when the model is refreshed
    Connections {
        target: plex
        function onMoviesModelChanged() {
            movieGridView._loading = false
        }
        function onSectionLoadFailed() {
            movieGridView._loading = false
        }
        function onGenresReady(sectionKey, genres) {
            sortFilterOverlay._genres = genres
            // Sync genre selection index
            sortFilterOverlay._genreIndex = 0
            if (movieGridView._currentGenreKey !== "") {
                for (var i = 0; i < genres.length; i++) {
                    if (genres[i].key === movieGridView._currentGenreKey) {
                        sortFilterOverlay._genreIndex = i + 1
                        movieGridView._currentGenreTitle = genres[i].title
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

    // ── Cell dimensions (design-grid px, scaled via vpx) ─────────────────────
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
            text: "◀  " + movieGridView.systemName
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
                if (movieGridView._currentSort !== "")
                    parts.push("Sort: " + movieGridView._sortLabel)
                if (movieGridView._currentGenreTitle !== "")
                    parts.push("Genre: " + movieGridView._currentGenreTitle)
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

    // ── Movie grid ────────────────────────────────────────────────────────────
    GridView {
        id: movieGrid

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: plex ? plex.moviesModel : null
        clip: true
        focus: true

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(movieGridView._targetCellW + movieGridView._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(movieGridView._targetCellW + movieGridView._cellSpacing)
        cellHeight: root.vpx(movieGridView._cellH + movieGridView._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        // ── Infinite scroll ──────────────────────────────────────────────────
        onCurrentIndexChanged: {
            var threshold = movieGrid.count - movieGrid._columns * 2
            if (movieGrid.count > 0 && movieGrid.currentIndex >= threshold) {
                plex.loadMoreMovies()
            }
        }

        Keys.onPressed: (event) => {
            if (keys.isContext2(event)) {
                event.accepted = true
                sortFilterOverlay.open()
            } else if (keys.isContext1(event)) {
                event.accepted = true
                var item = movieGrid.currentItem
                if (item) {
                    plex.toggleMyList(item.itemRatingKey, item.itemTitle, "movie",
                                      item.itemPosterLocal, "")
                }
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var item = movieGrid.currentItem
                if (item) {
                    movieGridView.movieSelected(item.movieRatingKey, movieGrid.currentIndex)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                movieGridView.back()
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                var mdl = plex ? plex.moviesModel : null
                movieGrid.currentIndex = JumpHelper.jumpIndex(
                    movieGrid.count, movieGrid.currentIndex, movieGridView._currentSort,
                    function(i) { return mdl ? mdl.titleAt(i) : "" }, 1
                )
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                var mdl2 = plex ? plex.moviesModel : null
                movieGrid.currentIndex = JumpHelper.jumpIndex(
                    movieGrid.count, movieGrid.currentIndex, movieGridView._currentSort,
                    function(i) { return mdl2 ? mdl2.titleAt(i) : "" }, -1
                )
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: movieGrid.count === 0 && !movieGridView._loading && !plex.moviesLoading
            text: "No movies found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Loading indicator — shown while a sort/filter re-fetch is in progress
        Text {
            anchors.centerIn: parent
            visible: movieGridView._loading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Movie tile delegate ───────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose ratingKey so the key handler can read it.
            readonly property string movieRatingKey: model.ratingKey
            // Expose additional fields for My List toggle
            readonly property string itemRatingKey: model.ratingKey
            readonly property string itemTitle: model.title || ""
            readonly property string itemPosterLocal: model.posterLocal || ""

            // Cache My List status at creation time (isInMyList reads from disk)
            property bool _inMyList: false
            Component.onCompleted: {
                if (plex) _inMyList = plex.isInMyList(model.ratingKey)
            }

            width: movieGrid.cellWidth
            height: movieGrid.cellHeight

            z: tileRoot.GridView.isCurrentItem && movieGrid.activeFocus ? 1 : 0

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(movieGridView._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                scale: tileRoot.GridView.isCurrentItem && movieGrid.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && movieGrid.activeFocus ? 0.15 : 0.0

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
                    // Poster takes ~80% of the card height (portrait 2:3 ratio)
                    height: Math.round(parent.height * 0.80)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.posterLocal === ""

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
                        source: model.posterLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(movieGridView._targetCellW)
                        sourceSize.height: Math.round(root.vpx(movieGridView._cellH) * 0.80)
                        visible: status === Image.Ready && model.posterLocal !== ""
                        clip: true
                    }
                }

                // ── Title label ───────────────────────────────────────────────
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

                // ── Year label ────────────────────────────────────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.year > 0 ? "(" + model.year + ")" : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
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
                    visible: tileRoot.GridView.isCurrentItem && movieGrid.activeFocus
                }
            }
        }
    }

    // ── Sort/Filter overlay ───────────────────────────────────────────────────
    //
    // A semi-transparent panel that slides in from the top when Y is pressed.
    // Navigation:
    //   Left/Right moves between sort options (top row).
    //   Up/Down moves between sort row and genre list.
    //   A (Return) applies the selection.
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
            // Sync selection to current state
            var sortKeys = ["az", "za", "recent", "year_desc", "year_asc", "rating"]
            var si = sortKeys.indexOf(movieGridView._currentSort)
            _sortIndex = si >= 0 ? si : 0

            // Fetch genres asynchronously — onGenresReady populates _genres
            plex.fetchGenres()

            // Sync view selection
            var viewKeys = ["grid", "list"]
            var vi = viewKeys.indexOf(movieGridView._viewMode)
            _viewIndex = vi >= 0 ? vi : 0

            _section = 0
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            movieGrid.forceActiveFocus()
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
            // Height: title + sort row + genre flow + view row + padding
            // Use implicit height from content so wrapped genres don't clip
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
                                var isActive = modelData.key === movieGridView._currentSort
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
                        text: (movieGridView._currentGenreKey === "" ? "✓ " : "") + "All"
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
                                var isActive = modelData.key === movieGridView._currentGenreKey
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
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        { key: "grid", label: "Grid" },
                        { key: "list", label: "List" }
                    ]

                    delegate: Rectangle {
                        width: root.vpx(80)
                        height: root.vpx(32)
                        color: sortFilterOverlay._section === 2
                               && sortFilterOverlay._viewIndex === index
                               ? Theme.colorPrimary
                               : "transparent"
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
                                var isActive = modelData.key === movieGridView._viewMode
                                return (isActive ? "✓ " : "") + modelData.label
                            }
                            color: sortFilterOverlay._section === 2
                                   && sortFilterOverlay._viewIndex === index
                                   ? Theme.colorOverlayText
                                   : Theme.colorText
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
                movieGridView._currentSort = newSort
                movieGridView._loading = true
                plex.sortMovies(newSort)
                if (settings) settings.setSortPlexMovies(newSort)

                // Apply genre
                if (sortFilterOverlay._genreIndex === 0) {
                    movieGridView._currentGenreKey = ""
                    movieGridView._currentGenreTitle = ""
                    plex.filterByGenre("")
                    if (settings) settings.setFilterPlexMovieGenre("")
                } else {
                    var genre = sortFilterOverlay._genres[sortFilterOverlay._genreIndex - 1]
                    movieGridView._currentGenreKey = genre.key
                    movieGridView._currentGenreTitle = genre.title
                    plex.filterByGenre(genre.key)
                    if (settings) settings.setFilterPlexMovieGenre(genre.key)
                }

                // Apply view mode
                var viewKeys = ["grid", "list"]
                var newView = viewKeys[sortFilterOverlay._viewIndex]
                if (newView !== movieGridView._viewMode) {
                    sortFilterOverlay.visible = false
                    if (settings) settings.setWatchViewMode(newView)
                    movieGridView.viewModeChanged(newView)
                } else {
                    sortFilterOverlay.close()
                }
            }
        }
    }

    // ── Loading overlay ───────────────────────────────────────────────────────
    LoadingOverlay { loading: plex ? plex.moviesLoading : false }
}
