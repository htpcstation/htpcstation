import QtQuick
import ".."
import "../components"

// Local video movie detail view — shows metadata for a selected local video.
//
// Focus flow:
//   Gains focus when LocalVideosScreen switches to "movieDetail" view.
//   A (Return)  → emit play(moviePath)
//   B (Escape)  → emit back()
//   Up/Down     → scroll description
FocusScope {
    id: movieDetailView

    // Properties set by the orchestrator.
    property string moviePath:        ""
    property string movieTitle:       ""
    property int    movieYear:        0
    property string movieGenre:       ""
    property string movieDescription: ""
    property string moviePosterPath:  ""

    // Emitted when the user presses B / Escape to return to the movie grid/list.
    signal back()

    // Emitted when the user presses A / Return to play the movie.
    signal play(string path)

    // Only process input when this view is active.
    enabled: focus

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            movieDetailView.play(movieDetailView.moviePath)
        } else if (keys.isCancel(event)) {
            event.accepted = true
            movieDetailView.back()
        } else if (event.key === Qt.Key_Up) {
            event.accepted = true
            synopsisFlickable.contentY = Math.max(
                0,
                synopsisFlickable.contentY - root.vpx(40)
            )
        } else if (event.key === Qt.Key_Down) {
            event.accepted = true
            var maxY = Math.max(0, synopsisFlickable.contentHeight - synopsisFlickable.height)
            synopsisFlickable.contentY = Math.min(maxY, synopsisFlickable.contentY + root.vpx(40))
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
            text: "◀  " + movieDetailView.movieTitle
                  + (movieDetailView.movieYear > 0 ? " (" + movieDetailView.movieYear + ")" : "")
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            elide: Text.ElideRight
            width: parent.width - root.vpx(32)
        }
    }

    // ── Status bar ───────────────────────────────────────────────────────────
    Rectangle {
        id: statusBar
        anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Text {
            anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: keys.useGamepadLabels ? keys.acceptLabel + "  Play" : "A  Play"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Main content area ─────────────────────────────────────────────────────
    Item {
        id: contentArea

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(24)
        }

        // ── Left column: poster (35% width) ───────────────────────────────────
        Item {
            id: posterArea

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            width: Math.round(parent.width * 0.35)

            // Placeholder shown when there is no poster or while loading
            Rectangle {
                anchors.fill: parent
                color: Qt.darker(Theme.colorSecondary, 1.4)
                radius: root.vpx(Theme.focusRingRadius)
                visible: posterImage.status !== Image.Ready || !movieDetailView.moviePosterPath

                Text {
                    anchors.centerIn: parent
                    text: movieDetailView.movieTitle
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
                source: movieDetailView.moviePosterPath || ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: true
                visible: status === Image.Ready && !!movieDetailView.moviePosterPath
            }
        }

        // ── Right column: metadata + description ──────────────────────────────
        Item {
            id: rightColumn

            anchors {
                top: parent.top
                left: posterArea.right
                right: parent.right
                bottom: parent.bottom
                leftMargin: root.vpx(24)
            }

            // ── Metadata fields (anchored to top) ─────────────────────────────
            Column {
                id: metadataColumn

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                }
                spacing: root.vpx(6)

                Repeater {
                    model: [
                        {
                            label: "Year",
                            value: movieDetailView.movieYear > 0 ? String(movieDetailView.movieYear) : ""
                        },
                        {
                            label: "Genre",
                            value: movieDetailView.movieGenre || ""
                        }
                    ]

                    Row {
                        spacing: root.vpx(8)
                        visible: modelData.value !== ""

                        Text {
                            text: modelData.label + ":"
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(80)
                        }

                        Text {
                            text: modelData.value
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: rightColumn.width - root.vpx(80) - root.vpx(8)
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // ── Scrollable description ────────────────────────────────────────
            Flickable {
                id: synopsisFlickable

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(8)
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                clip: true
                contentWidth: width
                contentHeight: synopsisText.implicitHeight
                interactive: false  // D-pad scrolls via Keys.onPressed above

                Text {
                    id: synopsisText

                    width: synopsisFlickable.width
                    text: movieDetailView.movieDescription || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}
