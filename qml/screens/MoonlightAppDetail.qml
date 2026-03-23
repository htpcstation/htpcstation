import QtQuick
import ".."
import "../components"

// Moonlight app detail panel — shows metadata for a selected Moonlight app.
//
// Focus flow:
//   Gains focus when PcGamesScreen switches to "detail" view for a Moonlight source.
//   A (Return)  → emit launch(hostAddress, appName)
//   B (Escape)  → emit back()
//   Left/Right  → emit navigatePrev() / navigateNext()
FocusScope {
    id: moonlightAppDetail

    // The dict returned by moonlight.getApp(index). Set by PcGamesScreen.
    // Fields: name, hostAddress, hostName, hostUuid
    property var appData: ({})

    // Emitted when the user presses B / Escape to return to the app grid.
    signal back()

    // Emitted when the user presses A / Return to stream the app.
    signal launch(string hostAddress, string appName)

    // Emitted when the user presses Left/Right to navigate to prev/next app.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            var hostAddress = moonlightAppDetail.appData.hostAddress || ""
            var appName = moonlightAppDetail.appData.name || ""
            moonlightAppDetail.launch(hostAddress, appName)
        } else if (keys.isCancel(event)) {
            event.accepted = true
            moonlightAppDetail.back()
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            moonlightAppDetail.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            moonlightAppDetail.navigateNext()
        }
    }

    // ── Header bar ───────────────────────────────────────────────────────────
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
            text: "◀  " + (moonlightAppDetail.appData.name || "")
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            elide: Text.ElideRight
            width: parent.width - root.vpx(32)
        }
    }

    // ── Main content area ─────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
            margins: root.vpx(24)
        }

        // ── Left column: poster image ─────────────────────────────────────────
        Item {
            id: posterArea

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            // Poster area takes ~30% of the content width (portrait aspect)
            width: Math.round(parent.width * 0.30)

            // Placeholder shown when there is no image or while loading
            Rectangle {
                anchors.fill: parent
                color: Qt.darker(Theme.colorSecondary, 1.4)
                radius: root.vpx(Theme.focusRingRadius)
                visible: posterImage.status !== Image.Ready
                         || !moonlightAppDetail.appData.imagePath

                Text {
                    anchors.centerIn: parent
                    text: moonlightAppDetail.appData.name || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width - root.vpx(16)
                }
            }

            Image {
                id: posterImage

                anchors.fill: parent
                source: moonlightAppDetail.appData.imagePath
                        ? (moonlightAppDetail.appData.imagePath.startsWith("http")
                            ? moonlightAppDetail.appData.imagePath
                            : "file://" + moonlightAppDetail.appData.imagePath)
                        : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: status === Image.Ready && !!moonlightAppDetail.appData.imagePath
            }
        }

        // ── Right column: metadata ────────────────────────────────────────────
        Item {
            id: rightColumn

            anchors {
                top: parent.top
                left: posterArea.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(24)
            }

            // ── App name (large, title font) ──────────────────────────────────
            Text {
                id: appNameLabel

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                }
                text: moonlightAppDetail.appData.name || ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeTitle)
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            // ── Metadata fields ───────────────────────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: appNameLabel.bottom
                    topMargin: root.vpx(16)
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(8)

                Repeater {
                    model: [
                        {
                            label: "Host",
                            value: moonlightAppDetail.appData.hostName || ""
                        },
                    ]

                    Row {
                        spacing: root.vpx(8)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(100)
                        }

                        Text {
                            text: modelData.value
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                        }
                    }
                }
            }
        }
    }

    // ── Action hints bar ──────────────────────────────────────────────────────
    Rectangle {
        id: actionBar

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        height: root.vpx(48)
        color: Theme.colorSecondary

        Text {
            anchors.centerIn: parent
            text: keys.useGamepadLabels
                  ? "[◀▶] Prev/Next    [" + keys.acceptLabel + "] Stream    [" + keys.cancelLabel + "] Back"
                  : "[←→] Prev/Next    [Enter] Stream    [Esc] Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }
}
