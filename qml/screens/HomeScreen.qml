import QtQuick
import QtMultimedia
import ".."
import "../components"
import "."

// Home screen with top-level section navigation (Games / Watch / Settings).
//
// Focus flow:
//   App start → HomeScreen → tabBar → first tab (Games) has activeFocus
//   Left/Right  — move between tabs
//   LB/RB       — move between tabs (works even when focus is in content area)
//   A (Return)  — move focus into content area
//   B (Escape)  — return focus to tab bar (emitted by child screens via back())
//   Start/F10   — emit requestQuit() to open the quit dialog
//   Escape on tab bar — emit requestQuit() to open the quit dialog
FocusScope {
    id: homeScreen

    // Only process input when this screen is active.
    enabled: focus

    // Emitted when the user requests to quit (Start button or Escape on tab bar).
    signal requestQuit()

    // Emitted when SettingsScreen requests the controller mapping dialog.
    signal showControllerMapping()

    // Index of the currently selected (displayed) tab.
    property int currentTab: 0

    // All possible tabs (Settings is always last and always visible)
    readonly property var _allTabs: [
        { name: "Retro Games", source: "RetroGamesScreen.qml", setting: "showRetroGamesTab" },
        { name: "PC Games",    source: "PcGamesScreen.qml",    setting: "showPcGamesTab" },
        { name: "Plex Media",  source: "WatchScreen.qml",      setting: "showWatchTab" },
        { name: "Plex Music",  source: "ListenScreen.qml",     setting: "showListenTab" },
    ]

    // Tab visibility — built once on startup from saved settings.
    // Changes take effect on next launch (toggling in Settings saves
    // the preference and shows a "Restart to apply" toast).
    // IMPORTANT: These must NOT be bindings to settings properties,
    // otherwise toggling a setting triggers a live Repeater rebuild
    // which freezes the UI.
    property var tabNames:   []
    property var tabSources: []

    function _initTabs() {
        var names = []
        var sources = []
        var allTabs = _allTabs
        for (var i = 0; i < allTabs.length; i++) {
            var show = !settings || settings[allTabs[i].setting]
            if (show) {
                names.push(allTabs[i].name)
                sources.push(allTabs[i].source)
            }
        }
        names.push("Settings")
        sources.push("SettingsScreen.qml")
        tabNames = names
        tabSources = sources
    }

    // Set to true when LB/RB is pressed while focus is in the content area,
    // so onLoaded can give focus to the newly loaded content item.
    property bool _focusContentOnLoad: false

    // ── MPV running state ─────────────────────────────────────────────────────
    // True while an MPV process is active (used to gate the subtitle overlay).
    property bool _mpvRunning: false

    Connections {
        target: plex
        function onMpvStarted() { homeScreen._mpvRunning = true }
        function onMpvFinished() { homeScreen._mpvRunning = false }
        function onLyricsReady(ratingKey, lines) {
            if (ratingKey === homeScreen._nowPlayingTrack.ratingKey) {
                homeScreen._lyricsLines = lines
                homeScreen._lyricsAvailable = true
                homeScreen._lyricsRatingKey = ratingKey
            }
        }
        function onLyricsUnavailable(ratingKey) {
            if (ratingKey === homeScreen._nowPlayingTrack.ratingKey) {
                homeScreen._lyricsLines = []
                homeScreen._lyricsAvailable = false
                homeScreen._lyricsRatingKey = ratingKey
            }
        }
    }

    // ── Global music playback state ───────────────────────────────────────────
    // Index into _playOrder of the currently playing position (-1 = not playing).
    property int _playingIndex: -1
    // ratingKey of the album currently being played.
    property string _playingAlbumKey: ""
    // Metadata of the currently playing track (for Now Playing display).
    property var _nowPlayingTrack: ({})
    // Full track list for the current album.
    property var _playbackTracks: []
    // Album metadata for Now Playing display.
    property var _playbackAlbumData: ({})
    // Track name shown in the persistent status bar indicator.
    property string nowPlayingTrack: ""
    // Ordered list of indices into _playbackTracks. Shuffled when _shuffleEnabled,
    // otherwise [0, 1, 2, ...] in natural order.
    property var _playOrder: []
    // Whether shuffle is active. Rebuilt on each _playAlbum call.
    property bool _shuffleEnabled: false
    // Repeat mode: "off" | "one" | "all"
    property string _repeatMode: "off"
    // Lyrics for the currently playing track.
    property var    _lyricsLines:     []      // list of {ms, text} — empty = not loaded yet
    property bool   _lyricsAvailable: false   // false = unavailable or not yet fetched
    property string _lyricsRatingKey: ""      // ratingKey of the track lyrics were fetched for
    property bool   _lyricsEnabled:   true    // user toggle — hides/shows the lyrics panel

    // ── Global audio player ───────────────────────────────────────────────────
    MediaPlayer {
        id: musicPlayer
        audioOutput: AudioOutput { id: audioOut; volume: 1.0 }

        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.EndOfMedia) {
                homeScreen._playNext()
            } else if (mediaStatus === MediaPlayer.InvalidMedia) {
                // Track failed to load — stop rather than silently skipping.
                // The user can press Next manually.
                console.warn("HomeScreen: track failed to load (InvalidMedia) —",
                             homeScreen._nowPlayingTrack.title || "unknown")
            }
        }
    }

    // Expose playback state as properties so child screens (loaded via Loader)
    // can bind to them without needing direct access to the musicPlayer id.
    readonly property int musicPlaybackState: musicPlayer.playbackState
    readonly property int musicPosition: musicPlayer.position
    readonly property int musicDuration: musicPlayer.duration

    // ── Global playback functions ─────────────────────────────────────────────

    function _buildPlayOrder(length, startTrackIndex) {
        // Build _playOrder: shuffled or natural. startTrackIndex is the track the
        // user chose; it is always placed at position 0 in the order so it plays first.
        var order = []
        for (var i = 0; i < length; i++) order.push(i)
        if (_shuffleEnabled) {
            // Fisher-Yates shuffle
            for (var j = length - 1; j > 0; j--) {
                var k = Math.floor(Math.random() * (j + 1))
                var tmp = order[j]; order[j] = order[k]; order[k] = tmp
            }
            // Move startTrackIndex to position 0
            var pos = order.indexOf(startTrackIndex)
            if (pos > 0) { order.splice(pos, 1); order.unshift(startTrackIndex) }
        } else {
            // Natural order: rotate so startTrackIndex is first
            order = order.slice(startTrackIndex).concat(order.slice(0, startTrackIndex))
        }
        return order
    }

    function _playAlbum(tracks, albumData, startIndex) {
        if (!tracks || tracks.length === 0) return
        _playbackTracks = tracks
        _playbackAlbumData = albumData
        _playingAlbumKey = albumData.ratingKey || ""
        _playOrder = _buildPlayOrder(tracks.length, startIndex)
        _playTrackAtIndex(0)
    }

    // idx is a position in _playOrder, not a direct track index.
    function _playTrackAtIndex(idx) {
        if (idx < 0 || idx >= _playOrder.length) {
            // End of queue — stop (repeat-all wraps before reaching here)
            _playingIndex = -1
            _nowPlayingTrack = {}
            nowPlayingTrack = ""
            musicPlayer.stop()
            return
        }
        _playingIndex = idx
        var track = _playbackTracks[_playOrder[idx]]
        _nowPlayingTrack = track
        nowPlayingTrack = track.title || ""
        _lyricsLines = []
        _lyricsAvailable = false
        _lyricsRatingKey = ""
        if (plex && track.ratingKey) {
            plex.getLyrics(track.ratingKey, track.title,
                           track.grandparentTitle, track.parentTitle, track.durationMs)
        }
        var url = plex.getTrackStreamUrl(track.mediaKey)
        musicPlayer.source = url
        musicPlayer.play()
    }

    function _playNext() {
        if (_repeatMode === "one") {
            // Replay the same track from the start
            var url = plex.getTrackStreamUrl(_playbackTracks[_playOrder[_playingIndex]].mediaKey)
            musicPlayer.source = url
            musicPlayer.play()
            return
        }
        if (_playingIndex < _playOrder.length - 1) {
            _playTrackAtIndex(_playingIndex + 1)
        } else if (_repeatMode === "all" && _playOrder.length > 0) {
            _playTrackAtIndex(0)
        } else {
            _playingIndex = -1
            _nowPlayingTrack = {}
            nowPlayingTrack = ""
            musicPlayer.stop()
        }
    }

    function _playPrev() {
        // If more than 3s into the track, restart it instead of going back
        if (musicPlayer.position > 3000 && _playingIndex >= 0) {
            musicPlayer.position = 0
            return
        }
        if (_playingIndex > 0) {
            _playTrackAtIndex(_playingIndex - 1)
        } else if (_repeatMode === "all" && _playOrder.length > 0) {
            _playTrackAtIndex(_playOrder.length - 1)
        } else {
            musicPlayer.position = 0
        }
    }

    function _toggleShuffle() {
        _shuffleEnabled = !_shuffleEnabled
        if (_playingIndex >= 0 && _playOrder.length > 0) {
            // Rebuild the play order keeping the current track at position 0
            var currentTrackIdx = _playOrder[_playingIndex]
            _playOrder = _buildPlayOrder(_playbackTracks.length, currentTrackIdx)
            _playingIndex = 0
        }
    }

    function _cycleRepeat() {
        if (_repeatMode === "off")      _repeatMode = "all"
        else if (_repeatMode === "all") _repeatMode = "one"
        else                            _repeatMode = "off"
    }

    function _togglePlayPause() {
        if (musicPlayer.playbackState === MediaPlayer.PlayingState) {
            musicPlayer.pause()
        } else {
            musicPlayer.play()
        }
    }

    function _seekBy(deltaMs) {
        if (musicPlayer.duration <= 0) return
        musicPlayer.position = Math.max(0, Math.min(musicPlayer.position + deltaMs, musicPlayer.duration))
    }

    function _seekTo(ms) {
        if (musicPlayer.duration <= 0) return
        musicPlayer.position = Math.max(0, Math.min(Math.round(ms), musicPlayer.duration))
    }

    function _formatDuration(ms) {
        if (!ms || ms <= 0) return "0:00"
        var totalSec = Math.floor(ms / 1000)
        var min = Math.floor(totalSec / 60)
        var sec = totalSec % 60
        return min + ":" + (sec < 10 ? "0" : "") + sec
    }

    // Intercept Start and X button (isContext1) at the HomeScreen level.
    // Also intercept X button (isContext1) for global play/pause when music is loaded.
    // Also intercept Y button (isContext2) to show subtitle overlay when MPV is running
    // on the Watch tab.
    Keys.onPressed: (event) => {
        if (keys.isMenu(event)) {
            event.accepted = true
            homeScreen.requestQuit()
        } else if (keys.isContext1(event) && musicPlayer.playbackState !== MediaPlayer.StoppedState) {
            // Global X button play/pause — only when music is actively playing or paused.
            // When stopped (no music loaded or album ended), let the event pass through
            // to child screens (e.g. Retro Games uses X for Favorite).
            event.accepted = true
            homeScreen._togglePlayPause()
        }
    }

    // Trigger slide-in animation whenever the tab changes.
    onCurrentTabChanged: {
        contentLoader.x = contentArea.width
        slideInAnimation.start()
    }

    // ── Tab bar ──────────────────────────────────────────────────────────────
    Row {
        id: tabBar
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        spacing: root.vpx(8)

        focus: true

        Repeater {
            id: tabRepeater
            model: homeScreen.tabNames

            // Each tab is a FocusScope so it can own the focus ring.
            FocusScope {
                id: tabItem

                readonly property int tabIndex: index
                readonly property bool isSelected: homeScreen.currentTab === index

                width: root.vpx(140)
                height: tabBar.height

                // Navigate between tabs with Left/Right.
                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Left) {
                        event.accepted = true
                        if (homeScreen.currentTab > 0) {
                            homeScreen.currentTab--
                            tabRepeater.itemAt(homeScreen.currentTab).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Right) {
                        event.accepted = true
                        if (homeScreen.currentTab < homeScreen.tabNames.length - 1) {
                            homeScreen.currentTab++
                            tabRepeater.itemAt(homeScreen.currentTab).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (contentLoader.item) {
                            contentLoader.item.forceActiveFocus()
                        }
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        // Move focus into the content area.
                        if (contentLoader.item) {
                            contentLoader.item.forceActiveFocus()
                        }
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        // Escape on the tab bar → open quit dialog.
                        homeScreen.requestQuit()
                    }
                }

                // Tab label
                Text {
                    id: tabLabel
                    anchors {
                        horizontalCenter: parent.horizontalCenter
                        verticalCenter: parent.verticalCenter
                        verticalCenterOffset: -root.vpx(4)
                    }
                    text: modelData
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    color: tabItem.activeFocus ? Theme.colorText : Theme.colorTextDim
                }

                // Active-tab underline indicator
                Rectangle {
                    anchors {
                        bottom: parent.bottom
                        horizontalCenter: parent.horizontalCenter
                    }
                    width: tabLabel.width + root.vpx(8)
                    height: root.vpx(3)
                    color: Theme.colorTabUnderline
                    visible: tabItem.isSelected

                    Behavior on width {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                FocusRing {}
            }
        }
    }

    // ── Clock display ─────────────────────────────────────────────────────────
    ClockDisplay {
        id: clockDisplay
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: tabBar.verticalCenter
        }
    }

    // ── Network status indicator ──────────────────────────────────────────────
    NetworkIndicator {
        id: networkIndicator
        anchors {
            right: clockDisplay.left
            rightMargin: root.vpx(12)
            verticalCenter: tabBar.verticalCenter
        }
        online: networkMonitor ? networkMonitor.online : true
        visible: settings ? settings.showNetworkIndicator : true
    }

    // ── Now Playing persistent indicator ─────────────────────────────────────
    // Shows "♫ Track Name" in the top-right status bar when music is playing/paused.
    Text {
        id: nowPlayingIndicator
        visible: homeScreen.nowPlayingTrack !== ""
        text: "♫ " + homeScreen.nowPlayingTrack
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeSmall)
        elide: Text.ElideRight
        width: Math.min(implicitWidth, root.vpx(200))
        anchors {
            right: networkIndicator.left
            rightMargin: root.vpx(12)
            verticalCenter: tabBar.verticalCenter
        }
    }

    // Thin separator line below the tab bar
    Rectangle {
        id: separator
        anchors {
            top: tabBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(1)
        color: Theme.colorTextDim
        opacity: 0.3
    }

    // ── Content area ─────────────────────────────────────────────────────────
    Item {
        id: contentArea
        anchors {
            top: separator.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        clip: true

        Loader {
            id: contentLoader
            width: parent.width
            height: parent.height
            asynchronous: false
            source: homeScreen.tabSources[homeScreen.currentTab]

            // When the loaded item changes, wire up its back() signal and
            // give focus to the new content if LB/RB was pressed from content.
            onLoaded: {
                if (item) {
                    item.back.connect(returnFocusToTabBar)
                    // Forward showControllerMapping if the loaded screen has it
                    // (SettingsScreen emits this to open the mapping dialog).
                    if (item.showControllerMapping !== undefined) {
                        item.showControllerMapping.connect(homeScreen.showControllerMapping)
                    }
                    if (homeScreen._focusContentOnLoad) {
                        homeScreen._focusContentOnLoad = false
                        item.forceActiveFocus()
                    }
                }
            }
        }

        // Slide-in animation: slides the loader from off-screen right to x=0.
        NumberAnimation {
            id: slideInAnimation
            target: contentLoader
            property: "x"
            to: 0
            duration: Theme.animDurationNormal
            easing.type: Easing.OutQuad
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function returnFocusToTabBar() {
        var item = tabRepeater.itemAt(homeScreen.currentTab)
        if (item) item.forceActiveFocus()
    }

    // On startup, build tab arrays and give focus to the first tab.
    Component.onCompleted: {
        _initTabs()
        Qt.callLater(function() {
            var item = tabRepeater.itemAt(0)
            if (item) item.forceActiveFocus()
        })
    }


}
