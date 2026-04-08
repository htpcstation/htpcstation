# Task 012 — Fix gamepad disconnect crash + hint label flash on connect

## Context

Two related bugs in `backend/gamepad.py`:

### Bug 1 — Segfault on disconnect

`_DeviceHandler._on_readable` catches `OSError` (device gone) and calls:
1. `self._cleanup()` — disables the notifier but does NOT disconnect its signal or
   schedule it for deletion
2. `self._manager._remove_device(self._device.path)` — pops the handler from the dict,
   dropping the last Python reference to the `_DeviceHandler`

The `_DeviceHandler` is then garbage-collected by Python while Qt still holds the
`QSocketNotifier` object (it was parented to `self` but Python's GC runs before Qt's
object tree cleanup). Any pending notifier activation fires into a deleted C++ object →
segfault + "shared QObject was deleted directly".

**Fix:** In `_cleanup`, after `self._notifier.setEnabled(False)`, also:
- Disconnect the signal: `self._notifier.activated.disconnect(self._on_readable)`
- Schedule deletion: `self._notifier.deleteLater()`

Also: `_remove_device` should call `handler.deleteLater()` on the removed handler
instead of just dropping it from the dict, so Qt can clean up the C++ side safely
before Python GC runs.

Change `_remove_device` to:
```python
def _remove_device(self, path: str) -> None:
    handler = self._handlers.pop(path, None)
    if handler is not None:
        handler.deleteLater()
```

### Bug 2 — Hint labels flash to gamepad labels when gamepad is connected

When a gamepad is connected (or on startup), `_DeviceHandler.__init__` creates a
`QSocketNotifier`. The notifier fires immediately if the device fd has buffered events
(kernel queues events from the moment the device is opened). This causes
`setGamepadInput()` to be called, overriding keyboard mode even when the user last
pressed a keyboard key.

**Fix:** Do NOT call `setGamepadInput()` on the first read after device open. Instead,
only call `setGamepadInput()` when a button is actually intentionally pressed — i.e.
only on `EV_KEY` press events (value == 1) and meaningful axis events, not on the
initial fd-ready notification.

The call to `setGamepadInput()` is in `_inject`:
```python
def _inject(self, event_type: QEvent.Type, qt_key: Qt.Key) -> None:
    ...
    if event_type == QEvent.Type.KeyPress and self._manager.keys is not None:
        self._manager.keys.setGamepadInput()
```

This is already correct — it only fires on `KeyPress`, not `KeyRelease`. The flash
must come from the initial buffered events being processed as real presses.

Add a `_ready` flag to `_DeviceHandler` that starts as `False` and is set to `True`
after the first `_on_readable` call completes. Only call `setGamepadInput()` when
`_ready` is `True`:

```python
def __init__(self, ...):
    ...
    self._ready: bool = False   # skip setGamepadInput on first read (buffered events)
    ...

def _on_readable(self) -> None:
    try:
        for event in self._device.read():
            self._handle_event(event)
    except BlockingIOError:
        return
    except OSError:
        ...
    finally:
        self._ready = True   # mark ready after first read regardless of outcome

def _inject(self, event_type, qt_key):
    window = self._manager.window
    if window is None:
        return
    if event_type == QEvent.Type.KeyPress and self._manager.keys is not None and self._ready:
        self._manager.keys.setGamepadInput()
    event = QKeyEvent(event_type, qt_key, Qt.KeyboardModifier.NoModifier)
    QCoreApplication.sendEvent(window, event)
```

## Scope

- `backend/gamepad.py` only

## Non-goals

- Do not change any QML files.
- Do not change the mapping logic or any other backend file.

## Verification

- Connect a gamepad, use keyboard, disconnect gamepad → no crash, no segfault
- Connect a gamepad while in keyboard mode → hint labels stay as keyboard labels
- Press a gamepad button → hint labels switch to gamepad labels correctly
