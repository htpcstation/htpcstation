"""Data models for Moonlight game streaming hosts and apps.

Plain Python dataclasses — not QObjects. Populated by moonlight_parser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MoonlightHost:
    """Represents a single paired Moonlight host (PC running GameStream/Sunshine)."""

    name: str           # Hostname reported by the host, e.g. "***REMOVED***"
    uuid: str           # Unique host identifier
    address: str        # Primary connection address (IP or hostname)
    local_address: str  # LAN address
    remote_address: str # WAN/remote address
    manual_address: str # User-specified address override (may be empty)
    mac_address: str    # MAC address of the host NIC
    custom_name: str    # User-assigned alias (may be empty)

    @property
    def display_name(self) -> str:
        """Return custom_name if set, otherwise fall back to name."""
        return self.custom_name if self.custom_name else self.name


@dataclass
class MoonlightApp:
    """Represents a game/app available on a Moonlight host.

    Moonlight CLI uses app names (not numeric IDs) to launch, so no ID field
    is needed at this layer.
    """

    name: str           # App/game name as reported by the host
    host_uuid: str      # UUID of the host that owns this app
    image_path: str = ""  # Local filesystem path to the artwork poster (empty if unavailable)
    last_played: str = ""  # ISO 8601 UTC timestamp of last launch (empty if never played)
