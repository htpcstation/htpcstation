import QtQuick
import ".."
import "../components"

// Modal overlay for capturing a gamepad button to use as the RetroArch
// hotkey modifier (enable_hotkey button).
//
// Usage (from RetroarchHotkeysScreen):
//   ModifierCaptureDialog {
//       id: modifierCaptureDialog
//       anchors.fill: parent
//       visible: false
//   }
//
//   // Show:
//   modifierCaptureDialog.visible = true
//   modifierCaptureDialog.forceActiveFocus()
//
// Do NOT use id: root — ApplicationWindow owns that id.
FocusScope {
    id: captureDialog

    // Only process input when this dialog is active.
    enabled: focus
    visible: false

    // ── Signals ───────────────────────────────────────────────────────────────
    signal buttonCaptured(int evdev_code)
    signal cancelled()

    // ── Internal state ────────────────────────────────────────────────────────
    property bool _listening: false

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    onVisibleChanged: {
        if (visible) {
            captureDialog._listening = true
            if (typeof gamepadManager !== "undefined" && gamepadManager) {
                gamepadManager.startRawMode()
            }
            timeoutTimer.restart()
            pulseAnimation.restart()
        } else {
            captureDialog._listening = false
            timeoutTimer.stop()
            pulseAnimation.stop()
        }
    }

    function _capture(evdev_code) {
        captureDialog._listening = false
        timeoutTimer.stop()
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
        captureDialog.visible = false
        captureDialog.buttonCaptured(evdev_code)
    }

    function _cancel() {
        captureDialog._listening = false
        timeoutTimer.stop()
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
        captureDialog.visible = false
        captureDialog.cancelled()
    }

    // ── Timers ────────────────────────────────────────────────────────────────

    // 10-second timeout — auto-cancel
    Timer {
        id: timeoutTimer
        interval: 10000
        repeat: false
        onTriggered: {
            captureDialog._cancel()
        }
    }

    // ── Raw input connection ──────────────────────────────────────────────────
    Connections {
        target: (typeof gamepadManager !== "undefined") ? gamepadManager : null
        enabled: captureDialog._listening

        function onRawInput(evType, code, value) {
            if (evType === "button" && value === 1) {
                captureDialog._capture(code)
            }
        }
    }

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        event.accepted = true
        if (event.key === Qt.Key_Escape) {
            captureDialog._cancel()
        }
    }

    // ── Dark semi-transparent backdrop ────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorImagePlaceholder
        opacity: 0.85
    }

    // ── Centred card ──────────────────────────────────────────────────────────
    Rectangle {
        id: captureCard

        anchors.centerIn: parent
        width: root.vpx(560)
        height: root.vpx(320)

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
            text: "SET HOTKEY MODIFIER"
            color: Theme.colorPrimary
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            font.bold: true
            font.letterSpacing: root.vpx(2)
        }

        // ── Instruction text ──────────────────────────────────────────────────
        Text {
            id: instructionText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: titleText.bottom
                topMargin: root.vpx(20)
            }
            width: parent.width - root.vpx(64)
            text: "Press the button you want to use as the hotkey modifier\n(Home, L3, R3, or any unmapped button)"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        // ── Animated "listening..." indicator ─────────────────────────────────
        Row {
            id: listeningRow
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: instructionText.bottom
                topMargin: root.vpx(24)
            }
            spacing: root.vpx(8)

            // Pulsing dot
            Rectangle {
                id: pulseDot
                width: root.vpx(10)
                height: root.vpx(10)
                radius: root.vpx(5)
                color: Theme.colorPrimary
                anchors.verticalCenter: parent.verticalCenter

                opacity: 1.0

                SequentialAnimation {
                    id: pulseAnimation
                    running: captureDialog.visible
                    loops: Animation.Infinite

                    NumberAnimation {
                        target: pulseDot
                        property: "opacity"
                        from: 1.0
                        to: 0.2
                        duration: 600
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        target: pulseDot
                        property: "opacity"
                        from: 0.2
                        to: 1.0
                        duration: 600
                        easing.type: Easing.InOutSine
                    }
                }
            }

            Text {
                text: "listening..."
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // ── Cancel hint ───────────────────────────────────────────────────────
        Text {
            anchors {
                horizontalCenter: parent.horizontalCenter
                bottom: parent.bottom
                bottomMargin: root.vpx(20)
            }
            text: "Esc  Cancel"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
