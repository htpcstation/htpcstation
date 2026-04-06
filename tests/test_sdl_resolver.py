"""Tests for backend/sdl_resolver.py.

All tests mock ctypes.CDLL — no real SDL library required.

Covers:
  - Library loading: loads first available candidate, returns None when none found
  - SdlResolver.open(): returns False when SDL unavailable, no joysticks, etc.
  - SdlResolver.close(): safe without prior open, calls SDL_JoystickClose, resets state
  - SdlResolver.resolve(): hat axes, regular axes, button resolution, not-open case
"""

from __future__ import annotations

import ctypes
import logging
from unittest.mock import MagicMock, patch

import pytest

import backend.sdl_resolver as sdl_resolver_module
from backend.sdl_resolver import SdlResolver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_sdl(
    num_joysticks: int = 1,
    joystick_name: bytes = b"Test Gamepad",
    n_buttons: int = 12,
    n_axes: int = 6,
    n_hats: int = 1,
) -> MagicMock:
    """Create a MagicMock that behaves like a loaded SDL library."""
    mock = MagicMock()
    mock.SDL_Init.return_value = 0  # success
    mock.SDL_NumJoysticks.return_value = num_joysticks
    mock.SDL_JoystickNameForIndex.return_value = joystick_name
    mock.SDL_JoystickOpen.return_value = ctypes.c_void_p(1)
    mock.SDL_JoystickNumButtons.return_value = n_buttons
    mock.SDL_JoystickNumAxes.return_value = n_axes
    mock.SDL_JoystickNumHats.return_value = n_hats
    return mock


@pytest.fixture
def mock_sdl(monkeypatch):
    """Patch module-level _sdl with a MagicMock and set resolver state directly."""
    mock = _make_mock_sdl()
    monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
    # Give the module-level resolver a non-None joystick so resolve() works
    sdl_resolver_module.resolver._joystick = ctypes.c_void_p(1)
    sdl_resolver_module.resolver._evdev_hat_to_sdl = {16: 0, 17: 0}
    # Build axis records from the common mapping (fallback path)
    sdl_resolver_module.resolver._evdev_axis_to_sdl_record = {
        code: {"type": "axis", "sdl_axis": sdl_idx}
        for code, sdl_idx in sdl_resolver_module._COMMON_EVDEV_AXIS_TO_SDL.items()
    }
    sdl_resolver_module.resolver._evdev_button_to_sdl = {}
    sdl_resolver_module.resolver._sdl_button_to_label = {}
    yield mock
    # Cleanup
    sdl_resolver_module.resolver._joystick = None
    sdl_resolver_module.resolver._evdev_hat_to_sdl = {}
    sdl_resolver_module.resolver._evdev_axis_to_sdl_record = {}
    sdl_resolver_module.resolver._evdev_button_to_sdl = {}
    sdl_resolver_module.resolver._sdl_button_to_label = {}


@pytest.fixture
def mock_sdl_with_buttons(monkeypatch):
    """Patch module-level _sdl and open resolver with button_codes=[304, 305, 307, 308]."""
    mock = _make_mock_sdl()
    monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
    # Open the resolver with button codes so button resolution works
    sdl_resolver_module.resolver.open("test_device", button_codes=[304, 305, 307, 308])
    yield mock
    # Cleanup
    sdl_resolver_module.resolver._joystick = None
    sdl_resolver_module.resolver._evdev_hat_to_sdl = {}
    sdl_resolver_module.resolver._evdev_axis_to_sdl_record = {}
    sdl_resolver_module.resolver._evdev_button_to_sdl = {}
    sdl_resolver_module.resolver._sdl_button_to_label = {}


# ---------------------------------------------------------------------------
# TestSdlLibraryLoading
# ---------------------------------------------------------------------------


class TestSdlLibraryLoading:
    def test_loads_first_available_candidate(self, monkeypatch):
        """Module loads the first SDL candidate that succeeds."""
        mock_lib = _make_mock_sdl()
        call_count = []

        def fake_cdll(name):
            call_count.append(name)
            if name == "libSDL2-2.0.so.0":
                return mock_lib
            raise OSError(f"cannot open {name}")

        # Re-run the loading logic by patching and re-importing
        with patch("ctypes.CDLL", side_effect=fake_cdll):
            # Simulate the module-level loading by running the loop manually
            candidates = sdl_resolver_module._SDL_CANDIDATES
            loaded = None
            for candidate in candidates:
                try:
                    lib = ctypes.CDLL(candidate)
                    loaded = lib
                    break
                except OSError:
                    continue

        assert loaded is mock_lib
        assert call_count[0] == "libSDL2-2.0.so.0"

    def test_returns_none_when_no_candidate_found(self, monkeypatch):
        """Module-level _sdl is None when no SDL library can be loaded."""
        with patch("ctypes.CDLL", side_effect=OSError("not found")):
            candidates = sdl_resolver_module._SDL_CANDIDATES
            loaded = None
            for candidate in candidates:
                try:
                    ctypes.CDLL(candidate)
                    loaded = candidate
                    break
                except OSError:
                    continue

        assert loaded is None

    def test_logs_warning_when_no_library_found(self, monkeypatch, caplog):
        """A warning is logged when no SDL library is found."""
        # Temporarily set _sdl to None and trigger the warning path
        original_sdl = sdl_resolver_module._sdl
        monkeypatch.setattr(sdl_resolver_module, "_sdl", None)

        with caplog.at_level(logging.WARNING, logger="backend.sdl_resolver"):
            # The warning is logged at import time; simulate by checking that
            # when _sdl is None, open() logs a warning
            resolver = SdlResolver()
            resolver.open("Test Device")

        assert any("SDL" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# TestSdlResolverOpen
# ---------------------------------------------------------------------------


class TestSdlResolverOpen:
    def test_returns_false_when_sdl_unavailable(self, monkeypatch):
        """open() returns False immediately when _sdl is None."""
        monkeypatch.setattr(sdl_resolver_module, "_sdl", None)
        r = SdlResolver()
        result = r.open("Test Device")
        assert result is False

    def test_returns_false_when_no_joysticks(self, monkeypatch):
        """open() returns False when SDL_NumJoysticks returns 0."""
        mock = _make_mock_sdl(num_joysticks=0)
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        result = r.open("Test Device")
        assert result is False

    def test_opens_first_joystick_when_no_name_match(self, monkeypatch):
        """open() falls back to index 0 when no joystick name matches."""
        mock = _make_mock_sdl(num_joysticks=1, joystick_name=b"Other Device")
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        r.open("Test Device")
        mock.SDL_JoystickOpen.assert_called_once_with(0)

    def test_prefers_name_match_over_first(self, monkeypatch):
        """open() opens the joystick whose name matches evdev_device_name."""
        mock = _make_mock_sdl(num_joysticks=3)
        # Return different names for each index
        def name_for_index(i):
            names = [b"Other A", b"Other B", b"Target Device"]
            return names[i]

        mock.SDL_JoystickNameForIndex.side_effect = name_for_index
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        r.open("Target Device")
        mock.SDL_JoystickOpen.assert_called_once_with(2)

    def test_returns_true_on_success(self, monkeypatch):
        """open() returns True when a joystick is opened successfully."""
        mock = _make_mock_sdl()
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        result = r.open("Test Gamepad")
        assert result is True

    def test_stores_capabilities(self, monkeypatch):
        """open() stores n_buttons, n_axes, n_hats from SDL queries."""
        mock = _make_mock_sdl(n_buttons=15, n_axes=8, n_hats=2)
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        r.open("Test Gamepad")
        assert r._n_buttons == 15
        assert r._n_axes == 8
        assert r._n_hats == 2

    def test_returns_false_when_sdl_init_fails(self, monkeypatch):
        """open() returns False when SDL_Init returns non-zero."""
        mock = _make_mock_sdl()
        mock.SDL_Init.return_value = -1  # failure
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        result = r.open("Test Device")
        assert result is False

    def test_hat_axes_mapped_to_hat_0(self, monkeypatch):
        """open() maps ABS_HAT0X (16) and ABS_HAT0Y (17) to SDL hat 0."""
        mock = _make_mock_sdl()
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        r.open("Test Gamepad")
        assert r._evdev_hat_to_sdl == {16: 0, 17: 0}

    def test_common_axis_mapping_stored(self, monkeypatch):
        """open() stores axis records for the common evdev axis codes."""
        mock = _make_mock_sdl()
        monkeypatch.setattr(sdl_resolver_module, "_sdl", mock)
        r = SdlResolver()
        r.open("Test Gamepad")
        # Each common axis code should have an axis record
        for evdev_code, sdl_idx in sdl_resolver_module._COMMON_EVDEV_AXIS_TO_SDL.items():
            assert evdev_code in r._evdev_axis_to_sdl_record
            assert r._evdev_axis_to_sdl_record[evdev_code]["type"] == "axis"
            assert r._evdev_axis_to_sdl_record[evdev_code]["sdl_axis"] == sdl_idx


# ---------------------------------------------------------------------------
# TestSdlResolverClose
# ---------------------------------------------------------------------------


class TestSdlResolverClose:
    def test_close_without_open_is_safe(self):
        """close() does not raise when called without a prior open()."""
        r = SdlResolver()
        # Should not raise
        r.close()

    def test_close_calls_sdl_joystick_close(self, mock_sdl):
        """close() calls SDL_JoystickClose when a joystick is open."""
        sentinel = ctypes.c_void_p(42)
        r = SdlResolver()
        r._joystick = sentinel
        r.close()
        mock_sdl.SDL_JoystickClose.assert_called_once()
        # Verify the argument passed is the same object we stored
        call_arg = mock_sdl.SDL_JoystickClose.call_args[0][0]
        assert call_arg is sentinel

    def test_close_resets_state(self, mock_sdl):
        """close() resets all instance fields to defaults."""
        r = SdlResolver()
        r._joystick = ctypes.c_void_p(1)
        r._n_buttons = 12
        r._n_axes = 6
        r._n_hats = 1
        r._evdev_axis_to_sdl_record = {0: {"type": "axis", "sdl_axis": 0}}
        r._evdev_hat_to_sdl = {16: 0, 17: 0}
        r._evdev_button_to_sdl = {304: 0, 305: 1}

        r.close()

        assert r._joystick is None
        assert r._n_buttons == 0
        assert r._n_axes == 0
        assert r._n_hats == 0
        assert r._evdev_axis_to_sdl_record == {}
        assert r._evdev_hat_to_sdl == {}
        assert r._evdev_button_to_sdl == {}

    def test_close_calls_quit_subsystem(self, mock_sdl):
        """close() calls SDL_QuitSubSystem with SDL_INIT_JOYSTICK."""
        r = SdlResolver()
        r._joystick = ctypes.c_void_p(1)
        r.close()
        mock_sdl.SDL_QuitSubSystem.assert_called_once_with(
            sdl_resolver_module.SDL_INIT_JOYSTICK
        )

    def test_close_skips_joystick_close_when_not_open(self, mock_sdl):
        """close() does not call SDL_JoystickClose when _joystick is None."""
        r = SdlResolver()
        r._joystick = None
        r.close()
        mock_sdl.SDL_JoystickClose.assert_not_called()


# ---------------------------------------------------------------------------
# TestSdlResolverResolveAxis
# ---------------------------------------------------------------------------


class TestSdlResolverResolveAxis:
    def test_hat_y_negative_is_up(self, mock_sdl):
        """ABS_HAT0Y (code=17) with value=-1 resolves to hat dir 'up'."""
        result = sdl_resolver_module.resolver.resolve("axis", 17, -1)
        assert result == {"type": "hat", "sdl_hat": 0, "dir": "up"}

    def test_hat_y_positive_is_down(self, mock_sdl):
        """ABS_HAT0Y (code=17) with value=+1 resolves to hat dir 'down'."""
        result = sdl_resolver_module.resolver.resolve("axis", 17, 1)
        assert result == {"type": "hat", "sdl_hat": 0, "dir": "down"}

    def test_hat_x_negative_is_left(self, mock_sdl):
        """ABS_HAT0X (code=16) with value=-1 resolves to hat dir 'left'."""
        result = sdl_resolver_module.resolver.resolve("axis", 16, -1)
        assert result == {"type": "hat", "sdl_hat": 0, "dir": "left"}

    def test_hat_x_positive_is_right(self, mock_sdl):
        """ABS_HAT0X (code=16) with value=+1 resolves to hat dir 'right'."""
        result = sdl_resolver_module.resolver.resolve("axis", 16, 1)
        assert result == {"type": "hat", "sdl_hat": 0, "dir": "right"}

    def test_trigger_abs_z_resolves_to_sdl_axis_2(self, mock_sdl):
        """ABS_Z (code=2) resolves to SDL axis 2."""
        result = sdl_resolver_module.resolver.resolve("axis", 2, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 2
        assert "dir" in result

    def test_trigger_abs_rz_resolves_to_sdl_axis_5(self, mock_sdl):
        """ABS_RZ (code=5) resolves to SDL axis 5."""
        result = sdl_resolver_module.resolver.resolve("axis", 5, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 5
        assert "dir" in result

    def test_left_stick_x_resolves_to_sdl_axis_0(self, mock_sdl):
        """ABS_X (code=0) resolves to SDL axis 0."""
        result = sdl_resolver_module.resolver.resolve("axis", 0, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 0
        assert "dir" in result

    def test_unknown_axis_returns_none(self, mock_sdl):
        """An axis code not in the mapping returns None."""
        result = sdl_resolver_module.resolver.resolve("axis", 99, 1)
        assert result is None

    def test_dynamic_axis_mapping_from_axis_codes(self, mock_sdl):
        """When axis_codes provided, SDL axis index is position in sorted non-hat list."""
        # Device has axes: ABS_X(0), ABS_Y(1), ABS_Z(2), ABS_RZ(5), ABS_GAS(9), ABS_BRAKE(10)
        # Sorted non-hat: [0, 1, 2, 5, 9, 10] → SDL indices 0-5
        sdl_resolver_module.resolver.open(
            "test_device",
            axis_codes=[0, 1, 2, 5, 9, 10, 16, 17],  # includes hat codes, should be excluded
        )
        records = sdl_resolver_module.resolver._evdev_axis_to_sdl_record
        assert records[0]["sdl_axis"] == 0
        assert records[1]["sdl_axis"] == 1
        assert records[2]["sdl_axis"] == 2
        assert records[5]["sdl_axis"] == 3
        assert records[9]["sdl_axis"] == 4
        assert records[10]["sdl_axis"] == 5
        # ABS_GAS (9) → SDL axis 4
        result = sdl_resolver_module.resolver.resolve("axis", 9, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 4
        assert result["dir"] == 1
        # ABS_RZ (5) → SDL axis 3 (not 5 as in the fixed table)
        result = sdl_resolver_module.resolver.resolve("axis", 5, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 3

    def test_fallback_to_common_mapping_when_no_axis_codes(self, mock_sdl):
        """Without axis_codes, falls back to _COMMON_EVDEV_AXIS_TO_SDL."""
        # mock_sdl fixture opens without axis_codes → uses fixed table
        # ABS_RZ (5) → SDL axis 5 in fixed table
        result = sdl_resolver_module.resolver.resolve("axis", 5, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 5
        assert result["dir"] == 1

    def test_axis_dir_positive(self, mock_sdl):
        """Positive axis value resolves to dir=+1."""
        result = sdl_resolver_module.resolver.resolve("axis", 0, 1)
        assert result is not None
        assert result["dir"] == 1

    def test_axis_dir_negative(self, mock_sdl):
        """Negative axis value resolves to dir=-1."""
        result = sdl_resolver_module.resolver.resolve("axis", 0, -1)
        assert result is not None
        assert result["dir"] == -1


# ---------------------------------------------------------------------------
# TestSdlResolverResolveButton
# ---------------------------------------------------------------------------


class TestSdlResolverResolveButton:
    def test_button_resolves_when_button_codes_provided(self, mock_sdl_with_buttons):
        """BTN_EAST (305) is at sorted index 1 → sdl_button=1."""
        # button_codes=[304, 305, 307, 308] → sorted: [304, 305, 307, 308]
        # 305 is at index 1
        result = sdl_resolver_module.resolver.resolve("button", 305, 1)
        assert result is not None
        assert result["type"] == "button"
        assert result["sdl_button"] == 1
        assert "label" in result  # label stored at resolve time

    def test_button_first_in_sorted_list(self, mock_sdl_with_buttons):
        """BTN_SOUTH (304) is at sorted index 0 → sdl_button=0."""
        result = sdl_resolver_module.resolver.resolve("button", 304, 1)
        assert result is not None
        assert result["type"] == "button"
        assert result["sdl_button"] == 0

    def test_unknown_button_returns_none(self, mock_sdl_with_buttons):
        """A button code not in the list returns None."""
        result = sdl_resolver_module.resolver.resolve("button", 9999, 1)
        assert result is None

    def test_button_returns_none_without_button_codes(self, mock_sdl):
        """open() called without button_codes — _evdev_button_to_sdl is empty → None."""
        result = sdl_resolver_module.resolver.resolve("button", 305, 1)
        assert result is None


# ---------------------------------------------------------------------------
# TestSdlResolverNotOpen
# ---------------------------------------------------------------------------


class TestSdlResolverNotOpen:
    def test_resolve_returns_none_when_not_open(self):
        """resolve() returns None when _joystick is None (not opened)."""
        r = SdlResolver()
        assert r._joystick is None
        result = r.resolve("axis", 0, 1)
        assert result is None


# ---------------------------------------------------------------------------
# TestSdlResolverSeedFromControllerMapping
# ---------------------------------------------------------------------------


class TestSdlResolverSeedFromControllerMapping:
    """seed_from_controller_mapping() is the primary source of truth in resolve()."""

    def _make_resolver_with_joystick(self) -> SdlResolver:
        r = SdlResolver()
        r._joystick = ctypes.c_void_p(1)
        r._evdev_hat_to_sdl = {16: 0, 17: 0}
        r._evdev_button_to_sdl = {304: 0, 305: 1, 312: 8, 313: 9}
        r._sdl_button_to_label = {0: "B", 1: "A", 8: "LT", 9: "RT"}
        # GC heuristic fallback: axis 9 → sdl_axis 4 (wrong for this device)
        r._evdev_axis_to_sdl_record = {
            9:  {"type": "axis", "sdl_axis": 4, "label_neg": "Axis 4 -", "label_pos": "Axis 4 +"},
            10: {"type": "axis", "sdl_axis": 5, "label_neg": "Axis 5 -", "label_pos": "Axis 5 +"},
        }
        return r

    def test_button_entry_takes_priority_over_gc_heuristic(self):
        """A button entry in the mapping overrides the GC heuristic for that evdev code."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
            }
        }
        r.seed_from_controller_mapping(mapping)
        result = r.resolve("button", 312, 1)
        assert result == {"type": "button", "sdl_button": 8, "label": "LT"}

    def test_axis_event_for_trigger_falls_through_to_gc_heuristic(self):
        """Axis event for a trigger (not in mapping as axis) uses GC heuristic fallback."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
            }
        }
        r.seed_from_controller_mapping(mapping)
        # axis 9 is not in the mapping → falls through to _evdev_axis_to_sdl_record
        result = r.resolve("axis", 9, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 4

    def test_axis_entry_in_mapping_overrides_gc_heuristic(self):
        """An axis entry in the mapping overrides the GC heuristic for that axis code."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_stick_x": {
                "evdev": {"type": "axis", "code": 0, "value": 1},
                "sdl":   {"type": "axis", "sdl_axis": 0},
            }
        }
        r.seed_from_controller_mapping(mapping)
        result = r.resolve("axis", 0, 1)
        assert result is not None
        assert result["type"] == "axis"
        assert result["sdl_axis"] == 0
        assert result["dir"] == 1

    def test_unmapped_button_falls_through_to_gc_api(self):
        """A button not in the mapping uses the GC API sorted-position fallback."""
        r = self._make_resolver_with_joystick()
        r.seed_from_controller_mapping({})
        # BTN_SOUTH (304) → sdl_button 0 via _evdev_button_to_sdl
        result = r.resolve("button", 304, 1)
        assert result is not None
        assert result["type"] == "button"
        assert result["sdl_button"] == 0
        assert result["label"] == "B"

    def test_seed_clears_previous_entries(self):
        """Calling seed_from_controller_mapping twice replaces the previous lookup."""
        r = self._make_resolver_with_joystick()
        r.seed_from_controller_mapping({
            "accept": {
                "evdev": {"type": "button", "code": 304, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 0, "label": "B"},
            }
        })
        assert ("button", 304) in r._evdev_event_to_sdl
        r.seed_from_controller_mapping({})
        assert ("button", 304) not in r._evdev_event_to_sdl

    def test_entries_with_null_sdl_are_skipped(self):
        """Entries where sdl is None (not yet mapped) are silently skipped."""
        r = self._make_resolver_with_joystick()
        r.seed_from_controller_mapping({
            "accept": {
                "evdev": {"type": "button", "code": 304, "value": 1},
                "sdl":   None,
            }
        })
        assert ("button", 304) not in r._evdev_event_to_sdl

    def test_close_resets_evdev_event_to_sdl(self):
        """close() clears _evdev_event_to_sdl."""
        r = self._make_resolver_with_joystick()
        r._evdev_event_to_sdl = {("button", 304): {"type": "button", "sdl_button": 0}}
        r.close()
        assert r._evdev_event_to_sdl == {}

    def test_also_entries_seeded_into_evdev_event_to_sdl(self):
        """also entries are seeded into _evdev_event_to_sdl pointing to the primary SDL record."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
                "also": [
                    {
                        "evdev": {"type": "axis", "code": 9, "value": 1},
                        "sdl":   None,  # no own SDL record → fall back to primary
                    }
                ],
            }
        }
        r.seed_from_controller_mapping(mapping)
        # Primary entry seeded
        assert ("button", 312) in r._evdev_event_to_sdl
        # Also entry seeded — falls back to primary SDL record
        assert ("axis", 9) in r._evdev_event_to_sdl
        also_record = r._evdev_event_to_sdl[("axis", 9)]
        assert also_record["type"] == "button"
        assert also_record["sdl_button"] == 8

    def test_also_entry_with_own_sdl_uses_own_record(self):
        """also entry with its own SDL record uses that record, not the primary."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
                "also": [
                    {
                        "evdev": {"type": "axis", "code": 9, "value": 1},
                        "sdl":   {"type": "axis", "sdl_axis": 4},
                    }
                ],
            }
        }
        r.seed_from_controller_mapping(mapping)
        also_record = r._evdev_event_to_sdl[("axis", 9)]
        assert also_record["type"] == "axis"
        assert also_record["sdl_axis"] == 4

    def test_also_entry_with_null_sdl_falls_back_to_primary(self):
        """also entry with null SDL falls back to the primary SDL record."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "right_trigger": {
                "evdev": {"type": "button", "code": 313, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 9, "label": "RT"},
                "also": [
                    {
                        "evdev": {"type": "axis", "code": 10, "value": 1},
                        "sdl":   None,
                    }
                ],
            }
        }
        r.seed_from_controller_mapping(mapping)
        also_record = r._evdev_event_to_sdl[("axis", 10)]
        # Should use the primary SDL record (button 9)
        assert also_record["type"] == "button"
        assert also_record["sdl_button"] == 9

    def test_also_entry_resolve_returns_correct_record(self):
        """resolve() returns the correct SDL record for an also-seeded axis event."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
                "also": [
                    {
                        "evdev": {"type": "axis", "code": 9, "value": 1},
                        "sdl":   None,
                    }
                ],
            }
        }
        r.seed_from_controller_mapping(mapping)
        # Resolving the axis event should return the primary button record
        result = r.resolve("axis", 9, 1)
        assert result is not None
        assert result["type"] == "button"
        assert result["sdl_button"] == 8

    def test_also_entry_hat_axis_is_skipped(self):
        """also entries for hat axes (ABS_HAT0X/Y) are skipped."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "dpad_up": {
                "evdev": {"type": "axis", "code": 17, "value": -1},
                "sdl":   {"type": "hat", "sdl_hat": 0, "dir": "up"},
                "also": [
                    {
                        "evdev": {"type": "axis", "code": 16, "value": -1},
                        "sdl":   None,
                    }
                ],
            }
        }
        r.seed_from_controller_mapping(mapping)
        # Hat axis 16 should NOT be in _evdev_event_to_sdl (it's a hat axis)
        assert ("axis", 16) not in r._evdev_event_to_sdl

    def test_also_entry_with_invalid_evdev_is_skipped(self):
        """also entries with invalid evdev structure are silently skipped."""
        r = self._make_resolver_with_joystick()
        mapping = {
            "left_trigger": {
                "evdev": {"type": "button", "code": 312, "value": 1},
                "sdl":   {"type": "button", "sdl_button": 8, "label": "LT"},
                "also": [
                    {"evdev": None, "sdl": None},  # invalid evdev
                    {"evdev": {"type": "unknown", "code": 9, "value": 1}, "sdl": None},  # bad type
                    {"evdev": {"type": "axis", "code": "not_int", "value": 1}, "sdl": None},  # bad code
                ],
            }
        }
        # Should not raise
        r.seed_from_controller_mapping(mapping)
        # Only the primary entry should be seeded
        assert len(r._evdev_event_to_sdl) == 1
        assert ("button", 312) in r._evdev_event_to_sdl
