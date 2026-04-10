import QtQuick
import ".."
import "../components"

// Moonlight section screen.
//
// Three views:
//   "sources" — vertical list of Moonlight sources (Recently Played, Favorites, Apps)
//   "games"   — scrollable grid/list of apps for the selected source
//   "detail"  — full metadata panel for the selected app
//
// Focus flow:
//   Enter MoonlightScreen → sourceList gets focus (after moonlight.refresh())
//   Up/Down           — navigate sources (ListView handles natively)
//   A (Return)        — select source → switch to "games" view
//                       select app    → switch to "detail" view
//   B (Escape)        — from "sources": emit back() to return to tab bar
//                       from "games":   return to "sources" view
//                       from "detail":  return to "games" view
FocusScope {
    id: moonlightScreen

    // Emit when B (Escape) is pressed from the source list so HomeScreen can
    // return focus to the tab bar.
    signal back()

    // Navigation target passed by HomeScreen when navigating from recently played.
    // Unused until Task 004.
    property var navTarget: null

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "sources", "games", or "detail"
    property string currentView: "sources"

    // Display name of the currently selected source (set when a source is chosen).
    property string selectedSourceName: ""

    // Source key of the currently selected source.
    property string selectedSourceKey: ""

    // Index of the currently selected app in the active model.
    property int selectedGameIndex: -1

    // Track whether the current source is the "Recently Played" source.
    property bool isRecentSource: false

    // Track whether the current source is the "Favorites" source.
    property bool isFavoritesSource: false

    // JS array of recently played entries (populated when "recent" source is selected).
    property var _recentEntries: []

    // JS array of favorites entries (populated when "favorites" source is selected).
    property var _favoritesEntries: []

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Track whether we have already called moonlight.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // JS array of source entries built in Component.onCompleted.
    property var _sourceEntries: []

    // Guard: navTarget navigation fires only once (on first active focus).
    property bool _navTargetApplied: false

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: {
        if (currentView === "sources") {
            isFavoritesSource = false
            isRecentSource = false
        }
        _routeFocus()
    }
    on_ViewModeChanged: {
        if (settings) settings.setMoonlightViewMode(_viewMode)
        if (currentView === "games") _routeFocus()
    }
    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_refreshed) {
                _refreshed = true
                if (moonlight && moonlight.loading === false && moonlight.appsModel.rowCount() === 0) {
                    moonlight.refresh()
                } else if (moonlight && !moonlight.loading) {
                    // already loaded — no-op
                }
            }
            _routeFocus()
            if (navTarget && !_navTargetApplied) {
                _navTargetApplied = true
                if (navTarget.app_name) {
                    var targetName = navTarget.app_name
                    var count = moonlight && moonlight.appsModel ? moonlight.appsModel.rowCount() : 0
                    for (var i = 0; i < count; i++) {
                        var app = moonlight.getApp(i)
                        if (app && app.name === targetName) {
                            isRecentSource = false
                            isFavoritesSource = false
                            selectedGameIndex = i
                            currentView = "detail"
                            break
                        }
                    }
                }
            }
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
                if (_viewMode === "list") moonlightAppList.forceActiveFocus()
                else moonlightAppGrid.forceActiveFocus()
            }
        } else {
            if (isRecentSource) {
                recentlyPlayedDetail.forceActiveFocus()
            } else if (isFavoritesSource) {
                favoritesDetail.forceActiveFocus()
            } else {
                moonlightAppDetail.forceActiveFocus()
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
            text: "Moonlight"
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

        model: moonlightScreen._sourceEntries
        clip: true
        keyNavigationEnabled: true
        focus: true

        // Smooth focus movement between items
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        visible: moonlightScreen.currentView === "sources"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (currentItem) {
                    var sourceKey = currentItem.sourceKeyValue
                    var sourceName = currentItem.sourceNameValue
                    if (sourceKey === "recent") {
                        moonlightScreen.isRecentSource = true
                        moonlightScreen.isFavoritesSource = false
                        moonlightScreen._recentEntries = moonlight ? moonlight.getRecentlyPlayed() : []
                        recentlyPlayedGrid.entries = moonlightScreen._recentEntries
                        recentlyPlayedList.entries = moonlightScreen._recentEntries
                    } else if (sourceKey === "favorites") {
                        moonlightScreen.isFavoritesSource = true
                        moonlightScreen.isRecentSource = false
                        moonlightScreen._favoritesEntries = moonlight ? moonlight.getFavorites() : []
                        favoritesPlayedGrid.entries = moonlightScreen._favoritesEntries
                        favoritesPlayedList.entries = moonlightScreen._favoritesEntries
                    } else {
                        // "apps" source — show Moonlight app grid
                        moonlightScreen.isRecentSource = false
                        moonlightScreen.isFavoritesSource = false
                        moonlightAppGrid._currentSort = "az"
                    }
                    moonlightScreen.selectedSourceName = sourceName
                    moonlightScreen.selectedSourceKey = sourceKey
                    moonlightScreen.currentView = "games"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                moonlightScreen.back()
            }
        }

        delegate: FocusScope {
            id: delegateRoot

            // Expose source name and key so the ListView key handler can read them.
            readonly property string sourceNameValue: modelData.label
            readonly property string sourceKeyValue: modelData.key

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
                text: modelData.label
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // Item count (right-aligned)
            Text {
                anchors {
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: modelData.count > 0 ? modelData.count + " apps" : ""
                color: Theme.colorTextDim
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
                    sourceList.currentIndex = index
                    var sourceKey = modelData.key
                    var sourceName = modelData.label
                    if (sourceKey === "recent") {
                        moonlightScreen.isRecentSource = true
                        moonlightScreen.isFavoritesSource = false
                        moonlightScreen._recentEntries = moonlight ? moonlight.getRecentlyPlayed() : []
                        recentlyPlayedGrid.entries = moonlightScreen._recentEntries
                        recentlyPlayedList.entries = moonlightScreen._recentEntries
                    } else if (sourceKey === "favorites") {
                        moonlightScreen.isFavoritesSource = true
                        moonlightScreen.isRecentSource = false
                        moonlightScreen._favoritesEntries = moonlight ? moonlight.getFavorites() : []
                        favoritesPlayedGrid.entries = moonlightScreen._favoritesEntries
                        favoritesPlayedList.entries = moonlightScreen._favoritesEntries
                    } else {
                        moonlightScreen.isRecentSource = false
                        moonlightScreen.isFavoritesSource = false
                        moonlightAppGrid._currentSort = "az"
                    }
                    moonlightScreen.selectedSourceName = sourceName
                    moonlightScreen.selectedSourceKey = sourceKey
                    moonlightScreen.currentView = "games"
                }
            }
        }
    }

    // ── Recently Played grid view ────────────────────────────────────────────
    RecentlyPlayedGrid {
        id: recentlyPlayedGrid

        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource && moonlightScreen._viewMode === "grid"

        _viewMode: moonlightScreen._viewMode

        onBack: moonlightScreen.currentView = "sources"
        onGameSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Recently Played detail view ───────────────────────────────────────────
    RecentlyPlayedDetail {
        id: recentlyPlayedDetail

        anchors.fill: parent
        visible: moonlightScreen.currentView === "detail" && moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource

        gameData: moonlightScreen.currentView === "detail" && moonlightScreen.isRecentSource
                  && !moonlightScreen.isFavoritesSource
                  && moonlightScreen.selectedGameIndex >= 0
                  && moonlightScreen.selectedGameIndex < moonlightScreen._recentEntries.length
                  ? moonlightScreen._recentEntries[moonlightScreen.selectedGameIndex]
                  : ({})

        onBack: moonlightScreen.currentView = "games"
        onLaunch: (source, appId, hostAddress, appName) => {
            if (moonlight) moonlight.launchApp(hostAddress, appName)
        }
        onNavigatePrev: {
            if (moonlightScreen.selectedGameIndex > 0) {
                moonlightScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (moonlightScreen.selectedGameIndex < moonlightScreen._recentEntries.length - 1) {
                moonlightScreen.selectedGameIndex++
            }
        }
    }

    // ── Moonlight app grid view ──────────────────────────────────────────────
    MoonlightAppGrid {
        id: moonlightAppGrid

        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && !moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource && moonlightScreen._viewMode === "grid"

        sourceName: moonlightScreen.selectedSourceName
        hostOffline: false
        _viewMode: moonlightScreen._viewMode

        onBack: moonlightScreen.currentView = "sources"
        onAppSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Moonlight app detail view ─────────────────────────────────────────────
    MoonlightAppDetail {
        id: moonlightAppDetail

        anchors.fill: parent
        visible: moonlightScreen.currentView === "detail" && !moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource

        appData: moonlightScreen.currentView === "detail" && !moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource && moonlightScreen.selectedGameIndex >= 0
                 ? (moonlight ? moonlight.getApp(moonlightScreen.selectedGameIndex) : ({}))
                 : ({})

        onBack: {
            if (moonlightScreen._navTargetApplied) moonlightScreen.back()
            else moonlightScreen.currentView = "games"
        }
        onLaunch: (hostAddress, appName) => {
            if (moonlight) moonlight.launchApp(hostAddress, appName)
        }
        onNavigatePrev: {
            if (moonlightScreen.selectedGameIndex > 0) {
                moonlightScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (!moonlight) return
            var count = moonlight.appsModel.rowCount()
            if (moonlightScreen.selectedGameIndex < count - 1) {
                moonlightScreen.selectedGameIndex++
            }
        }
    }

    // ── Moonlight app list view ──────────────────────────────────────────────
    MoonlightAppList {
        id: moonlightAppList
        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && !moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource && moonlightScreen._viewMode === "list"
        sourceName: moonlightScreen.selectedSourceName
        hostOffline: false
        _viewMode: moonlightScreen._viewMode
        onBack: moonlightScreen.currentView = "sources"
        onAppSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Recently Played list view ────────────────────────────────────────────
    RecentlyPlayedList {
        id: recentlyPlayedList
        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && moonlightScreen.isRecentSource
                 && !moonlightScreen.isFavoritesSource && moonlightScreen._viewMode === "list"
        entries: moonlightScreen._recentEntries
        _viewMode: moonlightScreen._viewMode
        onBack: moonlightScreen.currentView = "sources"
        onGameSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Favorites grid view ──────────────────────────────────────────────────
    RecentlyPlayedGrid {
        id: favoritesPlayedGrid

        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && moonlightScreen.isFavoritesSource
                 && moonlightScreen._viewMode === "grid"

        entries: moonlightScreen._favoritesEntries
        sourceName: "Favorites"
        _viewMode: moonlightScreen._viewMode

        onBack: moonlightScreen.currentView = "sources"
        onGameSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Favorites list view ──────────────────────────────────────────────────
    RecentlyPlayedList {
        id: favoritesPlayedList

        anchors.fill: parent
        visible: moonlightScreen.currentView === "games" && moonlightScreen.isFavoritesSource
                 && moonlightScreen._viewMode === "list"

        entries: moonlightScreen._favoritesEntries
        sourceName: "Favorites"
        _viewMode: moonlightScreen._viewMode

        onBack: moonlightScreen.currentView = "sources"
        onGameSelected: (index) => {
            moonlightScreen.selectedGameIndex = index
            moonlightScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => { moonlightScreen._viewMode = mode }
    }

    // ── Favorites detail view ────────────────────────────────────────────────
    RecentlyPlayedDetail {
        id: favoritesDetail

        anchors.fill: parent
        visible: moonlightScreen.currentView === "detail" && moonlightScreen.isFavoritesSource

        gameData: moonlightScreen.currentView === "detail" && moonlightScreen.isFavoritesSource
                  && moonlightScreen.selectedGameIndex >= 0
                  && moonlightScreen.selectedGameIndex < moonlightScreen._favoritesEntries.length
                  ? moonlightScreen._favoritesEntries[moonlightScreen.selectedGameIndex]
                  : ({})

        onBack: moonlightScreen.currentView = "games"
        onLaunch: (source, appId, hostAddress, appName) => {
            if (moonlight) moonlight.launchApp(hostAddress, appName)
        }
        onNavigatePrev: {
            if (moonlightScreen.selectedGameIndex > 0) {
                moonlightScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            if (moonlightScreen.selectedGameIndex < moonlightScreen._favoritesEntries.length - 1) {
                moonlightScreen.selectedGameIndex++
            }
        }
    }

    // ── Toast notification ────────────────────────────────────────────────────
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

    // ── Wire moonlight.favoriteToggled → MoonlightScreen toast ───────────────
    Connections {
        target: moonlight
        function onFavoriteToggled(isFavorite) {
            toastBarText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
            toastBar.opacity = 1.0
            toastBarTimer.restart()
        }
    }

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.moonlightViewMode || "grid"
        }

        // Build source list
        var recentCount = moonlight ? moonlight.getRecentlyPlayed().length : 0
        var favCount = moonlight ? moonlight.favoriteCount : 0
        var appsCount = moonlight ? moonlight.appsModel.rowCount() : 0
        _sourceEntries = [
            { label: "Recently Played", key: "recent",    count: recentCount },
            { label: "Favorites",       key: "favorites", count: favCount },
            { label: "Apps",            key: "apps",      count: appsCount },
        ]

        // Trigger initial refresh if not yet loaded
        if (moonlight && !moonlight.loading && moonlight.appsModel.rowCount() === 0) {
            moonlight.refresh()
        }

    }
}
