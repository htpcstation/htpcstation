"""Tests for Task 007 — _migrate_cache_dirs() one-time migration.

Covers:
  - poster_cache/ → plex_cache/posters/ (rename when new dir absent)
  - poster_cache/ → plex_cache/posters/ (merge when both exist, skip conflicts)
  - plex_mylist.json → plex_cache/plex_mylist.json
  - livetv_cache/ → plex_cache/guide/ (rename when new dir absent)
  - livetv_cache/ → plex_cache/guide/ (merge when both exist, skip conflicts)
  - No-op when old paths do not exist
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
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
    import backend.plex_library as plex_lib_module
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    plex_lib_module.CONFIG_DIR = tmp_path
    plex_lib_module._PLEX_CACHE_DIR = tmp_path / "plex_cache"

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)

    return lib


@pytest.fixture(autouse=True)
def _restore_module_globals():
    """Restore backend.plex_library module globals after each test."""
    import backend.plex_library as m
    import backend.config as config_module
    original_config_dir = m.CONFIG_DIR
    original_plex_cache_dir = m._PLEX_CACHE_DIR
    yield
    m.CONFIG_DIR = original_config_dir
    m._PLEX_CACHE_DIR = original_plex_cache_dir


# ---------------------------------------------------------------------------
# poster_cache/ → plex_cache/posters/
# ---------------------------------------------------------------------------


class TestMigratePosterCache:
    def test_renames_poster_cache_to_plex_cache_posters(self, tmp_path: Path) -> None:
        """poster_cache/ is renamed to plex_cache/posters/ when new dir does not exist."""
        old_dir = tmp_path / "poster_cache"
        old_dir.mkdir()
        (old_dir / "abc123.jpg").write_bytes(b"fake image")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        new_dir = tmp_path / "plex_cache" / "posters"
        assert new_dir.exists()
        assert (new_dir / "abc123.jpg").exists()
        assert not old_dir.exists()

    def test_merges_poster_cache_when_both_exist(self, tmp_path: Path) -> None:
        """Files from poster_cache/ are moved to plex_cache/posters/ when both exist."""
        old_dir = tmp_path / "poster_cache"
        old_dir.mkdir()
        (old_dir / "new_file.jpg").write_bytes(b"new")

        new_dir = tmp_path / "plex_cache" / "posters"
        new_dir.mkdir(parents=True)
        (new_dir / "existing.jpg").write_bytes(b"existing")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        assert (new_dir / "new_file.jpg").exists()
        assert (new_dir / "existing.jpg").exists()
        # Old dir should be removed (was empty after move)
        assert not old_dir.exists()

    def test_does_not_overwrite_existing_file_in_merge(self, tmp_path: Path) -> None:
        """Conflicting files in plex_cache/posters/ are not overwritten during merge."""
        old_dir = tmp_path / "poster_cache"
        old_dir.mkdir()
        (old_dir / "conflict.jpg").write_bytes(b"old content")

        new_dir = tmp_path / "plex_cache" / "posters"
        new_dir.mkdir(parents=True)
        (new_dir / "conflict.jpg").write_bytes(b"new content")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        # New content should be preserved (old file skipped)
        assert (new_dir / "conflict.jpg").read_bytes() == b"new content"

    def test_noop_when_poster_cache_absent(self, tmp_path: Path) -> None:
        """No error when poster_cache/ does not exist."""
        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()  # should not raise


# ---------------------------------------------------------------------------
# plex_mylist.json → plex_cache/plex_mylist.json
# ---------------------------------------------------------------------------


class TestMigrateMyList:
    def test_moves_mylist_to_plex_cache(self, tmp_path: Path) -> None:
        """plex_mylist.json is moved to plex_cache/plex_mylist.json."""
        import json as _json
        old_file = tmp_path / "plex_mylist.json"
        content = _json.dumps([{"ratingKey": "1", "title": "Dune", "type": "movie",
                                 "posterLocal": "", "grandparentTitle": ""}])
        old_file.write_text(content, encoding="utf-8")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        new_file = tmp_path / "plex_cache" / "plex_mylist.json"
        assert new_file.exists()
        assert not old_file.exists()
        assert new_file.read_text(encoding="utf-8") == content

    def test_does_not_overwrite_existing_mylist(self, tmp_path: Path) -> None:
        """Old plex_mylist.json is not moved if plex_cache/plex_mylist.json already exists."""
        import json as _json
        old_content = _json.dumps([{"ratingKey": "old", "title": "Old", "type": "movie",
                                     "posterLocal": "", "grandparentTitle": ""}])
        new_content = _json.dumps([{"ratingKey": "new", "title": "New", "type": "movie",
                                     "posterLocal": "", "grandparentTitle": ""}])

        old_file = tmp_path / "plex_mylist.json"
        old_file.write_text(old_content, encoding="utf-8")

        new_dir = tmp_path / "plex_cache"
        new_dir.mkdir(parents=True)
        new_file = new_dir / "plex_mylist.json"
        new_file.write_text(new_content, encoding="utf-8")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        # New file should be preserved
        assert new_file.read_text(encoding="utf-8") == new_content
        # Old file should still exist (not moved)
        assert old_file.exists()

    def test_noop_when_mylist_absent(self, tmp_path: Path) -> None:
        """No error when plex_mylist.json does not exist."""
        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()  # should not raise


# ---------------------------------------------------------------------------
# livetv_cache/ → plex_cache/guide/
# ---------------------------------------------------------------------------


class TestMigrateLiveTvCache:
    def test_renames_livetv_cache_to_plex_cache_guide(self, tmp_path: Path) -> None:
        """livetv_cache/ is renamed to plex_cache/guide/ when new dir does not exist."""
        old_dir = tmp_path / "livetv_cache"
        old_dir.mkdir()
        (old_dir / "guide_cache.json").write_text("[]", encoding="utf-8")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        new_dir = tmp_path / "plex_cache" / "guide"
        assert new_dir.exists()
        assert (new_dir / "guide_cache.json").exists()
        assert not old_dir.exists()

    def test_merges_livetv_cache_when_both_exist(self, tmp_path: Path) -> None:
        """Files from livetv_cache/ are moved to plex_cache/guide/ when both exist."""
        old_dir = tmp_path / "livetv_cache"
        old_dir.mkdir()
        (old_dir / "new_guide.json").write_text("[]", encoding="utf-8")

        new_dir = tmp_path / "plex_cache" / "guide"
        new_dir.mkdir(parents=True)
        (new_dir / "existing.json").write_text("{}", encoding="utf-8")

        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()

        assert (new_dir / "new_guide.json").exists()
        assert (new_dir / "existing.json").exists()
        assert not old_dir.exists()

    def test_noop_when_livetv_cache_absent(self, tmp_path: Path) -> None:
        """No error when livetv_cache/ does not exist."""
        lib = _make_lib(tmp_path)
        lib._migrate_cache_dirs()  # should not raise
