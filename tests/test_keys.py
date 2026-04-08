"""Tests for backend/keys.py — semantic key abstraction.

Covers the isContext1 / isContext2 key code changes introduced in task 009:
  - isContext1 now maps to Key_1 (standard) / Key_2 (alternate)
  - isContext2 now maps to Key_2 (standard) / Key_1 (alternate)
  - isMenu still maps to Key_F10 (unchanged)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# PySide6 may not be available in the test environment; skip gracefully.
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from backend.keys import Keys  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(key_code: int) -> MagicMock:
    """Return a mock QJSValue whose .property('key').toInt() returns key_code.

    The mock is spec'd to QJSValue so that isinstance(event, QJSValue) is True
    inside _key_code(), causing the property-based extraction path to be used.
    """
    from PySide6.QtQml import QJSValue

    mock_event = MagicMock(spec=QJSValue)
    mock_event.property.return_value.toInt.return_value = key_code
    return mock_event


# ---------------------------------------------------------------------------
# isContext1 — standard layout (Key_1)
# ---------------------------------------------------------------------------

class TestIsContext1Standard:
    def setup_method(self):
        self.keys = Keys()
        # default layout is "standard"

    def test_key_1_triggers_context1(self):
        event = _make_event(Qt.Key.Key_1.value)
        assert self.keys.isContext1(event) is True

    def test_key_2_does_not_trigger_context1(self):
        event = _make_event(Qt.Key.Key_2.value)
        assert self.keys.isContext1(event) is False

    def test_key_f1_no_longer_triggers_context1(self):
        """F1 must NOT trigger context1 after task-009 change."""
        event = _make_event(Qt.Key.Key_F1.value)
        assert self.keys.isContext1(event) is False

    def test_key_f2_does_not_trigger_context1(self):
        event = _make_event(Qt.Key.Key_F2.value)
        assert self.keys.isContext1(event) is False


# ---------------------------------------------------------------------------
# isContext1 — alternate layout (Key_2)
# ---------------------------------------------------------------------------

class TestIsContext1Alternate:
    def setup_method(self):
        self.keys = Keys()
        self.keys.setButtonLayout("alternate")

    def test_key_2_triggers_context1_in_alternate(self):
        event = _make_event(Qt.Key.Key_2.value)
        assert self.keys.isContext1(event) is True

    def test_key_1_does_not_trigger_context1_in_alternate(self):
        event = _make_event(Qt.Key.Key_1.value)
        assert self.keys.isContext1(event) is False

    def test_key_f2_no_longer_triggers_context1_in_alternate(self):
        """F2 must NOT trigger context1 in alternate layout after task-009."""
        event = _make_event(Qt.Key.Key_F2.value)
        assert self.keys.isContext1(event) is False


# ---------------------------------------------------------------------------
# isContext2 — standard layout (Key_2)
# ---------------------------------------------------------------------------

class TestIsContext2Standard:
    def setup_method(self):
        self.keys = Keys()

    def test_key_2_triggers_context2(self):
        event = _make_event(Qt.Key.Key_2.value)
        assert self.keys.isContext2(event) is True

    def test_key_1_does_not_trigger_context2(self):
        event = _make_event(Qt.Key.Key_1.value)
        assert self.keys.isContext2(event) is False

    def test_key_f2_no_longer_triggers_context2(self):
        """F2 must NOT trigger context2 after task-009 change."""
        event = _make_event(Qt.Key.Key_F2.value)
        assert self.keys.isContext2(event) is False

    def test_key_f1_does_not_trigger_context2(self):
        event = _make_event(Qt.Key.Key_F1.value)
        assert self.keys.isContext2(event) is False


# ---------------------------------------------------------------------------
# isContext2 — alternate layout (Key_1)
# ---------------------------------------------------------------------------

class TestIsContext2Alternate:
    def setup_method(self):
        self.keys = Keys()
        self.keys.setButtonLayout("alternate")

    def test_key_1_triggers_context2_in_alternate(self):
        event = _make_event(Qt.Key.Key_1.value)
        assert self.keys.isContext2(event) is True

    def test_key_2_does_not_trigger_context2_in_alternate(self):
        event = _make_event(Qt.Key.Key_2.value)
        assert self.keys.isContext2(event) is False

    def test_key_f1_no_longer_triggers_context2_in_alternate(self):
        """F1 must NOT trigger context2 in alternate layout after task-009."""
        event = _make_event(Qt.Key.Key_F1.value)
        assert self.keys.isContext2(event) is False


# ---------------------------------------------------------------------------
# isMenu — Key_F10 unchanged
# ---------------------------------------------------------------------------

class TestIsMenuUnchanged:
    def setup_method(self):
        self.keys = Keys()

    def test_key_f10_triggers_menu(self):
        event = _make_event(Qt.Key.Key_F10.value)
        assert self.keys.isMenu(event) is True

    def test_key_1_does_not_trigger_menu(self):
        event = _make_event(Qt.Key.Key_1.value)
        assert self.keys.isMenu(event) is False

    def test_key_2_does_not_trigger_menu(self):
        event = _make_event(Qt.Key.Key_2.value)
        assert self.keys.isMenu(event) is False
