"""Pytest configuration for HTPC Station tests.

Ensures a QCoreApplication instance exists for the entire test session.
This is required for cross-thread Qt signal delivery (used by MoonlightLibrary
and PlexLibrary which use ThreadPoolExecutor + Qt signals).
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Create a QCoreApplication for the test session if one doesn't exist."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app
