# Task 004 — Sub-header hints: RecentlyPlayedGrid, RecentlyPlayedList, LiveTvScreen

## Context

Tasks 001–003 established and validated the pattern across 14 screens:
- Button hints removed from `headerBar` (56px)
- Button hints added as a right-aligned `Row` inside `statusBar` (28px sub-header)
  - `anchors.right: parent.right`, `anchors.rightMargin: root.vpx(140)`
  - `anchors.verticalCenter: parent.verticalCenter`
  - `spacing: root.vpx(16)`
  - Each hint: `color: Theme.colorTextDim`, `font.family: Theme.fontFamily`,
    `font.pixelSize: root.vpx(Theme.fontSizeSmall)`

Apply the same pattern to the three remaining screens.

## Objective

For each of the three screens:
1. Read the file fully first.
2. Remove ALL button hint `Text` elements from `headerBar`.
3. Add a right-aligned `Row` of those same hints inside `statusBar`.
4. Keep the left-side sort/status label in `statusBar` unchanged.
5. Keep `statusBar` height at `root.vpx(28)`.
6. If a screen has no `statusBar`, add one (28px, `color: Qt.darker(Theme.colorSecondary, 1.3)`)
   with an appropriate static label on the left, and update the content area anchor from
   `headerBar.bottom` to `statusBar.bottom`.

## Scope

- `qml/screens/RecentlyPlayedGrid.qml`
- `qml/screens/RecentlyPlayedList.qml`
- `qml/screens/LiveTvScreen.qml`

## Hints per screen (verify by reading — do not assume)

Read each file to find what hints currently exist in `headerBar`. Common patterns seen
in other screens: Scroll, Sort, Favorite, My List.

`LiveTvScreen.qml` may have a different structure — it is a live TV browser, not a
standard grid/list. Read it carefully before editing.

## Non-goals / Later

- Do not touch `RecentlyPlayedDetail.qml`.
- Do not change `statusBar` height.
- Do not introduce a shared component.
- Do not modify any other files.

## Constraints / Caveats

- Right margin must be `root.vpx(140)`.
- Preserve the `keys.useGamepadLabels` ternary pattern exactly as found.
- Hint ordering in the `Row`: left-to-right should be Scroll → Favorite/My List → Sort
  (matching the pattern from prior tasks).
