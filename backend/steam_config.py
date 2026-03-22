"""Steam configuration directory helper.

Single source of truth for the Steam config directory path.
Monkeypatch get_steam_dir() in tests to redirect all I/O to a temporary directory.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_steam_dir() -> Path:
    """Return the Steam config directory, creating subdirs if needed.

    Directory layout::

        ***REMOVED***.config/htpcstation/steam/
        ├── artwork_scraped/   # auto-downloaded artwork files
        └── artwork_custom/    # user-provided artwork overrides

    Respects XDG_CONFIG_HOME.  Monkeypatch this function in tests to redirect
    all I/O to a temporary directory.
    """
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    steam_dir = config_home / "htpcstation" / "steam"
    steam_dir.mkdir(parents=True, exist_ok=True)
    (steam_dir / "artwork_scraped").mkdir(exist_ok=True)
    (steam_dir / "artwork_custom").mkdir(exist_ok=True)
    return steam_dir
