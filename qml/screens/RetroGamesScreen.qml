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

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: if (activeFocus) _routeFocus()
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

        visible: retroGamesScreen.currentView === "systems"

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Up && currentIndex === 0) {
                event.accepted = true
                retroGamesScreen.back()
            } else if (keys.isAccept(event)) {
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

        onBack: retroGamesScreen.currentView = "games"
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

    // ── Wire library.favoriteToggled → toast notification ────────────────────
    Connections {
        target: library
        function onFavoriteToggled(isFavorite) {
            gameDetailView.showFavoriteToast(isFavorite)
        }
    }

    Component.onCompleted: {
        if (settings) {
            _viewMode = settings.retroGamesViewMode || "grid"
        }
    }
}
