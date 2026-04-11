import QtQuick
import ".."
import HTPCBackend 1.0

// Reusable action button row for Settings.
//
// A (Return) → emits clicked().
// Shows statusText briefly after action (auto-clears after 3 seconds).
FocusScope {
    id: buttonRoot

    property string label: ""
    property string statusText: ""

    signal clicked()

    implicitHeight: root.vpx(56)

    // Auto-clear status text after 3 seconds
    Timer {
        id: statusClearTimer
        interval: 3000
        repeat: false
        onTriggered: buttonRoot.statusText = ""
    }

    // ── Background highlight ──────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: buttonRoot.activeFocus ? 0.8 : 0.0
        radius: root.vpx(Theme.focusRingRadius)

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Button pill ───────────────────────────────────────────────────────────
    Rectangle {
        id: buttonPill
        anchors {
            left: parent.left
            leftMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        width: buttonLabel.implicitWidth + root.vpx(32)
        height: root.vpx(36)
        radius: root.vpx(Theme.focusRingRadius)
        color: buttonRoot.activeFocus ? Theme.colorPrimary : "transparent"
        border.color: buttonRoot.activeFocus ? Theme.colorPrimary : Theme.colorTextDim
        border.width: root.vpx(1)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.animDurationFast }
        }

        Text {
            id: buttonLabel
            anchors.centerIn: parent
            text: buttonRoot.label
            color: buttonRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
        }
    }

    // ── Status text ───────────────────────────────────────────────────────────
    Text {
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        text: buttonRoot.statusText
        color: buttonRoot.statusText.startsWith("Failed") || buttonRoot.statusText.startsWith("Error")
            ? Theme.colorError
            : Theme.colorPrimary
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
        visible: buttonRoot.statusText.length > 0

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Focus ring ────────────────────────────────────────────────────────────
    FocusRing {}

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (KeyHandler.isAccept(event)) {
            event.accepted = true
            buttonRoot.clicked()
            statusClearTimer.restart()
        }
    }
}
