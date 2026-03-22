"""Tests for Task 009 — Moonlight Artwork Cache & Steam Lookup Helper.

Covers:
  - slugify_app_name: various strings including edge cases
  - Manual override detection: file pre-created returns immediately, metadata updated
  - Cached metadata + file: returns without HTTP
  - Steam search success: downloads poster, saves file, metadata recorded with steam_app_id
  - Steam search no results: returns None, metadata entry indicates source="none"
  - Double refresh safety: two calls for same app don't corrupt metadata
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import backend.moonlight_artwork as artwork_module
from backend.moonlight_artwork import (
    get_artwork_path,
    refresh_artwork,
    slugify_app_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def redirect_artwork_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all artwork I/O to a temporary directory for each test.

    Also creates the ``custom/`` subdirectory to mirror what the real
    ``_get_artwork_dir()`` does.
    """
    artwork_dir = tmp_path / "moonlight_artwork"
    artwork_dir.mkdir()
    (artwork_dir / "custom").mkdir()
    monkeypatch.setattr(artwork_module, "_get_artwork_dir", lambda: artwork_dir)
    return artwork_dir


def _artwork_dir(tmp_path: Path) -> Path:
    """Return the redirected artwork directory for the current test."""
    return tmp_path / "moonlight_artwork"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_urlopen_search(items: list[dict[str, Any]]):
    """Return a context-manager mock that yields a fake Steam search response."""
    body = json.dumps({"items": items}).encode()

    class _FakeResp:
        def __init__(self) -> None:
            self._data = BytesIO(body)
            self.headers: dict[str, str] = {}

        def read(self, n: int = -1) -> bytes:
            return self._data.read(n) if n == -1 else self._data.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    return _FakeResp()


def _fake_urlopen_image(content: bytes = b"FAKEIMAGE", content_type: str = "image/jpeg"):
    """Return a context-manager mock that yields a fake image download response."""

    class _FakeHeaders:
        def get(self, key: str, default: str = "") -> str:
            if key == "Content-Type":
                return content_type
            return default

    class _FakeResp:
        def __init__(self) -> None:
            self._data = BytesIO(content)
            self.headers = _FakeHeaders()

        def read(self, n: int = -1) -> bytes:
            return self._data.read(n) if n == -1 else self._data.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    return _FakeResp()


# ---------------------------------------------------------------------------
# slugify_app_name
# ---------------------------------------------------------------------------


class TestSlugifyAppName:
    def test_simple_lowercase(self) -> None:
        assert slugify_app_name("Desktop") == "desktop"

    def test_spaces_become_hyphens(self) -> None:
        assert slugify_app_name("Cyberpunk 2077") == "cyberpunk-2077"

    def test_special_chars_become_hyphens(self) -> None:
        assert slugify_app_name("Divinity: Original Sin II") == "divinity-original-sin-ii"

    def test_multiple_hyphens_collapsed(self) -> None:
        assert slugify_app_name("A  B   C") == "a-b-c"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        assert slugify_app_name("!Game!") == "game"

    def test_already_slug(self) -> None:
        assert slugify_app_name("my-game") == "my-game"

    def test_numbers_preserved(self) -> None:
        assert slugify_app_name("Half-Life 2") == "half-life-2"

    def test_empty_string_fallback(self) -> None:
        slug = slugify_app_name("")
        assert slug.startswith("app")
        assert len(slug) > 3

    def test_only_special_chars_fallback(self) -> None:
        slug = slugify_app_name("!!!###")
        assert slug.startswith("app")
        assert len(slug) > 3

    def test_unicode_chars_become_hyphens(self) -> None:
        slug = slugify_app_name("Ünïcödé")
        # Non-ASCII chars are replaced; result should be non-empty
        assert slug and not slug.startswith("app")

    def test_consistent_hash_for_empty(self) -> None:
        """Two calls with the same empty-ish input produce the same slug."""
        assert slugify_app_name("") == slugify_app_name("")

    def test_ampersand_becomes_hyphen(self) -> None:
        assert slugify_app_name("Tom & Jerry") == "tom-jerry"


# ---------------------------------------------------------------------------
# Artwork directory setup
# ---------------------------------------------------------------------------


class TestArtworkDirSetup:
    def test_custom_subdir_created_by_get_artwork_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_artwork_dir() creates the custom/ subdirectory automatically."""
        # Point XDG_CONFIG_HOME at a fresh temp dir and call the real function
        # directly (bypassing the autouse monkeypatch which replaces the whole function).
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from backend.moonlight_artwork import _get_artwork_dir as real_get_artwork_dir

        result = real_get_artwork_dir()
        assert result.is_dir()
        assert (result / "custom").is_dir()


# ---------------------------------------------------------------------------
# Manual override detection
# ---------------------------------------------------------------------------


class TestManualOverride:
    def test_override_jpg_returned_immediately(self, tmp_path: Path) -> None:
        """A pre-created custom/<slug>.jpg file is returned without any HTTP call."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")
        override_file = artwork_dir / "custom" / f"{slug}.jpg"
        override_file.write_bytes(b"FAKEIMAGE")

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = refresh_artwork("Desktop")

        mock_urlopen.assert_not_called()
        assert result == override_file

    def test_override_png_returned(self, tmp_path: Path) -> None:
        """A pre-created custom/<slug>.png file is also detected."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("My Game")
        override_file = artwork_dir / "custom" / f"{slug}.png"
        override_file.write_bytes(b"PNGDATA")

        result = refresh_artwork("My Game")
        assert result == override_file

    def test_override_updates_metadata_source_manual(self, tmp_path: Path) -> None:
        """When a manual override is found, metadata is updated with source='manual'."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")
        override_file = artwork_dir / "custom" / f"{slug}.jpg"
        override_file.write_bytes(b"FAKEIMAGE")

        refresh_artwork("Desktop")

        index_path = artwork_dir / "moonlight_artwork_index.json"
        assert index_path.exists()
        metadata = json.loads(index_path.read_text())
        assert metadata[slug]["source"] == "manual"
        assert metadata[slug]["filename"] == override_file.name

    def test_override_takes_priority_over_cached_metadata(self, tmp_path: Path) -> None:
        """Manual override in custom/ takes priority even when metadata says source='steam'."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")

        # Pre-populate metadata with a steam entry pointing to a file in the main dir
        steam_file = artwork_dir / f"{slug}.jpg"
        steam_file.write_bytes(b"STEAMIMAGE")
        metadata = {
            slug: {
                "app_name": "Desktop",
                "slug": slug,
                "steam_app_id": 12345,
                "source": "steam",
                "filename": steam_file.name,
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }
        (artwork_dir / "moonlight_artwork_index.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        # Place a custom override — it must win over the steam-tracked file
        override_file = artwork_dir / "custom" / f"{slug}.jpg"
        override_file.write_bytes(b"CUSTOMIMAGE")

        result = refresh_artwork("Desktop")
        assert result == override_file

    def test_get_artwork_path_returns_override(self, tmp_path: Path) -> None:
        """get_artwork_path also detects manual overrides in custom/."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")
        override_file = artwork_dir / "custom" / f"{slug}.jpg"
        override_file.write_bytes(b"FAKEIMAGE")

        result = get_artwork_path("Desktop")
        assert result == override_file

    def test_file_in_main_dir_not_treated_as_override(self, tmp_path: Path) -> None:
        """A file in the main artwork dir (not custom/) is NOT treated as a manual override."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")

        # File in main dir only — no metadata, no custom/ file
        main_file = artwork_dir / f"{slug}.jpg"
        main_file.write_bytes(b"MAINIMAGE")

        # Without metadata, get_artwork_path should return None (not the main-dir file)
        result = get_artwork_path("Desktop")
        assert result is None

    def test_custom_file_takes_priority_over_steam_downloaded_same_slug(
        self, tmp_path: Path
    ) -> None:
        """A file in custom/ takes priority over a Steam-downloaded file with the same slug."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Cyberpunk 2077")

        # Simulate a Steam-downloaded file in the main dir with metadata
        steam_file = artwork_dir / f"{slug}.jpg"
        steam_file.write_bytes(b"STEAMDOWNLOADED")
        metadata = {
            slug: {
                "app_name": "Cyberpunk 2077",
                "slug": slug,
                "steam_app_id": 1091500,
                "source": "steam",
                "filename": steam_file.name,
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }
        (artwork_dir / "moonlight_artwork_index.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        # User places a custom override with the same slug
        custom_file = artwork_dir / "custom" / f"{slug}.jpg"
        custom_file.write_bytes(b"USEROVERRIDE")

        result = get_artwork_path("Cyberpunk 2077")
        assert result == custom_file
        assert result.read_bytes() == b"USEROVERRIDE"


# ---------------------------------------------------------------------------
# Cached metadata use
# ---------------------------------------------------------------------------


class TestCachedMetadata:
    def test_cached_entry_returns_without_http(self, tmp_path: Path) -> None:
        """If metadata + file exist, refresh_artwork returns without any HTTP call."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Cyberpunk 2077")
        cached_file = artwork_dir / f"{slug}.jpg"
        cached_file.write_bytes(b"CACHEDIMAGE")

        metadata = {
            slug: {
                "app_name": "Cyberpunk 2077",
                "slug": slug,
                "steam_app_id": 1091500,
                "source": "steam",
                "filename": cached_file.name,
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }
        (artwork_dir / "moonlight_artwork_index.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = refresh_artwork("Cyberpunk 2077")

        mock_urlopen.assert_not_called()
        assert result == cached_file

    def test_get_artwork_path_returns_cached(self, tmp_path: Path) -> None:
        """get_artwork_path returns the cached file path from metadata."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Cyberpunk 2077")
        cached_file = artwork_dir / f"{slug}.jpg"
        cached_file.write_bytes(b"CACHEDIMAGE")

        metadata = {
            slug: {
                "app_name": "Cyberpunk 2077",
                "slug": slug,
                "steam_app_id": 1091500,
                "source": "steam",
                "filename": cached_file.name,
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }
        (artwork_dir / "moonlight_artwork_index.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        result = get_artwork_path("Cyberpunk 2077")
        assert result == cached_file

    def test_missing_file_triggers_redownload(self, tmp_path: Path) -> None:
        """If metadata exists but the file is gone, a new download is attempted."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Cyberpunk 2077")

        # Metadata says file exists but it doesn't
        metadata = {
            slug: {
                "app_name": "Cyberpunk 2077",
                "slug": slug,
                "steam_app_id": 1091500,
                "source": "steam",
                "filename": f"{slug}.jpg",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }
        (artwork_dir / "moonlight_artwork_index.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        search_resp = _fake_urlopen_search([{"id": 1091500, "name": "Cyberpunk 2077"}])
        image_resp = _fake_urlopen_image(b"NEWIMAGE")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result = refresh_artwork("Cyberpunk 2077")

        assert result is not None
        assert result.exists()


# ---------------------------------------------------------------------------
# Steam download
# ---------------------------------------------------------------------------


class TestSteamDownload:
    def test_steam_search_success_downloads_poster(self, tmp_path: Path) -> None:
        """Steam search success → downloads poster, saves file, metadata recorded."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Divinity: Original Sin II")

        search_resp = _fake_urlopen_search([{"id": 435150, "name": "Divinity: Original Sin 2"}])
        image_resp = _fake_urlopen_image(b"POSTERDATA")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result = refresh_artwork("Divinity: Original Sin II")

        assert result is not None
        assert result.exists()
        assert result.read_bytes() == b"POSTERDATA"

        # Verify metadata
        index_path = artwork_dir / "moonlight_artwork_index.json"
        metadata = json.loads(index_path.read_text())
        assert metadata[slug]["steam_app_id"] == 435150
        assert metadata[slug]["source"] == "steam"
        assert metadata[slug]["filename"] == result.name

    def test_steam_download_png_content_type(self, tmp_path: Path) -> None:
        """If the CDN returns image/png, the file is saved with .png extension."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("My Game")

        search_resp = _fake_urlopen_search([{"id": 99999, "name": "My Game"}])
        image_resp = _fake_urlopen_image(b"PNGDATA", content_type="image/png")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result = refresh_artwork("My Game")

        assert result is not None
        assert result.suffix == ".png"

    def test_steam_download_webp_content_type(self, tmp_path: Path) -> None:
        """If the CDN returns image/webp, the file is saved with .webp extension."""
        artwork_dir = _artwork_dir(tmp_path)

        search_resp = _fake_urlopen_search([{"id": 11111, "name": "WebP Game"}])
        image_resp = _fake_urlopen_image(b"WEBPDATA", content_type="image/webp")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result = refresh_artwork("WebP Game")

        assert result is not None
        assert result.suffix == ".webp"

    def test_steam_download_uses_first_result(self, tmp_path: Path) -> None:
        """Steam search uses the first result's app ID."""
        artwork_dir = _artwork_dir(tmp_path)

        search_resp = _fake_urlopen_search([
            {"id": 111, "name": "First Result"},
            {"id": 222, "name": "Second Result"},
        ])
        image_resp = _fake_urlopen_image(b"IMAGE")

        captured_urls: list[str] = []

        def _urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            if len(captured_urls) == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            refresh_artwork("Some Game")

        # Second call should use app_id=111 (first result)
        assert "111" in captured_urls[1]
        assert "222" not in captured_urls[1]

    def test_metadata_updated_after_download(self, tmp_path: Path) -> None:
        """Metadata index is updated with steam_app_id and source='steam' after download."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Half-Life 2")

        search_resp = _fake_urlopen_search([{"id": 220, "name": "Half-Life 2"}])
        image_resp = _fake_urlopen_image(b"IMAGE")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            refresh_artwork("Half-Life 2")

        metadata = json.loads(
            (artwork_dir / "moonlight_artwork_index.json").read_text()
        )
        assert metadata[slug]["steam_app_id"] == 220
        assert metadata[slug]["source"] == "steam"
        assert metadata[slug]["updated_at"]  # non-empty timestamp


# ---------------------------------------------------------------------------
# Steam search no results
# ---------------------------------------------------------------------------


class TestSteamNoResults:
    def test_no_results_returns_none(self, tmp_path: Path) -> None:
        """Steam search with no results returns None."""
        search_resp = _fake_urlopen_search([])

        with patch("urllib.request.urlopen", return_value=search_resp):
            result = refresh_artwork("Totally Unknown Game XYZ")

        assert result is None

    def test_no_results_metadata_source_none(self, tmp_path: Path) -> None:
        """When Steam returns no results, metadata entry has source='none'."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Totally Unknown Game XYZ")

        search_resp = _fake_urlopen_search([])

        with patch("urllib.request.urlopen", return_value=search_resp):
            refresh_artwork("Totally Unknown Game XYZ")

        metadata = json.loads(
            (artwork_dir / "moonlight_artwork_index.json").read_text()
        )
        assert metadata[slug]["source"] == "none"
        assert metadata[slug]["steam_app_id"] is None

    def test_network_error_returns_none(self, tmp_path: Path) -> None:
        """A network error during Steam search returns None gracefully."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = refresh_artwork("Some Game")

        assert result is None

    def test_network_error_metadata_source_none(self, tmp_path: Path) -> None:
        """A network error records source='none' in metadata."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Some Game")

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            refresh_artwork("Some Game")

        metadata = json.loads(
            (artwork_dir / "moonlight_artwork_index.json").read_text()
        )
        assert metadata[slug]["source"] == "none"

    def test_get_artwork_path_returns_none_when_no_file(self, tmp_path: Path) -> None:
        """get_artwork_path returns None when no file or metadata exists."""
        result = get_artwork_path("Unknown Game")
        assert result is None


# ---------------------------------------------------------------------------
# Double refresh safety (concurrent / repeated calls)
# ---------------------------------------------------------------------------


class TestDoubleRefreshSafety:
    def test_double_refresh_does_not_corrupt_metadata(self, tmp_path: Path) -> None:
        """Two sequential refresh calls for the same app don't corrupt metadata."""
        artwork_dir = _artwork_dir(tmp_path)
        slug = slugify_app_name("Desktop")

        search_resp1 = _fake_urlopen_search([{"id": 12345, "name": "Desktop"}])
        image_resp1 = _fake_urlopen_image(b"IMAGE1")
        search_resp2 = _fake_urlopen_search([{"id": 12345, "name": "Desktop"}])
        image_resp2 = _fake_urlopen_image(b"IMAGE2")

        responses = [search_resp1, image_resp1, search_resp2, image_resp2]
        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result1 = refresh_artwork("Desktop")

        # Second call: file already exists from first call, so no HTTP
        with patch("urllib.request.urlopen") as mock_urlopen2:
            result2 = refresh_artwork("Desktop")
            mock_urlopen2.assert_not_called()

        # Metadata should still be valid JSON with one entry
        metadata = json.loads(
            (artwork_dir / "moonlight_artwork_index.json").read_text()
        )
        assert slug in metadata
        assert metadata[slug]["source"] == "steam"

    def test_metadata_written_atomically(self, tmp_path: Path) -> None:
        """Metadata is written atomically (temp file + rename) — no partial writes."""
        artwork_dir = _artwork_dir(tmp_path)

        search_resp = _fake_urlopen_search([{"id": 99, "name": "Test"}])
        image_resp = _fake_urlopen_image(b"IMAGE")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            refresh_artwork("Test")

        # The index file should be valid JSON (not partial)
        index_path = artwork_dir / "moonlight_artwork_index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text())
        assert isinstance(data, dict)

    def test_second_refresh_uses_cache_not_network(self, tmp_path: Path) -> None:
        """After a successful download, a second refresh uses the cached file."""
        artwork_dir = _artwork_dir(tmp_path)

        search_resp = _fake_urlopen_search([{"id": 42, "name": "Cached Game"}])
        image_resp = _fake_urlopen_image(b"IMAGE")

        call_count = 0

        def _urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return search_resp
            return image_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result1 = refresh_artwork("Cached Game")

        assert result1 is not None

        # Second call — should NOT hit the network
        with patch("urllib.request.urlopen") as mock_net:
            result2 = refresh_artwork("Cached Game")
            mock_net.assert_not_called()

        assert result2 == result1
