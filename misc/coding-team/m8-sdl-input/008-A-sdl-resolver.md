# Task 008-A — SDL resolver foundation

## Context

M8 introduces dual-record input mapping: every captured input stores both an evdev record
(for Qt key injection) and an SDL record (for RetroArch config and the browser extension).
This task builds the SDL resolver — the module that, given a connected evdev device and a
raw evdev event, returns the corresponding SDL representation.

The GameControllerDB is compiled into libSDL2/libSDL3 — no local cache or network fetch
needed. SDL is queried at runtime via ctypes.

## Objective

Create `backend/sdl_resolver.py`. No changes to any existing file in this task.

## Scope

### `backend/sdl_resolver.py`

**SDL record type** (what the resolver returns for a resolved input):
```python
# One of:
{"type": "button", "sdl_button": int}
{"type": "axis",   "sdl_axis": int, "dir": int}   # dir: +1 or -1
{"type": "hat",    "sdl_hat": int,  "dir": str}    # dir: "up"|"down"|"left"|"right"
# Or None if SDL unavailable / input not resolvable
```

**Library loading** — probe in order, load first that works:
```python
_SDL_CANDIDATES = [
    "libSDL2-2.0.so.0",
    "libSDL2-2.0.so",
    "libSDL2.so",
    "libSDL3.so.0",
    "libSDL3.so",
]
```
Use `ctypes.CDLL(name)` inside a try/except. Store the loaded lib as a module-level
`_sdl: ctypes.CDLL | None`. Log which library was loaded (INFO) or that none was found
(WARNING). This runs once at import time.

**SDL constants** (hard-coded — stable across SDL2/SDL3):
```python
SDL_INIT_JOYSTICK = 0x00000200
SDL_HAT_UP        = 0x01
SDL_HAT_RIGHT     = 0x02
SDL_HAT_DOWN      = 0x04
SDL_HAT_LEFT      = 0x08
```

**`SdlResolver` class:**

```python
class SdlResolver:
    """Resolves evdev input events to SDL joystick indices.

    Lifecycle: call open() before capturing, close() when done.
    Safe to call close() without a prior open().
    """

    def __init__(self) -> None:
        self._joystick: ctypes.c_void_p | None = None
        self._n_buttons: int = 0
        self._n_axes: int = 0
        self._n_hats: int = 0
        # evdev axis code → SDL axis index (for non-hat axes)
        self._evdev_axis_to_sdl: dict[int, int] = {}
        # evdev axis code → SDL hat index (for hat axes)
        self._evdev_hat_to_sdl: dict[int, int] = {}

    def open(self, evdev_device_name: str) -> bool:
        """Open the SDL joystick matching the given evdev device name.

        Returns True if a joystick was opened successfully, False otherwise.
        Logs a warning if SDL is unavailable or no matching joystick found.
        """
        ...

    def close(self) -> None:
        """Close the SDL joystick and release resources."""
        ...

    def resolve(self, evtype: str, code: int, value: int) -> dict | None:
        """Resolve an evdev event to an SDL record.

        evtype: "button" or "axis"
        code:   evdev button code (EV_KEY) or axis code (EV_ABS)
        value:  1 for button press; -1 or +1 for axis direction

        Returns an SDL record dict, or None if not resolvable.
        """
        ...
```

**`open()` implementation:**

1. Return False immediately if `_sdl is None`.
2. Call `_sdl.SDL_Init(SDL_INIT_JOYSTICK)`. If non-zero, log warning and return False.
3. Call `_sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")`.
4. `n = _sdl.SDL_NumJoysticks()`. If 0, log warning ("No SDL joysticks found"), return False.
5. Find the best matching joystick:
   - Iterate 0..n-1. For each index, get name via `SDL_JoystickNameForIndex(i)`.
   - Prefer exact name match with `evdev_device_name`.
   - Fall back to index 0 if no name match (single-device common case).
6. Open with `SDL_JoystickOpen(best_index)`. Store handle in `self._joystick`.
7. Query capabilities:
   - `self._n_buttons = SDL_JoystickNumButtons(joy)`
   - `self._n_axes = SDL_JoystickNumAxes(joy)`
   - `self._n_hats = SDL_JoystickNumHats(joy)`
8. Build `_evdev_axis_to_sdl` and `_evdev_hat_to_sdl`:
   - Hat axes (ABS_HAT0X=16, ABS_HAT0Y=17) → SDL hat 0. Hard-code this: hat axes always
     map to SDL hat 0 on any standard gamepad. `_evdev_hat_to_sdl = {16: 0, 17: 0}`.
   - Non-hat axes: sort the evdev axis codes that are NOT in {16, 17}, assign SDL axis
     indices 0, 1, 2, ... in sorted order. This matches SDL's internal ordering.
     The evdev axis codes to consider are those present on the device — but we don't have
     the device capabilities here. Use a standard ordered list of common EV_ABS codes:
     `[0, 1, 2, 3, 4, 5, 6, 7]` (ABS_X through ABS_WHEEL). Filter to those that are
     NOT hat codes. Assign SDL axis index by position.

     Actually — we don't know which axes the device has at open() time (we only have the
     device name, not its capabilities). Use a fixed mapping for common axes:
     ```python
     _COMMON_EVDEV_AXIS_TO_SDL: dict[int, int] = {
         0: 0,  # ABS_X  → SDL axis 0 (left stick X)
         1: 1,  # ABS_Y  → SDL axis 1 (left stick Y)
         2: 2,  # ABS_Z  → SDL axis 2 (L2 trigger)
         3: 3,  # ABS_RX → SDL axis 3 (right stick X)
         4: 4,  # ABS_RY → SDL axis 4 (right stick Y)
         5: 5,  # ABS_RZ → SDL axis 5 (R2 trigger)
     }
     ```
     This is correct for the vast majority of gamepads (XInput layout, Switch Pro,
     DualSense, 8BitDo). Non-standard devices may get wrong indices — acceptable
     limitation, same as the old hardcoded table.

     Store as `self._evdev_axis_to_sdl = dict(_COMMON_EVDEV_AXIS_TO_SDL)`.

9. Log success: device name, n_buttons, n_axes, n_hats.
10. Return True.

**`close()` implementation:**

1. If `self._joystick` is not None: call `SDL_JoystickClose(self._joystick)`.
2. Call `SDL_QuitSubSystem(SDL_INIT_JOYSTICK)`.
3. Reset all fields to defaults.

**`resolve()` implementation:**

```python
def resolve(self, evtype: str, code: int, value: int) -> dict | None:
    if self._joystick is None:
        return None

    if evtype == "button":
        # EV_KEY button: SDL button index = position in sorted EV_KEY codes.
        # We don't have the full button list here — use the evdev code directly
        # as a lookup key against a fixed table (same limitation as axis).
        # For now: SDL button index is not derivable without the full button list.
        # Return None — button SDL resolution requires the full device caps.
        # This will be resolved in Task 008-B where we pass device caps to open().
        return None  # placeholder — see Task 008-B

    elif evtype == "axis":
        if code in self._evdev_hat_to_sdl:
            # Hat axis
            hat_idx = self._evdev_hat_to_sdl[code]
            # ABS_HAT0Y: -1=up, +1=down; ABS_HAT0X: -1=left, +1=right
            if code == 17:  # ABS_HAT0Y
                direction = "up" if value < 0 else "down"
            else:           # ABS_HAT0X
                direction = "left" if value < 0 else "right"
            return {"type": "hat", "sdl_hat": hat_idx, "dir": direction}
        else:
            sdl_axis = self._evdev_axis_to_sdl.get(code)
            if sdl_axis is None:
                return None
            return {"type": "axis", "sdl_axis": sdl_axis, "dir": 1 if value > 0 else -1}

    return None
```

Note: button SDL resolution is left as `None` placeholder in this task. Task 008-B will
extend `open()` to accept device capabilities (the sorted EV_KEY button list) and build
a `_evdev_button_to_sdl` dict. This is intentional — 008-A establishes the structure and
gets axis/hat resolution working; 008-B completes button resolution when it has the full
device caps from `getDeviceCapabilities()`.

**Module-level convenience instance:**

```python
# Module-level singleton — one resolver per application lifetime.
# Opened/closed by GamepadManager around raw mode sessions.
resolver = SdlResolver()
```

**`ctypes` function signatures** (set restype/argtypes for safety):
```python
_sdl.SDL_Init.restype = ctypes.c_int
_sdl.SDL_Init.argtypes = [ctypes.c_uint32]
_sdl.SDL_NumJoysticks.restype = ctypes.c_int
_sdl.SDL_JoystickNameForIndex.restype = ctypes.c_char_p
_sdl.SDL_JoystickNameForIndex.argtypes = [ctypes.c_int]
_sdl.SDL_JoystickOpen.restype = ctypes.c_void_p
_sdl.SDL_JoystickOpen.argtypes = [ctypes.c_int]
_sdl.SDL_JoystickNumButtons.restype = ctypes.c_int
_sdl.SDL_JoystickNumButtons.argtypes = [ctypes.c_void_p]
_sdl.SDL_JoystickNumAxes.restype = ctypes.c_int
_sdl.SDL_JoystickNumAxes.argtypes = [ctypes.c_void_p]
_sdl.SDL_JoystickNumHats.restype = ctypes.c_int
_sdl.SDL_JoystickNumHats.argtypes = [ctypes.c_void_p]
_sdl.SDL_JoystickClose.restype = None
_sdl.SDL_JoystickClose.argtypes = [ctypes.c_void_p]
_sdl.SDL_QuitSubSystem.restype = None
_sdl.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
_sdl.SDL_SetHint.restype = ctypes.c_bool  # SDL_bool
_sdl.SDL_SetHint.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
```

Set these immediately after loading the library, before any calls.

### `tests/test_sdl_resolver.py`

New test file. All tests mock `ctypes.CDLL` — no real SDL required.

```python
class TestSdlLibraryLoading:
    def test_loads_first_available_candidate(self, monkeypatch): ...
    def test_returns_none_when_no_candidate_found(self, monkeypatch): ...
    def test_logs_warning_when_no_library_found(self, monkeypatch, caplog): ...

class TestSdlResolverOpen:
    def test_returns_false_when_sdl_unavailable(self): ...
    def test_returns_false_when_no_joysticks(self, mock_sdl): ...
    def test_opens_first_joystick_when_no_name_match(self, mock_sdl): ...
    def test_prefers_name_match_over_first(self, mock_sdl): ...
    def test_returns_true_on_success(self, mock_sdl): ...
    def test_stores_capabilities(self, mock_sdl): ...

class TestSdlResolverClose:
    def test_close_without_open_is_safe(self): ...
    def test_close_calls_sdl_joystick_close(self, mock_sdl): ...
    def test_close_resets_state(self, mock_sdl): ...

class TestSdlResolverResolveAxis:
    def test_hat_y_negative_is_up(self, mock_sdl): ...
    def test_hat_y_positive_is_down(self, mock_sdl): ...
    def test_hat_x_negative_is_left(self, mock_sdl): ...
    def test_hat_x_positive_is_right(self, mock_sdl): ...
    def test_trigger_abs_z_resolves_to_sdl_axis_2(self, mock_sdl): ...
    def test_trigger_abs_rz_resolves_to_sdl_axis_5(self, mock_sdl): ...
    def test_left_stick_x_resolves_to_sdl_axis_0(self, mock_sdl): ...
    def test_unknown_axis_returns_none(self, mock_sdl): ...
    def test_axis_dir_positive(self, mock_sdl): ...
    def test_axis_dir_negative(self, mock_sdl): ...

class TestSdlResolverResolveButton:
    def test_button_returns_none_placeholder(self, mock_sdl): ...
    # Button resolution is completed in Task 008-B

class TestSdlResolverNotOpen:
    def test_resolve_returns_none_when_not_open(self): ...
```

Use a `mock_sdl` fixture that patches the module-level `_sdl` with a `MagicMock` and
sets `resolver._joystick = ctypes.c_void_p(1)` (non-None sentinel).

## Non-goals / Later

- Do NOT modify `gamepad.py`, `controller_mapping.py`, `settings_manager.py`, or any QML.
- Button SDL resolution (completed in 008-B when device caps are available).
- `GamepadManager.startRawMode()` / `stopRawMode()` integration (008-B).

## Constraints / Caveats

- The module-level `_sdl` and `resolver` are initialised at import time. Tests that need
  to control `_sdl` must patch `backend.sdl_resolver._sdl` directly.
- `SDL_QuitSubSystem` (not `SDL_Quit`) — only quit the joystick subsystem, not all of SDL,
  to avoid interfering with any other SDL usage in the process.
- `SDL_JoystickNameForIndex` returns `bytes` via ctypes (c_char_p) — decode with `.decode()`
  before comparing to the Python string `evdev_device_name`.
- After all changes: `python3 -m pytest tests/ -q` must show 0 failures.
