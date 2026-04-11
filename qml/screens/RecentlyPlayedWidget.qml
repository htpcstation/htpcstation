import QtQuick
import ".."
import "../components"
import HTPCBackend 1.0

// Horizontal card row showing recently played items.
//
// Focus flow:
//   Gains focus when user presses Down from the tab bar (if items exist).
//   Left/Right — move between cards.
//   A (Return) — emit activated(source, navParams).
//   B (Escape) — emit back() so HomeScreen can return focus to the tab bar.
//   Up         — does nothing (event consumed).
FocusScope {
    id: widget

    signal activated(string source, var navParams)
    signal back()

    property var items: []

    // Empty state
    Text {
        anchors.centerIn: parent
        visible: widget.items.length === 0
        text: "Play something to see it get added here."
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
        horizontalAlignment: Text.AlignHCenter
    }

    // Content column: header + card row
    Column {
        anchors.centerIn: parent
        spacing: root.vpx(16)
        visible: widget.items.length > 0

        Row {
            id: cardRow
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: root.vpx(24)
            focus: widget.focus

            Repeater {
                id: cardRepeater
                model: Math.min(widget.items.length, 5)

                FocusScope {
                    id: cardItem

                    readonly property int cardIndex: index
                    readonly property var itemData: widget.items[index] || {}

                    width: root.vpx(200)
                    height: root.vpx(280) + root.vpx(40)

                    scale: activeFocus ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Left) {
                            event.accepted = true
                            if (index > 0) {
                                cardRepeater.itemAt(index - 1).forceActiveFocus()
                            }
                        } else if (event.key === Qt.Key_Right) {
                            event.accepted = true
                            if (index < Math.min(widget.items.length, 5) - 1) {
                                cardRepeater.itemAt(index + 1).forceActiveFocus()
                            }
                        } else if (event.key === Qt.Key_Up) {
                            event.accepted = true
                            widget.back()
                        } else if (KeyHandler.isCancel(event)) {
                            event.accepted = true
                            widget.back()
                        } else if (KeyHandler.isAccept(event)) {
                            event.accepted = true
                            var d = cardItem.itemData
                            widget.activated(d.source || "", d.nav_params || null)
                        }
                    }

                    Column {
                        anchors.fill: parent
                        spacing: root.vpx(6)

                        // Artwork area
                        Item {
                            id: artArea
                            width: root.vpx(200)
                            height: root.vpx(280)

                            // Placeholder background
                            Rectangle {
                                anchors.fill: parent
                                color: Theme.colorSurface
                                radius: root.vpx(6)
                                visible: artImage.status !== Image.Ready || !cardItem.itemData.artwork

                                Text {
                                    anchors.centerIn: parent
                                    text: {
                                        var title = cardItem.itemData.title || ""
                                        return title.length > 0 ? title.charAt(0).toUpperCase() : "▶"
                                    }
                                    color: Theme.colorTextDim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: root.vpx(Theme.fontSizeTitle)
                                }
                            }

                            // Artwork image with clip
                            Image {
                                id: artImage
                                anchors.fill: parent
                                source: cardItem.itemData.artwork || ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                cache: true
                                visible: status === Image.Ready && !!cardItem.itemData.artwork
                            }

                            // Focus ring
                            Rectangle {
                                anchors.fill: parent
                                color: "transparent"
                                border.color: Theme.colorAccent
                                border.width: root.vpx(4)
                                radius: root.vpx(6)
                                visible: cardItem.activeFocus
                            }
                        }

                        // Title text
                        Text {
                            width: root.vpx(200)
                            text: cardItem.itemData.title || ""
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    // Give focus to the first card when the widget receives focus
    onActiveFocusChanged: {
        if (activeFocus && widget.items.length > 0) {
            var first = cardRepeater.itemAt(0)
            if (first) first.forceActiveFocus()
        }
    }
}
