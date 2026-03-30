"""Moonlight configuration directory helper.

Single source of truth for the Moonlight config directory path.
Both moonlight_artwork.py and moonlight_play_history.py import from here.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_moonlight_dir() -> Path:
    """Return the Moonlight config directory, creating subdirs if needed.

    Directory layout::

        ~/.config/htpcstation/moonlight/
        ├── artwork_scraped/   # auto-downloaded artwork files
        ├── artwork_custom/    # user-provided artwork overrides
        ├── artwork_index.json # artwork metadata index
        └── play_history.json  # play timestamps

    Respects XDG_CONFIG_HOME.  Monkeypatch this function in tests to redirect
    all I/O to a temporary directory.
    """
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    moonlight_dir = config_home / "htpcstation" / "moonlight"
    moonlight_dir.mkdir(parents=True, exist_ok=True)
    (moonlight_dir / "artwork_scraped").mkdir(exist_ok=True)
    (moonlight_dir / "artwork_custom").mkdir(exist_ok=True)
    return moonlight_dir
