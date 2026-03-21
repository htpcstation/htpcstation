import QtQuick
import ".."
import "../components"

// Watch section screen — Plex library browser.
//
// Three views:
//   "libraries" — vertical list of Plex libraries + Continue Watching
//   "content"   — movie grid (PlexMovieGrid) or show grid (PlexShowGrid)
//   "detail"    — movie detail view (PlexMovieDetail) or show detail (PlexShowDetail)
//
// Focus flow:
//   Enter WatchScreen → libraryList gets focus (after plex.refresh())
//   Up/Down           — navigate library list
//   A (Return)        — select library → switch to "content" view
//   B (Escape)        — from "libraries": emit back() to return to tab bar
//                       from "content":   return to "libraries" view
//                       from "detail":    return to "content" view
FocusScope {
    id: watchScreen

    // Emit when B (Escape) is pressed from the library list so HomeScreen can
    // return focus to the tab bar.
    signal back()

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "libraries", "content", or "detail"
    property string currentView: "libraries"

    // Title of the currently selected library (set when a library is chosen).
    property string selectedLibraryTitle: ""

    // Section key of the currently selected library.
    property string selectedSectionKey: ""

    // Type of the currently selected library ("movie", "show", "ondeck").
    property string selectedLibraryType: ""

    // ratingKey of the movie selected for detail view.
    property string selectedRatingKey: ""

    // Index of the selected movie in the movies model (for prev/next navigation).
    property int selectedMovieIndex: -1

    // Full movie data dict for the detail view (populated when entering detail).
    property var selectedMovieData: ({})

    // ratingKey of the show selected for detail view.
    property string selectedShowRatingKey: ""

    // Track whether we have already called plex.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // Set to true once plex.availableChanged fires after a refresh, so we can
    // distinguish "still loading" from "finished but unavailable".
    property bool _availabilityKnown: false

    // JS array built from plex.getLibraryList() — used as the ListView model.
    property var _libraryEntries: []

    Connections {
        target: plex
        function onAvailableChanged() { watchScreen._availabilityKnown = true }
        function onLibrariesModelChanged() { watchScreen._libraryEntries = plex.getLibraryList() }
        function onOnDeckModelChanged() { watchScreen._libraryEntries = plex.getLibraryList() }
    }

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_refreshed || _libraryEntries.length === 0) {
                _refreshed = true
                _availabilityKnown = false
                plex.refresh()
            }
            _routeFocus()
        }
    }

    function _routeFocus() {
        if (currentView === "libraries") {
            libraryList.forceActiveFocus()
        } else if (currentView === "content") {
            if (selectedLibraryType === "movie") {
                movieGrid.forceActiveFocus()
            } else if (selectedLibraryType === "show") {
                showGrid.forceActiveFocus()
            } else {
                contentPlaceholder.forceActiveFocus()
            }
        } else if (currentView === "detail") {
            if (selectedLibraryType === "movie") {
                movieDetail.forceActiveFocus()
            } else if (selectedLibraryType === "show") {
                showDetail.forceActiveFocus()
            }
        }
    }

    // ── Library list ─────────────────────────────────────────────────────────
    Item {
        id: libraryListArea

        anchors.fill: parent
        visible: watchScreen.currentView === "libraries"

        // Loading indicator — shown immediately after refresh() is called,
        // before any data has arrived.
        Text {
            anchors.centerIn: parent
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            visible: watchScreen._refreshed
                     && watchScreen._libraryEntries.length === 0
                     && !watchScreen._availabilityKnown
        }

        // Server unavailable message — shown once the availability check
        // completes and the server is unreachable.
        Text {
            anchors.centerIn: parent
            text: "Plex server unavailable" + (plex.serverUrl ? " (" + plex.serverUrl + ")" : "")
            color: Theme.colorPrimary
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            visible: watchScreen._availabilityKnown
                     && !plex.available
                     && watchScreen._libraryEntries.length === 0
        }

        // The library list itself.
        // "Plex" is shown as a non-selectable header; library items are
        // indented below it.  Since Plex is the only service, it is always
        // auto-expanded.
        Column {
            id: libraryListColumn

            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(32)
            }

            // ── "Plex" service header (non-selectable) ────────────────────────
            Item {
                id: plexHeader

                width: parent.width
                height: root.vpx(48)

                Text {
                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(8)
                        verticalCenter: parent.verticalCenter
                    }
                    text: "Plex"
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: true
                }

                // Subtle separator below the header
                Rectangle {
                    anchors {
                        left: parent.left
                        right: parent.right
                        bottom: parent.bottom
                        leftMargin: root.vpx(8)
                        rightMargin: root.vpx(8)
                    }
                    height: root.vpx(1)
                    color: Theme.colorPrimary
                    opacity: 0.4
                }
            }

            // ── Library entries (indented under "Plex") ───────────────────────
            ListView {
                id: libraryList

                width: parent.width
                height: parent.height - plexHeader.height

                clip: true
                keyNavigationEnabled: true
                focus: true
                highlightMoveDuration: Theme.animDurationFast

                // Use the JS array built from plex.getLibraryList().
                model: watchScreen._libraryEntries

                Keys.onPressed: (event) => {
                    if (keys.isAccept(event)) {
                        event.accepted = true
                        if (currentItem) {
                            watchScreen.selectedLibraryTitle = currentItem.entryTitle
                            watchScreen.selectedSectionKey = currentItem.entrySectionKey
                            watchScreen.selectedLibraryType = currentItem.entryType
                            plex.selectLibrary(currentItem.entrySectionKey)
                            watchScreen.currentView = "content"
                        }
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        watchScreen.back()
                    }
                }

                delegate: FocusScope {
                    id: delegateRoot

                    // Expose the entry title, section key, and type so the ListView
                    // key handler can read them.
                    readonly property string entryTitle: modelData.title
                    readonly property string entrySectionKey: modelData.sectionKey
                    readonly property string entryType: modelData.type

                    width: libraryList.width
                    height: root.vpx(64)

                    // Highlight background for the focused item
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: delegateRoot.ListView.isCurrentItem ? 1.0 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on opacity {
                            NumberAnimation { duration: Theme.animDurationFast }
                        }
                    }

                    // Indentation indicator
                    Text {
                        anchors {
                            left: parent.left
                            leftMargin: root.vpx(16)
                            verticalCenter: parent.verticalCenter
                        }
                        text: "▸"
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        opacity: 0.5
                    }

                    // Library / section title
                    Text {
                        anchors {
                            left: parent.left
                            leftMargin: root.vpx(40)
                            verticalCenter: parent.verticalCenter
                        }
                        text: modelData.title
                        color: modelData.type === "ondeck" ? Theme.colorPrimary : Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    }

                    // Item count (right-aligned), shown when available
                    Text {
                        anchors {
                            right: parent.right
                            rightMargin: root.vpx(16)
                            verticalCenter: parent.verticalCenter
                        }
                        text: modelData.count > 0 ? modelData.count : ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                    }

                    // Focus ring — visible when this delegate is the current item
                    FocusRing {
                        visible: delegateRoot.ListView.isCurrentItem && libraryList.activeFocus
                    }

                    // Make the delegate the current item when clicked/tapped
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            libraryList.currentIndex = index
                            libraryList.forceActiveFocus()
                        }
                        onDoubleClicked: {
                            libraryList.currentIndex = index
                            watchScreen.selectedLibraryTitle = modelData.title
                            watchScreen.selectedSectionKey = modelData.sectionKey
                            watchScreen.selectedLibraryType = modelData.type
                            plex.selectLibrary(modelData.sectionKey)
                            watchScreen.currentView = "content"
                        }
                    }
                }
            }
        }
    }

    // ── Movie grid (task 017) ─────────────────────────────────────────────────
    PlexMovieGrid {
        id: movieGrid

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "movie"
        focus: false

        systemName: watchScreen.selectedLibraryTitle

        onMovieSelected: (ratingKey, index) => {
            watchScreen.selectedRatingKey = ratingKey
            watchScreen.selectedMovieIndex = index
            watchScreen.selectedMovieData = plex.getMovie(ratingKey)
            watchScreen.currentView = "detail"
        }

        onBack: {
            watchScreen.currentView = "libraries"
        }
    }

    // ── Movie detail view (task 017) ──────────────────────────────────────────
    PlexMovieDetail {
        id: movieDetail

        anchors.fill: parent
        visible: watchScreen.currentView === "detail"
                 && watchScreen.selectedLibraryType === "movie"
        focus: false

        movieData: watchScreen.selectedMovieData

        onBack: {
            watchScreen.currentView = "content"
        }

        onPlay: (ratingKey) => {
            plex.launchContent(ratingKey)
        }

        onNavigatePrev: {
            if (watchScreen.selectedMovieIndex > 0) {
                watchScreen.selectedMovieIndex--
                var rk = plex.getMovieRatingKeyAt(watchScreen.selectedMovieIndex)
                if (rk) {
                    watchScreen.selectedRatingKey = rk
                    watchScreen.selectedMovieData = plex.getMovie(rk)
                }
            }
        }

        onNavigateNext: {
            var count = plex.moviesCount()
            if (watchScreen.selectedMovieIndex < count - 1) {
                watchScreen.selectedMovieIndex++
                var rk = plex.getMovieRatingKeyAt(watchScreen.selectedMovieIndex)
                if (rk) {
                    watchScreen.selectedRatingKey = rk
                    watchScreen.selectedMovieData = plex.getMovie(rk)
                }
            }
        }
    }

    // ── Show grid (task 018) ──────────────────────────────────────────────────
    PlexShowGrid {
        id: showGrid

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "show"
        focus: false

        systemName: watchScreen.selectedLibraryTitle

        onShowSelected: (ratingKey) => {
            watchScreen.selectedShowRatingKey = ratingKey
            watchScreen.currentView = "detail"
        }

        onBack: {
            watchScreen.currentView = "libraries"
        }
    }

    // ── Show detail view (task 018) ───────────────────────────────────────────
    PlexShowDetail {
        id: showDetail

        anchors.fill: parent
        visible: watchScreen.currentView === "detail"
                 && watchScreen.selectedLibraryType === "show"
        focus: false

        showRatingKey: watchScreen.selectedShowRatingKey

        onBack: {
            watchScreen.currentView = "content"
        }

        onPlayEpisode: (ratingKey) => {
            plex.launchContent(ratingKey)
        }
    }

    // ── Content placeholder (non-movie, non-show libraries) ───────────────────
    FocusScope {
        id: contentPlaceholder

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType !== "movie"
                 && watchScreen.selectedLibraryType !== "show"
        focus: false

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                watchScreen.currentView = "libraries"
            }
        }

        Text {
            anchors.centerIn: parent
            text: watchScreen.selectedLibraryTitle
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeTitle)
        }

        FocusRing {}
    }
}
