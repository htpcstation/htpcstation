import QtQuick
import ".."

// Reusable focus-tint overlay for grid cell delegates.
// Set active to true when the cell is the current item AND the grid has focus.
Rectangle {
    property bool active: false

    anchors.fill: parent
    radius: parent.radius
    color: Theme.colorPrimary
    opacity: active ? 0.15 : 0.0

    Behavior on opacity {
        NumberAnimation { duration: Theme.animDurationFast }
    }
}
