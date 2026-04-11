"""Pytest configuration for HTPC Station tests.

Ensures a QCoreApplication instance exists for the entire test session.
This is required for cross-thread Qt signal delivery (used by MoonlightLibrary
and PlexLibrary which use ThreadPoolExecutor + Qt signals).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

# Import once at module level to avoid repeated import lookups in the autouse fixture.
from unittest.mock import MagicMock, patch

import backend.config as _config_module
import backend.plex_library as _plex_lib_module
import backend.live_tv_library as _live_tv_lib_module
from backend.plex_library import PlexLibrary as _PlexLibrary


class _SyncExecutor:
    """Synchronous stand-in for ThreadPoolExecutor used in tests.

    Calling .submit(fn, *args, **kwargs) runs fn immediately on the calling
    thread, making disk-persistence tests deterministic.
    """

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def sync_config_write_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace Config's background write executor with a synchronous shim.

    Ensures that Config.save() completes before the test continues, so
    save/reload round-trip tests remain deterministic.
    """
    monkeypatch.setattr(_config_module, "_write_executor", _SyncExecutor())


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Create a QCoreApplication for the test session if one doesn't exist."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def isolate_plex_cache(tmp_path: Path, monkeypatch):
    """Redirect all Plex cache I/O to tmp_path for every test.

    Patches the module-level constants that are computed at import time,
    so tests never touch ~/.config/htpcstation/plex_cache/.

    Directories are NOT pre-created here; production code creates them on
    demand via mkdir(parents=True, exist_ok=True) calls in cache-path helpers.
    This avoids polluting tmp_path with directories that interfere with tests
    that use tmp_path as a ROM directory or other filesystem root.
    """
    plex_cache = tmp_path / "plex_cache"
    posters = plex_cache / "posters"

    monkeypatch.setattr(_plex_lib_module, "_PLEX_CACHE_DIR", plex_cache)
    monkeypatch.setattr(_plex_lib_module, "_POSTER_CACHE_DIR", posters)
    monkeypatch.setattr(_live_tv_lib_module, "_CACHE_DIR", plex_cache / "guide")
    monkeypatch.setattr(_PlexLibrary, "_migrate_cache_dirs", lambda self: None)


@pytest.fixture(autouse=True)
def _mock_probe_requests_get():
    """Prevent _probe_server_url from making real network calls.

    The probe does requests.get(url + "/identity", timeout=3) which stalls
    the test suite when the URL is unreachable. Stub it globally; tests that
    specifically test probe behavior patch requests.get themselves.
    """
    with patch.object(_plex_lib_module, "requests",
                      MagicMock(get=MagicMock(return_value=MagicMock(status_code=200)))):
        yield
