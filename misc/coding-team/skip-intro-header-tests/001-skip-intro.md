# Task Brief 001 — Auto Skip Intro

## Context

`PlexClient.get_metadata(rating_key, include_markers=True)` already fetches marker data.
The `playWithMpv` worker in `plex_library.py` already calls `client.get_metadata(rating_key)`
(without `include_markers`). The `_mpvLaunchReady` internal signal carries 5 args:
`(url, title, start_ms, duration_ms, part_id)`.

`LibMpvPlayer.observe_time_pos(callback)` registers a push-based callback that fires on
every position change during playback (already used by `PlexTimelineReporter`).

The existing toast pattern in `WatchScreen.qml`: `_toastText` property + `toastTimer`
(2s) + `toastBar` Rectangle at bottom-centre, `z: 100`.

## Objective

1. Parse intro markers from Plex metadata in the `playWithMpv` worker
2. Emit `markersReady(intro_end_ms: int)` signal from `PlexLibrary` on launch
3. Add `mpvPositionChanged(int)` signal to `PlexLibrary` (push-based, from time-pos observer)
4. Add `plex.seekMpv(ms)` slot to `PlexLibrary`
5. Add `auto_skip_intro` setting to `Config` + `SettingsManager`
6. Wire auto-skip in `WatchScreen.qml` — seek + toast when position enters intro window
7. Add toggle to `SettingsScreen.qml`

## Scope

**Modified files:**
- `backend/plex_library.py`
- `backend/config.py`
- `backend/settings_manager.py`
- `qml/screens/WatchScreen.qml`
- `qml/screens/SettingsScreen.qml`

**New test file:** `tests/test_skip_intro.py`

---

## Python changes

### `backend/config.py`

Add alongside `_plex_player`:
```python
self._auto_skip_intro: bool = False
```

Add property + setter (same pattern as `set_plex_player`):
```python
@property
def auto_skip_intro(self) -> bool:
    return self._auto_skip_intro

def set_auto_skip_intro(self, enabled: bool) -> None:
    self._auto_skip_intro = bool(enabled)
    self.save()
```

Persist in `save()` under `plex.auto_skip_intro` (alongside `player`).
Load in the `plex` block of `_load()`.

### `backend/plex_library.py`

**New public signals** (add alongside existing signals):
```python
markersReady      = Signal(int)   # intro_end_ms (0 = no intro marker)
mpvPositionChanged = Signal(int)  # current MPV position in ms (push-based)
```

**`playWithMpv` worker** — change `client.get_metadata(rating_key)` to
`client.get_metadata(rating_key, include_markers=True)`. After extracting `duration_ms`
and `part_id`, parse markers:

```python
intro_end_ms = 0
for marker in meta.get("Marker", []):
    if marker.get("type") == "intro":
        intro_end_ms = int(marker.get("endTimeOffset", 0) or 0)
        break
```

Add `intro_end_ms` to `_mpvLaunchReady` signal — change from 5 args to 6:
`Signal(str, str, int, int, int, int)` → `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`

Update `_mpvLaunchReady.emit(...)` call to include `intro_end_ms`.
Update `_on_mpv_launch_ready` signature to accept `intro_end_ms`.
In `_on_mpv_launch_ready`, after calling `self._mpv_launcher.launch(...)`:
```python
self.markersReady.emit(intro_end_ms)
```

**`set_wid`** — register a second time-pos observer for position broadcasting:
```python
def _on_time_pos(pos_seconds: float) -> None:
    if pos_seconds is not None:
        self._mpvPositionMs.emit(int(pos_seconds * 1000))
self._mpv_launcher.observe_time_pos(_on_time_pos)
```

Add internal signal:
```python
_mpvPositionMs = Signal(int)
```
Connect in `__init__`:
```python
self._mpvPositionMs.connect(self.mpvPositionChanged)
```

**`seekMpv` slot:**
```python
@Slot(int)
def seekMpv(self, position_ms: int) -> None:
    """Seek MPV to an absolute position in milliseconds."""
    if self._mpv_launcher._player is None:
        return
    try:
        self._mpv_launcher._player.seek(position_ms / 1000.0, "absolute")
    except Exception:  # noqa: BLE001
        pass
```

### `backend/settings_manager.py`

Add `autoSkipIntro` Property + `setAutoSkipIntro` slot (same pattern as `plexPlayer`/`setPlexPlayer`):
```python
autoSkipIntroChanged = Signal()
autoSkipIntro = Property(bool, fget=..., notify=autoSkipIntroChanged)

@Slot(bool)
def setAutoSkipIntro(self, enabled: bool) -> None:
    self._config.set_auto_skip_intro(enabled)
    self.autoSkipIntroChanged.emit()
```

---

## QML changes

### `WatchScreen.qml`

Add properties:
```qml
property int  _introEndMs:      0      // 0 = no intro for current title
property bool _introSkipped:    false  // prevent double-skip
```

Add to the consolidated `Connections { target: plex }` block:
```qml
function onMarkersReady(introEndMs) {
    watchScreen._introEndMs = introEndMs
    watchScreen._introSkipped = false
}
function onMpvPositionChanged(posMs) {
    if (!settings || !settings.autoSkipIntro) return
    if (watchScreen._introEndMs <= 0) return
    if (watchScreen._introSkipped) return
    // Seek when position enters the intro window (any position < introEndMs
    // and > 5s to avoid triggering at the very start before the observer fires)
    if (posMs > 5000 && posMs < watchScreen._introEndMs) {
        watchScreen._introSkipped = true
        plex.seekMpv(watchScreen._introEndMs)
        watchScreen._toastText = "Skipping intro..."
        toastTimer.restart()
    }
}
```

Clear markers when a new title starts (add to `_launchMpv`):
```qml
watchScreen._introEndMs = 0
watchScreen._introSkipped = false
```

### `SettingsScreen.qml`

Add after the `"Video Player"` cycle entry:
```js
{ type: "toggle", label: "Auto-Skip Intro", settingKey: "autoSkipIntro" },
```

The `toggle` type is already handled by the settings list delegate — check how
`videoSnapAutoplay` is wired to confirm the exact pattern, then follow it.

---

## Tests (`tests/test_skip_intro.py`)

- `playWithMpv` worker calls `get_metadata` with `include_markers=True`
- `_mpvLaunchReady` emits 6 args when intro marker present
- `_mpvLaunchReady` emits `intro_end_ms=0` when no intro marker
- `markersReady` emitted with correct `intro_end_ms` from `_on_mpv_launch_ready`
- `markersReady` emitted with 0 when no marker
- `seekMpv` calls `player.seek` with correct seconds value
- `seekMpv` is a no-op when `_player` is None
- `Config.auto_skip_intro` defaults to False, persists via `save()`/`_load()`

## Constraints / Caveats

- `_mpvLaunchReady` signal arg count changes from 5 to 6 — update ALL test mocks
  that patch or assert on this signal (search `test_plex_backend.py` and
  `test_harden_batch1.py` for `_mpvLaunchReady`).
- The `observe_time_pos` callback runs on the mpv event thread — the `_mpvPositionMs`
  internal signal + `QueuedConnection` pattern already handles thread safety.
  Do NOT call `mpvPositionChanged.emit()` directly from the callback.
- `player.seek(seconds, "absolute")` — python-mpv uses seconds (float), not ms.
- The intro window check uses `posMs > 5000` to avoid false triggers at stream start.
- `_introSkipped` prevents re-triggering if the user seeks back into the intro window.
