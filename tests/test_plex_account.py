"""Tests for Task 001 — PlexAccount client.

Covers:
  - PlexAccount: correct headers set on session (token, client identifier, product)
  - PlexAccount.get_resources: successful response, filters to servers only
  - PlexAccount.get_resources: error handling (connection error, timeout, HTTP error)
  - PlexAccount.get_home_users: successful XML response parsing
  - PlexAccount.get_home_users: error handling
  - PlexAccount.switch_user: extracts authenticationToken from XML response
  - PlexAccount.switch_user: returns None on failure
  - PlexAccount.test_connection: returns True on success, False on failure
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests as req


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_account(token: str = "mytoken"):
    """Create a PlexAccount with a mocked requests.Session."""
    from backend.plex_account import PlexAccount

    with patch("backend.plex_account.requests.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        account = PlexAccount(token)
    # Replace the session on the already-created account so we can control it
    account._session = mock_session
    return account, mock_session


# ---------------------------------------------------------------------------
# __init__ — headers
# ---------------------------------------------------------------------------


class TestPlexAccountHeaders:
    def test_headers_set_on_session(self) -> None:
        from backend.plex_account import PlexAccount

        with patch("backend.plex_account.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            PlexAccount("tok123")

            mock_session.headers.update.assert_called_once_with(
                {
                    "X-Plex-Token": "tok123",
                    "Accept": "application/json",
                    "X-Plex-Client-Identifier": "htpcstation",
                    "X-Plex-Product": "HTPC Station",
                }
            )

    def test_token_stored(self) -> None:
        from backend.plex_account import PlexAccount

        with patch("backend.plex_account.requests.Session"):
            account = PlexAccount("secret_token")

        assert account._token == "secret_token"


# ---------------------------------------------------------------------------
# get_resources
# ---------------------------------------------------------------------------


class TestGetResources:
    def test_returns_server_resources_only(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "name": "My Plex Server",
                "clientIdentifier": "abc123",
                "provides": "server",
                "owned": True,
                "connections": [{"uri": "https://1-2-3-4.abc123.plex.direct:32400"}],
            },
            {
                "name": "Plex Web",
                "clientIdentifier": "web001",
                "provides": "client",
                "owned": False,
                "connections": [],
            },
            {
                "name": "Shared Server",
                "clientIdentifier": "xyz789",
                "provides": "server,client",
                "owned": False,
                "connections": [],
            },
        ]
        mock_session.get.return_value = mock_response

        result = account.get_resources()

        assert len(result) == 2
        identifiers = {r["clientIdentifier"] for r in result}
        assert identifiers == {"abc123", "xyz789"}

    def test_filters_out_non_server_resources(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "Player", "clientIdentifier": "p1", "provides": "player", "owned": True, "connections": []},
            {"name": "Client", "clientIdentifier": "c1", "provides": "client", "owned": True, "connections": []},
        ]
        mock_session.get.return_value = mock_response

        result = account.get_resources()

        assert result == []

    def test_calls_correct_url_with_https_param(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_session.get.return_value = mock_response

        account.get_resources()

        mock_session.get.assert_called_once()
        call_url = mock_session.get.call_args[0][0]
        assert call_url == "https://plex.tv/api/v2/resources"
        call_params = mock_session.get.call_args[1].get("params", {})
        assert call_params.get("includeHttps") == 1

    def test_returns_empty_list_on_connection_error(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

        result = account.get_resources()

        assert result == []

    def test_returns_empty_list_on_timeout(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.Timeout()

        result = account.get_resources()

        assert result == []

    def test_returns_empty_list_on_http_error(self) -> None:
        account, mock_session = _make_account()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("401")
        mock_session.get.return_value = mock_response

        result = account.get_resources()

        assert result == []

    def test_resource_fields_preserved(self) -> None:
        account, mock_session = _make_account()

        resource = {
            "name": "Home Server",
            "clientIdentifier": "home001",
            "provides": "server",
            "owned": True,
            "connections": [
                {"uri": "http://192.168.1.10:32400", "local": True, "relay": False, "protocol": "http"},
                {"uri": "https://1-2-3-4.home001.plex.direct:32400", "local": False, "relay": False, "protocol": "https"},
            ],
        }
        mock_response = MagicMock()
        mock_response.json.return_value = [resource]
        mock_session.get.return_value = mock_response

        result = account.get_resources()

        assert len(result) == 1
        assert result[0] == resource


# ---------------------------------------------------------------------------
# get_home_users
# ---------------------------------------------------------------------------


class TestGetHomeUsers:
    def test_returns_user_list_from_xml(self) -> None:
        account, mock_session = _make_account()

        xml_text = (
            '<MediaContainer>'
            '<User id="1" title="Admin" username="admin@example.com" admin="1" restricted="0" protected="0" thumb=""/>'
            '<User id="2" title="Kid" username="" admin="0" restricted="1" protected="1" thumb=""/>'
            '</MediaContainer>'
        )
        mock_response = MagicMock()
        mock_response.text = xml_text
        mock_session.get.return_value = mock_response

        result = account.get_home_users()

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["title"] == "Admin"
        assert result[0]["admin"] is True
        assert result[0]["restricted"] is False
        assert result[1]["id"] == 2
        assert result[1]["restricted"] is True
        assert result[1]["protected"] is True

    def test_returns_empty_list_when_no_users_in_xml(self) -> None:
        """Handle XML response with no User elements."""
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.text = "<MediaContainer></MediaContainer>"
        mock_session.get.return_value = mock_response

        result = account.get_home_users()

        assert result == []

    def test_calls_correct_url(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.text = "<MediaContainer></MediaContainer>"
        mock_session.get.return_value = mock_response

        account.get_home_users()

        call_url = mock_session.get.call_args[0][0]
        assert call_url == "https://plex.tv/api/home/users"

    def test_returns_empty_list_on_connection_error(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

        result = account.get_home_users()

        assert result == []

    def test_returns_empty_list_on_timeout(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.Timeout()

        result = account.get_home_users()

        assert result == []

    def test_returns_empty_list_on_http_error(self) -> None:
        account, mock_session = _make_account()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("403")
        mock_session.get.return_value = mock_response

        result = account.get_home_users()

        assert result == []

    def test_user_fields_parsed_correctly(self) -> None:
        account, mock_session = _make_account()

        xml_text = (
            '<MediaContainer>'
            '<User id="42" title="Jane" username="jane@example.com" admin="0"'
            ' restricted="0" protected="1" thumb="https://plex.tv/users/42/avatar"/>'
            '</MediaContainer>'
        )
        mock_response = MagicMock()
        mock_response.text = xml_text
        mock_session.get.return_value = mock_response

        result = account.get_home_users()

        assert len(result) == 1
        assert result[0] == {
            "id": 42,
            "title": "Jane",
            "username": "jane@example.com",
            "admin": False,
            "restricted": False,
            "protected": True,
            "thumb": "https://plex.tv/users/42/avatar",
        }


# ---------------------------------------------------------------------------
# switch_user
# ---------------------------------------------------------------------------


class TestSwitchUser:
    def test_returns_authentication_token_on_success(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.text = '<User id="2" title="Kid" authenticationToken="user_specific_token_abc"/>'
        mock_session.post.return_value = mock_response

        result = account.switch_user(2)

        assert result == "user_specific_token_abc"

    def test_calls_correct_url(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.text = '<User authenticationToken="tok"/>'
        mock_session.post.return_value = mock_response

        account.switch_user(42)

        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert call_url == "https://plex.tv/api/home/users/42/switch"

    def test_returns_none_on_connection_error(self) -> None:
        account, mock_session = _make_account()
        mock_session.post.side_effect = req.exceptions.ConnectionError("refused")

        result = account.switch_user(1)

        assert result is None

    def test_returns_none_on_timeout(self) -> None:
        account, mock_session = _make_account()
        mock_session.post.side_effect = req.exceptions.Timeout()

        result = account.switch_user(1)

        assert result is None

    def test_returns_none_on_http_error(self) -> None:
        account, mock_session = _make_account()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("403")
        mock_session.post.return_value = mock_response

        result = account.switch_user(1)

        assert result is None

    def test_returns_none_when_authentication_token_missing(self) -> None:
        """If the XML response has no authenticationToken attribute, return None."""
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.text = '<User id="2" title="Kid"/>'
        mock_session.post.return_value = mock_response

        result = account.switch_user(2)

        assert result is None


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_returns_true_on_success(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "username": "admin@example.com"}
        mock_session.get.return_value = mock_response

        result = account.test_connection()

        assert result is True

    def test_calls_correct_url(self) -> None:
        account, mock_session = _make_account()

        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_session.get.return_value = mock_response

        account.test_connection()

        call_url = mock_session.get.call_args[0][0]
        assert call_url == "https://plex.tv/api/v2/user"

    def test_returns_false_on_connection_error(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

        result = account.test_connection()

        assert result is False

    def test_returns_false_on_timeout(self) -> None:
        account, mock_session = _make_account()
        mock_session.get.side_effect = req.exceptions.Timeout()

        result = account.test_connection()

        assert result is False

    def test_returns_false_on_http_error(self) -> None:
        account, mock_session = _make_account()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("401")
        mock_session.get.return_value = mock_response

        result = account.test_connection()

        assert result is False

    def test_returns_false_on_invalid_token(self) -> None:
        """A 401 Unauthorized response should return False."""
        account, mock_session = _make_account()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("401 Unauthorized")
        mock_session.get.return_value = mock_response

        result = account.test_connection()

        assert result is False
