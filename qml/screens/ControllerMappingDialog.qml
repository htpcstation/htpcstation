import QtQuick
import ".."
import "../components"

// Full-screen controller mapping dialog.
// Walk the user through pressing each of the 14 controller inputs sequentially,
// record the raw evdev codes, then save the mapping.
//
// Usage (from main.qml):
//   ControllerMappingDialog {
//       id: controllerMappingDialog
//       anchors.fill: parent
//       visible: false
//   }
//
//   function showControllerMapping() {
//       controllerMappingDialog.visible = true
//       controllerMappingDialog.start()
//   }
//
// Do NOT use id: root — ApplicationWindow owns that id.
FocusScope {
    id: mappingDialog

    // Only process input when this dialog is active.
    enabled: focus

    // ── Internal state ────────────────────────────────────────────────────────

    // State machine: "idle" | "waiting" | "recorded" | "complete"
    property string _state: "idle"

    // Actions list loaded from Python (list of {name, displayName, skippable})
    property var _actions: []

    // Current action index
    property int _currentIndex: 0

    // Recorded mappings: list of {name, type, code, value}
    property var _recordedMappings: []

    // Countdown seconds remaining for skippable actions
    property int _skipCountdown: 5

    // Status text shown below the prompt
    property string _statusText: ""

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    // Called externally to begin the mapping flow.
    function start() {
        _actions = settings ? settings.getControllerActions() : []
        _recordedMappings = []
        _currentIndex = 0
        _state = "idle"

        if (_actions.length === 0) {
            _statusText = "No controller actions found."
            _state = "complete"
            return
        }

        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.startRawMode()
        }

        _advanceTo(0)
    }

    // Advance to the action at the given index.
    function _advanceTo(index) {
        skipTimer.stop()
        advanceTimer.stop()

        if (index >= _actions.length) {
            // Stop raw mode and auto-save.  We can't require a button press
            // to confirm because the A/B mapping may be swapped until the
            // new mapping is applied — the user would hit "cancel" thinking
            // they're hitting "accept".
            if (typeof gamepadManager !== "undefined" && gamepadManager) {
                gamepadManager.stopRawMode()
            }
            _state = "complete"
            _statusText = "Saved!"
            // Save immediately
            if (settings) {
                settings.saveControllerMapping(_recordedMappings)
            }
            // Close after a brief confirmation
            autoCloseTimer.restart()
            return
        }

        _currentIndex = index
        _state = "waiting"

        var action = _actions[index]
        if (action.skippable) {
            _skipCountdown = 5
            _statusText = "Press button to map, or wait to skip"
            skipTimer.restart()
        } else {
            _statusText = "Press the button now..."
        }
    }

    // Check if an input is already recorded for a previous action.
    function _isDuplicate(evType, code, value) {
        for (var i = 0; i < _recordedMappings.length; i++) {
            var m = _recordedMappings[i]
            if (m.type === evType && m.code === code && m.value === value) {
                return true
            }
        }
        return false
    }

    // Called when raw input arrives during "waiting" state.
    function _onRawInput(evType, code, value) {
        // Check for duplicates
        if (_isDuplicate(evType, code, value)) {
            _statusText = "Already mapped — press a different button"
            return
        }

        // Record immediately for all actions
        _recordInput(evType, code, value)
    }

    // Record the current action with the given raw input and advance.
    function _recordInput(evType, code, value) {
        skipTimer.stop()

        var action = _actions[_currentIndex]
        var entry = {
            "name": action.name,
            "type": evType,
            "code": code,
            "value": value
        }
        _recordedMappings.push(entry)

        _state = "recorded"
        _statusText = "\u2713 Recorded"

        advanceTimer.restart()
    }

    // Skip the current action (use default mapping entry — omit from recorded list
    // so saveControllerMapping will use whatever is already on disk for that action).
    function _skipCurrent() {
        skipTimer.stop()
        _state = "recorded"
        _statusText = "Skipped"
        advanceTimer.restart()
    }

    // Signal emitted when the dialog closes (caller restores focus).
    signal closed()

    // Cancel the dialog: discard changes, stop raw mode, hide.
    function _cancel() {
        skipTimer.stop()
        advanceTimer.stop()
        _state = "idle"
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
        mappingDialog.visible = false
        mappingDialog.closed()
    }

    // _save is no longer needed — auto-save happens in _advanceTo when
    // all actions are complete.

    // ── Timers ────────────────────────────────────────────────────────────────

    // Auto-skip countdown timer for skippable actions (fires every second).
    Timer {
        id: skipTimer
        interval: 1000
        repeat: true
        onTriggered: {
            mappingDialog._skipCountdown -= 1
            if (mappingDialog._skipCountdown <= 0) {
                skipTimer.stop()
                mappingDialog._skipCurrent()
            } else {
                mappingDialog._statusText = "Press button to map, or wait to skip (" + mappingDialog._skipCountdown + "s)"
            }
        }
    }

    // Brief pause after recording before advancing to the next action.
    Timer {
        id: advanceTimer
        interval: 500
        repeat: false
        onTriggered: {
            mappingDialog._advanceTo(mappingDialog._currentIndex + 1)
        }
    }

    // Auto-close after save confirmation.
    Timer {
        id: autoCloseTimer
        interval: 1000
        repeat: false
        onTriggered: {
            mappingDialog._state = "idle"
            mappingDialog.visible = false
            mappingDialog.closed()
        }
    }

    // ── Raw input connection ──────────────────────────────────────────────────

    Connections {
        target: (typeof gamepadManager !== "undefined") ? gamepadManager : null
        enabled: mappingDialog._state === "waiting"

        function onRawInput(evType, code, value) {
            mappingDialog._onRawInput(evType, code, value)
        }
    }

    // ── Key handling ─────────────────────────────────────────────────────────

    Keys.onPressed: (event) => {
        event.accepted = true  // consume all keys while dialog is open

        // Complete state auto-saves and auto-closes — no input needed.
        // Only handle cancel during the mapping flow (waiting/recorded).
        if (mappingDialog._state === "waiting" || mappingDialog._state === "recorded") {
            if (keys.isCancel(event)) {
                mappingDialog._cancel()
            }
        }
    }

    // ── Dark semi-transparent backdrop ───────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorImagePlaceholder
        opacity: 0.85
    }

    // ── Dialog card ──────────────────────────────────────────────────────────
    Rectangle {
        id: dialogCard

        anchors.centerIn: parent
        width: root.vpx(760)
        height: root.vpx(400)

        color: Theme.colorSecondary
        radius: root.vpx(8)

        // ── Title ─────────────────────────────────────────────────────────
        Text {
            id: titleText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: parent.top
                topMargin: root.vpx(28)
            }
            text: "CONFIGURE CONTROLLER"
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            font.bold: true
            font.letterSpacing: root.vpx(2)
            color: Theme.colorPrimary
        }

        // ── Progress indicator ────────────────────────────────────────────
        Text {
            id: progressText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: titleText.bottom
                topMargin: root.vpx(12)
            }
            text: {
                if (mappingDialog._state === "complete") return "Complete"
                if (mappingDialog._actions.length === 0) return ""
                return (mappingDialog._currentIndex + 1) + " / " + mappingDialog._actions.length
            }
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
            color: Theme.colorTextDim
        }

        // ── Prompt text ───────────────────────────────────────────────────
        Text {
            id: promptText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: progressText.bottom
                topMargin: root.vpx(28)
            }
            text: {
                if (mappingDialog._state === "complete") {
                    return "Configuration Complete"
                }
                if (mappingDialog._actions.length === 0 || mappingDialog._currentIndex >= mappingDialog._actions.length) {
                    return ""
                }
                return "Press  " + mappingDialog._actions[mappingDialog._currentIndex].displayName
            }
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            color: Theme.colorText
        }

        // ── Status text ───────────────────────────────────────────────────
        Text {
            id: statusText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: promptText.bottom
                topMargin: root.vpx(20)
            }
            text: mappingDialog._statusText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            color: {
                if (mappingDialog._state === "recorded") return Theme.colorSuccess
                return Theme.colorTextDim
            }
        }

        // Complete state shows "Saved!" briefly then auto-closes.
        // No save/cancel buttons needed.

        // ── Cancel hint (non-complete states) ─────────────────────────────
        Text {
            id: cancelHint
            anchors {
                horizontalCenter: parent.horizontalCenter
                bottom: parent.bottom
                bottomMargin: root.vpx(20)
            }
            visible: mappingDialog._state !== "complete"
            text: keys.useGamepadLabels ? keys.cancelLabel + "  Cancel" : "Esc  Cancel"
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
            color: Theme.colorTextDim
        }
    }
}
