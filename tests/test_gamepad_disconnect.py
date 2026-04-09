"""Tests for Task 012 — gamepad disconnect crash + hint label flash fixes.

Covers:
  - Bug 1: _cleanup disconnects notifier signal and schedules deleteLater
  - Bug 1: _remove_device calls handler.deleteLater() instead of just dropping
  - Bug 2: setGamepadInput() is NOT called on the first _on_readable (buffered events)
  - Bug 2: setGamepadInput() IS called after _ready is True
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evdev_mocks():
    """Return a minimal evdev mock namespace."""
    ecodes = MagicMock()
    ecodes.EV_KEY = 1
    ecodes.EV_ABS = 3
    ecodes.ABS_X = 0
    ecodes.ABS_Y = 1

    device = MagicMock()
    device.fd = 5
    device.name = "Test Gamepad"
    device.path = "/dev/input/event5"
    device.capabilities.return_value = {}

    return ecodes, device


def _make_handler(device, ecodes_mock):
    """Instantiate a _DeviceHandler with evdev mocked out."""
    import backend.gamepad as gp_module

    manager = MagicMock()
    manager._raw_mode = False
    manager._external_active = False
    manager.keys = None
    manager.window = None

    notifier = MagicMock()

    with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
         patch.object(gp_module, "ecodes", ecodes_mock), \
         patch("backend.gamepad.QSocketNotifier", return_value=notifier):
        handler = gp_module._DeviceHandler(device, manager, {})

    handler._notifier = notifier
    return handler, manager, notifier


# ---------------------------------------------------------------------------
# Bug 1 — _cleanup properly tears down the notifier
# ---------------------------------------------------------------------------

class TestCleanupNotifier:
    def test_cleanup_disables_notifier(self):
        ecodes_mock, device = _make_evdev_mocks()
        handler, _, notifier = _make_handler(device, ecodes_mock)

        handler._cleanup()

        notifier.setEnabled.assert_called_with(False)

    def test_cleanup_disconnects_signal(self):
        ecodes_mock, device = _make_evdev_mocks()
        handler, _, notifier = _make_handler(device, ecodes_mock)

        handler._cleanup()

        notifier.activated.disconnect.assert_called_once_with(handler._on_readable)

    def test_cleanup_schedules_delete_later(self):
        ecodes_mock, device = _make_evdev_mocks()
        handler, _, notifier = _make_handler(device, ecodes_mock)

        handler._cleanup()

        notifier.deleteLater.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 1 — _remove_device calls handler.deleteLater()
# ---------------------------------------------------------------------------

class TestRemoveDevice:
    def test_remove_device_calls_delete_later(self):
        import backend.gamepad as gp_module

        manager_obj = MagicMock()
        manager_obj._raw_mode = False
        manager_obj._external_active = False
        manager_obj.keys = None
        manager_obj.window = None

        ecodes_mock, device = _make_evdev_mocks()
        notifier = MagicMock()

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
             patch.object(gp_module, "ecodes", ecodes_mock), \
             patch("backend.gamepad.QSocketNotifier", return_value=notifier):
            gm = gp_module.GamepadManager()

        handler_mock = MagicMock()
        gm._handlers["/dev/input/event5"] = handler_mock

        gm._remove_device("/dev/input/event5")

        handler_mock.deleteLater.assert_called_once()
        assert "/dev/input/event5" not in gm._handlers

    def test_remove_device_missing_path_is_noop(self):
        import backend.gamepad as gp_module

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True):
            gm = gp_module.GamepadManager()

        # Should not raise
        gm._remove_device("/dev/input/event99")


# ---------------------------------------------------------------------------
# Bug 2 — _ready flag prevents setGamepadInput on first read
# ---------------------------------------------------------------------------

class TestReadyFlag:
    def test_ready_starts_false(self):
        ecodes_mock, device = _make_evdev_mocks()
        handler, _, _ = _make_handler(device, ecodes_mock)

        assert handler._ready is False

    def test_ready_set_after_first_on_readable(self):
        import backend.gamepad as gp_module

        ecodes_mock, device = _make_evdev_mocks()
        device.read.return_value = []  # no events

        handler, _, _ = _make_handler(device, ecodes_mock)

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
             patch.object(gp_module, "ecodes", ecodes_mock):
            handler._on_readable()

        assert handler._ready is True

    def test_ready_set_even_on_blocking_io_error(self):
        import backend.gamepad as gp_module

        ecodes_mock, device = _make_evdev_mocks()
        device.read.side_effect = BlockingIOError

        handler, _, _ = _make_handler(device, ecodes_mock)

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
             patch.object(gp_module, "ecodes", ecodes_mock):
            handler._on_readable()

        assert handler._ready is True

    def test_set_gamepad_input_not_called_when_not_ready(self):
        import backend.gamepad as gp_module

        ecodes_mock, device = _make_evdev_mocks()
        handler, manager, _ = _make_handler(device, ecodes_mock)

        keys_mock = MagicMock()
        manager.keys = keys_mock
        manager.window = MagicMock()
        handler._manager = manager
        handler._ready = False  # explicitly not ready

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
             patch.object(gp_module, "ecodes", ecodes_mock), \
             patch("backend.gamepad.QKeyEvent"), \
             patch("backend.gamepad.QCoreApplication"):
            from PySide6.QtCore import QEvent
            handler._inject(QEvent.Type.KeyPress, MagicMock())

        keys_mock.setGamepadInput.assert_not_called()

    def test_set_gamepad_input_called_when_ready(self):
        import backend.gamepad as gp_module

        ecodes_mock, device = _make_evdev_mocks()
        handler, manager, _ = _make_handler(device, ecodes_mock)

        keys_mock = MagicMock()
        manager.keys = keys_mock
        manager.window = MagicMock()
        handler._manager = manager
        handler._ready = True  # ready

        with patch.object(gp_module, "_EVDEV_AVAILABLE", True), \
             patch.object(gp_module, "ecodes", ecodes_mock), \
             patch("backend.gamepad.QKeyEvent"), \
             patch("backend.gamepad.QCoreApplication"):
            from PySide6.QtCore import QEvent
            handler._inject(QEvent.Type.KeyPress, MagicMock())

        keys_mock.setGamepadInput.assert_called_once()
