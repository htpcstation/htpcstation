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

    // Where the show detail view was entered from — used by onBack to return
    // to the correct origin view. Values: "show" | "mylist" | "ondeck" | ""
    property string _showDetailOrigin: ""

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // True while a fetchMovie() call is in-flight (result not yet received).
    property bool _movieLoading: false

    // Track whether we have already called plex.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // True when focus is inside a content grid/list — drives the library area
    // fade so the content area receives visual prominence.
    property bool _contentFocused: false

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
        _mpvLaunched = true
        _cancelledDuringLoad = false
        _isLoadingContent = true
        _loadingOverlayVisible = true
        watchScreen._introEndMs = 0
        watchScreen._introSkipped = false
        loadingOverlayTimer.restart()
        loadingTimeoutTimer.restart()
        plex.playWithMpv(ratingKey, startMs)
        // Overlay cleared by onMpvPlaybackReady → _clearLoading()
    }

    function _playContent(ratingKey, knownViewOffset) {
        if (!settings || (settings.plexPlayer || "mpv") === "browser") {
            plex.launchContent(ratingKey)
            return
        }
        _mpvLaunched = false
        _cancelledDuringLoad = false
        _isLoadingContent = true
        _loadingOverlayVisible = true
        loadingOverlayTimer.restart()
        loadingTimeoutTimer.restart()
        plex.fetchStreamInfo(ratingKey, knownViewOffset || 0)
        // Response arrives via plex.streamInfoReady signal — handled in Connections below
    }

    // Hide the loading overlay, respecting the 400ms minimum display time.
    // If the minimum-display timer is still running, mark pending and let the
    // timer do the hide; otherwise hide immediately.
    property bool _loadingHidePending: false
    function _clearLoading() {
        if (_mpvLaunched) {
            // MPV was already told to launch — stop it immediately so it never
            // renders a frame. Also keep _cancelledDuringLoad set as a safety
            // net in case onMpvPlaybackReady fires before the stop takes effect.
            _cancelledDuringLoad = true
            plex.stopMpv()
        }
        _isLoadingContent = false
        _mpvLaunched = false
        loadingTimeoutTimer.stop()
        if (loadingOverlayTimer.running) {
            _loadingHidePending = true
        } else {
            _loadingOverlayVisible = false
            _loadingHidePending = false
        }
        // Restore focus to the correct content item. Use a short delay so the
        // overlay's focus binding updates before _routeFocus() runs — otherwise
        // the overlay may still hold focus and swallow key events.
        focusRestoreTimer.restart()
    }

    Timer {
        id: focusRestoreTimer
        interval: 50
        onTriggered: {
            if (!watchScreen._resumeDialogVisible)
                watchScreen._routeFocus()
        }
    }

    // Loading state for content playback
    property bool _isLoadingContent: false
    property bool _loadingOverlayVisible: false
    // True from the moment plex.playWithMpv() is called until playback starts or is cancelled.
    property bool _mpvLaunched: false
    // Set when the user cancels after MPV was already launched — causes
    // onMpvPlaybackReady to immediately stop playback instead of showing video.
    property bool _cancelledDuringLoad: false
    // True while MPV is actively playing back content (set on playback ready, cleared on finish).
    property bool _mpvPlaying: false

    // Intro marker state for auto-skip
    property int  _introEndMs:   0      // 0 = no intro for current title
    property bool _introSkipped: false  // prevent double-skip

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

    // Error banner — shown when plex.plexError fires
    property string _errorMessage: ""
    property bool _errorPersistent: false   // true = auth error, stays until dismissed

    function _showPlexError(errorType) {
        // During active MPV playback, route transient errors to the toast
        // instead of the banner (auth errors always use the banner).
        if (_mpvPlaying && errorType !== "auth") {
            switch (errorType) {
                case "server":
                    _toastText = "Plex server unavailable"
                    break
                case "network":
                    _toastText = "Network error"
                    break
                case "not_found":
                    _toastText = "Content not found"
                    break
                default:
                    _toastText = "Unexpected error"
                    break
            }
            toastTimer.restart()
            return
        }
        switch (errorType) {
            case "auth":
                _errorMessage = "Plex sign-in required — go to Settings to sign in"
                _errorPersistent = true
                break
            case "server":
                _errorMessage = "Plex server unavailable"
                _errorPersistent = false
                break
            case "network":
                _errorMessage = "Network error — check your connection"
                _errorPersistent = false
                break
            case "not_found":
                _errorMessage = "Content not found"
                _errorPersistent = false
                break
            default:
                _errorMessage = "An unexpected error occurred"
                _errorPersistent = false
                break
        }
        if (!_errorPersistent) errorBannerTimer.restart()
    }

    Timer {
        id: errorBannerTimer
        interval: 5000
        onTriggered: watchScreen._errorMessage = ""
    }

    Timer {
        id: loadingOverlayTimer
        interval: 400
        onTriggered: {
            // Minimum display time elapsed. Hide now if loading is done,
            // or if a hide was requested while the timer was still running.
            // Do NOT hide while the resume dialog is visible — the overlay
            // serves as its backdrop and should stay until the dialog closes.
            if (watchScreen._resumeDialogVisible) return
            if (!watchScreen._isLoadingContent || watchScreen._loadingHidePending) {
                watchScreen._loadingOverlayVisible = false
                watchScreen._loadingHidePending = false
            }
        }
    }

    // 20s hard timeout — clears the overlay and shows an error if playback
    // never started (e.g. server offline, stream URL bad, MPV hung).
    Timer {
        id: loadingTimeoutTimer
        interval: 20000
        onTriggered: {
            if (watchScreen._isLoadingContent) {
                watchScreen._clearLoading()
                watchScreen._showPlexError("network")
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
        function onMpvPlaybackReady() {
            if (watchScreen._cancelledDuringLoad) {
                watchScreen._cancelledDuringLoad = false
                plex.stopMpv()
                return
            }
            // Playback started successfully — clear the launch flag before
            // calling _clearLoading() so it doesn't treat this as a cancel.
            watchScreen._mpvLaunched = false
            watchScreen._mpvPlaying = true
            watchScreen._clearLoading()
        }
        function onMpvStarted() { /* keep for _mpvRunning flag in HomeScreen */ }
        function onMpvFinished() {
            // Ignore a finish event if a new launch is already in progress —
            // this happens when the previous stop (from cancel or resume-dialog
            // confirm) fires processFinished after the next playWithMpv has started.
            if (watchScreen._mpvLaunched) return
            watchScreen._mpvPlaying = false
            watchScreen._clearLoading()
        }
        function onPlexError(errorType) { watchScreen._showPlexError(errorType) }
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
                // _isLoadingContent / overlay cleared by onMpvPlaybackReady
            }
        }
        function onMovieReady(ratingKey, movieData) {
            if (ratingKey === watchScreen.selectedRatingKey) {
                watchScreen.selectedMovieData = movieData
                watchScreen._movieLoading = false
            }
        }
        function onMarkersReady(introEndMs) {
            watchScreen._introEndMs = introEndMs
            watchScreen._introSkipped = false
        }
        function onMpvPositionChanged(posMs) {
            if (!settings || !settings.autoSkipIntro) return
            if (watchScreen._introEndMs <= 0) return
            if (watchScreen._introSkipped) return
            // Seek when position enters the intro window (any position < introEndMs
            // and > 5s to avoid triggering at the very start before the observer fires)
            if (posMs > 5000 && posMs < watchScreen._introEndMs) {
                watchScreen._introSkipped = true
                plex.seekMpv(watchScreen._introEndMs)
                watchScreen._toastText = "Skipping intro..."
                toastTimer.restart()
            }
        }
    }

    // Connect liveTV signals for channel list updates and loading overlay.
    Connections {
        target: liveTV
        function onChannelsChanged() {
            // Reserved for future use — Live TV entry in the library list
            // does not currently show a count, but this connection is here
            // so any future count display can be wired up without structural changes.
        }
        function onMpvPlaybackReady() { watchScreen._clearLoading() }
        function onMpvFinished() {
            if (watchScreen._mpvLaunched) return
            watchScreen._mpvPlaying = false
            watchScreen._clearLoading()
        }
    }

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    on_ViewModeChanged: { if (currentView === "content") _routeFocus() }
    onActiveFocusChanged: {
        if (activeFocus) {
            _contentFocused = false   // reset; _routeFocus will set correctly
            if (!_refreshed || _libraryEntries.length === 0) {
                _refreshed = true
                _availabilityKnown = false
                plex.refresh()
            }
            if (_resumeDialogVisible) {
                resumeDialog.forceActiveFocus()
                return
            }
            _routeFocus()
        }
    }

    function _routeFocus() {
        // Never steal focus from modal overlays.
        if (_resumeDialogVisible) { resumeDialog.forceActiveFocus(); return }
        if (_loadingOverlayVisible) { loadingOverlay.forceActiveFocus(); return }
        if (currentView === "libraries") {
            _contentFocused = false
            libraryList.forceActiveFocus()
        } else if (currentView === "content") {
            _contentFocused = true
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
            _contentFocused = false   // don't fade in detail view
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
        opacity: watchScreen._contentFocused ? 0.3 : 1.0
        Behavior on opacity { NumberAnimation { duration: 160 } }

        // ── Header bar ────────────────────────────────────────────────────────
        Rectangle {
            id: headerBar

            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: root.vpx(56)
            color: Theme.colorSecondary

            Text {
                anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                text: "Plex Media"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }
        }

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

        // ── Library entries ───────────────────────────────────────────────────
        ListView {
            id: libraryList

            anchors {
                top: headerBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(32)
                rightMargin: root.vpx(32)
                bottomMargin: root.vpx(32)
            }

            clip: true
            keyNavigationEnabled: true
            focus: true
            highlightMoveDuration: Theme.animDurationFast

            // Use the JS array built from plex.getLibraryList().
            model: watchScreen._libraryEntries
            onModelChanged: {
                currentIndex = 0
                positionViewAtBeginning()
            }

                Keys.onPressed: (event) => {
                    if (keys.isAccept(event)) {
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
            watchScreen.selectedMovieData = ({})
            watchScreen._movieLoading = true
            plex.fetchMovie(ratingKey)
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
                    watchScreen.selectedMovieData = ({})
                    watchScreen._movieLoading = true
                    plex.fetchMovie(rk)
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
                    watchScreen.selectedMovieData = ({})
                    watchScreen._movieLoading = true
                    plex.fetchMovie(rk)
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
            watchScreen._showDetailOrigin = "show"
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
            var origin = watchScreen._showDetailOrigin
            if (origin === "mylist") {
                watchScreen.selectedLibraryType = "mylist"
                watchScreen.currentView = "content"
                var myIdx = watchScreen._focusMemory["mylist"]
                if (myIdx !== undefined) {
                    if (watchScreen._viewMode === "list") myListListView.currentIndex = myIdx
                    else myListGridView.currentIndex = myIdx
                }
            } else {
                // "show" or any other origin — restore show grid/list
                watchScreen.currentView = "content"
                var showIdx = watchScreen._focusMemory["show"]
                if (showIdx !== undefined) {
                    if (watchScreen._viewMode === "list") showList.currentIndex = showIdx
                    else showGrid.currentIndex = showIdx
                }
            }
            watchScreen._showDetailOrigin = ""
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
            watchScreen.selectedMovieData = ({})
            watchScreen._movieLoading = true
            plex.fetchMovie(ratingKey)
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
            watchScreen._showDetailOrigin = "show"
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
                var mem = watchScreen._focusMemory
                mem["mylist"] = myListGridView.currentIndex
                watchScreen._focusMemory = mem
                watchScreen.selectedShowRatingKey = ratingKey
                watchScreen._showDetailOrigin = "mylist"
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
                var mem = watchScreen._focusMemory
                mem["mylist"] = myListListView.currentIndex
                watchScreen._focusMemory = mem
                watchScreen.selectedShowRatingKey = ratingKey
                watchScreen._showDetailOrigin = "mylist"
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
        onPlaybackLoading: {
            watchScreen._isLoadingContent = true
            watchScreen._loadingOverlayVisible = true
            loadingOverlayTimer.restart()
            loadingTimeoutTimer.restart()
        }
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
        if (plex && !_refreshed) {
            _refreshed = true
            _availabilityKnown = false
            plex.refresh()
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
                watchScreen._resumeDialogVisible = false
                // Keep _loadingOverlayVisible = true — the backdrop transitions
                // seamlessly into the loading overlay while MPV buffers.
                if (resumeDialog._focusedButton === 0) {
                    watchScreen._launchMpv(watchScreen._resumeRatingKey, watchScreen._resumeViewOffset)
                } else {
                    watchScreen._launchMpv(watchScreen._resumeRatingKey, 0)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                watchScreen._resumeDialogVisible = false
                watchScreen._loadingOverlayVisible = false
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

    // ── MPV playback handlers ─────────────────────────────────────────────────
    // ── Error banner ──────────────────────────────────────────────────────────
    Rectangle {
        id: errorBanner
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(44)
        color: watchScreen._errorPersistent ? Theme.colorAccentNegative || "#8B1A1A"
                                            : Qt.darker(Theme.colorSecondary, 1.4)
        visible: watchScreen._errorMessage !== ""
        z: 160

        Row {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            spacing: root.vpx(12)

            Text {
                text: watchScreen._errorPersistent ? "⚠" : "ℹ"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                text: watchScreen._errorMessage
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                visible: watchScreen._errorPersistent
                text: "  [Settings →]"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // Dismiss on any key press for persistent errors
        Keys.onPressed: (event) => {
            if (watchScreen._errorPersistent) {
                watchScreen._errorMessage = ""
                event.accepted = true
            }
        }
    }

    // ── Loading overlay ───────────────────────────────────────────────────────
    Rectangle {
        id: loadingOverlay
        anchors.fill: parent
        color: Theme.colorOverlay
        visible: watchScreen._loadingOverlayVisible
        z: 150

        onVisibleChanged: {
            if (visible) forceActiveFocus()
            // Focus restoration on hide is handled by focusRestoreTimer in _clearLoading()
        }

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                watchScreen._clearLoading()
            }
        }

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

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: keys.useGamepadLabels
                    ? "[" + keys.cancelLabel + "] Cancel"
                    : "[Esc] Cancel"
                color: Theme.colorOverlayText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                opacity: 0.6
            }
        }
    }
}
