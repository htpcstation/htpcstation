"""Tests for Task 010 — Emulator Launch & Lifecycle.

Covers:
  - write_game_stats: creates/updates stats fields in gamelist.xml
  - write_game_stats: removes <favorite> when favorite=False
  - write_game_stats: handles missing gamelist.xml gracefully
  - write_game_stats: handles game not found in gamelist.xml gracefully
  - GameListModel.notify_game_changed: emits dataChanged for valid row
  - GameLibrary.toggleFavorite: flips favorite and writes gamelist.xml
  - GameLibrary.launchGame: no-op when no launcher configured
"""

from __future__ import annotations

import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.gamelist import write_game_stats
from backend.models import Game


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_gamelist(system_path: Path, xml_body: str) -> None:
    """Write a minimal gamelist.xml to *system_path*."""
    content = f"<?xml version='1.0' encoding='utf-8'?>\n<gameList>{xml_body}</gameList>"
    (system_path / "gamelist.xml").write_text(content, encoding="utf-8")


def _make_game(system_path: Path, rom_name: str = "game.rom", **kwargs) -> Game:
    """Return a Game with sensible defaults for testing."""
    defaults = dict(
        path=system_path / rom_name,
        name="Test Game",
        play_count=0,
        game_time=0,
        last_played="",
        favorite=False,
        system_folder="snes",
    )
    defaults.update(kwargs)
    return Game(**defaults)


# ---------------------------------------------------------------------------
# write_game_stats
# ---------------------------------------------------------------------------


class TestWriteGameStats:
    def test_updates_playcount_gametime_lastplayed(self, tmp_path: Path) -> None:
        """Stats fields are written to the matching <game> element."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )
        game = _make_game(tmp_path, play_count=5, game_time=3600, last_played="20260321T120000")

        write_game_stats(tmp_path, game)

        root = ET.parse(tmp_path / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        assert elem.findtext("playcount") == "5"
        assert elem.findtext("gametime") == "3600"
        assert elem.findtext("lastplayed") == "20260321T120000"

    def test_sets_favorite_true(self, tmp_path: Path) -> None:
        """<favorite>true</favorite> is written when game.favorite is True."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )
        game = _make_game(tmp_path, favorite=True)

        write_game_stats(tmp_path, game)

        root = ET.parse(tmp_path / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        assert elem.findtext("favorite") == "true"

    def test_removes_favorite_when_false(self, tmp_path: Path) -> None:
        """<favorite> element is removed when game.favorite is False."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Test Game</name><favorite>true</favorite></game>",
        )
        game = _make_game(tmp_path, favorite=False)

        write_game_stats(tmp_path, game)

        root = ET.parse(tmp_path / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        assert elem.find("favorite") is None

    def test_creates_lastplayed_when_empty(self, tmp_path: Path) -> None:
        """When game.last_played is empty, a timestamp is generated automatically."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )
        game = _make_game(tmp_path, last_played="")

        write_game_stats(tmp_path, game)

        root = ET.parse(tmp_path / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        lp = elem.findtext("lastplayed")
        assert lp is not None and len(lp) == 15  # YYYYMMDDTHHMMSS

    def test_missing_gamelist_logs_warning(self, tmp_path: Path, caplog) -> None:
        """Missing gamelist.xml is handled gracefully (no exception, warning logged)."""
        import logging

        game = _make_game(tmp_path)

        with caplog.at_level(logging.WARNING, logger="backend.gamelist"):
            write_game_stats(tmp_path, game)  # should not raise

        assert any("gamelist.xml" in r.message for r in caplog.records)

    def test_game_not_found_logs_warning(self, tmp_path: Path, caplog) -> None:
        """When the game's path is not in gamelist.xml, a warning is logged."""
        import logging

        _write_gamelist(
            tmp_path,
            "<game><path>./other.rom</path><name>Other Game</name></game>",
        )
        game = _make_game(tmp_path, rom_name="missing.rom")

        with caplog.at_level(logging.WARNING, logger="backend.gamelist"):
            write_game_stats(tmp_path, game)

        assert any("missing.rom" in r.message for r in caplog.records)

    def test_updates_existing_playcount_element(self, tmp_path: Path) -> None:
        """An existing <playcount> element is updated, not duplicated."""
        _write_gamelist(
            tmp_path,
            "<game><path>./game.rom</path><name>Test Game</name><playcount>2</playcount></game>",
        )
        game = _make_game(tmp_path, play_count=7)

        write_game_stats(tmp_path, game)

        root = ET.parse(tmp_path / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        playcounts = elem.findall("playcount")
        assert len(playcounts) == 1
        assert playcounts[0].text == "7"


# ---------------------------------------------------------------------------
# GameListModel.notify_game_changed
# ---------------------------------------------------------------------------


class TestGameListModelNotifyGameChanged:
    def test_emits_data_changed_for_valid_row(self) -> None:
        """notify_game_changed emits dataChanged for a valid row index."""
        from backend.library import GameListModel

        game = Game(path=Path("/roms/game.rom"), name="Game", system_folder="snes")
        model = GameListModel([game])

        received: list = []
        model.dataChanged.connect(lambda tl, br, roles: received.append((tl.row(), br.row())))

        model.notify_game_changed(0)

        assert len(received) == 1
        assert received[0] == (0, 0)

    def test_no_emit_for_out_of_range_row(self) -> None:
        """notify_game_changed does nothing for an out-of-range index."""
        from backend.library import GameListModel

        model = GameListModel([])

        received: list = []
        model.dataChanged.connect(lambda tl, br, roles: received.append(True))

        model.notify_game_changed(0)
        model.notify_game_changed(-1)

        assert received == []


# ---------------------------------------------------------------------------
# GameLibrary.toggleFavorite
# ---------------------------------------------------------------------------


class TestGameLibraryToggleFavorite:
    def test_toggles_favorite_and_writes_gamelist(self, tmp_path: Path) -> None:
        """toggleFavorite flips the favorite flag and calls write_game_stats."""
        from backend.config import Config
        from backend.library import GameLibrary

        # Set up a minimal ROM directory with a gamelist.xml
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
        config.get_system.return_value = MagicMock(display_name="Super Nintendo", core="snes9x_libretro.so", extensions=[".smc"])

        library = GameLibrary(config)
        library.selectSystem("snes")

        # Initially not favorite
        games = library._games_model._games
        assert len(games) == 1
        assert games[0].favorite is False

        library.toggleFavorite(0)

        assert games[0].favorite is True

        # Verify written to disk
        root = ET.parse(system_dir / "gamelist.xml").getroot()
        elem = root.find("game")
        assert elem is not None
        assert elem.findtext("favorite") == "true"

        # Toggle back
        library.toggleFavorite(0)
        assert games[0].favorite is False

        root2 = ET.parse(system_dir / "gamelist.xml").getroot()
        elem2 = root2.find("game")
        assert elem2 is not None
        assert elem2.find("favorite") is None

    def test_toggle_out_of_range_is_noop(self, tmp_path: Path) -> None:
        """toggleFavorite with an out-of-range index does nothing."""
        from backend.config import Config
        from backend.library import GameLibrary

        config = MagicMock(spec=Config)
        config.rom_directory = None

        library = GameLibrary(config)
        # Should not raise
        library.toggleFavorite(0)
        library.toggleFavorite(-1)

    def test_favorite_toggled_signal_emitted(self, tmp_path: Path) -> None:
        """toggleFavorite emits favoriteToggled(bool) with the new favorite state."""
        from backend.config import Config
        from backend.library import GameLibrary

        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        (system_dir / "game.rom").touch()
        _write_gamelist(
            system_dir,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(
            display_name="Super Nintendo", core="snes9x_libretro.so", extensions=[".smc"]
        )

        library = GameLibrary(config)
        library.selectSystem("snes")

        received: list[bool] = []
        library.favoriteToggled.connect(lambda is_fav: received.append(is_fav))

        library.toggleFavorite(0)
        assert received == [True]

        library.toggleFavorite(0)
        assert received == [True, False]


# ---------------------------------------------------------------------------
# GameLibrary.launchGame
# ---------------------------------------------------------------------------


class TestGameLibraryLaunchGame:
    def test_launch_without_launcher_logs_warning(self, tmp_path: Path, caplog) -> None:
        """launchGame logs a warning when no launcher is configured."""
        import logging
        from backend.config import Config
        from backend.library import GameLibrary

        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        (system_dir / "game.rom").touch()
        _write_gamelist(
            system_dir,
            "<game><path>./game.rom</path><name>Test Game</name></game>",
        )

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(display_name="SNES", core="snes9x_libretro.so", extensions=[".smc"])

        library = GameLibrary(config, launcher=None)
        library.selectSystem("snes")

        with caplog.at_level(logging.WARNING, logger="backend.library"):
            library.launchGame(0)

        assert any("no launcher" in r.message for r in caplog.records)

    def test_launch_calls_launcher_with_command(self, tmp_path: Path) -> None:
        """launchGame calls launcher.launch() with the correct command."""
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
        config.get_system.return_value = MagicMock(display_name="SNES", core="snes9x_libretro.so", extensions=[".smc"])
        config.get_launch_command.return_value = ["retroarch", "-L", "snes9x_libretro.so", str(rom_path)]

        mock_launcher = MagicMock(spec=Launcher)
        mock_launcher.processFinished = MagicMock()
        mock_launcher.processFinished.connect = MagicMock()

        library = GameLibrary(config, launcher=mock_launcher)
        library.selectSystem("snes")
        library.launchGame(0)

        mock_launcher.launch.assert_called_once()
        call_args = mock_launcher.launch.call_args[0][0]
        assert "retroarch" in call_args[0]

    def test_active_game_set_optimistically_before_launch(self, tmp_path: Path) -> None:
        """_active_game is set before launch() returns (optimistic async tracking)."""
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
        config.get_system.return_value = MagicMock(display_name="SNES", core="snes9x_libretro.so", extensions=[".smc"])
        config.get_launch_command.return_value = ["retroarch", "-L", "snes9x_libretro.so", str(rom_path)]

        active_game_during_launch = []

        def capture_active_game(command):
            active_game_during_launch.append(library._active_game)

        mock_launcher = MagicMock(spec=Launcher)
        mock_launcher.processFinished = MagicMock()
        mock_launcher.processFinished.connect = MagicMock()
        mock_launcher.launch.side_effect = capture_active_game

        library = GameLibrary(config, launcher=mock_launcher)
        library.selectSystem("snes")
        library.launchGame(0)

        # _active_game must be set before launch() is called
        assert len(active_game_during_launch) == 1
        assert active_game_during_launch[0] is not None
        assert active_game_during_launch[0].name == "Test Game"

    def test_launch_out_of_range_is_noop(self, tmp_path: Path) -> None:
        """launchGame with an out-of-range index does nothing."""
        from backend.config import Config
        from backend.launcher import Launcher
        from backend.library import GameLibrary

        config = MagicMock(spec=Config)
        config.rom_directory = None

        mock_launcher = MagicMock(spec=Launcher)
        mock_launcher.processFinished = MagicMock()
        mock_launcher.processFinished.connect = MagicMock()

        library = GameLibrary(config, launcher=mock_launcher)
        library.launchGame(0)

        mock_launcher.launch.assert_not_called()


# ---------------------------------------------------------------------------
# Launcher — async signal-based start
# ---------------------------------------------------------------------------


class TestLauncherAsyncStart:
    def test_launch_returns_none(self) -> None:
        """launch() returns None — it is now a void async operation."""
        from backend.launcher import Launcher
        from PySide6.QtCore import QProcess

        launcher = Launcher()
        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            result = launcher.launch(["echo", "hello"])
        assert result is None

    def test_launch_empty_command_is_noop(self) -> None:
        """launch() with an empty command does nothing and returns None."""
        from backend.launcher import Launcher

        launcher = Launcher()
        result = launcher.launch([])
        assert result is None
        assert launcher._process is None

    def test_on_started_emits_process_started(self) -> None:
        """_on_started emits processStarted signal."""
        from backend.launcher import Launcher
        from PySide6.QtCore import QProcess

        launcher = Launcher()

        received: list[bool] = []
        launcher.processStarted.connect(lambda: received.append(True))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(["echo", "hello"])
            launcher._on_started()

        assert received == [True]

    def test_on_error_occurred_failed_to_start_emits_process_finished(self) -> None:
        """_on_error_occurred(FailedToStart) emits processFinished(-1, 0) and clears _process."""
        from backend.launcher import Launcher
        from PySide6.QtCore import QProcess

        launcher = Launcher()

        received: list[tuple] = []
        launcher.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(["echo", "hello"])
            assert launcher._process is not None
            launcher._on_error_occurred(QProcess.ProcessError.FailedToStart)

        assert received == [(-1, 0)]
        assert launcher._process is None

    def test_on_error_occurred_non_failed_to_start_is_ignored(self) -> None:
        """_on_error_occurred for non-FailedToStart errors does not emit processFinished."""
        from backend.launcher import Launcher
        from PySide6.QtCore import QProcess

        launcher = Launcher()

        received: list[tuple] = []
        launcher.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        with patch.object(QProcess, "start"), \
             patch.object(QProcess, "state", return_value=QProcess.ProcessState.NotRunning):
            launcher.launch(["echo", "hello"])
            launcher._on_error_occurred(QProcess.ProcessError.Crashed)

        assert received == []

    def test_process_finished_skips_notify_when_model_replaced(self, tmp_path: Path) -> None:
        """_on_process_finished skips notify_game_changed when the user navigated away.

        If the user switches to a different system while the emulator is running,
        _games_model is replaced by _apply_sort_filter.  The notification must be
        skipped so we don't fire dataChanged on the wrong (new) model.
        """
        from backend.config import Config
        from backend.launcher import Launcher
        from backend.library import GameLibrary

        # Two systems so we can navigate between them
        snes_dir = tmp_path / "snes"
        snes_dir.mkdir()
        (snes_dir / "game.rom").touch()
        _write_gamelist(snes_dir, "<game><path>./game.rom</path><name>SNES Game</name></game>")

        nes_dir = tmp_path / "nes"
        nes_dir.mkdir()
        (nes_dir / "other.rom").touch()
        _write_gamelist(nes_dir, "<game><path>./other.rom</path><name>NES Game</name></game>")

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(display_name="System", core="core.so", extensions=[".rom"])
        config.get_launch_command.return_value = ["retroarch", str(snes_dir / "game.rom")]

        mock_launcher = MagicMock(spec=Launcher)
        mock_launcher.processFinished = MagicMock()
        mock_launcher.processFinished.connect = MagicMock()

        library = GameLibrary(config, launcher=mock_launcher)
        library.selectSystem("snes")
        library.launchGame(0)

        # Capture the model that was active at launch time
        launch_model = library._active_games_model

        # User navigates to a different system while the emulator is running
        library.selectSystem("nes")

        # The games model must have been replaced
        assert library._games_model is not launch_model

        # Track dataChanged emissions on the *new* model
        new_model_notifications: list = []
        library._games_model.dataChanged.connect(
            lambda tl, br, roles: new_model_notifications.append((tl.row(), br.row()))
        )

        # Simulate the emulator finishing
        library._on_process_finished(0, 120)

        # notify_game_changed must NOT have fired on the new (wrong) model
        assert new_model_notifications == []

        # Stats must still have been updated on the Game object
        snes_game = library._systems_by_folder["snes"].games[0]
        assert snes_game.play_count == 1
        assert snes_game.game_time == 120

    def test_process_finished_notifies_when_model_unchanged(self, tmp_path: Path) -> None:
        """_on_process_finished calls notify_game_changed when the model hasn't changed."""
        from backend.config import Config
        from backend.launcher import Launcher
        from backend.library import GameLibrary

        system_dir = tmp_path / "snes"
        system_dir.mkdir()
        (system_dir / "game.rom").touch()
        _write_gamelist(system_dir, "<game><path>./game.rom</path><name>Test Game</name></game>")

        config = MagicMock(spec=Config)
        config.rom_directory = tmp_path
        config.get_system.return_value = MagicMock(display_name="SNES", core="core.so", extensions=[".rom"])
        config.get_launch_command.return_value = ["retroarch", str(system_dir / "game.rom")]

        mock_launcher = MagicMock(spec=Launcher)
        mock_launcher.processFinished = MagicMock()
        mock_launcher.processFinished.connect = MagicMock()

        library = GameLibrary(config, launcher=mock_launcher)
        library.selectSystem("snes")
        library.launchGame(0)

        # Track dataChanged on the current model (user did NOT navigate away)
        notifications: list = []
        library._games_model.dataChanged.connect(
            lambda tl, br, roles: notifications.append((tl.row(), br.row()))
        )

        library._on_process_finished(0, 60)

        # notify_game_changed SHOULD have fired
        assert len(notifications) == 1
        assert notifications[0] == (0, 0)

    def test_launch_ignores_when_process_already_running(self) -> None:
        """launch() is a no-op when a process is already running."""
        from backend.launcher import Launcher
        from PySide6.QtCore import QProcess

        launcher = Launcher()

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.Running
        launcher._process = mock_process

        result = launcher.launch(["echo", "hello"])
        assert result is None
        # _process should still be the original mock (no new process created)
        assert launcher._process is mock_process
