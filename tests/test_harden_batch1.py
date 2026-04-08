"""Tests for Task 001 — Batch 1 crash and stuck-UI fixes.

Covers:
  - C1: _mpvLaunchReady emitted with exactly 6 args on empty stream URL
  - C3: set_plex_player ignores invalid values and does not call save()
  - C4: _save_my_list swallows OSError without propagating
  - M9: Config.save() swallows OSError without propagating
  - H6: _artists_cache_path() returns a path under CONFIG_DIR, not hardcoded home
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

_FAKE_SERVER_RESOURCES = [
    {
        "clientIdentifier": "server123",
        "name": "Test Server",
        "owned": True,
        "provides": "server",
        "connections": [
            {
                "uri": "http://server:32400",
                "local": True,
                "relay": False,
                "protocol": "http",
            }
        ],
    }
]


def _make_plex_account_mock():
    mock_cls = MagicMock()
    mock_cls.return_value.get_resources.return_value = _FAKE_SERVER_RESOURCES
    mock_cls.return_value.switch_user.return_value = None
    return mock_cls


def _make_lib(tmp_path: Path):
    """Return a PlexLibrary with CONFIG_DIR and _PLEX_CACHE_DIR redirected to tmp_path."""
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    plex_cache = tmp_path / "plex_cache"
    plex_cache.mkdir(parents=True, exist_ok=True)

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.plex_library.CONFIG_DIR", tmp_path), \
         patch("backend.plex_library._PLEX_CACHE_DIR", plex_cache), \
         patch("backend.plex_library._POSTER_CACHE_DIR", plex_cache / "posters"):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)

    return lib


@pytest.fixture(autouse=True)
def _restore_config_dir():
    """Kept for backward compatibility; isolation is now handled by conftest.py."""
    yield


def _make_config(tmp_path: Path):
    """Return a Config instance with CONFIG_FILE and CONFIG_DIR redirected to tmp_path."""
    from backend.config import Config

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


# ---------------------------------------------------------------------------
# C1 — _mpvLaunchReady emitted with exactly 6 args on empty stream URL
# ---------------------------------------------------------------------------


class TestC1MpvLaunchReadyArgCount:
    """_mpvLaunchReady must be emitted with exactly 6 args (matching Signal declaration)."""

    def test_empty_url_emits_six_args(self, tmp_path: Path) -> None:
        """When get_stream_url returns empty, _mpvLaunchReady fires with 6 zero/empty args."""
        lib = _make_lib(tmp_path)

        mock_client = MagicMock()
        mock_client.get_stream_url.return_value = ("", 0)
        lib._client = mock_client

        received: list = []

        def _capture(url, title, start_ms, duration_ms, part_id, intro_end_ms):
            received.append((url, title, start_ms, duration_ms, part_id, intro_end_ms))

        lib._mpvLaunchReady.connect(_capture)

        lib.playWithMpv("123", 0)
        lib._executor.shutdown(wait=True)

        # The signal is cross-thread; process pending Qt events to deliver it.
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        assert len(received) == 1, "Signal should have been emitted exactly once"
        url, title, start_ms, duration_ms, part_id, intro_end_ms = received[0]
        assert url == ""
        assert title == ""
        assert start_ms == 0
        assert duration_ms == 0
        assert part_id == 0
        assert intro_end_ms == 0


# ---------------------------------------------------------------------------
# C3 — set_plex_player ignores invalid values
# ---------------------------------------------------------------------------


class TestC3SetPlexPlayerValidation:
    """set_plex_player must reject invalid values without calling save()."""

    def test_invalid_value_is_ignored(self, tmp_path: Path) -> None:
        """set_plex_player('invalid') leaves _plex_player unchanged."""
        config = _make_config(tmp_path)
        original = config.plex_player  # default value

        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config.set_plex_player("invalid")

        assert config.plex_player == original

    def test_invalid_value_does_not_call_save(self, tmp_path: Path) -> None:
        """set_plex_player('invalid') must not persist anything."""
        config = _make_config(tmp_path)

        with patch.object(config, "save") as mock_save, \
             patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config.set_plex_player("invalid")

        mock_save.assert_not_called()

    def test_valid_value_mpv_is_accepted(self, tmp_path: Path) -> None:
        """set_plex_player('mpv') is accepted and persisted."""
        config = _make_config(tmp_path)

        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config.set_plex_player("mpv")

        assert config.plex_player == "mpv"

    def test_valid_value_browser_is_accepted(self, tmp_path: Path) -> None:
        """set_plex_player('browser') is accepted and persisted."""
        config = _make_config(tmp_path)

        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config.set_plex_player("browser")

        assert config.plex_player == "browser"


# ---------------------------------------------------------------------------
# C4 — _save_my_list swallows OSError
# ---------------------------------------------------------------------------


class TestC4SaveMyListOSError:
    """_save_my_list must not propagate OSError."""

    def test_oserror_does_not_propagate(self, tmp_path: Path) -> None:
        """When open() raises OSError, _save_my_list logs and returns without raising."""
        lib = _make_lib(tmp_path)

        with patch("builtins.open", side_effect=OSError("disk full")):
            # Must not raise
            lib._save_my_list([])

    def test_mkdir_oserror_does_not_propagate(self, tmp_path: Path) -> None:
        """When mkdir raises OSError, _save_my_list logs and returns without raising."""
        lib = _make_lib(tmp_path)

        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            # Must not raise
            lib._save_my_list([])


# ---------------------------------------------------------------------------
# M9 — Config.save() swallows OSError
# ---------------------------------------------------------------------------


class TestM9ConfigSaveOSError:
    """Config.save() must not propagate OSError from write_text."""

    def test_write_text_oserror_does_not_propagate(self, tmp_path: Path) -> None:
        """When write_text raises OSError, save() logs and returns without raising."""
        config = _make_config(tmp_path)

        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path), \
             patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            # Must not raise
            config.save()

    def test_ensure_config_dir_oserror_does_not_propagate(self, tmp_path: Path) -> None:
        """When ensure_config_dir raises OSError, save() logs and returns without raising."""
        config = _make_config(tmp_path)

        with patch("backend.config.CONFIG_FILE", tmp_path / "config.json"), \
             patch("backend.config.CONFIG_DIR", tmp_path), \
             patch("backend.config.ensure_config_dir", side_effect=OSError("read-only fs")):
            # Must not raise
            config.save()


# ---------------------------------------------------------------------------
# H6 — _artists_cache_path uses CONFIG_DIR, not hardcoded home
# ---------------------------------------------------------------------------


class TestH6ArtistsCachePath:
    """_artists_cache_path must return a path under CONFIG_DIR."""

    def test_path_starts_with_config_dir(self, tmp_path: Path) -> None:
        """_artists_cache_path() returns a path under CONFIG_DIR, not ~/.config/htpcstation."""
        import backend.plex_library as plex_lib_module

        lib = _make_lib(tmp_path)
        # CONFIG_DIR is already redirected to tmp_path by _make_lib

        result = lib._artists_cache_path()

        assert str(result).startswith(str(tmp_path)), (
            f"Expected path under {tmp_path}, got {result}"
        )

    def test_path_does_not_use_hardcoded_home(self, tmp_path: Path) -> None:
        """_artists_cache_path() must not use Path.home() / '.config' / 'htpcstation'."""
        lib = _make_lib(tmp_path)

        hardcoded = Path.home() / ".config" / "htpcstation" / "poster_cache"
        result = lib._artists_cache_path()

        assert not str(result).startswith(str(hardcoded)), (
            f"Path still uses hardcoded home: {result}"
        )
