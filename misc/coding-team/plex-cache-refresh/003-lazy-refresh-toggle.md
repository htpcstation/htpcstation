# Task 003 — Lazy refresh Plex content toggle

## Context

When enabled, entering a third-level Plex screen (movie grid, show grid,
on-deck grid, artist grid, recently added) triggers a background
`plex.selectLibrary(sectionKey)` call to silently refresh that section's
content. When disabled (default), no automatic network call is made — the
user must use the Refresh button.

## Objective

### 1. `backend/config.py`

Add `lazy_refresh_plex` under the `plex` config section. Follow the exact
pattern of `auto_skip_intro` (lines ~402, 511–517, 899, 1059):

```python
# __init__:
self._lazy_refresh_plex: bool = False

# property + setter:
@property
def lazy_refresh_plex(self) -> bool:
    return self._lazy_refresh_plex

def set_lazy_refresh_plex(self, enabled: bool) -> None:
    self._lazy_refresh_plex = bool(enabled)
    self.save()

# save() — add to the plex dict alongside auto_skip_intro:
"lazy_refresh_plex": self._lazy_refresh_plex,

# _load() — add to the plex section load block:
self._lazy_refresh_plex = bool(plex.get("lazy_refresh_plex", False))
```

### 2. `backend/settings_manager.py`

Follow the exact pattern of `autoSkipIntro` (lines ~622–633):

```python
lazyRefreshPlexChanged = Signal()

def _get_lazy_refresh_plex(self) -> bool:
    return self._config.lazy_refresh_plex

lazyRefreshPlex = Property(bool, fget=_get_lazy_refresh_plex,
                           notify=lazyRefreshPlexChanged)

@Slot(bool)
def setLazyRefreshPlex(self, enabled: bool) -> None:
    self._config.set_lazy_refresh_plex(enabled)
    self.lazyRefreshPlexChanged.emit()
```

### 3. `qml/screens/SettingsScreen.qml`

Add the toggle to `_settingsModel` under the Plex header, after
`autoSkipIntro`:
```qml
{ type: "toggle", label: "Lazy Refresh Plex Content", settingKey: "lazyRefreshPlex" },
```

Add to `_getValue()`:
```qml
if (key === "lazyRefreshPlex") return settings.lazyRefreshPlex
```

Add to `_setValue()`:
```qml
else if (key === "lazyRefreshPlex") settings.setLazyRefreshPlex(value)
```

### 4. `qml/screens/WatchScreen.qml`

In `onCurrentViewChanged` (or wherever `currentView` transitions to
`"content"`), add a lazy refresh trigger:

```qml
onCurrentViewChanged: {
    _routeFocus()
    // Lazy refresh: re-fetch section content when entering a content view
    if (currentView === "content"
            && settings && settings.lazyRefreshPlex
            && selectedSectionKey !== ""
            && selectedLibraryType !== "mylist"
            && selectedLibraryType !== "livetv") {
        plex.selectLibrary(selectedSectionKey)
    }
}
```

Note: `mylist` and `livetv` do not use `selectLibrary()` — skip them.
`ondeck` uses `sectionKey = "ondeck"` — `plex.selectLibrary("ondeck")`
is the correct call (verify by reading how `_libraryEntries` is built for
the ondeck entry).

### 5. `qml/screens/ListenScreen.qml`

In `onCurrentViewChanged`, add a lazy refresh trigger when entering
`"artists"` or `"recentlyadded"`:

```qml
if ((currentView === "artists" || currentView === "recentlyadded")
        && settings && settings.lazyRefreshPlex
        && listenScreen._musicSectionKey !== "") {
    plex.selectLibrary(listenScreen._musicSectionKey)
}
```

Place this at the top of `onCurrentViewChanged`, before the existing
`if (currentView === "detail" ...)` chain.

## Scope

- `backend/config.py`
- `backend/settings_manager.py`
- `qml/screens/SettingsScreen.qml`
- `qml/screens/WatchScreen.qml`
- `qml/screens/ListenScreen.qml`

## Non-goals

- Do not change LiveTvScreen.
- Do not change `plex_library.py`.
- Do not add tests for the QML changes (no QML test framework).
- Add backend tests for the new config property and settings_manager slot
  (follow the pattern of existing `test_settings_backend.py` tests for
  `autoSkipIntro`).
