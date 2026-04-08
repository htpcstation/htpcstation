# Task Brief 005 — Add Header Bar to Second-Level Screens

## Context

Third-level screens (e.g. `GameGridView.qml`) already have a header bar:
```qml
Rectangle {
    id: headerBar
    anchors { top: parent.top; left: parent.left; right: parent.right }
    height: root.vpx(56)
    color: Theme.colorSecondary

    Text {
        anchors { left: parent.left; leftMargin: root.vpx(16); verticalCenter: parent.verticalCenter }
        text: "◀  " + someNameProp
        color: Theme.colorText
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeHeading)
    }
}
```
Content below it anchors `top: headerBar.bottom`.

Second-level screens have no header. Their top-level list/content anchors `top: parent.top` with `margins: root.vpx(32)`.

## Objective

Add an identical header bar to all six second-level screens. The header shows the tab name (hardcoded string). Content is pushed down to `headerBar.bottom`.

## Scope — six files, mechanical change each time

### Pattern to apply to each file

1. Add `Rectangle { id: headerBar ... }` immediately before the screen's primary content item (the source/system/library list or the top-level content area).
2. Change the primary content item's top anchor from `top: parent.top` to `top: headerBar.bottom`, and remove the top `margins` (keep left/right/bottom margins unchanged — they stay at `root.vpx(32)` or whatever they currently are).
3. The header text is just the tab name — no `"◀  "` prefix, no hints on the right side.

### Per-file details

**`qml/screens/RetroGamesScreen.qml`**
- Header text: `"Retro Games"`
- Primary content: `ListView { id: systemList }` — currently `top: parent.top`, `margins: root.vpx(32)`
- Change to: `top: headerBar.bottom`, keep `margins: root.vpx(32)` but note that `margins` sets all four sides — split it into explicit `left/right/bottom` margins of `root.vpx(32)` and set `top` anchor to `headerBar.bottom` with no topMargin.
- The `GameGridView`, `GameListView`, `GameDetailView` children anchor `anchors.fill: parent` — they are unaffected (they cover the full screen including the header area, which is correct since they have their own headers).

**`qml/screens/PcGamesScreen.qml`**
- Header text: `"PC Games"`
- Primary content: `ListView { id: sourceList }` — currently `top: parent.top`, `margins: root.vpx(32)`
- Same anchor split as above.
- Child game/detail views use `anchors.fill: parent` — unaffected.

**`qml/screens/MoonlightScreen.qml`**
- Header text: `"Moonlight"`
- Primary content: `ListView { id: sourceList }` — currently `top: parent.top`, `margins: root.vpx(32)`
- Same anchor split.
- Child views use `anchors.fill: parent` — unaffected.

**`qml/screens/WatchScreen.qml`**
- Header text: `"Plex Media"`
- Find the primary content item that anchors `top: parent.top` at the top level of `watchScreen`. This is the library list area (likely a `ListView` or `Item` wrapping it). Apply the same pattern.
- Child views (`PlexMovieGrid`, etc.) use `anchors.fill: parent` — unaffected.

**`qml/screens/ListenScreen.qml`**
- Header text: `"Plex Music"`
- Find the primary top-level content item anchoring `top: parent.top`. Apply the same pattern.
- Child views use `anchors.fill: parent` — unaffected.

**`qml/screens/SettingsScreen.qml`**
- Header text: `"Settings"`
- Find the primary `ListView` or `Item` anchoring `top: parent.top`. Apply the same pattern.
- Sub-screens (`SystemCoresScreen`, `RetroarchHotkeysScreen`) use `anchors.fill: parent` — unaffected.

## Non-goals / Later
- No hints or right-side content in the header (just the tab name).
- No changes to third-level screens.
- No backend changes.

## Constraints / Caveats
- **`id: root` must never be used** in these files. `root.vpx()` refers to the `ApplicationWindow`.
- **`margins` shorthand sets all four sides.** When the list currently uses `margins: root.vpx(32)`, split it into `leftMargin`, `rightMargin`, `bottomMargin` each set to `root.vpx(32)`, and anchor `top: headerBar.bottom` with no `topMargin`. Do not leave a `margins` shorthand alongside explicit anchor overrides — QML will warn.
- Read each file carefully before editing — the exact anchor structure varies slightly between screens.

## Acceptance Criteria
- All six screens show a `Theme.colorSecondary` header bar (height `vpx(56)`) with the tab name in `Theme.fontSizeHeading` at the top when the source/system list is visible.
- The list content starts below the header, not behind it.
- Child views (grid, detail, etc.) that use `anchors.fill: parent` are visually unchanged (they already cover the full screen and have their own headers).
- All 1931 tests still pass.
