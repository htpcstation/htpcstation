# Task 008-C — Dual-record hotkey assignment

## Context

Tasks 008-A and 008-B established the SDL resolver and dual-record controller mapping.
This task extends the hotkey assignment system to:
1. Support all input types (buttons, axes/triggers/sticks, hats/d-pad) in the capture dialog.
2. Store hotkey assignments as SDL records (not raw SDL button indices).
3. Write the correct `_btn`, `_axis`, or `_hat` key to retroarch.cfg on Apply.
4. Remove the now-obsolete `EVDEV_TO_SDL` table and `evdev_code_to_sdl_index()`.

The modifier (enable_hotkey) remains button-only — no axis/hat support for the modifier.

## New hotkey_mapping schema

Currently: `{action: int | None}` (SDL button index)
New: `{action: dict | None}` where dict is an SDL record:
```python
{"type": "button", "sdl_button": int}
{"type": "axis",   "sdl_axis": int, "dir": int}   # dir: +1 or -1
{"type": "hat",    "sdl_hat": int,  "dir": str}    # dir: "up"|"down"|"left"|"right"
```

Old int values in config.json are migrated on load: `int N` → `{"type": "button", "sdl_button": N}`.

## Scope

### `backend/retroarch_config.py`

**`HOTKEY_CFG_KEYS`** — change from `{action: cfg_key_str}` to `{action: dict}` with three
parallel keys per action:

```python
HOTKEY_CFG_KEYS: dict[str, dict[str, str]] = {
    "save_state": {
        "btn":  "input_save_state_btn",
        "axis": "input_save_state_axis",
        "hat":  "input_save_state_hat",
    },
    "load_state": {
        "btn":  "input_load_state_btn",
        "axis": "input_load_state_axis",
        "hat":  "input_load_state_hat",
    },
    "fast_forward_toggle": {
        "btn":  "input_toggle_fast_forward_btn",
        "axis": "input_toggle_fast_forward_axis",
        "hat":  "input_toggle_fast_forward_hat",
    },
    "fast_forward_hold": {
        "btn":  "input_hold_fast_forward_btn",
        "axis": "input_hold_fast_forward_axis",
        "hat":  "input_hold_fast_forward_hat",
    },
    "rewind": {
        "btn":  "input_rewind_btn",
        "axis": "input_rewind_axis",
        "hat":  "input_rewind_hat",
    },
    "menu_toggle": {
        "btn":  "input_menu_toggle_btn",
        "axis": "input_menu_toggle_axis",
        "hat":  "input_menu_toggle_hat",
    },
    "screenshot": {
        "btn":  "input_screenshot_btn",
        "axis": "input_screenshot_axis",
        "hat":  "input_screenshot_hat",
    },
    "show_fps": {
        "btn":  "input_toggle_statistics_btn",
        "axis": "input_toggle_statistics_axis",
        "hat":  "input_toggle_statistics_hat",
    },
    "state_slot_increase": {
        "btn":  "input_state_slot_increase_btn",
        "axis": "input_state_slot_increase_axis",
        "hat":  "input_state_slot_increase_hat",
    },
    "state_slot_decrease": {
        "btn":  "input_state_slot_decrease_btn",
        "axis": "input_state_slot_decrease_axis",
        "hat":  "input_state_slot_decrease_hat",
    },
    "pause_toggle": {
        "btn":  "input_pause_toggle_btn",
        "axis": "input_pause_toggle_axis",
        "hat":  "input_pause_toggle_hat",
    },
    "exit_emulator": {
        "btn":  "input_exit_emulator_btn",
        "axis": "input_exit_emulator_axis",
        "hat":  "input_exit_emulator_hat",
    },
    "enable_hotkey": {
        "btn":  "input_enable_hotkey_btn",
        "axis": "input_enable_hotkey_axis",   # written as "nul" always (modifier is btn-only)
        "hat":  "input_enable_hotkey_hat",    # written as "nul" always
    },
}
```

**`build_hotkey_cfg()`** — new signature and implementation:

```python
def build_hotkey_cfg(
    hotkey_mapping: dict[str, dict | None],  # hotkey_action → SDL record or None
    modifier_sdl_record: dict | None,        # SDL record for enable_hotkey, or None
) -> dict[str, str]:
    """Convert hotkey mapping to retroarch.cfg key=value pairs.

    For each action, writes exactly one of _btn/_axis/_hat with the value,
    and writes "nul" for the other two. None values write "nul" for all three.
    Modifier (enable_hotkey) is always written as _btn only (axis/hat = "nul").
    """
    result: dict[str, str] = {}

    for hotkey_action, cfg_keys in HOTKEY_CFG_KEYS.items():
        if hotkey_action == "enable_hotkey":
            sdl_record = modifier_sdl_record
        else:
            sdl_record = hotkey_mapping.get(hotkey_action)

        btn_key  = cfg_keys["btn"]
        axis_key = cfg_keys["axis"]
        hat_key  = cfg_keys["hat"]

        if sdl_record is None or hotkey_action == "enable_hotkey":
            # Modifier: always btn-only. Others: None = nul for all.
            if hotkey_action == "enable_hotkey" and sdl_record is not None:
                sdl_type = sdl_record.get("type")
                if sdl_type == "button":
                    result[btn_key]  = str(sdl_record["sdl_button"])
                else:
                    result[btn_key]  = "nul"
            else:
                result[btn_key]  = "nul"
            result[axis_key] = "nul"
            result[hat_key]  = "nul"
            continue

        sdl_type = sdl_record.get("type")

        if sdl_type == "button":
            result[btn_key]  = str(sdl_record["sdl_button"])
            result[axis_key] = "nul"
            result[hat_key]  = "nul"
        elif sdl_type == "axis":
            sdl_axis = sdl_record["sdl_axis"]
            direction = sdl_record["dir"]  # +1 or -1
            axis_str = f"+{sdl_axis}" if direction > 0 else f"-{sdl_axis}"
            result[btn_key]  = "nul"
            result[axis_key] = axis_str
            result[hat_key]  = "nul"
        elif sdl_type == "hat":
            sdl_hat = sdl_record["sdl_hat"]
            direction = sdl_record["dir"]  # "up"|"down"|"left"|"right"
            result[btn_key]  = "nul"
            result[axis_key] = "nul"
            result[hat_key]  = f"{sdl_hat}{direction}"  # e.g. "0up"
        else:
            result[btn_key]  = "nul"
            result[axis_key] = "nul"
            result[hat_key]  = "nul"

    return result
```

**Remove** `EVDEV_TO_SDL`, `evdev_code_to_sdl_index()` entirely.

### `backend/config.py`

**`_hotkey_mapping` type annotation** — update from `dict[str, int | None]` to
`dict[str, dict | None]`.

**`hotkey_mapping` property** — update return type annotation.

**`set_hotkey_mapping()`** — update parameter type annotation.

**`_load()`** — update migration for hotkey_mapping:

```python
raw_mapping = retroarch.get("hotkey_mapping")
if isinstance(raw_mapping, dict):
    loaded: dict[str, dict | None] = {}
    for k, v in raw_mapping.items():
        if v is None:
            loaded[k] = None
        elif isinstance(v, int):
            # Migration: old int SDL index → button record
            loaded[k] = {"type": "button", "sdl_button": v}
        elif isinstance(v, dict) and v.get("type") in ("button", "axis", "hat"):
            loaded[k] = v
        # else: malformed — skip (action will be absent from mapping, treated as None)
    self._hotkey_mapping = loaded
```

### `backend/settings_manager.py`

**Remove** `_SDL_TO_EVDEV` reverse map (no longer needed).
**Remove** `_sdl_to_evdev()` method.
**Remove** `_EVDEV_LABELS` dict and `_get_hotkey_button_label()` method.

**Add** `_sdl_record_label()` — human-readable label for an SDL record:

```python
_SDL_BUTTON_LABELS: dict[int, str] = {
    0: "A/East", 1: "B/South", 2: "X/West", 3: "Y/North",
    4: "L1", 5: "R1", 6: "Select", 7: "Start", 8: "Home",
    9: "L2", 10: "R2", 11: "L3", 12: "R3",
}

def _sdl_record_label(self, sdl_record: dict | None) -> str:
    """Return a human-readable label for an SDL record."""
    if sdl_record is None:
        return ""
    sdl_type = sdl_record.get("type")
    if sdl_type == "button":
        idx = sdl_record.get("sdl_button", -1)
        return self._SDL_BUTTON_LABELS.get(idx, f"Button {idx}")
    elif sdl_type == "axis":
        axis = sdl_record.get("sdl_axis", -1)
        direction = sdl_record.get("dir", 1)
        _AXIS_LABELS = {
            0: ("Left Stick Left", "Left Stick Right"),
            1: ("Left Stick Up",   "Left Stick Down"),
            2: ("L2 (Trigger)",    "L2 (Trigger)"),
            3: ("Right Stick Left","Right Stick Right"),
            4: ("Right Stick Up",  "Right Stick Down"),
            5: ("R2 (Trigger)",    "R2 (Trigger)"),
        }
        pair = _AXIS_LABELS.get(axis)
        if pair:
            return pair[0] if direction < 0 else pair[1]
        return f"Axis {axis} {'−' if direction < 0 else '+'}"
    elif sdl_type == "hat":
        direction = sdl_record.get("dir", "")
        _HAT_LABELS = {"up": "D-pad Up", "down": "D-pad Down",
                       "left": "D-pad Left", "right": "D-pad Right"}
        return _HAT_LABELS.get(direction, f"Hat {direction}")
    return ""
```

**`getRetroarchHotkeyConfig()`** — update to use SDL records:

- `modifier_sdl_record`: call `_sdl_resolver.resolve(...)` — wait, the modifier is stored
  as `hotkey_modifier_evdev` (int). We need to resolve it to an SDL record for display.
  But `SdlResolver` is only open during raw mode. For display purposes, use a simpler
  approach: the modifier is always a button, so derive its SDL record from the evdev code
  using the existing `evdev_code_to_sdl_index()` — but that function is being removed.

  **Revised approach for modifier display:** Store the modifier as both evdev code AND
  SDL record. When `setHotkeyModifier(evdev_code)` is called, also resolve and store the
  SDL record. Add `_hotkey_modifier_sdl: dict | None` to `Config`.

  Actually — simpler: keep `hotkey_modifier_evdev` as-is for the modifier (it's always a
  button, captured via the same dialog). For display, derive the label from the evdev code
  using `_EVDEV_LABELS` (keep this dict, just for the modifier). The modifier SDL record
  for `build_hotkey_cfg` is derived at Apply time: `{"type": "button", "sdl_button": N}`
  where N comes from... we no longer have `EVDEV_TO_SDL`.

  **The real fix:** `setHotkeyModifier` must also store the SDL record. Add
  `_hotkey_modifier_sdl: dict | None` to `Config`. `setHotkeyModifier(evdev_code)` calls
  `_sdl_resolver.resolve("button", evdev_code, 1)` and stores both the evdev code and the
  SDL record. `applyRetroarchHotkeys` uses the stored SDL record.

  Add to `Config.__init__`:
  ```python
  self._hotkey_modifier_sdl: dict | None = None
  ```

  Add property and setter:
  ```python
  @property
  def hotkey_modifier_sdl(self) -> dict | None:
      return self._hotkey_modifier_sdl

  def set_hotkey_modifier_sdl(self, record: dict | None) -> None:
      self._hotkey_modifier_sdl = record
      self.save()
  ```

  In `save()`, add to `retroarch` dict:
  ```python
  "hotkey_modifier_sdl": self._hotkey_modifier_sdl,
  ```

  In `_load()`, load it:
  ```python
  raw_modifier_sdl = retroarch.get("hotkey_modifier_sdl")
  if raw_modifier_sdl is None or (
      isinstance(raw_modifier_sdl, dict)
      and raw_modifier_sdl.get("type") in ("button", "axis", "hat")
  ):
      self._hotkey_modifier_sdl = raw_modifier_sdl
  ```

**`setHotkeyModifier(evdev_code)`** — also resolve and store SDL record:

```python
@Slot(int)
def setHotkeyModifier(self, evdev_code: int) -> None:
    from backend.sdl_resolver import resolver as _sdl_resolver
    sdl_record = _sdl_resolver.resolve("button", evdev_code, 1)
    # Evict any hotkey action using the same SDL record
    if sdl_record is not None:
        mapping = dict(self._config.hotkey_mapping)
        changed = False
        for action, rec in mapping.items():
            if rec == sdl_record:
                mapping[action] = None
                changed = True
        if changed:
            self._config.set_hotkey_mapping(mapping)
    self._config.set_hotkey_modifier_evdev(evdev_code)
    self._config.set_hotkey_modifier_sdl(sdl_record)
    logger.debug("setHotkeyModifier: evdev %d → SDL %s", evdev_code, sdl_record)
```

**`setHotkeyActionByEvdev(hotkey_action, evdev_code)`** — resolve SDL record and store:

```python
@Slot(str, int)
def setHotkeyActionByEvdev(self, hotkey_action: str, evdev_code: int) -> None:
    from backend.sdl_resolver import resolver as _sdl_resolver
    sdl_record = _sdl_resolver.resolve("button", evdev_code, 1)
    self._store_hotkey_sdl(hotkey_action, sdl_record)
    logger.debug("setHotkeyActionByEvdev: %s → evdev %d → SDL %s", hotkey_action, evdev_code, sdl_record)
```

**New slot `setHotkeyActionByAxis(hotkey_action, evdev_code, value)`** — for axis/hat inputs:

```python
@Slot(str, int, int)
def setHotkeyActionByAxis(self, hotkey_action: str, evdev_code: int, value: int) -> None:
    from backend.sdl_resolver import resolver as _sdl_resolver
    sdl_record = _sdl_resolver.resolve("axis", evdev_code, value)
    self._store_hotkey_sdl(hotkey_action, sdl_record)
    logger.debug("setHotkeyActionByAxis: %s → evdev %d/%d → SDL %s", hotkey_action, evdev_code, value, sdl_record)
```

**New private helper `_store_hotkey_sdl(hotkey_action, sdl_record)`**:

```python
def _store_hotkey_sdl(self, hotkey_action: str, sdl_record: dict | None) -> None:
    """Store an SDL record for a hotkey action, evicting conflicts."""
    mapping = dict(self._config.hotkey_mapping)
    # Evict any OTHER action using the same SDL record
    if sdl_record is not None:
        for action, rec in mapping.items():
            if action != hotkey_action and rec == sdl_record:
                mapping[action] = None
    # Evict modifier if it uses the same SDL record
    if sdl_record is not None and self._config.hotkey_modifier_sdl == sdl_record:
        self._config.set_hotkey_modifier_evdev(None)
        self._config.set_hotkey_modifier_sdl(None)
    mapping[hotkey_action] = sdl_record
    self._config.set_hotkey_mapping(mapping)
```

**`clearHotkeyAction(hotkey_action)`** — unchanged (sets to None).

**`getRetroarchHotkeyConfig()`** — update:

- `modifier_label`: use `_sdl_record_label(self._config.hotkey_modifier_sdl)` if SDL record
  available, else fall back to `_EVDEV_LABELS.get(modifier_evdev, f"Button {modifier_evdev}")`.
  Keep `_EVDEV_LABELS` for this fallback only.
- `hotkey_rows`: each row's `button_label` = `_sdl_record_label(sdl_record)` where
  `sdl_record = mapping.get(action)`.
- Remove `sdl_index` field from row dicts (no longer meaningful — replaced by full SDL record).
- Add `sdl_record` field to row dicts for QML to display.
- Return `modifier_sdl_record: self._config.hotkey_modifier_sdl` instead of `modifier_sdl`.

**`applyRetroarchHotkeys()`** — update:

```python
modifier_sdl_record = self._config.hotkey_modifier_sdl
mapping = dict(self._config.hotkey_mapping)
cfg_updates = _ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record)
```

Remove the old `modifier_evdev → evdev_code_to_sdl_index()` derivation.

### `qml/screens/ModifierCaptureDialog.qml`

**Add axis event handling** to `onRawInput` for hotkey rows (modifier stays button-only):

The dialog currently only handles `evType === "button"`. For hotkey rows (not the modifier
row), axis events should also trigger capture. The dialog doesn't know whether it's being
used for the modifier or a hotkey row — add a property to distinguish:

```qml
// Set to true when capturing a hotkey action (axis/hat allowed)
// Set to false (default) when capturing the modifier (button only)
property bool allowAxisInput: false
```

Update `onRawInput`:
```qml
function onRawInput(evType, code, value) {
    if (evType === "button" && value === 1) {
        captureDialog._pendingCode = code
        captureDialog._pendingEvType = "button"
        captureDialog._countdown = 3
        countdownTimer.restart()
        holdTimer.restart()
    } else if (evType === "button" && value === 0) {
        if (captureDialog._pendingCode === code
                && captureDialog._pendingEvType === "button"
                && holdTimer.running) {
            holdTimer.stop()
            countdownTimer.stop()
            captureDialog._countdown = 0
            captureDialog._pendingCode = -1
            captureDialog._pendingEvType = ""
            captureDialog._captureAxis(code, 0)  // no — use _captureButton
        }
        captureDialog._pendingCode = -1
        captureDialog._pendingEvType = ""
    } else if (evType === "axis" && captureDialog.allowAxisInput) {
        // Axis/hat: capture immediately on first event (no hold-to-clear for axes)
        captureDialog._captureAxisEvent(code, value)
    }
}
```

Wait — this is getting complex. Simplify: axis events capture immediately (no hold-to-clear
for axes — the user can't "hold" an axis in the same way). Button events use the existing
hold-to-clear mechanic.

Rename `_capture(evdev_code)` to `_captureButton(evdev_code)` and add `_captureAxis(code, value)`:

```qml
function _captureButton(evdev_code) {
    // same as current _capture()
    ...
    captureDialog.buttonCaptured(evdev_code)
}

function _captureAxis(code, value) {
    holdTimer.stop()
    countdownTimer.stop()
    captureDialog._pendingCode = -1
    captureDialog._countdown = 0
    captureDialog._listening = false
    timeoutTimer.stop()
    if (typeof gamepadManager !== "undefined" && gamepadManager) {
        gamepadManager.stopRawMode()
    }
    captureDialog.visible = false
    captureDialog.axisCaptured(code, value)
}
```

Add signal: `signal axisCaptured(int evdev_code, int value)`

Add property: `property string _pendingEvType: ""`

Update `onRawInput`:
```qml
function onRawInput(evType, code, value) {
    if (evType === "button" && value === 1) {
        captureDialog._pendingCode = code
        captureDialog._pendingEvType = "button"
        captureDialog._countdown = 3
        countdownTimer.restart()
        holdTimer.restart()
    } else if (evType === "button" && value === 0) {
        if (captureDialog._pendingCode === code
                && captureDialog._pendingEvType === "button"
                && holdTimer.running) {
            holdTimer.stop()
            countdownTimer.stop()
            captureDialog._countdown = 0
            var captured = captureDialog._pendingCode
            captureDialog._pendingCode = -1
            captureDialog._pendingEvType = ""
            captureDialog._captureButton(captured)
        } else {
            captureDialog._pendingCode = -1
            captureDialog._pendingEvType = ""
        }
    } else if (evType === "axis" && captureDialog.allowAxisInput) {
        // Axis/hat: capture immediately (no hold-to-clear)
        captureDialog._captureAxis(code, value)
    }
}
```

Update `_clear()`, `_cancel()`, `onVisibleChanged` to reset `_pendingEvType = ""`.

Update `holdTimer.onTriggered` to reset `_pendingEvType = ""` before calling `_clear()`.

### `qml/screens/RetroarchHotkeysScreen.qml`

**`hotkeyCaptureDialog`** — set `allowAxisInput: true` (hotkey rows allow all input types).
**`modifierCaptureDialog`** — `allowAxisInput` stays `false` (default, button-only).

**`hotkeyCaptureDialog.onAxisCaptured`** handler:
```qml
onAxisCaptured: (evdev_code, value) => {
    if (settings && hotkeysScreen._captureTargetAction !== "") {
        settings.setHotkeyActionByAxis(hotkeysScreen._captureTargetAction, evdev_code, value)
        hotkeysScreen.config = settings.getRetroarchHotkeyConfig()
    }
    hotkeysList.forceActiveFocus()
}
```

**Row display** — `button_label` is now derived from `sdl_record` via `_sdl_record_label()`
in Python. The QML delegate already reads `modelData._data.button_label` — no change needed
to the delegate itself.

### Tests

**`tests/test_retroarch_hotkeys.py`** — update:
- `TestBuildHotkeyCfg`: update to use SDL record dicts instead of int SDL indices.
  - `build_hotkey_cfg({"save_state": {"type": "button", "sdl_button": 3}}, None)`
  - Assert `input_save_state_btn = "3"`, `input_save_state_axis = "nul"`, `input_save_state_hat = "nul"`.
  - Add test for axis assignment: `{"type": "axis", "sdl_axis": 2, "dir": 1}` → `input_save_state_axis = "+2"`.
  - Add test for hat assignment: `{"type": "hat", "sdl_hat": 0, "dir": "up"}` → `input_save_state_hat = "0up"`.
  - Add test for modifier: SDL record → `input_enable_hotkey_btn = "N"`.
  - Update `TestNewHotkeyKeys`: `HOTKEY_CFG_KEYS["save_state"]` is now a dict with `btn`/`axis`/`hat` keys.
- `TestGetRetroarchHotkeyConfig`: update to use SDL record format.
- `TestSetHotkeyActionByEvdev`: update to mock `_sdl_resolver.resolve`.
- `TestDuplicatePrevention`: update to use SDL record dicts for comparison.
- Add `TestSetHotkeyActionByAxis`: tests for the new slot.
- `TestApplyRetroarchHotkeys`: update to use SDL records.

**`tests/test_settings_backend.py`** — update hotkey config tests for new schema.

## Non-goals / Later

- Do NOT change `ControllerMappingDialog.qml` (already done in 008-B).
- Do NOT change `controller_mapping.py` (already done in 008-B).
- Analog stick label improvements (V2 — current labels like "Left Stick Right" are sufficient).
- Per-system cfg overrides (V3).

## Constraints / Caveats

- `_sdl_resolver.resolve()` returns `None` when the resolver is not open (no device
  connected, or called outside raw mode). `setHotkeyActionByEvdev` and
  `setHotkeyActionByAxis` store `None` in this case — the row shows "Not set".
  This is acceptable: the user must have a controller connected to assign hotkeys.
- `EVDEV_TO_SDL` and `evdev_code_to_sdl_index()` are removed. Any code that imports
  them will break — search for all usages before removing.
- `_SDL_TO_EVDEV` in `settings_manager.py` (reverse map) is also removed.
- The `hotkey_modifier_sdl` field is new in config.json. Old configs without it load
  with `_hotkey_modifier_sdl = None` (modifier label falls back to evdev label).
- After all changes: `python3 -m pytest tests/ -q` must show 0 failures.
