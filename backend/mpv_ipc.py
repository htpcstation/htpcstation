"""MPV IPC client for HTPC Station.

Communicates with a running MPV process via its Unix socket
(--input-ipc-server). All methods are safe to call from the main thread
since socket operations are fast on a local socket.
"""

import json
import logging
import socket
from typing import Any

from backend.mpv_launcher import MPV_IPC_SOCKET

logger = logging.getLogger(__name__)


class MpvIpc:
    """Thin client for MPV's JSON IPC protocol."""

    def __init__(self, socket_path: str = MPV_IPC_SOCKET) -> None:
        self._socket_path = socket_path

    def is_available(self) -> bool:
        """Return True if the MPV IPC socket exists and is connectable."""
        import os
        return os.path.exists(self._socket_path)

    def command(self, *args: Any) -> Any:
        """Send a command and return the result value, or None on error."""
        try:
            msg = json.dumps({"command": list(args)}) + "\n"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(self._socket_path)
                s.sendall(msg.encode())
                # Read response (may be multiple lines; we want the first)
                data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
            line = data.split(b"\n")[0]
            resp = json.loads(line)
            if resp.get("error") == "success":
                return resp.get("data")
            logger.warning("MpvIpc.command %s: error=%s", args, resp.get("error"))
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("MpvIpc.command %s: %s", args, exc)
            return None

    def get_track_list(self) -> list[dict]:
        """Return the full track list from MPV.

        Each track dict has at minimum: id (int), type (str), selected (bool).
        Subtitle tracks also have: lang, title, external (bool).
        Returns [] if MPV is not running or the call fails.
        """
        result = self.command("get_property", "track-list")
        if not isinstance(result, list):
            return []
        return result

    def set_subtitle_track(self, track_id: int) -> None:
        """Select a subtitle track by its MPV track ID. Use 0 to disable."""
        if track_id == 0:
            self.command("set_property", "sid", "no")
        else:
            self.command("set_property", "sid", track_id)

    def set_audio_track(self, track_id: int) -> None:
        """Select an audio track by its MPV track ID."""
        self.command("set_property", "aid", track_id)
