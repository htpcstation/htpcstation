import QtQuick
import ".."
import "../components"

// Live TV channel guide screen.
//
// Shows a scrollable list of channels with current and next program info.
// Each row displays: channel logo, channel number + call sign (left column),
// current program + time range, next program + time range (right column).
//
// Focus flow:
//   Gains focus when WatchScreen switches to "content" view for "livetv".
//   Up/Down — navigate channel list.
//   A (Return) — play selected channel (MPV or browser depending on settings).
//   B (Escape) or Up from first row — emit back() to return to library list.
//   PgUp/PgDn — jump 10 rows at a time.
FocusScope {
    id: liveTvScreen

    signal back()
    // Emitted just before liveTV.playChannel() is called so WatchScreen can show
    // the loading overlay while MPV buffers the live stream.
    signal playbackLoading()

    // Only process input when this screen is active.
    enabled: focus

    // Unused for now; kept for consistency with other content screens.
    property string _viewMode: "grid"

    // ── Time formatting helper ────────────────────────────────────────────────
    function _formatTime(unixTs) {
        var d = new Date(unixTs * 1000)
        var h = d.getHours()
        var m = d.getMinutes()
        var ampm = h >= 12 ? "PM" : "AM"
        h = h % 12 || 12
        return h + ":" + (m < 10 ? "0" : "") + m + " " + ampm
    }

    // Trigger a refresh when this screen gains focus.
    // The warm-start path serves cache instantly, then background-refreshes.
    onActiveFocusChanged: {
        if (activeFocus) {
            liveTV.refresh()
            channelList.forceActiveFocus()
        }
    }

    // ── Header bar ────────────────────────────────────────────────────────────
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
            text: "◀  Live TV"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // Background refresh indicator
        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(200)
                verticalCenter: parent.verticalCenter
            }
            visible: liveTV ? (liveTV.loading && channelList.count > 0) : false
            text: "Refreshing..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

    }

    // ── Sub-header status bar ─────────────────────────────────────────────────
    Rectangle {
        id: statusBar

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
        }
        height: root.vpx(28)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Text {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            text: "Live TV"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }

        Row {
            anchors {
                right: parent.right
                rightMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(16)

            Text {
                text: keys.useGamepadLabels
                      ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll"
                      : "PgUp/PgDn  Scroll"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels
                      ? keys.context2Label + "  Refresh"
                      : "2  Refresh"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }

    // ── Loading indicator ─────────────────────────────────────────────────────
    Text {
        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
        }
        visible: liveTV ? (liveTV.loading && channelList.count === 0) : false
        text: "Loading channels..."
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeHeading)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    // ── Empty state ───────────────────────────────────────────────────────────
    Text {
        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
        }
        visible: liveTV ? (!liveTV.loading && channelList.count === 0) : false
        text: "No channels available"
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeHeading)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    // ── Channel list ──────────────────────────────────────────────────────────
    ListView {
        id: channelList

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
        }

        model: liveTV ? liveTV.channelsModel : null
        clip: true
        focus: true
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isCancel(event) || (event.key === Qt.Key_Up && currentIndex === 0)) {
                event.accepted = true
                liveTvScreen.back()
            } else if (keys.isAccept(event)) {
                event.accepted = true
                var ch = channelList.currentItem
                if (ch && ch.channelStreamUrl !== "") {
                    if (!settings || (settings.plexPlayer || "mpv") === "mpv") {
                        liveTvScreen.playbackLoading()
                        liveTV.playChannel(ch.channelVcn)
                    } else {
                        liveTV.playChannelBrowser(ch.channelVcn)
                    }
                }
            } else if (keys.isPageDown(event)) {
                event.accepted = true
                channelList.currentIndex = Math.min(channelList.count - 1,
                    channelList.currentIndex + 10)
            } else if (keys.isPageUp(event)) {
                event.accepted = true
                channelList.currentIndex = Math.max(0,
                    channelList.currentIndex - 10)
            } else if (keys.isContext2(event)) {
                event.accepted = true
                liveTV.forceRefresh()
            }
        }

        // ── Channel row delegate ──────────────────────────────────────────────
        delegate: FocusScope {
            id: rowDelegate

            // Expose channel fields for the key handler.
            readonly property string channelVcn: model.vcn
            readonly property string channelStreamUrl: model.streamUrl

            width: channelList.width
            height: root.vpx(90)

            // Whether this row is currently focused
            readonly property bool _isCurrent: rowDelegate.ListView.isCurrentItem

            // ── Highlight background ──────────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: rowDelegate._isCurrent && channelList.activeFocus ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            // ── Left column: logo + channel number + call sign ────────────────
            Item {
                id: leftCol

                anchors {
                    left: parent.left
                    top: parent.top
                    bottom: parent.bottom
                    leftMargin: root.vpx(12)
                }
                width: root.vpx(200)

                // Channel logo
                Item {
                    id: logoArea

                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    width: root.vpx(48)
                    height: root.vpx(48)

                    // Fallback rectangle shown when no logo or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(4)
                        visible: channelLogo.status !== Image.Ready || model.thumb === ""
                    }

                    Image {
                        id: channelLogo

                        anchors.fill: parent
                        source: model.thumb || ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        visible: status === Image.Ready && model.thumb !== ""
                    }
                }

                // Channel number (vcn)
                Text {
                    id: vcnText

                    anchors {
                        left: logoArea.right
                        leftMargin: root.vpx(8)
                        top: parent.top
                        topMargin: root.vpx(14)
                    }
                    text: model.vcn || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: true
                }

                // Call sign
                Text {
                    anchors {
                        left: logoArea.right
                        leftMargin: root.vpx(8)
                        top: vcnText.bottom
                        topMargin: root.vpx(2)
                    }
                    text: model.callSign || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    elide: Text.ElideRight
                    width: root.vpx(120)
                }
            }

            // ── Right column: current + next program ──────────────────────────
            Item {
                id: rightCol

                anchors {
                    left: leftCol.right
                    right: parent.right
                    top: parent.top
                    bottom: parent.bottom
                    leftMargin: root.vpx(8)
                    rightMargin: root.vpx(16)
                }

                // "● LIVE" badge — shown when channel is currently on air
                Text {
                    id: liveBadge

                    anchors {
                        left: parent.left
                        top: parent.top
                        topMargin: root.vpx(10)
                    }
                    text: "● LIVE"
                    color: Theme.colorPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    font.bold: true
                    visible: model.onAir === true
                }

                // "Not available" indicator — shown when no stream URL
                Text {
                    id: notAvailableText

                    anchors {
                        left: parent.left
                        top: parent.top
                        topMargin: root.vpx(10)
                    }
                    text: "Not available"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: model.streamUrl === ""
                }

                // Current program title
                Text {
                    id: currentTitle

                    anchors {
                        left: liveBadge.visible ? liveBadge.right : parent.left
                        leftMargin: liveBadge.visible ? root.vpx(8) : 0
                        right: currentTimeRange.left
                        rightMargin: root.vpx(8)
                        top: parent.top
                        topMargin: root.vpx(10)
                    }
                    text: model.currentProgram || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    font.bold: true
                    elide: Text.ElideRight
                    visible: model.currentProgram !== ""
                }

                // Current program time range (right-aligned)
                Text {
                    id: currentTimeRange

                    anchors {
                        right: parent.right
                        top: parent.top
                        topMargin: root.vpx(10)
                    }
                    text: model.currentStart > 0 && model.currentEnd > 0
                          ? liveTvScreen._formatTime(model.currentStart) + " - " + liveTvScreen._formatTime(model.currentEnd)
                          : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: text !== ""
                }

                // Next program title
                Text {
                    id: nextTitle

                    anchors {
                        left: parent.left
                        right: nextTimeRange.left
                        rightMargin: root.vpx(8)
                        top: currentTitle.bottom
                        topMargin: root.vpx(4)
                    }
                    text: model.nextProgram ? "NEXT: " + model.nextProgram : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    elide: Text.ElideRight
                    visible: model.nextProgram !== ""
                }

                // Next program time range (right-aligned)
                Text {
                    id: nextTimeRange

                    anchors {
                        right: parent.right
                        top: currentTimeRange.bottom
                        topMargin: root.vpx(4)
                    }
                    text: model.nextStart > 0 && model.nextEnd > 0
                          ? liveTvScreen._formatTime(model.nextStart) + " - " + liveTvScreen._formatTime(model.nextEnd)
                          : ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    visible: text !== ""
                }
            }

            // ── Separator line ────────────────────────────────────────────────
            Rectangle {
                anchors {
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }
                height: root.vpx(1)
                color: Theme.colorTextDim
                opacity: 0.15
            }

            // ── Focus ring ────────────────────────────────────────────────────
            FocusRing {
                visible: rowDelegate._isCurrent && channelList.activeFocus
            }

            // ── Mouse support ─────────────────────────────────────────────────
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    channelList.currentIndex = index
                    channelList.forceActiveFocus()
                }
                onDoubleClicked: {
                    channelList.currentIndex = index
                    if (model.streamUrl !== "") {
                        if (!settings || (settings.plexPlayer || "mpv") === "mpv") {
                            liveTvScreen.playbackLoading()
                            liveTV.playChannel(model.vcn)
                        } else {
                            liveTV.playChannelBrowser(model.vcn)
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
        height: root.vpx(40)
        color: Qt.darker(Theme.colorSecondary, 1.3)

        Row {
            anchors {
                left: parent.left
                leftMargin: root.vpx(16)
                verticalCenter: parent.verticalCenter
            }
            spacing: root.vpx(24)

            Text {
                text: keys.useGamepadLabels ? keys.acceptLabel + "  Watch" : "A  Watch"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels ? keys.cancelLabel + "  Back" : "B  Back"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }

            Text {
                text: keys.useGamepadLabels
                      ? keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll"
                      : "PgUp/PgDn  Scroll"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeSmall)
            }
        }
    }
}
