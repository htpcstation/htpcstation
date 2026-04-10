import QtQuick
import ".."

// Reusable selection row for settings.
//
// A (Return) → cycles to the next option in the list and emits selected(id).
// Shows label on left, currentValue on right (same layout as SettingTextInput
// in display mode).
// If options is empty, shows "None available" and ignores A button.
FocusScope {
    id: selectRoot

    property string label: ""
    property string currentValue: ""
    property var options: []
    // Function that returns fresh options on demand (called on each A press)
    property var optionsProvider: null

    signal selected(var id, string label)

    implicitHeight: root.vpx(56)

    // ── Background highlight ──────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorSecondary
        opacity: selectRoot.activeFocus ? 0.8 : 0.0
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
        text: selectRoot.label
        color: selectRoot.activeFocus ? Theme.colorText : Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)

        Behavior on color {
            ColorAnimation { duration: Theme.animDurationFast }
        }
    }

    // ── Current value display ─────────────────────────────────────────────────
    Text {
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: parent.verticalCenter
        }
        text: selectRoot.currentValue.length > 0
            ? selectRoot.currentValue
            : "Not selected"
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
        elide: Text.ElideMiddle
        width: parent.width * 0.55
        horizontalAlignment: Text.AlignRight
    }

    // ── Focus ring ────────────────────────────────────────────────────────────
    FocusRing {}

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            // Fetch fresh options on each press (API data may have changed)
            var opts = selectRoot.optionsProvider
                ? selectRoot.optionsProvider()
                : selectRoot.options
            if (!opts || opts.length === 0) return

            // Find the index of the currently selected option by matching currentValue
            var currentIdx = -1
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].label === selectRoot.currentValue) {
                    currentIdx = i
                    break
                }
            }
            // Cycle to next option (wrap around)
            var nextIdx = (currentIdx + 1) % opts.length
            selectRoot.selected(opts[nextIdx].id, opts[nextIdx].label)
        }
    }
}
