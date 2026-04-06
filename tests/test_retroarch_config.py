"""Tests for M6 Task 003 — retroarch_config module (updated for 008-C).

Covers:
  - read_cfg: missing file, key-value parsing, comment skipping, whitespace stripping
  - write_cfg: creates file, updates existing key, adds new key, creates parent dirs
  - build_hotkey_cfg: SDL record mapping, None → "nul", enable_hotkey, None modifier
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.retroarch_config as ra_cfg


# ===========================================================================
# TestReadCfg
# ===========================================================================


class TestReadCfg:
    def test_returns_empty_dict_for_missing_file(self, tmp_path: Path) -> None:
        result = ra_cfg.read_cfg(tmp_path / "nonexistent.cfg")
        assert result == {}

    def test_parses_key_value_pairs(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("input_menu_toggle_btn = 3\n", encoding="utf-8")
        result = ra_cfg.read_cfg(cfg)
        assert result == {"input_menu_toggle_btn": "3"}

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("# this is a comment\ninput_menu_toggle_btn = 5\n", encoding="utf-8")
        result = ra_cfg.read_cfg(cfg)
        assert "# this is a comment" not in result
        assert result["input_menu_toggle_btn"] == "5"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("  input_menu_toggle_btn  =  7  \n", encoding="utf-8")
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "7"


# ===========================================================================
# TestWriteCfg
# ===========================================================================


class TestWriteCfg:
    def test_creates_file_if_missing(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "3"})
        assert cfg.exists()
        assert "input_menu_toggle_btn = 3" in cfg.read_text(encoding="utf-8")

    def test_updates_existing_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("input_menu_toggle_btn = 0\nvideo_driver = gl\n", encoding="utf-8")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "5"})
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "5"
        assert result["video_driver"] == "gl"

    def test_adds_new_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("video_driver = gl\n", encoding="utf-8")
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "7"})
        result = ra_cfg.read_cfg(cfg)
        assert result["input_menu_toggle_btn"] == "7"
        assert result["video_driver"] == "gl"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        cfg = tmp_path / "deep" / "nested" / "retroarch.cfg"
        ra_cfg.write_cfg(cfg, {"input_menu_toggle_btn": "3"})
        assert cfg.exists()


# ===========================================================================
# TestBuildHotkeyCfg
# ===========================================================================


class TestBuildHotkeyCfg:
    def test_maps_button_sdl_record_to_btn_key(self) -> None:
        """{'menu_toggle': {'type': 'button', 'sdl_button': 3}} → btn='3', axis='nul', hat='nul'."""
        result = ra_cfg.build_hotkey_cfg(
            {"menu_toggle": {"type": "button", "sdl_button": 3}},
            modifier_sdl_record=None,
        )
        assert result["input_menu_toggle_btn"] == "3"
        assert result["input_menu_toggle_axis"] == "nul"
        assert result["input_menu_toggle_hat"] == "nul"

    def test_none_value_writes_nul_for_all_three(self) -> None:
        """{'menu_toggle': None} → btn='nul', axis='nul', hat='nul'."""
        result = ra_cfg.build_hotkey_cfg({"menu_toggle": None}, modifier_sdl_record=None)
        assert result["input_menu_toggle_btn"] == "nul"
        assert result["input_menu_toggle_axis"] == "nul"
        assert result["input_menu_toggle_hat"] == "nul"

    def test_includes_enable_hotkey_btn(self) -> None:
        """modifier_sdl_record button → input_enable_hotkey_btn='8'."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record={"type": "button", "sdl_button": 8})
        assert result["input_enable_hotkey_btn"] == "8"

    def test_none_modifier_writes_nul(self) -> None:
        """modifier_sdl_record=None → input_enable_hotkey_btn='nul'."""
        result = ra_cfg.build_hotkey_cfg({}, modifier_sdl_record=None)
        assert result["input_enable_hotkey_btn"] == "nul"

    def test_evdev_to_sdl_not_present(self) -> None:
        """EVDEV_TO_SDL has been removed from retroarch_config."""
        assert not hasattr(ra_cfg, "EVDEV_TO_SDL")

    def test_evdev_code_to_sdl_index_not_present(self) -> None:
        """evdev_code_to_sdl_index has been removed from retroarch_config."""
        assert not hasattr(ra_cfg, "evdev_code_to_sdl_index")
