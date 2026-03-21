"""Gamepad input manager for HTPC Station.

Detects evdev gamepads, translates D-pad/stick/button events into synthetic
QKeyEvents, and injects them into the active Qt window.  All QML navigation
code only sees keyboard events — it never touches gamepad input directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QSocketNotifier,
    QTimer,
    Qt,
)
from PySide6.QtGui import QKeyEvent

# ---------------------------------------------------------------------------
# Optional evdev import — Linux only, graceful fallback when absent
# ---------------------------------------------------------------------------

try:
    import evdev
    from evdev import InputDevice, ecodes

    _EVDEV_AVAILABLE = True
except ImportError:  # pragma: no cover
    _EVDEV_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Button → Qt key mapping (populated only when evdev is available)
# ---------------------------------------------------------------------------

_BUTTON_MAP: dict[int, Qt.Key] = {}
_TRIGGER_MAP: dict[int, Qt.Key] = {}
_DPAD_X_MAP: dict[int, Qt.Key] = {}
_DPAD_Y_MAP: dict[int, Qt.Key] = {}

if _EVDEV_AVAILABLE:
    _BUTTON_MAP = {
        ecodes.BTN_SOUTH: Qt.Key.Key_Escape,    # B — Cancel / back
        ecodes.BTN_EAST: Qt.Key.Key_Return,    # A — Accept
        ecodes.BTN_NORTH: Qt.Key.Key_F1,       # X — Context action 1
        ecodes.BTN_WEST: Qt.Key.Key_F2,        # Y — Context action 2
        ecodes.BTN_START: Qt.Key.Key_F10,      # Start — Menu
        ecodes.BTN_SELECT: Qt.Key.Key_F9,      # Select — Secondary menu
        ecodes.BTN_TL: Qt.Key.Key_PageUp,      # LB — Previous tab
        ecodes.BTN_TR: Qt.Key.Key_PageDown,    # RB — Next tab
    }

    # Trigger axes: value > threshold → key press
    _TRIGGER_MAP = {
        ecodes.ABS_Z: Qt.Key.Key_Home,   # LT — Page scroll up
        ecodes.ABS_RZ: Qt.Key.Key_End,   # RT — Page scroll down
    }

    # D-pad hat axes: value → key (negative / positive)
    _DPAD_X_MAP = {
        -1: Qt.Key.Key_Left,
        1: Qt.Key.Key_Right,
    }
    _DPAD_Y_MAP = {
        -1: Qt.Key.Key_Up,
        1: Qt.Key.Key_Down,
    }

# Analog stick dead zone: 30 % of the half-range
_STICK_DEAD_ZONE_RATIO = 0.30

# Trigger threshold: 25 % of full range (triggers go 0 → max)
_TRIGGER_THRESHOLD_RATIO = 0.25

# Auto-repeat timing (milliseconds)
_REPEAT_INITIAL_DELAY_MS = 500
_REPEAT_INTERVAL_MS = 80


# ---------------------------------------------------------------------------
# Per-device handler
# ---------------------------------------------------------------------------


class _DeviceHandler(QObject):
    """Reads events from a single evdev InputDevice and injects QKeyEvents."""

    def __init__(self, device: "InputDevice", manager: "GamepadManager") -> None:
        super().__init__()
        self._device = device
        self._manager = manager

        # Track which Qt keys are currently "pressed" by this device (refcount)
        self._pressed: dict[Qt.Key, int] = {}

        # Auto-repeat timers keyed by Qt key
        self._repeat_timers: dict[Qt.Key, QTimer] = {}

        # Analog stick state: current direction key (or None) per axis
        self._stick_x_key: Optional[Qt.Key] = None
        self._stick_y_key: Optional[Qt.Key] = None
        self._dpad_x_key: Optional[Qt.Key] = None
        self._dpad_y_key: Optional[Qt.Key] = None

        # Trigger state: axis code → currently pressed
        self._trigger_pressed: dict[int, bool] = {}

        # Axis info cache: axis code → (min, max)
        self._axis_info: dict[int, tuple[int, int]] = {}
        self._cache_axis_info()

        # Socket notifier to wake up when the device fd has data
        self._notifier = QSocketNotifier(
            device.fd, QSocketNotifier.Type.Read, self
        )
        self._notifier.activated.connect(self._on_readable)

        log.info("Gamepad connected: %s (%s)", device.name, device.path)

    def _cache_axis_info(self) -> None:
        """Cache AbsInfo (min/max) for axes we care about."""
        if not _EVDEV_AVAILABLE:
            return
        try:
            caps = self._device.capabilities()
            abs_caps = caps.get(ecodes.EV_ABS, [])  # type: ignore[union-attr]
            for axis, abs_info in abs_caps:
                self._axis_info[axis] = (abs_info.min, abs_info.max)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event reading
    # ------------------------------------------------------------------

    def _on_readable(self) -> None:
        """Called by QSocketNotifier when the device fd has data."""
        try:
            for event in self._device.read():
                self._handle_event(event)
        except BlockingIOError:
            return  # No events ready — not an error
        except OSError:
            # Device disconnected
            log.info("Gamepad disconnected: %s", self._device.path)
            self._cleanup()
            self._manager._remove_device(self._device.path)

    def _handle_event(self, event: object) -> None:
        if not _EVDEV_AVAILABLE:
            return
        ev_type = getattr(event, "type", None)
        ev_code = getattr(event, "code", None)
        ev_value = getattr(event, "value", None)
        if ev_type == ecodes.EV_KEY:  # type: ignore[union-attr]
            self._handle_button(ev_code, ev_value)
        elif ev_type == ecodes.EV_ABS:  # type: ignore[union-attr]
            self._handle_abs(ev_code, ev_value)

    # ------------------------------------------------------------------
    # Button events
    # ------------------------------------------------------------------

    def _handle_button(self, code: int, value: int) -> None:
        """value: 1 = press, 0 = release, 2 = kernel auto-repeat (ignored)."""
        qt_key = _BUTTON_MAP.get(code)
        if qt_key is None:
            return
        if value == 1:
            self._press_key(qt_key)
        elif value == 0:
            self._release_key(qt_key)

    # ------------------------------------------------------------------
    # Absolute axis events (D-pad, sticks, triggers)
    # ------------------------------------------------------------------

    def _handle_abs(self, code: int, value: int) -> None:
        if not _EVDEV_AVAILABLE:
            return
        if code == ecodes.ABS_HAT0X:  # type: ignore[union-attr]
            self._handle_dpad_axis(value, _DPAD_X_MAP, "_dpad_x_key")
        elif code == ecodes.ABS_HAT0Y:  # type: ignore[union-attr]
            self._handle_dpad_axis(value, _DPAD_Y_MAP, "_dpad_y_key")
        elif code == ecodes.ABS_X:  # type: ignore[union-attr]
            self._handle_stick_axis(value, code, is_x=True)
        elif code == ecodes.ABS_Y:  # type: ignore[union-attr]
            self._handle_stick_axis(value, code, is_y=True)
        elif code in _TRIGGER_MAP:
            self._handle_trigger(code, value)

    def _handle_dpad_axis(
        self,
        value: int,
        key_map: dict[int, Qt.Key],
        state_attr: str,
    ) -> None:
        """D-pad hat axes: -1, 0, or +1."""
        current_key: Optional[Qt.Key] = getattr(self, state_attr, None)
        new_key: Optional[Qt.Key] = key_map.get(value)

        if current_key and current_key != new_key:
            self._release_key(current_key)
        if new_key and new_key != current_key:
            self._press_key(new_key)

        setattr(self, state_attr, new_key)

    def _handle_stick_axis(
        self,
        value: int,
        code: int,
        is_x: bool = False,
        is_y: bool = False,
    ) -> None:
        """Left analog stick → navigation keys with dead-zone."""
        axis_min, axis_max = self._axis_info.get(code, (-32768, 32767))
        center = (axis_min + axis_max) / 2.0
        half_range = (axis_max - axis_min) / 2.0
        dead_zone = half_range * _STICK_DEAD_ZONE_RATIO

        offset = value - center

        if is_x:
            neg_key = Qt.Key.Key_Left
            pos_key = Qt.Key.Key_Right
            current_attr = "_stick_x_key"
        else:
            neg_key = Qt.Key.Key_Up
            pos_key = Qt.Key.Key_Down
            current_attr = "_stick_y_key"

        current_key: Optional[Qt.Key] = getattr(self, current_attr)

        if offset < -dead_zone:
            new_key: Optional[Qt.Key] = neg_key
        elif offset > dead_zone:
            new_key = pos_key
        else:
            new_key = None

        if current_key and current_key != new_key:
            self._release_key(current_key)
        if new_key and new_key != current_key:
            self._press_key(new_key)

        setattr(self, current_attr, new_key)

    def _handle_trigger(self, code: int, value: int) -> None:
        """Analog triggers (ABS_Z / ABS_RZ) → key press when past threshold."""
        qt_key = _TRIGGER_MAP[code]
        axis_min, axis_max = self._axis_info.get(code, (0, 255))
        threshold = axis_min + (axis_max - axis_min) * _TRIGGER_THRESHOLD_RATIO

        currently_pressed = self._trigger_pressed.get(code, False)
        should_press = value > threshold

        if should_press and not currently_pressed:
            self._trigger_pressed[code] = True
            self._press_key(qt_key)
        elif not should_press and currently_pressed:
            self._trigger_pressed[code] = False
            self._release_key(qt_key)

    # ------------------------------------------------------------------
    # Key injection helpers
    # ------------------------------------------------------------------

    def _press_key(self, qt_key: Qt.Key) -> None:
        count = self._pressed.get(qt_key, 0)
        self._pressed[qt_key] = count + 1
        if count == 0:  # first press
            self._inject(QEvent.Type.KeyPress, qt_key)
            self._start_repeat(qt_key)

    def _release_key(self, qt_key: Qt.Key) -> None:
        count = self._pressed.get(qt_key, 0)
        if count <= 0:
            return
        self._pressed[qt_key] = count - 1
        if count == 1:  # last release
            self._stop_repeat(qt_key)
            self._inject(QEvent.Type.KeyRelease, qt_key)

    def _inject(self, event_type: QEvent.Type, qt_key: Qt.Key) -> None:
        window = self._manager.window
        if window is None:
            return
        # Notify input source tracker that this is gamepad input
        if event_type == QEvent.Type.KeyPress and self._manager.keys is not None:
            self._manager.keys.setGamepadInput()
        event = QKeyEvent(event_type, qt_key, Qt.KeyboardModifier.NoModifier)
        QCoreApplication.sendEvent(window, event)

    # ------------------------------------------------------------------
    # Auto-repeat
    # ------------------------------------------------------------------

    def _start_repeat(self, qt_key: Qt.Key) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_repeat_initial(qt_key))
        timer.start(_REPEAT_INITIAL_DELAY_MS)
        self._repeat_timers[qt_key] = timer

    def _on_repeat_initial(self, qt_key: Qt.Key) -> None:
        if not self._pressed.get(qt_key, 0):
            return
        self._inject(QEvent.Type.KeyPress, qt_key)
        # Clean up the single-shot timer before replacing
        old_timer = self._repeat_timers.pop(qt_key, None)
        if old_timer is not None:
            old_timer.stop()
            old_timer.deleteLater()
        # Switch to interval timer
        timer = QTimer(self)
        timer.timeout.connect(lambda: self._on_repeat_tick(qt_key))
        timer.start(_REPEAT_INTERVAL_MS)
        self._repeat_timers[qt_key] = timer

    def _on_repeat_tick(self, qt_key: Qt.Key) -> None:
        if not self._pressed.get(qt_key, 0):
            self._stop_repeat(qt_key)
            return
        self._inject(QEvent.Type.KeyPress, qt_key)

    def _stop_repeat(self, qt_key: Qt.Key) -> None:
        timer = self._repeat_timers.pop(qt_key, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """Release all held keys and stop all timers."""
        for qt_key in list(self._pressed.keys()):
            if self._pressed.get(qt_key, 0) > 0:
                # Force refcount to 1 so _release_key emits KeyRelease
                self._pressed[qt_key] = 1
                self._release_key(qt_key)
        self._notifier.setEnabled(False)
        try:
            self._device.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GamepadManager — public API
# ---------------------------------------------------------------------------


class GamepadManager(QObject):
    """Manages gamepad detection and input injection for HTPC Station.

    Usage::

        manager = GamepadManager(app)
        manager.window = engine.rootObjects()[0]
        manager.start()
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.window: Optional[QObject] = None
        self.keys: Optional[QObject] = None  # Keys instance for input source tracking
        self._handlers: dict[str, _DeviceHandler] = {}  # path → handler
        self._warned_no_gamepad = False  # emit the "no gamepads" warning only once

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._scan_devices)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin scanning for gamepads and start reading input."""
        if not _EVDEV_AVAILABLE:
            log.warning(
                "evdev is not available — gamepad support disabled. "
                "Install it with: pip install evdev"
            )
            return
        self._scan_devices()
        self._poll_timer.start()

    def stop(self) -> None:
        """Stop all input reading and clean up."""
        self._poll_timer.stop()
        for handler in list(self._handlers.values()):
            handler._cleanup()
        self._handlers.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan_devices(self) -> None:
        """Detect newly connected gamepads."""
        if not _EVDEV_AVAILABLE:
            return

        try:
            device_paths = evdev.list_devices()  # type: ignore[union-attr]
        except Exception as exc:
            log.debug("evdev.list_devices() failed: %s", exc)
            return

        for path in device_paths:
            if path in self._handlers:
                continue
            try:
                device = InputDevice(path)  # type: ignore[misc]
                caps = device.capabilities()
                # A gamepad must have both absolute axes and buttons
                if ecodes.EV_ABS in caps and ecodes.EV_KEY in caps:  # type: ignore[union-attr]
                    self._handlers[path] = _DeviceHandler(device, self)
                else:
                    device.close()
            except (PermissionError, OSError) as exc:
                log.debug("Cannot open %s: %s", path, exc)

        if not self._handlers and not self._warned_no_gamepad:
            self._warned_no_gamepad = True
            log.warning(
                "No gamepads found. Make sure you are in the 'input' group "
                "or have read access to /dev/input/event* devices."
            )

    def _remove_device(self, path: str) -> None:
        """Called by a _DeviceHandler when its device disconnects."""
        self._handlers.pop(path, None)
