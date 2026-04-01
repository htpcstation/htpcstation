"""plex.tv account API client.

A plain Python class (not a QObject) that wraps plex.tv API calls for server
discovery and user switching.  All methods are safe to call from worker threads.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://plex.tv/api/v2"
_HOME_BASE_URL = "https://plex.tv/api"
_TIMEOUT = 10  # seconds


class PlexAccount:
    """HTTP client for the plex.tv account API.

    All requests include the X-Plex-Token header and Accept: application/json.
    Connection errors are handled gracefully — methods return empty results and
    log a warning rather than raising.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Plex-Token": token,
                "Accept": "application/json",
                "X-Plex-Client-Identifier": "htpcstation",
                "X-Plex-Product": "HTPC Station",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_resources(self) -> list[dict]:
        """GET /resources — returns list of server resources.

        Filters to resources where ``provides`` contains ``"server"``.
        Each resource has: name, clientIdentifier, owned, connections.
        """
        data = self._get("/resources", params={"includeHttps": 1})
        if data is None:
            return []
        return [
            r for r in data
            if isinstance(r, dict) and "server" in r.get("provides", "")
        ]

    def get_home_users(self) -> list[dict]:
        """GET /home/users — returns list of home user dicts.

        Each user has: id, title, username, admin, restricted, protected, thumb.
        Uses the /api/home/users endpoint (no v2) which returns XML.
        The old /api/ endpoints require the token as a query parameter.
        """
        url = f"{_HOME_BASE_URL}/home/users"
        root = self._get_xml(url, params={"X-Plex-Token": self._token})
        if root is None:
            return []
        users = []
        for user_el in root.findall("User"):
            a = user_el.attrib
            users.append(
                {
                    "id": int(a.get("id", 0)),
                    "title": a.get("title", ""),
                    "username": a.get("username", ""),
                    "admin": a.get("admin", "0") == "1",
                    "restricted": a.get("restricted", "0") == "1",
                    "protected": a.get("protected", "0") == "1",
                    "thumb": a.get("thumb", ""),
                    "restrictionProfile": a.get("restrictionProfile", ""),
                }
            )
        return users

    def switch_user(self, user_id: int) -> str | None:
        """POST /home/users/{user_id}/switch — switch to a home user.

        Returns the ``authenticationToken`` for the switched-to user, or ``None``
        on failure.  The /api/ endpoint returns XML, not JSON.
        """
        url = f"{_HOME_BASE_URL}/home/users/{user_id}/switch"
        try:
            # The old /api/ endpoints require the token as a query parameter
            response = self._session.post(
                url, params={"X-Plex-Token": self._token}, timeout=_TIMEOUT
            )
            response.raise_for_status()
            # The /api/ endpoint returns XML, not JSON
            root = ET.fromstring(response.text)
            return root.attrib.get("authenticationToken")
        except requests.exceptions.ConnectionError as exc:
            logger.warning("PlexAccount connection error for %s: %s", url, exc)
        except requests.exceptions.Timeout:
            logger.warning("PlexAccount request timed out for %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.warning("PlexAccount HTTP error for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexAccount unexpected error for %s: %s", url, exc)
        return None

    def test_connection(self) -> bool:
        """GET /user — validate the token.

        Returns ``True`` if the request succeeds, ``False`` otherwise.
        """
        data = self._get("/user")
        return data is not None

    # ------------------------------------------------------------------
    # OAuth / PIN methods (no token required)
    # ------------------------------------------------------------------

    @staticmethod
    def create_pin() -> tuple[int, str] | None:
        """POST /pins — create a new PIN for OAuth login.

        Does not require an auth token.  Returns ``(pin_id, code)`` on
        success, or ``None`` on error.
        """
        url = f"{_BASE_URL}/pins"
        headers = {
            "X-Plex-Client-Identifier": "htpcstation",
            "X-Plex-Product": "HTPC Station",
            "Accept": "application/json",
        }
        try:
            response = requests.post(
                url, params={"strong": "true"}, headers=headers, timeout=_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            return (data["id"], data["code"])
        except requests.exceptions.ConnectionError as exc:
            logger.warning("PlexAccount.create_pin connection error: %s", exc)
        except requests.exceptions.Timeout:
            logger.warning("PlexAccount.create_pin request timed out")
        except requests.exceptions.HTTPError as exc:
            logger.warning("PlexAccount.create_pin HTTP error: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexAccount.create_pin unexpected error: %s", exc)
        return None

    @staticmethod
    def check_pin(pin_id: int) -> str | None:
        """GET /pins/{pin_id} — check whether the user has completed OAuth login.

        Does not require an auth token.  Returns the ``authToken`` string if
        the user has authenticated, or ``None`` if not yet authenticated or on
        error.
        """
        url = f"{_BASE_URL}/pins/{pin_id}"
        headers = {
            "X-Plex-Client-Identifier": "htpcstation",
            "X-Plex-Product": "HTPC Station",
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, headers=headers, timeout=_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            token = data.get("authToken")
            return token if token else None
        except requests.exceptions.ConnectionError as exc:
            logger.warning("PlexAccount.check_pin connection error: %s", exc)
        except requests.exceptions.Timeout:
            logger.warning("PlexAccount.check_pin request timed out")
        except requests.exceptions.HTTPError as exc:
            logger.warning("PlexAccount.check_pin HTTP error: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexAccount.check_pin unexpected error: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> object | None:
        """Perform a GET request against _BASE_URL and return the parsed JSON, or None on error."""
        url = f"{_BASE_URL}{path}"
        return self._get_url(url, params)

    def _get_home(self, path: str, params: dict | None = None) -> object | None:
        """Perform a GET request against _HOME_BASE_URL and return the parsed JSON, or None on error."""
        url = f"{_HOME_BASE_URL}{path}"
        return self._get_url(url, params)

    def _get_xml(self, url: str, params: dict | None = None) -> ET.Element | None:
        """Perform a GET request and return the parsed XML root element, or None on error."""
        try:
            response = self._session.get(url, params=params, timeout=_TIMEOUT)
            response.raise_for_status()
            return ET.fromstring(response.text)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("PlexAccount connection error for %s: %s", url, exc)
        except requests.exceptions.Timeout:
            logger.warning("PlexAccount request timed out for %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.warning("PlexAccount HTTP error for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexAccount unexpected error for %s: %s", url, exc)
        return None

    def _get_url(self, url: str, params: dict | None = None) -> object | None:
        """Perform a GET request to the given URL and return the parsed JSON, or None on error."""
        try:
            response = self._session.get(url, params=params, timeout=_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as exc:
            logger.warning("PlexAccount connection error for %s: %s", url, exc)
        except requests.exceptions.Timeout:
            logger.warning("PlexAccount request timed out for %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.warning("PlexAccount HTTP error for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlexAccount unexpected error for %s: %s", url, exc)
        return None
