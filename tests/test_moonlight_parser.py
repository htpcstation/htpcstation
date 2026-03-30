"""Tests for Task 001 — Moonlight Config Parser and Models.

Covers:
  - moonlight_models: MoonlightHost and MoonlightApp dataclass fields
  - moonlight_models: MoonlightHost.display_name property
  - moonlight_parser.discover_moonlight_hosts: valid config with hosts
  - moonlight_parser.discover_moonlight_hosts: config with no [hosts] section
  - moonlight_parser.discover_moonlight_hosts: missing config file
  - moonlight_parser.discover_moonlight_hosts: malformed entries (missing name, missing all addresses)
  - moonlight_parser.discover_moonlight_hosts: multiple hosts
  - moonlight_parser.check_host_available: successful connection (mock socket)
  - moonlight_parser.check_host_available: connection refused (mock)
  - moonlight_parser.check_host_available: timeout (mock)
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.moonlight_models import MoonlightApp, MoonlightHost
from tests.local_overrides import get_override

HOST_NAME = get_override("moonlight_hostname", "***REMOVED***")
LOCAL_IP = get_override("moonlight_local_ip", "***REMOVED***")
MANUAL_IP = get_override("moonlight_manual_ip", "10.0.0.1")
PUBLIC_REMOTE_IP = get_override("moonlight_public_remote_ip", "***REMOVED***")
REALISTIC_UUID = get_override("moonlight_realistic_uuid", "12345678-9ABC-DEF0-1234-56789ABCDEF0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_conf(path: Path, content: str) -> Path:
    """Write a Moonlight.conf file to *path* (a directory) and return its path."""
    conf = path / "Moonlight.conf"
    conf.write_text(content, encoding="utf-8")
    return conf


def _minimal_conf(hosts_section: str = "") -> str:
    """Return a minimal Moonlight.conf with optional [hosts] content."""
    base = "[General]\ncertificate=@ByteArray(fake)\nkey=@ByteArray(fake)\n"
    if hosts_section:
        base += "\n[hosts]\n" + hosts_section
    return base


def _host_entry(
    prefix: int = 1,
    name: str = HOST_NAME,
    uuid: str = "test-uuid-1234",
    local_address: str = LOCAL_IP,
    remote_address: str = "1.2.3.4",
    manual_address: str = "",
    mac_address: str = "",
    custom_name: str = "",
) -> str:
    """Return INI lines for a single host entry using the real QSettings field names.

    QSettings writes all keys lowercase: ``hostname``, ``localaddress``, etc.
    The ``customname`` field is ``"false"`` when no custom name is set.
    """
    lines = [
        f"{prefix}\\hostname={name}",
        f"{prefix}\\uuid={uuid}",
        f"{prefix}\\localaddress={local_address}",
        f"{prefix}\\remoteaddress={remote_address}",
        f"{prefix}\\customname={'false' if not custom_name else custom_name}",
    ]
    if manual_address:
        lines.append(f"{prefix}\\manualaddress={manual_address}")
    if mac_address:
        lines.append(f"{prefix}\\macaddress={mac_address}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# MoonlightHost dataclass
# ---------------------------------------------------------------------------


class TestMoonlightHost:
    def test_all_fields_set(self) -> None:
        host = MoonlightHost(
            name=HOST_NAME,
            uuid="abc-123",
            address=LOCAL_IP,
            local_address=LOCAL_IP,
            remote_address="1.2.3.4",
            manual_address="",
            mac_address="AA:BB:CC:DD:EE:FF",
            custom_name="",
        )
        assert host.name == HOST_NAME
        assert host.uuid == "abc-123"
        assert host.address == LOCAL_IP
        assert host.local_address == LOCAL_IP
        assert host.remote_address == "1.2.3.4"
        assert host.manual_address == ""
        assert host.mac_address == "AA:BB:CC:DD:EE:FF"
        assert host.custom_name == ""

    def test_display_name_uses_name_when_custom_name_empty(self) -> None:
        host = MoonlightHost(
            name=HOST_NAME,
            uuid="",
            address=LOCAL_IP,
            local_address="",
            remote_address="",
            manual_address="",
            mac_address="",
            custom_name="",
        )
        assert host.display_name == HOST_NAME

    def test_display_name_prefers_custom_name(self) -> None:
        host = MoonlightHost(
            name=HOST_NAME,
            uuid="",
            address=LOCAL_IP,
            local_address="",
            remote_address="",
            manual_address="",
            mac_address="",
            custom_name="Gaming PC",
        )
        assert host.display_name == "Gaming PC"

    def test_display_name_with_whitespace_custom_name(self) -> None:
        """A non-empty custom_name (even with spaces) is preferred over name."""
        host = MoonlightHost(
            name=HOST_NAME,
            uuid="",
            address=LOCAL_IP,
            local_address="",
            remote_address="",
            manual_address="",
            mac_address="",
            custom_name="My Living Room PC",
        )
        assert host.display_name == "My Living Room PC"


# ---------------------------------------------------------------------------
# MoonlightApp dataclass
# ---------------------------------------------------------------------------


class TestMoonlightApp:
    def test_all_fields_set(self) -> None:
        app = MoonlightApp(name="Cyberpunk 2077", host_uuid="abc-123")
        assert app.name == "Cyberpunk 2077"
        assert app.host_uuid == "abc-123"

    def test_empty_fields(self) -> None:
        app = MoonlightApp(name="", host_uuid="")
        assert app.name == ""
        assert app.host_uuid == ""


# ---------------------------------------------------------------------------
# discover_moonlight_hosts — valid config
# ---------------------------------------------------------------------------


class TestDiscoverMoonlightHostsValid:
    def test_single_host_all_fields(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts parses a single host with all fields."""
        from backend.moonlight_parser import discover_moonlight_hosts

        conf = _write_conf(
            tmp_path,
            _minimal_conf(
                _host_entry(
                    prefix=1,
                    name=HOST_NAME,
                    uuid="host-uuid-1",
                    local_address=LOCAL_IP,
                    remote_address="5.6.7.8",
                    manual_address=MANUAL_IP,
                    mac_address="AA:BB:CC:DD:EE:FF",
                    custom_name="Gaming Rig",
                )
            ),
        )
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        h = hosts[0]
        assert h.name == HOST_NAME
        assert h.uuid == "host-uuid-1"
        # address is derived: manual_address takes priority
        assert h.address == MANUAL_IP
        assert h.local_address == LOCAL_IP
        assert h.remote_address == "5.6.7.8"
        assert h.manual_address == MANUAL_IP
        assert h.mac_address == "AA:BB:CC:DD:EE:FF"
        assert h.custom_name == "Gaming Rig"
        assert h.display_name == "Gaming Rig"

    def test_single_host_no_custom_name(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts handles a host without a custom name."""
        from backend.moonlight_parser import discover_moonlight_hosts

        conf = _write_conf(tmp_path, _minimal_conf(_host_entry(name="MYPC")))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].display_name == "MYPC"

    def test_multiple_hosts(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts returns all paired hosts."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            _host_entry(prefix=1, name="PC-ONE", uuid="uuid-1", local_address="192.168.0.10")
            + _host_entry(prefix=2, name="PC-TWO", uuid="uuid-2", local_address="192.168.0.20")
            + _host_entry(prefix=3, name="PC-THREE", uuid="uuid-3", local_address="192.168.0.30")
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 3
        names = [h.name for h in hosts]
        assert "PC-ONE" in names
        assert "PC-TWO" in names
        assert "PC-THREE" in names

    def test_hosts_returned_in_numeric_prefix_order(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts returns hosts ordered by numeric prefix."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            _host_entry(prefix=3, name="Third", uuid="uuid-3", local_address="192.168.0.3")
            + _host_entry(prefix=1, name="First", uuid="uuid-1", local_address="192.168.0.1")
            + _host_entry(prefix=2, name="Second", uuid="uuid-2", local_address="192.168.0.2")
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 3
        assert hosts[0].name == "First"
        assert hosts[1].name == "Second"
        assert hosts[2].name == "Third"

    def test_serverCert_stored_as_raw_string(self, tmp_path: Path) -> None:
        """@ByteArray values are stored as raw strings without decoding."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            _host_entry(prefix=1, name="MYPC", local_address=LOCAL_IP)
            + "1\\srvcert=@ByteArray(MIIBkTCB+wIJ...)\n"
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        # Should not raise; host is still parsed correctly
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].name == "MYPC"

    def test_realistic_config_with_apps_subkeys(self, tmp_path: Path) -> None:
        """Parses a realistic Moonlight.conf with apps\\ subkeys and customname=false."""
        from backend.moonlight_parser import discover_moonlight_hosts

        # Mirrors the actual QSettings output from a paired Apollo/Sunshine host
        realistic_section = (
            "1\\apps\\1\\appcollector=false\n"
            "1\\apps\\1\\directlaunch=false\n"
            "1\\apps\\1\\hdr=true\n"
            "1\\apps\\1\\hidden=false\n"
            "1\\apps\\1\\id=881448767\n"
            "1\\apps\\1\\name=Desktop\n"
            "1\\apps\\2\\appcollector=false\n"
            "1\\apps\\2\\directlaunch=false\n"
            "1\\apps\\2\\hdr=true\n"
            "1\\apps\\2\\hidden=false\n"
            "1\\apps\\2\\id=1969390298\n"
            "1\\apps\\2\\name=Divinity: Original Sin II\n"
            "1\\apps\\size=2\n"
            "1\\customname=false\n"
            f"1\\hostname={HOST_NAME}\n"
            "1\\ipv6address=\n"
            "1\\ipv6port=0\n"
            f"1\\localaddress={LOCAL_IP}\n"
            "1\\localport=47989\n"
            f"1\\manualaddress={LOCAL_IP}\n"
            "1\\manualport=47989\n"
            "1\\nvidiasw=false\n"
            f"1\\remoteaddress={PUBLIC_REMOTE_IP}\n"
            "1\\remoteport=47989\n"
            "1\\srvcert=@ByteArray(-----BEGIN CERTIFICATE-----\\nMIIC...\\n-----END CERTIFICATE-----\\n)\n"
            f"1\\uuid={REALISTIC_UUID}\n"
            "size=1\n"
        )
        conf = _write_conf(tmp_path, _minimal_conf(realistic_section))
        hosts = discover_moonlight_hosts(conf)

        assert len(hosts) == 1
        h = hosts[0]
        assert h.name == HOST_NAME
        assert h.uuid == REALISTIC_UUID
        assert h.local_address == LOCAL_IP
        assert h.remote_address == PUBLIC_REMOTE_IP
        assert h.manual_address == LOCAL_IP
        # address is derived: manual_address takes priority
        assert h.address == LOCAL_IP
        # customname=false means no custom name — display_name falls back to hostname
        assert h.custom_name == ""
        assert h.display_name == HOST_NAME

    def test_customname_false_string_treated_as_no_custom_name(self, tmp_path: Path) -> None:
        """customname=false (boolean string) is treated as no custom name set."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            "1\\hostname=MYPC\n"
            "1\\uuid=some-uuid\n"
            f"1\\localaddress={LOCAL_IP}\n"
            "1\\customname=false\n"
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].custom_name == ""
        assert hosts[0].display_name == "MYPC"

    def test_address_derived_from_manual_then_local_then_remote(self, tmp_path: Path) -> None:
        """host.address is derived: manual_address > local_address > remote_address."""
        from backend.moonlight_parser import discover_moonlight_hosts

        # Only remote address available
        section = (
            "1\\hostname=MYPC\n"
            "1\\uuid=some-uuid\n"
            f"1\\remoteaddress={PUBLIC_REMOTE_IP}\n"
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].address == PUBLIC_REMOTE_IP

        # local_address available (no manual)
        section2 = (
            "1\\hostname=MYPC\n"
            "1\\uuid=some-uuid\n"
            f"1\\localaddress={LOCAL_IP}\n"
            f"1\\remoteaddress={PUBLIC_REMOTE_IP}\n"
        )
        subdir = tmp_path / "conf2"
        subdir.mkdir(exist_ok=True)
        conf2 = _write_conf(subdir, _minimal_conf(section2))
        hosts2 = discover_moonlight_hosts(conf2)
        assert len(hosts2) == 1
        assert hosts2[0].address == LOCAL_IP


# ---------------------------------------------------------------------------
# discover_moonlight_hosts — missing / empty config
# ---------------------------------------------------------------------------


class TestDiscoverMoonlightHostsMissing:
    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts returns [] when the config file doesn't exist."""
        from backend.moonlight_parser import discover_moonlight_hosts

        hosts = discover_moonlight_hosts(tmp_path / "nonexistent.conf")
        assert hosts == []

    def test_returns_empty_when_no_hosts_section(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts returns [] when [hosts] section is absent."""
        from backend.moonlight_parser import discover_moonlight_hosts

        conf = _write_conf(tmp_path, _minimal_conf())  # no hosts section
        hosts = discover_moonlight_hosts(conf)
        assert hosts == []

    def test_returns_empty_for_empty_hosts_section(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts returns [] when [hosts] section is empty."""
        from backend.moonlight_parser import discover_moonlight_hosts

        conf = _write_conf(tmp_path, _minimal_conf(""))
        hosts = discover_moonlight_hosts(conf)
        assert hosts == []

    def test_uses_default_path_when_none_given(self, tmp_path: Path) -> None:
        """discover_moonlight_hosts uses the default path when config_path is None."""
        from backend.moonlight_parser import discover_moonlight_hosts

        # Patch the default path to a non-existent file — should return []
        fake_path = tmp_path / "Moonlight.conf"
        with patch("backend.moonlight_parser._DEFAULT_CONFIG_PATH", fake_path):
            hosts = discover_moonlight_hosts()
        assert hosts == []


# ---------------------------------------------------------------------------
# discover_moonlight_hosts — malformed entries
# ---------------------------------------------------------------------------


class TestDiscoverMoonlightHostsMalformed:
    def test_skips_entry_missing_name(self, tmp_path: Path) -> None:
        """Entries without a hostname field are skipped."""
        from backend.moonlight_parser import discover_moonlight_hosts

        # Entry with uuid and localaddress but no hostname
        section = f"1\\uuid=some-uuid\n1\\localaddress={LOCAL_IP}\n"
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert hosts == []

    def test_skips_entry_missing_all_addresses(self, tmp_path: Path) -> None:
        """Entries with a hostname but no address fields are skipped."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = "1\\hostname=MYPC\n1\\uuid=some-uuid\n1\\macaddress=AA:BB:CC:DD:EE:FF\n"
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert hosts == []

    def test_valid_entry_alongside_malformed_entry(self, tmp_path: Path) -> None:
        """Valid entries are returned even when other entries are malformed."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            # Entry 1: missing hostname — should be skipped
            "1\\uuid=bad-uuid\n1\\localaddress=192.168.0.1\n"
            # Entry 2: valid
            + _host_entry(prefix=2, name="GOOD-PC", uuid="good-uuid", local_address="192.168.0.2")
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].name == "GOOD-PC"

    def test_entry_with_only_manual_address_is_valid(self, tmp_path: Path) -> None:
        """An entry with only manualaddress (no localaddress/remoteaddress) is valid."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = "1\\hostname=MYPC\n1\\uuid=some-uuid\n1\\manualaddress=10.0.0.5\n"
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].name == "MYPC"
        assert hosts[0].manual_address == "10.0.0.5"

    def test_entry_with_only_local_address_is_valid(self, tmp_path: Path) -> None:
        """An entry with only localaddress is valid."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = "1\\hostname=MYPC\n1\\uuid=some-uuid\n1\\localaddress=192.168.1.100\n"
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].local_address == "192.168.1.100"

    def test_ignores_non_numeric_prefixes(self, tmp_path: Path) -> None:
        """Lines with non-numeric prefixes are ignored."""
        from backend.moonlight_parser import discover_moonlight_hosts

        section = (
            "abc\\hostname=BADPC\nabc\\localaddress=192.168.0.1\n"
            + _host_entry(prefix=1, name="GOODPC", local_address="192.168.0.2")
        )
        conf = _write_conf(tmp_path, _minimal_conf(section))
        hosts = discover_moonlight_hosts(conf)
        assert len(hosts) == 1
        assert hosts[0].name == "GOODPC"


# ---------------------------------------------------------------------------
# check_host_available — socket probe
# ---------------------------------------------------------------------------


class TestCheckHostAvailable:
    def test_returns_true_on_successful_connection(self) -> None:
        """check_host_available returns True when TCP connection succeeds."""
        from backend.moonlight_parser import check_host_available

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_sock) as mock_create:
            result = check_host_available(LOCAL_IP)

        assert result is True
        mock_create.assert_called_once_with((LOCAL_IP, 47984), timeout=2.0)

    def test_returns_false_on_connection_refused(self) -> None:
        """check_host_available returns False when connection is refused."""
        from backend.moonlight_parser import check_host_available

        with patch(
            "socket.create_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            result = check_host_available(LOCAL_IP)

        assert result is False

    def test_returns_false_on_timeout(self) -> None:
        """check_host_available returns False when connection times out."""
        from backend.moonlight_parser import check_host_available

        with patch(
            "socket.create_connection",
            side_effect=socket.timeout("timed out"),
        ):
            result = check_host_available(LOCAL_IP)

        assert result is False

    def test_returns_false_on_os_error(self) -> None:
        """check_host_available returns False on any OSError (e.g. network unreachable)."""
        from backend.moonlight_parser import check_host_available

        with patch(
            "socket.create_connection",
            side_effect=OSError("Network unreachable"),
        ):
            result = check_host_available(LOCAL_IP)

        assert result is False

    def test_custom_port_and_timeout(self) -> None:
        """check_host_available passes custom port and timeout to socket."""
        from backend.moonlight_parser import check_host_available

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_sock) as mock_create:
            result = check_host_available("10.0.0.1", port=47990, timeout=5.0)

        assert result is True
        mock_create.assert_called_once_with(("10.0.0.1", 47990), timeout=5.0)

    def test_default_port_is_47984(self) -> None:
        """check_host_available uses port 47984 (GameStream HTTPS API) by default."""
        from backend.moonlight_parser import check_host_available

        with patch(
            "socket.create_connection",
            side_effect=ConnectionRefusedError(),
        ) as mock_create:
            check_host_available(LOCAL_IP)

        args, kwargs = mock_create.call_args
        host, port = args[0]
        assert port == 47984
