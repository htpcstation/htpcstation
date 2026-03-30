import QtQuick
import ".."
import "../components"

// Settings screen — navigable list of settings organized into sections:
// Games, Plex, Browser, Moonlight, Controller, User Interface.
//
// Navigation:
//   Up/Down — move between setting rows (headers are skipped automatically)
//   A (Return) on text input — enter edit mode
//   A (Return) on toggle — toggle value
//   A (Return) on button — execute action
//   A (Return) on slider — enter adjust mode
//   B (Escape) — if in edit/adjust mode, exit it; otherwise emit back()
FocusScope {
    id: settingsScreen

    // Emit when B (Escape) is pressed so HomeScreen can return focus to the tab bar.
    signal back()

    // Emit to request the controller mapping dialog be shown.
    signal showControllerMapping()

    // Only process input when this screen is active.
    enabled: focus

    // ── Settings model ────────────────────────────────────────────────────────
    // Each entry specifies the type and properties of a setting row.
    // Headers are non-focusable visual separators.
    readonly property var _settingsModel: [
        { type: "header",  label: "Games" },
        { type: "text",    label: "ROMs Directory",    settingKey: "romDirectory" },
        { type: "text",    label: "RetroArch Command", settingKey: "retroarchCommand" },
        { type: "text",    label: "Cores Directory",   settingKey: "coresDirectory" },
        { type: "button",  label: "System Cores...",   action: "systemCores" },
        { type: "button",  label: "Rescan Library",    action: "rescan" },
        { type: "button",  label: "Clear Retro Games History", action: "clearRetroRecent" },
        { type: "header",  label: "Plex" },
        { type: "button",  label: "Sign in with Plex", action: "plexSignIn" },
        { type: "button",  label: "Test Connection",   action: "testPlex" },
        { type: "select",  label: "Server",            settingKey: "plexServer" },
        { type: "select",  label: "User",              settingKey: "plexUser" },
        { type: "select",  label: "Music Library",    settingKey: "musicLibrary" },
        { type: "header",  label: "Browser" },
        { type: "text",    label: "Browser Command",   settingKey: "browserCommand" },
        { type: "header",  label: "Moonlight" },
        { type: "text",    label: "Moonlight Command", settingKey: "moonlightCommand" },
        { type: "select",  label: "Host",              settingKey: "moonlightHost" },
        { type: "button",  label: "Open Moonlight",    action: "openMoonlight" },

        { type: "header",  label: "Controller" },
        { type: "select",  label: "Button Layout",    settingKey: "buttonLayout" },
        { type: "button",  label: "Map Controller",   action: "mapController" },
        { type: "button",  label: "Reset to Default", action: "resetController" },
        { type: "header",  label: "User Interface" },
        { type: "toggle",  label: "Video Snap Autoplay", settingKey: "videoSnapAutoplay" },
        { type: "slider",  label: "Video Snap Delay",    settingKey: "videoSnapDelayMs",
          min: 0, max: 5000, step: 100, suffix: "ms" },
        { type: "toggle",  label: "Network Indicator",   settingKey: "showNetworkIndicator" },
    ]

    // ── Toast notification ────────────────────────────────────────────────────
    property string _toastText: ""

    Timer {
        id: toastTimer
        interval: 2500
        repeat: false
        onTriggered: settingsScreen._toastText = ""
    }

    function _showToast(msg) {
        settingsScreen._toastText = msg
        toastTimer.restart()
    }

    // ── Helper: get current value for a setting key ───────────────────────────
    function _getValue(key) {
        if (!settings) return ""
        if (key === "romDirectory")       return settings.romDirectory
        if (key === "retroarchCommand")   return settings.retroarchCommand
        if (key === "coresDirectory")     return settings.coresDirectory
        if (key === "plexServer") {
            if (!plex) return "Not selected"
            var servers = plex.getServerList()
            for (var i = 0; i < servers.length; i++) {
                if (servers[i].id === settings.plexServerId) return servers[i].name
            }
            return "Not selected"
        }
        if (key === "plexUser") {
            if (!plex) return "Not selected"
            var users = plex.getHomeUsers()
            for (var j = 0; j < users.length; j++) {
                if (users[j].id == settings.plexUserId) return users[j].title
            }
            return "Not selected"
        }
        if (key === "musicLibrary") {
            if (!plex) return "Not selected"
            var musicLibs = plex.getMusicLibraries()
            for (var m = 0; m < musicLibs.length; m++) {
                if (musicLibs[m].id === settings.musicLibraryKey) return musicLibs[m].label
            }
            return "Not selected"
        }
        if (key === "browserCommand")     return settings.browserCommand
        if (key === "moonlightCommand")   return settings.moonlightCommand
        if (key === "moonlightHost") {
            if (!moonlight) return "Not selected"
            var hosts = settings.getHostsList()
            for (var k = 0; k < hosts.length; k++) {
                if (hosts[k].id === settings.moonlightHostUuid) return hosts[k].label
            }
            return "Not selected"
        }
        if (key === "videoSnapAutoplay")      return settings.videoSnapAutoplay
        if (key === "videoSnapDelayMs")       return settings.videoSnapDelayMs
        if (key === "showNetworkIndicator")   return settings.showNetworkIndicator
        if (key === "buttonLayout") {
            return settings.buttonLayout === "alternate" ? "Alternate (A=South)" : "Standard (A=East)"
        }
        return ""
    }

    // ── Helper: call the appropriate setter ───────────────────────────────────
    function _setValue(key, value) {
        if (!settings) return
        if (key === "romDirectory")       settings.setRomDirectory(value)
        else if (key === "retroarchCommand")   settings.setRetroarchCommand(value)
        else if (key === "coresDirectory")     settings.setCoresDirectory(value)
        else if (key === "plexServer") {
            if (plex) plex.selectServer(value)
            settings.setPlexServerId(value)
        }
        else if (key === "plexUser") {
            if (plex) plex.selectUser(parseInt(value))
            settings.setPlexUserId(parseInt(value))
        }
        else if (key === "browserCommand")     settings.setBrowserCommand(value)
        else if (key === "moonlightCommand")   settings.setMoonlightCommand(value)
        else if (key === "moonlightHost")      settings.setMoonlightHostUuid(value)
        else if (key === "musicLibrary")       settings.setMusicLibraryKey(value)
        else if (key === "videoSnapAutoplay")      settings.setVideoSnapAutoplay(value)
        else if (key === "videoSnapDelayMs")       settings.setVideoSnapDelayMs(value)
        else if (key === "showNetworkIndicator")   settings.setShowNetworkIndicator(value)
        else if (key === "buttonLayout")           settings.setButtonLayout(value)
    }

    // ── Focus routing ─────────────────────────────────────────────────────────
    onActiveFocusChanged: {
        if (activeFocus) {
            // Route focus to the current setting item
            var item = settingsList.currentItem
            if (item && item.children[0] && item.children[0].item) {
                item.children[0].item.forceActiveFocus()
            } else {
                settingsList.forceActiveFocus()
            }
        }
    }

    // ── Settings list ─────────────────────────────────────────────────────────
    ListView {
        id: settingsList

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: actionBar.top
            topMargin: root.vpx(24)
            leftMargin: root.vpx(48)
            rightMargin: root.vpx(48)
            bottomMargin: root.vpx(8)
        }

        model: settingsScreen._settingsModel
        clip: true
        focus: true
        keyNavigationEnabled: false  // We handle Up/Down manually to skip headers
        highlightMoveDuration: Theme.animDurationFast

        // Track whether any child is in edit/adjust mode
        property bool _childEditing: false

        // ── Key handling for the list ─────────────────────────────────────────
        Keys.onPressed: (event) => {
            // If a child is in edit/adjust mode, let it handle keys
            if (settingsList._childEditing) {
                return
            }

            if (event.key === Qt.Key_Up) {
                event.accepted = true
                _moveFocus(-1)
            } else if (event.key === Qt.Key_Down) {
                event.accepted = true
                _moveFocus(1)
            } else if (keys.isCancel(event)) {
                event.accepted = true
                settingsScreen.back()
            }
        }

        // Move focus by delta, skipping header rows
        function _moveFocus(delta) {
            var newIndex = currentIndex + delta
            while (newIndex >= 0 && newIndex < model.length) {
                if (model[newIndex].type !== "header") {
                    currentIndex = newIndex
                    // Force active focus on the loaded component
                    var item = currentItem
                    if (item && item.children[0] && item.children[0].item) {
                        item.children[0].item.forceActiveFocus()
                    }
                    return
                }
                newIndex += delta
            }
            if (delta < 0 && newIndex < 0) settingsScreen.back()
        }

        // Initialize to first non-header row.  Only sets currentIndex —
        // actual focus is routed via onActiveFocusChanged when the user
        // enters the content area (Down/A from tab bar).
        Component.onCompleted: {
            for (var i = 0; i < model.length; i++) {
                if (model[i].type !== "header") {
                    currentIndex = i
                    break
                }
            }
        }

        // ── Delegate ──────────────────────────────────────────────────────────
        delegate: Item {
            id: delegateWrapper
            width: settingsList.width
            height: loaderItem.item ? loaderItem.item.implicitHeight : 0

            readonly property var rowData: modelData
            readonly property bool isCurrentRow: settingsList.currentIndex === index

            Loader {
                id: loaderItem
                width: parent.width

                // Pick the right component based on type
                sourceComponent: {
                    if (rowData.type === "header")  return headerComp
                    if (rowData.type === "text")    return textInputComp
                    if (rowData.type === "toggle")  return toggleComp
                    if (rowData.type === "button")  return buttonComp
                    if (rowData.type === "slider")  return sliderComp
                    if (rowData.type === "select")  return selectComp
                    return null
                }

                // Give focus to the loaded item when it becomes the current row
                onLoaded: {
                    if (item && rowData.type !== "header") {
                        item.focus = Qt.binding(function() {
                            return delegateWrapper.isCurrentRow && settingsList.activeFocus
                        })
                    }
                }
            }

            // ── Header component ──────────────────────────────────────────────
            Component {
                id: headerComp
                Item {
                    implicitHeight: root.vpx(48)
                    width: parent ? parent.width : 0

                    // Separator line
                    Rectangle {
                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: headerLabel.verticalCenter
                        }
                        height: root.vpx(1)
                        color: Theme.colorTextDim
                        opacity: 0.3
                    }

                    // Header label on a background patch to "break" the line
                    Rectangle {
                        id: labelBg
                        anchors {
                            left: parent.left
                            verticalCenter: headerLabel.verticalCenter
                        }
                        width: headerLabel.width + root.vpx(16)
                        height: headerLabel.height + root.vpx(4)
                        color: Theme.colorBackground
                    }

                    Text {
                        id: headerLabel
                        anchors {
                            left: parent.left
                            bottom: parent.bottom
                            bottomMargin: root.vpx(6)
                        }
                        text: rowData.label
                        color: Theme.colorPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        font.bold: true
                        font.letterSpacing: root.vpx(2)
                    }
                }
            }

            // ── Text input component ──────────────────────────────────────────
            Component {
                id: textInputComp
                SettingTextInput {
                    width: parent ? parent.width : 0
                    label: rowData.label
                    value: settingsScreen._getValue(rowData.settingKey)
                    masked: rowData.masked || false

                    onEditingChanged: {
                        settingsList._childEditing = editing
                    }

                    onValueEdited: (newValue) => {
                        settingsScreen._setValue(rowData.settingKey, newValue)
                    }
                }
            }

            // ── Toggle component ──────────────────────────────────────────────
            Component {
                id: toggleComp
                SettingToggle {
                    width: parent ? parent.width : 0
                    label: rowData.label
                    checked: settingsScreen._getValue(rowData.settingKey)

                    onToggled: (newValue) => {
                        settingsScreen._setValue(rowData.settingKey, newValue)
                    }
                }
            }

            // ── Button component ──────────────────────────────────────────────
            Component {
                id: buttonComp
                SettingButton {
                    id: actionButton
                    width: parent ? parent.width : 0
                    label: rowData.label

                    onClicked: {
                        var action = rowData.action
                        if (action === "rescan") {
                            settings.rescanLibrary()
                            actionButton.statusText = "Rescanned!"
                        } else if (action === "testPlex") {
                            actionButton.statusText = "Testing..."
                            // Defer the synchronous call to next event loop turn
                            // so "Testing..." is rendered before blocking.
                            Qt.callLater(function() {
                                var ok = settings.testPlexConnection()
                                actionButton.statusText = ok ? "Connected!" : "Failed"
                            })
                        } else if (action === "plexSignIn") {
                            actionButton.statusText = "Opening browser..."
                            settings.signInWithPlex()
                        } else if (action === "openMoonlight") {
                            settings.openMoonlight()
                            actionButton.statusText = "Opening..."
                        } else if (action === "systemCores") {
                            settingsScreen._showToast("Coming soon")
                        } else if (action === "mapController") {
                            settingsScreen.showControllerMapping()
                        } else if (action === "resetController") {
                            if (settings) settings.resetControllerMapping()
                            settingsScreen._showToast("Controller mapping reset")
                        } else if (action === "clearRetroRecent") {
                            if (library) library.clearRecentlyPlayed()
                            settingsScreen._showToast("Retro game history cleared")

                    }
                }
            }

            // ── Slider component ──────────────────────────────────────────────
            Component {
                id: sliderComp
                SettingSlider {
                    width: parent ? parent.width : 0
                    label: rowData.label
                    value: settingsScreen._getValue(rowData.settingKey)
                    minValue: rowData.min !== undefined ? rowData.min : 0
                    maxValue: rowData.max !== undefined ? rowData.max : 5000
                    step: rowData.step !== undefined ? rowData.step : 100
                    suffix: rowData.suffix !== undefined ? rowData.suffix : ""

                    onAdjustingChanged: {
                        settingsList._childEditing = adjusting
                    }

                    onValueEdited: (newValue) => {
                        settingsScreen._setValue(rowData.settingKey, newValue)
                    }
                }
            }

            // ── Select component ──────────────────────────────────────────────
            Component {
                id: selectComp
                SettingSelect {
                    width: parent ? parent.width : 0
                    label: rowData.label
                    currentValue: settingsScreen._getValue(rowData.settingKey)
                    optionsProvider: function() {
                        if (rowData.settingKey === "buttonLayout") {
                            return [
                                { id: "standard",  label: "Standard (A=East)" },
                                { id: "alternate", label: "Alternate (A=South)" },
                            ]
                        }
                        if (rowData.settingKey === "moonlightHost") {
                            if (!settings) return []
                            return settings.getHostsList()
                        }
                        if (rowData.settingKey === "musicLibrary") {
                            if (!plex) return []
                            return plex.getMusicLibraries()
                        }
                        if (!plex) return []
                        if (rowData.settingKey === "plexServer") {
                            return plex.getServerList().map(function(item) {
                                return { id: item.id, label: item.name }
                            })
                        }
                        if (rowData.settingKey === "plexUser") {
                            return plex.getHomeUsers().map(function(item) {
                                return { id: item.id, label: item.title }
                            })
                        }
                        return []
                    }

                    onSelected: (id) => {
                        settingsScreen._setValue(rowData.settingKey, id)
                    }
                }
            }
        }
    }

    // ── Action bar ────────────────────────────────────────────────────────────
    Rectangle {
        id: actionBar
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        height: root.vpx(44)
        color: Theme.colorSecondary
        opacity: 0.8

        Row {
            anchors {
                left: parent.left
                leftMargin: root.vpx(48)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(24)

            Text {
                text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.acceptLabel + "  Select" : "Enter  Select"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Toast overlay ─────────────────────────────────────────────────────────
    Rectangle {
        id: toastOverlay
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: actionBar.top
            bottomMargin: root.vpx(16)
        }
        width: toastLabel.implicitWidth + root.vpx(32)
        height: root.vpx(40)
        radius: root.vpx(20)
        color: Theme.colorSecondary
        border.color: Theme.colorPrimary
        border.width: root.vpx(1)
        visible: settingsScreen._toastText.length > 0
        opacity: visible ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: Theme.animDurationFast }
        }

        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: settingsScreen._toastText
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
        }
    }
}
