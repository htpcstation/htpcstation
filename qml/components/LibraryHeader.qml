import QtQuick
import ".."

// Reusable two-bar header for grid and list library screens.
//
// Usage:
//   LibraryHeader {
//       id: header
//       title: systemName
//       statusText: "Sorted: " + _sortLabel
//       rightText1: keys.useGamepadLabels ? keys.pageUpLabel + "/..." : "PgUp/PgDn  Scroll"
//       rightText2: keys.useGamepadLabels ? keys.context2Label + "  Sort" : "2  Sort"
//   }
//   SomeContent { anchors.top: header.bottom ... }
Item {
    id: libraryHeader

    property string title: ""
    property string statusText: ""
    // Up to 3 right-side help strings; empty string = not shown
    property string rightText1: ""
    property string rightText2: ""
    property string rightText3: ""

    anchors { top: parent.top; left: parent.left; right: parent.right }
    height: root.vpx(56) + root.vpx(28)

    Rectangle {
        id: headerBar
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: "◀  " + libraryHeader.title
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    Rectangle {
        id: statusBar
        anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Text {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: libraryHeader.statusText
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
            visible: libraryHeader.statusText !== ""
        }

        Row {
            anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            spacing: root.vpx(16)

            Text {
                text: libraryHeader.rightText1
                visible: libraryHeader.rightText1 !== ""
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
            Text {
                text: libraryHeader.rightText2
                visible: libraryHeader.rightText2 !== ""
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
            Text {
                text: libraryHeader.rightText3
                visible: libraryHeader.rightText3 !== ""
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }
}
