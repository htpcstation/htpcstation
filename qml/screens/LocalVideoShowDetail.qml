import QtQuick
import ".."
import "../components"

// Local video show detail — season tabs + episode list for a local TV show.
//
// Data is passed in from the orchestrator (selectShow() was already called).
//
// Focus flow:
//   Opens → season tabs focused, selectSeason(0) called in Component.onCompleted
//   Left/Right on tabs → localVideos.selectSeason(newIndex), update _currentSeasonIndex
//   Down from tabs → episodeList.forceActiveFocus(), episodeList.currentIndex = 0
//   Up from first episode → seasonTabsArea.forceActiveFocus()
//   A on episode → playEpisode(model.path)
//   B anywhere → back()
FocusScope {
    id: showDetailView

    // Properties set by the orchestrator.
    property string showName:        ""
    property string showPosterPath:  ""
    property int    showYear:        0
    property string showDescription: ""
    property int    showSeasonCount: 0

    // Emitted when the user presses B / Escape to return to the show grid/list.
    signal back()

    // Emitted when the user presses A / Return on an episode.
    signal playEpisode(string path)

    // Only process input when this view is active.
    enabled: focus

    // Current season tab index
    property int _currentSeasonIndex: 0

    Component.onCompleted: {
        if (localVideos) localVideos.selectSeason(0)
    }

    // Route focus to season tabs when this view gains focus
    onActiveFocusChanged: {
        if (activeFocus) {
            seasonTabsArea.forceActiveFocus()
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
            text: "◀  " + showDetailView.showName
                  + (showDetailView.showYear > 0 ? " (" + showDetailView.showYear + ")" : "")
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
            text: keys.useGamepadLabels ? "[ ◀▶ ]  Season" : "[ ←→ ]  Season"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Main content layout ───────────────────────────────────────────────────
    Column {
        id: mainColumn

        anchors {
            top: statusBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        spacing: 0

        // ── Metadata row: poster + info ───────────────────────────────────────
        Item {
            id: metadataRow

            width: parent.width
            height: root.vpx(220)

            // ── Left column: poster ───────────────────────────────────────────
            Item {
                id: posterArea

                anchors {
                    top: parent.top
                    left: parent.left
                    bottom: parent.bottom
                    margins: root.vpx(16)
                }
                width: root.vpx(120)

                Rectangle {
                    anchors.fill: parent
                    color: Qt.darker(Theme.colorSecondary, 1.4)
                    radius: root.vpx(Theme.focusRingRadius)
                    visible: posterImage.status !== Image.Ready || !showDetailView.showPosterPath

                    Text {
                        anchors.centerIn: parent
                        text: showDetailView.showName
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - root.vpx(8)
                    }
                }

                Image {
                    id: posterImage

                    anchors.fill: parent
                    source: showDetailView.showPosterPath || ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: status === Image.Ready && !!showDetailView.showPosterPath
                }
            }

            // ── Right column: metadata fields ─────────────────────────────────
            Column {
                id: metadataInfoColumn

                anchors {
                    top: parent.top
                    left: posterArea.right
                    right: parent.right
                    topMargin: root.vpx(16)
                    leftMargin: root.vpx(16)
                    rightMargin: root.vpx(16)
                }
                spacing: root.vpx(4)

                Repeater {
                    model: [
                        {
                            label: "Year",
                            value: showDetailView.showYear > 0 ? String(showDetailView.showYear) : ""
                        },
                        {
                            label: "Seasons",
                            value: showDetailView.showSeasonCount > 0
                                ? String(showDetailView.showSeasonCount)
                                : ""
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
                            width: root.vpx(72)
                        }

                        Text {
                            text: modelData.value
                            color: Theme.colorText
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: metadataInfoColumn.width - root.vpx(72) - root.vpx(8)
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                        }
                    }
                }

                // Description (static — not scrollable per spec)
                Text {
                    width: metadataInfoColumn.width
                    topPadding: root.vpx(6)
                    text: showDetailView.showDescription
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    visible: text !== ""
                }
            }
        }

        // ── Season tabs (horizontal) ──────────────────────────────────────────
        Item {
            id: seasonTabsArea

            width: parent.width
            height: root.vpx(48)
            focus: true

            // Focus ring around the whole tab bar when it has focus
            FocusRing {
                visible: seasonTabsArea.activeFocus
            }

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Left) {
                    event.accepted = true
                    if (showDetailView._currentSeasonIndex > 0) {
                        showDetailView._currentSeasonIndex -= 1
                        if (localVideos) localVideos.selectSeason(showDetailView._currentSeasonIndex)
                    }
                } else if (event.key === Qt.Key_Right) {
                    event.accepted = true
                    if (showDetailView._currentSeasonIndex < seasonTabRepeater.count - 1) {
                        showDetailView._currentSeasonIndex += 1
                        if (localVideos) localVideos.selectSeason(showDetailView._currentSeasonIndex)
                    }
                } else if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    episodeList.forceActiveFocus()
                    episodeList.currentIndex = 0
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    showDetailView.back()
                }
            }

            // Horizontal scrollable row of season tabs
            Flickable {
                id: seasonTabsFlickable

                anchors.fill: parent
                contentWidth: seasonTabsRow.implicitWidth
                contentHeight: height
                clip: true
                interactive: false  // Controlled programmatically

                Row {
                    id: seasonTabsRow

                    height: parent.height
                    spacing: 0

                    Repeater {
                        id: seasonTabRepeater
                        model: localVideos ? localVideos.seasonsModel : null

                        Item {
                            id: seasonTab

                            property bool isSelected: index === showDetailView._currentSeasonIndex

                            width: tabLabel.implicitWidth + root.vpx(24)
                            height: seasonTabsRow.height

                            // Selected tab background
                            Rectangle {
                                anchors.fill: parent
                                color: seasonTab.isSelected
                                    ? Theme.colorPrimary
                                    : Theme.colorSecondary
                                opacity: seasonTab.isSelected ? 0.9 : 0.5
                                radius: root.vpx(Theme.focusRingRadius)

                                Behavior on opacity {
                                    NumberAnimation { duration: Theme.animDurationFast }
                                }
                                Behavior on color {
                                    ColorAnimation { duration: Theme.animDurationFast }
                                }
                            }

                            Text {
                                id: tabLabel

                                anchors.centerIn: parent
                                text: model.name || ""
                                color: seasonTab.isSelected
                                    ? Theme.colorBackground
                                    : Theme.colorText
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeBody)
                                font.bold: seasonTab.isSelected

                                Behavior on color {
                                    ColorAnimation { duration: Theme.animDurationFast }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    showDetailView._currentSeasonIndex = index
                                    if (localVideos) localVideos.selectSeason(index)
                                    seasonTabsArea.forceActiveFocus()
                                }
                            }

                            // Scroll the tab into view when selected
                            onIsSelectedChanged: {
                                if (isSelected) {
                                    var tabX = x
                                    var tabRight = tabX + width
                                    var visibleRight = seasonTabsFlickable.contentX + seasonTabsFlickable.width
                                    if (tabRight > visibleRight) {
                                        seasonTabsFlickable.contentX = tabRight - seasonTabsFlickable.width
                                    } else if (tabX < seasonTabsFlickable.contentX) {
                                        seasonTabsFlickable.contentX = tabX
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── Episode list ──────────────────────────────────────────────────────
        ListView {
            id: episodeList

            width: parent.width
            height: mainColumn.height
                    - metadataRow.height
                    - seasonTabsArea.height

            model: localVideos ? localVideos.episodesModel : null
            clip: true
            keyNavigationEnabled: true
            highlightMoveDuration: Theme.animDurationFast
            highlightRangeMode: ListView.ApplyRange
            preferredHighlightBegin: height * 0.35
            preferredHighlightEnd: height * 0.65

            Keys.onPressed: (event) => {
                if (keys.isAccept(event)) {
                    event.accepted = true
                    var item = episodeList.currentItem
                    if (item) {
                        showDetailView.playEpisode(item.episodePath)
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    showDetailView.back()
                } else if (event.key === Qt.Key_Up && episodeList.currentIndex <= 0) {
                    event.accepted = true
                    seasonTabsArea.forceActiveFocus()
                }
            }

            // ── Episode row delegate ─────────────────────────────────────────
            delegate: Item {
                id: episodeDelegate

                readonly property string episodePath: model.path || ""

                width: episodeList.width
                height: root.vpx(40)

                // Background highlight for the current item
                Rectangle {
                    anchors.fill: parent
                    color: Theme.colorSecondary
                    opacity: episodeDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                    radius: root.vpx(Theme.focusRingRadius)

                    scale: episodeDelegate.ListView.isCurrentItem && episodeList.activeFocus
                        ? Theme.focusScale : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                Text {
                    anchors {
                        left: parent.left
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(16)
                        rightMargin: root.vpx(16)
                    }
                    text: model.title || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeBody)
                    elide: Text.ElideRight
                }

                // Focus ring
                FocusRing {
                    visible: episodeDelegate.ListView.isCurrentItem && episodeList.activeFocus
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        episodeList.currentIndex = index
                        episodeList.forceActiveFocus()
                    }
                    onDoubleClicked: {
                        episodeList.currentIndex = index
                        if (localVideos) {
                            showDetailView.playEpisode(model.path || "")
                        }
                    }
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: episodeList.count === 0
                text: "No episodes found."
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
