import QtQuick
import ".."
import "../components"

// System Cores sub-screen — lists all discovered ROM systems and lets the
// user cycle through installed .so cores for each one using Left/Right arrows.
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
//       systemCoresScreen._availableCores = settings.getAvailableCores()
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

    // Cached list of installed cores — populated once on show, refreshed on coresDirectoryChanged
    property var _availableCores: []

    // Emit when B (Escape) is pressed.
    signal back()

    // ── Cycle core by delta (+1 forward, -1 backward) ─────────────────────────
    function _cycleCore(delta) {
        var cores = systemCoresScreen._availableCores
        if (cores.length === 0) {
            systemCoresScreen._showToast("No cores installed — run install.sh")
            return
        }
        var sys = systemCoresScreen.systems[systemsList.currentIndex]
        if (!sys) return
        var current = sys.core
        var idx = cores.indexOf(current)
        // If current core not in list, delta > 0 → go to index 0, delta < 0 → go to last
        var next
        if (idx < 0) {
            next = delta > 0 ? 0 : cores.length - 1
        } else {
            next = (idx + delta + cores.length) % cores.length
        }
        var newCore = cores[next]
        if (settings) settings.setSystemCore(sys.folderName, newCore)
        // Update local model
        var updated = systemCoresScreen.systems.slice()
        updated[systemsList.currentIndex] = {
            folderName: sys.folderName,
            displayName: sys.displayName,
            core: newCore
        }
        systemCoresScreen.systems = updated
    }

    // ── Key handling ──────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
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
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            systemCoresScreen._cycleCore(-1)
        } else if (event.key === Qt.Key_Right || keys.isAccept(event)) {
            event.accepted = true
            systemCoresScreen._cycleCore(1)
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

        Row {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(16)

            Text {
                text: systemCoresScreen._availableCores.length > 0
                    ? "◀▶  Change core"
                    : "No cores installed"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
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

            // ── Highlight for current row ─────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: delegateItem.isCurrentRow ? 0.4 : 0.0

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Display row ───────────────────────────────────────────────────
            Row {
                id: displayRow
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: root.vpx(8)
                    rightMargin: root.vpx(8)
                }

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
                    text: {
                        if (!delegateItem.systemData) return ""
                        var core = delegateItem.systemData.core
                        if (systemCoresScreen._availableCores.length > 0 && delegateItem.isCurrentRow)
                            return "◀  " + core + "  ▶"
                        return core
                    }
                    color: delegateItem.isCurrentRow ? Theme.colorText : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    height: root.vpx(56)
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
