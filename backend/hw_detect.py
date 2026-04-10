"""Detect VA-API hardware decode codecs via vainfo."""

from __future__ import annotations

import logging
import re
import subprocess

logger = logging.getLogger(__name__)

# Map VA-API profile prefixes to codec strings.
_PROFILE_MAP: dict[str, str] = {
    "VAProfileH264": "h264",
    "VAProfileHEVC": "hevc",
    "VAProfileAV1": "av1",
    "VAProfileVP9": "vp9",
    "VAProfileVP8": "vp8",
    "VAProfileMPEG2": "mpeg2",
    "VAProfileVC1": "vc1",
}


def detect_vaapi_codecs() -> list[str]:
    """Run ``vainfo`` and return a sorted, deduplicated list of codec strings
    that the hardware can decode (VLD entries only).

    Returns an empty list if ``vainfo`` is not installed or fails.
    """
    try:
        result = subprocess.run(
            ["vainfo"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("vainfo unavailable: %s", exc)
        return []
    except OSError as exc:
        logger.debug("vainfo failed: %s", exc)
        return []

    if result.returncode != 0:
        logger.debug("vainfo exited with %d", result.returncode)
        return []

    codecs: set[str] = set()
    for line in result.stdout.splitlines():
        if "VLD" not in line:
            continue
        for prefix, codec in _PROFILE_MAP.items():
            if prefix in line:
                codecs.add(codec)
                break

    return sorted(codecs)
