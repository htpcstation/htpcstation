# Task Brief 002 — HomeScreen Two-Level Launcher with Theme Images

## Context

`HomeScreen.qml` currently renders a top tab bar (text labels) + separator + `Loader` content area. The `Loader` always has a `source` set, eagerly loading tab content on every tab switch — this causes UI slowness because Plex tabs make network calls on load.

Task 001 added `settings.themeName` and `settings.themeDir` (a `file://` URL ending in `/`). The `themes/default/` directory contains:
- `home-background.png`
- `retrogames-button.png`
- `pcgames-button.png`
- `moonlight-button.png`
- `plexmedia-button.png`
- `plexmusic-button.png`
- `settings-button.png`

## Objective

Rewrite `HomeScreen.qml` to a two-level UI:

**Level 1 — Launcher (visible when no tab is active):**
- Full-screen background image (`home-background.png`)
- Centered horizontal row of image buttons (one per visible tab)
- Clock + wifi indicator + now-playing text overlaid in the top-right (same position as today)
- `Loader` has `source: ""`

**Level 2 — Tab content (visible after user selects a tab):**
- `Loader.source` set to the tab's QML file
- Launcher visuals hidden
- B (Escape) from content clears `Loader.source`, shows launcher, restores focus to the previously selected button

## Scope — only `qml/screens/HomeScreen.qml`

No other files change in this task.

### Tab data

Replace `_allTabs` with an extended structure that includes the image slug:

```qml
readonly property var _allTabs: [
    { name: "Retro Games", source: "RetroGamesScreen.qml", setting: "showRetroGamesTab", slug: "retrogames" },
    { name: "PC Games",    source: "PcGamesScreen.qml",    setting: "showPcGamesTab",    slug: "pcgames"    },
    { name: "Moonlight",   source: "MoonlightScreen.qml",  setting: "showMoonlightTab",  slug: "moonlight"  },
    { name: "Plex Media",  source: "WatchScreen.qml",      setting: "showWatchTab",       slug: "plexmedia"  },
    { name: "Plex Music",  source: "ListenScreen.qml",     setting: "showListenTab",      slug: "plexmusic"  },
    { name: "Settings",    source: "SettingsScreen.qml",   setting: null,                 slug: "settings"   },
]
```

Settings tab is always visible (no setting gate). Adjust `_initTabs()` accordingly — it currently pushes Settings separately; unify it so all tabs including Settings go through the same loop (check `setting === null` to mean always-visible).

Add a parallel `tabSlugs: []` property alongside `tabNames` and `tabSources`. Populate it in `_initTabs()`.

### State

Add:
```qml
property bool _launcherVisible: true   // true = show launcher, false = show tab content
property int  _activeTab: -1           // index into tabNames of the loaded tab (-1 = none)
```

Remove `currentTab` (it was used to drive the Loader source eagerly — no longer needed). The `_activeTab` replaces it for the purpose of tracking which tab is loaded.

**Important:** `onCurrentTabChanged` triggered the slide-in animation. Remove that handler and the slide-in animation entirely — the launcher replaces the tab-switching UX.

### Layout

**Background (launcher only):**
```qml
Image {
    id: launcherBackground
    anchors.fill: parent
    source: settings ? settings.themeDir + "home-background.png" : ""
    fillMode: Image.PreserveAspectCrop
    visible: homeScreen._launcherVisible
}
```

**Button row (launcher only):**
- `Row` centered on the screen (horizontalCenter + verticalCenter of parent)
- `spacing`: `root.vpx(24)`
- `visible: homeScreen._launcherVisible`
- Each button is a `FocusScope` containing:
  - An `Image` sized to fit (see sizing below)
  - A fallback `Rectangle` + `Text` label shown when `Image.status !== Image.Ready`
  - A `Rectangle` border (focus ring) — red, `border.color: Theme.colorAccent`, `border.width: root.vpx(4)`, `radius: root.vpx(6)`, `color: "transparent"`, `visible: buttonItem.activeFocus`

**Button sizing:** Dynamically fill the available width. Target: buttons fill ~80% of screen width with equal spacing. Compute button width as:
```
buttonWidth = (parent.width * 0.80 - spacing * (count - 1)) / count
```
Use `buttonWidth` for both width and height (square buttons). Clamp to a max of `root.vpx(200)` so they don't get absurdly large with few tabs. Use a `property int _buttonSize` on the Row or compute inline.

**Overlay (always visible, on top of both levels):**
- Clock, wifi indicator, now-playing text — keep their existing anchors (top-right of `homeScreen`). Remove the old `tabBar` Row and `separator` Rectangle entirely.

**Content area:**
- `Item` fills parent, `visible: !homeScreen._launcherVisible`
- Contains the `Loader` (same as today, minus the `source` binding)
- `Loader.source` is set imperatively on tab activation, cleared on return

### Navigation

**Launcher button `Keys.onPressed`:**
```
Left  → move focus to previous button (if index > 0)
Right → move focus to next button (if index < count-1)
Up    → accepted, do nothing
Down  → accepted, do nothing
Accept (keys.isAccept) → activate tab: set _activeTab = index, set Loader.source, set _launcherVisible = false, give Loader.item focus
Cancel (keys.isCancel) → accepted, do nothing (no quit dialog from launcher buttons — Start still handles quit at HomeScreen level)
```

**Return from tab content (B press):**
The existing `returnFocusToTabBar()` function is called when a child screen emits `back()`. Replace its body:
```qml
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
Add `property int _lastFocusedButton: 0` to track which button had focus before entering a tab.

**LB/RB tab switching:** Remove entirely. The launcher replaces tab switching — there is no in-content tab switching in the new model.

**Start/F10 (quit dialog):** Keep as-is at the `HomeScreen` level `Keys.onPressed`.

**X button global play/pause:** Keep as-is.

### Loader wiring

`onLoaded`: keep the `back()` signal connection and `showControllerMapping` forwarding. Remove the `_focusContentOnLoad` logic (no longer needed — focus is given directly after setting source). After setting `contentLoader.source`, use `Qt.callLater` to give focus to `contentLoader.item`.

Remove `_focusContentOnLoad` property entirely.

### Component.onCompleted

There is exactly ONE `Component.onCompleted` in `HomeScreen.qml`. Keep it. Change it to:
```qml
Component.onCompleted: {
    _initTabs()
    Qt.callLater(function() {
        var btn = buttonRepeater.itemAt(0)
        if (btn) btn.forceActiveFocus()
    })
}
```

### Music playback state

All the `MediaPlayer`, `AudioOutput`, music playback functions (`_playAlbum`, `_playNext`, etc.), `_mpvRunning`, lyrics state, and `Connections { target: plex }` — **keep all of these unchanged**. They are global state that child screens depend on. Only the navigation/layout portions of `HomeScreen.qml` change.

## Non-goals / Later
- Animated transition between launcher and tab content
- Vertical button layout
- Theme switcher in Settings UI
- Any changes to tab content screens

## Constraints / Caveats

- **`id: root` must never be used** in this file. `vpx()` is called as `root.vpx()` where `root` is the `ApplicationWindow` — this already works in the existing file.
- **One `Component.onCompleted` per QML scope.** The existing file has one — do not add a second.
- **Tab arrays must be built imperatively** in `Component.onCompleted`, never via bindings to `settings.*`.
- **Image local paths need `"file://"` prefix** — `settings.themeDir` already provides this.
- **Guard context property access:** `settings ? settings.themeDir : ""` — context properties can be null on first render.
- **Signal name conflict rule:** Do not name any signal `<propertyName>Changed`. `_launcherVisible` and `_activeTab` are plain properties, not signals — this is fine.
- **`Loader` source cleared on return** — this destroys the tab's QML component, stopping any network activity. This is intentional.
- **`buttonRepeater` id** — use `id: buttonRepeater` on the `Repeater` inside the button row so `returnFocusToTabBar()` can call `buttonRepeater.itemAt(...)`.
- **Fallback image:** When `Image.status !== Image.Ready` (error or loading), show a `Rectangle` with `color: Theme.colorSurface` and a centered `Text` with the tab name. Both the `Image` and the fallback `Rectangle` should be the same size as the button `FocusScope`. Use `visible: image.status === Image.Ready` on the `Image` and `visible: image.status !== Image.Ready` on the fallback.
- **`fillMode: Image.PreserveAspectCrop`** on the background image so it covers the full screen regardless of aspect ratio.
- **`fillMode: Image.PreserveAspectFit`** on button images so they scale cleanly within the square button area.
- **Remove the old tab bar `Row` (id: `tabBar`), the `separator` Rectangle, and the `contentArea` Item** — replace with the new layout described above. The `ClockDisplay`, `NetworkIndicator`, and now-playing `Text` should be re-anchored directly to `homeScreen` (the `FocusScope` root), not to `tabBar`.
- **`slideInAnimation` and `onCurrentTabChanged`** — remove both entirely.
