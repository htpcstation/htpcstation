"""Tests for Task 001 — In-app Plex login: backend PIN slot.

Covers:
  - SettingsManager.startPlexPinLogin: emits plexLoginStatus("waiting:<CODE>")
  - SettingsManager.startPlexPinLogin: emits plexLoginStatus("error") on PIN failure
  - SettingsManager._poll_oauth_pin (pin mode): emits plexLoginStatus("success") and stores token
  - SettingsManager._poll_oauth_pin (pin mode): emits plexLoginStatus("timeout") after max polls
  - SettingsManager.cancelPlexPinLogin: emits plexLoginStatus("cancelled") and stops timer
  - SettingsManager.cancelPlexPinLogin: no-op when no active login (no crash)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import Config


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path):
    """Create a SettingsManager with a real Config and mock dependencies."""
    from backend.settings_manager import SettingsManager

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        config = Config()

    config.save = MagicMock()
    library = MagicMock()
    plex_library = MagicMock()
    manager = SettingsManager(config, library, plex_library)
    return manager, config


# ---------------------------------------------------------------------------
# TestStartPlexPinLogin
# ---------------------------------------------------------------------------


class TestStartPlexPinLogin:
    def test_emits_waiting_with_code(self, tmp_path: Path) -> None:
        """startPlexPinLogin emits plexLoginStatus("waiting:ABCD") immediately."""
        manager, _ = _make_manager(tmp_path)

        emitted: list[str] = []
        manager.plexLoginStatus.connect(lambda s: emitted.append(s))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(42, "ABCD")):
            manager.startPlexPinLogin()

        # Clean up timer
        if manager._oauth_timer is not None:
            manager._oauth_timer.stop()

        assert "waiting:ABCD" in emitted

    def test_emits_error_on_pin_failure(self, tmp_path: Path) -> None:
        """startPlexPinLogin emits plexLoginStatus("error") when create_pin returns None."""
        manager, _ = _make_manager(tmp_path)

        emitted: list[str] = []
        manager.plexLoginStatus.connect(lambda s: emitted.append(s))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=None):
            manager.startPlexPinLogin()

        assert emitted == ["error"]
        # No timer should be running
        assert manager._oauth_timer is None

    def test_poll_emits_success(self, tmp_path: Path) -> None:
        """_poll_oauth_pin emits plexTokenChanged and plexLoginStatus("success") on token."""
        manager, config = _make_manager(tmp_path)

        login_statuses: list[str] = []
        token_changed: list[bool] = []
        manager.plexLoginStatus.connect(lambda s: login_statuses.append(s))
        manager.plexTokenChanged.connect(lambda: token_changed.append(True))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "CODE")):
            manager.startPlexPinLogin()

        # Simulate a successful poll
        with patch("backend.settings_manager.PlexAccount.check_pin",
                   return_value="my_auth_token"):
            manager._poll_oauth_pin()

        assert config.plex_token == "my_auth_token"
        assert len(token_changed) == 1
        assert "success" in login_statuses
        # Timer should be stopped after success
        assert manager._oauth_timer is None

    def test_poll_emits_timeout(self, tmp_path: Path) -> None:
        """_poll_oauth_pin emits plexLoginStatus("timeout") after _OAUTH_MAX_POLLS polls."""
        from backend.settings_manager import _OAUTH_MAX_POLLS

        manager, _ = _make_manager(tmp_path)

        login_statuses: list[str] = []
        manager.plexLoginStatus.connect(lambda s: login_statuses.append(s))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(1, "CODE")):
            manager.startPlexPinLogin()

        # Exhaust all polls without a token
        with patch("backend.settings_manager.PlexAccount.check_pin", return_value=None):
            for _ in range(_OAUTH_MAX_POLLS + 1):
                manager._poll_oauth_pin()

        assert "timeout" in login_statuses
        assert manager._oauth_timer is None

    def test_cancel_emits_cancelled(self, tmp_path: Path) -> None:
        """cancelPlexPinLogin emits plexLoginStatus("cancelled") and stops the timer."""
        manager, _ = _make_manager(tmp_path)

        login_statuses: list[str] = []
        manager.plexLoginStatus.connect(lambda s: login_statuses.append(s))

        with patch("backend.settings_manager.PlexAccount.create_pin",
                   return_value=(42, "ABCD")):
            manager.startPlexPinLogin()

        # Timer should be running
        assert manager._oauth_timer is not None

        manager.cancelPlexPinLogin()

        assert "cancelled" in login_statuses
        assert manager._oauth_timer is None


# ---------------------------------------------------------------------------
# TestCancelPlexPinLogin
# ---------------------------------------------------------------------------


class TestPlexServerNameUserTitle:
    def test_setPlexServerId_stores_name(self, tmp_path: Path) -> None:
        """setPlexServerId(id, name) stores both and emits both signals."""
        manager, config = _make_manager(tmp_path)

        id_changed: list[bool] = []
        name_changed: list[bool] = []
        manager.plexServerIdChanged.connect(lambda: id_changed.append(True))
        manager.plexServerNameChanged.connect(lambda: name_changed.append(True))

        manager.setPlexServerId("srv1", "My Server")

        assert config.plex_server_id == "srv1"
        assert config.plex_server_name == "My Server"
        assert len(id_changed) == 1
        assert len(name_changed) == 1

    def test_setPlexUserId_stores_title(self, tmp_path: Path) -> None:
        """setPlexUserId(id, title) stores both and emits both signals."""
        manager, config = _make_manager(tmp_path)

        id_changed: list[bool] = []
        title_changed: list[bool] = []
        manager.plexUserIdChanged.connect(lambda: id_changed.append(True))
        manager.plexUserTitleChanged.connect(lambda: title_changed.append(True))

        manager.setPlexUserId(42, "Alice")

        assert config.plex_user_id == 42
        assert config.plex_user_title == "Alice"
        assert len(id_changed) == 1
        assert len(title_changed) == 1

    def test_plexServerName_property(self, tmp_path: Path) -> None:
        """plexServerName property reflects config value."""
        manager, config = _make_manager(tmp_path)
        manager.setPlexServerId("srv1", "Test Server")
        assert manager.plexServerName == "Test Server"

    def test_plexUserTitle_property(self, tmp_path: Path) -> None:
        """plexUserTitle property reflects config value."""
        manager, config = _make_manager(tmp_path)
        manager.setPlexUserId(10, "Bob")
        assert manager.plexUserTitle == "Bob"

    def test_setPlexServerId_without_name(self, tmp_path: Path) -> None:
        """setPlexServerId with only id defaults name to empty string."""
        manager, config = _make_manager(tmp_path)
        manager.setPlexServerId("srv1")
        assert config.plex_server_name == ""

    def test_setPlexUserId_without_title(self, tmp_path: Path) -> None:
        """setPlexUserId with only id defaults title to empty string."""
        manager, config = _make_manager(tmp_path)
        manager.setPlexUserId(10)
        assert config.plex_user_title == ""


class TestCancelPlexPinLogin:
    def test_cancel_no_op_when_not_running(self, tmp_path: Path) -> None:
        """cancelPlexPinLogin emits plexLoginStatus("cancelled") even with no active login."""
        manager, _ = _make_manager(tmp_path)

        login_statuses: list[str] = []
        manager.plexLoginStatus.connect(lambda s: login_statuses.append(s))

        # No active login — should not crash
        manager.cancelPlexPinLogin()

        assert login_statuses == ["cancelled"]
        assert manager._oauth_timer is None
