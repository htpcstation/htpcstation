"""Tests for moonlight_play_history — play timestamp recording and retrieval.

Covers:
  - record_play: creates file, records timestamp
  - record_play: updates existing entry without corrupting others
  - get_last_played: returns timestamp or None
  - get_all_history: returns full dict
  - Atomic write: file is valid JSON after write
  - Concurrent calls: sequential calls don't corrupt the file
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import backend.moonlight_config as moonlight_config_module
import backend.moonlight_play_history as play_history_module
from backend.moonlight_play_history import (
    clear_history,
    get_all_history,
    get_last_played,
    record_play,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def redirect_moonlight_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all play history I/O to a temporary directory for each test.

    Creates the expected subdirectories to mirror what the real
    ``get_moonlight_dir()`` does.
    """
    moonlight_dir = tmp_path / "moonlight"
    moonlight_dir.mkdir()
    (moonlight_dir / "artwork_scraped").mkdir()
    (moonlight_dir / "artwork_custom").mkdir()
    monkeypatch.setattr(moonlight_config_module, "get_moonlight_dir", lambda: moonlight_dir)
    monkeypatch.setattr(play_history_module, "get_moonlight_dir", lambda: moonlight_dir)
    return moonlight_dir


# ---------------------------------------------------------------------------
# record_play
# ---------------------------------------------------------------------------


class TestRecordPlay:
    def test_creates_history_file(self, tmp_path: Path) -> None:
        """record_play creates play_history.json if it doesn't exist."""
        moonlight_dir = tmp_path / "moonlight"
        history_path = moonlight_dir / "play_history.json"
        assert not history_path.exists()

        record_play("Desktop")

        assert history_path.exists()

    def test_records_timestamp_for_app(self, tmp_path: Path) -> None:
        """record_play writes a non-empty ISO timestamp for the app."""
        record_play("Desktop")

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        assert "Desktop" in data
        ts = data["Desktop"]
        assert ts  # non-empty
        # Basic ISO format check: YYYY-MM-DDTHH:MM:SSZ
        assert len(ts) == 20
        assert ts.endswith("Z")
        assert "T" in ts

    def test_updates_existing_entry(self, tmp_path: Path) -> None:
        """record_play updates the timestamp for an already-recorded app."""
        record_play("Desktop")
        moonlight_dir = tmp_path / "moonlight"
        first_ts = json.loads((moonlight_dir / "play_history.json").read_text())["Desktop"]

        record_play("Desktop")
        second_ts = json.loads((moonlight_dir / "play_history.json").read_text())["Desktop"]

        # Both are valid timestamps; second may equal first if called in same second
        assert second_ts >= first_ts

    def test_preserves_other_entries(self, tmp_path: Path) -> None:
        """record_play for one app does not remove other apps' entries."""
        record_play("Desktop")
        record_play("Slime Rancher")
        record_play("Desktop")  # update Desktop again

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        assert "Desktop" in data
        assert "Slime Rancher" in data

    def test_multiple_apps_recorded(self, tmp_path: Path) -> None:
        """record_play can record multiple different apps."""
        apps = ["Desktop", "Cyberpunk 2077", "Half-Life 2"]
        for app in apps:
            record_play(app)

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        for app in apps:
            assert app in data

    def test_app_name_is_case_sensitive(self, tmp_path: Path) -> None:
        """record_play treats app names as case-sensitive keys."""
        record_play("desktop")
        record_play("Desktop")

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        assert "desktop" in data
        assert "Desktop" in data
        assert len(data) == 2

    def test_history_file_is_valid_json(self, tmp_path: Path) -> None:
        """The history file is always valid JSON after record_play."""
        record_play("Game A")
        record_play("Game B")

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# get_last_played
# ---------------------------------------------------------------------------


class TestGetLastPlayed:
    def test_returns_none_when_no_history(self) -> None:
        """get_last_played returns None when no history file exists."""
        result = get_last_played("Desktop")
        assert result is None

    def test_returns_none_for_unknown_app(self) -> None:
        """get_last_played returns None for an app not in history."""
        record_play("Desktop")
        result = get_last_played("Unknown Game")
        assert result is None

    def test_returns_timestamp_for_known_app(self) -> None:
        """get_last_played returns the recorded timestamp for a known app."""
        record_play("Desktop")
        result = get_last_played("Desktop")
        assert result is not None
        assert result.endswith("Z")
        assert "T" in result

    def test_returns_latest_timestamp_after_update(self) -> None:
        """get_last_played returns the most recent timestamp after multiple records."""
        record_play("Desktop")
        first = get_last_played("Desktop")
        record_play("Desktop")
        second = get_last_played("Desktop")
        assert second >= first  # type: ignore[operator]

    def test_case_sensitive_lookup(self) -> None:
        """get_last_played is case-sensitive."""
        record_play("Desktop")
        assert get_last_played("desktop") is None
        assert get_last_played("Desktop") is not None


# ---------------------------------------------------------------------------
# get_all_history
# ---------------------------------------------------------------------------


class TestGetAllHistory:
    def test_returns_empty_dict_when_no_history(self) -> None:
        """get_all_history returns {} when no history file exists."""
        result = get_all_history()
        assert result == {}

    def test_returns_all_recorded_apps(self) -> None:
        """get_all_history returns all recorded app entries."""
        record_play("Desktop")
        record_play("Slime Rancher")
        record_play("Cyberpunk 2077")

        result = get_all_history()
        assert set(result.keys()) == {"Desktop", "Slime Rancher", "Cyberpunk 2077"}

    def test_values_are_iso_timestamps(self) -> None:
        """get_all_history values are ISO 8601 UTC timestamps."""
        record_play("Desktop")
        result = get_all_history()
        ts = result["Desktop"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_returns_dict_type(self) -> None:
        """get_all_history always returns a dict."""
        result = get_all_history()
        assert isinstance(result, dict)

    def test_reflects_updates(self) -> None:
        """get_all_history reflects the latest state after updates."""
        record_play("Desktop")
        record_play("Desktop")
        record_play("New Game")

        result = get_all_history()
        assert "Desktop" in result
        assert "New Game" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Atomic write / concurrent safety
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_history_file_valid_json_after_write(self, tmp_path: Path) -> None:
        """The history file is valid JSON immediately after record_play."""
        record_play("Test Game")

        moonlight_dir = tmp_path / "moonlight"
        path = moonlight_dir / "play_history.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        assert "Test Game" in data

    def test_sequential_calls_do_not_corrupt(self, tmp_path: Path) -> None:
        """Multiple sequential record_play calls don't corrupt the history file."""
        apps = [f"Game {i}" for i in range(20)]
        for app in apps:
            record_play(app)

        moonlight_dir = tmp_path / "moonlight"
        data = json.loads((moonlight_dir / "play_history.json").read_text())
        assert isinstance(data, dict)
        for app in apps:
            assert app in data

    def test_concurrent_calls_do_not_corrupt(self, tmp_path: Path) -> None:
        """Concurrent record_play calls from multiple threads don't corrupt the file.

        This is a best-effort test: we verify the file is valid JSON and
        contains at least some of the expected entries after concurrent writes.
        """
        apps = [f"Game {i}" for i in range(10)]
        errors: list[Exception] = []

        def _record(app: str) -> None:
            try:
                record_play(app)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_record, args=(app,)) for app in apps]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised exceptions: {errors}"

        moonlight_dir = tmp_path / "moonlight"
        path = moonlight_dir / "play_history.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        # At least one app should be recorded
        assert len(data) >= 1


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------


class TestClearHistory:
    def test_clears_all_entries(self, tmp_path: Path) -> None:
        """clear_history removes all recorded entries."""
        record_play("Desktop")
        record_play("Slime Rancher")

        clear_history()

        result = get_all_history()
        assert result == {}

    def test_noop_when_no_history_file(self, tmp_path: Path) -> None:
        """clear_history does nothing when no history file exists (no error)."""
        moonlight_dir = tmp_path / "moonlight"
        assert not (moonlight_dir / "play_history.json").exists()

        clear_history()  # should not raise

        assert not (moonlight_dir / "play_history.json").exists()

    def test_file_contains_empty_object_after_clear(self, tmp_path: Path) -> None:
        """After clear_history, the file contains a valid empty JSON object."""
        record_play("Desktop")

        clear_history()

        moonlight_dir = tmp_path / "moonlight"
        path = moonlight_dir / "play_history.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {}

    def test_record_play_works_after_clear(self, tmp_path: Path) -> None:
        """New plays can be recorded after clear_history."""
        record_play("Desktop")
        clear_history()
        record_play("New Game")

        result = get_all_history()
        assert "New Game" in result
        assert "Desktop" not in result
