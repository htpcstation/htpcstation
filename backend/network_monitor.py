"""Network connectivity monitor for HTPC Station.

Periodically checks whether the device has internet access by attempting a
TCP connection to Cloudflare's public DNS resolver (1.1.1.1:53).  The result
is exposed to QML as the ``online`` Q_PROPERTY.
"""

from __future__ import annotations

import logging
import socket
from typing import Optional

from PySide6.QtCore import (
    Property,
    QObject,
    QTimer,
    Signal,
    Slot,
)

logger = logging.getLogger(__name__)

_CHECK_HOST = "1.1.1.1"
_CHECK_PORT = 53
_CHECK_TIMEOUT_S = 3
_POLL_INTERVAL_MS = 30_000  # 30 seconds


class NetworkMonitor(QObject):
    """Monitors internet connectivity and exposes the result to QML.

    Checks connectivity by opening a TCP socket to ``1.1.1.1:53`` (Cloudflare
    DNS).  The check is lightweight — no DNS resolution, no HTTP — and runs
    every 30 seconds via a ``QTimer``.

    The ``online`` property is updated whenever the connectivity state changes.
    Call ``refresh()`` to trigger an immediate re-check.
    """

    onlineChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._online: bool = False

        # Perform an immediate check on construction so the UI has a value
        # before the first timer tick.
        self._check()

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._check)
        self._timer.start()

    # ------------------------------------------------------------------
    # Property getter
    # ------------------------------------------------------------------

    def _get_online(self) -> bool:
        return self._online

    online = Property(bool, fget=_get_online, notify=onlineChanged)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Trigger an immediate connectivity check."""
        self._check()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check(self) -> None:
        """Check connectivity and update ``_online`` if the state changed."""
        new_state = self._is_online()
        if new_state != self._online:
            self._online = new_state
            logger.debug("NetworkMonitor: online=%s", self._online)
            self.onlineChanged.emit()

    @staticmethod
    def _is_online() -> bool:
        """Return True if a TCP connection to 1.1.1.1:53 succeeds."""
        try:
            with socket.create_connection(
                (_CHECK_HOST, _CHECK_PORT), timeout=_CHECK_TIMEOUT_S
            ):
                return True
        except OSError:
            return False
