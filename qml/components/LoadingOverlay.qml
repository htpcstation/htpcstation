// LoadingOverlay.qml
// Full-screen overlay that appears only if `loading` stays true longer than
// `delay` ms.  Fades in and out so it never flashes for quick operations.
//
// Usage:
//   LoadingOverlay { loading: someBackend.scanning }
//   LoadingOverlay { loading: _myLoadingFlag; delay: 500 }

import QtQuick
import ".."

Item {
    id: loadingOverlay
    anchors.fill: parent
    z: 100

    property bool loading: false
    property int  delay: Theme.loadingOverlayDelay

    // Internal: only true after delay fires
    property bool _visible: false

    Timer {
        id: delayTimer
        interval: loadingOverlay.delay
        running: false
        onTriggered: loadingOverlay._visible = true
    }

    onLoadingChanged: {
        if (loading) {
            _visible = false
            delayTimer.start()
        } else {
            delayTimer.stop()
            _visible = false
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.colorBackground
        opacity: loadingOverlay._visible ? 0.95 : 0.0
        // visible: false when fully transparent so it doesn't eat input
        visible: opacity > 0

        Behavior on opacity {
            NumberAnimation { duration: 150; easing.type: Easing.InOutQuad }
        }

        Text {
            anchors.centerIn: parent
            text: "Loading..."
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }
}
