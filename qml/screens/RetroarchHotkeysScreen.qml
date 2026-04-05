import QtQuick
import ".."
import "../components"

// RetroArch Hotkeys sub-screen — shows the hotkey modifier and the
// HTPC-action → RetroArch-hotkey mapping derived from the controller mapping.
//
// Usage (from SettingsScreen.qml):
//   RetroarchHotkeysScreen {
//       id: retroarchHotkeysScreen
//       anchors.fill: parent
//       visible: false
//   }
//
//   function showRetroarchHotkeys() {
//       retroarchHotkeysScreen.config = settings ? settings.getRetroarchHotkeyConfig() : {}
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
    //   { modifier_evdev, modifier_sdl, modifier_label, mapping, htpc_actions, cfg_path }
    property var config: ({})

    // Emit when B (Escape) is pressed.
    signal back()

    // ── Internal state ────────────────────────────────────────────────────────

    // Total focusable rows: modifier row + htpc_actions rows + apply button
    property int _rowCount: {
        var actions = (config && config.htpc_actions) ? config.htpc_actions.length : 0
        return 1 + actions + 1
    }

    // Currently focused row index (0 = modifier, 1..N = htpc actions, N+1 = apply)
    property int _focusedRow: 0

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
        } else if (keys.isAccept(event) || event.key === Qt.Key_Right) {
            event.accepted = true
            _activateFocused()
        } else if (keys.isCancel(event)) {
            event.accepted = true
            hotkeysScreen.back()
        }
    }

    function _scrollToFocused() {
        // Scroll the list so the focused row is visible.
        // The apply button is outside the scroll view, so only scroll for rows 0..N.
        var actions = (config && config.htpc_actions) ? config.htpc_actions.length : 0
        if (hotkeysScreen._focusedRow <= actions) {
            hotkeysList.positionViewAtIndex(hotkeysScreen._focusedRow, ListView.Contain)
        }
    }

    function _activateFocused() {
        var actions = (config && config.htpc_actions) ? config.htpc_actions.length : 0
        if (hotkeysScreen._focusedRow === 0) {
            // Modifier row — open capture dialog
            modifierCaptureDialog.visible = true
            modifierCaptureDialog.forceActiveFocus()
        } else if (hotkeysScreen._focusedRow === actions + 1) {
            // Apply button
            _applyHotkeys()
        }
        // Hotkey rows (1..N) are read-only in V1 — no action
    }

    function _applyHotkeys() {
        if (!settings) {
            hotkeysScreen._showToast("Error — check logs")
            return
        }
        try {
            settings.applyRetroarchHotkeys()
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
                text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
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
            bottom: applyButton.top
            topMargin: root.vpx(8)
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }

        clip: true
        interactive: false  // We handle scrolling manually via positionViewAtIndex
        highlightMoveDuration: Theme.animDurationFast

        // Model: modifier row (index 0) + one entry per htpc_action
        model: {
            var rows = [{ _type: "modifier" }]
            var actions = (hotkeysScreen.config && hotkeysScreen.config.htpc_actions)
                ? hotkeysScreen.config.htpc_actions : []
            for (var i = 0; i < actions.length; i++) {
                rows.push({ _type: "hotkey", _data: actions[i] })
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
            readonly property bool _isDimmed: {
                if (_isModifier) return false
                return _hotkeyData ? (_hotkeyData.sdl_index === null || _hotkeyData.sdl_index === undefined) : true
            }

            // ── Row highlight ─────────────────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateItem._isFocused ? 0.6 : 0.0
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

                // Left column: HTPC action label (e.g. "Accept", "Cancel", "Left Trigger")
                // Derived from htpc_action by replacing underscores and title-casing.
                Text {
                    width: parent.width * 0.55
                    text: {
                        if (!delegateItem._hotkeyData) return ""
                        var a = delegateItem._hotkeyData.htpc_action || ""
                        return a.replace(/_/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase() })
                    }
                    color: delegateItem._isDimmed ? Theme.colorTextDim
                        : (delegateItem._isFocused ? Theme.colorText : Theme.colorTextDim)
                    opacity: delegateItem._isDimmed ? 0.5 : 1.0
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)

                    Behavior on color {
                        ColorAnimation { duration: Theme.animDurationFast }
                    }
                }

                // Right column: hotkey action label (e.g. "Menu Toggle", "Exit Emulator")
                // The backend provides this as `label` (derived from hotkey_action).
                Text {
                    width: parent.width * 0.45
                    text: delegateItem._hotkeyData ? (delegateItem._hotkeyData.label || "") : ""
                    color: delegateItem._isDimmed ? Theme.colorTextDim
                        : (delegateItem._isFocused ? Theme.colorText : Theme.colorTextDim)
                    opacity: delegateItem._isDimmed ? 0.5 : 1.0
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

        readonly property bool _isFocused: {
            var actions = (hotkeysScreen.config && hotkeysScreen.config.htpc_actions)
                ? hotkeysScreen.config.htpc_actions.length : 0
            return hotkeysScreen._focusedRow === actions + 1
        }

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
            if (settings) {
                settings.setHotkeyModifier(evdev_code)
                // Refresh config so modifier_label updates
                hotkeysScreen.config = settings.getRetroarchHotkeyConfig()
            }
            // Focus the list directly — FocusScope needs a focused child to receive Keys events
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
