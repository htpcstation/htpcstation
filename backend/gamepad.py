"""Gamepad input manager for HTPC Station.

Detects evdev gamepads, translates D-pad/stick/button events into synthetic
QKeyEvents, and injects them into the active Qt window.  All QML navigation
code only sees keyboard events — it never touches gamepad input directly.

The button/axis → Qt.Key mapping is loaded from controller_mapping.py and
can be reconfigured at runtime via reloadMapping().
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
    Signal,
    Slot,
)
from PySide6.QtGui import QKeyEvent

from backend.controller_mapping import build_evdev_lookup, load_mapping

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

    def __init__(
        self,
        device: "InputDevice",
        manager: "GamepadManager",
        evdev_lookup: dict,
    ) -> None:
        super().__init__()
        self._device = device
        self._manager = manager
        self._evdev_lookup = evdev_lookup

        # Track which Qt keys are currently "pressed" by this device (refcount)
        self._pressed: dict[Qt.Key, int] = {}

        # Auto-repeat timers keyed by Qt key
        self._repeat_timers: dict[Qt.Key, QTimer] = {}

        # Analog stick state: current direction key (or None) per axis
        self._stick_x_key: Optional[Qt.Key] = None
        self._stick_y_key: Optional[Qt.Key] = None

        # D-pad axis state: axis code → currently pressed Qt.Key (or None)
        # Needed to release the previous direction when value returns to 0.
        self._dpad_axis_key: dict[int, Optional[Qt.Key]] = {}

        # Trigger state: axis code → currently pressed
        self._trigger_pressed: dict[int, bool] = {}

        # Combo detection: track which Qt keys are currently held
        self._buttons_held: set[Qt.Key] = set()
        self._combo_fired: bool = False

        # Axis info cache: axis code → (min, max)
        self._axis_info: dict[int, tuple[int, int]] = {}
        self._cache_axis_info()

        # Set to True after the first _on_readable call completes.
        # Prevents setGamepadInput() from firing on buffered events that are
        # queued from the moment the device fd is opened.
        self._ready: bool = False

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
        finally:
            self._ready = True  # mark ready after first read regardless of outcome

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
        if self._manager._raw_mode:
            if value in (0, 1):   # emit press AND release; skip auto-repeat (value=2)
                self._manager.rawInput.emit("button", code, value)
            return

        # While MPV is active it handles gamepad input via SDL — suppress Qt
        # injection to prevent double-handling (e.g. Start triggering both
        # MPV stop and the HTPC Station quit dialog).
        if self._manager._mpv_active:
            return

        qt_key = self._evdev_lookup.get((ecodes.EV_KEY, code, 1))  # type: ignore[union-attr]
        if qt_key is None:
            return

        # Track pressed state for combo detection
        if value == 1:
            self._buttons_held.add(qt_key)
        elif value == 0:
            self._buttons_held.discard(qt_key)

        # Start+Select combo detection
        if (Qt.Key.Key_F10 in self._buttons_held
                and Qt.Key.Key_F9 in self._buttons_held):
            if not self._combo_fired:
                self._combo_fired = True
                self._manager.startSelectCombo.emit()
            return  # suppress individual button actions while combo is active

        if self._combo_fired:
            # Reset combo once both are released
            if (Qt.Key.Key_F10 not in self._buttons_held
                    and Qt.Key.Key_F9 not in self._buttons_held):
                self._combo_fired = False
            return  # suppress until both released

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

        # In raw mode, emit ALL axis events so the mapping dialog can
        # discover which codes the controller uses.  Normalize the value
        # to -1/0/1 using the axis range so the mapping config stores
        # direction signs, not raw hardware values.
        if self._manager._mpv_active:
            return

        if self._manager._raw_mode:
            axis_min, axis_max = self._axis_info.get(code, (0, 0))
            if axis_min == axis_max:
                # Unknown range — emit raw value (hat axes report -1/0/1 natively)
                if value != 0:
                    self._manager.rawInput.emit("axis", code, value)
            else:
                center = (axis_min + axis_max) / 2.0
                half_range = (axis_max - axis_min) / 2.0
                threshold = half_range * 0.5  # 50% dead zone for direction detection
                offset = value - center
                if offset < -threshold:
                    self._manager.rawInput.emit("axis", code, -1)
                elif offset > threshold:
                    self._manager.rawInput.emit("axis", code, 1)
                # else: near center — don't emit (neutral position)
            return

        # Determine if this axis is a trigger (0-to-max) or a D-pad hat (-1/0/1)
        # by checking what's in the lookup.
        # Triggers: only (EV_ABS, code, 1) is in the lookup
        # D-pad hats: both (EV_ABS, code, -1) and (EV_ABS, code, 1) may be in lookup
        has_neg = (ecodes.EV_ABS, code, -1) in self._evdev_lookup  # type: ignore[union-attr]
        has_pos = (ecodes.EV_ABS, code, 1) in self._evdev_lookup  # type: ignore[union-attr]

        if not has_neg and not has_pos:
            # Axis not in mapping — fall through to analog stick handler
            # for ABS_X/ABS_Y (if not mapped as D-pad, they may be sticks)
            if code == ecodes.ABS_X:  # type: ignore[union-attr]
                self._handle_stick_axis(value, code, is_x=True)
            elif code == ecodes.ABS_Y:  # type: ignore[union-attr]
                self._handle_stick_axis(value, code, is_y=True)
            return

        if has_neg:
            # D-pad style axis.  Normalize the raw value to -1/0/1 using
            # the axis range (handles both hat axes that natively report
            # -1/0/1 and analog axes like ABS_X/Y that report 0-255).
            axis_min, axis_max = self._axis_info.get(code, (-1, 1))
            if axis_min == -1 and axis_max == 1:
                # Already -1/0/1 (hat axis) — use raw value
                normalized = value
            else:
                center = (axis_min + axis_max) / 2.0
                half_range = (axis_max - axis_min) / 2.0
                threshold = half_range * 0.5
                offset = value - center
                if offset < -threshold:
                    normalized = -1
                elif offset > threshold:
                    normalized = 1
                else:
                    normalized = 0
            self._handle_dpad_axis(code, normalized)
        else:
            # Trigger style axis: 0 to max, threshold-based
            self._handle_trigger(code, value)

    def _handle_dpad_axis(self, code: int, value: int) -> None:
        """D-pad hat axes: -1, 0, or +1.  Not called in raw mode."""
        if not _EVDEV_AVAILABLE:
            return

        current_key: Optional[Qt.Key] = self._dpad_axis_key.get(code)

        if value == 0:
            new_key: Optional[Qt.Key] = None
        else:
            sign = 1 if value > 0 else -1
            new_key = self._evdev_lookup.get((ecodes.EV_ABS, code, sign))  # type: ignore[union-attr]

        if current_key and current_key != new_key:
            self._release_key(current_key)
        if new_key and new_key != current_key:
            self._press_key(new_key)

        self._dpad_axis_key[code] = new_key

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
        """Analog triggers → key press when past threshold.  Not called in raw mode."""
        if not _EVDEV_AVAILABLE:
            return
        qt_key = self._evdev_lookup.get((ecodes.EV_ABS, code, 1))  # type: ignore[union-attr]
        if qt_key is None:
            return

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
        # Notify input source tracker that this is gamepad input.
        # Guard with _ready to skip buffered events from device open.
        if (event_type == QEvent.Type.KeyPress
                and self._manager.keys is not None
                and self._ready):
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

    def _release_all_keys(self) -> None:
        """Release all held keys and stop all auto-repeat timers."""
        for qt_key in list(self._pressed.keys()):
            if self._pressed.get(qt_key, 0) > 0:
                self._pressed[qt_key] = 1
                self._release_key(qt_key)
        # Also clear D-pad axis state so no direction is "stuck"
        self._dpad_axis_key.clear()
        # Clear trigger state
        self._trigger_pressed.clear()
        # Clear combo state
        self._buttons_held.clear()
        self._combo_fired = False

    def _cleanup(self) -> None:
        """Release all held keys, stop all timers, and close the device."""
        self._release_all_keys()
        self._notifier.setEnabled(False)
        self._notifier.activated.disconnect(self._on_readable)
        self._notifier.deleteLater()
        try:
            self._device.close()
        except Exception:
            pass

    def _update_lookup(self, evdev_lookup: dict) -> None:
        """Update the evdev lookup table (called by GamepadManager.reloadMapping)."""
        self._evdev_lookup = evdev_lookup


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

    # Emitted in raw mode: (event_type_str, code, value)
    # event_type_str is "button" or "axis"
    rawInput = Signal(str, int, int)

    # Emitted when Start+Select are pressed simultaneously.
    # Connected in main.py to kill the browser process.
    startSelectCombo = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.window: Optional[QObject] = None
        self.keys: Optional[QObject] = None  # Keys instance for input source tracking
        self._handlers: dict[str, _DeviceHandler] = {}  # path → handler
        self._warned_no_gamepad = False  # emit the "no gamepads" warning only once
        self._raw_mode: bool = False
        self._mpv_active: bool = False

        # Load mapping and build the unified lookup table
        self._evdev_lookup: dict = build_evdev_lookup(load_mapping())

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

    @Slot(bool)
    def setMpvActive(self, active: bool) -> None:
        """Suppress Qt key injection while MPV is playing.

        When MPV is active, it handles gamepad input via its own SDL layer.
        Injecting the same events into Qt causes double-handling (e.g. Start
        triggers both MPV stop and the HTPC Station quit dialog).
        On deactivation, releases all held keys so no stale state carries over.
        """
        self._mpv_active = active
        if not active:
            for handler in self._handlers.values():
                handler._release_all_keys()

    @Slot()
    def startRawMode(self) -> None:
        """Enter raw mode: events emit rawInput signal instead of injecting keys.

        Releases all currently pressed keys and stops all auto-repeat timers
        so no stale key events leak into the mapping dialog.
        """
        # Release all pressed keys and stop repeat timers in every handler
        for handler in self._handlers.values():
            handler._release_all_keys()
        self._raw_mode = True

        # Open SDL resolver for the first connected device
        if self._handlers:
            handler = next(iter(self._handlers.values()))
            device_name = getattr(handler._device, "name", "")
            caps = self.getDeviceCapabilities()
            button_codes = caps.get("buttons", [])
            axis_codes = caps.get("axes", [])
            from backend.sdl_resolver import resolver as _sdl_resolver
            from backend.controller_mapping import load_mapping
            _sdl_resolver.open(device_name, button_codes, axis_codes)
            # Seed axis→SDL records from the saved controller mapping.
            # This gives correct SDL records for triggers/sticks that the
            # GameController API heuristic may not resolve correctly.
            _sdl_resolver.seed_from_controller_mapping(load_mapping())

    @Slot()
    def stopRawMode(self) -> None:
        """Exit raw mode, resume normal key injection.

        Clears all pressed-key state so no stale presses carry over from
        buttons that were held during raw mode.
        """
        self._raw_mode = False
        # Clear pressed state so buttons held during raw mode don't
        # appear as "already pressed" and suppress their next real press.
        for handler in self._handlers.values():
            handler._release_all_keys()

        from backend.sdl_resolver import resolver as _sdl_resolver
        _sdl_resolver.close()

    @Slot()
    def reloadMapping(self) -> None:
        """Reload the controller mapping from disk and rebuild the lookup table.

        Call this after the mapping dialog saves a new config.
        """
        self._evdev_lookup = build_evdev_lookup(load_mapping())
        for handler in self._handlers.values():
            handler._update_lookup(self._evdev_lookup)

    @Slot(result="QVariant")
    def getDeviceCapabilities(self) -> dict:
        """Return the first connected gamepad's button and axis capabilities.

        Returns a dict with keys:
            ``buttons`` — sorted list of EV_KEY button codes
            ``axes``    — sorted list of EV_ABS axis codes
            ``name``    — device name string

        Returns an empty dict if no device is connected or evdev is unavailable.
        """
        if not _EVDEV_AVAILABLE or not self._handlers:
            return {}

        # Use the first connected device
        handler = next(iter(self._handlers.values()))
        device = handler._device

        try:
            caps = device.capabilities()
        except Exception as exc:
            log.warning("getDeviceCapabilities: failed to read capabilities: %s", exc)
            return {}

        buttons: list[int] = sorted(
            int(code)
            for code in caps.get(ecodes.EV_KEY, [])  # type: ignore[union-attr]
        )
        axes: list[int] = sorted(
            int(code)
            for code, _abs_info in caps.get(ecodes.EV_ABS, [])  # type: ignore[union-attr]
        )

        return {
            "buttons": buttons,
            "axes": axes,
            "name": getattr(device, "name", ""),
        }

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
                    self._handlers[path] = _DeviceHandler(device, self, self._evdev_lookup)
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
        handler = self._handlers.pop(path, None)
        if handler is not None:
            handler.deleteLater()
