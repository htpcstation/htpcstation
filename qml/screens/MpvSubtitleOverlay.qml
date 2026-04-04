import QtQuick
import QtQuick.Window
import ".."

Window {
    id: subtitleOverlay

    // Show/hide API
    function showOverlay() {
        var tracks = plex.getMpvSubtitleTracks()
        subtitleModel.clear()
        // Add "Off" option first
        subtitleModel.append({trackId: 0, label: "Off", selected: tracks.length > 0 && tracks.every(t => !t.selected)})
        for (var i = 0; i < tracks.length; i++) {
            var t = tracks[i]
            var label = t.title || t.lang || ("Track " + t.id)
            if (t.external) label += " [external]"
            subtitleModel.append({trackId: t.id, label: label, selected: t.selected})
        }
        // Focus the currently selected item
        var selIdx = 0
        for (var j = 0; j < subtitleModel.count; j++) {
            if (subtitleModel.get(j).selected) { selIdx = j; break }
        }
        trackList.currentIndex = selIdx
        subtitleOverlay.show()
        subtitleOverlay.raise()
        subtitleOverlay.requestActivate()
        trackList.forceActiveFocus()
    }

    flags: Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
    color: "transparent"
    width: 480
    height: Math.min(subtitleModel.count * 56 + 80, 500)
    // Centre on screen
    x: (Screen.width - width) / 2
    y: (Screen.height - height) / 2

    // Dark semi-transparent panel
    Rectangle {
        anchors.fill: parent
        color: Theme.colorPanelDark
        radius: 12

        Column {
            anchors { top: parent.top; left: parent.left; right: parent.right; topMargin: 20; leftMargin: 20; rightMargin: 20 }
            spacing: 4

            Text {
                text: "Subtitles"
                color: Theme.colorOverlayText
                font.pixelSize: 20
                font.bold: true
            }

            ListView {
                id: trackList
                width: parent.width
                height: Math.min(subtitleModel.count * 56, 420)
                model: subtitleModel
                clip: true
                focus: true
                keyNavigationEnabled: true

                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Space) {
                        event.accepted = true
                        var item = subtitleModel.get(trackList.currentIndex)
                        if (item) {
                            plex.setMpvSubtitleTrack(item.trackId)
                            subtitleOverlay.hide()
                        }
                    } else if (event.key === Qt.Key_Escape) {
                        event.accepted = true
                        subtitleOverlay.hide()
                    }
                }

                delegate: Rectangle {
                    width: trackList.width
                    height: 52
                    color: trackList.currentIndex === index ? Theme.colorRowHighlight : "transparent"
                    radius: 6

                    Row {
                        anchors { verticalCenter: parent.verticalCenter; left: parent.left; leftMargin: 12 }
                        spacing: 12

                        Text {
                            text: model.selected ? "●" : "○"
                            color: model.selected ? Theme.colorTrackSelected : Theme.colorTrackMuted
                            font.pixelSize: 16
                        }
                        Text {
                            text: model.label
                            color: Theme.colorOverlayText
                            font.pixelSize: 16
                        }
                    }
                }
            }
        }
    }

    ListModel { id: subtitleModel }
}
