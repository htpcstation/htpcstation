"""Data models for Live TV (EPG + HDHomeRun).

Plain Python dataclasses — not QObjects. Parsed from Plex EPG API JSON responses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiveTvChannel:
    """Represents a single Live TV channel with current/next program info."""

    channel_id: int
    vcn: str                  # e.g. "7.1"
    title: str                # e.g. "7.1 WKBWDT (ABC)"
    call_sign: str            # e.g. "WKBWDT"
    thumb: str                # absolute URL (channel logo)
    grid_key: str             # Plex EPG channel identifier
    stream_url: str           # HDHomeRun direct stream URL (may be "" if not available)
    current_program: str      # title of currently airing program
    current_start: int        # unix timestamp
    current_end: int          # unix timestamp
    current_thumb: str        # program poster URL
    next_program: str         # title of next program
    next_start: int
    next_end: int
    next_thumb: str
    on_air: bool              # True if currently airing
    affiliate: str = ""       # e.g. "ABC" (from HDHomeRun guide)
    current_synopsis: str = ""  # synopsis of currently airing program
    next_synopsis: str = ""   # synopsis of next program
