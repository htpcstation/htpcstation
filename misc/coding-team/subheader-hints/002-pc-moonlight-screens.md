# Task 002 — Sub-header hints: SteamGameGrid, SteamGameList, MoonlightAppGrid, MoonlightAppList

## Context

Task 001 established the pattern in `GameGridView.qml` and `GameListView.qml`:
- Button hints removed from `headerBar` (56px)
- Button hints added as a right-aligned `Row` inside `statusBar` (28px sub-header)
  - `anchors.right: parent.right`, `anchors.rightMargin: root.vpx(140)`
  - `anchors.verticalCenter: parent.verticalCenter`
  - `spacing: root.vpx(16)`
  - Each hint: `color: Theme.colorTextDim`, `font.family: Theme.fontFamily`,
    `font.pixelSize: root.vpx(Theme.fontSizeSmall)`

Apply the same pattern to the four screens listed below.

## Objective

For each of the four screens:
1. Read the file fully first.
2. Remove ALL button hint `Text` elements from `headerBar`.
3. Add a right-aligned `Row` of those same hints inside `statusBar`.
4. Keep the left-side sort/status label in `statusBar` unchanged.
5. Keep `statusBar` height at `root.vpx(28)`.

## Scope

- `qml/screens/SteamGameGrid.qml`
- `qml/screens/SteamGameList.qml`
- `qml/screens/MoonlightAppGrid.qml`
- `qml/screens/MoonlightAppList.qml`

## Known hints per screen (verify by reading — do not assume)

**SteamGameGrid** (currently in `headerBar`):
- Scroll: `keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll"` / `"PgUp/PgDn  Scroll"`
- Favorite: `keys.context1Label + "  Favorite"` / `"F1  Favorite"`
- Sort: `keys.context2Label + "  Sort"` / `"F2  Sort"`

**SteamGameList** — read the file; likely same set as SteamGameGrid.

**MoonlightAppGrid** — read the file; likely Sort + Scroll hints.

**MoonlightAppList** — read the file; likely same as MoonlightAppGrid.

## Non-goals / Later

- Do not touch detail views (`SteamGameDetail.qml`, `MoonlightAppDetail.qml`).
- Do not change `statusBar` height.
- Do not introduce a shared component.
- Do not modify any other files.

## Constraints / Caveats

- Right margin must be `root.vpx(140)` — minimum safe distance from global indicators.
- Preserve the `keys.useGamepadLabels` ternary pattern exactly as found.
- Hint ordering in the `Row`: left-to-right should be Scroll → Favorite → Sort
  (least-used rightmost, matching the original right-to-left anchor chain).
