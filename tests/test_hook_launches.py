"""Tests for Task 002 — Hook all launch points into RecentlyPlayedManager.

Covers:
  - GameLibrary.launchGame: calls record() with correct retro args
  - GameLibrary.launchGame: no-op when recently_played is None
  - GameLibrary.launchGame: artwork is empty string when game has no image_path
  - SteamLibrary.launchGame: calls record() with correct steam args
  - SteamLibrary.launchGame: no-op when recently_played is None
  - SteamLibrary.launchGame: artwork empty when game has no image_path
  - MoonlightLibrary.launchApp: calls record() with correct moonlight args
  - MoonlightLibrary.launchApp: no-op when recently_played is None
  - MoonlightLibrary.launchApp: artwork empty when app has no image_path
  - PlexLibrary._on_mpv_launch_ready: calls record() with correct plexvideo args
  - PlexLibrary._on_mpv_launch_ready: no-op when recently_played is None
  - PlexLibrary._on_mpv_launch_ready: skips record when url is empty
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.steam_models import SteamGame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(system_path: Path, xml_body: str) -> None:
    content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
    (system_path / "gamelist.xml").write_text(content, encoding="utf-8")


def _mock_recently_played():
    """Return a minimal mock that behaves like RecentlyPlayedManager."""
    rp = MagicMock()
    return rp


# ---------------------------------------------------------------------------
# GameLibrary — retro game launch hook
# ---------------------------------------------------------------------------


class TestGameLibraryLaunchHook:
    def _make_library(self, tmp_path: Path, recently_played=None):
        from backend.config import Config
        from backend.launcher import Launcher
        from backend.library import GameLibrary

        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        rom_path = system_dir / "game.rom"
        rom_path.touch()
        _write_gamelist(
            system_dir,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="SNES", core="snes9x_libretro.so", extensions=[".smc"]
        )
        config.get_launch_command.return_value = ["retroarch", str(rom_path)]

        launcher = MagicMock(spec=Launcher)
        launcher.processFinished = MagicMock()
        launcher.processFinished.connect = MagicMock()

        library = GameLibrary(
            config, launcher=launcher, recently_played=recently_played
        )
        library.selectSystem("snes")
        return library

    def test_record_called_with_correct_args(self, tmp_path: Path) -> None:
        """launchGame calls record('retro', ...) with correct title, artwork, nav_params."""
        rp = _mock_recently_played()
        library = self._make_library(tmp_path, recently_played=rp)

        library.launchGame(0)

        rp.record.assert_called_once()
        source, title, artwork, nav_params = rp.record.call_args[0]
        assert source == "retro"
        assert title == "Test Game"
        assert isinstance(nav_params, dict)
        assert "rom_path" in nav_params
        assert nav_params["system_folder"] == "snes"

    def test_no_record_when_recently_played_is_none(self, tmp_path: Path) -> None:
        """launchGame does not raise and skips record() when recently_played is None."""
        library = self._make_library(tmp_path, recently_played=None)
        library.launchGame(0)  # should not raise

    def test_artwork_empty_when_no_image_path(self, tmp_path: Path) -> None:
        """artwork is '' when the game has no image_path."""
        rp = _mock_recently_played()
        library = self._make_library(tmp_path, recently_played=rp)

        library.launchGame(0)

        _, _, artwork, _ = rp.record.call_args[0]
        assert artwork == ""

    def test_artwork_file_uri_when_image_path_set(self, tmp_path: Path) -> None:
        """artwork is 'file://<path>' when the game has an image_path."""
        from backend.config import Config
        from backend.launcher import Launcher
        from backend.library import GameLibrary

        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        rom_path = system_dir / "game.rom"
        rom_path.touch()
        img_path = system_dir / "game.jpg"
        img_path.touch()
        _write_gamelist(
            system_dir,
            "<game>"
            "<path>./game.rom</path>"
            "<name>Art Game</name>"
            f"<image>{img_path}</image>"
            "</game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="SNES", core="snes9x_libretro.so", extensions=[".smc"]
        )
        config.get_launch_command.return_value = ["retroarch", str(rom_path)]

        launcher = MagicMock(spec=Launcher)
        launcher.processFinished = MagicMock()
        launcher.processFinished.connect = MagicMock()

        rp = _mock_recently_played()
        library = GameLibrary(config, launcher=launcher, recently_played=rp)
        library.selectSystem("snes")
        library.launchGame(0)

        _, _, artwork, _ = rp.record.call_args[0]
        assert artwork.startswith("file://")
        assert "game.jpg" in artwork


# ---------------------------------------------------------------------------
# SteamLibrary — Steam game launch hook
# ---------------------------------------------------------------------------


class TestSteamLibraryLaunchHook:
    def _make_library(self, recently_played=None, games=None):
        from backend.library import GameLibrary
        from backend.steam_library import SteamLibrary

        steam = SteamLibrary(recently_played=recently_played)
        if games is not None:
            steam._all_games = games
            steam._current_games = list(games)
        return steam

    def test_record_called_with_correct_args(self) -> None:
        """launchGame calls record('steam', ...) with correct title, artwork, nav_params."""
        game = SteamGame(
            app_id="440",
            name="Team Fortress 2",
            install_dir="tf",
            last_played=0,
            size_on_disk=0,
            image_path="/path/to/art.jpg",
        )
        rp = _mock_recently_played()
        steam = self._make_library(recently_played=rp, games=[game])

        with patch("PySide6.QtCore.QProcess.startDetached"):
            steam.launchGame("440")

        rp.record.assert_called_once()
        source, title, artwork, nav_params = rp.record.call_args[0]
        assert source == "steam"
        assert title == "Team Fortress 2"
        assert artwork == "file:///path/to/art.jpg"
        assert nav_params == {"app_id": "440"}

    def test_no_record_when_recently_played_is_none(self) -> None:
        """launchGame does not raise when recently_played is None."""
        game = SteamGame(app_id="440", name="TF2", install_dir="tf",
                         last_played=0, size_on_disk=0, image_path="")
        steam = self._make_library(recently_played=None, games=[game])
        with patch("PySide6.QtCore.QProcess.startDetached"):
            steam.launchGame("440")  # should not raise

    def test_artwork_empty_when_no_image_path(self) -> None:
        """artwork is '' when the game has no image_path."""
        game = SteamGame(app_id="440", name="TF2", install_dir="tf",
                         last_played=0, size_on_disk=0, image_path="")
        rp = _mock_recently_played()
        steam = self._make_library(recently_played=rp, games=[game])

        with patch("PySide6.QtCore.QProcess.startDetached"):
            steam.launchGame("440")

        _, _, artwork, _ = rp.record.call_args[0]
        assert artwork == ""

    def test_no_record_when_game_not_found(self) -> None:
        """record() is not called when the app_id doesn't match any game."""
        rp = _mock_recently_played()
        steam = self._make_library(recently_played=rp, games=[])

        with patch("PySide6.QtCore.QProcess.startDetached"):
            steam.launchGame("999")

        rp.record.assert_not_called()


# ---------------------------------------------------------------------------
# MoonlightLibrary — Moonlight app launch hook
# ---------------------------------------------------------------------------


class TestMoonlightLibraryLaunchHook:
    def _make_library(self, recently_played=None):
        from backend.moonlight_library import MoonlightLibrary
        from backend.moonlight_models import MoonlightApp

        lib = MoonlightLibrary(recently_played=recently_played)
        app = MoonlightApp(
            name="Cyberpunk 2077",
            host_uuid="host-uuid-1",
            image_path="/path/to/cyberpunk.jpg",
            last_played="",
        )
        lib._all_apps = [app]
        lib._current_apps = [app]
        return lib

    def test_record_called_with_correct_args(self) -> None:
        """launchApp calls record('moonlight', ...) with correct title, artwork, nav_params."""
        rp = _mock_recently_played()
        lib = self._make_library(recently_played=rp)

        with patch.object(lib._launcher, "launch"):
            lib.launchApp("192.168.1.100", "Cyberpunk 2077")

        rp.record.assert_called_once()
        source, title, artwork, nav_params = rp.record.call_args[0]
        assert source == "moonlight"
        assert title == "Cyberpunk 2077"
        assert artwork == "file:///path/to/cyberpunk.jpg"
        assert nav_params == {"host_address": "192.168.1.100", "app_name": "Cyberpunk 2077"}

    def test_no_record_when_recently_played_is_none(self) -> None:
        """launchApp does not raise when recently_played is None."""
        lib = self._make_library(recently_played=None)
        with patch.object(lib._launcher, "launch"):
            lib.launchApp("192.168.1.100", "Cyberpunk 2077")  # should not raise

    def test_artwork_empty_when_app_has_no_image(self) -> None:
        """artwork is '' when the app has no image_path."""
        from backend.moonlight_library import MoonlightLibrary
        from backend.moonlight_models import MoonlightApp

        rp = _mock_recently_played()
        lib = MoonlightLibrary(recently_played=rp)
        app = MoonlightApp(
            name="Game X",
            host_uuid="h1",
            image_path="",
            last_played="",
        )
        lib._all_apps = [app]
        lib._current_apps = [app]

        with patch.object(lib._launcher, "launch"):
            lib.launchApp("10.0.0.1", "Game X")

        _, _, artwork, _ = rp.record.call_args[0]
        assert artwork == ""

    def test_artwork_empty_when_app_not_found(self) -> None:
        """artwork is '' when no app matches app_name."""
        from backend.moonlight_library import MoonlightLibrary

        rp = _mock_recently_played()
        lib = MoonlightLibrary(recently_played=rp)
        lib._all_apps = []

        with patch.object(lib._launcher, "launch"):
            lib.launchApp("10.0.0.1", "Unknown App")

        _, _, artwork, _ = rp.record.call_args[0]
        assert artwork == ""


# ---------------------------------------------------------------------------
# PlexLibrary — Plex video launch hook via _on_mpv_launch_ready
# ---------------------------------------------------------------------------


class TestPlexLibraryLaunchHook:
    def _make_plex_library(self, recently_played=None):
        from backend.config import Config
        from backend.plex_library import PlexLibrary

        config = MagicMock(spec=Config)
        config.plex_url = ""
        config.plex_token = ""
        config.browser_command = ""
        config.button_layout = "xbox"
        config.plex_transcode_mode = "auto"
        config.hw_decode_codecs = []

        lib = PlexLibrary(config, recently_played=recently_played)
        return lib

    def test_record_called_on_successful_launch(self) -> None:
        """_on_mpv_launch_ready calls record('plexvideo', ...) with pending metadata."""
        rp = _mock_recently_played()
        lib = self._make_plex_library(recently_played=rp)

        # Set up pending state as the worker would
        lib._pending_play_rating_key = "12345"
        lib._pending_record_title = "Breaking Bad"
        lib._pending_record_artwork = "file:///posters/bb.jpg"
        lib._pending_record_media_type = "episode"

        with patch.object(lib._mpv_launcher, "launch"):
            lib._on_mpv_launch_ready(
                url="http://plex/stream",
                title="Breaking Bad — Pilot",
                start_ms=0,
                duration_ms=3600000,
                part_id=1,
                intro_end_ms=0,
            )

        rp.record.assert_called_once()
        source, title, artwork, nav_params = rp.record.call_args[0]
        assert source == "plexvideo"
        assert title == "Breaking Bad"
        assert artwork == "file:///posters/bb.jpg"
        assert nav_params == {"rating_key": "12345", "media_type": "episode"}

    def test_no_record_when_url_empty(self) -> None:
        """_on_mpv_launch_ready skips record() when url is empty (failed stream)."""
        rp = _mock_recently_played()
        lib = self._make_plex_library(recently_played=rp)
        lib._pending_record_title = "Some Movie"

        # Empty URL → early return
        lib._on_mpv_launch_ready(
            url="",
            title="",
            start_ms=0,
            duration_ms=0,
            part_id=0,
            intro_end_ms=0,
        )

        rp.record.assert_not_called()

    def test_no_record_when_recently_played_is_none(self) -> None:
        """_on_mpv_launch_ready does not raise when recently_played is None."""
        lib = self._make_plex_library(recently_played=None)
        lib._pending_play_rating_key = "1"
        lib._pending_record_title = "Movie"
        lib._pending_record_artwork = ""
        lib._pending_record_media_type = "movie"

        with patch.object(lib._mpv_launcher, "launch"):
            lib._on_mpv_launch_ready(
                url="http://plex/stream",
                title="Movie",
                start_ms=0,
                duration_ms=0,
                part_id=0,
                intro_end_ms=0,
            )  # should not raise
