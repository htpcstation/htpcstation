import QtQuick
import ".."
import "../components"

// Listen section screen — Plex music library browser.
//
// Two views:
//   "artists"  — grid of artists from the Plex music library
//   "detail"   — artist detail view showing album list
//
// Focus flow:
//   Enter ListenScreen → artistGrid gets focus (after library is selected)
//   D-pad               — navigate artist grid / album list
//   A (Return)          — select artist → show album list
//                         select album → store ratingKey (track list: next task)
//   B (Escape)          — from "artists": emit back() to return to tab bar
//                         from "detail":  return to "artists" view
FocusScope {
    id: listenScreen

    // Emit when B (Escape) is pressed from the top-level view so HomeScreen
    // can return focus to the tab bar.
    signal back()

    // Emitted when the user selects an artist (for task 004 to connect).
    signal artistSelected(string ratingKey)

    // Only process input when this screen is active.
    enabled: focus

    // Current view: "artists" or "detail"
    property string currentView: "artists"

    // Section key of the music library (set on first load).
    property string _musicSectionKey: ""

    // True while artists are loading (set false when artistsModel arrives).
    property bool _loading: true

    // True if no music library was found in Plex.
    property bool _noLibrary: false

    // Prevent redundant library lookups when re-entering the tab.
    property bool _initialized: false

    // Selected artist ratingKey (set when user selects an artist).
    property string _selectedArtistKey: ""

    // Artist detail data and album list (populated when entering detail view).
    property var _artistData: ({})
    property var _albums: []

    // Selected album ratingKey (stored for the next task — track list).
    property string _selectedAlbumKey: ""

    // ── Try to find and select the music library ────────────────────────────
    function _trySelectMusicLibrary() {
        if (_musicSectionKey) return  // already selected
        if (!plex || !settings) return

        // Wait until libraries are loaded — selectLibrary needs the
        // libraries model to resolve the section type.  If we call it
        // before libraries are loaded, section_type is "" and the
        // artist cache/API branch never runs.
        var libs = plex.getLibraryList()
        if (libs.length === 0) return  // not loaded yet — wait for onLibrariesModelChanged

        var configuredKey = settings.musicLibraryKey
        if (configuredKey) {
            // Verify the configured library still exists
            for (var i = 0; i < libs.length; i++) {
                if (libs[i].sectionKey === configuredKey && libs[i].type === "artist") {
                    _musicSectionKey = configuredKey
                    _noLibrary = false
                    plex.selectLibrary(configuredKey)
                    return
                }
            }
            // Configured library not found — fall through to auto-select
        }

        // No library configured or configured one not found — fall back to first artist library
        for (var j = 0; j < libs.length; j++) {
            if (libs[j].type === "artist") {
                _musicSectionKey = libs[j].sectionKey
                _noLibrary = false
                plex.selectLibrary(libs[j].sectionKey)
                // Auto-save the selection
                if (settings) settings.setMusicLibraryKey(libs[j].sectionKey)
                return
            }
        }

        _loading = false
        _noLibrary = true
    }

    // ── Connections ───────────────────────────────────────────────────────────
    Connections {
        target: plex
        function onArtistsModelChanged() {
            listenScreen._loading = false
        }
        function onLibrariesModelChanged() {
            listenScreen._trySelectMusicLibrary()
        }
    }

    // ── Focus routing ─────────────────────────────────────────────────────────
    function _routeFocus() {
        if (currentView === "artists") {
            artistGrid.forceActiveFocus()
        } else if (currentView === "detail") {
            albumList.forceActiveFocus()
        }
    }

    onActiveFocusChanged: {
        if (activeFocus) {
            if (!_initialized) {
                _initialized = true
                _loading = true
                _noLibrary = false
                if (plex) {
                    plex.refresh()
                    _trySelectMusicLibrary()
                }
            }
            _routeFocus()
        }
    }

    onCurrentViewChanged: {
        if (currentView === "detail" && _selectedArtistKey) {
            _artistData = plex.getArtist(_selectedArtistKey)
            _albums = plex.getArtistAlbums(_selectedArtistKey)
            // Set initial focus to first non-header entry (index 1, since index 0 is the first header)
            var firstAlbum = 0
            for (var i = 0; i < _albums.length; i++) {
                if (_albums[i].type !== "header") {
                    firstAlbum = i
                    break
                }
            }
            albumList.currentIndex = firstAlbum
        }
        _routeFocus()
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
            text: "◀  Music"
            color: Theme.colorText
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }
    }

    // ── Artist grid ───────────────────────────────────────────────────────────
    // Cell dimensions: portrait poster (160w × 240h)
    readonly property int _targetCellW: 160
    readonly property int _cellH: 240
    readonly property int _cellSpacing: 12

    GridView {
        id: artistGrid

        anchors {
            top: headerBar.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: root.vpx(16)
        }

        model: plex ? plex.artistsModel : null
        clip: true
        focus: true
        visible: listenScreen.currentView === "artists"

        readonly property int _columns: Math.max(1, Math.floor(width / root.vpx(listenScreen._targetCellW + listenScreen._cellSpacing)))
        cellWidth: _columns > 0 ? Math.floor(width / _columns) : root.vpx(listenScreen._targetCellW + listenScreen._cellSpacing)
        cellHeight: root.vpx(listenScreen._cellH + listenScreen._cellSpacing)

        // Smooth highlight movement
        highlightMoveDuration: Theme.animDurationFast

        Keys.onPressed: (event) => {
            if (keys.isAccept(event)) {
                event.accepted = true
                var item = artistGrid.currentItem
                if (item) {
                    listenScreen._selectedArtistKey = item.artistRatingKey
                    listenScreen.artistSelected(item.artistRatingKey)
                    listenScreen.currentView = "detail"
                }
            } else if (keys.isCancel(event)) {
                event.accepted = true
                listenScreen.back()
            } else if (event.key === Qt.Key_Up && artistGrid.currentIndex < artistGrid._columns) {
                event.accepted = true
                listenScreen.back()
            }
        }

        // ── Loading indicator ────────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._loading
            text: "Loading..."
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── No library message ───────────────────────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: listenScreen._noLibrary && !listenScreen._loading
            text: "No music library found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Empty state (loaded but no artists) ──────────────────────────────
        Text {
            anchors.centerIn: parent
            visible: !listenScreen._loading && !listenScreen._noLibrary && artistGrid.count === 0
            text: "No artists found"
            color: Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeHeading)
        }

        // ── Artist tile delegate ─────────────────────────────────────────────
        delegate: Item {
            id: tileRoot

            // Expose ratingKey so the key handler can read it.
            readonly property string artistRatingKey: model.ratingKey

            width: artistGrid.cellWidth
            height: artistGrid.cellHeight

            // Inner container — slightly inset from the cell to create spacing
            Rectangle {
                id: tileCard

                anchors {
                    fill: parent
                    margins: root.vpx(listenScreen._cellSpacing / 2)
                }

                color: Theme.colorSecondary
                radius: root.vpx(Theme.focusRingRadius)

                // Subtle highlight when focused
                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.colorPrimary
                    opacity: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus ? 0.15 : 0.0

                    Behavior on opacity {
                        NumberAnimation { duration: Theme.animDurationFast }
                    }
                }

                // ── Poster image area ────────────────────────────────────────
                Item {
                    id: posterArea

                    anchors {
                        top: parent.top
                        left: parent.left
                        right: parent.right
                    }
                    // Poster takes ~80% of the card height
                    height: Math.round(parent.height * 0.80)

                    // Placeholder shown when there is no poster or while loading
                    Rectangle {
                        anchors.fill: parent
                        color: Qt.darker(Theme.colorSecondary, 1.4)
                        radius: root.vpx(Theme.focusRingRadius)
                        visible: posterImage.status !== Image.Ready || model.imageLocal === ""

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.vpx(8)
                            text: model.title || ""
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
                        source: model.imageLocal || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        // Limit decoded resolution to the display size for performance
                        sourceSize.width: root.vpx(listenScreen._targetCellW)
                        sourceSize.height: Math.round(root.vpx(listenScreen._cellH) * 0.80)
                        visible: status === Image.Ready && model.imageLocal !== ""
                        clip: true
                    }
                }

                // ── Artist name label ────────────────────────────────────────
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
                    text: model.title || ""
                    color: Theme.colorText
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // ── Genre subtitle ───────────────────────────────────────────
                Text {
                    anchors {
                        top: titleText.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: root.vpx(6)
                        rightMargin: root.vpx(6)
                        topMargin: root.vpx(2)
                    }
                    text: model.genre || ""
                    color: Theme.colorTextDim
                    font.family: Theme.fontFamily
                    font.pixelSize: root.vpx(Theme.fontSizeSmall)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }

                // Focus ring — visible when this tile is the current item
                FocusRing {
                    visible: tileRoot.GridView.isCurrentItem && artistGrid.activeFocus
                }
            }
        }
    }

    // ── Artist detail view ────────────────────────────────────────────────────
    Item {
        id: artistDetailView

        anchors.fill: parent
        visible: listenScreen.currentView === "detail"

        // ── Detail header bar ────────────────────────────────────────────────
        Rectangle {
            id: detailHeaderBar

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
                text: "◀  " + (listenScreen._artistData.title || "")
                color: Theme.colorText
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
                elide: Text.ElideRight
            }
        }

        // ── Album list ───────────────────────────────────────────────────────
        ListView {
            id: albumList

            anchors {
                top: detailHeaderBar.bottom
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                margins: root.vpx(8)
            }

            model: listenScreen._albums
            clip: true
            focus: false
            keyNavigationEnabled: false
            highlightMoveDuration: Theme.animDurationFast

            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    var next = albumList.currentIndex + 1
                    while (next < listenScreen._albums.length && listenScreen._albums[next].type === "header") next++
                    if (next < listenScreen._albums.length) albumList.currentIndex = next
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    var prev = albumList.currentIndex - 1
                    while (prev >= 0 && listenScreen._albums[prev].type === "header") prev--
                    if (prev >= 0) albumList.currentIndex = prev
                } else if (keys.isAccept(event)) {
                    event.accepted = true
                    var album = listenScreen._albums[albumList.currentIndex]
                    if (album && album.type === "album") {
                        listenScreen._selectedAlbumKey = album.ratingKey
                    }
                } else if (keys.isCancel(event)) {
                    event.accepted = true
                    listenScreen.currentView = "artists"
                }
            }

            // ── Empty state ──────────────────────────────────────────────────
            Text {
                anchors.centerIn: parent
                visible: listenScreen.currentView === "detail" && listenScreen._albums.length === 0
                text: "No albums found"
                color: Theme.colorTextDim
                font.family: Theme.fontFamily
                font.pixelSize: root.vpx(Theme.fontSizeHeading)
            }

            // ── Album row delegate ───────────────────────────────────────────
            delegate: Item {
                id: albumDelegate

                property bool isHeader: modelData.type === "header"

                width: albumList.width
                height: isHeader ? root.vpx(40) : root.vpx(96)

                // ── Section header ───────────────────────────────────────────
                Item {
                    anchors.fill: parent
                    visible: albumDelegate.isHeader

                    Text {
                        anchors {
                            left: parent.left
                            leftMargin: root.vpx(8)
                            bottom: parent.bottom
                            bottomMargin: root.vpx(6)
                        }
                        text: modelData.title || ""
                        color: Theme.colorTextDim
                        font.family: Theme.fontFamily
                        font.pixelSize: root.vpx(Theme.fontSizeSmall)
                        font.bold: true
                    }

                    Rectangle {
                        anchors {
                            left: parent.left
                            right: parent.right
                            bottom: parent.bottom
                            leftMargin: root.vpx(8)
                            rightMargin: root.vpx(8)
                        }
                        height: 1
                        color: Theme.colorTextDim
                        opacity: 0.3
                    }
                }

                // ── Album row ────────────────────────────────────────────────────────────
                Item {
                    anchors.fill: parent
                    visible: !albumDelegate.isHeader

                    // Highlight background for focused item
                    Rectangle {
                        anchors.fill: parent
                        color: Theme.colorSecondary
                        opacity: albumDelegate.ListView.isCurrentItem ? 1.0 : 0.0
                        radius: root.vpx(Theme.focusRingRadius)

                        Behavior on opacity {
                            NumberAnimation { duration: Theme.animDurationFast }
                        }
                    }

                    Row {
                        anchors {
                            left: parent.left
                            right: parent.right
                            leftMargin: root.vpx(8)
                            rightMargin: root.vpx(8)
                            verticalCenter: parent.verticalCenter
                        }
                        spacing: root.vpx(12)

                        // ── Album art thumbnail ──────────────────────────
                        Item {
                            width: root.vpx(80)
                            height: root.vpx(80)

                            // Placeholder shown when there is no art or while loading
                            Rectangle {
                                anchors.fill: parent
                                color: Qt.darker(Theme.colorSecondary, 1.4)
                                radius: root.vpx(Theme.focusRingRadius)
                                visible: albumArt.status !== Image.Ready || !modelData.posterLocal

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - root.vpx(8)
                                    text: modelData.title || ""
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
                                id: albumArt

                                anchors.fill: parent
                                source: modelData.posterLocal || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                sourceSize.width: root.vpx(80)
                                sourceSize.height: root.vpx(80)
                                visible: status === Image.Ready && modelData.posterLocal
                                clip: true
                            }
                        }

                        // ── Album title and subtitle ─────────────────
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: root.vpx(4)
                            width: parent.width - root.vpx(80) - root.vpx(12)

                            Text {
                                width: parent.width
                                text: modelData.title || ""
                                color: albumDelegate.ListView.isCurrentItem
                                    ? Theme.colorText
                                    : Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeBody)
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }

                            Text {
                                width: parent.width
                                text: {
                                    var yr = modelData.year || ""
                                    var cnt = modelData.leafCount || 0
                                    var trackStr = cnt === 1 ? "1 track" : (cnt + " tracks")
                                    return yr ? (yr + " · " + trackStr) : trackStr
                                }
                                color: Theme.colorTextDim
                                font.family: Theme.fontFamily
                                font.pixelSize: root.vpx(Theme.fontSizeSmall)
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }
                        }
                    }

                    // Focus ring
                    FocusRing {
                        visible: albumDelegate.ListView.isCurrentItem && albumList.activeFocus
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            albumList.currentIndex = index
                            albumList.forceActiveFocus()
                        }
                        onDoubleClicked: {
                            albumList.currentIndex = index
                            var album = listenScreen._albums[index]
                            if (album && album.type === "album") {
                                listenScreen._selectedAlbumKey = album.ratingKey
                            }
                        }
                    }
                }
            }
        }
    }
}
