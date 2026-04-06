"""Read/write RetroArch hotkey configuration in retroarch.cfg."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RETROARCH_CFG = (
    Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"
)

# Hotkey action name → dict of three parallel cfg keys (btn / axis / hat)
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
