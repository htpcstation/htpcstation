# Task 008-B — Dual-record controller mapping wizard

## Context

Task 008-A created `backend/sdl_resolver.py` with `SdlResolver` that resolves axis/hat
events to SDL records. Button resolution was left as a `None` placeholder because it
requires the device's full EV_KEY button list to compute SDL button indices.

This task:
1. Completes button resolution in `SdlResolver.open()` by passing device capabilities.
2. Changes the mapping schema from single evdev records to dual evdev+SDL records.
3. Wires `SdlResolver` into `GamepadManager.startRawMode()` / `stopRawMode()`.
4. Updates `ControllerMappingDialog.qml` to record both halves per input.
5. Updates `saveControllerMapping` to store dual records.
6. Updates `load_mapping` to migrate old single-record format.
7. Updates `build_evdev_lookup` to read the `evdev` half.
8. Updates `build_web_gamepad_mapping` to read the `sdl` half.
9. Removes `_HAT_BUTTON_OFFSETS`, `_ABS_HAT_CODES`, and the hat→button offset logic.

## New mapping entry schema

Each action entry changes from:
```json
{"type": "button", "code": 305, "value": 1}
```
to:
```json
{
  "evdev": {"type": "button", "code": 305, "value": 1},
  "sdl":   {"type": "button", "sdl_button": 0}
}
```

The `sdl` half may be `null` if SDL resolution failed.

`DEFAULT_MAPPING` entries are updated to dual-record format with `"sdl": null` (SDL
indices are device-specific — no hardcoded defaults).

The `_device` metadata key is removed from the mapping file. It was used by
`build_web_gamepad_mapping` to compute SDL indices; that computation is now done at
capture time by `SdlResolver`. The `_device` key is no longer needed.

## Scope

### `backend/sdl_resolver.py` — complete button resolution

Extend `open()` to accept an optional `button_codes: list[int]` parameter:

```python
def open(self, evdev_device_name: str, button_codes: list[int] | None = None) -> bool:
```

After the existing capability queries, if `button_codes` is provided:
```python
sorted_buttons = sorted(button_codes)
self._evdev_button_to_sdl = {code: idx for idx, code in enumerate(sorted_buttons)}
```

Update `resolve()` for buttons:
```python
if evtype == "button":
    sdl_btn = self._evdev_button_to_sdl.get(code)
    if sdl_btn is None:
        return None
    return {"type": "button", "sdl_button": sdl_btn}
```

Add `self._evdev_button_to_sdl: dict[int, int] = {}` to `__init__`.
Reset it in `close()`.

### `backend/controller_mapping.py`

**`DEFAULT_MAPPING`** — update all entries to dual-record format:
```python
DEFAULT_MAPPING: dict[str, dict] = {
    "dpad_up": {
        "evdev": {"type": "axis",   "code": _ABS_HAT0Y, "value": -1},
        "sdl":   None,
    },
    "accept": {
        "evdev": {"type": "button", "code": _BTN_EAST, "value": 1},
        "sdl":   None,
    },
    # ... all 14 actions
}
```

**`load_mapping()`** — update validation and migration:

```python
def load_mapping() -> dict[str, dict]:
    ...
    for action, entry in data.items():
        if action == "_device":
            continue  # silently drop legacy _device key
        if not isinstance(entry, dict):
            continue

        # Migration: old single-record format → wrap as evdev half
        if "evdev" not in entry and entry.get("type") in ("button", "axis"):
            entry = {"evdev": entry, "sdl": None}

        evdev_part = entry.get("evdev")
        if (
            isinstance(evdev_part, dict)
            and evdev_part.get("type") in ("button", "axis")
            and isinstance(evdev_part.get("code"), int)
            and isinstance(evdev_part.get("value"), int)
        ):
            sdl_part = entry.get("sdl")  # may be None or a dict
            result[action] = {"evdev": evdev_part, "sdl": sdl_part}
    ...
```

**`build_evdev_lookup()`** — read `evdev` half:

```python
for action_name, entry in mapping.items():
    qt_key = _ACTION_KEY_MAP.get(action_name)
    if qt_key is None:
        continue

    evdev_part = entry.get("evdev") if isinstance(entry, dict) else None
    if not isinstance(evdev_part, dict):
        continue

    ev_type_str = evdev_part.get("type")
    code = evdev_part.get("code")
    value = evdev_part.get("value")
    ...  # rest unchanged
```

**`build_web_gamepad_mapping()`** — read `sdl` half. Complete rewrite of the function:

The old implementation computed SDL indices from `_device` capabilities using
`_HAT_BUTTON_OFFSETS` and sorted button/axis lists. The new implementation reads the
pre-computed SDL records from the `sdl` half of each entry.

```python
def build_web_gamepad_mapping(mapping: dict, button_layout: str = "standard") -> Optional[dict]:
    """Generate a Web Gamepad API button/axis mapping from the stored config.

    Reads the ``sdl`` half of each dual-record entry. Returns None if no entry
    has a non-null sdl half (user has not run the mapping dialog with SDL support).
    """
    # Check if any entry has SDL data
    has_sdl = any(
        isinstance(entry, dict) and entry.get("sdl") is not None
        for action, entry in mapping.items()
        if not action.startswith("_")
    )
    if not has_sdl:
        return None

    _layout_swap: dict[str, str] = {}
    if button_layout == "alternate":
        _layout_swap = {
            "accept": "cancel", "cancel": "accept",
            "context1": "context2", "context2": "context1",
        }

    buttons_out: dict[int, str] = {}
    axes_out: dict[int, list] = {}
    dpad_buttons_out: dict[int, bool] = {}

    for action_name, entry in mapping.items():
        if action_name.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue

        sdl = entry.get("sdl")
        if not isinstance(sdl, dict):
            continue

        swapped_name = _layout_swap.get(action_name, action_name)
        web_name = _WEB_ACTION_NAMES.get(swapped_name, swapped_name)

        sdl_type = sdl.get("type")

        if sdl_type == "button":
            web_idx = sdl.get("sdl_button")
            if isinstance(web_idx, int):
                buttons_out[web_idx] = web_name

        elif sdl_type == "hat":
            # SDL hats are exposed as buttons in the Web Gamepad API.
            # Hat 0 directions map to buttons at indices beyond the regular buttons.
            # We don't know n_regular_buttons here — use a fixed offset of 0 for hat 0.
            # The browser extension must handle hat-to-button mapping itself.
            # Store as a special entry with hat info for the extension to interpret.
            hat_idx = sdl.get("sdl_hat", 0)
            direction = sdl.get("dir", "")
            # Encode as a synthetic high button index: hat 0 up=1000, down=1001, etc.
            # The extension will recognise these as hat inputs.
            _HAT_WEB_INDICES = {"up": 1000, "down": 1001, "left": 1002, "right": 1003}
            web_idx = _HAT_WEB_INDICES.get(direction)
            if web_idx is not None:
                buttons_out[web_idx] = web_name
                dpad_buttons_out[web_idx] = True

        elif sdl_type == "axis":
            sdl_axis = sdl.get("sdl_axis")
            direction = sdl.get("dir", 1)
            if isinstance(sdl_axis, int):
                existing = axes_out.get(sdl_axis)
                if existing is None:
                    axes_out[sdl_axis] = [None, None]
                if direction == -1:
                    axes_out[sdl_axis][0] = web_name
                else:
                    axes_out[sdl_axis][1] = web_name

    return {
        "buttons": buttons_out,
        "axes": axes_out,
        "dpadButtons": dpad_buttons_out,
    }
```

**Remove** `_ABS_HAT_CODES`, `_HAT_BUTTON_OFFSETS` constants entirely.

**`get_default_mapping()`** — unchanged (deep copy still works with nested dicts).

**`save_mapping()`** — unchanged (writes whatever dict is passed).

### `backend/gamepad.py`

**`startRawMode()`** — open the SDL resolver:

```python
@Slot()
def startRawMode(self) -> None:
    for handler in self._handlers.values():
        handler._release_all_keys()
    self._raw_mode = True

    # Open SDL resolver for the first connected device
    if self._handlers:
        handler = next(iter(self._handlers.values()))
        device_name = getattr(handler._device, "name", "")
        caps = self.getDeviceCapabilities()
        button_codes = caps.get("buttons", [])
        from backend.sdl_resolver import resolver as _sdl_resolver
        _sdl_resolver.open(device_name, button_codes)
```

**`stopRawMode()`** — close the SDL resolver:

```python
@Slot()
def stopRawMode(self) -> None:
    self._raw_mode = False
    for handler in self._handlers.values():
        handler._release_all_keys()

    from backend.sdl_resolver import resolver as _sdl_resolver
    _sdl_resolver.close()
```

Use a local import inside the methods to avoid circular import risk and to keep the
import lazy (SDL resolver is only needed during raw mode).

### `backend/settings_manager.py`

**`saveControllerMapping()`** — update to store dual records:

```python
@Slot("QVariant")
def saveControllerMapping(self, mapping: object) -> None:
    from PySide6.QtQml import QJSValue
    if isinstance(mapping, QJSValue):
        mapping = mapping.toVariant()
    if not isinstance(mapping, list):
        logger.warning("saveControllerMapping: expected list, got %s", type(mapping))
        return

    from backend.sdl_resolver import resolver as _sdl_resolver

    mapping_dict: dict[str, dict] = {}
    for entry in mapping:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        ev_type = entry.get("type")
        code = entry.get("code")
        value = entry.get("value")
        if (
            isinstance(name, str)
            and ev_type in ("button", "axis")
            and isinstance(code, int)
            and isinstance(value, int)
        ):
            evdev_part = {"type": ev_type, "code": code, "value": value}
            # Resolve SDL half — value for axis is already ±1 from raw mode normalisation
            sdl_part = _sdl_resolver.resolve(ev_type, code, value)
            mapping_dict[name] = {"evdev": evdev_part, "sdl": sdl_part}

    # _device key is no longer stored — SDL resolution is done at capture time
    save_mapping(mapping_dict)
    logger.info("saveControllerMapping: saved %d entries", len(mapping_dict))

    if self._gamepad_manager is not None:
        self._gamepad_manager.reloadMapping()
```

Remove the `_device` caps recording block entirely.

### `qml/screens/ControllerMappingDialog.qml`

The QML dialog records `{name, type, code, value}` per input and passes the list to
`settings.saveControllerMapping()`. The SDL resolution now happens in `saveControllerMapping`
on the Python side — **no QML changes needed**. The dialog continues to pass the same
evdev-format list; Python wraps each entry into the dual-record format.

No changes to `ControllerMappingDialog.qml`.

### `tests/test_sdl_resolver.py`

Add tests for the completed button resolution:

```python
class TestSdlResolverResolveButton:
    def test_button_resolves_when_button_codes_provided(self, mock_sdl_with_buttons):
        # open() called with button_codes=[304, 305, 307, 308]
        # BTN_EAST (305) is at sorted index 1 → sdl_button=1
        result = resolver.resolve("button", 305, 1)
        assert result == {"type": "button", "sdl_button": 1}

    def test_button_first_in_sorted_list(self, mock_sdl_with_buttons):
        # BTN_SOUTH (304) is at sorted index 0 → sdl_button=0
        result = resolver.resolve("button", 304, 1)
        assert result == {"type": "button", "sdl_button": 0}

    def test_unknown_button_returns_none(self, mock_sdl_with_buttons):
        result = resolver.resolve("button", 9999, 1)
        assert result is None

    def test_button_returns_none_without_button_codes(self, mock_sdl):
        # open() called without button_codes — _evdev_button_to_sdl is empty
        result = resolver.resolve("button", 305, 1)
        assert result is None
```

Add `mock_sdl_with_buttons` fixture: same as `mock_sdl` but calls
`resolver.open("test_device", button_codes=[304, 305, 307, 308])` with a mocked SDL.

### `tests/test_controller_mapping.py`

Update tests that reference the old single-record format:

- `test_reads_from_file_correctly`: update fixture data to dual-record format.
- `test_skips_invalid_entries_and_uses_defaults_for_them`: update.
- `test_default_mapping_button_entries`: assert `entry["evdev"]["type"] == "button"` etc.
- `test_default_mapping_dpad_axis_entries`: assert `entry["evdev"]["type"] == "axis"` etc.
- `test_default_mapping_trigger_entries`: same.
- `test_button_type_dpad_mapping`: update.
- `test_all_14_default_actions_have_entries`: assert dual-record structure.
- `test_build_evdev_lookup_*` tests: update fixture mappings to dual-record format.
- `test_reload_mapping_*` tests: update fixture data.
- Add migration test: old single-record entry in JSON → loaded as dual-record with `sdl: None`.
- Add test: `_device` key in JSON is silently dropped on load.
- `build_web_gamepad_mapping` tests: update to use dual-record format with SDL halves.
  - Tests that previously relied on `_device` capabilities: replace with SDL-half data.
  - Add test: `build_web_gamepad_mapping` returns None when all SDL halves are null.
  - Add test: hat entries produce correct `dpadButtons` entries.

### `tests/test_settings_backend.py`

Update `saveControllerMapping` tests:
- Mock `backend.sdl_resolver.resolver.resolve` to return a known SDL record.
- Assert saved mapping has dual-record format.
- Assert `_device` key is NOT saved.

## Non-goals / Later

- Do NOT change `RetroarchHotkeysScreen.qml` or `ModifierCaptureDialog.qml` (008-C).
- Do NOT change `retroarch_config.py` (008-C).
- Do NOT change `hotkey_mapping` schema in `config.py` (008-C).
- The browser extension's `content.js` hat handling (synthetic 1000+ indices) is a
  known temporary measure — the extension will need updating in a future task to
  handle hat inputs properly. This is acceptable for now.

## Constraints / Caveats

- `DEFAULT_MAPPING` has `"sdl": None` for all entries. This is correct — SDL indices
  are device-specific and cannot be hardcoded. The mapping wizard populates them.
- `build_web_gamepad_mapping` returns `None` when no entry has a non-null SDL half.
  This is the correct fallback — the browser extension uses its own defaults.
- `load_mapping` migration: old format entries (no `"evdev"` key) are wrapped as
  `{"evdev": old_entry, "sdl": None}`. This preserves all existing evdev mappings.
- The `_device` key is silently dropped on load (not an error — just legacy data).
- `saveControllerMapping` no longer records `_device`. The `getDeviceCapabilities()`
  slot in `GamepadManager` remains unchanged (still used by `startRawMode` to get
  button codes for `SdlResolver.open()`).
- After all changes: `python3 -m pytest tests/ -q` must show 0 failures.
