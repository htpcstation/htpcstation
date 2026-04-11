"""Moonlight play history tracker.

Records and reads timestamps for when Moonlight apps are launched.

History file: ~/.config/htpcstation/moonlight/play_history.json

Format::

    {
        "Desktop": "2026-03-22T18:45:00Z",
        "Slime Rancher": "2026-03-21T14:30:00Z"
    }

Keys are original app names (case-sensitive), not slugs.

Public API:
    record_play(app_name) -> None
    get_last_played(app_name) -> Optional[str]
    get_all_history() -> dict[str, str]
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.moonlight_config import get_moonlight_dir
from backend.utils import load_json

logger = logging.getLogger(__name__)


def _get_history_path() -> Path:
    """Return the path to the play history JSON file."""
    return get_moonlight_dir() / "play_history.json"


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_history() -> dict[str, str]:
    """Load the play history from disk.  Returns an empty dict on any error."""
    path = _get_history_path()
    try:
        return load_json(path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("moonlight_play_history: failed to load history: %s", exc)
        return {}


def _save_history(history: dict[str, str]) -> None:
    """Atomically write *history* to the play history file."""
    path = _get_history_path()
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        os.replace(tmp_name, path)
    except OSError as exc:
        logger.warning("moonlight_play_history: failed to save history: %s", exc)
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def record_play(app_name: str) -> None:
    """Record the current UTC timestamp for *app_name*.

    Creates or updates the entry for *app_name* in the play history file.
    Uses atomic writes to avoid corruption.
    """
    history = _load_history()
    history[app_name] = _now_utc()
    _save_history(history)
    logger.debug("moonlight_play_history: recorded play for '%s'", app_name)


def get_last_played(app_name: str) -> Optional[str]:
    """Return the ISO timestamp of the last play for *app_name*, or None."""
    history = _load_history()
    return history.get(app_name)


def get_all_history() -> dict[str, str]:
    """Return the full play history as ``{app_name: iso_timestamp}``."""
    return _load_history()


def clear_history() -> None:
    """Delete all play history entries by overwriting the file with an empty object."""
    path = _get_history_path()
    if path.exists():
        path.write_text("{}", encoding="utf-8")
        logger.debug("moonlight_play_history: cleared all play history")
