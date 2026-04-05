"""LRC and plain-text lyrics parser.

Provides two public functions:

- :func:`parse_lrc`   — parse a synced LRC string into timed lyric dicts.
- :func:`parse_plain` — parse a plain-text lyrics string into untimed lyric dicts.
"""

from __future__ import annotations

import re
from typing import Optional

# Matches a single LRC timestamp: [mm:ss.xx]
# Groups: (minutes, seconds, hundredths)
_TIMESTAMP_RE = re.compile(r"\[(\d+):(\d{2})\.(\d{2})\]")


def parse_lrc(text: Optional[str]) -> list[dict]:
    """Parse a synced LRC string into a list of timed lyric dicts.

    Each LRC line has the format ``[mm:ss.xx] lyric text``.  A single line
    may carry multiple timestamps (e.g. ``[00:10.00][00:20.00] text``); one
    entry is emitted per timestamp.  Header tags (``[ar:...]``, ``[ti:...]``,
    etc.) are ignored.  Lines with blank lyric text are included with
    ``text: ""``.

    Args:
        text: Raw LRC string as returned by the LRCLIB ``syncedLyrics`` field.
              ``None`` is treated as an empty string.

    Returns:
        A list of ``{"ms": int, "text": str}`` dicts sorted ascending by
        ``ms``.  Returns ``[]`` for empty / unparseable input.
    """
    if not text:
        return []

    entries: list[dict] = []

    for line in text.splitlines():
        timestamps = _TIMESTAMP_RE.findall(line)
        if not timestamps:
            continue

        # Lyric text is everything after the last timestamp tag
        last_tag_end = 0
        for m in _TIMESTAMP_RE.finditer(line):
            last_tag_end = m.end()
        lyric_text = line[last_tag_end:].strip()

        for minutes, seconds, hundredths in timestamps:
            ms = int(minutes) * 60_000 + int(seconds) * 1_000 + int(hundredths) * 10
            entries.append({"ms": ms, "text": lyric_text})

    entries.sort(key=lambda e: e["ms"])
    return entries


def parse_plain(text: Optional[str]) -> list[dict]:
    """Parse a plain-text lyrics string into a list of untimed lyric dicts.

    Each non-empty line in *text* becomes one entry with ``ms: -1``.

    Args:
        text: Raw plain-text lyrics string as returned by the LRCLIB
              ``plainLyrics`` field.  ``None`` is treated as an empty string.

    Returns:
        A list of ``{"ms": -1, "text": str}`` dicts, one per non-empty line.
        Returns ``[]`` for empty input.
    """
    if not text:
        return []

    return [{"ms": -1, "text": line} for line in text.splitlines() if line]
