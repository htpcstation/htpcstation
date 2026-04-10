"""Tests for TmdbScraper and _parse_movie_title.

All HTTP calls are mocked — no real network access.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from backend.local_video_library import (
    LocalVideoCache,
    TmdbScraper,
    VideoFile,
    _parse_movie_title,
)
from backend.local_video_library import Show, Season


# ---------------------------------------------------------------------------
# _parse_movie_title
# ---------------------------------------------------------------------------


class TestParseMovieTitle:
    def test_title_with_year_in_parens(self) -> None:
        title, year = _parse_movie_title("The Matrix (1999)")
        assert title == "The Matrix"
        assert year == 1999

    def test_no_parens_returns_stem_and_none(self) -> None:
        title, year = _parse_movie_title("Some.Movie.2020")
        assert title == "Some.Movie.2020"
        assert year is None

    def test_non_numeric_year_returns_stem_and_none(self) -> None:
        title, year = _parse_movie_title("Movie (not-a-year)")
        assert title == "Movie (not-a-year)"
        assert year is None

    def test_strips_extra_spaces_around_title(self) -> None:
        title, year = _parse_movie_title("  Heat  (1995)")
        assert title == "Heat"
        assert year == 1995


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scraper() -> TmdbScraper:
    """Return a TmdbScraper with a mocked requests.Session."""
    scraper = TmdbScraper.__new__(TmdbScraper)
    scraper._api_key = "testkey"
    scraper._session = MagicMock()
    return scraper


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


def _error_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    return resp


# ---------------------------------------------------------------------------
# search_movie
# ---------------------------------------------------------------------------


class TestSearchMovie:
    def test_returns_first_result_when_no_year(self) -> None:
        scraper = _make_scraper()
        movie_a = {"id": 1, "title": "Movie A", "release_date": "2010-01-01"}
        scraper._session.get.return_value = _json_response({"results": [movie_a]})
        result = scraper.search_movie("Movie A", None)
        assert result == movie_a

    def test_prefers_year_matching_result(self) -> None:
        scraper = _make_scraper()
        first = {"id": 1, "title": "Inception", "release_date": "2005-06-01"}
        match = {"id": 2, "title": "Inception", "release_date": "2010-07-16"}
        scraper._session.get.return_value = _json_response({"results": [first, match]})
        result = scraper.search_movie("Inception", 2010)
        assert result == match

    def test_falls_back_to_first_result_when_no_year_match(self) -> None:
        scraper = _make_scraper()
        first = {"id": 1, "title": "Inception", "release_date": "2005-06-01"}
        second = {"id": 2, "title": "Inception", "release_date": "2008-03-01"}
        scraper._session.get.return_value = _json_response({"results": [first, second]})
        result = scraper.search_movie("Inception", 2010)
        assert result == first  # no match → fallback to results[0]

    def test_returns_none_when_results_empty(self) -> None:
        scraper = _make_scraper()
        scraper._session.get.return_value = _json_response({"results": []})
        assert scraper.search_movie("Unknown", None) is None

    def test_returns_none_and_logs_on_request_exception(self, caplog) -> None:
        scraper = _make_scraper()
        scraper._session.get.side_effect = requests.ConnectionError("refused")
        with caplog.at_level(logging.WARNING):
            result = scraper.search_movie("Film", None)
        assert result is None
        assert any("search_movie" in r.message for r in caplog.records)

    def test_omits_year_param_when_none(self) -> None:
        scraper = _make_scraper()
        movie = {"id": 5, "title": "Test", "release_date": "2015-01-01"}
        scraper._session.get.return_value = _json_response({"results": [movie]})
        scraper.search_movie("Test", None)
        _, kwargs = scraper._session.get.call_args
        assert "year" not in kwargs.get("params", {})

    def test_includes_year_param_when_provided(self) -> None:
        scraper = _make_scraper()
        movie = {"id": 5, "title": "Test", "release_date": "2015-01-01"}
        scraper._session.get.return_value = _json_response({"results": [movie]})
        scraper.search_movie("Test", 2015)
        _, kwargs = scraper._session.get.call_args
        assert kwargs.get("params", {}).get("year") == 2015


# ---------------------------------------------------------------------------
# search_tv_show
# ---------------------------------------------------------------------------


class TestSearchTvShow:
    def test_returns_first_result(self) -> None:
        scraper = _make_scraper()
        show = {"id": 10, "name": "Breaking Bad", "first_air_date": "2008-01-20"}
        scraper._session.get.return_value = _json_response({"results": [show]})
        result = scraper.search_tv_show("Breaking Bad")
        assert result == show

    def test_returns_none_when_results_empty(self) -> None:
        scraper = _make_scraper()
        scraper._session.get.return_value = _json_response({"results": []})
        assert scraper.search_tv_show("NoShow") is None

    def test_returns_none_and_logs_on_request_exception(self, caplog) -> None:
        scraper = _make_scraper()
        scraper._session.get.side_effect = requests.Timeout("timed out")
        with caplog.at_level(logging.WARNING):
            result = scraper.search_tv_show("Show")
        assert result is None
        assert any("search_tv_show" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# download_poster
# ---------------------------------------------------------------------------


class TestDownloadPoster:
    def test_writes_content_and_returns_true(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        content = b"\xff\xd8\xff fake jpeg"
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.content = content
        scraper._session.get.return_value = resp

        dest = tmp_path / "posters" / "movie.jpg"
        result = scraper.download_poster("/abc123.jpg", dest)

        assert result is True
        assert dest.exists()
        assert dest.read_bytes() == content

    def test_returns_false_on_http_error(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        scraper._session.get.return_value = _error_response()

        dest = tmp_path / "movie.jpg"
        result = scraper.download_poster("/fail.jpg", dest)

        assert result is False
        assert not dest.exists()

    def test_strips_leading_slash_in_url(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.content = b"img"
        scraper._session.get.return_value = resp

        dest = tmp_path / "poster.jpg"
        scraper.download_poster("/abc123.jpg", dest)

        url_called = scraper._session.get.call_args[0][0]
        assert "//abc123" not in url_called
        assert url_called.endswith("/abc123.jpg")

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.content = b"img"
        scraper._session.get.return_value = resp

        dest = tmp_path / "deep" / "nested" / "poster.jpg"
        result = scraper.download_poster("/p.jpg", dest)

        assert result is True
        assert dest.parent.is_dir()


# ---------------------------------------------------------------------------
# scrape_movies
# ---------------------------------------------------------------------------


def _make_cache(tmp_path: Path) -> LocalVideoCache:
    cache_dir = tmp_path / "movies"
    cache_dir.mkdir(parents=True, exist_ok=True)
    art_dir = cache_dir / "artwork_scraped"
    art_dir.mkdir(parents=True, exist_ok=True)
    cache = LocalVideoCache(cache_dir, has_scraped_art=True)
    return cache


class TestScrapeMovies:
    def _video(self, tmp_path: Path, stem: str) -> VideoFile:
        p = tmp_path / f"{stem}.mkv"
        p.write_bytes(b"")
        return VideoFile(title=stem, path=str(p))

    def test_skips_tombstoned_entries(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)
        cache._data = {"Tombstoned (2000)": {"tmdb_id": None}}

        item = self._video(tmp_path, "Tombstoned (2000)")

        with patch.object(scraper, "search_movie") as mock_search:
            with patch("time.sleep"):
                scraper.scrape_movies([item], cache)

        mock_search.assert_not_called()

    def test_skips_already_scraped_entries(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)
        cache._data = {"Movie (2020)": {"tmdb_id": 99}}

        item = self._video(tmp_path, "Movie (2020)")

        with patch.object(scraper, "search_movie") as mock_search:
            with patch("time.sleep"):
                scraper.scrape_movies([item], cache)

        mock_search.assert_not_called()

    def test_writes_tombstone_on_no_result(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)

        item = self._video(tmp_path, "Unknown Film (2001)")

        with patch.object(scraper, "search_movie", return_value=None):
            with patch("time.sleep"):
                scraper.scrape_movies([item], cache)

        assert cache.is_tombstoned("Unknown Film (2001)")

    def test_calls_set_entry_with_correct_fields(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)

        item = self._video(tmp_path, "The Matrix (1999)")
        tmdb_result = {
            "id": 603,
            "title": "The Matrix",
            "release_date": "1999-03-31",
            "overview": "A computer hacker learns...",
            "poster_path": None,
        }

        with patch.object(scraper, "search_movie", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_movies([item], cache)

        entry = cache.get_entry("The Matrix (1999)")
        assert entry is not None
        assert entry["title"] == "The Matrix"
        assert entry["year"] == 1999
        assert entry["description"] == "A computer hacker learns..."
        assert entry["tmdb_id"] == 603
        assert entry["genres"] == []
        assert entry["rating"] == ""
        assert entry["poster_scraped"] == ""

    def test_sets_poster_scraped_when_poster_downloaded(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)

        item = self._video(tmp_path, "Inception (2010)")
        tmdb_result = {
            "id": 27205,
            "title": "Inception",
            "release_date": "2010-07-16",
            "overview": "A thief...",
            "poster_path": "/poster.jpg",
        }

        with patch.object(scraper, "search_movie", return_value=tmdb_result):
            with patch.object(scraper, "download_poster", return_value=True) as mock_dl:
                with patch("time.sleep"):
                    scraper.scrape_movies([item], cache)

        entry = cache.get_entry("Inception (2010)")
        assert entry is not None
        expected_dest = cache._scraped_art_dir / "Inception (2010).jpg"
        assert entry["poster_scraped"] == str(expected_dest)
        mock_dl.assert_called_once_with("/poster.jpg", expected_dest)

    def test_leaves_poster_scraped_empty_when_no_poster_path(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)

        item = self._video(tmp_path, "No Poster (2005)")
        tmdb_result = {
            "id": 1,
            "title": "No Poster",
            "release_date": "2005-01-01",
            "overview": "",
            "poster_path": None,
        }

        with patch.object(scraper, "search_movie", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_movies([item], cache)

        entry = cache.get_entry("No Poster (2005)")
        assert entry["poster_scraped"] == ""

    def test_calls_on_progress_after_each_item(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_cache(tmp_path)

        items = [self._video(tmp_path, f"Film{i} ({2000 + i})") for i in range(3)]
        tmdb_result = {
            "id": 1,
            "title": "Film",
            "release_date": "2000-01-01",
            "overview": "",
            "poster_path": None,
        }

        progress_calls = []

        with patch.object(scraper, "search_movie", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_movies(items, cache, on_progress=lambda d, t: progress_calls.append((d, t)))

        assert progress_calls == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# scrape_tv_shows
# ---------------------------------------------------------------------------


def _make_show(name: str) -> Show:
    s = Show(name=name, path=f"/media/{name}")
    s.seasons = [Season(name="Season 1", number=1, episodes=[])]
    return s


def _make_tv_cache(tmp_path: Path) -> LocalVideoCache:
    cache_dir = tmp_path / "tv_shows"
    cache_dir.mkdir(parents=True, exist_ok=True)
    art_dir = cache_dir / "artwork_scraped"
    art_dir.mkdir(parents=True, exist_ok=True)
    cache = LocalVideoCache(cache_dir, has_scraped_art=True)
    return cache


class TestScrapeTvShows:
    def test_uses_show_name_as_key(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        show = _make_show("Breaking Bad")
        tmdb_result = {
            "id": 1396,
            "name": "Breaking Bad",
            "first_air_date": "2008-01-20",
            "overview": "A chemistry teacher...",
            "poster_path": None,
        }

        with patch.object(scraper, "search_tv_show", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_tv_shows([show], cache)

        entry = cache.get_entry("Breaking Bad")
        assert entry is not None
        assert entry["title"] == "Breaking Bad"
        assert entry["tmdb_id"] == 1396

    def test_entry_uses_name_field_as_title(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        show = _make_show("breaking bad")  # folder may differ from TMDb name
        tmdb_result = {
            "id": 1396,
            "name": "Breaking Bad",
            "first_air_date": "2008-01-20",
            "overview": "A chemistry teacher...",
            "poster_path": None,
        }

        with patch.object(scraper, "search_tv_show", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_tv_shows([show], cache)

        entry = cache.get_entry("breaking bad")
        assert entry["title"] == "Breaking Bad"

    def test_uses_first_air_date_as_year(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        show = _make_show("Succession")
        tmdb_result = {
            "id": 999,
            "name": "Succession",
            "first_air_date": "2018-06-03",
            "overview": "Power struggle...",
            "poster_path": None,
        }

        with patch.object(scraper, "search_tv_show", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_tv_shows([show], cache)

        entry = cache.get_entry("Succession")
        assert entry["year"] == 2018

    def test_writes_tombstone_on_no_result(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        show = _make_show("Unknown Show")

        with patch.object(scraper, "search_tv_show", return_value=None):
            with patch("time.sleep"):
                scraper.scrape_tv_shows([show], cache)

        assert cache.is_tombstoned("Unknown Show")

    def test_skips_tombstoned(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        cache._data = {"Tombstoned Show": {"tmdb_id": None}}
        show = _make_show("Tombstoned Show")

        with patch.object(scraper, "search_tv_show") as mock_search:
            with patch("time.sleep"):
                scraper.scrape_tv_shows([show], cache)

        mock_search.assert_not_called()

    def test_poster_scraped_set_when_downloaded(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        show = _make_show("Westworld")
        tmdb_result = {
            "id": 1000,
            "name": "Westworld",
            "first_air_date": "2016-10-02",
            "overview": "Androids in a park...",
            "poster_path": "/ww.jpg",
        }

        with patch.object(scraper, "search_tv_show", return_value=tmdb_result):
            with patch.object(scraper, "download_poster", return_value=True):
                with patch("time.sleep"):
                    scraper.scrape_tv_shows([show], cache)

        entry = cache.get_entry("Westworld")
        expected_dest = cache._scraped_art_dir / "Westworld.jpg"
        assert entry["poster_scraped"] == str(expected_dest)

    def test_calls_on_progress_after_each_item(self, tmp_path: Path) -> None:
        scraper = _make_scraper()
        cache = _make_tv_cache(tmp_path)
        shows = [_make_show(f"Show{i}") for i in range(2)]
        tmdb_result = {
            "id": 1,
            "name": "Show",
            "first_air_date": "2020-01-01",
            "overview": "",
            "poster_path": None,
        }

        progress_calls = []

        with patch.object(scraper, "search_tv_show", return_value=tmdb_result):
            with patch("time.sleep"):
                scraper.scrape_tv_shows(shows, cache, on_progress=lambda d, t: progress_calls.append((d, t)))

        assert progress_calls == [(1, 2), (2, 2)]
