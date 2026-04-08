import QtQuick
import ".."
import "../components"

// Plex movie detail view — shows full metadata for a selected movie.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "detail" view.
//   A (Return)  → emit play(ratingKey)
//   B (Escape)  → emit back()
//   Up/Down     → scroll synopsis if it overflows
FocusScope {
    id: movieDetailView

    // The dict returned by plex.getMovie(ratingKey). Set by WatchScreen.
    property var movieData: ({})

    // Emitted when the user presses B / Escape to return to the movie grid.
    signal back()

    // Emitted when the user presses A / Return to play the movie.
    signal play(string ratingKey)

    // Emitted when the user presses Left/Right to navigate to prev/next movie.
    signal navigatePrev()
    signal navigateNext()

    // Only process input when this view is active.
    enabled: focus

    // Local viewCount for optimistic toggle of Mark Watched / Unwatched.
    property int _viewCount: 0
    onMovieDataChanged: {
        _viewCount = (movieData && movieData.viewCount !== undefined && movieData.viewCount !== null)
                     ? movieData.viewCount : 0
    }

    // ── Key handling ─────────────────────────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) {
            event.accepted = true
            movieDetailView.play(movieDetailView.movieData.ratingKey || "")
        } else if (keys.isContext1(event)) {
            event.accepted = true
            if (plex && movieDetailView.movieData.ratingKey) {
                plex.toggleMyList(movieDetailView.movieData.ratingKey,
                                  movieDetailView.movieData.title || "",
                                  "movie",
                                  movieDetailView.movieData.posterLocal || "",
                                  "")
            }
        } else if (keys.isContext2(event)) {
            event.accepted = true
            if (plex && movieDetailView.movieData.ratingKey) {
                if (movieDetailView._viewCount > 0) {
                    plex.markUnplayed(movieDetailView.movieData.ratingKey)
                    movieDetailView._viewCount = 0
                } else {
                    plex.markPlayed(movieDetailView.movieData.ratingKey)
                    movieDetailView._viewCount = 1
                }
            }
        } else if (keys.isCancel(event)) {
            event.accepted = true
            movieDetailView.back()
        } else if (event.key === Qt.Key_Left) {
            event.accepted = true
            movieDetailView.navigatePrev()
        } else if (event.key === Qt.Key_Right) {
            event.accepted = true
            movieDetailView.navigateNext()
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

    // ── Helper: format duration from milliseconds to "Xh Ym" ─────────────────
    function _formatDuration(ms) {
        var totalMin = Math.floor(ms / 60000)
        var h = Math.floor(totalMin / 60)
        var m = totalMin % 60
        return h > 0 ? h + "h " + m + "m" : m + "m"
    }

    // ── Helper: format audience rating as "X.X/10" ───────────────────────────
    function _formatRating(rating) {
        if (!rating || rating <= 0) return ""
        return rating.toFixed(1) + "/10"
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
            text: {
                var title = movieDetailView.movieData.title || ""
                var year = movieDetailView.movieData.year
                return "◀  " + title + (year > 0 ? " (" + year + ")" : "")
            }
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            elide: Text.ElideRight
            width: parent.width - root.vpx(32)
        }
    }

    // ── Status bar (sub-header) ───────────────────────────────────────────────
    Rectangle {
        id: statusBar
        anchors { top: headerBar.bottom; left: parent.left; right: parent.right }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Row {
            anchors { right: parent.right; rightMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            spacing: root.vpx(16)

            Text {
                text: keys.useGamepadLabels ? "[ ◀▶ ]  Prev/Next" : "[ ←→ ]  Prev/Next"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.context1Label + "  My List" : "1  My List"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: {
                    var watchLabel = movieDetailView._viewCount > 0 ? "Mark Unwatched" : "Mark Watched"
                    return keys.useGamepadLabels
                        ? keys.context2Label + "  " + watchLabel
                        : "2  " + watchLabel
                }
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
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

        // ── Left column: poster ───────────────────────────────────────────────
        Item {
            id: posterArea

            anchors {
                top: parent.top
                left: parent.left
                bottom: parent.bottom
            }
            // Poster takes ~35% of the content width
            width: Math.round(parent.width * 0.35)

            // Placeholder shown when there is no poster or while loading
            Rectangle {
                anchors.fill: parent
                color: Qt.darker(Theme.colorSecondary, 1.4)
                radius: root.vpx(Theme.focusRingRadius)
                visible: posterImage.status !== Image.Ready || !movieDetailView.movieData.posterLocal

                Text {
                    anchors.centerIn: parent
                    text: movieDetailView.movieData.title || ""
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
                source: movieDetailView.movieData.posterLocal || ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: status === Image.Ready && !!movieDetailView.movieData.posterLocal
            }
        }

        // ── Right column: metadata + tagline + synopsis ───────────────────────
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
                            label: "Studio",
                            value: movieDetailView.movieData.studio || ""
                        },
                        {
                            label: "Rating",
                            value: movieDetailView.movieData.contentRating || ""
                        },
                        {
                            label: "Score",
                            value: movieDetailView._formatRating(movieDetailView.movieData.audienceRating)
                        },
                        {
                            label: "Runtime",
                            value: movieDetailView.movieData.duration > 0
                                ? movieDetailView._formatDuration(movieDetailView.movieData.duration)
                                : ""
                        },
                        {
                            label: "Genre",
                            value: (movieDetailView.movieData.genres || []).join(", ")
                        },
                        {
                            label: "Director",
                            value: (movieDetailView.movieData.directors || []).join(", ")
                        },
                        {
                            label: "Cast",
                            value: (movieDetailView.movieData.cast || []).join(", ")
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

                // ── Separator ─────────────────────────────────────────────────
                Rectangle {
                    width: metadataColumn.width
                    height: root.vpx(1)
                    color: Theme.colorTextDim
                    opacity: 0.3
                }

                // ── My List status ────────────────────────────────────────────
                Text {
                    text: (plex && movieDetailView.movieData.ratingKey
                           && plex.isInMyList(movieDetailView.movieData.ratingKey))
                          ? "★ In My List"
                          : "☆ Add to My List"
                    color: (plex && movieDetailView.movieData.ratingKey
                            && plex.isInMyList(movieDetailView.movieData.ratingKey))
                           ? Theme.colorPrimary
                           : Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    visible: !!movieDetailView.movieData.ratingKey
                }
            }

            // ── Tagline (italic, if present) ──────────────────────────────────
            Text {
                id: taglineText

                anchors {
                    top: metadataColumn.bottom
                    topMargin: root.vpx(10)
                    left: parent.left
                    right: parent.right
                }
                text: movieDetailView.movieData.tagline || ""
                visible: text !== ""
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                font.italic: true
                wrapMode: Text.Wrap
            }

            // ── Synopsis (scrollable) — fills remaining space ─────────────────
            Flickable {
                id: synopsisFlickable

                anchors {
                    top: taglineText.visible ? taglineText.bottom : metadataColumn.bottom
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
                    text: movieDetailView.movieData.summary || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    wrapMode: Text.Wrap
                }
            }
        }
    }

}
