"""Moonlight config parser and host discovery.

Parses the QSettings INI config written by the Moonlight Flatpak to discover
paired streaming hosts, and provides a TCP availability probe.
"""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Optional

from backend.moonlight_models import MoonlightHost

logger = logging.getLogger(__name__)

# Default config path for the Moonlight Flatpak
_DEFAULT_CONFIG_PATH = Path.home() / (
    ".var/app/com.moonlight_stream.Moonlight/config/"
    "Moonlight Game Streaming Project/Moonlight.conf"
)

# GameStream HTTPS API port (used for availability probing)
_GAMESTREAM_PORT = 47984


# ---------------------------------------------------------------------------
# Config parser
# ---------------------------------------------------------------------------


def _parse_hosts_section(text: str) -> dict[str, dict[str, str]]:
    """Parse the raw text of a QSettings INI file and extract host entries.

    QSettings writes backslash-separated keys like ``1\\name``, ``1\\uuid``.
    Python's configparser treats ``\\`` as an escape sequence, so we parse
    the ``[hosts]`` section manually to avoid that ambiguity.

    Returns a dict mapping numeric prefix (e.g. ``"1"``) to a dict of field
    name → value.
    """
    hosts: dict[str, dict[str, str]] = {}
    in_hosts = False

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Section header detection
        if line.startswith("["):
            in_hosts = line.lower() == "[hosts]"
            continue

        if not in_hosts:
            continue

        # Skip blank lines and comments
        if not line or line.startswith(";") or line.startswith("#"):
            continue

        # Key=value lines inside [hosts]
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # QSettings keys look like "1\name", "2\uuid", etc.
        if "\\" not in key:
            continue

        prefix, _, field = key.partition("\\")
        prefix = prefix.strip()
        field = field.strip()

        if not prefix.isdigit():
            continue

        hosts.setdefault(prefix, {})[field] = value

    return hosts


def discover_moonlight_hosts(
    config_path: Optional[Path] = None,
) -> list[MoonlightHost]:
    """Discover paired Moonlight hosts from the Flatpak config file.

    Args:
        config_path: Path to ``Moonlight.conf``.  Defaults to the standard
            Flatpak location under ``***REMOVED***.var/app/``.

    Returns:
        A list of :class:`MoonlightHost` objects, one per paired host.
        Returns an empty list if the config file does not exist, has no
        ``[hosts]`` section, or all entries are malformed.
    """
    if config_path is None:
        config_path = _DEFAULT_CONFIG_PATH

    if not config_path.is_file():
        logger.debug("discover_moonlight_hosts: config not found at %s", config_path)
        return []

    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("discover_moonlight_hosts: cannot read %s: %s", config_path, exc)
        return []

    raw_hosts = _parse_hosts_section(text)
    if not raw_hosts:
        logger.debug("discover_moonlight_hosts: no [hosts] section in %s", config_path)
        return []

    hosts: list[MoonlightHost] = []
    for prefix, fields in sorted(raw_hosts.items(), key=lambda kv: int(kv[0])):
        host = _build_host(prefix, fields)
        if host is not None:
            hosts.append(host)

    return hosts


def _build_host(prefix: str, fields: dict[str, str]) -> Optional[MoonlightHost]:
    """Construct a MoonlightHost from raw field dict, or return None if invalid.

    A host is considered valid if it has a non-empty ``hostname`` and at least
    one non-empty address field (``localaddress``, ``remoteaddress``, or
    ``manualaddress``).

    QSettings writes all keys in lowercase (e.g. ``hostname``, ``localaddress``).
    """
    name = fields.get("hostname", "").strip()
    if not name:
        logger.debug("_build_host: skipping entry %s — missing hostname", prefix)
        return None

    local_address = fields.get("localaddress", "").strip()
    remote_address = fields.get("remoteaddress", "").strip()
    manual_address = fields.get("manualaddress", "").strip()

    if not any([local_address, remote_address, manual_address]):
        logger.debug("_build_host: skipping entry %s (%s) — no address", prefix, name)
        return None

    # Derive the primary address: prefer manual_address, then local, then remote
    address = manual_address or local_address or remote_address

    # customname is a boolean string in the real config ("false" means no custom name)
    raw_custom_name = fields.get("customname", "").strip()
    custom_name = "" if raw_custom_name.lower() in ("false", "true", "") else raw_custom_name

    return MoonlightHost(
        name=name,
        uuid=fields.get("uuid", "").strip(),
        address=address,
        local_address=local_address,
        remote_address=remote_address,
        manual_address=manual_address,
        mac_address=fields.get("macaddress", "").strip(),
        custom_name=custom_name,
    )


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def check_host_available(
    address: str,
    port: int = _GAMESTREAM_PORT,
    timeout: float = 2.0,
) -> bool:
    """Probe whether a Moonlight host is reachable via TCP.

    Attempts a TCP connection to *address*:*port* (default 47984, the
    GameStream HTTPS API port).  Returns ``True`` if the connection succeeds
    within *timeout* seconds, ``False`` otherwise.

    Args:
        address: IP address or hostname of the host.
        port: TCP port to probe.  Defaults to 47984.
        timeout: Connection timeout in seconds.  Defaults to 2.0.

    Returns:
        ``True`` if the host accepted the connection, ``False`` on any error
        (connection refused, timeout, DNS failure, etc.).
    """
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False
