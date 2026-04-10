import QtQuick
import ".."
import "../components"

// Settings screen — tabbed layout with two focus zones:
//   1. Tab strip (horizontal) — Left/Right to switch tabs
//   2. Content list — the settings ListView
//
// Navigation:
//   Down from tabs → content list
//   B from content list → tab strip
//   B from tab strip → back()
FocusScope {
    id: settingsScreen

    // Emit when B (Escape) is pressed so HomeScreen can return focus to the tab bar.
    signal back()

    // Emit to request the controller mapping dialog be shown.
    signal showControllerMapping()

    // Only process input when this screen is active.
    enabled: focus

    // Incremented when plex.librariesModelChanged fires so the select
    // options expression re-evaluates reactively.
    property int _librariesVersion: 0

    // ── Focus zone tracking ──────────────────────────────────────────────────
    // "tabs" | "content"
    property string _focusZone: "tabs"

    // ── Tab / sub-category indices ───────────────────────────────────────────
    property int _activeTabIndex: 0

    // ── Tabs data model ──────────────────────────────────────────────────────
    readonly property var _tabs: [
        {
            name: "Games",
            subcategories: [
                {
                    name: "Paths",
                    settings: [
                        { type: "text", label: "ROMs Directory", settingKey: "romDirectory" },
                        { type: "text", label: "Cores Directory", settingKey: "coresDirectory" },
                        { type: "text", label: "Music Directory", settingKey: "localMusicDirectory" },
                    ]
                },
                {
                    name: "Retroarch",
                    settings: [
                        { type: "text",    label: "RetroArch Command", settingKey: "retroarchCommand" },
                        { type: "button",  label: "System Cores...",   action: "systemCores" },
                        { type: "button",  label: "RetroArch Hotkeys", action: "retroarchHotkeys" },
                        { type: "button",  label: "Rescan Library",    action: "rescan" },
                        { type: "button",  label: "Clear Retro Games History", action: "clearRetroRecent" },
                        { type: "toggle",  label: "Video Snap Autoplay", settingKey: "videoSnapAutoplay" },
                        { type: "slider",  label: "Video Snap Delay",    settingKey: "videoSnapDelayMs",
                          min: 0, max: 5000, step: 100, suffix: "ms" },
                    ]
                },
                {
                    name: "Moonlight",
                    settings: [
                        { type: "text",    label: "Moonlight Command", settingKey: "moonlightCommand" },
                        { type: "select",  label: "Host",              settingKey: "moonlightHost" },
                        { type: "button",  label: "Open Moonlight",    action: "openMoonlight" },
                    ]
                }
            ]
        },
        {
            name: "Plex",
            subcategories: null,
            settings: [
                { type: "button",  label: "Sign in with Plex", action: "plexSignIn" },
                { type: "button",  label: "Test Connection",   action: "testPlex" },
                { type: "select",  label: "Server",            settingKey: "plexServer" },
                { type: "select",  label: "User",              settingKey: "plexUser" },
                { type: "select",  label: "Music Library",    settingKey: "musicLibrary" },
                { type: "cycle",   label: "Video Player",      settingKey: "plexPlayer" },
                { type: "toggle",  label: "Auto-Skip Intro",   settingKey: "autoSkipIntro" },
                { type: "select",  label: "Video Quality",     settingKey: "transcodeMode" },
            ]
        },
        {
            name: "Controller",
            subcategories: null,
            settings: [
                { type: "select",  label: "Button Layout",    settingKey: "buttonLayout" },
                { type: "button",  label: "Map Controller",   action: "mapController" },
                { type: "button",  label: "Reset to Default", action: "resetController" },
            ]
        },
        {
            name: "User Interface",
            subcategories: [
                {
                    name: "Appearance",
                    settings: [
                        { type: "toggle",  label: "Network Indicator", settingKey: "showNetworkIndicator" },
                    ]
                },
                {
                    name: "Visible Tabs",
                    settings: [
                        { type: "toggle",  label: "Retro Games",  settingKey: "showRetroGamesTab" },
                        { type: "toggle",  label: "PC Games",     settingKey: "showPcGamesTab" },
                        { type: "toggle",  label: "Moonlight",    settingKey: "showMoonlightTab" },
                        { type: "toggle",  label: "Plex Media",   settingKey: "showWatchTab" },
                        { type: "toggle",  label: "Plex Music",   settingKey: "showListenTab" },
                        { type: "toggle",  label: "Local Music",  settingKey: "showLocalMusicTab" },
                        { type: "toggle",  label: "Videos",       settingKey: "showLocalVideosTab" },
                    ]
                }
            ]
        },
        {
            name: "Videos",
            subcategories: [
                {
                    name: "Default Categories",
                    settings: [
                        { type: "text", label: "Movies Path",   settingKey: "localVideoMoviesPath" },
                        { type: "text", label: "TV Shows Path", settingKey: "localVideoTvShowsPath" },
                    ]
                },
                {
                    name: "TMDb",
                    settings: [
                        { type: "text",   label: "API Key",         settingKey: "tmdbApiKey", masked: true },
                        { type: "button", label: "Scrape Movies",   action: "scrapeMovies" },
                        { type: "button", label: "Scrape TV Shows", action: "scrapeTvShows" },
                    ]
                },
                {
                    name: "Custom Categories",
                    settings: [
                        { type: "button", label: "Manage Custom Categories...", action: "videoCategories" },
                    ]
                }
            ]
        },
        {
            name: "Advanced",
            subcategories: null,
            settings: [
                { type: "text",  label: "Browser Command",  settingKey: "browserCommand" },
            ]
        }
    ]

    // ── Derived state ────────────────────────────────────────────────────────
    function _currentSettings() {
        var tab = _tabs[_activeTabIndex]
        if (tab.subcategories) {
            // Flatten sub-categories into a single list with header dividers
            var items = []
            for (var i = 0; i < tab.subcategories.length; i++) {
                var sub = tab.subcategories[i]
                items.push({ type: "header", label: sub.name })
                for (var j = 0; j < sub.settings.length; j++)
                    items.push(sub.settings[j])
            }
            return items
        }
        return tab.settings
    }

    // ── System Cores sub-screen ──────────────────────────────────────────────
    function showSystemCores() {
        systemCoresScreen.systems = settings ? settings.getSystemsList() : []
        systemCoresScreen.visible = true
        systemCoresScreen.forceActiveFocus()
    }

    // ── RetroArch Hotkeys sub-screen ─────────────────────────────────────────
    function showRetroarchHotkeys() {
        retroarchHotkeysScreen.config = settings ? settings.getRetroarchHotkeyConfig() : {}
        retroarchHotkeysScreen.visible = true
        retroarchHotkeysScreen.forceActiveFocus()
    }

    // ── Toast notification ───────────────────────────────────────────────────
    property string _toastText: ""

    Timer {
        id: toastTimer
        interval: 2500
        repeat: false
        onTriggered: settingsScreen._toastText = ""
    }

    function _showToast(msg) {
        settingsScreen._toastText = msg
        toastTimer.restart()
    }

    // ── Helper: get current value for a setting key ──────────────────────────
    function _getValue(key) {
        if (!settings) return ""
        if (key === "romDirectory")       return settings.romDirectory
        if (key === "retroarchCommand")   return settings.retroarchCommand
        if (key === "coresDirectory")     return settings.coresDirectory
        if (key === "plexServer") {
            return settings.plexServerName || "Not selected"
        }
        if (key === "plexUser") {
            return settings.plexUserTitle || "Not selected"
        }
        if (key === "musicLibrary") {
            if (!plex) return "Not selected"
            var musicLibs = plex.getMusicLibraries()
            for (var m = 0; m < musicLibs.length; m++) {
                if (musicLibs[m].id === settings.musicLibraryKey) return musicLibs[m].label
            }
            return "Not selected"
        }
        if (key === "browserCommand")     return settings.browserCommand
        if (key === "moonlightCommand")   return settings.moonlightCommand
        if (key === "moonlightHost") {
            if (!moonlight) return "Not selected"
            var hosts = settings.getHostsList()
            for (var k = 0; k < hosts.length; k++) {
                if (hosts[k].id === settings.moonlightHostUuid) return hosts[k].label
            }
            return "Not selected"
        }
        if (key === "videoSnapAutoplay")      return settings.videoSnapAutoplay
        if (key === "videoSnapDelayMs")       return settings.videoSnapDelayMs
        if (key === "showNetworkIndicator")   return settings.showNetworkIndicator
        if (key === "buttonLayout") {
            return settings.buttonLayout === "alternate" ? "Alternate (A=South)" : "Standard (A=East)"
        }
        if (key === "showRetroGamesTab")  return settings.showRetroGamesTab
        if (key === "showPcGamesTab")     return settings.showPcGamesTab
        if (key === "showMoonlightTab")   return settings.showMoonlightTab
        if (key === "showWatchTab")       return settings.showWatchTab
        if (key === "showListenTab")      return settings.showListenTab
        if (key === "showLocalMusicTab")  return settings.showLocalMusicTab
        if (key === "showLocalVideosTab") return settings.showLocalVideosTab
        if (key === "localVideoMoviesPath") {
            var movieCats = settings ? settings.localVideoCategories : []
            return movieCats.length > 0 && movieCats[0].paths && movieCats[0].paths.length > 0 ? movieCats[0].paths[0] : ""
        }
        if (key === "localVideoTvShowsPath") {
            var tvCats = settings ? settings.localVideoCategories : []
            return tvCats.length > 1 && tvCats[1].paths && tvCats[1].paths.length > 0 ? tvCats[1].paths[0] : ""
        }
        if (key === "tmdbApiKey") return settings ? settings.tmdbApiKey : ""
        if (key === "localMusicDirectory") return settings.localMusicDirectory
        if (key === "autoSkipIntro")      return settings.autoSkipIntro
        if (key === "transcodeMode") {
            var modeMap = { "direct": "Direct Play", "auto": "Auto", "480p": "480p", "720p": "720p", "1080p": "1080p" }
            return modeMap[settings.transcodeMode] || "Auto"
        }

        return ""
    }

    // ── Helper: call the appropriate setter ──────────────────────────────────
    function _setValue(key, value, label) {
        if (!settings) return
        if (key === "romDirectory")       settings.setRomDirectory(value)
        else if (key === "retroarchCommand")   settings.setRetroarchCommand(value)
        else if (key === "coresDirectory")     settings.setCoresDirectory(value)
        else if (key === "plexServer") {
            if (plex) plex.selectServer(value)
            settings.setPlexServerId(value, label || "")
        }
        else if (key === "plexUser") {
            if (plex) {
                plex.selectUser(parseInt(value))
                plex.refresh()
            }
            settings.setPlexUserId(parseInt(value), label || "")
        }
        else if (key === "browserCommand")     settings.setBrowserCommand(value)
        else if (key === "moonlightCommand")   settings.setMoonlightCommand(value)
        else if (key === "moonlightHost")      settings.setMoonlightHostUuid(value)
        else if (key === "musicLibrary")       settings.setMusicLibraryKey(value)
        else if (key === "videoSnapAutoplay")      settings.setVideoSnapAutoplay(value)
        else if (key === "videoSnapDelayMs")       settings.setVideoSnapDelayMs(value)
        else if (key === "showNetworkIndicator")   settings.setShowNetworkIndicator(value)
        else if (key === "buttonLayout") {
            settings.setButtonLayout(value)
            // Refresh hotkey screen labels — face button labels depend on layout
            if (retroarchHotkeysScreen.visible && settings)
                retroarchHotkeysScreen.config = settings.getRetroarchHotkeyConfig()
        }
        else if (key === "showRetroGamesTab") {
            settings.setShowRetroGamesTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showPcGamesTab") {
            settings.setShowPcGamesTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showMoonlightTab") {
            settings.setShowMoonlightTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showWatchTab") {
            settings.setShowWatchTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showListenTab") {
            settings.setShowListenTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showLocalMusicTab") {
            settings.setShowLocalMusicTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "showLocalVideosTab") {
            settings.setShowLocalVideosTab(value)
            if (settingsScreen._showToast) settingsScreen._showToast("Restart to apply")
        }
        else if (key === "localVideoMoviesPath") {
            var moviesCats = settings.localVideoCategories
            var moviesName = moviesCats.length > 0 ? moviesCats[0].name : "Movies"
            settings.updateLocalVideoCategory(0, moviesName, [value], "flat")
        }
        else if (key === "localVideoTvShowsPath") {
            var tvCatsSet = settings.localVideoCategories
            var tvName = tvCatsSet.length > 1 ? tvCatsSet[1].name : "TV Shows"
            settings.updateLocalVideoCategory(1, tvName, [value], "tv_shows")
        }
        else if (key === "tmdbApiKey") settings.setTmdbApiKey(value)
        else if (key === "localMusicDirectory") settings.setLocalMusicDirectory(value)
        else if (key === "autoSkipIntro") {
            settings.setAutoSkipIntro(value)
        }
        else if (key === "transcodeMode") {
            settings.setTranscodeMode(value)
        }

    }

    // ── Focus routing ────────────────────────────────────────────────────────
    function _routeFocus() {
        if (systemCoresScreen.visible) {
            systemCoresScreen.forceActiveFocus()
            return
        }
        if (retroarchHotkeysScreen.visible) {
            retroarchHotkeysScreen.forceActiveFocus()
            return
        }
        if (videoCategoriesScreen.visible) {
            videoCategoriesScreen.forceActiveFocus()
            return
        }
        if (_focusZone === "tabs") {
            tabStrip.forceActiveFocus()
        } else {
            // Focus the loaded component inside the current delegate
            var item = settingsList.currentItem
            if (item && item.children[0] && item.children[0].item) {
                item.children[0].item.forceActiveFocus()
            } else {
                settingsList.forceActiveFocus()
            }
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            _routeFocus()
        }
    }

    on_FocusZoneChanged: {
        if (activeFocus) {
            _routeFocus()
        }
    }

    on_ActiveTabIndexChanged: {
        _refreshModel()
    }

    function _refreshModel() {
        var items = _currentSettings()
        settingsList.model = items
        // Set index to first non-header row
        for (var i = 0; i < items.length; i++) {
            if (items[i].type !== "header") {
                settingsList.currentIndex = i
                return
            }
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
            text: "Settings"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Tab strip ────────────────────────────────────────────────────────────
    FocusScope {
        id: tabStrip

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(48)

        Row {
            id: tabRow
            anchors {
                left: parent.left
                leftMargin: root.vpx(48)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(32)

            Repeater {
                model: settingsScreen._tabs

                Item {
                    width: tabLabel.implicitWidth + root.vpx(8)
                    height: tabStrip.height

                    Text {
                        id: tabLabel
                        anchors.centerIn: parent
                        text: modelData.name
                        color: index === settingsScreen._activeTabIndex
                               ? Theme.colorPrimary : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        font.bold: index === settingsScreen._activeTabIndex

                        Behavior on color {
                            ColorAnimation { duration: Theme.animDurationFast }
                        }
                    }

                    // Active tab underline
                    Rectangle {
                        anchors {
                            bottom: parent.bottom
                            left: parent.left
                            right: parent.right
                        }
                        height: root.vpx(2)
                        color: Theme.colorPrimary
                        visible: index === settingsScreen._activeTabIndex
                    }
                }
            }
        }

        // Subtle bottom border for the tab strip
        Rectangle {
            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
            }
            height: root.vpx(1)
            color: Theme.colorTextDim
            opacity: 0.2
        }

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Left) {
                event.accepted = true
                if (settingsScreen._activeTabIndex > 0)
                    settingsScreen._activeTabIndex--
            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                if (settingsScreen._activeTabIndex < settingsScreen._tabs.length - 1)
                    settingsScreen._activeTabIndex++
            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                settingsScreen._focusZone = "content"
            } else if (keys.isCancel(event)) {
                event.accepted = true
                settingsScreen.back()
            }
        }
    }

    // ── Delegate components (top-level) ──────────────────────────────────────

    // ── Header component ─────────────────────────────────────────────────
    Component {
        id: headerComp
        Item {
            property var rowData
            implicitHeight: root.vpx(48)
            width: parent ? parent.width : 0

            // Separator line
            Rectangle {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: headerLabel.verticalCenter
                }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.3
            }

            // Header label on a background patch to "break" the line
            Rectangle {
                anchors {
                    left: parent.left
                    verticalCenter: headerLabel.verticalCenter
                }
                width: headerLabel.width + root.vpx(16)
                height: headerLabel.height + root.vpx(4)
                color: Theme.colorBackground
            }

            Text {
                id: headerLabel
                anchors {
                    left: parent.left
                    bottom: parent.bottom
                    bottomMargin: root.vpx(6)
                }
                text: rowData ? rowData.label : ""
                color: Theme.colorPrimary
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                font.bold: true
                font.letterSpacing: root.vpx(2)
            }
        }
    }

    // ── Text input component ─────────────────────────────────────────────
    Component {
        id: textInputComp
        SettingTextInput {
            property var rowData
            width: parent ? parent.width : 0
            label: rowData ? rowData.label : ""
            value: rowData ? settingsScreen._getValue(rowData.settingKey) : ""
            masked: rowData ? (rowData.masked || false) : false

            onEditingChanged: {
                settingsList._childEditing = editing
            }

            onValueEdited: (newValue) => {
                if (rowData) settingsScreen._setValue(rowData.settingKey, newValue)
            }
        }
    }

    // ── Toggle component ─────────────────────────────────────────────────
    Component {
        id: toggleComp
        SettingToggle {
            property var rowData
            width: parent ? parent.width : 0
            label: rowData ? rowData.label : ""
            checked: rowData ? settingsScreen._getValue(rowData.settingKey) : false

            onToggled: (newValue) => {
                if (rowData) settingsScreen._setValue(rowData.settingKey, newValue)
            }
        }
    }

    // ── Button component ─────────────────────────────────────────────────
    Component {
        id: buttonComp
        SettingButton {
            id: actionButton
            property var rowData
            width: parent ? parent.width : 0
            label: rowData ? rowData.label : ""

            onClicked: {
                if (!rowData) return
                var action = rowData.action
                if (action === "rescan") {
                    settings.rescanLibrary()
                    actionButton.statusText = "Rescanned!"
                } else if (action === "testPlex") {
                    actionButton.statusText = "Testing..."
                    // Defer the synchronous call to next event loop turn
                    // so "Testing..." is rendered before blocking.
                    Qt.callLater(function() {
                        var ok = settings.testPlexConnection()
                        actionButton.statusText = ok ? "Connected!" : "Failed"
                    })
                } else if (action === "plexSignIn") {
                    plexLoginOverlay.visible = true
                    plexLoginOverlay.forceActiveFocus()
                    settings.startPlexPinLogin()
                } else if (action === "openMoonlight") {
                    settings.openMoonlight()
                    actionButton.statusText = "Opening..."
                } else if (action === "systemCores") {
                    settingsScreen.showSystemCores()
                } else if (action === "retroarchHotkeys") {
                    settingsScreen.showRetroarchHotkeys()
                } else if (action === "mapController") {
                    settingsScreen.showControllerMapping()
                } else if (action === "resetController") {
                    if (settings) settings.resetControllerMapping()
                    settingsScreen._showToast("Controller mapping reset")
                } else if (action === "clearRetroRecent") {
                    if (library) library.clearRecentlyPlayed()
                    settingsScreen._showToast("Retro game history cleared")
                } else if (action === "videoCategories") {
                    videoCategoriesScreen.open()
                } else if (action === "scrapeMovies") {
                    if (localVideos) {
                        localVideos.scrapeMovies()
                        if (settingsScreen._showToast) settingsScreen._showToast("Scraping movies...")
                    }
                } else if (action === "scrapeTvShows") {
                    if (localVideos) {
                        localVideos.scrapeTvShows()
                        if (settingsScreen._showToast) settingsScreen._showToast("Scraping TV shows...")
                    }
                }
            }
        }
    }

    // ── Slider component ─────────────────────────────────────────────────
    Component {
        id: sliderComp
        SettingSlider {
            property var rowData
            width: parent ? parent.width : 0
            label: rowData ? rowData.label : ""
            value: rowData ? settingsScreen._getValue(rowData.settingKey) : 0
            minValue: rowData && rowData.min !== undefined ? rowData.min : 0
            maxValue: rowData && rowData.max !== undefined ? rowData.max : 5000
            step: rowData && rowData.step !== undefined ? rowData.step : 100
            suffix: rowData && rowData.suffix !== undefined ? rowData.suffix : ""

            onAdjustingChanged: {
                settingsList._childEditing = adjusting
            }

            onValueEdited: (newValue) => {
                if (rowData) settingsScreen._setValue(rowData.settingKey, newValue)
            }
        }
    }

    // ── Select component ─────────────────────────────────────────────────
    Component {
        id: selectComp
        SettingSelect {
            property var rowData
            width: parent ? parent.width : 0
            label: rowData ? rowData.label : ""
            currentValue: rowData ? settingsScreen._getValue(rowData.settingKey) : ""
            optionsProvider: function() {
                if (!rowData) return []
                if (rowData.settingKey === "buttonLayout") {
                    return [
                        { id: "standard",  label: "Standard (A=East)" },
                        { id: "alternate", label: "Alternate (A=South)" },
                    ]
                }
                if (rowData.settingKey === "transcodeMode") {
                    return [
                        { id: "direct", label: "Direct Play" },
                        { id: "auto",   label: "Auto" },
                        { id: "480p",   label: "480p" },
                        { id: "720p",   label: "720p" },
                        { id: "1080p",  label: "1080p" },
                    ]
                }
                if (rowData.settingKey === "moonlightHost") {
                    if (!settings) return []
                    return settings.getHostsList()
                }
                if (rowData.settingKey === "musicLibrary") {
                    if (!plex) return []
                    // Read _librariesVersion so this expression re-evaluates
                    // when onLibrariesModelChanged fires.
                    void settingsScreen._librariesVersion
                    var libs = plex.getMusicLibraries()
                    if (libs.length === 0) plex.refresh()
                    return libs
                }
                if (!plex) return []
                if (rowData.settingKey === "plexServer") {
                    return plex.getServerList().map(function(item) {
                        return { id: item.id, label: item.name }
                    })
                }
                if (rowData.settingKey === "plexUser") {
                    return plex.getHomeUsers().map(function(item) {
                        return { id: item.id, label: item.title }
                    })
                }
                return []
            }

            onSelected: (id, label) => {
                if (rowData) settingsScreen._setValue(rowData.settingKey, id, label)
            }
        }
    }

    // ── Cycle component (cycles through a fixed set of values) ───────────
    // Matches the SettingToggle layout: label on left, value pill on right.
    Component {
        id: cycleComp
        FocusScope {
            id: cycleRoot

            property var rowData
            implicitHeight: root.vpx(56)
            width: parent ? parent.width : 0

            // ── Background highlight ─────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: cycleRoot.activeFocus ? 0.8 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Row label ────────────────────────────────────────────────
            Text {
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: rowData ? rowData.label : ""
                color: cycleRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Value pill ───────────────────────────────────────────────
            Rectangle {
                id: valuePill
                anchors {
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                width: valueLabel.implicitWidth + root.vpx(24)
                height: root.vpx(32)
                radius: root.vpx(Theme.focusRingRadius)
                color: cycleRoot.activeFocus ? Theme.colorPrimary : "transparent"
                border.color: cycleRoot.activeFocus ? Theme.colorPrimary : Theme.colorTextDim
                border.width: root.vpx(1)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }
                Behavior on border.color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }

                Text {
                    id: valueLabel
                    anchors.centerIn: parent
                    text: (settings && (settings.plexPlayer || "mpv") === "mpv")
                        ? "MPV"
                        : "Browser"
                    color: cycleRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }
            }

            // ── Focus ring ───────────────────────────────────────────────
            FocusRing {}

            // ── Key handling ─────────────────────────────────────────────
            Keys.onPressed: (event) => {
                if (keys.isAccept(event)
                        || event.key === Qt.Key_Left
                        || event.key === Qt.Key_Right) {
                    event.accepted = true
                    if (settings) {
                        settings.setPlexPlayer(
                            (settings.plexPlayer || "mpv") === "mpv" ? "browser" : "mpv"
                        )
                    }
                }
            }
        }
    }

    // ── Content list ─────────────────────────────────────────────────────────
    ListView {
        id: settingsList

        anchors {
            top: tabStrip.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }

        model: settingsScreen._currentSettings()
        clip: true
        focus: true
        keyNavigationEnabled: false
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        // Track whether any child is in edit/adjust mode
        property bool _childEditing: false

        // ── Key handling for the list ────────────────────────────────────
        Keys.onPressed: (event) => {
            // If a child is in edit/adjust mode, let it handle keys
            if (settingsList._childEditing) {
                return
            }

            if (event.key === Qt.Key_Up) {
                event.accepted = true
                _moveFocus(-1)
            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                _moveFocus(1)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                settingsScreen._focusZone = "tabs"
            }
        }

        // Move focus by delta, skipping header rows.
        // When moving up past the first item, jump to the tab strip.
        function _moveFocus(delta) {
            var newIndex = currentIndex + delta
            while (newIndex >= 0 && newIndex < model.length) {
                if (model[newIndex].type !== "header") {
                    currentIndex = newIndex
                    // Force active focus on the loaded component
                    var item = currentItem
                    if (item && item.children[0] && item.children[0].item) {
                        item.children[0].item.forceActiveFocus()
                    }
                    return
                }
                newIndex += delta
            }
            // Ran off the top — move focus to tab strip
            if (delta < 0) {
                settingsScreen._focusZone = "tabs"
            }
        }

        // ── Delegate ─────────────────────────────────────────────────────
        delegate: Item {
            id: delegateWrapper
            width: settingsList.width
            height: loaderItem.item ? loaderItem.item.implicitHeight : 0

            readonly property var rowData: modelData
            readonly property bool isCurrentRow: settingsList.currentIndex === index

            Loader {
                id: loaderItem
                width: parent.width

                // Pick the right component based on type
                sourceComponent: {
                    if (rowData.type === "header")  return headerComp
                    if (rowData.type === "text")    return textInputComp
                    if (rowData.type === "toggle")  return toggleComp
                    if (rowData.type === "button")  return buttonComp
                    if (rowData.type === "slider")  return sliderComp
                    if (rowData.type === "select")  return selectComp
                    if (rowData.type === "cycle")   return cycleComp
                    return null
                }

                // Pass rowData and set up focus binding on the loaded item
                onLoaded: {
                    if (item) {
                        item.rowData = Qt.binding(function() {
                            return delegateWrapper.rowData
                        })
                        if (rowData.type !== "header") {
                            item.focus = Qt.binding(function() {
                                return delegateWrapper.isCurrentRow && settingsList.activeFocus
                            })
                        }
                    }
                }
            }
        }
    }

    // ── Toast overlay ────────────────────────────────────────────────────────
    Rectangle {
        id: toastOverlay
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(16)
        }
        width: toastLabel.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(20)
        color: Theme.colorSecondary
        border.color: Theme.colorPrimary
        border.width: root.vpx(1)
        visible: settingsScreen._toastText.length > 0
        opacity: visible ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: settingsScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }

    // ── System Cores sub-screen (declared last so it renders on top) ─────────
    SystemCoresScreen {
        id: systemCoresScreen
        anchors.fill: parent
        visible: false

        onBack: {
            systemCoresScreen.visible = false
            settingsScreen._focusZone = "content"
            settingsScreen._routeFocus()
        }
    }

    // ── RetroArch Hotkeys sub-screen ─────────────────────────────────────────
    RetroarchHotkeysScreen {
        id: retroarchHotkeysScreen
        anchors.fill: parent
        visible: false

        onBack: {
            retroarchHotkeysScreen.visible = false
            settingsScreen._focusZone = "content"
            settingsScreen._routeFocus()
        }
    }

    // ── Video Categories sub-screen ──────────────────────────────────────────
    FocusScope {
        id: videoCategoriesScreen
        anchors.fill: parent
        visible: false
        z: 10
        enabled: focus

        // List model: custom categories only (index 2+ from settings.localVideoCategories)
        property var _listModel: []

        // Form state
        property bool _formVisible: false
        property bool _formIsEdit: false
        property int  _formEditIndex: -1   // index into _listModel (not the settings array)
        property string _formName: ""
        property string _formPath: ""
        property string _formType: "flat"  // "flat" | "tv_shows"

        // Focused row in the list (when form is hidden)
        property int _focusedRow: 0

        // Form field focus: 0=name, 1=path, 2=type, 3=save, 4=cancel
        property int _formFocusedField: 0

        function open() {
            _refreshList()
            videoCategoriesScreen._focusedRow = 0
            videoCategoriesScreen._formVisible = false
            visible = true
            forceActiveFocus()
        }

        function close() {
            visible = false
            settingsScreen._routeFocus()
        }

        function _refreshList() {
            var all = settings ? settings.localVideoCategories : []
            var custom = []
            for (var i = 2; i < all.length; i++)
                custom.push(all[i])
            videoCategoriesScreen._listModel = custom
        }

        function _openAddForm() {
            videoCategoriesScreen._formIsEdit = false
            videoCategoriesScreen._formEditIndex = -1
            videoCategoriesScreen._formName = ""
            videoCategoriesScreen._formPath = ""
            videoCategoriesScreen._formType = "flat"
            videoCategoriesScreen._formFocusedField = 0
            videoCategoriesScreen._formVisible = true
        }

        function _openEditForm(listIndex) {
            var cat = videoCategoriesScreen._listModel[listIndex]
            if (!cat) return
            videoCategoriesScreen._formIsEdit = true
            videoCategoriesScreen._formEditIndex = listIndex
            videoCategoriesScreen._formName = cat.name || ""
            videoCategoriesScreen._formPath = (cat.paths && cat.paths.length > 0) ? cat.paths[0] : ""
            videoCategoriesScreen._formType = cat.type || "flat"
            videoCategoriesScreen._formFocusedField = 0
            videoCategoriesScreen._formVisible = true
        }

        function _saveForm() {
            var nm = videoCategoriesScreen._formName.trim()
            var ph = videoCategoriesScreen._formPath.trim()
            if (nm === "") return
            if (!settings) return
            if (videoCategoriesScreen._formIsEdit) {
                var settingsIdx = videoCategoriesScreen._formEditIndex + 2
                settings.updateLocalVideoCategory(settingsIdx, nm, [ph], videoCategoriesScreen._formType)
            } else {
                settings.addLocalVideoCategory(nm, [ph], videoCategoriesScreen._formType)
            }
            videoCategoriesScreen._formVisible = false
        }

        function _cancelForm() {
            videoCategoriesScreen._formVisible = false
        }

        function _deleteRow(listIndex) {
            if (!settings) return
            settings.removeLocalVideoCategory(listIndex + 2)
            // _refreshList() will be called by the Connections block
        }

        // ── Key handling ──────────────────────────────────────────────────────
        Keys.onPressed: (event) => {
            if (videoCategoriesScreen._formVisible) {
                _handleFormKey(event)
            } else {
                _handleListKey(event)
            }
        }

        function _handleListKey(event) {
            var rowCount = videoCategoriesScreen._listModel.length + 1  // categories + "Add" row
            if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (videoCategoriesScreen._focusedRow > 0)
                    videoCategoriesScreen._focusedRow--
            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (videoCategoriesScreen._focusedRow < rowCount - 1)
                    videoCategoriesScreen._focusedRow++
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var addRowIndex = videoCategoriesScreen._listModel.length
                if (videoCategoriesScreen._focusedRow === addRowIndex) {
                    _openAddForm()
                } else {
                    _openEditForm(videoCategoriesScreen._focusedRow)
                }
            } else if (event.key === Qt.Key_Y) {
                // Y button / Y key = Delete
                event.accepted = true
                var delIdx = videoCategoriesScreen._focusedRow
                if (delIdx < videoCategoriesScreen._listModel.length) {
                    _deleteRow(delIdx)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                videoCategoriesScreen.close()
            }
        }

        function _handleFormKey(event) {
            var fieldCount = 5  // name, path, type, save, cancel
            var ff = videoCategoriesScreen._formFocusedField
            if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (ff > 0) videoCategoriesScreen._formFocusedField = ff - 1
            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (ff < fieldCount - 1) videoCategoriesScreen._formFocusedField = ff + 1
            } else if (ff === 2 &&
                       (event.key === Qt.Key_Left || event.key === Qt.Key_Right)) {
                // Toggle type field
                event.accepted = true
                videoCategoriesScreen._formType =
                    videoCategoriesScreen._formType === "flat" ? "tv_shows" : "flat"
            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (ff === 2) {
                    // Toggle type
                    videoCategoriesScreen._formType =
                        videoCategoriesScreen._formType === "flat" ? "tv_shows" : "flat"
                } else if (ff === 3) {
                    _saveForm()
                } else if (ff === 4) {
                    _cancelForm()
                }
                // fields 0 and 1 (name/path) are text inputs; accept handled by them
            } else if (keys.isCancel(event)) {
                event.accepted = true
                _cancelForm()
            }
        }

        // ── Dark background overlay ───────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: Theme.colorBackground
        }

        // ── Header bar ────────────────────────────────────────────────────────
        Rectangle {
            id: vcHeaderBar
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: root.vpx(56)
            color: Theme.colorSecondary

            Text {
                anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                text: "◀  Custom Video Categories"
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            Row {
                anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                spacing: root.vpx(16)
                visible: !videoCategoriesScreen._formVisible

                Text {
                    text: "Y  Delete"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }

                Text {
                    text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }
            }
        }

        // ── List view (shown when form is hidden) ─────────────────────────────
        ListView {
            id: vcList
            anchors {
                top: vcHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                topMargin: root.vpx(8)
                leftMargin: root.vpx(48)
                rightMargin: root.vpx(48)
                bottomMargin: root.vpx(8)
            }
            visible: !videoCategoriesScreen._formVisible
            clip: true
            interactive: false
            highlightMoveDuration: Theme.animDurationFast

            model: {
                var rows = []
                var cats = videoCategoriesScreen._listModel
                for (var i = 0; i < cats.length; i++)
                    rows.push({ _type: "category", _data: cats[i], _index: i })
                rows.push({ _type: "add" })
                return rows
            }

            delegate: Item {
                id: vcDelegate
                width: vcList.width
                height: root.vpx(56)

                readonly property bool _isFocused: videoCategoriesScreen._focusedRow === index
                readonly property bool _isAdd: modelData._type === "add"
                readonly property var _cat: modelData._data || null
                readonly property int _catIndex: modelData._index !== undefined ? modelData._index : -1

                // ── Highlight ─────────────────────────────────────────────────
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: vcDelegate._isFocused ? 0.6 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)
                    Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                }

                // ── Focus ring ────────────────────────────────────────────────
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.color: Theme.colorFocusRing
                    border.width: root.vpx(Theme.focusRingWidth)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: vcDelegate._isFocused
                }

                // ── Category row layout ───────────────────────────────────────
                Row {
                    anchors {
                        left: parent.left; right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(16); rightMargin: root.vpx(16)
                    }
                    visible: !vcDelegate._isAdd

                    Text {
                        width: parent.width * 0.3
                        text: vcDelegate._cat ? (vcDelegate._cat.name || "") : ""
                        color: vcDelegate._isFocused ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        height: root.vpx(56)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                    }

                    Text {
                        width: parent.width * 0.5
                        text: {
                            if (!vcDelegate._cat) return ""
                            var paths = vcDelegate._cat.paths
                            return (paths && paths.length > 0) ? paths[0] : ""
                        }
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        height: root.vpx(56)
                    }

                    Text {
                        width: parent.width * 0.2
                        text: {
                            if (!vcDelegate._cat) return ""
                            return vcDelegate._cat.type === "tv_shows" ? "TV Shows" : "Flat"
                        }
                        color: Theme.colorPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        horizontalAlignment: Text.AlignRight
                        verticalAlignment: Text.AlignVCenter
                        height: root.vpx(56)
                    }
                }

                // ── Add row layout ────────────────────────────────────────────
                Text {
                    anchors {
                        left: parent.left; leftMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    visible: vcDelegate._isAdd
                    text: "+ Add Category"
                    color: vcDelegate._isFocused ? Theme.colorPrimary : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: true
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                }

                // ── Separator ─────────────────────────────────────────────────
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: root.vpx(1)
                    color: Theme.colorTextDim
                    opacity: 0.15
                }
            }

            // Keep view scrolled to focused row
            onModelChanged: {
                positionViewAtIndex(videoCategoriesScreen._focusedRow, ListView.Contain)
            }
        }

        // Keep list scrolled on focus change
        Connections {
            target: videoCategoriesScreen
            function on_FocusedRowChanged() {
                vcList.positionViewAtIndex(videoCategoriesScreen._focusedRow, ListView.Contain)
            }
        }

        // ── Add / Edit form ───────────────────────────────────────────────────
        Item {
            id: vcForm
            anchors {
                top: vcHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                topMargin: root.vpx(24)
                leftMargin: root.vpx(48)
                rightMargin: root.vpx(48)
                bottomMargin: root.vpx(8)
            }
            visible: videoCategoriesScreen._formVisible

            Column {
                anchors { top: parent.top; left: parent.left; right: parent.right }
                spacing: root.vpx(4)

                // Form title
                Text {
                    text: videoCategoriesScreen._formIsEdit ? "Edit Category" : "Add Category"
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    bottomPadding: root.vpx(12)
                }

                // ── Name field ────────────────────────────────────────────────
                Item {
                    id: vcNameRow
                    width: parent.width
                    height: root.vpx(56)
                    readonly property bool _isFocused: videoCategoriesScreen._formFocusedField === 0

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: vcNameRow._isFocused ? 0.6 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)
                        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Theme.colorFocusRing
                        border.width: root.vpx(Theme.focusRingWidth)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: vcNameRow._isFocused
                    }

                    Text {
                        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        width: parent.width * 0.25
                        text: "Name"
                        color: vcNameRow._isFocused ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                    }

                    TextInput {
                        id: vcNameInput
                        anchors {
                            left: parent.left; leftMargin: parent.width * 0.28
                            right: parent.right; rightMargin: root.vpx(16)
                            verticalCenter: parent.verticalCenter
                        }
                        text: videoCategoriesScreen._formName
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        focus: vcNameRow._isFocused

                        onTextChanged: {
                            if (vcNameRow._isFocused)
                                videoCategoriesScreen._formName = text
                        }

                        // Sync when form opens
                        Connections {
                            target: videoCategoriesScreen
                            function on_FormNameChanged() { vcNameInput.text = videoCategoriesScreen._formName }
                            function on_FormVisibleChanged() {
                                if (videoCategoriesScreen._formVisible)
                                    vcNameInput.text = videoCategoriesScreen._formName
                            }
                        }
                    }

                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: root.vpx(1); color: Theme.colorTextDim; opacity: 0.15
                    }
                }

                // ── Path field ────────────────────────────────────────────────
                Item {
                    id: vcPathRow
                    width: parent.width
                    height: root.vpx(56)
                    readonly property bool _isFocused: videoCategoriesScreen._formFocusedField === 1

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: vcPathRow._isFocused ? 0.6 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)
                        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Theme.colorFocusRing
                        border.width: root.vpx(Theme.focusRingWidth)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: vcPathRow._isFocused
                    }

                    Text {
                        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        width: parent.width * 0.25
                        text: "Path"
                        color: vcPathRow._isFocused ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                    }

                    TextInput {
                        id: vcPathInput
                        anchors {
                            left: parent.left; leftMargin: parent.width * 0.28
                            right: parent.right; rightMargin: root.vpx(16)
                            verticalCenter: parent.verticalCenter
                        }
                        text: videoCategoriesScreen._formPath
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        focus: vcPathRow._isFocused

                        onTextChanged: {
                            if (vcPathRow._isFocused)
                                videoCategoriesScreen._formPath = text
                        }

                        Connections {
                            target: videoCategoriesScreen
                            function on_FormPathChanged() { vcPathInput.text = videoCategoriesScreen._formPath }
                            function on_FormVisibleChanged() {
                                if (videoCategoriesScreen._formVisible)
                                    vcPathInput.text = videoCategoriesScreen._formPath
                            }
                        }
                    }

                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: root.vpx(1); color: Theme.colorTextDim; opacity: 0.15
                    }
                }

                // ── Type toggle ───────────────────────────────────────────────
                Item {
                    id: vcTypeRow
                    width: parent.width
                    height: root.vpx(56)
                    readonly property bool _isFocused: videoCategoriesScreen._formFocusedField === 2

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: vcTypeRow._isFocused ? 0.6 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)
                        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Theme.colorFocusRing
                        border.width: root.vpx(Theme.focusRingWidth)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: vcTypeRow._isFocused
                    }

                    Text {
                        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        text: "Type"
                        color: vcTypeRow._isFocused ? Theme.colorText : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                    }

                    Rectangle {
                        anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        width: typeLabel.implicitWidth + root.vpx(24)
                        height: root.vpx(32)
                        radius: root.vpx(Theme.focusRingRadius)
                        color: vcTypeRow._isFocused ? Theme.colorPrimary : "transparent"
                        border.color: vcTypeRow._isFocused ? Theme.colorPrimary : Theme.colorTextDim
                        border.width: root.vpx(1)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                        Behavior on border.color { ColorAnimation { duration: Theme.animDurationFast } }

                        Text {
                            id: typeLabel
                            anchors.centerIn: parent
                            text: videoCategoriesScreen._formType === "tv_shows" ? "TV Shows" : "Flat"
                            color: vcTypeRow._isFocused ? Theme.colorText : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                        }
                    }

                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: root.vpx(1); color: Theme.colorTextDim; opacity: 0.15
                    }
                }

                // ── Save button ───────────────────────────────────────────────
                Item {
                    id: vcSaveRow
                    width: parent.width
                    height: root.vpx(56)
                    readonly property bool _isFocused: videoCategoriesScreen._formFocusedField === 3

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: vcSaveRow._isFocused ? 0.8 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)
                        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Theme.colorFocusRing
                        border.width: root.vpx(Theme.focusRingWidth)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: vcSaveRow._isFocused
                    }

                    Rectangle {
                        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        width: vcSaveLabel.implicitWidth + root.vpx(32)
                        height: root.vpx(36)
                        radius: root.vpx(Theme.focusRingRadius)
                        color: vcSaveRow._isFocused ? Theme.colorPrimary : "transparent"
                        border.color: vcSaveRow._isFocused ? Theme.colorPrimary : Theme.colorTextDim
                        border.width: root.vpx(1)
                        Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                        Behavior on border.color { ColorAnimation { duration: Theme.animDurationFast } }

                        Text {
                            id: vcSaveLabel
                            anchors.centerIn: parent
                            text: "Save"
                            color: vcSaveRow._isFocused ? Theme.colorText : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                        }
                    }

                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: root.vpx(1); color: Theme.colorTextDim; opacity: 0.15
                    }
                }

                // ── Cancel button ─────────────────────────────────────────────
                Item {
                    id: vcCancelRow
                    width: parent.width
                    height: root.vpx(56)
                    readonly property bool _isFocused: videoCategoriesScreen._formFocusedField === 4

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: vcCancelRow._isFocused ? 0.6 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)
                        Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Theme.colorFocusRing
                        border.width: root.vpx(Theme.focusRingWidth)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: vcCancelRow._isFocused
                    }

                    Rectangle {
                        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
                        width: vcCancelLabel.implicitWidth + root.vpx(32)
                        height: root.vpx(36)
                        radius: root.vpx(Theme.focusRingRadius)
                        color: "transparent"
                        border.color: vcCancelRow._isFocused ? Theme.colorTextDim : Theme.colorTextDim
                        border.width: root.vpx(1)

                        Text {
                            id: vcCancelLabel
                            anchors.centerIn: parent
                            text: "Cancel"
                            color: vcCancelRow._isFocused ? Theme.colorText : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                        }
                    }
                }
            }
        }
    }

    // ── React to localVideoCategoriesChanged while sub-screen is open ────────
    Connections {
        target: settings
        function onLocalVideoCategoriesChanged() {
            if (videoCategoriesScreen.visible) videoCategoriesScreen._refreshList()
        }
    }

    // ── Plex PIN login: signal connections ───────────────────────────────────
    Connections {
        target: settings
        function onPlexLoginStatus(status) {
            if (status.startsWith("waiting:")) {
                plexLoginOverlay._pinCode = status.substring(8)
                plexLoginOverlay._status = "waiting"
            } else if (status === "success") {
                plexLoginOverlay._status = "success"
                plexLoginDismissTimer.start()
            } else if (status === "timeout") {
                plexLoginOverlay._status = "timeout"
                plexLoginDismissTimer.start()
            } else if (status === "error") {
                plexLoginOverlay._status = "error"
                plexLoginDismissTimer.start()
            } else if (status === "cancelled") {
                plexLoginOverlay.visible = false
                settingsScreen._routeFocus()
            }
        }
    }

    // ── localVideos scrape signals ───────────────────────────────────────────
    Connections {
        target: localVideos
        function onScrapeFinished(displayName, scraped, tombstoned, skipped) {
            var parts = [scraped + " scraped"]
            if (tombstoned > 0) parts.push(tombstoned + " not found on TMDb")
            if (skipped > 0) parts.push(skipped + " already done")
            if (settingsScreen._showToast) settingsScreen._showToast(displayName + ": " + parts.join(", "))
        }
        function onScrapeError(message) {
            if (settingsScreen._showToast) settingsScreen._showToast(message)
        }
        function onScrapeProgressChanged(done, total) {
            var pct = total > 0 ? Math.round(done / total * 100) : 0
            for (var i = 0; i < settingsList.count; i++) {
                var item = settingsList.itemAtIndex(i)
                if (!item) continue
                var comp = item.children[0] && item.children[0].item
                if (comp && (comp.rowData) &&
                    (comp.rowData.action === "scrapeMovies" || comp.rowData.action === "scrapeTvShows")) {
                    comp.statusText = done + " / " + total + " (" + pct + "%)"
                }
            }
        }
    }

    // ── Plex libraries model: force select re-evaluation on change ──────────
    Connections {
        target: plex
        function onLibrariesModelChanged() {
            settingsScreen._librariesVersion++
        }
    }

    // ── Plex PIN login: auto-dismiss after success / timeout / error ─────────
    Timer {
        id: plexLoginDismissTimer
        interval: 2000
        onTriggered: {
            plexLoginOverlay.visible = false
            settingsScreen._routeFocus()
        }
    }

    // ── Plex PIN login overlay (declared last so it renders on top) ──────────
    PlexLoginOverlay {
        id: plexLoginOverlay
        anchors.fill: parent
    }

    Component.onCompleted: {
        _refreshModel()
        // Set initial index to first non-header row
        for (var i = 0; i < settingsList.model.length; i++) {
            if (settingsList.model[i].type !== "header") {
                settingsList.currentIndex = i
                break
            }
        }
    }
}
