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

    // Previous view — used by Now Playing's B button to return to the right place
    property string _previousView: "menu"

    function _goToNowPlaying() {
        _previousView = currentView
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
        }
        function onLibrariesModelChanged() {
            listenScreen._trySelectMusicLibrary()
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
            listenMenu.forceActiveFocus()
        } else if (currentView === "artists") {
            artistGrid.forceActiveFocus()
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
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_initialized) {
                _initialized = true
                _loading = true
                _noLibrary = false
                if (plex) {
                    plex.refresh()
                    _trySelectMusicLibrary()
                }
            }
            _routeFocus()
        }
    }

    onCurrentViewChanged: {
        if (currentView === "detail" && _selectedArtistKey) {
            _artistData = plex.getArtist(_selectedArtistKey)
            _albums = plex.getArtistAlbums(_selectedArtistKey)
            // Set initial focus to first non-header entry (index 1, since index 0 is the first header)
            var firstAlbum = 0
            for (var i = 0; i < _albums.length; i++) {
                if (_albums[i].type !== "header") {
                    firstAlbum = i
                    break
                }
            }
            albumList.currentIndex = firstAlbum
        } else if (currentView === "recentlyadded" && _musicSectionKey) {
            _recentAlbums = plex.getRecentlyAddedAlbums(_musicSectionKey)
            recentAlbumsList.currentIndex = 0
        } else if (currentView === "album" && _selectedAlbumKey) {
            _albumData = plex.getAlbum(_selectedAlbumKey)
            _tracks = plex.getTracks(_selectedAlbumKey)
            trackList.currentIndex = 0
        }
        _routeFocus()
    }

    // ── Header bar (shared by menu and artists views) ──────────────────────────
    Rectangle {
        id: headerBar

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        color: Theme.colorSecondary
        visible: listenScreen.currentView === "menu" || listenScreen.currentView === "artists"

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: listenScreen.currentView === "artists" ? "◀  Artists" : "Listen"
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
            margins: root.vpx(16)
        }

        visible: listenScreen.currentView === "menu"
        clip: true
        focus: false
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast

        model: {
            var items = []
            // Now Playing — only show when music is loaded
            if (homeScreen._playbackTracks.length > 0) {
                items.push({ label: "Now Playing", action: "nowplaying" })
            }
            items.push({ label: "Recently Added", action: "recentlyadded" })
            items.push({ label: "Artists", action: "artists" })
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
                    color: menuDelegate.ListView.isCurrentItem && listenMenu.activeFocus
                        ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: menuDelegate.ListView.isCurrentItem
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
                    } else if (item.menuAction === "artists") {
                        listenScreen.currentView = "artists"
                    }
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.back()
            } else if (event.key === Qt.Key_Up && listenMenu.currentIndex === 0) {
                event.accepted = true
                listenScreen.back()
            }
        }
    }

    // ── Artist grid ───────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h)
    readonly property int _targetCellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    GridView {
        id: artistGrid

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: plex ? plex.artistsModel : null
        clip: true
        focus: true
        visible: listenScreen.currentView === "artists"

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(listenScreen._targetCellW + listenScreen._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(listenScreen._targetCellW + listenScreen._cellSpacing)
        cellHeight: root.vpx(listenScreen._cellH + listenScreen._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                var item = artistGrid.currentItem
                if (item) {
                    listenScreen._selectedArtistKey = item.artistRatingKey
                    listenScreen.artistSelected(item.artistRatingKey)
                    listenScreen.currentView = "detail"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.currentView = "menu"
            } else if (event.key === Qt.Key_Up && artistGrid.currentIndex < artistGrid._columns) {
                event.accepted = true
                listenScreen.currentView = "menu"
            }
        }

        // ── Loading indicator ────────────────────────────────────────────────
        Column {
            anchors.centerIn: parent
            visible: listenScreen._loading
            spacing: root.vpx(8)

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Loading music library..."
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "First load may take several minutes"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                opacity: 0.7
            }
        }

        // ── No library message ───────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._noLibrary && !listenScreen._loading
            text: "No music library found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Empty state (loaded but no artists) ──────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: !listenScreen._loading && !listenScreen._noLibrary && artistGrid.count === 0
            text: "No artists found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Artist tile delegate ─────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose ratingKey so the key handler can read it.
            readonly property string artistRatingKey: model.ratingKey

            width: artistGrid.cellWidth
            height: artistGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(listenScreen._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus ? 0.15 : 0.0

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // ── Poster image area ────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~80% of the card height
                    height: Math.round(parent.height * 0.80)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.imageLocal === ""

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
                        source: model.imageLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(listenScreen._targetCellW)
                        sourceSize.height: Math.round(root.vpx(listenScreen._cellH) * 0.80)
                        visible: status === Image.Ready && model.imageLocal !== ""
                        clip: true
                    }
                }

                // ── Artist name label ────────────────────────────────────────
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

                // ── Genre subtitle ───────────────────────────────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.genre || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus
                }
            }
        }
    }

    // ── Album detail view ─────────────────────────────────────────────────────
    Item {
        id: albumDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "album"

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
                visible: listenScreen.currentView === "album" && listenScreen._tracks.length === 0
                text: "No tracks found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Track row delegate ───────────────────────────────────────────
            delegate: Item {
                id: trackDelegate

                // True when this track is the one currently playing
                readonly property bool isPlaying: homeScreen._playingAlbumKey === listenScreen._selectedAlbumKey
                                                  && homeScreen._playingIndex === index

                width: trackList.width
                height: root.vpx(48)

                // Highlight background for focused item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: trackDelegate.ListView.isCurrentItem && !trackList._playAllFocused ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

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

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.currentView = listenScreen._previousView || "menu"
            } else if (keys.isAccept(event)) {
                // A button — play/pause
                event.accepted = true
                homeScreen._togglePlayPause()
            } else if (keys.isContext1(event)) {
                // X button — play/pause (handled globally by HomeScreen, but accept here too)
                event.accepted = true
                homeScreen._togglePlayPause()
            } else if (event.key === Qt.Key_Left || keys.isPrevTab(event)) {
                event.accepted = true
                if (homeScreen._playingIndex > 0) {
                    homeScreen._playTrackAtIndex(homeScreen._playingIndex - 1)
                }
            } else if (event.key === Qt.Key_Right || keys.isNextTab(event)) {
                event.accepted = true
                homeScreen._playNext()
            }
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

            // ── Right: track info + controls ─────────────────────────────────
            Column {
                id: nowPlayingInfoColumn

                anchors {
                    top: parent.top
                    left: nowPlayingArtArea.right
                    right: parent.right
                    leftMargin: root.vpx(32)
                }
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

                // Year
                Text {
                    width: parent.width
                    text: homeScreen._playbackAlbumData.year > 0
                        ? "" + homeScreen._playbackAlbumData.year
                        : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: homeScreen._playbackAlbumData.year > 0
                }

                // Spacer
                Item { width: 1; height: root.vpx(16) }

                // ── Playback controls (visual, not focusable) ────────────────
                Row {
                    spacing: root.vpx(32)

                    // Skip back
                    Text {
                        text: "◀◀"
                        color: homeScreen._playingIndex > 0
                            ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(28)
                        opacity: homeScreen._playingIndex > 0 ? 1.0 : 0.4
                    }

                    // Play/Pause
                    Text {
                        text: homeScreen.musicPlaybackState === 1  // MediaPlayer.PlayingState == 1
                            ? "❚❚" : "▶"
                        color: Theme.colorPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(32)
                    }

                    // Skip forward
                    Text {
                        text: "▶▶"
                        color: homeScreen._playingIndex < homeScreen._playbackTracks.length - 1
                            ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(28)
                        opacity: homeScreen._playingIndex < homeScreen._playbackTracks.length - 1
                            ? 1.0 : 0.4
                    }
                }

                // Spacer
                Item { width: 1; height: root.vpx(8) }

                // ── Progress bar ─────────────────────────────────────────────
                Item {
                    width: parent.width
                    height: root.vpx(6)

                    // Track background
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.6)
                        radius: root.vpx(3)
                    }

                    // Progress fill
                    Rectangle {
                        width: homeScreen.musicDuration > 0
                            ? parent.width * (homeScreen.musicPosition / homeScreen.musicDuration)
                            : 0
                        height: parent.height
                        color: Theme.colorPrimary
                        radius: root.vpx(3)
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

                // ── Space reserved for future lyrics toggle ──────────────────
                Item { width: 1; height: root.vpx(16) }
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
                    ? "[" + keys.acceptLabel + "] Play/Pause    ["
                      + keys.cancelLabel + "] Back    [◀] Prev    [▶] Next"
                    : "[Enter] Play/Pause    [Esc] Back    [←] Prev    [→] Next"
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
                visible: listenScreen.currentView === "recentlyadded" && listenScreen._recentAlbums.length === 0
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

    // ── Artist detail view ────────────────────────────────────────────────────
    Item {
        id: artistDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "detail"

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
                visible: listenScreen.currentView === "detail" && listenScreen._albums.length === 0
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
