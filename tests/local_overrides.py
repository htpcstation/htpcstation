"""Utilities to override test fixtures with local values.

This allows developers to keep personal hostnames/IPs in a JSON file that is
ignored by git while the default repository values remain sanitized.

Usage:
    from tests.local_overrides import get_override

    HOST = get_override("moonlight_hostname", "DESKTOP-HTPC")

Create ``tests/local_overrides.json`` or ``tests/.local/test_overrides.json``
with a JSON object mapping keys to values, e.g.::

    {
        "moonlight_hostname": "DESKTOP-MYPC",
        "moonlight_local_ip": "192.168.50.5"
    }

Alternatively set ``HTPC_TEST_OVERRIDES=/path/to/file.json`` to point to a
custom overrides file elsewhere on your system.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


def _candidate_paths() -> list[Path]:
    """Return candidate override file paths in priority order."""
    paths: list[Path] = []
    env_path = os.environ.get("HTPC_TEST_OVERRIDES")
    if env_path:
        paths.append(Path(env_path).expanduser())

    tests_dir = Path(__file__).resolve().parent
    paths.append(tests_dir / "local_overrides.json")
    paths.append(tests_dir / ".local" / "test_overrides.json")
    return paths


@lru_cache(maxsize=1)
def _load_overrides() -> Dict[str, Any]:
    """Load overrides JSON from the first existing candidate file."""
    for path in _candidate_paths():
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:  # pragma: no cover - sanity check
                raise ValueError(f"Invalid JSON in override file {path}") from exc
    return {}


def get_override(key: str, default: Any) -> Any:
    """Return overridden value for *key* if provided, else *default*."""
    return _load_overrides().get(key, default)
