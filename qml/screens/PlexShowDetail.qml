import QtQuick
import ".."
import "../components"

// Plex show detail view — combined show metadata + season/episode browser.
//
// Layout (single scrollable view):
//   Header bar: ◀ Show Title (Year)
//   Content:
//     Left column: poster
//     Right column: metadata (genre, rating, score, seasons, episodes, cast)
//   Synopsis
//   Season tabs (horizontal Row of clickable season labels)
//   Episode list (vertical ListView, updates when season tab changes)
//   Action bar: [A] Play  [B] Back
//
// Focus flow:
//   Opens → season tabs get focus → first season auto-selected → episodes load
//   Left/Right in season tabs → switch season, episodes update automatically
//   Down from season tabs → focus moves to episode list
//   Up from first episode → focus returns to season tabs
//   A on episode → emit playEpisode(ratingKey)
//   B anywhere → emit back()
FocusScope {
    id: showDetailView

    // ratingKey of the show to display. Set by WatchScreen.
    property string showRatingKey: ""

    // Emitted when the user presses B / Escape to return to the show grid.
    signal back()

    // Emitted when the user presses A / Return on an episode.
    signal playEpisode(string ratingKey)

    // Only process input when this view is active.
    enabled: focus

    // ── Data properties ───────────────────────────────────────────────────────
    property var showData: ({})
    property var seasons: []
    property var episodes: []
    property int currentSeasonIndex: 0

    // ── Load data when showRatingKey changes ──────────────────────────────────
    onShowRatingKeyChanged: {
        if (showRatingKey !== "") {
            _loadShow()
        }
    }

    Component.onCompleted: {
        if (showRatingKey !== "") {
            _loadShow()
        }
    }

    function _loadShow() {
        showData = plex.getShow(showRatingKey)
        seasons = plex.getSeasons(showRatingKey)
        episodes = []
        currentSeasonIndex = 0
        // Auto-select first season
        if (seasons.length > 0) {
            _loadEpisodes(seasons[0].ratingKey)
        }
    }

    function _loadEpisodes(seasonRatingKey) {
        episodes = plex.getEpisodes(seasonRatingKey)
    }

    function _selectSeason(idx) {
        if (idx < 0 || idx >= seasons.length) return
        currentSeasonIndex = idx
        _loadEpisodes(seasons[idx].ratingKey)
    }

    // ── Helper: format duration from milliseconds to "Xh Ym" or "Ym" ─────────
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

    // ── Helper: watched indicator character ───────────────────────────────────
    function _watchedIndicator(episode) {
        if (episode.viewed) return "●"
        if (episode.viewOffset > 0) return "◐"
        return "○"
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
                var title = showDetailView.showData.title || ""
                var year = showDetailView.showData.year
                return "◀  " + title + (year > 0 ? " (" + year + ")" : "")
            }
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
            elide: Text.ElideRight
            width: parent.width - root.vpx(32)
        }
    }

    // ── Main scrollable content ───────────────────────────────────────────────
    Flickable {
        id: mainFlickable

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: actionBar.top
        }
        clip: true
        contentWidth: width
        contentHeight: contentColumn.implicitHeight + root.vpx(16)
        interactive: false  // D-pad scrolls via focus management

        Column {
            id: contentColumn

            width: mainFlickable.width
            spacing: 0

            // ── Metadata row: poster + info ───────────────────────────────────
            Item {
                id: metadataRow

                width: parent.width
                height: root.vpx(220)

                // ── Left column: poster ───────────────────────────────────────
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
                        visible: posterImage.status !== Image.Ready
                                 || !showDetailView.showData.posterLocal

                        Text {
                            anchors.centerIn: parent
                            text: showDetailView.showData.title || ""
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
                        source: showDetailView.showData.posterLocal || ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        visible: status === Image.Ready
                                 && !!showDetailView.showData.posterLocal
                    }
                }

                // ── Right column: metadata fields ─────────────────────────────
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
                                label: "Genre",
                                value: (showDetailView.showData.genres || []).join(", ")
                            },
                            {
                                label: "Rating",
                                value: showDetailView.showData.contentRating || ""
                            },
                            {
                                label: "Score",
                                value: showDetailView._formatRating(
                                    showDetailView.showData.audienceRating)
                            },
                            {
                                label: "Seasons",
                                value: showDetailView.showData.childCount > 0
                                    ? "" + showDetailView.showData.childCount
                                    : ""
                            },
                            {
                                label: "Episodes",
                                value: showDetailView.showData.leafCount > 0
                                    ? "" + showDetailView.showData.leafCount
                                    : ""
                            },
                            {
                                label: "Cast",
                                value: (showDetailView.showData.cast || []).join(", ")
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

                    // ── My List status ────────────────────────────────────────
                    Text {
                        text: (plex && showDetailView.showData.ratingKey
                               && plex.isInMyList(showDetailView.showData.ratingKey))
                              ? "★ In My List"
                              : "☆ Add to My List"
                        color: (plex && showDetailView.showData.ratingKey
                                && plex.isInMyList(showDetailView.showData.ratingKey))
                               ? Theme.colorPrimary
                               : Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeBody)
                        visible: !!showDetailView.showData.ratingKey
                    }
                }
            }

            // ── Synopsis ──────────────────────────────────────────────────────
            Text {
                id: synopsisText

                width: parent.width - root.vpx(32)
                x: root.vpx(16)
                topPadding: root.vpx(8)
                bottomPadding: root.vpx(8)
                text: showDetailView.showData.summary || ""
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeBody)
                wrapMode: Text.Wrap
                visible: text !== ""
            }

            // ── Season tabs (horizontal) ──────────────────────────────────────
            Item {
                id: seasonTabsArea

                width: parent.width
                height: root.vpx(48)
                visible: showDetailView.seasons.length > 0

                // Focus ring around the whole tab bar when it has focus
                FocusRing {
                    visible: seasonTabsArea.activeFocus
                }

                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Left) {
                        event.accepted = true
                        if (showDetailView.currentSeasonIndex > 0) {
                            showDetailView._selectSeason(showDetailView.currentSeasonIndex - 1)
                        }
                    } else if (event.key === Qt.Key_Right) {
                        event.accepted = true
                        if (showDetailView.currentSeasonIndex < showDetailView.seasons.length - 1) {
                            showDetailView._selectSeason(showDetailView.currentSeasonIndex + 1)
                        }
                    } else if (event.key === Qt.Key_Up) {
                        // Scroll up to show poster and metadata
                        event.accepted = true
                        mainFlickable.contentY = 0
                    } else if (event.key === Qt.Key_Down) {
                        event.accepted = true
                        if (episodeList.count > 0) {
                            episodeList.forceActiveFocus()
                            episodeList.currentIndex = 0
                            // Scroll to episode list
                            var tabsBottom = seasonTabsArea.y + seasonTabsArea.height
                            mainFlickable.contentY = tabsBottom
                        }
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
                            model: showDetailView.seasons

                            Item {
                                id: seasonTab

                                property bool isSelected: index === showDetailView.currentSeasonIndex

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
                                    text: {
                                        var s = modelData
                                        return s.title || ("S" + s.index)
                                    }
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
                                        showDetailView._selectSeason(index)
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

            // ── Episode section header ────────────────────────────────────────
            Item {
                width: parent.width
                height: root.vpx(32)

                Rectangle {
                    anchors {
                        left: parent.left
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: root.vpx(16)
                        rightMargin: root.vpx(16)
                    }
                    height: root.vpx(1)
                    color: Theme.colorTextDim
                    opacity: 0.4
                }

                Text {
                    anchors {
                        left: parent.left
                        leftMargin: root.vpx(16)
                        verticalCenter: parent.verticalCenter
                    }
                    text: {
                        var idx = showDetailView.currentSeasonIndex
                        if (idx >= 0 && idx < showDetailView.seasons.length) {
                            var s = showDetailView.seasons[idx]
                            return "Episodes (" + (s.title || ("Season " + s.index)) + ")"
                        }
                        return "Episodes"
                    }
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    font.bold: true
                }
            }

            // ── Episode list ──────────────────────────────────────────────────
            ListView {
                id: episodeList

                width: parent.width
                height: root.vpx(56) * Math.max(1, showDetailView.episodes.length)
                clip: true
                interactive: false
                keyNavigationEnabled: true
                highlightMoveDuration: Theme.animDurationFast

                model: showDetailView.episodes

                Keys.onPressed: (event) => {
                    if (keys.isAccept(event)) {
                        event.accepted = true
                        var ep = showDetailView.episodes[episodeList.currentIndex]
                        if (ep) {
                            showDetailView.playEpisode(ep.ratingKey)
                        }
                    } else if (keys.isCancel(event)) {
                        event.accepted = true
                        showDetailView.back()
                    } else if (event.key === Qt.Key_Up
                               && episodeList.currentIndex <= 0) {
                        // Move focus back to season tabs when pressing Up from first episode
                        event.accepted = true
                        seasonTabsArea.forceActiveFocus()
                        // Scroll back to show season tabs
                        mainFlickable.contentY = Math.max(0, seasonTabsArea.y - root.vpx(16))
                    }
                }

                onCurrentIndexChanged: {
                    // Scroll main flickable to keep current episode visible
                    var itemY = episodeList.y + currentIndex * root.vpx(56)
                    var visibleBottom = mainFlickable.contentY + mainFlickable.height
                    if (itemY + root.vpx(56) > visibleBottom) {
                        mainFlickable.contentY = itemY + root.vpx(56) - mainFlickable.height
                    } else if (itemY < mainFlickable.contentY) {
                        mainFlickable.contentY = itemY
                    }
                }

                delegate: Item {
                    id: episodeDelegate

                    width: episodeList.width
                    height: root.vpx(56)

                    // Highlight background for focused item
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: episodeDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on opacity {
                            NumberAnimation { duration: Theme.animDurationFast }
                        }
                    }

                    Row {
                        anchors {
                            left: parent.left
                            right: parent.right
                            leftMargin: root.vpx(16)
                            rightMargin: root.vpx(16)
                            verticalCenter: parent.verticalCenter
                        }
                        spacing: root.vpx(8)

                        // Focus indicator arrow
                        Text {
                            text: episodeDelegate.ListView.isCurrentItem ? "▸" : " "
                            color: Theme.colorPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(16)
                        }

                        // Episode number
                        Text {
                            text: {
                                var ep = modelData
                                var e = ep.index || 0
                                return "E" + (e < 10 ? "0" + e : "" + e)
                            }
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(40)
                        }

                        // Episode title
                        Text {
                            text: modelData.title || ""
                            color: episodeDelegate.ListView.isCurrentItem
                                ? Theme.colorText
                                : Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            elide: Text.ElideRight
                            width: episodeDelegate.width
                                   - root.vpx(16 + 16 + 16 + 8 + 40 + 8 + 48 + 8 + 24)
                        }

                        // Duration
                        Text {
                            text: modelData.duration > 0
                                ? showDetailView._formatDuration(modelData.duration)
                                : ""
                            color: Theme.colorTextDim
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(48)
                            horizontalAlignment: Text.AlignRight
                        }

                        // Watched indicator
                        Text {
                            text: showDetailView._watchedIndicator(modelData)
                            color: modelData.viewed
                                ? Theme.colorPrimary
                                : (modelData.viewOffset > 0
                                    ? Theme.colorPrimary
                                    : Theme.colorTextDim)
                            font.family: Theme.fontFamily
                            font.pixelSize: root.vpx(Theme.fontSizeBody)
                            width: root.vpx(24)
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    // In-progress bar
                    Rectangle {
                        anchors {
                            left: parent.left
                            right: parent.right
                            bottom: parent.bottom
                            leftMargin: root.vpx(16)
                            rightMargin: root.vpx(16)
                        }
                        height: root.vpx(3)
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(2)
                        visible: modelData.viewOffset > 0 && !modelData.viewed
                                 && modelData.duration > 0

                        Rectangle {
                            anchors {
                                left: parent.left
                                top: parent.top
                                bottom: parent.bottom
                            }
                            width: parent.width
                                   * Math.min(1.0, modelData.viewOffset / modelData.duration)
                            color: Theme.colorPrimary
                            radius: parent.radius
                        }
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
                            var ep = showDetailView.episodes[index]
                            if (ep) {
                                showDetailView.playEpisode(ep.ratingKey)
                            }
                        }
                    }
                }
            }

            // Bottom padding
            Item {
                width: parent.width
                height: root.vpx(16)
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
                  ? "[◀▶] Season    [▼] Episodes    [" + keys.acceptLabel + "] Play    [" + keys.context1Label + "] My List    [" + keys.cancelLabel + "] Back"
                  : "[←→] Season    [↓] Episodes    [Enter] Play    [F1] My List    [Esc] Back"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeSmall)
        }
    }

    // ── Focus routing ─────────────────────────────────────────────────────────
    // When this view gains focus, route to season tabs
    onActiveFocusChanged: {
        if (activeFocus) {
            mainFlickable.contentY = 0
            seasonTabsArea.forceActiveFocus()
        }
    }

    // ── X key handler for My List toggle ─────────────────────────────────────
    Keys.onPressed: (event) => {
        if (keys.isContext1(event)) {
            event.accepted = true
            if (plex && showDetailView.showData.ratingKey) {
                plex.toggleMyList(showDetailView.showData.ratingKey,
                                  showDetailView.showData.title || "",
                                  "show",
                                  showDetailView.showData.posterLocal || "",
                                  "")
            }
        }
    }
}
