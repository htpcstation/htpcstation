import QtQuick
import ".."
import "../components"

// Games section screen.
//
// Four view states:
//   "systems" — vertical list of discovered platforms with game counts
//   "games"   — scrollable grid of game tiles for the selected system (grid mode)
//   "games"   — split-panel list of game rows for the selected system (list mode)
//   "detail"  — full metadata panel for the selected game
//
// Focus flow:
//   Enter RetroGamesScreen → systemList gets focus
//   Up/Down           — navigate systems (ListView handles natively)
//   A (Return)        — select system → switch to "games" view
//                       select game   → switch to "detail" view
//   B (Escape)        — from "systems": emit back() to return to tab bar
//                       from "games":   return to "systems" view
//                       from "detail":  return to "games" view
FocusScope {
    id: retroGamesScreen

    // Emit when B (Escape) is pressed from the system list so HomeScreen can
    // return focus to the tab bar.
    signal back()

    // Navigation target passed by HomeScreen when navigating from recently played.
    // Unused until Task 004.
    property var navTarget: null

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "systems", "games", or "detail"
    property string currentView: "systems"

    // Display name of the currently selected system (set when a system is chosen).
    property string selectedSystemName: ""

    // Index of the currently selected game in library.gamesModel.
    property int selectedGameIndex: -1

    // Current view mode: "grid" or "list"
    property string _viewMode: "grid"

    // Guard: navTarget navigation fires only once (on first active focus).
    property bool _navTargetApplied: false

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: {
        if (activeFocus) {
            _routeFocus()
            if (navTarget && !_navTargetApplied) {
                _navTargetApplied = true
                if (navTarget.rom_path && navTarget.system_folder) {
                    library.selectSystem(navTarget.system_folder)
                    retroGamesScreen.selectedSystemName =
                        navTarget.system_display_name || navTarget.system_folder
                    var romPath = navTarget.rom_path
                    var count = library.gamesModel ? library.gamesModel.rowCount() : 0
                    for (var i = 0; i < count; i++) {
                        var g = library.getGame(i)
                        if (g && g.romPath === romPath) {
                            selectedGameIndex = i
                            currentView = "detail"
                            _routeFocus()
                            break
                        }
                    }
                }
            }
        }
    }
    on_ViewModeChanged: { if (currentView === "games") _routeFocus() }

    function _routeFocus() {
        if (currentView === "systems") {
            systemList.forceActiveFocus()
        } else if (currentView === "games") {
            if (_viewMode === "list") {
                gameListView.forceActiveFocus()
            } else {
                gameGridView.forceActiveFocus()
            }
        } else {
            gameDetailView.forceActiveFocus()
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
            text: "Retro Games"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── System list ──────────────────────────────────────────────────────────
    ListView {
        id: systemList

        anchors {
            top: headerBar.bottom
            topMargin: root.vpx(16)
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: library ? library.systemsModel : null
        clip: true
        keyNavigationEnabled: true
        focus: true

        // Smooth focus movement between items
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode:      ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd:   height * 0.65

        visible: retroGamesScreen.currentView === "systems"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (currentItem) {
                    library.selectSystem(currentItem.folderNameValue)
                    retroGamesScreen.selectedSystemName = currentItem.displayNameValue
                    retroGamesScreen.currentView = "games"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                retroGamesScreen.back()
            }
        }

        delegate: FocusScope {
            id: delegateRoot

            // Expose folderName and displayName so the ListView key handler can read them.
            readonly property string folderNameValue: model.folderName
            readonly property string displayNameValue: model.displayName

            width: systemList.width
            height: root.vpx(64)

            z: delegateRoot.ListView.isCurrentItem ? 1 : 0

            // Highlight background for the focused item
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateRoot.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: delegateRoot.ListView.isCurrentItem && systemList.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // System display name
            Text {
                id: nameLabel
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.displayName
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
                text: model.gameCount + " games"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
            }

            // Focus ring — visible when this delegate is the current item
            FocusRing {
                visible: delegateRoot.ListView.isCurrentItem && systemList.activeFocus
            }

            // Make the delegate the current item when clicked/tapped
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    systemList.currentIndex = index
                    systemList.forceActiveFocus()
                }
                onDoubleClicked: {
                    systemList.currentIndex = index
                    library.selectSystem(model.folderName)
                    retroGamesScreen.selectedSystemName = model.displayName
                    retroGamesScreen.currentView = "games"
                }
            }
        }
    }

    // ── Game grid view ───────────────────────────────────────────────────────
    GameGridView {
        id: gameGridView

        anchors.fill: parent
        visible: retroGamesScreen.currentView === "games" && retroGamesScreen._viewMode === "grid"

        systemName: retroGamesScreen.selectedSystemName
        _viewMode: retroGamesScreen._viewMode

        onBack: retroGamesScreen.currentView = "systems"
        onGameSelected: (index) => {
            retroGamesScreen.selectedGameIndex = index
            retroGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => {
            retroGamesScreen._viewMode = mode
        }
    }

    // ── Game list view ───────────────────────────────────────────────────────
    GameListView {
        id: gameListView

        anchors.fill: parent
        visible: retroGamesScreen.currentView === "games" && retroGamesScreen._viewMode === "list"

        systemName: retroGamesScreen.selectedSystemName
        _viewMode: retroGamesScreen._viewMode

        onBack: retroGamesScreen.currentView = "systems"
        onGameSelected: (index) => {
            retroGamesScreen.selectedGameIndex = index
            retroGamesScreen.currentView = "detail"
        }
        onViewModeChanged: (mode) => {
            retroGamesScreen._viewMode = mode
        }
    }

    // ── Game detail view ──────────────────────────────────────────────────────
    GameDetailView {
        id: gameDetailView

        anchors.fill: parent
        visible: retroGamesScreen.currentView === "detail"

        // Load game data only when the detail view is active to avoid unnecessary
        // library.getGame() calls while browsing systems or the game grid.
        gameData: retroGamesScreen.currentView === "detail" && retroGamesScreen.selectedGameIndex >= 0
                  ? library.getGame(retroGamesScreen.selectedGameIndex)
                  : ({})

        onBack: {
            if (retroGamesScreen._navTargetApplied) retroGamesScreen.back()
            else retroGamesScreen.currentView = "games"
        }
        onLaunch: library.launchGame(retroGamesScreen.selectedGameIndex)
        onToggleFavorite: library.toggleFavorite(retroGamesScreen.selectedGameIndex)
        onNavigatePrev: {
            if (retroGamesScreen.selectedGameIndex > 0) {
                retroGamesScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            var count = library.gamesModel.rowCount()
            if (retroGamesScreen.selectedGameIndex < count - 1) {
                retroGamesScreen.selectedGameIndex++
            }
        }
    }

    // ── Toast notification (shown after favorite toggle from any sub-view) ────
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

    // ── Wire library.favoriteToggled → toast notification ────────────────────
    Connections {
        target: library
        function onFavoriteToggled(isFavorite) {
            toastBarText.text = isFavorite ? "★ Added to Favorites" : "Removed from Favorites"
            toastBar.opacity = 1.0
            toastBarTimer.restart()
        }
    }

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.retroGamesViewMode || "grid"
        }
    }
}
