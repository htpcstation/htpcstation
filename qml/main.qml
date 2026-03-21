import QtQuick
import QtQuick.Controls
import "."
import "screens"
import "components"

ApplicationWindow {
    id: root

    width: 1920
    height: 1080
    visible: true
    visibility: Window.FullScreen
    title: "HTPC Station"
    color: Theme.colorBackground

    // Holds the focused item before the quit dialog is shown, so focus can be
    // restored exactly if the user cancels.
    property var _savedFocusItem: null

    // Scale a value from the 1280×720 design grid to the actual window size.
    // All child QML files call root.vpx(value) or simply vpx(value) when
    // they are direct children of this window.
    function vpx(value) {
        return Math.round(value * Math.min(width / 1280.0, height / 720.0))
    }

    HomeScreen {
        id: homeScreen
        anchors.fill: parent
        focus: true

        onRequestQuit: {
            _savedFocusItem = root.activeFocusItem
            quitDialog.visible = true
            quitDialog.forceActiveFocus()
        }
    }

    QuitDialog {
        id: quitDialog
        anchors.fill: parent
        visible: false

        onQuit: Qt.quit()

        onCancel: {
            quitDialog.visible = false
            if (_savedFocusItem) _savedFocusItem.forceActiveFocus()
            else homeScreen.forceActiveFocus()
        }
    }
}
