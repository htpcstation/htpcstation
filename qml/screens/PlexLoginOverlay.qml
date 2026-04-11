import QtQuick
import ".."
import HTPCBackend 1.0

// In-app Plex PIN login overlay.
// Shown when the user selects "Sign in with Plex" in Settings.
// The user visits plex.tv/link on another device and enters the displayed code.
//
// Usage (from SettingsScreen):
//   PlexLoginOverlay {
//       id: plexLoginOverlay
//       anchors.fill: parent
//   }
//   // Show:
//   plexLoginOverlay.visible = true
//   plexLoginOverlay.forceActiveFocus()
//   Settings.startPlexPinLogin()
//
// Wire plexLoginStatus signal in the parent (SettingsScreen), not here.
FocusScope {
    id: plexOverlay

    // Only process input when this overlay is active.
    enabled: focus
    visible: false

    // ── State ─────────────────────────────────────────────────────────────────
    property string _pinCode: ""
    property string _status: "waiting"   // "waiting" | "success" | "timeout" | "error"

    // Reset state whenever the overlay becomes visible.
    onVisibleChanged: {
        if (visible) {
            _pinCode = ""
            _status = "waiting"
        }
    }

    // ── Dark semi-transparent backdrop ────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorImagePlaceholder
        opacity: 0.7
    }

    // ── Centred card ──────────────────────────────────────────────────────────
    Rectangle {
        id: card

        anchors.centerIn: parent
        width: root.vpx(480)
        height: root.vpx(300)

        color: Theme.colorSecondary
        radius: root.vpx(8)

        // ── Title ─────────────────────────────────────────────────────────────
        Text {
            id: titleText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: parent.top
                topMargin: root.vpx(32)
            }
            text: "Sign in with Plex"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            font.bold: true
        }

        // ── Instruction ───────────────────────────────────────────────────────
        Text {
            id: instructionText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: titleText.bottom
                topMargin: root.vpx(12)
            }
            text: "Go to plex.tv/link on another device and enter:"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }

        // ── PIN code display ──────────────────────────────────────────────────
        Text {
            id: pinText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: instructionText.bottom
                topMargin: root.vpx(16)
            }
            text: plexOverlay._pinCode.length > 0 ? plexOverlay._pinCode : "----"
            color: Theme.colorPrimary
            font.family: "Monospace"
            font.pixelSize: root.vpx(48)
            font.bold: true
            font.letterSpacing: root.vpx(8)
        }

        // ── Status line ───────────────────────────────────────────────────────
        Text {
            id: statusText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: pinText.bottom
                topMargin: root.vpx(12)
            }
            text: {
                if (plexOverlay._status === "success")  return "Signed in!"
                if (plexOverlay._status === "timeout")  return "Timed out"
                if (plexOverlay._status === "error")    return "Error"
                return "Waiting\u2026"
            }
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }

        // ── Hint bar ──────────────────────────────────────────────────────────
        Rectangle {
            id: hintBar
            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            height: root.vpx(36)
            color: "transparent"

            Text {
                anchors.centerIn: parent
                text: KeyHandler.useGamepadLabels ? KeyHandler.cancelLabel + "  Cancel" : "Esc  Cancel"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (KeyHandler.isCancel(event)) {
            event.accepted = true
            Settings.cancelPlexPinLogin()
        }
    }
}
