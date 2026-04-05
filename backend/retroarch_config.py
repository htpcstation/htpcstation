"""Read/write RetroArch hotkey configuration in retroarch.cfg."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RETROARCH_CFG = (
    Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"
)

# Hotkey action name → retroarch.cfg key
HOTKEY_CFG_KEYS: dict[str, str] = {
    "menu_toggle":       "input_menu_toggle_btn",
    "exit_emulator":     "input_exit_emulator_btn",
    "save_state":        "input_save_state_btn",
    "load_state":        "input_load_state_btn",
    "state_slot_minus":  "input_state_slot_decrease_btn",
    "state_slot_plus":   "input_state_slot_increase_btn",
    "pause_toggle":      "input_pause_toggle_btn",
    "screenshot":        "input_screenshot_btn",
    "rewind":            "input_rewind_btn",
    "fast_forward":      "input_fast_forward_btn",
    "enable_hotkey":     "input_enable_hotkey_btn",
}

# HTPC Station action name → hotkey action name (for default mapping)
HTPC_TO_HOTKEY: dict[str, str] = {
    "accept":          "menu_toggle",
    "cancel":          "exit_emulator",
    "context1":        "save_state",
    "context2":        "load_state",
    "left_shoulder":   "state_slot_minus",
    "right_shoulder":  "state_slot_plus",
    "start":           "pause_toggle",
    "select":          "screenshot",
    "left_trigger":    "rewind",
    "right_trigger":   "fast_forward",
}

# Static evdev button code → SDL joypad index for 8BitDo Micro D-input.
# SDL indices are determined by the SDL gamepad database entry for this device.
# This table covers all buttons in DEFAULT_MAPPING plus BTN_MODE (Home).
# For unknown controllers, fall back to None (write "nul").
EVDEV_TO_SDL: dict[int, int] = {
    305: 0,   # BTN_EAST   → SDL 0
    304: 1,   # BTN_SOUTH  → SDL 1
    308: 2,   # BTN_WEST   → SDL 2
    307: 3,   # BTN_NORTH  → SDL 3
    310: 4,   # BTN_TL     → SDL 4
    311: 5,   # BTN_TR     → SDL 5
    314: 6,   # BTN_SELECT → SDL 6
    315: 7,   # BTN_START  → SDL 7
    316: 8,   # BTN_MODE   → SDL 8  (Home button)
    312: 9,   # BTN_TL2    → SDL 9
    313: 10,  # BTN_TR2    → SDL 10
    317: 11,  # BTN_THUMBL → SDL 11
    318: 12,  # BTN_THUMBR → SDL 12
}


def evdev_code_to_sdl_index(evdev_code: int) -> int | None:
    """Return SDL joypad index for an evdev button code, or None if unknown."""
    return EVDEV_TO_SDL.get(evdev_code)


def read_cfg(path: Path) -> dict[str, str]:
    """Read retroarch.cfg into a dict. Returns {} if file missing.

    Parses flat ``key = value`` lines. Strips quotes from values. Skips
    comment lines (starting with ``#``) and blank lines.
    """
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("read_cfg: could not read %s: %s", path, exc)
        return {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding double-quotes if present
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        result[key] = value
    return result


def write_cfg(path: Path, updates: dict[str, str]) -> None:
    """Write key=value pairs into retroarch.cfg.

    Reads existing file, updates/adds the given keys, writes back.
    Creates file and parent dirs if missing.
    Preserves all existing keys not in updates.
    """
    # Read existing content (preserving order and comments)
    existing_lines: list[str] = []
    if path.exists():
        try:
            existing_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("write_cfg: could not read %s: %s", path, exc)

    # Track which update keys have been written
    written: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            new_lines.append(f"{key} = {updates[key]}")
            written.add(key)
        else:
            new_lines.append(line)

    # Append any keys not already present in the file
    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key} = {value}")

    # Ensure parent directory exists
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.error("write_cfg: could not write %s: %s", path, exc)
        raise


def build_hotkey_cfg(
    hotkey_mapping: dict[str, int | None],  # hotkey_action → SDL index or None
    modifier_sdl: int | None,               # SDL index for enable_hotkey, or None
) -> dict[str, str]:
    """Convert hotkey mapping to retroarch.cfg key=value pairs.

    Returns dict ready to pass to write_cfg().
    None values write "nul". Includes input_enable_hotkey_btn.
    """
    result: dict[str, str] = {}

    for hotkey_action, cfg_key in HOTKEY_CFG_KEYS.items():
        if hotkey_action == "enable_hotkey":
            sdl_index = modifier_sdl
        else:
            sdl_index = hotkey_mapping.get(hotkey_action)

        if sdl_index is None:
            result[cfg_key] = "nul"
        else:
            result[cfg_key] = str(sdl_index)

    return result
