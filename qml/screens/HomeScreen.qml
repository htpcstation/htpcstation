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
        { name: "Music",       source: "LocalMusicScreen.qml",  setting: "showLocalMusicTab",   slug: "localmusic"  },
        { name: "Videos",      source: "LocalVideosScreen.qml", setting: "showLocalVideosTab",  slug: "localvideos" },
        { name: "Settings",    source: "SettingsScreen.qml",    setting: null,                  slug: "settings"    },
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

    // ── Now-playing overlay state ─────────────────────────────────────────────
    property bool _nowPlayingVisible: false
    property Item _nowPlayingReturnItem: null

    function _showNowPlaying() {
        _nowPlayingReturnItem = contentLoader.item || null
        _nowPlayingVisible = true
        nowPlayingView.forceActiveFocus()
    }

    function _hideNowPlaying() {
        _nowPlayingVisible = false
        if (_nowPlayingReturnItem) {
            _nowPlayingReturnItem.forceActiveFocus()
        }
    }

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
        if (recentlyPlayed) {
            var src = albumData.source === "local" ? "localmusic" : "plexmusic"
            var art = albumData.posterLocal || ""
            var navKey = src === "localmusic" ? "folder_path" : "rating_key"
            var navVal = src === "localmusic" ? (albumData.folderPath || "") : (albumData.ratingKey || "")
            var navParams = {}
            navParams[navKey] = navVal
            recentlyPlayed.record(src, albumData.title || albumData.name || "", art, navParams)
        }
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
        } else if (plex && !track.ratingKey && track.title && track.grandparentTitle) {
            // Local music track — use title/artist for LRCLIB lookup with empty ratingKey
            plex.getLyrics("", track.title,
                           track.grandparentTitle, track.parentTitle || "", track.durationMs || 0)
        }
        var url = track.streamUrl ? track.streamUrl : (plex && track.mediaKey ? plex.getTrackStreamUrl(track.mediaKey) : "")
        musicPlayer.source = url
        musicPlayer.play()
    }

    function _playNext() {
        if (_repeatMode === "one") {
            // Replay the same track from the start
            var t = _playbackTracks[_playOrder[_playingIndex]]
            var url = t.streamUrl ? t.streamUrl : (plex && t.mediaKey ? plex.getTrackStreamUrl(t.mediaKey) : "")
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
        source: (settings && settings.themeAvailable) ? settings.themeDir + "homescreen/home-background.png" : ""
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
        anchors.verticalCenterOffset: parent.height / 4
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
                        if (recentlyPlayedWidget.items.length > 0) {
                            recentlyPlayedWidget.forceActiveFocus()
                        }
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
                    source: (settings && settings.themeAvailable && index < homeScreen.tabSlugs.length && homeScreen.tabSlugs[index])
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

    // ── Divider between tab bar and Recently Played Widget ───────────────────
    Rectangle {
        id: tabDivider
        anchors.top: buttonRow.bottom
        anchors.topMargin: root.vpx(48)
        anchors.left: buttonRow.left
        anchors.right: buttonRow.right
        height: root.vpx(1)
        color: Theme.colorAccent
        visible: homeScreen._launcherVisible
        opacity: homeScreen._launcherOpacity
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
    }

    // ── Recently Played Widget ────────────────────────────────────────────────
    RecentlyPlayedWidget {
        id: recentlyPlayedWidget
        anchors.top: tabDivider.bottom
        anchors.topMargin: root.vpx(48)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.vpx(32)
        anchors.left: parent.left
        anchors.leftMargin: root.vpx(48)
        anchors.right: parent.right
        anchors.rightMargin: root.vpx(48)
        visible: homeScreen._launcherVisible
        opacity: homeScreen._launcherOpacity
        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
        focus: false
        items: recentlyPlayed ? recentlyPlayed.getRecent() : []
    }

    Connections {
        target: recentlyPlayed
        function onChanged() { recentlyPlayedWidget.items = recentlyPlayed ? recentlyPlayed.getRecent() : [] }
    }

    Connections {
        target: recentlyPlayedWidget
        function onBack() {
            var btn = buttonRepeater.itemAt(homeScreen._lastFocusedButton)
            if (btn) btn.forceActiveFocus()
        }
        function onActivated(source, navParams) {
            var slugMap = {
                "retro":      "retrogames",
                "steam":      "pcgames",
                "moonlight":  "moonlight",
                "plexvideo":  "plexmedia",
                "plexmusic":  "plexmusic",
                "localmusic": "localmusic",
                "localvideo": "localvideos"
            }
            var targetSlug = slugMap[source] || ""
            var tabIndex = homeScreen.tabSlugs.indexOf(targetSlug)
            if (tabIndex < 0) return
            homeScreen._lastFocusedButton = tabIndex
            homeScreen._activeTab = tabIndex
            contentLoader.setSource(homeScreen.tabSources[tabIndex], { "navTarget": navParams })
            homeScreen._launcherOpacity = 0.0
            tabEnterTimer.restart()
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

    // ── Now Playing overlay ─────────────────────────────────────────────────
    FocusScope {
        id: nowPlayingView

        anchors.fill: parent
        visible: homeScreen._nowPlayingVisible

        // Opaque background so the tab content beneath doesn't bleed through.
        Rectangle {
            anchors.fill: parent
            color: Theme.colorBackground
        }

        onActiveFocusChanged: {
            if (activeFocus) btnPlayPause.forceActiveFocus()
        }

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                homeScreen._hideNowPlaying()
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

            // ── Left: album art + codec info ────────────────────────────────
            Column {
                id: nowPlayingArtArea

                anchors {
                    verticalCenter: parent.verticalCenter
                    left: parent.left
                }
                width: Math.min(root.vpx(250), parent.height * 0.55)
                spacing: root.vpx(14)

                // Art container (square)
                Item {
                    width: parent.width
                    height: width

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

                // Codec info label directly below album art
                Text {
                    id: nowPlayingCodecInfo

                    anchors.horizontalCenter: parent.horizontalCenter
                    text: homeScreen._nowPlayingTrack.codecInfo || ""
                    visible: !!text
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    opacity: Theme.opacityButton
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
                    verticalCenter: parent.verticalCenter
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
