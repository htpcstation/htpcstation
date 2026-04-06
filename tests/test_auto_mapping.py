"""Tests for Task 003 — Browser Extension Auto-Generated Mapping.

Covers:
  - build_web_gamepad_mapping: returns None when no SDL halves present
  - build_web_gamepad_mapping: maps SDL button entries to correct Web API indices
  - build_web_gamepad_mapping: maps SDL hat entries to synthetic button indices
  - build_web_gamepad_mapping: maps SDL axis entries to Web API axis indices
  - build_web_gamepad_mapping: dpadButtons contains hat-derived button indices
  - generate_mapping_js: returns comment stub when no SDL data
  - generate_mapping_js: produces valid JS assignment with correct structure
  - GamepadManager.getDeviceCapabilities: returns empty dict when no device
  - GamepadManager.getDeviceCapabilities: returns sorted buttons and axes
  - _deploy_extension: writes generated_mapping.js to deployed dir
  - _deploy_extension: generated_mapping.js contains JS assignment when mapping has SDL data
  - _deploy_extension: generated_mapping.js contains stub when no SDL data
  - saveControllerMapping: stores dual-record format (no _device key)
  - saveControllerMapping: skips _device when gamepad_manager is None
  - content.js: fallback to defaults when __htpcGeneratedMapping is absent
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.controller_mapping import (
    build_web_gamepad_mapping,
    generate_mapping_js,
    get_default_mapping,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    from evdev import ecodes
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False


def _make_device_caps(
    buttons: list[int] | None = None,
    axes: list[int] | None = None,
    name: str = "Test Gamepad",
) -> dict:
    """Build a device capabilities dict (for getDeviceCapabilities tests)."""
    return {
        "buttons": buttons if buttons is not None else [304, 305, 307, 308, 310, 311, 314, 315],
        "axes": axes if axes is not None else [0, 1, 3, 4, 16, 17],
        "name": name,
    }


def _make_mapping_with_sdl(
    buttons: dict[str, int] | None = None,
    hats: dict[str, tuple[int, str]] | None = None,
    axes: dict[str, tuple[int, int]] | None = None,
) -> dict:
    """Return a mapping with SDL halves populated.

    buttons: {action_name: sdl_button_index}
    hats: {action_name: (sdl_hat_index, direction)}
    axes: {action_name: (sdl_axis_index, direction)}
    """
    m = get_default_mapping()
    if buttons:
        for action, sdl_btn in buttons.items():
            if action in m:
                m[action]["sdl"] = {"type": "button", "sdl_button": sdl_btn}
    if hats:
        for action, (hat_idx, direction) in hats.items():
            if action in m:
                m[action]["sdl"] = {"type": "hat", "sdl_hat": hat_idx, "dir": direction}
    if axes:
        for action, (axis_idx, direction) in axes.items():
            if action in m:
                m[action]["sdl"] = {"type": "axis", "sdl_axis": axis_idx, "dir": direction}
    return m


# ---------------------------------------------------------------------------
# build_web_gamepad_mapping
# ---------------------------------------------------------------------------


class TestBuildWebGamepadMapping:
    def test_returns_none_when_no_sdl_data(self) -> None:
        """Returns None when no entry has a non-null SDL half."""
        mapping = get_default_mapping()
        assert build_web_gamepad_mapping(mapping) is None

    def test_returns_none_when_all_sdl_halves_null(self) -> None:
        """Returns None when all SDL halves are explicitly null."""
        mapping = get_default_mapping()
        # All DEFAULT_MAPPING entries have sdl=None
        assert all(entry.get("sdl") is None for entry in mapping.values())
        assert build_web_gamepad_mapping(mapping) is None

    def test_button_type_maps_to_sdl_button_index(self) -> None:
        """SDL button entries map to the sdl_button index in the web mapping."""
        mapping = _make_mapping_with_sdl(
            buttons={"accept": 1, "cancel": 0, "left_shoulder": 4, "right_shoulder": 5,
                     "select": 6, "start": 7},
        )
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        buttons = result["buttons"]
        assert buttons[0] == "cancel"
        assert buttons[1] == "accept"
        assert buttons[4] == "leftBumper"
        assert buttons[5] == "rightBumper"
        assert buttons[6] == "select"
        assert buttons[7] == "start"

    def test_hat_entries_map_to_synthetic_indices(self) -> None:
        """SDL hat entries map to synthetic high button indices (1000+)."""
        mapping = _make_mapping_with_sdl(
            hats={
                "dpad_up": (0, "up"),
                "dpad_down": (0, "down"),
                "dpad_left": (0, "left"),
                "dpad_right": (0, "right"),
            },
        )
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        buttons = result["buttons"]
        assert buttons[1000] == "up"
        assert buttons[1001] == "down"
        assert buttons[1002] == "left"
        assert buttons[1003] == "right"

    def test_dpad_buttons_contains_hat_derived_indices(self) -> None:
        """dpadButtons dict contains all hat-derived button indices."""
        mapping = _make_mapping_with_sdl(
            hats={
                "dpad_up": (0, "up"),
                "dpad_down": (0, "down"),
                "dpad_left": (0, "left"),
                "dpad_right": (0, "right"),
            },
        )
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        dpad = result["dpadButtons"]
        assert dpad.get(1000) is True   # up
        assert dpad.get(1001) is True   # down
        assert dpad.get(1002) is True   # left
        assert dpad.get(1003) is True   # right

    def test_trigger_axes_map_to_sdl_axis_indices(self) -> None:
        """SDL axis entries map to the sdl_axis index in the web mapping."""
        mapping = _make_mapping_with_sdl(
            axes={"left_trigger": (2, 1), "right_trigger": (5, 1)},
        )
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        axes = result["axes"]
        assert 2 in axes
        assert axes[2][1] == "leftTrigger"
        assert 5 in axes
        assert axes[5][1] == "rightTrigger"

    def test_result_has_required_keys(self) -> None:
        """Result dict always has buttons, axes, and dpadButtons keys."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1})
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        assert "buttons" in result
        assert "axes" in result
        assert "dpadButtons" in result

    def test_entries_with_null_sdl_are_skipped(self) -> None:
        """Entries with sdl=None are silently skipped."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1})
        # cancel has sdl=None (not set in _make_mapping_with_sdl)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # cancel should not appear in buttons (its sdl is None)
        assert "cancel" not in result["buttons"].values()

    def test_metadata_keys_are_skipped(self) -> None:
        """Keys starting with _ are not treated as actions."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1})
        mapping["_device"] = {"buttons": [304, 305], "axes": [0, 1]}
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # _device should not appear as an action in the output
        assert "_device" not in result["buttons"].values()

    def test_hat_axes_not_in_sdl_data_are_skipped(self) -> None:
        """D-pad actions without SDL hat data are skipped."""
        # Only set SDL data for buttons, not for dpad (which uses hats)
        mapping = _make_mapping_with_sdl(buttons={"accept": 1, "cancel": 0})
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # D-pad actions should not appear in buttons (no SDL hat data)
        assert "up" not in result["buttons"].values()
        assert "down" not in result["buttons"].values()
        assert "left" not in result["buttons"].values()
        assert "right" not in result["buttons"].values()

    def test_buttons_sdl_index_determines_position(self) -> None:
        """SDL button index directly determines the web gamepad button position."""
        mapping = _make_mapping_with_sdl(
            buttons={"cancel": 0, "accept": 1},
        )
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        assert result["buttons"][0] == "cancel"
        assert result["buttons"][1] == "accept"


# ---------------------------------------------------------------------------
# generate_mapping_js
# ---------------------------------------------------------------------------


class TestGenerateMappingJs:
    def test_returns_comment_stub_when_no_sdl_data(self) -> None:
        """Returns a comment-only stub when no SDL halves are present."""
        mapping = get_default_mapping()
        js = generate_mapping_js(mapping)

        assert "window.__htpcGeneratedMapping" not in js
        assert js.startswith("//")

    def test_produces_js_assignment(self) -> None:
        """Produces a window.__htpcGeneratedMapping = {...}; assignment."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1, "cancel": 0})
        js = generate_mapping_js(mapping)

        assert js.startswith("window.__htpcGeneratedMapping = ")
        assert js.rstrip().endswith(";")

    def test_js_contains_valid_json_payload(self) -> None:
        """The JS assignment contains a valid JSON object."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1, "cancel": 0})
        js = generate_mapping_js(mapping)

        # Extract the JSON part between the first = and the trailing ;
        prefix = "window.__htpcGeneratedMapping = "
        assert js.startswith(prefix)
        json_part = js[len(prefix):].rstrip().rstrip(";")
        parsed = json.loads(json_part)

        assert isinstance(parsed, dict)
        assert "buttons" in parsed
        assert "axes" in parsed
        assert "dpadButtons" in parsed

    def test_js_buttons_keys_are_strings(self) -> None:
        """JSON object keys are always strings (JS object keys)."""
        mapping = _make_mapping_with_sdl(buttons={"accept": 1, "cancel": 0})
        js = generate_mapping_js(mapping)

        prefix = "window.__htpcGeneratedMapping = "
        json_part = js[len(prefix):].rstrip().rstrip(";")
        parsed = json.loads(json_part)

        # JSON keys are always strings
        for key in parsed["buttons"]:
            assert isinstance(key, str)


# ---------------------------------------------------------------------------
# GamepadManager.getDeviceCapabilities
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestGetDeviceCapabilities:
    def _make_manager_with_mock_device(self, buttons: list, abs_caps: list):
        """Create a GamepadManager with a mock device handler."""
        from backend.gamepad import GamepadManager, _DeviceHandler
        from backend.controller_mapping import build_evdev_lookup

        manager = GamepadManager()

        # Build mock device capabilities
        mock_caps = {
            ecodes.EV_KEY: buttons,
            ecodes.EV_ABS: abs_caps,
        }
        mock_device = MagicMock()
        mock_device.path = "/dev/input/event0"
        mock_device.name = "Mock Gamepad"
        mock_device.fd = 99
        mock_device.capabilities.return_value = mock_caps

        lookup = build_evdev_lookup(get_default_mapping())
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(mock_device, manager, lookup)
        manager._handlers[mock_device.path] = handler

        return manager

    def test_returns_empty_dict_when_no_handlers(self) -> None:
        """Returns {} when no devices are connected."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        assert manager._handlers == {}
        result = manager.getDeviceCapabilities()
        assert result == {}

    def test_returns_sorted_buttons(self) -> None:
        """Returns sorted list of EV_KEY button codes."""
        buttons = [315, 314, 311, 310, 308, 307, 305, 304]  # unsorted
        abs_caps = [
            (ecodes.ABS_X, MagicMock(min=-32768, max=32767)),
            (ecodes.ABS_HAT0X, MagicMock(min=-1, max=1)),
        ]
        manager = self._make_manager_with_mock_device(buttons, abs_caps)
        result = manager.getDeviceCapabilities()

        assert result["buttons"] == sorted(buttons)

    def test_returns_sorted_axes(self) -> None:
        """Returns sorted list of EV_ABS axis codes."""
        abs_caps = [
            (ecodes.ABS_HAT0Y, MagicMock(min=-1, max=1)),
            (ecodes.ABS_X, MagicMock(min=-32768, max=32767)),
            (ecodes.ABS_HAT0X, MagicMock(min=-1, max=1)),
        ]
        manager = self._make_manager_with_mock_device([304], abs_caps)
        result = manager.getDeviceCapabilities()

        expected_axes = sorted([ecodes.ABS_HAT0Y, ecodes.ABS_X, ecodes.ABS_HAT0X])
        assert result["axes"] == expected_axes

    def test_returns_device_name(self) -> None:
        """Returns the device name string."""
        manager = self._make_manager_with_mock_device([304], [])
        result = manager.getDeviceCapabilities()

        assert result["name"] == "Mock Gamepad"

    def test_returns_empty_dict_on_capabilities_exception(self) -> None:
        """Returns {} when device.capabilities() raises an exception."""
        from backend.gamepad import GamepadManager, _DeviceHandler
        from backend.controller_mapping import build_evdev_lookup

        manager = GamepadManager()

        mock_device = MagicMock()
        mock_device.path = "/dev/input/event0"
        mock_device.name = "Broken Device"
        mock_device.fd = 99
        mock_device.capabilities.side_effect = OSError("permission denied")

        lookup = build_evdev_lookup(get_default_mapping())
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(mock_device, manager, lookup)
        manager._handlers[mock_device.path] = handler

        result = manager.getDeviceCapabilities()
        assert result == {}


# ---------------------------------------------------------------------------
# BrowserLauncher._deploy_extension — generates mapping JS
# ---------------------------------------------------------------------------


class TestDeployExtensionGeneratesMappingJs:
    def test_deploy_writes_generated_mapping_js(self, tmp_path: Path) -> None:
        """_deploy_extension writes generated_mapping.js to the deployed dir."""
        from backend.browser_launcher import BrowserLauncher

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        result = launcher._deploy_extension()

        assert result == dst
        assert (dst / "generated_mapping.js").exists()

    def test_deploy_generates_js_assignment_when_sdl_data_present(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When mapping has SDL data, generated_mapping.js contains a JS assignment."""
        from backend.browser_launcher import BrowserLauncher

        # Patch load_mapping to return a mapping with SDL halves
        mapping_with_sdl = _make_mapping_with_sdl(buttons={"accept": 1, "cancel": 0})
        monkeypatch.setattr(
            "backend.browser_launcher.load_mapping",
            lambda: mapping_with_sdl,
        )

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        launcher._deploy_extension()

        js_content = (dst / "generated_mapping.js").read_text(encoding="utf-8")
        assert "window.__htpcGeneratedMapping" in js_content

    def test_deploy_generates_stub_when_no_sdl_data(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When mapping has no SDL data, generated_mapping.js is a comment stub."""
        from backend.browser_launcher import BrowserLauncher

        # Patch load_mapping to return a mapping without SDL halves (all null)
        monkeypatch.setattr(
            "backend.browser_launcher.load_mapping",
            lambda: get_default_mapping(),
        )

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        launcher._deploy_extension()

        js_content = (dst / "generated_mapping.js").read_text(encoding="utf-8")
        assert "window.__htpcGeneratedMapping" not in js_content
        assert "//" in js_content

    def test_deploy_still_returns_path_when_mapping_js_fails(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """_deploy_extension returns the deployed path even if mapping JS generation fails."""
        from backend.browser_launcher import BrowserLauncher

        # Patch load_mapping to raise an exception
        monkeypatch.setattr(
            "backend.browser_launcher.load_mapping",
            lambda: (_ for _ in ()).throw(RuntimeError("disk error")),
        )

        launcher = BrowserLauncher()
        src = tmp_path / "extension"
        src.mkdir()
        (src / "manifest.json").write_text("{}", encoding="utf-8")
        dst = tmp_path / "deployed"

        launcher._extension_dir = src
        launcher._extension_deploy_dir = dst

        result = launcher._deploy_extension()

        # Should still return the deployed path (mapping JS failure is non-fatal)
        assert result == dst


# ---------------------------------------------------------------------------
# SettingsManager.saveControllerMapping — dual-record format, no _device
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestSaveControllerMappingIncludesDevice:
    def _make_manager(self, tmp_path: Path, gamepad_manager=None):
        from backend.settings_manager import SettingsManager
        from backend.config import Config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()

        config.save = MagicMock()
        library = MagicMock()
        plex_library = MagicMock()
        return SettingsManager(
            config, library, plex_library, gamepad_manager=gamepad_manager
        )

    def test_saves_device_capabilities_when_gamepad_connected(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """saveControllerMapping stores dual-record format (no _device key)."""
        caps = _make_device_caps()
        mock_gm = MagicMock()
        mock_gm.getDeviceCapabilities.return_value = caps

        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        manager = self._make_manager(tmp_path, gamepad_manager=mock_gm)

        entries = [
            {"name": "accept", "type": "button", "code": 305, "value": 1},
        ]
        with patch("backend.sdl_resolver.resolver.resolve", return_value={"type": "button", "sdl_button": 1}):
            manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        # _device is no longer stored — SDL resolution is done at capture time
        assert "_device" not in saved
        # Dual-record format is stored
        assert "evdev" in saved["accept"]
        assert "sdl" in saved["accept"]

    def test_skips_device_when_gamepad_manager_is_none(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """saveControllerMapping does not include _device when gamepad_manager is None."""
        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        manager = self._make_manager(tmp_path, gamepad_manager=None)

        entries = [
            {"name": "accept", "type": "button", "code": 305, "value": 1},
        ]
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert "_device" not in saved

    def test_skips_device_when_capabilities_empty(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """saveControllerMapping never stores _device (SDL resolution is at capture time)."""
        mock_gm = MagicMock()
        mock_gm.getDeviceCapabilities.return_value = {}

        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        manager = self._make_manager(tmp_path, gamepad_manager=mock_gm)

        entries = [
            {"name": "accept", "type": "button", "code": 305, "value": 1},
        ]
        with patch("backend.sdl_resolver.resolver.resolve", return_value=None):
            manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert "_device" not in saved


# ---------------------------------------------------------------------------
# load_mapping — drops _device key (legacy)
# ---------------------------------------------------------------------------


class TestLoadMappingPreservesDevice:
    def test_load_mapping_drops_legacy_device_key(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """load_mapping silently drops the legacy _device key."""
        from backend.controller_mapping import load_mapping, save_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        caps = _make_device_caps()
        mapping = get_default_mapping()
        mapping["_device"] = caps  # type: ignore[assignment]
        save_mapping(mapping)

        loaded = load_mapping()
        # _device is now silently dropped on load
        assert "_device" not in loaded

    def test_load_mapping_without_device_key_returns_no_device(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """load_mapping returns no _device key when file has none."""
        from backend.controller_mapping import load_mapping, save_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        save_mapping(get_default_mapping())

        loaded = load_mapping()
        assert "_device" not in loaded
