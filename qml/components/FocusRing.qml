import QtQuick
import ".."

// Reusable focus indicator. Place as a child of any focusable item;
// it anchors to fill the parent and is only visible when the parent
// has activeFocus.
Rectangle {
    anchors.fill: parent

    color: "transparent"
    border.color: Theme.colorFocusRing
    border.width: root.vpx(Theme.focusRingWidth)
    radius: root.vpx(Theme.focusRingRadius)

    visible: parent.activeFocus

    // Subtle opacity pulse when focus is gained
    opacity: 1.0
    Behavior on opacity {
        NumberAnimation { duration: Theme.animDurationFast }
    }
}
