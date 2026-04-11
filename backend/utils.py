from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, TypeVar

import requests

_T = TypeVar("_T")
_logger = logging.getLogger(__name__)


def load_json(path: Path) -> dict | list:
    """Read and parse a JSON file. Returns {} if the file does not exist."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict | list, indent: int | None = 2) -> None:
    """Serialise data to a JSON file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent), encoding="utf-8")


def safe_request(call: Callable[[], _T], context: str = "") -> _T | None:
    """Execute a requests call and return the result, or None on network error.

    Logs a warning for ConnectionError, Timeout, and HTTPError.

    Args:
        call: A zero-argument callable that performs the request (e.g. a lambda).
        context: A short description used in the warning message.
    """
    try:
        return call()
    except requests.exceptions.ConnectionError as exc:
        _logger.warning("Connection error%s: %s", f" ({context})" if context else "", exc)
    except requests.exceptions.Timeout:
        _logger.warning("Request timed out%s", f" ({context})" if context else "")
    except requests.exceptions.HTTPError as exc:
        _logger.warning("HTTP error%s: %s", f" ({context})" if context else "", exc)
    return None
