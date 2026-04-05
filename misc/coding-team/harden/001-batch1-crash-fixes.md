# Task Brief 001 — Batch 1 crash and stuck-UI fixes

## Context

Seven targeted fixes across three files. No new features. No new signals or QML structure.
Each fix is independent — they can be applied in any order.

---

## Fix C1 — `_mpvLaunchReady.emit()` arg count mismatch (`plex_library.py` line 1173)

The signal is declared as `Signal(str, str, int, int, int)` — 5 args.
The error path emits 8 args:
```python
self._mpvLaunchReady.emit("", "", 0, 0, 0, 0, 0, 0)
```
Fix: change to 5 args:
```python
self._mpvLaunchReady.emit("", "", 0, 0, 0)
```

---

## Fix C3 — `assert` in `set_plex_player` (`config.py` line 362)

```python
def set_plex_player(self, player: str) -> None:
    assert player in ("mpv", "browser")   # removed by python -O
    self._plex_player = player
    self.save()
```
Fix: replace `assert` with a guard:
```python
def set_plex_player(self, player: str) -> None:
    if player not in ("mpv", "browser"):
        logger.warning("set_plex_player: invalid value %r — ignored", player)
        return
    self._plex_player = player
    self.save()
```

---

## Fix C4 — `_save_my_list` unhandled `OSError` (`plex_library.py` lines 2061–2066)

```python
def _save_my_list(self, items: list[dict]) -> None:
    path = CONFIG_DIR / "plex_mylist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(items, f, indent=2)
```
Fix: wrap in `try/except OSError` and log:
```python
def _save_my_list(self, items: list[dict]) -> None:
    path = CONFIG_DIR / "plex_mylist.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(items, f, indent=2)
    except OSError as exc:
        logger.warning("_save_my_list: could not write %s: %s", path, exc)
```

---

## Fix M1 — `wait_until_playing` timeout leaves loading overlay stuck (`mpv_launcher.py` lines 163–178)

Currently the `except` block in `_wait_and_signal` silently returns on any exception
(including `WaitUntilPlayingTimeout` after 30s). Neither `_on_playback_started` nor
`_emit_started` is called, so `mpvPlaybackStarted` never fires, and the loading overlay
in `WatchScreen` waits forever.

Fix: on timeout/exception, invoke `_emit_finished` via `QMetaObject.invokeMethod` so
`processFinished` fires and the overlay clears. Check `self._is_running` first to avoid
a spurious finished signal if the user already stopped playback.

```python
def _wait_and_signal() -> None:
    try:
        self._player.wait_until_playing(timeout=30)
    except Exception:  # noqa: BLE001
        # Timed out or stopped before first frame — clear the loading overlay.
        if self._is_running():
            QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                Qt.ConnectionType.QueuedConnection,
            )
        return
    QMetaObject.invokeMethod(
        self,
        "_on_playback_started",
        Qt.ConnectionType.QueuedConnection,
    )
    QMetaObject.invokeMethod(
        self,
        "_emit_started",
        Qt.ConnectionType.QueuedConnection,
    )
```

Check that `_emit_finished` exists as a `@Slot` on `LibMpvPlayer` — it should, since
`processFinished` is emitted from it. If it doesn't exist by that name, find the correct
slot name that emits `processFinished` and use that instead.

---

## Fix M3 — `EndOfMedia` fires on failed load, auto-advances silently (`HomeScreen.qml` line 125–129)

```qml
onMediaStatusChanged: {
    if (mediaStatus === MediaPlayer.EndOfMedia) {
        homeScreen._playNext()
    }
}
```

`EndOfMedia` fires both when a track finishes normally AND when a track fails to load
(bad URL, server offline). In the failure case, `_playNext()` is called immediately,
silently skipping to the next track. If multiple tracks are bad, the player rapidly
exhausts the queue.

Fix: also check for `InvalidMedia` and log it, but do NOT auto-advance on failure:
```qml
onMediaStatusChanged: {
    if (mediaStatus === MediaPlayer.EndOfMedia) {
        homeScreen._playNext()
    } else if (mediaStatus === MediaPlayer.InvalidMedia) {
        // Track failed to load — stop rather than silently skipping.
        // The user can press Next manually.
        console.warn("HomeScreen: track failed to load (InvalidMedia) —",
                     homeScreen._nowPlayingTrack.title || "unknown")
    }
}
```

---

## Fix H6 — `_artists_cache_path` hardcodes `~/.config/htpcstation` (`plex_library.py` line 2086)

```python
def _artists_cache_path(self) -> Path:
    cache_dir = Path.home() / ".config" / "htpcstation" / "poster_cache"
```

`CONFIG_DIR` is already imported/defined at the top of `plex_library.py` and used
everywhere else. Fix:
```python
def _artists_cache_path(self) -> Path:
    cache_dir = CONFIG_DIR / "poster_cache"
```

---

## Fix M9 — `config.save()` has no `OSError` handling (`config.py` line 666)

```python
CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

Fix: wrap the entire `save()` body in `try/except OSError` and log. Do not re-raise —
a save failure should not crash the app:
```python
try:
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
except OSError as exc:
    logger.warning("Config.save: could not write %s: %s", CONFIG_FILE, exc)
```

Check whether `ensure_config_dir()` (called before `write_text`) also needs the same
guard — if it raises `OSError`, it should also be caught here.

---

## Tests to add / update

Add a new test file `tests/test_harden_batch1.py` covering:

- **C1**: call `_worker_play_with_mpv` (or the equivalent internal method) with a mock
  that returns `("", 0)` from `get_stream_url`; assert `_mpvLaunchReady` is emitted with
  exactly 5 args, all zero/empty.
- **C3**: call `set_plex_player("invalid")` on a `Config` instance; assert `_plex_player`
  is unchanged and `save()` is not called.
- **C4**: mock `open()` to raise `OSError`; call `_save_my_list([])` on a `PlexLibrary`
  instance; assert no exception propagates.
- **M9**: mock `Path.write_text` to raise `OSError`; call `config.save()`; assert no
  exception propagates.
- **H6**: assert `_artists_cache_path()` returns a path that starts with `CONFIG_DIR`,
  not with `Path.home() / ".config" / "htpcstation"`.

M1 and M3 are QML/threading — no unit tests needed; the fix is the test.

---

## Constraints

- Do not change any signal signatures other than C1.
- Do not add new signals or slots.
- `logger` is already imported in both `plex_library.py` and `config.py` — use it.
- `CONFIG_DIR` is already defined in `plex_library.py` — confirm its name before using.
