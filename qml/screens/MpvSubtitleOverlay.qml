// MpvSubtitleOverlay.qml — in-process subtitle track picker overlay.
// Rendered as a regular QML FocusScope child of HomeScreen (NOT a Window).
// Since MPV now renders inside the Qt window, a QML overlay on top works correctly.
import QtQuick
import ".."
import "../components"

FocusScope {
    id: subtitleOverlay
    anchors.fill: parent
    visible: false
    enabled: visible

    // Track list data — populated when showOverlay() is called
    property var _tracks: []
    property int _selectedIndex: 0

    function showOverlay() {
        _tracks = plex.getMpvSubtitleTracks()
        // Find the currently selected track index
        _selectedIndex = 0
        for (var i = 0; i < _tracks.length; i++) {
            if (_tracks[i].selected) {
                _selectedIndex = i
                break
            }
        }
        visible = true
        forceActiveFocus()
    }

    function hideOverlay() {
        visible = false
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Up) {
            event.accepted = true
            if (_selectedIndex > 0) _selectedIndex--
        } else if (event.key === Qt.Key_Down) {
            event.accepted = true
            if (_selectedIndex < _tracks.length - 1) _selectedIndex++
        } else if (keys.isAccept(event)) {
            event.accepted = true
            if (_tracks.length > 0) {
                var track = _tracks[_selectedIndex]
                plex.setMpvSubtitleTrack(track.id)
            }
            hideOverlay()
        } else if (keys.isCancel(event)) {
            event.accepted = true
            hideOverlay()
        }
    }

    // Dark semi-transparent backdrop
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.75)

        MouseArea {
            anchors.fill: parent
            onClicked: subtitleOverlay.hideOverlay()
        }
    }

    // Panel
    Rectangle {
        id: overlayPanel
        anchors.centerIn: parent
        width: root.vpx(420)
        height: Math.min(
            root.vpx(60) + trackListView.count * root.vpx(52),
            root.vpx(480)
        )
        radius: root.vpx(Theme.focusRingRadius)
        color: Theme.colorSurfaceHigh

        // Title bar
        Rectangle {
            id: titleBar
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
            }
            height: root.vpx(52)
            radius: root.vpx(Theme.focusRingRadius)
            color: Theme.colorPrimary

            Text {
                anchors.centerIn: parent
                text: "Subtitle Track"
                color: Theme.colorTextOnAccent
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                font.bold: true
            }
        }

        // Track list
        ListView {
            id: trackListView
            anchors {
                top: titleBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(4)
            }
            clip: true
            model: subtitleOverlay._tracks
            currentIndex: subtitleOverlay._selectedIndex

            delegate: Rectangle {
                width: trackListView.width
                height: root.vpx(52)
                color: subtitleOverlay._selectedIndex === index
                    ? Theme.colorRowHighlight
                    : "transparent"
                radius: root.vpx(Theme.focusRingRadius)

                Behavior on color {
                    ColorAnimation { duration: Theme.animDurationFast }
                }

                // Selected indicator dot
                Rectangle {
                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(12)
                        verticalCenter: parent.verticalCenter
                    }
                    width: root.vpx(10)
                    height: root.vpx(10)
                    radius: root.vpx(5)
                    color: modelData.selected
                        ? Theme.colorTrackSelected
                        : Theme.colorTrackMuted
                }

                // Track label
                Text {
                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(32)
                        right: parent.right
                        rightMargin: root.vpx(12)
                        verticalCenter: parent.verticalCenter
                    }
                    text: {
                        var label = modelData.title || modelData.lang || ("Track " + modelData.id)
                        return label
                    }
                    color: modelData.selected
                        ? Theme.colorTrackSelected
                        : Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        subtitleOverlay._selectedIndex = index
                        plex.setMpvSubtitleTrack(modelData.id)
                        subtitleOverlay.hideOverlay()
                    }
                }
            }
        }
    }
}
