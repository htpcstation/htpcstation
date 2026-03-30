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
_DEFAULT_MOONLIGHT_COMMAND = "flatpak run com.moonlight_stream.Moonlight"

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
        self._plex_token: Optional[str] = None
        self._plex_server_id: Optional[str] = None
        self._plex_user_id: Optional[int] = None
        # Browser configuration
        self._browser_command: str = _DEFAULT_BROWSER_COMMAND
        # Moonlight configuration
        self._moonlight_command: str = _DEFAULT_MOONLIGHT_COMMAND
        self._moonlight_host_uuid: str = ""
        # UI settings
        self.video_snap_autoplay: bool = True
        self.video_snap_delay_ms: int = 1500
        self.show_network_indicator: bool = True
        self.button_layout: str = "standard"  # "standard" or "alternate"
        # Tab visibility settings
        self._show_retro_games_tab: bool = True
        self._show_pc_games_tab: bool = True
        self._show_watch_tab: bool = True
        self._show_listen_tab: bool = True
        # Music library selection
        self._music_library_key: str = ""
        # Sort preferences
        self._sort_retro_games: str = "az"
        self._sort_steam_games: str = "az"
        self._sort_moonlight_apps: str = "az"
        self._sort_plex_movies: str = ""
        self._sort_plex_shows: str = ""
        self._filter_plex_movie_genre: str = ""
        self._filter_plex_show_genre: str = ""

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
    def plex_token(self) -> Optional[str]:
        """Plex authentication token. None if not configured."""
        return self._plex_token

    @property
    def plex_server_id(self) -> Optional[str]:
        """Plex server machine identifier (clientIdentifier). None if not selected."""
        return self._plex_server_id

    @property
    def plex_user_id(self) -> Optional[int]:
        """Plex home user ID. None if not selected (uses admin account)."""
        return self._plex_user_id

    @property
    def browser_command(self) -> str:
        """Browser launch command, e.g. 'flatpak run com.brave.Browser'."""
        return self._browser_command

    @property
    def moonlight_command(self) -> str:
        """Moonlight launch command, e.g. 'flatpak run com.moonlight_stream.Moonlight'."""
        return self._moonlight_command

    @property
    def moonlight_host_uuid(self) -> str:
        """UUID of the selected Moonlight host. Empty string if not configured."""
        return self._moonlight_host_uuid

    @property
    def music_library_key(self) -> str:
        """Plex section key of the selected music library. Empty string if not configured."""
        return self._music_library_key

    @property
    def sort_retro_games(self) -> str:
        """Persisted sort key for the retro games grid. Defaults to 'az'."""
        return self._sort_retro_games

    @property
    def sort_steam_games(self) -> str:
        """Persisted sort key for the Steam games grid. Defaults to 'az'."""
        return self._sort_steam_games

    @property
    def sort_moonlight_apps(self) -> str:
        """Persisted sort key for the Moonlight apps grid. Defaults to 'az'."""
        return self._sort_moonlight_apps

    @property
    def sort_plex_movies(self) -> str:
        """Persisted sort key for the Plex movies grid. Empty string means default order."""
        return self._sort_plex_movies

    @property
    def sort_plex_shows(self) -> str:
        """Persisted sort key for the Plex shows grid. Empty string means default order."""
        return self._sort_plex_shows

    @property
    def filter_plex_movie_genre(self) -> str:
        """Persisted genre filter key for Plex movies. Empty string means no filter."""
        return self._filter_plex_movie_genre

    @property
    def filter_plex_show_genre(self) -> str:
        """Persisted genre filter key for Plex shows. Empty string means no filter."""
        return self._filter_plex_show_genre

    def set_rom_directory(self, path: "str | Path") -> None:
        """Set the ROM directory and persist the config."""
        self.rom_directory = Path(path).expanduser()
        self.save()

    def set_plex_token(self, token: str) -> None:
        """Set the Plex authentication token and persist the config."""
        self._plex_token = token if token else None
        self.save()

    def set_plex_server_id(self, server_id: str) -> None:
        """Set the Plex server machine identifier and persist the config."""
        self._plex_server_id = server_id if server_id else None
        self.save()

    def set_plex_user_id(self, user_id: int) -> None:
        """Set the Plex home user ID and persist the config."""
        self._plex_user_id = user_id if user_id else None
        self.save()

    def set_browser_command(self, command: str) -> None:
        """Set the browser launch command and persist the config."""
        self._browser_command = command
        self.save()

    def set_moonlight_command(self, command: str) -> None:
        """Set the Moonlight launch command and persist the config."""
        self._moonlight_command = command
        self.save()

    def set_moonlight_host_uuid(self, uuid: str) -> None:
        """Set the selected Moonlight host UUID and persist the config."""
        self._moonlight_host_uuid = uuid
        self.save()

    def set_music_library_key(self, key: str) -> None:
        """Set the selected Plex music library section key and persist the config."""
        self._music_library_key = key
        self.save()

    def set_sort_retro_games(self, key: str) -> None:
        """Set the sort preference for the retro games grid and persist the config."""
        self._sort_retro_games = key
        self.save()

    def set_sort_steam_games(self, key: str) -> None:
        """Set the sort preference for the Steam games grid and persist the config."""
        self._sort_steam_games = key
        self.save()

    def set_sort_moonlight_apps(self, key: str) -> None:
        """Set the sort preference for the Moonlight apps grid and persist the config."""
        self._sort_moonlight_apps = key
        self.save()

    def set_sort_plex_movies(self, key: str) -> None:
        """Set the sort preference for the Plex movies grid and persist the config."""
        self._sort_plex_movies = key
        self.save()

    def set_sort_plex_shows(self, key: str) -> None:
        """Set the sort preference for the Plex shows grid and persist the config."""
        self._sort_plex_shows = key
        self.save()

    def set_filter_plex_movie_genre(self, key: str) -> None:
        """Set the genre filter for Plex movies and persist the config."""
        self._filter_plex_movie_genre = key
        self.save()

    def set_filter_plex_show_genre(self, key: str) -> None:
        """Set the genre filter for Plex shows and persist the config."""
        self._filter_plex_show_genre = key
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

    def set_show_network_indicator(self, enabled: bool) -> None:
        """Set the network indicator visibility toggle and persist the config."""
        self.show_network_indicator = enabled
        self.save()

    def set_button_layout(self, layout: str) -> None:
        """Set the button layout ('standard' or 'alternate') and persist the config."""
        if layout in ("standard", "alternate"):
            self.button_layout = layout
            self.save()

    @property
    def show_retro_games_tab(self) -> bool:
        """Whether the Retro Games tab is visible. Defaults to True."""
        return self._show_retro_games_tab

    @property
    def show_pc_games_tab(self) -> bool:
        """Whether the PC Games tab is visible. Defaults to True."""
        return self._show_pc_games_tab

    @property
    def show_watch_tab(self) -> bool:
        """Whether the Watch tab is visible. Defaults to True."""
        return self._show_watch_tab

    @property
    def show_listen_tab(self) -> bool:
        """Whether the Listen tab is visible. Defaults to True."""
        return self._show_listen_tab

    def set_show_retro_games_tab(self, enabled: bool) -> None:
        """Set the Retro Games tab visibility and persist the config."""
        self._show_retro_games_tab = enabled
        self.save()

    def set_show_pc_games_tab(self, enabled: bool) -> None:
        """Set the PC Games tab visibility and persist the config."""
        self._show_pc_games_tab = enabled
        self.save()

    def set_show_watch_tab(self, enabled: bool) -> None:
        """Set the Watch tab visibility and persist the config."""
        self._show_watch_tab = enabled
        self.save()

    def set_show_listen_tab(self, enabled: bool) -> None:
        """Set the Listen tab visibility and persist the config."""
        self._show_listen_tab = enabled
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
                "token": self._plex_token or "",
                "server_id": self._plex_server_id or "",
                "user_id": self._plex_user_id or 0,
                "music_library_key": self._music_library_key,
            },
            "browser": {
                "command": self._browser_command,
            },
            "moonlight": {
                "command": self._moonlight_command,
                "host_uuid": self._moonlight_host_uuid,
            },
            "ui": {
                "video_snap_autoplay": self.video_snap_autoplay,
                "video_snap_delay_ms": self.video_snap_delay_ms,
                "show_network_indicator": self.show_network_indicator,
                "button_layout": self.button_layout,
            },
            "sort_preferences": {
                "retro_games": self._sort_retro_games,
                "steam_games": self._sort_steam_games,
                "moonlight_apps": self._sort_moonlight_apps,
                "plex_movies": self._sort_plex_movies,
                "plex_shows": self._sort_plex_shows,
                "plex_movie_genre": self._filter_plex_movie_genre,
                "plex_show_genre": self._filter_plex_show_genre,
            },
            "tabs": {
                "show_retro_games": self._show_retro_games_tab,
                "show_pc_games": self._show_pc_games_tab,
                "show_watch": self._show_watch_tab,
                "show_listen": self._show_listen_tab,
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
            token = plex.get("token", "")
            if token:
                self._plex_token = token
            server_id = plex.get("server_id", "")
            if server_id:
                self._plex_server_id = server_id
            user_id = plex.get("user_id", 0)
            if user_id:
                self._plex_user_id = int(user_id)
            self._music_library_key = plex.get("music_library_key", "")
            # Backward compatibility: old configs may have server_url — ignore it gracefully

        # browser section
        browser = raw.get("browser", {})
        if isinstance(browser, dict):
            command = browser.get("command", "")
            if command:
                self._browser_command = command

        # moonlight section
        moonlight = raw.get("moonlight", {})
        if isinstance(moonlight, dict):
            command = moonlight.get("command", "")
            if command:
                self._moonlight_command = command
            self._moonlight_host_uuid = moonlight.get("host_uuid", "")

        # ui section
        ui = raw.get("ui", {})
        if isinstance(ui, dict):
            if "video_snap_autoplay" in ui:
                self.video_snap_autoplay = bool(ui["video_snap_autoplay"])
            if "video_snap_delay_ms" in ui:
                self.video_snap_delay_ms = int(ui["video_snap_delay_ms"])
            if "show_network_indicator" in ui:
                self.show_network_indicator = bool(ui["show_network_indicator"])
            if "button_layout" in ui and ui["button_layout"] in ("standard", "alternate"):
                self.button_layout = ui["button_layout"]

        # sort_preferences section
        sort_prefs = raw.get("sort_preferences", {})
        if isinstance(sort_prefs, dict):
            self._sort_retro_games = sort_prefs.get("retro_games", "az")
            self._sort_steam_games = sort_prefs.get("steam_games", "az")
            self._sort_moonlight_apps = sort_prefs.get("moonlight_apps", "az")
            self._sort_plex_movies = sort_prefs.get("plex_movies", "")
            self._sort_plex_shows = sort_prefs.get("plex_shows", "")
            self._filter_plex_movie_genre = sort_prefs.get("plex_movie_genre", "")
            self._filter_plex_show_genre = sort_prefs.get("plex_show_genre", "")

        # tabs section
        tabs = raw.get("tabs", {})
        if isinstance(tabs, dict):
            if "show_retro_games" in tabs:
                self._show_retro_games_tab = bool(tabs["show_retro_games"])
            if "show_pc_games" in tabs:
                self._show_pc_games_tab = bool(tabs["show_pc_games"])
            if "show_watch" in tabs:
                self._show_watch_tab = bool(tabs["show_watch"])
            if "show_listen" in tabs:
                self._show_listen_tab = bool(tabs["show_listen"])


def ensure_config_dir() -> None:
    """Create the XDG config directory for htpcstation if it does not exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
