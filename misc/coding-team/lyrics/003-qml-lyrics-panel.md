# Task Brief 003 — QML lyrics panel in Now Playing

## Context

`plex.getLyrics(ratingKey, title, grandparentTitle, parentTitle, durationMs)` is now available.
It emits `plex.lyricsReady(ratingKey, lines)` where `lines` is a JS array of `{ms: int, text: string}`.
It emits `plex.lyricsUnavailable(ratingKey)` when no lyrics exist or on error.

For plain-text (unsynced) lyrics, all lines have `ms === -1`.
For LRC (synced) lyrics, `ms` is the timestamp in milliseconds.

The Now Playing view is in `qml/screens/ListenScreen.qml` starting at the comment
`// ── Now Playing view ──────────────────────────────────────────────────────`.

The Now Playing content area (`id: nowPlayingContent`) currently has:
- `nowPlayingArtArea` — left column, fixed width, album art
- `nowPlayingInfoColumn` — a `Column` anchored `left: nowPlayingArtArea.right, right: parent.right`
  containing: track title, artist, album, year, spacer, controls row (◀◀ ▶ ▶▶ ⇄ ↺), spacer,
  progress bar, time display, spacer

The playback state properties live on `homeScreen` (the `HomeScreen` item, accessible from
`ListenScreen` via the `homeScreen` id):
- `homeScreen._nowPlayingTrack` — current track dict (`{ratingKey, title, grandparentTitle, parentTitle, durationMs, ...}`)
- `homeScreen.musicPosition` — current position in ms (updates continuously)
- `homeScreen._playingIndex` — -1 when nothing playing

## Objective

Add a lyrics panel to the right ~40% of `nowPlayingContent`, and wire up fetch + display.

## Scope

**Modified files:**
- `qml/screens/ListenScreen.qml`
- `qml/screens/HomeScreen.qml`

No new files. No Python changes.

## Changes to HomeScreen.qml

Add these properties near the other `_playback*` properties:
```qml
property var    _lyricsLines:     []      // list of {ms, text} — empty = not loaded yet
property bool   _lyricsAvailable: false   // false = unavailable or not yet fetched
property string _lyricsRatingKey: ""      // ratingKey of the track lyrics were fetched for
```

In `_playTrackAtIndex`, after setting `_nowPlayingTrack` and before calling `musicPlayer.play()`,
add:
```qml
_lyricsLines = []
_lyricsAvailable = false
_lyricsRatingKey = ""
if (plex && track.ratingKey) {
    plex.getLyrics(track.ratingKey, track.title,
                   track.grandparentTitle, track.parentTitle, track.durationMs)
}
```

Add `Connections { target: plex }` block (or extend the existing one if present) with:
```qml
function onLyricsReady(ratingKey, lines) {
    if (ratingKey === homeScreen._nowPlayingTrack.ratingKey) {
        homeScreen._lyricsLines = lines
        homeScreen._lyricsAvailable = true
        homeScreen._lyricsRatingKey = ratingKey
    }
}
function onLyricsUnavailable(ratingKey) {
    if (ratingKey === homeScreen._nowPlayingTrack.ratingKey) {
        homeScreen._lyricsLines = []
        homeScreen._lyricsAvailable = false
        homeScreen._lyricsRatingKey = ratingKey
    }
}
```

The `ratingKey` guard prevents a slow response for a previous track from overwriting the
current track's lyrics.

**Important:** Check whether a `Connections { target: plex }` block already exists in
`HomeScreen.qml`. If it does, add the two new handler functions inside it rather than
creating a second block. (QML silently ignores duplicate `Connections` targets in some
versions — only one block per target is safe.)

## Changes to ListenScreen.qml — Now Playing layout

### Split the right side into two columns

Currently `nowPlayingInfoColumn` is a `Column` anchored to fill the full right portion.
Replace it with an `Item` (`id: nowPlayingRightArea`) that fills the same anchor space,
containing two children side by side:

**Left sub-column** (`id: nowPlayingInfoColumn`, ~60% width) — move all existing Column
children into this item unchanged. Change it from a `Column` to an `Item` containing a
`Column` anchored to fill it, so the existing children don't need anchor changes.
Actually the simplest approach: keep `nowPlayingInfoColumn` as a `Column` but give it a
fixed width of `nowPlayingRightArea.width * 0.58` instead of anchoring right to parent.right.

**Right lyrics panel** (`id: lyricsPanel`) — anchored:
```
left: nowPlayingInfoColumn.right
leftMargin: vpx(24)
right: parent.right
top: parent.top
bottom: parent.bottom
```

### Lyrics panel contents

```qml
Item {
    id: lyricsPanel
    // anchors as above

    // ── "No lyrics" placeholder ──────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        visible: homeScreen._lyricsRatingKey !== ""
                 && !homeScreen._lyricsAvailable
        text: "No lyrics available"
        color: Theme.colorTextDim
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeSmall)
    }

    // ── Lyrics list ───────────────────────────────────────────────────────
    ListView {
        id: lyricsView
        anchors.fill: parent
        clip: true
        visible: homeScreen._lyricsAvailable && homeScreen._lyricsLines.length > 0

        model: homeScreen._lyricsLines

        // Active line index: highest index where line.ms <= musicPosition.
        // For plain lyrics (all ms === -1), activeIndex stays -1 (no highlight).
        property int activeIndex: {
            var pos = homeScreen.musicPosition
            var lines = homeScreen._lyricsLines
            var idx = -1
            for (var i = 0; i < lines.length; i++) {
                if (lines[i].ms !== -1 && lines[i].ms <= pos) idx = i
            }
            return idx
        }

        // Auto-scroll to keep active line centred.
        onActiveIndexChanged: {
            if (activeIndex >= 0) {
                positionViewAtIndex(activeIndex, ListView.Center)
            }
        }

        delegate: Text {
            width: lyricsView.width
            text: modelData.text
            color: index === lyricsView.activeIndex
                ? Theme.colorPrimary
                : Theme.colorTextDim
            font.family: Theme.fontFamily
            font.pixelSize: root.vpx(Theme.fontSizeBody)
            wrapMode: Text.Wrap
            topPadding: root.vpx(3)
            bottomPadding: root.vpx(3)

            Behavior on color {
                ColorAnimation { duration: Theme.animDurationFast }
            }
        }
    }
}
```

### Remove the placeholder spacer

Remove the existing `// ── Space reserved for future lyrics toggle ──────────────────`
spacer `Item` at the bottom of `nowPlayingInfoColumn` — it's no longer needed.

## Constraints / Caveats

- `homeScreen` is the id of the `HomeScreen` item — it's accessible from `ListenScreen`
  because `ListenScreen` is a child of `HomeScreen` in the component tree.
- `root.vpx()` is defined on the `ApplicationWindow` (id: `root`) — use it for all sizes.
- `Theme.*` tokens are available globally via the `Theme.qml` singleton.
- Do NOT add `focus: true` or `Keys` handlers to the lyrics panel — it must be purely visual.
- The `lyricsView.activeIndex` property binding re-evaluates on every `musicPosition` change
  (many times per second). Keep the loop simple — the track list is at most ~200 lines.
- `positionViewAtIndex` with `ListView.Center` is the correct Qt call for centring.

## Non-goals
- No scrolling the lyrics panel with the gamepad
- No lyrics for playlist tracks (only album playback triggers `getLyrics`)
- No loading spinner while lyrics are being fetched (panel is simply empty until ready)
