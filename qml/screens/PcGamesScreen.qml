import QtQuick
import ".."
import "../components"

// PC Games section screen.
//
// Three views:
//   "sources" — vertical list of Steam game sources with game counts
//   "games"   — scrollable grid of game tiles for the selected source
//   "detail"  — full metadata panel for the selected game
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

    // Track whether the current source is the "Recently Played" source.
    property bool isRecentSource: false

    // Track whether the current source is the "PC Favorites" source.
    property bool isFavoritesSource: false

    // JS array of recently played entries (populated when "recent" source is selected).
    property var _recentEntries: []

    // JS array of favorites entries (populated when "favorites" source is selected).
    property var _favoritesEntries: []

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Track whether we have already called steam.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: {
        if (currentView === "sources") {
            isFavoritesSource = false
            isRecentSource = false
        }
        _routeFocus()
    }
    on_ViewModeChanged: { if (currentView === "games") _routeFocus() }
    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_refreshed) {
                _refreshed = true
                if (steam) steam.refresh()
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
            } else if (isFavoritesSource) {
                if (_viewMode === "list") favoritesPlayedList.forceActiveFocus()
                else favoritesPlayedGrid.forceActiveFocus()
            } else {
                if (_viewMode === "list") steamGameList.forceActiveFocus()
                else steamGameGrid.forceActiveFocus()
            }
        } else {
            if (isRecentSource) {
                recentlyPlayedDetail.forceActiveFocus()
            } else if (isFavoritesSource) {
                favoritesDetail.forceActiveFocus()
            } else {
                steamGameDetail.forceActiveFocus()
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
            text: "PC Games"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Source list ──────────────────────────────────────────────────────────
    ListView {
        id: sourceList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: steam ? steam.sourcesModel : null
        clip: true
        keyNavigationEnabled: true
        focus: true

        // Smooth focus movement between items
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        visible: pcGamesScreen.currentView === "sources"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (!steam) return
                if (currentItem) {
                    var sourceKey = currentItem.sourceKeyValue
                    var sourceName = currentItem.sourceNameValue
                    if (sourceKey === "recent") {
                        pcGamesScreen.isRecentSource = true
                        pcGamesScreen.isFavoritesSource = false
                        pcGamesScreen._recentEntries = steam.getRecentlyPlayed()
                        recentlyPlayedGrid.entries = pcGamesScreen._recentEntries
                        recentlyPlayedList.entries = pcGamesScreen._recentEntries
                    } else if (sourceKey === "favorites") {
                        pcGamesScreen.isFavoritesSource = true
                        pcGamesScreen.isRecentSource = false
                        var entries = steam ? steam.getFavorites() : []
                        pcGamesScreen._favoritesEntries = entries
                        favoritesPlayedGrid.entries = entries
                        favoritesPlayedList.entries = entries
                    } else {
                        steam.selectSource(sourceKey)
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isFavoritesSource = false
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

            // Expose source name and key so the ListView key handler can read them.
            readonly property string sourceNameValue: model.name
            readonly property string sourceKeyValue: model.source

            width: sourceList.width
            height: root.vpx(64)

            z: delegateRoot.ListView.isCurrentItem ? 1 : 0

            // Highlight background for the focused item
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateRoot.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: delegateRoot.ListView.isCurrentItem && sourceList.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

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
                        pcGamesScreen.isFavoritesSource = false
                        pcGamesScreen._recentEntries = steam.getRecentlyPlayed()
                        recentlyPlayedGrid.entries = pcGamesScreen._recentEntries
                        recentlyPlayedList.entries = pcGamesScreen._recentEntries
                    } else if (sourceKey === "favorites") {
                        pcGamesScreen.isFavoritesSource = true
                        pcGamesScreen.isRecentSource = false
                        var entries2 = steam ? steam.getFavorites() : []
                        pcGamesScreen._favoritesEntries = entries2
                        favoritesPlayedGrid.entries = entries2
                        favoritesPlayedList.entries = entries2
                    } else {
                        steam.selectSource(sourceKey)
                        pcGamesScreen.isRecentSource = false
                        pcGamesScreen.isFavoritesSource = false
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
                 && !pcGamesScreen.isFavoritesSource && pcGamesScreen._viewMode === "grid"

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
                 && !pcGamesScreen.isFavoritesSource

        // Load game data from the JS array when the detail view is active.
        gameData: pcGamesScreen.currentView === "detail" && pcGamesScreen.isRecentSource
                  && !pcGamesScreen.isFavoritesSource
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
        visible: pcGamesScreen.currentView === "games"
                 && !pcGamesScreen.isRecentSource && !pcGamesScreen.isFavoritesSource
                 && pcGamesScreen._viewMode === "grid"

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
        visible: pcGamesScreen.currentView === "detail"
                 && !pcGamesScreen.isRecentSource && !pcGamesScreen.isFavoritesSource

        // Load game data only when the detail view is active to avoid unnecessary
        // steam.getGame() calls while browsing sources or the game grid.
        gameData: pcGamesScreen.currentView === "detail"
                  && !pcGamesScreen.isRecentSource && !pcGamesScreen.isFavoritesSource
                  && pcGamesScreen.selectedGameIndex >= 0
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

    // ── Steam game list view ─────────────────────────────────────────────────
    SteamGameList {
        id: steamGameList
        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games"
                 && !pcGamesScreen.isRecentSource && !pcGamesScreen.isFavoritesSource
                 && pcGamesScreen._viewMode === "list"
        sourceName: pcGamesScreen.selectedSourceName
        _viewMode: pcGamesScreen._viewMode
        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
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
                 && !pcGamesScreen.isFavoritesSource && pcGamesScreen._viewMode === "list"
        entries: pcGamesScreen._recentEntries
        _viewMode: pcGamesScreen._viewMode
        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── PC Favorites grid view ───────────────────────────────────────────────
    RecentlyPlayedGrid {
        id: favoritesPlayedGrid

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isFavoritesSource
                 && pcGamesScreen._viewMode === "grid"

        entries: pcGamesScreen._favoritesEntries
        sourceName: "PC Favorites"
        _viewMode: pcGamesScreen._viewMode

        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── PC Favorites list view ───────────────────────────────────────────────
    RecentlyPlayedList {
        id: favoritesPlayedList

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games" && pcGamesScreen.isFavoritesSource
                 && pcGamesScreen._viewMode === "list"

        entries: pcGamesScreen._favoritesEntries
        sourceName: "PC Favorites"
        _viewMode: pcGamesScreen._viewMode

        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { pcGamesScreen._viewMode = mode }
    }

    // ── PC Favorites detail view ─────────────────────────────────────────────
    RecentlyPlayedDetail {
        id: favoritesDetail

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "detail" && pcGamesScreen.isFavoritesSource

        // Load game data from the JS array when the detail view is active.
        gameData: pcGamesScreen.currentView === "detail" && pcGamesScreen.isFavoritesSource
                  && pcGamesScreen.selectedGameIndex >= 0
                  && pcGamesScreen.selectedGameIndex < pcGamesScreen._favoritesEntries.length
                  ? pcGamesScreen._favoritesEntries[pcGamesScreen.selectedGameIndex]
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
            if (pcGamesScreen.selectedGameIndex < pcGamesScreen._favoritesEntries.length - 1) {
                pcGamesScreen.selectedGameIndex++
            }
        }
    }

    // ── Toast notification (shown after favorite toggle from any sub-view) ────
    // Reusable toast — shown briefly after favorite toggle
    Rectangle {
        id: toastBar

        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(64)
        }
        width: toastBarText.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        color: Theme.colorOverlay
        radius: root.vpx(8)
        opacity: 0.0
        visible: opacity > 0
        // Render above all sub-views
        z: 100

        Text {
            id: toastBarText
            anchors.centerIn: parent
            color: Theme.colorOverlayText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }

        Behavior on opacity {
            NumberAnimation { duration: 200 }
        }

        Timer {
            id: toastBarTimer
            interval: 2000
            repeat: false
            onTriggered: toastBar.opacity = 0.0
        }
    }

    // ── Wire steam.favoriteToggled → PcGamesScreen toast ─────────────────────
    Connections {
        target: steam
        function onFavoriteToggled(isFavorite) {
            toastBarText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
            toastBar.opacity = 1.0
            toastBarTimer.restart()
        }
    }

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.pcGamesViewMode || "grid"
        }
    }
}
