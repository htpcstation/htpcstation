# Task 009 — Tab transition opacity fade

> Full spec in `misc/coding-team/ui-redesign/task-sheet.md`.
> Test command: `python3 -m pytest tests/ -q`
> Single file: `qml/screens/HomeScreen.qml`

## Current state

- `_launcherVisible: bool` is the single toggle.
- `launcherBackground` (Image) and `buttonRow` (Row) both have
  `visible: homeScreen._launcherVisible` — hard cut on/off.
- Content `Item` has `visible: !homeScreen._launcherVisible` — hard cut.
- `ClockDisplay`, `NetworkIndicator`, now-playing indicators are siblings
  declared after the content area — they must NOT be affected by the fade.
- `returnFocusToTabBar()` sets `_launcherVisible = true` synchronously.
- The A-press handler sets `contentLoader.source` then `_launcherVisible = false`
  then calls `Qt.callLater` to give focus to the loaded item.

## The approach

Layer opacity on top of the existing `visible` toggle. Keep `_launcherVisible`
as the structural visibility flag (it still controls `focus` on `buttonRow`
and prevents the Loader from receiving input while hidden). Add opacity
properties that animate before the visibility flips.

### New properties

```qml
property real _launcherOpacity: 1.0
property real _contentOpacity:  0.0
```

### Launcher items — add opacity binding + Behavior

On `launcherBackground` (Image):
```qml
opacity: homeScreen._launcherOpacity
Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
```

On `buttonRow` (Row):
```qml
opacity: homeScreen._launcherOpacity
Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
```

### Content item — add opacity binding + Behavior

On the content `Item` (the one wrapping `contentLoader`):
```qml
opacity: homeScreen._contentOpacity
Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
```

### Entering a tab (A-press in `buttonItem.Keys.onPressed`)

Replace the current block:
```qml
// Current:
homeScreen._lastFocusedButton = index
homeScreen._activeTab = index
contentLoader.source = homeScreen.tabSources[index]
homeScreen._launcherVisible = false
Qt.callLater(function() {
    if (contentLoader.item) contentLoader.item.forceActiveFocus()
})
```

With:
```qml
homeScreen._lastFocusedButton = index
homeScreen._activeTab = index
contentLoader.source = homeScreen.tabSources[index]
homeScreen._launcherOpacity = 0.0   // start fade-out
tabEnterTimer.restart()
```

Add a `Timer` (inside `HomeScreen`):
```qml
Timer {
    id: tabEnterTimer
    interval: Theme.animDurationFast   // 150ms — matches fade duration
    onTriggered: {
        homeScreen._launcherVisible = false
        homeScreen._contentOpacity = 1.0   // fade in content
        Qt.callLater(function() {
            if (contentLoader.item) contentLoader.item.forceActiveFocus()
        })
    }
}
```

### Returning to launcher (`returnFocusToTabBar()`)

Replace the current function:
```qml
// Current:
function returnFocusToTabBar() {
    contentLoader.source = ""
    homeScreen._launcherVisible = true
    homeScreen._activeTab = -1
    Qt.callLater(function() {
        var btn = buttonRepeater.itemAt(homeScreen._lastFocusedButton)
        if (btn) btn.forceActiveFocus()
    })
}
```

With:
```qml
function returnFocusToTabBar() {
    homeScreen._contentOpacity = 0.0   // start fade-out
    tabExitTimer.restart()
}

Timer {
    id: tabExitTimer
    interval: Theme.animDurationFast   // 150ms
    onTriggered: {
        contentLoader.source = ""
        homeScreen._activeTab = -1
        homeScreen._launcherVisible = true
        homeScreen._launcherOpacity = 1.0   // fade in launcher
        Qt.callLater(function() {
            var btn = buttonRepeater.itemAt(homeScreen._lastFocusedButton)
            if (btn) btn.forceActiveFocus()
        })
    }
}
```

## Constraints / Caveats

- `ClockDisplay`, `NetworkIndicator`, `nowPlayingIndicator`, `playPauseHint`
  are declared after the content `Item` in the file and are direct children
  of `HomeScreen` (not children of the fading items). They must NOT be
  moved or given opacity bindings — they are unaffected by design.
- `buttonRow.focus: homeScreen._launcherVisible` must remain — this is what
  prevents the button row from receiving input while hidden. Do not change it.
- `contentLoader.source` is set BEFORE the fade starts (in the A-press
  handler) so the Loader has the full 150ms to begin loading the QML file
  while the launcher fades out. Do not move it into the timer.
- `_launcherOpacity` must be reset to `1.0` before `_launcherVisible` is
  set to `true` in `tabExitTimer` — otherwise the launcher appears invisible
  when it becomes visible again.
- `_contentOpacity` must be reset to `0.0` before `_launcherVisible` is set
  to `false` in `tabEnterTimer` — it already is (default is 0.0), but if
  the user rapidly presses B then A, the timer may fire with stale state.
  Add a guard: in `tabEnterTimer.onTriggered`, only proceed if
  `!homeScreen._launcherVisible` is about to become true (i.e. the tab is
  still being entered). Simplest guard: check `homeScreen._activeTab !== -1`.
- `Theme.animDurationFast` is 150ms — use it for both timers and both
  Behaviors so the fade duration matches exactly.
- No Python files change in this task.
- All tests must pass.
