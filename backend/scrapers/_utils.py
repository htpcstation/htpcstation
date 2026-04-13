"""Shared utilities for scraper adapters.

Provides credential-scrubbing regex and a shared file download helper used by
multiple scraper adapters so the logic is not duplicated.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------

# Covers ScreenScraper params (devpassword, sspassword, devid, ssid) as well
# as generic 'password', 'token', and 'api_key' query parameters.
_SCRUB_PATTERN = re.compile(
    r"(devpassword|sspassword|devid|ssid|password|token|api_key|apikey|client_secret)=([^&\s)\"]*)",
    re.IGNORECASE,
)


def scrub_url(text: str) -> str:
    """Replace sensitive credential values in *text* with ``***``.

    Safe to call on any string — non-matching text is returned unchanged.
    """
    return _SCRUB_PATTERN.sub(r"\1=***", text)


# ---------------------------------------------------------------------------
# Shared file download helper
# ---------------------------------------------------------------------------


def iso_date_to_gamelist(date_str: str) -> str:
    """Convert "YYYY-MM-DD" to "YYYYMMDDTHHMMSS". Returns "" on any error."""
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            return f"{parts[0]}{parts[1].zfill(2)}{parts[2].zfill(2)}T000000"
    except Exception:  # noqa: BLE001
        pass
    return ""


def download_file(session: requests.Session, url: str, dest_path: Path) -> bool:
    """Download *url* to *dest_path*.  Creates parent directories automatically.

    Returns ``True`` on success, ``False`` on any exception (logged at WARNING).
    The caller is responsible for choosing a unique *dest_path*.
    """
    try:
        resp = session.get(url, timeout=(10, 60), stream=True)
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with dest_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[scraper] download failed for %s: %s", url, exc)
        return False
