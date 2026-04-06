import QtQuick
import ".."
import "../components"

// Modal overlay for capturing a gamepad button to use as the RetroArch
// hotkey modifier (enable_hotkey button) or a hotkey action button.
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

    // Set to true when capturing a hotkey action (axis/hat allowed)
    // Set to false (default) when capturing the modifier (button only)
    property bool allowAxisInput: false

    // ── Signals ───────────────────────────────────────────────────────────────
    signal buttonCaptured(int evdev_code)
    signal axisCaptured(int evdev_code, int value)
    signal buttonCleared()
    signal cancelled()

    // ── Internal state ────────────────────────────────────────────────────────
    property bool _listening: false
    property int _pendingCode: -1
    property string _pendingEvType: ""
    property int _countdown: 0

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    onVisibleChanged: {
        if (visible) {
            captureDialog._listening = true
            captureDialog._pendingEvType = ""
            if (typeof gamepadManager !== "undefined" && gamepadManager) {
                gamepadManager.startRawMode()
            }
            timeoutTimer.restart()
            pulseAnimation.restart()
        } else {
            captureDialog._listening = false
            holdTimer.stop()
            countdownTimer.stop()
            captureDialog._pendingCode = -1
            captureDialog._pendingEvType = ""
            captureDialog._countdown = 0
            timeoutTimer.stop()
            pulseAnimation.stop()
        }
    }

    function _captureButton(evdev_code) {
        holdTimer.stop()
        countdownTimer.stop()
        captureDialog._pendingCode = -1
        captureDialog._pendingEvType = ""
        captureDialog._countdown = 0
        captureDialog._listening = false
        timeoutTimer.stop()
        captureDialog.visible = false
        // Emit signal BEFORE stopRawMode so the SDL resolver is still open
        // when the handler calls settings.setHotkeyActionByEvdev().
        captureDialog.buttonCaptured(evdev_code)
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
    }

    function _captureAxis(code, value) {
        holdTimer.stop()
        countdownTimer.stop()
        captureDialog._pendingCode = -1
        captureDialog._pendingEvType = ""
        captureDialog._countdown = 0
        captureDialog._listening = false
        timeoutTimer.stop()
        captureDialog.visible = false
        // Emit signal BEFORE stopRawMode so the SDL resolver is still open
        // when the handler calls settings.setHotkeyActionByAxis().
        captureDialog.axisCaptured(code, value)
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
    }

    function _clear() {
        holdTimer.stop()
        countdownTimer.stop()
        captureDialog._pendingCode = -1
        captureDialog._pendingEvType = ""
        captureDialog._countdown = 0
        captureDialog._listening = false
        timeoutTimer.stop()
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
        captureDialog.visible = false
        captureDialog.buttonCleared()
    }

    function _cancel() {
        holdTimer.stop()
        countdownTimer.stop()
        captureDialog._pendingCode = -1
        captureDialog._pendingEvType = ""
        captureDialog._countdown = 0
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

    // 3-second hold-to-clear timer
    Timer {
        id: holdTimer
        interval: 3000
        repeat: false
        onTriggered: {
            captureDialog._pendingCode = -1
            captureDialog._pendingEvType = ""
            captureDialog._clear()
        }
    }

    // 1-second tick timer — runs while hold timer is active
    Timer {
        id: countdownTimer
        interval: 1000
        repeat: true
        onTriggered: {
            if (captureDialog._countdown > 0) {
                captureDialog._countdown -= 1
            }
        }
    }

    // ── Raw input connection ──────────────────────────────────────────────────
    Connections {
        target: (typeof gamepadManager !== "undefined") ? gamepadManager : null
        enabled: captureDialog._listening

        function onRawInput(evType, code, value) {
            // Guard: _listening may have been cleared by a prior event in the same
            // tick (e.g. dual-reporting devices that fire both EV_ABS and EV_KEY
            // for the same physical button, like L2/R2 on some D-input controllers).
            if (!captureDialog._listening) return

            if (evType === "button" && value === 1) {
                // Button pressed — start hold timer, record pending code
                captureDialog._pendingCode = code
                captureDialog._pendingEvType = "button"
                captureDialog._countdown = 3
                countdownTimer.restart()
                holdTimer.restart()
            } else if (evType === "button" && value === 0) {
                // Button released — if hold timer still running, it's a tap → capture
                if (captureDialog._pendingCode === code
                        && captureDialog._pendingEvType === "button"
                        && holdTimer.running) {
                    holdTimer.stop()
                    countdownTimer.stop()
                    captureDialog._countdown = 0
                    var captured = captureDialog._pendingCode
                    captureDialog._pendingCode = -1
                    captureDialog._pendingEvType = ""
                    captureDialog._captureButton(captured)
                } else {
                    captureDialog._pendingCode = -1
                    captureDialog._pendingEvType = ""
                }
                // If hold timer already fired, _clear() was already called — do nothing
            } else if (evType === "axis" && captureDialog.allowAxisInput) {
                // Axis/hat: capture immediately (no hold-to-clear)
                captureDialog._captureAxis(code, value)
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
        height: root.vpx(360)

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
            text: "Tap to assign.\nHold 3 seconds to clear."
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

        // ── Countdown display — visible while a button is being held ─────────
        Text {
            id: countdownText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: listeningRow.bottom
                topMargin: root.vpx(16)
            }
            visible: captureDialog._pendingCode !== -1
            text: captureDialog._countdown > 0 ? captureDialog._countdown + "..." : "Clearing..."
            color: Theme.colorPrimary
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            font.bold: true
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
