import QtQuick
import ".."
import "../components"
import HTPCBackend 1.0

// RetroArch Hotkeys sub-screen — shows the hotkey modifier and the
// hotkey action → button mapping, plus rewind Settings.
//
// Usage (from SettingsScreen.qml):
//   RetroarchHotkeysScreen {
//       id: retroarchHotkeysScreen
//       anchors.fill: parent
//       visible: false
//   }
//
//   function showRetroarchHotkeys() {
//       retroarchHotkeysScreen.config = Settings ? Settings.getRetroarchHotkeyConfig() : {}
//       retroarchHotkeysScreen.visible = true
//       retroarchHotkeysScreen.forceActiveFocus()
//   }
//
// Do NOT use id: root — ApplicationWindow owns that id.
FocusScope {
    id: hotkeysScreen

    // Only process input when this screen is active.
    enabled: focus

    // Config object populated by showRetroarchHotkeys():
    //   { modifier_evdev, modifier_sdl, modifier_label, mapping, hotkey_rows, cfg_path,
    //     rewind_enable, rewind_buffer_size, rewind_granularity }
    property var config: ({})

    // Emit when B (Escape) is pressed.
    signal back()

    // ── Internal state ────────────────────────────────────────────────────────

    // Total focusable rows:
    //   Row 0:     modifier
    //   Rows 1–N:  hotkey rows (from config.hotkey_rows)
    //   Row N+1:   Rewind Enable (toggle)
    //   Row N+2:   Buffer Size (cycle)
    //   Row N+3:   Rewind Frames (cycle)
    //   Row N+4:   Apply button
    property int _rowCount: {
        var rows = (config && config.hotkey_rows) ? config.hotkey_rows.length : 0
        return 1 + rows + 3 + 1  // modifier + hotkeys + rewind rows + apply
    }

    // Currently focused row index
    property int _focusedRow: 0

    // Which hotkey action is being captured
    property string _captureTargetAction: ""

    // Rewind state (kept in sync with config)
    property bool _rewindEnable: config ? !!config.rewind_enable : false
    property int _rewindBufferSize: config ? (config.rewind_buffer_size || 20) : 20
    property int _rewindGranularity: config ? (config.rewind_granularity || 1) : 1

    // Sync rewind state when config changes
    onConfigChanged: {
        if (config) {
            hotkeysScreen._rewindEnable = !!config.rewind_enable
            hotkeysScreen._rewindBufferSize = config.rewind_buffer_size || 20
            hotkeysScreen._rewindGranularity = config.rewind_granularity || 1
        }
        // Warn if the controller mapping wizard hasn't been run yet.
        if (Settings && !Settings.hasControllerMappingWithSdl()) {
            hotkeysScreen._showToast("Recommended: run the controller mapping wizard before assigning hotkeys")
        }
    }

    // Buffer size cycle values
    readonly property var _bufferSizeOptions: [20, 40, 60, 80, 100, 150, 200, 300, 500]
    // Rewind frames cycle values
    readonly property var _granularityOptions: [1, 2, 4, 8, 16, 32]

    // ── Toast notification ────────────────────────────────────────────────────
    property string _toastText: ""

    Timer {
        id: toastTimer
        interval: 2500
        repeat: false
        onTriggered: hotkeysScreen._toastText = ""
    }

    function _showToast(msg) {
        hotkeysScreen._toastText = msg
        toastTimer.restart()
    }

    // ── Helper: number of hotkey rows ─────────────────────────────────────────
    function _hotkeyRowCount() {
        return (config && config.hotkey_rows) ? config.hotkey_rows.length : 0
    }

    // ── Rewind row indices (computed from hotkey count) ───────────────────────
    // Row index for Rewind Enable
    function _rewindEnableRow() { return 1 + _hotkeyRowCount() }
    // Row index for Buffer Size
    function _bufferSizeRow()   { return 2 + _hotkeyRowCount() }
    // Row index for Rewind Frames
    function _granularityRow()  { return 3 + _hotkeyRowCount() }
    // Row index for Apply button
    function _applyRow()        { return 4 + _hotkeyRowCount() }

    // ── Cycle helpers ─────────────────────────────────────────────────────────
    function _cycleBufferSize(forward) {
        var opts = hotkeysScreen._bufferSizeOptions
        var idx = opts.indexOf(hotkeysScreen._rewindBufferSize)
        if (idx < 0) idx = 0
        if (forward) {
            idx = (idx + 1) % opts.length
        } else {
            idx = (idx - 1 + opts.length) % opts.length
        }
        var newVal = opts[idx]
        hotkeysScreen._rewindBufferSize = newVal
        if (Settings) Settings.setRewindBufferSize(newVal)
    }

    function _cycleGranularity(forward) {
        var opts = hotkeysScreen._granularityOptions
        var idx = opts.indexOf(hotkeysScreen._rewindGranularity)
        if (idx < 0) idx = 0
        if (forward) {
            idx = (idx + 1) % opts.length
        } else {
            idx = (idx - 1 + opts.length) % opts.length
        }
        var newVal = opts[idx]
        hotkeysScreen._rewindGranularity = newVal
        if (Settings) Settings.setRewindGranularity(newVal)
    }

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Up) {
            event.accepted = true
            if (hotkeysScreen._focusedRow > 0) {
                hotkeysScreen._focusedRow -= 1
                _scrollToFocused()
            }
        } else if (event.key === Qt.Key_Down) {
            event.accepted = true
            if (hotkeysScreen._focusedRow < hotkeysScreen._rowCount - 1) {
                hotkeysScreen._focusedRow += 1
                _scrollToFocused()
            }
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            var focused = hotkeysScreen._focusedRow
            if (focused === _bufferSizeRow()) {
                _cycleBufferSize(false)
            } else if (focused === _granularityRow()) {
                _cycleGranularity(false)
            }
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            var focused = hotkeysScreen._focusedRow
            if (focused === _bufferSizeRow()) {
                _cycleBufferSize(true)
            } else if (focused === _granularityRow()) {
                _cycleGranularity(true)
            } else if (focused === 0 || focused === _applyRow()) {
                _activateFocused()
            }
            // hotkey rows and rewind enable: Right does nothing
        } else if (KeyHandler.isAccept(event)) {
            event.accepted = true
            _activateFocused()
        } else if (KeyHandler.isCancel(event)) {
            event.accepted = true
            hotkeysScreen.back()
        }
    }

    function _scrollToFocused() {
        // Only scroll for rows inside the ListView (modifier + hotkey rows).
        var rows = _hotkeyRowCount()
        if (hotkeysScreen._focusedRow <= rows) {
            hotkeysList.positionViewAtIndex(hotkeysScreen._focusedRow, ListView.Contain)
        }
    }

    function _activateFocused() {
        var rows = _hotkeyRowCount()
        if (hotkeysScreen._focusedRow === 0) {
            // Modifier row — open modifier capture dialog
            modifierCaptureDialog.visible = true
            modifierCaptureDialog.forceActiveFocus()
        } else if (hotkeysScreen._focusedRow >= 1 && hotkeysScreen._focusedRow <= rows) {
            // Hotkey row — open hotkey capture dialog
            var rowData = config.hotkey_rows[hotkeysScreen._focusedRow - 1]
            hotkeysScreen._captureTargetAction = rowData.hotkey_action
            hotkeyCaptureDialog.visible = true
            hotkeyCaptureDialog.forceActiveFocus()
        } else if (hotkeysScreen._focusedRow === _rewindEnableRow()) {
            // Toggle rewind enable
            var newVal = !hotkeysScreen._rewindEnable
            hotkeysScreen._rewindEnable = newVal
            if (Settings) Settings.setRewindEnable(newVal)
        } else if (hotkeysScreen._focusedRow === _bufferSizeRow()) {
            // Cycle buffer size forward on Accept
            _cycleBufferSize(true)
        } else if (hotkeysScreen._focusedRow === _granularityRow()) {
            // Cycle granularity forward on Accept
            _cycleGranularity(true)
        } else if (hotkeysScreen._focusedRow === _applyRow()) {
            // Apply button
            _applyHotkeys()
        }
    }

    function _applyHotkeys() {
        if (!Settings) {
            hotkeysScreen._showToast("Error — check logs")
            return
        }
        try {
            Settings.applyRetroarchHotkeys()
            hotkeysScreen._showToast("Applied")
        } catch (e) {
            hotkeysScreen._showToast("Error — check logs")
        }
    }

    // ── Dark background ───────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorBackground
    }

    // ── Header bar ────────────────────────────────────────────────────────────
    Rectangle {
        id: headerBar

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "◀  RetroArch Hotkeys"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        Row {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(16)

            Text {
                text: "Enter  Select"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: KeyHandler.useGamepadLabels ? KeyHandler.cancelLabel + "  Back" : "Esc  Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Scrollable list (modifier row + hotkey rows) ──────────────────────────
    ListView {
        id: hotkeysList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: rewindSection.top
            topMargin: root.vpx(8)
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }

        clip: true
        interactive: false  // We handle scrolling manually via positionViewAtIndex
        highlightMoveDuration: Theme.animDurationFast

        // Model: modifier row (index 0) + one entry per hotkey_row
        model: {
            var rows = [{ _type: "modifier" }]
            var hotkeys = (hotkeysScreen.config && hotkeysScreen.config.hotkey_rows)
                ? hotkeysScreen.config.hotkey_rows : []
            for (var i = 0; i < hotkeys.length; i++) {
                rows.push({ _type: "hotkey", _data: hotkeys[i] })
            }
            return rows
        }

        delegate: Item {
            id: delegateItem
            width: hotkeysList.width
            height: root.vpx(56)

            readonly property int _listIndex: index
            readonly property bool _isFocused: hotkeysScreen._focusedRow === index
            readonly property bool _isModifier: modelData._type === "modifier"
            readonly property var _hotkeyData: modelData._data || null

            // ── Row highlight ─────────────────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateItem._isFocused ? Theme.opacityOverlay : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Focus ring ────────────────────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: Theme.colorFocusRing
                border.width: root.vpx(Theme.focusRingWidth)
                radius: root.vpx(Theme.focusRingRadius)
                visible: delegateItem._isFocused
            }

            // ── Modifier row layout ───────────────────────────────────────────
            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                visible: delegateItem._isModifier

                Text {
                    width: parent.width * 0.55
                    text: "Hotkey Enable Button"
                    color: delegateItem._isFocused ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: true
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }

                Text {
                    width: parent.width * 0.45
                    text: {
                        var lbl = hotkeysScreen.config ? hotkeysScreen.config.modifier_label : ""
                        return lbl || "Not set"
                    }
                    color: {
                        var lbl = hotkeysScreen.config ? hotkeysScreen.config.modifier_label : ""
                        return lbl ? Theme.colorPrimary : Theme.colorTextDim
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }
            }

            // ── Hotkey row layout ─────────────────────────────────────────────
            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                visible: !delegateItem._isModifier

                // Left column: hotkey action label (e.g. "Save State")
                Text {
                    width: parent.width * 0.55
                    text: delegateItem._hotkeyData ? (delegateItem._hotkeyData.label || "") : ""
                    color: delegateItem._isFocused ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Right column: assigned button label (e.g. "A/East") or "Not set"
                Text {
                    width: parent.width * 0.45
                    text: {
                        if (!delegateItem._hotkeyData) return "Not set"
                        var lbl = delegateItem._hotkeyData.button_label
                        return (lbl && lbl !== "") ? lbl : "Not set"
                    }
                    color: {
                        if (!delegateItem._hotkeyData) return Theme.colorTextDim
                        var lbl = delegateItem._hotkeyData.button_label
                        return (lbl && lbl !== "") ? Theme.colorPrimary : Theme.colorTextDim
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }
            }

            // ── Separator line ────────────────────────────────────────────────
            Rectangle {
                anchors {
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }
        }
    }

    // ── Rewind section (3 rows: Enable, Buffer Size, Rewind Frames) ───────────
    Item {
        id: rewindSection
        anchors {
            left: parent.left
            right: parent.right
            bottom: applyButton.top
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(0)
        }
        height: root.vpx(56) * 3

        // ── Row: Rewind Enable ────────────────────────────────────────────────
        Item {
            id: rewindEnableRow
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
            }
            height: root.vpx(56)

            readonly property bool _isFocused: hotkeysScreen._focusedRow === hotkeysScreen._rewindEnableRow()

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: rewindEnableRow._isFocused ? 0.6 : 0.0
                radius: root.vpx(Theme.focusRingRadius)
                Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
            }
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: Theme.colorFocusRing
                border.width: root.vpx(Theme.focusRingWidth)
                radius: root.vpx(Theme.focusRingRadius)
                visible: rewindEnableRow._isFocused
            }

            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }

                Text {
                    width: parent.width * 0.55
                    text: "Rewind"
                    color: rewindEnableRow._isFocused ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                }

                Text {
                    width: parent.width * 0.45
                    text: hotkeysScreen._rewindEnable ? "On" : "Off"
                    color: hotkeysScreen._rewindEnable ? Theme.colorPrimary : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                }
            }

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }
        }

        // ── Row: Buffer Size ──────────────────────────────────────────────────
        Item {
            id: bufferSizeRow
            anchors {
                left: parent.left
                right: parent.right
                top: rewindEnableRow.bottom
            }
            height: root.vpx(56)

            readonly property bool _isFocused: hotkeysScreen._focusedRow === hotkeysScreen._bufferSizeRow()

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: bufferSizeRow._isFocused ? 0.6 : 0.0
                radius: root.vpx(Theme.focusRingRadius)
                Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
            }
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: Theme.colorFocusRing
                border.width: root.vpx(Theme.focusRingWidth)
                radius: root.vpx(Theme.focusRingRadius)
                visible: bufferSizeRow._isFocused
            }

            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }

                Text {
                    width: parent.width * 0.55
                    text: "Buffer Size"
                    color: bufferSizeRow._isFocused ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                }

                Text {
                    width: parent.width * 0.45
                    text: hotkeysScreen._rewindBufferSize + " MB"
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                }
            }

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }
        }

        // ── Row: Rewind Frames ────────────────────────────────────────────────
        Item {
            id: granularityRow
            anchors {
                left: parent.left
                right: parent.right
                top: bufferSizeRow.bottom
            }
            height: root.vpx(56)

            readonly property bool _isFocused: hotkeysScreen._focusedRow === hotkeysScreen._granularityRow()

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: granularityRow._isFocused ? 0.6 : 0.0
                radius: root.vpx(Theme.focusRingRadius)
                Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
            }
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: Theme.colorFocusRing
                border.width: root.vpx(Theme.focusRingWidth)
                radius: root.vpx(Theme.focusRingRadius)
                visible: granularityRow._isFocused
            }

            Row {
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }

                Text {
                    width: parent.width * 0.55
                    text: "Rewind Frames"
                    color: granularityRow._isFocused ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                    Behavior on color { ColorAnimation { duration: Theme.animDurationFast } }
                }

                Text {
                    width: parent.width * 0.45
                    text: hotkeysScreen._rewindGranularity + " frames"
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                }
            }

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }
        }
    }

    // ── Apply button ──────────────────────────────────────────────────────────
    Item {
        id: applyButton

        anchors {
            left: parent.left
            right: parent.right
            bottom: toastOverlay.top
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }
        height: root.vpx(56)

        readonly property bool _isFocused: hotkeysScreen._focusedRow === hotkeysScreen._applyRow()

        // ── Background highlight ──────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: Theme.colorSecondary
            opacity: applyButton._isFocused ? 0.8 : 0.0
            radius: root.vpx(Theme.focusRingRadius)

            Behavior on opacity {
                NumberAnimation { duration: Theme.animDurationFast }
            }
        }

        // ── Focus ring ────────────────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: "transparent"
            border.color: Theme.colorFocusRing
            border.width: root.vpx(Theme.focusRingWidth)
            radius: root.vpx(Theme.focusRingRadius)
            visible: applyButton._isFocused
        }

        // ── Button pill ───────────────────────────────────────────────────────
        Rectangle {
            id: applyPill
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            width: applyLabel.implicitWidth + root.vpx(32)
            height: root.vpx(36)
            radius: root.vpx(Theme.focusRingRadius)
            color: applyButton._isFocused ? Theme.colorPrimary : "transparent"
            border.color: applyButton._isFocused ? Theme.colorPrimary : Theme.colorTextDim
            border.width: root.vpx(1)

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
            Behavior on border.color {
                ColorAnimation { duration: Theme.animDurationFast }
            }

            Text {
                id: applyLabel
                anchors.centerIn: parent
                text: "Apply to retroarch.cfg"
                color: applyButton._isFocused ? Theme.colorText : Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }
            }
        }
    }

    // ── Toast overlay ─────────────────────────────────────────────────────────
    Rectangle {
        id: toastOverlay
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(60)
        }
        width: toastLabel.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(20)
        color: Theme.colorSecondary
        border.color: Theme.colorPrimary
        border.width: root.vpx(1)
        visible: hotkeysScreen._toastText.length > 0
        opacity: visible ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: hotkeysScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }

    // ── Modifier capture dialog (declared last so it renders on top) ──────────
    ModifierCaptureDialog {
        id: modifierCaptureDialog
        anchors.fill: parent
        visible: false

        onButtonCaptured: (evdev_code) => {
            if (Settings) {
                Settings.setHotkeyModifier(evdev_code)
                // Refresh config so modifier_label updates
                hotkeysScreen.config = Settings.getRetroarchHotkeyConfig()
            }
            // Focus the list directly — FocusScope needs a focused child to receive Keys events
            hotkeysList.forceActiveFocus()
        }

        onButtonCleared: {
            if (Settings) {
                Settings.clearHotkeyModifier()
                hotkeysScreen.config = Settings.getRetroarchHotkeyConfig()
            }
            hotkeysList.forceActiveFocus()
        }

        onCancelled: {
            hotkeysList.forceActiveFocus()
        }
    }

    // ── Hotkey capture dialog (for hotkey rows 1–N) ───────────────────────────
    ModifierCaptureDialog {
        id: hotkeyCaptureDialog
        anchors.fill: parent
        visible: false
        allowAxisInput: true

        onButtonCaptured: (evdev_code) => {
            if (Settings && hotkeysScreen._captureTargetAction !== "") {
                Settings.setHotkeyActionByEvdev(hotkeysScreen._captureTargetAction, evdev_code)
                hotkeysScreen.config = Settings.getRetroarchHotkeyConfig()
            }
            hotkeysList.forceActiveFocus()
        }

        onAxisCaptured: (evdev_code, value) => {
            if (Settings && hotkeysScreen._captureTargetAction !== "") {
                Settings.setHotkeyActionByAxis(hotkeysScreen._captureTargetAction, evdev_code, value)
                hotkeysScreen.config = Settings.getRetroarchHotkeyConfig()
            }
            hotkeysList.forceActiveFocus()
        }

        onButtonCleared: {
            if (Settings && hotkeysScreen._captureTargetAction !== "") {
                Settings.clearHotkeyAction(hotkeysScreen._captureTargetAction)
                hotkeysScreen.config = Settings.getRetroarchHotkeyConfig()
            }
            hotkeysList.forceActiveFocus()
        }

        onCancelled: {
            hotkeysList.forceActiveFocus()
        }
    }

    // ── Reset focused row when screen opens ───────────────────────────────────
    Component.onCompleted: {
        hotkeysScreen._focusedRow = 0
    }
}
