import QtQuick
import QtQuick.Window
import ".."

Window {
    id: skipIntroOverlay

    // Called by HomeScreen when markers arrive
    function showForIntro(introStartMs, introEndMs) {
        if (introEndMs <= 0) return
        _introEndMs = introEndMs
        _introStartMs = introStartMs
        skipIntroOverlay.show()
        skipIntroOverlay.raise()
        skipBtn.forceActiveFocus()
    }

    function hideOverlay() {
        skipIntroOverlay.hide()
    }

    property int _introStartMs: 0
    property int _introEndMs: 0

    flags: Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
    color: "transparent"
    width: 220
    height: 60
    // Bottom-right corner
    x: Screen.width - width - 48
    y: Screen.height - height - 80

    Rectangle {
        anchors.fill: parent
        color: Theme.colorPanelDark
        radius: 8
        opacity: 0.92

        Text {
            id: skipBtn
            anchors.centerIn: parent
            text: "Skip Intro  \u25B6"
            color: skipBtn.activeFocus ? Theme.colorAccent : Theme.colorOverlayText
            font.pixelSize: 18
            font.bold: true
            focus: true

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Space) {
                    event.accepted = true
                    plex.skipIntro()
                    skipIntroOverlay.hide()
                } else if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    skipIntroOverlay.hide()
                }
            }
        }
    }
}
