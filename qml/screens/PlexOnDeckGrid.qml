import QtQuick
import ".."
import "../components"

// Plex on-deck (Continue Watching) grid — shows a scrollable grid of in-progress items.
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for the ondeck library.
//   Arrow keys navigate the grid natively.
//   A (Return) on a cell → emits itemSelected(ratingKey).
//   B (Escape) → emits back() so WatchScreen can return to the library list.
//
// No sort/filter overlay — on-deck is a fixed list ordered by Plex.
FocusScope {
    id: onDeckGridView

    // Emitted when the user presses B / Escape to return to the library list.
    signal back()

    // Emitted when the user presses A / Return on an item cell.
    // ratingKey is the Plex ratingKey for the selected item.
    signal itemSelected(string ratingKey)

    // ── Cell dimensions (same as PlexMovieGrid for visual consistency) ────────
    readonly property int _cellW: 160
    readonly property int _cellH: 280
    readonly property int _cellSpacing: 12

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
            text: "◀  Continue Watching"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // B button hint
        Text {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "Esc  Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── On-deck grid ──────────────────────────────────────────────────────────
    GridView {
        id: onDeckGrid

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: plex ? plex.onDeckModel : null
        clip: true
        focus: true

        cellWidth: root.vpx(onDeckGridView._cellW + onDeckGridView._cellSpacing)
        cellHeight: root.vpx(onDeckGridView._cellH + onDeckGridView._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                var item = onDeckGrid.currentItem
                if (item) {
                    onDeckGridView.itemSelected(item.itemRatingKey)
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                onDeckGridView.back()
            }
        }

        // ── Empty state ──────────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: onDeckGrid.count === 0
            text: "Nothing in progress"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── On-deck tile delegate ─────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose ratingKey so the key handler can read it.
            readonly property string itemRatingKey: model.ratingKey

            width: onDeckGrid.cellWidth
            height: onDeckGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(onDeckGridView._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && onDeckGrid.activeFocus ? 0.15 : 0.0

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // ── Poster image area ─────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~75% of the card height (portrait 2:3 ratio)
                    height: Math.round(parent.height * 0.75)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.posterLocal === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.type === "episode"
                                  ? (model.grandparentTitle || model.title || "")
                                  : (model.title || "")
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeSmall)
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }
                    }

                    Image {
                        id: posterImage

                        anchors.fill: parent
                        source: model.posterLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(onDeckGridView._cellW)
                        sourceSize.height: Math.round(root.vpx(onDeckGridView._cellH) * 0.75)
                        visible: status === Image.Ready && model.posterLocal !== ""
                        clip: true
                    }

                    // ── Progress bar ──────────────────────────────────────────
                    // Shown at the bottom of the poster area
                    Item {
                        id: progressBarArea

                        anchors {
                            left: parent.left
                            right: parent.right
                            bottom: parent.bottom
                        }
                        height: root.vpx(4)
                        visible: model.duration > 0

                        // Track (background)
                        Rectangle {
                            anchors.fill: parent
                            color: Qt.rgba(0, 0, 0, 0.5)
                        }

                        // Fill (progress)
                        Rectangle {
                            anchors {
                                left: parent.left
                                top: parent.top
                                bottom: parent.bottom
                            }
                            width: {
                                var pct = model.duration > 0
                                          ? Math.min(1.0, model.viewOffset / model.duration)
                                          : 0.0
                                return parent.width * pct
                            }
                            color: Theme.colorPrimary
                        }
                    }
                }

                // ── Title label ───────────────────────────────────────────────
                // For episodes: show name on first line, episode title on second.
                // For movies: just the title.
                Text {
                    id: titleText

                    anchors {
                        top: posterArea.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(4)
                    }
                    text: model.type === "episode"
                          ? (model.grandparentTitle || "")
                          : (model.title || "")
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Episode title (second line, episodes only) ─────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.type === "episode" ? (model.title || "") : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    visible: model.type === "episode"
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && onDeckGrid.activeFocus
                }
            }
        }
    }
}
