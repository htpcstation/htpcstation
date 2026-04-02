import QtQuick
import ".."

// Modal quit confirmation dialog.
// Place at the window level (above HomeScreen) so it overlays everything.
//
// Usage:
//   QuitDialog {
//       id: quitDialog
//       onQuit:   Qt.quit()
//       onCancel: { visible = false; homeScreen.forceActiveFocus() }
//   }
//
// When visible is set to true, call forceActiveFocus() on this item so the
// FocusScope captures all key input.
FocusScope {
    id: quitDialog

    // Only process input when this dialog is active.
    enabled: focus

    // Emitted when the user confirms quit.
    signal quit()
    // Emitted when the user cancels.
    signal cancel()

    // Track which button is focused: 0 = Quit, 1 = Cancel
    property int _selectedButton: 0

    // Reset selection whenever the dialog becomes visible.
    onVisibleChanged: {
        if (visible) {
            _selectedButton = 0
        }
    }

    // ── Dark semi-transparent backdrop ───────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorImagePlaceholder
        opacity: 0.7
    }

    // ── Dialog box ───────────────────────────────────────────────────────────
    Rectangle {
        id: dialogBox

        anchors.centerIn: parent
        width: root.vpx(400)
        height: root.vpx(200)

        color: Theme.colorSecondary
        radius: root.vpx(8)

        // ── Prompt text ──────────────────────────────────────────────────────
        Text {
            id: promptText
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: parent.top
                topMargin: root.vpx(40)
            }
            text: "Quit HTPC Station?"
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            color: Theme.colorText
        }

        // ── Button row ───────────────────────────────────────────────────────
        Row {
            id: buttonRow
            anchors {
                horizontalCenter: parent.horizontalCenter
                bottom: parent.bottom
                bottomMargin: root.vpx(32)
            }
            spacing: root.vpx(24)

            // "Quit" button
            FocusScope {
                id: quitButton
                width: root.vpx(120)
                height: root.vpx(44)

                // This button is "focused" when _selectedButton == 0
                readonly property bool isActive: quitDialog._selectedButton === 0

                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorPrimary
                    radius: root.vpx(Theme.focusRingRadius)
                    opacity: quitButton.isActive ? 1.0 : 0.5

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }

                    Text {
                        anchors.centerIn: parent
                        text: "Quit"
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        color: Theme.colorText
                    }
                }

                FocusRing {
                    visible: quitButton.isActive
                }
            }

            // "Cancel" button
            FocusScope {
                id: cancelButton
                width: root.vpx(120)
                height: root.vpx(44)

                // This button is "focused" when _selectedButton == 1
                readonly property bool isActive: quitDialog._selectedButton === 1

                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    border.color: Theme.colorTextDim
                    border.width: root.vpx(1)
                    radius: root.vpx(Theme.focusRingRadius)
                    opacity: cancelButton.isActive ? 1.0 : 0.5

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        color: Theme.colorText
                    }
                }

                FocusRing {
                    visible: cancelButton.isActive
                }
            }
        }
    }

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Left) {
            event.accepted = true
            _selectedButton = 0
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            _selectedButton = 1
        } else if (keys.isAccept(event)) {
            event.accepted = true
            if (_selectedButton === 0) {
                quitDialog.quit()
            } else {
                quitDialog.cancel()
            }
        } else if (keys.isCancel(event)) {
            event.accepted = true
            quitDialog.cancel()
        }
    }
}
