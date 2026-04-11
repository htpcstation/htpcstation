"""Tests for backend/utils.py — safe_request utility.

Covers:
  - safe_request: returns call() result on success
  - safe_request: returns None and logs on ConnectionError
  - safe_request: returns None and logs on Timeout
  - safe_request: returns None and logs on HTTPError
  - safe_request: context string is included in log message when provided
  - safe_request: no context string suffix when context is empty
  - safe_request: non-requests exceptions propagate (not swallowed)
"""

from __future__ import annotations

import logging

import pytest
import requests

from backend.utils import safe_request


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSafeRequestSuccess:
    def test_returns_call_result(self) -> None:
        result = safe_request(lambda: "hello")
        assert result == "hello"

    def test_returns_none_when_call_returns_none(self) -> None:
        result = safe_request(lambda: None)
        assert result is None

    def test_returns_complex_value(self) -> None:
        payload = {"key": [1, 2, 3]}
        result = safe_request(lambda: payload)
        assert result is payload


# ---------------------------------------------------------------------------
# Network error handling — returns None
# ---------------------------------------------------------------------------


class TestSafeRequestNetworkErrors:
    def test_returns_none_on_connection_error(self) -> None:
        def _call():
            raise requests.exceptions.ConnectionError("refused")

        result = safe_request(_call)
        assert result is None

    def test_returns_none_on_timeout(self) -> None:
        def _call():
            raise requests.exceptions.Timeout()

        result = safe_request(_call)
        assert result is None

    def test_returns_none_on_http_error(self) -> None:
        def _call():
            raise requests.exceptions.HTTPError("404 Not Found")

        result = safe_request(_call)
        assert result is None


# ---------------------------------------------------------------------------
# Logging output
# ---------------------------------------------------------------------------


class TestSafeRequestLogging:
    def test_logs_warning_on_connection_error(self, caplog) -> None:
        def _call():
            raise requests.exceptions.ConnectionError("refused")

        with caplog.at_level(logging.WARNING, logger="backend.utils"):
            safe_request(_call, context="test endpoint")

        assert any("Connection error" in r.message for r in caplog.records)

    def test_logs_warning_on_timeout(self, caplog) -> None:
        def _call():
            raise requests.exceptions.Timeout()

        with caplog.at_level(logging.WARNING, logger="backend.utils"):
            safe_request(_call, context="test endpoint")

        assert any("timed out" in r.message for r in caplog.records)

    def test_logs_warning_on_http_error(self, caplog) -> None:
        def _call():
            raise requests.exceptions.HTTPError("500 Internal Server Error")

        with caplog.at_level(logging.WARNING, logger="backend.utils"):
            safe_request(_call, context="test endpoint")

        assert any("HTTP error" in r.message for r in caplog.records)

    def test_context_appears_in_log_when_provided(self, caplog) -> None:
        def _call():
            raise requests.exceptions.ConnectionError("refused")

        with caplog.at_level(logging.WARNING, logger="backend.utils"):
            safe_request(_call, context="my context")

        assert any("my context" in r.message for r in caplog.records)

    def test_no_context_suffix_when_context_empty(self, caplog) -> None:
        def _call():
            raise requests.exceptions.Timeout()

        with caplog.at_level(logging.WARNING, logger="backend.utils"):
            safe_request(_call)

        # No parentheses in the message when context is absent
        assert all("(" not in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Non-requests exceptions propagate
# ---------------------------------------------------------------------------


class TestSafeRequestPropagation:
    def test_value_error_propagates(self) -> None:
        def _call():
            raise ValueError("bad value")

        with pytest.raises(ValueError, match="bad value"):
            safe_request(_call)

    def test_runtime_error_propagates(self) -> None:
        def _call():
            raise RuntimeError("unexpected")

        with pytest.raises(RuntimeError):
            safe_request(_call)
