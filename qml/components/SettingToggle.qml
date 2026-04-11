import QtQuick
import ".."
import HTPCBackend 1.0

// Reusable toggle row for boolean Settings.
//
// A (Return) or Left/Right toggles the value and emits toggled(newValue).
// Shows "ON" in Theme.colorPrimary or "OFF" in Theme.colorTextDim.
FocusScope {
    id: toggleRoot

    property string label: ""
    property bool checked: false

    signal toggled(bool newValue)

    implicitHeight: root.vpx(56)

    // ── Background highlight ──────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: toggleRoot.activeFocus ? 0.8 : 0.0
        radius: root.vpx(Theme.focusRingRadius)

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Label ─────────────────────────────────────────────────────────────────
    Text {
        anchors {
            left: parent.left
            leftMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        text: toggleRoot.label
        color: toggleRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Toggle indicator ──────────────────────────────────────────────────────
    Rectangle {
        id: togglePill
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        width: root.vpx(64)
        height: root.vpx(32)
        radius: root.vpx(Theme.focusRingRadius)
        color: toggleRoot.checked ? Theme.colorPrimary : Theme.colorSecondary
        border.color: toggleRoot.checked ? Theme.colorPrimary : Theme.colorTextDim
        border.width: root.vpx(2)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.animDurationFast }
        }

        Text {
            anchors.centerIn: parent
            text: toggleRoot.checked ? "ON" : "OFF"
            color: toggleRoot.checked ? Theme.colorText : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
            font.bold: true

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
        }
    }

    // ── Focus ring ────────────────────────────────────────────────────────────
    FocusRing {}

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (KeyHandler.isAccept(event) || event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
            event.accepted = true
            toggleRoot.toggled(!toggleRoot.checked)
        }
    }
}
