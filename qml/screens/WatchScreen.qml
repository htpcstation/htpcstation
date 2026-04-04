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

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Track whether we have already called plex.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // Set to true once plex.availableChanged fires after a refresh, so we can
    // distinguish "still loading" from "finished but unavailable".
    property bool _availabilityKnown: false

    // JS array built from plex.getLibraryList() — used as the ListView model.
    // Filters out "artist" type libraries (Music, Audiobooks) since those
    // are accessible under the Listen tab.
    property var _libraryEntries: []

    function _getVideoLibraries() {
        var all = plex.getLibraryList()
        var filtered = []
        for (var i = 0; i < all.length; i++) {
            if (all[i].type !== "artist") filtered.push(all[i])
        }
        return filtered
    }

    // ── Resume dialog state ───────────────────────────────────────────────────
    property bool _resumeDialogVisible: false
    property string _resumeRatingKey: ""
    property int _resumeViewOffset: 0   // ms
    // Per-section focus memory: keys are selectedLibraryType strings
    // ("movie", "show", "ondeck", "mylist") plus "show-episode" for the
    // episode list inside a show detail view.
    property var _focusMemory: ({})

    function _formatDuration(ms) {
        var s = Math.floor(ms / 1000)
        var h = Math.floor(s / 3600)
        var m = Math.floor((s % 3600) / 60)
        var sec = s % 60
        return h + ":" + (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec
    }

    function _showResumeDialog(ratingKey, viewOffsetMs) {
        // Save current index into per-section focus memory so cancel can restore it
        if (currentView === "content") {
            var mem = _focusMemory
            if (selectedLibraryType === "movie") {
                mem["movie"] = (_viewMode === "list") ? movieList.currentIndex : movieGrid.currentIndex
            } else if (selectedLibraryType === "ondeck") {
                mem["ondeck"] = (_viewMode === "list") ? onDeckList.currentIndex : onDeckGrid.currentIndex
            } else if (selectedLibraryType === "mylist") {
                mem["mylist"] = (_viewMode === "list") ? myListListView.currentIndex : myListGridView.currentIndex
            }
            _focusMemory = mem
        } else if (currentView === "detail" && selectedLibraryType === "show") {
            var mem = _focusMemory
            mem["show-episode"] = showDetail.episodeCurrentIndex
            _focusMemory = mem
        }

        _resumeRatingKey = ratingKey
        _resumeViewOffset = viewOffsetMs
        _resumeDialogVisible = true
        resumeDialog.forceActiveFocus()
    }

    function _launchMpv(ratingKey, startMs) {
        _resumeDialogVisible = false
        plex.playWithMpv(ratingKey, startMs)
    }

    function _playContent(ratingKey, knownViewOffset) {
        if (!settings || (settings.plexPlayer || "mpv") === "browser") {
            plex.launchContent(ratingKey)
            return
        }
        _isLoadingContent = true
        _loadingOverlayVisible = true
        loadingOverlayTimer.restart()
        plex.fetchStreamInfo(ratingKey, knownViewOffset || 0)
        // Response arrives via plex.streamInfoReady signal — handled in Connections below
    }

    // Hide the loading overlay, respecting the 400ms minimum display time.
    // If the minimum-display timer is still running, mark pending and let the
    // timer do the hide; otherwise hide immediately.
    property bool _loadingHidePending: false
    function _clearLoading() {
        _isLoadingContent = false
        if (loadingOverlayTimer.running) {
            _loadingHidePending = true
        } else {
            _loadingOverlayVisible = false
            _loadingHidePending = false
        }
    }

    // Loading state for content playback
    property bool _isLoadingContent: false
    property bool _loadingOverlayVisible: false

    // Toast text for My List add/remove notifications
    property string _toastText: ""

    function _showMyListToast(added) {
        _toastText = added ? "Added to My List" : "Removed from My List"
        toastTimer.restart()
    }

    Timer {
        id: toastTimer
        interval: 2000
        onTriggered: watchScreen._toastText = ""
    }

    Timer {
        id: loadingOverlayTimer
        interval: 400
        onTriggered: {
            // Minimum display time elapsed. Hide now if loading is done,
            // or if a hide was requested while the timer was still running.
            if (!watchScreen._isLoadingContent || watchScreen._loadingHidePending) {
                watchScreen._loadingOverlayVisible = false
                watchScreen._loadingHidePending = false
            }
        }
    }

    Rectangle {
        id: toastBar
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: root.vpx(32) }
        width: toastLabel.width + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(6)
        color: Theme.colorSecondary
        visible: watchScreen._toastText !== ""
        z: 100

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: watchScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }

    Connections {
        target: plex
        function onAvailableChanged() { watchScreen._availabilityKnown = true }
        function onLibrariesModelChanged() { watchScreen._libraryEntries = watchScreen._getVideoLibraries() }
        function onOnDeckModelChanged() { watchScreen._libraryEntries = watchScreen._getVideoLibraries() }
        function onMyListChanged(added) {
            watchScreen._libraryEntries = watchScreen._getVideoLibraries()
            watchScreen._showMyListToast(added)
        }
    }

    // Connect liveTV.channelsChanged for future use (e.g. updating channel count).
    Connections {
        target: liveTV
        function onChannelsChanged() {
            // Reserved for future use — Live TV entry in the library list
            // does not currently show a count, but this connection is here
            // so any future count display can be wired up without structural changes.
        }
    }

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    on_ViewModeChanged: { if (currentView === "content") _routeFocus() }
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
                if (_viewMode === "list") movieList.forceActiveFocus()
                else movieGrid.forceActiveFocus()
            } else if (selectedLibraryType === "show") {
                if (_viewMode === "list") showList.forceActiveFocus()
                else showGrid.forceActiveFocus()
            } else if (selectedLibraryType === "ondeck") {
                if (_viewMode === "list") onDeckList.forceActiveFocus()
                else onDeckGrid.forceActiveFocus()
            } else if (selectedLibraryType === "mylist") {
                if (_viewMode === "list") myListListView.forceActiveFocus()
                else myListGridView.forceActiveFocus()
            } else if (selectedLibraryType === "livetv") {
                liveTvGuide.forceActiveFocus()
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
            text: "Plex server unavailable" + (plex && plex.serverUrl ? " (" + plex.serverUrl + ")" : "")
            color: Theme.colorPrimary
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            visible: watchScreen._availabilityKnown
                     && plex && !plex.available
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
                    if (event.key === Qt.Key_Up && currentIndex === 0) {
                        event.accepted = true
                        watchScreen.back()
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        if (currentItem) {
                            if (currentItem.entryType === "livetv") {
                                // Navigate to embedded Live TV guide instead of launching browser
                                watchScreen.selectedLibraryType = "livetv"
                                watchScreen.currentView = "content"
                            } else {
                                watchScreen.selectedLibraryTitle = currentItem.entryTitle
                                watchScreen.selectedSectionKey = currentItem.entrySectionKey
                                watchScreen.selectedLibraryType = currentItem.entryType
                                plex.selectLibrary(currentItem.entrySectionKey)
                                watchScreen.currentView = "content"
                            }
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
                            if (modelData.type === "livetv") {
                                // Navigate to embedded Live TV guide instead of launching browser
                                watchScreen.selectedLibraryType = "livetv"
                                watchScreen.currentView = "content"
                            } else {
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
    }

    // ── Movie grid (task 017) ─────────────────────────────────────────────────
    PlexMovieGrid {
        id: movieGrid

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "movie"
                 && watchScreen._viewMode === "grid"
        focus: false

        systemName: watchScreen.selectedLibraryTitle
        _viewMode: watchScreen._viewMode

        onMovieSelected: (ratingKey, index) => {
            var mem = watchScreen._focusMemory
            mem["movie"] = movieGrid.currentIndex
            watchScreen._focusMemory = mem
            watchScreen.selectedRatingKey = ratingKey
            watchScreen.selectedMovieIndex = index
            watchScreen.selectedMovieData = plex.getMovie(ratingKey)
            watchScreen.currentView = "detail"
        }

        onBack: {
            watchScreen.currentView = "libraries"
        }

        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
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
            var savedIdx = watchScreen._focusMemory["movie"]
            watchScreen.currentView = "content"
            if (savedIdx !== undefined) {
                if (watchScreen._viewMode === "list") movieList.currentIndex = savedIdx
                else movieGrid.currentIndex = savedIdx
            }
        }

        onPlay: (ratingKey) => {
            watchScreen._playContent(ratingKey)
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
                 && watchScreen._viewMode === "grid"
        focus: false

        systemName: watchScreen.selectedLibraryTitle
        _viewMode: watchScreen._viewMode

        onShowSelected: (ratingKey) => {
            var mem = watchScreen._focusMemory
            mem["show"] = showGrid.currentIndex
            watchScreen._focusMemory = mem
            watchScreen.selectedShowRatingKey = ratingKey
            watchScreen.currentView = "detail"
        }

        onBack: {
            watchScreen.currentView = "libraries"
        }

        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
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
            var savedIdx = watchScreen._focusMemory["show"]
            watchScreen.currentView = "content"
            if (savedIdx !== undefined) {
                if (watchScreen._viewMode === "list") showList.currentIndex = savedIdx
                else showGrid.currentIndex = savedIdx
            }
        }

        onPlayEpisode: (ratingKey) => {
            watchScreen._playContent(ratingKey)
        }
    }

    // ── On-deck grid (Continue Watching) ─────────────────────────────────────
    PlexOnDeckGrid {
        id: onDeckGrid

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "ondeck"
                 && watchScreen._viewMode === "grid"
        focus: false

        _viewMode: watchScreen._viewMode

        onItemSelected: (ratingKey) => {
            watchScreen._playContent(ratingKey, onDeckGrid.currentViewOffset)
        }

        onBack: {
            watchScreen.currentView = "libraries"
        }

        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── Movie list view ───────────────────────────────────────────────────────
    PlexMovieList {
        id: movieList

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "movie"
                 && watchScreen._viewMode === "list"
        focus: false

        systemName: watchScreen.selectedLibraryTitle
        _viewMode: watchScreen._viewMode

        onMovieSelected: (ratingKey, index) => {
            var mem = watchScreen._focusMemory
            mem["movie"] = movieList.currentIndex
            watchScreen._focusMemory = mem
            watchScreen.selectedRatingKey = ratingKey
            watchScreen.selectedMovieIndex = index
            watchScreen.selectedMovieData = plex.getMovie(ratingKey)
            watchScreen.currentView = "detail"
        }

        onBack: watchScreen.currentView = "libraries"
        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── Show list view ────────────────────────────────────────────────────────
    PlexShowList {
        id: showList

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "show"
                 && watchScreen._viewMode === "list"
        focus: false

        systemName: watchScreen.selectedLibraryTitle
        _viewMode: watchScreen._viewMode

        onShowSelected: (ratingKey) => {
            var mem = watchScreen._focusMemory
            mem["show"] = showList.currentIndex
            watchScreen._focusMemory = mem
            watchScreen.selectedShowRatingKey = ratingKey
            watchScreen.currentView = "detail"
        }

        onBack: watchScreen.currentView = "libraries"
        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── On-deck list view ─────────────────────────────────────────────────────
    PlexOnDeckList {
        id: onDeckList

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "ondeck"
                 && watchScreen._viewMode === "list"
        focus: false

        _viewMode: watchScreen._viewMode

        onItemSelected: (ratingKey) => { watchScreen._playContent(ratingKey, onDeckList.currentViewOffset) }
        onBack: watchScreen.currentView = "libraries"
        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── My List grid view ─────────────────────────────────────────────────────
    PlexOnDeckGrid {
        id: myListGridView

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "mylist"
                 && watchScreen._viewMode === "grid"

        model: plex ? plex.myListModel : null
        sourceTitle: "My List"
        _viewMode: watchScreen._viewMode

        onItemSelected: (ratingKey) => {
            var itemType = plex.getMyListItemType(ratingKey)
            if (itemType === "show") {
                watchScreen.selectedShowRatingKey = ratingKey
                watchScreen.selectedLibraryType = "show"
                watchScreen.currentView = "detail"
            } else {
                watchScreen._playContent(ratingKey, myListGridView.currentViewOffset)
            }
        }
        onBack: watchScreen.currentView = "libraries"
        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── My List list view ─────────────────────────────────────────────────────
    PlexOnDeckList {
        id: myListListView

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "mylist"
                 && watchScreen._viewMode === "list"

        model: plex ? plex.myListModel : null
        sourceTitle: "My List"
        _viewMode: watchScreen._viewMode

        onItemSelected: (ratingKey) => {
            var itemType = plex.getMyListItemType(ratingKey)
            if (itemType === "show") {
                watchScreen.selectedShowRatingKey = ratingKey
                watchScreen.selectedLibraryType = "show"
                watchScreen.currentView = "detail"
            } else {
                watchScreen._playContent(ratingKey, myListListView.currentViewOffset)
            }
        }
        onBack: watchScreen.currentView = "libraries"
        onViewModeChanged: (mode) => { watchScreen._viewMode = mode }
    }

    // ── Live TV guide ─────────────────────────────────────────────────────────
    LiveTvScreen {
        id: liveTvGuide

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType === "livetv"
        focus: false

        onBack: watchScreen.currentView = "libraries"
    }

    // ── Content placeholder (non-movie, non-show, non-ondeck, non-mylist, non-livetv libraries) ───────
    FocusScope {
        id: contentPlaceholder

        anchors.fill: parent
        visible: watchScreen.currentView === "content"
                 && watchScreen.selectedLibraryType !== "movie"
                 && watchScreen.selectedLibraryType !== "show"
                 && watchScreen.selectedLibraryType !== "ondeck"
                 && watchScreen.selectedLibraryType !== "mylist"
                 && watchScreen.selectedLibraryType !== "livetv"
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

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.watchViewMode || "grid"
        }
    }

    // ── Resume dialog overlay (declared last for highest z-order) ─────────────
    Rectangle {
        id: resumeDialog

        anchors.centerIn: parent
        width: root.vpx(360)
        height: root.vpx(160)
        radius: root.vpx(Theme.focusRingRadius)
        color: Theme.colorSecondary
        border.color: Theme.colorPrimary
        border.width: root.vpx(2)
        visible: watchScreen._resumeDialogVisible
        z: 200

        // Track which button is focused: 0 = Resume, 1 = Start from beginning
        property int _focusedButton: 0

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                event.accepted = true
                resumeDialog._focusedButton = resumeDialog._focusedButton === 0 ? 1 : 0
            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (resumeDialog._focusedButton === 0) {
                    watchScreen._launchMpv(watchScreen._resumeRatingKey, watchScreen._resumeViewOffset)
                } else {
                    watchScreen._launchMpv(watchScreen._resumeRatingKey, 0)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                watchScreen._resumeDialogVisible = false
                // Restore previously focused index from per-section memory
                // (set suppress flag to prevent onActiveFocusChanged reset for ondeck/mylist)
                if (watchScreen.currentView === "content") {
                    var key = watchScreen.selectedLibraryType
                    var savedIdx = watchScreen._focusMemory[key]
                    if (savedIdx !== undefined) {
                        if (key === "movie") {
                            if (watchScreen._viewMode === "list") movieList.currentIndex = savedIdx
                            else movieGrid.currentIndex = savedIdx
                        } else if (key === "ondeck") {
                            if (watchScreen._viewMode === "list") {
                                onDeckList._suppressIndexReset = true
                                onDeckList.currentIndex = savedIdx
                            } else {
                                onDeckGrid._suppressIndexReset = true
                                onDeckGrid.currentIndex = savedIdx
                            }
                        } else if (key === "mylist") {
                            if (watchScreen._viewMode === "list") {
                                myListListView._suppressIndexReset = true
                                myListListView.currentIndex = savedIdx
                            } else {
                                myListGridView._suppressIndexReset = true
                                myListGridView.currentIndex = savedIdx
                            }
                        }
                    }
                } else if (watchScreen.currentView === "detail" && watchScreen.selectedLibraryType === "show") {
                    var savedIdx = watchScreen._focusMemory["show-episode"]
                    if (savedIdx !== undefined) {
                        showDetail.episodeCurrentIndex = savedIdx
                    }
                }
                watchScreen._routeFocus()
            }
        }

        Column {
            anchors {
                fill: parent
                margins: root.vpx(20)
            }
            spacing: root.vpx(12)

            Text {
                text: "Resume playback?"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                font.bold: true
            }

            // Resume button
            Rectangle {
                width: parent.width
                height: root.vpx(44)
                radius: root.vpx(Theme.focusRingRadius)
                color: resumeDialog._focusedButton === 0
                    ? Theme.colorPrimary
                    : Qt.darker(Theme.colorSecondary, 1.4)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }

                Text {
                    anchors.centerIn: parent
                    text: "Resume from " + watchScreen._formatDuration(watchScreen._resumeViewOffset)
                    color: resumeDialog._focusedButton === 0
                        ? Theme.colorBackground
                        : Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                }
            }

            // Start from beginning button
            Rectangle {
                width: parent.width
                height: root.vpx(44)
                radius: root.vpx(Theme.focusRingRadius)
                color: resumeDialog._focusedButton === 1
                    ? Theme.colorPrimary
                    : Qt.darker(Theme.colorSecondary, 1.4)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }

                Text {
                    anchors.centerIn: parent
                    text: "Start from beginning"
                    color: resumeDialog._focusedButton === 1
                        ? Theme.colorBackground
                        : Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                }
            }
        }
    }

    // ── MPV started handler — clear loading state ─────────────────────────────
    Connections {
        target: plex
        function onMpvStarted() { watchScreen._clearLoading() }
    }

    // ── Stream info ready handler — async response from fetchStreamInfo ──────
    Connections {
        target: plex
        function onStreamInfoReady(ratingKey, url, viewOffsetMs) {
            if (!watchScreen._isLoadingContent) return  // cancelled or stale
            if (!url) {
                watchScreen._clearLoading()
                plex.launchContent(ratingKey)
                return
            }
            if (viewOffsetMs > 0) {
                watchScreen._clearLoading()
                watchScreen._showResumeDialog(ratingKey, viewOffsetMs)
            } else {
                watchScreen._launchMpv(ratingKey, 0)
                // _isLoadingContent / overlay cleared by onMpvStarted
            }
        }
    }

    // ── Loading overlay ───────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorOverlay
        visible: watchScreen._loadingOverlayVisible
        z: 150

        Column {
            anchors.centerIn: parent
            spacing: root.vpx(16)

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Loading..."
                color: Theme.colorOverlayText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }
        }
    }
}
