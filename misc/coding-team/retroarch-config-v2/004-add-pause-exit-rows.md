# Task 004 — Add pause_toggle and exit_emulator hotkey rows

## Context

Two hotkey actions were in M6 but omitted from the V2 row list. They need to be added back.

No QML changes needed — `RetroarchHotkeysScreen` is fully data-driven from `_HOTKEY_ROWS`.

## Objective

Add `pause_toggle` (row 11) and `exit_emulator` (row 12) to the hotkey config.

## Scope

### `backend/retroarch_config.py`

Add two entries to `HOTKEY_CFG_KEYS` (insert before `"enable_hotkey"`):

```python
"pause_toggle":         "input_pause_toggle_btn",
"exit_emulator":        "input_exit_emulator_btn",
```

Final key order should be:
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
    "pause_toggle":         "input_pause_toggle_btn",
    "exit_emulator":        "input_exit_emulator_btn",
    "enable_hotkey":        "input_enable_hotkey_btn",
}
```

### `backend/settings_manager.py`

Add two entries to `_HOTKEY_ROWS` (append after `state_slot_decrease`):

```python
{"hotkey_action": "pause_toggle",  "label": "Pause Toggle"},
{"hotkey_action": "exit_emulator", "label": "Exit Emulator"},
```

### `tests/test_retroarch_hotkeys.py`

- `TestNewHotkeyKeys`: add two tests:
  ```python
  def test_pause_toggle_key_present(self):
      assert "pause_toggle" in ra_cfg.HOTKEY_CFG_KEYS
      assert ra_cfg.HOTKEY_CFG_KEYS["pause_toggle"] == "input_pause_toggle_btn"

  def test_exit_emulator_key_present(self):
      assert "exit_emulator" in ra_cfg.HOTKEY_CFG_KEYS
      assert ra_cfg.HOTKEY_CFG_KEYS["exit_emulator"] == "input_exit_emulator_btn"
  ```

- `TestGetRetroarchHotkeyConfig::test_htpc_actions_ordered_correctly` (now tests `hotkey_rows`):
  update the assertion from `len == 10` to `len == 12`, and verify last entry is `exit_emulator`.

- `TestApplyRetroarchHotkeys::test_derives_mapping_from_controller_when_empty` (if it asserts
  a specific count of `nul` keys): update if needed to account for 12 hotkey keys instead of 10.

- `tests/test_settings_backend.py::TestRetroarchHotkeyConfig::test_htpc_actions_has_10_entries`:
  update to assert `len(result["hotkey_rows"]) == 12`.

## Non-goals / Later

- No QML changes.
- No new config.py changes (no new stored fields).
- No rewind changes.

## Constraints / Caveats

- `build_hotkey_cfg()` iterates `HOTKEY_CFG_KEYS` — adding entries there is sufficient for them
  to be written to `retroarch.cfg` on Apply. No other backend changes needed.
- `_HOTKEY_ROWS` drives the QML display. Adding entries there is sufficient for them to appear
  as interactive rows. No QML changes needed.
- After changes, `python3 -m pytest tests/ -q` must show 0 failures.
