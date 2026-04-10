# Task 001 — Rewrite SettingsScreen with tabbed layout

## Context

The current SettingsScreen (`qml/screens/SettingsScreen.qml`, 745 lines) is a flat vertical ListView with header rows as section dividers. It needs to be restructured into a tabbed layout with horizontal tab strip, optional vertical sidebar for sub-categories, and a settings content list.

## Objective

Replace the single-list layout with a three-zone design:
1. **Tab strip** — horizontal row of text labels at the top
2. **Sidebar** — vertical list of sub-categories on the left (only for tabs that have sub-categories)
3. **Content list** — the settings ListView on the right (or full-width when no sidebar)

## Tab Structure

```
Games (has sidebar)
├── Paths:      ROMs Directory, Cores Directory
├── Retroarch:  RetroArch Command, System Cores..., RetroArch Hotkeys,
│               Rescan Library, Clear Retro Games History,
│               Video Snap Autoplay, Video Snap Delay
└── Moonlight:  Moonlight Command, Host, Open Moonlight

Plex (no sidebar — full-width list)
    Sign in with Plex, Test Connection, Server, User,
    Music Library, Video Player, Auto-Skip Intro

Controller (no sidebar — full-width list)
    Button Layout, Map Controller, Reset to Default

User Interface (has sidebar)
├── Appearance:   Network Indicator
└── Visible Tabs: Retro Games, PC Games, Moonlight, Plex Media, Plex Music

Advanced (no sidebar — full-width list)
    Browser Command
```

## Layout Spec

### Tab strip
- Full width, anchored below a header bar that says "Settings" (keep existing header bar style).
- Each tab is a text label in a horizontal Row, spaced evenly or with fixed padding.
- Underline or highlight on the active tab (use `Theme.colorPrimary` for active, `Theme.colorTextDim` for inactive). A simple 2px bottom-border accent line on the active tab is sufficient.
- Font: `Theme.fontFamily`, `Theme.fontSizeBody`.
- The tab strip itself is a FocusScope. Left/Right changes the selected tab. Down moves focus into the sidebar (if present) or the content list.
- B from the tab strip emits `back()`.

### Sidebar (Games, User Interface tabs only)
- Fixed width (~180 vpx), anchored left below tab strip, full height to bottom.
- Background: `Theme.colorSecondary` (subtle contrast from the main `Theme.colorBackground`).
- Each sub-category is a text label. The active sub-category uses `Theme.colorPrimary` text + a left accent bar or highlight; inactive uses `Theme.colorTextDim`.
- Up/Down navigates sub-categories and immediately switches the content list to show that sub-category's settings.
- Right or A from sidebar → focus moves to the content list.
- B from sidebar → focus moves to the tab strip.
- Left from sidebar → focus moves to the tab strip.

### Content list
- Anchored to the right of the sidebar (or full-width if no sidebar), below the tab strip, to parent bottom.
- This is essentially the existing `settingsList` ListView, but filtered to only show settings for the current tab + sub-category.
- Reuse all existing delegate components: headerComp, textInputComp, toggleComp, buttonComp, sliderComp, selectComp, cycleComp. No headers needed in the content list since the sidebar already identifies the section.
- Up/Down navigates settings rows. Keys.onPressed with `_moveFocus` pattern (no headers to skip now, but keep the pattern in case future items need skipping).
- B from content list → focus to sidebar (if sidebar exists) or tab strip.
- Left from content list (when not editing) → focus to sidebar (if sidebar exists) or tab strip.

## Data Model

Replace the flat `_settingsModel` array with a structured object. Use a property like:

```javascript
readonly property var _tabs: [
    {
        name: "Games",
        subcategories: [
            {
                name: "Paths",
                settings: [
                    { type: "text", label: "ROMs Directory", settingKey: "romDirectory" },
                    { type: "text", label: "Cores Directory", settingKey: "coresDirectory" },
                ]
            },
            {
                name: "Retroarch",
                settings: [
                    { type: "text",    label: "RetroArch Command", settingKey: "retroarchCommand" },
                    { type: "button",  label: "System Cores...",   action: "systemCores" },
                    { type: "button",  label: "RetroArch Hotkeys", action: "retroarchHotkeys" },
                    { type: "button",  label: "Rescan Library",    action: "rescan" },
                    { type: "button",  label: "Clear Retro Games History", action: "clearRetroRecent" },
                    { type: "toggle",  label: "Video Snap Autoplay", settingKey: "videoSnapAutoplay" },
                    { type: "slider",  label: "Video Snap Delay",    settingKey: "videoSnapDelayMs",
                      min: 0, max: 5000, step: 100, suffix: "ms" },
                ]
            },
            {
                name: "Moonlight",
                settings: [
                    { type: "text",    label: "Moonlight Command", settingKey: "moonlightCommand" },
                    { type: "select",  label: "Host",              settingKey: "moonlightHost" },
                    { type: "button",  label: "Open Moonlight",    action: "openMoonlight" },
                ]
            }
        ]
    },
    {
        name: "Plex",
        subcategories: null,
        settings: [
            { type: "button",  label: "Sign in with Plex", action: "plexSignIn" },
            { type: "button",  label: "Test Connection",   action: "testPlex" },
            { type: "select",  label: "Server",            settingKey: "plexServer" },
            { type: "select",  label: "User",              settingKey: "plexUser" },
            { type: "select",  label: "Music Library",    settingKey: "musicLibrary" },
            { type: "cycle",   label: "Video Player",      settingKey: "plexPlayer" },
            { type: "toggle",  label: "Auto-Skip Intro",   settingKey: "autoSkipIntro" },
        ]
    },
    {
        name: "Controller",
        subcategories: null,
        settings: [
            { type: "select",  label: "Button Layout",    settingKey: "buttonLayout" },
            { type: "button",  label: "Map Controller",   action: "mapController" },
            { type: "button",  label: "Reset to Default", action: "resetController" },
        ]
    },
    {
        name: "User Interface",
        subcategories: [
            {
                name: "Appearance",
                settings: [
                    { type: "toggle",  label: "Network Indicator", settingKey: "showNetworkIndicator" },
                ]
            },
            {
                name: "Visible Tabs",
                settings: [
                    { type: "toggle",  label: "Retro Games",  settingKey: "showRetroGamesTab" },
                    { type: "toggle",  label: "PC Games",     settingKey: "showPcGamesTab" },
                    { type: "toggle",  label: "Moonlight",    settingKey: "showMoonlightTab" },
                    { type: "toggle",  label: "Plex Media",   settingKey: "showWatchTab" },
                    { type: "toggle",  label: "Plex Music",   settingKey: "showListenTab" },
                ]
            }
        ]
    },
    {
        name: "Advanced",
        subcategories: null,
        settings: [
            { type: "text",  label: "Browser Command",  settingKey: "browserCommand" },
        ]
    }
]
```

Use two state properties to track position:
- `property int _activeTabIndex: 0`
- `property int _activeSubIndex: 0`

Derive the current settings list with a computed helper function:
```javascript
function _currentSettings() {
    var tab = _tabs[_activeTabIndex]
    if (tab.subcategories)
        return tab.subcategories[_activeSubIndex].settings
    return tab.settings
}
```

Assign this to the content ListView's model. Reassign whenever `_activeTabIndex` or `_activeSubIndex` changes.

## Focus Flow

Track which zone has focus with a property:
```javascript
// "tabs" | "sidebar" | "content"
property string _focusZone: "tabs"
```

Focus routing in `onActiveFocusChanged`:
- If sub-screens (SystemCoresScreen, RetroarchHotkeysScreen) are visible, route there.
- Otherwise route to whichever zone is active.

**Tab strip keys:**
- Left/Right: change `_activeTabIndex` (wrap or clamp — clamp is fine)
- Down: set `_focusZone` to "sidebar" if current tab has subcategories, else "content"
- B: emit `back()`

**Sidebar keys:**
- Up/Down: change `_activeSubIndex` (clamp at bounds)
- Right or A: set `_focusZone` to "content"
- Left or B: set `_focusZone` to "tabs"

**Content list keys:**
- Up/Down: navigate settings rows (existing `_moveFocus` pattern, no headers to skip)
- Left (when not editing): set `_focusZone` to "sidebar" if sidebar exists, else "tabs"
- B (when not editing): set `_focusZone` to "sidebar" if sidebar exists, else "tabs"

Write a `_routeFocus()` function that reads `_focusZone` and calls `forceActiveFocus()` on the right element. Call it from `onActiveFocusChanged`, and whenever `_focusZone` changes.

## Preserved Unchanged

- `_getValue(key)` and `_setValue(key, value, label)` functions — no changes.
- `_showToast(msg)` and toast overlay — no changes.
- `showSystemCores()` and `showRetroarchHotkeys()` functions — no changes.
- SystemCoresScreen, RetroarchHotkeysScreen, PlexLoginOverlay — no changes. Their `onBack` handlers should call `_routeFocus()` (or directly focus the content list) instead of `settingsList.forceActiveFocus()`.
- Plex login Connections block — no changes except the dismiss targets (use `_routeFocus()` instead of `settingsList.forceActiveFocus()`).
- All delegate components (textInputComp, toggleComp, buttonComp, sliderComp, selectComp, cycleComp) — preserve exactly as they are, but move them from being nested inside the delegate `Item` to being top-level Components in the file (they'll be referenced by the delegate Loader via id just as before).
- `_librariesVersion` and its Connections block — no changes.

## Non-goals

- Do NOT change any setting component files (SettingTextInput.qml, etc.).
- Do NOT change any backend files.
- Do NOT add new settings or remove existing ones.
- Do NOT change the headerComp delegate — it is no longer used (the sidebar replaces section headers). Remove it from the delegate.

## Caveats

- **Only ONE `Component.onCompleted` per QML scope.** Don't add a second one.
- **Never use `id: root`** — that belongs to the ApplicationWindow.
- Content list `currentIndex` should reset to 0 when `_activeTabIndex` or `_activeSubIndex` changes.
- When changing tabs, reset `_activeSubIndex` to 0.
- The sidebar should visually indicate which sub-category is selected even when the content list has focus (keep the highlight persistent, not just on activeFocus).

## Acceptance criteria

- All five tabs render and are navigable with Left/Right.
- Games and User Interface tabs show sidebar; Plex, Controller, Advanced do not.
- Down from tab strip enters sidebar or content as appropriate.
- All settings are accessible and functional (verify at least: toggle a tab visibility toggle, edit a text input, open System Cores sub-screen, trigger Plex Sign In overlay).
- B from any zone navigates back correctly (content→sidebar→tabs→back).
- All existing tests pass.
