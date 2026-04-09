# UI Redesign — Task Sheet

> Session resume reference. All tasks are in dependency order.
> Working directory: `/home/thwonp/opencode/htpcstation`
> Plan directory: `misc/coding-team/ui-redesign/`
> Test command: `python3 -m pytest tests/ -q`

---

## Status

| Task | Title | Status |
|------|-------|--------|
| 006  | Theme foundation | pending |
| 007  | Focus scale animation | pending |
| 008  | ListView highlight centering | pending |
| 009  | Tab transition opacity fade | pending |

---

## Task 006 — Theme foundation
**Files:** `qml/Theme.qml`, `backend/config.py`, `backend/settings_manager.py`

### A. Palette — replace blue-tinted stack with neutral dark grays

In `Theme.qml`, replace the three `_bg` / `_surface` / `_surfaceHigh` palette
vars:

| Token | Old | New |
|-------|-----|-----|
| `_bg` | `#1a1a2e` | `#111111` |
| `_surface` | `#16213e` | `#1c1c1c` |
| `_surfaceHigh` | `#0f3460` | `#2a2a2a` |

Keep `_accent: "#e94560"` as the hardcoded default (overridable at runtime —
see section C below).

### B. Typography — switch to Liberation Sans + add weight tokens

`Liberation Sans` is confirmed present on this system with Regular and Bold
(`/usr/share/fonts/liberation-sans-fonts/`). It is metrically identical to
Arial and universally available on Linux.

In `Theme.qml`:
```qml
readonly property string fontFamily:       "Liberation Sans"
readonly property int    fontWeightNormal: Font.Normal   // 400
readonly property int    fontWeightBold:   Font.Bold     // 700
```

`font.bold: true` already works everywhere it's used — no QML-wide sweep
needed. The new tokens are for future consistency; existing `font.bold: true`
usages are correct and need not change.

### C. Runtime-overridable accent + focus ring colors

Two new color settings, persisted to `config.json` under the `ui` section.

**`config.py` changes:**

1. Add two new private fields in `__init__` (after `_theme_name`):
   ```python
   self._accent_color: str = "#e94560"      # default accent
   self._focus_ring_color: str = "#e94560"  # default focus ring (same as accent)
   ```

2. Add property + setter for each (same pattern as `theme_name`):
   ```python
   @property
   def accent_color(self) -> str:
       return self._accent_color

   def set_accent_color(self, color: str) -> None:
       """Set the accent color (CSS hex string) and persist."""
       color = color.strip()
       if not color.startswith("#") or len(color) not in (4, 7, 9):
           logger.warning("set_accent_color: invalid value %r — ignored", color)
           return
       self._accent_color = color
       self.save()

   @property
   def focus_ring_color(self) -> str:
       return self._focus_ring_color

   def set_focus_ring_color(self, color: str) -> None:
       """Set the focus ring color (CSS hex string) and persist."""
       color = color.strip()
       if not color.startswith("#") or len(color) not in (4, 7, 9):
           logger.warning("set_focus_ring_color: invalid value %r — ignored", color)
           return
       self._focus_ring_color = color
       self.save()
   ```

3. In `save()`, add to the `"ui"` dict:
   ```python
   "accent_color": self._accent_color,
   "focus_ring_color": self._focus_ring_color,
   ```

4. In `_load()`, inside the `ui` block:
   ```python
   raw_accent = ui.get("accent_color", "").strip()
   if raw_accent.startswith("#") and len(raw_accent) in (4, 7, 9):
       self._accent_color = raw_accent
   raw_focus = ui.get("focus_ring_color", "").strip()
   if raw_focus.startswith("#") and len(raw_focus) in (4, 7, 9):
       self._focus_ring_color = raw_focus
   ```

**`settings_manager.py` changes:**

Add two signals, two Q_PROPERTYs, and two `@Slot` setters following the
exact same pattern as `themeName` / `setThemeName`:

```python
# Signals (add alongside themeNameChanged)
accentColorChanged = Signal()
focusRingColorChanged = Signal()

# Getters
def _get_accent_color(self) -> str:
    return self._config.accent_color

def _get_focus_ring_color(self) -> str:
    return self._config.focus_ring_color

# Q_PROPERTYs (add alongside themeName)
accentColor = Property(str, fget=_get_accent_color, notify=accentColorChanged)
focusRingColor = Property(str, fget=_get_focus_ring_color, notify=focusRingColorChanged)

# Slots
@Slot(str)
def setAccentColor(self, color: str) -> None:
    self._config.set_accent_color(color)
    self.accentColorChanged.emit()

@Slot(str)
def setFocusRingColor(self, color: str) -> None:
    self._config.set_focus_ring_color(color)
    self.focusRingColorChanged.emit()
```

**`Theme.qml` changes — wire runtime colors from `settings`:**

Replace the hardcoded `_accent` palette var and the two semantic tokens that
use it with runtime-overridable versions:

```qml
// Remove the hardcoded _accent palette var.
// Replace colorAccent and colorFocusRing with settings-driven properties:

readonly property color colorAccent:    settings ? settings.accentColor    : "#e94560"
readonly property color colorFocusRing: settings ? settings.focusRingColor : "#e94560"

// colorPrimary and colorTabUnderline already alias colorAccent — no change needed.
// colorHighlight derives from colorAccent — update to use the property:
readonly property color colorHighlight: Qt.rgba(colorAccent.r, colorAccent.g, colorAccent.b, 0.15)
```

Note: `settings` is a context property available globally in QML. The
`? :` guard handles the brief window before `settings` is set.

### D. Focus ring radius — increase from 4 → 10

In `Theme.qml`:
```qml
readonly property int focusRingRadius: 10
```

### Acceptance criteria for Task 006
- App launches with neutral dark gray background (no blue tint).
- `config.json` `ui` section contains `accent_color` and `focus_ring_color`
  keys after first run.
- Calling `settings.setAccentColor("#00ff88")` from QML updates all
  `Theme.colorAccent` usages live (no restart needed).
- Focus rings are visibly rounder.
- All tests pass.

---

## Task 007 — Focus scale animation
**Files:** `qml/components/FocusRing.qml`, and focusable items across all screens.

### Approach

Add a `scale` animation to every focusable item. The `FocusRing` component
already anchors to `parent` — extend it to also drive the parent's scale.

**Problem:** QML components cannot set properties on their parent. Instead,
use a companion pattern: every focusable item that uses `FocusRing` also
declares:

```qml
scale: activeFocus ? 1.05 : 1.0
Behavior on scale {
    NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
}
```

Add two new tokens to `Theme.qml`:
```qml
readonly property real  focusScale:        1.05
readonly property int   focusScaleDuration: 120
```

**Scope of items to update** (apply scale + Behavior to each):
- `HomeScreen.qml` — `buttonItem` FocusScope (the tab buttons)
- `WatchScreen.qml` — library list delegate `FocusScope` (`delegateRoot`)
- `RetroGamesScreen.qml` — system list delegate, game grid/list delegates
- `GameGridView.qml` — grid delegate
- `GameListView.qml` — list delegate
- `ListenScreen.qml` — menu delegate, artist/album/track delegates
- `PlexMovieGrid.qml`, `PlexShowGrid.qml`, `PlexOnDeckGrid.qml` — grid delegates
- `PlexMovieList.qml`, `PlexShowList.qml`, `PlexOnDeckList.qml` — list delegates
- `PlexArtistGrid.qml`, `PlexArtistList.qml` — delegates
- `MoonlightAppGrid.qml`, `MoonlightAppList.qml` — delegates
- `SteamGameGrid.qml`, `SteamGameList.qml` — delegates
- `RecentlyPlayedGrid.qml`, `RecentlyPlayedList.qml` — delegates
- Detail view action buttons (PlexMovieDetail, PlexShowDetail, etc.)

**Caveats:**
- Do NOT apply scale to items inside a `clip: true` parent — the scaled item
  will be clipped at its original bounds. Either remove `clip` from the
  ListView (use `clip: false` and rely on the screen boundary) or apply scale
  only to inner content (e.g. a card `Rectangle`) rather than the delegate
  root.
- Grid delegates that are tightly packed may overlap neighbours at 1.05×.
  Use `z: activeFocus ? 1 : 0` on the delegate to ensure the focused item
  renders on top.
- The `FocusRing` component itself does not need changes — it already
  `anchors.fill: parent` and will scale with the parent automatically.

### Acceptance criteria for Task 007
- Every focusable item smoothly scales up 5% when focused and back when
  unfocused, with a 120ms OutCubic ease.
- No clipping artifacts on any screen.
- Focused grid items render above their neighbours.
- All tests pass.

---

## Task 008 — ListView highlight centering
**Files:** All QML files containing `ListView` or `GridView` declarations.

### The problem
No ListView/GridView has `preferredHighlightBegin` / `preferredHighlightEnd`
set. The focused item skates to the top or bottom edge before the list
scrolls — the focus indicator moves, not the content.

### The fix
Add to every `ListView` and `GridView`:

```qml
highlightRangeMode:      ListView.ApplyRange
preferredHighlightBegin: height * 0.35
preferredHighlightEnd:   height * 0.65
```

`ApplyRange` (not `StrictlyEnforceRange`) is correct here: it keeps the
focused item in the center third when possible but allows it to be at the
edge when the list is too short to scroll. `StrictlyEnforceRange` would
prevent focus from reaching the first/last items in short lists.

**All ListViews/GridViews to update** (confirmed from codebase audit):
- `WatchScreen.qml` — `libraryList`
- `RetroGamesScreen.qml` — `systemList`
- `GameGridView.qml` — `gameGrid`
- `GameListView.qml` — `gameListView`
- `ListenScreen.qml` — `listenMenu`, `recentlyAddedList`, `playlistList`,
  `albumList`, `trackList`, `playlistTrackList`
- `PlexMovieGrid.qml`, `PlexShowGrid.qml`, `PlexOnDeckGrid.qml`
- `PlexMovieList.qml`, `PlexShowList.qml`, `PlexOnDeckList.qml`
- `PlexArtistGrid.qml`, `PlexArtistList.qml`
- `MoonlightAppGrid.qml`, `MoonlightAppList.qml`
- `MoonlightScreen.qml` — host list
- `SteamGameGrid.qml`, `SteamGameList.qml`
- `RecentlyPlayedGrid.qml`, `RecentlyPlayedList.qml`
- `PcGamesScreen.qml` — system list
- `LiveTvScreen.qml` — channel list
- `SettingsScreen.qml` — settings list

**Caveats:**
- `preferredHighlightBegin/End` are in **pixels**, not fractions. Use
  `height * 0.35` and `height * 0.65` so they scale with the list height.
- For `GridView`, the same properties apply but refer to the scroll axis
  (vertical for a vertical grid).
- Do not add to the `PlexShowDetail` episode list inner ListView if it
  already has custom scroll logic — check first.

### Acceptance criteria for Task 008
- On every list/grid with more items than fit on screen, the focused item
  stays in the center third of the viewport as the user navigates.
- Short lists (fewer items than fill the viewport) are unaffected.
- All tests pass.

---

## Task 009 — Tab transition opacity fade
**Files:** `qml/screens/HomeScreen.qml` only.

### The problem
Entering a tab (`_launcherVisible = false`) and returning (`back()` signal)
are hard cuts. The hero fade was attempted previously but never worked.

### The fix
Replace the boolean `_launcherVisible` hard-cut with an opacity-based fade.

**Approach:**

1. Add a `_contentOpacity` property (default 0.0) and a `_launcherOpacity`
   property (default 1.0).

2. The launcher `Row` and background `Image` bind to `opacity: _launcherOpacity`
   with a `Behavior`:
   ```qml
   Behavior on opacity { NumberAnimation { duration: Theme.animDurationFast } }
   ```

3. The content `Item` binds to `opacity: _contentOpacity` with the same
   `Behavior`.

4. On tab activation (A-press):
   - Set `_launcherOpacity = 0.0` (triggers 150ms fade out)
   - After 150ms (`Timer { interval: 150 }`), set `_launcherVisible = false`
     and `_contentOpacity = 1.0` (triggers 150ms fade in of content)

5. On `back()` (returning to launcher):
   - Set `_contentOpacity = 0.0` (150ms fade out)
   - After 150ms, set `_launcherVisible = true` and `_launcherOpacity = 1.0`

**Keep `_launcherVisible`** as the structural visibility toggle (it controls
`focus` and `visible` on the launcher row) — the opacity is layered on top.
This avoids focus-management complexity.

**Caveats:**
- The `ClockDisplay` and `NetworkIndicator` overlays sit above the launcher
  and content — they should not fade. Ensure they are not children of the
  fading items.
- The `QuitDialog` and `ControllerMappingDialog` are in `main.qml` above
  `HomeScreen` — unaffected.
- Do not animate `focus` changes — only `opacity`. Focus must transfer
  immediately when the content loads, not after the animation completes.

### Acceptance criteria for Task 009
- Entering a tab: launcher fades out over 150ms, content fades in over 150ms.
- Returning from a tab: content fades out over 150ms, launcher fades in over 150ms.
- No focus glitches — keyboard/gamepad input works immediately after A-press.
- Clock and network indicator are unaffected by the fade.
- All tests pass.

---

## Key reference: config.json `ui` section after Task 006

```json
"ui": {
  "video_snap_autoplay": true,
  "video_snap_delay_ms": 1500,
  "show_network_indicator": true,
  "button_layout": "standard",
  "retro_games_view_mode": "grid",
  "pc_games_view_mode": "grid",
  "moonlight_view_mode": "grid",
  "watch_view_mode": "grid",
  "listen_view_mode": "grid",
  "theme_name": "default",
  "accent_color": "#e94560",
  "focus_ring_color": "#e94560"
}
```

## Key reference: Theme.qml tokens added/changed in Task 006

| Token | Change |
|-------|--------|
| `_bg` | `#1a1a2e` → `#111111` |
| `_surface` | `#16213e` → `#1c1c1c` |
| `_surfaceHigh` | `#0f3460` → `#2a2a2a` |
| `fontFamily` | `"Sans"` → `"Liberation Sans"` |
| `fontWeightNormal` | new — `Font.Normal` |
| `fontWeightBold` | new — `Font.Bold` |
| `focusRingRadius` | `4` → `10` |
| `colorAccent` | hardcoded → `settings ? settings.accentColor : "#e94560"` |
| `colorFocusRing` | hardcoded → `settings ? settings.focusRingColor : "#e94560"` |
| `colorHighlight` | updated to derive from `colorAccent` property |
| `focusScale` | new — `1.05` |
| `focusScaleDuration` | new — `120` |
