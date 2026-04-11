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

    // Guard to prevent the mapping dialog from reopening immediately
    // after closing (the A-press that saves can propagate to the settings
    // screen and re-trigger the "Map Controller" button).
    property bool _mappingDialogCooldown: false

    // Show the controller mapping dialog (called by SettingsScreen).
    function showControllerMapping() {
        if (_mappingDialogCooldown) return
        controllerMappingLoader.active = true
        // forceActiveFocus() and start() are called in Loader.onLoaded
        // (item may not be ready synchronously after setting active).
    }

    // When the window regains focus after Alt+Tab, re-deliver focus to the
    // last active item. Without this, FocusScopes with `enabled: focus` can
    // end up with activeFocus but no focused child, silently eating all input.
    onActiveChanged: {
        if (active) {
            var item = root.activeFocusItem
            if (item) item.forceActiveFocus()
            else homeScreen.forceActiveFocus()
        }
    }

    HomeScreen {
        id: homeScreen
        anchors.fill: parent
        focus: true

        onRequestQuit: {
            _savedFocusItem = root.activeFocusItem
            quitDialogLoader.active = true
            // forceActiveFocus() is called in quitDialogLoader.onLoaded
        }

        onShowControllerMapping: root.showControllerMapping()
    }

    Loader {
        id: quitDialogLoader
        anchors.fill: parent
        active: false
        sourceComponent: QuitDialog {
            anchors.fill: parent

            onQuit: Qt.quit()

            onCancel: {
                quitDialogLoader.active = false
                if (_savedFocusItem) _savedFocusItem.forceActiveFocus()
                else homeScreen.forceActiveFocus()
            }
        }

        onLoaded: item.forceActiveFocus()
    }

    Loader {
        id: controllerMappingLoader
        anchors.fill: parent
        active: false
        sourceComponent: ControllerMappingDialog {
            anchors.fill: parent

            onClosed: {
                root._mappingDialogCooldown = true
                mappingCloseTimer.restart()
                controllerMappingLoader.active = false
            }
        }

        onLoaded: {
            item.forceActiveFocus()
            item.start()
        }
    }

    Timer {
        id: mappingCloseTimer
        interval: 500
        repeat: false
        onTriggered: {
            root._mappingDialogCooldown = false
            homeScreen.forceActiveFocus()
        }
    }
}
