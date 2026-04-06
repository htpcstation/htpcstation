"""Controller mapping configuration for HTPC Station.

Stores and loads evdev button/axis mappings from a JSON config file.
Provides a unified runtime lookup table for use by gamepad.py.

This is a pure data module — no Qt widget dependencies, only Qt.Key enum.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional evdev import — graceful fallback when absent
# ---------------------------------------------------------------------------

try:
    from evdev import ecodes

    _EVDEV_AVAILABLE = True
except ImportError:  # pragma: no cover
    ecodes = None  # type: ignore[assignment]
    _EVDEV_AVAILABLE = False

# ---------------------------------------------------------------------------
# Semantic action definitions
# ---------------------------------------------------------------------------

# Each entry: (action_name, display_name, qt_key, skippable)
ACTIONS: list[tuple[str, str, Qt.Key, bool]] = [
    ("dpad_up",         "D-pad Up",              Qt.Key.Key_Up,       False),
    ("dpad_down",       "D-pad Down",            Qt.Key.Key_Down,     False),
    ("dpad_left",       "D-pad Left",            Qt.Key.Key_Left,     False),
    ("dpad_right",      "D-pad Right",           Qt.Key.Key_Right,    False),
    ("accept",          "Face Button East",       Qt.Key.Key_Return,   False),
    ("cancel",          "Face Button South",      Qt.Key.Key_Escape,   False),
    ("context1",        "Face Button North",      Qt.Key.Key_F1,       False),
    ("context2",        "Face Button West",       Qt.Key.Key_F2,       False),
    ("left_shoulder",   "Left Shoulder",          Qt.Key.Key_PageUp,   True),
    ("right_shoulder",  "Right Shoulder",         Qt.Key.Key_PageDown, True),
    ("left_trigger",    "Left Trigger",           Qt.Key.Key_Home,     True),
    ("right_trigger",   "Right Trigger",          Qt.Key.Key_End,      True),
    ("start",           "Start",                  Qt.Key.Key_F10,      False),
    ("select",          "Select",                 Qt.Key.Key_F9,       False),
]

# Convenience lookup: action_name → Qt.Key
_ACTION_KEY_MAP: dict[str, Qt.Key] = {name: key for name, _, key, _ in ACTIONS}

# ---------------------------------------------------------------------------
# Default mapping — mirrors the hardcoded values previously in gamepad.py
# Raw int values are used so this works even without evdev installed.
# ---------------------------------------------------------------------------

# evdev ecodes values (hard-coded as ints for evdev-absent environments)
_BTN_SOUTH  = 304
_BTN_EAST   = 305
_BTN_NORTH  = 307
_BTN_WEST   = 308
_BTN_TL     = 310
_BTN_TR     = 311
_BTN_SELECT = 314
_BTN_START  = 315
_ABS_Z      = 2
_ABS_RZ     = 5
_ABS_HAT0X  = 16
_ABS_HAT0Y  = 17

DEFAULT_MAPPING: dict[str, dict] = {
    "dpad_up":        {"evdev": {"type": "axis",   "code": _ABS_HAT0Y,  "value": -1}, "sdl": None},
    "dpad_down":      {"evdev": {"type": "axis",   "code": _ABS_HAT0Y,  "value":  1}, "sdl": None},
    "dpad_left":      {"evdev": {"type": "axis",   "code": _ABS_HAT0X,  "value": -1}, "sdl": None},
    "dpad_right":     {"evdev": {"type": "axis",   "code": _ABS_HAT0X,  "value":  1}, "sdl": None},
    "accept":         {"evdev": {"type": "button", "code": _BTN_EAST,   "value":  1}, "sdl": None},
    "cancel":         {"evdev": {"type": "button", "code": _BTN_SOUTH,  "value":  1}, "sdl": None},
    "context1":       {"evdev": {"type": "button", "code": _BTN_NORTH,  "value":  1}, "sdl": None},
    "context2":       {"evdev": {"type": "button", "code": _BTN_WEST,   "value":  1}, "sdl": None},
    "left_shoulder":  {"evdev": {"type": "button", "code": _BTN_TL,     "value":  1}, "sdl": None},
    "right_shoulder": {"evdev": {"type": "button", "code": _BTN_TR,     "value":  1}, "sdl": None},
    "left_trigger":   {"evdev": {"type": "axis",   "code": _ABS_Z,      "value":  1}, "sdl": None},
    "right_trigger":  {"evdev": {"type": "axis",   "code": _ABS_RZ,     "value":  1}, "sdl": None},
    "start":          {"evdev": {"type": "button", "code": _BTN_START,  "value":  1}, "sdl": None},
    "select":         {"evdev": {"type": "button", "code": _BTN_SELECT, "value":  1}, "sdl": None},
}

# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def get_mapping_path() -> Path:
    """Return the path to the controller mapping config file."""
    return Path.home() / ".config" / "htpcstation" / "controller_mapping.json"


def get_default_mapping() -> dict[str, dict]:
    """Return a deep copy of DEFAULT_MAPPING."""
    import copy
    return copy.deepcopy(DEFAULT_MAPPING)


def load_mapping() -> dict[str, dict]:
    """Load mapping from file; fall back to DEFAULT_MAPPING if missing or corrupt.

    Supports migration from the old single-record format (pre-008-B):
    entries without an ``evdev`` key are wrapped as ``{"evdev": old_entry, "sdl": None}``.

    The ``_device`` key (legacy) is silently dropped on load.
    """
    path = get_mapping_path()
    if not path.exists():
        return get_default_mapping()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("Mapping file root must be a JSON object")
        # Validate and merge with defaults so new actions always have entries
        result = get_default_mapping()
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
                result[action] = {
                    "evdev": evdev_part,
                    "sdl": sdl_part,
                    "also": entry.get("also") or [],
                }
        return result
    except Exception as exc:
        log.warning("Failed to load controller mapping from %s: %s — using defaults", path, exc)
        return get_default_mapping()


def save_mapping(mapping: dict[str, dict]) -> None:
    """Atomically write mapping to the config file."""
    path = get_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to a temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".controller_mapping_", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

# ---------------------------------------------------------------------------
# Runtime lookup builder
# ---------------------------------------------------------------------------

# evdev event type constants (hard-coded for evdev-absent environments)
_EV_KEY = 1
_EV_ABS = 3


def build_evdev_lookup(mapping: dict[str, dict]) -> dict[tuple[int, int, int], Qt.Key]:
    """Build a unified runtime lookup: (ev_type, ev_code, ev_value_sign) → Qt.Key.

    For button entries (type="button"):
        key is (EV_KEY, code, 1)

    For axis entries (type="axis"):
        key is (EV_ABS, code, sign) where sign is -1 or 1

    Returns an empty dict when evdev is not available (so callers can safely
    check membership without special-casing the absent-evdev path).
    """
    if not _EVDEV_AVAILABLE:
        return {}

    lookup: dict[tuple[int, int, int], Qt.Key] = {}

    for action_name, entry in mapping.items():
        qt_key = _ACTION_KEY_MAP.get(action_name)
        if qt_key is None:
            continue  # Unknown action — skip

        evdev_part = entry.get("evdev") if isinstance(entry, dict) else None
        if not isinstance(evdev_part, dict):
            continue

        ev_type_str = evdev_part.get("type")
        code = evdev_part.get("code")
        value = evdev_part.get("value")

        if not isinstance(code, int) or not isinstance(value, int):
            continue

        if ev_type_str == "button":
            lookup[(ecodes.EV_KEY, code, 1)] = qt_key  # type: ignore[union-attr]
        elif ev_type_str == "axis":
            sign = 1 if value >= 0 else -1
            lookup[(ecodes.EV_ABS, code, sign)] = qt_key  # type: ignore[union-attr]

    return lookup


# ---------------------------------------------------------------------------
# Web Gamepad API mapping generation
# ---------------------------------------------------------------------------

# Translation from our semantic action names to the names content.js expects.
_WEB_ACTION_NAMES: dict[str, str] = {
    "dpad_up":        "up",
    "dpad_down":      "down",
    "dpad_left":      "left",
    "dpad_right":     "right",
    "accept":         "accept",
    "cancel":         "cancel",
    "context1":       "contextAction1",
    "context2":       "contextAction2",
    "left_shoulder":  "leftBumper",
    "right_shoulder": "rightBumper",
    "left_trigger":   "leftTrigger",
    "right_trigger":  "rightTrigger",
    "start":          "start",
    "select":         "select",
}


def build_web_gamepad_mapping(mapping: dict, button_layout: str = "standard") -> Optional[dict]:
    """Generate a Web Gamepad API button/axis mapping from the stored config.

    Reads the ``sdl`` half of each dual-record entry. Returns None if no entry
    has a non-null sdl half (user has not run the mapping dialog with SDL support).

    Returns a dict with keys:
        ``buttons``     — {web_index: action_name}
        ``axes``        — {web_index: [neg_action, pos_action]}
        ``dpadButtons`` — {web_index: True} for D-pad button indices
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


def generate_mapping_js(mapping: dict, button_layout: str = "standard") -> str:
    """Generate a JavaScript snippet that sets ``window.__htpcGeneratedMapping``.

    Returns a string of valid JavaScript.  If the mapping has no ``_device``
    info, returns a comment-only stub so the extension falls back to defaults.
    """
    web_mapping = build_web_gamepad_mapping(mapping, button_layout=button_layout)
    if web_mapping is None:
        return "// No device capabilities recorded — extension will use defaults.\n"

    # Serialise to JSON and wrap in a JS assignment
    payload = json.dumps(web_mapping, indent=2)
    return f"window.__htpcGeneratedMapping = {payload};\n"
