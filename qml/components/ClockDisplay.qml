import QtQuick
import ".."

// Displays the current time in HH:MM (24-hour) format.
// Pure display — no focus, no interaction.
// Positioned by the parent; updates every minute via a Timer.
Text {
    id: clockDisplay

    // No focus or interaction
    focus: false
    activeFocusOnTab: false

    text: Qt.formatTime(new Date(), "HH:mm")

    font.family: Theme.fontFamily
    font.pixelSize: root.vpx(Theme.fontSizeBody)
    color: Theme.colorText

    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            var t = Qt.formatTime(new Date(), "HH:mm")
            if (clockDisplay.text !== t) clockDisplay.text = t
        }
    }
}
