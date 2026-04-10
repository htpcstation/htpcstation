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
    LocalVideoLibrary,
    Season,
    SeasonListModel,
    Show,
    ShowListModel,
    VideoFile,
    VideoListModel,
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
