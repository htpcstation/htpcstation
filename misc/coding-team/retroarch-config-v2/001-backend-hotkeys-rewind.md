# Task 001 — Backend: hotkey keys + rewind config

## Context

M6 shipped `retroarch_config.py` with a 10-hotkey mapping derived from HTPC controller actions.
V2 replaces that with a direct hotkey-function-centric model (no HTPC action indirection) and
adds three rewind settings written to `retroarch.cfg` on Apply.

Reference files:
- `backend/retroarch_config.py`
- `backend/config.py` (search for `hotkey_modifier_evdev` to find the retroarch section)
- `backend/settings_manager.py` (search for `getRetroarchHotkeyConfig`)
- `tests/test_retroarch_hotkeys.py` — will be updated in Task 003; do NOT touch tests here

## Objective

1. Update `HOTKEY_CFG_KEYS` in `retroarch_config.py`.
2. Remove `HTPC_TO_HOTKEY` from `retroarch_config.py`.
3. Add rewind properties to `config.py`.
4. Update `settings_manager.py`: new `getRetroarchHotkeyConfig()` shape, new rewind slots, updated `applyRetroarchHotkeys()`.

## Scope

### `backend/retroarch_config.py`

Replace `HOTKEY_CFG_KEYS` with:

```python
HOTKEY_CFG_KEYS: dict[str, str] = {
    "save_state":           "input_save_state_btn",
    "load_state":           "input_load_state_btn",
    "fast_forward_toggle":  "input_toggle_fast_forward_btn",
    "fast_forward_hold":    "input_hold_fast_forward_btn",
    "rewind":               "input_rewind_btn",
    "menu_toggle":          "input_menu_toggle_btn",
    "screenshot":           "input_screenshot_btn",
    "show_fps":             "input_toggle_statistics_btn",
    "state_slot_increase":  "input_state_slot_increase_btn",
    "state_slot_decrease":  "input_state_slot_decrease_btn",
    "enable_hotkey":        "input_enable_hotkey_btn",
}
```

Remove `HTPC_TO_HOTKEY` entirely.

`build_hotkey_cfg()` signature and logic are unchanged — it already iterates `HOTKEY_CFG_KEYS`
and handles `enable_hotkey` specially. No changes needed there.

### `backend/config.py`

In `__init__`, alongside the existing hotkey fields, add:

```python
self._rewind_enable: bool = False
self._rewind_buffer_size: int = 20      # MB
self._rewind_granularity: int = 1       # frames
```

Add properties and setters (same pattern as `hotkey_modifier_evdev`):

```python
@property
def rewind_enable(self) -> bool: ...

def set_rewind_enable(self, value: bool) -> None:
    self._rewind_enable = value
    self.save()

@property
def rewind_buffer_size(self) -> int: ...

def set_rewind_buffer_size(self, value: int) -> None:
    self._rewind_buffer_size = value
    self.save()

@property
def rewind_granularity(self) -> int: ...

def set_rewind_granularity(self, value: int) -> None:
    self._rewind_granularity = value
    self.save()
```

In `save()`, add to the `retroarch` dict:

```python
"rewind_enable": self._rewind_enable,
"rewind_buffer_size": self._rewind_buffer_size,
"rewind_granularity": self._rewind_granularity,
```

In `_load()`, read them back from the `retroarch` section (same pattern as `hotkey_modifier_evdev`).
Use `bool()` coercion for `rewind_enable`, `int()` for the two size fields.
Guard with `isinstance` checks — malformed JSON should fall back to defaults silently.

### `backend/settings_manager.py`

**`_HTPC_ACTION_ORDER`** — remove this class attribute entirely.

**`_EVDEV_LABELS`** — keep as-is (still needed for modifier label).

**New class attribute** — ordered hotkey rows for the UI:

```python
_HOTKEY_ROWS: list[dict] = [
    {"hotkey_action": "save_state",          "label": "Save State"},
    {"hotkey_action": "load_state",          "label": "Load State"},
    {"hotkey_action": "fast_forward_toggle", "label": "Fast Forward (Toggle)"},
    {"hotkey_action": "fast_forward_hold",   "label": "Fast Forward (Hold)"},
    {"hotkey_action": "rewind",              "label": "Rewind"},
    {"hotkey_action": "menu_toggle",         "label": "Open Menu"},
    {"hotkey_action": "screenshot",          "label": "Screenshot"},
    {"hotkey_action": "show_fps",            "label": "Show FPS"},
    {"hotkey_action": "state_slot_increase", "label": "Next Save Slot"},
    {"hotkey_action": "state_slot_decrease", "label": "Previous Save Slot"},
]
```

**`getRetroarchHotkeyConfig()`** — simplify. Remove the first-run derivation from controller
mapping entirely. The mapping is now always `config.hotkey_mapping` (empty dict = nothing
assigned yet, which is fine — QML shows "Not set"). Build `hotkey_rows` from `_HOTKEY_ROWS`:

```python
hotkey_rows = []
for row in self._HOTKEY_ROWS:
    action = row["hotkey_action"]
    sdl_index = mapping.get(action)
    evdev_code = self._sdl_to_evdev(sdl_index)  # reverse lookup for label
    hotkey_rows.append({
        "hotkey_action": action,
        "label": row["label"],
        "sdl_index": sdl_index,
        "button_label": self._get_hotkey_button_label(evdev_code) if evdev_code is not None else "",
    })
```

Add a `_sdl_to_evdev()` helper that reverses `EVDEV_TO_SDL` (build a reverse dict once as a
class-level or module-level constant — `SDL_TO_EVDEV: dict[int, int]`).

Return dict gains three new keys:

```python
"rewind_enable": self._config.rewind_enable,
"rewind_buffer_size": self._config.rewind_buffer_size,
"rewind_granularity": self._config.rewind_granularity,
```

Rename `htpc_actions` key to `hotkey_rows` in the returned dict.

**`applyRetroarchHotkeys()`** — after writing hotkey cfg, also write rewind keys:

```python
rewind_updates = {
    "rewind_enable": "true" if self._config.rewind_enable else "false",
    "rewind_buffer_size": str(self._config.rewind_buffer_size),
    "rewind_granularity": str(self._config.rewind_granularity),
}
_ra_cfg.write_cfg(cfg_path, rewind_updates)
```

Remove the first-run derivation block from `applyRetroarchHotkeys()` too (same logic as above —
no more HTPC mapping derivation).

**New slots** for rewind:

```python
@Slot(bool)
def setRewindEnable(self, value: bool) -> None:
    self._config.set_rewind_enable(value)

@Slot(int)
def setRewindBufferSize(self, value: int) -> None:
    self._config.set_rewind_buffer_size(value)

@Slot(int)
def setRewindGranularity(self, value: int) -> None:
    self._config.set_rewind_granularity(value)
```

No Q_PROPERTYs needed for rewind — QML reads them via `getRetroarchHotkeyConfig()` on open.

## Non-goals / Later

- Do NOT touch any QML files.
- Do NOT touch test files (Task 003).
- Do NOT add Q_PROPERTYs for rewind settings.
- Do NOT implement per-system overrides.

## Constraints / Caveats

- `Config.save()` has a guard that refuses to write if in-memory token+server_id are blank but
  on-disk file has credentials. The rewind setters call `self.save()` — this is fine, same
  pattern as all other setters.
- `SDL_TO_EVDEV` reverse map: build from `EVDEV_TO_SDL` in `retroarch_config.py`. Since all SDL
  indices are unique (confirmed by existing test), the reverse is unambiguous.
- The `hotkey_mapping` dict in config stores `hotkey_action → SDL index`. The new key names
  (`fast_forward_toggle`, `fast_forward_hold`, `show_fps`) must match exactly what QML will
  pass to `setHotkeyAction()`.
- `setHotkeyAction(hotkey_action, sdl_index)` already exists and is unchanged — it just stores
  into the mapping dict. No changes needed.
