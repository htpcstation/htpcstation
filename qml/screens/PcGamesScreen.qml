import QtQuick
import ".."
import "../components"

// PC Games section screen.
//
// Three views:
//   "sources" — vertical list of game sources (Steam, etc.) with game counts
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

    // Index of the currently selected game in steam.gamesModel.
    property int selectedGameIndex: -1

    // Track whether we have already called steam.refresh() to avoid re-fetching
    // every time the user navigates back to this tab.
    property bool _refreshed: false

    // Give focus to the appropriate child whenever the view changes or this
    // screen gains focus.
    onCurrentViewChanged: _routeFocus()
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
            steamGameGrid.forceActiveFocus()
        } else {
            steamGameDetail.forceActiveFocus()
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
            if (keys.isAccept(event)) {
                event.accepted = true
                if (!steam) return
                if (currentItem) {
                    steam.selectSource(currentItem.sourceKeyValue)
                    pcGamesScreen.selectedSourceName = currentItem.sourceNameValue
                    pcGamesScreen.selectedSourceKey = currentItem.sourceKeyValue
                    steamGameGrid._currentSort = "az"
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
                text: model.gameCount + " games"
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
                    if (!steam) return
                    sourceList.currentIndex = index
                    steam.selectSource(model.source)
                    pcGamesScreen.selectedSourceName = model.name
                    pcGamesScreen.selectedSourceKey = model.source
                    steamGameGrid._currentSort = "az"
                    pcGamesScreen.currentView = "games"
                }
            }
        }
    }

    // ── Game grid view ───────────────────────────────────────────────────────
    SteamGameGrid {
        id: steamGameGrid

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "games"

        sourceName: pcGamesScreen.selectedSourceName

        onBack: pcGamesScreen.currentView = "sources"
        onGameSelected: (index) => {
            pcGamesScreen.selectedGameIndex = index
            pcGamesScreen.currentView = "detail"
        }
    }

    // ── Game detail view ──────────────────────────────────────────────────────
    SteamGameDetail {
        id: steamGameDetail

        anchors.fill: parent
        visible: pcGamesScreen.currentView === "detail"

        // Load game data only when the detail view is active to avoid unnecessary
        // steam.getGame() calls while browsing sources or the game grid.
        gameData: pcGamesScreen.currentView === "detail" && pcGamesScreen.selectedGameIndex >= 0
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
}
