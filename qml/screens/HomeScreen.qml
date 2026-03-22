import QtQuick
import ".."
import "../components"

// Home screen with top-level section navigation (Games / Watch / Settings).
//
// Focus flow:
//   App start → HomeScreen → tabBar → first tab (Games) has activeFocus
//   Left/Right  — move between tabs
//   LB/RB       — move between tabs (works even when focus is in content area)
//   A (Return)  — move focus into content area
//   B (Escape)  — return focus to tab bar (emitted by child screens via back())
//   Start/F10   — emit requestQuit() to open the quit dialog
//   Escape on tab bar — emit requestQuit() to open the quit dialog
FocusScope {
    id: homeScreen

    // Only process input when this screen is active.
    enabled: focus

    // Emitted when the user requests to quit (Start button or Escape on tab bar).
    signal requestQuit()

    // Index of the currently selected (displayed) tab.
    property int currentTab: 0

    readonly property var tabNames: ["Retro Games", "PC Games", "Watch", "Settings"]
    readonly property var tabSources: [
        "RetroGamesScreen.qml",
        "PcGamesScreen.qml",
        "WatchScreen.qml",
        "SettingsScreen.qml"
    ]

    // Set to true when LB/RB is pressed while focus is in the content area,
    // so onLoaded can give focus to the newly loaded content item.
    property bool _focusContentOnLoad: false

    // Intercept LB/RB and Start at the HomeScreen level so they work even
    // when focus is inside the content area.
    Keys.onPressed: (event) => {
        if (keys.isMenu(event)) {
            event.accepted = true
            homeScreen.requestQuit()
        } else if (keys.isPrevTab(event)) {
            event.accepted = true
            if (currentTab > 0) {
                // Remember whether focus was in the content area before switching.
                _focusContentOnLoad = contentLoader.item !== null && contentLoader.item.activeFocus
                currentTab--
                if (!_focusContentOnLoad) {
                    tabRepeater.itemAt(currentTab).forceActiveFocus()
                }
            }
        } else if (keys.isNextTab(event)) {
            event.accepted = true
            if (currentTab < tabNames.length - 1) {
                _focusContentOnLoad = contentLoader.item !== null && contentLoader.item.activeFocus
                currentTab++
                if (!_focusContentOnLoad) {
                    tabRepeater.itemAt(currentTab).forceActiveFocus()
                }
            }
        }
    }

    // Trigger slide-in animation whenever the tab changes.
    onCurrentTabChanged: {
        contentLoader.x = contentArea.width
        slideInAnimation.start()
    }

    // ── Tab bar ──────────────────────────────────────────────────────────────
    Row {
        id: tabBar
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: root.vpx(56)
        spacing: root.vpx(8)

        focus: true

        Repeater {
            id: tabRepeater
            model: homeScreen.tabNames

            // Each tab is a FocusScope so it can own the focus ring.
            FocusScope {
                id: tabItem

                readonly property int tabIndex: index
                readonly property bool isSelected: homeScreen.currentTab === index

                width: root.vpx(140)
                height: tabBar.height

                // Navigate between tabs with Left/Right.
                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Left) {
                        event.accepted = true
                        if (homeScreen.currentTab > 0) {
                            homeScreen.currentTab--
                            tabRepeater.itemAt(homeScreen.currentTab).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Right) {
                        event.accepted = true
                        if (homeScreen.currentTab < homeScreen.tabNames.length - 1) {
                            homeScreen.currentTab++
                            tabRepeater.itemAt(homeScreen.currentTab).forceActiveFocus()
                        }
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (contentLoader.item) {
                            contentLoader.item.forceActiveFocus()
                        }
                    } else if (keys.isAccept(event)) {
                        event.accepted = true
                        // Move focus into the content area.
                        if (contentLoader.item) {
                            contentLoader.item.forceActiveFocus()
                        }
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        // Escape on the tab bar → open quit dialog.
                        homeScreen.requestQuit()
                    }
                }

                // Tab label
                Text {
                    id: tabLabel
                    anchors {
                        horizontalCenter: parent.horizontalCenter
                        verticalCenter: parent.verticalCenter
                        verticalCenterOffset: -root.vpx(4)
                    }
                    text: modelData
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    color: tabItem.activeFocus ? Theme.colorText : Theme.colorTextDim
                }

                // Active-tab underline indicator
                Rectangle {
                    anchors {
                        bottom: parent.bottom
                        horizontalCenter: parent.horizontalCenter
                    }
                    width: tabLabel.width + root.vpx(8)
                    height: root.vpx(3)
                    color: Theme.colorTabUnderline
                    visible: tabItem.isSelected

                    Behavior on width {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                FocusRing {}
            }
        }
    }

    // ── Clock display ─────────────────────────────────────────────────────────
    ClockDisplay {
        id: clockDisplay
        anchors {
            right: parent.right
            rightMargin: root.vpx(16)
            verticalCenter: tabBar.verticalCenter
        }
    }

    // ── Network status indicator ──────────────────────────────────────────────
    NetworkIndicator {
        id: networkIndicator
        anchors {
            right: clockDisplay.left
            rightMargin: root.vpx(12)
            verticalCenter: tabBar.verticalCenter
        }
        online: networkMonitor ? networkMonitor.online : true
        visible: settings ? settings.showNetworkIndicator : true
    }

    // Thin separator line below the tab bar
    Rectangle {
        id: separator
        anchors {
            top: tabBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(1)
        color: Theme.colorTextDim
        opacity: 0.3
    }

    // ── Content area ─────────────────────────────────────────────────────────
    Item {
        id: contentArea
        anchors {
            top: separator.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        clip: true

        Loader {
            id: contentLoader
            width: parent.width
            height: parent.height
            asynchronous: false
            source: homeScreen.tabSources[homeScreen.currentTab]

            // When the loaded item changes, wire up its back() signal and
            // give focus to the new content if LB/RB was pressed from content.
            onLoaded: {
                if (item) {
                    item.back.connect(returnFocusToTabBar)
                    if (homeScreen._focusContentOnLoad) {
                        homeScreen._focusContentOnLoad = false
                        item.forceActiveFocus()
                    }
                }
            }
        }

        // Slide-in animation: slides the loader from off-screen right to x=0.
        NumberAnimation {
            id: slideInAnimation
            target: contentLoader
            property: "x"
            to: 0
            duration: Theme.animDurationNormal
            easing.type: Easing.OutQuad
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function returnFocusToTabBar() {
        tabRepeater.itemAt(homeScreen.currentTab).forceActiveFocus()
    }

    // On startup, give focus to the first tab.
    Component.onCompleted: {
        tabRepeater.itemAt(0).forceActiveFocus()
    }
}
