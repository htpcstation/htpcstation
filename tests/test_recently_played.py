"""Tests for RecentlyPlayedManager.

Covers:
  - record(): de-duplication by source + nav_params
  - record(): prepends new entry (most recent first)
  - record(): trims list to 50 entries
  - record(): artwork normalisation (prepend file://)
  - record(): persists to disk and emits changed()
  - getRecent(): returns at most 5 entries
  - __init__: loads existing JSON from disk on construction
  - __init__: tolerates missing or corrupt JSON file
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import backend.recently_played as rp_module
from backend.recently_played import RecentlyPlayedManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def redirect_history_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all I/O to a temporary path for each test."""
    history_path = tmp_path / "recently_played.json"
    monkeypatch.setattr(rp_module, "_HISTORY_PATH", history_path)
    return history_path


class _SyncExecutor:
    """Synchronous stand-in for ThreadPoolExecutor used in tests."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def sync_write_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the background write executor with a synchronous shim so that
    disk-persistence tests are deterministic and do not race."""
    monkeypatch.setattr(rp_module, "_write_executor", _SyncExecutor())


@pytest.fixture()
def manager() -> RecentlyPlayedManager:
    return RecentlyPlayedManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(mgr: RecentlyPlayedManager, source: str = "steam", title: str = "Game",
            artwork: str = "", nav_params: dict | None = None) -> None:
    mgr.record(source, title, artwork, nav_params or {"app_id": "1"})


# ---------------------------------------------------------------------------
# record() — de-duplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_duplicate_source_and_nav_params_removed(self, manager: RecentlyPlayedManager) -> None:
        """Re-recording the same source+nav_params replaces the existing entry."""
        manager.record("steam", "Game A", "", {"app_id": "100"})
        manager.record("steam", "Game A updated", "", {"app_id": "100"})

        entries = manager.getRecent()
        matching = [e for e in entries if e["nav_params"] == {"app_id": "100"}]
        assert len(matching) == 1
        assert matching[0]["title"] == "Game A updated"

    def test_different_nav_params_not_deduped(self, manager: RecentlyPlayedManager) -> None:
        """Different nav_params for same source are kept as distinct entries."""
        manager.record("steam", "Game A", "", {"app_id": "100"})
        manager.record("steam", "Game B", "", {"app_id": "200"})

        entries = manager.getRecent()
        app_ids = [e["nav_params"]["app_id"] for e in entries]
        assert "100" in app_ids
        assert "200" in app_ids

    def test_same_nav_params_different_source_not_deduped(self, manager: RecentlyPlayedManager) -> None:
        """Same nav_params but different source are kept as distinct entries."""
        manager.record("retro", "Title", "", {"rom_path": "/rom.gb", "system_folder": "gb"})
        manager.record("steam", "Title", "", {"rom_path": "/rom.gb", "system_folder": "gb"})

        entries = manager.getRecent()
        assert len(entries) == 2

    def test_dedup_moves_entry_to_front(self, manager: RecentlyPlayedManager) -> None:
        """Re-recording an existing item moves it to position 0."""
        manager.record("steam", "Game A", "", {"app_id": "1"})
        manager.record("steam", "Game B", "", {"app_id": "2"})
        manager.record("steam", "Game A again", "", {"app_id": "1"})

        entries = manager.getRecent()
        assert entries[0]["nav_params"]["app_id"] == "1"
        assert entries[0]["title"] == "Game A again"


# ---------------------------------------------------------------------------
# record() — trim to 50
# ---------------------------------------------------------------------------


class TestTrim:
    def test_trim_to_50_entries(self, manager: RecentlyPlayedManager) -> None:
        """List is trimmed to 50 after exceeding that count."""
        for i in range(60):
            manager.record("steam", f"Game {i}", "", {"app_id": str(i)})

        assert len(manager._entries) == 50

    def test_most_recent_retained_after_trim(self, manager: RecentlyPlayedManager) -> None:
        """After trimming, the most recently recorded items are kept."""
        for i in range(60):
            manager.record("steam", f"Game {i}", "", {"app_id": str(i)})

        # The last recorded item (i=59) should be at position 0.
        assert manager._entries[0]["nav_params"]["app_id"] == "59"
        # Items 0-9 should have been dropped.
        app_ids = {e["nav_params"]["app_id"] for e in manager._entries}
        assert "0" not in app_ids


# ---------------------------------------------------------------------------
# record() — artwork normalisation
# ---------------------------------------------------------------------------


class TestArtworkNormalisation:
    def test_prepends_file_scheme_when_missing(self, manager: RecentlyPlayedManager) -> None:
        manager.record("retro", "Game", "/abs/path/art.jpg", {"rom_path": "/r.gb", "system_folder": "gb"})
        assert manager._entries[0]["artwork"] == "file:///abs/path/art.jpg"

    def test_does_not_double_prepend(self, manager: RecentlyPlayedManager) -> None:
        manager.record("retro", "Game", "file:///abs/path/art.jpg",
                       {"rom_path": "/r.gb", "system_folder": "gb"})
        assert manager._entries[0]["artwork"] == "file:///abs/path/art.jpg"

    def test_empty_artwork_stays_empty(self, manager: RecentlyPlayedManager) -> None:
        manager.record("steam", "Game", "", {"app_id": "1"})
        assert manager._entries[0]["artwork"] == ""


# ---------------------------------------------------------------------------
# record() — persistence and signal
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_saves_to_disk(self, manager: RecentlyPlayedManager, tmp_path: Path) -> None:
        manager.record("steam", "Game", "", {"app_id": "42"})

        path = tmp_path / "recently_played.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert data[0]["nav_params"]["app_id"] == "42"

    def test_emits_changed_signal(self, manager: RecentlyPlayedManager) -> None:
        received: list[bool] = []
        manager.changed.connect(lambda: received.append(True))

        manager.record("steam", "Game", "", {"app_id": "1"})

        assert len(received) == 1

    def test_atomic_write_produces_valid_json(self, manager: RecentlyPlayedManager,
                                              tmp_path: Path) -> None:
        for i in range(5):
            manager.record("steam", f"Game {i}", "", {"app_id": str(i)})

        path = tmp_path / "recently_played.json"
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 5


# ---------------------------------------------------------------------------
# getRecent() — slice
# ---------------------------------------------------------------------------


class TestGetRecent:
    def test_returns_at_most_5(self, manager: RecentlyPlayedManager) -> None:
        for i in range(10):
            manager.record("steam", f"Game {i}", "", {"app_id": str(i)})

        result = manager.getRecent()
        assert len(result) == 5

    def test_returns_most_recent_first(self, manager: RecentlyPlayedManager) -> None:
        for i in range(7):
            manager.record("steam", f"Game {i}", "", {"app_id": str(i)})

        result = manager.getRecent()
        assert result[0]["nav_params"]["app_id"] == "6"

    def test_returns_all_when_fewer_than_5(self, manager: RecentlyPlayedManager) -> None:
        manager.record("steam", "Only Game", "", {"app_id": "1"})

        result = manager.getRecent()
        assert len(result) == 1

    def test_returns_empty_list_when_no_entries(self, manager: RecentlyPlayedManager) -> None:
        assert manager.getRecent() == []

    def test_returns_list_of_dicts(self, manager: RecentlyPlayedManager) -> None:
        manager.record("steam", "Game", "", {"app_id": "1"})
        result = manager.getRecent()
        assert isinstance(result, list)
        assert isinstance(result[0], dict)


# ---------------------------------------------------------------------------
# __init__ — loading from disk
# ---------------------------------------------------------------------------


class TestInit:
    def test_loads_existing_json_on_construction(self, tmp_path: Path) -> None:
        """Manager loads persisted entries from disk on construction."""
        path = tmp_path / "recently_played.json"
        data = [{"source": "steam", "title": "Loaded Game", "artwork": "",
                 "timestamp": "2026-01-01T00:00:00Z", "nav_params": {"app_id": "99"}}]
        path.write_text(json.dumps(data), encoding="utf-8")

        mgr = RecentlyPlayedManager()
        result = mgr.getRecent()
        assert len(result) == 1
        assert result[0]["title"] == "Loaded Game"

    def test_starts_empty_when_file_missing(self) -> None:
        """Manager starts with an empty list when the JSON file doesn't exist."""
        mgr = RecentlyPlayedManager()
        assert mgr.getRecent() == []

    def test_starts_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        """Manager recovers gracefully from corrupt JSON."""
        path = tmp_path / "recently_played.json"
        path.write_text("not valid json{{", encoding="utf-8")

        mgr = RecentlyPlayedManager()
        assert mgr.getRecent() == []

    def test_starts_empty_on_wrong_json_type(self, tmp_path: Path) -> None:
        """Manager resets when JSON contains a non-list type."""
        path = tmp_path / "recently_played.json"
        path.write_text('{"not": "a list"}', encoding="utf-8")

        mgr = RecentlyPlayedManager()
        assert mgr.getRecent() == []
