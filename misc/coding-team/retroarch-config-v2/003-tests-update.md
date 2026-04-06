# Task 003 — Tests: update existing + add new coverage

## Context

Tasks 001 and 002 changed the backend. 12 tests are currently failing because they reference
the old API (`htpc_actions`, `HTPC_TO_HOTKEY`, first-run controller derivation, old cfg keys).
This task fixes those tests and adds new coverage for the V2 features.

Currently failing:
- `tests/test_retroarch_hotkeys.py` — 8 failures
- `tests/test_settings_backend.py::TestRetroarchHotkeyConfig` — 4 failures

Run to confirm before starting:
```
python3 -m pytest tests/test_retroarch_hotkeys.py tests/test_settings_backend.py -q -k "retroarch or Retroarch or hotkey or Hotkey" 2>&1 | tail -20
```

## Objective

1. Fix all 12 failing tests.
2. Add new tests for: rewind config (config.py), rewind slots (settings_manager), new hotkey keys
   (`fast_forward_toggle`, `fast_forward_hold`, `show_fps`), `setHotkeyActionByEvdev`,
   `clearHotkeyAction`, `applyRetroarchHotkeys` writes rewind keys.

## Scope

### `tests/test_retroarch_hotkeys.py`

**`TestBuildHotkeyCfg`** — two failures:

- `test_integer_values_written_as_strings`: passes `{"menu_toggle": 3, "exit_emulator": 1}` but
  `exit_emulator` is no longer in `HOTKEY_CFG_KEYS`. Fix: replace `exit_emulator` with
  `load_state` (which IS in the new keys). Assert `input_load_state_btn` instead of
  `input_exit_emulator_btn`.

- `test_missing_hotkey_action_writes_nul`: passes `{"menu_toggle": 3}` and asserts
  `input_exit_emulator_btn == "nul"`. Fix: assert `input_load_state_btn == "nul"` instead
  (any key that's in `HOTKEY_CFG_KEYS` but not in the mapping dict).

**`TestGetRetroarchHotkeyConfig`** — four failures:

- `test_returns_expected_keys`: asserts `"htpc_actions" in result`. Fix: assert
  `"hotkey_rows" in result` instead. Also assert `"rewind_enable"`, `"rewind_buffer_size"`,
  `"rewind_granularity"` are in result.

- `test_htpc_actions_ordered_correctly`: tests old `htpc_actions` order. Replace entirely:
  assert `result["hotkey_rows"]` has 10 entries and the first is `"save_state"`, last is
  `"state_slot_decrease"`.

- `test_htpc_actions_have_required_keys`: tests old keys on `htpc_actions` rows. Replace:
  assert each row in `result["hotkey_rows"]` has keys `hotkey_action`, `label`, `sdl_index`,
  `button_label`.

- `test_first_run_derives_mapping_from_controller`: tests the removed first-run derivation.
  Replace entirely with a test that verifies: when `hotkey_mapping` is empty, `hotkey_rows`
  all have `sdl_index == None` and `button_label == ""`.

**`TestApplyRetroarchHotkeys`** — two failures:

- `test_writes_cfg_keys_to_file`: asserts `input_exit_emulator_btn` in result. Fix: replace
  with `input_load_state_btn` (use `load_state: 1` in the mapping dict).

- `test_derives_mapping_from_controller_when_empty`: tests removed first-run derivation.
  Replace with: when `hotkey_mapping` is empty, `applyRetroarchHotkeys()` writes `nul` for
  all hotkey keys (no derivation from controller mapping).

**New test classes to add to `test_retroarch_hotkeys.py`:**

```python
class TestNewHotkeyKeys:
    """Verify the new/renamed keys are in HOTKEY_CFG_KEYS."""
    def test_fast_forward_toggle_key_present(self):
        assert "fast_forward_toggle" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_toggle"] == "input_toggle_fast_forward_btn"

    def test_fast_forward_hold_key_present(self):
        assert "fast_forward_hold" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_hold"] == "input_hold_fast_forward_btn"

    def test_show_fps_key_present(self):
        assert "show_fps" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["show_fps"] == "input_toggle_statistics_btn"

    def test_old_fast_forward_key_removed(self):
        # The old "fast_forward" key (input_fast_forward_btn) is gone
        assert "fast_forward" not in ra_cfg.HOTKEY_CFG_KEYS

    def test_htpc_to_hotkey_removed(self):
        assert not hasattr(ra_cfg, "HTPC_TO_HOTKEY")


class TestSetHotkeyActionByEvdev:
    def test_known_evdev_code_sets_sdl_index(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        manager.setHotkeyActionByEvdev("save_state", 305)  # BTN_EAST → SDL 0
        assert config.hotkey_mapping["save_state"] == 0

    def test_unknown_evdev_code_sets_none(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        manager.setHotkeyActionByEvdev("save_state", 9999)
        assert config.hotkey_mapping["save_state"] is None

    def test_overwrites_existing_mapping(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 5}
        manager.setHotkeyActionByEvdev("save_state", 316)  # BTN_MODE → SDL 8
        assert config.hotkey_mapping["save_state"] == 8


class TestClearHotkeyAction:
    def test_sets_action_to_none(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 3}
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["save_state"] is None

    def test_adds_none_entry_for_unset_action(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["save_state"] is None

    def test_does_not_affect_other_actions(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": 3, "load_state": 1}
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["load_state"] == 1
```

**New rewind tests in `test_retroarch_hotkeys.py`:**

```python
class TestConfigRewindProperties:
    def test_rewind_enable_default_false(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.rewind_enable is False

    def test_rewind_buffer_size_default_20(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.rewind_buffer_size == 20

    def test_rewind_granularity_default_1(self, tmp_path):
        config = _make_config(tmp_path)
        assert config.rewind_granularity == 1

    def test_set_rewind_enable_persists(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_enable(True)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_enable"] is True

    def test_set_rewind_buffer_size_persists(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_buffer_size(100)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_buffer_size"] == 100

    def test_set_rewind_granularity_persists(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_granularity(8)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_granularity"] == 8

    def test_load_rewind_fields_from_json(self, tmp_path):
        config = _make_config(tmp_path, {
            "retroarch": {
                "rewind_enable": True,
                "rewind_buffer_size": 200,
                "rewind_granularity": 4,
            }
        })
        assert config.rewind_enable is True
        assert config.rewind_buffer_size == 200
        assert config.rewind_granularity == 4

    def test_malformed_rewind_fields_use_defaults(self, tmp_path):
        config = _make_config(tmp_path, {
            "retroarch": {
                "rewind_enable": "not_a_bool",
                "rewind_buffer_size": "not_an_int",
                "rewind_granularity": None,
            }
        })
        # Malformed values fall back to defaults
        assert config.rewind_buffer_size == 20
        assert config.rewind_granularity == 1


class TestRewindSlots:
    def test_set_rewind_enable(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        manager.setRewindEnable(True)
        assert config.rewind_enable is True

    def test_set_rewind_buffer_size(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        manager.setRewindBufferSize(150)
        assert config.rewind_buffer_size == 150

    def test_set_rewind_granularity(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        manager.setRewindGranularity(16)
        assert config.rewind_granularity == 16


class TestApplyRetroarchHotkeysWritesRewind:
    def test_apply_writes_rewind_enable_true(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_enable = True
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_enable"] == "true"

    def test_apply_writes_rewind_enable_false(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_enable = False
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_enable"] == "false"

    def test_apply_writes_rewind_buffer_size(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_buffer_size = 200
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_buffer_size"] == "200"

    def test_apply_writes_rewind_granularity(self, tmp_path):
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_granularity = 8
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_granularity"] == "8"
```

### `tests/test_settings_backend.py` — `TestRetroarchHotkeyConfig` class (4 failures)

- `test_get_config_returns_expected_shape`: asserts `"htpc_actions"` key. Fix: assert
  `"hotkey_rows"` key instead. Also assert `"rewind_enable"`, `"rewind_buffer_size"`,
  `"rewind_granularity"` present.

- `test_htpc_actions_has_10_entries`: asserts `len(result["htpc_actions"]) == 10`. Fix:
  assert `len(result["hotkey_rows"]) == 10`.

- `test_apply_retroarch_hotkeys_writes_cfg`: asserts `input_exit_emulator_btn`. Fix: assert
  `input_load_state_btn` (use `load_state` in the mapping dict).

- `test_first_run_derives_mapping_from_controller`: tests removed derivation. Replace with:
  when `hotkey_mapping` is empty, `hotkey_rows` all have `sdl_index` as `None`.

## Non-goals / Later

- Do NOT add QML tests (no QML test infrastructure exists).
- Do NOT add tests for `ModifierCaptureDialog` hold mechanic (QML-only).
- Do NOT change any non-retroarch tests.

## Constraints / Caveats

- The `_make_config` and `_make_manager` helpers already exist in `test_retroarch_hotkeys.py`.
  Reuse them for all new test classes.
- `test_malformed_rewind_fields_use_defaults`: the `rewind_enable` field with value
  `"not_a_bool"` — check how `config.py` handles it. If it uses `bool()` coercion,
  `bool("not_a_bool")` is `True` (non-empty string). The brief says "malformed JSON falls back
  to defaults silently" — verify the actual implementation before writing the assertion.
  Use `isinstance(raw, bool)` guard in the test expectation to match what the code actually does.
- After all fixes, the full test suite must show **0 failures**.

## Acceptance criteria

- `python3 -m pytest tests/ -q 2>&1 | tail -5` shows 0 failures.
- New test count is at least 1,792 + 30 (approximate — exact count will vary).
