import QtQuick
import ".."
import "../components"

// Listen section screen — Plex music library browser.
//
// Four views:
//   "artists"    — grid of artists from the Plex music library
//   "detail"     — artist detail view showing album list
//   "album"      — album detail view showing track listing
//   "nowplaying" — Now Playing view with album art, track info, and controls
//
// Focus flow:
//   Enter ListenScreen → artistGrid gets focus (after library is selected)
//   D-pad               — navigate artist grid / album list / track list
//   A (Return)          — select artist → show album list
//                         select album → show track listing
//   B (Escape)          — from "artists": emit back() to return to tab bar
//                         from "detail":  return to "artists" view
//                         from "album":   return to "detail" view
//                         from "nowplaying": return to "album" view
//
// Playback is handled by HomeScreen's musicPlayer (background playback).
// ListenScreen calls homeScreen._playAlbum() / homeScreen._togglePlayPause() etc.
FocusScope {
    id: listenScreen

    // Emit when B (Escape) is pressed from the top-level view so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Emitted when the user selects an artist (for task 004 to connect).
    signal artistSelected(string ratingKey)

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "menu", "artists", "detail", "album", or "nowplaying"
    property string currentView: "menu"

    // Current artists view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Previous view — used by Now Playing's B button to return to the right place
    property string _previousView: "menu"

    function _goToNowPlaying() {
        currentView = "nowplaying"
    }

    // Section key of the music library (set on first load).
    property string _musicSectionKey: ""

    // True while artists are loading (set false when artistsModel arrives).
    property bool _loading: true

    // True if no music library was found in Plex.
    property bool _noLibrary: false

    // Prevent redundant library lookups when re-entering the tab.
    property bool _initialized: false

    // True while a manual Refresh is in-flight (set false when artists data arrives).
    property bool _refreshing: false

    // Selected artist ratingKey (set when user selects an artist).
    property string _selectedArtistKey: ""

    // Artist detail data and album list (populated when entering detail view).
    property var _artistData: ({})
    property var _albums: []

    // Selected album ratingKey (set when user selects an album).
    property string _selectedAlbumKey: ""

    // Album detail data and track list (populated when entering album view).
    property var _albumData: ({})
    property var _tracks: []

    // Recently added albums list (populated when entering recentlyadded view).
    property var _recentAlbums: []

    // Which view to return to when pressing B from album detail.
    // "detail" when entering from artist detail, "recentlyadded" when entering from Recently Added.
    property string _albumReturnView: "detail"

    // Playlists list (populated when entering playlists view).
    property var _playlists: []

    // Selected playlist data (set when user selects a playlist).
    property var _selectedPlaylist: ({})  // {ratingKey, title, leafCount, duration}

    // Playlist tracks (populated when entering playlistdetail view).
    property var _playlistTracks: []

    // Loading flags for async view transitions
    property bool _detailLoading: false
    property bool _albumLoading: false
    property bool _recentLoading: false
    property bool _playlistsLoading: false
    property bool _playlistTracksLoading: false

    // Error banner — shown when plex.plexError fires
    property string _errorMessage: ""
    property bool _errorPersistent: false   // true = auth error, stays until dismissed

    function _showPlexError(errorType) {
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
        onTriggered: listenScreen._errorMessage = ""
    }

    // ── Try to find and select the music library ────────────────────────────
    function _trySelectMusicLibrary() {
        if (_musicSectionKey) return  // already selected
        if (!plex || !settings) return

        // Wait until libraries are loaded — selectLibrary needs the
        // libraries model to resolve the section type.  If we call it
        // before libraries are loaded, section_type is "" and the
        // artist cache/API branch never runs.
        var libs = plex.getLibraryList()
        if (libs.length === 0) return  // not loaded yet — wait for onLibrariesModelChanged

        var configuredKey = settings.musicLibraryKey
        if (configuredKey) {
            // Verify the configured library still exists
            for (var i = 0; i < libs.length; i++) {
                if (libs[i].sectionKey === configuredKey && libs[i].type === "artist") {
                    _musicSectionKey = configuredKey
                    _noLibrary = false
                    plex.selectLibrary(configuredKey)
                    return
                }
            }
            // Configured library not found — fall through to auto-select
        }

        // No library configured or configured one not found — fall back to first artist library
        for (var j = 0; j < libs.length; j++) {
            if (libs[j].type === "artist") {
                _musicSectionKey = libs[j].sectionKey
                _noLibrary = false
                plex.selectLibrary(libs[j].sectionKey)
                // Auto-save the selection
                if (settings) settings.setMusicLibraryKey(libs[j].sectionKey)
                return
            }
        }

        _loading = false
        _noLibrary = true
    }

    // ── Connections ───────────────────────────────────────────────────────────
    Connections {
        target: plex
        function onArtistsModelChanged() {
            listenScreen._loading = false
            listenScreen._refreshing = false
        }
        function onLibrariesModelChanged() {
            listenScreen._trySelectMusicLibrary()
        }
        function onPlexError(errorType) { listenScreen._showPlexError(errorType) }

        function onArtistDetailReady(ratingKey, data) {
            if (ratingKey !== listenScreen._selectedArtistKey) return
            listenScreen._artistData = data.artist
            listenScreen._albums = data.albums
            listenScreen._detailLoading = false
            // Set initial focus to first non-header entry
            var firstAlbum = 0
            for (var i = 0; i < listenScreen._albums.length; i++) {
                if (listenScreen._albums[i].type !== "header") { firstAlbum = i; break }
            }
            albumList.currentIndex = firstAlbum
        }

        function onAlbumDetailReady(ratingKey, data) {
            if (ratingKey !== listenScreen._selectedAlbumKey) return
            listenScreen._albumData = data.album
            listenScreen._tracks = data.tracks
            listenScreen._albumLoading = false
            trackList.currentIndex = 0
        }

        function onRecentAlbumsReady(albums) {
            listenScreen._recentAlbums = albums
            listenScreen._recentLoading = false
            recentAlbumsList.currentIndex = 0
        }

        function onPlaylistsReady(playlists) {
            listenScreen._playlists = playlists
            listenScreen._playlistsLoading = false
            playlistsList.currentIndex = 0
        }

        function onPlaylistTracksReady(ratingKey, tracks) {
            if (ratingKey !== listenScreen._selectedPlaylist.ratingKey) return
            listenScreen._playlistTracks = tracks
            listenScreen._playlistTracksLoading = false
            playlistTrackList.currentIndex = 0
        }
    }

    // ── Duration formatting helpers ───────────────────────────────────────────
    function _formatDuration(ms) {
        if (!ms || ms <= 0) return ""
        var totalSec = Math.floor(ms / 1000)
        var min = Math.floor(totalSec / 60)
        var sec = totalSec % 60
        return min + ":" + (sec < 10 ? "0" : "") + sec
    }

    function _formatTotalDuration(tracks) {
        var total = 0
        for (var i = 0; i < tracks.length; i++) {
            total += (tracks[i].durationMs || 0)
        }
        return _formatDuration(total)
    }

    function _formatPlaylistDuration(ms) {
        var totalMin = Math.floor(ms / 60000)
        var h = Math.floor(totalMin / 60)
        var m = totalMin % 60
        if (h > 0) return h + "h " + m + "m"
        return m + "m"
    }

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "menu") {
            listenMenu.forceActiveFocus()
        } else if (currentView === "artists") {
            if (_viewMode === "list") {
                artistList.forceActiveFocus()
            } else {
                artistGrid.forceActiveFocus()
            }
        } else if (currentView === "detail") {
            albumList.forceActiveFocus()
        } else if (currentView === "recentlyadded") {
            recentAlbumsList.forceActiveFocus()
        } else if (currentView === "album") {
            trackList._playAllFocused = true
            trackList.forceActiveFocus()
            trackList.currentIndex = 0
            trackList.positionViewAtBeginning()
        } else if (currentView === "nowplaying") {
            nowPlayingView.forceActiveFocus()
        } else if (currentView === "playlists") {
            playlistsList.forceActiveFocus()
        } else if (currentView === "playlistdetail") {
            playlistTrackList._playAllFocused = true
            playlistTrackList.forceActiveFocus()
            playlistTrackList.currentIndex = 0
            playlistTrackList.positionViewAtBeginning()
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_initialized) {
                _initialized = true
                _loading = true
                _noLibrary = false
                if (plex) {
                    _trySelectMusicLibrary()
                }
            } else if (_noLibrary && !_loading) {
                // Retry: plex was unavailable on first load but artists model is still empty
                _trySelectMusicLibrary()
            }
            _routeFocus()
        }
    }

    onCurrentViewChanged: {
        // Lazy refresh: silently re-fetch section content when entering artists or recently added
        if ((currentView === "artists" || currentView === "recentlyadded")
                && listenScreen._musicSectionKey !== "") {
            plex.selectLibrary(listenScreen._musicSectionKey)
        }
        if (currentView !== "nowplaying") {
            _previousView = currentView
        }
        if (currentView === "detail" && _selectedArtistKey) {
            _detailLoading = true
            _artistData = {}
            _albums = []
            plex.fetchArtistDetail(_selectedArtistKey)
        } else if (currentView === "recentlyadded" && _musicSectionKey) {
            _recentLoading = true
            _recentAlbums = []
            plex.fetchRecentAlbums(_musicSectionKey)
        } else if (currentView === "album" && _selectedAlbumKey) {
            _albumLoading = true
            _albumData = {}
            _tracks = []
            plex.fetchAlbumDetail(_selectedAlbumKey)
        } else if (currentView === "playlists") {
            _playlistsLoading = true
            _playlists = []
            plex.fetchPlaylists()
        } else if (currentView === "playlistdetail" && _selectedPlaylist.ratingKey) {
            _playlistTracksLoading = true
            _playlistTracks = []
            plex.fetchPlaylistTracks(_selectedPlaylist.ratingKey)
        }
        _routeFocus()
    }

    on_ViewModeChanged: {
        if (currentView === "artists") _routeFocus()
    }

    Component.onCompleted: {
        if (settings) {
            var savedMode = settings.listenViewMode
            if (savedMode) _viewMode = savedMode
        }
    }

    // ── Header bar ───────────────────────────────────────────────────────────
    Rectangle {
        id: headerBar

        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: "Plex Music"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Menu list ─────────────────────────────────────────────────────────────
    ListView {
        id: listenMenu

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(16)
            rightMargin: root.vpx(16)
            bottomMargin: root.vpx(16)
        }

        visible: listenScreen.currentView === "menu"
        clip: true
        focus: false
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        model: {
            var items = []
            // Now Playing — only show when music is loaded
            if (homeScreen._playbackTracks.length > 0) {
                items.push({ label: "Now Playing", action: "nowplaying" })
            }
            items.push({ label: "Recently Added", action: "recentlyadded" })
            items.push({ label: "Playlists", action: "playlists" })
            items.push({ label: "Artists", action: "artists" })
            items.push({ label: listenScreen._refreshing ? "Refreshing..." : "↻  Refresh",
                         action: "refresh" })
            return items
        }

        delegate: Item {
            id: menuDelegate

            width: listenMenu.width
            height: root.vpx(56)

            readonly property string menuAction: modelData.action

            // Subtle highlight for current item
            Rectangle {
                anchors.fill: parent
                color: Theme.colorPrimary
                opacity: menuDelegate.ListView.isCurrentItem && listenMenu.activeFocus ? 0.12 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: menuDelegate.ListView.isCurrentItem && listenMenu.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
            }

            Row {
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                spacing: root.vpx(12)

                Text {
                    id: menuLabel
                    text: modelData.label
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeHeading)
                }

                // Now Playing — show current track to the right
                Text {
                    visible: modelData.action === "nowplaying" && homeScreen.nowPlayingTrack !== ""
                    text: "♫ " + homeScreen.nowPlayingTrack
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, parent.width - menuLabel.width - parent.spacing)
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            // Focus ring
            FocusRing {
                visible: menuDelegate.ListView.isCurrentItem && listenMenu.activeFocus
            }
        }

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                var item = listenMenu.currentItem
                if (item) {
                    if (item.menuAction === "nowplaying") {
                        listenScreen._goToNowPlaying()
                    } else if (item.menuAction === "recentlyadded") {
                        listenScreen.currentView = "recentlyadded"
                    } else if (item.menuAction === "playlists") {
                        listenScreen.currentView = "playlists"
                    } else if (item.menuAction === "artists") {
                        listenScreen.currentView = "artists"
                    } else if (item.menuAction === "refresh") {
                        if (!listenScreen._refreshing) {
                            listenScreen._refreshing = true
                            listenScreen._loading = true
                            plex.refresh()
                            _trySelectMusicLibrary()
                        }
                    }
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.back()
            }
        }
    }

    // ── Artist grid component ─────────────────────────────────────────────────
    PlexArtistGrid {
        id: artistGrid
        anchors.fill: parent
        visible: listenScreen.currentView === "artists" && listenScreen._viewMode === "grid"
        loading: listenScreen._loading
        noLibrary: listenScreen._noLibrary
        _viewMode: listenScreen._viewMode
        onBack: listenScreen.currentView = "menu"
        onArtistSelected: (ratingKey) => {
            listenScreen._selectedArtistKey = ratingKey
            listenScreen.artistSelected(ratingKey)
            listenScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { listenScreen._viewMode = mode }
    }

    // ── Artist list component ─────────────────────────────────────────────────
    PlexArtistList {
        id: artistList
        anchors.fill: parent
        visible: listenScreen.currentView === "artists" && listenScreen._viewMode === "list"
        loading: listenScreen._loading
        noLibrary: listenScreen._noLibrary
        _viewMode: listenScreen._viewMode
        onBack: listenScreen.currentView = "menu"
        onArtistSelected: (ratingKey) => {
            listenScreen._selectedArtistKey = ratingKey
            listenScreen.artistSelected(ratingKey)
            listenScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { listenScreen._viewMode = mode }
    }

    // ── Album detail view ─────────────────────────────────────────────────────
    Item {
        id: albumDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "album"

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._albumLoading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            z: 10
        }

        // ── Album detail header bar ──────────────────────────────────────────
        Rectangle {
            id: albumDetailHeaderBar

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
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: {
                    var title = listenScreen._albumData.title || ""
                    var year = listenScreen._albumData.year
                    return "◀  " + title + (year > 0 ? " (" + year + ")" : "")
                }
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
            }
        }

        // ── Track list with album info header ────────────────────────────────
        ListView {
            id: trackList

            anchors {
                top: albumDetailHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: albumActionBar.top
            }

            model: listenScreen._tracks
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            // When true, the Play All button in the header is focused
            // instead of a track row.
            property bool _playAllFocused: true

            Keys.onPressed: (event) => {
                if (trackList._playAllFocused) {
                    // Play All button is focused
                    if (keys.isAccept(event)) {
                        event.accepted = true
                        homeScreen._playAlbum(listenScreen._tracks, listenScreen._albumData, 0)
                        listenScreen._goToNowPlaying()
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        trackList._playAllFocused = false
                        trackList.currentIndex = 0
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        listenScreen.currentView = listenScreen._albumReturnView
                    }
                } else {
                    // Track list is focused
                    if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (trackList.currentIndex < listenScreen._tracks.length - 1) {
                            trackList.currentIndex++
                        }
                    } else if (event.key === Qt.Key_Up) {
                        event.accepted = true
                        if (trackList.currentIndex > 0) {
                            trackList.currentIndex--
                        } else {
                            // At first track — move focus to Play All button
                            trackList._playAllFocused = true
                            // Scroll to top to show the Play All button
                            trackList.positionViewAtBeginning()
                        }
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        homeScreen._playAlbum(listenScreen._tracks, listenScreen._albumData, trackList.currentIndex)
                        listenScreen._goToNowPlaying()
                    } else if (keys.isContext1(event)) {
                        // X button — Play All (from track 1)
                        // Note: HomeScreen's global X handler will catch this if music is already playing.
                        // If no music is loaded yet, start playback here.
                        event.accepted = true
                        homeScreen._playAlbum(listenScreen._tracks, listenScreen._albumData, 0)
                        listenScreen._goToNowPlaying()
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        listenScreen.currentView = listenScreen._albumReturnView
                    }
                }
            }

            // ── Album info header component ──────────────────────────────────
            header: Item {
                id: albumInfoHeader

                width: trackList.width

                Column {
                    width: parent.width
                    spacing: 0

                    // ── Top section: art + metadata ──────────────────────────
                    Item {
                        width: parent.width
                        height: root.vpx(220)

                        // ── Left: album art ──────────────────────────────────
                        Item {
                            id: albumArtArea

                            anchors {
                                top: parent.top
                                left: parent.left
                                bottom: parent.bottom
                                margins: root.vpx(16)
                            }
                            width: root.vpx(200)

                            Rectangle {
                                anchors.fill: parent
                                color: Qt.darker(Theme.colorSecondary, 1.4)
                                radius: root.vpx(Theme.focusRingRadius)
                                visible: albumDetailArt.status !== Image.Ready
                                         || !listenScreen._albumData.posterLocal

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - root.vpx(8)
                                    text: listenScreen._albumData.title || ""
                                    color: Theme.colorTextDim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                    wrapMode: Text.Wrap
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }

                            Image {
                                id: albumDetailArt

                                anchors.fill: parent
                                source: listenScreen._albumData.posterLocal || ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                visible: status === Image.Ready
                                         && !!listenScreen._albumData.posterLocal
                            }
                        }

                        // ── Middle: metadata fields ───────────────────────────
                        Column {
                            id: albumMetadataColumn

                            anchors {
                                top: parent.top
                                left: albumArtArea.right
                                topMargin: root.vpx(16)
                                leftMargin: root.vpx(16)
                            }
                            width: root.vpx(220)
                            spacing: root.vpx(4)

                            Repeater {
                                model: [
                                    {
                                        label: "Artist",
                                        value: listenScreen._albumData.parentTitle || ""
                                    },
                                    {
                                        label: "Genre",
                                        value: listenScreen._albumData.genre || ""
                                    },
                                    {
                                        label: "Label",
                                        value: listenScreen._albumData.studio || ""
                                    },
                                    {
                                        label: "Year",
                                        value: listenScreen._albumData.year > 0
                                            ? "" + listenScreen._albumData.year
                                            : ""
                                    },
                                    {
                                        label: "Tracks",
                                        value: listenScreen._tracks.length > 0
                                            ? listenScreen._tracks.length + " tracks · "
                                              + listenScreen._formatTotalDuration(listenScreen._tracks)
                                            : ""
                                    },
                                    {
                                        label: "Rating",
                                        value: listenScreen._albumData.rating > 0
                                            ? (listenScreen._albumData.rating * 10).toFixed(1) + "/10"
                                            : ""
                                    },
                                ]

                                Row {
                                    spacing: root.vpx(8)
                                    visible: modelData.value !== ""

                                    Text {
                                        text: modelData.label + ":"
                                        color: Theme.colorTextDim
                                        font.family: Theme.fontFamily
                                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                                        width: root.vpx(56)
                                    }

                                    Text {
                                        text: modelData.value
                                        color: Theme.colorText
                                        font.family: Theme.fontFamily
                                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                                        width: albumMetadataColumn.width - root.vpx(56) - root.vpx(8)
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        // ── Right: summary ───────────────────────────────────
                        Flickable {
                            anchors {
                                top: parent.top
                                left: albumMetadataColumn.right
                                right: parent.right
                                bottom: parent.bottom
                                topMargin: root.vpx(16)
                                leftMargin: root.vpx(16)
                                rightMargin: root.vpx(16)
                                bottomMargin: root.vpx(16)
                            }
                            contentHeight: summaryText.implicitHeight
                            clip: true
                            interactive: false
                            visible: !!(listenScreen._albumData.summary)

                            Text {
                                id: summaryText
                                width: parent.width
                                text: listenScreen._albumData.summary || ""
                                color: Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                            }
                        }
                    }

                    // ── Separator ────────────────────────────────────────────
                    Rectangle {
                        width: parent.width - root.vpx(32)
                        x: root.vpx(16)
                        height: root.vpx(1)
                        color: Theme.colorTextDim
                        opacity: 0.4
                    }

                    // ── Tracks header with Play All button ───────────────────
                    Item {
                        width: parent.width
                        height: root.vpx(36)

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.vpx(16)
                                verticalCenter: parent.verticalCenter
                            }
                            text: "Tracks"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            font.bold: true
                        }

                        // Play All button (centered, focusable via D-pad)
                        Rectangle {
                            id: playAllBtn
                            anchors {
                                horizontalCenter: parent.horizontalCenter
                                verticalCenter: parent.verticalCenter
                            }
                            width: playAllLabel.implicitWidth + root.vpx(16)
                            height: root.vpx(26)
                            color: trackList._playAllFocused && trackList.activeFocus
                                ? Theme.colorPrimary : "transparent"
                            border.color: Theme.colorPrimary
                            border.width: root.vpx(1)
                            radius: root.vpx(Theme.focusRingRadius)
                            opacity: (trackList._playAllFocused && trackList.activeFocus)
                                || playAllMouse.containsMouse ? 1.0 : 0.7

                            Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                            Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }

                            Text {
                                id: playAllLabel
                                anchors.centerIn: parent
                                text: "▶ Play All"
                                color: trackList._playAllFocused && trackList.activeFocus
                                    ? Theme.colorBackground : Theme.colorPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeSmall)

                                Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                            }

                            MouseArea {
                                id: playAllMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    homeScreen._playAlbum(listenScreen._tracks, listenScreen._albumData, 0)
                                    listenScreen._goToNowPlaying()
                                }
                            }
                        }
                    }
                }

                // Bind height to the Column's implicit height
                implicitHeight: children[0].implicitHeight
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "album" && listenScreen._tracks.length === 0 && !listenScreen._albumLoading
                text: "No tracks found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Track row delegate ───────────────────────────────────────────
            delegate: Item {
                id: trackDelegate

                // True when this track is the one currently playing.
                // _playOrder[_playingIndex] is the actual track index in _playbackTracks;
                // compare that against this delegate's index in the model.
                readonly property bool isPlaying: homeScreen._playingAlbumKey === listenScreen._selectedAlbumKey
                                                  && homeScreen._playingIndex >= 0
                                                  && homeScreen._playOrder[homeScreen._playingIndex] === index

                width: trackList.width
                height: root.vpx(48)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: trackDelegate.ListView.isCurrentItem && !trackList._playAllFocused ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: trackDelegate.ListView.isCurrentItem && !trackList._playAllFocused && trackList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                Row {
                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(16)
                        rightMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: root.vpx(8)

                    // Track number or now-playing indicator
                    Text {
                        text: trackDelegate.isPlaying ? "▶" : (modelData.index > 0 ? "" + modelData.index : "" + (index + 1))
                        color: trackDelegate.isPlaying ? Theme.colorPrimary : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(32)
                        horizontalAlignment: Text.AlignRight
                    }

                    // Track title
                    Text {
                        text: modelData.title || ""
                        color: trackDelegate.isPlaying
                            ? Theme.colorPrimary
                            : (trackDelegate.ListView.isCurrentItem && !trackList._playAllFocused ? Theme.colorText : Theme.colorTextDim)
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        width: parent.width - root.vpx(32) - root.vpx(8) - root.vpx(48) - root.vpx(8)
                    }

                    // Duration (right-aligned, dim, M:SS format)
                    Text {
                        text: listenScreen._formatDuration(modelData.durationMs)
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(48)
                        horizontalAlignment: Text.AlignRight
                    }
                }

                // Focus ring
                FocusRing {
                    visible: trackDelegate.ListView.isCurrentItem && trackList.activeFocus && !trackList._playAllFocused
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        trackList.currentIndex = index
                        trackList.forceActiveFocus()
                    }
                    onDoubleClicked: {
                        trackList.currentIndex = index
                        trackList.forceActiveFocus()
                        homeScreen._playAlbum(listenScreen._tracks, listenScreen._albumData, index)
                        listenScreen._goToNowPlaying()
                    }
                }
            }
        }

        // ── Action bar ───────────────────────────────────────────────────────
        Rectangle {
            id: albumActionBar

            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            height: root.vpx(40)
            color: Theme.colorSecondary

            Text {
                anchors.centerIn: parent
                text: keys.useGamepadLabels
                    ? "[" + keys.acceptLabel + "] Play from track    ["
                      + keys.context1Label + "] Play All    ["
                      + keys.cancelLabel + "] Back"
                    : "[Enter] Play from track    [Esc] Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Now Playing view ──────────────────────────────────────────────────────
    FocusScope {
        id: nowPlayingView

        anchors.fill: parent
        visible: listenScreen.currentView === "nowplaying"

        onActiveFocusChanged: {
            if (activeFocus) btnPlayPause.forceActiveFocus()
        }

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.currentView = listenScreen._previousView || "menu"
            } else if (keys.isPrevTab(event)) {
                // LB — always prev track regardless of which button has focus
                event.accepted = true
                homeScreen._playPrev()
            } else if (keys.isNextTab(event)) {
                // RB — always next track regardless of which button has focus
                event.accepted = true
                homeScreen._playNext()
            }
            // Left/Right navigate between buttons (handled by KeyNavigation on each button).
            // A activates the focused button (handled per-button).
        }

        // ── Now Playing header bar ───────────────────────────────────────────
        Rectangle {
            id: nowPlayingHeaderBar

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
                text: "◀  Now Playing"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }
        }

        // ── Main content area ────────────────────────────────────────────────
        Item {
            id: nowPlayingContent

            anchors {
                top: nowPlayingHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: nowPlayingActionBar.top
                margins: root.vpx(24)
            }

            // ── Left: album art ──────────────────────────────────────────────
            Item {
                id: nowPlayingArtArea

                anchors {
                    top: parent.top
                    left: parent.left
                    bottom: parent.bottom
                }
                width: Math.min(root.vpx(250), parent.height * 0.55)

                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: nowPlayingArt.status !== Image.Ready
                             || !homeScreen._playbackAlbumData.posterLocal

                    Text {
                        anchors.centerIn: parent
                        width: parent.width - root.vpx(8)
                        text: homeScreen._playbackAlbumData.title || ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                Image {
                    id: nowPlayingArt

                    anchors.fill: parent
                    source: homeScreen._playbackAlbumData.posterLocal || ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: status === Image.Ready
                             && !!homeScreen._playbackAlbumData.posterLocal
                }
            }

            // ── Right: track info + controls + lyrics ─────────────────────────
            Item {
                id: nowPlayingRightArea

                anchors {
                    top: parent.top
                    left: nowPlayingArtArea.right
                    right: parent.right
                    bottom: parent.bottom
                    leftMargin: root.vpx(32)
                }

            // ── Left sub-column: track info + controls ───────────────────────
            Column {
                id: nowPlayingInfoColumn

                anchors {
                    top: parent.top
                    left: parent.left
                }
                width: nowPlayingRightArea.width * 0.58
                spacing: root.vpx(8)

                // Track title
                Text {
                    width: parent.width
                    text: homeScreen._nowPlayingTrack.title || ""
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                }

                // Artist name
                Text {
                    width: parent.width
                    text: homeScreen._playbackAlbumData.parentTitle || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                }

                // Album name
                Text {
                    width: parent.width
                    text: homeScreen._playbackAlbumData.title || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                }

                // Year · Track number
                Text {
                    width: parent.width
                    text: {
                        var parts = []
                        if (homeScreen._playbackAlbumData.year > 0)
                            parts.push("" + homeScreen._playbackAlbumData.year)
                        if (homeScreen._nowPlayingTrack.index > 0)
                            parts.push("Track " + homeScreen._nowPlayingTrack.index)
                        return parts.join("  ·  ")
                    }
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: homeScreen._playbackAlbumData.year > 0
                             || homeScreen._nowPlayingTrack.index > 0
                }

                // Spacer
                Item { width: 1; height: root.vpx(16) }

                // ── Playback controls (focusable buttons) ────────────────────
                Row {
                    id: controlsRow
                    spacing: root.vpx(16)

                    // ── Prev ─────────────────────────────────────────────────
                    FocusScope {
                        id: btnPrev
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.right: btnPlayPause
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._playPrev()
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnPrev.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: "◀◀"
                                color: Theme.colorText
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(24)
                                opacity: homeScreen._playingIndex > 0 || homeScreen._repeatMode === "all" ? 1.0 : 0.35
                            }
                        }
                    }

                    // ── Play/Pause ────────────────────────────────────────────
                    FocusScope {
                        id: btnPlayPause
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.left: btnPrev
                        KeyNavigation.right: btnNext
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._togglePlayPause()
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnPlayPause.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: homeScreen.musicPlaybackState === 1 ? "❚❚" : "▶"
                                color: Theme.colorPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(28)
                            }
                        }
                    }

                    // ── Next ─────────────────────────────────────────────────
                    FocusScope {
                        id: btnNext
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.left: btnPlayPause
                        KeyNavigation.right: btnShuffle
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._playNext()
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnNext.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: "▶▶"
                                color: Theme.colorText
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(24)
                                opacity: homeScreen._playingIndex < homeScreen._playOrder.length - 1 || homeScreen._repeatMode === "all" ? 1.0 : 0.35
                            }
                        }
                    }

                    // ── Separator ─────────────────────────────────────────────
                    Rectangle {
                        width: root.vpx(1)
                        height: root.vpx(32)
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.colorTextDim
                        opacity: 0.4
                    }

                    // ── Shuffle ───────────────────────────────────────────────
                    FocusScope {
                        id: btnShuffle
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.left: btnNext
                        KeyNavigation.right: btnRepeat
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._toggleShuffle()
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: homeScreen._shuffleEnabled
                                ? Qt.rgba(Theme.colorPrimary.r, Theme.colorPrimary.g, Theme.colorPrimary.b, 0.15)
                                : "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnShuffle.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: "⇄"
                                color: homeScreen._shuffleEnabled ? Theme.colorPrimary : Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(22)
                            }
                        }
                    }

                    // ── Repeat ────────────────────────────────────────────────
                    FocusScope {
                        id: btnRepeat
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.left: btnShuffle
                        KeyNavigation.right: btnLyrics
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._cycleRepeat()
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: homeScreen._repeatMode !== "off"
                                ? Qt.rgba(Theme.colorPrimary.r, Theme.colorPrimary.g, Theme.colorPrimary.b, 0.15)
                                : "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnRepeat.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: homeScreen._repeatMode === "one" ? "↺¹" : "↺"
                                color: homeScreen._repeatMode !== "off" ? Theme.colorPrimary : Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(22)
                            }
                        }
                    }

                    // ── Separator ─────────────────────────────────────────────
                    Rectangle {
                        width: root.vpx(1)
                        height: root.vpx(32)
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.colorTextDim
                        opacity: 0.4
                    }

                    // ── Lyrics toggle ─────────────────────────────────────────
                    FocusScope {
                        id: btnLyrics
                        width: root.vpx(56); height: root.vpx(48)
                        KeyNavigation.left: btnRepeat
                        KeyNavigation.down: progressBar

                        Keys.onPressed: (event) => {
                            if (keys.isAccept(event)) {
                                event.accepted = true
                                homeScreen._lyricsEnabled = !homeScreen._lyricsEnabled
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: homeScreen._lyricsEnabled
                                ? Qt.rgba(Theme.colorPrimary.r, Theme.colorPrimary.g, Theme.colorPrimary.b, 0.15)
                                : "transparent"
                            radius: root.vpx(Theme.focusRingRadius)
                            border.color: Theme.colorFocusRing
                            border.width: btnLyrics.activeFocus ? root.vpx(Theme.focusRingWidth) : 0

                            Text {
                                anchors.centerIn: parent
                                text: "♪"
                                color: homeScreen._lyricsEnabled ? Theme.colorPrimary : Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(22)
                            }
                        }
                    }
                }

                // Spacer
                Item { width: 1; height: root.vpx(8) }

                // ── Progress bar — keyboard seek ±10s/±30s, mouse click/drag ──
                Item {
                    id: progressBar
                    width: parent.width
                    height: root.vpx(20)   // taller hit area; bar drawn inside

                    // Must be explicitly focusable — plain Item does not receive
                    // key events unless focus: true is set directly on it.
                    focus: true
                    KeyNavigation.up: btnPlayPause

                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Left) {
                            event.accepted = true
                            homeScreen._seekBy(-10000)
                        } else if (event.key === Qt.Key_Right) {
                            event.accepted = true
                            homeScreen._seekBy(10000)
                        } else if (keys.isPrevTab(event)) {
                            event.accepted = true
                            homeScreen._seekBy(-30000)
                        } else if (keys.isNextTab(event)) {
                            event.accepted = true
                            homeScreen._seekBy(30000)
                        }
                    }

                    // Bar track
                    Rectangle {
                        id: barTrack
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: progressBar.activeFocus ? root.vpx(8) : root.vpx(6)
                        color: Qt.darker(Theme.colorSecondary, 1.6)
                        radius: root.vpx(4)

                        Behavior on height { NumberAnimation { duration: Theme.animDurationFast } }

                        // Progress fill
                        Rectangle {
                            width: homeScreen.musicDuration > 0
                                ? parent.width * (homeScreen.musicPosition / homeScreen.musicDuration)
                                : 0
                            height: parent.height
                            color: Theme.colorPrimary
                            radius: parent.radius
                        }

                        // Thumb — visible when focused or hovered
                        Rectangle {
                            visible: (progressBar.activeFocus || seekArea.containsMouse)
                                     && homeScreen.musicDuration > 0
                            x: homeScreen.musicDuration > 0
                                ? parent.width * (homeScreen.musicPosition / homeScreen.musicDuration) - width / 2
                                : 0
                            anchors.verticalCenter: parent.verticalCenter
                            width: root.vpx(14)
                            height: root.vpx(14)
                            radius: width / 2
                            color: Theme.colorPrimary
                        }
                    }

                    // Mouse drag — covers the full hit area (not just the thin bar)
                    MouseArea {
                        id: seekArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor

                        function seekToMouse(mouseX) {
                            if (homeScreen.musicDuration <= 0) return
                            var ratio = Math.max(0, Math.min(1, mouseX / width))
                            homeScreen._seekTo(ratio * homeScreen.musicDuration)
                        }

                        onPressed: (mouse) => {
                            progressBar.forceActiveFocus()
                            seekToMouse(mouse.x)
                        }
                        onPositionChanged: (mouse) => {
                            if (pressed) seekToMouse(mouse.x)
                        }
                    }
                }

                // Time display
                Text {
                    text: homeScreen._formatDuration(homeScreen.musicPosition)
                        + " / "
                        + homeScreen._formatDuration(homeScreen.musicDuration)
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }

            }

            // ── Right sub-column: lyrics panel ───────────────────────────────
            Item {
                id: lyricsPanel

                anchors {
                    left: nowPlayingInfoColumn.right
                    leftMargin: root.vpx(24)
                    right: parent.right
                    top: parent.top
                    bottom: parent.bottom
                }

                visible: homeScreen._lyricsEnabled

                // ── "No lyrics" placeholder ──────────────────────────────────
                Text {
                    anchors.centerIn: parent
                    visible: homeScreen._lyricsRatingKey !== ""
                             && !homeScreen._lyricsAvailable
                    text: "No lyrics available"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }

                // ── Lyrics list ───────────────────────────────────────────────
                ListView {
                    id: lyricsView
                    anchors.fill: parent
                    clip: true
                    visible: homeScreen._lyricsAvailable && homeScreen._lyricsLines.length > 0

                    model: homeScreen._lyricsLines

                    // Active line index: highest index where line.ms <= musicPosition.
                    // For plain lyrics (all ms === -1), activeIndex stays -1 (no highlight).
                    property int activeIndex: {
                        var pos = homeScreen.musicPosition
                        var lines = homeScreen._lyricsLines
                        var idx = -1
                        for (var i = 0; i < lines.length; i++) {
                            if (lines[i].ms !== -1 && lines[i].ms <= pos) idx = i
                        }
                        return idx
                    }

                    // Auto-scroll to keep active line centred.
                    onActiveIndexChanged: {
                        if (activeIndex >= 0) {
                            positionViewAtIndex(activeIndex, ListView.Center)
                        }
                    }

                    delegate: Text {
                        width: lyricsView.width
                        text: modelData.text
                        color: index === lyricsView.activeIndex
                            ? Theme.colorPrimary
                            : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        wrapMode: Text.Wrap
                        topPadding: root.vpx(3)
                        bottomPadding: root.vpx(3)

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }
                    }
                }
            }
            }
        }

        // ── Action bar ───────────────────────────────────────────────────────
        Rectangle {
            id: nowPlayingActionBar

            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            height: root.vpx(40)
            color: Theme.colorSecondary

            Text {
                anchors.centerIn: parent
                    text: keys.useGamepadLabels
                        ? "[" + keys.acceptLabel + "] Select    ["
                          + keys.cancelLabel + "] Back    [LB] Prev    [RB] Next    [" + keys.context1Label + "] Play/Pause    [↓] Seek bar    [←][→] Navigate/Seek"
                        : "[Enter] Select    [Esc] Back    [PgUp] Prev    [PgDn] Next    [1] Play/Pause    [↓] Seek bar    [←][→] Navigate/Seek"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Recently Added view ───────────────────────────────────────────────────
    Item {
        id: recentlyAddedView

        anchors.fill: parent
        visible: listenScreen.currentView === "recentlyadded"

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._recentLoading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            z: 10
        }

        // ── Recently Added header bar ────────────────────────────────────────
        Rectangle {
            id: recentlyAddedHeaderBar

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
                text: "◀  Recently Added"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }
        }

        // ── Recently Added album list ────────────────────────────────────────
        ListView {
            id: recentAlbumsList

            anchors {
                top: recentlyAddedHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(8)
            }

            model: listenScreen._recentAlbums
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    if (recentAlbumsList.currentIndex < listenScreen._recentAlbums.length - 1) {
                        recentAlbumsList.currentIndex++
                    }
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    if (recentAlbumsList.currentIndex > 0) {
                        recentAlbumsList.currentIndex--
                    }
                } else if (keys.isAccept(event)) {
                    event.accepted = true
                    var album = listenScreen._recentAlbums[recentAlbumsList.currentIndex]
                    if (album) {
                        listenScreen._selectedAlbumKey = album.ratingKey
                        listenScreen._albumReturnView = "recentlyadded"
                        listenScreen.currentView = "album"
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    listenScreen.currentView = "menu"
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "recentlyadded" && listenScreen._recentAlbums.length === 0 && !listenScreen._recentLoading
                text: "No recently added albums"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Album row delegate ───────────────────────────────────────────
            delegate: Item {
                id: recentAlbumDelegate

                width: recentAlbumsList.width
                height: root.vpx(96)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: recentAlbumDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: recentAlbumDelegate.ListView.isCurrentItem && recentAlbumsList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                Row {
                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(8)
                        rightMargin: root.vpx(8)
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: root.vpx(12)

                    // ── Album art thumbnail ──────────────────────────────────
                    Item {
                        width: root.vpx(80)
                        height: root.vpx(80)

                        // Placeholder shown when there is no art or while loading
                        Rectangle {
                            anchors.fill: parent
                            color: Qt.darker(Theme.colorSecondary, 1.4)
                            radius: root.vpx(Theme.focusRingRadius)
                            visible: recentAlbumArt.status !== Image.Ready || !modelData.posterLocal

                            Text {
                                anchors.centerIn: parent
                                width: parent.width - root.vpx(8)
                                text: modelData.title || ""
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
                            id: recentAlbumArt

                            anchors.fill: parent
                            source: modelData.posterLocal || ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            sourceSize.width: root.vpx(80)
                            sourceSize.height: root.vpx(80)
                            visible: status === Image.Ready && modelData.posterLocal
                            clip: true
                        }
                    }

                    // ── Album title, artist, and year ────────────────────────
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: root.vpx(4)
                        width: parent.width - root.vpx(80) - root.vpx(12)

                        Text {
                            width: parent.width
                            text: modelData.title || ""
                            color: recentAlbumDelegate.ListView.isCurrentItem
                                ? Theme.colorText
                                : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            width: parent.width
                            text: modelData.parentTitle || ""
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            width: parent.width
                            text: modelData.year > 0 ? "" + modelData.year : ""
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                            visible: modelData.year > 0
                        }
                    }
                }

                // Focus ring
                FocusRing {
                    visible: recentAlbumDelegate.ListView.isCurrentItem && recentAlbumsList.activeFocus
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        recentAlbumsList.currentIndex = index
                        recentAlbumsList.forceActiveFocus()
                    }
                    onDoubleClicked: {
                        recentAlbumsList.currentIndex = index
                        var album = listenScreen._recentAlbums[index]
                        if (album) {
                            listenScreen._selectedAlbumKey = album.ratingKey
                            listenScreen._albumReturnView = "recentlyadded"
                            listenScreen.currentView = "album"
                        }
                    }
                }
            }
        }
    }

    // ── Playlists view ────────────────────────────────────────────────────────
    Item {
        id: playlistsView

        anchors.fill: parent
        visible: listenScreen.currentView === "playlists"

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._playlistsLoading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            z: 10
        }

        // ── Playlists header bar ─────────────────────────────────────────────
        Rectangle {
            id: playlistsHeaderBar

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
                text: "◀  Playlists"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }
        }

        // ── Playlists list ───────────────────────────────────────────────────
        ListView {
            id: playlistsList

            anchors {
                top: playlistsHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(8)
            }

            model: listenScreen._playlists
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    if (playlistsList.currentIndex < listenScreen._playlists.length - 1) {
                        playlistsList.currentIndex++
                    }
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    if (playlistsList.currentIndex > 0) {
                        playlistsList.currentIndex--
                    }
                } else if (keys.isAccept(event)) {
                    event.accepted = true
                    var pl = listenScreen._playlists[playlistsList.currentIndex]
                    if (pl) {
                        listenScreen._selectedPlaylist = pl
                        listenScreen.currentView = "playlistdetail"
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    listenScreen.currentView = "menu"
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "playlists" && listenScreen._playlists.length === 0 && !listenScreen._playlistsLoading
                text: "No playlists found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Playlist row delegate ────────────────────────────────────────
            delegate: Item {
                id: playlistDelegate

                width: playlistsList.width
                height: root.vpx(64)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: playlistDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: playlistDelegate.ListView.isCurrentItem && playlistsList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                Column {
                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(16)
                        rightMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: root.vpx(4)

                    Text {
                        width: parent.width
                        text: modelData.title || ""
                        color: playlistDelegate.ListView.isCurrentItem
                            ? Theme.colorText
                            : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        width: parent.width
                        text: {
                            var cnt = modelData.leafCount || 0
                            var trackStr = cnt === 1 ? "1 track" : (cnt + " tracks")
                            var dur = modelData.duration || 0
                            if (dur > 0) {
                                return trackStr + " · " + listenScreen._formatPlaylistDuration(dur)
                            }
                            return trackStr
                        }
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }
                }

                // Focus ring
                FocusRing {
                    visible: playlistDelegate.ListView.isCurrentItem && playlistsList.activeFocus
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        playlistsList.currentIndex = index
                        playlistsList.forceActiveFocus()
                    }
                    onDoubleClicked: {
                        playlistsList.currentIndex = index
                        var pl = listenScreen._playlists[index]
                        if (pl) {
                            listenScreen._selectedPlaylist = pl
                            listenScreen.currentView = "playlistdetail"
                        }
                    }
                }
            }
        }
    }

    // ── Playlist detail view ──────────────────────────────────────────────────
    Item {
        id: playlistDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "playlistdetail"

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._playlistTracksLoading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            z: 10
        }

        // ── Playlist detail header bar ───────────────────────────────────────
        Rectangle {
            id: playlistDetailHeaderBar

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
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: "◀  " + (listenScreen._selectedPlaylist.title || "")
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
            }
        }

        // ── Playlist track list ──────────────────────────────────────────────
        ListView {
            id: playlistTrackList

            anchors {
                top: playlistDetailHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: playlistDetailActionBar.top
            }

            model: listenScreen._playlistTracks
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            // When true, the Play All button in the header is focused
            // instead of a track row.
            property bool _playAllFocused: true

            Keys.onPressed: (event) => {
                if (playlistTrackList._playAllFocused) {
                    // Play All button is focused
                    if (keys.isAccept(event)) {
                        event.accepted = true
                        var playlistAlbumData = {
                            ratingKey: listenScreen._selectedPlaylist.ratingKey,
                            title: listenScreen._selectedPlaylist.title,
                            year: 0,
                            parentTitle: "Playlist",
                            posterLocal: "",
                        }
                        homeScreen._playAlbum(listenScreen._playlistTracks, playlistAlbumData, 0)
                        listenScreen._goToNowPlaying()
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        playlistTrackList._playAllFocused = false
                        playlistTrackList.currentIndex = 0
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        listenScreen.currentView = "playlists"
                    }
                } else {
                    // Track list is focused
                    if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (playlistTrackList.currentIndex < listenScreen._playlistTracks.length - 1) {
                            playlistTrackList.currentIndex++
                        }
                    } else if (event.key === Qt.Key_Up) {
                        event.accepted = true
                        if (playlistTrackList.currentIndex > 0) {
                            playlistTrackList.currentIndex--
                        } else {
                            // At first track — move focus to Play All button
                            playlistTrackList._playAllFocused = true
                            playlistTrackList.positionViewAtBeginning()
                        }
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        var albumData = {
                            ratingKey: listenScreen._selectedPlaylist.ratingKey,
                            title: listenScreen._selectedPlaylist.title,
                            year: 0,
                            parentTitle: "Playlist",
                            posterLocal: "",
                        }
                        homeScreen._playAlbum(listenScreen._playlistTracks, albumData, playlistTrackList.currentIndex)
                        listenScreen._goToNowPlaying()
                    } else if (keys.isContext1(event)) {
                        // X button — Play All (from track 1)
                        event.accepted = true
                        var albumDataX = {
                            ratingKey: listenScreen._selectedPlaylist.ratingKey,
                            title: listenScreen._selectedPlaylist.title,
                            year: 0,
                            parentTitle: "Playlist",
                            posterLocal: "",
                        }
                        homeScreen._playAlbum(listenScreen._playlistTracks, albumDataX, 0)
                        listenScreen._goToNowPlaying()
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        listenScreen.currentView = "playlists"
                    }
                }
            }

            // ── Tracks header with Play All button ───────────────────────────
            header: Item {
                id: playlistTracksHeader

                width: playlistTrackList.width
                height: root.vpx(36)

                Text {
                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    text: "Tracks"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    font.bold: true
                }

                // Play All button (centered, focusable via D-pad)
                Rectangle {
                    id: playlistPlayAllBtn
                    anchors {
                        horizontalCenter: parent.horizontalCenter
                        verticalCenter: parent.verticalCenter
                    }
                    width: playlistPlayAllLabel.implicitWidth + root.vpx(16)
                    height: root.vpx(26)
                    color: playlistTrackList._playAllFocused && playlistTrackList.activeFocus
                        ? Theme.colorPrimary : "transparent"
                    border.color: Theme.colorPrimary
                    border.width: root.vpx(1)
                    radius: root.vpx(Theme.focusRingRadius)
                    opacity: (playlistTrackList._playAllFocused && playlistTrackList.activeFocus)
                        || playlistPlayAllMouse.containsMouse ? 1.0 : 0.7

                    Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }

                    Text {
                        id: playlistPlayAllLabel
                        anchors.centerIn: parent
                        text: "▶ Play All"
                        color: playlistTrackList._playAllFocused && playlistTrackList.activeFocus
                            ? Theme.colorBackground : Theme.colorPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)

                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                    }

                    MouseArea {
                        id: playlistPlayAllMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            var albumData = {
                                ratingKey: listenScreen._selectedPlaylist.ratingKey,
                                title: listenScreen._selectedPlaylist.title,
                                year: 0,
                                parentTitle: "Playlist",
                                posterLocal: "",
                            }
                            homeScreen._playAlbum(listenScreen._playlistTracks, albumData, 0)
                            listenScreen._goToNowPlaying()
                        }
                    }
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "playlistdetail" && listenScreen._playlistTracks.length === 0 && !listenScreen._playlistTracksLoading
                text: "No tracks found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Playlist track row delegate ──────────────────────────────────
            delegate: Item {
                id: playlistTrackDelegate

                width: playlistTrackList.width
                height: root.vpx(48)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: playlistTrackDelegate.ListView.isCurrentItem && !playlistTrackList._playAllFocused ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: playlistTrackDelegate.ListView.isCurrentItem && !playlistTrackList._playAllFocused && playlistTrackList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                Row {
                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(16)
                        rightMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: root.vpx(8)

                    // Track title
                    Column {
                        width: parent.width - root.vpx(48) - root.vpx(8)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: root.vpx(2)

                        Text {
                            width: parent.width
                            text: modelData.title || ""
                            color: playlistTrackDelegate.ListView.isCurrentItem && !playlistTrackList._playAllFocused
                                ? Theme.colorText : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        // Artist name (dim) — important for playlists since tracks come from different artists
                        Text {
                            width: parent.width
                            text: modelData.grandparentTitle || ""
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                            visible: (modelData.grandparentTitle || "") !== ""
                        }
                    }

                    // Duration (right-aligned, dim, M:SS format)
                    Text {
                        text: listenScreen._formatDuration(modelData.durationMs)
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(48)
                        horizontalAlignment: Text.AlignRight
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                // Focus ring
                FocusRing {
                    visible: playlistTrackDelegate.ListView.isCurrentItem && playlistTrackList.activeFocus && !playlistTrackList._playAllFocused
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        playlistTrackList.currentIndex = index
                        playlistTrackList.forceActiveFocus()
                    }
                    onDoubleClicked: {
                        playlistTrackList.currentIndex = index
                        playlistTrackList.forceActiveFocus()
                        var albumData = {
                            ratingKey: listenScreen._selectedPlaylist.ratingKey,
                            title: listenScreen._selectedPlaylist.title,
                            year: 0,
                            parentTitle: "Playlist",
                            posterLocal: "",
                        }
                        homeScreen._playAlbum(listenScreen._playlistTracks, albumData, index)
                        listenScreen._goToNowPlaying()
                    }
                }
            }
        }

        // ── Action bar ───────────────────────────────────────────────────────
        Rectangle {
            id: playlistDetailActionBar

            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            height: root.vpx(40)
            color: Theme.colorSecondary

            Text {
                anchors.centerIn: parent
                text: keys.useGamepadLabels
                    ? "[" + keys.acceptLabel + "] Play from track    ["
                      + keys.context1Label + "] Play All    ["
                      + keys.cancelLabel + "] Back"
                    : "[Enter] Play from track    [Esc] Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Error banner ──────────────────────────────────────────────────────────
    Rectangle {
        id: errorBanner
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(44)
        color: listenScreen._errorPersistent ? Theme.colorAccentNegative || "#8B1A1A"
                                             : Qt.darker(Theme.colorSecondary, 1.4)
        visible: listenScreen._errorMessage !== ""
        z: 160

        Row {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            spacing: root.vpx(12)

            Text {
                text: listenScreen._errorPersistent ? "⚠" : "ℹ"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                text: listenScreen._errorMessage
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                visible: listenScreen._errorPersistent
                text: "  [Settings →]"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // Dismiss on any key press for persistent errors
        Keys.onPressed: (event) => {
            if (listenScreen._errorPersistent) {
                listenScreen._errorMessage = ""
                event.accepted = true
            }
        }
    }

    // ── Artist detail view ────────────────────────────────────────────────────
    Item {
        id: artistDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "detail"

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._detailLoading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            z: 10
        }

        // ── Detail header bar ────────────────────────────────────────────────
        Rectangle {
            id: detailHeaderBar

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
                text: "◀  " + (listenScreen._artistData.title || "")
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
            }
        }

        // ── Album list ───────────────────────────────────────────────────────
        ListView {
            id: albumList

            anchors {
                top: detailHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(8)
            }

            model: listenScreen._albums
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    var next = albumList.currentIndex + 1
                    while (next < listenScreen._albums.length && listenScreen._albums[next].type === "header") next++
                    if (next < listenScreen._albums.length) albumList.currentIndex = next
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    var prev = albumList.currentIndex - 1
                    while (prev >= 0 && listenScreen._albums[prev].type === "header") prev--
                    if (prev >= 0) albumList.currentIndex = prev
                } else if (keys.isAccept(event)) {
                    event.accepted = true
                    var album = listenScreen._albums[albumList.currentIndex]
                    if (album && album.type === "album") {
                        listenScreen._selectedAlbumKey = album.ratingKey
                        listenScreen._albumReturnView = "detail"
                        listenScreen.currentView = "album"
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    listenScreen.currentView = "artists"
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "detail" && listenScreen._albums.length === 0 && !listenScreen._detailLoading
                text: "No albums found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Album row delegate ───────────────────────────────────────────
            delegate: Item {
                id: albumDelegate

                property bool isHeader: modelData.type === "header"

                width: albumList.width
                height: isHeader ? root.vpx(40) : root.vpx(96)

                // ── Section header ───────────────────────────────────────────
                Item {
                    anchors.fill: parent
                    visible: albumDelegate.isHeader

                    Text {
                        anchors {
                            left: parent.left
                            leftMargin: root.vpx(8)
                            bottom: parent.bottom
                            bottomMargin: root.vpx(6)
                        }
                        text: modelData.title || ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        font.bold: true
                    }

                    Rectangle {
                        anchors {
                            left: parent.left
                            right: parent.right
                            bottom: parent.bottom
                            leftMargin: root.vpx(8)
                            rightMargin: root.vpx(8)
                        }
                        height: 1
                        color: Theme.colorTextDim
                        opacity: 0.3
                    }
                }

                // ── Album row ────────────────────────────────────────────────────────────
                Item {
                    anchors.fill: parent
                    visible: !albumDelegate.isHeader

                    // Highlight background for focused item
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: albumDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)

                        scale: albumDelegate.ListView.isCurrentItem && albumList.activeFocus
                            ? Theme.focusScale : 1.0
                        Behavior on scale {
                            NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                        }

                        Behavior on opacity {
                            NumberAnimation { duration: Theme.animDurationFast }
                        }
                    }

                    Row {
                        anchors {
                            left: parent.left
                            right: parent.right
                            leftMargin: root.vpx(8)
                            rightMargin: root.vpx(8)
                            verticalCenter: parent.verticalCenter
                        }
                        spacing: root.vpx(12)

                        // ── Album art thumbnail ──────────────────────────
                        Item {
                            width: root.vpx(80)
                            height: root.vpx(80)

                            // Placeholder shown when there is no art or while loading
                            Rectangle {
                                anchors.fill: parent
                                color: Qt.darker(Theme.colorSecondary, 1.4)
                                radius: root.vpx(Theme.focusRingRadius)
                                visible: albumArt.status !== Image.Ready || !modelData.posterLocal

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - root.vpx(8)
                                    text: modelData.title || ""
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
                                id: albumArt

                                anchors.fill: parent
                                source: modelData.posterLocal || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                sourceSize.width: root.vpx(80)
                                sourceSize.height: root.vpx(80)
                                visible: status === Image.Ready && modelData.posterLocal
                                clip: true
                            }
                        }

                        // ── Album title and subtitle ─────────────────
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: root.vpx(4)
                            width: parent.width - root.vpx(80) - root.vpx(12)

                            Text {
                                width: parent.width
                                text: modelData.title || ""
                                color: albumDelegate.ListView.isCurrentItem
                                    ? Theme.colorText
                                    : Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeBody)
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }

                            Text {
                                width: parent.width
                                text: {
                                    var yr = modelData.year || ""
                                    var cnt = modelData.leafCount || 0
                                    if (cnt > 0) {
                                        var trackStr = cnt === 1 ? "1 track" : (cnt + " tracks")
                                        return yr ? (yr + " · " + trackStr) : trackStr
                                    }
                                    return yr ? "" + yr : ""
                                }
                                color: Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }
                        }
                    }

                    // Focus ring
                    FocusRing {
                        visible: albumDelegate.ListView.isCurrentItem && albumList.activeFocus
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            albumList.currentIndex = index
                            albumList.forceActiveFocus()
                        }
                        onDoubleClicked: {
                            albumList.currentIndex = index
                            var album = listenScreen._albums[index]
                            if (album && album.type === "album") {
                                listenScreen._selectedAlbumKey = album.ratingKey
                                listenScreen._albumReturnView = "detail"
                                listenScreen.currentView = "album"
                            }
                        }
                    }
                }
            }
        }
    }
}
