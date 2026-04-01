import QtQuick
import ".."
import "../components"

// System Cores sub-screen — lists all discovered ROM systems and lets the
// user edit the .so core filename for each one.
//
// Usage (from SettingsScreen.qml):
//   SystemCoresScreen {
//       id: systemCoresScreen
//       anchors.fill: parent
//       visible: false
//   }
//
//   function showSystemCores() {
//       systemCoresScreen.systems = settings.getSystemsList()
//       systemCoresScreen.visible = true
//       systemCoresScreen.forceActiveFocus()
//   }
//
// Do NOT use id: root — ApplicationWindow owns that id.
FocusScope {
    id: systemCoresScreen

    // Only process input when this screen is active.
    enabled: focus

    // The list of systems: [{folderName, displayName, core}]
    property var systems: []

    // Index of the row currently being edited (-1 = none)
    property int _editingIndex: -1

    // Emit when B (Escape) is pressed and no row is being edited.
    signal back()

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        // If a row is being edited, let the TextInput handle keys
        if (systemCoresScreen._editingIndex >= 0) {
            return
        }

        if (event.key === Qt.Key_Up) {
            event.accepted = true
            if (systemsList.currentIndex > 0) {
                systemsList.currentIndex -= 1
                systemsList.positionViewAtIndex(systemsList.currentIndex, ListView.Contain)
            }
        } else if (event.key === Qt.Key_Down) {
            event.accepted = true
            if (systemsList.currentIndex < systemsList.count - 1) {
                systemsList.currentIndex += 1
                systemsList.positionViewAtIndex(systemsList.currentIndex, ListView.Contain)
            }
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            event.accepted = true
            if (systemsList.count > 0) {
                systemCoresScreen._editingIndex = systemsList.currentIndex
            }
        } else if (keys.isCancel(event)) {
            event.accepted = true
            systemCoresScreen.back()
        }
    }

    // ── Dark background ───────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.colorBackground
    }

    // ── Header bar ────────────────────────────────────────────────────────────
    Rectangle {
        id: headerBar

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "◀  System Cores"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        Text {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Empty state ───────────────────────────────────────────────────────────
    Text {
        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(48)
        }
        visible: systemCoresScreen.systems.length === 0
        text: "No systems found. Set your ROM directory in Retro Games settings."
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    // ── Systems list ──────────────────────────────────────────────────────────
    ListView {
        id: systemsList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(8)
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }

        model: systemCoresScreen.systems
        clip: true
        visible: systemCoresScreen.systems.length > 0
        currentIndex: 0
        highlightMoveDuration: Theme.animDurationFast

        delegate: Item {
            id: delegateItem

            width: systemsList.width
            height: root.vpx(56)

            readonly property var systemData: modelData
            readonly property bool isCurrentRow: systemsList.currentIndex === index
            readonly property bool isEditing: systemCoresScreen._editingIndex === index

            // ── Highlight for current row ─────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateItem.isCurrentRow && !delegateItem.isEditing ? 0.4 : 0.0

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Normal display row ────────────────────────────────────────────
            Row {
                id: displayRow
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(8)
                    rightMargin: root.vpx(8)
                }
                visible: !delegateItem.isEditing

                Text {
                    width: parent.width * 0.55
                    text: delegateItem.systemData ? delegateItem.systemData.displayName : ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                }

                Text {
                    width: parent.width * 0.45
                    text: delegateItem.systemData ? delegateItem.systemData.core : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
                }
            }

            // ── Inline edit row ───────────────────────────────────────────────
            Item {
                id: editRow
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(8)
                    rightMargin: root.vpx(8)
                }
                height: root.vpx(40)
                visible: delegateItem.isEditing

                // Label on the left
                Text {
                    id: editLabel
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    width: parent.width * 0.45
                    text: delegateItem.systemData ? delegateItem.systemData.displayName : ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                }

                // Text input on the right
                Rectangle {
                    id: inputBg
                    anchors {
                        left: editLabel.right
                        right: parent.right
                        leftMargin: root.vpx(8)
                        verticalCenter: parent.verticalCenter
                    }
                    height: root.vpx(36)
                    color: Qt.darker(Theme.colorSecondary, 1.3)
                    border.color: Theme.colorPrimary
                    border.width: root.vpx(1)
                    radius: root.vpx(4)

                    TextInput {
                        id: coreInput
                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                            leftMargin: root.vpx(8)
                            rightMargin: root.vpx(8)
                        }
                        text: delegateItem.systemData ? delegateItem.systemData.core : ""
                        color: Theme.colorText
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        selectByMouse: true
                        activeFocusOnTab: false
                        clip: true

                        // Focus the input when the edit row becomes visible
                        onVisibleChanged: {
                            if (visible) {
                                coreInput.forceActiveFocus()
                                coreInput.selectAll()
                            }
                        }

                        Keys.onReturnPressed: {
                            var newCore = coreInput.text.trim()
                            if (settings && delegateItem.systemData) {
                                settings.setSystemCore(delegateItem.systemData.folderName, newCore)
                                // Update the local model so the display row reflects the change
                                var updated = systemCoresScreen.systems.slice()
                                updated[index] = {
                                    folderName: delegateItem.systemData.folderName,
                                    displayName: delegateItem.systemData.displayName,
                                    core: newCore
                                }
                                systemCoresScreen.systems = updated
                            }
                            systemCoresScreen._editingIndex = -1
                            systemCoresScreen._showToast("Saved")
                            systemCoresScreen.forceActiveFocus()
                        }

                        Keys.onEscapePressed: {
                            systemCoresScreen._editingIndex = -1
                            systemCoresScreen.forceActiveFocus()
                        }
                    }
                }
            }

            // Separator line
            Rectangle {
                anchors {
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }
        }
    }

    // ── Toast notification ────────────────────────────────────────────────────
    property string _toastText: ""

    Timer {
        id: toastTimer
        interval: 2500
        repeat: false
        onTriggered: systemCoresScreen._toastText = ""
    }

    function _showToast(msg) {
        systemCoresScreen._toastText = msg
        toastTimer.restart()
    }

    Rectangle {
        id: toastOverlay
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: root.vpx(60)
        }
        width: toastLabel.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(20)
        color: Theme.colorSecondary
        border.color: Theme.colorPrimary
        border.width: root.vpx(1)
        visible: systemCoresScreen._toastText.length > 0
        opacity: visible ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: systemCoresScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }
}
