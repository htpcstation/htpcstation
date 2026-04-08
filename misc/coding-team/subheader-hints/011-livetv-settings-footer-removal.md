# Task 011 — Remove remaining footer actionBars: LiveTvScreen + SettingsScreen

## Context

Two screens still have a footer `actionBar`. These are the last two in the codebase.

**LiveTvScreen**: footer shows Watch (Accept), Back (Cancel), and Scroll. Accept and
Cancel are universally understood and excluded from hints per project convention. Scroll
is already shown in the `statusBar` sub-header. The footer adds nothing — remove it.

**SettingsScreen**: footer shows Back (Cancel) and Select (Accept). Both are universally
understood. Remove the footer entirely — no hints need to move anywhere.

## Objective

### LiveTvScreen.qml

1. Remove the `actionBar` Rectangle (id: `actionBar`, ~lines 486–528).
2. Fix the three content elements that anchor `bottom: actionBar.top` — change to
   `bottom: parent.bottom`. The three elements are the loading indicator Text, the
   empty state Text, and the `channelList` ListView. Read the file to find exact line
   numbers.

### SettingsScreen.qml

1. Remove the `actionBar` Rectangle (id: `actionBar`, ~lines 648–681).
2. Fix `toastOverlay` anchor: `bottom: actionBar.top` → `bottom: parent.bottom`
   (keep the existing `bottomMargin: root.vpx(16)`).
3. Fix the settings content area that anchors `bottom: actionBar.top` → `bottom: parent.bottom`.
   Read the file to find the exact element.

## Scope

- `qml/screens/LiveTvScreen.qml`
- `qml/screens/SettingsScreen.qml`

## Non-goals

- Do not add any hints anywhere — nothing needs to move to a statusBar.
- Do not change key bindings.
- Do not change any other files.

## Verification

After the change, grep for `actionBar` across all qml/screens/*.qml — zero results
expected.
