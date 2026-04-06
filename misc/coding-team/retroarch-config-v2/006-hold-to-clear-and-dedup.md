# Task 006 — Hold-to-clear (timer-only) + duplicate button prevention

## Context

### Why release events don't exist in raw mode

`gamepad.py` `_handle_button()` in raw mode:
```python
if self._manager._raw_mode:
    if value == 1:
        self._manager.rawInput.emit("button", code, value)
    return
```
Only `value === 1` (press) is emitted. Release (`value === 0`) and auto-repeat (`value === 2`)
are never emitted in raw mode. Any mechanic depending on `value === 0` will never fire.

### Hold-to-clear mechanic (press-only world)

Since only press events arrive, "hold to clear" must be approximated as:
- First press → start 3s timer, record `_pendingCode = code`.
- Second press (any button) before timer fires → cancel timer, capture that button immediately.
- Timer fires (3s with no second press) → clear the assignment.

UX: user presses the button they want to clear, waits 3 seconds without pressing anything
else → clears. Pressing a different button within 3s assigns that button instead.

Instruction text: `"Press to assign.\nHold 3 seconds to clear."`

### Duplicate button prevention

When a button is assigned (modifier or hotkey action), its SDL index may already be used
elsewhere. The new assignment should silently displace the old one:
- In `setHotkeyModifier(evdev_code)`: after computing `sdl`, scan `hotkey_mapping` for any
  action whose SDL index equals `sdl` and set it to `None`.
- In `setHotkeyActionByEvdev(hotkey_action, evdev_code)`: after computing `sdl`, check if
  `modifier_sdl == sdl` → clear modifier. Also scan `hotkey_mapping` for any OTHER action
  with the same SDL index and set it to `None`.

---

## Scope

### `qml/screens/ModifierCaptureDialog.qml`

**Remove** the `Qt.Key_F9` → `_clear()` branch from `Keys.onPressed` (Select-to-clear is gone).

**Add** `property int _pendingCode: -1`.

**Add** `Timer { id: holdTimer; interval: 3000; repeat: false }`.

**Update** `onRawInput`:
```qml
function onRawInput(evType, code, value) {
    if (evType === "button" && value === 1) {
        if (captureDialog._pendingCode === -1) {
            // First press — start hold timer
            captureDialog._pendingCode = code
            holdTimer.restart()
        } else {
            // Second press before timer fired — capture immediately
            holdTimer.stop()
            captureDialog._pendingCode = -1
            captureDialog._capture(code)
        }
    }
}
```

**`holdTimer.onTriggered`**:
```qml
onTriggered: {
    captureDialog._pendingCode = -1
    captureDialog._clear()
}
```

**Update `onVisibleChanged`** (visible = false branch): add `holdTimer.stop()` and reset
`_pendingCode = -1`.

**Update `_capture()`**: add `holdTimer.stop()` and `_pendingCode = -1` reset before emitting.

**Update `_clear()`**: add `holdTimer.stop()` and `_pendingCode = -1` reset before emitting.

**Update `_cancel()`**: add `holdTimer.stop()` and `_pendingCode = -1` reset before emitting.

**Update instruction text**:
```
"Press to assign.\nHold 3 seconds to clear."
```

### `backend/settings_manager.py`

**`setHotkeyModifier(evdev_code)`** — add duplicate eviction after computing `sdl`:
```python
@Slot(int)
def setHotkeyModifier(self, evdev_code: int) -> None:
    sdl = _ra_cfg.evdev_code_to_sdl_index(evdev_code)
    # Evict any hotkey action already using this SDL index
    if sdl is not None:
        mapping = dict(self._config.hotkey_mapping)
        changed = False
        for action, idx in mapping.items():
            if idx == sdl:
                mapping[action] = None
                changed = True
        if changed:
            self._config.set_hotkey_mapping(mapping)
    self._config.set_hotkey_modifier_evdev(evdev_code)
    logger.debug("setHotkeyModifier: evdev %d → SDL %s", evdev_code, sdl)
```

**`setHotkeyActionByEvdev(hotkey_action, evdev_code)`** — add duplicate eviction:
```python
@Slot(str, int)
def setHotkeyActionByEvdev(self, hotkey_action: str, evdev_code: int) -> None:
    sdl = _ra_cfg.evdev_code_to_sdl_index(evdev_code)
    mapping = dict(self._config.hotkey_mapping)
    # Evict any OTHER action already using this SDL index
    if sdl is not None:
        for action, idx in mapping.items():
            if action != hotkey_action and idx == sdl:
                mapping[action] = None
    # Evict modifier if it uses the same SDL index
    if sdl is not None:
        modifier_sdl = (
            _ra_cfg.evdev_code_to_sdl_index(self._config.hotkey_modifier_evdev)
            if self._config.hotkey_modifier_evdev is not None
            else None
        )
        if modifier_sdl == sdl:
            self._config.set_hotkey_modifier_evdev(None)
    mapping[hotkey_action] = sdl
    self._config.set_hotkey_mapping(mapping)
    logger.debug("setHotkeyActionByEvdev: %s → evdev %d → SDL %s", hotkey_action, evdev_code, sdl)
```

### `tests/test_retroarch_hotkeys.py`

Add new test class `TestDuplicatePrevention`:

```python
class TestDuplicatePrevention:
    def test_set_modifier_evicts_conflicting_hotkey(self, tmp_path):
        """Assigning a button as modifier clears any hotkey using the same SDL index."""
        manager, config = _make_manager(tmp_path)
        # BTN_EAST (305) → SDL 0; assign save_state to SDL 0 first
        config._hotkey_mapping = {"save_state": 0}
        # Now assign BTN_EAST as modifier → should clear save_state
        manager.setHotkeyModifier(305)
        assert config.hotkey_mapping["save_state"] is None
        assert config.hotkey_modifier_evdev == 305

    def test_set_hotkey_evicts_conflicting_hotkey(self, tmp_path):
        """Assigning a button to a hotkey clears any other hotkey using the same SDL index."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 0, "load_state": 3}
        # Assign load_state to SDL 0 (same as save_state) → save_state should be cleared
        manager.setHotkeyActionByEvdev("load_state", 305)  # BTN_EAST → SDL 0
        assert config.hotkey_mapping["save_state"] is None
        assert config.hotkey_mapping["load_state"] == 0

    def test_set_hotkey_evicts_conflicting_modifier(self, tmp_path):
        """Assigning a button to a hotkey clears the modifier if it uses the same SDL index."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 305  # BTN_EAST → SDL 0
        config._hotkey_mapping = {}
        # Assign save_state to BTN_EAST → modifier should be cleared
        manager.setHotkeyActionByEvdev("save_state", 305)
        assert config.hotkey_modifier_evdev is None
        assert config.hotkey_mapping["save_state"] == 0

    def test_set_hotkey_does_not_evict_self(self, tmp_path):
        """Re-assigning the same button to the same hotkey does not clear it."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 0}
        manager.setHotkeyActionByEvdev("save_state", 305)  # BTN_EAST → SDL 0 again
        assert config.hotkey_mapping["save_state"] == 0

    def test_set_modifier_unknown_evdev_no_eviction(self, tmp_path):
        """Unknown evdev code (SDL=None) does not evict anything."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 0}
        manager.setHotkeyModifier(9999)  # unknown → SDL None
        assert config.hotkey_mapping["save_state"] == 0
```

## Non-goals / Later

- Do NOT change `RetroarchHotkeysScreen.qml` — the `onButtonCleared` handlers are already
  correct; they call `clearHotkeyAction` / `clearHotkeyModifier` and refresh config.
- Do NOT change `SettingsScreen.qml`.
- Do NOT change `config.py`.

## Constraints / Caveats

- `set_hotkey_modifier_evdev` calls `self.save()` internally. `set_hotkey_mapping` also calls
  `self.save()`. In `setHotkeyModifier`, if eviction changes the mapping, `set_hotkey_mapping`
  saves once, then `set_hotkey_modifier_evdev` saves again. Two saves is acceptable.
- In `setHotkeyActionByEvdev`, if the modifier is evicted, `set_hotkey_modifier_evdev(None)`
  saves once, then `set_hotkey_mapping` saves again. Also acceptable.
- `_pendingCode` reset in `holdTimer.onTriggered` must happen BEFORE calling `_clear()`,
  because `_clear()` sets `visible = false` which triggers `onVisibleChanged` which also
  resets `_pendingCode` — double reset is harmless but the order should be explicit.
- After this fix, the full test suite must show 0 failures.
