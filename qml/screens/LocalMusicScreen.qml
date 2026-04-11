import QtQuick
import ".."
import "../components"

// Local Music screen — browse and play local music files.
//
// Views:
//   "menu"       — main menu (Now Playing, Artists, Browse Folders, Scan Library)
//   "artists"    — grid/list of artists from the local music library
//   "detail"     — artist detail view showing album list
//   "album"      — album detail view showing track listing
//   "folders"    — filetree browser
//
// Focus flow:
//   Enter LocalMusicScreen → menu gets focus
//   D-pad                  — navigate menu / artist grid / album list / track list / folder list
//   A (Return)             — select item
//   B (Escape)             — go back one level; from menu emit back()
//
// Playback is handled by HomeScreen's musicPlayer (background playback).
// LocalMusicScreen calls homeScreen._playAlbum() etc.
FocusScope {
    id: localMusicScreen

    // Emit when B (Escape) is pressed from the menu so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Navigation target passed by HomeScreen when navigating from recently played.
    // Unused until Task 004.
    property var navTarget: null

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "menu", "artists", "detail", "album", "folders"
    property string currentView: "menu"

    // Current artists view mode: "grid" or "list"
    property string _viewMode: "grid"

    // True while artists are loading (set false when artistsModel arrives).
    property bool _loading: false

    // True while a scan is in progress.
    property bool _scanning: false

    // Prevent redundant initialization when re-entering the tab.
    property bool _initialized: false

    // Selected artist name (set when user selects an artist).
    property string _selectedArtistName: ""

    // Artist detail data and album list (populated when entering detail view).
    property var _artistData: ({})
    property var _albums: []

    // Selected album folder path (set when user selects an album).
    property string _selectedAlbumFolder: ""

    // Album detail data and track list (populated when entering album view).
    property var _albumData: ({})
    property var _tracks: []

    // Which view to return to when pressing B from album detail.
    property string _albumReturnView: "detail"

    // Guard: navTarget navigation fires only once (on first active focus).
    property bool _navTargetApplied: false

    // Filetree browser state.
    property var _folderData: ({})       // {folders: [], tracks: []}
    property string _currentFolder: ""   // current filetree path
    property var _folderHistory: []      // stack for filetree back navigation

    // Toast text
    property string _toastText: ""

    Timer {
        id: toastTimer
        interval: 5000
        onTriggered: localMusicScreen._toastText = ""
    }

    function _goToNowPlaying() {
        homeScreen._showNowPlaying()
    }

    // ── Connections ───────────────────────────────────────────────────────────
    Connections {
        target: localMusic ? localMusic : null
        function onArtistsModelChanged() {
            localMusicScreen._loading = false
            localMusicScreen._scanning = false
        }
        function onScanComplete() {
            localMusicScreen._scanning = false
        }
        function onArtistDetailReady(artistName, data) {
            if (artistName !== localMusicScreen._selectedArtistName) return
            localMusicScreen._artistData = data.artist
            localMusicScreen._albums = data.albums
            // Set initial focus to first non-header entry
            var firstAlbum = 0
            for (var i = 0; i < localMusicScreen._albums.length; i++) {
                if (localMusicScreen._albums[i].type !== "header") { firstAlbum = i; break }
            }
            albumList.currentIndex = firstAlbum
        }
        function onAlbumDetailReady(folderPath, data) {
            if (folderPath !== localMusicScreen._selectedAlbumFolder) return
            localMusicScreen._albumData = data.album
            localMusicScreen._tracks = data.tracks
            trackList.currentIndex = 0
        }
        function onFolderContentsReady(folderPath, data) {
            if (folderPath !== localMusicScreen._currentFolder) return
            localMusicScreen._folderData = data
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

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "menu") {
            localMusicMenu.forceActiveFocus()
        } else if (currentView === "artists") {
            if (_viewMode === "list") {
                artistList.forceActiveFocus()
            } else {
                artistGrid.forceActiveFocus()
            }
        } else if (currentView === "detail") {
            albumList.forceActiveFocus()
        } else if (currentView === "album") {
            trackList._playAllFocused = true
            trackList.forceActiveFocus()
            trackList.currentIndex = 0
            trackList.positionViewAtBeginning()
        } else if (currentView === "folders") {
            folderList.forceActiveFocus()
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_initialized) {
                _initialized = true
                // Check if cached data is already loaded
                if (localMusic && localMusic.artistsModel && localMusic.artistsModel.rowCount() > 0) {
                    _loading = false
                }
            }
            _routeFocus()
            if (navTarget && !_navTargetApplied) {
                _navTargetApplied = true
                if (navTarget.folder_path) {
                    _selectedAlbumFolder = navTarget.folder_path
                    _albumReturnView = "menu"
                    currentView = "album"
                    _routeFocus()
                }
            }
        }
    }

    onCurrentViewChanged: {
        if (currentView === "detail" && _selectedArtistName) {
            _artistData = {}
            _albums = []
            if (localMusic) localMusic.fetchArtistDetail(_selectedArtistName)
        } else if (currentView === "album" && _selectedAlbumFolder) {
            _albumData = {}
            _tracks = []
            if (localMusic) localMusic.fetchAlbumDetail(_selectedAlbumFolder)
        }
        _routeFocus()
    }

    on_ViewModeChanged: {
        if (currentView === "artists") _routeFocus()
    }

    Component.onCompleted: {
        if (settings) {
            var savedMode = settings.localMusicViewMode
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
            text: "Music"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Menu list ─────────────────────────────────────────────────────────────
    ListView {
        id: localMusicMenu

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

        visible: localMusicScreen.currentView === "menu"
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
            items.push({ label: "Artists", action: "artists" })
            items.push({ label: "Browse Folders", action: "folders" })
            items.push({ label: localMusicScreen._scanning ? "Scanning..." : "Scan Library",
                         action: "scan" })
            return items
        }

        delegate: Item {
            id: menuDelegate

            width: localMusicMenu.width
            height: root.vpx(64)

            readonly property string menuAction: modelData.action

            // Highlight background for the focused item
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: menuDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

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
                visible: menuDelegate.ListView.isCurrentItem && localMusicMenu.activeFocus
            }
        }

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                var item = localMusicMenu.currentItem
                if (item) {
                    if (item.menuAction === "nowplaying") {
                        localMusicScreen._goToNowPlaying()
                    } else if (item.menuAction === "artists") {
                        localMusicScreen.currentView = "artists"
                    } else if (item.menuAction === "folders") {
                        var musicDir = settings ? settings.localMusicDirectory : ""
                        if (musicDir && localMusic) {
                            localMusicScreen._currentFolder = musicDir
                            localMusicScreen._folderHistory = []
                            localMusicScreen._folderData = {}
                            localMusic.browseFolder(musicDir)
                        }
                        localMusicScreen.currentView = "folders"
                    } else if (item.menuAction === "scan") {
                        if (!localMusicScreen._scanning && localMusic) {
                            localMusicScreen._scanning = true
                            localMusicScreen._loading = true
                            localMusic.scan()
                        }
                    }
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localMusicScreen.back()
            }
        }
    }

    // ── Artist grid component ─────────────────────────────────────────────────
    LocalArtistGrid {
        id: artistGrid
        anchors.fill: parent
        visible: localMusicScreen.currentView === "artists" && localMusicScreen._viewMode === "grid"
        loading: localMusicScreen._loading
        _viewMode: localMusicScreen._viewMode
        onBack: localMusicScreen.currentView = "menu"
        onArtistSelected: (artistName) => {
            localMusicScreen._selectedArtistName = artistName
            localMusicScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { localMusicScreen._viewMode = mode }
    }

    // ── Artist list component ─────────────────────────────────────────────────
    LocalArtistList {
        id: artistList
        anchors.fill: parent
        visible: localMusicScreen.currentView === "artists" && localMusicScreen._viewMode === "list"
        loading: localMusicScreen._loading
        _viewMode: localMusicScreen._viewMode
        onBack: localMusicScreen.currentView = "menu"
        onArtistSelected: (artistName) => {
            localMusicScreen._selectedArtistName = artistName
            localMusicScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { localMusicScreen._viewMode = mode }
    }

    // ── Artist detail view ────────────────────────────────────────────────────
    Item {
        id: artistDetailView

        anchors.fill: parent
        visible: localMusicScreen.currentView === "detail"

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
                text: "◀  " + (localMusicScreen._artistData.title || "")
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

            model: localMusicScreen._albums
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
                    while (next < localMusicScreen._albums.length && localMusicScreen._albums[next].type === "header") next++
                    if (next < localMusicScreen._albums.length) albumList.currentIndex = next
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    var prev = albumList.currentIndex - 1
                    while (prev >= 0 && localMusicScreen._albums[prev].type === "header") prev--
                    if (prev >= 0) albumList.currentIndex = prev
                } else if (keys.isAccept(event)) {
                    event.accepted = true
                    var album = localMusicScreen._albums[albumList.currentIndex]
                    if (album && album.type === "album") {
                        localMusicScreen._selectedAlbumFolder = album.folderPath
                        localMusicScreen._albumReturnView = "detail"
                        localMusicScreen.currentView = "album"
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    localMusicScreen.currentView = "artists"
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: localMusicScreen.currentView === "detail" && localMusicScreen._albums.length === 0
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

                // ── Album row ────────────────────────────────────────────────
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
                                    var cnt = modelData.trackCount || 0
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
                            var album = localMusicScreen._albums[index]
                            if (album && album.type === "album") {
                                localMusicScreen._selectedAlbumFolder = album.folderPath
                                localMusicScreen._albumReturnView = "detail"
                                localMusicScreen.currentView = "album"
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Album detail view ─────────────────────────────────────────────────────
    Item {
        id: albumDetailView

        anchors.fill: parent
        visible: localMusicScreen.currentView === "album"

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
                    var title = localMusicScreen._albumData.title || ""
                    var year = localMusicScreen._albumData.year
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

            model: localMusicScreen._tracks
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
                        homeScreen._playAlbum(localMusicScreen._tracks, localMusicScreen._albumData, 0)
                        localMusicScreen._goToNowPlaying()
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        trackList._playAllFocused = false
                        trackList.currentIndex = 0
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        if (localMusicScreen._navTargetApplied) localMusicScreen.back()
                        else localMusicScreen.currentView = localMusicScreen._albumReturnView
                    }
                } else {
                    // Track list is focused
                    if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (trackList.currentIndex < localMusicScreen._tracks.length - 1) {
                            trackList.currentIndex++
                        }
                    } else if (event.key === Qt.Key_Up) {
                        event.accepted = true
                        if (trackList.currentIndex > 0) {
                            trackList.currentIndex--
                        } else {
                            // At first track — move focus to Play All button
                            trackList._playAllFocused = true
                            trackList.positionViewAtBeginning()
                        }
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        homeScreen._playAlbum(localMusicScreen._tracks, localMusicScreen._albumData, trackList.currentIndex)
                        localMusicScreen._goToNowPlaying()
                    } else if (keys.isContext1(event)) {
                        // X button — Play All (from track 1)
                        event.accepted = true
                        homeScreen._playAlbum(localMusicScreen._tracks, localMusicScreen._albumData, 0)
                        localMusicScreen._goToNowPlaying()
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        if (localMusicScreen._navTargetApplied) localMusicScreen.back()
                        else localMusicScreen.currentView = localMusicScreen._albumReturnView
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
                                         || !localMusicScreen._albumData.posterLocal

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - root.vpx(8)
                                    text: localMusicScreen._albumData.title || ""
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
                                source: localMusicScreen._albumData.posterLocal || ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                visible: status === Image.Ready
                                         && !!localMusicScreen._albumData.posterLocal
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
                                        value: localMusicScreen._albumData.artist || ""
                                    },
                                    {
                                        label: "Genre",
                                        value: localMusicScreen._albumData.genre || ""
                                    },
                                    {
                                        label: "Year",
                                        value: localMusicScreen._albumData.year > 0
                                            ? "" + localMusicScreen._albumData.year
                                            : ""
                                    },
                                    {
                                        label: "Tracks",
                                        value: localMusicScreen._tracks.length > 0
                                            ? localMusicScreen._tracks.length + " tracks · "
                                              + localMusicScreen._formatTotalDuration(localMusicScreen._tracks)
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
                                    homeScreen._playAlbum(localMusicScreen._tracks, localMusicScreen._albumData, 0)
                                    localMusicScreen._goToNowPlaying()
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
                visible: localMusicScreen.currentView === "album" && localMusicScreen._tracks.length === 0
                text: "No tracks found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Track row delegate ───────────────────────────────────────────
            delegate: Item {
                id: trackDelegate

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

                    // Track number
                    Text {
                        text: modelData.index > 0 ? "" + modelData.index : "" + (index + 1)
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(32)
                        horizontalAlignment: Text.AlignRight
                    }

                    // Track title
                    Text {
                        text: modelData.title || ""
                        color: trackDelegate.ListView.isCurrentItem && !trackList._playAllFocused ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        width: parent.width - root.vpx(32) - root.vpx(8) - root.vpx(48) - root.vpx(8)
                    }

                    // Duration (right-aligned, dim, M:SS format)
                    Text {
                        text: localMusicScreen._formatDuration(modelData.durationMs)
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
                        homeScreen._playAlbum(localMusicScreen._tracks, localMusicScreen._albumData, index)
                        localMusicScreen._goToNowPlaying()
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

    // ── Filetree browser view ─────────────────────────────────────────────────
    Item {
        id: folderBrowserView

        anchors.fill: parent
        visible: localMusicScreen.currentView === "folders"

        // ── Folder header bar ────────────────────────────────────────────────
        Rectangle {
            id: folderHeaderBar

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
                    if (localMusicScreen._folderHistory.length === 0) {
                        return "◀  Browse Folders"
                    }
                    // Show the current folder name
                    var parts = localMusicScreen._currentFolder.split("/")
                    return "◀  " + (parts[parts.length - 1] || "Browse Folders")
                }
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
            }
        }

        // ── Folder action bar ────────────────────────────────────────────────
        Rectangle {
            id: folderActionBar

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
                    ? "[" + keys.acceptLabel + "] Open    ["
                      + keys.context2Label + "] Play Folder    ["
                      + keys.cancelLabel + "] Back"
                    : "[Enter] Open    [2] Play Folder    [Esc] Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }

        // ── Folder/file list ─────────────────────────────────────────────────
        ListView {
            id: folderList

            anchors {
                top: folderHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: folderActionBar.top
                margins: root.vpx(8)
            }

            model: {
                var items = []
                var data = localMusicScreen._folderData
                if (data && data.folders) {
                    for (var i = 0; i < data.folders.length; i++) {
                        items.push({ type: "folder", data: data.folders[i] })
                    }
                }
                if (data && data.tracks) {
                    for (var j = 0; j < data.tracks.length; j++) {
                        items.push({ type: "track", data: data.tracks[j], trackIndex: j })
                    }
                }
                return items
            }
            clip: true
            focus: false
            keyNavigationEnabled: true
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode:      ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd:   height * 0.65

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = folderList.model[folderList.currentIndex]
                    if (!item) return
                    if (item.type === "folder") {
                        // Navigate into subfolder
                        var history = localMusicScreen._folderHistory.slice()
                        history.push(localMusicScreen._currentFolder)
                        localMusicScreen._folderHistory = history
                        localMusicScreen._currentFolder = item.data.path
                        localMusicScreen._folderData = {}
                        if (localMusic) localMusic.browseFolder(item.data.path)
                        folderList.currentIndex = 0
                    } else if (item.type === "track") {
                        // Play from this track
                        var tracks = localMusicScreen._folderData.tracks || []
                        var folderName = localMusicScreen._currentFolder.split("/")
                        var albumData = {
                            title: folderName[folderName.length - 1] || "Folder",
                            artist: "",
                            ratingKey: "",
                            source: "local",
                            folderPath: localMusicScreen._currentFolder,
                        }
                        homeScreen._playAlbum(tracks, albumData, item.trackIndex)
                        localMusicScreen._goToNowPlaying()
                    }
                } else if (keys.isContext2(event)) {
                    // Y button — play entire current folder
                    event.accepted = true
                    var folderTracks = localMusicScreen._folderData.tracks || []
                    if (folderTracks.length > 0) {
                        var fName = localMusicScreen._currentFolder.split("/")
                        var fAlbumData = {
                            title: fName[fName.length - 1] || "Folder",
                            artist: "",
                            ratingKey: "",
                            source: "local",
                            folderPath: localMusicScreen._currentFolder,
                        }
                        homeScreen._playAlbum(folderTracks, fAlbumData, 0)
                        localMusicScreen._goToNowPlaying()
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    var hist = localMusicScreen._folderHistory
                    if (hist.length > 0) {
                        // Go back to parent folder
                        var newHistory = hist.slice()
                        var parentFolder = newHistory.pop()
                        localMusicScreen._folderHistory = newHistory
                        localMusicScreen._currentFolder = parentFolder
                        localMusicScreen._folderData = {}
                        if (localMusic) localMusic.browseFolder(parentFolder)
                        folderList.currentIndex = 0
                    } else {
                        // At root — return to menu
                        localMusicScreen.currentView = "menu"
                    }
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: folderList.count === 0
                text: "Empty folder"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Folder/file row delegate ─────────────────────────────────────
            delegate: Item {
                id: folderDelegate

                width: folderList.width
                height: root.vpx(48)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: folderDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: folderDelegate.ListView.isCurrentItem && folderList.activeFocus
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

                    // Icon
                    Text {
                        text: modelData.type === "folder" ? "📁" : "♪"
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        width: root.vpx(24)
                        color: Theme.colorText
                    }

                    // Name
                    Text {
                        text: modelData.type === "folder"
                            ? modelData.data.name || ""
                            : modelData.data.title || ""
                        color: folderDelegate.ListView.isCurrentItem
                            ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        width: parent.width - root.vpx(24) - root.vpx(8) - root.vpx(64) - root.vpx(8)
                    }

                    // Subtitle (item count for folders, duration for tracks)
                    Text {
                        text: {
                            if (modelData.type === "folder") {
                                var cnt = modelData.data.itemCount || 0
                                return cnt > 0 ? cnt + " files" : ""
                            }
                            return localMusicScreen._formatDuration(modelData.data.durationMs)
                        }
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        width: root.vpx(64)
                        horizontalAlignment: Text.AlignRight
                    }
                }

                // Focus ring
                FocusRing {
                    visible: folderDelegate.ListView.isCurrentItem && folderList.activeFocus
                }
            }
        }
    }

    // ── Toast ─────────────────────────────────────────────────────────────────
    Rectangle {
        id: toastBanner
        anchors {
            bottom: parent.bottom
            horizontalCenter: parent.horizontalCenter
            bottomMargin: root.vpx(60)
        }
        width: toastLabel.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(Theme.focusRingRadius)
        color: Theme.colorSecondary
        opacity: localMusicScreen._toastText !== "" ? 0.95 : 0.0
        visible: opacity > 0

        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: localMusicScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }
}
