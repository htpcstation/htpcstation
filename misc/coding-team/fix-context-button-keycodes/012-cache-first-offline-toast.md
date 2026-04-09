# Task 012 — Cache-first offline display + unified toast errors

## Context

When the network is unavailable:

1. `_worker_load_section` emits the cache (movies/shows/artists), then hits
   the network call, gets an exception, and `return`s — without emitting
   `_moviesReady` / `_showsReady` / `_artistsReady`. Those are the only
   signals that clear `_loading = false` in QML. Result: `_loading` stays
   `true` forever, the "Loading..." spinner covers the cached data.

2. `_worker_refresh` fails the `get_identity()` call, emits
   `_availabilityReady(False)`, but never emits `_librariesReady`. QML's
   `_refreshing` is only cleared by `onLibrariesModelChanged` (which fires
   from `_librariesReady`). Result: `_refreshing` stays `true` on WatchScreen.

3. `plexError` is emitted from the worker thread without `QueuedConnection`
   (it's emitted directly, not via `__init__` connect). QML's `onPlexError`
   may not fire reliably.

4. Both WatchScreen and ListenScreen have a full error banner Rectangle
   (top-of-screen strip) that is visually inconsistent with the toast style
   used everywhere else.

## Objective

- Cache is always displayed immediately; network failure never blocks browsing.
- All errors (including auth) route to the toast. Error banner removed.
- `_loading` and `_refreshing` are always cleared, even on network failure.
- A toast "Network unavailable" appears when a background refresh fails.

---

## Part A — `backend/plex_library.py`

### A1. Add `sectionLoadFailed` signal

```python
sectionLoadFailed = Signal()   # emitted when _worker_load_section network call fails
```

Add alongside the other signals (~line 477).

### A2. Connect `sectionLoadFailed` with QueuedConnection in `__init__`

The signal has no internal slot — it is consumed by QML only. No `.connect()`
needed in Python. Just declare it.

### A3. Emit `sectionLoadFailed` on network failure in `_worker_load_section`

```python
# Before (line 2100–2102):
except Exception as exc:  # noqa: BLE001
    logger.warning("PlexLibrary: failed to load section %s: %s", section_key, exc)
    return

# After:
except Exception as exc:  # noqa: BLE001
    logger.warning("PlexLibrary: failed to load section %s: %s", section_key, exc)
    self.sectionLoadFailed.emit()
    return
```

### A4. Emit cached libraries in `_worker_refresh` on failure

When `get_identity()` fails, `_librariesReady` is never emitted, so
`_refreshing` never clears. Fix: emit the cached libraries before the
network call so the UI always has data, and `_refreshing` clears via
`onLibrariesModelChanged` regardless of network outcome.

```python
def _worker_refresh(self, client: PlexClient) -> None:
    """Worker: check availability, fetch libraries and on-deck."""
    # Emit cached data immediately so the UI is never blank during a slow
    # or failed network call. onLibrariesModelChanged will clear _refreshing.
    cached_libraries = self._load_libraries_cache()
    if cached_libraries:
        self._librariesReady.emit(cached_libraries, True)
    cached_ondeck = self._load_ondeck_cache()
    if cached_ondeck:
        self._onDeckCacheReady.emit(cached_ondeck)

    try:
        identity = client.get_identity()
        ...  # rest of existing logic unchanged
```

### A5. Fix `plexError` cross-thread emission

`plexError` is emitted directly from `_on_plex_error` which runs on the
worker thread (called via `set_error_callback`). Wrap it to ensure it
reaches the main thread:

```python
def _on_plex_error(self, error_type) -> None:
    """Called on worker thread when a Plex API request fails."""
    # Use invokeMethod to ensure delivery on the main thread
    QMetaObject.invokeMethod(
        self,
        "_emit_plex_error",
        Qt.ConnectionType.QueuedConnection,
        Q_ARG(str, error_type.value),
    )
    if error_type == PlexErrorType.NETWORK and self._client is not None:
        if self._client.try_next_connection():
            logger.info("PlexLibrary: reconnected to server via fallback URL")

@Slot(str)
def _emit_plex_error(self, error_type: str) -> None:
    self.plexError.emit(error_type)
```

Import `QMetaObject` and `Q_ARG` from `PySide6.QtCore` if not already
imported. Check the existing imports first — add only what's missing.

---

## Part B — `qml/screens/WatchScreen.qml`

### B1. Remove the error banner entirely

Delete:
- `property string _errorMessage: ""`
- `property bool _errorPersistent: false`
- `function _showPlexError(errorType) { ... }` (the full function)
- `Timer { id: errorBannerTimer ... }`
- `Rectangle { id: errorBanner ... }` (the full block, ~lines 1208–1254)

### B2. Route `onPlexError` to toast

Replace the `onPlexError` handler in `Connections { target: plex }`:

```qml
function onPlexError(errorType) {
    switch (errorType) {
        case "auth":
            watchScreen._toastText = "Plex sign-in required — go to Settings"
            break
        case "server":
            watchScreen._toastText = "Plex server unavailable"
            break
        case "network":
            watchScreen._toastText = "Network unavailable"
            break
        case "not_found":
            watchScreen._toastText = "Content not found"
            break
        default:
            watchScreen._toastText = "Plex error"
            break
    }
    toastTimer.restart()
}
```

Auth errors no longer persist — they auto-dismiss after 5s like all others.
The "[Settings →]" hint is dropped (the text is self-explanatory).

### B3. Handle `onSectionLoadFailed` — clear `_loading` in content screens

WatchScreen itself doesn't have `_loading` — it has `_refreshing`. But the
content screens (PlexMovieGrid etc.) are loaded inside WatchScreen's
`contentLoader`. They handle `onSectionLoadFailed` themselves (Part D).

WatchScreen does need to handle the case where `_refreshing` is stuck.
`_worker_refresh` now emits cached libraries first (Part A4), so
`onLibrariesModelChanged` fires and clears `_refreshing` even on failure.
No additional change needed here.

### B4. Update `loadingTimeoutTimer` — remove `_showPlexError` call

```qml
// Before:
onTriggered: {
    if (watchScreen._isLoadingContent) {
        watchScreen._clearLoading()
        watchScreen._showPlexError("network")
    }
}

// After:
onTriggered: {
    if (watchScreen._isLoadingContent) {
        watchScreen._clearLoading()
        watchScreen._toastText = "Network unavailable"
        toastTimer.restart()
    }
}
```

---

## Part C — `qml/screens/ListenScreen.qml`

### C1. Remove the error banner entirely

Delete:
- `property string _errorMessage: ""`
- `property bool _errorPersistent: false`
- `function _showPlexError(errorType) { ... }`
- `Timer { id: errorBannerTimer ... }`
- `Rectangle { id: errorBanner ... }` (~lines 2409–2456)

### C2. Add toast infrastructure (WatchScreen already has it; ListenScreen does not)

Add alongside the removed error properties:

```qml
property string _toastText: ""

Timer {
    id: toastTimer
    interval: 5000
    onTriggered: listenScreen._toastText = ""
}
```

Add the toast Rectangle (match WatchScreen's toastBar exactly):

```qml
Rectangle {
    id: toastBar
    anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: root.vpx(32) }
    width: toastLabel.width + root.vpx(32)
    height: root.vpx(40)
    radius: root.vpx(6)
    color: Theme.colorSecondary
    visible: listenScreen._toastText !== ""
    z: 100

    Text {
        id: toastLabel
        anchors.centerIn: parent
        text: listenScreen._toastText
        color: Theme.colorText
        font.family: Theme.fontFamily
        font.pixelSize: root.vpx(Theme.fontSizeBody)
    }
}
```

Place it at the same z-order position where `errorBanner` was (end of file,
before the artist detail view or after the last overlay).

### C3. Route `onPlexError` to toast

Replace the `onPlexError` handler in `Connections { target: plex }`:

```qml
function onPlexError(errorType) {
    switch (errorType) {
        case "auth":
            listenScreen._toastText = "Plex sign-in required — go to Settings"
            break
        case "server":
            listenScreen._toastText = "Plex server unavailable"
            break
        case "network":
            listenScreen._toastText = "Network unavailable"
            break
        case "not_found":
            listenScreen._toastText = "Content not found"
            break
        default:
            listenScreen._toastText = "Plex error"
            break
    }
    toastTimer.restart()
}
```

### C4. Handle `onSectionLoadFailed`

Add to `Connections { target: plex }`:

```qml
function onSectionLoadFailed() {
    listenScreen._loading = false
    if (plex && plex.artistsModel && plex.artistsModel.count > 0) {
        listenScreen._toastText = "Network unavailable — showing cached data"
    } else {
        listenScreen._toastText = "Network unavailable"
    }
    toastTimer.restart()
}
```

---

## Part D — `PlexMovieGrid.qml`, `PlexMovieList.qml`, `PlexShowGrid.qml`, `PlexShowList.qml`

Each of these has `_loading` cleared only by `onMoviesModelChanged` /
`onShowsModelChanged`. Add `onSectionLoadFailed` to each screen's
`Connections { target: plex }` block:

### `PlexMovieGrid.qml` and `PlexMovieList.qml`

```qml
function onSectionLoadFailed() {
    movieGridView._loading = false   // or movieListView._loading for list variant
    if (plex && plex.moviesModel && plex.moviesModel.count > 0) {
        // toast is shown by WatchScreen's onSectionLoadFailed handler
    }
}
```

Wait — the movie/show grid/list screens don't have their own toast. They are
loaded inside WatchScreen's `contentLoader`. WatchScreen has the toast.
So the toast must be shown from WatchScreen, not from the content screen.

**Revised approach for D:**

Add `onSectionLoadFailed` to WatchScreen's `Connections { target: plex }`:

```qml
function onSectionLoadFailed() {
    // The content screen clears its own _loading flag.
    // WatchScreen shows the toast.
    watchScreen._toastText = "Network unavailable — showing cached data"
    toastTimer.restart()
}
```

And in each of the four content screens, add to their own
`Connections { target: plex }`:

```qml
function onSectionLoadFailed() {
    movieGridView._loading = false   // adjust id per file
}
```

This way: `_loading` is cleared by the content screen, toast is shown by
WatchScreen. No duplication.

---

## Summary of all files changed

- `backend/plex_library.py` — `sectionLoadFailed` signal, emit on section
  failure, emit cache in `_worker_refresh`, fix `plexError` cross-thread
- `qml/screens/WatchScreen.qml` — remove error banner, route errors to toast,
  add `onSectionLoadFailed` toast handler, fix `loadingTimeoutTimer`
- `qml/screens/ListenScreen.qml` — remove error banner, add toast
  infrastructure, route errors to toast, add `onSectionLoadFailed` handler
- `qml/screens/PlexMovieGrid.qml` — add `onSectionLoadFailed` → clear `_loading`
- `qml/screens/PlexMovieList.qml` — add `onSectionLoadFailed` → clear `_loading`
- `qml/screens/PlexShowGrid.qml` — add `onSectionLoadFailed` → clear `_loading`
- `qml/screens/PlexShowList.qml` — add `onSectionLoadFailed` → clear `_loading`

## Non-goals / Later

- Do not add toast to PlexMovieGrid/List/ShowGrid/List themselves — WatchScreen
  owns the toast for all content loaded in its contentLoader.
- Do not change the `plexError` signal definition or its string values.
- Do not change any other screens (LiveTvScreen, SettingsScreen, etc.).

## Constraints / Caveats

- `sectionLoadFailed` is emitted from a worker thread. Since it has no
  Python-side slot (QML connects to it directly), PySide6 will deliver it
  to QML via the event loop automatically when emitted cross-thread from a
  Signal with QML connections. Verify this works — if not, add a no-op
  Python slot connected with QueuedConnection as a trampoline.
- `QMetaObject` and `Q_ARG` may already be imported — check before adding.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
