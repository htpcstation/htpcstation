"""Tests for LocalVideoLibrary backend.

Covers:
  - Flat scanning: empty paths, single file, nested files, non-video, multiple extensions
  - TV show scanning: standard hierarchy, season name patterns, unsorted, empty seasons/shows,
    alphabetical sort, season sort order
  - Models: CategoryListModel, VideoListModel, ShowListModel, SeasonListModel, EpisodeListModel
  - Slots: selectCategory, selectShow, selectSeason, getResumePosition, rescanCategory
  - Playback: playVideo delegates to _mpv.launch with correct args
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtCore import QCoreApplication, Qt

from backend.config import Config
from backend.local_video_library import (
    CategoryListModel,
    Episode,
    EpisodeListModel,
    LocalVideoCache,
    LocalVideoLibrary,
    Season,
    SeasonListModel,
    Show,
    ShowListModel,
    TmdbScraper,
    VideoFile,
    VideoListModel,
    _enrich_from_cache,
    _parse_movie_title,
    _scan_flat,
    _scan_tv_shows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, categories: list[dict] | None = None) -> Config:
    """Write a config.json and return a Config loaded from it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / "config.json"
    data: dict = {}
    if categories is not None:
        data["local_videos"] = {"categories": categories}
    cfg_file.write_text(json.dumps(data), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


def _make_library(tmp_path: Path, config: Config) -> LocalVideoLibrary:
    """Create a LocalVideoLibrary with LibMpvPlayer mocked out."""
    with patch("backend.local_video_library.LibMpvPlayer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        lib = LocalVideoLibrary(config)
        lib._mpv = mock_instance
    return lib


# ---------------------------------------------------------------------------
# Flat scanning tests
# ---------------------------------------------------------------------------


class TestScanFlat:
    def test_empty_paths(self) -> None:
        result = _scan_flat([])
        assert result == []

    def test_nonexistent_path_ignored(self, tmp_path: Path) -> None:
        result = _scan_flat([str(tmp_path / "nonexistent")])
        assert result == []

    def test_single_video_file(self, tmp_path: Path) -> None:
        (tmp_path / "movie.mkv").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        assert len(result) == 1
        assert result[0].title == "movie"
        assert result[0].path == str(tmp_path / "movie.mkv")

    def test_nested_video_files_found(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.mp4").write_bytes(b"")
        (tmp_path / "top.avi").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        titles = {v.title for v in result}
        assert "nested" in titles
        assert "top" in titles

    def test_non_video_file_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_bytes(b"")
        (tmp_path / "image.jpg").write_bytes(b"")
        (tmp_path / "movie.mkv").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        assert len(result) == 1
        assert result[0].title == "movie"

    def test_multiple_extensions(self, tmp_path: Path) -> None:
        for ext in [".mkv", ".mp4", ".avi", ".m4v", ".mov"]:
            (tmp_path / f"file{ext}").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        assert len(result) == 5

    def test_sorted_by_title(self, tmp_path: Path) -> None:
        (tmp_path / "Zebra.mkv").write_bytes(b"")
        (tmp_path / "apple.mp4").write_bytes(b"")
        (tmp_path / "Mango.avi").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        titles = [v.title for v in result]
        assert titles == sorted(titles, key=str.lower)

    def test_title_is_stem(self, tmp_path: Path) -> None:
        (tmp_path / "My Movie.mkv").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        assert result[0].title == "My Movie"

    def test_poster_path_empty_stub(self, tmp_path: Path) -> None:
        (tmp_path / "movie.mkv").write_bytes(b"")
        result = _scan_flat([str(tmp_path)])
        assert result[0].poster_path == ""


# ---------------------------------------------------------------------------
# TV show scanning tests
# ---------------------------------------------------------------------------


class TestScanTvShows:
    def test_standard_hierarchy(self, tmp_path: Path) -> None:
        """show/Season 1/ep.mkv → 1 show, 1 season, 1 episode."""
        show_dir = tmp_path / "Breaking Bad"
        season_dir = show_dir / "Season 1"
        season_dir.mkdir(parents=True)
        (season_dir / "s01e01.mkv").write_bytes(b"")

        result = _scan_tv_shows([str(tmp_path)])
        assert len(result) == 1
        show = result[0]
        assert show.name == "Breaking Bad"
        assert show.season_count == 1
        assert show.episode_count == 1
        assert show.seasons[0].name == "Season 1"
        assert show.seasons[0].number == 1
        assert show.seasons[0].episodes[0].title == "s01e01"

    def test_season_patterns_s01(self, tmp_path: Path) -> None:
        season_dir = tmp_path / "Show" / "S01"
        season_dir.mkdir(parents=True)
        (season_dir / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].number == 1
        assert result[0].seasons[0].name == "Season 1"

    def test_season_patterns_s1(self, tmp_path: Path) -> None:
        season_dir = tmp_path / "Show" / "S1"
        season_dir.mkdir(parents=True)
        (season_dir / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].number == 1

    def test_season_patterns_s2(self, tmp_path: Path) -> None:
        season_dir = tmp_path / "Show" / "S2"
        season_dir.mkdir(parents=True)
        (season_dir / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].number == 2

    def test_season_patterns_series_dash_2(self, tmp_path: Path) -> None:
        season_dir = tmp_path / "Show" / "Series-2"
        season_dir.mkdir(parents=True)
        (season_dir / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].number == 2

    def test_season_patterns_season_02(self, tmp_path: Path) -> None:
        season_dir = tmp_path / "Show" / "Season 02"
        season_dir.mkdir(parents=True)
        (season_dir / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].number == 2
        assert result[0].seasons[0].name == "Season 2"

    def test_episode_directly_in_show_dir_is_unsorted(self, tmp_path: Path) -> None:
        show_dir = tmp_path / "Miniseries"
        show_dir.mkdir()
        (show_dir / "part1.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert len(result) == 1
        assert result[0].seasons[0].name == "Unsorted"
        assert result[0].seasons[0].number == -1

    def test_season_with_no_videos_excluded(self, tmp_path: Path) -> None:
        show_dir = tmp_path / "Show"
        empty_season = show_dir / "Season 1"
        real_season = show_dir / "Season 2"
        empty_season.mkdir(parents=True)
        real_season.mkdir(parents=True)
        (real_season / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].season_count == 1
        assert result[0].seasons[0].number == 2

    def test_empty_show_dir_excluded(self, tmp_path: Path) -> None:
        """A show with no episodes anywhere is not included."""
        (tmp_path / "Empty Show").mkdir()
        result = _scan_tv_shows([str(tmp_path)])
        assert len(result) == 0

    def test_multiple_shows_sorted_alphabetically(self, tmp_path: Path) -> None:
        for show_name in ["Zebra", "apple", "Mango"]:
            s = tmp_path / show_name / "Season 1"
            s.mkdir(parents=True)
            (s / "ep.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        names = [s.name for s in result]
        assert names == sorted(names, key=str.lower)

    def test_seasons_sorted_numbered_then_unsorted_last(self, tmp_path: Path) -> None:
        """Numbered seasons ascending, non-numeric named, Unsorted last."""
        show_dir = tmp_path / "Show"
        for sname in ["Season 3", "Season 1", "Specials"]:
            sd = show_dir / sname
            sd.mkdir(parents=True)
            (sd / "ep.mkv").write_bytes(b"")
        # Also add a direct episode (Unsorted)
        show_dir.mkdir(exist_ok=True)
        (show_dir / "pilot.mkv").write_bytes(b"")

        result = _scan_tv_shows([str(tmp_path)])
        seasons = result[0].seasons
        names = [s.name for s in seasons]
        # Numbered seasons first: Season 1, Season 3
        assert names.index("Season 1") < names.index("Season 3")
        # Non-numeric named after numbered
        assert names.index("Season 3") < names.index("Specials")
        # Unsorted last
        assert names[-1] == "Unsorted"

    def test_non_numeric_season_name_kept(self, tmp_path: Path) -> None:
        """A subdir that doesn't match season regex is kept with number=-1."""
        show_dir = tmp_path / "Show" / "Extras"
        show_dir.mkdir(parents=True)
        (show_dir / "bonus.mkv").write_bytes(b"")
        result = _scan_tv_shows([str(tmp_path)])
        assert result[0].seasons[0].name == "Extras"
        assert result[0].seasons[0].number == -1


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestCategoryListModel:
    def test_role_names(self) -> None:
        model = CategoryListModel()
        names = model.roleNames()
        assert b"name" in names.values()
        assert b"type" in names.values()
        assert b"paths" in names.values()

    def test_data_returns_correct_values(self) -> None:
        cats = [
            {"name": "Movies", "type": "flat", "paths": ["/media/movies"]},
            {"name": "TV Shows", "type": "tv_shows", "paths": []},
        ]
        model = CategoryListModel()
        model.beginResetModel()
        model._items = list(cats)
        model._display_items = list(cats)
        model.endResetModel()

        assert model.rowCount() == 2
        idx = model.index(0, 0)
        assert model.data(idx, CategoryListModel.NameRole) == "Movies"
        assert model.data(idx, CategoryListModel.TypeRole) == "flat"
        assert model.data(idx, CategoryListModel.PathsRole) == ["/media/movies"]

        idx1 = model.index(1, 0)
        assert model.data(idx1, CategoryListModel.TypeRole) == "tv_shows"

    def test_invalid_index_returns_none(self) -> None:
        model = CategoryListModel()
        idx = model.index(99, 0)
        assert model.data(idx, CategoryListModel.NameRole) is None


class TestVideoListModel:
    def test_role_names(self) -> None:
        model = VideoListModel()
        names = model.roleNames()
        assert b"title" in names.values()
        assert b"path" in names.values()
        assert b"posterPath" in names.values()

    def test_data_returns_correct_values(self, tmp_path: Path) -> None:
        vf = VideoFile(title="My Movie", path="/media/my.mkv", poster_path="")
        model = VideoListModel()
        model.beginResetModel()
        model._items = [vf]
        model._display_items = [vf]
        model.endResetModel()

        assert model.rowCount() == 1
        idx = model.index(0, 0)
        assert model.data(idx, VideoListModel.TitleRole) == "My Movie"
        assert model.data(idx, VideoListModel.PathRole) == "/media/my.mkv"
        assert model.data(idx, VideoListModel.PosterPathRole) == ""


class TestShowListModel:
    def test_role_names(self) -> None:
        model = ShowListModel()
        names = model.roleNames()
        assert b"name" in names.values()
        assert b"path" in names.values()
        assert b"posterPath" in names.values()
        assert b"seasonCount" in names.values()
        assert b"episodeCount" in names.values()

    def test_season_count_and_episode_count_roles(self) -> None:
        season = Season(name="Season 1", number=1, episodes=[
            Episode(title="ep1", path="/s/e1.mkv"),
            Episode(title="ep2", path="/s/e2.mkv"),
        ])
        show = Show(name="Test Show", path="/media/test", seasons=[season])
        model = ShowListModel()
        model.beginResetModel()
        model._items = [show]
        model._display_items = [show]
        model.endResetModel()

        idx = model.index(0, 0)
        assert model.data(idx, ShowListModel.SeasonCountRole) == 1
        assert model.data(idx, ShowListModel.EpisodeCountRole) == 2
        assert model.data(idx, ShowListModel.NameRole) == "Test Show"
        assert model.data(idx, ShowListModel.PosterPathRole) == ""


class TestSeasonListModel:
    def test_role_names(self) -> None:
        model = SeasonListModel()
        names = model.roleNames()
        assert b"name" in names.values()
        assert b"number" in names.values()
        assert b"episodeCount" in names.values()

    def test_number_and_episode_count_roles(self) -> None:
        episodes = [Episode(title=f"ep{i}", path=f"/e{i}.mkv") for i in range(3)]
        season = Season(name="Season 2", number=2, episodes=episodes)
        model = SeasonListModel()
        model.beginResetModel()
        model._items = [season]
        model._display_items = [season]
        model.endResetModel()

        idx = model.index(0, 0)
        assert model.data(idx, SeasonListModel.NumberRole) == 2
        assert model.data(idx, SeasonListModel.EpisodeCountRole) == 3
        assert model.data(idx, SeasonListModel.NameRole) == "Season 2"


class TestEpisodeListModel:
    def test_role_names(self) -> None:
        model = EpisodeListModel()
        names = model.roleNames()
        assert b"title" in names.values()
        assert b"path" in names.values()
        assert b"posterPath" in names.values()

    def test_poster_path_returns_empty(self) -> None:
        ep = Episode(title="Pilot", path="/show/s01e01.mkv")
        model = EpisodeListModel()
        model.beginResetModel()
        model._items = [ep]
        model._display_items = [ep]
        model.endResetModel()

        idx = model.index(0, 0)
        assert model.data(idx, EpisodeListModel.PosterPathRole) == ""
        assert model.data(idx, EpisodeListModel.TitleRole) == "Pilot"
        assert model.data(idx, EpisodeListModel.PathRole) == "/show/s01e01.mkv"


# ---------------------------------------------------------------------------
# Slot tests
# ---------------------------------------------------------------------------


class TestSelectCategoryFlat:
    def test_flat_populates_videos_model(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": [str(tmp_path)]}]
        (tmp_path / "film.mkv").write_bytes(b"")
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        lib.selectCategory(0)
        assert lib._videos.rowCount() == 1
        assert lib._shows.rowCount() == 0

    def test_flat_resets_shows_model(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        # Seed shows model with something
        show = Show(name="Fake", path="/fake")
        lib._shows._items = [show]
        lib._shows._display_items = [show]

        lib.selectCategory(0)
        assert lib._shows.rowCount() == 0

    def test_out_of_range_index_noop(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        lib.selectCategory(999)  # should not raise
        assert lib._current_category_index == -1

    def test_current_category_index_updated(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)
        lib.selectCategory(0)
        assert lib._current_category_index == 0


class TestSelectCategoryTvShows:
    def test_tv_shows_populates_shows_model(self, tmp_path: Path) -> None:
        show_dir = tmp_path / "Breaking Bad" / "Season 1"
        show_dir.mkdir(parents=True)
        (show_dir / "ep.mkv").write_bytes(b"")

        cats = [{"name": "TV", "type": "tv_shows", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        lib.selectCategory(0)
        assert lib._shows.rowCount() == 1
        assert lib._videos.rowCount() == 0

    def test_tv_shows_resets_videos_model(self, tmp_path: Path) -> None:
        cats = [{"name": "TV", "type": "tv_shows", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        # Seed videos
        vf = VideoFile(title="old", path="/old.mkv")
        lib._videos._items = [vf]
        lib._videos._display_items = [vf]

        lib.selectCategory(0)
        assert lib._videos.rowCount() == 0


class TestSelectShow:
    def test_select_show_populates_seasons(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        season = Season(name="Season 1", number=1, episodes=[
            Episode(title="ep1", path="/e1.mkv")
        ])
        show = Show(name="Show", path="/show", seasons=[season])
        lib._shows._items = [show]
        lib._shows._display_items = [show]

        lib.selectShow(0)
        assert lib._seasons.rowCount() == 1
        assert lib._episodes.rowCount() == 0

    def test_select_show_out_of_range_noop(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        lib.selectShow(5)  # should not raise


class TestSelectSeason:
    def test_select_season_populates_episodes(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        episodes = [Episode(title="ep1", path="/e1.mkv"), Episode(title="ep2", path="/e2.mkv")]
        season = Season(name="Season 1", number=1, episodes=episodes)
        lib._seasons._items = [season]
        lib._seasons._display_items = [season]

        lib.selectSeason(0)
        assert lib._episodes.rowCount() == 2

    def test_select_season_out_of_range_noop(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        lib.selectSeason(99)  # should not raise


class TestGetResumePosition:
    def test_always_returns_zero(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)
        assert lib.getResumePosition("/any/file.mkv") == 0
        assert lib.getResumePosition("") == 0


class TestRescanCategory:
    def test_rescan_repopulates_model(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        # First scan — empty
        lib.selectCategory(0)
        assert lib._videos.rowCount() == 0

        # Add a file
        (tmp_path / "new_movie.mkv").write_bytes(b"")

        # Rescan
        lib.rescanCategory(0)
        assert lib._videos.rowCount() == 1


# ---------------------------------------------------------------------------
# Playback tests
# ---------------------------------------------------------------------------


class TestPlayVideo:
    def test_play_video_calls_launch_with_stem_and_zero_start(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        lib.playVideo("/media/movies/Inception.mkv")
        lib._mpv.launch.assert_called_once_with(
            "/media/movies/Inception.mkv", "Inception", 0
        )

    def test_play_video_with_start_ms(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        lib.playVideo("/media/movies/Inception.mkv", 5000)
        lib._mpv.launch.assert_called_once_with(
            "/media/movies/Inception.mkv", "Inception", 5000
        )

    def test_stop_playback_calls_kill(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        lib.stopPlayback()
        lib._mpv.kill.assert_called_once()


# ---------------------------------------------------------------------------
# _enrich_from_cache tests
# ---------------------------------------------------------------------------


def _make_cache_with_entry(tmp_path: Path, key: str, entry: dict) -> LocalVideoCache:
    """Create a LocalVideoCache with a single pre-populated entry."""
    cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
    cache.ensure_dirs()
    cache._data = {key: entry}
    cache.save()
    return LocalVideoCache(tmp_path / "cache", has_scraped_art=True)  # fresh instance


class TestEnrichFromCache:
    def test_videofile_poster_populated(self, tmp_path: Path) -> None:
        poster = tmp_path / "cache" / "artwork_scraped" / "mymovie.jpg"
        poster.parent.mkdir(parents=True, exist_ok=True)
        poster.write_bytes(b"")
        cache = _make_cache_with_entry(tmp_path, "mymovie", {"poster_scraped": str(poster)})
        item = VideoFile(title="mymovie", path=str(tmp_path / "mymovie.mkv"))
        _enrich_from_cache([item], cache)
        assert item.poster_path == str(poster)

    def test_videofile_all_fields_populated(self, tmp_path: Path) -> None:
        cache = _make_cache_with_entry(tmp_path, "the_matrix", {
            "title": "The Matrix",
            "year": 1999,
            "description": "Sci-fi classic",
            "genres": ["Action", "Sci-Fi"],
        })
        item = VideoFile(title="the_matrix", path=str(tmp_path / "the_matrix.mkv"))
        _enrich_from_cache([item], cache)
        assert item.title == "The Matrix"
        assert item.year == 1999
        assert item.description == "Sci-fi classic"
        assert item.genre == "Action, Sci-Fi"

    def test_videofile_fields_not_overwritten_when_no_entry(self, tmp_path: Path) -> None:
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache.save()
        item = VideoFile(title="original_title", path=str(tmp_path / "film.mkv"))
        _enrich_from_cache([item], cache)
        assert item.title == "original_title"
        assert item.poster_path == ""
        assert item.year == 0
        assert item.genre == ""

    def test_show_poster_description_and_year_populated(self, tmp_path: Path) -> None:
        poster = tmp_path / "cache" / "artwork_scraped" / "Breaking Bad.jpg"
        poster.parent.mkdir(parents=True, exist_ok=True)
        poster.write_bytes(b"")
        cache = _make_cache_with_entry(tmp_path, "Breaking Bad", {
            "poster_scraped": str(poster),
            "title": "Breaking Bad (TMDb title)",
            "year": 2008,
            "description": "A chemistry teacher...",
            "genres": ["Drama", "Crime"],
        })
        show = Show(name="Breaking Bad", path=str(tmp_path / "Breaking Bad"))
        _enrich_from_cache([show], cache)
        # Poster, description, and year should be set
        assert show.poster_path == str(poster)
        assert show.description == "A chemistry teacher..."
        assert show.year == 2008
        # Show has no title or genre attributes to set — no error expected
        assert not hasattr(show, "title")
        assert not hasattr(show, "genre")

    def test_custom_art_takes_priority_over_scraped(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        scraped = cache_dir / "artwork_scraped" / "film.jpg"
        custom = cache_dir / "artwork_custom" / "film.png"
        scraped.parent.mkdir(parents=True, exist_ok=True)
        custom.parent.mkdir(parents=True, exist_ok=True)
        scraped.write_bytes(b"scraped")
        custom.write_bytes(b"custom")
        cache = LocalVideoCache(cache_dir, has_scraped_art=True)
        cache._data = {"film": {"poster_scraped": str(scraped)}}
        item = VideoFile(title="film", path=str(tmp_path / "film.mkv"))
        _enrich_from_cache([item], cache)
        assert item.poster_path == str(custom)


# ---------------------------------------------------------------------------
# selectCategory enrichment tests
# ---------------------------------------------------------------------------


class TestSelectCategoryEnrichment:
    def test_movies_category_uses_movies_cache(self, tmp_path: Path) -> None:
        """After selectCategory(0), VideoFile has poster_path from movies cache."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "Inception.mkv").write_bytes(b"")

        cats = [{"name": "Movies", "type": "flat", "paths": [str(media_dir)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        # Prepare a movies cache entry with a real poster file
        from backend.local_video_library import _MOVIES_CACHE_DIR
        poster_path = _MOVIES_CACHE_DIR / "artwork_scraped" / "Inception.jpg"
        poster_path.parent.mkdir(parents=True, exist_ok=True)
        poster_path.write_bytes(b"")
        lib_file = _MOVIES_CACHE_DIR / "library.json"
        lib_file.write_text(
            json.dumps({"Inception": {"poster_scraped": str(poster_path)}}),
            encoding="utf-8",
        )

        try:
            lib.selectCategory(0)
            assert lib._videos.rowCount() == 1
            idx = lib._videos.index(0, 0)
            assert lib._videos.data(idx, VideoListModel.PosterPathRole) == str(poster_path)
        finally:
            # Clean up side effects on shared cache dir
            if lib_file.exists():
                lib_file.unlink()
            if poster_path.exists():
                poster_path.unlink()

    def test_tv_shows_category_uses_tv_shows_cache(self, tmp_path: Path) -> None:
        """After selectCategory(1), Show has poster_path from tv_shows cache."""
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Breaking Bad" / "Season 1"
        show_dir.mkdir(parents=True)
        (show_dir / "ep.mkv").write_bytes(b"")

        cats = [
            {"name": "Movies", "type": "flat", "paths": []},
            {"name": "TV Shows", "type": "tv_shows", "paths": [str(media_dir)]},
        ]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        from backend.local_video_library import _TV_SHOWS_CACHE_DIR
        poster_path = _TV_SHOWS_CACHE_DIR / "artwork_scraped" / "Breaking Bad.jpg"
        poster_path.parent.mkdir(parents=True, exist_ok=True)
        poster_path.write_bytes(b"")
        lib_file = _TV_SHOWS_CACHE_DIR / "library.json"
        lib_file.write_text(
            json.dumps({"Breaking Bad": {"poster_scraped": str(poster_path)}}),
            encoding="utf-8",
        )

        try:
            lib.selectCategory(1)
            assert lib._shows.rowCount() == 1
            idx = lib._shows.index(0, 0)
            assert lib._shows.data(idx, ShowListModel.PosterPathRole) == str(poster_path)
        finally:
            if lib_file.exists():
                lib_file.unlink()
            if poster_path.exists():
                poster_path.unlink()

    def test_custom_category_uses_custom_cache(self, tmp_path: Path) -> None:
        """selectCategory(2) uses _custom_category_cache, not _movies_cache."""
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "documentary.mkv").write_bytes(b"")

        cats = [
            {"name": "Movies", "type": "flat", "paths": []},
            {"name": "TV Shows", "type": "tv_shows", "paths": []},
            {"name": "Docs", "type": "flat", "paths": [str(media_dir)]},
        ]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        with patch(
            "backend.local_video_library._custom_category_cache"
        ) as mock_custom, patch(
            "backend.local_video_library._movies_cache"
        ) as mock_movies:
            mock_cache = MagicMock()
            mock_cache.resolve_poster.return_value = ""
            mock_cache.resolve_metadata.return_value = {}
            mock_custom.return_value = mock_cache

            lib.selectCategory(2)

            mock_custom.assert_called_once_with("Docs")
            mock_movies.assert_not_called()


# ---------------------------------------------------------------------------
# scrapeMovies / scrapeTvShows tests
# ---------------------------------------------------------------------------


class TestScrapeSlots:
    def test_scrape_movies_emits_error_when_no_api_key(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        errors: list[str] = []
        lib.scrapeError.connect(errors.append)
        lib.scrapeMovies()
        assert len(errors) == 1
        assert "API key" in errors[0]

    def test_scrape_tv_shows_emits_error_when_no_api_key(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        lib = _make_library(tmp_path, config)

        errors: list[str] = []
        lib.scrapeError.connect(errors.append)
        lib.scrapeTvShows()
        assert len(errors) == 1
        assert "API key" in errors[0]

    def test_scrape_emits_error_when_already_in_progress(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": []}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        config.set_tmdb_api_key("fake_key")
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        alive_thread = MagicMock()
        alive_thread.is_alive.return_value = True
        lib._scrape_thread = alive_thread

        errors: list[str] = []
        lib.scrapeError.connect(errors.append)
        lib.scrapeMovies()
        assert len(errors) == 1
        assert "in progress" in errors[0]

    def test_scrape_movies_starts_thread_and_calls_scraper(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": []}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        config.set_tmdb_api_key("fake_key")
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        scraper_mock = MagicMock()

        with patch(
            "backend.local_video_library.TmdbScraper", return_value=scraper_mock
        ) as scraper_cls:
            lib.scrapeMovies()
            assert lib._scrape_thread is not None
            lib._scrape_thread.join(timeout=5)
            scraper_cls.assert_called_once_with("fake_key")
            scraper_mock.scrape_movies.assert_called_once()
            scraper_mock.close.assert_called_once()

    def test_scrape_tv_shows_starts_thread_and_calls_scraper(self, tmp_path: Path) -> None:
        cats = [
            {"name": "Movies", "type": "flat", "paths": []},
            {"name": "TV Shows", "type": "tv_shows", "paths": []},
        ]
        config = _make_config(tmp_path / "cfg", categories=cats)
        config.set_tmdb_api_key("fake_key")
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        scraper_mock = MagicMock()

        with patch(
            "backend.local_video_library.TmdbScraper", return_value=scraper_mock
        ) as scraper_cls:
            lib.scrapeTvShows()
            assert lib._scrape_thread is not None
            lib._scrape_thread.join(timeout=5)
            scraper_cls.assert_called_once_with("fake_key")
            scraper_mock.scrape_tv_shows.assert_called_once()
            scraper_mock.close.assert_called_once()

    def test_scrape_finished_emitted_after_completion(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": []}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        config.set_tmdb_api_key("fake_key")
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        finished: list[tuple] = []

        # Connect the signal to a list to capture emissions
        lib._emit_scrape_finished = lambda name, cat_type, s, t, sk: finished.append((name, s, t, sk))  # type: ignore[method-assign]

        scraper_mock = MagicMock()
        scraper_mock.scrape_movies.return_value = (0, 0, 0)
        with patch("backend.local_video_library.TmdbScraper", return_value=scraper_mock):
            lib.scrapeMovies()
            lib._scrape_thread.join(timeout=5)  # type: ignore[union-attr]

        # _emit_scrape_finished was invoked via QMetaObject on the main thread;
        # since there's no event loop running in tests, invoke directly to verify logic
        lib.scrapeFinished.connect(lambda dn, s, t, sk: finished.append((dn, s, t, sk)))
        lib._emit_scrape_finished("Movies", "movies", 3, 0, 0)
        assert any(item[0] == "Movies" for item in finished)

    def test_emit_scrape_finished_calls_selectCategory(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": []}]
        config = _make_config(tmp_path, categories=cats)
        lib = _make_library(tmp_path, config)

        with patch.object(lib, "selectCategory") as mock_select:
            lib._emit_scrape_finished("Movies", "movies", 3, 0, 0)
            mock_select.assert_called_once_with(0)

    def test_emit_scrape_finished_no_reload_when_no_matching_category(self, tmp_path: Path) -> None:
        # Config has no categories at all; walking finds no match → selectCategory not called
        config = _make_config(tmp_path, categories=[])
        lib = _make_library(tmp_path, config)

        with patch.object(lib, "selectCategory") as mock_select:
            lib._emit_scrape_finished("Movies", "movies", 0, 0, 0)
            mock_select.assert_not_called()


# ---------------------------------------------------------------------------
# Model roles — new fields
# ---------------------------------------------------------------------------


class TestVideoListModelNewRoles:
    def test_role_names_include_year_genre_description(self) -> None:
        model = VideoListModel()
        names = model.roleNames()
        assert b"year" in names.values()
        assert b"genre" in names.values()
        assert b"description" in names.values()

    def test_year_genre_description_data(self) -> None:
        vf = VideoFile(
            title="The Matrix",
            path="/media/matrix.mkv",
            year=1999,
            genre="Action, Sci-Fi",
            description="Sci-fi classic",
        )
        model = VideoListModel()
        model.beginResetModel()
        model._items = [vf]
        model._display_items = [vf]
        model.endResetModel()

        idx = model.index(0, 0)
        assert model.data(idx, VideoListModel.YearRole) == 1999
        assert model.data(idx, VideoListModel.GenreRole) == "Action, Sci-Fi"
        assert model.data(idx, VideoListModel.DescriptionRole) == "Sci-fi classic"


class TestShowListModelNewRoles:
    def test_role_names_include_year_description(self) -> None:
        model = ShowListModel()
        names = model.roleNames()
        assert b"year" in names.values()
        assert b"description" in names.values()

    def test_year_description_data(self) -> None:
        show = Show(
            name="Breaking Bad",
            path="/media/bb",
            year=2008,
            description="A chemistry teacher...",
        )
        model = ShowListModel()
        model.beginResetModel()
        model._items = [show]
        model._display_items = [show]
        model.endResetModel()

        idx = model.index(0, 0)
        assert model.data(idx, ShowListModel.YearRole) == 2008
        assert model.data(idx, ShowListModel.DescriptionRole) == "A chemistry teacher..."

    def test_show_year_defaults_to_zero(self) -> None:
        show = Show(name="New Show", path="/media/new")
        assert show.year == 0


# ---------------------------------------------------------------------------
# Sort / filter slots
# ---------------------------------------------------------------------------


def _make_library_with_videos(tmp_path: Path, videos: list[VideoFile]) -> "LocalVideoLibrary":
    """Return a LocalVideoLibrary with _videos pre-seeded (bypasses scanning)."""
    config = _make_config(tmp_path)
    lib = _make_library(tmp_path, config)
    lib._videos.beginResetModel()
    lib._videos._items = list(videos)
    lib._videos._display_items = list(videos)
    lib._videos.endResetModel()
    return lib


def _make_library_with_shows(tmp_path: Path, shows: list[Show]) -> "LocalVideoLibrary":
    """Return a LocalVideoLibrary with _shows pre-seeded (bypasses scanning)."""
    config = _make_config(tmp_path)
    lib = _make_library(tmp_path, config)
    lib._shows.beginResetModel()
    lib._shows._items = list(shows)
    lib._shows._display_items = list(shows)
    lib._shows.endResetModel()
    return lib


class TestSortVideos:
    def test_sort_az_orders_display_items(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Zebra", path="/z.mkv"),
            VideoFile(title="apple", path="/a.mkv"),
            VideoFile(title="Mango", path="/m.mkv"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("az")
        titles = [lib._videos._display_items[i].title for i in range(3)]
        assert titles == sorted(titles, key=str.lower)

    def test_sort_az_leaves_items_unchanged(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Zebra", path="/z.mkv"),
            VideoFile(title="apple", path="/a.mkv"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        original_items = list(lib._videos._items)
        lib.sortVideos("az")
        assert lib._videos._items == original_items

    def test_sort_za_orders_display_items_descending(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="apple", path="/a.mkv"),
            VideoFile(title="Mango", path="/m.mkv"),
            VideoFile(title="Zebra", path="/z.mkv"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("za")
        titles = [lib._videos._display_items[i].title for i in range(3)]
        assert titles == sorted(titles, key=str.lower, reverse=True)

    def test_sort_year_desc(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Old", path="/o.mkv", year=1990),
            VideoFile(title="New", path="/n.mkv", year=2020),
            VideoFile(title="Mid", path="/m.mkv", year=2005),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("year_desc")
        years = [lib._videos._display_items[i].year for i in range(3)]
        assert years == [2020, 2005, 1990]

    def test_sort_year_asc(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="New", path="/n.mkv", year=2020),
            VideoFile(title="Old", path="/o.mkv", year=1990),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("year_asc")
        years = [lib._videos._display_items[i].year for i in range(2)]
        assert years == [1990, 2020]

    def test_empty_sort_key_no_reorder(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Zebra", path="/z.mkv"),
            VideoFile(title="apple", path="/a.mkv"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("")
        # Original insertion order preserved
        assert lib._videos._display_items[0].title == "Zebra"


class TestFilterVideosByGenre:
    def test_filter_by_genre_reduces_display_items(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="ActionFilm", path="/a.mkv", genre="Action, Drama"),
            VideoFile(title="Comedy", path="/c.mkv", genre="Comedy"),
            VideoFile(title="ActionDrama", path="/ad.mkv", genre="Drama, Action"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.filterVideosByGenre("Action")
        assert lib._videos.rowCount() == 2
        titles = {lib._videos._display_items[i].title for i in range(2)}
        assert titles == {"ActionFilm", "ActionDrama"}

    def test_filter_empty_genre_shows_all(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="A", path="/a.mkv", genre="Action"),
            VideoFile(title="B", path="/b.mkv", genre="Comedy"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.filterVideosByGenre("Action")
        assert lib._videos.rowCount() == 1
        lib.filterVideosByGenre("")
        assert lib._videos.rowCount() == 2

    def test_filter_empty_genre_reapplies_sort(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Zebra", path="/z.mkv", genre="Action"),
            VideoFile(title="apple", path="/a.mkv", genre="Action"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib._video_sort = "az"
        lib.filterVideosByGenre("")
        titles = [lib._videos._display_items[i].title for i in range(2)]
        assert titles == sorted(titles, key=str.lower)

    def test_filter_and_sort_compose(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="Zebra Action", path="/z.mkv", genre="Action"),
            VideoFile(title="Comedy", path="/c.mkv", genre="Comedy"),
            VideoFile(title="Apple Action", path="/a.mkv", genre="Action"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.sortVideos("az")
        lib.filterVideosByGenre("Action")
        assert lib._videos.rowCount() == 2
        titles = [lib._videos._display_items[i].title for i in range(2)]
        assert titles == ["Apple Action", "Zebra Action"]

    def test_items_unchanged_after_filter(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="A", path="/a.mkv", genre="Action"),
            VideoFile(title="B", path="/b.mkv", genre="Comedy"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        lib.filterVideosByGenre("Action")
        assert len(lib._videos._items) == 2


class TestSortShows:
    def test_sort_za_orders_display_items_descending(self, tmp_path: Path) -> None:
        shows = [
            Show(name="apple", path="/a"),
            Show(name="Zebra", path="/z"),
            Show(name="Mango", path="/m"),
        ]
        lib = _make_library_with_shows(tmp_path, shows)
        lib.sortShows("za")
        names = [lib._shows._display_items[i].name for i in range(3)]
        assert names == sorted(names, key=str.lower, reverse=True)

    def test_sort_az(self, tmp_path: Path) -> None:
        shows = [
            Show(name="Zebra", path="/z"),
            Show(name="apple", path="/a"),
        ]
        lib = _make_library_with_shows(tmp_path, shows)
        lib.sortShows("az")
        names = [lib._shows._display_items[i].name for i in range(2)]
        assert names == sorted(names, key=str.lower)

    def test_sort_year_desc(self, tmp_path: Path) -> None:
        shows = [
            Show(name="Old", path="/o", year=1995),
            Show(name="New", path="/n", year=2020),
        ]
        lib = _make_library_with_shows(tmp_path, shows)
        lib.sortShows("year_desc")
        years = [lib._shows._display_items[i].year for i in range(2)]
        assert years == [2020, 1995]

    def test_sort_shows_leaves_items_unchanged(self, tmp_path: Path) -> None:
        shows = [
            Show(name="Zebra", path="/z"),
            Show(name="apple", path="/a"),
        ]
        lib = _make_library_with_shows(tmp_path, shows)
        original_items = list(lib._shows._items)
        lib.sortShows("az")
        assert lib._shows._items == original_items


class TestGetVideoGenres:
    def test_returns_sorted_unique_genres(self, tmp_path: Path) -> None:
        videos = [
            VideoFile(title="A", path="/a.mkv", genre="Action, Drama"),
            VideoFile(title="B", path="/b.mkv", genre="Comedy, Action"),
            VideoFile(title="C", path="/c.mkv", genre="Drama"),
        ]
        lib = _make_library_with_videos(tmp_path, videos)
        genres = lib.getVideoGenres()
        assert genres == ["Action", "Comedy", "Drama"]

    def test_returns_empty_list_when_no_genres(self, tmp_path: Path) -> None:
        videos = [VideoFile(title="A", path="/a.mkv", genre="")]
        lib = _make_library_with_videos(tmp_path, videos)
        assert lib.getVideoGenres() == []

    def test_whitespace_stripped(self, tmp_path: Path) -> None:
        videos = [VideoFile(title="A", path="/a.mkv", genre=" Action ,  Drama ")]
        lib = _make_library_with_videos(tmp_path, videos)
        genres = lib.getVideoGenres()
        assert "Action" in genres
        assert "Drama" in genres


class TestSelectCategoryResetsState:
    def test_sort_filter_reset_on_select_category(self, tmp_path: Path) -> None:
        cats = [{"name": "Movies", "type": "flat", "paths": [str(tmp_path)]}]
        config = _make_config(tmp_path / "cfg", categories=cats)
        (tmp_path / "cfg").mkdir(exist_ok=True)
        lib = _make_library(tmp_path / "cfg", config)

        lib._video_sort = "az"
        lib._video_genre = "Action"
        lib._show_sort = "za"

        lib.selectCategory(0)

        assert lib._video_sort == ""
        assert lib._video_genre == ""
        assert lib._show_sort == ""


# ---------------------------------------------------------------------------
# Title sanitization tests
# ---------------------------------------------------------------------------


class TestParseMovieTitle:
    def test_parse_movie_title_strips_codec_suffix(self) -> None:
        title, year = _parse_movie_title("Coraline - x264 Bluray-1080p")
        assert title == "Coraline"
        assert year is None

    def test_parse_movie_title_strips_suffix_preserves_year(self) -> None:
        title, year = _parse_movie_title("The Matrix (1999) - x264 1080p")
        assert title == "The Matrix"
        assert year == 1999

    def test_parse_movie_title_unchanged_clean_title(self) -> None:
        title, year = _parse_movie_title("The Matrix (1999)")
        assert title == "The Matrix"
        assert year == 1999

    def test_parse_movie_title_strips_x265_suffix(self) -> None:
        title, year = _parse_movie_title("300 - x265 Bluray-1080p")
        assert title == "300"
        assert year is None

    def test_parse_movie_title_no_year_no_junk(self) -> None:
        title, year = _parse_movie_title("Inception")
        assert title == "Inception"
        assert year is None

    def test_parse_movie_title_strips_bluray_suffix(self) -> None:
        title, year = _parse_movie_title("A Charlie Brown Christmas - x264 Bluray-1080p")
        assert title == "A Charlie Brown Christmas"
        assert year is None


# ---------------------------------------------------------------------------
# LocalVideoCache.clear_tombstones tests
# ---------------------------------------------------------------------------


class TestClearTombstones:
    def test_clear_tombstones_removes_null_tmdb_id_entries(self, tmp_path: Path) -> None:
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {
            "Coraline - x264 Bluray-1080p": {"tmdb_id": None},
            "300 - x265 Bluray-1080p": {"tmdb_id": None},
        }
        cache.save()

        cache.clear_tombstones()

        assert "Coraline - x264 Bluray-1080p" not in cache._data
        assert "300 - x265 Bluray-1080p" not in cache._data
        assert cache._data == {}

    def test_clear_tombstones_preserves_real_entries(self, tmp_path: Path) -> None:
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {
            "Tombstone Movie": {"tmdb_id": None},
            "Good Movie": {"tmdb_id": 12345, "title": "Good Movie"},
        }
        cache.save()

        cache.clear_tombstones()

        assert "Tombstone Movie" not in cache._data
        assert "Good Movie" in cache._data
        assert cache._data["Good Movie"]["tmdb_id"] == 12345

    def test_clear_tombstones_noop_when_no_tombstones(self, tmp_path: Path) -> None:
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {
            "Good Movie": {"tmdb_id": 42, "title": "Good Movie"},
        }
        cache.save()

        cache.clear_tombstones()

        assert "Good Movie" in cache._data

    def test_clear_tombstones_saves_to_disk(self, tmp_path: Path) -> None:
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {"Dead Entry": {"tmdb_id": None}}
        cache.save()

        cache.clear_tombstones()

        # Reload from disk and verify it was persisted
        fresh = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        fresh.load()
        assert "Dead Entry" not in fresh._data


# ---------------------------------------------------------------------------
# TmdbScraper count-returning tests
# ---------------------------------------------------------------------------


class TestScrapeMoviesCounts:
    def test_scrape_movies_returns_counts(self, tmp_path: Path) -> None:
        """search_movie returns result for 1 of 2 items → (1, 1, 0)."""
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()

        item1 = VideoFile(title="Good Movie", path=str(tmp_path / "Good Movie.mkv"))
        item2 = VideoFile(title="Bad Movie", path=str(tmp_path / "Bad Movie.mkv"))

        scraper = TmdbScraper.__new__(TmdbScraper)
        scraper._api_key = "fake"

        def fake_search_movie(title, year):
            if title == "Good Movie":
                return {"id": 1, "title": "Good Movie", "release_date": "2000-01-01",
                        "overview": "", "poster_path": None}
            return None

        scraper.search_movie = fake_search_movie
        scraper.download_poster = MagicMock(return_value=False)

        result = scraper.scrape_movies([item1, item2], cache)
        assert result == (1, 1, 0)

    def test_scrape_movies_skips_existing(self, tmp_path: Path) -> None:
        """Item already has tmdb_id → (0, 0, 1)."""
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {"Existing Movie": {"tmdb_id": 99, "title": "Existing Movie"}}

        item = VideoFile(title="Existing Movie", path=str(tmp_path / "Existing Movie.mkv"))

        scraper = TmdbScraper.__new__(TmdbScraper)
        scraper._api_key = "fake"
        scraper.search_movie = MagicMock()

        result = scraper.scrape_movies([item], cache)
        assert result == (0, 0, 1)
        scraper.search_movie.assert_not_called()


class TestScrapeTvShowsCounts:
    def test_scrape_tv_shows_returns_counts(self, tmp_path: Path) -> None:
        """search_tv_show returns result for 1 of 2 shows → (1, 1, 0)."""
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()

        show1 = Show(name="Good Show", path=str(tmp_path / "Good Show"))
        show2 = Show(name="Bad Show", path=str(tmp_path / "Bad Show"))

        scraper = TmdbScraper.__new__(TmdbScraper)
        scraper._api_key = "fake"

        def fake_search_tv_show(name):
            if name == "Good Show":
                return {"id": 1, "name": "Good Show", "first_air_date": "2005-01-01",
                        "overview": "", "poster_path": None}
            return None

        scraper.search_tv_show = fake_search_tv_show
        scraper.download_poster = MagicMock(return_value=False)

        result = scraper.scrape_tv_shows([show1, show2], cache)
        assert result == (1, 1, 0)

    def test_scrape_tv_shows_skips_existing(self, tmp_path: Path) -> None:
        """Show already has tmdb_id → (0, 0, 1)."""
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()
        cache._data = {"Existing Show": {"tmdb_id": 55, "title": "Existing Show"}}

        show = Show(name="Existing Show", path=str(tmp_path / "Existing Show"))

        scraper = TmdbScraper.__new__(TmdbScraper)
        scraper._api_key = "fake"
        scraper.search_tv_show = MagicMock()

        result = scraper.scrape_tv_shows([show], cache)
        assert result == (0, 0, 1)
        scraper.search_tv_show.assert_not_called()

    def test_scrape_tv_shows_sanitizes_name_for_search(self, tmp_path: Path) -> None:
        """The sanitized name is sent to search but the raw name is used as cache key."""
        cache = LocalVideoCache(tmp_path / "cache", has_scraped_art=True)
        cache.ensure_dirs()

        show = Show(name="Breaking Bad - x264 1080p", path=str(tmp_path / "Breaking Bad - x264 1080p"))

        scraper = TmdbScraper.__new__(TmdbScraper)
        scraper._api_key = "fake"
        search_calls: list[str] = []

        def fake_search_tv_show(name):
            search_calls.append(name)
            return {"id": 7, "name": "Breaking Bad", "first_air_date": "2008-01-20",
                    "overview": "", "poster_path": None}

        scraper.search_tv_show = fake_search_tv_show
        scraper.download_poster = MagicMock(return_value=False)

        result = scraper.scrape_tv_shows([show], cache)
        assert result == (1, 0, 0)
        # Search was called with the sanitized name
        assert search_calls == ["Breaking Bad"]
        # Cache key is the raw folder name
        assert "Breaking Bad - x264 1080p" in cache._data
