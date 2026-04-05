"""Tests for M6 Task 001 — RetroArch hotkey backend.

Covers:
  - retroarch_config: read_cfg / write_cfg / build_hotkey_cfg / evdev_code_to_sdl_index
  - config.py: hotkey_modifier_evdev, hotkey_mapping, retroarch_cfg_path properties
  - config.py: save/load round-trip for retroarch hotkey section
  - settings_manager: getRetroarchHotkeyConfig (first-run derivation and stored mapping)
  - settings_manager: setHotkeyAction, setHotkeyModifier, clearHotkeyModifier
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
# retroarch_config — evdev_code_to_sdl_index
# ===========================================================================


class TestEvdevCodeToSdlIndex:
    def test_known_code_returns_sdl_index(self) -> None:
        """BTN_EAST (305) maps to SDL 0."""
        assert ra_cfg.evdev_code_to_sdl_index(305) == 0

    def test_home_button_maps_to_sdl_8(self) -> None:
        """BTN_MODE (316) maps to SDL 8."""
        assert ra_cfg.evdev_code_to_sdl_index(316) == 8

    def test_unknown_code_returns_none(self) -> None:
        """An evdev code not in the table returns None."""
        assert ra_cfg.evdev_code_to_sdl_index(9999) is None

    def test_all_table_entries_are_unique_sdl_indices(self) -> None:
        """Each evdev code maps to a distinct SDL index."""
        sdl_indices = list(ra_cfg.EVDEV_TO_SDL.values())
        assert len(sdl_indices) == len(set(sdl_indices))


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
# retroarch_config — build_hotkey_cfg
# ===========================================================================


class TestBuildHotkeyCfg:
    def test_none_values_write_nul(self) -> None:
        mapping = {action: None for action in ra_cfg.HOTKEY_CFG_KEYS if action != "enable_hotkey"}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl=None)
        assert result["input_enable_hotkey_btn"] == "nul"
        assert result["input_menu_toggle_btn"] == "nul"

    def test_integer_values_written_as_strings(self) -> None:
        mapping = {"menu_toggle": 3, "exit_emulator": 1}
        result = ra_cfg.build_hotkey_cfg(mapping, modifier_sdl=8)
        assert result["input_menu_toggle_btn"] == "3"
        assert result["input_exit_emulator_btn"] == "1"
        assert result["input_enable_hotkey_btn"] == "8"

    def test_modifier_sdl_written_to_enable_hotkey_btn(self) -> None:
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl=8)
        assert result["input_enable_hotkey_btn"] == "8"

    def test_all_hotkey_cfg_keys_present_in_output(self) -> None:
        """build_hotkey_cfg always outputs all HOTKEY_CFG_KEYS."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl=None)
        for cfg_key in ra_cfg.HOTKEY_CFG_KEYS.values():
            assert cfg_key in result, f"Missing key: {cfg_key}"

    def test_missing_hotkey_action_writes_nul(self) -> None:
        """Actions not in the mapping dict are written as nul."""
        result = ra_cfg.build_hotkey_cfg({"menu_toggle": 3}, modifier_sdl=None)
        assert result["input_exit_emulator_btn"] == "nul"


# ===========================================================================
# Config — hotkey properties
# ===========================================================================


class TestConfigHotkeyProperties:
    def test_hotkey_modifier_evdev_default_is_none(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.hotkey_modifier_evdev is None

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
            config.set_hotkey_mapping({"menu_toggle": 3, "exit_emulator": 1})

        assert config.hotkey_mapping == {"menu_toggle": 3, "exit_emulator": 1}
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["retroarch"]["hotkey_mapping"]["menu_toggle"] == 3

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

    def test_load_reads_hotkey_mapping(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            {"retroarch": {"hotkey_mapping": {"menu_toggle": 3, "exit_emulator": 1}}},
        )
        assert config.hotkey_mapping == {"menu_toggle": 3, "exit_emulator": 1}

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
        assert "hotkey_mapping" in retroarch
        assert "retroarch_cfg_path" in retroarch


# ===========================================================================
# SettingsManager — getRetroarchHotkeyConfig
# ===========================================================================


class TestGetRetroarchHotkeyConfig:
    def test_returns_expected_keys(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        assert "modifier_evdev" in result
        assert "modifier_sdl" in result
        assert "modifier_label" in result
        assert "mapping" in result
        assert "htpc_actions" in result
        assert "cfg_path" in result

    def test_modifier_evdev_none_when_not_configured(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        assert result["modifier_evdev"] is None
        assert result["modifier_sdl"] is None
        assert result["modifier_label"] == ""

    def test_modifier_evdev_set_returns_sdl_and_label(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 316  # BTN_MODE → SDL 8
        result = manager.getRetroarchHotkeyConfig()
        assert result["modifier_evdev"] == 316
        assert result["modifier_sdl"] == 8
        assert result["modifier_label"] == "Home"

    def test_htpc_actions_ordered_correctly(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        htpc_actions = result["htpc_actions"]
        expected_order = [
            "accept", "cancel", "context1", "context2",
            "left_shoulder", "right_shoulder",
            "start", "select",
            "left_trigger", "right_trigger",
        ]
        actual_order = [row["htpc_action"] for row in htpc_actions]
        assert actual_order == expected_order

    def test_htpc_actions_have_required_keys(self, tmp_path: Path) -> None:
        manager, _ = _make_manager(tmp_path)
        result = manager.getRetroarchHotkeyConfig()
        for row in result["htpc_actions"]:
            assert "htpc_action" in row
            assert "hotkey_action" in row
            assert "label" in row
            assert "sdl_index" in row

    def test_first_run_derives_mapping_from_controller(self, tmp_path: Path) -> None:
        """When hotkey_mapping is empty, SDL indices are derived from controller mapping."""
        manager, config = _make_manager(tmp_path)
        # Ensure mapping is empty (first run)
        assert config.hotkey_mapping == {}

        # Patch load_mapping to return a known mapping
        fake_mapping = {
            "accept": {"type": "button", "code": 305, "value": 1},  # BTN_EAST → SDL 0
        }
        with patch("backend.settings_manager.load_mapping", return_value=fake_mapping):
            result = manager.getRetroarchHotkeyConfig()

        # accept → menu_toggle → BTN_EAST (305) → SDL 0
        mapping = result["mapping"]
        assert mapping.get("menu_toggle") == 0

    def test_stored_mapping_used_when_not_empty(self, tmp_path: Path) -> None:
        """When hotkey_mapping is set, it is used directly without deriving from controller."""
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"menu_toggle": 7}

        with patch("backend.settings_manager.load_mapping") as mock_load:
            result = manager.getRetroarchHotkeyConfig()

        mock_load.assert_not_called()
        assert result["mapping"]["menu_toggle"] == 7

    def test_cfg_path_reflects_config(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config.retroarch_cfg_path = Path("/custom/retroarch.cfg")
        result = manager.getRetroarchHotkeyConfig()
        assert result["cfg_path"] == "/custom/retroarch.cfg"

    def test_axis_actions_map_to_none_on_first_run(self, tmp_path: Path) -> None:
        """Axis-based actions (triggers) cannot be translated to SDL button index → None."""
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}

        # left_trigger is an axis in DEFAULT_MAPPING — should map to None
        fake_mapping = {
            "left_trigger": {"type": "axis", "code": 2, "value": 1},
        }
        with patch("backend.settings_manager.load_mapping", return_value=fake_mapping):
            result = manager.getRetroarchHotkeyConfig()

        # left_trigger → rewind; axis entries cannot be SDL button indices
        assert result["mapping"].get("rewind") is None


# ===========================================================================
# SettingsManager — setHotkeyAction
# ===========================================================================


class TestSetHotkeyAction:
    def test_updates_single_action_in_mapping(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_mapping = {"menu_toggle": 0, "exit_emulator": 1}

        manager.setHotkeyAction("menu_toggle", 5)

        assert config.hotkey_mapping["menu_toggle"] == 5
        assert config.hotkey_mapping["exit_emulator"] == 1

    def test_adds_new_action_to_empty_mapping(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        assert config.hotkey_mapping == {}

        manager.setHotkeyAction("save_state", 3)

        assert config.hotkey_mapping["save_state"] == 3


# ===========================================================================
# SettingsManager — setHotkeyModifier / clearHotkeyModifier
# ===========================================================================


class TestSetHotkeyModifier:
    def test_set_modifier_updates_config(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        manager.setHotkeyModifier(316)
        assert config.hotkey_modifier_evdev == 316

    def test_clear_modifier_sets_none(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        config._hotkey_modifier_evdev = 316
        manager.clearHotkeyModifier()
        assert config.hotkey_modifier_evdev is None


# ===========================================================================
# SettingsManager — applyRetroarchHotkeys
# ===========================================================================


class TestApplyRetroarchHotkeys:
    def test_writes_cfg_keys_to_file(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys writes all HOTKEY_CFG_KEYS to retroarch.cfg."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_evdev = 316  # BTN_MODE → SDL 8
        config._hotkey_mapping = {"menu_toggle": 3, "exit_emulator": 1}

        manager.applyRetroarchHotkeys()

        assert cfg_path.exists()
        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_menu_toggle_btn"] == "3"
        assert result["input_exit_emulator_btn"] == "1"
        assert result["input_enable_hotkey_btn"] == "8"

    def test_none_modifier_writes_nul_for_enable_hotkey(self, tmp_path: Path) -> None:
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_modifier_evdev = None
        config._hotkey_mapping = {"menu_toggle": 3}

        manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        assert result["input_enable_hotkey_btn"] == "nul"

    def test_does_not_raise_on_write_error(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys logs error but does not raise on write failure."""
        manager, config = _make_manager(tmp_path)
        config.retroarch_cfg_path = Path("/nonexistent/readonly/retroarch.cfg")
        config._hotkey_mapping = {"menu_toggle": 3}

        # Should not raise
        manager.applyRetroarchHotkeys()

    def test_derives_mapping_from_controller_when_empty(self, tmp_path: Path) -> None:
        """applyRetroarchHotkeys derives mapping from controller when hotkey_mapping is empty."""
        manager, config = _make_manager(tmp_path)
        cfg_path = tmp_path / "retroarch.cfg"
        config.retroarch_cfg_path = cfg_path
        config._hotkey_mapping = {}

        fake_mapping = {
            "accept": {"type": "button", "code": 305, "value": 1},  # BTN_EAST → SDL 0
        }
        with patch("backend.settings_manager.load_mapping", return_value=fake_mapping):
            manager.applyRetroarchHotkeys()

        result = ra_cfg.read_cfg(cfg_path)
        # accept → menu_toggle → BTN_EAST (305) → SDL 0
        assert result["input_menu_toggle_btn"] == "0"


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
