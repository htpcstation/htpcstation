"""Semantic key abstraction for HTPC Station.

Exposes a ``keys`` context property to QML so that navigation code can test
against semantic actions (accept, cancel, etc.) rather than raw Qt key codes.

QML usage::

    Keys.onPressed: (event) => {
        if (keys.isAccept(event)) { /* launch */ }
        else if (keys.isCancel(event)) { /* go back */ }
    }

The ``event`` parameter from QML ``Keys.onPressed`` is a QML KeyEvent object.
When passed to a Python slot it arrives as a ``QJSValue``; we extract the
``key`` property (an int) to compare against the mapped Qt key codes.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot, Property, Qt
from PySide6.QtQml import QJSValue


def _key_code(event: QJSValue) -> int:
    """Extract the integer key code from a QML KeyEvent passed as QJSValue."""
    if isinstance(event, QJSValue):
        return int(event.property("key").toInt())
    # Fallback: if somehow a plain int arrives
    return int(event)


class Keys(QObject):
    """Semantic key helper exposed to QML as the ``keys`` context property.

    Also tracks whether the last input came from a gamepad or keyboard,
    exposed as the ``useGamepadLabels`` property. QML hint bars bind to
    this to show "A/B/X/Y" vs "Enter/Esc" labels.
    """

    useGamepadLabelsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._use_gamepad_labels: bool = True  # default to gamepad

    def _get_use_gamepad_labels(self) -> bool:
        return self._use_gamepad_labels

    useGamepadLabels = Property(bool, _get_use_gamepad_labels,
                                notify=useGamepadLabelsChanged)

    @Slot()
    def setGamepadInput(self) -> None:
        """Called by GamepadManager when a gamepad event is injected."""
        if not self._use_gamepad_labels:
            self._use_gamepad_labels = True
            self.useGamepadLabelsChanged.emit()

    @Slot()
    def setKeyboardInput(self) -> None:
        """Called when a real keyboard event is detected."""
        if self._use_gamepad_labels:
            self._use_gamepad_labels = False
            self.useGamepadLabelsChanged.emit()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isAccept(self, event: QJSValue) -> bool:
        """A button / Enter — confirm / launch."""
        return _key_code(event) == Qt.Key.Key_Return

    @Slot(QJSValue, result=bool)
    def isCancel(self, event: QJSValue) -> bool:
        """B button / Escape — cancel / go back."""
        return _key_code(event) == Qt.Key.Key_Escape

    # ------------------------------------------------------------------
    # Context actions
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isContext1(self, event: QJSValue) -> bool:
        """X button / F1 — context action 1."""
        return _key_code(event) == Qt.Key.Key_F1

    @Slot(QJSValue, result=bool)
    def isContext2(self, event: QJSValue) -> bool:
        """Y button / F2 — context action 2."""
        return _key_code(event) == Qt.Key.Key_F2

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isMenu(self, event: QJSValue) -> bool:
        """Start button / F10 — open menu / settings."""
        return _key_code(event) == Qt.Key.Key_F10

    # ------------------------------------------------------------------
    # Tab navigation
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isPrevTab(self, event: QJSValue) -> bool:
        """LB / PageUp — previous tab."""
        return _key_code(event) == Qt.Key.Key_PageUp

    @Slot(QJSValue, result=bool)
    def isNextTab(self, event: QJSValue) -> bool:
        """RB / PageDown — next tab."""
        return _key_code(event) == Qt.Key.Key_PageDown

    # ------------------------------------------------------------------
    # Page scroll
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isPageUp(self, event: QJSValue) -> bool:
        """LT / Home — scroll page up."""
        return _key_code(event) == Qt.Key.Key_Home

    @Slot(QJSValue, result=bool)
    def isPageDown(self, event: QJSValue) -> bool:
        """RT / End — scroll page down."""
        return _key_code(event) == Qt.Key.Key_End
