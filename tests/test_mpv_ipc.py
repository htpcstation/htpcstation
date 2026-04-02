"""Tests for MpvIpc (Task 001 — MPV IPC client).

Covers:
  - is_available() returns False when socket file absent
  - get_track_list() returns [] when socket absent
  - get_track_list() parses track list correctly (mock socket)
  - set_subtitle_track(0) sends set_property sid no
  - set_subtitle_track(3) sends set_property sid 3
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_false_when_socket_absent(self, tmp_path: Path) -> None:
        """is_available() returns False when the socket file does not exist."""
        from backend.mpv_ipc import MpvIpc

        nonexistent = str(tmp_path / "mpv.sock")
        ipc = MpvIpc(socket_path=nonexistent)
        assert ipc.is_available() is False

    def test_returns_true_when_socket_present(self, tmp_path: Path) -> None:
        """is_available() returns True when the socket file exists."""
        from backend.mpv_ipc import MpvIpc

        sock_path = tmp_path / "mpv.sock"
        sock_path.touch()
        ipc = MpvIpc(socket_path=str(sock_path))
        assert ipc.is_available() is True


# ---------------------------------------------------------------------------
# get_track_list()
# ---------------------------------------------------------------------------


class TestGetTrackList:
    def test_returns_empty_list_when_socket_absent(self, tmp_path: Path) -> None:
        """get_track_list() returns [] when the socket file does not exist."""
        from backend.mpv_ipc import MpvIpc

        nonexistent = str(tmp_path / "mpv.sock")
        ipc = MpvIpc(socket_path=nonexistent)
        result = ipc.get_track_list()
        assert result == []

    def test_parses_track_list_correctly(self, tmp_path: Path) -> None:
        """get_track_list() returns the parsed track list from MPV."""
        from backend.mpv_ipc import MpvIpc

        track_list = [
            {"id": 1, "type": "video", "selected": True},
            {"id": 2, "type": "audio", "selected": True, "lang": "eng"},
            {"id": 3, "type": "sub", "selected": False, "lang": "eng", "title": "English", "external": False},
            {"id": 4, "type": "sub", "selected": True, "lang": "fre", "title": "French", "external": True},
        ]
        response = json.dumps({"error": "success", "data": track_list}).encode() + b"\n"

        mock_sock = MagicMock()
        mock_sock.__enter__ = lambda s: s
        mock_sock.__exit__ = MagicMock(return_value=False)
        mock_sock.recv.side_effect = [response, b""]

        sock_path = str(tmp_path / "mpv.sock")
        ipc = MpvIpc(socket_path=sock_path)

        with patch("socket.socket", return_value=mock_sock):
            result = ipc.get_track_list()

        assert result == track_list

    def test_returns_empty_list_on_connection_error(self, tmp_path: Path) -> None:
        """get_track_list() returns [] when the socket connection fails."""
        from backend.mpv_ipc import MpvIpc

        sock_path = str(tmp_path / "mpv.sock")
        ipc = MpvIpc(socket_path=sock_path)

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = lambda s: s
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_socket_cls.return_value = mock_sock

            result = ipc.get_track_list()

        assert result == []


# ---------------------------------------------------------------------------
# set_subtitle_track()
# ---------------------------------------------------------------------------


class TestSetSubtitleTrack:
    def _capture_sent_command(self, tmp_path: Path, track_id: int) -> dict:
        """Helper: call set_subtitle_track and return the parsed JSON command sent."""
        from backend.mpv_ipc import MpvIpc

        sent_data = []

        mock_sock = MagicMock()
        mock_sock.__enter__ = lambda s: s
        mock_sock.__exit__ = MagicMock(return_value=False)

        def capture_sendall(data: bytes) -> None:
            sent_data.append(data)

        mock_sock.sendall.side_effect = capture_sendall
        # Return a success response
        response = json.dumps({"error": "success", "data": None}).encode() + b"\n"
        mock_sock.recv.side_effect = [response, b""]

        sock_path = str(tmp_path / "mpv.sock")
        ipc = MpvIpc(socket_path=sock_path)

        with patch("socket.socket", return_value=mock_sock):
            ipc.set_subtitle_track(track_id)

        assert sent_data, "No data was sent to the socket"
        return json.loads(sent_data[0].decode().strip())

    def test_set_subtitle_track_zero_sends_sid_no(self, tmp_path: Path) -> None:
        """set_subtitle_track(0) sends set_property sid no."""
        cmd = self._capture_sent_command(tmp_path, 0)
        assert cmd["command"] == ["set_property", "sid", "no"]

    def test_set_subtitle_track_nonzero_sends_sid_id(self, tmp_path: Path) -> None:
        """set_subtitle_track(3) sends set_property sid 3."""
        cmd = self._capture_sent_command(tmp_path, 3)
        assert cmd["command"] == ["set_property", "sid", 3]
