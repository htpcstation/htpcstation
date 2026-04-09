import QtQuick
import QtMultimedia
import ".."
import "../components"
import "."

// Home screen with two-level launcher UI.
//
// Focus flow:
//   App start → HomeScreen → buttonRow → first button has activeFocus
//   Left/Right  — move between launcher buttons
//   A (Return)  — activate tab: load content, hide launcher
//   B (Escape)  — return from tab content to launcher (emitted by child screens via back())
//   Start/F10   — emit requestQuit() to open the quit dialog
//   X button    — global play/pause when music is playing/paused
FocusScope {
    id: homeScreen

    // Only process input when this screen is active.
    enabled: focus

    // Emitted when the user requests to quit (Start button or Escape on tab bar).
    signal requestQuit()

    // Emitted when SettingsScreen requests the controller mapping dialog.
    signal showControllerMapping()

    // All possible tabs (Settings is always visible — setting === null)
    readonly property var _allTabs: [
        { name: "Retro Games", source: "RetroGamesScreen.qml", setting: "showRetroGamesTab", slug: "retrogames" },
        { name: "PC Games",    source: "PcGamesScreen.qml",    setting: "showPcGamesTab",    slug: "pcgames"    },
        { name: "Moonlight",   source: "MoonlightScreen.qml",  setting: "showMoonlightTab",  slug: "moonlight"  },
        { name: "Plex Media",  source: "WatchScreen.qml",      setting: "showWatchTab",       slug: "plexmedia"  },
        { name: "Plex Music",  source: "ListenScreen.qml",     setting: "showListenTab",      slug: "plexmusic"  },
        { name: "Settings",    source: "SettingsScreen.qml",   setting: null,                 slug: "settings"   },
    ]

    // Tab visibility — built once on startup from saved settings.
    // Changes take effect on next launch (toggling in Settings saves
    // the preference and shows a "Restart to apply" toast).
    // IMPORTANT: These must NOT be bindings to settings properties,
    // otherwise toggling a setting triggers a live Repeater rebuild
    // which freezes the UI.
    property var tabNames:   []
    property var tabSources: []
    property var tabSlugs:   []

    // Launcher state
    property bool _launcherVisible: true   // true = show launcher, false = show tab content
    property int  _activeTab: -1           // index into tabNames of the loaded tab (-1 = none)
    property int  _lastFocusedButton: 0    // which button had focus before entering a tab

    // Opacity properties for tab transition fade animation
    property real _launcherOpacity: 1.0
    property real _contentOpacity:  0.0

    function _initTabs() {
        var names = []
        var sources = []
        var slugs = []
        var allTabs = _allTabs
        for (var i = 0; i < allTabs.length; i++) {
            var tab = allTabs[i]
            var show = tab.setting === null || !settings || settings[tab.setting]
            if (show) {
                names.push(tab.name)
                sources.push(tab.source)
                slugs.push(tab.slug)
            }
        }
        tabNames = names
        tabSources = sources
        tabSlugs = slugs
    }

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

    // ── Launcher background ───────────────────────────────────────────────────
    Image {
        id: launcherBackground
        anchors.fill: parent
        source: settings ? settings.themeDir + "homescreen/home-background.png" : ""
        fillMode: Image.PreserveAspectCrop
        visible: homeScreen._launcherVisible
        opacity: homeScreen._launcherOpacity
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
    }

    // ── Launcher button row ───────────────────────────────────────────────────
    Row {
        id: buttonRow
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.top
        anchors.verticalCenterOffset: parent.height / 6
        spacing: root.vpx(24)
        visible: homeScreen._launcherVisible
        focus: homeScreen._launcherVisible
        opacity: homeScreen._launcherOpacity
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }

        property int _buttonSize: {
            var count = homeScreen.tabNames.length
            if (count === 0) return root.vpx(200)
            var computed = (parent.width * 0.80 - spacing * (count - 1)) / count
            return Math.min(Math.round(computed), root.vpx(200))
        }

        Repeater {
            id: buttonRepeater
            model: homeScreen.tabNames

            FocusScope {
                id: buttonItem

                readonly property int buttonIndex: index

                width: buttonRow._buttonSize
                height: buttonRow._buttonSize

                scale: activeFocus ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Left) {
                        event.accepted = true
                        if (index > 0) {
                            buttonRepeater.itemAt(index - 1).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Right) {
                        event.accepted = true
                        if (index < homeScreen.tabNames.length - 1) {
                            buttonRepeater.itemAt(index + 1).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Up) {
                        event.accepted = true
                        // do nothing
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        // do nothing
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        homeScreen._lastFocusedButton = index
                        homeScreen._activeTab = index
                        contentLoader.source = homeScreen.tabSources[index]
                        homeScreen._launcherOpacity = 0.0   // start fade-out
                        tabEnterTimer.restart()
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        // do nothing — Start still handles quit at HomeScreen level
                    }
                }

                // Button image
                Image {
                    id: buttonImage
                    anchors.fill: parent
                    source: (settings && index < homeScreen.tabSlugs.length && homeScreen.tabSlugs[index])
                        ? settings.themeDir + "homescreen/" + homeScreen.tabSlugs[index] + "-button.png"
                        : ""
                    fillMode: Image.PreserveAspectFit
                    visible: buttonImage.status === Image.Ready
                }

                // Fallback when image is not ready
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSurface
                    visible: buttonImage.status !== Image.Ready

                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        color: Theme.colorText
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        width: parent.width - root.vpx(8)
                    }
                }

                // Focus ring
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.color: Theme.colorAccent
                    border.width: root.vpx(4)
                    radius: root.vpx(6)
                    visible: buttonItem.activeFocus
                }
            }
        }
    }

    // ── Content area ─────────────────────────────────────────────────────────
    Item {
        anchors.fill: parent
        visible: !homeScreen._launcherVisible
        opacity: homeScreen._contentOpacity
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }

        Loader {
            id: contentLoader
            width: parent.width
            height: parent.height
            asynchronous: false
            source: ""

            // When the loaded item changes, wire up its back() signal.
            onLoaded: {
                if (item) {
                    item.back.connect(returnFocusToTabBar)
                    // Forward showControllerMapping if the loaded screen has it
                    // (SettingsScreen emits this to open the mapping dialog).
                    if (item.showControllerMapping !== undefined) {
                        item.showControllerMapping.connect(homeScreen.showControllerMapping)
                    }
                }
            }
        }
    }

    // ── Clock display — declared after content area so it renders on top ────────
    ClockDisplay {
        id: clockDisplay
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.top
            verticalCenterOffset: root.vpx(28)
        }
    }

    // ── Network status indicator ──────────────────────────────────────────────
    NetworkIndicator {
        id: networkIndicator
        anchors {
            right: clockDisplay.left
            rightMargin: root.vpx(12)
            verticalCenter: clockDisplay.verticalCenter
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
            verticalCenter: clockDisplay.verticalCenter
        }
    }

    // ── Play/pause hint — shown next to now playing indicator ─────────────────
    Text {
        id: playPauseHint
        visible: homeScreen.nowPlayingTrack !== ""
        text: homeScreen.musicPlaybackState === MediaPlayer.PlayingState ? "▶" : "■"
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeSmall)
        anchors {
            right: nowPlayingIndicator.left
            rightMargin: root.vpx(8)
            verticalCenter: clockDisplay.verticalCenter
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function returnFocusToTabBar() {
        homeScreen._contentOpacity = 0.0   // start fade-out
        tabExitTimer.restart()
    }

    Timer {
        id: tabEnterTimer
        interval: Theme.animDurationFast   // 150ms — matches fade duration
        onTriggered: {
            if (homeScreen._activeTab === -1) return   // guard: rapid B then A
            homeScreen._contentOpacity = 0.0
            homeScreen._launcherVisible = false
            homeScreen._contentOpacity = 1.0   // fade in content
            Qt.callLater(function() {
                if (contentLoader.item) contentLoader.item.forceActiveFocus()
            })
        }
    }

    Timer {
        id: tabExitTimer
        interval: Theme.animDurationFast   // 150ms
        onTriggered: {
            contentLoader.source = ""
            homeScreen._activeTab = -1
            homeScreen._launcherOpacity = 1.0   // reset before making visible
            homeScreen._launcherVisible = true
            Qt.callLater(function() {
                var btn = buttonRepeater.itemAt(homeScreen._lastFocusedButton)
                if (btn) btn.forceActiveFocus()
            })
        }
    }

    // On startup, build tab arrays and give focus to the first button.
    Component.onCompleted: {
        _initTabs()
        Qt.callLater(function() {
            var btn = buttonRepeater.itemAt(0)
            if (btn) btn.forceActiveFocus()
        })
    }


}
