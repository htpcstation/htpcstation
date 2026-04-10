# Task 004: Settings for Local Music

## Context

The Local Music tab needs settings for: directory path, tab visibility toggle, view mode, and sort preference. These follow established patterns in the codebase.

## Objective

Wire up all settings needed for the Local Music tab: path config, tab toggle, view mode, sort preference.

## Scope

### backend/config.py

The `local_music_directory` field was already added in Task 003. Now add:

- `self._show_local_music_tab: bool = True` (in `__init__`, near the other `_show_*` fields around line 400)
- `show_local_music_tab` property (getter, like `show_listen_tab` at line ~898)
- `set_show_local_music_tab(self, enabled: bool)` setter
- `self._local_music_view_mode: str = "grid"` (like `_listen_view_mode`)
- `local_music_view_mode` property + `set_local_music_view_mode()` setter
- `self._sort_local_music_artists: str = "az"` (like `_sort_plex_artists`)
- `sort_local_music_artists` property + `set_sort_local_music_artists()` setter
- Serialize all new fields in `save()` — add `"show_local_music"` to the `"tabs"` dict, add `"local_music_view_mode"` and `"sort_local_music_artists"` to the `"ui"` dict (or wherever similar Plex settings live)
- Deserialize in `_load()` following the same pattern

### backend/settings_manager.py

Add to the SettingsManager class (follow exact patterns of existing tab/view settings):

**Signals:**
- `localMusicDirectoryChanged = Signal()`
- `localMusicViewModeChanged = Signal()`
- `sortLocalMusicArtistsChanged = Signal()`
- (tab visibility can reuse existing `tabVisibilityChanged` signal)

**Getters:**
- `_get_local_music_directory(self) -> str` — returns `str(self._config.local_music_directory or "")`
- `_get_show_local_music_tab(self) -> bool`
- `_get_local_music_view_mode(self) -> str`
- `_get_sort_local_music_artists(self) -> str`

**Properties:**
- `localMusicDirectory = Property(str, fget=..., notify=localMusicDirectoryChanged)`
- `showLocalMusicTab = Property(bool, fget=..., notify=tabVisibilityChanged)`
- `localMusicViewMode = Property(str, fget=..., notify=localMusicViewModeChanged)`
- `sortLocalMusicArtists = Property(str, fget=..., notify=sortLocalMusicArtistsChanged)`

**Setters (Slots):**
- `setLocalMusicDirectory(self, path: str)` — validate path exists (like setRomDirectory), call config setter, emit signal
- `setShowLocalMusicTab(self, enabled: bool)` — call config setter, save, emit tabVisibilityChanged
- `setLocalMusicViewMode(self, mode: str)` — call config setter, save, emit signal
- `setSortLocalMusicArtists(self, key: str)` — call config setter, save, emit signal

### qml/screens/SettingsScreen.qml

Add entries to the settings categories array:

1. In the **"Paths"** category (line ~43), add:
   ```
   { type: "text", label: "Music Directory", settingKey: "localMusicDirectory" }
   ```

2. In the **"Tabs"** category (line ~104), add a toggle:
   ```
   { type: "toggle", label: "Local Music", settingKey: "showLocalMusicTab" }
   ```

3. Wire up the getter in the `_getValue` function:
   - `if (key === "localMusicDirectory") return settings.localMusicDirectory`
   - `if (key === "showLocalMusicTab") return settings.showLocalMusicTab`

4. Wire up the setter in the `_setValue` function:
   - `if (key === "localMusicDirectory") settings.setLocalMusicDirectory(value)`
   - For `showLocalMusicTab`: follow the pattern of `showListenTab` (call setter, re-init tabs)

## Non-goals
- Don't create LocalMusicScreen QML (Task 005)
- Don't register the tab in HomeScreen yet (Task 005)
- Don't wire up main.py (Task 006)

## Constraints
- Tab visibility toggles that affect HomeScreen call `homeScreen._initTabs()` after toggling — follow the existing pattern for other tab toggles.
- The `localMusicDirectory` text field must validate the path exists before saving (same as ROM directory).
