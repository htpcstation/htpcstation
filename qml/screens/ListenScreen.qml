import QtQuick
import ".."
import "../components"

// Listen section screen — Plex music library browser.
//
// Three views:
//   "artists"  — grid of artists from the Plex music library
//   "detail"   — artist detail view (album tabs + track list)
//
// Focus flow:
//   Enter ListenScreen → artistGrid gets focus (after plex.refresh())
//   D-pad               — navigate artist grid
//   A (Return)          — select artist → switch to "detail" view
//   B (Escape)          — from "artists": emit back() to return to tab bar
//                         from "detail":  return to "artists" view
FocusScope {
    id: listenScreen

    // Emit when B (Escape) is pressed from the top-level view so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "artists" or "detail"
    property string currentView: "artists"

    // Prevent redundant refreshes when re-entering the tab.
    property bool _refreshed: false

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "artists") {
            artistPlaceholder.forceActiveFocus()
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_refreshed) {
                _refreshed = true
                if (plex) plex.refresh()
            }
            _routeFocus()
        }
    }

    onCurrentViewChanged: _routeFocus()

    // ── Placeholder (temporary until PlexArtistGrid is implemented) ───────────
    FocusScope {
        id: artistPlaceholder
        anchors.fill: parent
        focus: true

        Keys.onPressed: (event) => {
            if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.back()
            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                listenScreen.back()
            }
        }

        Rectangle {
            anchors.fill: parent
            color: Theme.colorBackground

            Text {
                anchors.centerIn: parent
                text: "♫  Music"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeTitle)
            }
        }
    }
}
