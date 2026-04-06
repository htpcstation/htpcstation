# Task 007 — Emit release events in raw mode + restore hold-to-clear

## Context

Raw mode currently only emits `value === 1` (press) from `gamepad.py`. This prevents
hold-to-clear from working in `ModifierCaptureDialog`. The fix is to also emit `value === 0`
(release) in raw mode, then guard the one other consumer (`ControllerMappingDialog`) against
receiving release events.

## Scope — 4 files

### 1. `backend/gamepad.py`

Change one line in `_handle_button`:

```python
# Before:
if self._manager._raw_mode:
    if value == 1:
        self._manager.rawInput.emit("button", code, value)
    return

# After:
if self._manager._raw_mode:
    if value in (0, 1):   # emit press AND release; skip auto-repeat (value=2)
        self._manager.rawInput.emit("button", code, value)
    return
```

### 2. `qml/screens/ControllerMappingDialog.qml`

Add a release-event guard at the top of `_onRawInput` (line ~119):

```qml
function _onRawInput(evType, code, value) {
    // Ignore release events — only map on press
    if (evType === "button" && value !== 1) return

    // Check for duplicates
    if (_isDuplicate(evType, code, value)) { ... }
    ...
}
```

No other changes to this file.

### 3. `qml/screens/ModifierCaptureDialog.qml`

Restore the original hold-to-clear mechanic (press → start timer; release before timer →
capture; timer fires → clear). Replace the current two-press mechanic entirely.

**`_pendingCode`** — keep as-is (already present from Task 006).

**`holdTimer`** — change `interval` from 3000 to 3000 (unchanged). Keep `repeat: false`.

**`onRawInput`** — replace with:
```qml
function onRawInput(evType, code, value) {
    if (evType === "button" && value === 1) {
        // Button pressed — start hold timer, record pending code
        captureDialog._pendingCode = code
        holdTimer.restart()
    } else if (evType === "button" && value === 0) {
        // Button released — if hold timer still running, it's a tap → capture
        if (captureDialog._pendingCode === code && holdTimer.running) {
            holdTimer.stop()
            captureDialog._pendingCode = -1
            captureDialog._capture(code)
        }
        // If hold timer already fired, _clear() was already called — do nothing
        captureDialog._pendingCode = -1
    }
}
```

**`holdTimer.onTriggered`** — fires after 3s hold → clear:
```qml
onTriggered: {
    captureDialog._pendingCode = -1
    captureDialog._clear()
}
```

**`_capture()`, `_clear()`, `_cancel()`** — each must stop `holdTimer` and reset
`_pendingCode = -1` before proceeding. Already done in Task 006 — verify they're still
correct after this change.

**`onVisibleChanged`** (false branch) — must stop `holdTimer` and reset `_pendingCode = -1`.
Already done in Task 006 — verify.

**Instruction text** — update to:
```
"Tap to assign.\nHold 3 seconds to clear."
```

**Visible countdown** — add a countdown text element inside `captureCard` that shows the
remaining seconds while `_pendingCode !== -1`. Use a 1-second repeating `Timer` to tick
down a `property int _countdown` from 3 to 0.

Implementation:
```qml
// Countdown state
property int _countdown: 0

// 1-second tick timer — runs while hold timer is active
Timer {
    id: countdownTimer
    interval: 1000
    repeat: true
    onTriggered: {
        if (captureDialog._countdown > 0) {
            captureDialog._countdown -= 1
        }
    }
}
```

Start `countdownTimer` and set `_countdown = 3` when `holdTimer.restart()` is called
(i.e. on button-down in `onRawInput`). Stop `countdownTimer` and reset `_countdown = 0`
in `_capture()`, `_clear()`, `_cancel()`, and the `onVisibleChanged` false branch.

Display the countdown in the card — show it only when `_pendingCode !== -1`:

```qml
// Countdown display — visible while a button is being held
Text {
    id: countdownText
    anchors {
        horizontalCenter: parent.horizontalCenter
        top: listeningRow.bottom
        topMargin: root.vpx(16)
    }
    visible: captureDialog._pendingCode !== -1
    text: captureDialog._countdown > 0 ? captureDialog._countdown + "..." : "Clearing..."
    color: Theme.colorPrimary
    font.family: Theme.fontFamily
    font.pixelSize: root.vpx(Theme.fontSizeHeading)
    font.bold: true
}
```

Place this Text element inside `captureCard`, after `listeningRow`. The card height may need
to increase slightly to accommodate it — increase from `vpx(320)` to `vpx(360)` if needed.

### 4. `tests/test_controller_mapping.py`

Update `test_raw_mode_button_release_does_not_emit` — this test currently asserts that
release events are NOT emitted. After the `gamepad.py` change, they ARE emitted. Update it:

```python
def test_raw_mode_button_release_emits_raw_input(self) -> None:
    """In raw mode, button release (value=0) now emits rawInput."""
    from backend.gamepad import GamepadManager

    manager = GamepadManager()
    manager.startRawMode()

    received: list[tuple] = []
    manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

    handler = self._make_handler(manager)

    event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 0)
    handler._handle_event(event)

    assert len(received) == 1
    assert received[0] == ("button", ecodes.BTN_SOUTH, 0)
```

Also add a test confirming auto-repeat (value=2) is still NOT emitted:

```python
def test_raw_mode_button_autorepeat_does_not_emit(self) -> None:
    """In raw mode, kernel auto-repeat (value=2) does NOT emit rawInput."""
    from backend.gamepad import GamepadManager

    manager = GamepadManager()
    manager.startRawMode()

    received: list[tuple] = []
    manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

    handler = self._make_handler(manager)

    event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 2)
    handler._handle_event(event)

    assert received == []
```

## Non-goals / Later

- Do NOT change `RetroarchHotkeysScreen.qml`.
- Do NOT change `backend/settings_manager.py`.
- Do NOT change `backend/config.py`.

## Constraints / Caveats

- The `Connections` block in `ModifierCaptureDialog` has `enabled: captureDialog._listening`.
  When `_capture()` sets `_listening = false` before emitting `buttonCaptured`, the
  `Connections` block is disabled. Any subsequent release event from the same button press
  will not fire `onRawInput` again — no double-capture risk.
- `countdownTimer` must be stopped in ALL exit paths: `_capture()`, `_clear()`, `_cancel()`,
  and `onVisibleChanged` false branch.
- The `_countdown` display shows `"Clearing..."` when it reaches 0 (the instant before
  `holdTimer` fires and `_clear()` is called). This gives visual feedback that the clear
  is imminent.
- After all changes, `python3 -m pytest tests/ -q` must show 0 failures.
