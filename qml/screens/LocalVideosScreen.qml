import QtQuick
import ".."
import "../components"

// Local Videos screen — browse and play local video files.
//
// Views:
//   "categories"  — ListView of all configured video categories
//   "videos"      — LocalVideoMovieGrid or LocalVideoMovieList (based on _viewMode)
//   "movieDetail" — LocalVideoMovieDetail
//   "shows"       — LocalVideoShowGrid or LocalVideoShowList (based on _viewMode)
//   "showDetail"  — LocalVideoShowDetail
//
// Focus flow:
//   Enter LocalVideosScreen → categoriesList gets focus
//   A (Return)        — select item
//   B (Escape)        — go back one level; from categories emit back()
FocusScope {
    id: localVideosScreen

    // Emit when B (Escape) is pressed from the categories view so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Navigation target passed by HomeScreen when navigating from recently played.
    property var navTarget: null

    // Only process input when this screen is active.
    enabled: focus

    // Current view state
    property string currentView: "categories"
    property string _viewMode: "grid"
    property var _selectedMovieData: ({})
    property var _selectedShowData: ({})
    property int _selectedShowIndex: -1

    // Category name for the selected category
    property string _currentCategoryName: ""
    property int _selectedCategoryIndex: -1

    // Guard: navTarget navigation fires only once (on first active focus).
    property bool _navTargetApplied: false

    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: {
        if (activeFocus) {
            _routeFocus()
            if (navTarget && !_navTargetApplied) {
                _navTargetApplied = true
                if (navTarget.type === "movie" && navTarget.path) {
                    localVideosScreen._selectedMovieData = {
                        "path":        navTarget.path,
                        "title":       navTarget.title       || "",
                        "posterPath":  navTarget.poster_path || "",
                        "year":        0,
                        "genre":       "",
                        "description": ""
                    }
                    localVideosScreen.currentView = "movieDetail"
                    _routeFocus()
                } else if (navTarget.type === "show" && navTarget.show_path) {
                    localVideosScreen._selectedShowData = {
                        "name":        navTarget.show_name        || "",
                        "path":        navTarget.show_path        || "",
                        "posterPath":  navTarget.show_poster_path || "",
                        "year":        0,
                        "description": "",
                        "seasonCount": 0
                    }
                    localVideosScreen.currentView = "showDetail"
                    _routeFocus()
                }
            }
        }
    }

    Component.onCompleted: {
        if (settings) _viewMode = settings.localVideoViewMode || "grid"
    }

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "categories")
            categoriesList.forceActiveFocus()
        else if (currentView === "videos")
            (_viewMode === "grid" ? movieGrid : movieList).forceActiveFocus()
        else if (currentView === "movieDetail")
            movieDetail.forceActiveFocus()
        else if (currentView === "shows")
            (_viewMode === "grid" ? showGrid : showList).forceActiveFocus()
        else if (currentView === "showDetail")
            showDetail.forceActiveFocus()
    }

    // ── Categories header bar ────────────────────────────────────────────────
    Rectangle {
        id: categoriesHeader

        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(56)
        color: Theme.colorSecondary
        visible: localVideosScreen.currentView === "categories"

        Text {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: "Videos"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Categories ListView ───────────────────────────────────────────────────
    ListView {
        id: categoriesList

        anchors {
            top: categoriesHeader.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(16)
            rightMargin: root.vpx(16)
            bottomMargin: root.vpx(16)
        }

        model: localVideos ? localVideos.categoriesModel : null
        clip: true
        keyNavigationEnabled: true
        focus: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "categories"
        enabled: visible

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0 && currentItem) {
                    localVideos.selectCategory(currentIndex)
                    localVideosScreen._selectedCategoryIndex = currentIndex
                    localVideosScreen._currentCategoryName = currentItem.categoryName
                    if (currentItem.categoryType === "flat") {
                        localVideosScreen.currentView = "videos"
                    } else {
                        localVideosScreen.currentView = "shows"
                    }
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.back()
            }
        }

        delegate: Item {
            id: categoryDelegate

            readonly property string categoryType: model.type
            readonly property string categoryName: model.name

            width: categoriesList.width
            height: root.vpx(64)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: categoryDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: categoryDelegate.ListView.isCurrentItem && categoriesList.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            Text {
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.name
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            FocusRing {
                visible: categoryDelegate.ListView.isCurrentItem && categoriesList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    categoriesList.currentIndex = index
                    categoriesList.forceActiveFocus()
                }
                onDoubleClicked: {
                    categoriesList.currentIndex = index
                    if (localVideos) {
                        localVideos.selectCategory(index)
                        localVideosScreen._selectedCategoryIndex = index
                        localVideosScreen._currentCategoryName = model.name
                        if (model.type === "flat") {
                            localVideosScreen.currentView = "videos"
                        } else {
                            localVideosScreen.currentView = "shows"
                        }
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: categoriesList.count === 0
            text: "No video categories configured.\nAdd paths in Settings."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ── Movies grid ───────────────────────────────────────────────────────────
    LocalVideoMovieGrid {
        id: movieGrid

        anchors.fill: parent
        visible: localVideosScreen.currentView === "videos" && localVideosScreen._viewMode === "grid"
        enabled: visible

        systemName: localVideosScreen._currentCategoryName
        _viewMode: localVideosScreen._viewMode

        onMovieSelected: (index, data) => {
            localVideosScreen._selectedMovieData = data
            localVideosScreen.currentView = "movieDetail"
        }
        onViewModeChanged: (mode) => {
            localVideosScreen._viewMode = mode
            localVideosScreen._routeFocus()
        }
        onBack: localVideosScreen.currentView = "categories"
    }

    // ── Movies list ───────────────────────────────────────────────────────────
    LocalVideoMovieList {
        id: movieList

        anchors.fill: parent
        visible: localVideosScreen.currentView === "videos" && localVideosScreen._viewMode === "list"
        enabled: visible

        systemName: localVideosScreen._currentCategoryName
        _viewMode: localVideosScreen._viewMode

        onMovieSelected: (index, data) => {
            localVideosScreen._selectedMovieData = data
            localVideosScreen.currentView = "movieDetail"
        }
        onViewModeChanged: (mode) => {
            localVideosScreen._viewMode = mode
            localVideosScreen._routeFocus()
        }
        onBack: localVideosScreen.currentView = "categories"
    }

    // ── Movie detail ──────────────────────────────────────────────────────────
    LocalVideoMovieDetail {
        id: movieDetail

        anchors.fill: parent
        visible: localVideosScreen.currentView === "movieDetail"
        enabled: visible

        moviePath:        localVideosScreen._selectedMovieData.path        || ""
        movieTitle:       localVideosScreen._selectedMovieData.title       || ""
        movieYear:        localVideosScreen._selectedMovieData.year        || 0
        movieGenre:       localVideosScreen._selectedMovieData.genre       || ""
        movieDescription: localVideosScreen._selectedMovieData.description || ""
        moviePosterPath:  localVideosScreen._selectedMovieData.posterPath  || ""

        onPlay: (path) => {
            if (recentlyPlayed) {
                var art = localVideosScreen._selectedMovieData.posterPath || ""
                if (art && !art.startsWith("file://")) art = "file://" + art
                recentlyPlayed.record("localvideo",
                    localVideosScreen._selectedMovieData.title || "",
                    art,
                    {
                        "type":        "movie",
                        "path":        localVideosScreen._selectedMovieData.path  || "",
                        "title":       localVideosScreen._selectedMovieData.title || "",
                        "poster_path": localVideosScreen._selectedMovieData.posterPath || ""
                    }
                )
            }
            if (localVideos) localVideos.playVideo(path, localVideos.getResumePosition(path))
        }
        onBack: {
            if (localVideosScreen._navTargetApplied) localVideosScreen.back()
            else localVideosScreen.currentView = "videos"
        }
    }

    // ── Shows grid ────────────────────────────────────────────────────────────
    LocalVideoShowGrid {
        id: showGrid

        anchors.fill: parent
        visible: localVideosScreen.currentView === "shows" && localVideosScreen._viewMode === "grid"
        enabled: visible

        systemName: localVideosScreen._currentCategoryName
        _viewMode: localVideosScreen._viewMode

        onShowSelected: (index, data) => {
            localVideosScreen._selectedShowIndex = index
            localVideosScreen._selectedShowData = data
            if (localVideos) localVideos.selectShow(index)
            localVideosScreen.currentView = "showDetail"
        }
        onViewModeChanged: (mode) => {
            localVideosScreen._viewMode = mode
            localVideosScreen._routeFocus()
        }
        onBack: localVideosScreen.currentView = "categories"
    }

    // ── Shows list ────────────────────────────────────────────────────────────
    LocalVideoShowList {
        id: showList

        anchors.fill: parent
        visible: localVideosScreen.currentView === "shows" && localVideosScreen._viewMode === "list"
        enabled: visible

        systemName: localVideosScreen._currentCategoryName
        _viewMode: localVideosScreen._viewMode

        onShowSelected: (index, data) => {
            localVideosScreen._selectedShowIndex = index
            localVideosScreen._selectedShowData = data
            if (localVideos) localVideos.selectShow(index)
            localVideosScreen.currentView = "showDetail"
        }
        onViewModeChanged: (mode) => {
            localVideosScreen._viewMode = mode
            localVideosScreen._routeFocus()
        }
        onBack: localVideosScreen.currentView = "categories"
    }

    // ── Show detail ───────────────────────────────────────────────────────────
    LocalVideoShowDetail {
        id: showDetail

        anchors.fill: parent
        visible: localVideosScreen.currentView === "showDetail"
        enabled: visible

        showName:        localVideosScreen._selectedShowData.name        || ""
        showPosterPath:  localVideosScreen._selectedShowData.posterPath  || ""
        showYear:        localVideosScreen._selectedShowData.year        || 0
        showDescription: localVideosScreen._selectedShowData.description || ""
        showSeasonCount: localVideosScreen._selectedShowData.seasonCount || 0

        onPlayEpisode: (path) => {
            if (recentlyPlayed) {
                var art = localVideosScreen._selectedShowData.posterPath || ""
                if (art && !art.startsWith("file://")) art = "file://" + art
                recentlyPlayed.record("localvideo",
                    localVideosScreen._selectedShowData.name || "",
                    art,
                    {
                        "type":             "show",
                        "show_path":        localVideosScreen._selectedShowData.path       || "",
                        "show_name":        localVideosScreen._selectedShowData.name       || "",
                        "show_poster_path": localVideosScreen._selectedShowData.posterPath || ""
                    }
                )
            }
            if (localVideos) localVideos.playVideo(path, localVideos.getResumePosition(path))
        }
        onBack: {
            if (localVideosScreen._navTargetApplied) localVideosScreen.back()
            else localVideosScreen.currentView = "shows"
        }
    }
}
