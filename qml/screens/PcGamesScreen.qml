import QtQuick
import ".."
import "../components"

// PC Games section screen.
//
// Three views:
//   "sources" — vertical list of game sources (Steam, Moonlight, etc.) with game counts
//   "games"   — scrollable grid of game/app tiles for the selected source
//   "detail"  — full metadata panel for the selected game/app
//
// Focus flow:
//   Enter PcGamesScreen → sourceList gets focus (after steam.refresh())
//   Up/Down           — navigate sources (ListView handles natively)
//   A (Return)        — select source → switch to "games" view
//                       select game   → switch to "detail" view
//   B (Escape)        — from "sources": emit back() to return to tab bar
//                       from "games":   return to "sources" view
//                       from "detail":  return to "games" view
FocusScope {
    id: pcGamesScreen

    // Emit when B (Escape) is pressed from the source list so HomeScreen can
    // return focus to the tab bar.
    signal back()

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "sources", "games", or "detail"
    property string currentView: "sources"

    // Display name of the currently selected source (set when a source is chosen).
    property string selectedSourceName: ""

    // Source key of the currently selected source.
    property string selectedSourceKey: ""

    // Index of the currently selected game/app in the active model.
    property int selectedGameIndex: -1

    // Track whether the current source is a Moonlight source.
    property bool isMoonlightSource: false

    // Track whether the current source is the "Recently Played" source.
    property bool isRecentSource: false

    // Track whether the currently selected Moonlight source is offline.
    property bool isMoonlightOffline: false

    // JS array of recently played entries (populated when "recent" source is selected).
    property var _recentEntries: []

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Track whether we have already called steam.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    on_ViewModeChanged: { if (currentView === "games") _routeFocus() }
    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_refreshed) {
                _refreshed = true
                if (steam) steam.refresh()
                if (moonlight) moonlight.refresh()
            }
            _routeFocus()
        }
    }

    function _routeFocus() {
        if (currentView === "sources") {
            sourceList.forceActiveFocus()
        } else if (currentView === "games") {
            if (isRecentSource) {
                if (_viewMode === "list") recentlyPlayedList.forceActiveFocus()
                else recentlyPlayedGrid.forceActiveFocus()
            } else if (isMoonlightSource) {
                if (_viewMode === "list") moonlightAppList.forceActiveFocus()
                else moonlightAppGrid.forceActiveFocus()
            } else {
                if (_viewMode === "list") steamGameList.forceActiveFocus()
                else steamGameGrid.forceActiveFocus()
            }
        } else {
            if (isRecentSource) {
                recentlyPlayedDetail.forceActiveFocus()
            } else if (isMoonlightSource) {
                moonlightAppDetail.forceActiveFocus()
            } else {
                steamGameDetail.forceActiveFocus()
            }
        }
    }

    // ── Source list ──────────────────────────────────────────────────────────
    ListView {
        id: sourceList

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(32)
        }

        model: steam ? steam.sourcesModel : null
        clip: true
        keyNavigationEnabled: true
        focus: true

        // Smooth focus movement between items
        highlightMoveDuration: Theme.animDurationFast

        visible: pcGamesScreen.currentView === "sources"

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Up && currentIndex === 0) {
                event.accepted = true
                pcGamesScreen.back()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                if (!steam) return
                if (currentItem) {
                    var sourceKey = currentItem.sourceKeyValue
                    var sourceName = currentItem.sourceNameValue
                    if (sourceKey === "recent") {
                        pcGamesScreen.isRecentSource = true
                        pcGamesScreen.isMoonlightSource = false
                        pcGamesScreen.isMoonlightOffline = false
                        pcGamesScreen._recentEntries = steam.getRecentlyPlayed()
                        recentlyPlayedGrid.entries = pcGamesScreen._recentEntries
                        recentlyPlayedList.entries = pcGamesScreen._recentEntries
                    } else if (sourceKey === "moonlight") {
                        if (!moonlight) return
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isMoonlightSource = true
                        pcGamesScreen.isMoonlightOffline = currentItem.offlineValue || false
                        moonlightAppGrid._currentSort = "az"
                    } else {
                        steam.selectSource(sourceKey)
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isMoonlightSource = false
                        pcGamesScreen.isMoonlightOffline = false
                        steamGameGrid._currentSort = "az"
                    }
                    pcGamesScreen.selectedSourceName = sourceName
                    pcGamesScreen.selectedSourceKey = sourceKey
                    pcGamesScreen.currentView = "games"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                pcGamesScreen.back()
            }
        }

        delegate: FocusScope {
            id: delegateRoot

            // Expose source name, key, and offline state so the ListView key handler can read them.
            readonly property string sourceNameValue: model.name
            readonly property string sourceKeyValue: model.source
            readonly property bool offlineValue: model.offline || false

            width: sourceList.width
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

            // Source display name
            Text {
                id: nameLabel
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.name
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // Game count (right-aligned)
            Text {
                anchors {
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.loading ? "Loading..." : (model.offline ? "Unavailable" : model.gameCount + " games")
                color: model.offline && !model.loading ? Theme.colorPrimary : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
            }

            // Focus ring — visible when this delegate is the current item
            FocusRing {
                visible: delegateRoot.ListView.isCurrentItem && sourceList.activeFocus
            }

            // Make the delegate the current item when clicked/tapped
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    sourceList.currentIndex = index
                    sourceList.forceActiveFocus()
                }
                onDoubleClicked: {
                    if (!steam) return
                    sourceList.currentIndex = index
                    var sourceKey = model.source
                    var sourceName = model.name
                    if (sourceKey === "recent") {
                        pcGamesScreen.isRecentSource = true
                        pcGamesScreen.isMoonlightSource = false
                        pcGamesScreen.isMoonlightOffline = false
                        pcGamesScreen._recentEntries = steam.getRecentlyPlayed()
                        recentlyPlayedGrid.entries = pcGamesScreen._recentEntries
                        recentlyPlayedList.entries = pcGamesScreen._recentEntries
                    } else if (sourceKey === "moonlight") {
                        if (!moonlight) return
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isMoonlightSource = true
                        pcGamesScreen.isMoonlightOffline = model.offline || false
                        moonlightAppGrid._currentSort = "az"
                    } else {
                        steam.selectSource(sourceKey)
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isMoonlightSource = false
                        pcGamesScreen.isMoonlightOffline = false
                        steamGameGrid._currentSort = "az"
                    }
                    pcGamesScreen.selectedSourceName = sourceName
                    pcGamesScreen.selectedSourceKey = sourceKey
                    pcGamesScreen.currentView = "games"
                }
            }
        }
    }

    // ── Recently Played grid view ────────────────────────────────────────────
    RecentlyPlayedGrid {
        id: recentlyPlayedGrid

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isRecentSource
                 && pcGamesScreen._viewMode === "grid"

        _viewMode: pcGamesScreen._viewMode

        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── Recently Played detail view ───────────────────────────────────────────
    RecentlyPlayedDetail {
        id: recentlyPlayedDetail

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "detail" && pcGamesScreen.isRecentSource

        // Load game data from the JS array when the detail view is active.
        gameData: pcGamesScreen.currentView === "detail" && pcGamesScreen.isRecentSource
                  && pcGamesScreen.selectedGameIndex >= 0
                  && pcGamesScreen.selectedGameIndex < pcGamesScreen._recentEntries.length
                  ? pcGamesScreen._recentEntries[pcGamesScreen.selectedGameIndex]
                  : ({})

        onBack: pcGamesScreen.currentView = "games"
        onLaunch: (source, appId, hostAddress, appName) => {
            if (steam) steam.launchRecentGame(source, appId, hostAddress, appName)
        }
        onNavigatePrev: {
            if (pcGamesScreen.selectedGameIndex > 0) {
                pcGamesScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (pcGamesScreen.selectedGameIndex < pcGamesScreen._recentEntries.length - 1) {
                pcGamesScreen.selectedGameIndex++
            }
        }
    }

    // ── Steam game grid view ─────────────────────────────────────────────────
    SteamGameGrid {
        id: steamGameGrid

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && !pcGamesScreen.isMoonlightSource
                 && !pcGamesScreen.isRecentSource && pcGamesScreen._viewMode === "grid"

        sourceName: pcGamesScreen.selectedSourceName
        _viewMode: pcGamesScreen._viewMode

        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── Steam game detail view ────────────────────────────────────────────────
    SteamGameDetail {
        id: steamGameDetail

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "detail" && !pcGamesScreen.isMoonlightSource
                 && !pcGamesScreen.isRecentSource

        // Load game data only when the detail view is active to avoid unnecessary
        // steam.getGame() calls while browsing sources or the game grid.
        gameData: pcGamesScreen.currentView === "detail" && !pcGamesScreen.isMoonlightSource
                  && !pcGamesScreen.isRecentSource && pcGamesScreen.selectedGameIndex >= 0
                  ? (steam ? steam.getGame(pcGamesScreen.selectedGameIndex) : ({}))
                  : ({})

        onBack: pcGamesScreen.currentView = "games"
        onLaunch: (appId) => {
            if (steam) steam.launchGame(appId)
        }
        onNavigatePrev: {
            if (pcGamesScreen.selectedGameIndex > 0) {
                pcGamesScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (!steam) return
            var count = steam.gamesModel.rowCount()
            if (pcGamesScreen.selectedGameIndex < count - 1) {
                pcGamesScreen.selectedGameIndex++
            }
        }
    }

    // ── Moonlight app grid view ──────────────────────────────────────────────
    MoonlightAppGrid {
        id: moonlightAppGrid

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isMoonlightSource
                 && pcGamesScreen._viewMode === "grid"

        sourceName: pcGamesScreen.selectedSourceName
        hostOffline: pcGamesScreen.isMoonlightOffline
        _viewMode: pcGamesScreen._viewMode

        onBack: pcGamesScreen.currentView = "sources"
        onAppSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── Moonlight app detail view ─────────────────────────────────────────────
    MoonlightAppDetail {
        id: moonlightAppDetail

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "detail" && pcGamesScreen.isMoonlightSource

        // Load app data only when the detail view is active.
        appData: pcGamesScreen.currentView === "detail" && pcGamesScreen.isMoonlightSource && pcGamesScreen.selectedGameIndex >= 0
                 ? (moonlight ? moonlight.getApp(pcGamesScreen.selectedGameIndex) : ({}))
                 : ({})

        onBack: pcGamesScreen.currentView = "games"
        onLaunch: (hostAddress, appName) => {
            if (moonlight) moonlight.launchApp(hostAddress, appName)
        }
        onNavigatePrev: {
            if (pcGamesScreen.selectedGameIndex > 0) {
                pcGamesScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (!moonlight) return
            var count = moonlight.appsModel.rowCount()
            if (pcGamesScreen.selectedGameIndex < count - 1) {
                pcGamesScreen.selectedGameIndex++
            }
        }
    }

    // ── Steam game list view ─────────────────────────────────────────────────
    SteamGameList {
        id: steamGameList
        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && !pcGamesScreen.isMoonlightSource
                 && !pcGamesScreen.isRecentSource && pcGamesScreen._viewMode === "list"
        sourceName: pcGamesScreen.selectedSourceName
        _viewMode: pcGamesScreen._viewMode
        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── Moonlight app list view ──────────────────────────────────────────────
    MoonlightAppList {
        id: moonlightAppList
        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isMoonlightSource
                 && pcGamesScreen._viewMode === "list"
        sourceName: pcGamesScreen.selectedSourceName
        hostOffline: pcGamesScreen.isMoonlightOffline
        _viewMode: pcGamesScreen._viewMode
        onBack: pcGamesScreen.currentView = "sources"
        onAppSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── Recently Played list view ────────────────────────────────────────────
    RecentlyPlayedList {
        id: recentlyPlayedList
        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isRecentSource
                 && pcGamesScreen._viewMode === "list"
        entries: pcGamesScreen._recentEntries
        _viewMode: pcGamesScreen._viewMode
        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.pcGamesViewMode || "grid"
        }
    }
}
