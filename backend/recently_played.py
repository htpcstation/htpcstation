"""Recently-played cross-category history manager for HTPC Station.

Stores and retrieves a unified list of recently-played items (games, movies,
albums, etc.) persisted to ~/.config/htpcstation/recently_played.json.

Entry schema::

    {
        "source": "retro|steam|moonlight|plexvideo|plexmusic|localmusic",
        "title": "Game/Movie/Album title",
        "artwork": "file:///abs/path/to/art.jpg",
        "timestamp": "2026-04-10T10:00:00Z",
        "nav_params": { ... }
    }

Public API (QObject slots exposed to QML):
    record(source, title, artwork, nav_params) -> None
    getRecent() -> list[dict]

Signal:
    changed()
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from backend.config import CONFIG_DIR
from backend.utils import load_json

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 50
_RECENT_COUNT = 5

# Module-level path so tests can monkeypatch it.
_HISTORY_PATH = CONFIG_DIR / "recently_played.json"

_write_executor = ThreadPoolExecutor(max_workers=1)


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RecentlyPlayedManager(QObject):
    """Cross-category recently-played list, persisted to disk.

    Instantiated in ``main.py`` and exposed to QML as ``recentlyPlayed``.
    """

    changed = Signal()

    def __init__(self, config=None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._entries: list[dict] = self._load()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str, str, str, "QVariantMap")
    def record(self, source: str, title: str, artwork: str, nav_params: dict) -> None:
        """Record a play event and persist to disk.

        - Normalises *artwork*: prepends ``file://`` if non-empty and missing.
        - De-duplicates: removes any existing entry where *source* and
          *nav_params* both match, then prepends the new entry.
        - Trims to the most recent ``_MAX_ENTRIES`` entries.
        - Writes atomically and emits ``changed()``.
        """
        if artwork and not artwork.startswith("file://"):
            artwork = "file://" + artwork

        # Convert QVariantMap to plain dict for reliable equality comparisons.
        nav_params = dict(nav_params)

        # Remove existing duplicate (same source + same nav_params).
        self._entries = [
            e for e in self._entries
            if not (e["source"] == source and e.get("nav_params") == nav_params)
        ]

        entry: dict = {
            "source": source,
            "title": title,
            "artwork": artwork,
            "timestamp": _now_utc(),
            "nav_params": nav_params,
        }
        self._entries.insert(0, entry)
        self._entries = self._entries[:_MAX_ENTRIES]

        _write_executor.submit(self._save)
        self.changed.emit()

    @Slot(result="QVariantList")
    def getRecent(self) -> list:
        """Return the *_RECENT_COUNT* most recent entries as a list of dicts."""
        return list(self._entries[:_RECENT_COUNT])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        """Load entries from disk.  Returns ``[]`` on missing file or error."""
        path = _HISTORY_PATH
        if not path.exists():
            return []
        try:
            data = load_json(path)
            if isinstance(data, list):
                return data
            logger.warning("recently_played: unexpected data type in JSON, resetting")
            return []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("recently_played: failed to load history: %s", exc)
            return []

    def _save(self) -> None:
        """Atomically write ``self._entries`` to disk."""
        path = _HISTORY_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2)
            os.replace(tmp_name, path)
        except OSError as exc:
            logger.warning("recently_played: failed to save history: %s", exc)
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
