import QtQuick
import ".."
import "../components"

// Local Videos screen — browse and play local video files.
//
// Views:
//   "categories" — ListView of all configured video categories
//   "videos"     — ListView of flat video files in the selected category
//   "shows"      — ListView of TV shows in the selected category
//   "seasons"    — ListView of seasons within a selected show
//   "episodes"   — ListView of episodes within a selected season
//
// Focus flow:
//   Enter LocalVideosScreen → categoriesList gets focus
//   Up/Down           — navigate items (ListView handles natively)
//   A (Return)        — select item
//   B (Escape)        — go back one level; from categories emit back()
FocusScope {
    id: localVideosScreen

    // Emit when B (Escape) is pressed from the categories view so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Navigation target passed by HomeScreen when navigating from recently played.
    // navTarget deep-link routing is a future milestone.
    property var navTarget: null

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "categories", "videos", "shows", "seasons", "episodes"
    property string currentView: "categories"

    property int _selectedCategoryIndex: -1
    property int _selectedShowIndex: -1
    property int _selectedSeasonIndex: -1

    onCurrentViewChanged: _routeFocus()
    onActiveFocusChanged: if (activeFocus) _routeFocus()

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "categories") {
            categoriesList.forceActiveFocus()
        } else if (currentView === "videos") {
            videosList.forceActiveFocus()
        } else if (currentView === "shows") {
            showsList.forceActiveFocus()
        } else if (currentView === "seasons") {
            seasonsList.forceActiveFocus()
        } else if (currentView === "episodes") {
            episodesList.forceActiveFocus()
        }
    }

    // ── Header bar ───────────────────────────────────────────────────────────
    Rectangle {
        id: headerBar

        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.vpx(56)
        color: Theme.colorSecondary

        Text {
            anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
            text: "Videos"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Categories ListView ───────────────────────────────────────────────────
    ListView {
        id: categoriesList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: localVideos ? localVideos.categoriesModel : null
        clip: true
        keyNavigationEnabled: true
        focus: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "categories"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0 && currentItem) {
                    localVideos.selectCategory(currentIndex)
                    localVideosScreen._selectedCategoryIndex = currentIndex
                    if (currentItem.categoryType === "flat") {
                        localVideosScreen.currentView = "videos"
                    } else {
                        localVideosScreen.currentView = "shows"
                    }
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.back()
            }
        }

        delegate: Item {
            id: categoryDelegate

            readonly property string categoryType: model.type

            width: categoriesList.width
            height: root.vpx(64)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: categoryDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: categoryDelegate.ListView.isCurrentItem && categoriesList.activeFocus
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
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.name
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            FocusRing {
                visible: categoryDelegate.ListView.isCurrentItem && categoriesList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    categoriesList.currentIndex = index
                    categoriesList.forceActiveFocus()
                }
                onDoubleClicked: {
                    categoriesList.currentIndex = index
                    if (localVideos) {
                        localVideos.selectCategory(index)
                        localVideosScreen._selectedCategoryIndex = index
                        if (model.type === "flat") {
                            localVideosScreen.currentView = "videos"
                        } else {
                            localVideosScreen.currentView = "shows"
                        }
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: categoriesList.count === 0
            text: "No video categories configured.\nAdd paths in Settings."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ── Videos ListView ───────────────────────────────────────────────────────
    ListView {
        id: videosList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: localVideos ? localVideos.videosModel : null
        clip: true
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "videos"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0 && currentItem) {
                    localVideos.playVideo(currentItem.videoPath, localVideos.getResumePosition(currentItem.videoPath))
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.currentView = "categories"
            }
        }

        delegate: Item {
            id: videoDelegate

            readonly property string videoPath: model.path

            width: videosList.width
            height: root.vpx(64)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: videoDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: videoDelegate.ListView.isCurrentItem && videosList.activeFocus
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
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.title
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
                width: parent.width - root.vpx(32)
            }

            FocusRing {
                visible: videoDelegate.ListView.isCurrentItem && videosList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    videosList.currentIndex = index
                    videosList.forceActiveFocus()
                }
                onDoubleClicked: {
                    videosList.currentIndex = index
                    if (localVideos) {
                        localVideos.playVideo(model.path, localVideos.getResumePosition(model.path))
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: videosList.count === 0
            text: "No videos found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ── Shows ListView ────────────────────────────────────────────────────────
    ListView {
        id: showsList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: localVideos ? localVideos.showsModel : null
        clip: true
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "shows"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0) {
                    localVideos.selectShow(currentIndex)
                    localVideosScreen._selectedShowIndex = currentIndex
                    localVideosScreen.currentView = "seasons"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.currentView = "categories"
            }
        }

        delegate: Item {
            id: showDelegate

            width: showsList.width
            height: root.vpx(72)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: showDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: showDelegate.ListView.isCurrentItem && showsList.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            Column {
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                spacing: root.vpx(4)

                Text {
                    text: model.name
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    elide: Text.ElideRight
                    width: parent.width
                }

                Text {
                    text: model.seasonCount + " seasons · " + model.episodeCount + " episodes"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }
            }

            FocusRing {
                visible: showDelegate.ListView.isCurrentItem && showsList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    showsList.currentIndex = index
                    showsList.forceActiveFocus()
                }
                onDoubleClicked: {
                    showsList.currentIndex = index
                    if (localVideos) {
                        localVideos.selectShow(index)
                        localVideosScreen._selectedShowIndex = index
                        localVideosScreen.currentView = "seasons"
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: showsList.count === 0
            text: "No shows found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ── Seasons ListView ──────────────────────────────────────────────────────
    ListView {
        id: seasonsList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: localVideos ? localVideos.seasonsModel : null
        clip: true
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "seasons"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0) {
                    localVideos.selectSeason(currentIndex)
                    localVideosScreen._selectedSeasonIndex = currentIndex
                    localVideosScreen.currentView = "episodes"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.currentView = "shows"
            }
        }

        delegate: Item {
            id: seasonDelegate

            width: seasonsList.width
            height: root.vpx(72)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: seasonDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: seasonDelegate.ListView.isCurrentItem && seasonsList.activeFocus
                    ? Theme.focusScale : 1.0
                Behavior on scale {
                    NumberAnimation { duration: Theme.focusScaleDuration; easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    NumberAnimation { duration: Theme.animDurationFast }
                }
            }

            Column {
                anchors {
                    left: parent.left
                    leftMargin: root.vpx(16)
                    right: parent.right
                    rightMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                spacing: root.vpx(4)

                Text {
                    text: model.name
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeHeading)
                    elide: Text.ElideRight
                    width: parent.width
                }

                Text {
                    text: model.episodeCount + " episodes"
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                }
            }

            FocusRing {
                visible: seasonDelegate.ListView.isCurrentItem && seasonsList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    seasonsList.currentIndex = index
                    seasonsList.forceActiveFocus()
                }
                onDoubleClicked: {
                    seasonsList.currentIndex = index
                    if (localVideos) {
                        localVideos.selectSeason(index)
                        localVideosScreen._selectedSeasonIndex = index
                        localVideosScreen.currentView = "episodes"
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: seasonsList.count === 0
            text: "No seasons found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ── Episodes ListView ─────────────────────────────────────────────────────
    ListView {
        id: episodesList

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            topMargin: root.vpx(16)
            leftMargin: root.vpx(32)
            rightMargin: root.vpx(32)
            bottomMargin: root.vpx(32)
        }

        model: localVideos ? localVideos.episodesModel : null
        clip: true
        keyNavigationEnabled: true
        highlightMoveDuration: Theme.animDurationFast
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.65

        visible: localVideosScreen.currentView === "episodes"

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                if (localVideos && currentIndex >= 0 && currentItem) {
                    localVideos.playVideo(currentItem.episodePath, localVideos.getResumePosition(currentItem.episodePath))
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                localVideosScreen.currentView = "seasons"
            }
        }

        delegate: Item {
            id: episodeDelegate

            readonly property string episodePath: model.path

            width: episodesList.width
            height: root.vpx(64)

            Rectangle {
                anchors.fill: parent
                color: Theme.colorSecondary
                opacity: episodeDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                radius: root.vpx(Theme.focusRingRadius)

                scale: episodeDelegate.ListView.isCurrentItem && episodesList.activeFocus
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
                    leftMargin: root.vpx(16)
                    verticalCenter: parent.verticalCenter
                }
                text: model.title
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
                width: parent.width - root.vpx(32)
            }

            FocusRing {
                visible: episodeDelegate.ListView.isCurrentItem && episodesList.activeFocus
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    episodesList.currentIndex = index
                    episodesList.forceActiveFocus()
                }
                onDoubleClicked: {
                    episodesList.currentIndex = index
                    if (localVideos) {
                        localVideos.playVideo(model.path, localVideos.getResumePosition(model.path))
                    }
                }
            }
        }

        // Empty state
        Text {
            anchors.centerIn: parent
            visible: episodesList.count === 0
            text: "No episodes found."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
