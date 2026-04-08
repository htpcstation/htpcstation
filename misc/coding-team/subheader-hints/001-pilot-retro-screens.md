# Task 001 — Sub-header hints pilot: GameGridView + GameListView

## Context

Global status indicators (clock, network, now playing) live in `HomeScreen.qml` and are
anchored to the top-right of the screen at all times. Third-level screens currently place
button hints (Sort, Scroll, etc.) in their `headerBar` (also top-right), causing visual
overlap with those indicators.

The fix: move all button hints out of `headerBar` and into the existing `statusBar`
(the 28px sub-header below the main header). The `statusBar` already shows sort info on
the left; hints go on the right.

This task covers the two pilot screens. The pattern established here will be replicated
across all remaining third-level screens in subsequent tasks.

## Objective

In `GameGridView.qml` and `GameListView.qml`:

1. **Remove** all button hint `Text` elements from `headerBar` (the 56px bar).
   - `GameGridView`: remove `sortHint` and `scrollHint`
   - `GameListView`: inspect and remove equivalent hints (same pattern expected)
2. **Add** a right-aligned `Row` of hints inside `statusBar`:
   - Anchored: `anchors.right: parent.right`, `anchors.rightMargin: root.vpx(140)`,
     `anchors.verticalCenter: parent.verticalCenter`
   - Spacing: `root.vpx(16)` between hint items
   - Each hint is a `Text` element matching the existing dim-text style:
     `color: Theme.colorTextDim`, `font.family: Theme.fontFamily`,
     `font.pixelSize: root.vpx(Theme.fontSizeSmall)`
3. **Keep** the existing left-side sort label in `statusBar` exactly as-is.
4. The `statusBar` height stays at `root.vpx(28)` — do not increase it.

## Scope

- `qml/screens/GameGridView.qml`
- `qml/screens/GameListView.qml`

Read `GameListView.qml` first to confirm its current hint structure before editing.

## Hints to move (GameGridView)

| Hint text (gamepad) | Hint text (keyboard) |
|---|---|
| `keys.context2Label + "  Sort"` | `"F2  Sort"` |
| `keys.pageUpLabel + "/" + keys.pageDownLabel + "  Scroll"` | `"PgUp/PgDn  Scroll"` |

Preserve the `keys.useGamepadLabels` ternary pattern exactly.

## Non-goals / Later

- Do not touch `GameDetailView.qml` — it uses a footer `actionBar` intentionally.
- Do not change the `statusBar` height.
- Do not introduce a shared component — inline Text elements only.
- Do not add a `showButtonHints` config toggle (later task).
- Do not change any other files.

## Constraints / Caveats

- Right margin of `root.vpx(140)` is the minimum safe distance from the global indicators.
  Do not use a smaller value.
- The `statusBar` is only 28px tall. Keep hint font at `fontSizeSmall` (14px design units).
  Vertical centering is critical — use `anchors.verticalCenter: parent.verticalCenter` on
  both the left Row and the right Row.
- `GameListView.qml` may have a different set of hints — read it first and move whatever
  hints are currently in its `headerBar`.
