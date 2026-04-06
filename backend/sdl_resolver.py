"""SDL resolver for HTPC Station.

Resolves evdev input events to SDL joystick records for use in RetroArch
config and the browser extension.

The GameControllerDB is compiled into libSDL2/libSDL3 — no local cache or
network fetch needed. SDL is queried at runtime via ctypes.
"""

from __future__ import annotations

import ctypes
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDL constants (stable across SDL2/SDL3)
# ---------------------------------------------------------------------------

SDL_INIT_JOYSTICK = 0x00000200

# ---------------------------------------------------------------------------
# Fallback evdev axis → SDL axis index (XInput layout).
# Used only when axis_codes is not passed to open().
# ---------------------------------------------------------------------------

_COMMON_EVDEV_AXIS_TO_SDL: dict[int, int] = {
    0: 0,  # ABS_X  → SDL axis 0 (left stick X)
    1: 1,  # ABS_Y  → SDL axis 1 (left stick Y)
    2: 2,  # ABS_Z  → SDL axis 2 (L2 trigger)
    3: 3,  # ABS_RX → SDL axis 3 (right stick X)
    4: 4,  # ABS_RY → SDL axis 4 (right stick Y)
    5: 5,  # ABS_RZ → SDL axis 5 (R2 trigger)
}

# ---------------------------------------------------------------------------
# Library loading — probe candidates in order, load first that works
# ---------------------------------------------------------------------------

_SDL_CANDIDATES = [
    "libSDL2-2.0.so.0",
    "libSDL2-2.0.so",
    "libSDL2.so",
    "libSDL3.so.0",
    "libSDL3.so",
]

# ---------------------------------------------------------------------------
# SDL GameController button bind struct
# ---------------------------------------------------------------------------

class _SDL_GameControllerButtonBind(ctypes.Structure):
    class _BindValue(ctypes.Union):
        class _HatBind(ctypes.Structure):
            _fields_ = [("hat", ctypes.c_int), ("hat_mask", ctypes.c_int)]
        _fields_ = [
            ("button", ctypes.c_int),
            ("axis",   ctypes.c_int),
            ("hat",    _HatBind),
        ]
    _fields_ = [("bindType", ctypes.c_int), ("value", _BindValue)]

_SDL_CONTROLLER_BINDTYPE_BUTTON = 1
_SDL_CONTROLLER_BINDTYPE_AXIS   = 2

# SDL_CONTROLLER_BUTTON enum → label
_SDL_CONTROLLER_BUTTON_LABELS: dict[int, str] = {
    0:  "A",
    1:  "B",
    2:  "X",
    3:  "Y",
    4:  "Back",
    5:  "Guide",
    6:  "Start",
    7:  "L3",
    8:  "R3",
    9:  "LB",
    10: "RB",
    11: "D-pad Up",
    12: "D-pad Down",
    13: "D-pad Left",
    14: "D-pad Right",
}

# SDL_CONTROLLER_AXIS enum → (neg_label, pos_label)
_SDL_CONTROLLER_AXIS_LABELS: dict[int, tuple[str, str]] = {
    0: ("Left Stick Left",  "Left Stick Right"),
    1: ("Left Stick Up",    "Left Stick Down"),
    2: ("Right Stick Left", "Right Stick Right"),
    3: ("Right Stick Up",   "Right Stick Down"),
    4: ("LT",               "LT"),
    5: ("RT",               "RT"),
}

_sdl: ctypes.CDLL | None = None

for _candidate in _SDL_CANDIDATES:
    try:
        _lib = ctypes.CDLL(_candidate)
        _lib.SDL_Init.restype = ctypes.c_int
        _lib.SDL_Init.argtypes = [ctypes.c_uint32]
        _lib.SDL_NumJoysticks.restype = ctypes.c_int
        _lib.SDL_JoystickNameForIndex.restype = ctypes.c_char_p
        _lib.SDL_JoystickNameForIndex.argtypes = [ctypes.c_int]
        _lib.SDL_JoystickOpen.restype = ctypes.c_void_p
        _lib.SDL_JoystickOpen.argtypes = [ctypes.c_int]
        _lib.SDL_JoystickNumButtons.restype = ctypes.c_int
        _lib.SDL_JoystickNumButtons.argtypes = [ctypes.c_void_p]
        _lib.SDL_JoystickNumAxes.restype = ctypes.c_int
        _lib.SDL_JoystickNumAxes.argtypes = [ctypes.c_void_p]
        _lib.SDL_JoystickNumHats.restype = ctypes.c_int
        _lib.SDL_JoystickNumHats.argtypes = [ctypes.c_void_p]
        _lib.SDL_JoystickClose.restype = None
        _lib.SDL_JoystickClose.argtypes = [ctypes.c_void_p]
        _lib.SDL_QuitSubSystem.restype = None
        _lib.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
        _lib.SDL_SetHint.restype = ctypes.c_bool
        _lib.SDL_SetHint.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        _lib.SDL_IsGameController.restype = ctypes.c_int
        _lib.SDL_IsGameController.argtypes = [ctypes.c_int]
        _lib.SDL_GameControllerOpen.restype = ctypes.c_void_p
        _lib.SDL_GameControllerOpen.argtypes = [ctypes.c_int]
        _lib.SDL_GameControllerClose.restype = None
        _lib.SDL_GameControllerClose.argtypes = [ctypes.c_void_p]
        _lib.SDL_GameControllerGetBindForButton.restype = _SDL_GameControllerButtonBind
        _lib.SDL_GameControllerGetBindForButton.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _lib.SDL_GameControllerGetBindForAxis.restype = _SDL_GameControllerButtonBind
        _lib.SDL_GameControllerGetBindForAxis.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _sdl = _lib
        log.info("SDL library loaded: %s", _candidate)
        break
    except OSError:
        continue

if _sdl is None:
    log.warning(
        "No SDL library found (tried: %s). SDL joystick resolution unavailable.",
        ", ".join(_SDL_CANDIDATES),
    )


# ---------------------------------------------------------------------------
# SdlResolver
# ---------------------------------------------------------------------------


class SdlResolver:
    """Resolves evdev input events to SDL records for RetroArch config.

    Lifecycle: call open() before capturing, close() when done.
    Safe to call close() without a prior open().
    """

    def __init__(self) -> None:
        self._joystick: ctypes.c_void_p | None = None
        self._n_buttons: int = 0
        self._n_axes: int = 0
        self._n_hats: int = 0
        # evdev axis code → SDL record ({"type":"axis",...} or {"type":"button",...})
        # Determined at open() time via GameController API.
        # D-input triggers appear as joystick buttons in SDL → stored as button records.
        self._evdev_axis_to_sdl_record: dict[int, dict] = {}
        # evdev hat axis code → SDL hat index
        self._evdev_hat_to_sdl: dict[int, int] = {}
        # evdev button code → SDL button index (sorted position in EV_KEY list)
        self._evdev_button_to_sdl: dict[int, int] = {}
        # SDL joystick button index → human-readable label
        self._sdl_button_to_label: dict[int, str] = {}
        # Controller mapping lookup: (evdev_type, evdev_code) → SDL record.
        # Populated by seed_from_controller_mapping(). Takes priority over all
        # other resolution paths in resolve().
        self._evdev_event_to_sdl: dict[tuple[str, int], dict] = {}

    def _build_sdl_record(self, sdl_part: dict) -> dict | None:
        """Build an SDL record dict with label embedded from a stored sdl_part.

        Returns None if sdl_part is not a valid SDL record.
        """
        sdl_type = sdl_part.get("type")
        if sdl_type == "button":
            sdl_btn = sdl_part.get("sdl_button", -1)
            # Prefer label already stored in the sdl_part (set at capture time)
            label = sdl_part.get("label") or self._sdl_button_to_label.get(
                sdl_btn, f"Button {sdl_btn}"
            )
            return {"type": "button", "sdl_button": sdl_btn, "label": label}
        elif sdl_type == "axis":
            sdl_axis = sdl_part.get("sdl_axis", -1)
            label_pair = _SDL_CONTROLLER_AXIS_LABELS.get(
                sdl_axis, (f"Axis {sdl_axis} -", f"Axis {sdl_axis} +")
            )
            return {
                "type": "axis",
                "sdl_axis": sdl_axis,
                "label_neg": label_pair[0],
                "label_pos": label_pair[1],
            }
        elif sdl_type == "hat":
            return dict(sdl_part)
        return None

    def seed_from_controller_mapping(self, mapping: dict) -> None:
        """Build a direct (evdev_type, evdev_code) → SDL record lookup from the
        saved controller mapping.

        This is the primary source of truth for resolve(). It covers every input
        the user physically pressed during the mapping wizard — buttons, axes, and
        hats — with correct SDL records and labels.

        The GC API heuristics in open() remain as fallback for inputs not present
        in the controller mapping (e.g. Home/Guide button, unmapped extras).

        Call after open(). Safe to call when joystick is not open (no-op).
        """
        self._evdev_event_to_sdl = {}
        for action, entry in mapping.items():
            if action.startswith("_") or not isinstance(entry, dict):
                continue
            evdev_part = entry.get("evdev")
            sdl_part = entry.get("sdl")
            if not (
                isinstance(evdev_part, dict)
                and evdev_part.get("type") in ("button", "axis")
                and isinstance(evdev_part.get("code"), int)
                and isinstance(sdl_part, dict)
                and sdl_part.get("type") in ("button", "axis", "hat")
            ):
                continue

            evdev_type = evdev_part["type"]
            evdev_code = evdev_part["code"]

            # Build the SDL record with label embedded
            sdl_record = self._build_sdl_record(sdl_part)
            if sdl_record is None:
                continue

            self._evdev_event_to_sdl[(evdev_type, evdev_code)] = sdl_record

            # Co-firing entries — same or own SDL record
            for also_entry in entry.get("also") or []:
                also_evdev = also_entry.get("evdev")
                also_sdl = also_entry.get("sdl")
                if not (
                    isinstance(also_evdev, dict)
                    and also_evdev.get("type") in ("button", "axis")
                    and isinstance(also_evdev.get("code"), int)
                ):
                    continue
                also_type = also_evdev["type"]
                also_code = also_evdev["code"]
                # Skip hat axes — they are handled separately
                if (also_type, also_code) in [
                    ("axis", k) for k in self._evdev_hat_to_sdl
                ]:
                    continue
                # Use the also entry's own SDL record if available, otherwise use the primary
                if isinstance(also_sdl, dict) and also_sdl.get("type") in ("button", "axis", "hat"):
                    also_record = self._build_sdl_record(also_sdl)
                else:
                    also_record = sdl_record  # fall back to primary SDL record
                if also_record is not None:
                    self._evdev_event_to_sdl[(also_type, also_code)] = also_record

        log.debug("Seeded %d event→SDL records from controller mapping",
                  len(self._evdev_event_to_sdl))

    def open(self, evdev_device_name: str, button_codes: list[int] | None = None,
             axis_codes: list[int] | None = None) -> bool:
        """Open the SDL joystick matching the given evdev device name.

        Args:
            evdev_device_name: evdev device name to match against SDL joysticks.
            button_codes: EV_KEY button codes from the device. Used to build
                the evdev→SDL button index mapping (sorted position).
            axis_codes: EV_ABS axis codes from the device. Used to build the
                evdev→SDL axis mapping dynamically (sorted non-hat position).

        Returns True on success, False otherwise.
        """
        if _sdl is None:
            log.warning("SDL unavailable — cannot open joystick for '%s'", evdev_device_name)
            return False

        ret = _sdl.SDL_Init(SDL_INIT_JOYSTICK)
        if ret != 0:
            log.warning("SDL_Init(SDL_INIT_JOYSTICK) failed (ret=%d)", ret)
            return False

        _sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")

        n = _sdl.SDL_NumJoysticks()
        if n == 0:
            log.warning("No SDL joysticks found")
            return False

        # Prefer exact name match, fall back to index 0
        best_index = 0
        for i in range(n):
            raw_name = _sdl.SDL_JoystickNameForIndex(i)
            if raw_name is not None:
                name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
                if name == evdev_device_name:
                    best_index = i
                    break

        joy = _sdl.SDL_JoystickOpen(best_index)
        self._joystick = joy
        self._n_buttons = _sdl.SDL_JoystickNumButtons(joy)
        self._n_axes    = _sdl.SDL_JoystickNumAxes(joy)
        self._n_hats    = _sdl.SDL_JoystickNumHats(joy)

        # Hat axes: ABS_HAT0X=16, ABS_HAT0Y=17 → SDL hat 0
        self._evdev_hat_to_sdl = {16: 0, 17: 0}
        _HAT_CODES = {16, 17}

        # Button mapping: sorted EV_KEY codes → sequential SDL button indices
        if button_codes is not None:
            self._evdev_button_to_sdl = {
                code: idx for idx, code in enumerate(sorted(button_codes))
            }
        else:
            self._evdev_button_to_sdl = {}

        # Non-hat evdev axis codes sorted → SDL joystick axis indices 0,1,2,...
        if axis_codes is not None:
            non_hat_sorted = sorted(c for c in axis_codes if c not in _HAT_CODES)
        else:
            non_hat_sorted = sorted(_COMMON_EVDEV_AXIS_TO_SDL.keys())
        # SDL joystick axis index → evdev axis code
        joy_axis_to_evdev: dict[int, int] = {
            idx: code for idx, code in enumerate(non_hat_sorted)
        }

        # Build axis SDL records and button labels via GameController API.
        #
        # Key: some devices (D-input) map triggers as joystick BUTTONS in SDL,
        # not as joystick axes. We detect this and store a button record for
        # those evdev axis codes so RetroArch gets input_*_btn, not input_*_axis.
        #
        # Algorithm:
        # 1. Find which SDL joystick axis indices are bound to GC logical axes.
        # 2. The remaining (unbound) joystick axis indices correspond to evdev
        #    axes that SDL treats as buttons (triggers on D-input).
        # 3. For each GC logical axis bound as a joystick button, assign the
        #    next unbound evdev axis code → button record (in GC axis order).
        self._sdl_button_to_label = {}
        self._evdev_axis_to_sdl_record = {}

        try:
            if _sdl.SDL_IsGameController(best_index):
                gc = _sdl.SDL_GameControllerOpen(best_index)
                if gc:
                    # Step 1: button labels from GC button binds
                    for btn_enum, label in _SDL_CONTROLLER_BUTTON_LABELS.items():
                        bind = _sdl.SDL_GameControllerGetBindForButton(gc, btn_enum)
                        if bind.bindType == _SDL_CONTROLLER_BINDTYPE_BUTTON:
                            self._sdl_button_to_label[bind.value.button] = label

                    # Step 2: find which joystick axis indices are GC-bound
                    gc_bound_joy_axes: set[int] = set()
                    for gc_axis in range(6):
                        b = _sdl.SDL_GameControllerGetBindForAxis(gc, gc_axis)
                        if b.bindType == _SDL_CONTROLLER_BINDTYPE_AXIS:
                            gc_bound_joy_axes.add(b.value.axis)

                    # Unbound joystick axis indices → evdev codes (in sorted order)
                    # These correspond to axes SDL maps as buttons (D-input triggers)
                    unbound_evdev_axes = [
                        code for joy_idx, code in sorted(joy_axis_to_evdev.items())
                        if joy_idx not in gc_bound_joy_axes
                    ]
                    unbound_idx = 0

                    # Step 3: build evdev_axis_to_sdl_record for each GC axis
                    for gc_axis in range(6):
                        bind = _sdl.SDL_GameControllerGetBindForAxis(gc, gc_axis)
                        label_pair = _SDL_CONTROLLER_AXIS_LABELS.get(
                            gc_axis, (f"Axis{gc_axis}", f"Axis{gc_axis}")
                        )

                        if bind.bindType == _SDL_CONTROLLER_BINDTYPE_AXIS:
                            joy_axis = bind.value.axis
                            evdev_code = joy_axis_to_evdev.get(joy_axis)
                            if evdev_code is not None:
                                # Label stored in record — survives after resolver closes
                                self._evdev_axis_to_sdl_record[evdev_code] = {
                                    "type": "axis",
                                    "sdl_axis": joy_axis,
                                    "label_neg": label_pair[0],
                                    "label_pos": label_pair[1],
                                }

                        elif bind.bindType == _SDL_CONTROLLER_BINDTYPE_BUTTON:
                            joy_btn = bind.value.button
                            if joy_btn not in self._sdl_button_to_label:
                                self._sdl_button_to_label[joy_btn] = label_pair[1]
                            if unbound_idx < len(unbound_evdev_axes):
                                evdev_code = unbound_evdev_axes[unbound_idx]
                                label = self._sdl_button_to_label.get(joy_btn, f"Button {joy_btn}")
                                self._evdev_axis_to_sdl_record[evdev_code] = {
                                    "type": "button",
                                    "sdl_button": joy_btn,
                                    "label": label,
                                }
                                log.debug(
                                    "Trigger: evdev axis %d → SDL button %d (%s)",
                                    evdev_code, joy_btn, label,
                                )
                                unbound_idx += 1

                    _sdl.SDL_GameControllerClose(gc)
                    log.debug("Axis records: %s", self._evdev_axis_to_sdl_record)
                    log.debug("Button labels: %s", self._sdl_button_to_label)

        except Exception as exc:
            log.warning("Failed to build SDL GameController mappings: %s", exc)
            self._sdl_button_to_label = {}
            self._evdev_axis_to_sdl_record = {}

        # Fallback: any non-hat axis not covered by GameController API
        for joy_idx, evdev_code in joy_axis_to_evdev.items():
            if evdev_code not in self._evdev_axis_to_sdl_record:
                self._evdev_axis_to_sdl_record[evdev_code] = {
                    "type": "axis",
                    "sdl_axis": joy_idx,
                    "label_neg": f"Axis {joy_idx} -",
                    "label_pos": f"Axis {joy_idx} +",
                }

        log.info(
            "SDL joystick opened: '%s' (buttons=%d, axes=%d, hats=%d)",
            evdev_device_name, self._n_buttons, self._n_axes, self._n_hats,
        )
        return True

    def button_label(self, sdl_button_index: int) -> str:
        """Return a human-readable label for an SDL joystick button index."""
        return self._sdl_button_to_label.get(sdl_button_index, f"Button {sdl_button_index}")

    def close(self) -> None:
        """Close the SDL joystick and release resources."""
        if _sdl is not None and self._joystick is not None:
            _sdl.SDL_JoystickClose(self._joystick)
        if _sdl is not None:
            _sdl.SDL_QuitSubSystem(SDL_INIT_JOYSTICK)
        self._joystick = None
        self._n_buttons = 0
        self._n_axes = 0
        self._n_hats = 0
        self._evdev_axis_to_sdl_record = {}
        self._evdev_hat_to_sdl = {}
        self._evdev_button_to_sdl = {}
        self._sdl_button_to_label = {}
        self._evdev_event_to_sdl = {}

    def resolve(self, evtype: str, code: int, value: int) -> dict | None:
        """Resolve an evdev event to an SDL record.

        evtype: "button" or "axis"
        code:   evdev button code (EV_KEY) or axis code (EV_ABS)
        value:  1 for button press; -1 or +1 for axis direction

        Returns an SDL record dict, or None if not resolvable.
        """
        if self._joystick is None:
            return None

        # --- Priority 1: controller mapping (source of truth) ---
        # Covers every input the user physically pressed during the mapping wizard.
        # For axis events, the mapping stores the evdev type at capture time (button
        # or axis), so we look up by (evtype, code) directly.
        mapping_record = self._evdev_event_to_sdl.get((evtype, code))
        if mapping_record is not None:
            sdl_type = mapping_record.get("type")
            if sdl_type == "button":
                return dict(mapping_record)  # already has label
            elif sdl_type == "axis":
                direction = 1 if value > 0 else -1
                label = mapping_record.get(
                    "label_pos" if direction > 0 else "label_neg", ""
                )
                return {"type": "axis", "sdl_axis": mapping_record["sdl_axis"],
                        "dir": direction, "label": label}
            elif sdl_type == "hat":
                # Hat direction from the axis value (same logic as below)
                if code == 17:
                    direction = "up" if value < 0 else "down"
                else:
                    direction = "left" if value < 0 else "right"
                return {"type": "hat", "sdl_hat": mapping_record.get("sdl_hat", 0),
                        "dir": direction}

        # --- Priority 2: GC API / sorted-position fallback ---

        if evtype == "button":
            sdl_btn = self._evdev_button_to_sdl.get(code)
            if sdl_btn is None:
                return None
            label = self._sdl_button_to_label.get(sdl_btn, f"Button {sdl_btn}")
            return {"type": "button", "sdl_button": sdl_btn, "label": label}

        elif evtype == "axis":
            if code in self._evdev_hat_to_sdl:
                hat_idx = self._evdev_hat_to_sdl[code]
                if code == 17:   # ABS_HAT0Y: -1=up, +1=down
                    direction = "up" if value < 0 else "down"
                else:            # ABS_HAT0X: -1=left, +1=right
                    direction = "left" if value < 0 else "right"
                return {"type": "hat", "sdl_hat": hat_idx, "dir": direction}

            record = self._evdev_axis_to_sdl_record.get(code)
            if record is None:
                return None
            if record["type"] == "button":
                label = record.get("label", f"Button {record['sdl_button']}")
                return {"type": "button", "sdl_button": record["sdl_button"], "label": label}
            else:
                direction = 1 if value > 0 else -1
                label = record.get("label_pos" if direction > 0 else "label_neg", "")
                return {"type": "axis", "sdl_axis": record["sdl_axis"],
                        "dir": direction, "label": label}

        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

resolver = SdlResolver()
