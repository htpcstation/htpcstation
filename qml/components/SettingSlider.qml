import QtQuick
import ".."

// Reusable numeric slider row for settings.
//
// A (Return) → enters adjust mode (arrows become visible).
// Left/Right in adjust mode → decrease/increase by step.
// A or B in adjust mode → confirms and exits adjust mode, emits valueChanged.
FocusScope {
    id: sliderRoot

    property string label: ""
    property int value: 0
    property int minValue: 0
    property int maxValue: 5000
    property int step: 100
    property string suffix: "ms"
    property bool adjusting: false
    property int _adjustValue: sliderRoot.value  // local value during adjustment

    signal valueEdited(int newValue)

    implicitHeight: root.vpx(56)

    // ── Background highlight ──────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: sliderRoot.activeFocus ? 0.8 : 0.0
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
        text: sliderRoot.label
        color: sliderRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Value display with arrows ─────────────────────────────────────────────
    Row {
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        spacing: root.vpx(8)

        // Left arrow
        Text {
            text: "◀"
            color: sliderRoot.adjusting ? Theme.colorPrimary : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            visible: sliderRoot.adjusting || sliderRoot.activeFocus
            opacity: sliderRoot.adjusting ? 1.0 : 0.4

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
            Behavior on opacity {
                NumberAnimation { duration: Theme.animDurationFast }
            }
        }

        // Value text
        Text {
            text: (sliderRoot.adjusting ? sliderRoot._adjustValue : sliderRoot.value) + sliderRoot.suffix
            color: sliderRoot.adjusting ? Theme.colorPrimary : Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            font.bold: sliderRoot.adjusting

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
        }

        // Right arrow
        Text {
            text: "▶"
            color: sliderRoot.adjusting ? Theme.colorPrimary : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            visible: sliderRoot.adjusting || sliderRoot.activeFocus
            opacity: sliderRoot.adjusting ? 1.0 : 0.4

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
            Behavior on opacity {
                NumberAnimation { duration: Theme.animDurationFast }
            }
        }
    }

    // ── Focus ring ────────────────────────────────────────────────────────────
    FocusRing {
        visible: sliderRoot.activeFocus && !sliderRoot.adjusting
    }

    // Adjusting mode ring (different color to indicate active adjustment)
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: Theme.colorPrimary
        border.width: root.vpx(Theme.focusRingWidth)
        radius: root.vpx(Theme.focusRingRadius)
        visible: sliderRoot.adjusting
        opacity: 0.7
    }

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (!sliderRoot.adjusting) {
            if (keys.isAccept(event)) {
                event.accepted = true
                sliderRoot._adjustValue = sliderRoot.value
                sliderRoot.adjusting = true
            }
        } else {
            if (event.key === Qt.Key_Left) {
                event.accepted = true
                sliderRoot._adjustValue = Math.max(sliderRoot.minValue, sliderRoot._adjustValue - sliderRoot.step)
            } else if (event.key === Qt.Key_Right) {
                event.accepted = true
                sliderRoot._adjustValue = Math.min(sliderRoot.maxValue, sliderRoot._adjustValue + sliderRoot.step)
            } else if (keys.isAccept(event)) {
                event.accepted = true
                sliderRoot.adjusting = false
                sliderRoot.valueEdited(sliderRoot._adjustValue)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                sliderRoot._adjustValue = sliderRoot.value  // revert
                sliderRoot.adjusting = false
            }
        }
    }
}
