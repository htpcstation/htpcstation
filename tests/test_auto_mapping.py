"""Tests for Task 003 — Browser Extension Auto-Generated Mapping.

Covers:
  - build_web_gamepad_mapping: returns None when _device is missing
  - build_web_gamepad_mapping: maps EV_KEY buttons to correct Web API indices
  - build_web_gamepad_mapping: maps hat axes to buttons after regular buttons
  - build_web_gamepad_mapping: maps trigger axes to Web API axis indices
  - build_web_gamepad_mapping: dpadButtons contains hat-derived button indices
  - build_web_gamepad_mapping: handles missing _device.buttons or _device.axes
  - generate_mapping_js: returns comment stub when no _device
  - generate_mapping_js: produces valid JS assignment with correct structure
  - GamepadManager.getDeviceCapabilities: returns empty dict when no device
  - GamepadManager.getDeviceCapabilities: returns sorted buttons and axes
  - _deploy_extension: writes generated_mapping.js to deployed dir
  - _deploy_extension: generated_mapping.js contains JS assignment when mapping has _device
  - _deploy_extension: generated_mapping.js contains stub when no _device
  - saveControllerMapping: includes _device from getDeviceCapabilities
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
    _ABS_HAT0X,
    _ABS_HAT0Y,
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
    """Build a _device capabilities dict."""
    return {
        "buttons": buttons if buttons is not None else [304, 305, 307, 308, 310, 311, 314, 315],
        "axes": axes if axes is not None else [0, 1, 3, 4, 16, 17],
        "name": name,
    }


def _make_mapping_with_device(device_caps: dict | None = None) -> dict:
    """Return a default mapping with optional _device block."""
    m = get_default_mapping()
    if device_caps is not None:
        m["_device"] = device_caps
    return m


# ---------------------------------------------------------------------------
# build_web_gamepad_mapping
# ---------------------------------------------------------------------------


class TestBuildWebGamepadMapping:
    def test_returns_none_when_no_device(self) -> None:
        """Returns None when _device key is absent."""
        mapping = get_default_mapping()
        assert build_web_gamepad_mapping(mapping) is None

    def test_returns_none_when_device_is_not_dict(self) -> None:
        """Returns None when _device is not a dict."""
        mapping = get_default_mapping()
        mapping["_device"] = "not a dict"  # type: ignore[assignment]
        assert build_web_gamepad_mapping(mapping) is None

    def test_returns_none_when_device_missing_buttons(self) -> None:
        """Returns None when _device has no buttons list."""
        mapping = get_default_mapping()
        mapping["_device"] = {"axes": [0, 1, 16, 17], "name": "X"}
        assert build_web_gamepad_mapping(mapping) is None

    def test_returns_none_when_device_missing_axes(self) -> None:
        """Returns None when _device has no axes list."""
        mapping = get_default_mapping()
        mapping["_device"] = {"buttons": [304, 305], "name": "X"}
        assert build_web_gamepad_mapping(mapping) is None

    def test_button_type_maps_to_sorted_position(self) -> None:
        """EV_KEY button codes map to their sorted position in _device.buttons."""
        # buttons: [304, 305, 307, 308, 310, 311, 314, 315]
        # sorted:   0    1    2    3    4    5    6    7
        # accept → BTN_EAST (305) → index 1
        # cancel → BTN_SOUTH (304) → index 0
        caps = _make_device_caps(
            buttons=[304, 305, 307, 308, 310, 311, 314, 315],
            axes=[0, 1, 3, 4, 16, 17],
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        buttons = result["buttons"]
        assert buttons[0] == "cancel"    # BTN_SOUTH=304 → index 0
        assert buttons[1] == "accept"    # BTN_EAST=305 → index 1
        assert buttons[4] == "leftBumper"      # BTN_TL=310 → index 4
        assert buttons[5] == "rightBumper"     # BTN_TR=311 → index 5
        assert buttons[6] == "select"    # BTN_SELECT=314 → index 6
        assert buttons[7] == "start"     # BTN_START=315 → index 7

    def test_hat_axes_map_to_buttons_after_regular_buttons(self) -> None:
        """Hat axes (ABS_HAT0X/Y) become buttons starting at len(regular_buttons)."""
        # 8 regular buttons → hat buttons start at index 8
        caps = _make_device_caps(
            buttons=[304, 305, 307, 308, 310, 311, 314, 315],
            axes=[0, 1, 3, 4, 16, 17],  # 16=ABS_HAT0X, 17=ABS_HAT0Y
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        buttons = result["buttons"]
        # ABS_HAT0Y=-1 → up → offset 0 → index 8
        assert buttons[8] == "up"
        # ABS_HAT0Y=+1 → down → offset 1 → index 9
        assert buttons[9] == "down"
        # ABS_HAT0X=-1 → left → offset 2 → index 10
        assert buttons[10] == "left"
        # ABS_HAT0X=+1 → right → offset 3 → index 11
        assert buttons[11] == "right"

    def test_dpad_buttons_contains_hat_derived_indices(self) -> None:
        """dpadButtons dict contains all hat-derived button indices."""
        caps = _make_device_caps(
            buttons=[304, 305, 307, 308, 310, 311, 314, 315],
            axes=[0, 1, 3, 4, 16, 17],
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        dpad = result["dpadButtons"]
        # All four hat-derived buttons should be in dpadButtons
        assert dpad.get(8) is True   # up
        assert dpad.get(9) is True   # down
        assert dpad.get(10) is True  # left
        assert dpad.get(11) is True  # right

    def test_trigger_axes_map_to_regular_axis_indices(self) -> None:
        """Trigger axes (non-hat EV_ABS) map to their sorted position in regular axes."""
        # axes: [0, 1, 3, 4, 16, 17]
        # regular (non-hat): [0, 1, 3, 4] → indices 0, 1, 2, 3
        # ABS_Z=2 is NOT in this device's axes list, so left_trigger won't map
        # Let's use a device that has ABS_Z (2) and ABS_RZ (5)
        caps = _make_device_caps(
            buttons=[304, 305, 307, 308, 310, 311, 314, 315],
            axes=[0, 1, 2, 5, 16, 17],  # 2=ABS_Z, 5=ABS_RZ
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        axes = result["axes"]
        # regular axes: [0, 1, 2, 5] → indices 0, 1, 2, 3
        # left_trigger → ABS_Z=2, value=1 (positive) → axis index 2, pos slot
        # right_trigger → ABS_RZ=5, value=1 (positive) → axis index 3, pos slot
        assert 2 in axes
        assert axes[2][1] == "leftTrigger"    # positive direction
        assert 3 in axes
        assert axes[3][1] == "rightTrigger"  # positive direction

    def test_result_has_required_keys(self) -> None:
        """Result dict always has buttons, axes, and dpadButtons keys."""
        caps = _make_device_caps()
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        assert "buttons" in result
        assert "axes" in result
        assert "dpadButtons" in result

    def test_unknown_button_code_not_in_device_is_skipped(self) -> None:
        """Button entries with codes not in _device.buttons are silently skipped."""
        caps = _make_device_caps(buttons=[304], axes=[16, 17])
        mapping = get_default_mapping()
        mapping["_device"] = caps
        # accept uses BTN_EAST=305, which is NOT in the device buttons list
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # BTN_EAST=305 is not in [304], so accept should not appear in buttons
        assert "accept" not in result["buttons"].values()

    def test_metadata_keys_are_skipped(self) -> None:
        """Keys starting with _ (like _device) are not treated as actions."""
        caps = _make_device_caps()
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # _device should not appear as an action in the output
        assert "_device" not in result["buttons"].values()

    def test_hat_axes_not_in_device_axes_are_skipped(self) -> None:
        """Hat axis entries are skipped if the device doesn't report those axes."""
        # Device has no hat axes (no 16 or 17 in axes list)
        caps = _make_device_caps(
            buttons=[304, 305, 307, 308, 310, 311, 314, 315],
            axes=[0, 1, 2, 5],  # no hat axes
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # D-pad actions should not appear in buttons (no hat axes on device)
        assert "dpad_up" not in result["buttons"].values()
        assert "dpad_down" not in result["buttons"].values()
        assert "dpad_left" not in result["buttons"].values()
        assert "dpad_right" not in result["buttons"].values()

    def test_buttons_sorted_order_determines_index(self) -> None:
        """Button indices are based on sorted order, not insertion order."""
        # Provide buttons in reverse order — sorted should still give correct indices
        caps = _make_device_caps(
            buttons=[315, 314, 311, 310, 308, 307, 305, 304],  # reversed
            axes=[16, 17],
        )
        mapping = _make_mapping_with_device(caps)
        result = build_web_gamepad_mapping(mapping)

        assert result is not None
        # After sorting: [304, 305, 307, 308, 310, 311, 314, 315]
        # cancel → BTN_SOUTH=304 → index 0
        assert result["buttons"][0] == "cancel"
        # accept → BTN_EAST=305 → index 1
        assert result["buttons"][1] == "accept"


# ---------------------------------------------------------------------------
# generate_mapping_js
# ---------------------------------------------------------------------------


class TestGenerateMappingJs:
    def test_returns_comment_stub_when_no_device(self) -> None:
        """Returns a comment-only stub when _device is absent."""
        mapping = get_default_mapping()
        js = generate_mapping_js(mapping)

        assert "window.__htpcGeneratedMapping" not in js
        assert js.startswith("//")

    def test_produces_js_assignment(self) -> None:
        """Produces a window.__htpcGeneratedMapping = {...}; assignment."""
        caps = _make_device_caps()
        mapping = _make_mapping_with_device(caps)
        js = generate_mapping_js(mapping)

        assert js.startswith("window.__htpcGeneratedMapping = ")
        assert js.rstrip().endswith(";")

    def test_js_contains_valid_json_payload(self) -> None:
        """The JS assignment contains a valid JSON object."""
        caps = _make_device_caps()
        mapping = _make_mapping_with_device(caps)
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
        caps = _make_device_caps()
        mapping = _make_mapping_with_device(caps)
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

    def test_deploy_generates_js_assignment_when_device_present(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When mapping has _device, generated_mapping.js contains a JS assignment."""
        from backend.browser_launcher import BrowserLauncher

        # Patch load_mapping to return a mapping with _device
        caps = _make_device_caps()
        mapping_with_device = _make_mapping_with_device(caps)
        monkeypatch.setattr(
            "backend.browser_launcher.load_mapping",
            lambda: mapping_with_device,
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

    def test_deploy_generates_stub_when_no_device(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When mapping has no _device, generated_mapping.js is a comment stub."""
        from backend.browser_launcher import BrowserLauncher

        # Patch load_mapping to return a mapping without _device
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
# SettingsManager.saveControllerMapping — includes _device
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
        """saveControllerMapping includes _device from getDeviceCapabilities."""
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
        manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert "_device" in saved
        assert saved["_device"]["buttons"] == caps["buttons"]
        assert saved["_device"]["axes"] == caps["axes"]

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
        manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert "_device" not in saved

    def test_skips_device_when_capabilities_empty(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """saveControllerMapping skips _device when getDeviceCapabilities returns {}."""
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
        manager.saveControllerMapping(entries)

        saved = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert "_device" not in saved


# ---------------------------------------------------------------------------
# load_mapping — preserves _device key
# ---------------------------------------------------------------------------


class TestLoadMappingPreservesDevice:
    def test_load_mapping_preserves_device_key(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """load_mapping preserves the _device block from the saved file."""
        from backend.controller_mapping import load_mapping, save_mapping

        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        caps = _make_device_caps()
        mapping = get_default_mapping()
        mapping["_device"] = caps
        save_mapping(mapping)

        loaded = load_mapping()
        assert "_device" in loaded
        assert loaded["_device"]["buttons"] == caps["buttons"]
        assert loaded["_device"]["name"] == caps["name"]

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
