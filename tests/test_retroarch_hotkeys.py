"""Tests for M6 Task 001 — RetroArch hotkey backend (updated for 008-C dual-record).

Covers:
  - retroarch_config: read_cfg / write_cfg / build_hotkey_cfg (SDL record format)
  - config.py: hotkey_modifier_evdev, hotkey_modifier_sdl, hotkey_mapping, retroarch_cfg_path
  - config.py: save/load round-trip for retroarch hotkey section
  - settings_manager: getRetroarchHotkeyConfig (SDL record format)
  - settings_manager: setHotkeyAction, setHotkeyModifier, clearHotkeyModifier
  - settings_manager: setHotkeyActionByEvdev, setHotkeyActionByAxis
  - settings_manager: applyRetroarchHotkeys writes correct keys to retroarch.cfg
  - settings_manager: getRetroarchCfgPath / setRetroarchCfgPath
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import Config
import backend.retroarch_config as ra_cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, data: dict | None = None) -> Config:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(data or {}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


def _make_manager(tmp_path: Path, config_data: dict | None = None):
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data or {}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    manager = SettingsManager(config, library, plex_library)
    return manager, config


# ===========================================================================
# retroarch_config — read_cfg
# ===========================================================================


class TestReadCfg:
    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        result = ra_cfg.read_cfg(tmp_path / "nonexistent.cfg")
        assert result == {}

    def test_parses_key_value_pairs(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text('input_menu_toggle_btn = 3\ninput_exit_emulator_btn = 1\n')
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "3"
        assert result["input_exit_emulator_btn"] == "1"

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text('# This is a comment\ninput_menu_toggle_btn = 5\n')
        result = ra_cfg.read_cfg(cfg)
        assert "# This is a comment" not in result
        assert result["input_menu_toggle_btn"] == "5"

    def test_strips_double_quotes_from_values(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text('video_driver = "gl"\n')
        result = ra_cfg.read_cfg(cfg)
        assert result["video_driver"] == "gl"

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text('\n\ninput_menu_toggle_btn = 2\n\n')
        result = ra_cfg.read_cfg(cfg)
        assert result == {"input_menu_toggle_btn": "2"}

    def test_nul_value_preserved(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text('input_menu_toggle_btn = nul\n')
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "nul"


# ===========================================================================
# retroarch_config — write_cfg
# ===========================================================================


class TestWriteCfg:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        cfg = tmp_path / "sub" / "retroarch.cfg"
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "3"})
        assert cfg.exists()
        content = cfg.read_text()
        assert "input_menu_toggle_btn = 3" in content

    def test_updates_existing_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("input_menu_toggle_btn = 0\n")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "5"})
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "5"

    def test_preserves_unrelated_keys(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("video_driver = gl\ninput_menu_toggle_btn = 0\n")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "3"})
        result = ra_cfg.read_cfg(cfg)
        assert result["video_driver"] == "gl"
        assert result["input_menu_toggle_btn"] == "3"

    def test_appends_new_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("video_driver = gl\n")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "7"})
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "7"
        assert result["video_driver"] == "gl"

    def test_values_are_unquoted_integers(self, tmp_path: Path) -> None:
        """retroarch.cfg values must be unquoted integers, not strings."""
        cfg = tmp_path / "retroarch.cfg"
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "3"})
        raw = cfg.read_text()
        assert '"3"' not in raw
        assert "input_menu_toggle_btn = 3" in raw

    def test_preserves_comment_lines(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("# My comment\ninput_menu_toggle_btn = 0\n")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "2"})
        raw = cfg.read_text()
        assert "# My comment" in raw


# ===========================================================================
# retroarch_config — build_hotkey_cfg (SDL record format)
# ===========================================================================


class TestBuildHotkeyCfg:
    def test_none_values_write_nul_for_all_three_keys(self) -> None:
        """None SDL record writes nul for btn, axis, and hat keys."""
        mapping = {action: None for action in ra_cfg.HOTKEY_CFG_KEYS if action != "enable_hotkey"}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_enable_hotkey_btn"] == "nul"
        assert result["input_enable_hotkey_axis"] == "nul"
        assert result["input_enable_hotkey_hat"] == "nul"
        assert result["input_menu_toggle_btn"] == "nul"
        assert result["input_menu_toggle_axis"] == "nul"
        assert result["input_menu_toggle_hat"] == "nul"

    def test_button_record_writes_btn_key(self) -> None:
        """Button SDL record writes btn key, nul for axis and hat."""
        mapping = {"save_state": {"type": "button", "sdl_button": 3}}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_save_state_btn"] == "3"
        assert result["input_save_state_axis"] == "nul"
        assert result["input_save_state_hat"] == "nul"

    def test_axis_record_positive_direction(self) -> None:
        """Axis SDL record with dir=+1 writes +N to axis key."""
        mapping = {"save_state": {"type": "axis", "sdl_axis": 2, "dir": 1}}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_save_state_btn"] == "nul"
        assert result["input_save_state_axis"] == "+2"
        assert result["input_save_state_hat"] == "nul"

    def test_axis_record_negative_direction(self) -> None:
        """Axis SDL record with dir=-1 writes -N to axis key."""
        mapping = {"save_state": {"type": "axis", "sdl_axis": 1, "dir": -1}}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_save_state_axis"] == "-1"

    def test_hat_record_writes_hat_key(self) -> None:
        """Hat SDL record writes hat key in format NNdir."""
        mapping = {"save_state": {"type": "hat", "sdl_hat": 0, "dir": "up"}}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_save_state_btn"] == "nul"
        assert result["input_save_state_axis"] == "nul"
        assert result["input_save_state_hat"] == "0up"

    def test_hat_record_down_direction(self) -> None:
        """Hat SDL record with dir=down writes 0down."""
        mapping = {"load_state": {"type": "hat", "sdl_hat": 0, "dir": "down"}}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl_record=None)
        assert result["input_load_state_hat"] == "0down"

    def test_modifier_button_record_writes_enable_hotkey_btn(self) -> None:
        """Modifier SDL button record writes input_enable_hotkey_btn."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record={"type": "button", "sdl_button": 8})
        assert result["input_enable_hotkey_btn"] == "8"
        assert result["input_enable_hotkey_axis"] == "nul"
        assert result["input_enable_hotkey_hat"] == "nul"

    def test_modifier_none_writes_nul_for_enable_hotkey(self) -> None:
        """None modifier writes nul for all enable_hotkey keys."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record=None)
        assert result["input_enable_hotkey_btn"] == "nul"
        assert result["input_enable_hotkey_axis"] == "nul"
        assert result["input_enable_hotkey_hat"] == "nul"

    def test_modifier_axis_record_writes_nul_btn(self) -> None:
        """Modifier is btn-only: axis SDL record for modifier writes nul for btn."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record={"type": "axis", "sdl_axis": 2, "dir": 1})
        assert result["input_enable_hotkey_btn"] == "nul"
        assert result["input_enable_hotkey_axis"] == "nul"
        assert result["input_enable_hotkey_hat"] == "nul"

    def test_all_hotkey_cfg_keys_present_in_output(self) -> None:
        """build_hotkey_cfg always outputs all HOTKEY_CFG_KEYS (btn/axis/hat for each)."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record=None)
        for action, cfg_keys in ra_cfg.HOTKEY_CFG_KEYS.items():
            for key_type in ("btn", "axis", "hat"):
                assert cfg_keys[key_type] in result, f"Missing key: {cfg_keys[key_type]}"

    def test_missing_hotkey_action_writes_nul(self) -> None:
        """Actions not in the mapping dict are written as nul for all three keys."""
        result = ra_cfg.build_hotkey_cfg({"menu_toggle": {"type": "button", "sdl_button": 3}}, modifier_sdl_record=None)
        assert result["input_load_state_btn"] == "nul"
        assert result["input_load_state_axis"] == "nul"
        assert result["input_load_state_hat"] == "nul"


# ===========================================================================
# Config — hotkey properties
# ===========================================================================


class TestConfigHotkeyProperties:
    def test_hotkey_modifier_evdev_default_is_none(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.hotkey_modifier_evdev is None

    def test_hotkey_modifier_sdl_default_is_none(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.hotkey_modifier_sdl is None

    def test_hotkey_mapping_default_is_empty(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.hotkey_mapping == {}

    def test_retroarch_cfg_path_default_is_flatpak_path(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert "retroarch.cfg" in str(config.retroarch_cfg_path)
        assert "org.libretro.RetroArch" in str(config.retroarch_cfg_path)

    def test_set_hotkey_modifier_evdev_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hotkey_modifier_evdev(316)

        assert config.hotkey_modifier_evdev == 316
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["hotkey_modifier_evdev"] == 316

    def test_set_hotkey_modifier_sdl_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hotkey_modifier_sdl({"type": "button", "sdl_button": 8})

        assert config.hotkey_modifier_sdl == {"type": "button", "sdl_button": 8}
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["hotkey_modifier_sdl"] == {"type": "button", "sdl_button": 8}

    def test_set_hotkey_modifier_evdev_none_saves_null(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hotkey_modifier_evdev(None)

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["hotkey_modifier_evdev"] is None

    def test_set_hotkey_mapping_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hotkey_mapping({
                "menu_toggle": {"type": "button", "sdl_button": 3},
                "exit_emulator": {"type": "button", "sdl_button": 1},
            })

        assert config.hotkey_mapping == {
            "menu_toggle": {"type": "button", "sdl_button": 3},
            "exit_emulator": {"type": "button", "sdl_button": 1},
        }
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["hotkey_mapping"]["menu_toggle"] == {"type": "button", "sdl_button": 3}

    def test_set_retroarch_cfg_path_updates_and_saves(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_retroarch_cfg_path("/tmp/retroarch.cfg")

        assert str(config.retroarch_cfg_path) == "/tmp/retroarch.cfg"
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["retroarch_cfg_path"] == "/tmp/retroarch.cfg"

    def test_retroarch_cfg_path_str_property(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert isinstance(config.retroarch_cfg_path_str, str)
        assert config.retroarch_cfg_path_str == str(config.retroarch_cfg_path)


# ===========================================================================
# Config — save/load round-trip for hotkey section
# ===========================================================================


class TestConfigHotkeyRoundTrip:
    def test_load_reads_hotkey_modifier_evdev(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_modifier_evdev": 316}},
        )
        assert config.hotkey_modifier_evdev == 316

    def test_load_reads_hotkey_modifier_sdl(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_modifier_sdl": {"type": "button", "sdl_button": 8}}},
        )
        assert config.hotkey_modifier_sdl == {"type": "button", "sdl_button": 8}

    def test_load_reads_hotkey_mapping_sdl_records(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_mapping": {
                "menu_toggle": {"type": "button", "sdl_button": 3},
                "exit_emulator": {"type": "axis", "sdl_axis": 2, "dir": 1},
            }}},
        )
        assert config.hotkey_mapping["menu_toggle"] == {"type": "button", "sdl_button": 3}
        assert config.hotkey_mapping["exit_emulator"] == {"type": "axis", "sdl_axis": 2, "dir": 1}

    def test_load_migrates_old_int_mapping_to_button_record(self, tmp_path: Path) -> None:
        """Old int SDL index values are migrated to button records on load."""
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_mapping": {"menu_toggle": 3, "exit_emulator": 1}}},
        )
        assert config.hotkey_mapping["menu_toggle"] == {"type": "button", "sdl_button": 3}
        assert config.hotkey_mapping["exit_emulator"] == {"type": "button", "sdl_button": 1}

    def test_load_reads_retroarch_cfg_path(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            {"retroarch": {"retroarch_cfg_path": "/custom/retroarch.cfg"}},
        )
        assert str(config.retroarch_cfg_path) == "/custom/retroarch.cfg"

    def test_load_hotkey_mapping_null_values(self, tmp_path: Path) -> None:
        """hotkey_mapping values can be null (None) in JSON."""
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_mapping": {"menu_toggle": None}}},
        )
        assert config.hotkey_mapping == {"menu_toggle": None}

    def test_load_missing_hotkey_section_uses_defaults(self, tmp_path: Path) -> None:
        """Config without hotkey keys in retroarch section uses defaults."""
        config = _make_config(tmp_path, {"retroarch": {"command": "retroarch"}})
        assert config.hotkey_modifier_evdev is None
        assert config.hotkey_modifier_sdl is None
        assert config.hotkey_mapping == {}

    def test_save_includes_hotkey_keys(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.save()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        retroarch = saved["retroarch"]
        assert "hotkey_modifier_evdev" in retroarch
        assert "hotkey_modifier_sdl" in retroarch
        assert "hotkey_mapping" in retroarch
        assert "retroarch_cfg_path" in retroarch

    def test_load_ignores_malformed_hotkey_mapping_entries(self, tmp_path: Path) -> None:
        """Malformed entries (wrong type) are skipped during load."""
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_mapping": {
                "menu_toggle": {"type": "unknown_type", "foo": 1},
                "save_state": {"type": "button", "sdl_button": 3},
            }}},
        )
        # malformed entry is skipped
        assert "menu_toggle" not in config.hotkey_mapping
        assert config.hotkey_mapping["save_state"] == {"type": "button", "sdl_button": 3}


# ===========================================================================
# SettingsManager — getRetroarchHotkeyConfig
# ===========================================================================


class TestGetRetroarchHotkeyConfig:
    def test_returns_expected_keys(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        assert "modifier_evdev" in result
        assert "modifier_sdl_record" in result
        assert "modifier_label" in result
        assert "mapping" in result
        assert "hotkey_rows" in result
        assert "cfg_path" in result
        assert "rewind_enable" in result
        assert "rewind_buffer_size" in result
        assert "rewind_granularity" in result

    def test_modifier_evdev_none_when_not_configured(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        assert result["modifier_evdev"] is None
        assert result["modifier_sdl_record"] is None
        assert result["modifier_label"] == ""

    def test_modifier_sdl_record_used_for_label(self, tmp_path: Path) -> None:
        """When modifier_sdl is set, label comes from SDL record via resolver.button_label."""
        from unittest.mock import patch
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 316
        config._hotkey_modifier_sdl = {"type": "button", "sdl_button": 8}
        with patch("backend.sdl_resolver.resolver.button_label", return_value="Home"):
            result = manager.getRetroarchHotkeyConfig()
        assert result["modifier_evdev"] == 316
        assert result["modifier_sdl_record"] == {"type": "button", "sdl_button": 8}
        assert result["modifier_label"] == "Home"

    def test_modifier_evdev_fallback_label_when_no_sdl_record(self, tmp_path: Path) -> None:
        """When modifier_sdl is None but evdev is set, label falls back to evdev label."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 316  # BTN_MODE → "Home" in _EVDEV_LABELS
        config._hotkey_modifier_sdl = None
        result = manager.getRetroarchHotkeyConfig()
        assert result["modifier_label"] == "Home"

    def test_htpc_actions_ordered_correctly(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        hotkey_rows = result["hotkey_rows"]
        assert len(hotkey_rows) == 12
        assert hotkey_rows[0]["hotkey_action"] == "save_state"
        assert hotkey_rows[-1]["hotkey_action"] == "exit_emulator"

    def test_htpc_actions_have_required_keys(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        for row in result["hotkey_rows"]:
            assert "hotkey_action" in row
            assert "label" in row
            assert "sdl_record" in row
            assert "button_label" in row

    def test_first_run_all_rows_have_none_sdl_record(self, tmp_path: Path) -> None:
        """When hotkey_mapping is empty, hotkey_rows all have sdl_record == None."""
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}

        result = manager.getRetroarchHotkeyConfig()

        for row in result["hotkey_rows"]:
            assert row["sdl_record"] is None
            assert row["button_label"] == ""

    def test_stored_mapping_used_when_not_empty(self, tmp_path: Path) -> None:
        """When hotkey_mapping is set, it is used directly."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"menu_toggle": {"type": "button", "sdl_button": 7}}

        result = manager.getRetroarchHotkeyConfig()

        assert result["mapping"]["menu_toggle"] == {"type": "button", "sdl_button": 7}

    def test_button_label_from_sdl_record(self, tmp_path: Path) -> None:
        """button_label is derived from SDL record via resolver.button_label."""
        from unittest.mock import patch
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": {"type": "button", "sdl_button": 0}}

        with patch("backend.sdl_resolver.resolver.button_label", return_value="A"):
            result = manager.getRetroarchHotkeyConfig()

        save_state_row = next(r for r in result["hotkey_rows"] if r["hotkey_action"] == "save_state")
        assert save_state_row["button_label"] == "A"

    def test_axis_label_from_sdl_record(self, tmp_path: Path) -> None:
        """button_label for axis SDL record uses the label stored in the record."""
        manager, config = _make_manager(tmp_path)
        # label is stored in the record at capture time by resolver.resolve()
        config._hotkey_mapping = {"rewind": {"type": "axis", "sdl_axis": 2, "dir": 1, "label": "LT"}}

        result = manager.getRetroarchHotkeyConfig()

        rewind_row = next(r for r in result["hotkey_rows"] if r["hotkey_action"] == "rewind")
        assert rewind_row["button_label"] == "LT"

    def test_hat_label_from_sdl_record(self, tmp_path: Path) -> None:
        """button_label for hat SDL record shows D-pad direction label."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": {"type": "hat", "sdl_hat": 0, "dir": "up"}}

        result = manager.getRetroarchHotkeyConfig()

        save_state_row = next(r for r in result["hotkey_rows"] if r["hotkey_action"] == "save_state")
        assert save_state_row["button_label"] == "D-pad Up"

    def test_cfg_path_reflects_config(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config.retroarch_cfg_path = Path("/custom/retroarch.cfg")
        result = manager.getRetroarchHotkeyConfig()
        assert result["cfg_path"] == "/custom/retroarch.cfg"


# ===========================================================================
# SettingsManager — setHotkeyAction
# ===========================================================================


class TestSetHotkeyAction:
    def test_updates_single_action_in_mapping(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {
            "menu_toggle": {"type": "button", "sdl_button": 0},
            "exit_emulator": {"type": "button", "sdl_button": 1},
        }

        manager.setHotkeyAction("menu_toggle", 5)

        assert config.hotkey_mapping["menu_toggle"] == 5
        assert config.hotkey_mapping["exit_emulator"] == {"type": "button", "sdl_button": 1}

    def test_adds_new_action_to_empty_mapping(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}

        manager.setHotkeyAction("save_state", 3)

        assert config.hotkey_mapping["save_state"] == 3


# ===========================================================================
# SettingsManager — setHotkeyModifier / clearHotkeyModifier
# ===========================================================================


class TestSetHotkeyModifier:
    def test_set_modifier_updates_evdev_config(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        mock_sdl_record = {"type": "button", "sdl_button": 8}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_sdl_record):
            manager.setHotkeyModifier(316)
        assert config.hotkey_modifier_evdev == 316

    def test_set_modifier_stores_sdl_record(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        mock_sdl_record = {"type": "button", "sdl_button": 8}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_sdl_record):
            manager.setHotkeyModifier(316)
        assert config.hotkey_modifier_sdl == mock_sdl_record

    def test_set_modifier_stores_none_when_resolver_returns_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.setHotkeyModifier(316)
        assert config.hotkey_modifier_evdev == 316
        assert config.hotkey_modifier_sdl is None

    def test_clear_modifier_sets_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 316
        config._hotkey_modifier_sdl = {"type": "button", "sdl_button": 8}
        manager.clearHotkeyModifier()
        assert config.hotkey_modifier_evdev is None
        assert config.hotkey_modifier_sdl is None


# ===========================================================================
# SettingsManager — applyRetroarchHotkeys
# ===========================================================================


class TestApplyRetroarchHotkeys:
    def test_writes_button_cfg_keys_to_file(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys writes btn/axis/hat keys to retroarch.cfg."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_sdl = {"type": "button", "sdl_button": 8}
        config._hotkey_mapping = {
            "menu_toggle": {"type": "button", "sdl_button": 3},
            "load_state": {"type": "button", "sdl_button": 1},
        }

        manager.applyRetroarchHotkeys()

        assert cfg_path.exists()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_menu_toggle_btn"] == "3"
        assert result["input_menu_toggle_axis"] == "nul"
        assert result["input_menu_toggle_hat"] == "nul"
        assert result["input_load_state_btn"] == "1"
        assert result["input_enable_hotkey_btn"] == "8"
        assert result["input_enable_hotkey_axis"] == "nul"

    def test_writes_axis_cfg_key_to_file(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys writes axis key for axis SDL records."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_sdl = None
        config._hotkey_mapping = {
            "rewind": {"type": "axis", "sdl_axis": 2, "dir": 1},
        }

        manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_rewind_btn"] == "nul"
        assert result["input_rewind_axis"] == "+2"
        assert result["input_rewind_hat"] == "nul"

    def test_writes_hat_cfg_key_to_file(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys writes hat key for hat SDL records."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_sdl = None
        config._hotkey_mapping = {
            "save_state": {"type": "hat", "sdl_hat": 0, "dir": "up"},
        }

        manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_save_state_btn"] == "nul"
        assert result["input_save_state_axis"] == "nul"
        assert result["input_save_state_hat"] == "0up"

    def test_none_modifier_writes_nul_for_enable_hotkey(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_sdl = None
        config._hotkey_mapping = {"menu_toggle": {"type": "button", "sdl_button": 3}}

        manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_enable_hotkey_btn"] == "nul"

    def test_does_not_raise_on_write_error(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys logs error but does not raise on write failure."""
        manager, config = _make_manager(tmp_path)
        config.retroarch_cfg_path = Path("/nonexistent/readonly/retroarch.cfg")
        config._hotkey_mapping = {"menu_toggle": {"type": "button", "sdl_button": 3}}

        # Should not raise
        manager.applyRetroarchHotkeys()

    def test_empty_mapping_writes_nul_for_all_hotkey_keys(self, tmp_path: Path) -> None:
        """When hotkey_mapping is empty, applyRetroarchHotkeys writes nul for all hotkey keys."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_sdl = None
        config._hotkey_mapping = {}

        manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        # All btn/axis/hat keys should be nul when mapping is empty
        for action, cfg_keys in ra_cfg.HOTKEY_CFG_KEYS.items():
            for key_type in ("btn", "axis", "hat"):
                key = cfg_keys[key_type]
                assert result[key] == "nul", f"Expected nul for {key}, got {result.get(key)}"


# ===========================================================================
# SettingsManager — getRetroarchCfgPath / setRetroarchCfgPath
# ===========================================================================


class TestRetroarchCfgPathSlots:
    def test_get_retroarch_cfg_path_returns_string(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        result = manager.getRetroarchCfgPath()
        assert isinstance(result, str)
        assert "retroarch.cfg" in result

    def test_set_retroarch_cfg_path_updates_config(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        manager.setRetroarchCfgPath("/custom/retroarch.cfg")
        assert str(config.retroarch_cfg_path) == "/custom/retroarch.cfg"


# ===========================================================================
# retroarch_config — new HOTKEY_CFG_KEYS structure
# ===========================================================================


class TestNewHotkeyKeys:
    """Verify the new triple-key structure in HOTKEY_CFG_KEYS."""

    def test_fast_forward_toggle_key_present(self) -> None:
        assert "fast_forward_toggle" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_toggle"]["btn"] == "input_toggle_fast_forward_btn"
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_toggle"]["axis"] == "input_toggle_fast_forward_axis"
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_toggle"]["hat"] == "input_toggle_fast_forward_hat"

    def test_fast_forward_hold_key_present(self) -> None:
        assert "fast_forward_hold" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["fast_forward_hold"]["btn"] == "input_hold_fast_forward_btn"

    def test_show_fps_key_present(self) -> None:
        assert "show_fps" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["show_fps"]["btn"] == "input_toggle_statistics_btn"

    def test_old_fast_forward_key_removed(self) -> None:
        # The old "fast_forward" key (input_fast_forward_btn) is gone
        assert "fast_forward" not in ra_cfg.HOTKEY_CFG_KEYS

    def test_htpc_to_hotkey_removed(self) -> None:
        assert not hasattr(ra_cfg, "HTPC_TO_HOTKEY")

    def test_pause_toggle_key_present(self) -> None:
        assert "pause_toggle" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["pause_toggle"]["btn"] == "input_pause_toggle_btn"

    def test_exit_emulator_key_present(self) -> None:
        assert "exit_emulator" in ra_cfg.HOTKEY_CFG_KEYS
        assert ra_cfg.HOTKEY_CFG_KEYS["exit_emulator"]["btn"] == "input_exit_emulator_btn"

    def test_each_action_has_btn_axis_hat_keys(self) -> None:
        """Every action in HOTKEY_CFG_KEYS has btn, axis, and hat sub-keys."""
        for action, cfg_keys in ra_cfg.HOTKEY_CFG_KEYS.items():
            assert "btn" in cfg_keys, f"Missing 'btn' for {action}"
            assert "axis" in cfg_keys, f"Missing 'axis' for {action}"
            assert "hat" in cfg_keys, f"Missing 'hat' for {action}"

    def test_evdev_to_sdl_removed(self) -> None:
        """EVDEV_TO_SDL table has been removed."""
        assert not hasattr(ra_cfg, "EVDEV_TO_SDL")

    def test_evdev_code_to_sdl_index_removed(self) -> None:
        """evdev_code_to_sdl_index function has been removed."""
        assert not hasattr(ra_cfg, "evdev_code_to_sdl_index")


# ===========================================================================
# SettingsManager — setHotkeyActionByEvdev
# ===========================================================================


class TestSetHotkeyActionByEvdev:
    def test_stores_sdl_record_from_resolver(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByEvdev("save_state", 305)
        assert config.hotkey_mapping["save_state"] == mock_record

    def test_stores_none_when_resolver_returns_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.setHotkeyActionByEvdev("save_state", 9999)
        assert config.hotkey_mapping["save_state"] is None

    def test_overwrites_existing_mapping(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": {"type": "button", "sdl_button": 5}}
        new_record = {"type": "button", "sdl_button": 8}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=new_record):
            manager.setHotkeyActionByEvdev("save_state", 316)
        assert config.hotkey_mapping["save_state"] == new_record


# ===========================================================================
# SettingsManager — setHotkeyActionByAxis
# ===========================================================================


class TestSetHotkeyActionByAxis:
    def test_stores_axis_sdl_record(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "axis", "sdl_axis": 2, "dir": 1}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByAxis("rewind", 2, 1)
        assert config.hotkey_mapping["rewind"] == mock_record

    def test_stores_hat_sdl_record(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "hat", "sdl_hat": 0, "dir": "up"}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByAxis("save_state", 17, -1)
        assert config.hotkey_mapping["save_state"] == mock_record

    def test_stores_none_when_resolver_returns_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.setHotkeyActionByAxis("rewind", 99, 1)
        assert config.hotkey_mapping["rewind"] is None

    def test_evicts_conflicting_action(self, tmp_path: Path) -> None:
        """setHotkeyActionByAxis evicts another action using the same SDL record."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "axis", "sdl_axis": 2, "dir": 1}
        config._hotkey_mapping = {"save_state": mock_record}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByAxis("rewind", 2, 1)
        assert config.hotkey_mapping["save_state"] is None
        assert config.hotkey_mapping["rewind"] == mock_record


# ===========================================================================
# SettingsManager — clearHotkeyAction
# ===========================================================================


class TestClearHotkeyAction:
    def test_sets_action_to_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"save_state": {"type": "button", "sdl_button": 3}}
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["save_state"] is None

    def test_adds_none_entry_for_unset_action(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["save_state"] is None

    def test_does_not_affect_other_actions(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {
            "save_state": {"type": "button", "sdl_button": 3},
            "load_state": {"type": "button", "sdl_button": 1},
        }
        manager.clearHotkeyAction("save_state")
        assert config.hotkey_mapping["load_state"] == {"type": "button", "sdl_button": 1}


# ===========================================================================
# Config — rewind properties
# ===========================================================================


class TestConfigRewindProperties:
    def test_rewind_enable_default_false(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.rewind_enable is False

    def test_rewind_buffer_size_default_20(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.rewind_buffer_size == 20

    def test_rewind_granularity_default_1(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.rewind_granularity == 1

    def test_set_rewind_enable_persists(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_enable(True)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_enable"] is True

    def test_set_rewind_buffer_size_persists(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_buffer_size(100)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_buffer_size"] == 100

    def test_set_rewind_granularity_persists(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_rewind_granularity(8)
        saved = json.loads(config_file.read_text())
        assert saved["retroarch"]["rewind_granularity"] == 8

    def test_load_rewind_fields_from_json(self, tmp_path: Path) -> None:
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

    def test_malformed_rewind_fields_use_defaults(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, {
            "retroarch": {
                "rewind_enable": "not_a_bool",
                "rewind_buffer_size": "not_an_int",
                "rewind_granularity": None,
            }
        })
        # Malformed values fall back to defaults (config.py uses isinstance guards)
        assert config.rewind_buffer_size == 20
        assert config.rewind_granularity == 1


# ===========================================================================
# SettingsManager — rewind slots
# ===========================================================================


class TestRewindSlots:
    def test_set_rewind_enable(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        manager.setRewindEnable(True)
        assert config.rewind_enable is True

    def test_set_rewind_buffer_size(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        manager.setRewindBufferSize(150)
        assert config.rewind_buffer_size == 150

    def test_set_rewind_granularity(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        manager.setRewindGranularity(16)
        assert config.rewind_granularity == 16


# ===========================================================================
# SettingsManager — applyRetroarchHotkeys writes rewind settings
# ===========================================================================


class TestApplyRetroarchHotkeysWritesRewind:
    def test_apply_writes_rewind_enable_true(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_enable = True
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_enable"] == "true"

    def test_apply_writes_rewind_enable_false(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_enable = False
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_enable"] == "false"

    def test_apply_writes_rewind_buffer_size(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_buffer_size = 200
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_buffer_size"] == "200"

    def test_apply_writes_rewind_granularity(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._rewind_granularity = 8
        manager.applyRetroarchHotkeys()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["rewind_granularity"] == "8"


# ===========================================================================
# SettingsManager — duplicate button prevention
# ===========================================================================


class TestDuplicatePrevention:
    def test_set_modifier_evicts_conflicting_hotkey(self, tmp_path):
        """Assigning a button as modifier clears any hotkey using the same SDL record."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        config._hotkey_mapping = {"save_state": mock_record}
        # Now assign same SDL record as modifier → should clear save_state
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyModifier(305)
        assert config.hotkey_mapping["save_state"] is None
        assert config.hotkey_modifier_evdev == 305

    def test_set_hotkey_evicts_conflicting_hotkey(self, tmp_path):
        """Assigning a button to a hotkey clears any other hotkey using the same SDL record."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        config._hotkey_mapping = {
            "save_state": mock_record,
            "load_state": {"type": "button", "sdl_button": 3},
        }
        # Assign load_state to same SDL record as save_state → save_state should be cleared
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByEvdev("load_state", 305)
        assert config.hotkey_mapping["save_state"] is None
        assert config.hotkey_mapping["load_state"] == mock_record

    def test_set_hotkey_evicts_conflicting_modifier(self, tmp_path):
        """Assigning a button to a hotkey clears the modifier if it uses the same SDL record."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        config._hotkey_modifier_sdl = mock_record
        config._hotkey_modifier_evdev = 305
        config._hotkey_mapping = {}
        # Assign save_state to same SDL record → modifier should be cleared
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByEvdev("save_state", 305)
        assert config.hotkey_modifier_evdev is None
        assert config.hotkey_modifier_sdl is None
        assert config.hotkey_mapping["save_state"] == mock_record

    def test_set_hotkey_does_not_evict_self(self, tmp_path):
        """Re-assigning the same button to the same hotkey does not clear it."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        config._hotkey_mapping = {"save_state": mock_record}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=mock_record):
            manager.setHotkeyActionByEvdev("save_state", 305)
        assert config.hotkey_mapping["save_state"] == mock_record

    def test_set_modifier_unknown_evdev_no_eviction(self, tmp_path):
        """Unknown evdev code (SDL=None) does not evict anything."""
        manager, config = _make_manager(tmp_path)
        mock_record = {"type": "button", "sdl_button": 0}
        config._hotkey_mapping = {"save_state": mock_record}
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.setHotkeyModifier(9999)
        assert config.hotkey_mapping["save_state"] == mock_record
