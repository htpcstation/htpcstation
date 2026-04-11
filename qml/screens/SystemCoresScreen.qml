import QtQuick
import ".."
import "../components"
import HTPCBackend 1.0

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
//       systemCoresScreen.systems = Settings.getSystemsList()
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

    // Compatible+installed cores for the currently selected row — updated on row change and on open.
    property var _currentRowCores: []

    // Core overrides applied during this session: folderName → core filename.
    // Delegates read this first so the systems array never needs to be reassigned during cycling.
    property var _corePatch: ({})

    // Emit when B (Escape) is pressed.
    signal back()

    // When the systems list is set (screen opens), reset patch and update cores for row 0.
    onSystemsChanged: {
        systemCoresScreen._corePatch = ({})
        var sys = systemsList.currentIndex >= 0
            ? systemCoresScreen.systems[systemsList.currentIndex]
            : null
        systemCoresScreen._currentRowCores = (sys && Settings)
            ? Settings.getAvailableCores(sys.folderName) : []
    }

    // Update _currentRowCores when the selected row changes.
    Connections {
        target: systemsList
        function onCurrentIndexChanged() {
            var sys = systemsList.currentIndex >= 0
                ? systemCoresScreen.systems[systemsList.currentIndex]
                : null
            systemCoresScreen._currentRowCores = (sys && Settings)
                ? Settings.getAvailableCores(sys.folderName) : []
        }
    }

    // ── Cycle core by delta (+1 forward, -1 backward) ─────────────────────────
    function _cycleCore(delta) {
        var cores = systemCoresScreen._currentRowCores
        if (cores.length === 0) {
            systemCoresScreen._showToast("No cores installed — run install.sh")
            return
        }
        var sys = systemCoresScreen.systems[systemsList.currentIndex]
        if (!sys) return
        // Use patched core if one exists for this row, otherwise use the original
        var current = systemCoresScreen._corePatch[sys.folderName] || sys.core
        var idx = cores.indexOf(current)
        var next
        if (idx < 0) {
            next = delta > 0 ? 0 : cores.length - 1
        } else {
            next = (idx + delta + cores.length) % cores.length
        }
        var newCore = cores[next]
        if (Settings) Settings.setSystemCore(sys.folderName, newCore)
        // Assign a new object so QML detects the change and re-evaluates delegate bindings
        var patch = Object.assign({}, systemCoresScreen._corePatch)
        patch[sys.folderName] = newCore
        systemCoresScreen._corePatch = patch
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
        } else if (event.key === Qt.Key_Right || KeyHandler.isAccept(event)) {
            event.accepted = true
            systemCoresScreen._cycleCore(1)
        } else if (KeyHandler.isCancel(event)) {
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
                text: systemCoresScreen._currentRowCores.length > 0
                    ? "◀▶  Change core"
                    : "No cores installed"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: KeyHandler.useGamepadLabels ? KeyHandler.cancelLabel + "  Back" : "Esc  Back"
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
        text: "No systems found. Set your ROM directory in Retro Games Settings."
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
                        var core = systemCoresScreen._corePatch[delegateItem.systemData.folderName]
                            || delegateItem.systemData.core
                        if (systemCoresScreen._currentRowCores.length > 0 && delegateItem.isCurrentRow)
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
