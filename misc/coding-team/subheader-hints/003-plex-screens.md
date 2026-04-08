# Task 003 — Sub-header hints: Plex screens (8 files)

## Context

Tasks 001 and 002 established and validated the pattern:
- Button hints removed from `headerBar` (56px)
- Button hints added as a right-aligned `Row` inside `statusBar` (28px sub-header)
  - `anchors.right: parent.right`, `anchors.rightMargin: root.vpx(140)`
  - `anchors.verticalCenter: parent.verticalCenter`
  - `spacing: root.vpx(16)`
  - Each hint: `color: Theme.colorTextDim`, `font.family: Theme.fontFamily`,
    `font.pixelSize: root.vpx(Theme.fontSizeSmall)`

Apply the same pattern to all 8 Plex screens listed below.

## Objective

For each of the eight screens:
1. Read the file fully first.
2. Remove ALL button hint `Text` elements from `headerBar`.
3. Add a right-aligned `Row` of those same hints inside `statusBar`.
4. Keep the left-side sort/status label in `statusBar` unchanged.
5. Keep `statusBar` height at `root.vpx(28)`.

## Scope

- `qml/screens/PlexMovieGrid.qml`
- `qml/screens/PlexMovieList.qml`
- `qml/screens/PlexShowGrid.qml`
- `qml/screens/PlexShowList.qml`
- `qml/screens/PlexOnDeckGrid.qml`
- `qml/screens/PlexOnDeckList.qml`
- `qml/screens/PlexArtistGrid.qml`
- `qml/screens/PlexArtistList.qml`

## Hints per screen (verify by reading — do not assume)

**PlexMovieGrid** (known from earlier inspection):
- My List: `keys.context1Label + "  My List"` / `"F1  My List"`
- Sort/Filter: `keys.context2Label + "  Sort / Filter"` / `"F2  Sort / Filter"`

**All others** — read each file; hints vary. Common patterns:
- Scroll: `keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll"` / `"PgUp/PgDn  Scroll"`
- My List / Watchlist / Favorite: `keys.context1Label + "  ..."` / `"F1  ..."`
- Sort / Filter: `keys.context2Label + "  Sort"` or `"  Sort / Filter"` / `"F2  ..."`

## Hint ordering in the Row

Left-to-right: Scroll → My List/Watchlist/Favorite → Sort/Filter  
(matches the original right-to-left anchor chain: Sort was rightmost)

## Non-goals / Later

- Do not touch detail views (`PlexMovieDetail.qml`, `PlexShowDetail.qml`).
- Do not change `statusBar` height.
- Do not introduce a shared component.
- Do not modify any other files.

## Constraints / Caveats

- Right margin must be `root.vpx(140)`.
- Preserve the `keys.useGamepadLabels` ternary pattern exactly as found.
- Some Plex screens may have a `_loading` state indicator in the `statusBar` — leave it
  on the left side, do not remove it.
