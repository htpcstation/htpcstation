"""Configuration management for HTPC Station.

Loads and saves a JSON config file at ***REMOVED***.config/htpcstation/config.json.
Ships built-in defaults for ~20 common retro systems.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "htpcstation"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULT_RETROARCH_COMMAND = "flatpak run org.libretro.RetroArch"
_DEFAULT_CORES_DIRECTORY = "***REMOVED***.var/app/org.libretro.RetroArch/config/retroarch/cores"
_DEFAULT_BROWSER_COMMAND = "flatpak run com.brave.Browser"

SYSTEM_DEFAULTS: dict[str, dict] = {
    "gb": {"display_name": "Game Boy", "core": "gambatte_libretro.so", "extensions": [".gb"]},
    "gbc": {"display_name": "Game Boy Color", "core": "gambatte_libretro.so", "extensions": [".gbc"]},
    "gba": {"display_name": "Game Boy Advance", "core": "gpsp_libretro.so", "extensions": [".gba"]},
    "nes": {"display_name": "Nintendo Entertainment System", "core": "mesen_libretro.so", "extensions": [".nes"]},
    "snes": {"display_name": "Super Nintendo", "core": "snes9x_libretro.so", "extensions": [".smc", ".sfc"]},
    "n64": {"display_name": "Nintendo 64", "core": "mupen64plus_next_libretro.so", "extensions": [".n64", ".z64", ".v64"]},
    "nds": {"display_name": "Nintendo DS", "core": "melonds_libretro.so", "extensions": [".nds"]},
    "megadrive": {"display_name": "Sega Genesis / Mega Drive", "core": "genesis_plus_gx_libretro.so", "extensions": [".md", ".bin", ".gen"]},
    "sega32x": {"display_name": "Sega 32X", "core": "picodrive_libretro.so", "extensions": [".32x"]},
    "segacd": {"display_name": "Sega CD", "core": "genesis_plus_gx_libretro.so", "extensions": [".chd", ".cue"]},
    "mastersystem": {"display_name": "Sega Master System", "core": "genesis_plus_gx_libretro.so", "extensions": [".sms"]},
    "gamegear": {"display_name": "Sega Game Gear", "core": "genesis_plus_gx_libretro.so", "extensions": [".gg"]},
    "psx": {"display_name": "PlayStation", "core": "mednafen_psx_hw_libretro.so", "extensions": [".chd", ".cue", ".pbp"]},
    "pce": {"display_name": "PC Engine / TurboGrafx-16", "core": "mednafen_pce_libretro.so", "extensions": [".pce"]},
    "ngpc": {"display_name": "Neo Geo Pocket Color", "core": "mednafen_ngp_libretro.so", "extensions": [".ngc", ".ngp"]},
    "ngp": {"display_name": "Neo Geo Pocket", "core": "mednafen_ngp_libretro.so", "extensions": [".ngp"]},
    "atari2600": {"display_name": "Atari 2600", "core": "stella_libretro.so", "extensions": [".a26"]},
    "atari7800": {"display_name": "Atari 7800", "core": "prosystem_libretro.so", "extensions": [".a78"]},
    "wonderswan": {"display_name": "WonderSwan", "core": "mednafen_wswan_libretro.so", "extensions": [".ws"]},
    "wonderswancolor": {"display_name": "WonderSwan Color", "core": "mednafen_wswan_libretro.so", "extensions": [".wsc"]},
}


@dataclass
class SystemConfig:
    """Configuration for a single emulated system."""

    display_name: str
    core: str
    extensions: list[str] = field(default_factory=list)


class Config:
    """Application configuration.

    Loads ``***REMOVED***.config/htpcstation/config.json`` on construction.
    If the file does not exist it is created with defaults.
    If the file is malformed a warning is logged and defaults are used.
    """

    def __init__(self) -> None:
        ensure_config_dir()

        self.retroarch_command: str = _DEFAULT_RETROARCH_COMMAND
        self.cores_directory: Path = Path(_DEFAULT_CORES_DIRECTORY).expanduser()
        self.rom_directory: Optional[Path] = None
        # Merged system configs: built-in defaults overridden by user config.
        self._systems: dict[str, SystemConfig] = {
            key: SystemConfig(**values) for key, values in SYSTEM_DEFAULTS.items()
        }
        # Plex Media Server configuration
        self._plex_server_url: Optional[str] = None
        self._plex_token: Optional[str] = None
        # Browser configuration
        self._browser_command: str = _DEFAULT_BROWSER_COMMAND
        # UI settings
        self.video_snap_autoplay: bool = True
        self.video_snap_delay_ms: int = 1500

        if CONFIG_FILE.exists():
            self._load()
        else:
            self.save()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_system(self, folder_name: str) -> SystemConfig:
        """Return the SystemConfig for *folder_name*.

        Falls back to a minimal "unknown" config when the folder name is not
        recognised so callers never have to handle ``None``.
        """
        if folder_name in self._systems:
            return self._systems[folder_name]
        return SystemConfig(display_name=folder_name, core="", extensions=[])

    def get_launch_command(self, folder_name: str, rom_path: "str | Path") -> list[str]:
        """Build the RetroArch launch command for *rom_path* using the core
        configured for *folder_name*.

        Returns a list suitable for ``subprocess.run`` / ``QProcess``.
        """
        system = self.get_system(folder_name)
        core_path = self.cores_directory / system.core
        # Split the retroarch_command string into tokens so the caller gets a
        # proper argv list regardless of how the command is stored.
        command_tokens = self.retroarch_command.split()
        return [*command_tokens, "--fullscreen", "-L", str(core_path), str(rom_path)]

    @property
    def plex_server_url(self) -> Optional[str]:
        """Plex Media Server URL, e.g. 'http://192.168.0.2:32400'. None if not configured."""
        return self._plex_server_url

    @property
    def plex_token(self) -> Optional[str]:
        """Plex authentication token. None if not configured."""
        return self._plex_token

    @property
    def browser_command(self) -> str:
        """Browser launch command, e.g. 'flatpak run com.brave.Browser'."""
        return self._browser_command

    def set_rom_directory(self, path: "str | Path") -> None:
        """Set the ROM directory and persist the config."""
        self.rom_directory = Path(path).expanduser()
        self.save()

    def set_plex_server_url(self, url: str) -> None:
        """Set the Plex server URL and persist the config."""
        self._plex_server_url = url if url else None
        self.save()

    def set_plex_token(self, token: str) -> None:
        """Set the Plex authentication token and persist the config."""
        self._plex_token = token if token else None
        self.save()

    def set_browser_command(self, command: str) -> None:
        """Set the browser launch command and persist the config."""
        self._browser_command = command
        self.save()

    def set_retroarch_command(self, command: str) -> None:
        """Set the RetroArch launch command and persist the config."""
        self.retroarch_command = command
        self.save()

    def set_cores_directory(self, path: str) -> None:
        """Set the RetroArch cores directory and persist the config."""
        self.cores_directory = Path(path).expanduser()
        self.save()

    def set_system_core(self, folder_name: str, core: str) -> None:
        """Set the core for a specific system and persist the config."""
        if folder_name in self._systems:
            self._systems[folder_name].core = core
        else:
            self._systems[folder_name] = SystemConfig(
                display_name=folder_name, core=core, extensions=[]
            )
        self.save()

    def set_video_snap_autoplay(self, enabled: bool) -> None:
        """Set the video snap autoplay toggle and persist the config."""
        self.video_snap_autoplay = enabled
        self.save()

    def set_video_snap_delay_ms(self, delay: int) -> None:
        """Set the video snap delay in milliseconds and persist the config."""
        self.video_snap_delay_ms = delay
        self.save()

    def save(self) -> None:
        """Write the current configuration to ``config.json``."""
        ensure_config_dir()
        data: dict = {
            "rom_directory": str(self.rom_directory) if self.rom_directory else "",
            "retroarch": {
                "command": self.retroarch_command,
                "cores_directory": str(self.cores_directory),
            },
            "systems": {
                key: {
                    "display_name": sc.display_name,
                    "core": sc.core,
                    "extensions": sc.extensions,
                }
                for key, sc in self._systems.items()
            },
            "plex": {
                "server_url": self._plex_server_url or "",
                "token": self._plex_token or "",
            },
            "browser": {
                "command": self._browser_command,
            },
            "ui": {
                "video_snap_autoplay": self.video_snap_autoplay,
                "video_snap_delay_ms": self.video_snap_delay_ms,
            },
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load config from disk, merging with built-in defaults."""
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load config file %s: %s — using defaults", CONFIG_FILE, exc)
            return

        if not isinstance(raw, dict):
            logger.warning("Config file %s has unexpected format (not a JSON object) — using defaults", CONFIG_FILE)
            return

        # rom_directory
        rom_dir_raw: str = raw.get("rom_directory", "")
        if rom_dir_raw:
            self.rom_directory = Path(rom_dir_raw).expanduser()

        # retroarch section
        retroarch = raw.get("retroarch", {})
        if isinstance(retroarch, dict):
            if "command" in retroarch:
                self.retroarch_command = retroarch["command"]
            if "cores_directory" in retroarch:
                self.cores_directory = Path(retroarch["cores_directory"]).expanduser()

        # systems — merge: built-in defaults first, then user overrides
        user_systems: dict = raw.get("systems", {})
        if isinstance(user_systems, dict):
            for key, values in user_systems.items():
                if not isinstance(values, dict):
                    continue
                if key in self._systems:
                    # Update existing SystemConfig fields selectively
                    existing = self._systems[key]
                    existing.display_name = values.get("display_name", existing.display_name)
                    existing.core = values.get("core", existing.core)
                    existing.extensions = values.get("extensions", existing.extensions)
                else:
                    # Unknown system defined by user — add it
                    self._systems[key] = SystemConfig(
                        display_name=values.get("display_name", key),
                        core=values.get("core", ""),
                        extensions=values.get("extensions", []),
                    )

        # plex section
        plex = raw.get("plex", {})
        if isinstance(plex, dict):
            server_url = plex.get("server_url", "")
            if server_url:
                self._plex_server_url = server_url
            token = plex.get("token", "")
            if token:
                self._plex_token = token

        # browser section
        browser = raw.get("browser", {})
        if isinstance(browser, dict):
            command = browser.get("command", "")
            if command:
                self._browser_command = command

        # ui section
        ui = raw.get("ui", {})
        if isinstance(ui, dict):
            if "video_snap_autoplay" in ui:
                self.video_snap_autoplay = bool(ui["video_snap_autoplay"])
            if "video_snap_delay_ms" in ui:
                self.video_snap_delay_ms = int(ui["video_snap_delay_ms"])


def ensure_config_dir() -> None:
    """Create the XDG config directory for htpcstation if it does not exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
