import QtQuick
import ".."
import HTPCBackend 1.0

// Reusable text input row for Settings (paths, URLs, commands).
//
// Normal mode: shows label on left, value on right (masked if masked=true).
// Edit mode (entered via A/Return): value becomes editable TextInput.
//   Enter  — confirms new value, emits valueChanged, exits edit mode
//   Escape — cancels edit, restores original value, exits edit mode
//
// Place inside a ListView delegate; the parent ListView should give this
// item focus when it is the current row.
FocusScope {
    id: textInputRoot

    property string label: ""
    property string value: ""
    property bool masked: false
    property bool editing: false

    signal valueEdited(string newValue)

    // Internal: the text being edited (may differ from value until confirmed)
    property string _editText: ""

    // Row height: taller when editing to accommodate the hint text
    implicitHeight: editing
        ? root.vpx(72)
        : root.vpx(56)

    Behavior on implicitHeight {
        NumberAnimation { duration: Theme.animDurationFast }
    }

    // ── Background highlight ──────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: textInputRoot.activeFocus ? 0.8 : 0.0
        radius: root.vpx(Theme.focusRingRadius)

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Label ─────────────────────────────────────────────────────────────────
    Text {
        id: labelText
        anchors {
            left: parent.left
            leftMargin: root.vpx(16)
            top: parent.top
            topMargin: root.vpx(16)
        }
        text: textInputRoot.label
        color: textInputRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Value display (normal mode) ───────────────────────────────────────────
    Text {
        id: valueDisplay
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            top: parent.top
            topMargin: root.vpx(16)
        }
        visible: !textInputRoot.editing
        text: textInputRoot.masked
            ? "•".repeat(Math.min(textInputRoot.value.length, 16))
            : (textInputRoot.value.length > 0 ? textInputRoot.value : "—")
        color: textInputRoot.value.length > 0 ? Theme.colorTextDim : Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
        elide: Text.ElideMiddle
        width: parent.width * 0.55
        horizontalAlignment: Text.AlignRight
    }

    // ── TextInput (edit mode) ─────────────────────────────────────────────────
    Rectangle {
        id: inputBackground
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            top: parent.top
            topMargin: root.vpx(10)
        }
        width: parent.width * 0.55
        height: root.vpx(36)
        visible: textInputRoot.editing
        color: Theme.colorBackground
        border.color: Theme.colorPrimary
        border.width: root.vpx(1)
        radius: root.vpx(Theme.focusRingRadius)

        TextInput {
            id: textField
            anchors {
                fill: parent
                leftMargin: root.vpx(8)
                rightMargin: root.vpx(8)
                topMargin: root.vpx(4)
                bottomMargin: root.vpx(4)
            }
            text: textInputRoot._editText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            clip: true
            focus: textInputRoot.editing

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    event.accepted = true
                    var newValue = textField.text
                    textInputRoot.editing = false
                    textInputRoot.valueEdited(newValue)
                } else if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    textInputRoot.editing = false
                    // Restore original value (don't emit)
                }
            }
        }
    }

    // ── Edit hint ─────────────────────────────────────────────────────────────
    Text {
        id: editHint
        anchors {
            left: parent.left
            leftMargin: root.vpx(16)
            bottom: parent.bottom
            bottomMargin: root.vpx(6)
        }
        visible: textInputRoot.editing
        text: "Type to edit · Enter to confirm · Esc to cancel"
        color: Theme.colorPrimary
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeSmall)
        opacity: 0.9
    }

    // ── Focus ring ────────────────────────────────────────────────────────────
    FocusRing {
        visible: textInputRoot.activeFocus && !textInputRoot.editing
    }

    // ── Key handling (normal mode) ────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (!textInputRoot.editing && KeyHandler.isAccept(event)) {
            event.accepted = true
            textInputRoot._editText = textInputRoot.value
            textInputRoot.editing = true
            textField.forceActiveFocus()
            textField.selectAll()
        } else if (!textInputRoot.editing && KeyHandler.isCancel(event)) {
            // Let the parent ListView handle cancel (back navigation)
        }
    }

    // When editing ends, return focus to the FocusScope so key navigation works
    onEditingChanged: {
        if (!editing) {
            textInputRoot.forceActiveFocus()
        }
    }
}
