"""Tests for NetworkMonitor (backend/network_monitor.py).

Covers:
  - online property has a value after construction
  - online is True when socket.create_connection succeeds
  - online is False when socket.create_connection raises OSError
  - onlineChanged signal is emitted when state transitions
  - onlineChanged signal is NOT emitted when state stays the same
  - refresh() triggers an immediate check
  - timer interval is 30 seconds
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.network_monitor import NetworkMonitor, _POLL_INTERVAL_MS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_monitor(socket_succeeds: bool) -> NetworkMonitor:
    """Create a NetworkMonitor with a mocked socket.create_connection."""
    side_effect = None if socket_succeeds else OSError("unreachable")
    with patch(
        "backend.network_monitor.socket.create_connection",
        side_effect=side_effect,
    ):
        monitor = NetworkMonitor()
    return monitor


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestNetworkMonitorConstruction:
    def test_online_property_has_value_after_construction(self) -> None:
        """online is a bool immediately after construction."""
        with patch("backend.network_monitor.socket.create_connection"):
            monitor = NetworkMonitor()
        assert isinstance(monitor.online, bool)

    def test_online_is_true_when_socket_succeeds(self) -> None:
        """online=True when the socket connection succeeds."""
        monitor = _make_monitor(socket_succeeds=True)
        assert monitor.online is True

    def test_online_is_false_when_socket_fails(self) -> None:
        """online=False when the socket connection raises OSError."""
        monitor = _make_monitor(socket_succeeds=False)
        assert monitor.online is False

    def test_timer_interval_is_30_seconds(self) -> None:
        """The internal QTimer fires every 30 000 ms."""
        with patch("backend.network_monitor.socket.create_connection"):
            monitor = NetworkMonitor()
        assert monitor._timer.interval() == _POLL_INTERVAL_MS
        assert _POLL_INTERVAL_MS == 30_000

    def test_timer_is_running_after_construction(self) -> None:
        """The internal QTimer is active after construction."""
        with patch("backend.network_monitor.socket.create_connection"):
            monitor = NetworkMonitor()
        assert monitor._timer.isActive()


# ---------------------------------------------------------------------------
# Signal emission
# ---------------------------------------------------------------------------


class TestNetworkMonitorSignals:
    def test_online_changed_emitted_on_state_transition(self) -> None:
        """onlineChanged is emitted when the online state changes."""
        # Start offline
        monitor = _make_monitor(socket_succeeds=False)
        assert monitor.online is False

        emitted: list[bool] = []
        monitor.onlineChanged.connect(lambda: emitted.append(True))

        # Simulate going online
        with patch(
            "backend.network_monitor.socket.create_connection",
        ):
            monitor._check()

        assert len(emitted) == 1
        assert monitor.online is True

    def test_online_changed_not_emitted_when_state_unchanged(self) -> None:
        """onlineChanged is NOT emitted when the state stays the same."""
        monitor = _make_monitor(socket_succeeds=True)
        assert monitor.online is True

        emitted: list[bool] = []
        monitor.onlineChanged.connect(lambda: emitted.append(True))

        # Check again — still online, no change
        with patch("backend.network_monitor.socket.create_connection"):
            monitor._check()

        assert len(emitted) == 0

    def test_online_changed_emitted_on_offline_transition(self) -> None:
        """onlineChanged is emitted when going from online to offline."""
        monitor = _make_monitor(socket_succeeds=True)
        assert monitor.online is True

        emitted: list[bool] = []
        monitor.onlineChanged.connect(lambda: emitted.append(True))

        with patch(
            "backend.network_monitor.socket.create_connection",
            side_effect=OSError("unreachable"),
        ):
            monitor._check()

        assert len(emitted) == 1
        assert monitor.online is False


# ---------------------------------------------------------------------------
# refresh() slot
# ---------------------------------------------------------------------------


class TestNetworkMonitorRefresh:
    def test_refresh_triggers_immediate_check(self) -> None:
        """refresh() calls _check() which updates the online state."""
        monitor = _make_monitor(socket_succeeds=False)
        assert monitor.online is False

        emitted: list[bool] = []
        monitor.onlineChanged.connect(lambda: emitted.append(True))

        with patch("backend.network_monitor.socket.create_connection"):
            monitor.refresh()

        assert monitor.online is True
        assert len(emitted) == 1

    def test_refresh_does_not_emit_when_state_unchanged(self) -> None:
        """refresh() does not emit onlineChanged when state is already correct."""
        monitor = _make_monitor(socket_succeeds=True)
        assert monitor.online is True

        emitted: list[bool] = []
        monitor.onlineChanged.connect(lambda: emitted.append(True))

        with patch("backend.network_monitor.socket.create_connection"):
            monitor.refresh()

        assert len(emitted) == 0


# ---------------------------------------------------------------------------
# _is_online static method
# ---------------------------------------------------------------------------


class TestNetworkMonitorIsOnline:
    def test_returns_true_on_successful_connection(self) -> None:
        """_is_online returns True when create_connection succeeds."""
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.network_monitor.socket.create_connection",
            return_value=mock_conn,
        ):
            result = NetworkMonitor._is_online()

        assert result is True

    def test_returns_false_on_os_error(self) -> None:
        """_is_online returns False when create_connection raises OSError."""
        with patch(
            "backend.network_monitor.socket.create_connection",
            side_effect=OSError("connection refused"),
        ):
            result = NetworkMonitor._is_online()

        assert result is False

    def test_returns_false_on_timeout(self) -> None:
        """_is_online returns False on a timeout (TimeoutError is a subclass of OSError)."""
        with patch(
            "backend.network_monitor.socket.create_connection",
            side_effect=TimeoutError("timed out"),
        ):
            result = NetworkMonitor._is_online()

        assert result is False
