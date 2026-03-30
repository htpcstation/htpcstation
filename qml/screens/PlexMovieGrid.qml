import QtQuick
import ".."
import "../components"

// Plex movie poster grid — shows a scrollable grid of movie posters.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for a movie library.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits movieSelected(ratingKey).
//   B (Escape) → emits back() so WatchScreen can return to the library list.
//   Y (F2)     → opens the sort/filter overlay panel.
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

    // Display name of the currently selected library (set by WatchScreen).
    property string systemName: ""

    // ── Sort/filter state (mirrors backend state for display) ──────────────────
    property string _currentSort: ""
    property string _currentGenreKey: ""
    property string _currentGenreTitle: ""

    // True while a sort/filter re-fetch is in progress
    property bool _loading: false

    // Clear loading flag when the model is refreshed
    Connections {
        target: plex
        function onMoviesModelChanged() {
            movieGridView._loading = false
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

        // Y button hint
        Text {
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
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var item = movieGrid.currentItem
                if (item) {
                    movieGridView.movieSelected(item.movieRatingKey, movieGrid.currentIndex)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                movieGridView.back()
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: movieGrid.count === 0 && !movieGridView._loading
            text: "Loading movies..."
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

            width: movieGrid.cellWidth
            height: movieGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(movieGridView._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

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

        // 0 = sort row focused, 1 = genre list focused
        property int _section: 0
        // Index within sort options
        property int _sortIndex: 0
        // Index within genre list (0 = "All")
        property int _genreIndex: 0
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

            // Load genres
            _genres = plex.getMovieGenres()

            // Sync genre selection
            _genreIndex = 0
            if (movieGridView._currentGenreKey !== "") {
                for (var i = 0; i < _genres.length; i++) {
                    if (_genres[i].key === movieGridView._currentGenreKey) {
                        _genreIndex = i + 1  // +1 for "All" at index 0
                        break
                    }
                }
            }

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
            // Height: title + sort row + genre flow (wraps to multiple rows) + padding
            // Use implicit height from content so wrapped genres don't clip
            height: genreRow.y + genreRow.height + root.vpx(16)
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
                                var isActive = modelData.key === movieGridView._currentSort
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
                        text: (movieGridView._currentGenreKey === "" ? "✓ " : "") + "All"
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
                                var isActive = modelData.key === movieGridView._currentGenreKey
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
        }

        // ── Key handling ─────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            var sortCount = sortFilterOverlay._sortOptions.length
            // +1 for "All"
            var genreCount = sortFilterOverlay._genres.length + 1

            if (keys.isCancel(event) || keys.isContext2(event)) {
                // B or Y — dismiss without applying
                event.accepted = true
                sortFilterOverlay.close()

            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (sortFilterOverlay._section === 1)
                    sortFilterOverlay._section = 0

            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (sortFilterOverlay._section === 0)
                    sortFilterOverlay._section = 1

            } else if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (sortFilterOverlay._section === 0) {
                    if (sortFilterOverlay._sortIndex > 0)
                        sortFilterOverlay._sortIndex -= 1
                } else {
                    if (sortFilterOverlay._genreIndex > 0)
                        sortFilterOverlay._genreIndex -= 1
                }

            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (sortFilterOverlay._section === 0) {
                    if (sortFilterOverlay._sortIndex < sortCount - 1)
                        sortFilterOverlay._sortIndex += 1
                } else {
                    if (sortFilterOverlay._genreIndex < genreCount - 1)
                        sortFilterOverlay._genreIndex += 1
                }

            } else if (keys.isAccept(event)) {
                event.accepted = true
                // Dismiss overlay immediately so user sees the grid with loading indicator
                sortFilterOverlay.close()
                if (sortFilterOverlay._section === 0) {
                    // Apply sort
                    var newSort = sortFilterOverlay._sortOptions[sortFilterOverlay._sortIndex].key
                    movieGridView._currentSort = newSort
                    movieGridView._loading = true
                    plex.sortMovies(newSort)
                } else {
                    // Apply genre filter
                    if (sortFilterOverlay._genreIndex === 0) {
                        // "All" — clear filter
                        movieGridView._currentGenreKey = ""
                        movieGridView._currentGenreTitle = ""
                        movieGridView._loading = true
                        plex.filterByGenre("")
                    } else {
                        var gi = sortFilterOverlay._genreIndex - 1
                        var genre = sortFilterOverlay._genres[gi]
                        movieGridView._currentGenreKey = genre.key
                        movieGridView._currentGenreTitle = genre.title
                        movieGridView._loading = true
                        plex.filterByGenre(genre.key)
                    }
                }
            }
        }
    }
}
