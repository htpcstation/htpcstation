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

    The ``buttonLayout`` property controls whether face button labels
    follow the standard convention (A=south, B=east) or alternate
    convention (A=east, B=south).  This only affects the display labels,
    not the semantic mapping (accept is always east, cancel is always south).
    """

    useGamepadLabelsChanged = Signal()
    buttonLayoutChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._use_gamepad_labels: bool = True  # default to gamepad
        self._button_layout: str = "standard"  # "standard" or "alternate"

    def _get_use_gamepad_labels(self) -> bool:
        return self._use_gamepad_labels

    useGamepadLabels = Property(bool, _get_use_gamepad_labels,
                                notify=useGamepadLabelsChanged)

    # -- Button layout (standard / alternate) -----------------------------

    def _get_button_layout(self) -> str:
        return self._button_layout

    buttonLayout = Property(str, _get_button_layout,
                            notify=buttonLayoutChanged)

    @Slot(str)
    def setButtonLayout(self, layout: str) -> None:
        """Set the button layout to 'standard' or 'alternate'."""
        if layout not in ("standard", "alternate"):
            return
        if layout != self._button_layout:
            self._button_layout = layout
            self.buttonLayoutChanged.emit()

    # -- Face button labels -----------------------------------------------
    # Standard:  A=east, B=south, X=north, Y=west  (accept=A, cancel=B)
    # Alternate: A=south, B=east, X=west, Y=north  (accept=B, cancel=A)
    # Our semantic mapping: accept=east, cancel=south, context1=north, context2=west

    def _get_accept_label(self) -> str:
        # accept = east physical button
        return "A" if self._button_layout == "standard" else "B"

    def _get_cancel_label(self) -> str:
        # cancel = south physical button
        return "B" if self._button_layout == "standard" else "A"

    def _get_context1_label(self) -> str:
        # context1 = north physical button
        return "X" if self._button_layout == "standard" else "Y"

    def _get_context2_label(self) -> str:
        # context2 = west physical button
        return "Y" if self._button_layout == "standard" else "X"

    acceptLabel = Property(str, _get_accept_label, notify=buttonLayoutChanged)
    cancelLabel = Property(str, _get_cancel_label, notify=buttonLayoutChanged)
    context1Label = Property(str, _get_context1_label, notify=buttonLayoutChanged)
    context2Label = Property(str, _get_context2_label, notify=buttonLayoutChanged)

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
        """Accept action — east button (standard) or south button (alternate)."""
        code = _key_code(event)
        if self._button_layout == "alternate":
            return code == Qt.Key.Key_Escape  # south button
        return code == Qt.Key.Key_Return  # east button

    @Slot(QJSValue, result=bool)
    def isCancel(self, event: QJSValue) -> bool:
        """Cancel action — south button (standard) or east button (alternate)."""
        code = _key_code(event)
        if self._button_layout == "alternate":
            return code == Qt.Key.Key_Return  # east button
        return code == Qt.Key.Key_Escape  # south button

    # ------------------------------------------------------------------
    # Context actions
    # ------------------------------------------------------------------

    @Slot(QJSValue, result=bool)
    def isContext1(self, event: QJSValue) -> bool:
        """Context action 1 — north button (standard) or west button (alternate)."""
        code = _key_code(event)
        if self._button_layout == "alternate":
            return code == Qt.Key.Key_F2  # west button
        return code == Qt.Key.Key_F1  # north button

    @Slot(QJSValue, result=bool)
    def isContext2(self, event: QJSValue) -> bool:
        """Context action 2 — west button (standard) or north button (alternate)."""
        code = _key_code(event)
        if self._button_layout == "alternate":
            return code == Qt.Key.Key_F1  # north button
        return code == Qt.Key.Key_F2  # west button

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
