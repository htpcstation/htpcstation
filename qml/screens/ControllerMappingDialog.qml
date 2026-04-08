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

    // Recorded mappings: list of {name, type, code, value} (may also have also: [...])
    property var _recordedMappings: []

    // Co-firing events collected in the same tick as the primary event.
    property var _coFiringEvents: []

    // Currently held raw button codes — used to detect Start+Select combo cancel.
    property var _heldButtons: ({})

    // Evdev codes for start and select, loaded from the controller mapping.
    property int _startCode: -1
    property int _selectCode: -1

    // Countdown seconds remaining for auto-skip timer (skippable actions)
    property int _skipCountdown: 5

    // Hold-to-skip state: evdev code of the button being held for skip, -1 if none
    property int _holdSkipCode: -1
    property string _holdSkipEvType: "button"
    property int _holdSkipValue: 1
    property int _holdSkipCountdown: 3

    // Status text shown below the prompt
    property string _statusText: ""

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    // Called externally to begin the mapping flow.
    function start() {
        _actions = settings ? settings.getControllerActions() : []
        _recordedMappings = []
        _coFiringEvents = []
        _heldButtons = {}
        _currentIndex = 0
        _state = "idle"

        // Load start/select evdev codes for combo-cancel detection
        if (settings) {
            var m = settings.getControllerActionEvdevCodes()
            mappingDialog._startCode  = m["start"]  !== undefined ? m["start"]  : -1
            mappingDialog._selectCode = m["select"] !== undefined ? m["select"] : -1
        }

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
        holdSkipTimer.stop()
        holdSkipCountdownTimer.stop()
        mappingDialog._holdSkipCode = -1
        mappingDialog._holdSkipEvType = "button"
        mappingDialog._holdSkipValue = 1
        mappingDialog._holdSkipCountdown = 3

        if (index >= _actions.length) {
            // Stop raw mode and auto-save.  We can't require a button press
            // to confirm because the A/B mapping may be swapped until the
            // new mapping is applied — the user would hit "cancel" thinking
            // they're hitting "accept".
            _state = "complete"
            _statusText = "Saved!"
            // Save BEFORE stopping raw mode so the SDL resolver is still open
            // when saveControllerMapping resolves SDL records for each input.
            if (settings) {
                settings.saveControllerMapping(_recordedMappings)
            }
            if (typeof gamepadManager !== "undefined" && gamepadManager) {
                gamepadManager.stopRawMode()
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

    // Check if an input is already recorded for a previous action (including also arrays).
    function _isDuplicate(evType, code, value) {
        for (var i = 0; i < _recordedMappings.length; i++) {
            var m = _recordedMappings[i]
            if (m.type === evType && m.code === code && m.value === value) return true
            var also = m.also || []
            for (var j = 0; j < also.length; j++) {
                if (also[j].type === evType && also[j].code === code && also[j].value === value)
                    return true
            }
        }
        return false
    }

    // Called for all raw input while Connections is enabled.
    function _onRawInput(evType, code, value) {
        // Track held buttons for Start+Select combo cancel (works in any state).
        if (evType === "button") {
            if (value === 1) {
                var held = mappingDialog._heldButtons
                held[code] = true
                mappingDialog._heldButtons = held
                // Start+Select held simultaneously → cancel at any time
                if (mappingDialog._startCode >= 0 && mappingDialog._selectCode >= 0
                        && mappingDialog._heldButtons[mappingDialog._startCode]
                        && mappingDialog._heldButtons[mappingDialog._selectCode]) {
                    mappingDialog._cancel()
                    return
                }
            } else if (value === 0) {
                var held2 = mappingDialog._heldButtons
                delete held2[code]
                mappingDialog._heldButtons = held2
                // Button released — if it was the hold-to-skip button and timer
                // is still running, cancel the hold and record the input normally.
                if (mappingDialog._holdSkipCode === code && holdSkipTimer.running) {
                    holdSkipTimer.stop()
                    holdSkipCountdownTimer.stop()
                    var recEvType = mappingDialog._holdSkipEvType
                    var recCode  = mappingDialog._holdSkipCode
                    var recValue = mappingDialog._holdSkipValue
                    mappingDialog._holdSkipCode = -1
                    mappingDialog._holdSkipEvType = "button"
                    mappingDialog._holdSkipValue = 1
                    mappingDialog._holdSkipCountdown = 3
                    mappingDialog._statusText = ""
                    if (mappingDialog._state === "waiting" && !_isDuplicate(recEvType, recCode, recValue)) {
                        mappingDialog._coFiringEvents = []
                        _recordInput(recEvType, recCode, recValue)
                        coFiringTimer.restart()
                    }
                }
                return
            }
        }

        // Only process mapping input during "waiting" state.
        // Axis events are also accepted during the co-firing window (interval:0 timer).
        // Button events during the co-firing window are NOT co-firing — ignore them.
        if (evType === "button" && mappingDialog._state !== "waiting") return
        if (evType === "axis" && mappingDialog._state !== "waiting" && !coFiringTimer.running) return

        // Silently skip duplicates
        if (_isDuplicate(evType, code, value)) {
            if (mappingDialog._state === "waiting")
                _statusText = "Already mapped — press a different button"
            return
        }

        if (!coFiringTimer.running) {
            // First event for this action — check if skippable and start hold timer
            var action = mappingDialog._actions[mappingDialog._currentIndex]
            if (action && action.skippable && mappingDialog._holdSkipCode === -1) {
                // Skippable action: start hold-to-skip timer.
                // Record on button release (handled in value===0 block above).
                // For axis events (triggers), record immediately after hold timer
                // fires or is cancelled — store the event for later.
                mappingDialog._holdSkipCode = code
                mappingDialog._holdSkipEvType = evType
                mappingDialog._holdSkipValue = value
                mappingDialog._holdSkipCountdown = 3
                mappingDialog._statusText = "Hold to skip..."
                holdSkipTimer.restart()
                holdSkipCountdownTimer.restart()
            } else {
                // Non-skippable or already have a pending hold — record immediately
                mappingDialog._coFiringEvents = []
                _recordInput(evType, code, value)
                coFiringTimer.restart()
            }
        } else if (evType === "axis") {
            // Co-firing axis event — collect it (only axes co-fire with buttons)
            mappingDialog._coFiringEvents.push({"type": evType, "code": code, "value": value})
        }
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
        holdSkipTimer.stop()
        holdSkipCountdownTimer.stop()
        mappingDialog._holdSkipCode = -1
        mappingDialog._holdSkipEvType = "button"
        mappingDialog._holdSkipValue = 1
        mappingDialog._holdSkipCountdown = 3
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
        coFiringTimer.stop()
        holdSkipTimer.stop()
        holdSkipCountdownTimer.stop()
        mappingDialog._coFiringEvents = []
        mappingDialog._heldButtons = {}
        mappingDialog._holdSkipCode = -1
        mappingDialog._holdSkipEvType = "button"
        mappingDialog._holdSkipValue = 1
        mappingDialog._holdSkipCountdown = 3
        _state = "idle"
        if (typeof gamepadManager !== "undefined" && gamepadManager) {
            gamepadManager.stopRawMode()
        }
        mappingDialog.visible = false
        mappingDialog.closed()
    }

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

    // Fires one event loop tick after the primary event is recorded.
    // By then all co-firing events from the same _on_readable() loop have arrived.
    Timer {
        id: coFiringTimer
        interval: 0
        repeat: false
        onTriggered: {
            // Co-firing collection window closed. If any co-firing events were collected,
            // update the last recorded entry to include them.
            if (mappingDialog._coFiringEvents.length > 0) {
                var last = _recordedMappings[_recordedMappings.length - 1]
                last.also = mappingDialog._coFiringEvents.slice()
                _recordedMappings[_recordedMappings.length - 1] = last
                mappingDialog._coFiringEvents = []
            }
        }
    }

    // Hold-to-skip: fires after 3s hold on a skippable action.
    Timer {
        id: holdSkipTimer
        interval: 3000
        repeat: false
        onTriggered: {
            holdSkipCountdownTimer.stop()
            mappingDialog._holdSkipCode = -1
            mappingDialog._holdSkipEvType = "button"
            mappingDialog._holdSkipValue = 1
            mappingDialog._holdSkipCountdown = 3
            mappingDialog._skipCurrent()
        }
    }

    // Ticks every second to update the hold-to-skip countdown display.
    Timer {
        id: holdSkipCountdownTimer
        interval: 1000
        repeat: true
        onTriggered: {
            if (mappingDialog._holdSkipCountdown > 1) {
                mappingDialog._holdSkipCountdown -= 1
                mappingDialog._statusText = "Hold to skip (" + mappingDialog._holdSkipCountdown + "s)..."
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
        // Enabled in all active states so we can track button releases for
        // the Start+Select combo cancel and co-firing axis collection.
        enabled: mappingDialog._state !== "idle"

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
            text: keys && keys.useGamepadLabels ? "Start+Select  —  Cancel" : "Esc  —  Cancel"
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
            color: Theme.colorTextDim
        }
    }
}
