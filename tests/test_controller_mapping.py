"""Tests for backend/controller_mapping.py and gamepad.py refactor.

Covers:
  - load_mapping returns defaults when no file exists
  - load_mapping reads from file correctly
  - save_mapping writes and can be read back
  - build_evdev_lookup produces correct entries for default mapping
  - build_evdev_lookup handles button-type D-pad (non-axis D-pad)
  - get_default_mapping returns a copy (not the same object)
  - GamepadManager raw mode: startRawMode causes events to emit rawInput
  - GamepadManager.reloadMapping updates the lookup table
  - _DeviceHandler with unified lookup (mock evdev device)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from backend.controller_mapping import (
    DEFAULT_MAPPING,
    ACTIONS,
    build_evdev_lookup,
    get_default_mapping,
    get_mapping_path,
    load_mapping,
    save_mapping,
    _ACTION_KEY_MAP,
    _EV_KEY,
    _EV_ABS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    from evdev import ecodes
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False

pytestmark_evdev = pytest.mark.skipif(
    not _EVDEV_AVAILABLE, reason="evdev not available"
)


# ---------------------------------------------------------------------------
# controller_mapping module tests
# ---------------------------------------------------------------------------


class TestGetDefaultMapping:
    def test_returns_copy_not_same_object(self) -> None:
        """get_default_mapping returns a new dict, not the DEFAULT_MAPPING singleton."""
        result = get_default_mapping()
        assert result is not DEFAULT_MAPPING

    def test_copy_is_equal_to_default(self) -> None:
        """get_default_mapping content matches DEFAULT_MAPPING."""
        result = get_default_mapping()
        assert result == DEFAULT_MAPPING

    def test_modifying_copy_does_not_affect_default(self) -> None:
        """Mutating the returned copy does not change DEFAULT_MAPPING."""
        result = get_default_mapping()
        result["dpad_up"]["code"] = 9999
        assert DEFAULT_MAPPING["dpad_up"]["code"] != 9999

    def test_all_14_actions_present(self) -> None:
        """Default mapping contains all 14 semantic actions."""
        result = get_default_mapping()
        action_names = [name for name, _, _, _ in ACTIONS]
        for name in action_names:
            assert name in result, f"Missing action: {name}"


class TestLoadMapping:
    def test_returns_defaults_when_no_file(self, tmp_path: Path, monkeypatch) -> None:
        """load_mapping returns DEFAULT_MAPPING when config file does not exist."""
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: tmp_path / "nonexistent.json",
        )
        result = load_mapping()
        assert result == DEFAULT_MAPPING

    def test_reads_from_file_correctly(self, tmp_path: Path, monkeypatch) -> None:
        """load_mapping reads and returns the mapping from a valid JSON file."""
        mapping_file = tmp_path / "controller_mapping.json"
        custom_mapping = get_default_mapping()
        custom_mapping["accept"]["code"] = 999
        mapping_file.write_text(json.dumps(custom_mapping), encoding="utf-8")

        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        result = load_mapping()
        assert result["accept"]["code"] == 999

    def test_falls_back_to_defaults_on_corrupt_file(self, tmp_path: Path, monkeypatch) -> None:
        """load_mapping falls back to defaults when the file is corrupt JSON."""
        mapping_file = tmp_path / "controller_mapping.json"
        mapping_file.write_text("not valid json {{{", encoding="utf-8")

        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        result = load_mapping()
        assert result == DEFAULT_MAPPING

    def test_falls_back_to_defaults_on_wrong_root_type(self, tmp_path: Path, monkeypatch) -> None:
        """load_mapping falls back to defaults when root is not a JSON object."""
        mapping_file = tmp_path / "controller_mapping.json"
        mapping_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        result = load_mapping()
        assert result == DEFAULT_MAPPING

    def test_skips_invalid_entries_and_uses_defaults_for_them(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """load_mapping skips entries with invalid structure, using defaults for those."""
        mapping_file = tmp_path / "controller_mapping.json"
        partial = {"accept": {"type": "button", "code": 999, "value": 1}}
        mapping_file.write_text(json.dumps(partial), encoding="utf-8")

        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        result = load_mapping()
        # accept was overridden
        assert result["accept"]["code"] == 999
        # dpad_up was not in file, so it uses the default
        assert result["dpad_up"] == DEFAULT_MAPPING["dpad_up"]


class TestSaveMapping:
    def test_writes_and_can_be_read_back(self, tmp_path: Path, monkeypatch) -> None:
        """save_mapping writes JSON that load_mapping can read back."""
        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        custom = get_default_mapping()
        custom["cancel"]["code"] = 777
        save_mapping(custom)

        assert mapping_file.exists()
        result = load_mapping()
        assert result["cancel"]["code"] == 777

    def test_creates_parent_directories(self, tmp_path: Path, monkeypatch) -> None:
        """save_mapping creates parent directories if they don't exist."""
        mapping_file = tmp_path / "deep" / "nested" / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        save_mapping(get_default_mapping())
        assert mapping_file.exists()

    def test_atomic_write_produces_valid_json(self, tmp_path: Path, monkeypatch) -> None:
        """save_mapping produces valid JSON (atomic write via temp file + rename)."""
        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )
        save_mapping(get_default_mapping())
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "dpad_up" in data


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestBuildEvdevLookup:
    def test_default_mapping_button_entries(self) -> None:
        """build_evdev_lookup maps button entries to (EV_KEY, code, 1) → Qt.Key."""
        lookup = build_evdev_lookup(DEFAULT_MAPPING)

        # accept → BTN_EAST → Key_Return
        assert (ecodes.EV_KEY, ecodes.BTN_EAST, 1) in lookup
        assert lookup[(ecodes.EV_KEY, ecodes.BTN_EAST, 1)] == Qt.Key.Key_Return

        # cancel → BTN_SOUTH → Key_Escape
        assert (ecodes.EV_KEY, ecodes.BTN_SOUTH, 1) in lookup
        assert lookup[(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)] == Qt.Key.Key_Escape

    def test_default_mapping_dpad_axis_entries(self) -> None:
        """build_evdev_lookup maps D-pad axis entries to (EV_ABS, code, sign) → Qt.Key."""
        lookup = build_evdev_lookup(DEFAULT_MAPPING)

        # dpad_up → ABS_HAT0Y, value=-1 → Key_Up
        assert (ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)] == Qt.Key.Key_Up

        # dpad_down → ABS_HAT0Y, value=1 → Key_Down
        assert (ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1)] == Qt.Key.Key_Down

        # dpad_left → ABS_HAT0X, value=-1 → Key_Left
        assert (ecodes.EV_ABS, ecodes.ABS_HAT0X, -1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_HAT0X, -1)] == Qt.Key.Key_Left

        # dpad_right → ABS_HAT0X, value=1 → Key_Right
        assert (ecodes.EV_ABS, ecodes.ABS_HAT0X, 1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_HAT0X, 1)] == Qt.Key.Key_Right

    def test_default_mapping_trigger_entries(self) -> None:
        """build_evdev_lookup maps trigger axis entries to (EV_ABS, code, 1) → Qt.Key."""
        lookup = build_evdev_lookup(DEFAULT_MAPPING)

        # left_trigger → ABS_Z, value=1 → Key_Home
        assert (ecodes.EV_ABS, ecodes.ABS_Z, 1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_Z, 1)] == Qt.Key.Key_Home

        # right_trigger → ABS_RZ, value=1 → Key_End
        assert (ecodes.EV_ABS, ecodes.ABS_RZ, 1) in lookup
        assert lookup[(ecodes.EV_ABS, ecodes.ABS_RZ, 1)] == Qt.Key.Key_End

    def test_button_type_dpad_mapping(self) -> None:
        """build_evdev_lookup handles D-pad mapped to buttons (not axes)."""
        # Some controllers report D-pad as buttons
        custom_mapping = get_default_mapping()
        custom_mapping["dpad_up"] = {"type": "button", "code": 544, "value": 1}
        custom_mapping["dpad_down"] = {"type": "button", "code": 545, "value": 1}

        lookup = build_evdev_lookup(custom_mapping)

        assert (ecodes.EV_KEY, 544, 1) in lookup
        assert lookup[(ecodes.EV_KEY, 544, 1)] == Qt.Key.Key_Up
        assert (ecodes.EV_KEY, 545, 1) in lookup
        assert lookup[(ecodes.EV_KEY, 545, 1)] == Qt.Key.Key_Down

    def test_unknown_action_is_skipped(self) -> None:
        """build_evdev_lookup skips entries with unknown action names."""
        custom_mapping = get_default_mapping()
        custom_mapping["unknown_action"] = {"type": "button", "code": 999, "value": 1}

        lookup = build_evdev_lookup(custom_mapping)
        # The unknown action should not appear in the lookup
        assert (ecodes.EV_KEY, 999, 1) not in lookup

    def test_invalid_entry_is_skipped(self) -> None:
        """build_evdev_lookup skips entries with invalid code/value types."""
        custom_mapping = get_default_mapping()
        custom_mapping["accept"] = {"type": "button", "code": "not_an_int", "value": 1}

        lookup = build_evdev_lookup(custom_mapping)
        # accept should not be in lookup since code is invalid
        # (BTN_EAST from default is gone, replaced by invalid entry)
        assert (ecodes.EV_KEY, ecodes.BTN_EAST, 1) not in lookup

    def test_all_14_default_actions_have_entries(self) -> None:
        """build_evdev_lookup produces an entry for each of the 14 default actions."""
        lookup = build_evdev_lookup(DEFAULT_MAPPING)
        # 14 actions → 14 entries (each action maps to exactly one key combo)
        assert len(lookup) == 14


# ---------------------------------------------------------------------------
# GamepadManager tests
# ---------------------------------------------------------------------------


def _make_mock_device(path: str = "/dev/input/event0") -> MagicMock:
    """Create a mock evdev InputDevice."""
    device = MagicMock()
    device.path = path
    device.name = "Mock Gamepad"
    device.fd = 99
    device.capabilities.return_value = {}
    return device


def _make_mock_event(ev_type: int, code: int, value: int) -> MagicMock:
    """Create a mock evdev event."""
    event = MagicMock()
    event.type = ev_type
    event.code = code
    event.value = value
    return event


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestGamepadManagerRawMode:
    """Test GamepadManager raw mode behavior."""

    def _make_handler(self, manager, lookup=None):
        """Create a _DeviceHandler with a mock device."""
        from backend.gamepad import _DeviceHandler

        if lookup is None:
            lookup = build_evdev_lookup(DEFAULT_MAPPING)

        device = _make_mock_device()
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(device, manager, lookup)
        return handler

    def test_start_raw_mode_sets_flag(self) -> None:
        """startRawMode sets _raw_mode to True."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        assert manager._raw_mode is False
        manager.startRawMode()
        assert manager._raw_mode is True

    def test_stop_raw_mode_clears_flag(self) -> None:
        """stopRawMode sets _raw_mode to False."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()
        manager.stopRawMode()
        assert manager._raw_mode is False

    def test_raw_mode_button_press_emits_raw_input(self) -> None:
        """In raw mode, button press emits rawInput instead of injecting key."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)

        # Simulate BTN_SOUTH press
        event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
        handler._handle_event(event)

        assert len(received) == 1
        assert received[0] == ("button", ecodes.BTN_SOUTH, 1)

    def test_raw_mode_button_release_does_not_emit(self) -> None:
        """In raw mode, button release (value=0) does NOT emit rawInput."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)

        # Simulate BTN_SOUTH release
        event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 0)
        handler._handle_event(event)

        assert received == []

    def test_raw_mode_dpad_axis_emits_raw_input(self) -> None:
        """In raw mode, D-pad axis event emits rawInput."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)

        # Simulate ABS_HAT0Y = -1 (D-pad up)
        event = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)
        handler._handle_event(event)

        assert len(received) == 1
        assert received[0] == ("axis", ecodes.ABS_HAT0Y, -1)

    def test_raw_mode_dpad_axis_zero_does_not_emit(self) -> None:
        """In raw mode, D-pad axis returning to 0 does NOT emit rawInput."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)

        # First press
        event = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)
        handler._handle_event(event)
        # Release (value=0)
        event2 = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0)
        handler._handle_event(event2)

        # Only the press should have emitted
        assert len(received) == 1

    def test_raw_mode_trigger_axis_emits_raw_input(self) -> None:
        """In raw mode, trigger axis crossing threshold emits rawInput."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)
        # Set axis info so threshold is known
        handler._axis_info[ecodes.ABS_Z] = (0, 255)

        # Simulate ABS_Z = 200 (past 25% threshold of 255 = 63.75)
        event = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_Z, 200)
        handler._handle_event(event)

        assert len(received) == 1
        assert received[0][0] == "axis"
        assert received[0][1] == ecodes.ABS_Z

    def test_normal_mode_button_press_does_not_emit_raw_input(self) -> None:
        """In normal mode, button press does NOT emit rawInput."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        # raw mode is off by default

        received: list[tuple] = []
        manager.rawInput.connect(lambda t, c, v: received.append((t, c, v)))

        handler = self._make_handler(manager)

        event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
        handler._handle_event(event)

        assert received == []

    def test_raw_mode_does_not_inject_key_events(self) -> None:
        """In raw mode, no QKeyEvent is injected into the window."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        manager.startRawMode()

        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        with patch("backend.gamepad.QCoreApplication.sendEvent") as mock_send:
            event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
            handler._handle_event(event)
            mock_send.assert_not_called()


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestGamepadManagerReloadMapping:
    """Test GamepadManager.reloadMapping behavior."""

    def test_reload_mapping_updates_lookup(self, tmp_path: Path, monkeypatch) -> None:
        """reloadMapping rebuilds the lookup table from the saved config."""
        from backend.gamepad import GamepadManager

        # Start with default mapping (no file → defaults)
        mapping_file = tmp_path / "controller_mapping.json"
        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        manager = GamepadManager()
        # Before reload, lookup uses the default (BTN_EAST=305 → accept)
        assert (ecodes.EV_KEY, ecodes.BTN_EAST, 1) in manager._evdev_lookup

        # Now save a custom mapping that changes accept to code 999
        custom = get_default_mapping()
        custom["accept"]["code"] = 999
        mapping_file.write_text(json.dumps(custom), encoding="utf-8")

        manager.reloadMapping()

        # After reload, lookup uses the custom code
        assert (ecodes.EV_KEY, 999, 1) in manager._evdev_lookup
        assert (ecodes.EV_KEY, ecodes.BTN_EAST, 1) not in manager._evdev_lookup

    def test_reload_mapping_updates_existing_handlers(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """reloadMapping propagates the new lookup to all active device handlers."""
        from backend.gamepad import GamepadManager, _DeviceHandler

        mapping_file = tmp_path / "controller_mapping.json"
        mapping_file.write_text(json.dumps(get_default_mapping()), encoding="utf-8")

        monkeypatch.setattr(
            "backend.controller_mapping.get_mapping_path",
            lambda: mapping_file,
        )

        manager = GamepadManager()

        # Create a handler and register it
        device = _make_mock_device()
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(device, manager, manager._evdev_lookup)
        manager._handlers[device.path] = handler

        # Now save a new mapping and reload
        custom = get_default_mapping()
        custom["accept"]["code"] = 888
        mapping_file.write_text(json.dumps(custom), encoding="utf-8")

        manager.reloadMapping()

        # Handler's lookup should be updated
        assert (ecodes.EV_KEY, 888, 1) in handler._evdev_lookup


@pytest.mark.skipif(not _EVDEV_AVAILABLE, reason="evdev not available")
class TestDeviceHandlerUnifiedLookup:
    """Test _DeviceHandler event handling with the unified lookup."""

    def _make_handler(self, manager, lookup=None):
        from backend.gamepad import _DeviceHandler

        if lookup is None:
            lookup = build_evdev_lookup(DEFAULT_MAPPING)

        device = _make_mock_device()
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(device, manager, lookup)
        return handler

    def test_button_press_injects_key(self) -> None:
        """Button press event injects the mapped Qt key."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        with patch("backend.gamepad.QCoreApplication.sendEvent") as mock_send:
            with patch("backend.gamepad.QTimer"):
                event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
                handler._handle_event(event)

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] is mock_window

    def test_button_release_injects_key_release(self) -> None:
        """Button release event injects a KeyRelease event."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        injected_events = []

        def capture_event(window, event):
            injected_events.append(event.type())

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                # Press
                press_event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
                handler._handle_event(press_event)
                # Release
                release_event = _make_mock_event(ecodes.EV_KEY, ecodes.BTN_SOUTH, 0)
                handler._handle_event(release_event)

        assert QEvent.Type.KeyPress in injected_events
        assert QEvent.Type.KeyRelease in injected_events

    def test_unmapped_button_is_ignored(self) -> None:
        """Button events for codes not in the lookup are silently ignored."""
        from backend.gamepad import GamepadManager

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        with patch("backend.gamepad.QCoreApplication.sendEvent") as mock_send:
            event = _make_mock_event(ecodes.EV_KEY, 9999, 1)  # unmapped code
            handler._handle_event(event)

        mock_send.assert_not_called()

    def test_dpad_axis_press_and_release(self) -> None:
        """D-pad axis: press on non-zero value, release when value returns to 0."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        injected_events = []

        def capture_event(window, event):
            injected_events.append((event.type(), event.key()))

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                # D-pad up press
                press = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)
                handler._handle_event(press)
                # D-pad release
                release = _make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0)
                handler._handle_event(release)

        press_events = [(t, k) for t, k in injected_events if t == QEvent.Type.KeyPress]
        release_events = [(t, k) for t, k in injected_events if t == QEvent.Type.KeyRelease]

        assert len(press_events) == 1
        assert press_events[0][1] == Qt.Key.Key_Up
        assert len(release_events) == 1
        assert release_events[0][1] == Qt.Key.Key_Up

    def test_dpad_axis_direction_change_releases_old_key(self) -> None:
        """D-pad axis: changing direction releases the old key before pressing new one."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)

        injected_events = []

        def capture_event(window, event):
            injected_events.append((event.type(), event.key()))

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                # D-pad up
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1))
                # D-pad down (direction change without going through 0)
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1))

        # Should have: KeyPress(Up), KeyRelease(Up), KeyPress(Down)
        types_and_keys = [(t, k) for t, k in injected_events]
        assert (QEvent.Type.KeyPress, Qt.Key.Key_Up) in types_and_keys
        assert (QEvent.Type.KeyRelease, Qt.Key.Key_Up) in types_and_keys
        assert (QEvent.Type.KeyPress, Qt.Key.Key_Down) in types_and_keys

    def test_trigger_axis_threshold_crossing(self) -> None:
        """Trigger axis: key pressed when value crosses threshold, released when below."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)
        handler._axis_info[ecodes.ABS_Z] = (0, 255)

        injected_events = []

        def capture_event(window, event):
            injected_events.append((event.type(), event.key()))

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                # Below threshold (25% of 255 = 63.75)
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_Z, 30))
                assert injected_events == []

                # Above threshold
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_Z, 200))
                assert any(t == QEvent.Type.KeyPress for t, _ in injected_events)

                # Back below threshold
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_Z, 10))
                assert any(t == QEvent.Type.KeyRelease for t, _ in injected_events)

    def test_stick_axis_not_in_lookup_still_works(self) -> None:
        """Left stick (ABS_X/ABS_Y) still works even though it's not in the lookup."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        handler = self._make_handler(manager)
        handler._axis_info[ecodes.ABS_X] = (-32768, 32767)

        injected_events = []

        def capture_event(window, event):
            injected_events.append((event.type(), event.key()))

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                # Push stick far left (past dead zone)
                handler._handle_event(_make_mock_event(ecodes.EV_ABS, ecodes.ABS_X, -30000))

        assert any(k == Qt.Key.Key_Left for _, k in injected_events)

    def test_button_type_dpad_mapping_works(self) -> None:
        """D-pad mapped to buttons (not axes) works correctly via unified lookup."""
        from backend.gamepad import GamepadManager
        from PySide6.QtCore import QEvent

        # Custom mapping: D-pad up is a button
        custom_mapping = get_default_mapping()
        custom_mapping["dpad_up"] = {"type": "button", "code": 544, "value": 1}
        lookup = build_evdev_lookup(custom_mapping)

        manager = GamepadManager()
        mock_window = MagicMock()
        manager.window = mock_window

        device = _make_mock_device()
        from backend.gamepad import _DeviceHandler
        with patch("backend.gamepad.QSocketNotifier"):
            handler = _DeviceHandler(device, manager, lookup)

        injected_events = []

        def capture_event(window, event):
            injected_events.append((event.type(), event.key()))

        with patch("backend.gamepad.QCoreApplication.sendEvent", side_effect=capture_event):
            with patch("backend.gamepad.QTimer"):
                handler._handle_event(_make_mock_event(ecodes.EV_KEY, 544, 1))

        assert any(k == Qt.Key.Key_Up for _, k in injected_events)
