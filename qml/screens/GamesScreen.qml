import QtQuick
import ".."
import "../components"

// Games section screen.
//
// Three views:
//   "systems" — vertical list of discovered platforms with game counts
//   "games"   — scrollable grid of game tiles for the selected system
//   "detail"  — full metadata panel for the selected game
//
// Focus flow:
//   Enter GamesScreen → systemList gets focus
//   Up/Down           — navigate systems (ListView handles natively)
//   A (Return)        — select system → switch to "games" view
//                       select game   → switch to "detail" view
//   B (Escape)        — from "systems": emit back() to return to tab bar
//                       from "games":   return to "systems" view
//                       from "detail":  return to "games" view
FocusScope {
    id: gamesScreen

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

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: if (activeFocus) _routeFocus()

    function _routeFocus() {
        if (currentView === "systems") {
            systemList.forceActiveFocus()
        } else if (currentView === "games") {
            gameGridView.forceActiveFocus()
        } else {
            gameDetailView.forceActiveFocus()
        }
    }

    // ── System list ──────────────────────────────────────────────────────────
    ListView {
        id: systemList

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(32)
        }

        model: library.systemsModel
        clip: true
        keyNavigationEnabled: true
        focus: true

        // Smooth focus movement between items
        highlightMoveDuration: Theme.animDurationFast

        visible: gamesScreen.currentView === "systems"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (currentItem) {
                    library.selectSystem(currentItem.folderNameValue)
                    gamesScreen.selectedSystemName = currentItem.displayNameValue
                    gameGridView._currentSort = "az"
                    gamesScreen.currentView = "games"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                gamesScreen.back()
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
                    gamesScreen.selectedSystemName = model.displayName
                    gameGridView._currentSort = "az"
                    gamesScreen.currentView = "games"
                }
            }
        }
    }

    // ── Game grid view ───────────────────────────────────────────────────────
    GameGridView {
        id: gameGridView

        anchors.fill: parent
        visible: gamesScreen.currentView === "games"

        systemName: gamesScreen.selectedSystemName

        onBack: gamesScreen.currentView = "systems"
        onGameSelected: (index) => {
            gamesScreen.selectedGameIndex = index
            gamesScreen.currentView = "detail"
        }
    }

    // ── Game detail view ──────────────────────────────────────────────────────
    GameDetailView {
        id: gameDetailView

        anchors.fill: parent
        visible: gamesScreen.currentView === "detail"

        // Load game data only when the detail view is active to avoid unnecessary
        // library.getGame() calls while browsing systems or the game grid.
        gameData: gamesScreen.currentView === "detail" && gamesScreen.selectedGameIndex >= 0
                  ? library.getGame(gamesScreen.selectedGameIndex)
                  : ({})

        onBack: gamesScreen.currentView = "games"
        onLaunch: library.launchGame(gamesScreen.selectedGameIndex)
        onToggleFavorite: library.toggleFavorite(gamesScreen.selectedGameIndex)
        onNavigatePrev: {
            if (gamesScreen.selectedGameIndex > 0) {
                gamesScreen.selectedGameIndex--
            }
        }
        onNavigateNext: {
            var count = library.gamesModel.rowCount()
            if (gamesScreen.selectedGameIndex < count - 1) {
                gamesScreen.selectedGameIndex++
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
}
